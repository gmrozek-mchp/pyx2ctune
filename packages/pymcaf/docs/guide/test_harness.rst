Test Harness
============

The :class:`~pymcaf.TestHarness` class provides access to MCAF's built-in
test modes for accretive testing of motor control firmware.  Access it via
:attr:`conn.test_harness <pymcaf.Connection.test_harness>`.

For background on MCAF test harness design, see the
`MCAF Test Harness documentation
<https://microchiptech.github.io/mcaf-doc/9.0.1/components/testharness.html>`_.

Guard management
----------------

The test harness guard prevents accidental activation of test modes.  You
must enable it before using any test harness features:

.. code-block:: python

   th = conn.test_harness

   # Enable guard with automatic timeout refresh (background thread)
   th.enable_guard()

   # ... use test harness ...

   # Disable guard when done
   th.disable_guard()

The guard uses a key/timeout mechanism.  When enabled, pymcaf starts a
background thread that periodically writes ``GUARD_TIMEOUT_MAX`` to prevent
the firmware from resetting the guard.

Operating modes
---------------

MCAF supports several operating modes for accretive testing:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Mode
     - Description
   * - ``OperatingMode.DISABLED``
     - Output transistors off; feedback computations still run
   * - ``OperatingMode.FORCE_VOLTAGE_DQ``
     - Open-loop voltage control in the dq frame
   * - ``OperatingMode.FORCE_CURRENT``
     - Current (torque) control mode
   * - ``OperatingMode.NORMAL``
     - Normal velocity control

.. code-block:: python

   from pymcaf import OperatingMode

   th.operating_mode = OperatingMode.FORCE_CURRENT
   print(th.operating_mode)  # OperatingMode.FORCE_CURRENT

Mode entry/exit procedures
--------------------------

The test harness provides convenience methods that follow the documented
MCAF mode entry procedures:

.. code-block:: python

   # Enter current control test mode (OM_DISABLED -> OM_FORCE_CURRENT)
   th.enter_current_mode()

   # Enter open-loop voltage mode (OM_DISABLED -> OM_FORCE_VOLTAGE_DQ)
   th.enter_force_voltage_mode()

   # Enter velocity override mode (sets override flag, stays in OM_NORMAL)
   th.enter_velocity_override_mode()

   # Return to normal operation
   th.exit_to_normal()

Override flags
--------------

Override flags control whether specific features use their normal input
or a test override:

.. code-block:: python

   # Set individual flags by name
   th.set_override_flags(
       velocity_command=True,
       commutation=True,
       stall_detection=True,
   )

   # Read the raw override bitfield
   print(f"overrides = 0x{th.overrides:04X}")

Forced state transitions
------------------------

Force state machine transitions without using hardware buttons:

.. code-block:: python

   from pymcaf import ForceState

   th.force_state(ForceState.RUN)    # equivalent to pressing "start"
   th.force_state(ForceState.STOP)   # equivalent to pressing "stop"

Symmetric perturbation (square wave)
-------------------------------------

The :attr:`~pymcaf.TestHarness.sqwave` sub-object configures a square-wave
perturbation signal:

.. code-block:: python

   from pymcaf import DQPair

   th.sqwave.halfperiod = 10                        # PWM cycles
   th.sqwave.idq_amplitude = DQPair(d=0.0, q=0.5)  # 0.5 A q-axis
   th.sqwave.start()

   # ... capture step response ...

   th.sqwave.stop()

Asymmetric perturbation
-----------------------

The :attr:`~pymcaf.TestHarness.asymmetric` sub-object configures an
asymmetric pulse waveform with two independently timed phases:

.. code-block:: python

   phase0 = th.asymmetric.phase(0)
   phase0.duration = 8
   phase0.idq = DQPair(d=0.0, q=1.0)

   phase1 = th.asymmetric.phase(1)
   phase1.duration = 12
   phase1.idq = DQPair(d=0.0, q=-0.4)

   th.asymmetric.start()

Autostepping and autobalance are also available -- see
:class:`~pymcaf.AsymmetricPerturbation` for details.
