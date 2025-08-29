
------------------------------------------------
Install dependencies & start the service locally
------------------------------------------------

1. Enter the utils project folder:

.. code-block:: console

    cd utils

2. If running on CSCS, create a blank conda environment with your desired python version and configure poetry to install to this environment, eg.

.. code-block:: console

    poetry config --local virtualenvs.create false
    conda create --prefix ./.conda-env python=3.11
    conda activate ./.conda-env

3. Install packages

.. code-block:: console

    poetry install


------------------------------------------------
Run the tests and quality tools (locally)
------------------------------------------------

1. Enter the utils project folder:

.. code-block:: console

    cd utils

2. Create a .env file in the test folder containing following four variables (paths need changing):

.. code-block::

    FLEXPART_PREFIX=/path/to/flexpart/installation
    TEST_DATA=/path/to/input/test_data


1. Activate conda env (if running at CSCS)

.. code-block:: console

    conda activate ./.conda-env

4. Run tests 

.. code-block:: console

    poetry run pytest


5. Run pylint

.. code-block:: console

    poetry run pylint flexpart_ifs_utils


6. Run mypy

.. code-block:: console

    poetry run mypy flexpart_ifs_utils
