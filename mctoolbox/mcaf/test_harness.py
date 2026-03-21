"""MCAF test harness management (mctoolbox layer).

Thin wrapper around :class:`pymcaf.TestHarness` that satisfies the
:class:`mctoolbox.interfaces.TestHarness` ABC.  All individual
operations delegate to the pymcaf SDK; this module adds only the
mctoolbox-specific workflow orchestration (``enter_test_mode`` /
``exit_test_mode`` dispatcher).

Reference: https://microchiptech.github.io/mcaf-doc/9.0.1/components/testharness.html
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mctoolbox import interfaces as _interfaces

if TYPE_CHECKING:
    from mctoolbox.mcaf.session import TuningSession

logger = logging.getLogger(__name__)


class TestHarness(_interfaces.TestHarness):
    """Manages the MCAF runtime test harness.

    Delegates guard, operating mode, override, and perturbation control
    to :attr:`pymcaf.Connection.test_harness`.  Provides the mctoolbox
    ``enter_test_mode`` / ``exit_test_mode`` ABC interface.
    """

    def __init__(self, session: TuningSession):
        self._session = session

    @property
    def _th(self):
        """Shortcut to the pymcaf TestHarness instance."""
        return self._session.conn.test_harness

    # ── ABC interface ──────────────────────────────────────────────────

    def enter_test_mode(self, mode: str = "current") -> str:
        """Enter a test operating mode by name.

        Args:
            mode: One of ``"current"``, ``"velocity_override"``,
                  ``"force_voltage"``.

        Returns:
            The name of the operating mode actually entered.
        """
        dispatch = {
            "current": self._th.enter_current_mode,
            "velocity_override": self._th.enter_velocity_override_mode,
            "force_voltage": self._th.enter_force_voltage_mode,
        }
        fn = dispatch.get(mode)
        if fn is None:
            raise ValueError(
                f"Unknown test mode {mode!r}; "
                f"choose from {list(dispatch)}"
            )
        fn()
        return self._th.operating_mode.name

    def exit_test_mode(self) -> None:
        """Return to normal operation safely."""
        self._th.exit_to_normal()

    def get_motor_state(self) -> _interfaces.MotorState:
        """Read the current motor state machine state."""
        ms = self._session.conn.motor.state
        return _interfaces.MotorState(value=ms.value, name=ms.name)

    @property
    def guard_active(self) -> bool:
        return self._th.guard_active

    # ── Convenience delegates ─────────────────────────────────────────
    # These let existing mctoolbox code keep calling methods on the
    # mctoolbox TestHarness without changing call sites.

    def enable_guard(self) -> None:
        self._th.enable_guard()

    def disable_guard(self) -> None:
        self._th.disable_guard()

    def set_operating_mode(self, mode) -> None:
        self._th.operating_mode = mode

    def get_operating_mode(self):
        return self._th.operating_mode

    def set_overrides(self, flags: int) -> None:
        self._th.overrides = flags

    def get_overrides(self) -> int:
        return self._th.overrides

    def set_override_flags(self, **kwargs: bool) -> None:
        self._th.set_override_flags(**kwargs)

    def force_state(self, transition) -> None:
        self._th.force_state(transition)

    # ── Legacy high-level methods (delegate to pymcaf) ────────────────

    def enter_current_test_mode(self) -> None:
        self._th.enter_current_mode()

    def enter_velocity_override_mode(self) -> None:
        self._th.enter_velocity_override_mode()

    def enter_force_voltage_mode(self) -> None:
        self._th.enter_force_voltage_mode()

    # ── Legacy engineering-unit helpers (delegate to motor) ────────────

    def set_commutation_frequency(self, omega: int) -> None:
        self._th.override_omega_electrical = omega

    def get_commutation_frequency(self) -> int:
        return self._th.override_omega_electrical

    def set_commutation_frequency_rpm(self, rpm: float) -> int:
        conn = self._session.conn
        counts = conn.engineering_to_q15(rpm, "mcapi.fullscale.velocity")
        self._th.override_omega_electrical = counts
        logger.info("Set commutation frequency: %.1f RPM (%d counts)", rpm, counts)
        return counts

    def set_dq_current(self, d: int, q: int) -> None:
        from pymcaf.types import DQPair
        self._session.conn.motor.idq_cmd_raw = DQPair(d=float(d), q=float(q))

    def get_dq_current(self) -> tuple[int, int]:
        pair = self._session.conn.motor.idq_cmd_raw
        return (int(pair.d), int(pair.q))

    def set_dq_current_amps(self, d_amps: float, q_amps: float) -> tuple[int, int]:
        from pymcaf.types import DQPair
        self._session.conn.motor.idq_cmd_raw = DQPair(d=d_amps, q=q_amps)
        conn = self._session.conn
        d_counts = conn.engineering_to_q15(d_amps, "mcapi.fullscale.current")
        q_counts = conn.engineering_to_q15(q_amps, "mcapi.fullscale.current")
        return d_counts, q_counts

    def set_dq_voltage(self, d: int, q: int) -> None:
        from pymcaf.types import DQPair
        self._session.conn.motor.vdq_cmd = DQPair(d=float(d), q=float(q))

    def get_dq_voltage(self) -> tuple[int, int]:
        pair = self._session.conn.motor.vdq_cmd
        return (int(pair.d), int(pair.q))

    def set_dq_voltage_volts(self, d_volts: float, q_volts: float) -> tuple[int, int]:
        from pymcaf.types import DQPair
        self._session.conn.motor.vdq_cmd = DQPair(d=d_volts, q=q_volts)
        conn = self._session.conn
        d_counts = conn.engineering_to_q15(d_volts, "mcapi.fullscale.voltage")
        q_counts = conn.engineering_to_q15(q_volts, "mcapi.fullscale.voltage")
        return d_counts, q_counts
