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

    # Read measured q-axis current in Amps
    iq = conn.motor.idq_q

    # Set velocity command in RPM
    conn.motor.velocity_cmd = 1000.0

    # Read PI gain in V/A
    kp = conn.motor.current_kp_q

    # Test harness control
    conn.test_harness.enable_guard()
    conn.test_harness.operating_mode = OperatingMode.FORCE_CURRENT

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
from pymcaf.motor import Motor
from pymcaf.parameters import ParameterDB, ParameterInfo
from pymcaf.test_harness import (
    AsymmetricPerturbation,
    SquareWavePerturbation,
    TestHarness,
)
from pymcaf.types import (
    ABCTriple,
    AlphaBetaPair,
    DQPair,
    MotorState,
)

__version__ = "0.1.0"

__all__ = [
    "ABCTriple",
    "AlphaBetaPair",
    "AsymmetricPerturbation",
    "Backend",
    "Connection",
    "DQPair",
    "ForceState",
    "GUARD_KEY_RESET",
    "GUARD_KEY_VALID",
    "GUARD_TIMEOUT_MAX",
    "MOTOR_STATES",
    "Motor",
    "MotorState",
    "OperatingMode",
    "OverrideFlag",
    "ParameterDB",
    "ParameterInfo",
    "SquareWavePerturbation",
    "TestHarness",
]
