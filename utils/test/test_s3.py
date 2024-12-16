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
        db = session.client('dynamodb', region_name=CONFIG.main.aws.db.nwp_model_data.region)
        
        db.create_table(
            TableName=CONFIG.main.aws.db.nwp_model_data.name,
            KeySchema=[
                {
                    'AttributeName': 'ObjectKey',
                    'KeyType': 'HASH'
                },
                {
                    'AttributeName': 'EnsembleNumber',
                    'KeyType': 'RANGE'
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'ObjectKey',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'EnsembleNumber',
                    'AttributeType': 'N'
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        yield db


def test_list_objs_in_bucket_db(db, model_data: Path):

    table = CONFIG.main.aws.db.nwp_model_data

    params = {'date': '20010101',
              'time': '1800',
              'model': 'TEST'}

    some_files = list(model_data.iterdir())[:3]

    for i, path in enumerate(some_files):
        _add_item_to_table(table, db, str(path), step=i, number=1, **params)
    for i, path in enumerate(some_files):
        _add_item_to_table(table, db, str(path)+'1', step=i, number=2, **params)

    result_1 = list_objs_in_bucket_via_dynamodb(table, **params)

    assert len(result_1) == len(some_files)
    assert {k for k in result_1.keys()} == {str(path) for path in some_files}

def test_download_keys_from_bucket(s3, model_data: Path):
    
    bucket = CONFIG.main.aws.s3.nwp_model_data

    some_files: list[Path] = list(model_data.iterdir())[4:7]
    _add_files_to_bucket(bucket, some_files, s3)

    with tempfile.TemporaryDirectory() as tmpdirname:
        download_keys_from_bucket([str(f.name) for f in some_files], Path(tmpdirname), bucket)

        files_downloaded = [f.name for f in Path(tmpdirname).iterdir()]

        for file in some_files:
            assert file.name in files_downloaded

        assert len(some_files) == len(files_downloaded)


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
        actual = s3.get_object(Bucket = bucket.name, Key = f"{md.model}/{md.date}_{md.time}/{site}/{md.number:03}/{path.name}")["Body"].read()
        with open(path, mode='rb') as f:
            assert actual == f.read()

def _add_files_to_bucket(bucket: Bucket, files: list[Path], s3) -> None:

    for path in files:
        s3.upload_file(path, bucket.name, path.name)


def _add_item_to_table(dbtable: DBTable,
                       dynamodb,
                        path: str, 
                        model: str = 'TEST',
                        time: str = '1200',
                        date: str = '20240607',
                        number: int = 1,
                        step: int = 1) -> None:

    dynamodb.put_item(
        TableName=dbtable.name,
        Item={
            "ObjectKey": {"S": path},
            "EnsembleNumber": {"N": str(number)},
            "ForecastDate": {"S": date},
            "Step": {"N": str(step)},
            "ForecastTime": {"S": time},
            "Model": {"S": model},
        })