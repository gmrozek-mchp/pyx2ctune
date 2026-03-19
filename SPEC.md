# pyx2ctune -- Specification

A Python library for real-time tuning of Microchip MCAF motor control firmware via X2Cscope.

## Goals

Build a Python package (`pyx2ctune`) that wraps [pyX2Cscope](https://x2cscope.github.io/pyx2cscope/) to provide **MCAF-aware motor control tuning workflows**. The library automates the [MCAF test harness](https://microchiptech.github.io/mcaf-doc/9.0.1/components/testharness.html) to tune PI control loop gains on live hardware, capture step responses, and compute performance metrics -- all from Python scripts or Jupyter notebooks.

**Phase 1** delivers a scriptable library for current loop tuning. **Phase 2** adds a cross-platform GUI (Windows, macOS, Linux) for ease of use by others.

## Background

### Ecosystem

| Component | Role |
|-----------|------|
| [motorBench Development Suite](https://www.microchip.com/en-us/solutions/technologies/motor-control-and-drive/motorbench-development-suite) (v2.55) | GUI tool in MPLAB X that measures motor parameters, auto-tunes gains, and generates firmware code |
| [MCAF](https://microchiptech.github.io/mcaf-doc/9.0.1/index.html) (R9 / RC31) | Motor Control Application Framework -- the generated firmware running on the dsPIC |
| [X2Cscope](https://x2cscope.github.io/) | Runtime diagnostics protocol embedded in MCAF firmware, communicates over UART |
| [pyX2Cscope](https://pypi.org/project/pyx2cscope/) (v0.5.0+) | Python library that talks X2Cscope's LNet protocol, reads ELF files for variable resolution |
| **pyx2ctune** (this project) | MCAF-specific tuning automation built on top of pyX2Cscope |

### Reference Hardware

The initial development target is:

- **Board**: MCS MCLV-48V-300W Development Board (EV18H47A)
- **MCU**: dsPIC33CK256MP508
- **Motor**: Linix 45ZWN24-40 (PMSM, 5 pole pairs)
- **Communication**: UART1 at 115200 baud (TX: RD14, RX: RD13)
- **Firmware**: MCAF R9 with X2Cscope diagnostics enabled

The library should not be hardware-specific; it works with any MCAF project that has X2Cscope enabled.

### Current Loop Tuning Workflow

Per [MCAF section 5.1.6](https://microchiptech.github.io/mcaf-doc/9.0.1/algorithms/foc/tuning.html), the recommended approach for tuning current loop PI gains at runtime is:

1. Enable the test harness guard (`systemData.testing.guard.key = 0xD1A6`)
2. Enter a test operating mode (e.g., `OM_FORCE_CURRENT` or `OM_NORMAL` with velocity override)
3. Set PI gains via runtime variables (`motor.idCtrl.kp/ki`, `motor.iqCtrl.kp/ki`)
4. Inject square-wave perturbation via the test harness (`motor.testing.sqwave.*`)
5. Capture the step response using X2Cscope scope channels (`motor.idq.q`, `motor.idqCmd.q`, `motor.vdq.q`)
6. Evaluate metrics: overshoot, rise time, settling time
7. Iterate on gains until performance is satisfactory

This is the workflow pyx2ctune automates.

## Architecture

```
pyx2ctune/                  # Python package
  __init__.py
  connection.py             # X2CScope connection wrapper
  parameters.py             # parameters.json reader + Q-format conversion
  test_harness.py           # MCAF test harness management
  current_tuning.py         # Current loop tuning workflow
  capture.py                # Scope data acquisition
  analysis.py               # Step response metric computation
  plotting.py               # matplotlib visualization
examples/
  current_loop_tune.py      # End-to-end current loop tuning script
  gain_sweep.py             # Automated Kp/Ki sweep with metrics
pyproject.toml              # Package config, dependencies
SPEC.md                     # This file
```

### Dependency on pyX2Cscope

pyx2ctune uses pyX2Cscope as a library. It does **not** reimplement any low-level communication:

- **pyX2Cscope handles**: serial/TCP connection, LNet protocol, ELF file parsing (DWARF debug info), variable read/write, scope channel management, trigger configuration
- **pyx2ctune handles**: MCAF domain knowledge (parameter semantics, Q-format conversion, test harness orchestration, tuning workflows, step response analysis)

### Data Flow

```
User script (Python / Jupyter)
  │
  ▼
pyx2ctune library
  ├── TuningSession           → X2CScope(port, elf_file)
  ├── ParameterDB             → reads parameters.json
  ├── TestHarness             → writes guard, mode, overrides via X2CScope
  ├── CurrentTuning           → writes PI gains, perturbation config via X2CScope
  ├── ScopeCapture            → configures/captures scope channels via X2CScope
  └── Analysis / Plotting     → processes captured data locally
  │
  ▼
pyX2Cscope (X2CScope class)
  │
  ▼ UART (115200 baud, LNet protocol)
  │
  ▼
dsPIC33CK firmware (MCAF + X2Cscope)
```

## Module Specifications

### 1. `connection.py` -- Session Management

```python
class TuningSession:
    def __init__(self, port: str, elf_file: str,
                 baud_rate: int = 115200,
                 parameters_json: str | None = None):
        """
        Connect to target via pyX2Cscope and load variable information.

        Args:
            port: Serial port (e.g., "/dev/tty.usbmodem1", "COM3")
            elf_file: Path to compiled firmware ELF with debug symbols
            baud_rate: UART baud rate (default 115200, configurable)
            parameters_json: Optional path to motorBench parameters.json
        """

    def get_variable(self, name: str) -> Variable:
        """Get a firmware variable by name, with caching."""

    def disconnect(self):
        """Clean up connection."""
```

Exposes sub-objects:
- `session.test_harness` -- `TestHarness` instance
- `session.current` -- `CurrentTuning` instance
- `session.capture` -- `ScopeCapture` instance
- `session.params` -- `ParameterDB` instance (if parameters_json provided)

### 2. `parameters.py` -- Q-Format Conversion

Reads `parameters.json` generated by motorBench. Each parameter has:

| Field | Description | Example |
|-------|-------------|---------|
| `define_name` | C preprocessor symbol | `KIP` |
| `key` | Hierarchical key | `foc.kip` |
| `intended_value` | Engineering value | `0.6139` |
| `q` | Fixed-point Q format | `15` |
| `scale` | Full-scale value | `1.722` |
| `units` | Physical unit | `V/A` |

**Conversion formulas:**

- Counts to engineering: `value = (counts / 2^q) * scale`
- Engineering to counts: `counts = round(value / scale * 2^q)`

**Key current loop parameters:**

| Key | Description | Scale | Q | Units |
|-----|-------------|-------|---|-------|
| `foc.kip` | Current loop proportional gain | 1.722 | 15 | V/A |
| `foc.kii` | Current loop integral gain | 34437 | 15 | V/A/s |
| `foc.kwp` | Velocity loop proportional gain | 0.0702 | 15 | A/(rad/s) |
| `foc.kwi` | Velocity loop integral gain | 70.16 | 15 | A/rad |

```python
class ParameterDB:
    def __init__(self, json_path: str): ...

    def counts_to_engineering(self, key: str, counts: int) -> float:
        """Convert fixed-point counts to engineering units."""

    def engineering_to_counts(self, key: str, value: float) -> int:
        """Convert engineering units to fixed-point counts."""

    def get_info(self, key: str) -> ParameterInfo:
        """Get full parameter metadata (units, scale, Q, description)."""
```

### 3. `test_harness.py` -- MCAF Test Harness Control

Manages the test harness per [MCAF section 4.5](https://microchiptech.github.io/mcaf-doc/9.0.1/components/testharness.html).

**Constants:**

```python
GUARD_KEY_VALID   = 0xD1A6
GUARD_KEY_RESET   = 0x0000
GUARD_TIMEOUT_MAX = 0xFFFF

# Operating modes (motor.testing.operatingMode)
OM_DISABLED                  = 0
OM_FORCE_VOLTAGE_PWM         = 1
OM_FORCE_VOLTAGE_ALPHABETA   = 2
OM_FORCE_VOLTAGE_DQ          = 3
OM_FORCE_CURRENT             = 4
OM_NORMAL                    = 5

# State transitions (motor.testing.forceStateChange)
TEST_FORCE_STATE_NONE     = 0
TEST_FORCE_STATE_RUN      = 1
TEST_FORCE_STATE_STOP     = 2
TEST_FORCE_STATE_STOP_NOW = 3
```

**Key firmware variables:**

| Variable | Description |
|----------|-------------|
| `systemData.testing.guard.key` | Guard key (write `0xD1A6` to enable test features) |
| `systemData.testing.guard.timeout` | Guard timeout counter (refresh with `0xFFFF`) |
| `motor.testing.operatingMode` | Operating mode enum |
| `motor.testing.overrides` | Override bitfield |
| `motor.testing.forceStateChange` | Force state transition |
| `motor.testing.sqwave.value` | Square wave enable (+1/-1 or 0) |
| `motor.testing.sqwave.halfperiod` | Square wave half-period in PWM cycles |
| `motor.testing.sqwave.idq.d` | D-axis current perturbation amplitude |
| `motor.testing.sqwave.idq.q` | Q-axis current perturbation amplitude |
| `motor.testing.sqwave.velocity` | Velocity perturbation amplitude |

```python
class TestHarness:
    def enable_guard(self):
        """Set guard key to 0xD1A6 and start timeout refresh thread."""

    def disable_guard(self):
        """Reset guard key to 0 and stop refresh thread."""

    def set_operating_mode(self, mode: int): ...
    def set_overrides(self, **kwargs): ...
    def force_state(self, transition: int): ...

    def enter_current_test_mode(self):
        """
        High-level: enter OM_FORCE_CURRENT mode safely.
        Steps (per MCAF section 4.5.15.2):
          1. Enable guard
          2. Set operatingMode = OM_DISABLED
          3. Set desired dq current references
          4. Set operatingMode = OM_FORCE_CURRENT
        """

    def exit_test_mode(self):
        """
        High-level: return to normal operation.
        Steps:
          1. Stop perturbation
          2. Set operatingMode = OM_NORMAL
          3. Force state stop
          4. Disable guard
        """
```

### 4. `current_tuning.py` -- PI Gain Tuning

```python
class CurrentTuning:
    def set_gains(self, kp: float, ki: float, units: str = "engineering"):
        """
        Set current loop PI gains for both d and q axes.

        In engineering mode, kp is in V/A and ki is in V/A/s.
        Converts to fixed-point counts using ParameterDB.
        Writes to motor.idCtrl.kp/ki and motor.iqCtrl.kp/ki.
        Also manages shift counts (nkp, nki) if gain overflows Q15.
        """

    def get_gains(self) -> dict:
        """Read current gains from firmware, return in engineering units."""

    def setup_step_test(self, axis: str = "q",
                        amplitude: int = 500,
                        halfperiod: int = 100):
        """
        Configure and start square-wave perturbation.

        Args:
            axis: "q" or "d" (which current axis to perturb)
            amplitude: perturbation amplitude in counts
            halfperiod: half-period in PWM cycles (at 20kHz: 100 = 5ms -> 100Hz)
        """

    def stop_perturbation(self):
        """Set sqwave.value = 0 to stop perturbation."""
```

### 5. `capture.py` -- Scope Data Acquisition

```python
@dataclass
class StepResponse:
    time_us: np.ndarray          # Time axis in microseconds
    reference: np.ndarray        # Current reference (idqCmd)
    measured: np.ndarray         # Measured current (idq)
    voltage: np.ndarray          # Voltage output (vdq)
    axis: str                    # "q" or "d"
    gains: dict                  # PI gains at time of capture
    sample_time: int             # Scope prescaler
    metadata: dict               # Additional context

class ScopeCapture:
    def configure_current_loop(self, axis: str = "q", sample_time: int = 1):
        """
        Set up scope channels for current loop analysis.
        Channels: motor.idq.{axis}, motor.idqCmd.{axis}, motor.vdq.{axis}
        """

    def capture_frame(self, timeout: float = 5.0) -> StepResponse:
        """
        Request scope data, poll until ready, return StepResponse.
        """
```

### 6. `analysis.py` -- Step Response Metrics

```python
@dataclass
class StepMetrics:
    overshoot: float             # Normalized fraction (0.0 = none, 0.1 = 10%)
    rise_time_us: float          # 10% to 90% of step, in microseconds
    settling_time_us: float      # Time to stay within ±5% band, in microseconds
    steady_state_error: float    # Final value error as fraction of step size

def compute_metrics(response: StepResponse) -> StepMetrics:
    """
    Analyze a captured step response.
    1. Detect step edges in the reference signal
    2. Isolate individual step transitions
    3. Compute metrics for each step, return worst-case / average
    """
```

### 7. `plotting.py` -- Visualization

```python
def plot_step_response(response: StepResponse,
                       metrics: StepMetrics | None = None,
                       show: bool = True) -> matplotlib.figure.Figure:
    """
    Plot step response with optional metric annotations.
    - Top subplot: current reference vs measured
    - Bottom subplot: voltage output
    - Annotations: overshoot marker, rise/settle time spans
    - Title: gain values and key metrics
    """

def plot_gain_sweep(results: list[dict],
                    show: bool = True) -> matplotlib.figure.Figure:
    """
    Summary plot from an automated gain sweep.
    X-axis: Kp (or Ki), Y-axes: overshoot, rise time, settling time.
    """
```

## Configuration

### Runtime Configuration

The `TuningSession` constructor accepts all configuration directly. No config files are required, but pyX2Cscope's `config.ini` can be used for defaults.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `port` | (required) | Serial port path |
| `elf_file` | (required) | Path to firmware ELF with debug symbols |
| `baud_rate` | `115200` | UART baud rate (may increase to 625000 later) |
| `parameters_json` | `None` | Path to motorBench `parameters.json` for unit conversion |

### MCAF Variable Naming

Firmware variables follow the MCAF naming convention using dot-separated hierarchical names that map to C struct member access:

- `motor` → `MCAF_MOTOR_DATA` struct
- `systemData` → `MCAF_SYSTEM_DATA` struct

Example: `motor.idCtrl.kp` corresponds to `MCAF_MOTOR_DATA.idCtrl.kp` in the firmware.

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pyx2cscope` | `>= 0.5.0` | X2Cscope communication, ELF parsing |
| `numpy` | `>= 1.26` | Numerical computation (transitive via pyx2cscope) |
| `matplotlib` | `>= 3.7` | Plotting (transitive via pyx2cscope) |
| `pyyaml` | `>= 6.0` | Reading MCAF YAML configuration files |

**Python version**: 3.12 (compatible with pyX2Cscope's supported range of 3.10-3.12)

## Constraints

- **Read-only access to `motorbench/` directory**: The `motorbench/` folder contains firmware generated by motorBench/MCC. pyx2ctune reads files from it (e.g., `parameters.json`, YAML configs) but never modifies them. Firmware changes are handled separately.
- **No firmware recompilation required**: All tuning is done at runtime via X2Cscope variable writes. The firmware must already be built and flashed with X2Cscope enabled.
- **Safety**: The test harness guard mechanism ensures test modes auto-disable if the guard timeout expires (3.27 seconds at 20kHz). The library refreshes the timeout automatically while a test session is active.

## Example Usage

```python
from pyx2ctune import TuningSession

# Connect
session = TuningSession(
    port="/dev/tty.usbmodem1",
    elf_file="motorbench/mclv-48v-300w/mclv-48v-300w.X/dist/default/debug/mclv-48v-300w.X.debug.elf",
    parameters_json="motorbench/mclv-48v-300w/mclv-48v-300w.X/mcc_generated_files/motorBench/aux-files/parameters.json"
)

# Enter current loop test mode
session.test_harness.enter_current_test_mode()

# Set gains (engineering units: V/A, V/A/s)
session.current.set_gains(kp=4.487, ki=12168)

# Configure scope and inject perturbation
session.capture.configure_current_loop(axis="q")
session.current.setup_step_test(axis="q", amplitude=500, halfperiod=100)

# Capture and analyze
response = session.capture.capture_frame()
metrics = compute_metrics(response)
print(metrics)
# StepMetrics(overshoot=0.02, rise_time_us=80, settling_time_us=400, steady_state_error=0.001)

plot_step_response(response, metrics)

# Automated gain sweep
from pyx2ctune.analysis import compute_metrics
from pyx2ctune.plotting import plot_gain_sweep

results = []
for kp in [1.0, 2.0, 4.0, 6.0, 8.0]:
    session.current.set_gains(kp=kp, ki=12168)
    response = session.capture.capture_frame()
    m = compute_metrics(response)
    results.append({"kp": kp, "ki": 12168, **m.__dict__})

plot_gain_sweep(results)

# Clean up
session.current.stop_perturbation()
session.test_harness.exit_test_mode()
session.disconnect()
```

## Phase 2: Cross-Platform GUI

Once the library is validated with real hardware, add a GUI layer:

- **Framework**: Qt (PySide6) or web (Flask) -- to be decided based on Phase 1 experience
- **Features**: Interactive gain sliders, live step response display, Bode plot visualization, parameter presets
- **Packaging**: Standalone executable via PyInstaller or Briefcase (Windows, macOS, Linux)
- **Architecture**: Thin UI layer calling the same pyx2ctune library functions -- no business logic in the GUI

## References

- [motorBench Development Suite](https://www.microchip.com/en-us/solutions/technologies/motor-control-and-drive/motorbench-development-suite)
- [motorBench Release Collateral (v2.55.0)](https://github.com/microchip-pic-avr-solutions/motorbench-release-collateral/tree/2.55.0)
- [MCAF Documentation (R9, docver 9.0.1)](https://microchiptech.github.io/mcaf-doc/9.0.1/index.html)
- [MCAF Test Harness (section 4.5)](https://microchiptech.github.io/mcaf-doc/9.0.1/components/testharness.html)
- [Current Loop Tuning (section 5.1.6)](https://microchiptech.github.io/mcaf-doc/9.0.1/algorithms/foc/tuning.html)
- [MCAF Configuration Parameters (section 3.5)](https://microchiptech.github.io/mcaf-doc/9.0.1/architecture/config-params.html)
- [pyX2Cscope Documentation](https://x2cscope.github.io/pyx2cscope/)
- [pyX2Cscope API / Scripting](https://x2cscope.github.io/pyx2cscope/scripting.html)
