"""Scope data acquisition for step response capture.

Uses pyX2Cscope's scope channel API to capture waveform data from the
target firmware and packages it into a StepResponse dataclass for analysis.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pyx2ctune.connection import TuningSession

logger = logging.getLogger(__name__)

_PARAM_FULLSCALE_CURRENT = "mcapi.fullscale.current"
_PARAM_FULLSCALE_VOLTAGE = "mcapi.fullscale.voltage"

# Default scope variables for current loop analysis
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
    gains: dict = field(default_factory=dict)
    sample_time: int = 1
    control_period_us: float = 50.0
    current_units: str = "counts"
    voltage_units: str = "counts"
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

    def configure_current_loop(
        self,
        axis: str = "q",
        sample_time: int = 1,
    ) -> None:
        """Set up scope channels for current loop step response capture.

        Configures three channels: measured current, reference current,
        and voltage output for the specified axis.

        Args:
            axis: "q" or "d" (which current axis to capture).
            sample_time: Scope prescaler. 1 = every ISR sample (highest
                resolution). Higher values extend capture duration at
                lower resolution.
        """
        axis = axis.lower()
        if axis not in _CURRENT_LOOP_VARS:
            raise ValueError(f"axis must be 'q' or 'd', got {axis!r}")

        x2c = self._session.x2c
        x2c.clear_all_scope_channel()

        var_names = _CURRENT_LOOP_VARS[axis]
        for role, var_name in var_names.items():
            var = self._session.get_variable(var_name)
            x2c.add_scope_channel(var)
            logger.debug("Added scope channel: %s (%s)", var_name, role)

        x2c.set_sample_time(sample_time)
        self._configured_axis = axis
        self._configured_vars = var_names
        self._sample_time = sample_time

        logger.info(
            "Scope configured for %s-axis current loop (sample_time=%d)",
            axis, sample_time,
        )

    def capture_frame(self, timeout: float = 5.0) -> StepResponse:
        """Capture a single frame of scope data.

        Requests data acquisition, polls until complete, and returns
        the captured waveforms as a StepResponse.

        Args:
            timeout: Maximum time to wait for data in seconds.

        Returns:
            StepResponse with time axis and captured signals.

        Raises:
            TimeoutError: If scope data is not ready within timeout.
            RuntimeError: If scope is not configured.
        """
        if self._configured_axis is None:
            raise RuntimeError(
                "Scope not configured. Call configure_current_loop() first."
            )

        logger.info("Capture requested (%s-axis, timeout=%.1fs)", self._configured_axis, timeout)

        x2c = self._session.x2c
        x2c.request_scope_data()

        start = time.monotonic()
        poll_interval = 0.02
        while not x2c.is_scope_data_ready():
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
        measured_data = np.array(
            channel_data.get(var_names["measured"], []), dtype=np.float64
        )
        reference_data = np.array(
            channel_data.get(var_names["reference"], []), dtype=np.float64
        )
        voltage_data = np.array(
            channel_data.get(var_names["voltage"], []), dtype=np.float64
        )

        n_samples = len(measured_data)
        dt_us = self._control_period_us * self._sample_time
        time_us = np.arange(n_samples) * dt_us

        current_units = "counts"
        voltage_units = "counts"
        params = self._session.params
        if params is not None:
            try:
                ifs = params.get_info(_PARAM_FULLSCALE_CURRENT).intended_value
                measured_data = (measured_data / 32768.0) * ifs
                reference_data = (reference_data / 32768.0) * ifs
                current_units = "A"
            except KeyError:
                pass
            try:
                vfs = params.get_info(_PARAM_FULLSCALE_VOLTAGE).intended_value
                voltage_data = (voltage_data / 32768.0) * vfs
                voltage_units = "V"
            except KeyError:
                pass

        gains = {}
        try:
            gains_obj = self._session.current.get_gains(self._configured_axis)
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
            "Captured %d samples (%.1f ms) on %s-axis",
            n_samples, capture_duration_ms, self._configured_axis,
        )

        return StepResponse(
            time_us=time_us,
            reference=reference_data,
            measured=measured_data,
            voltage=voltage_data,
            axis=self._configured_axis,
            gains=gains,
            sample_time=self._sample_time,
            control_period_us=self._control_period_us,
            current_units=current_units,
            voltage_units=voltage_units,
            metadata={
                "var_measured": var_names["measured"],
                "var_reference": var_names["reference"],
                "var_voltage": var_names["voltage"],
                "capture_duration_ms": capture_duration_ms,
            },
        )
