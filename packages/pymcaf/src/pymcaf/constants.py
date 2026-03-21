"""MCAF firmware constants and enumerations.

Defines the protocol-level constants for the MCAF test harness,
operating modes, state transitions, and override flags.

Reference: https://microchiptech.github.io/mcaf-doc/9.0.1/components/testharness.html
"""

from enum import IntEnum

# ── Guard key ─────────────────────────────────────────────────────────

GUARD_KEY_VALID = 0xD1A6
GUARD_KEY_RESET = 0x0000
GUARD_TIMEOUT_MAX = 0xFFFF


# ── Enumerations ──────────────────────────────────────────────────────

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


# ── Motor state machine ──────────────────────────────────────────────

MOTOR_STATES: dict[int, str] = {
    0: "RESTART",
    1: "STOPPED",
    2: "STARTING",
    3: "RUNNING",
    4: "STOPPING",
    5: "FAULT",
    6: "TEST_DISABLE",
    7: "TEST_ENABLE",
    8: "TEST_RESTART",
}
