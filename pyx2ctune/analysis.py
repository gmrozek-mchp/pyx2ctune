"""Step response analysis and metric computation.

Analyzes captured step response data to compute standard control
performance metrics: overshoot, rise time, settling time, and
steady-state error.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pyx2ctune.capture import StepResponse


@dataclass
class StepMetrics:
    """Computed metrics for a step response.

    Attributes:
        overshoot: Normalized overshoot fraction (0.0 = none, 0.1 = 10%).
        rise_time_us: Time from 10% to 90% of step change, in microseconds.
        settling_time_us: Time to enter and stay within the settling band
            (default +/-5%), in microseconds, measured from the step edge.
        steady_state_error: Final value error as a fraction of step size.
        step_size: Magnitude of the detected step change in counts.
        n_steps: Number of step transitions detected and averaged.
    """

    overshoot: float
    rise_time_us: float
    settling_time_us: float
    steady_state_error: float
    step_size: float = 0.0
    n_steps: int = 0


def compute_metrics(
    response: StepResponse,
    settling_band: float = 0.05,
    steady_state_fraction: float = 0.2,
) -> StepMetrics:
    """Analyze a captured step response and compute performance metrics.

    Detects rising and falling step edges in the reference signal,
    isolates individual step transitions, and computes metrics for each.
    Returns averaged metrics across all detected steps.

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
        return StepMetrics(
            overshoot=0.0,
            rise_time_us=0.0,
            settling_time_us=0.0,
            steady_state_error=0.0,
        )

    edges = _detect_step_edges(ref)
    if not edges:
        return StepMetrics(
            overshoot=0.0,
            rise_time_us=0.0,
            settling_time_us=0.0,
            steady_state_error=0.0,
        )

    all_overshoot = []
    all_rise_time = []
    all_settling_time = []
    all_ss_error = []
    all_step_size = []

    for i, edge_idx in enumerate(edges):
        end_idx = edges[i + 1] if i + 1 < len(edges) else len(ref)

        if end_idx - edge_idx < 5:
            continue

        seg_ref = ref[edge_idx:end_idx]
        seg_meas = meas[edge_idx:end_idx]
        seg_time = time_us[edge_idx:end_idx] - time_us[edge_idx]
        n_seg = len(seg_ref)

        initial_value = meas[max(0, edge_idx - 1)]
        final_ref = seg_ref[-1]
        step_size = final_ref - initial_value

        if abs(step_size) < 1e-9:
            continue

        rising = step_size > 0
        abs_step = abs(step_size)

        # Overshoot
        if rising:
            peak = np.max(seg_meas)
            overshoot = max(0.0, (peak - final_ref) / abs_step)
        else:
            trough = np.min(seg_meas)
            overshoot = max(0.0, (final_ref - trough) / abs_step)

        # Rise time (10% to 90%)
        level_10 = initial_value + 0.1 * step_size
        level_90 = initial_value + 0.9 * step_size

        t_10 = _find_crossing_time(seg_meas, seg_time, level_10, rising)
        t_90 = _find_crossing_time(seg_meas, seg_time, level_90, rising)

        if t_10 is not None and t_90 is not None and t_90 > t_10:
            rise_time = t_90 - t_10
        else:
            rise_time = 0.0

        # Settling time
        ss_start = max(1, n_seg - int(n_seg * steady_state_fraction))
        ss_value = np.mean(seg_meas[ss_start:])
        band = settling_band * abs_step
        settling_time = _find_settling_time(
            seg_meas, seg_time, ss_value, band
        )

        # Steady-state error
        ss_error = abs(ss_value - final_ref) / abs_step

        all_overshoot.append(overshoot)
        all_rise_time.append(rise_time)
        all_settling_time.append(settling_time)
        all_ss_error.append(ss_error)
        all_step_size.append(abs_step)

    if not all_overshoot:
        return StepMetrics(
            overshoot=0.0,
            rise_time_us=0.0,
            settling_time_us=0.0,
            steady_state_error=0.0,
        )

    return StepMetrics(
        overshoot=float(np.mean(all_overshoot)),
        rise_time_us=float(np.mean(all_rise_time)),
        settling_time_us=float(np.mean(all_settling_time)),
        steady_state_error=float(np.mean(all_ss_error)),
        step_size=float(np.mean(all_step_size)),
        n_steps=len(all_overshoot),
    )


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
            # Skip ahead to avoid detecting the same edge multiple times
            i += max(1, len(ref) // 20)
        else:
            i += 1

    return edges


def _find_crossing_time(
    signal: np.ndarray,
    time_us: np.ndarray,
    level: float,
    rising: bool,
) -> float | None:
    """Find the time when the signal first crosses a given level.

    Uses linear interpolation between samples for sub-sample accuracy.

    Returns:
        Time in microseconds, or None if crossing not found.
    """
    for i in range(len(signal) - 1):
        if rising:
            if signal[i] <= level <= signal[i + 1]:
                frac = (level - signal[i]) / (signal[i + 1] - signal[i])
                return time_us[i] + frac * (time_us[i + 1] - time_us[i])
        else:
            if signal[i] >= level >= signal[i + 1]:
                frac = (signal[i] - level) / (signal[i] - signal[i + 1])
                return time_us[i] + frac * (time_us[i + 1] - time_us[i])
    return None


def _find_settling_time(
    signal: np.ndarray,
    time_us: np.ndarray,
    final_value: float,
    band: float,
) -> float:
    """Find the time after which the signal stays within +/-band of final_value.

    Searches backward from the end to find the last excursion outside
    the settling band.

    Returns:
        Settling time in microseconds.
    """
    for i in range(len(signal) - 1, -1, -1):
        if abs(signal[i] - final_value) > band:
            if i + 1 < len(time_us):
                return float(time_us[i + 1])
            return float(time_us[-1])
    return 0.0
