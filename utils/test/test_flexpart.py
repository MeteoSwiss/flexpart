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
def mock_s3_endpoint(aws_credentials):
    s3_endpoint = "http://localhost:5000"
    with mock.patch.dict(os.environ, {
        "AWS_ENDPOINT_URL": s3_endpoint,
        "MAIN__AWS__S3__OUTPUT__ENDPOINT_URL": s3_endpoint
    }):
        server = ThreadedMotoServer()
        server.start()
        yield s3_endpoint
    server.stop()


@pytest.fixture
def mock_environment(monkeypatch):
    monkeypatch.setenv("IBDATE", '20241210')
    monkeypatch.setenv("IBTIME", '00')
    monkeypatch.setenv("IEDATE", '20241210')
    monkeypatch.setenv("IETIME", '05')
    # Below vars are used in entrypoint.sh
    monkeypatch.setenv("FORECAST_DATETIME", '2024121000')
    monkeypatch.setenv("RELEASE_SITE_NAME", 'BEZ')


@pytest.mark.slow
def test_flexpart_run(mock_s3_endpoint, mock_environment):

    s3_client = boto3.Session().client('s3', endpoint_url=mock_s3_endpoint)
    s3_client.create_bucket(Bucket=CONFIG.main.aws.s3.output.name)

    entrypoint = os.getenv('PYTEST_ENTRYPOINT')

    process = subprocess.run(f"/bin/bash {entrypoint}", shell=True, capture_output=True, text=True)

    stdout = process.stdout
    
    print(stdout)

    expected_msg = "CONGRATULATIONS: YOU HAVE SUCCESSFULLY COMPLETED A FLEXPART MODEL RUN!"

    assert process.returncode == 0
    assert expected_msg in stdout
    
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