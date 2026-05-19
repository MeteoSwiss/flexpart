import os
import subprocess
import glob
from pathlib import Path

import pytest
from moto.server import ThreadedMotoServer
from unittest import mock
import boto3

from flexpart_ifs_utils import CONFIG
from test.conftest import aws_credentials
from flexpart_ifs_utils.grib_utils import extract_metadata_from_grib_file


@pytest.fixture(autouse=True)
def aws_server_session(aws_credentials):

    _S3_SERVER_HOST = '127.0.0.1'
    _S3_SERVER_PORT = 5555
    server = ThreadedMotoServer(ip_address=_S3_SERVER_HOST, port=_S3_SERVER_PORT)

    with mock.patch.dict(os.environ, {
        "AWS_ENDPOINT_URL": f'http://{_S3_SERVER_HOST}:{_S3_SERVER_PORT}'
    }):
        server.start()
        session = boto3.Session()

        try:
            yield session
        finally:
            server.stop()

@pytest.fixture
def mock_environment(monkeypatch):
    monkeypatch.setenv("EMISSION_START_YYYY", '2024')
    monkeypatch.setenv("EMISSION_START_MM", '12')
    monkeypatch.setenv("EMISSION_START_DD", '10')
    monkeypatch.setenv("EMISSION_START_ZZ", '00')
    monkeypatch.setenv("EMISSION_END_YYYY", '2024')
    monkeypatch.setenv("EMISSION_END_MM", '12')
    monkeypatch.setenv("EMISSION_END_DD", '10')
    monkeypatch.setenv("EMISSION_END_ZZ", '05')
    monkeypatch.setenv("SIMULATION_END_YYYY", '2024')
    monkeypatch.setenv("SIMULATION_END_MM", '12')
    monkeypatch.setenv("SIMULATION_END_DD", '10')
    monkeypatch.setenv("SIMULATION_END_ZZ", '05')
    # Below vars are used in entrypoint.sh
    monkeypatch.setenv("FORECAST_DATETIME", '2024121000')
    monkeypatch.setenv("RELEASE_SITE_NAME", 'BEZ')
    monkeypatch.setenv("MODEL", 'IFS-HRES-Europe')


@pytest.mark.slow
def test_flexpart_run(aws_server_session, mock_environment):

    s3_client = boto3.Session().client('s3')
    s3_client.create_bucket(Bucket=CONFIG.main.aws.s3.output.name)

    process = subprocess.run(f"/bin/bash {os.getenv('PYTEST_ENTRYPOINT')}",
                             shell=True,
                             capture_output=True,
                             text=True,
                             env=os.environ)

    print(process.stdout)
    print(process.stderr)

    expected_msg = "CONGRATULATIONS: YOU HAVE SUCCESSFULLY COMPLETED A FLEXPART MODEL RUN!"

    assert process.returncode == 0
    assert expected_msg in process.stdout

    jobs_dir = Path(os.environ['JOBS_DIR'])

    # assert that NETCDF output files were produced
    path_list = [Path(f) for f in glob.iglob(str(jobs_dir)+'/*/output/*', recursive=True) if os.path.isfile(f) and Path(f).suffix == '.nc']
    assert len(path_list) > 0

    md = extract_metadata_from_grib_file(
        next((jobs_dir/'data').iterdir())
    )

    # assert that output files are uploaded to S3 (moto3)
    in_mem_client = boto3.client("s3")
    for path in path_list:
        key = f"{md.date}_{md.time[:2]}/{os.getenv('RELEASE_SITE_NAME')}/{path.name}"
        actual = in_mem_client.get_object(Bucket = CONFIG.main.aws.s3.output.name, Key = key)["Body"].read()
        with open(path, mode='rb') as f:
            assert actual == f.read()
