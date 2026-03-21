"""MCAF test harness management.

Controls the runtime test harness in MCAF firmware (section 4.5):
guard key/timeout, operating modes, override flags, state transitions,
and perturbation signals.

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
    MOTOR_STATES,
    ForceState,
    OperatingMode,
    OverrideFlag,
)

from mctoolbox import interfaces as _interfaces

if TYPE_CHECKING:
    from mctoolbox.mcaf.session import TuningSession

logger = logging.getLogger(__name__)

# At 20kHz ISR, 0xFFFF counts = ~3.27 seconds.  Refresh well before expiry.
_GUARD_REFRESH_INTERVAL_S = 1.5

# Firmware variable paths
_VAR_GUARD_KEY = "systemData.testing.guard.key"
_VAR_GUARD_TIMEOUT = "systemData.testing.guard.timeout"
_VAR_OPERATING_MODE = "motor.testing.operatingMode"
_VAR_OVERRIDES = "motor.testing.overrides"
_VAR_FORCE_STATE = "motor.testing.forceStateChange"
_VAR_SQWAVE_VALUE = "motor.testing.sqwave.value"
_VAR_IDQCMDRAW_D = "motor.idqCmdRaw.d"
_VAR_IDQCMDRAW_Q = "motor.idqCmdRaw.q"
_VAR_OVERRIDE_OMEGA = "motor.testing.overrideOmegaElectrical"
_VAR_VDQ_CMD_D = "motor.vdqCmd.d"
_VAR_VDQ_CMD_Q = "motor.vdqCmd.q"
_VAR_MOTOR_STATE = "motor.state"

_PARAM_FULLSCALE_CURRENT = "mcapi.fullscale.current"
_PARAM_FULLSCALE_VOLTAGE = "mcapi.fullscale.voltage"
_PARAM_FULLSCALE_VELOCITY = "mcapi.fullscale.velocity"


class TestHarness(_interfaces.TestHarness):
    """Manages the MCAF runtime test harness.

    Handles guard key activation/refresh, operating mode transitions,
    override flags, and provides high-level methods for entering/exiting
    test modes safely.
    """

    def __init__(self, session: TuningSession):
        self._session = session
        self._guard_thread: threading.Thread | None = None
        self._guard_stop_event = threading.Event()
        self._guard_active = False

    # ── ABC interface ──────────────────────────────────────────────────

    def enter_test_mode(self, mode: str = "current") -> str:
        """Enter a test operating mode by name.

        Args:
            mode: One of "current", "velocity_override", "force_voltage".

        Returns:
            The name of the operating mode actually entered.
        """
        dispatch = {
            "current": self.enter_current_test_mode,
            "velocity_override": self.enter_velocity_override_mode,
            "force_voltage": self.enter_force_voltage_mode,
        }
        fn = dispatch.get(mode)
        if fn is None:
            raise ValueError(
                f"Unknown test mode {mode!r}; "
                f"choose from {list(dispatch)}"
            )
        fn()
        return self.get_operating_mode().name

    def exit_test_mode(self) -> None:
        """Return to normal operation safely.

        Steps:
          1. Stop any active perturbation
          2. Clear overrides
          3. Set operatingMode = OM_NORMAL
          4. Force state to STOP
          5. Disable guard
        """
        try:
            self._session.write_variable(_VAR_SQWAVE_VALUE, 0)
        except Exception:
            pass

        try:
            self.set_overrides(0)
        except Exception:
            pass

        self.set_operating_mode(OperatingMode.NORMAL)
        time.sleep(0.05)
        self.force_state(ForceState.STOP)
        self.disable_guard()
        logger.info("Exited test mode, returned to OM_NORMAL")

    def get_motor_state(self) -> _interfaces.MotorState:
        """Read the current motor state machine state."""
        value = int(self._session.read_variable(_VAR_MOTOR_STATE))
        name = MOTOR_STATES.get(value, f"UNKNOWN({value})")
        return _interfaces.MotorState(value=value, name=name)

    @property
    def guard_active(self) -> bool:
        return self._guard_active

    # ── Guard Management ──────────────────────────────────────────────

    def enable_guard(self) -> None:
        """Activate the test harness guard and start the timeout refresh thread.

        Sets systemData.testing.guard.key = 0xD1A6 and periodically
        refreshes the timeout counter to prevent automatic guard expiry.
        """
        if self._guard_active:
            logger.debug("Guard already active")
            return

        self._session.write_variable(_VAR_GUARD_KEY, GUARD_KEY_VALID)
        self._session.write_variable(_VAR_GUARD_TIMEOUT, GUARD_TIMEOUT_MAX)
        self._guard_active = True

        self._guard_stop_event.clear()
        self._guard_thread = threading.Thread(
            target=self._guard_refresh_loop,
            name="mctoolbox-guard-refresh",
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
            self._session.write_variable(_VAR_GUARD_KEY, GUARD_KEY_RESET)
        except Exception:
            logger.warning("Failed to reset guard key during disable", exc_info=True)

        self._guard_active = False
        logger.info("Test harness guard disabled")

    def _guard_refresh_loop(self) -> None:
        """Background thread that periodically refreshes the guard timeout."""
        while not self._guard_stop_event.wait(timeout=_GUARD_REFRESH_INTERVAL_S):
            try:
                self._session.write_variable(_VAR_GUARD_TIMEOUT, GUARD_TIMEOUT_MAX)
            except Exception:
                logger.warning("Guard timeout refresh failed", exc_info=True)

    # ── Operating Mode ────────────────────────────────────────────────

    def set_operating_mode(self, mode: OperatingMode | int) -> None:
        """Set the test harness operating mode.

        Args:
            mode: One of the OperatingMode enum values.
        """
        self._session.write_variable(_VAR_OPERATING_MODE, int(mode))
        logger.info("Operating mode set to %s", OperatingMode(mode).name)

    def get_operating_mode(self) -> OperatingMode:
        """Read the current operating mode from firmware."""
        value = self._session.read_variable(_VAR_OPERATING_MODE)
        return OperatingMode(int(value))

    # ── Overrides ─────────────────────────────────────────────────────

    def set_overrides(self, flags: int) -> None:
        """Set the override bitfield directly.

        Args:
            flags: Bitfield value combining OverrideFlag values.
        """
        self._session.write_variable(_VAR_OVERRIDES, flags)
        logger.debug("Overrides set to 0x%04X", flags)

    def get_overrides(self) -> int:
        """Read the current override bitfield."""
        return int(self._session.read_variable(_VAR_OVERRIDES))

    def set_override_flags(self, **kwargs: bool) -> None:
        """Set individual override flags by name.

        Args:
            velocity_command: Override velocity command input.
            commutation: Override commutation angle.
            dc_link_compensation: Override DC link compensation.
            stall_detection: Mask stall detection.
            startup_pause: Pause at end of open-loop startup.
            flux_control: Override flux control d-axis reference.
            zero_sequence_modulation: Override ZSM offset.
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

        current = self.get_overrides()
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

        self.set_overrides(current)

    # ── State Transitions ─────────────────────────────────────────────

    def force_state(self, transition: ForceState | int) -> None:
        """Force a state machine transition.

        Args:
            transition: One of the ForceState enum values.
        """
        self._session.write_variable(_VAR_FORCE_STATE, int(transition))
        logger.info("Forced state transition: %s", ForceState(transition).name)

    # ── High-Level Test Mode Methods ──────────────────────────────────

    def enter_current_test_mode(self) -> None:
        """Enter OM_FORCE_CURRENT mode safely.

        Follows the procedure from MCAF section 4.5.15.2 / 4.5.15.6:
          1. Enable guard
          2. Set operatingMode = OM_DISABLED
          3. Zero baseline dq current commands (idqCmdRaw)
          4. Set operatingMode = OM_FORCE_CURRENT
        """
        self.enable_guard()
        self.set_operating_mode(OperatingMode.DISABLED)
        time.sleep(0.05)
        self._session.write_variable(_VAR_IDQCMDRAW_D, 0)
        self._session.write_variable(_VAR_IDQCMDRAW_Q, 0)
        self.set_operating_mode(OperatingMode.FORCE_CURRENT)
        logger.info("Entered current test mode (OM_FORCE_CURRENT)")

    def enter_velocity_override_mode(self) -> None:
        """Enter normal mode with velocity command override.

        Follows the procedure from MCAF section 4.5.15.5:
          1. Enable guard
          2. Set velocity command override flag
          3. Force motor to RUN state
        """
        self.enable_guard()
        self.set_override_flags(velocity_command=True)
        self.force_state(ForceState.RUN)
        logger.info("Entered velocity override mode (forced RUN)")

    def enter_force_voltage_mode(self) -> None:
        """Enter OM_FORCE_VOLTAGE_DQ mode.

        Follows MCAF section 4.5.15.1:
          1. Enable guard
          2. Set operatingMode = OM_DISABLED
          3. Set commutation override and override omega
          4. Set operatingMode = OM_FORCE_VOLTAGE_DQ
        """
        self.enable_guard()
        self.set_operating_mode(OperatingMode.DISABLED)
        time.sleep(0.05)
        self.set_override_flags(commutation=True)
        self.set_operating_mode(OperatingMode.FORCE_VOLTAGE_DQ)
        logger.info("Entered force voltage DQ mode")

    # ── Commutation & Direct Variable Control ────────────────────────

    def set_commutation_frequency(self, omega: int) -> None:
        """Set the commutation override frequency (raw counts).

        Args:
            omega: Electrical angular velocity in Q15 counts.
        """
        self._session.write_variable(_VAR_OVERRIDE_OMEGA, omega)
        logger.debug("Set override omega electrical: %d", omega)

    def get_commutation_frequency(self) -> int:
        """Read the commutation override frequency (raw counts)."""
        return int(self._session.read_variable(_VAR_OVERRIDE_OMEGA))

    def set_dq_current(self, d: int, q: int) -> None:
        """Set dq current command (raw Q15 counts).

        Args:
            d: D-axis current command in Q15 counts.
            q: Q-axis current command in Q15 counts.
        """
        self._session.write_variable(_VAR_IDQCMDRAW_D, d)
        self._session.write_variable(_VAR_IDQCMDRAW_Q, q)
        logger.debug("Set dq current: d=%d, q=%d", d, q)

    def get_dq_current(self) -> tuple[int, int]:
        """Read the current dq current command (raw Q15 counts)."""
        d = int(self._session.read_variable(_VAR_IDQCMDRAW_D))
        q = int(self._session.read_variable(_VAR_IDQCMDRAW_Q))
        return d, q

    def set_dq_voltage(self, d: int, q: int) -> None:
        """Set dq voltage command (raw Q15 counts).

        Only effective in OM_FORCE_VOLTAGE_DQ mode.

        Args:
            d: D-axis voltage command in Q15 counts.
            q: Q-axis voltage command in Q15 counts.
        """
        self._session.write_variable(_VAR_VDQ_CMD_D, d)
        self._session.write_variable(_VAR_VDQ_CMD_Q, q)
        logger.debug("Set dq voltage: d=%d, q=%d", d, q)

    def get_dq_voltage(self) -> tuple[int, int]:
        """Read the current dq voltage command (raw Q15 counts)."""
        d = int(self._session.read_variable(_VAR_VDQ_CMD_D))
        q = int(self._session.read_variable(_VAR_VDQ_CMD_Q))
        return d, q

    # ── Engineering-unit helpers ──────────────────────────────────────

    def set_commutation_frequency_rpm(self, rpm: float) -> int:
        """Set commutation frequency in RPM, returning the Q15 count written.

        Args:
            rpm: Desired commutation frequency in RPM.

        Returns:
            The raw Q15 count actually written to firmware.
        """
        conn = self._session.conn
        counts = conn.engineering_to_q15(rpm, _PARAM_FULLSCALE_VELOCITY)
        self.set_commutation_frequency(counts)
        logger.info("Set commutation frequency: %.1f RPM (%d counts)", rpm, counts)
        return counts

    def set_dq_current_amps(self, d_amps: float, q_amps: float) -> tuple[int, int]:
        """Set dq current command in Amps, returning the Q15 counts written.

        Args:
            d_amps: D-axis current in Amps.
            q_amps: Q-axis current in Amps.

        Returns:
            Tuple of (d_counts, q_counts) actually written.
        """
        conn = self._session.conn
        d_counts = conn.engineering_to_q15(d_amps, _PARAM_FULLSCALE_CURRENT)
        q_counts = conn.engineering_to_q15(q_amps, _PARAM_FULLSCALE_CURRENT)
        self.set_dq_current(d_counts, q_counts)
        logger.info(
            "Set dq current: d=%.3f A (%d), q=%.3f A (%d)",
            d_amps, d_counts, q_amps, q_counts,
        )
        return d_counts, q_counts

    def set_dq_voltage_volts(self, d_volts: float, q_volts: float) -> tuple[int, int]:
        """Set dq voltage command in Volts, returning the Q15 counts written.

        Args:
            d_volts: D-axis voltage in Volts.
            q_volts: Q-axis voltage in Volts.

        Returns:
            Tuple of (d_counts, q_counts) actually written.
        """
        conn = self._session.conn
        d_counts = conn.engineering_to_q15(d_volts, _PARAM_FULLSCALE_VOLTAGE)
        q_counts = conn.engineering_to_q15(q_volts, _PARAM_FULLSCALE_VOLTAGE)
        self.set_dq_voltage(d_counts, q_counts)
        logger.info(
            "Set dq voltage: d=%.2f V (%d), q=%.2f V (%d)",
            d_volts, d_counts, q_volts, q_counts,
        )
        return d_counts, q_counts
