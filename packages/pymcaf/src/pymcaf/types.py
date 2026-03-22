"""Generic motor control value types.

These types represent universal FOC motor control concepts and are not
specific to any particular firmware framework.  They use real-world
engineering units and standard reference-frame terminology.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DQPair:
    """DQ-frame (synchronous) vector pair.

    Units depend on context -- typically Amps for current, Volts for
    voltage.
    """

    d: float
    """Direct-axis component."""
    q: float
    """Quadrature-axis component."""

    def __iter__(self):
        yield self.d
        yield self.q


@dataclass
class AlphaBetaPair:
    """Alpha-beta frame (stationary) vector pair.

    Units depend on context -- typically Amps for current, Volts for
    voltage.
    """

    alpha: float
    """Alpha-axis component."""
    beta: float
    """Beta-axis component."""

    def __iter__(self):
        yield self.alpha
        yield self.beta


@dataclass
class ABCTriple:
    """Three-phase (abc) values.

    Units depend on context -- Amps for current, Volts for voltage,
    or fractional (0.0--1.0) for duty cycles.
    """

    a: float
    """Phase A value."""
    b: float
    """Phase B value."""
    c: float
    """Phase C value."""

    def __iter__(self):
        yield self.a
        yield self.b
        yield self.c


@dataclass
class MotorState:
    """Motor controller state machine snapshot."""

    value: int
    """Numeric state code from firmware."""
    name: str
    """Human-readable state name (e.g. ``"RUNNING"``)."""
