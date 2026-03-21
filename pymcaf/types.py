"""Generic motor control value types.

These types represent universal FOC motor control concepts and are not
specific to any particular firmware framework.  They use real-world
engineering units and standard reference-frame terminology.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DQPair:
    """DQ-frame (synchronous) vector pair."""

    d: float
    q: float

    def __iter__(self):
        yield self.d
        yield self.q


@dataclass
class AlphaBetaPair:
    """Alpha-beta frame (stationary) vector pair."""

    alpha: float
    beta: float

    def __iter__(self):
        yield self.alpha
        yield self.beta


@dataclass
class ABCTriple:
    """Three-phase (abc) values."""

    a: float
    b: float
    c: float

    def __iter__(self):
        yield self.a
        yield self.b
        yield self.c


@dataclass
class MotorState:
    """Motor controller state machine snapshot."""

    value: int
    name: str


@dataclass
class PIGainValues:
    """PI controller gain values in engineering units.

    The ``kp`` and ``ki`` fields hold values in engineering units
    (e.g. V/A, V/A/s for current gains).  Raw firmware representation
    is available via the ``*_raw`` and ``*_shift`` fields.
    """

    kp: float
    ki: float
    kp_raw: int = 0
    ki_raw: int = 0
    kp_shift: int = 0
    ki_shift: int = 0
    kp_units: str = ""
    ki_units: str = ""
