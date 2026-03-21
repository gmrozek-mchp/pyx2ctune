"""Shared scope panel with preset views, trigger controls, and capture buttons.

Provides a unified capture interface used by all tabs. A tab bar at the
top selects which firmware variables are captured and how units are displayed.
Each tab has its own content page (via QStackedWidget) for view-specific
controls, while sample time, trigger, and capture buttons are shared.
Trigger level is automatically converted from engineering units to Q15
counts based on the selected view's fullscale parameter.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabBar,
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
    stop_requested = pyqtSignal()
    view_changed = pyqtSignal(str)  # view_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fullscale: dict[str, float] = {}
        self._continuous = False
        # Per-view settings: view_id → (trigger_enabled, trigger_level, sample_time)
        self._view_settings: dict[str, tuple[bool, float, int]] = {}
        self._prev_view: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_panel())
        self._prev_view = self.current_view()
        self._connect_internal()

    def _build_panel(self) -> QGroupBox:
        grp = QGroupBox("Scope")
        outer = QVBoxLayout(grp)

        self._view_tabs = QTabBar()
        self._view_tabs.setExpanding(False)
        self._view_stack = QStackedWidget()
        self._view_pages: dict[str, QWidget] = {}
        for i, (view_id, display, *_) in enumerate(_VIEW_PRESETS):
            self._view_tabs.addTab(display)
            self._view_tabs.setTabData(i, view_id)
            page = QWidget()
            page.setLayout(QVBoxLayout())
            page.layout().setContentsMargins(0, 0, 0, 0)
            self._view_stack.addWidget(page)
            self._view_pages[view_id] = page
        outer.addWidget(self._view_tabs)
        outer.addWidget(self._view_stack)

        sample_row = QHBoxLayout()
        sample_row.addWidget(QLabel("Sample time:"))
        self._sample_time_spin = QSpinBox()
        self._sample_time_spin.setRange(1, 255)
        self._sample_time_spin.setValue(1)
        self._sample_time_spin.setToolTip(
            "Scope prescaler: 1 = every ISR sample (fastest).\n"
            "Higher values extend the capture window at lower resolution."
        )
        sample_row.addWidget(self._sample_time_spin)
        sample_row.addStretch()
        outer.addLayout(sample_row)

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

        self._run_btn = QPushButton("Run")
        self._run_btn.setMinimumHeight(36)
        font = self._run_btn.font()
        font.setBold(True)
        self._run_btn.setFont(font)
        btn_layout.addWidget(self._run_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setMinimumHeight(36)
        self._stop_btn.setEnabled(False)
        btn_layout.addWidget(self._stop_btn)

        outer.addLayout(btn_layout)
        return grp

    def _connect_internal(self) -> None:
        self._view_tabs.currentChanged.connect(self._view_stack.setCurrentIndex)
        self._view_tabs.currentChanged.connect(self._on_view_changed)
        self._capture_btn.clicked.connect(self.capture_single_requested.emit)
        self._run_btn.clicked.connect(
            self.continuous_start_requested.emit,
        )
        self._stop_btn.clicked.connect(self.stop_requested.emit)

    def _on_view_changed(self, index: int) -> None:
        if index < 0 or index >= len(_VIEW_PRESETS):
            return

        # Save settings for the view we're leaving
        if self._prev_view is not None:
            self._view_settings[self._prev_view] = (
                self._trigger_check.isChecked(),
                self._trigger_level_spin.value(),
                self._sample_time_spin.value(),
            )

        view_id, _, channel_label, unit, _ = _VIEW_PRESETS[index]
        self._trigger_channel_label.setText(channel_label)
        self._trigger_level_spin.setSuffix(f" {unit}")

        # Restore settings for the view we're entering
        saved = self._view_settings.get(view_id)
        if saved is not None:
            enabled, level, st = saved
            self._trigger_check.setChecked(enabled)
            self._trigger_level_spin.setValue(level)
            self._sample_time_spin.setValue(st)
        else:
            self._trigger_check.setChecked(True)
            self._trigger_level_spin.setValue(0.0)
            self._sample_time_spin.setValue(1)

        self._prev_view = view_id
        self.view_changed.emit(view_id)

    # ── Public API ────────────────────────────────────────────────────

    def current_view(self) -> str:
        """Return the selected view ID (e.g. 'current_q', 'velocity')."""
        idx = self._view_tabs.currentIndex()
        if 0 <= idx < self._view_tabs.count():
            return self._view_tabs.tabData(idx) or "current_q"
        return "current_q"

    def set_view(self, view_id: str) -> None:
        """Programmatically select a view by its ID."""
        for i in range(self._view_tabs.count()):
            if self._view_tabs.tabData(i) == view_id:
                self._view_tabs.setCurrentIndex(i)
                return

    def view_page(self, view_id: str) -> QWidget:
        """Return the per-tab content page for *view_id*.

        Callers can add view-specific widgets to the page's layout::

            page = scope_panel.view_page("velocity")
            page.layout().addWidget(my_custom_widget)
        """
        return self._view_pages[view_id]

    def sample_time(self) -> int:
        return self._sample_time_spin.value()

    def trigger_enabled(self) -> bool:
        return self._trigger_check.isChecked()

    def trigger_level_q15(self) -> float:
        """Return trigger level converted to raw Q15 counts."""
        value = self._trigger_level_spin.value()
        idx = self._view_tabs.currentIndex()
        if idx < 0 or idx >= len(_VIEW_PRESETS):
            return round(value)
        fs_key = _VIEW_PRESETS[idx][4]
        fs = self._fullscale.get(fs_key, 0.0)
        if fs > 0:
            return round(value / fs * 32768)
        return round(value)

    def set_connected(self, connected: bool) -> None:
        self._capture_btn.setEnabled(connected)
        self._run_btn.setEnabled(connected)
        self._stop_btn.setEnabled(False)
        self._sample_time_spin.setEnabled(connected)
        self._trigger_check.setEnabled(connected)
        self._trigger_level_spin.setEnabled(connected)

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
                fs = params.get_fullscale(param_name)
                if fs > 0:
                    self._fullscale[key] = fs

    def on_disconnected(self) -> None:
        self._fullscale = {}
        self._trigger_level_spin.setValue(0.0)
        self._trigger_check.setChecked(True)
        self._sample_time_spin.setValue(1)

    def on_capture_started(self) -> None:
        self._capture_btn.setEnabled(False)
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

    def on_capture_done(self) -> None:
        if self._continuous:
            return
        self._capture_btn.setEnabled(True)
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def on_capture_cancelled(self) -> None:
        self._capture_btn.setEnabled(True)
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def on_continuous_started(self) -> None:
        self._continuous = True
        self._capture_btn.setEnabled(False)
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

    def on_continuous_stopped(self) -> None:
        self._continuous = False
        self._capture_btn.setEnabled(True)
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    # ── Settings persistence ──────────────────────────────────────────

    def save_settings(self, settings) -> None:
        # Snapshot current widgets into the cache before persisting
        cur = self.current_view()
        self._view_settings[cur] = (
            self._trigger_check.isChecked(),
            self._trigger_level_spin.value(),
            self._sample_time_spin.value(),
        )
        settings.setValue("scope/view", cur)
        for view_id, *_ in _VIEW_PRESETS:
            saved = self._view_settings.get(view_id)
            if saved is not None:
                enabled, level, st = saved
                settings.setValue(f"scope/{view_id}/trigger", enabled)
                settings.setValue(f"scope/{view_id}/level", level)
                settings.setValue(f"scope/{view_id}/sample_time", st)

    def restore_settings(self, settings) -> None:
        for view_id, *_ in _VIEW_PRESETS:
            trig = settings.value(f"scope/{view_id}/trigger")
            level = settings.value(f"scope/{view_id}/level", type=float)
            st = settings.value(f"scope/{view_id}/sample_time", type=int)
            if trig is not None:
                enabled = str(trig).lower() in ("true", "1")
                self._view_settings[view_id] = (
                    enabled, level or 0.0, st or 1,
                )

        view = settings.value("scope/view", "")
        if view:
            self.set_view(view)

        # Apply cached settings for the active view
        saved = self._view_settings.get(self.current_view())
        if saved is not None:
            self._trigger_check.setChecked(saved[0])
            self._trigger_level_spin.setValue(saved[1])
            self._sample_time_spin.setValue(saved[2])
