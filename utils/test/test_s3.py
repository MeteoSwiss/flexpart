import tempfile
from pathlib import Path

import boto3
import pytest

from flexpart_ifs_utils.s3_utils import (
    list_objs_in_bucket_via_dynamodb,
    download_keys_from_bucket,
    upload_directory)
from flexpart_ifs_utils import CONFIG
from flexpart_ifs_utils.config.service_settings import Bucket, DBTable
from flexpart_ifs_utils.grib_utils import extract_metadata_from_grib_file

from test.conftest import s3, model_data, aws_credentials

@pytest.fixture(scope="function")
def db(aws_credentials):
    from moto import mock_aws
    with mock_aws():
        session = boto3.Session()
        db = session.client('dynamodb', region_name=CONFIG.main.aws.db_table.region)

        db.create_table(
            TableName=CONFIG.main.aws.db_table.name,
            KeySchema=[
                {
                    'AttributeName': 'ObjectKey',
                    'KeyType': 'HASH'
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'ObjectKey',
                    'AttributeType': 'S'
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        yield db


def test_list_objs_in_bucket(db, model_data: Path):
    """
    Test for listing objects in the bucket via DynamoDB.
    """

    # Get the table configuration
    table_config = CONFIG.main.aws.db_table

    params = {'date': '20241210', 'time': '0000', 'model': 'IFS-HRES'}

    path_list = list(model_data.iterdir())[:3]

    # Add items to the DynamoDB mock table
    for i, path in enumerate(path_list):
        _add_item_to_table(table_config, db, str(path), step=i, domain='GLOBAL', **params)
        _add_item_to_table(table_config, db, f"{path}_c", domain='EUROPE', step=i, **params)

    result = list_objs_in_bucket_via_dynamodb(table_config, **params)

    # Validate the results
    assert len(result) == 2*len(path_list)
    assert {k for k in result.keys()} == {str(path) for path in path_list} | {f"{path}_c" for path in path_list}


import tempfile
from pathlib import Path

@pytest.mark.parametrize("s3", [
    ("aws", None),
], indirect=True)
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

@pytest.mark.parametrize("s3", [
    ("aws", None),
], indirect=True)
def test_upload_directory(s3, model_data: Path):

    # given
    bucket = CONFIG.main.aws.s3.output
    site = 'ABC'

    # when
    upload_directory(model_data, model_data, site, bucket)

    # then
    assert 'Contents' in s3.list_objects(Bucket = bucket.name)

    md = extract_metadata_from_grib_file(Path(next(model_data.iterdir())))

    for path in model_data.iterdir():

        # check the files were uploaded as expected
        actual = s3.get_object(Bucket = bucket.name, Key = f"{md.date}_{md.time[:2]}/{site}/{path.name}")["Body"].read()
        with open(path, mode='rb') as f:
            assert actual == f.read()

def _add_files_to_bucket(bucket: Bucket, files: list[Path], s3) -> None:

    for path in files:
        s3.upload_file(path, bucket.name, path.name)


def _add_item_to_table(dbtable: DBTable,
                       dynamodb,
                       path: str,
                       time: str = '1200',
                       date: str = '20240607',
                       step: int = 1,
                       model: str = "IFS-HRES",
                       domain: str = "GLOBAL") -> None:

    dynamodb.put_item(
        TableName=dbtable.name,
        Item={
            "ObjectKey": {"S": path},
            "ForecastDate": {"S": date},
            "Step": {"N": str(step)},
            "ForecastTime": {"S": time},
            "Model": {"S": model},
            "DomainName": {"S": domain},
        })
