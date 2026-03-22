"""Current Loop Tuning tab.

PI gain read/write, symmetric square-wave perturbation, and test harness
control for step response analysis of the current controller.
Supports both OM_FORCE_CURRENT (use case 4.5.15.6) and velocity-
override (use case 4.5.15.5) test modes.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

_MONO = QFont()
_MONO.setStyleHint(QFont.Monospace)
_MONO.setPointSize(10)


class CurrentLoopTab(QWidget):
    """Tab for current loop PI tuning with step response capture."""

    read_gains_requested = pyqtSignal(str)             # axis
    set_gains_requested = pyqtSignal(float, float)     # kp, ki
    enter_test_requested = pyqtSignal(str, float)       # mode, velocity_rpm
    exit_test_requested = pyqtSignal()
    start_perturbation_requested = pyqtSignal(str, float, float)  # axis, amplitude, halfperiod
    stop_perturbation_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_gains_panel())
        layout.addWidget(self._build_test_harness_panel())
        layout.addWidget(self._build_perturbation_panel())
        layout.addStretch()

        self._connect_internal()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_gains_panel(self) -> QGroupBox:
        grp = QGroupBox("PI Gains")
        layout = QVBoxLayout(grp)

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

        layout.addSpacing(8)

        set_layout = QFormLayout()
        self._kp_spin = QDoubleSpinBox()
        self._kp_spin.setRange(0.0, 100.0)
        self._kp_spin.setDecimals(4)
        self._kp_spin.setSingleStep(0.1)
        self._kp_spin.setSuffix("  V/A")
        self._kp_spin.setValue(0.0)

        self._ki_spin = QDoubleSpinBox()
        self._ki_spin.setRange(0.0, 100000.0)
        self._ki_spin.setDecimals(1)
        self._ki_spin.setSingleStep(100.0)
        self._ki_spin.setSuffix("  V/A/s")
        self._ki_spin.setValue(0.0)

        set_layout.addRow("New Kp:", self._kp_spin)
        set_layout.addRow("New Ki:", self._ki_spin)
        layout.addLayout(set_layout)

        self._set_gains_btn = QPushButton("Set Gains")
        layout.addWidget(self._set_gains_btn)

        return grp

    def _build_test_harness_panel(self) -> QGroupBox:
        grp = QGroupBox("Test Harness")
        layout = QVBoxLayout(grp)

        self._mode_group = QButtonGroup(self)
        self._radio_vel_override = QRadioButton("Under velocity control")
        self._radio_force_current = QRadioButton("Force current (no velocity loop)")
        self._radio_force_current.setChecked(True)
        self._mode_group.addButton(self._radio_vel_override, 0)
        self._mode_group.addButton(self._radio_force_current, 1)
        layout.addWidget(self._radio_vel_override)

        vel_row = QHBoxLayout()
        vel_row.addSpacing(24)
        self._vel_cmd_label = QLabel("Speed:")
        vel_row.addWidget(self._vel_cmd_label)
        self._vel_cmd_spin = QDoubleSpinBox()
        self._vel_cmd_spin.setRange(-6000.0, 6000.0)
        self._vel_cmd_spin.setValue(500.0)
        self._vel_cmd_spin.setDecimals(0)
        self._vel_cmd_spin.setSingleStep(100.0)
        self._vel_cmd_spin.setSuffix(" RPM")
        vel_row.addWidget(self._vel_cmd_spin)
        vel_row.addStretch()
        layout.addLayout(vel_row)

        layout.addWidget(self._radio_force_current)

        layout.addSpacing(4)

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

        motor_layout = QHBoxLayout()
        motor_layout.addWidget(QLabel("State:"))
        self._state_label = QLabel("--")
        self._state_label.setFont(_MONO)
        motor_layout.addWidget(self._state_label)
        motor_layout.addSpacing(16)
        motor_layout.addWidget(QLabel("Speed:"))
        self._speed_label = QLabel("--")
        self._speed_label.setFont(_MONO)
        motor_layout.addWidget(self._speed_label)
        motor_layout.addStretch()
        layout.addLayout(motor_layout)

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

        self._amplitude_spin = QDoubleSpinBox()
        self._amplitude_spin.setRange(0.0, 50.0)
        self._amplitude_spin.setValue(0.0)
        self._amplitude_spin.setDecimals(3)
        self._amplitude_spin.setSingleStep(0.1)
        self._amplitude_spin.setSuffix("  A")
        form.addRow("Amplitude:", self._amplitude_spin)

        self._halfperiod_spin = QDoubleSpinBox()
        self._halfperiod_spin.setRange(0.0, 500.0)
        self._halfperiod_spin.setValue(0.0)
        self._halfperiod_spin.setDecimals(2)
        self._halfperiod_spin.setSingleStep(0.5)
        self._halfperiod_spin.setSuffix("  ms")
        form.addRow("Half-period:", self._halfperiod_spin)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        self._start_perturb_btn = QPushButton("Start")
        self._stop_perturb_btn = QPushButton("Stop")
        btn_layout.addWidget(self._start_perturb_btn)
        btn_layout.addWidget(self._stop_perturb_btn)
        layout.addLayout(btn_layout)

        return grp

    # ── Internal signal wiring ────────────────────────────────────────

    def _connect_internal(self) -> None:
        self._read_gains_btn.clicked.connect(self._on_read_gains)
        self._set_gains_btn.clicked.connect(self._on_set_gains)
        self._enter_test_btn.clicked.connect(self._on_enter_test)
        self._radio_vel_override.toggled.connect(self._on_mode_toggled)
        self._on_mode_toggled(self._radio_vel_override.isChecked())
        self._exit_test_btn.clicked.connect(
            lambda: self.exit_test_requested.emit(),
        )
        self._start_perturb_btn.clicked.connect(self._on_start_perturbation)
        self._stop_perturb_btn.clicked.connect(
            lambda: self.stop_perturbation_requested.emit(),
        )

    def _on_read_gains(self) -> None:
        self.read_gains_requested.emit(self._axis_combo.currentText())

    def _on_set_gains(self) -> None:
        self.set_gains_requested.emit(
            self._kp_spin.value(), self._ki_spin.value(),
        )

    def _on_mode_toggled(self, vel_checked: bool) -> None:
        self._vel_cmd_label.setVisible(vel_checked)
        self._vel_cmd_spin.setVisible(vel_checked)

    def _on_enter_test(self) -> None:
        if self._radio_force_current.isChecked():
            self.enter_test_requested.emit("force_current", 0.0)
        else:
            self.enter_test_requested.emit(
                "velocity_override", self._vel_cmd_spin.value(),
            )

    def _on_start_perturbation(self) -> None:
        self.start_perturbation_requested.emit(
            self._axis_combo.currentText(),
            self._amplitude_spin.value(),
            self._halfperiod_spin.value(),
        )

    # ── Public interface for MainWindow ───────────────────────────────

    def set_connected(self, connected: bool) -> None:
        self._read_gains_btn.setEnabled(connected)
        self._set_gains_btn.setEnabled(connected)
        self._kp_spin.setEnabled(connected)
        self._ki_spin.setEnabled(connected)

        self._radio_vel_override.setEnabled(connected)
        self._radio_force_current.setEnabled(connected)
        self._vel_cmd_spin.setEnabled(connected)
        self._enter_test_btn.setEnabled(connected)
        self._exit_test_btn.setEnabled(connected)

        self._axis_combo.setEnabled(connected)
        self._amplitude_spin.setEnabled(connected)
        self._halfperiod_spin.setEnabled(connected)
        self._start_perturb_btn.setEnabled(connected)
        self._stop_perturb_btn.setEnabled(connected)

    def on_connected(self, session) -> None:
        self._mode_label.setText("--")
        self._guard_label.setText("Inactive")

        defaults = session.current.get_default_perturbation()
        self._amplitude_spin.setValue(defaults["amplitude_a"])
        self._halfperiod_spin.setValue(defaults["halfperiod_ms"])

    def on_speed_read(self, rpm: float, state: str) -> None:
        self._state_label.setText(state)
        if state in ("RUNNING", "TEST_ENABLE", "STOPPING"):
            if rpm >= 0:
                self._speed_label.setText(f"{rpm:.0f} RPM (FWD)")
            else:
                self._speed_label.setText(f"{rpm:.0f} RPM (REV)")
        else:
            self._speed_label.setText("--")

    def on_disconnected(self) -> None:
        self._mode_label.setText("--")
        self._guard_label.setText("--")
        self._state_label.setText("--")
        self._speed_label.setText("--")
        self._cur_kp_label.setText("--")
        self._cur_ki_label.setText("--")
        self._kp_spin.setValue(0.0)
        self._ki_spin.setValue(0.0)
        self._amplitude_spin.setValue(0.0)
        self._halfperiod_spin.setValue(0.0)

    def on_gains_read(self, gains) -> None:
        self._cur_kp_label.setText(f"{gains.kp:.4f} {gains.kp_units}")
        self._cur_ki_label.setText(f"{gains.ki:.2f} {gains.ki_units}")
        self._kp_spin.setValue(gains.kp)
        self._ki_spin.setValue(gains.ki)

    def on_gains_set(self, result) -> None:
        self._cur_kp_label.setText(f"{result.kp:.4f} {result.kp_units}")
        self._cur_ki_label.setText(f"{result.ki:.2f} {result.ki_units}")

    def on_test_mode_entered(self, mode_name: str) -> None:
        self._mode_label.setText(mode_name)
        self._guard_label.setText("Active")

    def on_test_mode_exited(self) -> None:
        self._mode_label.setText("NORMAL")
        self._guard_label.setText("Inactive")

    def on_perturbation_started(self) -> None:
        self._start_perturb_btn.setEnabled(False)
        self._stop_perturb_btn.setEnabled(True)

    def on_perturbation_stopped(self) -> None:
        self._start_perturb_btn.setEnabled(True)

    def current_axis(self) -> str:
        return self._axis_combo.currentText()

    # ── Settings persistence helpers ──────────────────────────────────

    def save_settings(self, settings) -> None:
        settings.setValue("current/axis", self._axis_combo.currentText())
        settings.setValue("current/amplitude", self._amplitude_spin.value())
        settings.setValue("current/halfperiod", self._halfperiod_spin.value())
        settings.setValue("current/velocity_cmd", self._vel_cmd_spin.value())
        settings.setValue(
            "current/mode",
            "velocity" if self._radio_vel_override.isChecked() else "force",
        )

    def restore_settings(self, settings) -> None:
        axis = settings.value("current/axis", "")
        if axis:
            idx = self._axis_combo.findText(axis)
            if idx >= 0:
                self._axis_combo.setCurrentIndex(idx)

        amp = settings.value("current/amplitude", type=float)
        if amp:
            self._amplitude_spin.setValue(amp)

        hp = settings.value("current/halfperiod", type=float)
        if hp:
            self._halfperiod_spin.setValue(hp)

        vel = settings.value("current/velocity_cmd", type=float)
        if vel:
            self._vel_cmd_spin.setValue(vel)

        mode = settings.value("current/mode", "")
        if mode == "velocity":
            self._radio_vel_override.setChecked(True)
        elif mode == "force":
            self._radio_force_current.setChecked(True)
