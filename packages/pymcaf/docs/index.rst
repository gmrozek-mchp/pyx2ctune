pymcaf
======

**Python SDK for Microchip MCAF motor control firmware.**

pymcaf provides a typed, engineering-unit interface for communicating with
MCAF-based motor controllers at runtime via
`pyX2Cscope <https://x2cscope.github.io/pyx2cscope/>`_.
All public APIs work in real-world units (Amps, Volts, RPM) --
Q-format conversion is handled internally.

Features
--------

- **Motor variables** -- read currents, voltages, velocities, duty cycles, and
  PI gains as typed properties in engineering units.
- **Test harness** -- guard management, operating mode control, override flags,
  forced state transitions, and perturbation signals.
- **Scope capture** -- oscilloscope-style waveform recording from firmware
  variables.
- **Pluggable backends** -- ships with a pyX2Cscope backend; implement the
  :class:`~pymcaf.Backend` ABC to add your own transport.
- **Standalone** -- zero dependencies on higher-level tools; usable as a
  general-purpose MCAF SDK.

.. code-block:: python

   from pymcaf import Connection, OperatingMode

   conn = Connection.via_x2cscope(
       port="/dev/tty.usbmodem1",
       elf_file="firmware.elf",
       parameters_json="parameters.json",
   )

   # Read measured q-axis current in Amps
   iq = conn.motor.idq.q

   # Set velocity command in RPM
   conn.motor.velocity_cmd = 1000.0

   # Read current-loop PI gains
   kp = conn.motor.current_kp_q
   ki = conn.motor.current_ki_q
   print(f"Kp = {kp:.4f} V/A, Ki = {ki:.2f} V/A/s")

   conn.disconnect()

Contents
--------

.. toctree::
   :maxdepth: 2

   installation
   quickstart
   guide/index
   api/index

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
