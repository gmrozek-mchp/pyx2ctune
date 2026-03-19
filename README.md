# pyx2ctune

A Python library for real-time tuning of Microchip MCAF motor control firmware via [X2Cscope](https://x2cscope.github.io/).

pyx2ctune wraps [pyX2Cscope](https://pypi.org/project/pyx2cscope/) to provide MCAF-specific tuning workflows: automated test harness control, PI gain adjustment in engineering units, step response capture, and performance metric computation.

## Installation

```bash
pip install -e .
```

## Quick Start

```python
from pyx2ctune import TuningSession
from pyx2ctune.analysis import compute_metrics
from pyx2ctune.plotting import plot_step_response

session = TuningSession(
    port="/dev/tty.usbmodem1",
    elf_file="path/to/firmware.elf",
    parameters_json="path/to/parameters.json",
)

session.test_harness.enter_current_test_mode()
session.current.set_gains(kp=4.487, ki=12168)

session.capture.configure_current_loop(axis="q")
session.current.setup_step_test(axis="q", amplitude=500, halfperiod=100)

response = session.capture.capture_frame()
metrics = compute_metrics(response)
plot_step_response(response, metrics)

session.current.stop_perturbation()
session.test_harness.exit_test_mode()
session.disconnect()
```

See [SPEC.md](SPEC.md) for full documentation.

## References

- [motorBench Development Suite](https://www.microchip.com/en-us/solutions/technologies/motor-control-and-drive/motorbench-development-suite)
- [MCAF Documentation](https://microchiptech.github.io/mcaf-doc/9.0.1/index.html)
- [pyX2Cscope](https://x2cscope.github.io/pyx2cscope/)
