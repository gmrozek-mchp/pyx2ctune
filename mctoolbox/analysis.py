"""Step response analysis and metric computation.

Analyzes captured step response data to compute standard control
performance metrics using python-control's step_info().

Multi-step waveforms (e.g. from a periodic reference injection) are
segmented first, then each segment is analyzed individually and the
results averaged.
"""

from __future__ import annotations

from dataclasses import dataclass

import control
import numpy as np

from mctoolbox.capture import StepResponse


@dataclass
class StepMetrics:
    """Computed metrics for a step response.

    Attributes:
        overshoot: Normalized overshoot fraction (0.0 = none, 0.1 = 10%).
        rise_time_us: Time from 10% to 90% of step change, in microseconds.
        settling_time_us: Time to enter and stay within the settling band,
            in microseconds, measured from the step edge.
        steady_state_error: Final value error as a fraction of step size.
        step_size: Magnitude of the detected step change in counts.
        n_steps: Number of step transitions detected and averaged.
        undershoot: Normalized undershoot fraction.
        peak: Absolute peak value in original signal units.
        peak_time_us: Time of peak value relative to step edge.
        settling_min: Minimum value after rise time, in original signal units.
        settling_max: Maximum value after rise time, in original signal units.
    """

    overshoot: float
    rise_time_us: float
    settling_time_us: float
    steady_state_error: float
    step_size: float = 0.0
    n_steps: int = 0
    undershoot: float = 0.0
    peak: float = 0.0
    peak_time_us: float = 0.0
    settling_min: float = 0.0
    settling_max: float = 0.0


_EMPTY_METRICS = StepMetrics(
    overshoot=0.0,
    rise_time_us=0.0,
    settling_time_us=0.0,
    steady_state_error=0.0,
)


def compute_metrics(
    response: StepResponse,
    settling_band: float = 0.05,
    steady_state_fraction: float = 0.2,
) -> StepMetrics:
    """Analyze a captured step response and compute performance metrics.

    Detects rising and falling step edges in the reference signal,
    isolates individual step transitions, and delegates per-segment
    metric computation to ``control.step_info()``.  Returns averaged
    metrics across all detected steps.

    Args:
        response: Captured StepResponse from ScopeCapture.
        settling_band: Fraction of step size for settling criterion
            (default 0.05 = +/-5%).
        steady_state_fraction: Fraction of step duration to use for
            computing steady-state value (from the end of each step).

    Returns:
        StepMetrics with averaged values across detected steps.
    """
    ref = response.reference
    meas = response.measured
    time_us = response.time_us

    if len(ref) < 10:
        return _EMPTY_METRICS

    edges = _detect_step_edges(ref)
    if not edges:
        return _EMPTY_METRICS

    accum: dict[str, list[float]] = {
        "overshoot": [],
        "rise_time_us": [],
        "settling_time_us": [],
        "ss_error": [],
        "step_size": [],
        "undershoot": [],
        "peak": [],
        "peak_time_us": [],
        "settling_min": [],
        "settling_max": [],
    }

    for i, edge_idx in enumerate(edges):
        end_idx = edges[i + 1] if i + 1 < len(edges) else len(ref)

        if end_idx - edge_idx < 5:
            continue

        seg_meas = meas[edge_idx:end_idx]
        seg_time = time_us[edge_idx:end_idx] - time_us[edge_idx]

        initial_value = meas[max(0, edge_idx - 1)]
        final_ref = ref[end_idx - 1]
        step_size = final_ref - initial_value

        if abs(step_size) < 1e-9:
            continue

        info = _segment_step_info(
            seg_meas, seg_time, initial_value, step_size, settling_band,
        )
        if info is None:
            continue

        # Steady-state error from actual response tail vs reference
        n_seg = len(seg_meas)
        ss_start = max(1, n_seg - int(n_seg * steady_state_fraction))
        ss_value = float(np.mean(seg_meas[ss_start:]))
        ss_error = abs(ss_value - final_ref) / abs(step_size)

        accum["overshoot"].append(info["Overshoot"] / 100.0)
        accum["rise_time_us"].append(info["RiseTime"])
        accum["settling_time_us"].append(info["SettlingTime"])
        accum["ss_error"].append(ss_error)
        accum["step_size"].append(abs(step_size))
        accum["undershoot"].append(info["Undershoot"] / 100.0)
        accum["peak"].append(info["Peak"] + initial_value)
        accum["peak_time_us"].append(info["PeakTime"])
        accum["settling_min"].append(info["SettlingMin"] + initial_value)
        accum["settling_max"].append(info["SettlingMax"] + initial_value)

    if not accum["overshoot"]:
        return _EMPTY_METRICS

    return StepMetrics(
        overshoot=float(np.mean(accum["overshoot"])),
        rise_time_us=float(np.mean(accum["rise_time_us"])),
        settling_time_us=float(np.mean(accum["settling_time_us"])),
        steady_state_error=float(np.mean(accum["ss_error"])),
        step_size=float(np.mean(accum["step_size"])),
        n_steps=len(accum["overshoot"]),
        undershoot=float(np.mean(accum["undershoot"])),
        peak=float(np.mean(accum["peak"])),
        peak_time_us=float(np.mean(accum["peak_time_us"])),
        settling_min=float(np.mean(accum["settling_min"])),
        settling_max=float(np.mean(accum["settling_max"])),
    )


def _segment_step_info(
    seg_meas: np.ndarray,
    seg_time: np.ndarray,
    initial_value: float,
    step_size: float,
    settling_band: float,
) -> dict[str, float] | None:
    """Run ``control.step_info()`` on a single normalized segment.

    Subtracts *initial_value* so the signal starts near zero, then
    passes *step_size* as ``final_output`` so that metrics are computed
    relative to the intended setpoint.

    Returns the result dict, or *None* if the segment is too short or
    noisy for the library to extract valid metrics.
    """
    normalized = seg_meas - initial_value
    try:
        info: dict[str, float] = control.step_info(
            normalized,
            timepts=seg_time,
            final_output=step_size,
            SettlingTimeThreshold=settling_band,
            RiseTimeLimits=(0.1, 0.9),
        )
    except (IndexError, ValueError, ZeroDivisionError):
        return None

    if np.isnan(info["RiseTime"]) or np.isnan(info["SettlingTime"]):
        return None

    return info


def _detect_step_edges(ref: np.ndarray, min_change_fraction: float = 0.3) -> list[int]:
    """Detect indices where the reference signal makes a step transition.

    Uses the derivative of the reference signal to find abrupt changes.

    Args:
        ref: Reference signal array.
        min_change_fraction: Minimum change as fraction of signal range
            to qualify as a step edge.

    Returns:
        List of sample indices where step edges occur.
    """
    diff = np.diff(ref)
    signal_range = np.max(ref) - np.min(ref)

    if signal_range < 1e-9:
        return []

    threshold = signal_range * min_change_fraction
    edge_mask = np.abs(diff) > threshold

    edges = []
    i = 0
    while i < len(edge_mask):
        if edge_mask[i]:
            edges.append(i + 1)
            i += max(1, len(ref) // 20)
        else:
            i += 1

    return edges
