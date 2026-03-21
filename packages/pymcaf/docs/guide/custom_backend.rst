Custom Backends
===============

pymcaf uses a pluggable backend architecture.  The built-in
:class:`~pymcaf.backends.x2cscope.X2CScopeBackend` communicates over UART
via pyX2Cscope, but you can implement the :class:`~pymcaf.Backend` ABC to
support other transports (TCP/IP, CAN, simulation, etc.).

Implementing a backend
----------------------

Subclass :class:`~pymcaf.Backend` and implement all abstract methods:

.. code-block:: python

   from pymcaf import Backend

   class MyBackend(Backend):
       def __init__(self, address: str):
           self._address = address
           # ... set up connection ...

       def read_variable(self, name: str) -> int | float:
           # Read the named firmware variable and return its raw value
           ...

       def write_variable(self, name: str, value: int | float) -> None:
           # Write a raw value to the named firmware variable
           ...

       def disconnect(self) -> None:
           # Clean up resources
           ...

       # Scope methods (required by the ABC)
       def clear_scope_channels(self) -> None: ...
       def add_scope_channel(self, name: str) -> None: ...
       def set_scope_trigger(self, channel, level, mode, delay, edge) -> None: ...
       def reset_scope_trigger(self) -> None: ...
       def set_sample_time(self, prescaler: int) -> None: ...
       def request_scope_data(self) -> None: ...
       def is_scope_data_ready(self) -> bool: ...
       def get_scope_channel_data(self, channel: str) -> list: ...

Using a custom backend
----------------------

Pass your backend to :class:`~pymcaf.Connection` directly:

.. code-block:: python

   from pymcaf import Connection

   backend = MyBackend("192.168.1.100")
   conn = Connection(backend, parameters_json="parameters.json")

   # Use conn.motor, conn.test_harness, etc. as normal
   print(conn.motor.omega)

All higher-level interfaces (Motor, TestHarness, Scope) work identically
regardless of which backend is used.

Testing with a mock backend
----------------------------

A mock backend is useful for unit testing code that depends on pymcaf
without requiring hardware.  Use :attr:`Motor.VAR_* <pymcaf.Motor>`
constants to reference variables by their generic names:

.. code-block:: python

   from pymcaf.motor import Motor

   class MockBackend(Backend):
       def __init__(self):
           self._vars = {
               Motor.VAR_CURRENT_DQ_D: 0,
               Motor.VAR_CURRENT_DQ_Q: 16384,  # ~0.5 in Q15
               "motor.state": 3,                # RUNNING
           }

       def read_variable(self, name: str) -> int | float:
           return self._vars.get(name, 0)

       def write_variable(self, name: str, value: int | float) -> None:
           self._vars[name] = value

       def disconnect(self) -> None:
           pass

       # ... stub scope methods ...
