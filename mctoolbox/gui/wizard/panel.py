"""WizardPanel: sidebar widget for guided tuning workflows."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt, QSettings, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mctoolbox.gui.wizard.engine import EngineState, WizardEngine
from mctoolbox.wizard_schema import (
    StepDef,
    StepStatus,
    WizardDefinition,
    discover_wizards,
)
from mctoolbox.gui.wizard.input_factory import (
    create_input_widget,
    get_widget_value,
    set_widget_value,
)
from mctoolbox.gui.workers import SessionWorker

_STATUS_ICONS = {
    StepStatus.PENDING: "\u25cb",   # ○
    StepStatus.ACTIVE: "\u25cf",    # ●
    StepStatus.COMPLETE: "\u2713",  # ✓
    StepStatus.SKIPPED: "\u2012",   # ‒
    StepStatus.ERROR: "\u2717",     # ✗
}

_BOLD = QFont()
_BOLD.setBold(True)


class WizardPanel(QWidget):
    """Sidebar panel that renders a wizard and drives the WizardEngine."""

    close_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setMaximumWidth(420)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self._engine = WizardEngine(self)
        self._wizards: list[WizardDefinition] = []
        self._input_widgets: dict[str, QWidget] = {}
        self._settings = QSettings("mctoolbox", "mctoolbox")

        self._build_ui()
        self._connect_engine()
        self._load_wizard_list()

    @property
    def engine(self) -> WizardEngine:
        return self._engine

    # ── UI Construction ───────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # Header: wizard selector + close
        header = QHBoxLayout()
        header.setSpacing(4)
        lbl = QLabel("Wizard:")
        lbl.setFont(_BOLD)
        header.addWidget(lbl)
        self._wizard_combo = QComboBox()
        self._wizard_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._wizard_combo.currentIndexChanged.connect(self._on_wizard_selected)
        header.addWidget(self._wizard_combo, stretch=1)
        close_btn = QPushButton("\u00d7")  # ×
        close_btn.setFixedSize(24, 24)
        close_btn.setFlat(True)
        close_btn.setToolTip("Close wizard panel")
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        root.addLayout(header)

        # Description
        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet("color: gray; font-size: 11px;")
        root.addWidget(self._desc_label)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFrameShadow(QFrame.Sunken)
        root.addWidget(div)

        # Step list
        self._step_list = QListWidget()
        self._step_list.setMaximumHeight(160)
        self._step_list.setSelectionMode(QListWidget.NoSelection)
        self._step_list.setFocusPolicy(Qt.NoFocus)
        root.addWidget(self._step_list)

        # Divider
        div2 = QFrame()
        div2.setFrameShape(QFrame.HLine)
        div2.setFrameShadow(QFrame.Sunken)
        root.addWidget(div2)

        # Active step area (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._step_content = QWidget()
        self._step_layout = QVBoxLayout(self._step_content)
        self._step_layout.setContentsMargins(0, 0, 0, 0)
        self._step_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._step_content)
        root.addWidget(scroll, stretch=1)

        # Step title + description (inside step area)
        self._step_title = QLabel()
        self._step_title.setFont(_BOLD)
        self._step_title.setWordWrap(True)
        self._step_layout.addWidget(self._step_title)

        self._step_desc = QLabel()
        self._step_desc.setWordWrap(True)
        self._step_layout.addWidget(self._step_desc)

        # Input form (dynamic)
        self._form_group = QGroupBox()
        self._form_layout = QFormLayout(self._form_group)
        self._form_layout.setContentsMargins(4, 8, 4, 4)
        self._step_layout.addWidget(self._form_group)
        self._form_group.hide()

        # Iterate prompt (shown after step completes with iterate)
        self._iterate_widget = QWidget()
        iter_layout = QVBoxLayout(self._iterate_widget)
        iter_layout.setContentsMargins(0, 8, 0, 0)
        self._iterate_label = QLabel()
        self._iterate_label.setWordWrap(True)
        self._iterate_label.setFont(_BOLD)
        iter_layout.addWidget(self._iterate_label)
        iter_btns = QHBoxLayout()
        self._iterate_yes = QPushButton("Yes, continue")
        self._iterate_no = QPushButton("No, go back")
        iter_btns.addWidget(self._iterate_no)
        iter_btns.addWidget(self._iterate_yes)
        iter_layout.addLayout(iter_btns)
        self._step_layout.addWidget(self._iterate_widget)
        self._iterate_widget.hide()

        # Spacer
        self._step_layout.addStretch()

        # Navigation buttons (outside scroll, always visible)
        nav = QHBoxLayout()
        self._back_btn = QPushButton("\u2190 Back")
        self._execute_btn = QPushButton("Execute \u2192")
        self._start_btn = QPushButton("Start Wizard")
        nav.addWidget(self._back_btn)
        nav.addStretch()
        nav.addWidget(self._start_btn)
        nav.addWidget(self._execute_btn)
        root.addLayout(nav)

        self._back_btn.clicked.connect(self._on_back)
        self._execute_btn.clicked.connect(self._on_execute)
        self._start_btn.clicked.connect(self._on_start)
        self._iterate_yes.clicked.connect(self._on_iterate_yes)
        self._iterate_no.clicked.connect(self._on_iterate_no)

        self._set_idle_state()

    # ── Engine wiring ─────────────────────────────────────────────

    def _connect_engine(self) -> None:
        self._engine.step_changed.connect(self._on_step_changed)
        self._engine.step_status_changed.connect(self._on_step_status_changed)
        self._engine.step_completed.connect(self._on_step_completed)
        self._engine.iterate_requested.connect(self._on_iterate_requested)
        self._engine.wizard_finished.connect(self._on_wizard_finished)
        self._engine.engine_error.connect(self._on_engine_error)

    def set_worker(self, worker: SessionWorker) -> None:
        self._engine.set_worker(worker)

    def set_connected(self, connected: bool) -> None:
        self._engine.set_connected(connected)

    # ── Wizard list management ────────────────────────────────────

    def _load_wizard_list(self) -> None:
        self._wizards = discover_wizards()
        self._wizard_combo.blockSignals(True)
        self._wizard_combo.clear()
        for w in self._wizards:
            self._wizard_combo.addItem(w.name, w.id)
        self._wizard_combo.blockSignals(False)
        if self._wizards:
            self._on_wizard_selected(0)

    def _on_wizard_selected(self, index: int) -> None:
        if index < 0 or index >= len(self._wizards):
            return
        defn = self._wizards[index]
        self._engine.load(defn)
        self._desc_label.setText(defn.description)
        self._populate_step_list(defn)
        self._set_idle_state()

    # ── Step list display ─────────────────────────────────────────

    def _populate_step_list(self, defn: WizardDefinition) -> None:
        self._step_list.clear()
        for i, step in enumerate(defn.steps):
            icon = _STATUS_ICONS[StepStatus.PENDING]
            item = QListWidgetItem(f"  {icon}  {i + 1}. {step.title}")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self._step_list.addItem(item)

    def _on_step_status_changed(self, index: int, status_name: str) -> None:
        if index < 0 or index >= self._step_list.count():
            return
        status = StepStatus[status_name]
        icon = _STATUS_ICONS[status]
        step = self._engine.definition.steps[index]
        item = self._step_list.item(index)
        item.setText(f"  {icon}  {index + 1}. {step.title}")
        if status == StepStatus.ACTIVE:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        else:
            font = item.font()
            font.setBold(False)
            item.setFont(font)

    # ── Active step rendering ─────────────────────────────────────

    def _on_step_changed(self, index: int) -> None:
        defn = self._engine.definition
        if defn is None or index < 0 or index >= len(defn.steps):
            return
        step = defn.steps[index]
        self._render_step(step)
        self._step_list.setCurrentRow(index)

    def _render_step(self, step: StepDef) -> None:
        self._iterate_widget.hide()
        self._step_title.setText(f"Step {self._engine.current_index + 1}: {step.title}")
        self._step_desc.setText(step.description)

        # Clear old inputs
        self._input_widgets.clear()
        while self._form_layout.rowCount() > 0:
            self._form_layout.removeRow(0)

        if step.inputs:
            self._form_group.show()
            for inp in step.inputs:
                widget = create_input_widget(inp)
                self._input_widgets[inp.id] = widget

                if inp.prefill:
                    val = self._engine.resolve_prefill(inp.prefill)
                    if val is not None:
                        set_widget_value(widget, val)

                if inp.persist:
                    saved = self._settings.value(f"wizard/{inp.id}")
                    if saved is not None:
                        set_widget_value(widget, saved)

                self._form_layout.addRow(inp.label + ":", widget)
        else:
            self._form_group.hide()

        self._back_btn.setEnabled(self._engine.current_index > 0)
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText(
            "Execute \u2192" if step.action else "Next \u2192"
        )
        self._start_btn.hide()
        self._execute_btn.show()
        self._back_btn.show()

    def _collect_inputs(self) -> dict[str, Any]:
        values = {}
        defn = self._engine.definition
        if defn is None:
            return values
        step = defn.steps[self._engine.current_index]
        for inp in step.inputs:
            widget = self._input_widgets.get(inp.id)
            if widget is not None:
                val = get_widget_value(widget)
                values[inp.id] = val
                if inp.persist:
                    self._settings.setValue(f"wizard/{inp.id}", val)
        return values

    # ── Navigation slots ──────────────────────────────────────────

    def _on_start(self) -> None:
        self._engine.start()

    def _on_execute(self) -> None:
        values = self._collect_inputs()
        self._execute_btn.setEnabled(False)
        self._back_btn.setEnabled(False)
        self._engine.execute(values)

    def _on_back(self) -> None:
        self._engine.go_back()

    # ── Step completion ───────────────────────────────────────────

    def _on_step_completed(self, index: int, payload: object) -> None:
        pass  # engine auto-advances unless iterate is set

    def _on_iterate_requested(self, prompt: str) -> None:
        self._iterate_label.setText(prompt)
        self._iterate_widget.show()
        self._execute_btn.hide()

    def _on_iterate_yes(self) -> None:
        self._iterate_widget.hide()
        self._engine.iterate_accept()

    def _on_iterate_no(self) -> None:
        self._iterate_widget.hide()
        self._engine.iterate_reject()

    # ── Wizard finished ───────────────────────────────────────────

    def _on_wizard_finished(self) -> None:
        self._step_title.setText("Wizard Complete")
        self._step_desc.setText(
            "All steps have been completed. You can close this panel "
            "or restart the wizard."
        )
        self._form_group.hide()
        self._iterate_widget.hide()
        self._execute_btn.hide()
        self._back_btn.hide()
        self._start_btn.setText("Restart Wizard")
        self._start_btn.show()

    # ── Error display ─────────────────────────────────────────────

    def _on_engine_error(self, message: str) -> None:
        self._step_desc.setText(f"Error: {message}")
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText("Retry \u2192")
        self._back_btn.setEnabled(self._engine.current_index > 0)

    # ── Idle state ────────────────────────────────────────────────

    def _set_idle_state(self) -> None:
        defn = self._engine.definition
        self._step_title.setText("Ready")
        self._step_desc.setText(
            f'Click "Start Wizard" to begin the {defn.name} workflow.'
            if defn else "Select a wizard above."
        )
        self._form_group.hide()
        self._iterate_widget.hide()
        self._execute_btn.hide()
        self._back_btn.hide()
        self._start_btn.setText("Start Wizard")
        self._start_btn.show()
