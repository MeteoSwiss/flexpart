import os
import shutil
from pathlib import Path
from typing import Generator, NoReturn
from unittest.mock import MagicMock, patch

import boto3
import pytest
from dotenv import load_dotenv
from moto import mock_aws

from flexpart_ifs_utils import CONFIG

WORKDIR: Path = Path(os.path.realpath(__file__)).parent
# Found above the tests: the repository root in a checkout, /scratch in the tester image.
_CONTROL_FILE_DIRS = ("options", "options.meteoswiss", "templates")


@pytest.fixture(scope="function")
def aws_credentials():
    """
    Mocked AWS credentials for moto.
    Strictly not necessary, but it's a good safety net if somehow the regular connection is invoked.
    """
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    if os.getenv("AWS_PROFILE"):
        del os.environ["AWS_PROFILE"]


@pytest.fixture(scope="function")
def s3(aws_credentials):
    with mock_aws():
        s3 = boto3.Session().client("s3", region_name="us-east-1")

        s3.create_bucket(Bucket=CONFIG.main.aws.s3.output.name)
        s3.create_bucket(Bucket="test-bucket")
        yield s3


@pytest.fixture(scope="session")
def model_data() -> Path:
    """Real IFS GRIB input (TEST_DATA). Only the end-to-end Flexpart run needs it."""
    path = Path(os.getenv("TEST_DATA", ""))
    if not os.getenv("TEST_DATA") or not path.is_dir() or not any(path.iterdir()):
        _missing(f"TEST_DATA must point to a non-empty directory of model data (got {os.getenv('TEST_DATA')!r}).")
    return path


@pytest.fixture
def sample_files(tmp_path) -> Path:
    """A few small files to move through S3, for tests that care about bytes, not GRIB contents."""
    data_dir = tmp_path / "sample"
    data_dir.mkdir()
    for i in range(3):
        (data_dir / f"dispf-{i}").write_bytes(os.urandom(64))
    return data_dir


@pytest.fixture(scope="session")
def resource_dir() -> Path:
    resource: Path = Path(os.path.dirname(os.path.realpath(__file__))) / "resource"
    return resource


@pytest.fixture(scope="session")
def site_config_file() -> Path:
    # A single site's config as downloaded from the site-config S3 bucket (see
    # dispersionmodelling-deployment/config/flexpart/sites_ifs.yaml). Plain data: it is no longer a
    # Jinja template of the namelist, so there is nothing to render before loading it.
    return Path(os.path.dirname(os.path.realpath(__file__))) / "references/testerhausen_site.yaml"


@pytest.fixture(scope="session")
def reference_forecast_datetime() -> str:
    """The forecast reference the reference namelists were generated from.

    With testerhausen_site.yaml's 3/3/8 hour offsets this yields the simulation and release windows
    in references/Testerhausen/input/{COMMAND,RELEASES}.
    """
    return "202412092100"


@pytest.fixture(scope="session")
def control_files_prefix(tmp_path_factory) -> Path:
    """A stand-in for a Flexpart install prefix holding only the control files prepare_job_directory
    copies in (share/options, share/options.meteoswiss, share/templates) - no bin/FLEXPART.

    They are linked from the source tree: the same directories spack installs under share/ (see
    spack_repo/flexpart/packages/flexpart_ifs/package.py), so preparing a job directory is tested
    without a Flexpart build. Tests that run the model use `flexpart_install` instead.
    """
    source_root = next(
        (d for d in WORKDIR.parents if all((d / name).is_dir() for name in _CONTROL_FILE_DIRS)),
        None,
    )
    if source_root is None:
        pytest.fail(f"No ancestor of {WORKDIR} contains the control file directories {_CONTROL_FILE_DIRS}.")

    prefix = tmp_path_factory.mktemp("flexpart_prefix")
    (prefix / "share").mkdir()
    for name in _CONTROL_FILE_DIRS:
        (prefix / "share" / name).symlink_to(source_root / name, target_is_directory=True)
    return prefix


@pytest.fixture(scope="session")
def templates_dir(control_files_prefix) -> Path:
    """Where the anonymized control-file templates live, same path prepare_job_directory uses."""
    return control_files_prefix / "share" / "templates"


@pytest.fixture(scope="session")
def flexpart_install() -> Path:
    """A real Flexpart installation (FLEXPART_PREFIX with bin/FLEXPART), for tests running the model."""
    prefix = Path(os.getenv("FLEXPART_PREFIX", "/unset"))
    if not (prefix / "bin" / "FLEXPART").exists():
        _missing("Set FLEXPART_PREFIX (e.g. in test/.env) to a Flexpart IFS installation with bin/FLEXPART.")
    return prefix


@pytest.fixture(scope="session")
def jobs_dir(model_data) -> Path:
    """The jobs directory entrypoint.sh works in, with the model data linked in as jobs/data.

    JOBS_DIR when set (the tester image sets it); otherwise a fresh test/jobs.
    """
    if os.getenv("JOBS_DIR"):
        path = Path(os.environ["JOBS_DIR"])
        path.mkdir(parents=True, exist_ok=True)
    else:
        path = WORKDIR / "jobs"
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir()
        os.environ["JOBS_DIR"] = str(path)

    data_link = path / "data"
    if data_link.is_symlink():
        data_link.unlink()
    data_link.symlink_to(model_data)
    return path


@pytest.fixture
def reference_data_end(monkeypatch):
    """End of available model data, as the state machine still supplies it."""
    monkeypatch.setenv("SIMULATION_END_YYYY", "2024")
    monkeypatch.setenv("SIMULATION_END_MM", "12")
    monkeypatch.setenv("SIMULATION_END_DD", "10")
    monkeypatch.setenv("SIMULATION_END_ZZ", "05")


@pytest.fixture(scope="session")
def references() -> Path:
    references: Path = Path(os.path.dirname(os.path.realpath(__file__))) / "references"
    return references


@pytest.fixture(scope="function")
def mock_config() -> Generator:
    with patch("flexpart_ifs_utils.CONFIG") as mock_config:
        mock_config.main.openmp_config = MagicMock(num_threads=5, stack_size="1000M")
        yield mock_config


@pytest.fixture(autouse=True)
def set_entrypoint(monkeypatch):
    if "PYTEST_ENTRYPOINT" not in os.environ:
        entrypoint_script = str(WORKDIR.parent.parent / "entrypoint.sh")
        print("PYTEST_ENTRYPOINT: %s" % entrypoint_script)
        monkeypatch.setenv("PYTEST_ENTRYPOINT", entrypoint_script)


def pytest_configure(config):
    # Local runs can provide FLEXPART_PREFIX, TEST_DATA, ... in test/.env. Nothing is
    # required up front: each test requests the resources it needs through the fixtures above.
    load_dotenv(override=True)


def _missing(reason: str) -> NoReturn:
    """Skip a test whose external resource is unavailable."""
    pytest.skip(reason)
