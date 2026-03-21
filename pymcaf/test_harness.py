"""MCAF test harness interface.

Provides typed access to the MCAF runtime test harness: guard
management, operating modes, override flags, state transitions,
and perturbation signal configuration.

All amplitude values use engineering units (Amps, Volts, RPM).
MCAF-specific firmware variable paths are internal constants.

Reference: https://microchiptech.github.io/mcaf-doc/9.0.1/components/testharness.html
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from pymcaf.constants import (
    GUARD_KEY_RESET,
    GUARD_KEY_VALID,
    GUARD_TIMEOUT_MAX,
    ForceState,
    OperatingMode,
    OverrideFlag,
)
from pymcaf.types import DQPair

if TYPE_CHECKING:
    from pymcaf.connection import Connection

logger = logging.getLogger(__name__)

# At 20 kHz ISR, 0xFFFF counts = ~3.27 seconds.  Refresh well before expiry.
_GUARD_REFRESH_INTERVAL_S = 1.5

# ── MCAF firmware variable paths (internal) ──────────────────────────

_VAR_GUARD_KEY = "systemData.testing.guard.key"
_VAR_GUARD_TIMEOUT = "systemData.testing.guard.timeout"
_VAR_OPERATING_MODE = "motor.testing.operatingMode"
_VAR_OVERRIDES = "motor.testing.overrides"
_VAR_FORCE_STATE = "motor.testing.forceStateChange"
_VAR_MOTOR_STATE = "motor.state"

_VAR_OVERRIDE_OMEGA = "motor.testing.overrideOmegaElectrical"
_VAR_OVERRIDE_COMM_MAX = "motor.testing.overrideCommutationOnOff.maxCount"
_VAR_OVERRIDE_COMM_THRESH = "motor.testing.overrideCommutationOnOff.threshold"
_VAR_OVERRIDE_ZSM_OFFSET = "motor.testing.overrideZeroSequenceOffset"

# Square wave perturbation
_VAR_SQ_VALUE = "motor.testing.sqwave.value"
_VAR_SQ_HALFPERIOD = "motor.testing.sqwave.halfperiod"
_VAR_SQ_IDQ_D = "motor.testing.sqwave.idq.d"
_VAR_SQ_IDQ_Q = "motor.testing.sqwave.idq.q"
_VAR_SQ_VEL_ELEC = "motor.testing.sqwave.velocity.electrical"
_VAR_SQ_VDQ_D = "motor.testing.sqwave.vdq.d"
_VAR_SQ_VDQ_Q = "motor.testing.sqwave.vdq.q"

# Asymmetric perturbation
_VAR_AP_ENABLE = "motor.testing.perturb.enable"
_VAR_AP_AUTOBALANCE = "motor.testing.perturb.autobalanceRatio"
_VAR_AP_STEP_COUNT = "motor.testing.perturb.step.count"
_VAR_AP_STEP_IDQ_D = "motor.testing.perturb.step.idq.d"
_VAR_AP_STEP_IDQ_Q = "motor.testing.perturb.step.idq.q"

# Current command (used by mode-entry procedures)
_VAR_IDQCMDRAW_D = "motor.idqCmdRaw.d"
_VAR_IDQCMDRAW_Q = "motor.idqCmdRaw.q"

# Fullscale parameter keys
_FS_CURRENT = "mcapi.fullscale.current"
_FS_VOLTAGE = "mcapi.fullscale.voltage"
_FS_VELOCITY = "mcapi.fullscale.velocity"


def _ap_phase_var(phase: int, suffix: str) -> str:
    """Build an asymmetric perturbation phase variable path."""
    return f"motor.testing.perturb.phase[{phase}].{suffix}"


# ── Perturbation sub-interfaces ──────────────────────────────────────


class SquareWavePerturbation:
    """Symmetric square-wave perturbation control.

    Access via :attr:`TestHarness.sqwave`.
    """

    def __init__(self, conn: Connection):
        self._conn = conn

    @property
    def active(self) -> bool:
        """Whether the square wave is currently running."""
        return int(self._conn.read_raw(_VAR_SQ_VALUE)) != 0

    def start(self) -> None:
        """Start the square wave (sets ``sqwave.value = 1``)."""
        self._conn.write_raw(_VAR_SQ_VALUE, 1)
        logger.info("Square wave perturbation started")

    def stop(self) -> None:
        """Stop the square wave (sets ``sqwave.value = 0``)."""
        self._conn.write_raw(_VAR_SQ_VALUE, 0)
        logger.info("Square wave perturbation stopped")

    @property
    def halfperiod(self) -> int:
        """Half-period in PWM/ISR cycles."""
        return int(self._conn.read_raw(_VAR_SQ_HALFPERIOD))

    @halfperiod.setter
    def halfperiod(self, value: int) -> None:
        self._conn.write_raw(_VAR_SQ_HALFPERIOD, int(value))

    @property
    def idq_amplitude(self) -> DQPair:
        """Current perturbation amplitude (Amps)."""
        return DQPair(
            d=self._conn.read_q15(_VAR_SQ_IDQ_D, _FS_CURRENT),
            q=self._conn.read_q15(_VAR_SQ_IDQ_Q, _FS_CURRENT),
        )

    @idq_amplitude.setter
    def idq_amplitude(self, value: DQPair) -> None:
        self._conn.write_q15(_VAR_SQ_IDQ_D, value.d, _FS_CURRENT)
        self._conn.write_q15(_VAR_SQ_IDQ_Q, value.q, _FS_CURRENT)

    @property
    def velocity_amplitude(self) -> float:
        """Velocity perturbation amplitude (RPM)."""
        return self._conn.read_q15(_VAR_SQ_VEL_ELEC, _FS_VELOCITY)

    @velocity_amplitude.setter
    def velocity_amplitude(self, value: float) -> None:
        self._conn.write_q15(_VAR_SQ_VEL_ELEC, value, _FS_VELOCITY)

    @property
    def vdq_amplitude(self) -> DQPair:
        """Voltage perturbation amplitude (Volts)."""
        return DQPair(
            d=self._conn.read_q15(_VAR_SQ_VDQ_D, _FS_VOLTAGE),
            q=self._conn.read_q15(_VAR_SQ_VDQ_Q, _FS_VOLTAGE),
        )

    @vdq_amplitude.setter
    def vdq_amplitude(self, value: DQPair) -> None:
        self._conn.write_q15(_VAR_SQ_VDQ_D, value.d, _FS_VOLTAGE)
        self._conn.write_q15(_VAR_SQ_VDQ_Q, value.q, _FS_VOLTAGE)


class _AsymmetricPhase:
    """Configuration for one phase of an asymmetric perturbation waveform."""

    def __init__(self, conn: Connection, phase: int):
        self._conn = conn
        self._phase = phase

    @property
    def duration(self) -> int:
        """Phase duration in PWM/ISR cycles."""
        return int(self._conn.read_raw(_ap_phase_var(self._phase, "duration")))

    @duration.setter
    def duration(self, value: int) -> None:
        self._conn.write_raw(_ap_phase_var(self._phase, "duration"), int(value))

    @property
    def idq_amplitude(self) -> DQPair:
        """Current perturbation amplitude for this phase (Amps)."""
        return DQPair(
            d=self._conn.read_q15(
                _ap_phase_var(self._phase, "idq.d"), _FS_CURRENT,
            ),
            q=self._conn.read_q15(
                _ap_phase_var(self._phase, "idq.q"), _FS_CURRENT,
            ),
        )

    @idq_amplitude.setter
    def idq_amplitude(self, value: DQPair) -> None:
        self._conn.write_q15(
            _ap_phase_var(self._phase, "idq.d"), value.d, _FS_CURRENT,
        )
        self._conn.write_q15(
            _ap_phase_var(self._phase, "idq.q"), value.q, _FS_CURRENT,
        )

    @property
    def velocity_amplitude(self) -> float:
        """Velocity perturbation amplitude for this phase (RPM)."""
        return self._conn.read_q15(
            _ap_phase_var(self._phase, "velocity.electrical"), _FS_VELOCITY,
        )

    @velocity_amplitude.setter
    def velocity_amplitude(self, value: float) -> None:
        self._conn.write_q15(
            _ap_phase_var(self._phase, "velocity.electrical"), value, _FS_VELOCITY,
        )

    @property
    def vdq_amplitude(self) -> DQPair:
        """Voltage perturbation amplitude for this phase (Volts)."""
        return DQPair(
            d=self._conn.read_q15(
                _ap_phase_var(self._phase, "vdq.d"), _FS_VOLTAGE,
            ),
            q=self._conn.read_q15(
                _ap_phase_var(self._phase, "vdq.q"), _FS_VOLTAGE,
            ),
        )

    @vdq_amplitude.setter
    def vdq_amplitude(self, value: DQPair) -> None:
        self._conn.write_q15(
            _ap_phase_var(self._phase, "vdq.d"), value.d, _FS_VOLTAGE,
        )
        self._conn.write_q15(
            _ap_phase_var(self._phase, "vdq.q"), value.q, _FS_VOLTAGE,
        )


class AsymmetricPerturbation:
    """Asymmetric pulse waveform perturbation control (MCAF R7+).

    Access via :attr:`TestHarness.asymmetric`.
    """

    def __init__(self, conn: Connection):
        self._conn = conn
        self._phases = [_AsymmetricPhase(conn, 0), _AsymmetricPhase(conn, 1)]

    @property
    def active(self) -> bool:
        """Whether the asymmetric perturbation is running."""
        return int(self._conn.read_raw(_VAR_AP_ENABLE)) != 0

    def start(self) -> None:
        """Start the asymmetric perturbation."""
        self._conn.write_raw(_VAR_AP_ENABLE, 1)
        logger.info("Asymmetric perturbation started")

    def stop(self) -> None:
        """Stop the asymmetric perturbation."""
        self._conn.write_raw(_VAR_AP_ENABLE, 0)
        logger.info("Asymmetric perturbation stopped")

    def phase(self, k: int) -> _AsymmetricPhase:
        """Get configuration for phase *k* (0 or 1).

        Args:
            k: Phase index (0 or 1).
        """
        if k not in (0, 1):
            raise ValueError(f"Phase index must be 0 or 1, got {k}")
        return self._phases[k]

    @property
    def autobalance_ratio(self) -> float:
        """Autobalance ratio (Q16 stored, returned as float 0.0-1.0)."""
        raw = self._conn.read_raw(_VAR_AP_AUTOBALANCE)
        return raw / 65536.0

    @autobalance_ratio.setter
    def autobalance_ratio(self, value: float) -> None:
        self._conn.write_raw(_VAR_AP_AUTOBALANCE, round(value * 65536))

    @property
    def step_count(self) -> int:
        """Number of times to step the current per phase."""
        return int(self._conn.read_raw(_VAR_AP_STEP_COUNT))

    @step_count.setter
    def step_count(self, value: int) -> None:
        self._conn.write_raw(_VAR_AP_STEP_COUNT, int(value))

    @property
    def step_idq(self) -> DQPair:
        """Current step size per iteration (Amps)."""
        return DQPair(
            d=self._conn.read_q15(_VAR_AP_STEP_IDQ_D, _FS_CURRENT),
            q=self._conn.read_q15(_VAR_AP_STEP_IDQ_Q, _FS_CURRENT),
        )

    @step_idq.setter
    def step_idq(self, value: DQPair) -> None:
        self._conn.write_q15(_VAR_AP_STEP_IDQ_D, value.d, _FS_CURRENT)
        self._conn.write_q15(_VAR_AP_STEP_IDQ_Q, value.q, _FS_CURRENT)


# ── Main TestHarness class ───────────────────────────────────────────


class TestHarness:
    """Interface to the MCAF runtime test harness.

    Provides guard management, operating mode control, override flags,
    forced state transitions, and perturbation signal configuration.

    Instantiated automatically by :attr:`pymcaf.Connection.test_harness`.
    """

    def __init__(self, conn: Connection):
        self._conn = conn
        self._guard_thread: threading.Thread | None = None
        self._guard_stop_event = threading.Event()
        self._guard_active = False

        self.sqwave = SquareWavePerturbation(conn)
        self.asymmetric = AsymmetricPerturbation(conn)

    # ── Guard management ──────────────────────────────────────────────

    @property
    def guard_active(self) -> bool:
        """Whether the test harness guard is currently enabled."""
        return self._guard_active

    def enable_guard(self) -> None:
        """Activate the test harness guard and start timeout refresh.

        Sets ``systemData.testing.guard.key = 0xD1A6`` and periodically
        refreshes the timeout counter to prevent automatic guard expiry.
        """
        if self._guard_active:
            logger.debug("Guard already active")
            return

        self._conn.write_raw(_VAR_GUARD_KEY, GUARD_KEY_VALID)
        self._conn.write_raw(_VAR_GUARD_TIMEOUT, GUARD_TIMEOUT_MAX)
        self._guard_active = True

        self._guard_stop_event.clear()
        self._guard_thread = threading.Thread(
            target=self._guard_refresh_loop,
            name="pymcaf-guard-refresh",
            daemon=True,
        )
        self._guard_thread.start()
        logger.info("Test harness guard enabled")

    def disable_guard(self) -> None:
        """Deactivate the test harness guard and stop the refresh thread."""
        if not self._guard_active:
            return

        self._guard_stop_event.set()
        if self._guard_thread is not None:
            self._guard_thread.join(timeout=3.0)
            self._guard_thread = None

        try:
            self._conn.write_raw(_VAR_GUARD_KEY, GUARD_KEY_RESET)
        except Exception:
            logger.warning("Failed to reset guard key", exc_info=True)

        self._guard_active = False
        logger.info("Test harness guard disabled")

    def _guard_refresh_loop(self) -> None:
        while not self._guard_stop_event.wait(timeout=_GUARD_REFRESH_INTERVAL_S):
            try:
                self._conn.write_raw(_VAR_GUARD_TIMEOUT, GUARD_TIMEOUT_MAX)
            except Exception:
                logger.warning("Guard timeout refresh failed", exc_info=True)

    # ── Operating mode ────────────────────────────────────────────────

    @property
    def operating_mode(self) -> OperatingMode:
        """Current test harness operating mode."""
        value = self._conn.read_raw(_VAR_OPERATING_MODE)
        return OperatingMode(int(value))

    @operating_mode.setter
    def operating_mode(self, mode: OperatingMode | int) -> None:
        self._conn.write_raw(_VAR_OPERATING_MODE, int(mode))
        logger.info("Operating mode set to %s", OperatingMode(mode).name)

    # ── Override flags ────────────────────────────────────────────────

    @property
    def overrides(self) -> int:
        """Raw override bitfield value."""
        return int(self._conn.read_raw(_VAR_OVERRIDES))

    @overrides.setter
    def overrides(self, flags: int) -> None:
        self._conn.write_raw(_VAR_OVERRIDES, flags)
        logger.debug("Overrides set to 0x%04X", flags)

    def set_override_flags(self, **kwargs: bool) -> None:
        """Set individual override flags by name.

        Keyword arguments correspond to :class:`~pymcaf.constants.OverrideFlag`
        member names in lowercase:

        - ``velocity_command``
        - ``commutation``
        - ``dc_link_compensation``
        - ``stall_detection``
        - ``startup_pause``
        - ``flux_control``
        - ``zero_sequence_modulation``
        """
        flag_map = {
            "velocity_command": OverrideFlag.VELOCITY_COMMAND,
            "commutation": OverrideFlag.COMMUTATION,
            "dc_link_compensation": OverrideFlag.DC_LINK_COMPENSATION,
            "stall_detection": OverrideFlag.STALL_DETECTION,
            "startup_pause": OverrideFlag.STARTUP_PAUSE,
            "flux_control": OverrideFlag.FLUX_CONTROL,
            "zero_sequence_modulation": OverrideFlag.ZERO_SEQUENCE_MODULATION,
        }

        current = self.overrides
        for name, enabled in kwargs.items():
            if name not in flag_map:
                raise ValueError(
                    f"Unknown override flag: {name!r}. "
                    f"Valid flags: {list(flag_map.keys())}"
                )
            if enabled:
                current |= flag_map[name]
            else:
                current &= ~flag_map[name]

        self.overrides = current

    # ── State transitions ─────────────────────────────────────────────

    def force_state(self, transition: ForceState | int) -> None:
        """Force a state machine transition.

        Args:
            transition: One of the :class:`~pymcaf.constants.ForceState` values.
        """
        self._conn.write_raw(_VAR_FORCE_STATE, int(transition))
        logger.info("Forced state transition: %s", ForceState(transition).name)

    # ── Commutation override ──────────────────────────────────────────

    @property
    def override_omega_electrical(self) -> int:
        """Commutation override frequency (raw int16 dtheta/dt counts).

        Note: this has different scaling than ``motor.omegaElectrical``.
        With N=1 k=1 at 20 kHz ISR, 1 count = ~0.305 Hz electrical.
        """
        return int(self._conn.read_raw(_VAR_OVERRIDE_OMEGA))

    @override_omega_electrical.setter
    def override_omega_electrical(self, value: int) -> None:
        self._conn.write_raw(_VAR_OVERRIDE_OMEGA, int(value))

    @property
    def commutation_on_off_max_count(self) -> int:
        """On-off commutation period N-1 (MCAF R4+)."""
        return int(self._conn.read_raw(_VAR_OVERRIDE_COMM_MAX))

    @commutation_on_off_max_count.setter
    def commutation_on_off_max_count(self, value: int) -> None:
        self._conn.write_raw(_VAR_OVERRIDE_COMM_MAX, int(value))

    @property
    def commutation_on_off_threshold(self) -> int:
        """On-off commutation active cycles k (MCAF R4+)."""
        return int(self._conn.read_raw(_VAR_OVERRIDE_COMM_THRESH))

    @commutation_on_off_threshold.setter
    def commutation_on_off_threshold(self, value: int) -> None:
        self._conn.write_raw(_VAR_OVERRIDE_COMM_THRESH, int(value))

    @property
    def override_zsm_offset(self) -> int:
        """Zero-sequence modulation override offset (raw counts)."""
        return int(self._conn.read_raw(_VAR_OVERRIDE_ZSM_OFFSET))

    @override_zsm_offset.setter
    def override_zsm_offset(self, value: int) -> None:
        self._conn.write_raw(_VAR_OVERRIDE_ZSM_OFFSET, int(value))

    # ── Documented mode entry/exit procedures ─────────────────────────

    def enter_current_mode(self) -> None:
        """Enter OM_FORCE_CURRENT mode safely.

        Follows MCAF section 4.5.15.2:
          1. Enable guard
          2. Set operatingMode = OM_DISABLED
          3. Zero dq current commands
          4. Set operatingMode = OM_FORCE_CURRENT
        """
        self.enable_guard()
        self.operating_mode = OperatingMode.DISABLED
        time.sleep(0.05)
        self._conn.write_raw(_VAR_IDQCMDRAW_D, 0)
        self._conn.write_raw(_VAR_IDQCMDRAW_Q, 0)
        self.operating_mode = OperatingMode.FORCE_CURRENT
        logger.info("Entered current test mode (OM_FORCE_CURRENT)")

    def enter_force_voltage_mode(self) -> None:
        """Enter OM_FORCE_VOLTAGE_DQ mode.

        Follows MCAF section 4.5.15.1:
          1. Enable guard
          2. Set operatingMode = OM_DISABLED
          3. Set commutation override
          4. Set operatingMode = OM_FORCE_VOLTAGE_DQ
        """
        self.enable_guard()
        self.operating_mode = OperatingMode.DISABLED
        time.sleep(0.05)
        self.set_override_flags(commutation=True)
        self.operating_mode = OperatingMode.FORCE_VOLTAGE_DQ
        logger.info("Entered force voltage DQ mode")

    def enter_velocity_override_mode(self) -> None:
        """Enter normal mode with velocity command override.

        Follows MCAF section 4.5.15.3:
          1. Enable guard
          2. Set velocity command override flag
          3. Force motor to RUN state
        """
        self.enable_guard()
        self.set_override_flags(velocity_command=True)
        self.force_state(ForceState.RUN)
        logger.info("Entered velocity override mode (forced RUN)")

    def exit_to_normal(self) -> None:
        """Return to normal operation safely.

        Steps:
          1. Stop any active perturbation
          2. Clear overrides
          3. Set operatingMode = OM_NORMAL
          4. Force state to STOP
          5. Disable guard
        """
        try:
            self.sqwave.stop()
        except Exception:
            pass
        try:
            self.asymmetric.stop()
        except Exception:
            pass

        try:
            self.overrides = 0
        except Exception:
            pass

        self.operating_mode = OperatingMode.NORMAL
        time.sleep(0.05)
        self.force_state(ForceState.STOP)
        self.disable_guard()
        logger.info("Exited test mode, returned to OM_NORMAL")

    def __repr__(self) -> str:
        return f"TestHarness(guard_active={self._guard_active})"
