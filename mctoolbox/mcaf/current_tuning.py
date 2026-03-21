"""Current loop PI gain tuning.

Provides methods to read/write PI gains in engineering units,
configure square-wave perturbation for step response testing,
and manage shift counts for gain overflow.

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

# Firmware variable paths for PI controller gains
_GAIN_VARS = {
    "d": {
        "kp": "motor.idCtrl.kp",
        "ki": "motor.idCtrl.ki",
        "nkp": "motor.idCtrl.nkp",
        "nki": "motor.idCtrl.nki",
    },
    "q": {
        "kp": "motor.iqCtrl.kp",
        "ki": "motor.iqCtrl.ki",
        "nkp": "motor.iqCtrl.nkp",
        "nki": "motor.iqCtrl.nki",
    },
}

# Perturbation variable paths
_VAR_SQWAVE_VALUE = "motor.testing.sqwave.value"
_VAR_SQWAVE_HALFPERIOD = "motor.testing.sqwave.halfperiod"
_VAR_SQWAVE_IDQ_D = "motor.testing.sqwave.idq.d"
_VAR_SQWAVE_IDQ_Q = "motor.testing.sqwave.idq.q"

# Baseline current command variables (zeroed for perturbation testing)
_VAR_IDQCMDRAW_D = "motor.idqCmdRaw.d"
_VAR_IDQCMDRAW_Q = "motor.idqCmdRaw.q"

# parameters.json keys for gain scaling
_PARAM_KIP = "foc.kip"
_PARAM_KII = "foc.kii"

# parameters.json keys for perturbation unit conversion
_PARAM_FULLSCALE_CURRENT = "mcapi.fullscale.current"
_PARAM_ISR_DIVIDER = "timing.mcafIsrSubsampleDivider"
_PARAM_MAX_CURRENT_CMD = "sat_pi.currentMaximumCommand"


@dataclass
class CurrentGains(_interfaces.PIGains):
    """Current loop PI gains in engineering units."""

    kp_counts: int = 0
    ki_counts: int = 0
    kp_shift: int = 0
    ki_shift: int = 0
    kp_units: str = "V/A"
    ki_units: str = "V/A/s"


class CurrentTuning(_interfaces.LoopTuner):
    """Current loop PI gain tuning interface.

    Reads and writes PI gains for the d-axis and q-axis current loops,
    converting between engineering units (V/A, V/A/s) and firmware
    fixed-point counts via the pymcaf Connection.
    """

    def __init__(self, session: TuningSession):
        self._session = session

    def get_gains(self, axis: str = "q", **kwargs: Any) -> CurrentGains:
        """Read current PI gains from firmware and convert to engineering units.

        Args:
            axis: "q" or "d" (which current loop to read).

        Returns:
            CurrentGains with both engineering values and raw counts.
        """
        axis = axis.lower()
        if axis not in _GAIN_VARS:
            raise ValueError(f"axis must be 'q' or 'd', got {axis!r}")

        conn = self._session.conn
        vars_ = _GAIN_VARS[axis]

        kp_eng, kp_counts, kp_q = conn.read_pi_gain(
            vars_["kp"], vars_["nkp"], _PARAM_KIP,
        )
        ki_eng, ki_counts, ki_q = conn.read_pi_gain(
            vars_["ki"], vars_["nki"], _PARAM_KII,
        )

        result = CurrentGains(
            kp=kp_eng,
            ki=ki_eng,
            kp_counts=kp_counts,
            ki_counts=ki_counts,
            kp_shift=kp_q,
            ki_shift=ki_q,
        )
        logger.info(
            "Read %s-axis gains: Kp=%.4f %s (counts=%d, Q%d), "
            "Ki=%.2f %s (counts=%d, Q%d)",
            axis, result.kp, result.kp_units, result.kp_counts, result.kp_shift,
            result.ki, result.ki_units, result.ki_counts, result.ki_shift,
        )
        return result

    def set_gains(
        self,
        kp: float,
        ki: float,
        units: str = "engineering",
        axes: str = "both",
        **kwargs: Any,
    ) -> CurrentGains:
        """Set current loop PI gains.

        When units="engineering", kp is in V/A and ki is in V/A/s.
        The method converts to fixed-point counts via the pymcaf
        Connection, managing shift counts to handle potential overflow.

        When units="counts", kp and ki are written directly as integer
        counts (shift counts are not modified).

        Args:
            kp: Proportional gain.
            ki: Integral gain.
            units: "engineering" or "counts".
            axes: "both", "q", or "d" -- which axes to write.

        Returns:
            CurrentGains reflecting the values actually written.
        """
        conn = self._session.conn
        target_axes = self._resolve_axes(axes)

        if units == "counts":
            kp_counts = int(kp)
            ki_counts = int(ki)
            for axis in target_axes:
                vars_ = _GAIN_VARS[axis]
                self._session.write_variable(vars_["kp"], kp_counts)
                self._session.write_variable(vars_["ki"], ki_counts)

            first = _GAIN_VARS[target_axes[0]]
            actual_nkp = int(self._session.read_variable(first["nkp"]))
            actual_nki = int(self._session.read_variable(first["nki"]))
            kp_q = 15 - actual_nkp
            ki_q = 15 - actual_nki

        elif units == "engineering":
            kp_counts_result = ki_counts_result = 0
            kp_q = ki_q = 0
            for axis in target_axes:
                vars_ = _GAIN_VARS[axis]
                kp_counts_result, nkp = conn.write_pi_gain(
                    vars_["kp"], vars_["nkp"], _PARAM_KIP, kp,
                )
                ki_counts_result, nki = conn.write_pi_gain(
                    vars_["ki"], vars_["nki"], _PARAM_KII, ki,
                )
                kp_q = 15 - nkp
                ki_q = 15 - nki
            kp_counts = kp_counts_result
            ki_counts = ki_counts_result
        else:
            raise ValueError(f"units must be 'engineering' or 'counts', got {units!r}")

        result = CurrentGains(
            kp=kp if units == "engineering" else float(kp_counts),
            ki=ki if units == "engineering" else float(ki_counts),
            kp_counts=kp_counts,
            ki_counts=ki_counts,
            kp_shift=kp_q,
            ki_shift=ki_q,
        )
        logger.info(
            "Set current gains: Kp=%.4f %s (counts=%d, Q%d), "
            "Ki=%.2f %s (counts=%d, Q%d) on axes=%s",
            result.kp, result.kp_units, result.kp_counts, result.kp_shift,
            result.ki, result.ki_units, result.ki_counts, result.ki_shift,
            axes,
        )
        return result

    @staticmethod
    def _resolve_axes(axes: str) -> list[str]:
        axes = axes.lower()
        if axes == "both":
            return ["d", "q"]
        if axes in ("d", "q"):
            return [axes]
        raise ValueError(f"axes must be 'both', 'q', or 'd', got {axes!r}")

    # ── Perturbation Unit Conversion ─────────────────────────────────

    @property
    def fullscale_current(self) -> float | None:
        """Return the full-scale current in Amps from parameters.json, or None."""
        params = self._session.params
        if params is None:
            return None
        try:
            return params.get_info(_PARAM_FULLSCALE_CURRENT).intended_value
        except KeyError:
            return None

    def _isr_period_s(self) -> float | None:
        params = self._session.params
        if params is None:
            return None
        try:
            return params.get_info(_PARAM_ISR_DIVIDER).scale
        except KeyError:
            return None

    def amps_to_counts(self, amps: float) -> int:
        """Convert a current amplitude in Amps to Q15 counts."""
        conn = self._session.conn
        return conn.engineering_to_q15(amps, _PARAM_FULLSCALE_CURRENT)

    def counts_to_amps(self, counts: int) -> float:
        """Convert Q15 counts to a current amplitude in Amps."""
        conn = self._session.conn
        return conn.q15_to_engineering(counts, _PARAM_FULLSCALE_CURRENT)

    def ms_to_isr_cycles(self, ms: float) -> int:
        """Convert a half-period in milliseconds to ISR cycles."""
        isr_period = self._isr_period_s()
        if isr_period is None:
            raise RuntimeError(
                "ParameterDB required for timing unit conversion. "
                "Pass parameters_json to TuningSession."
            )
        return round(ms / 1000.0 / isr_period)

    def isr_cycles_to_ms(self, cycles: int) -> float:
        """Convert ISR cycles to milliseconds."""
        isr_period = self._isr_period_s()
        if isr_period is None:
            return float(cycles)
        return cycles * isr_period * 1000.0

    def get_perturbation_scaling(self) -> dict | None:
        """Return scaling info for GUI display, or None if parameters unavailable."""
        ifs = self.fullscale_current
        isr_period = self._isr_period_s()
        if ifs is None or isr_period is None:
            return None
        return {
            "fullscale_current_a": ifs,
            "isr_period_s": isr_period,
            "isr_freq_hz": 1.0 / isr_period,
        }

    def get_default_perturbation(self) -> dict:
        """Return suggested perturbation defaults based on parameters.json.

        Amplitude is set to 25% of the maximum current command.
        Half-period defaults to 5.0 ms (100 Hz square wave).
        """
        params = self._session.params
        amplitude_a = 0.5
        if params is not None:
            try:
                max_cmd = params.get_info(_PARAM_MAX_CURRENT_CMD).intended_value
                amplitude_a = round(max_cmd * 0.25, 3)
            except KeyError:
                pass
        return {
            "amplitude_a": amplitude_a,
            "halfperiod_ms": 5.0,
        }

    # ── Perturbation Control ──────────────────────────────────────────

    def start_perturbation(self, **kwargs: Any) -> None:
        """Start a square-wave perturbation for step response testing.

        Accepts the same keyword arguments as setup_step_test().
        """
        self.setup_step_test(**kwargs)

    def setup_step_test(
        self,
        axis: str = "q",
        amplitude: float = 0.5,
        halfperiod: float = 5.0,
        units: str = "engineering",
    ) -> None:
        """Configure and start a square-wave perturbation for step response testing.

        Args:
            axis: "q" or "d" -- which current axis to perturb.
            amplitude: Perturbation amplitude. In engineering mode, Amps.
                In counts mode, raw Q15 counts.
            halfperiod: Half-period. In engineering mode, milliseconds.
                In counts mode, ISR cycles.
            units: "engineering" (Amps / ms) or "counts" (raw values).
        """
        if units == "engineering":
            amp_counts = self.amps_to_counts(amplitude)
            hp_cycles = self.ms_to_isr_cycles(halfperiod)
        elif units == "counts":
            amp_counts = int(amplitude)
            hp_cycles = int(halfperiod)
        else:
            raise ValueError(f"units must be 'engineering' or 'counts', got {units!r}")

        self._session.write_variable(_VAR_IDQCMDRAW_D, 0)
        self._session.write_variable(_VAR_IDQCMDRAW_Q, 0)

        self._session.write_variable(_VAR_SQWAVE_HALFPERIOD, hp_cycles)

        if axis.lower() == "q":
            self._session.write_variable(_VAR_SQWAVE_IDQ_Q, amp_counts)
            self._session.write_variable(_VAR_SQWAVE_IDQ_D, 0)
        elif axis.lower() == "d":
            self._session.write_variable(_VAR_SQWAVE_IDQ_D, amp_counts)
            self._session.write_variable(_VAR_SQWAVE_IDQ_Q, 0)
        else:
            raise ValueError(f"axis must be 'q' or 'd', got {axis!r}")

        self._session.write_variable(_VAR_SQWAVE_VALUE, 1)
        logger.info(
            "Started step test: axis=%s, amplitude=%.3f A (%d counts), "
            "halfperiod=%.2f ms (%d cycles)",
            axis, amplitude if units == "engineering" else self.counts_to_amps(amp_counts),
            amp_counts,
            halfperiod if units == "engineering" else self.isr_cycles_to_ms(hp_cycles),
            hp_cycles,
        )

    def stop_perturbation(self) -> None:
        """Stop the square-wave perturbation signal."""
        self._session.write_variable(_VAR_SQWAVE_VALUE, 0)
        logger.info("Stopped perturbation")
