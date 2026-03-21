"""Step response data container.

Framework-agnostic dataclass for captured waveform data.
The MCAF-specific ScopeCapture that produces these objects
lives in mctoolbox.mcaf.capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class StepResponse:
    """Captured step response data from a scope acquisition.

    Attributes:
        time_us: Time axis in microseconds.
        reference: Current reference signal (idqCmd).
        measured: Measured current signal (idq).
        voltage: Voltage output from PI controller (vdq).
        axis: Which current axis was captured ("q" or "d").
        gains: PI gains at time of capture.
        sample_time: Scope prescaler (1 = every sample).
        control_period_us: Control ISR period in microseconds.
        metadata: Additional context (variable names, etc.).
    """

    time_us: np.ndarray
    reference: np.ndarray
    measured: np.ndarray
    voltage: np.ndarray
    axis: str
    loop_type: str = "current"
    gains: dict = field(default_factory=dict)
    sample_time: int = 1
    control_period_us: float = 50.0
    current_units: str = "counts"
    voltage_units: str = "counts"
    reference_units: str = ""
    measured_units: str = ""
    output_units: str = ""
    metadata: dict = field(default_factory=dict)
