Installation
============

Requirements
------------

- Python 3.10 -- 3.12
- A Microchip MCAF motor control project with X2Cscope enabled
- The compiled ELF file with debug symbols
- A ``parameters.json`` file from motorBench (for unit conversion)

From PyPI
---------

.. code-block:: bash

   pip install pymcaf

From source (editable)
----------------------

Clone the repository and install in editable mode:

.. code-block:: bash

   git clone https://github.com/microchip/pyx2ctune.git
   cd pyx2ctune
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -e packages/pymcaf

Optional: build the documentation locally
------------------------------------------

.. code-block:: bash

   pip install -e "packages/pymcaf[docs]"
   cd packages/pymcaf/docs
   make html
   # open _build/html/index.html
