"""Allow running with: python -m mctoolbox.gui"""

import os
from pathlib import Path

# pyx2cscope unconditionally writes a log file to cwd at import time.
# When launched as a .app bundle, cwd is "/" (read-only), so move to a
# writable directory before importing anything from mctoolbox.
_log_dir = Path.home() / ".mctoolbox"
_log_dir.mkdir(exist_ok=True)
os.chdir(_log_dir)

from mctoolbox.gui import main  # noqa: E402

main()
