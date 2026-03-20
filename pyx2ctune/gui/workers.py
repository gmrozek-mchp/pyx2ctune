"""Background worker for serial operations.

All pyx2ctune library calls that touch the serial port run on a single
worker thread so the GUI stays responsive and UART access is serialized.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QMutex, QWaitCondition


class Command(Enum):
    CONNECT = auto()
    DISCONNECT = auto()
    READ_GAINS = auto()
    SET_GAINS = auto()
    ENTER_TEST_MODE = auto()
    EXIT_TEST_MODE = auto()
    START_PERTURBATION = auto()
    STOP_PERTURBATION = auto()
    CONFIGURE_SCOPE = auto()
    CAPTURE = auto()
    CAPTURE_CONTINUOUS_START = auto()
    CAPTURE_CONTINUOUS_STOP = auto()
    _CONTINUOUS_FRAME = auto()


@dataclass
class WorkItem:
    command: Command
    kwargs: dict


class SessionWorker(QObject):
    """Runs pyx2ctune operations on a background thread.

    The main window posts commands via submit(); results arrive as signals.
    """

    # Result signals
    connected = pyqtSignal(object)          # TuningSession
    disconnected = pyqtSignal()
    gains_read = pyqtSignal(object)         # CurrentGains
    gains_set = pyqtSignal(object)          # CurrentGains
    test_mode_entered = pyqtSignal(str)     # operating mode name
    test_mode_exited = pyqtSignal()
    perturbation_started = pyqtSignal()
    perturbation_stopped = pyqtSignal()
    scope_configured = pyqtSignal()
    capture_done = pyqtSignal(object, object)  # StepResponse, StepMetrics
    continuous_started = pyqtSignal()
    continuous_stopped = pyqtSignal()
    error = pyqtSignal(str, str)            # (command_name, error_message)
    status = pyqtSignal(str)                # status bar text
    busy_changed = pyqtSignal(bool)         # True when working

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session = None
        self._queue: list[WorkItem] = []
        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._running = True
        self._continuous_stop = threading.Event()
        self._continuous_active = False
        self._continuous_frame_count = 0
        self._continuous_timeout = 10.0

    @property
    def session(self):
        return self._session

    def submit(self, command: Command, **kwargs: Any) -> None:
        self._mutex.lock()
        self._queue.append(WorkItem(command, kwargs))
        self._condition.wakeOne()
        self._mutex.unlock()

    def request_stop_continuous(self) -> None:
        """Signal the continuous capture loop to stop (thread-safe)."""
        self._continuous_stop.set()

    def stop(self) -> None:
        self._mutex.lock()
        self._running = False
        self._condition.wakeOne()
        self._mutex.unlock()

    @pyqtSlot()
    def run(self) -> None:
        """Main loop -- waits for work items and executes them."""
        while True:
            self._mutex.lock()
            while self._running and not self._queue:
                self._condition.wait(self._mutex)
            if not self._running and not self._queue:
                self._mutex.unlock()
                break
            item = self._queue.pop(0)
            self._mutex.unlock()

            is_bg = item.command == Command._CONTINUOUS_FRAME
            if not is_bg:
                self.busy_changed.emit(True)
            try:
                self._dispatch(item)
            except Exception:
                tb = traceback.format_exc()
                self.error.emit(item.command.name, tb)
                if is_bg and self._continuous_active:
                    self._continuous_active = False
                    self.continuous_stopped.emit()
            finally:
                if not is_bg:
                    self.busy_changed.emit(False)

    def _dispatch(self, item: WorkItem) -> None:
        cmd = item.command
        kw = item.kwargs

        if cmd == Command.CONNECT:
            self._do_connect(**kw)
        elif cmd == Command.DISCONNECT:
            self._do_disconnect()
        elif cmd == Command.READ_GAINS:
            self._do_read_gains(**kw)
        elif cmd == Command.SET_GAINS:
            self._do_set_gains(**kw)
        elif cmd == Command.ENTER_TEST_MODE:
            self._do_enter_test_mode()
        elif cmd == Command.EXIT_TEST_MODE:
            self._do_exit_test_mode()
        elif cmd == Command.START_PERTURBATION:
            self._do_start_perturbation(**kw)
        elif cmd == Command.STOP_PERTURBATION:
            self._do_stop_perturbation()
        elif cmd == Command.CONFIGURE_SCOPE:
            self._do_configure_scope(**kw)
        elif cmd == Command.CAPTURE:
            self._do_capture(**kw)
        elif cmd == Command.CAPTURE_CONTINUOUS_START:
            self._do_start_continuous(**kw)
        elif cmd == Command.CAPTURE_CONTINUOUS_STOP:
            self.request_stop_continuous()
        elif cmd == Command._CONTINUOUS_FRAME:
            self._do_continuous_frame()

    # ── Command implementations ───────────────────────────────────────

    def _do_connect(self, port: str, elf_file: str,
                    baud_rate: int, parameters_json: str | None) -> None:
        from pyx2ctune.connection import TuningSession

        self.status.emit(f"Connecting to {port}...")
        session = TuningSession(
            port=port,
            elf_file=elf_file,
            baud_rate=baud_rate,
            parameters_json=parameters_json or None,
        )
        self._session = session
        self.status.emit(f"Connected to {port}")
        self.connected.emit(session)

    def _do_disconnect(self) -> None:
        if self._session is not None:
            self.status.emit("Disconnecting...")
            self._session.disconnect()
            self._session = None
            self.status.emit("Disconnected")
            self.disconnected.emit()

    def _do_read_gains(self, axis: str = "q") -> None:
        self.status.emit(f"Reading {axis}-axis gains...")
        gains = self._session.current.get_gains(axis=axis)
        self.status.emit(
            f"Kp={gains.kp:.4f} {gains.kp_units} (Q{gains.kp_shift})  "
            f"Ki={gains.ki:.2f} {gains.ki_units} (Q{gains.ki_shift})"
        )
        self.gains_read.emit(gains)

    def _do_set_gains(self, kp: float, ki: float) -> None:
        self.status.emit("Setting gains...")
        result = self._session.current.set_gains(kp=kp, ki=ki)
        self.status.emit(
            f"Set Kp={result.kp:.4f} (Q{result.kp_shift})  "
            f"Ki={result.ki:.2f} (Q{result.ki_shift})"
        )
        self.gains_set.emit(result)

    def _do_enter_test_mode(self) -> None:
        self.status.emit("Entering current test mode...")
        self._session.test_harness.enter_current_test_mode()
        mode = self._session.test_harness.get_operating_mode()
        self.status.emit(f"Test mode: {mode.name}")
        self.test_mode_entered.emit(mode.name)

    def _do_exit_test_mode(self) -> None:
        self.status.emit("Exiting test mode...")
        self._session.test_harness.exit_test_mode()
        self.status.emit("Normal operation")
        self.test_mode_exited.emit()

    def _do_start_perturbation(self, axis: str, amplitude: float,
                               halfperiod: float) -> None:
        self.status.emit("Starting perturbation...")
        self._session.current.setup_step_test(
            axis=axis, amplitude=amplitude, halfperiod=halfperiod,
            units="engineering",
        )
        self.status.emit(
            f"Perturbation: {axis}-axis, {amplitude:.3f} A, T/2={halfperiod:.2f} ms"
        )
        self.perturbation_started.emit()

    def _do_stop_perturbation(self) -> None:
        try:
            self._session.current.stop_perturbation()
        except Exception:
            pass
        self.status.emit("Perturbation stopped")
        self.perturbation_stopped.emit()

    def _do_configure_scope(self, axis: str, sample_time: int) -> None:
        self.status.emit("Configuring scope...")
        self._session.capture.configure_current_loop(
            axis=axis, sample_time=sample_time,
        )
        self.status.emit(f"Scope configured: {axis}-axis")
        self.scope_configured.emit()

    def _do_capture(self, timeout: float = 10.0) -> None:
        from pyx2ctune.analysis import compute_metrics

        self.status.emit("Capturing scope data...")
        response = self._session.capture.capture_frame(timeout=timeout)
        metrics = compute_metrics(response)
        self.status.emit(
            f"Captured {len(response.measured)} samples  "
            f"OS={metrics.overshoot:.1%}  Tr={metrics.rise_time_us:.0f}\u00b5s"
        )
        self.capture_done.emit(response, metrics)

    def _do_start_continuous(self, timeout: float = 10.0) -> None:
        """Begin cooperative continuous capture.

        Clears the stop event, emits the started signal, and queues the
        first frame.  Subsequent frames re-queue themselves so that other
        commands (set gains, etc.) can be interleaved.
        """
        self._continuous_stop.clear()
        self._continuous_active = True
        self._continuous_frame_count = 0
        self._continuous_timeout = timeout
        self.continuous_started.emit()
        self.status.emit("Continuous capture running...")
        self.submit(Command._CONTINUOUS_FRAME)

    def _do_continuous_frame(self) -> None:
        """Capture a single scope frame and re-queue if not stopped."""
        if not self._continuous_active or self._continuous_stop.is_set():
            if self._continuous_active:
                self._continuous_active = False
                self.status.emit(
                    f"Continuous capture stopped "
                    f"({self._continuous_frame_count} frames)"
                )
                self.continuous_stopped.emit()
            return

        from pyx2ctune.analysis import compute_metrics

        try:
            response = self._session.capture.capture_frame(
                timeout=self._continuous_timeout,
                abort_event=self._continuous_stop,
            )
        except InterruptedError:
            self._continuous_active = False
            self.status.emit(
                f"Continuous capture stopped "
                f"({self._continuous_frame_count} frames)"
            )
            self.continuous_stopped.emit()
            return

        metrics = compute_metrics(response)
        self._continuous_frame_count += 1
        self.status.emit(
            f"Frame {self._continuous_frame_count}  "
            f"OS={metrics.overshoot:.1%}  "
            f"Tr={metrics.rise_time_us:.0f}\u00b5s  "
            f"Ts={metrics.settling_time_us:.0f}\u00b5s"
        )
        self.capture_done.emit(response, metrics)

        if not self._continuous_stop.is_set():
            self.submit(Command._CONTINUOUS_FRAME)
        else:
            self._continuous_active = False
            self.status.emit(
                f"Continuous capture stopped "
                f"({self._continuous_frame_count} frames)"
            )
            self.continuous_stopped.emit()
