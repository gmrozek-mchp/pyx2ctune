"""Matplotlib canvas widget for embedding step response plots in Qt."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from pyx2ctune.analysis import StepMetrics
from pyx2ctune.capture import StepResponse


class PlotWidget(QWidget):
    """Embeds a matplotlib figure with two subplots (current + voltage)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._figure = Figure(figsize=(8, 5), tight_layout=True)
        self._canvas = FigureCanvas(self._figure)
        self._toolbar = NavigationToolbar(self._canvas, self)

        self._ax_current = self._figure.add_subplot(2, 1, 1)
        self._ax_voltage = self._figure.add_subplot(2, 1, 2, sharex=self._ax_current)
        self._setup_empty()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas)

    def _setup_empty(self) -> None:
        for ax in (self._ax_current, self._ax_voltage):
            ax.set_facecolor("#fafafa")
            ax.grid(True, alpha=0.3)

        self._ax_current.set_ylabel("Current")
        self._ax_voltage.set_ylabel("Voltage")
        self._ax_voltage.set_xlabel("Time (ms)")
        self._figure.suptitle("No data captured yet", fontsize=10, color="gray")

    def update_plot(self, response: StepResponse,
                    metrics: StepMetrics | None = None) -> None:
        """Redraw with new step response data."""
        ax_c = self._ax_current
        ax_v = self._ax_voltage
        ax_c.clear()
        ax_v.clear()

        time_ms = response.time_us / 1000.0

        ax_c.plot(time_ms, response.reference, "r-", linewidth=1.0,
                  label="Reference", alpha=0.8)
        ax_c.plot(time_ms, response.measured, "b-", linewidth=1.0,
                  label="Measured")
        ax_c.set_ylabel(f"I{response.axis} ({response.current_units})")
        ax_c.legend(loc="upper right", fontsize=8)
        ax_c.grid(True, alpha=0.3)

        ax_v.plot(time_ms, response.voltage, "g-", linewidth=1.0,
                  label="Voltage")
        ax_v.set_ylabel(f"V{response.axis} ({response.voltage_units})")
        ax_v.set_xlabel("Time (ms)")
        ax_v.legend(loc="upper right", fontsize=8)
        ax_v.grid(True, alpha=0.3)

        # Title
        gains = response.gains
        title = f"{response.axis.upper()}-axis step response"
        if gains:
            title += (
                f"  |  Kp={gains.get('kp', 0):.4g}  "
                f"Ki={gains.get('ki', 0):.4g}"
            )
        if metrics is not None and metrics.n_steps > 0:
            title += (
                f"  |  OS={metrics.overshoot:.1%}  "
                f"Tr={metrics.rise_time_us:.0f}\u00b5s  "
                f"Ts={metrics.settling_time_us:.0f}\u00b5s"
            )
            self._annotate_overshoot(ax_c, response, metrics)

        self._figure.suptitle(title, fontsize=10)
        self._canvas.draw_idle()

    def _annotate_overshoot(self, ax, response: StepResponse,
                            metrics: StepMetrics) -> None:
        if metrics.overshoot < 0.005:
            return

        ref = response.reference
        meas = response.measured
        time_ms = response.time_us / 1000.0
        ref_range = np.max(ref) - np.min(ref)
        if ref_range < 1e-9:
            return

        diff = np.diff(ref)
        threshold = ref_range * 0.3
        edge_indices = np.where(np.abs(diff) > threshold)[0]
        if len(edge_indices) == 0:
            return

        edge_idx = edge_indices[0] + 1
        step_size = ref[min(edge_idx + 5, len(ref) - 1)] - ref[max(0, edge_idx - 1)]
        rising = step_size > 0

        end_idx = edge_indices[1] + 1 if len(edge_indices) > 1 else len(meas)
        seg_meas = meas[edge_idx:end_idx]
        if len(seg_meas) == 0:
            return

        peak_local = int(np.argmax(seg_meas) if rising else np.argmin(seg_meas))
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

    def clear(self) -> None:
        self._ax_current.clear()
        self._ax_voltage.clear()
        self._setup_empty()
        self._canvas.draw_idle()
