"""Wizard engine: Qt state machine and SessionWorker integration.

The engine interprets wizard definition files and drives step execution
through the existing SessionWorker command queue.  Schema dataclasses
and YAML loading live in mctoolbox.wizard_schema (no Qt dependency).
"""

from __future__ import annotations

import re
from enum import Enum, auto
from typing import Any

from PyQt5.QtCore import QObject, pyqtSignal

from mctoolbox.gui.workers import Command, SessionWorker
from mctoolbox.wizard_schema import (
    ActionDef,
    StepStatus,
    WizardDefinition,
    _REF_PATTERN,
)


class EngineState(Enum):
    IDLE = auto()
    SHOWING_STEP = auto()
    EXECUTING = auto()
    WAITING = auto()
    STEP_COMPLETE = auto()
    ITERATING = auto()
    FINISHED = auto()


class WizardEngine(QObject):
    """Interprets a WizardDefinition and drives it through the SessionWorker.

    Signals
    -------
    step_changed(int)
        Emitted when the active step index changes.
    step_status_changed(int, str)
        Emitted when a step's status changes (index, status name).
    step_completed(int, object)
        Emitted when a step finishes successfully (index, signal payload).
    iterate_requested(str)
        Emitted when the completed step has an iterate prompt.
    wizard_finished()
        Emitted when all steps are done.
    engine_error(str)
        Emitted on error (message).
    status_message(str)
        Informational text for the status bar.
    """

    step_changed = pyqtSignal(int)
    step_status_changed = pyqtSignal(int, str)
    step_completed = pyqtSignal(int, object)
    iterate_requested = pyqtSignal(str)
    wizard_finished = pyqtSignal()
    engine_error = pyqtSignal(str)
    status_message = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._definition: WizardDefinition | None = None
        self._worker: SessionWorker | None = None
        self._state = EngineState.IDLE
        self._current_index = -1
        self._step_statuses: list[StepStatus] = []
        self._context: dict[str, Any] = {}
        self._pending_signal: str = ""
        self._pending_connection = None
        self._connected_to_target = False
        self._seq_remaining: list[ActionDef] = []

    # ── Setup ─────────────────────────────────────────────────────

    def load(self, definition: WizardDefinition) -> None:
        self._cleanup_signal()
        self._definition = definition
        self._step_statuses = [StepStatus.PENDING] * len(definition.steps)
        self._context.clear()
        self._current_index = -1
        self._state = EngineState.IDLE

    def set_worker(self, worker: SessionWorker) -> None:
        if self._worker is not None:
            self._worker.error.disconnect(self._on_worker_error)
            self._worker.connected.disconnect(self._on_target_connected)
            self._worker.disconnected.disconnect(self._on_target_disconnected)
        self._worker = worker
        worker.error.connect(self._on_worker_error)
        worker.connected.connect(self._on_target_connected)
        worker.disconnected.connect(self._on_target_disconnected)

    def set_connected(self, connected: bool) -> None:
        self._connected_to_target = connected

    @property
    def definition(self) -> WizardDefinition | None:
        return self._definition

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def state(self) -> EngineState:
        return self._state

    def step_status(self, index: int) -> StepStatus:
        if 0 <= index < len(self._step_statuses):
            return self._step_statuses[index]
        return StepStatus.PENDING

    def context_value(self, ref: str) -> Any:
        """Resolve a dotted reference like 'read_gains.kp' from the context."""
        parts = ref.split(".")
        obj = self._context
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            elif hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return None
        return obj

    # ── Navigation ────────────────────────────────────────────────

    def start(self) -> None:
        if self._definition is None or not self._definition.steps:
            return
        self._go_to_step(0)

    def advance(self) -> None:
        """Move to the next step (or finish)."""
        if self._definition is None:
            return
        next_idx = self._current_index + 1
        if next_idx >= len(self._definition.steps):
            self._state = EngineState.FINISHED
            self.wizard_finished.emit()
            return
        self._go_to_step(next_idx)

    def go_back(self) -> None:
        if self._current_index > 0:
            self._cleanup_signal()
            self._go_to_step(self._current_index - 1)

    def jump_to(self, step_id: str) -> None:
        if self._definition is None:
            return
        idx = self._definition.step_index(step_id)
        if idx >= 0:
            self._cleanup_signal()
            self._go_to_step(idx)

    def _go_to_step(self, index: int) -> None:
        if self._definition is None:
            return
        step = self._definition.steps[index]

        if step.skip_if and self._check_condition(step.skip_if):
            self._set_step_status(index, StepStatus.SKIPPED)
            if index + 1 < len(self._definition.steps):
                self._go_to_step(index + 1)
            else:
                self._state = EngineState.FINISHED
                self.wizard_finished.emit()
            return

        self._current_index = index
        self._set_step_status(index, StepStatus.ACTIVE)
        self._state = EngineState.SHOWING_STEP
        self.step_changed.emit(index)

        if step.auto_execute:
            self.execute()

    def _check_condition(self, cond: str) -> bool:
        if cond == "connected":
            return self._connected_to_target
        return self._context.get(cond) is not None

    # ── Execution ─────────────────────────────────────────────────

    def execute(self, input_values: dict[str, Any] | None = None) -> None:
        """Execute the current step's action with the provided input values."""
        if self._definition is None or self._worker is None:
            return
        step = self._definition.steps[self._current_index]

        if input_values:
            self._context[step.id] = input_values
            self._context.update(input_values)

        if step.action is None:
            self._complete_step(None)
            return

        self._state = EngineState.EXECUTING

        if step.wait_for:
            self._connect_signal(step.wait_for)

        if step.action.sequence:
            self._seq_remaining = list(step.action.sequence)
            self._execute_next_in_sequence()
        else:
            self._submit_action(step.action)

        if not step.wait_for:
            self._complete_step(None)

    def _execute_next_in_sequence(self) -> None:
        if not self._seq_remaining:
            return
        action = self._seq_remaining.pop(0)
        self._submit_action(action)
        if self._seq_remaining and not self._pending_signal:
            self._execute_next_in_sequence()

    def _submit_action(self, action: ActionDef) -> None:
        if self._worker is None or action.command is None:
            return
        try:
            cmd = Command[action.command]
        except KeyError:
            self.engine_error.emit(f"Unknown command: {action.command}")
            return

        kwargs = {}
        if action.args:
            for key, val in action.args.items():
                kwargs[key] = self._resolve_value(val)

        self.status_message.emit(f"Executing {action.command}...")
        self._worker.submit(cmd, **kwargs)

    # ── $ref resolution ───────────────────────────────────────────

    def _resolve_value(self, val: Any) -> Any:
        """Resolve $ref expressions in a value."""
        if isinstance(val, str) and "$" in val:
            match = _REF_PATTERN.fullmatch(val)
            if match:
                resolved = self.context_value(match.group(1))
                return resolved if resolved is not None else val
            def _sub(m: re.Match) -> str:
                resolved = self.context_value(m.group(1))
                return str(resolved) if resolved is not None else m.group(0)
            return _REF_PATTERN.sub(_sub, val)
        return val

    def resolve_prefill(self, ref: str) -> Any:
        """Public resolver for prefill expressions (used by the panel)."""
        if not ref:
            return None
        ref_clean = ref.lstrip("$")
        return self.context_value(ref_clean)

    # ── Signal handling ───────────────────────────────────────────

    def _connect_signal(self, signal_name: str) -> None:
        self._cleanup_signal()
        if self._worker is None:
            return
        sig = getattr(self._worker, signal_name, None)
        if sig is None:
            self.engine_error.emit(f"Unknown signal: {signal_name}")
            return
        self._pending_signal = signal_name
        self._state = EngineState.WAITING

        def _handler(*args):
            self._on_signal_received(signal_name, args)

        sig.connect(_handler)
        self._pending_connection = (sig, _handler)

    def _cleanup_signal(self) -> None:
        if self._pending_connection is not None:
            sig, handler = self._pending_connection
            try:
                sig.disconnect(handler)
            except (TypeError, RuntimeError):
                pass
            self._pending_connection = None
        self._pending_signal = ""
        self._seq_remaining.clear()

    def _on_signal_received(self, signal_name: str, args: tuple) -> None:
        if signal_name != self._pending_signal:
            return
        self._cleanup_signal()

        if self._seq_remaining:
            self._execute_next_in_sequence()
            return

        payload = args[0] if args else None
        self._extract_outputs(payload)
        self._complete_step(payload)

    def _extract_outputs(self, payload: Any) -> None:
        if self._definition is None or payload is None:
            return
        step = self._definition.steps[self._current_index]
        step_outputs = {}
        for out in step.outputs:
            val = getattr(payload, out.from_signal, None)
            if val is not None:
                step_outputs[out.id] = val
                self._context[out.id] = val
        if step_outputs:
            self._context[step.id] = (
                {**self._context.get(step.id, {}), **step_outputs}
                if isinstance(self._context.get(step.id), dict)
                else step_outputs
            )

    def _complete_step(self, payload: Any) -> None:
        idx = self._current_index
        self._set_step_status(idx, StepStatus.COMPLETE)
        self._state = EngineState.STEP_COMPLETE
        self.step_completed.emit(idx, payload)

        step = self._definition.steps[idx]
        if step.iterate:
            self._state = EngineState.ITERATING
            self.iterate_requested.emit(step.iterate.prompt)
        else:
            self.advance()

    def iterate_accept(self) -> None:
        """User is satisfied -- advance past the iterate step."""
        self.advance()

    def iterate_reject(self) -> None:
        """User wants to try again -- jump back."""
        if self._definition is None:
            return
        step = self._definition.steps[self._current_index]
        if step.iterate and step.iterate.goto_on_no:
            self.jump_to(step.iterate.goto_on_no)

    # ── Error handling ────────────────────────────────────────────

    def _on_worker_error(self, cmd_name: str, message: str) -> None:
        if self._state in (EngineState.EXECUTING, EngineState.WAITING):
            self._cleanup_signal()
            self._set_step_status(self._current_index, StepStatus.ERROR)
            self._state = EngineState.SHOWING_STEP
            self.engine_error.emit(f"{cmd_name}: {message}")

    def _on_target_connected(self, session: object) -> None:
        self._connected_to_target = True

    def _on_target_disconnected(self) -> None:
        self._connected_to_target = False

    # ── Helpers ───────────────────────────────────────────────────

    def _set_step_status(self, index: int, status: StepStatus) -> None:
        if 0 <= index < len(self._step_statuses):
            self._step_statuses[index] = status
            self.step_status_changed.emit(index, status.name)
