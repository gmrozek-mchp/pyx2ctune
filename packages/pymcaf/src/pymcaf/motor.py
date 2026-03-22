"""Typed access to MCAF motor control variables.

Provides a :class:`Motor` class with property-based read/write access
to motor signals, commands, duty cycles, and PI gains -- all in
engineering units (Amps, Volts, RPM, fractional duty cycle).

Property names use generic FOC terminology.  MCAF-specific firmware
variable paths are internal constants.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pymcaf.constants import MOTOR_STATES
from pymcaf.types import (
    ABCTriple,
    AlphaBetaPair,
    DQPair,
    MotorState,
)

if TYPE_CHECKING:
    from pymcaf.connection import Connection

logger = logging.getLogger(__name__)

# ── MCAF firmware variable paths (internal) ──────────────────────────

_VAR_IDQ_D = "motor.idq.d"
_VAR_IDQ_Q = "motor.idq.q"
_VAR_IALPHABETA_ALPHA = "motor.ialphabeta.alpha"
_VAR_IALPHABETA_BETA = "motor.ialphabeta.beta"
_VAR_IABC_A = "motor.iabc.a"
_VAR_IABC_B = "motor.iabc.b"

_VAR_VDQ_D = "motor.vdq.d"
_VAR_VDQ_Q = "motor.vdq.q"
_VAR_VALPHABETA_ALPHA = "motor.valphabeta.alpha"
_VAR_VALPHABETA_BETA = "motor.valphabeta.beta"
_VAR_VABC_A = "motor.vabc.a"
_VAR_VABC_B = "motor.vabc.b"
_VAR_VABC_C = "motor.vabc.c"

_VAR_IDQCMDRAW_D = "motor.idqCmdRaw.d"
_VAR_IDQCMDRAW_Q = "motor.idqCmdRaw.q"
_VAR_IDQCMD_D = "motor.idqCmd.d"
_VAR_IDQCMD_Q = "motor.idqCmd.q"
_VAR_VDQCMD_D = "motor.vdqCmd.d"
_VAR_VDQCMD_Q = "motor.vdqCmd.q"

_VAR_VELOCITY_CMD = "motor.velocityControl.velocityCmd"
_VAR_VELOCITY_CMD_RL = "motor.velocityControl.velocityCmdRateLimited"
_VAR_OMEGA_CMD = "motor.omegaCmd"
_VAR_OMEGA_ELECTRICAL = "motor.omegaElectrical"
_VAR_THETA_ELECTRICAL = "motor.thetaElectrical"

_VAR_VDC = "systemData.vDC"
_VAR_MOTOR_STATE = "motor.state"

_VAR_DABC_RAW_A = "motor.dabcRaw.a"
_VAR_DABC_RAW_B = "motor.dabcRaw.b"
_VAR_DABC_RAW_C = "motor.dabcRaw.c"
_VAR_DABC_UNSHIFTED_A = "motor.dabcUnshifted.a"
_VAR_DABC_UNSHIFTED_B = "motor.dabcUnshifted.b"
_VAR_DABC_UNSHIFTED_C = "motor.dabcUnshifted.c"
_VAR_DABC_A = "motor.dabc.a"
_VAR_DABC_B = "motor.dabc.b"
_VAR_DABC_C = "motor.dabc.c"

# PI gain variable paths per axis
_CURRENT_GAIN_VARS = {
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

_VELOCITY_GAIN_VARS = {
    "kp": "motor.omegaCtrl.kp",
    "ki": "motor.omegaCtrl.ki",
    "nkp": "motor.omegaCtrl.nkp",
    "nki": "motor.omegaCtrl.nki",
}

# parameters.json keys
_FS_CURRENT = "mcapi.fullscale.current"
_FS_VOLTAGE = "mcapi.fullscale.voltage"
_FS_VELOCITY = "mcapi.fullscale.velocity"
_PARAM_KIP = "foc.kip"
_PARAM_KII = "foc.kii"
_PARAM_KWP = "foc.kwp"
_PARAM_KWI = "foc.kwi"

# Q15 duty-cycle scale (firmware represents 0..1 as 0..32768)
_DUTY_SCALE = 32768.0


class Motor:
    """Typed access to MCAF motor control variables in engineering units.

    All current values are in Amps, voltages in Volts, velocities in RPM,
    and duty cycles as fractional values (0.0 to 1.0).

    Instantiated automatically by :attr:`pymcaf.Connection.motor`.
    """

    # ── Public variable identifiers ───────────────────────────────────
    #
    # Generic motor control names mapped to framework-specific firmware
    # variable identifiers.  Other SDKs (e.g. pyqspin) would expose the
    # same constant names with their own framework-specific values.

    VAR_CURRENT_DQ_D: str = _VAR_IDQ_D
    """Measured d-axis current."""
    VAR_CURRENT_DQ_Q: str = _VAR_IDQ_Q
    """Measured q-axis current."""
    VAR_CURRENT_CMD_DQ_D: str = _VAR_IDQCMD_D
    """d-axis current command (post-perturbation)."""
    VAR_CURRENT_CMD_DQ_Q: str = _VAR_IDQCMD_Q
    """q-axis current command (post-perturbation)."""
    VAR_VOLTAGE_DQ_D: str = _VAR_VDQ_D
    """d-axis output voltage."""
    VAR_VOLTAGE_DQ_Q: str = _VAR_VDQ_Q
    """q-axis output voltage."""
    VAR_VELOCITY: str = _VAR_OMEGA_ELECTRICAL
    """Estimated electrical velocity."""
    VAR_VELOCITY_CMD: str = _VAR_VELOCITY_CMD
    """Velocity command (user input)."""
    VAR_VELOCITY_REF: str = _VAR_OMEGA_CMD
    """Velocity reference to speed controller (post rate-limiting)."""

    def __init__(self, conn: Connection):
        self._conn = conn

    # ── Helpers ────────────────────────────────────────────────────────

    def _read_dq(self, d_var: str, q_var: str, fs: str) -> DQPair:
        return DQPair(
            d=self._conn.read_q15(d_var, fs),
            q=self._conn.read_q15(q_var, fs),
        )

    def _write_dq(self, d_var: str, q_var: str, fs: str, val: DQPair) -> None:
        self._conn.write_q15(d_var, val.d, fs)
        self._conn.write_q15(q_var, val.q, fs)

    def _read_ab(self, a_var: str, b_var: str, fs: str) -> AlphaBetaPair:
        return AlphaBetaPair(
            alpha=self._conn.read_q15(a_var, fs),
            beta=self._conn.read_q15(b_var, fs),
        )

    def _read_abc_q15(self, a: str, b: str, c: str, fs: str) -> ABCTriple:
        return ABCTriple(
            a=self._conn.read_q15(a, fs),
            b=self._conn.read_q15(b, fs),
            c=self._conn.read_q15(c, fs),
        )

    def _read_abc_duty(self, a: str, b: str, c: str) -> ABCTriple:
        return ABCTriple(
            a=self._conn.read_raw(a) / _DUTY_SCALE,
            b=self._conn.read_raw(b) / _DUTY_SCALE,
            c=self._conn.read_raw(c) / _DUTY_SCALE,
        )

    def _read_pi_gain(
        self, gain_var: str, shift_var: str, param_key: str,
    ) -> tuple[float, int, int]:
        """Read a PI gain and convert to engineering units.

        Accounts for the runtime shift count (nkp/nki) to compute the
        effective Q-format before converting.

        Returns:
            Tuple of (engineering_value, raw_counts, effective_q).
        """
        params = self._conn._require_params()
        counts = int(self._conn.read_raw(gain_var))
        nkp = int(self._conn.read_raw(shift_var))
        info = params.get_info(param_key)
        effective_q = 15 - nkp
        eng_value = (counts / (1 << effective_q)) * info.scale
        return eng_value, counts, effective_q

    def _write_pi_gain(
        self, gain_var: str, shift_var: str, param_key: str, value: float,
    ) -> tuple[int, int]:
        """Convert an engineering gain value and write to firmware.

        Computes the fixed-point representation, adjusting the shift
        count if the value overflows Q15.  Writes both the gain and
        shift variables to firmware.

        Returns:
            Tuple of (counts, nkp) actually written.
        """
        params = self._conn._require_params()
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

        self._conn.write_raw(gain_var, counts)
        self._conn.write_raw(shift_var, nkp)
        return counts, nkp

    # ── Measured signals (read-only) ──────────────────────────────────

    @property
    def idq(self) -> DQPair:
        """Measured dq-frame current (Amps)."""
        return self._read_dq(_VAR_IDQ_D, _VAR_IDQ_Q, _FS_CURRENT)

    @property
    def ialphabeta(self) -> AlphaBetaPair:
        """Measured stationary-frame current (Amps)."""
        return self._read_ab(
            _VAR_IALPHABETA_ALPHA, _VAR_IALPHABETA_BETA, _FS_CURRENT,
        )

    @property
    def iabc(self) -> ABCTriple:
        """Measured three-phase current (Amps).

        MCAF typically only measures phases a and b; c may be derived.
        """
        return ABCTriple(
            a=self._conn.read_q15(_VAR_IABC_A, _FS_CURRENT),
            b=self._conn.read_q15(_VAR_IABC_B, _FS_CURRENT),
            c=0.0,
        )

    @property
    def vdq(self) -> DQPair:
        """Output dq-frame voltage (Volts)."""
        return self._read_dq(_VAR_VDQ_D, _VAR_VDQ_Q, _FS_VOLTAGE)

    @property
    def valphabeta(self) -> AlphaBetaPair:
        """Output stationary-frame voltage (Volts)."""
        return self._read_ab(
            _VAR_VALPHABETA_ALPHA, _VAR_VALPHABETA_BETA, _FS_VOLTAGE,
        )

    @property
    def vabc(self) -> ABCTriple:
        """Desired phase voltages (Volts)."""
        return self._read_abc_q15(
            _VAR_VABC_A, _VAR_VABC_B, _VAR_VABC_C, _FS_VOLTAGE,
        )

    @property
    def omega(self) -> float:
        """Estimated motor velocity (RPM)."""
        return self._conn.read_q15(_VAR_OMEGA_ELECTRICAL, _FS_VELOCITY)

    @property
    def theta_electrical(self) -> float:
        """Electrical angle (degrees, 0-360)."""
        return int(self._conn.read_raw(_VAR_THETA_ELECTRICAL)) * (360.0 / 65536.0)

    @property
    def vdc(self) -> float:
        """DC link voltage (Volts)."""
        return self._conn.read_q15(_VAR_VDC, _FS_VOLTAGE)

    @property
    def state(self) -> MotorState:
        """Motor state machine state."""
        value = int(self._conn.read_raw(_VAR_MOTOR_STATE))
        name = MOTOR_STATES.get(value, f"UNKNOWN({value})")
        return MotorState(value=value, name=name)

    # ── Command signals ───────────────────────────────────────────────

    @property
    def idq_cmd_raw(self) -> DQPair:
        """Current command pre-perturbation (Amps)."""
        return self._read_dq(_VAR_IDQCMDRAW_D, _VAR_IDQCMDRAW_Q, _FS_CURRENT)

    @idq_cmd_raw.setter
    def idq_cmd_raw(self, value: DQPair) -> None:
        self._write_dq(_VAR_IDQCMDRAW_D, _VAR_IDQCMDRAW_Q, _FS_CURRENT, value)

    @property
    def idq_cmd(self) -> DQPair:
        """Current command post-perturbation (Amps, read-only)."""
        return self._read_dq(_VAR_IDQCMD_D, _VAR_IDQCMD_Q, _FS_CURRENT)

    @property
    def vdq_cmd(self) -> DQPair:
        """Voltage command (Volts)."""
        return self._read_dq(_VAR_VDQCMD_D, _VAR_VDQCMD_Q, _FS_VOLTAGE)

    @vdq_cmd.setter
    def vdq_cmd(self, value: DQPair) -> None:
        self._write_dq(_VAR_VDQCMD_D, _VAR_VDQCMD_Q, _FS_VOLTAGE, value)

    @property
    def velocity_cmd(self) -> float:
        """Velocity command (RPM)."""
        return self._conn.read_q15(_VAR_VELOCITY_CMD, _FS_VELOCITY)

    @velocity_cmd.setter
    def velocity_cmd(self, value: float) -> None:
        self._conn.write_q15(_VAR_VELOCITY_CMD, value, _FS_VELOCITY)

    @property
    def velocity_cmd_rate_limited(self) -> float:
        """Rate-limited velocity command (RPM, read-only)."""
        return self._conn.read_q15(_VAR_VELOCITY_CMD_RL, _FS_VELOCITY)

    # ── Duty cycles ───────────────────────────────────────────────────

    @property
    def dabc_raw(self) -> ABCTriple:
        """Duty cycles before dead-time compensation, ZSM, and clipping (0.0-1.0)."""
        return self._read_abc_duty(
            _VAR_DABC_RAW_A, _VAR_DABC_RAW_B, _VAR_DABC_RAW_C,
        )

    @property
    def dabc_unshifted(self) -> ABCTriple:
        """Duty cycles after dead-time comp, before ZSM and clipping (0.0-1.0)."""
        return self._read_abc_duty(
            _VAR_DABC_UNSHIFTED_A, _VAR_DABC_UNSHIFTED_B, _VAR_DABC_UNSHIFTED_C,
        )

    @property
    def dabc(self) -> ABCTriple:
        """Final duty cycles after ZSM and clipping (0.0-1.0)."""
        return self._read_abc_duty(_VAR_DABC_A, _VAR_DABC_B, _VAR_DABC_C)

    @dabc.setter
    def dabc(self, value: ABCTriple) -> None:
        self._conn.write_raw(_VAR_DABC_A, round(value.a * _DUTY_SCALE))
        self._conn.write_raw(_VAR_DABC_B, round(value.b * _DUTY_SCALE))
        self._conn.write_raw(_VAR_DABC_C, round(value.c * _DUTY_SCALE))

    # ── Current loop PI gains ────────────────────────────────────────

    @property
    def current_kp_d(self) -> float:
        """D-axis current loop proportional gain (V/A)."""
        v = _CURRENT_GAIN_VARS["d"]
        eng, _, _ = self._read_pi_gain(v["kp"], v["nkp"], _PARAM_KIP)
        return eng

    @current_kp_d.setter
    def current_kp_d(self, value: float) -> None:
        v = _CURRENT_GAIN_VARS["d"]
        self._write_pi_gain(v["kp"], v["nkp"], _PARAM_KIP, value)

    @property
    def current_ki_d(self) -> float:
        """D-axis current loop integral gain (V/A/s)."""
        v = _CURRENT_GAIN_VARS["d"]
        eng, _, _ = self._read_pi_gain(v["ki"], v["nki"], _PARAM_KII)
        return eng

    @current_ki_d.setter
    def current_ki_d(self, value: float) -> None:
        v = _CURRENT_GAIN_VARS["d"]
        self._write_pi_gain(v["ki"], v["nki"], _PARAM_KII, value)

    @property
    def current_kp_q(self) -> float:
        """Q-axis current loop proportional gain (V/A)."""
        v = _CURRENT_GAIN_VARS["q"]
        eng, _, _ = self._read_pi_gain(v["kp"], v["nkp"], _PARAM_KIP)
        return eng

    @current_kp_q.setter
    def current_kp_q(self, value: float) -> None:
        v = _CURRENT_GAIN_VARS["q"]
        self._write_pi_gain(v["kp"], v["nkp"], _PARAM_KIP, value)

    @property
    def current_ki_q(self) -> float:
        """Q-axis current loop integral gain (V/A/s)."""
        v = _CURRENT_GAIN_VARS["q"]
        eng, _, _ = self._read_pi_gain(v["ki"], v["nki"], _PARAM_KII)
        return eng

    @current_ki_q.setter
    def current_ki_q(self, value: float) -> None:
        v = _CURRENT_GAIN_VARS["q"]
        self._write_pi_gain(v["ki"], v["nki"], _PARAM_KII, value)

    # ── Velocity loop PI gains ────────────────────────────────────────

    @property
    def velocity_kp(self) -> float:
        """Velocity loop proportional gain (A/(rad/s))."""
        eng, _, _ = self._read_pi_gain(
            _VELOCITY_GAIN_VARS["kp"], _VELOCITY_GAIN_VARS["nkp"], _PARAM_KWP,
        )
        return eng

    @velocity_kp.setter
    def velocity_kp(self, value: float) -> None:
        self._write_pi_gain(
            _VELOCITY_GAIN_VARS["kp"], _VELOCITY_GAIN_VARS["nkp"],
            _PARAM_KWP, value,
        )

    @property
    def velocity_ki(self) -> float:
        """Velocity loop integral gain (A/rad)."""
        eng, _, _ = self._read_pi_gain(
            _VELOCITY_GAIN_VARS["ki"], _VELOCITY_GAIN_VARS["nki"], _PARAM_KWI,
        )
        return eng

    @velocity_ki.setter
    def velocity_ki(self, value: float) -> None:
        self._write_pi_gain(
            _VELOCITY_GAIN_VARS["ki"], _VELOCITY_GAIN_VARS["nki"],
            _PARAM_KWI, value,
        )

    def __repr__(self) -> str:
        return f"Motor(conn={self._conn!r})"
