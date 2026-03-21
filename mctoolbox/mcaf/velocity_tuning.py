"""Velocity loop PI gain tuning.

Provides methods to read/write velocity PI gains in engineering units,
set velocity commands, and configure square-wave velocity perturbation
for step response testing.

Delegates gain read/write to :attr:`pymcaf.Connection.motor` and
perturbation control to :attr:`pymcaf.Connection.test_harness.sqwave`.

Reference: https://microchiptech.github.io/mcaf-doc/9.0.1/algorithms/foc/tuning.html
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pymcaf.types import PIGainValues

from mctoolbox import interfaces as _interfaces

if TYPE_CHECKING:
    from mctoolbox.mcaf.session import TuningSession

logger = logging.getLogger(__name__)

_PARAM_FULLSCALE_VELOCITY = "mcapi.fullscale.velocity"
_PARAM_ISR_DIVIDER = "timing.mcafIsrSubsampleDivider"


@dataclass
class VelocityGains(_interfaces.PIGains):
    """Velocity loop PI gains in engineering units."""

    kp_counts: int = 0
    ki_counts: int = 0
    kp_shift: int = 0
    ki_shift: int = 0
    kp_units: str = "A/(rad/s)"
    ki_units: str = "A/rad"


def _pi_to_velocity_gains(g: PIGainValues) -> VelocityGains:
    """Convert a generic PIGainValues to the mctoolbox VelocityGains type."""
    return VelocityGains(
        kp=g.kp, ki=g.ki,
        kp_counts=g.kp_raw, ki_counts=g.ki_raw,
        kp_shift=g.kp_shift, ki_shift=g.ki_shift,
        kp_units=g.kp_units, ki_units=g.ki_units,
    )


class VelocityTuning(_interfaces.LoopTuner):
    """Velocity loop PI gain tuning interface.

    Reads and writes PI gains for the velocity controller, converting
    between engineering units and firmware fixed-point counts via the
    pymcaf Motor interface.
    """

    def __init__(self, session: TuningSession):
        self._session = session

    # ── Gain Read / Write ─────────────────────────────────────────────

    def get_gains(self, **kwargs: Any) -> VelocityGains:
        """Read velocity PI gains from firmware."""
        motor = self._session.conn.motor
        g = motor.read_velocity_gains()
        result = _pi_to_velocity_gains(g)
        logger.info(
            "Read velocity gains: Kp=%.6f %s (counts=%d, Q%d), "
            "Ki=%.4f %s (counts=%d, Q%d)",
            result.kp, result.kp_units, result.kp_counts, result.kp_shift,
            result.ki, result.ki_units, result.ki_counts, result.ki_shift,
        )
        return result

    def set_gains(self, kp: float, ki: float,
                  units: str = "engineering", **kwargs: Any) -> VelocityGains:
        """Set velocity loop PI gains.

        Args:
            kp: Proportional gain (A/(rad/s) in engineering units).
            ki: Integral gain (A/rad in engineering units).
            units: "engineering" or "counts".

        Returns:
            VelocityGains reflecting the values actually written.
        """
        motor = self._session.conn.motor

        if units == "counts":
            kp_counts = int(kp)
            ki_counts = int(ki)
            motor.write_velocity_gains_raw(kp_counts, ki_counts)
            return VelocityGains(
                kp=float(kp_counts), ki=float(ki_counts),
                kp_counts=kp_counts, ki_counts=ki_counts,
            )

        if units != "engineering":
            raise ValueError(
                f"units must be 'engineering' or 'counts', got {units!r}"
            )

        g = motor.write_velocity_gains(kp, ki)
        result = _pi_to_velocity_gains(g)
        logger.info(
            "Set velocity gains: Kp=%.6f %s (counts=%d, Q%d), "
            "Ki=%.4f %s (counts=%d, Q%d)",
            result.kp, result.kp_units, result.kp_counts, result.kp_shift,
            result.ki, result.ki_units, result.ki_counts, result.ki_shift,
        )
        return result

    # ── Velocity Command ──────────────────────────────────────────────

    @property
    def fullscale_velocity_rpm(self) -> float | None:
        """Return the full-scale velocity in RPM from parameters.json, or None."""
        params = self._session.params
        if params is None:
            return None
        try:
            return params.get_info(_PARAM_FULLSCALE_VELOCITY).intended_value
        except KeyError:
            return None

    def rpm_to_counts(self, rpm: float) -> int:
        """Convert RPM to Q15 velocity counts."""
        return self._session.conn.engineering_to_q15(rpm, _PARAM_FULLSCALE_VELOCITY)

    def counts_to_rpm(self, counts: int) -> float:
        """Convert Q15 velocity counts to RPM."""
        return self._session.conn.q15_to_engineering(counts, _PARAM_FULLSCALE_VELOCITY)

    def set_velocity_command(self, rpm: float) -> None:
        """Set the velocity command in RPM.

        Requires the velocity command override to be active.
        """
        self._session.conn.motor.velocity_cmd = rpm
        logger.info("Set velocity command: %.1f RPM", rpm)

    def get_velocity_command(self) -> float:
        """Read the current velocity command in RPM."""
        return self._session.conn.motor.velocity_cmd

    def get_measured_velocity(self) -> float:
        """Read the measured electrical velocity in RPM."""
        return self._session.conn.motor.omega

    # ── Velocity Perturbation ─────────────────────────────────────────

    def _isr_period_s(self) -> float | None:
        params = self._session.params
        if params is None:
            return None
        try:
            return params.get_info(_PARAM_ISR_DIVIDER).scale
        except KeyError:
            return None

    def ms_to_isr_cycles(self, ms: float) -> int:
        isr_period = self._isr_period_s()
        if isr_period is None:
            raise RuntimeError("ParameterDB required for timing conversion.")
        return round(ms / 1000.0 / isr_period)

    def isr_cycles_to_ms(self, cycles: int) -> float:
        isr_period = self._isr_period_s()
        if isr_period is None:
            return float(cycles)
        return cycles * isr_period * 1000.0

    def start_perturbation(self, **kwargs: Any) -> None:
        """Start a square-wave velocity perturbation."""
        self.setup_velocity_perturbation(**kwargs)

    def setup_velocity_perturbation(
        self,
        amplitude_rpm: float = 100.0,
        halfperiod_ms: float = 50.0,
    ) -> None:
        """Configure and start a square-wave velocity perturbation.

        Args:
            amplitude_rpm: Perturbation amplitude in RPM.
            halfperiod_ms: Half-period in milliseconds.
        """
        sqwave = self._session.conn.test_harness.sqwave
        hp_cycles = self.ms_to_isr_cycles(halfperiod_ms)

        sqwave.halfperiod = hp_cycles
        sqwave.velocity_amplitude = amplitude_rpm
        sqwave.start()

        logger.info(
            "Started velocity perturbation: %.1f RPM, T/2=%.2f ms (%d cycles)",
            amplitude_rpm, halfperiod_ms, hp_cycles,
        )

    def stop_perturbation(self) -> None:
        """Stop the square-wave perturbation signal."""
        self._session.conn.test_harness.sqwave.stop()
        logger.info("Stopped velocity perturbation")

    def get_default_perturbation(self) -> dict:
        """Return suggested velocity perturbation defaults.

        Amplitude is set to 5% of fullscale velocity.
        Half-period defaults to 50 ms (10 Hz square wave).
        """
        amplitude_rpm = 100.0
        fs = self.fullscale_velocity_rpm
        if fs is not None:
            amplitude_rpm = round(fs * 0.05, 1)
        return {
            "amplitude_rpm": amplitude_rpm,
            "halfperiod_ms": 50.0,
        }
