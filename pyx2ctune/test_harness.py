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
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyx2ctune.connection import TuningSession

logger = logging.getLogger(__name__)

# Guard constants
GUARD_KEY_VALID = 0xD1A6
GUARD_KEY_RESET = 0x0000
GUARD_TIMEOUT_MAX = 0xFFFF

# At 20kHz ISR, 0xFFFF counts = ~3.27 seconds.  Refresh well before expiry.
_GUARD_REFRESH_INTERVAL_S = 1.5


class OperatingMode(IntEnum):
    """MCAF test harness operating modes (motor.testing.operatingMode).

    From test_harness.h: MCAF_OPERATING_MODE enum.
    """

    DISABLED = 0
    FORCE_VOLTAGE_DQ = 1
    FORCE_CURRENT = 2
    NORMAL = 3


class ForceState(IntEnum):
    """Forced state transitions (motor.testing.forceStateChange)."""

    NONE = 0
    RUN = 1
    STOP = 2
    STOP_NOW = 3


class OverrideFlag(IntEnum):
    """Override bitfield positions in motor.testing.overrides."""

    VELOCITY_COMMAND = 0x0001
    COMMUTATION = 0x0002
    DC_LINK_COMPENSATION = 0x0004
    STALL_DETECTION = 0x0008
    STARTUP_PAUSE = 0x0010
    FLUX_CONTROL = 0x0020
    ZERO_SEQUENCE_MODULATION = 0x0040


# Firmware variable paths
_VAR_GUARD_KEY = "systemData.testing.guard.key"
_VAR_GUARD_TIMEOUT = "systemData.testing.guard.timeout"
_VAR_OPERATING_MODE = "motor.testing.operatingMode"
_VAR_OVERRIDES = "motor.testing.overrides"
_VAR_FORCE_STATE = "motor.testing.forceStateChange"
_VAR_SQWAVE_VALUE = "motor.testing.sqwave.value"


class TestHarness:
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
            name="pyx2ctune-guard-refresh",
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
                self._session.get_variable(_VAR_GUARD_TIMEOUT).set_value(GUARD_TIMEOUT_MAX)
            except Exception:
                logger.warning("Guard timeout refresh failed", exc_info=True)

    @property
    def guard_active(self) -> bool:
        return self._guard_active

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

        Follows the procedure from MCAF section 4.5.15.2:
          1. Enable guard
          2. Set operatingMode = OM_DISABLED
          3. Set operatingMode = OM_FORCE_CURRENT

        The motor will be in current control mode with static dq references
        that can be changed via diagnostic tools or the CurrentTuning module.
        """
        self.enable_guard()
        self.set_operating_mode(OperatingMode.DISABLED)
        time.sleep(0.05)
        self.set_operating_mode(OperatingMode.FORCE_CURRENT)
        logger.info("Entered current test mode (OM_FORCE_CURRENT)")

    def enter_velocity_override_mode(self) -> None:
        """Enter normal mode with velocity command override.

        Follows the procedure from MCAF section 4.5.15.3:
          1. Enable guard
          2. Set velocity command override flag
        """
        self.enable_guard()
        self.set_override_flags(velocity_command=True)
        logger.info("Entered velocity override mode")

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
