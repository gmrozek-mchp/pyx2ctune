"""Scope data acquisition for step response capture.

Uses pyX2Cscope's scope channel API to capture waveform data from the
target firmware and packages it into a StepResponse dataclass for analysis.
Supports triggered acquisition on the current reference for stable
continuous display during square-wave perturbation testing.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pyx2ctune.connection import TuningSession

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


class ScopeCapture:
    """Scope data acquisition manager.

    Configures pyX2Cscope scope channels for current loop analysis,
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

        x2c = self._session.x2c
        x2c.clear_all_scope_channel()

        for role, var_name in var_names.items():
            var = self._session.get_variable(var_name)
            x2c.add_scope_channel(var)
            logger.debug("Added scope channel: %s (%s)", var_name, role)

        if trigger:
            from pyx2cscope.x2cscope import TriggerConfig

            ref_var = self._session.get_variable(var_names["reference"])
            config = TriggerConfig(
                variable=ref_var,
                trigger_level=trigger_level,
                trigger_mode=1,
                trigger_delay=trigger_delay,
                trigger_edge=trigger_edge,
            )
            x2c.set_scope_trigger(config)
            logger.info(
                "Scope trigger on %s: level=%s, edge=%s, delay=%d",
                var_names["reference"],
                trigger_level,
                "rising" if trigger_edge == 0 else "falling",
                trigger_delay,
            )
        else:
            x2c.reset_scope_trigger()

        x2c.set_sample_time(sample_time)
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

        Requests data acquisition, polls until complete, and returns
        the captured waveforms as a StepResponse.

        Args:
            timeout: Maximum time to wait for data in seconds.
            abort_event: Optional threading.Event.  If set while polling,
                an InterruptedError is raised so callers (e.g. continuous
                capture loops) can exit cleanly.

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

        x2c = self._session.x2c
        x2c.request_scope_data()

        start = time.monotonic()
        poll_interval = 0.02
        while not x2c.is_scope_data_ready():
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

        channel_data = x2c.get_scope_channel_data(valid_data=True)

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
        params = self._session.params

        if loop == "velocity":
            if params is not None:
                try:
                    vfs = params.get_info(
                        _PARAM_FULLSCALE_VELOCITY,
                    ).intended_value
                    measured_data = (measured_data / 32768.0) * vfs
                    reference_data = (reference_data / 32768.0) * vfs
                    ref_units = meas_units = "RPM"
                except KeyError:
                    pass
                try:
                    ifs = params.get_info(
                        _PARAM_FULLSCALE_CURRENT,
                    ).intended_value
                    output_data = (output_data / 32768.0) * ifs
                    out_units = "A"
                    current_units = "A"
                except KeyError:
                    pass
        elif loop == "open_voltage":
            if params is not None:
                try:
                    vfs = params.get_info(
                        _PARAM_FULLSCALE_VOLTAGE,
                    ).intended_value
                    measured_data = (measured_data / 32768.0) * vfs
                    reference_data = (reference_data / 32768.0) * vfs
                    voltage_units = "V"
                    ref_units = meas_units = "V"
                except KeyError:
                    pass
                try:
                    ifs = params.get_info(
                        _PARAM_FULLSCALE_CURRENT,
                    ).intended_value
                    output_data = (output_data / 32768.0) * ifs
                    out_units = "A"
                    current_units = "A"
                except KeyError:
                    pass
        elif loop == "open_current":
            if params is not None:
                try:
                    ifs = params.get_info(
                        _PARAM_FULLSCALE_CURRENT,
                    ).intended_value
                    measured_data = (measured_data / 32768.0) * ifs
                    reference_data = (reference_data / 32768.0) * ifs
                    current_units = "A"
                    ref_units = meas_units = "A"
                except KeyError:
                    pass
                try:
                    vfs = params.get_info(
                        _PARAM_FULLSCALE_VELOCITY,
                    ).intended_value
                    output_data = (output_data / 32768.0) * vfs
                    out_units = "RPM"
                except KeyError:
                    pass
        else:
            if params is not None:
                try:
                    ifs = params.get_info(
                        _PARAM_FULLSCALE_CURRENT,
                    ).intended_value
                    measured_data = (measured_data / 32768.0) * ifs
                    reference_data = (reference_data / 32768.0) * ifs
                    current_units = "A"
                    ref_units = meas_units = "A"
                except KeyError:
                    pass
                try:
                    vfs = params.get_info(
                        _PARAM_FULLSCALE_VOLTAGE,
                    ).intended_value
                    output_data = (output_data / 32768.0) * vfs
                    voltage_units = "V"
                    out_units = "V"
                except KeyError:
                    pass

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
