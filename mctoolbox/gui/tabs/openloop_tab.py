"""Open Loop commissioning tab.

Provides direct access to MCAF test harness operating modes,
override flags, commutation override, DQ current/voltage commands,
and forced state transitions for motor commissioning.

All settings are in real-world engineering units (A, V, RPM).
Conversion to/from Q15 counts happens in the worker layer.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox,
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


class OpenLoopTab(QWidget):
    """Tab for open-loop commissioning and test harness control."""

    force_state_requested = pyqtSignal(int)                    # ForceState value
    set_overrides_requested = pyqtSignal(dict)                 # {flag_name: bool}
    set_commutation_freq_requested = pyqtSignal(float)         # RPM
    set_dq_current_requested = pyqtSignal(float, float)        # d, q in Amps
    set_dq_voltage_requested = pyqtSignal(float, float)        # d, q in Volts
    read_status_requested = pyqtSignal()
    enter_force_voltage_requested = pyqtSignal()
    enter_force_current_requested = pyqtSignal()
    exit_test_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_mode_panel())
        layout.addWidget(self._build_overrides_panel())
        layout.addWidget(self._build_commutation_panel())
        layout.addWidget(self._build_dq_current_panel())
        layout.addWidget(self._build_dq_voltage_panel())
        layout.addWidget(self._build_state_panel())
        layout.addStretch()

        self._connect_internal()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_mode_panel(self) -> QGroupBox:
        grp = QGroupBox("Operating Mode")
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

        layout.addSpacing(4)

        btn_layout = QHBoxLayout()
        self._enter_voltage_btn = QPushButton("Force Voltage DQ")
        self._enter_current_btn = QPushButton("Force Current")
        self._exit_test_btn = QPushButton("Exit Test Mode")
        self._read_status_btn = QPushButton("Refresh")
        self._read_status_btn.setFixedWidth(70)
        btn_layout.addWidget(self._enter_voltage_btn)
        btn_layout.addWidget(self._enter_current_btn)
        btn_layout.addWidget(self._exit_test_btn)
        btn_layout.addWidget(self._read_status_btn)
        layout.addLayout(btn_layout)

        return grp

    def _build_overrides_panel(self) -> QGroupBox:
        grp = QGroupBox("Override Flags")
        layout = QVBoxLayout(grp)

        self._override_checks: dict[str, QCheckBox] = {}
        override_defs = [
            ("velocity_command", "Velocity Command"),
            ("commutation", "Commutation Angle"),
            ("dc_link_compensation", "DC Link Compensation"),
            ("stall_detection", "Stall Detection"),
            ("startup_pause", "Startup Pause"),
            ("flux_control", "Flux Control"),
            ("zero_sequence_modulation", "Zero Sequence Modulation"),
        ]

        row = QHBoxLayout()
        for i, (key, label) in enumerate(override_defs):
            cb = QCheckBox(label)
            self._override_checks[key] = cb
            row.addWidget(cb)
            if (i + 1) % 3 == 0:
                layout.addLayout(row)
                row = QHBoxLayout()
        if row.count() > 0:
            layout.addLayout(row)

        self._apply_overrides_btn = QPushButton("Apply Overrides")
        layout.addWidget(self._apply_overrides_btn)

        return grp

    def _build_commutation_panel(self) -> QGroupBox:
        grp = QGroupBox("Commutation Override")
        layout = QVBoxLayout(grp)

        form = QFormLayout()
        self._omega_spin = QDoubleSpinBox()
        self._omega_spin.setRange(-10000.0, 10000.0)
        self._omega_spin.setValue(0.0)
        self._omega_spin.setDecimals(1)
        self._omega_spin.setSingleStep(10.0)
        self._omega_spin.setSuffix("  RPM")
        form.addRow("ω electrical:", self._omega_spin)
        layout.addLayout(form)

        self._set_omega_btn = QPushButton("Set Commutation Frequency")
        layout.addWidget(self._set_omega_btn)

        return grp

    def _build_dq_current_panel(self) -> QGroupBox:
        grp = QGroupBox("DQ Current Command (OM_FORCE_CURRENT)")
        layout = QVBoxLayout(grp)

        form = QFormLayout()
        self._id_spin = QDoubleSpinBox()
        self._id_spin.setRange(-50.0, 50.0)
        self._id_spin.setValue(0.0)
        self._id_spin.setDecimals(3)
        self._id_spin.setSingleStep(0.1)
        self._id_spin.setSuffix("  A")
        form.addRow("Id:", self._id_spin)

        self._iq_spin = QDoubleSpinBox()
        self._iq_spin.setRange(-50.0, 50.0)
        self._iq_spin.setValue(0.0)
        self._iq_spin.setDecimals(3)
        self._iq_spin.setSingleStep(0.1)
        self._iq_spin.setSuffix("  A")
        form.addRow("Iq:", self._iq_spin)
        layout.addLayout(form)

        self._set_idq_btn = QPushButton("Set DQ Current")
        layout.addWidget(self._set_idq_btn)

        return grp

    def _build_dq_voltage_panel(self) -> QGroupBox:
        grp = QGroupBox("DQ Voltage Command (OM_FORCE_VOLTAGE_DQ)")
        layout = QVBoxLayout(grp)

        form = QFormLayout()
        self._vd_spin = QDoubleSpinBox()
        self._vd_spin.setRange(-100.0, 100.0)
        self._vd_spin.setValue(0.0)
        self._vd_spin.setDecimals(2)
        self._vd_spin.setSingleStep(0.1)
        self._vd_spin.setSuffix("  V")
        form.addRow("Vd:", self._vd_spin)

        self._vq_spin = QDoubleSpinBox()
        self._vq_spin.setRange(-100.0, 100.0)
        self._vq_spin.setValue(0.0)
        self._vq_spin.setDecimals(2)
        self._vq_spin.setSingleStep(0.1)
        self._vq_spin.setSuffix("  V")
        form.addRow("Vq:", self._vq_spin)
        layout.addLayout(form)

        self._set_vdq_btn = QPushButton("Set DQ Voltage")
        layout.addWidget(self._set_vdq_btn)

        return grp

    def _build_state_panel(self) -> QGroupBox:
        grp = QGroupBox("Force State Transition")
        layout = QHBoxLayout(grp)

        self._force_run_btn = QPushButton("Force RUN")
        self._force_stop_btn = QPushButton("Force STOP")
        self._force_stop_now_btn = QPushButton("Force STOP NOW")
        layout.addWidget(self._force_run_btn)
        layout.addWidget(self._force_stop_btn)
        layout.addWidget(self._force_stop_now_btn)

        return grp

    # ── Internal signal wiring ────────────────────────────────────────

    def _connect_internal(self) -> None:
        self._enter_voltage_btn.clicked.connect(
            lambda: self.enter_force_voltage_requested.emit(),
        )
        self._enter_current_btn.clicked.connect(
            lambda: self.enter_force_current_requested.emit(),
        )
        self._exit_test_btn.clicked.connect(
            lambda: self.exit_test_requested.emit(),
        )
        self._read_status_btn.clicked.connect(
            lambda: self.read_status_requested.emit(),
        )
        self._apply_overrides_btn.clicked.connect(self._on_apply_overrides)
        self._set_omega_btn.clicked.connect(
            lambda: self.set_commutation_freq_requested.emit(
                self._omega_spin.value(),
            ),
        )
        self._set_idq_btn.clicked.connect(
            lambda: self.set_dq_current_requested.emit(
                self._id_spin.value(), self._iq_spin.value(),
            ),
        )
        self._set_vdq_btn.clicked.connect(
            lambda: self.set_dq_voltage_requested.emit(
                self._vd_spin.value(), self._vq_spin.value(),
            ),
        )
        self._force_run_btn.clicked.connect(
            lambda: self.force_state_requested.emit(1),
        )
        self._force_stop_btn.clicked.connect(
            lambda: self.force_state_requested.emit(2),
        )
        self._force_stop_now_btn.clicked.connect(
            lambda: self.force_state_requested.emit(3),
        )

    def _on_apply_overrides(self) -> None:
        flags = {
            key: cb.isChecked()
            for key, cb in self._override_checks.items()
        }
        self.set_overrides_requested.emit(flags)

    # ── Public interface for MainWindow ───────────────────────────────

    def set_connected(self, connected: bool) -> None:
        self._enter_voltage_btn.setEnabled(connected)
        self._enter_current_btn.setEnabled(connected)
        self._exit_test_btn.setEnabled(connected)
        self._read_status_btn.setEnabled(connected)

        for cb in self._override_checks.values():
            cb.setEnabled(connected)
        self._apply_overrides_btn.setEnabled(connected)

        self._omega_spin.setEnabled(connected)
        self._set_omega_btn.setEnabled(connected)

        self._id_spin.setEnabled(connected)
        self._iq_spin.setEnabled(connected)
        self._set_idq_btn.setEnabled(connected)

        self._vd_spin.setEnabled(connected)
        self._vq_spin.setEnabled(connected)
        self._set_vdq_btn.setEnabled(connected)

        self._force_run_btn.setEnabled(connected)
        self._force_stop_btn.setEnabled(connected)
        self._force_stop_now_btn.setEnabled(connected)

    def on_connected(self, session) -> None:
        self._mode_label.setText("--")
        self._guard_label.setText("Inactive")

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
        self._id_spin.setValue(0.0)
        self._iq_spin.setValue(0.0)
        self._vd_spin.setValue(0.0)
        self._vq_spin.setValue(0.0)
        self._omega_spin.setValue(0.0)
        for cb in self._override_checks.values():
            cb.setChecked(False)

    def on_test_mode_entered(self, mode_name: str) -> None:
        self._mode_label.setText(mode_name)
        self._guard_label.setText("Active")

    def on_test_mode_exited(self) -> None:
        self._mode_label.setText("NORMAL")
        self._guard_label.setText("Inactive")

    def on_status_read(self, mode_name: str, overrides: int) -> None:
        """Update display from a status readback."""
        self._mode_label.setText(mode_name)
        self._guard_label.setText(
            "Active" if mode_name != "NORMAL" else "Inactive",
        )
        from pymcaf.constants import OverrideFlag
        for key, cb in self._override_checks.items():
            flag = OverrideFlag[key.upper()]
            cb.setChecked(bool(overrides & flag))
