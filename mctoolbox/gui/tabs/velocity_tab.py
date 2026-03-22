"""Velocity Loop Tuning tab.

PI gain read/write for the velocity controller, velocity command setting,
square-wave velocity perturbation for step response analysis.
Covers use cases 4.5.15.3 and 4.5.15.4.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_MONO = QFont()
_MONO.setStyleHint(QFont.Monospace)
_MONO.setPointSize(10)


class VelocityLoopTab(QWidget):
    """Tab for velocity loop PI tuning with step response capture."""

    read_gains_requested = pyqtSignal()
    set_gains_requested = pyqtSignal(float, float)     # kwp, kwi
    set_velocity_requested = pyqtSignal(float)         # rpm
    enter_test_requested = pyqtSignal(float)          # velocity_rpm
    exit_test_requested = pyqtSignal()
    start_perturbation_requested = pyqtSignal(float, float)  # amplitude_rpm, halfperiod_ms
    stop_perturbation_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_gains_panel())
        layout.addWidget(self._build_command_panel())
        layout.addWidget(self._build_test_harness_panel())
        layout.addWidget(self._build_perturbation_panel())
        layout.addStretch()

        self._connect_internal()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_gains_panel(self) -> QGroupBox:
        grp = QGroupBox("Velocity PI Gains")
        layout = QVBoxLayout(grp)

        read_layout = QFormLayout()
        self._cur_kwp_label = QLabel("--")
        self._cur_kwp_label.setFont(_MONO)
        self._cur_kwi_label = QLabel("--")
        self._cur_kwi_label.setFont(_MONO)
        read_layout.addRow("Kwp:", self._cur_kwp_label)
        read_layout.addRow("Kwi:", self._cur_kwi_label)
        layout.addLayout(read_layout)

        self._read_gains_btn = QPushButton("Read Gains from Board")
        layout.addWidget(self._read_gains_btn)

        layout.addSpacing(8)

        set_layout = QFormLayout()
        self._kwp_spin = QDoubleSpinBox()
        self._kwp_spin.setRange(0.0, 10.0)
        self._kwp_spin.setDecimals(6)
        self._kwp_spin.setSingleStep(0.001)
        self._kwp_spin.setSuffix("  A/(rad/s)")
        self._kwp_spin.setValue(0.0)

        self._kwi_spin = QDoubleSpinBox()
        self._kwi_spin.setRange(0.0, 1000.0)
        self._kwi_spin.setDecimals(4)
        self._kwi_spin.setSingleStep(0.01)
        self._kwi_spin.setSuffix("  A/rad")
        self._kwi_spin.setValue(0.0)

        set_layout.addRow("New Kwp:", self._kwp_spin)
        set_layout.addRow("New Kwi:", self._kwi_spin)
        layout.addLayout(set_layout)

        self._set_gains_btn = QPushButton("Set Gains")
        layout.addWidget(self._set_gains_btn)

        return grp

    def _build_command_panel(self) -> QGroupBox:
        grp = QGroupBox("Velocity Command")
        layout = QVBoxLayout(grp)

        form = QFormLayout()
        self._velocity_spin = QDoubleSpinBox()
        self._velocity_spin.setRange(-6000.0, 6000.0)
        self._velocity_spin.setValue(0.0)
        self._velocity_spin.setDecimals(1)
        self._velocity_spin.setSingleStep(100.0)
        self._velocity_spin.setSuffix("  RPM")
        form.addRow("Velocity:", self._velocity_spin)
        layout.addLayout(form)

        self._set_velocity_btn = QPushButton("Set Velocity Command")
        layout.addWidget(self._set_velocity_btn)

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
        self._enter_test_btn = QPushButton("Enable Velocity Override")
        self._exit_test_btn = QPushButton("Exit Test Mode")
        btn_layout.addWidget(self._enter_test_btn)
        btn_layout.addWidget(self._exit_test_btn)
        layout.addLayout(btn_layout)

        return grp

    def _build_perturbation_panel(self) -> QGroupBox:
        grp = QGroupBox("Velocity Perturbation")
        layout = QVBoxLayout(grp)

        form = QFormLayout()
        self._amplitude_spin = QDoubleSpinBox()
        self._amplitude_spin.setRange(0.0, 3000.0)
        self._amplitude_spin.setValue(0.0)
        self._amplitude_spin.setDecimals(1)
        self._amplitude_spin.setSingleStep(10.0)
        self._amplitude_spin.setSuffix("  RPM")
        form.addRow("Amplitude:", self._amplitude_spin)

        self._halfperiod_spin = QDoubleSpinBox()
        self._halfperiod_spin.setRange(0.0, 5000.0)
        self._halfperiod_spin.setValue(0.0)
        self._halfperiod_spin.setDecimals(1)
        self._halfperiod_spin.setSingleStep(10.0)
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
        self._read_gains_btn.clicked.connect(
            lambda: self.read_gains_requested.emit(),
        )
        self._set_gains_btn.clicked.connect(self._on_set_gains)
        self._set_velocity_btn.clicked.connect(
            lambda: self.set_velocity_requested.emit(
                self._velocity_spin.value(),
            ),
        )
        self._enter_test_btn.clicked.connect(
            lambda: self.enter_test_requested.emit(
                self._velocity_spin.value(),
            ),
        )
        self._exit_test_btn.clicked.connect(
            lambda: self.exit_test_requested.emit(),
        )
        self._start_perturb_btn.clicked.connect(self._on_start_perturbation)
        self._stop_perturb_btn.clicked.connect(
            lambda: self.stop_perturbation_requested.emit(),
        )

    def _on_set_gains(self) -> None:
        self.set_gains_requested.emit(
            self._kwp_spin.value(), self._kwi_spin.value(),
        )

    def _on_start_perturbation(self) -> None:
        self.start_perturbation_requested.emit(
            self._amplitude_spin.value(),
            self._halfperiod_spin.value(),
        )

    # ── Public interface for MainWindow ───────────────────────────────

    def set_connected(self, connected: bool) -> None:
        self._read_gains_btn.setEnabled(connected)
        self._set_gains_btn.setEnabled(connected)
        self._kwp_spin.setEnabled(connected)
        self._kwi_spin.setEnabled(connected)

        self._velocity_spin.setEnabled(connected)
        self._set_velocity_btn.setEnabled(connected)

        self._enter_test_btn.setEnabled(connected)
        self._exit_test_btn.setEnabled(connected)

        self._amplitude_spin.setEnabled(connected)
        self._halfperiod_spin.setEnabled(connected)
        self._start_perturb_btn.setEnabled(connected)
        self._stop_perturb_btn.setEnabled(connected)

    def on_connected(self, session) -> None:
        self._mode_label.setText("--")
        self._guard_label.setText("Inactive")

        defaults = session.velocity.get_default_perturbation()
        self._amplitude_spin.setValue(defaults["amplitude_rpm"])
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
        self._cur_kwp_label.setText("--")
        self._cur_kwi_label.setText("--")
        self._kwp_spin.setValue(0.0)
        self._kwi_spin.setValue(0.0)
        self._velocity_spin.setValue(0.0)
        self._amplitude_spin.setValue(0.0)
        self._halfperiod_spin.setValue(0.0)

    def on_gains_read(self, gains) -> None:
        self._cur_kwp_label.setText(f"{gains.kp:.6f} {gains.kp_units}")
        self._cur_kwi_label.setText(f"{gains.ki:.4f} {gains.ki_units}")
        self._kwp_spin.setValue(gains.kp)
        self._kwi_spin.setValue(gains.ki)

    def on_gains_set(self, result) -> None:
        self._cur_kwp_label.setText(f"{result.kp:.6f} {result.kp_units}")
        self._cur_kwi_label.setText(f"{result.ki:.4f} {result.ki_units}")

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

    # ── Settings persistence ──────────────────────────────────────────

    def save_settings(self, settings) -> None:
        settings.setValue("velocity/amplitude", self._amplitude_spin.value())
        settings.setValue("velocity/halfperiod", self._halfperiod_spin.value())
        settings.setValue("velocity/command", self._velocity_spin.value())

    def restore_settings(self, settings) -> None:
        amp = settings.value("velocity/amplitude", type=float)
        if amp:
            self._amplitude_spin.setValue(amp)
        hp = settings.value("velocity/halfperiod", type=float)
        if hp:
            self._halfperiod_spin.setValue(hp)
        vel = settings.value("velocity/command", type=float)
        if vel:
            self._velocity_spin.setValue(vel)
