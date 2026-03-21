"""Velocity loop PI gain tuning.

Provides methods to read/write velocity PI gains in engineering units,
set velocity commands, and configure square-wave velocity perturbation
for step response testing.

Reference: https://microchiptech.github.io/mcaf-doc/9.0.1/algorithms/foc/tuning.html
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mctoolbox import interfaces as _interfaces

if TYPE_CHECKING:
    from mctoolbox.mcaf.session import TuningSession

logger = logging.getLogger(__name__)

_GAIN_VARS = {
    "kp": "motor.omegaCtrl.kp",
    "ki": "motor.omegaCtrl.ki",
    "nkp": "motor.omegaCtrl.nkp",
    "nki": "motor.omegaCtrl.nki",
}

_VAR_VELOCITY_CMD = "motor.velocityControl.velocityCmd"
_VAR_OMEGA_ELECTRICAL = "motor.omegaElectrical"
_VAR_SQWAVE_VALUE = "motor.testing.sqwave.value"
_VAR_SQWAVE_HALFPERIOD = "motor.testing.sqwave.halfperiod"
_VAR_SQWAVE_VEL_ELEC = "motor.testing.sqwave.velocity.electrical"

_PARAM_KWP = "foc.kwp"
_PARAM_KWI = "foc.kwi"
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


class VelocityTuning(_interfaces.LoopTuner):
    """Velocity loop PI gain tuning interface.

    Reads and writes PI gains for the velocity controller, converting
    between engineering units and firmware fixed-point counts using
    the ParameterDB.
    """

    def __init__(self, session: TuningSession):
        self._session = session

    # ── Gain Read / Write ─────────────────────────────────────────────

    def get_gains(self, **kwargs: Any) -> VelocityGains:
        """Read velocity PI gains from firmware."""
        kp_counts = int(self._session.read_variable(_GAIN_VARS["kp"]))
        ki_counts = int(self._session.read_variable(_GAIN_VARS["ki"]))
        nkp = int(self._session.read_variable(_GAIN_VARS["nkp"]))
        nki = int(self._session.read_variable(_GAIN_VARS["nki"]))

        params = self._session.params
        if params is not None:
            kp_info = params.get_info(_PARAM_KWP)
            ki_info = params.get_info(_PARAM_KWI)
            kp_eng = (kp_counts / (1 << (15 - nkp))) * kp_info.scale
            ki_eng = (ki_counts / (1 << (15 - nki))) * ki_info.scale
        else:
            kp_eng = float(kp_counts)
            ki_eng = float(ki_counts)

        result = VelocityGains(
            kp=kp_eng, ki=ki_eng,
            kp_counts=kp_counts, ki_counts=ki_counts,
            kp_shift=15 - nkp, ki_shift=15 - nki,
        )
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
        if units == "counts":
            kp_counts = int(kp)
            ki_counts = int(ki)
            nkp = None
            nki = None
        elif units == "engineering":
            kp_counts, nkp = self._engineering_to_counts_with_shift(
                _PARAM_KWP, kp,
            )
            ki_counts, nki = self._engineering_to_counts_with_shift(
                _PARAM_KWI, ki,
            )
        else:
            raise ValueError(
                f"units must be 'engineering' or 'counts', got {units!r}"
            )

        self._session.write_variable(_GAIN_VARS["kp"], kp_counts)
        self._session.write_variable(_GAIN_VARS["ki"], ki_counts)
        if nkp is not None:
            self._session.write_variable(_GAIN_VARS["nkp"], nkp)
        if nki is not None:
            self._session.write_variable(_GAIN_VARS["nki"], nki)

        actual_nkp = nkp if nkp is not None else int(
            self._session.read_variable(_GAIN_VARS["nkp"])
        )
        actual_nki = nki if nki is not None else int(
            self._session.read_variable(_GAIN_VARS["nki"])
        )

        result = VelocityGains(
            kp=kp if units == "engineering" else float(kp_counts),
            ki=ki if units == "engineering" else float(ki_counts),
            kp_counts=kp_counts, ki_counts=ki_counts,
            kp_shift=15 - actual_nkp, ki_shift=15 - actual_nki,
        )
        logger.info(
            "Set velocity gains: Kp=%.6f %s (counts=%d, Q%d), "
            "Ki=%.4f %s (counts=%d, Q%d)",
            result.kp, result.kp_units, result.kp_counts, result.kp_shift,
            result.ki, result.ki_units, result.ki_counts, result.ki_shift,
        )
        return result

    def _engineering_to_counts_with_shift(
        self, param_key: str, value: float,
    ) -> tuple[int, int]:
        """Convert an engineering value to counts with overflow-safe shifting."""
        params = self._session.params
        if params is None:
            raise RuntimeError(
                "ParameterDB required for engineering unit conversion."
            )

        info = params.get_info(param_key)
        nkp = 15 - info.q
        effective_q = 15 - nkp
        counts = round(value / info.scale * (1 << effective_q))

        while not (-32768 <= counts <= 32767) and effective_q > 0:
            nkp += 1
            effective_q = 15 - nkp
            counts = round(value / info.scale * (1 << effective_q))

        if not (-32768 <= counts <= 32767):
            raise ValueError(
                f"Cannot represent {value} {info.units} for {param_key!r} "
                f"in int16 (tried nkp up to {nkp}, Q{effective_q})"
            )

        return counts, nkp

    # ── Velocity Command ──────────────────────────────────────────────

    @property
    def fullscale_velocity_rpm(self) -> float | None:
        """Return the full-scale velocity in RPM from parameters.json, or None."""
        return self._fullscale_velocity_rpm()

    def _fullscale_velocity_rpm(self) -> float | None:
        params = self._session.params
        if params is None:
            return None
        try:
            return params.get_info(_PARAM_FULLSCALE_VELOCITY).intended_value
        except KeyError:
            return None

    def rpm_to_counts(self, rpm: float) -> int:
        """Convert RPM to Q15 velocity counts."""
        fs = self._fullscale_velocity_rpm()
        if fs is None:
            raise RuntimeError("ParameterDB required for RPM conversion.")
        return round(rpm / fs * 32768)

    def counts_to_rpm(self, counts: int) -> float:
        """Convert Q15 velocity counts to RPM."""
        fs = self._fullscale_velocity_rpm()
        if fs is None:
            return float(counts)
        return (counts / 32768) * fs

    def set_velocity_command(self, rpm: float) -> None:
        """Set the velocity command in RPM.

        Requires the velocity command override to be active.
        """
        counts = self.rpm_to_counts(rpm)
        self._session.write_variable(_VAR_VELOCITY_CMD, counts)
        logger.info("Set velocity command: %.1f RPM (%d counts)", rpm, counts)

    def get_velocity_command(self) -> float:
        """Read the current velocity command in RPM."""
        counts = int(self._session.read_variable(_VAR_VELOCITY_CMD))
        return self.counts_to_rpm(counts)

    def get_measured_velocity(self) -> float:
        """Read the measured electrical velocity in RPM."""
        counts = int(self._session.read_variable(_VAR_OMEGA_ELECTRICAL))
        return self.counts_to_rpm(counts)

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
        """Start a square-wave velocity perturbation.

        Accepts the same keyword arguments as setup_velocity_perturbation().
        """
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
        amp_counts = self.rpm_to_counts(amplitude_rpm)
        hp_cycles = self.ms_to_isr_cycles(halfperiod_ms)

        self._session.write_variable(_VAR_SQWAVE_HALFPERIOD, hp_cycles)
        self._session.write_variable(_VAR_SQWAVE_VEL_ELEC, amp_counts)
        self._session.write_variable(_VAR_SQWAVE_VALUE, 1)

        logger.info(
            "Started velocity perturbation: %.1f RPM (%d counts), "
            "T/2=%.2f ms (%d cycles)",
            amplitude_rpm, amp_counts, halfperiod_ms, hp_cycles,
        )

    def stop_perturbation(self) -> None:
        """Stop the square-wave perturbation signal."""
        self._session.write_variable(_VAR_SQWAVE_VALUE, 0)
        logger.info("Stopped velocity perturbation")

    def get_default_perturbation(self) -> dict:
        """Return suggested velocity perturbation defaults.

        Amplitude is set to 5% of fullscale velocity.
        Half-period defaults to 50 ms (10 Hz square wave).
        """
        amplitude_rpm = 100.0
        fs = self._fullscale_velocity_rpm()
        if fs is not None:
            amplitude_rpm = round(fs * 0.05, 1)
        return {
            "amplitude_rpm": amplitude_rpm,
            "halfperiod_ms": 50.0,
        }
