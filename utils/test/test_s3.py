import tempfile
from pathlib import Path

import boto3
import pytest
import sqlite3

from flexpart_ifs_utils.s3_utils import (
    list_objs_in_bucket_via_dynamodb,
    list_objs_in_bucket_via_sqlite,
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
        db = session.client('dynamodb', region_name= CONFIG.main.aws.db.nwp_model_data.region)
        
        db.create_table(
            TableName=CONFIG.main.aws.db.nwp_model_data.name,
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

@pytest.fixture(scope="function")
def sqlite_db():
    connection = sqlite3.connect("file::memory:?cache=shared")
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE uploaded (
        key TEXT PRIMARY KEY,
        forecast_ref_time TEXT,
        step INTEGER
    )
    """)

    yield connection

    connection.close()


@pytest.mark.parametrize("backend_type", ["dynamodb", "sqlite"])
def test_list_objs_in_bucket(backend_type, db, sqlite_db, model_data: Path):
    """
    Test for listing objects in the bucket using different backends (DynamoDB or SQLite).
    """

    # Get the table configuration
    table_config = CONFIG.main.aws.db.nwp_model_data
    table_name = table_config.name

    # Set backend type dynamically
    table_config.backend_type = backend_type

    params = {'date': '20241210', 'time': '0000'}
    forecast_ref_time = '2024-12-10 00:00:00'

    some_files = list(model_data.iterdir())[:3]

    # Handle each backend type separately
    if backend_type == "dynamodb":
        # Add items to the DynamoDB mock table
        for i, path in enumerate(some_files):
            _add_item_to_table(table_config, db, str(path), step=i, **params)
        # Use the DynamoDB list function
        result = list_objs_in_bucket_via_dynamodb(table_config, **params)

    elif backend_type == "sqlite":
        # Add items to the SQLite mock database
        # Unpack the connection and table name from the fixture
        connection = sqlite_db
        table_config.name = "file::memory:?cache=shared"
        for i, path in enumerate(some_files):
            sqlite_db.execute("""
            INSERT INTO uploaded (key, forecast_ref_time, step)
            VALUES (?, ?, ?)
            """, (str(path), forecast_ref_time, i))
        connection.commit()

        # Use the SQLite list function
        result = list_objs_in_bucket_via_sqlite(table_config, **params)

    else:
        raise ValueError(f"Unsupported backend_type: {backend_type}")

    # Validate the results
    assert len(result) == len(some_files)
    assert {k for k in result.keys()} == {str(path) for path in some_files}



import tempfile
from pathlib import Path

@pytest.mark.parametrize("s3", [
    ("aws", None),
], indirect=True)
def test_download_keys_from_bucket(s3, model_data: Path):
    # Configure the bucket dynamically
    bucket = CONFIG.main.aws.s3.nwp_model_data

    # Add some files to the mocked bucket
    some_files = list(model_data.iterdir())[4:7]
    _add_files_to_bucket(bucket, some_files, s3)

    # Use a temporary directory to download files
    with tempfile.TemporaryDirectory() as tmpdirname:
        download_keys_from_bucket([str(f.name) for f in some_files], Path(tmpdirname), bucket)

        # Verify that all files are downloaded
        files_downloaded = [f.name for f in Path(tmpdirname).iterdir()]
        assert len(some_files) == len(files_downloaded)
        for file in some_files:
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
                        step: int = 1) -> None:

    dynamodb.put_item(
        TableName=dbtable.name,
        Item={
            "ObjectKey": {"S": path},
            "ForecastDate": {"S": date},
            "Step": {"N": str(step)},
            "ForecastTime": {"S": time},
        })
