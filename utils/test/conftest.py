import os
from pathlib import Path
import subprocess
import shutil
import logging
from typing import Generator

import pytest
import boto3
from dotenv import load_dotenv
from unittest.mock import MagicMock, patch

from flexpart_ifs_utils import CONFIG

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
    """
    This fixture replaces the regular boto3 client with the mocking library moto.
    The replacement is done by mocking the constant which is used to make sure that a S3 client is reused for calls.
    This replacement is a bit different from the usual way of introducing moto described in
    https://docs.getmoto.org/en/latest/docs/getting_started.html. Doing it this way was caused by problems with the
    MinIO server url which could not be easily overwritten.
    """
    from moto import mock_aws
    with mock_aws():
        session = boto3.Session()
        s3 = session.client('s3')
        s3.create_bucket(Bucket=CONFIG.main.aws.s3.nwp_model_data.name)
        s3.create_bucket(Bucket=CONFIG.main.aws.s3.output.name)
        yield s3

@pytest.fixture(scope="session")
def model_data() -> Path:
    return Path(os.environ['TEST_DATA'])



@pytest.fixture(scope="session")
def resource_dir() -> Path:
    resource: Path = Path(os.path.dirname(os.path.realpath(__file__))) / 'resource'
    return resource


@pytest.fixture(scope="session")
def jinja_template() -> Path:
    jinja_template: Path = Path(os.path.dirname(os.path.realpath(__file__))).parent / 'flexpart_ifs_utils/runtime_configuration.j2'
    return jinja_template

@pytest.fixture(scope="session")
def references() -> Path:
    references: Path = Path(os.path.dirname(os.path.realpath(__file__))) / 'references'
    return references


@pytest.fixture(scope="function")
def mock_config() -> Generator:
    with patch("flexpart_ifs_utils.CONFIG") as mock_config:
        mock_config.main.openmp_config = MagicMock(num_threads=5, stack_size="1000M")
        yield mock_config

WORKDIR: Path = Path(os.path.dirname(os.path.realpath(__file__))) 

def pytest_configure(config):

    # The below functions are required for setting up local tests only.
    load_dotenv(override=True)
    _set_grib_definitions_path()
    _set_local_flexpart_install_prefix()
    _set_local_eccodes_install_prefix()
    _set_local_jobs_dir()
    _set_local_entrypoint()
    _set_local_test_data_path()


def _set_local_flexpart_install_prefix():
    # If running locally, provide a installation path FLEXPART_PREFIX (where Flexpart IFS is installed) in .env
    if not os.getenv('FLEXPART_PREFIX'):

        bin_dir = Path(os.getenv("FLEXPART_PREFIX", '/unset')) / 'bin' / 'FLEXPART'
        if bin_dir.exists():
            print("FLEXPART_PREFIX: %s" % os.getenv("FLEXPART_PREFIX", 'unset'))
        else:
            logging.error("Set FLEXPART_PREFIX in test/.env for local testing.")
            raise RuntimeError("FLEXPART_PREFIX is undefined.")


def _set_local_eccodes_install_prefix():
    try:
        import eccodes
    except RuntimeError as e:
        load_dotenv()
        lib = Path(os.getenv("ECCODES_DIR", '/unset')) / 'lib' / 'libeccodes.so'
        if lib.exists():
            print("ECCODES_DIR: %s" % os.getenv("ECCODES_DIR", 'unset'))
        else:
            logging.error("Set ECCODES_DIR in test/.env for local testing.")
            raise RuntimeError("ECCODES_DIR is undefined.")

def _set_local_jobs_dir():
    if not os.getenv('JOBS_DIR'):
        jobs_dir = WORKDIR / 'jobs'
        os.environ['JOBS_DIR'] = str(jobs_dir)
        print("JOBS_DIR: %s" % os.getenv("JOBS_DIR", 'unset'))

        if not jobs_dir.exists():
            os.makedirs( jobs_dir )
        else:
            shutil.rmtree( jobs_dir )
            os.makedirs( jobs_dir )


def _set_local_entrypoint():
    if not os.getenv('PYTEST_ENTRYPOINT'):
        os.environ['PYTEST_ENTRYPOINT'] = str( WORKDIR.parent.parent / 'entrypoint.sh' )
        print("PYTEST_ENTRYPOINT: %s" % os.getenv("PYTEST_ENTRYPOINT", 'unset'))


def _set_local_test_data_path():
    # If running locally, provide a path for TEST_DATA in .env - the directory will be symlinked to the job dir.
    if os.getenv('TEST_DATA'):
        try:
            src_data_dir = Path(os.getenv('TEST_DATA'))
            contents = os.listdir(src_data_dir)
            if not contents:
                raise FileNotFoundError
        except FileNotFoundError:
            raise FileNotFoundError('The path you provided for environment variable TEST_DATA: %s is empty or does not exist.' % src_data_dir)
        
        print("TEST_DATA: %s" % os.getenv("TEST_DATA", 'unset'))
        dst_data_dir = Path(os.getenv('JOBS_DIR')) / 'data'
        if dst_data_dir.is_symlink():
            os.unlink(dst_data_dir)

        os.symlink(src_data_dir, dst_data_dir)
    else:
        raise RuntimeError('TEST_DATA path is undefined.')

def _set_grib_definitions_path():

    if 'GRIB_DEFINITION_PATH' not in os.environ:

        definitions_dir = WORKDIR / 'resource'

        if not os.path.exists(definitions_dir / 'eccodes'):

            eccodes_dir = f"{WORKDIR / 'eccodes'}"
            
            if os.path.exists(eccodes_dir) and os.path.isdir(eccodes_dir):
                shutil.rmtree(eccodes_dir)

            subprocess.run(["git", "clone", "--depth", "1", "-b", "2.35.1",
                            "git@github.com:ecmwf/eccodes.git", f"{eccodes_dir}"])
            
            # Keep only definitions folder from eccodes
            definitions_src = WORKDIR / 'eccodes'
            definitions_dest = definitions_dir / 'eccodes' / 'definitions'
            shutil.copytree(definitions_src / 'definitions', definitions_dest)
            shutil.rmtree(definitions_src)

        os.environ["GRIB_DEFINITION_PATH"] = f"{definitions_dir / 'eccodes' / 'definitions'}"

    print("GRIB_DEFINITION_PATH: %s" % os.getenv("GRIB_DEFINITION_PATH", 'unset'))



