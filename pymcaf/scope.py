"""Scope interface for oscilloscope-like data capture.

Provides a clean API for configuring scope channels, triggers,
and capturing waveform data from the target firmware.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymcaf.backend import Backend


class Scope:
    """Oscilloscope-like data capture interface.

    Wraps the backend's scope operations with a friendlier API.
    Scope data is returned in raw firmware units; use
    :class:`~pymcaf.connection.Connection` conversion methods
    or :class:`~pymcaf.parameters.ParameterDB` to convert to
    engineering units.
    """

    def __init__(self, backend: Backend):
        self._backend = backend

    def clear_channels(self) -> None:
        """Remove all configured scope channels."""
        self._backend.clear_scope_channels()

    def add_channel(self, name: str) -> None:
        """Add a firmware variable as a scope channel.

        Args:
            name: Dot-separated variable name (e.g. "motor.idq.q").
        """
        self._backend.add_scope_channel(name)

    def set_trigger(
        self,
        channel_name: str,
        level: float = 0,
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
        self._backend.set_scope_trigger(channel_name, level, mode, delay, edge)

    def reset_trigger(self) -> None:
        """Disable the scope trigger."""
        self._backend.reset_scope_trigger()

    def set_sample_time(self, prescaler: int) -> None:
        """Set the scope sample time prescaler.

        Args:
            prescaler: 1 = every ISR sample, 2 = every other, etc.
        """
        self._backend.set_sample_time(prescaler)

    def request_data(self) -> None:
        """Initiate a scope data capture."""
        self._backend.request_scope_data()

    def is_data_ready(self) -> bool:
        """Check whether the scope capture is complete."""
        return self._backend.is_scope_data_ready()

    def get_channel_data(self) -> dict[str, list[float]]:
        """Retrieve captured scope data.

        Returns:
            Dict mapping variable names to lists of raw sample values.
        """
        return self._backend.get_scope_channel_data()
