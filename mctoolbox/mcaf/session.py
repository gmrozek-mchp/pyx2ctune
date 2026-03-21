"""Session management for MCAF motor control tuning.

Wraps a pymcaf Connection and wires up the tuning sub-modules
(TestHarness, CurrentTuning, VelocityTuning, ScopeCapture).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pymcaf import Connection

from mctoolbox import interfaces as _interfaces

if TYPE_CHECKING:
    from pymcaf.parameters import ParameterDB

logger = logging.getLogger(__name__)

_LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s  %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class TuningSession(_interfaces.TuningSession):
    """Top-level session for MCAF motor control tuning.

    Wraps a :class:`pymcaf.Connection` and initialises tuning
    sub-modules for test harness control, current/velocity loop
    tuning, and scope capture.

    Args:
        conn: A :class:`pymcaf.Connection` to the target board.
        log_dir: Directory for session log files. Defaults to "logs"
            relative to the current working directory.
    """

    def __init__(
        self,
        conn: Connection,
        log_dir: str | Path = "logs",
    ):
        self._conn = conn

        self._file_handler = self._setup_file_logging(Path(log_dir))

        logger.info("Session created with %r", conn)

        from mctoolbox.mcaf.capture import ScopeCapture
        from mctoolbox.mcaf.current_tuning import CurrentTuning
        from mctoolbox.mcaf.test_harness import TestHarness
        from mctoolbox.mcaf.velocity_tuning import VelocityTuning

        self.test_harness = TestHarness(self)
        self.current = CurrentTuning(self)
        self.velocity = VelocityTuning(self)
        self.capture = ScopeCapture(self)

    @property
    def conn(self) -> Connection:
        """The underlying pymcaf Connection."""
        return self._conn

    @property
    def params(self) -> ParameterDB | None:
        """Shortcut to the connection's ParameterDB."""
        return self._conn.params

    # ── Variable access (convenience delegates) ───────────────────────

    def read_variable(self, name: str) -> int | float:
        """Read the raw value of a firmware variable.

        Convenience method that delegates to ``conn.read_raw()``.
        """
        return self._conn.read_raw(name)

    def write_variable(self, name: str, value: int | float) -> None:
        """Write a raw value to a firmware variable.

        Convenience method that delegates to ``conn.write_raw()``.
        """
        self._conn.write_raw(name, value)

    def disconnect(self) -> None:
        """Disconnect from the target and clean up resources."""
        self.test_harness.disable_guard()
        self._conn.disconnect()
        logger.info("Session disconnected")
        self._teardown_file_logging()

    # ── Convenience factory ───────────────────────────────────────────

    @classmethod
    def from_x2cscope(
        cls,
        port: str,
        elf_file: str,
        baud_rate: int = 115200,
        parameters_json: str | None = None,
        **kwargs,
    ) -> TuningSession:
        """Create a TuningSession using the pyx2cscope backend.

        This is the simplest way to connect to a board:

        .. code-block:: python

            session = TuningSession.from_x2cscope(
                port="/dev/tty.usbmodem1",
                elf_file="firmware.elf",
                parameters_json="parameters.json",
            )

        Args:
            port: Serial port.
            elf_file: Path to firmware ELF.
            baud_rate: UART baud rate (default 115200).
            parameters_json: Optional path to parameters.json.
            **kwargs: Additional arguments passed to TuningSession.
        """
        conn = Connection.via_x2cscope(
            port=port,
            elf_file=elf_file,
            baud_rate=baud_rate,
            parameters_json=parameters_json,
        )
        return cls(conn, **kwargs)

    # ── Session Logging ───────────────────────────────────────────────

    def _setup_file_logging(self, log_dir: Path) -> logging.FileHandler | None:
        """Attach a DEBUG-level FileHandler to the mctoolbox logger hierarchy."""
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning("Could not create log directory %s", log_dir)
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"session_{timestamp}.log"

        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT))

        pkg_logger = logging.getLogger("mctoolbox")
        pkg_logger.addHandler(handler)
        pkg_logger.setLevel(logging.DEBUG)
        pkg_logger.propagate = False

        self._log_path = log_path
        logger.info("Session log: %s", log_path)
        return handler

    def _teardown_file_logging(self) -> None:
        """Remove the session file handler."""
        if self._file_handler is not None:
            logger.info("Session log closed: %s", self._log_path)
            self._file_handler.flush()
            logging.getLogger("mctoolbox").removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

    @property
    def log_path(self) -> Path | None:
        """Path to the current session log file, or None if logging failed."""
        return getattr(self, "_log_path", None)

    def __repr__(self) -> str:
        return f"TuningSession({self._conn!r})"
