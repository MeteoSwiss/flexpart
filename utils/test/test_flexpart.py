import glob
import os
import subprocess
from pathlib import Path
from unittest import mock

import boto3
import pytest
from moto.server import ThreadedMotoServer

from flexpart_ifs_utils import CONFIG
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
    monkeypatch.setenv("RELEASE_SITE_NAME", 'Testerhausen')
    monkeypatch.setenv("MODEL", 'IFS-Europe')


# The Testerhausen site block Terraform would upload to `sites/Testerhausen.yaml` in the site-config bucket -
# see dispersionmodelling-deployment/config/flexpart/sites_ifs.yaml. Date placeholders are still
# unrendered Jinja, exactly as the app downloads it: rendering happens locally after download.
TESTERHAUSEN_SITE_CONFIG = """
name: Testerhausen
command:
  LDIRECT: 1
  IBDATE: "{{ data.EMISSION_START_YYYY }}{{ data.EMISSION_START_MM }}{{ data.EMISSION_START_DD }}"
  IBTIME: "{{ data.EMISSION_START_ZZ }}0000"
  IEDATE: "{{ data.SIMULATION_END_YYYY }}{{ data.SIMULATION_END_MM }}{{ data.SIMULATION_END_DD }}"
  IETIME: "{{ data.SIMULATION_END_ZZ }}0000"
  LOUTSTEP: 10800
releases:
  NSPEC: 1
  SPECNUM_REL: 16
  IDATE1: "{{ data.EMISSION_START_YYYY }}{{ data.EMISSION_START_MM }}{{ data.EMISSION_START_DD }}"
  ITIME1: "{{ data.EMISSION_START_ZZ }}0000"
  IDATE2: "{{ data.EMISSION_END_YYYY }}{{ data.EMISSION_END_MM }}{{ data.EMISSION_END_DD }}"
  ITIME2: "{{ data.EMISSION_END_ZZ }}0000"
  LON1: 8.2284
  LAT1: 47.5519
  Z1: 100
  ZKIND: 1
  MASS: "2.8800E10"
  COMMENT: Testerhausen
"""


@pytest.mark.slow
def test_flexpart_run(aws_server_session, mock_environment):

    s3_client = boto3.Session().client('s3')
    s3_client.create_bucket(Bucket=CONFIG.main.aws.s3.output.name)
    s3_client.create_bucket(Bucket=CONFIG.main.aws.s3.site_config.name)
    s3_client.put_object(
        Bucket=CONFIG.main.aws.s3.site_config.name,
        Key=f"{CONFIG.main.runtime_config.site_config_key_prefix}Testerhausen.yaml",
        Body=TESTERHAUSEN_SITE_CONFIG.encode("utf-8"),
    )

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
