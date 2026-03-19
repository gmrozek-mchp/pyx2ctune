"""Current loop PI gain tuning.

Provides methods to read/write PI gains in engineering units,
configure square-wave perturbation for step response testing,
and manage shift counts for gain overflow.

Reference: https://microchiptech.github.io/mcaf-doc/9.0.1/algorithms/foc/tuning.html
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyx2ctune.connection import TuningSession

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

# parameters.json keys for gain scaling
_PARAM_KIP = "foc.kip"
_PARAM_KII = "foc.kii"


@dataclass
class CurrentGains:
    """Current loop PI gains in engineering units."""

    kp: float
    ki: float
    kp_counts: int
    ki_counts: int
    kp_shift: int
    ki_shift: int
    kp_units: str = "V/A"
    ki_units: str = "V/A/s"


class CurrentTuning:
    """Current loop PI gain tuning interface.

    Reads and writes PI gains for the d-axis and q-axis current loops,
    converting between engineering units (V/A, V/A/s) and firmware
    fixed-point counts using the ParameterDB.
    """

    def __init__(self, session: TuningSession):
        self._session = session

    def get_gains(self, axis: str = "q") -> CurrentGains:
        """Read current PI gains from firmware and convert to engineering units.

        Args:
            axis: "q" or "d" (which current loop to read).

        Returns:
            CurrentGains with both engineering values and raw counts.
        """
        axis = axis.lower()
        if axis not in _GAIN_VARS:
            raise ValueError(f"axis must be 'q' or 'd', got {axis!r}")

        vars_ = _GAIN_VARS[axis]
        kp_counts = int(self._session.read_variable(vars_["kp"]))
        ki_counts = int(self._session.read_variable(vars_["ki"]))
        nkp = int(self._session.read_variable(vars_["nkp"]))
        nki = int(self._session.read_variable(vars_["nki"]))

        params = self._session.params
        if params is not None:
            kp_info = params.get_info(_PARAM_KIP)
            ki_info = params.get_info(_PARAM_KII)
            kp_eng = (kp_counts / (1 << nkp)) * kp_info.scale
            ki_eng = (ki_counts / (1 << nki)) * ki_info.scale
        else:
            kp_eng = float(kp_counts)
            ki_eng = float(ki_counts)

        result = CurrentGains(
            kp=kp_eng,
            ki=ki_eng,
            kp_counts=kp_counts,
            ki_counts=ki_counts,
            kp_shift=nkp,
            ki_shift=nki,
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
    ) -> CurrentGains:
        """Set current loop PI gains.

        When units="engineering", kp is in V/A and ki is in V/A/s.
        The method converts to fixed-point counts using ParameterDB and
        manages shift counts to handle potential overflow.

        When units="counts", kp and ki are written directly as integer counts
        (shift counts are not modified).

        Args:
            kp: Proportional gain.
            ki: Integral gain.
            units: "engineering" or "counts".
            axes: "both", "q", or "d" -- which axes to write.

        Returns:
            CurrentGains reflecting the values actually written.
        """
        if units == "counts":
            kp_counts = int(kp)
            ki_counts = int(ki)
            nkp = None
            nki = None
        elif units == "engineering":
            kp_counts, nkp = self._engineering_to_counts_with_shift(
                _PARAM_KIP, kp
            )
            ki_counts, nki = self._engineering_to_counts_with_shift(
                _PARAM_KII, ki
            )
        else:
            raise ValueError(f"units must be 'engineering' or 'counts', got {units!r}")

        target_axes = self._resolve_axes(axes)

        for axis in target_axes:
            vars_ = _GAIN_VARS[axis]
            self._session.write_variable(vars_["kp"], kp_counts)
            self._session.write_variable(vars_["ki"], ki_counts)
            if nkp is not None:
                self._session.write_variable(vars_["nkp"], nkp)
            if nki is not None:
                self._session.write_variable(vars_["nki"], nki)

        actual_nkp = nkp if nkp is not None else int(
            self._session.read_variable(_GAIN_VARS[target_axes[0]]["nkp"])
        )
        actual_nki = nki if nki is not None else int(
            self._session.read_variable(_GAIN_VARS[target_axes[0]]["nki"])
        )

        result = CurrentGains(
            kp=kp if units == "engineering" else float(kp_counts),
            ki=ki if units == "engineering" else float(ki_counts),
            kp_counts=kp_counts,
            ki_counts=ki_counts,
            kp_shift=actual_nkp,
            ki_shift=actual_nki,
        )
        logger.info(
            "Set current gains: Kp=%.4f %s (counts=%d, Q%d), "
            "Ki=%.2f %s (counts=%d, Q%d) on axes=%s",
            result.kp, result.kp_units, result.kp_counts, result.kp_shift,
            result.ki, result.ki_units, result.ki_counts, result.ki_shift,
            axes,
        )
        return result

    def _engineering_to_counts_with_shift(
        self, param_key: str, value: float
    ) -> tuple[int, int]:
        """Convert an engineering value to counts, adjusting shift if needed.

        If the value overflows at the default Q-format, reduce the shift count
        and scale the counts accordingly to stay within int16 range.

        Returns:
            (counts, shift) tuple.
        """
        params = self._session.params
        if params is None:
            raise RuntimeError(
                "ParameterDB required for engineering unit conversion. "
                "Pass parameters_json to TuningSession."
            )

        info = params.get_info(param_key)
        base_q = info.q
        raw_counts = value / info.scale * (1 << base_q)

        shift = base_q
        counts = round(raw_counts)

        while not (-32768 <= counts <= 32767) and shift > 0:
            shift -= 1
            counts = round(value / info.scale * (1 << shift))

        if not (-32768 <= counts <= 32767):
            raise ValueError(
                f"Cannot represent {value} {info.units} for {param_key!r} "
                f"in any Q format (min shift tried: Q{shift})"
            )

        return counts, shift

    @staticmethod
    def _resolve_axes(axes: str) -> list[str]:
        axes = axes.lower()
        if axes == "both":
            return ["d", "q"]
        if axes in ("d", "q"):
            return [axes]
        raise ValueError(f"axes must be 'both', 'q', or 'd', got {axes!r}")

    # ── Perturbation Control ──────────────────────────────────────────

    def setup_step_test(
        self,
        axis: str = "q",
        amplitude: int = 500,
        halfperiod: int = 100,
    ) -> None:
        """Configure and start a square-wave perturbation for step response testing.

        Args:
            axis: "q" or "d" -- which current axis to perturb.
            amplitude: Perturbation amplitude in raw counts.
            halfperiod: Half-period in PWM cycles. At 20kHz ISR rate,
                100 cycles = 5ms half-period = 100Hz square wave.
        """
        self._session.write_variable(_VAR_SQWAVE_HALFPERIOD, halfperiod)

        if axis.lower() == "q":
            self._session.write_variable(_VAR_SQWAVE_IDQ_Q, amplitude)
            self._session.write_variable(_VAR_SQWAVE_IDQ_D, 0)
        elif axis.lower() == "d":
            self._session.write_variable(_VAR_SQWAVE_IDQ_D, amplitude)
            self._session.write_variable(_VAR_SQWAVE_IDQ_Q, 0)
        else:
            raise ValueError(f"axis must be 'q' or 'd', got {axis!r}")

        self._session.write_variable(_VAR_SQWAVE_VALUE, 1)
        logger.info(
            "Started step test: axis=%s, amplitude=%d counts, halfperiod=%d cycles",
            axis, amplitude, halfperiod,
        )

    def stop_perturbation(self) -> None:
        """Stop the square-wave perturbation signal."""
        self._session.write_variable(_VAR_SQWAVE_VALUE, 0)
        logger.info("Stopped perturbation")
