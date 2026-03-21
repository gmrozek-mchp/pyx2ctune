"""Scope data acquisition for step response capture (MCAF implementation).

Uses the pymcaf scope interface to capture waveform data from the target
firmware and packages it into a StepResponse dataclass for analysis.
Supports triggered acquisition on the current reference for stable
continuous display during square-wave perturbation testing.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

import numpy as np

from mctoolbox import interfaces as _interfaces
from mctoolbox.capture import StepResponse

if TYPE_CHECKING:
    from mctoolbox.mcaf.session import TuningSession

logger = logging.getLogger(__name__)

_PARAM_FULLSCALE_CURRENT = "mcapi.fullscale.current"
_PARAM_FULLSCALE_VOLTAGE = "mcapi.fullscale.voltage"
_PARAM_FULLSCALE_VELOCITY = "mcapi.fullscale.velocity"

# Scope variables for current loop analysis
_CURRENT_LOOP_VARS = {
    "q": {
        "measured": "motor.idq.q",
        "reference": "motor.idqCmd.q",
        "voltage": "motor.vdq.q",
    },
    "d": {
        "measured": "motor.idq.d",
        "reference": "motor.idqCmd.d",
        "voltage": "motor.vdq.d",
    },
}

# Scope variables for velocity loop analysis
_VELOCITY_LOOP_VARS = {
    "measured": "motor.omegaElectrical",
    "reference": "motor.omegaCmd",
    "output": "motor.idqCmd.q",
}

# Scope variables for open-loop analysis
_OPEN_VOLTAGE_VARS = {
    "measured": "motor.vdq.d",
    "reference": "motor.vdq.q",
    "output": "motor.idq.q",
}

_OPEN_CURRENT_VARS = {
    "measured": "motor.idq.d",
    "reference": "motor.idq.q",
    "output": "motor.omegaElectrical",
}

# Unified view lookup: view_id -> (var_dict, loop_type, axis)
_VIEW_CONFIGS = {
    "current_q": (_CURRENT_LOOP_VARS["q"], "current", "q"),
    "current_d": (_CURRENT_LOOP_VARS["d"], "current", "d"),
    "velocity": (_VELOCITY_LOOP_VARS, "velocity", "velocity"),
    "open_voltage": (_OPEN_VOLTAGE_VARS, "open_voltage", "open"),
    "open_current": (_OPEN_CURRENT_VARS, "open_current", "open"),
}


class ScopeCapture(_interfaces.WaveformCapture):
    """Scope data acquisition manager.

    Configures scope channels for various loop analysis views,
    captures frames, and returns StepResponse objects.
    """

    def __init__(self, session: TuningSession, control_freq_hz: float = 20000.0):
        """
        Args:
            session: Active TuningSession.
            control_freq_hz: Control ISR frequency in Hz (default 20kHz).
                Used to compute the time axis for captured data.
        """
        self._session = session
        self._control_period_us = 1e6 / control_freq_hz
        self._configured_axis: str | None = None
        self._configured_vars: dict[str, str] = {}
        self._loop_type: str = "current"

    # ── ABC interface ──────────────────────────────────────────────────

    def configure(self, view: str, **kwargs: Any) -> None:
        """Configure capture channels for a named view preset.

        Delegates to configure_view().
        """
        self.configure_view(view, **kwargs)

    # ── View configuration ─────────────────────────────────────────────

    def configure_view(
        self,
        view: str,
        sample_time: int = 1,
        trigger: bool = True,
        trigger_level: float = 0,
        trigger_edge: int = 0,
        trigger_delay: int = 0,
    ) -> None:
        """Configure scope channels from a named preset view.

        Args:
            view: One of "current_q", "current_d", "velocity",
                "open_voltage", "open_current".
            sample_time: Scope prescaler (1 = every ISR sample).
            trigger: If True, trigger on the view's reference channel.
            trigger_level: Trigger threshold in raw Q15 counts.
            trigger_edge: 0 = rising, 1 = falling.
            trigger_delay: Pre/post-trigger delay percentage.
        """
        if view not in _VIEW_CONFIGS:
            raise ValueError(
                f"Unknown view {view!r}; "
                f"choose from {list(_VIEW_CONFIGS)}"
            )

        var_names, loop_type, axis = _VIEW_CONFIGS[view]

        scope = self._session.conn.scope

        scope.clear_channels()
        for role, var_name in var_names.items():
            scope.add_channel(var_name)
            logger.debug("Added scope channel: %s (%s)", var_name, role)

        if trigger:
            scope.set_trigger(
                var_names["reference"],
                level=trigger_level,
                mode=1,
                delay=trigger_delay,
                edge=trigger_edge,
            )
            logger.info(
                "Scope trigger on %s: level=%s, edge=%s, delay=%d",
                var_names["reference"],
                trigger_level,
                "rising" if trigger_edge == 0 else "falling",
                trigger_delay,
            )
        else:
            scope.reset_trigger()

        scope.set_sample_time(sample_time)
        self._configured_axis = axis
        self._configured_vars = var_names
        self._sample_time = sample_time
        self._loop_type = loop_type

        logger.info(
            "Scope configured: view=%s (sample_time=%d, trigger=%s)",
            view, sample_time, trigger,
        )

    def configure_current_loop(
        self, axis: str = "q", **kwargs,
    ) -> None:
        """Convenience wrapper: configure scope for current loop."""
        self.configure_view(f"current_{axis.lower()}", **kwargs)

    def configure_velocity_loop(self, **kwargs) -> None:
        """Convenience wrapper: configure scope for velocity loop."""
        self.configure_view("velocity", **kwargs)

    def capture_frame(
        self,
        timeout: float = 5.0,
        abort_event: threading.Event | None = None,
    ) -> StepResponse:
        """Capture a single frame of scope data.

        Args:
            timeout: Maximum time to wait for data in seconds.
            abort_event: Optional threading.Event.  If set while polling,
                an InterruptedError is raised.

        Returns:
            StepResponse with time axis and captured signals.

        Raises:
            TimeoutError: If scope data is not ready within timeout.
            InterruptedError: If abort_event is set during polling.
            RuntimeError: If scope is not configured.
        """
        if self._configured_axis is None:
            raise RuntimeError(
                "Scope not configured. Call configure_current_loop() "
                "or configure_velocity_loop() first."
            )

        logger.info("Capture requested (%s-axis, timeout=%.1fs)", self._configured_axis, timeout)

        scope = self._session.conn.scope

        scope.request_data()

        start = time.monotonic()
        poll_interval = 0.02
        while not scope.is_data_ready():
            if abort_event is not None and abort_event.is_set():
                raise InterruptedError("Capture aborted")
            if time.monotonic() - start > timeout:
                raise TimeoutError(
                    f"Scope data not ready after {timeout}s. "
                    f"Check that firmware is running and perturbation is active."
                )
            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 0.2)

        elapsed = time.monotonic() - start
        logger.info("Scope data ready after %.2fs", elapsed)

        channel_data = scope.get_channel_data()

        var_names = self._configured_vars
        loop = self._loop_type

        if loop in ("velocity", "open_voltage", "open_current"):
            measured_key, reference_key, output_key = (
                "measured", "reference", "output",
            )
        else:
            measured_key, reference_key, output_key = (
                "measured", "reference", "voltage",
            )

        measured_data = np.array(
            channel_data.get(var_names[measured_key], []), dtype=np.float64,
        )
        reference_data = np.array(
            channel_data.get(var_names[reference_key], []), dtype=np.float64,
        )
        output_data = np.array(
            channel_data.get(var_names[output_key], []), dtype=np.float64,
        )

        n_samples = len(measured_data)
        dt_us = self._control_period_us * self._sample_time
        time_us = np.arange(n_samples) * dt_us

        current_units = "counts"
        voltage_units = "counts"
        ref_units = "counts"
        meas_units = "counts"
        out_units = "counts"

        conn = self._session.conn

        if loop == "velocity":
            measured_data, reference_data, meas_units, ref_units = (
                self._try_scale_q15(measured_data, reference_data, _PARAM_FULLSCALE_VELOCITY, "RPM", conn)
            )
            output_data, out_units = self._try_scale_single(
                output_data, _PARAM_FULLSCALE_CURRENT, "A", conn,
            )
            current_units = out_units
        elif loop == "open_voltage":
            measured_data, reference_data, meas_units, ref_units = (
                self._try_scale_q15(measured_data, reference_data, _PARAM_FULLSCALE_VOLTAGE, "V", conn)
            )
            voltage_units = meas_units
            output_data, out_units = self._try_scale_single(
                output_data, _PARAM_FULLSCALE_CURRENT, "A", conn,
            )
            current_units = out_units
        elif loop == "open_current":
            measured_data, reference_data, meas_units, ref_units = (
                self._try_scale_q15(measured_data, reference_data, _PARAM_FULLSCALE_CURRENT, "A", conn)
            )
            current_units = meas_units
            output_data, out_units = self._try_scale_single(
                output_data, _PARAM_FULLSCALE_VELOCITY, "RPM", conn,
            )
        else:
            measured_data, reference_data, meas_units, ref_units = (
                self._try_scale_q15(measured_data, reference_data, _PARAM_FULLSCALE_CURRENT, "A", conn)
            )
            current_units = meas_units
            output_data, out_units = self._try_scale_single(
                output_data, _PARAM_FULLSCALE_VOLTAGE, "V", conn,
            )
            voltage_units = out_units

        gains = {}
        try:
            if loop == "velocity":
                gains_obj = self._session.velocity.get_gains()
                gains = {
                    "kp": gains_obj.kp,
                    "ki": gains_obj.ki,
                    "kp_counts": gains_obj.kp_counts,
                    "ki_counts": gains_obj.ki_counts,
                    "kp_shift": gains_obj.kp_shift,
                    "ki_shift": gains_obj.ki_shift,
                }
            elif loop in ("current",):
                gains_obj = self._session.current.get_gains(
                    self._configured_axis,
                )
                gains = {
                    "kp": gains_obj.kp,
                    "ki": gains_obj.ki,
                    "kp_counts": gains_obj.kp_counts,
                    "ki_counts": gains_obj.ki_counts,
                    "kp_shift": gains_obj.kp_shift,
                    "ki_shift": gains_obj.ki_shift,
                }
        except Exception:
            logger.debug("Could not read gains during capture", exc_info=True)

        capture_duration_ms = n_samples * dt_us / 1000
        logger.info(
            "Captured %d samples (%.1f ms) on %s",
            n_samples, capture_duration_ms, self._configured_axis,
        )

        return StepResponse(
            time_us=time_us,
            reference=reference_data,
            measured=measured_data,
            voltage=output_data,
            axis=self._configured_axis,
            loop_type=self._loop_type,
            gains=gains,
            sample_time=self._sample_time,
            control_period_us=self._control_period_us,
            current_units=current_units,
            voltage_units=voltage_units,
            reference_units=ref_units,
            measured_units=meas_units,
            output_units=out_units,
            metadata={
                "var_measured": var_names[measured_key],
                "var_reference": var_names[reference_key],
                "var_output": var_names[output_key],
                "capture_duration_ms": capture_duration_ms,
                "loop_type": self._loop_type,
            },
        )

    # ── Unit conversion helpers ───────────────────────────────────────

    @staticmethod
    def _try_scale_q15(
        measured: np.ndarray,
        reference: np.ndarray,
        fullscale_param: str,
        unit_label: str,
        conn,
    ) -> tuple[np.ndarray, np.ndarray, str, str]:
        """Scale a pair of Q15 arrays to engineering units if possible."""
        params = conn.params
        if params is not None:
            try:
                fs = params.get_info(fullscale_param).intended_value
                measured = (measured / 32768.0) * fs
                reference = (reference / 32768.0) * fs
                return measured, reference, unit_label, unit_label
            except KeyError:
                pass
        return measured, reference, "counts", "counts"

    @staticmethod
    def _try_scale_single(
        data: np.ndarray,
        fullscale_param: str,
        unit_label: str,
        conn,
    ) -> tuple[np.ndarray, str]:
        """Scale a single Q15 array to engineering units if possible."""
        params = conn.params
        if params is not None:
            try:
                fs = params.get_info(fullscale_param).intended_value
                data = (data / 32768.0) * fs
                return data, unit_label
            except KeyError:
                pass
        return data, "counts"

    # ── Trigger level conversion ─────────────────────────────────────

    def trigger_level_to_q15(
        self,
        value: float,
        fullscale_key: str,
    ) -> int:
        """Convert an engineering-unit trigger level to Q15 counts.

        Args:
            value: Trigger level in engineering units (A, V, or RPM).
            fullscale_key: One of "current", "voltage", "velocity".

        Returns:
            Q15 integer counts for the scope trigger.
        """
        param_map = {
            "current": _PARAM_FULLSCALE_CURRENT,
            "voltage": _PARAM_FULLSCALE_VOLTAGE,
            "velocity": _PARAM_FULLSCALE_VELOCITY,
        }
        param_name = param_map.get(fullscale_key, fullscale_key)
        conn = self._session.conn
        try:
            return conn.engineering_to_q15(value, param_name)
        except (RuntimeError, ValueError):
            return round(value)
