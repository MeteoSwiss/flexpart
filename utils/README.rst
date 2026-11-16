
------------------------------------------------
Install dependencies & start the service locally
------------------------------------------------

1. Install spack packages

.. code-block:: console

    spack env activate spack_env
    spack install

2. Enter the utils project folder:

.. code-block:: console

    cd utils

3. If running on CSCS, create a blank conda environment with your desired python version and configure poetry to install to this environment, eg.

.. code-block:: console

    poetry config --local virtualenvs.create false
    conda create --prefix ./.conda-env python=3.13
    conda activate ./.conda-env

4. Install packages

.. code-block:: console

    poetry install


------------------------------------------------
Run the tests and quality tools (locally)
------------------------------------------------

1. Enter the utils project folder:

.. code-block:: console

    cd utils

2. Create a ``.env`` file in the test folder with the settings for the end-to-end Flexpart run
   (``test/test_flexpart.py``). Relative paths are relative to ``utils/``. All other tests run without it.

.. code-block::

    # IFS GRIB input for the end-to-end run (dispf2024121000 ... dispf2024121005).
    TEST_DATA=test_data

    # Optional: a Flexpart IFS installation (with bin/FLEXPART) to run instead of building one.
    # FLEXPART_PREFIX=/path/to/flexpart-ifs/installation

    # Optional: where the end-to-end run writes its job directory (default: test/jobs).
    # JOBS_DIR=/path/to/jobs

3. Make sure ``spack`` is on your ``PATH`` (see the `Spack installation instructions
   <https://spack.readthedocs.io/en/latest/getting_started.html>`_), unless you set ``FLEXPART_PREFIX``.

   Without ``FLEXPART_PREFIX``, the end-to-end test builds Flexpart from this checkout itself, with the
   same spack environment as the image (``spack_env``). The dependencies are installed from the
   MeteoSwiss spack build cache in Nexus (``test/spack/mirrors.yaml``, read-only, no credentials needed),
   so the first build takes about a minute. The build is kept under ``spack-root/`` and reused until the
   Flexpart sources (``src``, ``options``, ``options.meteoswiss``, ``templates``, ``pathnames``,
   ``spack_repo``, ``spack_env/spack.yaml``) change. It is built from a copy of those, so spack never
   modifies the checkout.

   To use another Flexpart binary instead, set ``FLEXPART_PREFIX`` in ``test/.env`` to an installation
   containing ``bin/FLEXPART``; nothing is built then.

   Without spack on the ``PATH`` and without ``FLEXPART_PREFIX``, the end-to-end test is skipped, with the
   reason shown in the pytest summary.

4. Activate conda env (if running at CSCS)

.. code-block:: console

    conda activate ./.conda-env

5. Run tests. A spack build always shows its progress. Add ``-s`` to also see the end-to-end run's own
   output (``entrypoint.sh`` and Flexpart) as it happens; without it, that output is only shown when the
   test fails.

.. code-block:: console

    poetry run pytest
    poetry run pytest -s test/test_flexpart.py

6. Run pylint

.. code-block:: console

    poetry run pylint flexpart_ifs_utils


7. Run mypy

.. code-block:: console

    poetry run mypy flexpart_ifs_utils
