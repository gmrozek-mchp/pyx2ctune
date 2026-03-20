"""Shared scope panel with preset views, trigger controls, and capture buttons.

Provides a unified capture interface used by all tabs. The View dropdown
selects which firmware variables are captured and how units are displayed.
Trigger level is automatically converted from engineering units to Q15
counts based on the selected view's fullscale parameter.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# (view_id, display_name, trigger_channel_label, trigger_unit, fullscale_key)
_VIEW_PRESETS = [
    ("current_q", "Current Iq", "on Iq ref", "A", "current"),
    ("current_d", "Current Id", "on Id ref", "A", "current"),
    ("velocity", "Velocity", "on velocity cmd", "RPM", "velocity"),
    ("open_voltage", "Open Voltage DQ", "on Vq", "V", "voltage"),
    ("open_current", "Open Current DQ", "on Iq", "A", "current"),
]


class ScopePanel(QWidget):
    """Scope capture controls shared across all tuning tabs."""

    capture_single_requested = pyqtSignal()
    continuous_start_requested = pyqtSignal()
    continuous_stop_requested = pyqtSignal()
    cancel_capture_requested = pyqtSignal()
    view_changed = pyqtSignal(str)  # view_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fullscale: dict[str, float] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_panel())
        self._connect_internal()

    def _build_panel(self) -> QGroupBox:
        grp = QGroupBox("Scope")
        outer = QVBoxLayout(grp)

        view_row = QHBoxLayout()
        view_row.addWidget(QLabel("View:"))
        self._view_combo = QComboBox()
        for view_id, display, *_ in _VIEW_PRESETS:
            self._view_combo.addItem(display, view_id)
        view_row.addWidget(self._view_combo, stretch=1)
        outer.addLayout(view_row)

        trigger_row = QHBoxLayout()
        self._trigger_check = QCheckBox("Trigger")
        self._trigger_check.setChecked(True)
        trigger_row.addWidget(self._trigger_check)
        self._trigger_channel_label = QLabel("on Iq ref")
        trigger_row.addWidget(self._trigger_channel_label)
        trigger_row.addWidget(QLabel("Level:"))
        self._trigger_level_spin = QDoubleSpinBox()
        self._trigger_level_spin.setRange(-10000.0, 10000.0)
        self._trigger_level_spin.setDecimals(2)
        self._trigger_level_spin.setValue(0.0)
        self._trigger_level_spin.setSuffix(" A")
        trigger_row.addWidget(self._trigger_level_spin)
        trigger_row.addStretch()
        outer.addLayout(trigger_row)

        btn_layout = QHBoxLayout()

        self._capture_btn = QPushButton("Single")
        self._capture_btn.setMinimumHeight(36)
        btn_layout.addWidget(self._capture_btn)

        self._continuous_start_btn = QPushButton("Start")
        self._continuous_start_btn.setMinimumHeight(36)
        font = self._continuous_start_btn.font()
        font.setBold(True)
        self._continuous_start_btn.setFont(font)
        btn_layout.addWidget(self._continuous_start_btn)

        self._continuous_stop_btn = QPushButton("Stop")
        self._continuous_stop_btn.setMinimumHeight(36)
        self._continuous_stop_btn.setEnabled(False)
        btn_layout.addWidget(self._continuous_stop_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setMinimumHeight(36)
        self._cancel_btn.setEnabled(False)
        btn_layout.addWidget(self._cancel_btn)

        outer.addLayout(btn_layout)
        return grp

    def _connect_internal(self) -> None:
        self._view_combo.currentIndexChanged.connect(self._on_view_changed)
        self._capture_btn.clicked.connect(self.capture_single_requested.emit)
        self._continuous_start_btn.clicked.connect(
            self.continuous_start_requested.emit,
        )
        self._continuous_stop_btn.clicked.connect(
            self.continuous_stop_requested.emit,
        )
        self._cancel_btn.clicked.connect(self.cancel_capture_requested.emit)

    def _on_view_changed(self, index: int) -> None:
        if index < 0 or index >= len(_VIEW_PRESETS):
            return
        view_id, _, channel_label, unit, _ = _VIEW_PRESETS[index]
        self._trigger_channel_label.setText(channel_label)
        self._trigger_level_spin.setSuffix(f" {unit}")
        self.view_changed.emit(view_id)

    # ── Public API ────────────────────────────────────────────────────

    def current_view(self) -> str:
        """Return the selected view ID (e.g. 'current_q', 'velocity')."""
        return self._view_combo.currentData() or "current_q"

    def set_view(self, view_id: str) -> None:
        """Programmatically select a view by its ID."""
        idx = self._view_combo.findData(view_id)
        if idx >= 0:
            self._view_combo.setCurrentIndex(idx)

    def trigger_enabled(self) -> bool:
        return self._trigger_check.isChecked()

    def trigger_level_q15(self) -> float:
        """Return trigger level converted to raw Q15 counts."""
        value = self._trigger_level_spin.value()
        idx = self._view_combo.currentIndex()
        if idx < 0 or idx >= len(_VIEW_PRESETS):
            return round(value)
        fs_key = _VIEW_PRESETS[idx][4]
        fs = self._fullscale.get(fs_key, 0.0)
        if fs > 0:
            return round(value / fs * 32768)
        return round(value)

    def set_connected(self, connected: bool) -> None:
        self._capture_btn.setEnabled(connected)
        self._continuous_start_btn.setEnabled(connected)
        self._continuous_stop_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._view_combo.setEnabled(connected)

    def on_connected(self, session) -> None:
        """Store fullscale values for trigger level conversion."""
        self._fullscale = {}
        params = session.params
        if params is not None:
            for key, param_name in (
                ("current", "mcapi.fullscale.current"),
                ("voltage", "mcapi.fullscale.voltage"),
                ("velocity", "mcapi.fullscale.velocity"),
            ):
                try:
                    self._fullscale[key] = params.get_info(
                        param_name,
                    ).intended_value
                except (KeyError, AttributeError):
                    pass

    def on_disconnected(self) -> None:
        self._fullscale = {}
        self._trigger_level_spin.setValue(0.0)

    def on_capture_started(self) -> None:
        if not self._continuous_stop_btn.isEnabled():
            self._capture_btn.setEnabled(False)
            self._cancel_btn.setEnabled(True)

    def on_capture_done(self) -> None:
        if self._continuous_stop_btn.isEnabled():
            return
        self._cancel_btn.setEnabled(False)
        self._capture_btn.setEnabled(True)

    def on_capture_cancelled(self) -> None:
        self._cancel_btn.setEnabled(False)
        self._capture_btn.setEnabled(True)

    def on_continuous_started(self) -> None:
        self._continuous_start_btn.setEnabled(False)
        self._continuous_stop_btn.setEnabled(True)
        self._capture_btn.setEnabled(False)

    def on_continuous_stopped(self) -> None:
        self._continuous_start_btn.setEnabled(True)
        self._continuous_stop_btn.setEnabled(False)
        self._capture_btn.setEnabled(True)

    # ── Settings persistence ──────────────────────────────────────────

    def save_settings(self, settings) -> None:
        settings.setValue("scope/view", self.current_view())
        settings.setValue("scope/trigger", self._trigger_check.isChecked())
        settings.setValue(
            "scope/trigger_level", self._trigger_level_spin.value(),
        )

    def restore_settings(self, settings) -> None:
        view = settings.value("scope/view", "")
        if view:
            self.set_view(view)
        trig = settings.value("scope/trigger")
        if trig is not None:
            self._trigger_check.setChecked(
                str(trig).lower() in ("true", "1"),
            )
        level = settings.value("scope/trigger_level", type=float)
        if level:
            self._trigger_level_spin.setValue(level)
