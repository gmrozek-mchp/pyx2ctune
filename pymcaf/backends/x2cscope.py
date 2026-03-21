"""pyx2cscope backend for pymcaf.

Implements the :class:`~pymcaf.backend.Backend` interface using
pyX2Cscope for serial/LNet communication and ELF-based variable
resolution.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pyx2cscope.x2cscope import X2CScope

from pymcaf.backend import Backend

if TYPE_CHECKING:
    from pyx2cscope.variable.variable import Variable

logger = logging.getLogger(__name__)


class X2CScopeBackend(Backend):
    """Board communication backend using pyX2Cscope.

    Connects to an MCAF target over UART, loads the ELF file for
    variable resolution, and provides scope data acquisition.

    Args:
        port: Serial port (e.g. "/dev/tty.usbmodem1", "COM3").
        elf_file: Path to compiled firmware ELF with debug symbols.
        baud_rate: UART baud rate (default 115200).
    """

    def __init__(self, port: str, elf_file: str, baud_rate: int = 115200):
        self._port = port
        self._elf_file = str(Path(elf_file).resolve())

        logger.info("Connecting to %s at %d baud", port, baud_rate)
        self._x2c = X2CScope(port=port, baud_rate=baud_rate)

        root_logger = logging.getLogger()
        prev_level = root_logger.level
        root_logger.setLevel(logging.ERROR)
        try:
            self._x2c.import_variables(self._elf_file)
        finally:
            root_logger.setLevel(prev_level)

        logger.info("Loaded variables from %s", self._elf_file)
        self._variable_cache: dict[str, Variable] = {}

    def _get_variable(self, name: str) -> Variable:
        """Resolve a variable name to a pyX2Cscope Variable, with caching."""
        if name not in self._variable_cache:
            try:
                self._variable_cache[name] = self._x2c.get_variable(name)
            except Exception as e:
                raise KeyError(
                    f"Variable {name!r} not found in ELF. "
                    f"Use backend.list_variables() to see available names."
                ) from e
        return self._variable_cache[name]

    def list_variables(self) -> list[str]:
        """Return all variable names available in the loaded ELF."""
        return self._x2c.list_variables()

    # ── Backend ABC implementation ────────────────────────────────────

    def read_variable(self, name: str) -> int | float:
        value = self._get_variable(name).get_value()
        logger.debug("Read  %s = %s", name, value)
        return value

    def write_variable(self, name: str, value: int | float) -> None:
        self._get_variable(name).set_value(value)
        logger.debug("Wrote %s = %s", name, value)

    def disconnect(self) -> None:
        self._x2c.disconnect()
        logger.info("Disconnected from %s", self._port)

    # ── Scope operations ──────────────────────────────────────────────

    def clear_scope_channels(self) -> None:
        self._x2c.clear_all_scope_channel()

    def add_scope_channel(self, name: str) -> None:
        var = self._get_variable(name)
        self._x2c.add_scope_channel(var)

    def set_scope_trigger(
        self,
        channel_name: str,
        level: float,
        mode: int = 1,
        delay: int = 0,
        edge: int = 0,
    ) -> None:
        from pyx2cscope.x2cscope import TriggerConfig

        var = self._get_variable(channel_name)
        config = TriggerConfig(
            variable=var,
            trigger_level=level,
            trigger_mode=mode,
            trigger_delay=delay,
            trigger_edge=edge,
        )
        self._x2c.set_scope_trigger(config)

    def reset_scope_trigger(self) -> None:
        self._x2c.reset_scope_trigger()

    def set_sample_time(self, prescaler: int) -> None:
        self._x2c.set_sample_time(prescaler)

    def request_scope_data(self) -> None:
        self._x2c.request_scope_data()

    def is_scope_data_ready(self) -> bool:
        return self._x2c.is_scope_data_ready()

    def get_scope_channel_data(self) -> dict[str, list[float]]:
        return self._x2c.get_scope_channel_data(valid_data=True)

    def __repr__(self) -> str:
        return (
            f"X2CScopeBackend(port={self._port!r}, "
            f"elf={Path(self._elf_file).name!r})"
        )
