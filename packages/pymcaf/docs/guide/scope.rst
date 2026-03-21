Scope Capture
=============

The :class:`~pymcaf.scope.Scope` class provides oscilloscope-style waveform
capture from firmware variables.  Access it via
:attr:`conn.scope <pymcaf.Connection.scope>`.

.. note::

   Scope values are returned in **raw firmware units**.  Use
   :meth:`~pymcaf.Connection.q15_to_engineering` or the
   :class:`~pymcaf.ParameterDB` to convert to engineering units after
   capture.

Basic workflow
--------------

Use :attr:`Motor.VAR_* <pymcaf.Motor>` constants to reference firmware
variables by their generic motor control names rather than hardcoding
framework-specific paths:

.. code-block:: python

   from pymcaf.motor import Motor

   scope = conn.scope

   # 1. Configure channels using Motor variable identifiers
   scope.clear_channels()
   scope.add_channel(Motor.VAR_CURRENT_DQ_Q)
   scope.add_channel(Motor.VAR_VELOCITY)

   # 2. Set sample time
   scope.set_sample_time(1)  # every N-th ISR cycle

   # 3. Configure trigger (optional)
   scope.set_trigger(
       channel_name=Motor.VAR_CURRENT_DQ_Q,
       level=1000,
       mode=1,
       delay=0,
       edge=0,
   )

   # 4. Request data capture
   scope.request_data()

   # 5. Wait for data
   while not scope.is_data_ready():
       pass  # or time.sleep(0.01)

   # 6. Retrieve data
   data = scope.get_channel_data()

Converting to engineering units
-------------------------------

.. code-block:: python

   import numpy as np

   data = scope.get_channel_data()
   raw_current = data[Motor.VAR_CURRENT_DQ_Q]
   eng_data = [
       conn.q15_to_engineering(sample, "mcapi.fullscale.current")
       for sample in raw_current
   ]

Trigger modes
-------------

The trigger behavior depends on the backend implementation.  Refer to the
`pyX2Cscope documentation <https://x2cscope.github.io/pyx2cscope/>`_ for
details on trigger modes and edge settings.
