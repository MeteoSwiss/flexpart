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
    # port=0 lets the OS assign a free ephemeral port, avoiding collisions when tests from
    # multiple repos/runs share this machine.
    server = ThreadedMotoServer(ip_address=_S3_SERVER_HOST, port=0)
    server.start()
    host, port = server.get_host_and_port()

    with mock.patch.dict(os.environ, {
        "AWS_ENDPOINT_URL": f'http://{host}:{port}'
    }):
        session = boto3.Session()

        try:
            yield session
        finally:
            server.stop()

@pytest.fixture
def mock_environment(monkeypatch):
    # End of the available model data. The eight EMISSION_* variables that used to accompany this are
    # no longer read: the release window comes from the site's own offsets.
    monkeypatch.setenv("SIMULATION_END_YYYY", '2024')
    monkeypatch.setenv("SIMULATION_END_MM", '12')
    monkeypatch.setenv("SIMULATION_END_DD", '10')
    monkeypatch.setenv("SIMULATION_END_ZZ", '05')
    # Below vars are used in entrypoint.sh. FORECAST_DATETIME is YYYYMMDDhhmm, as the run scheduler
    # builds it from forecast_date + forecast_time; it has to stay aligned with the reference time of
    # the GRIB in TEST_DATA, because the upload key is derived from it.
    monkeypatch.setenv("FORECAST_DATETIME", '202412100000')
    monkeypatch.setenv("RELEASE_SITE_NAME", 'Testerhausen')
    monkeypatch.setenv("MODEL", 'IFS-Europe')


# The Testerhausen site object Terraform would upload to `sites/Testerhausen.yaml` in the site-config
# bucket - see dispersionmodelling-deployment/config/flexpart/sites_ifs.yaml. Plain data: no Jinja and
# no dates, so there is nothing to render after download. The offsets resolve against
# FORECAST_DATETIME to the 00:00-05:00 window the GRIB in TEST_DATA covers; the byte-level check
# against the reference namelists lives in test_prepare.py.
TESTERHAUSEN_SITE_CONFIG = """
name: Testerhausen
latitude: 47.5519
longitude: 8.2284
height_m: 100
height_reference: agl
species: 16
mass_bq: 2.8800e+10
output_interval_s: 10800
direction: forward
comment: Testerhausen
simulation_start_offset_h: 0
release_start_offset_h: 0
release_end_offset_h: 5
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

    # The concentration grid carries no simulation-start stamp, so nothing downstream has to
    # re-derive the release offset to address it.
    assert 'grid_conc.nc' in [path.name for path in path_list]

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
