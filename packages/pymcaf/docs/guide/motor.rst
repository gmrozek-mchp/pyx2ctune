Motor Variables
===============

The :class:`~pymcaf.Motor` class provides typed, property-based access to
MCAF motor control variables.  All values are in engineering units.  Access
it via :attr:`conn.motor <pymcaf.Connection.motor>`.

Measured signals (read-only)
----------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Property
     - Units
     - Description
   * - :attr:`~pymcaf.Motor.idq`
     - Amps
     - Measured dq-frame current
   * - :attr:`~pymcaf.Motor.ialphabeta`
     - Amps
     - Measured stationary-frame current
   * - :attr:`~pymcaf.Motor.iabc`
     - Amps
     - Measured three-phase current (c may be zero)
   * - :attr:`~pymcaf.Motor.vdq`
     - Volts
     - Output dq-frame voltage
   * - :attr:`~pymcaf.Motor.valphabeta`
     - Volts
     - Output stationary-frame voltage
   * - :attr:`~pymcaf.Motor.vabc`
     - Volts
     - Desired phase voltages
   * - :attr:`~pymcaf.Motor.omega`
     - RPM
     - Estimated motor velocity
   * - :attr:`~pymcaf.Motor.theta_electrical`
     - degrees
     - Electrical angle (0--360)
   * - :attr:`~pymcaf.Motor.vdc`
     - Volts
     - DC link voltage
   * - :attr:`~pymcaf.Motor.state`
     - --
     - State machine state (:class:`~pymcaf.MotorState`)

Command signals
---------------

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Property
     - Units
     - Description
   * - :attr:`~pymcaf.Motor.idq_cmd_raw`
     - Amps
     - Current command pre-perturbation (read/write)
   * - :attr:`~pymcaf.Motor.idq_cmd`
     - Amps
     - Current command post-perturbation (read-only)
   * - :attr:`~pymcaf.Motor.vdq_cmd`
     - Volts
     - Voltage command (read/write)
   * - :attr:`~pymcaf.Motor.velocity_cmd`
     - RPM
     - Velocity command (read/write)
   * - :attr:`~pymcaf.Motor.velocity_cmd_rate_limited`
     - RPM
     - Rate-limited velocity command (read-only)

Duty cycles
-----------

Duty cycles are fractional values from 0.0 to 1.0.

.. list-table::
   :header-rows: 1
   :widths: 25 55

   * - Property
     - Description
   * - :attr:`~pymcaf.Motor.dabc_raw`
     - Before dead-time compensation, ZSM, and clipping
   * - :attr:`~pymcaf.Motor.dabc_unshifted`
     - After dead-time comp, before ZSM and clipping
   * - :attr:`~pymcaf.Motor.dabc`
     - Final duty cycles (read/write)

PI gains
--------

PI gains are individual float properties, consistent with all other motor
parameters.

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Property
     - Units
     - Description
   * - :attr:`~pymcaf.Motor.current_kp_d`
     - V/A
     - D-axis current loop proportional gain (read/write)
   * - :attr:`~pymcaf.Motor.current_ki_d`
     - V/A/s
     - D-axis current loop integral gain (read/write)
   * - :attr:`~pymcaf.Motor.current_kp_q`
     - V/A
     - Q-axis current loop proportional gain (read/write)
   * - :attr:`~pymcaf.Motor.current_ki_q`
     - V/A/s
     - Q-axis current loop integral gain (read/write)
   * - :attr:`~pymcaf.Motor.velocity_kp`
     - A/(rad/s)
     - Velocity loop proportional gain (read/write)
   * - :attr:`~pymcaf.Motor.velocity_ki`
     - A/rad
     - Velocity loop integral gain (read/write)

.. code-block:: python

   # Current loop (per-axis)
   kp = motor.current_kp_q          # read
   motor.current_kp_q = 0.5         # write
   motor.current_ki_q = 100.0

   # Both axes
   motor.current_kp_d = motor.current_kp_q = 0.5
   motor.current_ki_d = motor.current_ki_q = 100.0

   # Velocity loop
   kp = motor.velocity_kp
   motor.velocity_kp = 0.01
   motor.velocity_ki = 0.5

Variable identifiers
--------------------

The ``Motor`` class exposes public constants that map generic motor control
names to framework-specific firmware variable identifiers.  These are useful
when configuring scope channels or other tools that need to reference
firmware variables by name:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Constant
     - Description
   * - :attr:`~pymcaf.Motor.VAR_CURRENT_DQ_D`
     - Measured d-axis current
   * - :attr:`~pymcaf.Motor.VAR_CURRENT_DQ_Q`
     - Measured q-axis current
   * - :attr:`~pymcaf.Motor.VAR_CURRENT_CMD_DQ_D`
     - d-axis current command (post-perturbation)
   * - :attr:`~pymcaf.Motor.VAR_CURRENT_CMD_DQ_Q`
     - q-axis current command (post-perturbation)
   * - :attr:`~pymcaf.Motor.VAR_VOLTAGE_DQ_D`
     - d-axis output voltage
   * - :attr:`~pymcaf.Motor.VAR_VOLTAGE_DQ_Q`
     - q-axis output voltage
   * - :attr:`~pymcaf.Motor.VAR_VELOCITY`
     - Estimated electrical velocity
   * - :attr:`~pymcaf.Motor.VAR_VELOCITY_CMD`
     - Velocity command (user input)
   * - :attr:`~pymcaf.Motor.VAR_VELOCITY_REF`
     - Velocity reference to speed controller (post rate-limiting)

.. code-block:: python

   from pymcaf.motor import Motor

   # Use constants to configure scope channels
   scope.add_channel(Motor.VAR_CURRENT_DQ_Q)
   scope.add_channel(Motor.VAR_CURRENT_CMD_DQ_Q)

   # Set trigger on the current command
   scope.set_trigger(Motor.VAR_CURRENT_CMD_DQ_Q, level=1000)

These constants use generic motor control vocabulary so that other SDKs
(e.g. a future Qspin SDK) can expose the same constant names with their
own framework-specific values.

Reference frames
----------------

pymcaf uses standard FOC reference-frame terminology:

- **dq** -- synchronous (rotating) frame, aligned with the rotor flux
- **alpha-beta** -- stationary frame (Clarke transform output)
- **abc** -- three-phase quantities (phase A, B, C)

All reference-frame conversions happen inside the firmware; pymcaf reads
the result of each transform stage.
