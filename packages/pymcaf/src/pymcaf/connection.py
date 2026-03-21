"""High-level connection to an MCAF motor controller.

Wraps a :class:`~pymcaf.backend.Backend` with optional
:class:`~pymcaf.parameters.ParameterDB` to provide engineering-unit
read/write methods that abstract away Q-format conversion.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pymcaf.scope import Scope

if TYPE_CHECKING:
    from pymcaf.backend import Backend
    from pymcaf.parameters import ParameterDB

logger = logging.getLogger(__name__)


class Connection:
    """Connection to an MCAF-based motor controller.

    Provides raw and engineering-unit access to firmware variables,
    plus oscilloscope data capture via the :attr:`scope` attribute.

    Args:
        backend: Board communication backend.
        parameters_json: Optional path to motorBench parameters.json
            for Q-format unit conversion.
    """

    def __init__(
        self,
        backend: Backend,
        parameters_json: str | None = None,
    ):
        self._backend = backend

        self._params: ParameterDB | None = None
        if parameters_json is not None:
            from pymcaf.parameters import ParameterDB

            self._params = ParameterDB(parameters_json)
            logger.info("Loaded %s", self._params)

        self.scope = Scope(self._backend)
        self._motor = None
        self._test_harness = None

    @property
    def backend(self) -> Backend:
        """The underlying board communication backend."""
        return self._backend

    @property
    def params(self) -> ParameterDB | None:
        """The parameter database, or None if not loaded."""
        return self._params

    @property
    def motor(self):
        """Typed access to motor control variables.

        Returns a :class:`~pymcaf.motor.Motor` instance providing
        property-based read/write of currents, voltages, velocities,
        duty cycles, and PI gains in engineering units.
        """
        if self._motor is None:
            from pymcaf.motor import Motor

            self._motor = Motor(self)
        return self._motor

    @property
    def test_harness(self):
        """Test harness interface.

        Returns a :class:`~pymcaf.test_harness.TestHarness` instance
        providing guard management, operating mode control, override
        flags, state transitions, and perturbation configuration.
        """
        if self._test_harness is None:
            from pymcaf.test_harness import TestHarness

            self._test_harness = TestHarness(self)
        return self._test_harness

    # ── Raw variable access ───────────────────────────────────────────

    def read_raw(self, name: str) -> int | float:
        """Read the raw value of a firmware variable.

        No unit conversion is applied.  Use this for integers, enums,
        bitfields, and other values that don't require Q-format scaling.
        """
        return self._backend.read_variable(name)

    def write_raw(self, name: str, value: int | float) -> None:
        """Write a raw value to a firmware variable.

        No unit conversion is applied.
        """
        self._backend.write_variable(name, value)

    # ── Q15 conversion ────────────────────────────────────────────────

    def _require_params(self) -> ParameterDB:
        if self._params is None:
            raise RuntimeError(
                "ParameterDB required for unit conversion. "
                "Pass parameters_json when creating the Connection."
            )
        return self._params

    def read_q15(self, name: str, fullscale_param: str) -> float:
        """Read a Q15-encoded variable and return in engineering units.

        Args:
            name: Firmware variable name.
            fullscale_param: Parameter key for the fullscale value
                (e.g. "mcapi.fullscale.current").

        Returns:
            Value in engineering units (Amps, Volts, RPM, etc.).
        """
        params = self._require_params()
        raw = self._backend.read_variable(name)
        fs = params.get_fullscale(fullscale_param)
        if fs <= 0:
            return float(raw)
        return (raw / 32768.0) * fs

    def write_q15(self, name: str, value: float, fullscale_param: str) -> None:
        """Convert an engineering value to Q15 counts and write.

        Args:
            name: Firmware variable name.
            value: Value in engineering units.
            fullscale_param: Parameter key for the fullscale value.
        """
        params = self._require_params()
        fs = params.get_fullscale(fullscale_param)
        if fs <= 0:
            raise ValueError(
                f"Invalid fullscale for {fullscale_param!r} (got {fs})"
            )
        counts = round(value / fs * 32768)
        self._backend.write_variable(name, counts)

    def q15_to_engineering(self, raw: int | float, fullscale_param: str) -> float:
        """Convert a raw Q15 value to engineering units without a read.

        Useful for converting scope data after capture.

        Args:
            raw: Raw Q15 value from firmware.
            fullscale_param: Parameter key for the fullscale value.

        Returns:
            Value in engineering units.
        """
        params = self._require_params()
        fs = params.get_fullscale(fullscale_param)
        if fs <= 0:
            return float(raw)
        return (raw / 32768.0) * fs

    def engineering_to_q15(self, value: float, fullscale_param: str) -> int:
        """Convert an engineering value to Q15 counts without a write.

        Args:
            value: Value in engineering units.
            fullscale_param: Parameter key for the fullscale value.

        Returns:
            Q15 integer counts.
        """
        params = self._require_params()
        fs = params.get_fullscale(fullscale_param)
        if fs <= 0:
            raise ValueError(
                f"Invalid fullscale for {fullscale_param!r} (got {fs})"
            )
        return round(value / fs * 32768)

    # ── Lifecycle ─────────────────────────────────────────────────────

    def disconnect(self) -> None:
        """Disconnect from the target and release resources."""
        self._backend.disconnect()

    # ── Convenience factory ───────────────────────────────────────────

    @classmethod
    def via_x2cscope(
        cls,
        port: str,
        elf_file: str,
        baud_rate: int = 115200,
        **kwargs,
    ) -> Connection:
        """Create a Connection using the pyx2cscope backend.

        Args:
            port: Serial port (e.g. "/dev/tty.usbmodem1", "COM3").
            elf_file: Path to compiled firmware ELF with debug symbols.
            baud_rate: UART baud rate (default 115200).
            **kwargs: Additional arguments passed to Connection
                (e.g. parameters_json).
        """
        from pymcaf.backends.x2cscope import X2CScopeBackend

        backend = X2CScopeBackend(port, elf_file, baud_rate)
        return cls(backend, **kwargs)

    def __repr__(self) -> str:
        params_str = f", params={self._params!r}" if self._params else ""
        return f"Connection(backend={self._backend!r}{params_str})"
