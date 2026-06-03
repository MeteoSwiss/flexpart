import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import pytest

from flexpart_ifs_utils import CONFIG
from flexpart_ifs_utils.config.service_settings import Bucket
from flexpart_ifs_utils.grib_utils import extract_metadata_from_grib_file
from flexpart_ifs_utils.s3_utils import (download_keys_from_bucket,
                                         list_objs_in_bucket,
                                         upload_output)


def test_list_objs_in_bucket(s3, model_data: Path):

    bucket = CONFIG.main.aws.s3.nwp_model_data

    params = {'date': '20241210', 'time': '0000', 'model': 'IFS-HRES'}

    path_list = list(model_data.iterdir())[:3]

    for i, path in enumerate(path_list):
        _add_item_to_bucket_with_metadata(bucket, s3, str(path), str(path), step=i, domain='GLOBAL', **params)
        _add_item_to_bucket_with_metadata(bucket, s3, str(path), f"{path}_c", domain='EUROPE', step=i, **params)

    result = list_objs_in_bucket(
        start_time=datetime.strptime("20241210_0000", "%Y%m%d_%H%M"),
        end_time=datetime.strptime("20241210_0000", "%Y%m%d_%H%M") + timedelta(hours=3),
        bucket = bucket
    )

    # Validate the results
    assert len(result) == 2*len(path_list)
    assert {k for k in result} == {str(path) for path in path_list} | {f"{path}_c" for path in path_list}


def test_download_keys_from_bucket(s3, model_data: Path):
    # Configure the bucket dynamically
    bucket = CONFIG.main.aws.s3.nwp_model_data

    # Add some files to the mocked bucket
    path_list = list(model_data.iterdir())[4:7]
    _add_files_to_bucket(bucket, path_list, s3)

    # Use a temporary directory to download files
    with tempfile.TemporaryDirectory() as tmpdirname:
        download_keys_from_bucket([str(f.name) for f in path_list], Path(tmpdirname), bucket)

        # Verify that all files are downloaded
        files_downloaded = [f.name for f in Path(tmpdirname).iterdir()]
        assert len(path_list) == len(files_downloaded)
        for file in path_list:
            assert file.name in files_downloaded


def test_upload_output(s3, model_data: Path):

    # given
    bucket = CONFIG.main.aws.s3.output
    site = 'ABC'
    datetime = '2024060712'

    # when
    upload_output(model_data, site, datetime, bucket)

    # then
    assert 'Contents' in s3.list_objects(Bucket = bucket.name)

    for path in model_data.iterdir():

        # check the files were uploaded as expected
        actual = s3.get_object(Bucket = bucket.name, Key = f"20240607_12/{site}/{path.name}")["Body"].read()
        with open(path, mode='rb') as f:
            assert actual == f.read()

def _add_files_to_bucket(bucket: Bucket, files: list[Path], s3) -> None:

    for path in files:
        s3.upload_file(path, bucket.name, path.name)


def _add_item_to_bucket_with_metadata(bucket: Bucket,
                       s3_client,
                       path: str,
                       key: str,
                       time: str = '1200',
                       date: str = '20240607',
                       step: int = 1,
                       model: str = "IFS-HRES",
                       domain: str = "GLOBAL") -> None:

    with open(path, "rb") as f:
        s3_client.put_object(
            Bucket=bucket.name,
            Key=path if key is None else key,
            Body=f,
            Metadata={
                "data": json.dumps({
                    "time": time,
                    "date": date,
                    "step": str(step),
                    "model": model,
                    "domain": domain,
                }),
            },
        )
