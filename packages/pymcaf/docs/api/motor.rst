Motor
=====

.. autoclass:: pymcaf.motor.Motor
   :no-members:
   :show-inheritance:

Measured signals (read-only)
----------------------------

.. autoproperty:: pymcaf.motor.Motor.idq
.. autoproperty:: pymcaf.motor.Motor.idq_d
.. autoproperty:: pymcaf.motor.Motor.idq_q
.. autoproperty:: pymcaf.motor.Motor.ialphabeta
.. autoproperty:: pymcaf.motor.Motor.ialphabeta_alpha
.. autoproperty:: pymcaf.motor.Motor.ialphabeta_beta
.. autoproperty:: pymcaf.motor.Motor.iabc
.. autoproperty:: pymcaf.motor.Motor.iabc_a
.. autoproperty:: pymcaf.motor.Motor.iabc_b
.. autoproperty:: pymcaf.motor.Motor.iabc_c
.. autoproperty:: pymcaf.motor.Motor.vdq
.. autoproperty:: pymcaf.motor.Motor.vdq_d
.. autoproperty:: pymcaf.motor.Motor.vdq_q
.. autoproperty:: pymcaf.motor.Motor.valphabeta
.. autoproperty:: pymcaf.motor.Motor.valphabeta_alpha
.. autoproperty:: pymcaf.motor.Motor.valphabeta_beta
.. autoproperty:: pymcaf.motor.Motor.vabc
.. autoproperty:: pymcaf.motor.Motor.vabc_a
.. autoproperty:: pymcaf.motor.Motor.vabc_b
.. autoproperty:: pymcaf.motor.Motor.vabc_c
.. autoproperty:: pymcaf.motor.Motor.omega
.. autoproperty:: pymcaf.motor.Motor.theta_electrical
.. autoproperty:: pymcaf.motor.Motor.vdc
.. autoproperty:: pymcaf.motor.Motor.state

Command signals
---------------

.. autoproperty:: pymcaf.motor.Motor.idq_cmd_raw
.. autoproperty:: pymcaf.motor.Motor.idq_cmd_raw_d
.. autoproperty:: pymcaf.motor.Motor.idq_cmd_raw_q
.. autoproperty:: pymcaf.motor.Motor.idq_cmd
.. autoproperty:: pymcaf.motor.Motor.idq_cmd_d
.. autoproperty:: pymcaf.motor.Motor.idq_cmd_q
.. autoproperty:: pymcaf.motor.Motor.vdq_cmd
.. autoproperty:: pymcaf.motor.Motor.vdq_cmd_d
.. autoproperty:: pymcaf.motor.Motor.vdq_cmd_q
.. autoproperty:: pymcaf.motor.Motor.velocity_cmd
.. autoproperty:: pymcaf.motor.Motor.velocity_cmd_rate_limited

Duty cycles
-----------

.. autoproperty:: pymcaf.motor.Motor.dabc_raw
.. autoproperty:: pymcaf.motor.Motor.dabc_raw_a
.. autoproperty:: pymcaf.motor.Motor.dabc_raw_b
.. autoproperty:: pymcaf.motor.Motor.dabc_raw_c
.. autoproperty:: pymcaf.motor.Motor.dabc_unshifted
.. autoproperty:: pymcaf.motor.Motor.dabc_unshifted_a
.. autoproperty:: pymcaf.motor.Motor.dabc_unshifted_b
.. autoproperty:: pymcaf.motor.Motor.dabc_unshifted_c
.. autoproperty:: pymcaf.motor.Motor.dabc
.. autoproperty:: pymcaf.motor.Motor.dabc_a
.. autoproperty:: pymcaf.motor.Motor.dabc_b
.. autoproperty:: pymcaf.motor.Motor.dabc_c

Current loop PI gains
---------------------

.. autoproperty:: pymcaf.motor.Motor.current_kp_d
.. autoproperty:: pymcaf.motor.Motor.current_ki_d
.. autoproperty:: pymcaf.motor.Motor.current_kp_q
.. autoproperty:: pymcaf.motor.Motor.current_ki_q

Velocity loop PI gains
----------------------

.. autoproperty:: pymcaf.motor.Motor.velocity_kp
.. autoproperty:: pymcaf.motor.Motor.velocity_ki

Variable identifiers
--------------------

.. autoattribute:: pymcaf.motor.Motor.VAR_CURRENT_DQ_D
.. autoattribute:: pymcaf.motor.Motor.VAR_CURRENT_DQ_Q
.. autoattribute:: pymcaf.motor.Motor.VAR_CURRENT_CMD_DQ_D
.. autoattribute:: pymcaf.motor.Motor.VAR_CURRENT_CMD_DQ_Q
.. autoattribute:: pymcaf.motor.Motor.VAR_VOLTAGE_DQ_D
.. autoattribute:: pymcaf.motor.Motor.VAR_VOLTAGE_DQ_Q
.. autoattribute:: pymcaf.motor.Motor.VAR_VELOCITY
.. autoattribute:: pymcaf.motor.Motor.VAR_VELOCITY_CMD
.. autoattribute:: pymcaf.motor.Motor.VAR_VELOCITY_REF
