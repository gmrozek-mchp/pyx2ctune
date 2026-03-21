"""Wizard definition schema and YAML loader.

Dataclasses that describe wizard steps, inputs, actions, and outputs.
These are pure data -- no Qt or GUI dependencies.
"""

from __future__ import annotations

import importlib.resources
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

import yaml

_REF_PATTERN = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_.]*)")


# ── Step status ───────────────────────────────────────────────────────

class StepStatus(Enum):
    PENDING = auto()
    ACTIVE = auto()
    COMPLETE = auto()
    SKIPPED = auto()
    ERROR = auto()


# ── YAML schema dataclasses ──────────────────────────────────────────

@dataclass
class InputDef:
    """Declarative description of one user input field."""

    id: str
    type: str  # float, integer, choice, bool, file_path, serial_port
    label: str = ""
    default: Any = None
    suffix: str = ""
    range: list[float] | None = None  # [min, max]
    decimals: int = 2
    step: float | None = None
    options: list[str] | None = None  # for choice type
    filter: str = ""  # for file_path type
    prefill: str = ""  # $ref expression for auto-fill from earlier output
    persist: bool = False
    required: bool = True
    visible_when: dict[str, str] | None = None

    @classmethod
    def from_dict(cls, d: dict) -> InputDef:
        return cls(
            id=d["id"],
            type=d["type"],
            label=d.get("label", d["id"]),
            default=d.get("default"),
            suffix=d.get("suffix", ""),
            range=d.get("range"),
            decimals=d.get("decimals", 2),
            step=d.get("step"),
            options=d.get("options"),
            filter=d.get("filter", ""),
            prefill=d.get("prefill", ""),
            persist=d.get("persist", False),
            required=d.get("required", True),
            visible_when=d.get("visible_when"),
        )


@dataclass
class ActionDef:
    """One or more commands to submit to the worker."""

    command: str | None = None
    args: dict[str, Any] | None = None
    sequence: list[ActionDef] | None = None

    @classmethod
    def from_dict(cls, d: dict) -> ActionDef:
        seq = None
        if "sequence" in d:
            seq = [ActionDef.from_dict(item) for item in d["sequence"]]
        return cls(
            command=d.get("command"),
            args=d.get("args"),
            sequence=seq,
        )


@dataclass
class OutputDef:
    """Extracts a value from a signal payload into the wizard context."""

    id: str
    from_signal: str

    @classmethod
    def from_dict(cls, d: dict) -> OutputDef:
        return cls(id=d["id"], from_signal=d["from_signal"])


@dataclass
class IterateDef:
    """Defines an iterate-or-advance choice after a step completes."""

    prompt: str = "Satisfied with the result?"
    goto_on_no: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> IterateDef:
        return cls(
            prompt=d.get("prompt", "Satisfied with the result?"),
            goto_on_no=d.get("goto_on_no", ""),
        )


@dataclass
class StepDef:
    """Full definition of a single wizard step."""

    id: str
    title: str
    description: str = ""
    requires: list[str] = field(default_factory=list)
    inputs: list[InputDef] = field(default_factory=list)
    action: ActionDef | None = None
    wait_for: str = ""
    outputs: list[OutputDef] = field(default_factory=list)
    show_plot: bool = False
    iterate: IterateDef | None = None
    auto_execute: bool = False
    skip_if: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> StepDef:
        inputs = [InputDef.from_dict(i) for i in d.get("inputs", [])]
        action = ActionDef.from_dict(d["action"]) if "action" in d else None
        outputs = [OutputDef.from_dict(o) for o in d.get("outputs", [])]
        iterate = IterateDef.from_dict(d["iterate"]) if "iterate" in d else None
        return cls(
            id=d["id"],
            title=d["title"],
            description=d.get("description", ""),
            requires=d.get("requires", []),
            inputs=inputs,
            action=action,
            wait_for=d.get("wait_for", ""),
            outputs=outputs,
            show_plot=d.get("show_plot", False),
            iterate=iterate,
            auto_execute=d.get("auto_execute", False),
            skip_if=d.get("skip_if", ""),
        )


@dataclass
class WizardDefinition:
    """Parsed wizard definition from a YAML file."""

    id: str
    name: str
    description: str
    steps: list[StepDef]

    @classmethod
    def from_dict(cls, d: dict) -> WizardDefinition:
        steps = [StepDef.from_dict(s) for s in d.get("steps", [])]
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            steps=steps,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> WizardDefinition:
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    def step_by_id(self, step_id: str) -> StepDef | None:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    def step_index(self, step_id: str) -> int:
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                return i
        return -1


# ── Discovery ─────────────────────────────────────────────────────────

def discover_wizards() -> list[WizardDefinition]:
    """Find and parse all shipped wizard YAML files."""
    wizards: list[WizardDefinition] = []
    pkg = importlib.resources.files("mctoolbox") / "wizards"
    for item in pkg.iterdir():
        if hasattr(item, "name") and item.name.endswith((".yaml", ".yml")):
            with importlib.resources.as_file(item) as p:
                wizards.append(WizardDefinition.from_yaml(p))
    return sorted(wizards, key=lambda w: w.name)
