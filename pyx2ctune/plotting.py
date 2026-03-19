"""Visualization for step response data and tuning results.

Provides matplotlib-based plots for step response waveforms with
metric annotations, and summary plots for automated gain sweeps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np

if TYPE_CHECKING:
    from matplotlib.figure import Figure

from pyx2ctune.analysis import StepMetrics
from pyx2ctune.capture import StepResponse


def plot_step_response(
    response: StepResponse,
    metrics: StepMetrics | None = None,
    show: bool = True,
    title: str | None = None,
) -> Figure:
    """Plot a captured step response with optional metric annotations.

    Creates a two-panel figure:
    - Top: current reference vs measured current
    - Bottom: voltage output from PI controller

    Args:
        response: Captured StepResponse data.
        metrics: Optional computed StepMetrics to annotate.
        show: If True, call plt.show() after creating the figure.
        title: Optional custom title. If None, auto-generated from gains.

    Returns:
        matplotlib Figure object.
    """
    time_ms = response.time_us / 1000.0

    fig, (ax_current, ax_voltage) = plt.subplots(
        2, 1, figsize=(10, 6), sharex=True,
        gridspec_kw={"height_ratios": [2, 1]},
    )

    # Current subplot
    ax_current.plot(time_ms, response.reference, "r-", linewidth=1.0,
                    label="Reference", alpha=0.8)
    ax_current.plot(time_ms, response.measured, "b-", linewidth=1.0,
                    label="Measured")
    ax_current.set_ylabel(f"I{response.axis} (counts)")
    ax_current.legend(loc="upper right", fontsize=8)
    ax_current.grid(True, alpha=0.3)

    # Voltage subplot
    ax_voltage.plot(time_ms, response.voltage, "g-", linewidth=1.0,
                    label="Voltage")
    ax_voltage.set_ylabel(f"V{response.axis} (counts)")
    ax_voltage.set_xlabel("Time (ms)")
    ax_voltage.legend(loc="upper right", fontsize=8)
    ax_voltage.grid(True, alpha=0.3)

    # Title
    if title is None:
        gains = response.gains
        if gains:
            title = (
                f"{response.axis.upper()}-axis step response  |  "
                f"Kp={gains.get('kp', '?'):.4g}  Ki={gains.get('ki', '?'):.4g}"
            )
        else:
            title = f"{response.axis.upper()}-axis step response"

    if metrics is not None and metrics.n_steps > 0:
        metrics_text = (
            f"  |  OS={metrics.overshoot:.1%}  "
            f"Tr={metrics.rise_time_us:.0f}\u00b5s  "
            f"Ts={metrics.settling_time_us:.0f}\u00b5s"
        )
        title += metrics_text
        _annotate_metrics(ax_current, response, metrics)

    fig.suptitle(title, fontsize=10)
    fig.tight_layout()

    if show:
        plt.show()

    return fig


def _annotate_metrics(
    ax: plt.Axes,
    response: StepResponse,
    metrics: StepMetrics,
) -> None:
    """Add metric annotations to the current subplot."""
    if metrics.n_steps == 0:
        return

    ref = response.reference
    meas = response.measured
    time_ms = response.time_us / 1000.0

    ref_range = np.max(ref) - np.min(ref)
    if ref_range < 1e-9:
        return

    # Mark overshoot peak
    if metrics.overshoot > 0.005:
        diff = np.diff(ref)
        threshold = ref_range * 0.3
        edge_indices = np.where(np.abs(diff) > threshold)[0]

        if len(edge_indices) > 0:
            edge_idx = edge_indices[0] + 1
            step_size = ref[min(edge_idx + 5, len(ref) - 1)] - ref[max(0, edge_idx - 1)]
            rising = step_size > 0

            end_idx = edge_indices[1] + 1 if len(edge_indices) > 1 else len(meas)
            seg_meas = meas[edge_idx:end_idx]

            if len(seg_meas) > 0:
                if rising:
                    peak_local = int(np.argmax(seg_meas))
                else:
                    peak_local = int(np.argmin(seg_meas))

                peak_idx = edge_idx + peak_local
                if 0 <= peak_idx < len(time_ms):
                    ax.axhline(y=meas[peak_idx], color="orange", linestyle=":",
                               alpha=0.5, linewidth=0.8)
                    ax.annotate(
                        f"OS={metrics.overshoot:.1%}",
                        xy=(time_ms[peak_idx], meas[peak_idx]),
                        fontsize=7, color="orange",
                        xytext=(5, 5), textcoords="offset points",
                    )


def plot_gain_sweep(
    results: list[dict],
    x_key: str = "kp",
    show: bool = True,
    title: str = "Gain Sweep Results",
) -> Figure:
    """Plot summary metrics from an automated gain sweep.

    Args:
        results: List of dicts, each containing at least the x_key
            and metric fields (overshoot, rise_time_us, settling_time_us).
        x_key: Which gain to use as x-axis ("kp" or "ki").
        show: If True, call plt.show().
        title: Plot title.

    Returns:
        matplotlib Figure object.
    """
    x_values = [r[x_key] for r in results]

    fig, axes = plt.subplots(3, 1, figsize=(8, 8), sharex=True)

    # Overshoot
    axes[0].plot(x_values, [r["overshoot"] * 100 for r in results], "o-", color="red")
    axes[0].set_ylabel("Overshoot (%)")
    axes[0].grid(True, alpha=0.3)
    axes[0].axhline(y=10, color="red", linestyle="--", alpha=0.4, linewidth=0.8)

    # Rise time
    axes[1].plot(x_values, [r["rise_time_us"] for r in results], "s-", color="blue")
    axes[1].set_ylabel("Rise Time (\u00b5s)")
    axes[1].grid(True, alpha=0.3)

    # Settling time
    axes[2].plot(x_values, [r["settling_time_us"] for r in results], "^-", color="green")
    axes[2].set_ylabel("Settling Time (\u00b5s)")
    axes[2].set_xlabel(f"{x_key.upper()} gain")
    axes[2].grid(True, alpha=0.3)

    fig.suptitle(title, fontsize=11)
    fig.tight_layout()

    if show:
        plt.show()

    return fig
