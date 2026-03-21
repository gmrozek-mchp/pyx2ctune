"""Background worker for serial operations.

All mctoolbox library calls that touch the serial port run on a single
worker thread so the GUI stays responsive and UART access is serialized.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QMutex, QWaitCondition

from pymcaf.constants import ForceState


class Command(Enum):
    CONNECT = auto()
    DISCONNECT = auto()
    READ_GAINS = auto()
    SET_GAINS = auto()
    ENTER_TEST_MODE = auto()
    ENTER_VELOCITY_OVERRIDE_MODE = auto()
    EXIT_TEST_MODE = auto()
    START_PERTURBATION = auto()
    STOP_PERTURBATION = auto()
    CONFIGURE_SCOPE = auto()
    CAPTURE = auto()
    READ_VELOCITY_GAINS = auto()
    SET_VELOCITY_GAINS = auto()
    SET_VELOCITY_COMMAND = auto()
    START_VELOCITY_PERTURBATION = auto()
    STOP_VELOCITY_PERTURBATION = auto()
    ENTER_FORCE_VOLTAGE_MODE = auto()
    SET_OVERRIDES = auto()
    SET_COMMUTATION_FREQ = auto()
    SET_DQ_CURRENT = auto()
    SET_DQ_VOLTAGE = auto()
    FORCE_STATE = auto()
    READ_HARNESS_STATUS = auto()
    READ_MEASURED_SPEED = auto()
    CAPTURE_CONTINUOUS_START = auto()
    CAPTURE_CONTINUOUS_STOP = auto()
    _CONTINUOUS_FRAME = auto()


@dataclass
class WorkItem:
    command: Command
    kwargs: dict


class SessionWorker(QObject):
    """Runs mctoolbox operations on a background thread.

    The main window posts commands via submit(); results arrive as signals.
    """

    # Result signals
    connected = pyqtSignal(object)          # TuningSession
    disconnected = pyqtSignal()
    gains_read = pyqtSignal(object)         # CurrentGains
    gains_set = pyqtSignal(object)          # CurrentGains
    velocity_gains_read = pyqtSignal(object)   # VelocityGains
    velocity_gains_set = pyqtSignal(object)    # VelocityGains
    velocity_command_set = pyqtSignal()
    velocity_perturbation_started = pyqtSignal()
    velocity_perturbation_stopped = pyqtSignal()
    force_voltage_entered = pyqtSignal(str)   # mode name
    overrides_applied = pyqtSignal()
    commutation_freq_set = pyqtSignal()
    dq_current_set = pyqtSignal()
    dq_voltage_set = pyqtSignal()
    state_forced = pyqtSignal()
    harness_status_read = pyqtSignal(str, int)  # mode_name, overrides
    measured_speed_read = pyqtSignal(float, str)   # RPM, state_name
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

    capture_started = pyqtSignal()
    capture_cancelled = pyqtSignal()

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
        self._capture_abort = threading.Event()

    @property
    def session(self):
        return self._session

    def submit(self, command: Command, **kwargs: Any) -> None:
        self._mutex.lock()
        self._queue.append(WorkItem(command, kwargs))
        self._condition.wakeOne()
        self._mutex.unlock()

    def cancel_capture(self) -> None:
        """Cancel a pending single capture (thread-safe)."""
        self._capture_abort.set()

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

            is_bg = item.command in (
                Command._CONTINUOUS_FRAME, Command.CAPTURE,
                Command.READ_MEASURED_SPEED,
            )
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
        elif cmd == Command.ENTER_VELOCITY_OVERRIDE_MODE:
            self._do_enter_velocity_override_mode(**kw)
        elif cmd == Command.EXIT_TEST_MODE:
            self._do_exit_test_mode()
        elif cmd == Command.START_PERTURBATION:
            self._do_start_perturbation(**kw)
        elif cmd == Command.STOP_PERTURBATION:
            self._do_stop_perturbation()
        elif cmd == Command.READ_VELOCITY_GAINS:
            self._do_read_velocity_gains()
        elif cmd == Command.SET_VELOCITY_GAINS:
            self._do_set_velocity_gains(**kw)
        elif cmd == Command.SET_VELOCITY_COMMAND:
            self._do_set_velocity_command(**kw)
        elif cmd == Command.START_VELOCITY_PERTURBATION:
            self._do_start_velocity_perturbation(**kw)
        elif cmd == Command.STOP_VELOCITY_PERTURBATION:
            self._do_stop_velocity_perturbation()
        elif cmd == Command.ENTER_FORCE_VOLTAGE_MODE:
            self._do_enter_force_voltage_mode()
        elif cmd == Command.SET_OVERRIDES:
            self._do_set_overrides(**kw)
        elif cmd == Command.SET_COMMUTATION_FREQ:
            self._do_set_commutation_freq(**kw)
        elif cmd == Command.SET_DQ_CURRENT:
            self._do_set_dq_current(**kw)
        elif cmd == Command.SET_DQ_VOLTAGE:
            self._do_set_dq_voltage(**kw)
        elif cmd == Command.FORCE_STATE:
            self._do_force_state(**kw)
        elif cmd == Command.READ_HARNESS_STATUS:
            self._do_read_harness_status()
        elif cmd == Command.READ_MEASURED_SPEED:
            self._do_read_measured_speed()
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
        from mctoolbox.mcaf.session import TuningSession

        self.status.emit(f"Connecting to {port}...")
        session = TuningSession.from_x2cscope(
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
            self.status.emit("Stopping motor and disconnecting...")
            try:
                self._session.test_harness.exit_test_mode()
            except Exception:
                pass
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

    def _do_enter_velocity_override_mode(self, velocity_rpm: float = 0.0) -> None:
        self.status.emit(f"Entering velocity override ({velocity_rpm:.0f} RPM)...")
        th = self._session.test_harness
        th.enable_guard()
        th.set_override_flags(velocity_command=True)
        self._session.velocity.set_velocity_command(velocity_rpm)
        th.force_state(ForceState.RUN)
        mode = th.get_operating_mode()
        self.status.emit(
            f"Test mode: {mode.name} (vel override, {velocity_rpm:.0f} RPM)"
        )
        self.test_mode_entered.emit(f"{mode.name} (vel override)")

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

    # ── Velocity commands ────────────────────────────────────────────

    def _do_read_velocity_gains(self) -> None:
        self.status.emit("Reading velocity gains...")
        gains = self._session.velocity.get_gains()
        self.status.emit(
            f"Kwp={gains.kp:.6f} {gains.kp_units} (Q{gains.kp_shift})  "
            f"Kwi={gains.ki:.4f} {gains.ki_units} (Q{gains.ki_shift})"
        )
        self.velocity_gains_read.emit(gains)

    def _do_set_velocity_gains(self, kp: float, ki: float) -> None:
        self.status.emit("Setting velocity gains...")
        result = self._session.velocity.set_gains(kp=kp, ki=ki)
        self.status.emit(
            f"Set Kwp={result.kp:.6f} (Q{result.kp_shift})  "
            f"Kwi={result.ki:.4f} (Q{result.ki_shift})"
        )
        self.velocity_gains_set.emit(result)

    def _do_set_velocity_command(self, rpm: float) -> None:
        self.status.emit(f"Setting velocity command: {rpm:.1f} RPM...")
        self._session.velocity.set_velocity_command(rpm)
        self.status.emit(f"Velocity command: {rpm:.1f} RPM")
        self.velocity_command_set.emit()

    def _do_start_velocity_perturbation(self, amplitude_rpm: float,
                                        halfperiod_ms: float) -> None:
        self.status.emit("Starting velocity perturbation...")
        self._session.velocity.setup_velocity_perturbation(
            amplitude_rpm=amplitude_rpm, halfperiod_ms=halfperiod_ms,
        )
        self.status.emit(
            f"Velocity perturbation: {amplitude_rpm:.1f} RPM, "
            f"T/2={halfperiod_ms:.1f} ms"
        )
        self.velocity_perturbation_started.emit()

    def _do_stop_velocity_perturbation(self) -> None:
        try:
            self._session.velocity.stop_perturbation()
        except Exception:
            pass
        self.status.emit("Velocity perturbation stopped")
        self.velocity_perturbation_stopped.emit()

    # ── Open-loop / harness commands ──────────────────────────────────

    def _do_enter_force_voltage_mode(self) -> None:
        self.status.emit("Entering force voltage DQ mode...")
        self._session.test_harness.enter_force_voltage_mode()
        mode = self._session.test_harness.get_operating_mode()
        self.status.emit(f"Test mode: {mode.name}")
        self.force_voltage_entered.emit(mode.name)
        self.test_mode_entered.emit(mode.name)

    def _do_set_overrides(self, flags: dict) -> None:
        self.status.emit("Applying override flags...")
        self._session.test_harness.set_override_flags(**flags)
        self.status.emit("Override flags applied")
        self.overrides_applied.emit()

    def _do_set_commutation_freq(self, rpm: float) -> None:
        self.status.emit(f"Setting commutation frequency: {rpm:.1f} RPM...")
        counts = self._session.test_harness.set_commutation_frequency_rpm(rpm)
        self.status.emit(f"Commutation frequency: {rpm:.1f} RPM ({counts} counts)")
        self.commutation_freq_set.emit()

    def _do_set_dq_current(self, d: float, q: float) -> None:
        self.status.emit(f"Setting dq current: d={d:.3f} A, q={q:.3f} A...")
        self._session.test_harness.set_dq_current_amps(d, q)
        self.status.emit(f"DQ current: d={d:.3f} A, q={q:.3f} A")
        self.dq_current_set.emit()

    def _do_set_dq_voltage(self, d: float, q: float) -> None:
        self.status.emit(f"Setting dq voltage: d={d:.2f} V, q={q:.2f} V...")
        self._session.test_harness.set_dq_voltage_volts(d, q)
        self.status.emit(f"DQ voltage: d={d:.2f} V, q={q:.2f} V")
        self.dq_voltage_set.emit()

    def _do_force_state(self, transition: int) -> None:
        name = ForceState(transition).name
        self.status.emit(f"Forcing state: {name}...")
        self._session.test_harness.force_state(transition)
        self.status.emit(f"State forced: {name}")
        self.state_forced.emit()

    def _do_read_harness_status(self) -> None:
        self.status.emit("Reading harness status...")
        mode = self._session.test_harness.get_operating_mode()
        overrides = self._session.test_harness.get_overrides()
        self.status.emit(
            f"Mode: {mode.name}, Overrides: 0x{overrides:04X}",
        )
        self.harness_status_read.emit(mode.name, overrides)

    def _do_read_measured_speed(self) -> None:
        rpm = self._session.velocity.get_measured_velocity()
        state = self._session.test_harness.get_motor_state()
        self.measured_speed_read.emit(rpm, state.name)

    # ── Scope commands ────────────────────────────────────────────────

    def _do_configure_scope(self, view: str, sample_time: int = 1,
                            trigger: bool = True,
                            trigger_level: float = 0) -> None:
        self.status.emit(f"Configuring scope ({view})...")
        self._session.capture.configure_view(
            view=view, sample_time=sample_time,
            trigger=trigger, trigger_level=trigger_level,
        )
        trig_str = f"trigger={'on' if trigger else 'off'}"
        self.status.emit(f"Scope configured: {view} ({trig_str})")
        self.scope_configured.emit()

    def _do_capture(self, timeout: float = 10.0) -> None:
        from mctoolbox.analysis import compute_metrics

        self._capture_abort.clear()
        self.capture_started.emit()
        self.status.emit("Waiting for trigger...")
        try:
            response = self._session.capture.capture_frame(
                timeout=timeout, abort_event=self._capture_abort,
            )
        except InterruptedError:
            self.status.emit("Capture cancelled")
            self.capture_cancelled.emit()
            return
        metrics = compute_metrics(response)
        self.status.emit(
            f"Captured {len(response.measured)} samples  "
            f"OS={metrics.overshoot:.1%}  Tr={metrics.rise_time_us:.0f}\u00b5s"
        )
        self.capture_done.emit(response, metrics)

    def _do_start_continuous(self, timeout: float = 10.0) -> None:
        """Begin cooperative continuous capture."""
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

        from mctoolbox.analysis import compute_metrics

        self.capture_started.emit()
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
