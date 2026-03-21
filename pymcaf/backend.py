"""Abstract backend interface for board communication.

Defines the contract that any board communication backend must satisfy.
The default implementation uses pyx2cscope; alternatives (simulator,
TCP, etc.) can be plugged in by implementing this ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Backend(ABC):
    """Pluggable board communication interface.

    Provides low-level variable I/O and oscilloscope operations.
    Implementations handle protocol details (LNet, ELF parsing, etc.).
    """

    # ── Variable I/O ──────────────────────────────────────────────────

    @abstractmethod
    def read_variable(self, name: str) -> int | float:
        """Read the raw value of a firmware variable.

        Args:
            name: Dot-separated variable name (e.g. "motor.idCtrl.kp").

        Returns:
            The raw value from the target (integer or float).

        Raises:
            KeyError: If the variable is not found.
        """

    @abstractmethod
    def write_variable(self, name: str, value: int | float) -> None:
        """Write a raw value to a firmware variable.

        Args:
            name: Dot-separated variable name.
            value: Value to write.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection and release resources."""

    # ── Scope operations ──────────────────────────────────────────────

    @abstractmethod
    def clear_scope_channels(self) -> None:
        """Remove all configured scope channels."""

    @abstractmethod
    def add_scope_channel(self, name: str) -> None:
        """Add a firmware variable as a scope channel.

        Args:
            name: Dot-separated variable name to capture.
        """

    @abstractmethod
    def set_scope_trigger(
        self,
        channel_name: str,
        level: float,
        mode: int = 1,
        delay: int = 0,
        edge: int = 0,
    ) -> None:
        """Configure the scope trigger.

        Args:
            channel_name: Variable name of the trigger channel.
            level: Trigger threshold (raw counts).
            mode: Trigger mode (1 = normal).
            delay: Pre/post-trigger delay percentage.
            edge: 0 = rising, 1 = falling.
        """

    @abstractmethod
    def reset_scope_trigger(self) -> None:
        """Disable the scope trigger."""

    @abstractmethod
    def set_sample_time(self, prescaler: int) -> None:
        """Set the scope sample time prescaler.

        Args:
            prescaler: 1 = every ISR sample, 2 = every other, etc.
        """

    @abstractmethod
    def request_scope_data(self) -> None:
        """Initiate a scope data capture."""

    @abstractmethod
    def is_scope_data_ready(self) -> bool:
        """Check whether the scope capture is complete."""

    @abstractmethod
    def get_scope_channel_data(self) -> dict[str, list[float]]:
        """Retrieve captured scope data.

        Returns:
            Dict mapping variable names to lists of sample values.
        """
