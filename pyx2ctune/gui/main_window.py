"""Main application window for pyx2ctune GUI."""

from __future__ import annotations

from pathlib import Path

import serial.tools.list_ports
from PyQt5.QtCore import Qt, QSettings, QThread
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from pyx2ctune.gui.plot_widget import PlotWidget
from pyx2ctune.gui.workers import Command, SessionWorker

_MONO = QFont()
_MONO.setStyleHint(QFont.Monospace)
_MONO.setPointSize(10)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pyx2ctune -- Current Loop Tuning")
        self.setMinimumSize(1100, 700)

        self._session = None
        self._settings = QSettings("pyx2ctune", "pyx2ctune")

        self._build_ui()
        self._start_worker()
        self._connect_signals()
        self._set_ui_state(connected=False)
        self._restore_settings()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._build_connection_panel())

        splitter = self._splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._build_gains_panel())
        left_layout.addWidget(self._build_test_harness_panel())
        left_layout.addWidget(self._build_perturbation_panel())
        left_layout.addWidget(self._build_capture_panel())
        left_layout.addStretch()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._plot = PlotWidget()
        right_layout.addWidget(self._plot, stretch=3)
        right_layout.addWidget(self._build_metrics_panel(), stretch=0)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 760])

        root.addWidget(splitter, stretch=1)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _build_connection_panel(self) -> QGroupBox:
        grp = QGroupBox("Connection")
        layout = QGridLayout(grp)

        layout.addWidget(QLabel("Port:"), 0, 0)
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.setMinimumWidth(200)
        layout.addWidget(self._port_combo, 0, 1)

        self._refresh_ports_btn = QPushButton("Refresh")
        self._refresh_ports_btn.setFixedWidth(70)
        layout.addWidget(self._refresh_ports_btn, 0, 2)

        layout.addWidget(QLabel("Baud:"), 0, 3)
        self._baud_spin = QSpinBox()
        self._baud_spin.setRange(9600, 921600)
        self._baud_spin.setValue(115200)
        self._baud_spin.setFixedWidth(90)
        layout.addWidget(self._baud_spin, 0, 4)

        layout.addWidget(QLabel("ELF:"), 1, 0)
        self._elf_edit = QLineEdit()
        self._elf_edit.setPlaceholderText("Path to firmware .elf file")
        layout.addWidget(self._elf_edit, 1, 1, 1, 3)
        self._elf_browse = QPushButton("Browse...")
        self._elf_browse.setFixedWidth(80)
        layout.addWidget(self._elf_browse, 1, 4)

        layout.addWidget(QLabel("Params:"), 2, 0)
        self._params_edit = QLineEdit()
        self._params_edit.setPlaceholderText("Path to parameters.json (optional)")
        layout.addWidget(self._params_edit, 2, 1, 1, 3)
        self._params_browse = QPushButton("Browse...")
        self._params_browse.setFixedWidth(80)
        layout.addWidget(self._params_browse, 2, 4)

        btn_layout = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._disconnect_btn = QPushButton("Disconnect")
        btn_layout.addStretch()
        btn_layout.addWidget(self._connect_btn)
        btn_layout.addWidget(self._disconnect_btn)
        layout.addLayout(btn_layout, 0, 5, 1, 1)

        self._refresh_ports()
        return grp

    def _build_gains_panel(self) -> QGroupBox:
        grp = QGroupBox("PI Gains")
        layout = QVBoxLayout(grp)

        # Current gains readback
        read_layout = QFormLayout()
        self._cur_kp_label = QLabel("--")
        self._cur_kp_label.setFont(_MONO)
        self._cur_ki_label = QLabel("--")
        self._cur_ki_label.setFont(_MONO)
        read_layout.addRow("Kp:", self._cur_kp_label)
        read_layout.addRow("Ki:", self._cur_ki_label)
        layout.addLayout(read_layout)

        self._read_gains_btn = QPushButton("Read Gains from Board")
        layout.addWidget(self._read_gains_btn)

        # Separator
        layout.addSpacing(8)

        # New gains input
        set_layout = QFormLayout()
        self._kp_spin = QDoubleSpinBox()
        self._kp_spin.setRange(0.0, 100.0)
        self._kp_spin.setDecimals(4)
        self._kp_spin.setSingleStep(0.1)
        self._kp_spin.setSuffix("  V/A")
        self._kp_spin.setValue(0.614)

        self._ki_spin = QDoubleSpinBox()
        self._ki_spin.setRange(0.0, 100000.0)
        self._ki_spin.setDecimals(1)
        self._ki_spin.setSingleStep(100.0)
        self._ki_spin.setSuffix("  V/A/s")
        self._ki_spin.setValue(1268.0)

        set_layout.addRow("New Kp:", self._kp_spin)
        set_layout.addRow("New Ki:", self._ki_spin)
        layout.addLayout(set_layout)

        self._set_gains_btn = QPushButton("Set Gains")
        layout.addWidget(self._set_gains_btn)

        return grp

    def _build_test_harness_panel(self) -> QGroupBox:
        grp = QGroupBox("Test Harness")
        layout = QVBoxLayout(grp)

        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Mode:"))
        self._mode_label = QLabel("--")
        self._mode_label.setFont(_MONO)
        status_layout.addWidget(self._mode_label)
        status_layout.addSpacing(16)
        status_layout.addWidget(QLabel("Guard:"))
        self._guard_label = QLabel("--")
        self._guard_label.setFont(_MONO)
        status_layout.addWidget(self._guard_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        btn_layout = QHBoxLayout()
        self._enter_test_btn = QPushButton("Enter Test Mode")
        self._exit_test_btn = QPushButton("Exit Test Mode")
        btn_layout.addWidget(self._enter_test_btn)
        btn_layout.addWidget(self._exit_test_btn)
        layout.addLayout(btn_layout)

        return grp

    def _build_perturbation_panel(self) -> QGroupBox:
        grp = QGroupBox("Perturbation")
        layout = QVBoxLayout(grp)

        form = QFormLayout()
        self._axis_combo = QComboBox()
        self._axis_combo.addItems(["q", "d"])
        form.addRow("Axis:", self._axis_combo)

        self._amplitude_spin = QSpinBox()
        self._amplitude_spin.setRange(1, 32767)
        self._amplitude_spin.setValue(500)
        self._amplitude_spin.setSuffix("  counts")
        form.addRow("Amplitude:", self._amplitude_spin)

        self._halfperiod_spin = QSpinBox()
        self._halfperiod_spin.setRange(1, 10000)
        self._halfperiod_spin.setValue(100)
        self._halfperiod_spin.setSuffix("  PWM cycles")
        form.addRow("Half-period:", self._halfperiod_spin)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        self._start_perturb_btn = QPushButton("Start")
        self._stop_perturb_btn = QPushButton("Stop")
        btn_layout.addWidget(self._start_perturb_btn)
        btn_layout.addWidget(self._stop_perturb_btn)
        layout.addLayout(btn_layout)

        return grp

    def _build_capture_panel(self) -> QGroupBox:
        grp = QGroupBox("Capture")
        layout = QHBoxLayout(grp)
        self._capture_btn = QPushButton("Capture && Analyze")
        self._capture_btn.setMinimumHeight(36)
        font = self._capture_btn.font()
        font.setBold(True)
        self._capture_btn.setFont(font)
        layout.addWidget(self._capture_btn)
        return grp

    def _build_metrics_panel(self) -> QGroupBox:
        grp = QGroupBox("Metrics")
        layout = QGridLayout(grp)

        labels = [
            ("Overshoot:", "_os_label"),
            ("Rise time:", "_tr_label"),
            ("Settling time:", "_ts_label"),
            ("SSE:", "_sse_label"),
            ("Steps detected:", "_steps_label"),
        ]
        for row, (text, attr) in enumerate(labels):
            layout.addWidget(QLabel(text), row, 0)
            lbl = QLabel("--")
            lbl.setFont(_MONO)
            setattr(self, attr, lbl)
            layout.addWidget(lbl, row, 1)

        layout.setColumnStretch(1, 1)
        return grp

    # ── Worker Setup ──────────────────────────────────────────────────

    def _start_worker(self) -> None:
        self._worker = SessionWorker()
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

    def _connect_signals(self) -> None:
        # Connection panel
        self._refresh_ports_btn.clicked.connect(self._refresh_ports)
        self._elf_browse.clicked.connect(self._browse_elf)
        self._params_browse.clicked.connect(self._browse_params)
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn.clicked.connect(self._on_disconnect)

        # Gains
        self._read_gains_btn.clicked.connect(self._on_read_gains)
        self._set_gains_btn.clicked.connect(self._on_set_gains)

        # Test harness
        self._enter_test_btn.clicked.connect(self._on_enter_test)
        self._exit_test_btn.clicked.connect(self._on_exit_test)

        # Perturbation
        self._start_perturb_btn.clicked.connect(self._on_start_perturbation)
        self._stop_perturb_btn.clicked.connect(self._on_stop_perturbation)

        # Capture
        self._capture_btn.clicked.connect(self._on_capture)

        # Worker results
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.gains_read.connect(self._on_gains_read)
        self._worker.gains_set.connect(self._on_gains_set)
        self._worker.test_mode_entered.connect(self._on_test_mode_entered)
        self._worker.test_mode_exited.connect(self._on_test_mode_exited)
        self._worker.perturbation_started.connect(self._on_perturbation_started)
        self._worker.perturbation_stopped.connect(self._on_perturbation_stopped)
        self._worker.capture_done.connect(self._on_capture_done)
        self._worker.error.connect(self._on_error)
        self._worker.status.connect(self._status_bar.showMessage)
        self._worker.busy_changed.connect(self._on_busy_changed)

    # ── UI State ──────────────────────────────────────────────────────

    def _set_ui_state(self, connected: bool) -> None:
        self._port_combo.setEnabled(not connected)
        self._baud_spin.setEnabled(not connected)
        self._elf_edit.setEnabled(not connected)
        self._elf_browse.setEnabled(not connected)
        self._params_edit.setEnabled(not connected)
        self._params_browse.setEnabled(not connected)
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)

        self._read_gains_btn.setEnabled(connected)
        self._set_gains_btn.setEnabled(connected)
        self._enter_test_btn.setEnabled(connected)
        self._exit_test_btn.setEnabled(connected)
        self._start_perturb_btn.setEnabled(connected)
        self._stop_perturb_btn.setEnabled(connected)
        self._capture_btn.setEnabled(connected)

    # ── Slots: Connection ─────────────────────────────────────────────

    def _refresh_ports(self) -> None:
        self._port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in sorted(ports, key=lambda x: x.device):
            desc = f"{p.device}" if not p.description or p.description == "n/a" \
                else f"{p.device} - {p.description}"
            self._port_combo.addItem(desc, p.device)

    def _browse_elf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ELF File", "",
            "ELF Files (*.elf);;All Files (*)",
        )
        if path:
            self._elf_edit.setText(path)

    def _browse_params(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select parameters.json", "",
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            self._params_edit.setText(path)

    def _on_connect(self) -> None:
        port = self._port_combo.currentData() or self._port_combo.currentText()
        elf = self._elf_edit.text().strip()
        if not port or not elf:
            QMessageBox.warning(self, "Missing fields",
                                "Port and ELF file are required.")
            return
        params = self._params_edit.text().strip() or None
        self._connect_btn.setEnabled(False)
        self._worker.submit(
            Command.CONNECT,
            port=port, elf_file=elf,
            baud_rate=self._baud_spin.value(),
            parameters_json=params,
        )

    def _on_disconnect(self) -> None:
        self._worker.submit(Command.DISCONNECT)

    def _on_connected(self, session) -> None:
        self._session = session
        self._set_ui_state(connected=True)
        self._mode_label.setText("--")
        self._guard_label.setText("Inactive")
        self._worker.submit(Command.STOP_PERTURBATION)
        self._worker.submit(Command.EXIT_TEST_MODE)
        self._worker.submit(
            Command.READ_GAINS, axis=self._axis_combo.currentText(),
        )

    def _on_disconnected(self) -> None:
        self._session = None
        self._set_ui_state(connected=False)
        self._mode_label.setText("--")
        self._guard_label.setText("--")
        self._cur_kp_label.setText("--")
        self._cur_ki_label.setText("--")

    # ── Slots: Gains ──────────────────────────────────────────────────

    def _on_read_gains(self) -> None:
        axis = self._axis_combo.currentText()
        self._worker.submit(Command.READ_GAINS, axis=axis)

    def _on_set_gains(self) -> None:
        self._worker.submit(
            Command.SET_GAINS,
            kp=self._kp_spin.value(),
            ki=self._ki_spin.value(),
        )

    def _on_gains_read(self, gains) -> None:
        self._cur_kp_label.setText(
            f"{gains.kp:.4f} {gains.kp_units}  (counts={gains.kp_counts}, Q{gains.kp_shift})"
        )
        self._cur_ki_label.setText(
            f"{gains.ki:.2f} {gains.ki_units}  (counts={gains.ki_counts}, Q{gains.ki_shift})"
        )
        self._kp_spin.setValue(gains.kp)
        self._ki_spin.setValue(gains.ki)

    def _on_gains_set(self, result) -> None:
        self._cur_kp_label.setText(
            f"{result.kp:.4f} {result.kp_units}  (counts={result.kp_counts}, Q{result.kp_shift})"
        )
        self._cur_ki_label.setText(
            f"{result.ki:.2f} {result.ki_units}  (counts={result.ki_counts}, Q{result.ki_shift})"
        )

    # ── Slots: Test Harness ───────────────────────────────────────────

    def _on_enter_test(self) -> None:
        self._worker.submit(Command.ENTER_TEST_MODE)

    def _on_exit_test(self) -> None:
        self._worker.submit(Command.EXIT_TEST_MODE)

    def _on_test_mode_entered(self, mode_name: str) -> None:
        self._mode_label.setText(mode_name)
        self._guard_label.setText("Active")

    def _on_test_mode_exited(self) -> None:
        self._mode_label.setText("NORMAL")
        self._guard_label.setText("Inactive")

    # ── Slots: Perturbation ───────────────────────────────────────────

    def _on_start_perturbation(self) -> None:
        axis = self._axis_combo.currentText()
        self._worker.submit(Command.CONFIGURE_SCOPE,
                            axis=axis, sample_time=1)
        self._worker.submit(
            Command.START_PERTURBATION,
            axis=axis,
            amplitude=self._amplitude_spin.value(),
            halfperiod=self._halfperiod_spin.value(),
        )

    def _on_stop_perturbation(self) -> None:
        self._worker.submit(Command.STOP_PERTURBATION)

    def _on_perturbation_started(self) -> None:
        self._start_perturb_btn.setEnabled(False)
        self._stop_perturb_btn.setEnabled(True)

    def _on_perturbation_stopped(self) -> None:
        self._start_perturb_btn.setEnabled(True)

    # ── Slots: Capture ────────────────────────────────────────────────

    def _on_capture(self) -> None:
        self._capture_btn.setEnabled(False)
        self._worker.submit(Command.CAPTURE, timeout=10.0)

    def _on_capture_done(self, response, metrics) -> None:
        self._plot.update_plot(response, metrics)
        self._capture_btn.setEnabled(True)

        if metrics.n_steps > 0:
            self._os_label.setText(f"{metrics.overshoot:.1%}")
            self._tr_label.setText(f"{metrics.rise_time_us:.0f} \u00b5s")
            self._ts_label.setText(f"{metrics.settling_time_us:.0f} \u00b5s")
            self._sse_label.setText(f"{metrics.steady_state_error:.3f}")
            self._steps_label.setText(str(metrics.n_steps))
        else:
            for lbl in (self._os_label, self._tr_label, self._ts_label,
                        self._sse_label):
                lbl.setText("--")
            self._steps_label.setText("0 (no steps detected)")

    # ── Error / Busy ──────────────────────────────────────────────────

    def _on_error(self, cmd_name: str, message: str) -> None:
        self._status_bar.showMessage(f"Error: {cmd_name}")
        self._set_ui_state(connected=self._session is not None)
        self._capture_btn.setEnabled(self._session is not None)
        QMessageBox.critical(
            self, f"Error: {cmd_name}",
            f"Command {cmd_name} failed:\n\n{message}",
        )

    def _on_busy_changed(self, busy: bool) -> None:
        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    # ── Settings Persistence ─────────────────────────────────────────

    def _save_settings(self) -> None:
        s = self._settings
        s.setValue("port", self._port_combo.currentData() or self._port_combo.currentText())
        s.setValue("elf_file", self._elf_edit.text())
        s.setValue("params_json", self._params_edit.text())
        s.setValue("baud_rate", self._baud_spin.value())
        s.setValue("axis", self._axis_combo.currentText())
        s.setValue("amplitude", self._amplitude_spin.value())
        s.setValue("halfperiod", self._halfperiod_spin.value())
        s.setValue("geometry", self.saveGeometry())
        s.setValue("splitter", self._splitter.saveState() if hasattr(self, "_splitter") else None)

    def _restore_settings(self) -> None:
        s = self._settings

        port = s.value("port", "")
        if port:
            idx = self._port_combo.findData(port)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
            else:
                self._port_combo.setEditText(port)

        elf = s.value("elf_file", "")
        if elf:
            self._elf_edit.setText(elf)

        params = s.value("params_json", "")
        if params:
            self._params_edit.setText(params)

        baud = s.value("baud_rate", type=int)
        if baud:
            self._baud_spin.setValue(baud)

        axis = s.value("axis", "")
        if axis:
            idx = self._axis_combo.findText(axis)
            if idx >= 0:
                self._axis_combo.setCurrentIndex(idx)

        amp = s.value("amplitude", type=int)
        if amp:
            self._amplitude_spin.setValue(amp)

        hp = s.value("halfperiod", type=int)
        if hp:
            self._halfperiod_spin.setValue(hp)

        geom = s.value("geometry")
        if geom:
            self.restoreGeometry(geom)

        splitter_state = s.value("splitter")
        if splitter_state and hasattr(self, "_splitter"):
            self._splitter.restoreState(splitter_state)

    # ── Window Close ──────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._save_settings()
        if self._session is not None:
            self._worker.submit(Command.EXIT_TEST_MODE)
            self._worker.submit(Command.DISCONNECT)
        self._worker.stop()
        self._worker_thread.quit()
        self._worker_thread.wait(3000)
        super().closeEvent(event)
