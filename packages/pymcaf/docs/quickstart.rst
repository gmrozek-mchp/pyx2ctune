Quick Start
===========

This guide walks through the basics: connecting to hardware, reading motor
variables, writing commands, and using the test harness.

Connecting
----------

Use the :meth:`~pymcaf.Connection.via_x2cscope` factory to connect over
UART using pyX2Cscope:

.. code-block:: python

   from pymcaf import Connection

   conn = Connection.via_x2cscope(
       port="/dev/tty.usbmodem1",   # or "COM3" on Windows
       elf_file="firmware.elf",
       parameters_json="parameters.json",
   )

The ``parameters_json`` argument is optional but required for any method that
converts between fixed-point and engineering units.

Reading motor variables
-----------------------

The :attr:`~pymcaf.Connection.motor` property returns a
:class:`~pymcaf.Motor` instance with typed properties for all motor control
signals:

.. code-block:: python

   motor = conn.motor

   # Measured dq-frame current (Amps)
   idq = motor.idq
   print(f"Id = {idq.d:.3f} A, Iq = {idq.q:.3f} A")

   # Estimated velocity (RPM)
   print(f"Speed = {motor.omega:.1f} RPM")

   # DC link voltage (Volts)
   print(f"Vdc = {motor.vdc:.2f} V")

   # State machine state
   state = motor.state
   print(f"State = {state.name} ({state.value})")

Writing commands
----------------

Writable properties accept engineering-unit values:

.. code-block:: python

   from pymcaf import DQPair

   # Set current command (Amps)
   motor.idq_cmd_raw = DQPair(d=0.0, q=0.5)

   # Set velocity command (RPM)
   motor.velocity_cmd = 500.0

PI gains
--------

Read and write PI controller gains in engineering units:

.. code-block:: python

   # Read q-axis current loop gains
   gains = motor.read_current_gains(axis="q")
   print(f"Kp = {gains.kp:.4f} {gains.kp_units}")
   print(f"Ki = {gains.ki:.4f} {gains.ki_units}")

   # Write new gains
   motor.write_current_gains(axis="q", kp=0.5, ki=100.0)

Test harness
------------

The :attr:`~pymcaf.Connection.test_harness` property provides guard
management, operating mode control, and perturbation signals:

.. code-block:: python

   from pymcaf import OperatingMode

   th = conn.test_harness

   # Enable the test harness guard (with automatic timeout refresh)
   th.enable_guard()

   # Enter current control test mode
   th.enter_current_mode()

   # Configure a square-wave current perturbation
   th.sqwave.idq_amplitude = DQPair(d=0.0, q=0.5)  # 0.5 A
   th.sqwave.halfperiod = 10  # PWM cycles
   th.sqwave.start()

   # ... run test ...

   th.sqwave.stop()
   th.exit_to_normal()
   th.disable_guard()

Disconnecting
-------------

Always disconnect when finished:

.. code-block:: python

   conn.disconnect()
