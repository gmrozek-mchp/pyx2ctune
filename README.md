# pyx2ctune

A Python library for real-time tuning of Microchip MCAF motor control firmware via [X2Cscope](https://x2cscope.github.io/).

pyx2ctune wraps [pyX2Cscope](https://pypi.org/project/pyx2cscope/) to provide MCAF-specific tuning workflows: automated test harness control, PI gain adjustment in engineering units (with Q-format conversion), step response capture, and performance metric computation.

## Getting Started

### Prerequisites

- Python 3.10+ ([python.org](https://www.python.org/downloads/))
- MCAF firmware built and flashed with X2Cscope enabled
- Target board connected via USB/UART

### Setup

Create a virtual environment and install the package with Jupyter support:

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

pip install -e ".[notebook]"
```

This installs the `pyx2ctune` library, its dependencies (`pyx2cscope`, `numpy`,
`matplotlib`), and Jupyter (`jupyterlab`, `ipykernel`).

If you only need the library (no notebook or GUI), use `pip install -e .` instead.

### GUI Application

Launch the standalone GUI:

```bash
pyx2ctune-gui
# or: python -m pyx2ctune.gui
```

The GUI provides the same tuning workflow as the notebook in a point-and-click
interface: connect to the board, read/set PI gains, enter test mode, configure
perturbation, capture step responses, and view metrics -- all without writing code.
Connection settings and file paths are remembered between sessions.

Pre-built executables for Windows, macOS, and Linux are available on the
[Releases](https://github.com/gmrozek-mchp/pyx2ctune/releases) page (no Python
installation required).

**macOS note:** Open the `.dmg`, drag `pyx2ctune` to the Applications folder,
then right-click the app in Applications and select **Open** on first launch
(required because the app is not signed with an Apple Developer certificate).

### Jupyter Notebook

Alternatively, use the interactive notebook for a code-driven workflow:

```bash
jupyter lab notebooks/current_loop_tuning.ipynb
```

The notebook walks through the full current loop tuning workflow:

1. Configure serial port and file paths
2. Connect to the target board
3. Read current PI gains from firmware
4. Enter current test mode (activates test harness guard)
5. Set PI gains in engineering units (V/A, V/A/s)
6. Configure scope and start square-wave perturbation
7. Capture and analyze step response (overshoot, rise time, settling time)
8. Iterate on gains with quick re-capture
9. (Optional) Automated Kp sweep with summary plot
10. Clean up

## Quick Start (Script)

```python
from pyx2ctune import TuningSession
from pyx2ctune.analysis import compute_metrics
from pyx2ctune.plotting import plot_step_response

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

Console output is kept quiet by default. To see log messages inline in a notebook,
change the `logging.basicConfig` level from `WARNING` to `INFO`.

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
