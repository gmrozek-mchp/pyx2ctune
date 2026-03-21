"""Matplotlib canvas widget for embedding step response plots in Qt.

Optimized for continuous (live) updates: line objects are reused across
frames via set_data() to minimize redraw overhead.
"""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from mctoolbox.analysis import StepMetrics
from mctoolbox.capture import StepResponse


class PlotWidget(QWidget):
    """Embeds a matplotlib figure with two subplots (current + voltage).

    Line objects are cached so that continuous capture updates only
    change data arrays and axis limits rather than recreating artists.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._figure = Figure(figsize=(8, 5), tight_layout=True)
        self._canvas = FigureCanvas(self._figure)
        self._toolbar = NavigationToolbar(self._canvas, self)

        self._ax_current = self._figure.add_subplot(2, 1, 1)
        self._ax_voltage = self._figure.add_subplot(2, 1, 2, sharex=self._ax_current)

        self._line_ref = None
        self._line_meas = None
        self._line_volt = None
        self._os_hline = None
        self._os_annotation = None

        self._setup_empty()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas)

        self._overlay = QLabel("Waiting for trigger\u2026", self)
        self._overlay.setAlignment(Qt.AlignCenter)
        self._overlay.setStyleSheet(
            "QLabel {"
            "  background-color: rgba(0, 0, 0, 160);"
            "  color: #ffffff;"
            "  font-size: 22px;"
            "  font-weight: bold;"
            "  border-radius: 12px;"
            "  padding: 24px 48px;"
            "}"
        )
        self._overlay.setVisible(False)

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
        """Redraw with new step response data.

        On the first call the line artists are created.  Subsequent calls
        reuse them via ``set_data()`` for faster continuous updates.
        """
        time_ms = response.time_us / 1000.0
        ax_c = self._ax_current
        ax_v = self._ax_voltage

        if self._line_ref is None:
            ax_c.clear()
            ax_v.clear()
            ax_c.grid(True, alpha=0.3)
            ax_v.grid(True, alpha=0.3)

            (self._line_ref,) = ax_c.plot(
                time_ms, response.reference, "r-", linewidth=1.0,
                label="Reference", alpha=0.8,
            )
            (self._line_meas,) = ax_c.plot(
                time_ms, response.measured, "b-", linewidth=1.0,
                label="Measured",
            )
            ax_c.legend(loc="upper right", fontsize=8)

            (self._line_volt,) = ax_v.plot(
                time_ms, response.voltage, "g-", linewidth=1.0,
                label="Voltage",
            )
            ax_v.legend(loc="upper right", fontsize=8)
        else:
            self._line_ref.set_data(time_ms, response.reference)
            self._line_meas.set_data(time_ms, response.measured)
            self._line_volt.set_data(time_ms, response.voltage)

        self._remove_annotations()

        loop = response.loop_type
        if loop == "velocity":
            ax_c.set_ylabel(
                f"Velocity ({response.measured_units or 'counts'})",
            )
            ax_v.set_ylabel(
                f"Iq output ({response.output_units or 'counts'})",
            )
        elif loop == "open_voltage":
            ax_c.set_ylabel(
                f"Vdq ({response.measured_units or 'counts'})",
            )
            ax_v.set_ylabel(
                f"Iq ({response.output_units or 'counts'})",
            )
        elif loop == "open_current":
            ax_c.set_ylabel(
                f"Idq ({response.measured_units or 'counts'})",
            )
            ax_v.set_ylabel(
                f"Velocity ({response.output_units or 'counts'})",
            )
        else:
            ax_c.set_ylabel(
                f"I{response.axis} ({response.current_units})",
            )
            ax_v.set_ylabel(
                f"V{response.axis} ({response.voltage_units})",
            )
        ax_v.set_xlabel("Time (ms)")

        ax_c.relim()
        ax_c.autoscale_view()
        ax_v.relim()
        ax_v.autoscale_view()

        gains = response.gains
        if loop == "velocity":
            title = "Velocity loop step response"
        elif loop == "open_voltage":
            title = "Open loop — Voltage DQ"
        elif loop == "open_current":
            title = "Open loop — Current DQ"
        else:
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

    def _remove_annotations(self) -> None:
        """Remove overshoot annotations from the previous frame."""
        if self._os_hline is not None:
            self._os_hline.remove()
            self._os_hline = None
        if self._os_annotation is not None:
            self._os_annotation.remove()
            self._os_annotation = None

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
            self._os_hline = ax.axhline(
                y=meas[peak_idx], color="orange", linestyle=":",
                alpha=0.5, linewidth=0.8,
            )
            self._os_annotation = ax.annotate(
                f"OS={metrics.overshoot:.1%}",
                xy=(time_ms[peak_idx], meas[peak_idx]),
                fontsize=7, color="orange",
                xytext=(5, 5), textcoords="offset points",
            )

    def show_waiting(self, message: str = "Waiting for trigger\u2026") -> None:
        self._overlay.setText(message)
        self._overlay.adjustSize()
        self._center_overlay()
        self._overlay.setVisible(True)
        self._overlay.raise_()

    def hide_waiting(self) -> None:
        self._overlay.setVisible(False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._overlay.isVisible():
            self._center_overlay()

    def _center_overlay(self) -> None:
        self._overlay.adjustSize()
        x = (self.width() - self._overlay.width()) // 2
        y = (self.height() - self._overlay.height()) // 2
        self._overlay.move(x, y)

    def clear(self) -> None:
        """Reset the plot to its empty state."""
        self._line_ref = None
        self._line_meas = None
        self._line_volt = None
        self._remove_annotations()
        self._ax_current.clear()
        self._ax_voltage.clear()
        self._setup_empty()
        self._canvas.draw_idle()

