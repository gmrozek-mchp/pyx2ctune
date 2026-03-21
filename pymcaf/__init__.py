"""pymcaf -- Python SDK for Microchip MCAF motor control firmware.

Provides a pluggable interface for communicating with MCAF-based
motor controllers.  All public APIs accept and return engineering
units; Q-format conversion is handled internally.

Quick start::

    from pymcaf import Connection

    conn = Connection.via_x2cscope(
        port="/dev/tty.usbmodem1",
        elf_file="firmware.elf",
        parameters_json="parameters.json",
    )

    # Read current in Amps
    iq = conn.read_q15("motor.idq.q", "mcapi.fullscale.current")

    # Read PI gain in V/A
    kp, counts, q = conn.read_pi_gain(
        "motor.iqCtrl.kp", "motor.iqCtrl.nkp", "foc.kip",
    )

    conn.disconnect()
"""

from pymcaf.backend import Backend
from pymcaf.connection import Connection
from pymcaf.constants import (
    GUARD_KEY_RESET,
    GUARD_KEY_VALID,
    GUARD_TIMEOUT_MAX,
    MOTOR_STATES,
    ForceState,
    OperatingMode,
    OverrideFlag,
)
from pymcaf.parameters import ParameterDB, ParameterInfo

__version__ = "0.1.0"

__all__ = [
    "Backend",
    "Connection",
    "ForceState",
    "GUARD_KEY_RESET",
    "GUARD_KEY_VALID",
    "GUARD_TIMEOUT_MAX",
    "MOTOR_STATES",
    "OperatingMode",
    "OverrideFlag",
    "ParameterDB",
    "ParameterInfo",
]
