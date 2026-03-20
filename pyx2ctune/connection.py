"""Session management for pyx2ctune.

Wraps pyX2Cscope's X2CScope class and wires up the tuning sub-modules
(TestHarness, CurrentTuning, ScopeCapture, ParameterDB).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pyx2cscope.x2cscope import X2CScope

from pyx2ctune.parameters import ParameterDB

if TYPE_CHECKING:
    from pyx2cscope.variable.variable import Variable

logger = logging.getLogger(__name__)

_LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s  %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class TuningSession:
    """Top-level session for MCAF motor control tuning.

    Connects to the target MCU via pyX2Cscope, loads the ELF file for
    variable resolution, and initializes tuning sub-modules.

    Args:
        port: Serial port (e.g. "/dev/tty.usbmodem1", "COM3").
        elf_file: Path to compiled firmware ELF with debug symbols.
        baud_rate: UART baud rate (default 115200).
        parameters_json: Optional path to motorBench parameters.json
            for Q-format unit conversion.
        log_dir: Directory for session log files. Defaults to "logs"
            relative to the current working directory.
    """

    def __init__(
        self,
        port: str,
        elf_file: str,
        baud_rate: int = 115200,
        parameters_json: str | None = None,
        log_dir: str | Path = "logs",
    ):
        self._port = port
        self._elf_file = str(Path(elf_file).resolve())
        self._baud_rate = baud_rate
        self._variable_cache: dict[str, Variable] = {}

        self._file_handler = self._setup_file_logging(Path(log_dir))

        logger.info("Connecting to %s at %d baud", port, baud_rate)
        self._x2c = X2CScope(port=port, baud_rate=baud_rate)

        # pyX2Cscope's DWARF parser emits many harmless warnings for
        # XC16-compiled ELFs; suppress them during import.
        root_logger = logging.getLogger()
        prev_level = root_logger.level
        root_logger.setLevel(logging.ERROR)
        try:
            self._x2c.import_variables(self._elf_file)
        finally:
            root_logger.setLevel(prev_level)
        logger.info("Loaded variables from %s", self._elf_file)

        self.params: ParameterDB | None = None
        if parameters_json is not None:
            self.params = ParameterDB(parameters_json)
            logger.info("Loaded %s", self.params)

        # Deferred imports to avoid circular dependencies
        from pyx2ctune.capture import ScopeCapture
        from pyx2ctune.current_tuning import CurrentTuning
        from pyx2ctune.test_harness import TestHarness
        from pyx2ctune.velocity_tuning import VelocityTuning

        self.test_harness = TestHarness(self)
        self.current = CurrentTuning(self)
        self.velocity = VelocityTuning(self)
        self.capture = ScopeCapture(self)

    @property
    def x2c(self) -> X2CScope:
        """Access the underlying pyX2Cscope instance."""
        return self._x2c

    def get_variable(self, name: str) -> Variable:
        """Get a firmware variable by name, with caching.

        Args:
            name: Dot-separated variable name (e.g. "motor.idCtrl.kp").

        Returns:
            pyX2Cscope Variable object for reading/writing values.

        Raises:
            KeyError: If the variable is not found in the ELF file.
        """
        if name not in self._variable_cache:
            try:
                self._variable_cache[name] = self._x2c.get_variable(name)
            except Exception as e:
                raise KeyError(
                    f"Variable {name!r} not found in ELF. "
                    f"Use session.x2c.list_variables() to see available names."
                ) from e
        return self._variable_cache[name]

    def read_variable(self, name: str) -> int | float:
        """Read the current value of a firmware variable.

        Args:
            name: Dot-separated variable name.

        Returns:
            The raw value read from the target.
        """
        value = self.get_variable(name).get_value()
        logger.debug("Read  %s = %s", name, value)
        return value

    def write_variable(self, name: str, value: int | float) -> None:
        """Write a value to a firmware variable.

        Args:
            name: Dot-separated variable name.
            value: Value to write.
        """
        self.get_variable(name).set_value(value)
        logger.debug("Wrote %s = %s", name, value)

    def disconnect(self) -> None:
        """Disconnect from the target and clean up resources."""
        self.test_harness.disable_guard()
        self._x2c.disconnect()
        logger.info("Disconnected from %s", self._port)
        self._teardown_file_logging()

    # ── Session Logging ───────────────────────────────────────────────

    def _setup_file_logging(self, log_dir: Path) -> logging.FileHandler | None:
        """Attach a DEBUG-level FileHandler to the pyx2ctune logger hierarchy."""
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

        pkg_logger = logging.getLogger("pyx2ctune")
        pkg_logger.addHandler(handler)
        # Set logger to DEBUG so the file handler captures everything,
        # but don't affect console output -- that's controlled by the
        # root logger's handler level (set via logging.basicConfig).
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
            logging.getLogger("pyx2ctune").removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

    @property
    def log_path(self) -> Path | None:
        """Path to the current session log file, or None if logging failed."""
        return getattr(self, "_log_path", None)

    def __repr__(self) -> str:
        return (
            f"TuningSession(port={self._port!r}, "
            f"baud_rate={self._baud_rate}, "
            f"elf={Path(self._elf_file).name!r})"
        )
