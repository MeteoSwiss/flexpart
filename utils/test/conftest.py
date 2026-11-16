import hashlib
import logging
import os
import shutil
import subprocess
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
# The spack environment the image builds Flexpart with, and what that build reads from the checkout.
_SPACK_ENV = "spack_env"
_BUILD_INPUTS = ("src", "options", "options.meteoswiss", "templates", "pathnames", "spack_repo", f"{_SPACK_ENV}/spack.yaml")
# Install root of the image build (Dockerfile) that fills the build cache (test/spack/mirrors.yaml).
_BUILD_CACHE_ROOT = "/opt/spack-root"


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
    # The moto server runs on 127.0.0.1: keep requests to it away from any HTTP proxy configured in the
    # shell, which would otherwise route (and slow down, or hang) them.
    for var in ("NO_PROXY", "no_proxy"):
        hosts = [h for h in os.environ.get(var, "").split(",") if h]
        if "127.0.0.1" not in hosts:
            os.environ[var] = ",".join(hosts + ["127.0.0.1"])


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
    # Absolute: a relative path (from the working directory) would break the symlink jobs_dir makes to it.
    return path.absolute()


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
def flexpart_install(pytestconfig) -> Path:
    """A real Flexpart installation (FLEXPART_PREFIX with bin/FLEXPART), for tests running the model.

    FLEXPART_PREFIX when set (the image sets it). Otherwise Flexpart is built from this checkout with the
    image's spack environment (spack_env) under spack-root/, the dependencies coming from the build cache.
    The build is reused until the Flexpart sources change.
    """
    source_root = next((d for d in WORKDIR.parents if (d / _SPACK_ENV / "spack.yaml").is_file()), None)
    given = Path(os.environ["FLEXPART_PREFIX"]).absolute() if os.getenv("FLEXPART_PREFIX") else None
    # spack_env's own view in the checkout (spack-view) is treated like no prefix: built and kept up to date.
    if given and not (source_root and given == (source_root / "spack-view").absolute()):
        if not (given / "bin" / "FLEXPART").exists():
            pytest.fail(f"FLEXPART_PREFIX={given} has no bin/FLEXPART.")
        return given
    if source_root is None:
        _missing(f"Set FLEXPART_PREFIX: no {_SPACK_ENV}/spack.yaml above {WORKDIR} to build Flexpart from.")

    prefix = _build_flexpart(pytestconfig, source_root)
    os.environ["FLEXPART_PREFIX"] = str(prefix)
    # Like the image: the Python side decodes GRIB with the ecCodes Flexpart was built against.
    os.environ["ECCODES_DIR"] = str(prefix)
    os.environ["FINDLIBS_DISABLE_PACKAGE"] = "yes"
    os.environ["FINDLIBS_DISABLE_PYTHON"] = "yes"
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
    # The app's logging config puts everything at INFO; silence the per-request chatter of boto and
    # the moto server (werkzeug) so failures show the application's own logs.
    for name in ("botocore", "boto3", "urllib3", "werkzeug"):
        logging.getLogger(name).setLevel(logging.WARNING)
    # Local runs can provide FLEXPART_PREFIX, TEST_DATA, ... in test/.env. Nothing is
    # required up front: each test requests the resources it needs through the fixtures above.
    load_dotenv(override=True)


def _missing(reason: str) -> NoReturn:
    """Skip a test whose external resource is unavailable."""
    pytest.skip(reason)


def _build_flexpart(pytestconfig, source_root: Path) -> Path:
    """Build Flexpart with spack_env if its sources changed since the last build, and return the view.

    Built from a copy of the sources, as in the image (Dockerfile): spack writes into the environment and
    the develop sources it builds (spack.lock, detected compilers, the package's Makefile edit, stage
    links), and that should not happen to the checkout. Everything lives under the git-ignored spack-root/.
    """
    spack = shutil.which("spack") or (os.getenv("SPACK_ROOT") and str(Path(os.environ["SPACK_ROOT"]) / "bin" / "spack"))
    if not spack or not Path(spack).exists():
        _missing("Set FLEXPART_PREFIX, or put spack on PATH to build Flexpart for the tests.")

    work = source_root / "spack-root"
    build = work / "build"  # the copied sources, laid out as in the image; spack-view ends up in here
    view = build / "spack-view"
    stamp = work / "sources.sha256"
    install_root = _short_install_root(source_root, work / "install")

    sources = _build_sources(source_root)
    fingerprint = _fingerprint(source_root, sources)
    if (view / "bin" / "FLEXPART").exists() and stamp.is_file() and stamp.read_text() == fingerprint:
        return view

    # A fresh copy each time: spack rebuilds a develop package whenever its sources are newer than the
    # install anyway, and this only runs when they changed.
    shutil.rmtree(build, ignore_errors=True)
    for name in sources:
        (build / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / name, build / name)

    spack_cmd = [
        spack,
        "-C", str(WORKDIR / "spack"),
        "-c", f"config:install_tree:root:{install_root}",
        "-e", str(build / _SPACK_ENV),
    ]
    capture = pytestconfig.pluginmanager.getplugin("capturemanager")
    with capture.global_and_fixture_disabled():
        print(f"\nBuilding Flexpart with spack into {view} (reused until the sources change) ...", flush=True)
        for args in (["concretize", "--force"], ["install", "--fail-fast"]):
            if subprocess.run(spack_cmd + args, cwd=build).returncode != 0:
                pytest.fail(f"'spack {' '.join(args)}' failed for {build / _SPACK_ENV}, see the output above.")
    stamp.write_text(fingerprint)
    return view


def _short_install_root(source_root: Path, store: Path) -> Path:
    """A symlink to `store` whose path is no longer than the one the build cache was built under.

    The cached binaries hard-code their /opt/spack-root prefix and spack can only relocate them to a path
    of at most that length, which the checkout's spack-root is not. spack keeps the symlinked path as the
    install root, so the files stay in the checkout; the link is recreated whenever /tmp was cleared.
    """
    store.mkdir(parents=True, exist_ok=True)
    link = Path(f"/tmp/fp-{hashlib.sha256(str(source_root).encode()).hexdigest()[:6]}")
    assert len(str(link)) <= len(_BUILD_CACHE_ROOT), f"{link} is longer than {_BUILD_CACHE_ROOT}"
    if not (link.is_symlink() and Path(os.readlink(link)) == store):
        if link.is_symlink():
            link.unlink()
        link.symlink_to(store, target_is_directory=True)
    return link


def _build_sources(source_root: Path) -> list[str]:
    """The files the Flexpart build uses, relative to the checkout: tracked and untracked, without
    git-ignored build output."""
    files = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *_BUILD_INPUTS],
        cwd=source_root, capture_output=True, check=True,
    ).stdout.decode().split("\0")
    return sorted(name for name in set(files) if name and (source_root / name).is_file())


def _fingerprint(source_root: Path, sources: list[str]) -> str:
    digest = hashlib.sha256()
    for name in sources:
        digest.update(name.encode() + b"\0" + (source_root / name).read_bytes() + b"\0")
    return digest.hexdigest()
