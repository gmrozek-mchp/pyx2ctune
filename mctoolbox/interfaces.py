"""Abstract interfaces for motor control tuning.

Defines the contracts that any motor control framework implementation
(MCAF, custom, etc.) must satisfy.  The GUI and wizard layers program
against these interfaces, not against concrete implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pymcaf.types import MotorState, PIGainValues

if TYPE_CHECKING:
    import threading

    import numpy as np


# ── Data types (canonical definitions live in pymcaf.types) ───────────

@dataclass
class PIGains:
    """PI controller gains in engineering units.

    Subclasses may add implementation-specific fields (e.g. raw counts,
    Q-format shift values).
    """

    kp: float
    ki: float
    kp_units: str = ""
    ki_units: str = ""


# ── Abstract base classes ─────────────────────────────────────────────

class TestHarness(ABC):
    """Safety-guarded test mode management.

    Handles enabling/disabling the safety guard, entering and exiting
    test modes, and querying motor state.  Implementation details
    (guard keys, operating mode enums, etc.) are framework-specific.
    """

    @abstractmethod
    def enter_test_mode(self, mode: str = "current") -> str:
        """Enter a test operating mode.

        Args:
            mode: Implementation-defined mode name
                  (e.g. "current", "velocity_override", "force_voltage").

        Returns:
            The name of the mode actually entered.
        """

    @abstractmethod
    def exit_test_mode(self) -> None:
        """Return the controller to normal operation safely."""

    @abstractmethod
    def get_motor_state(self) -> MotorState:
        """Read the current motor state machine state."""

    @property
    @abstractmethod
    def guard_active(self) -> bool:
        """Whether the safety guard is currently enabled."""


class LoopTuner(ABC):
    """PI gain read/write and perturbation control for one control loop."""

    @abstractmethod
    def get_gains(self, **kwargs: Any) -> PIGains:
        """Read the current PI gains from the controller."""

    @abstractmethod
    def set_gains(self, kp: float, ki: float, **kwargs: Any) -> PIGains:
        """Write new PI gains and return the values actually applied."""

    @abstractmethod
    def start_perturbation(self, **kwargs: Any) -> None:
        """Start a test perturbation signal (e.g. square wave)."""

    @abstractmethod
    def stop_perturbation(self) -> None:
        """Stop the perturbation signal."""

    @abstractmethod
    def get_default_perturbation(self) -> dict[str, Any]:
        """Return suggested default perturbation parameters."""


class WaveformCapture(ABC):
    """Waveform acquisition for step-response analysis."""

    @abstractmethod
    def configure(self, view: str, **kwargs: Any) -> None:
        """Configure capture channels for a named view preset.

        Args:
            view: Implementation-defined view identifier
                  (e.g. "current_q", "velocity").
        """

    @abstractmethod
    def capture_frame(
        self,
        timeout: float = 5.0,
        abort_event: threading.Event | None = None,
    ) -> Any:
        """Capture a single waveform frame.

        Returns:
            A StepResponse (from mctoolbox.capture) or compatible object.
        """


class TuningSession(ABC):
    """Top-level session connecting to a motor controller.

    Provides access to sub-modules for test harness management,
    loop tuning, and waveform capture.
    """

    test_harness: TestHarness
    current: LoopTuner
    velocity: LoopTuner
    capture: WaveformCapture

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the controller and release resources."""
