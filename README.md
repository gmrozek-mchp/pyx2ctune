# mctoolbox

A Python library and GUI for real-time tuning of Microchip MCAF motor control firmware via [X2Cscope](https://x2cscope.github.io/).

mctoolbox wraps [pyX2Cscope](https://pypi.org/project/pyx2cscope/) to provide MCAF-specific tuning workflows: automated test harness control, PI gain adjustment in engineering units (with Q-format conversion), step response capture, and performance metric computation.

## Getting Started

### Prerequisites

- Python 3.10+ ([python.org](https://www.python.org/downloads/))
- MCAF firmware built and flashed with X2Cscope enabled
- Target board connected via USB/UART

### Setup

Create a virtual environment and install the package:

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

pip install -e .
```

This installs the `mctoolbox` library and its dependencies (`pyx2cscope`, `numpy`,
`matplotlib`, `control`).

### GUI Application

Launch the standalone GUI:

```bash
mctoolbox-gui
# or: python -m mctoolbox.gui
```

The GUI provides a point-and-click tuning workflow: connect to the board,
read/set PI gains, enter test mode, configure perturbation, capture step
responses, and view metrics -- all without writing code. Connection settings
and file paths are remembered between sessions.

Pre-built executables for Windows, macOS, and Linux are available on the
[Releases](https://github.com/gmrozek-mchp/mctoolbox/releases) page (no Python
installation required).

**macOS note:** Open the `.dmg`, drag `mctoolbox` to the Applications folder,
then right-click the app in Applications and select **Open** on first launch
(required because the app is not signed with an Apple Developer certificate).

### Quick Start (Script)

```python
from mctoolbox import TuningSession
from mctoolbox.analysis import compute_metrics
from mctoolbox.plotting import plot_step_response

session = TuningSession(
    port="/dev/tty.usbmodem1",
    elf_file="path/to/firmware.elf",
    parameters_json="path/to/parameters.json",
)

gains = session.current.get_gains(axis="q")
print(f"Kp = {gains.kp:.4f} {gains.kp_units}  (Q{gains.kp_shift})")

session.test_harness.enter_current_test_mode()
session.current.set_gains(kp=3.0, ki=5000)

session.capture.configure_current_loop(axis="q")
session.current.setup_step_test(axis="q", amplitude=0.5, halfperiod=5.0)

response = session.capture.capture_frame()
metrics = compute_metrics(response)
plot_step_response(response, metrics)

session.current.stop_perturbation()
session.test_harness.exit_test_mode()
session.disconnect()
```

## Session Logging

Each `TuningSession` automatically creates a timestamped log file in the `logs/` directory
(e.g. `logs/session_20260319_143022.log`). The log captures all variable reads/writes,
gain changes, test harness events, and scope captures at DEBUG level.

## License

This project is licensed under the [MIT License](LICENSE).

Third-party dependencies are subject to their own licenses. See
[THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) for a complete listing,
including licensing considerations for PyQt5 (GPL-3.0, transitive via
pyx2cscope) and Microchip proprietary packages.

## References

See [SPEC.md](SPEC.md) for full architecture and module documentation.

- [motorBench Development Suite](https://www.microchip.com/en-us/solutions/technologies/motor-control-and-drive/motorbench-development-suite)
- [MCAF Documentation](https://microchiptech.github.io/mcaf-doc/9.0.1/index.html)
- [pyX2Cscope](https://x2cscope.github.io/pyx2cscope/)
