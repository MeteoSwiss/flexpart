import logging
import os
from pathlib import Path
import glob
from datetime import datetime as dt

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


from flexpart_ifs_utils.config.service_settings import Bucket, DBTable
from flexpart_ifs_utils import CONFIG
from flexpart_ifs_utils.grib_utils import extract_metadata_from_grib_file, _is_grib_file, RunMetadata, GribMetadata

import sqlite3

_logger = logging.getLogger(__name__)

def get_s3_resource(endpoint_url, access_key, secret_key):
    """Get a boto3 S3 resource."""
    return boto3.resource(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )

def upload_directory(directory: Path,
                     input_path: Path,
                     site: str,
                     bucket: Bucket = CONFIG.main.aws.s3.output,
                     parent: str | None = None) -> None:
    """
    Uploads the contents of a specified directory to an S3 bucket.

    This function verifies the existence of the provided directories, 
    extracts metadata from the Flexpart input directory, and uploads files from the 
    specified directory to the provided S3 bucket, with metadata attached. 
    If a parent directory is specified, only files within that parent directory are uploaded.

    Args:
        directory (Path): The directory containing files to upload.
        input_path (Path): The directory containing input data from which metadata is extracted.
        site (str): The (3 letter) short name of the release site that was simulated by Flexpart.
        bucket (Bucket, optional): The S3 bucket where files will be uploaded. 
            Defaults to CONFIG.main.aws.s3.output.
        parent (str, optional): The name of the parent directory. 
            If specified, only files within this parent directory are uploaded. Defaults to None.

    Raises:
        RuntimeError: If the specified directory does not exist or if 
            the input directory for metadata extraction does not exist.
        Exception: If any other error occurs during the upload process.
    """

    # Verify directory exists
    if not directory.is_dir():
        _logger.error("Directory is empty, cannot upload: %s ", directory)
        raise RuntimeError("Directory provided to upload does not exist.")

    # Verify directory contains input data from which metadata is extracted
    if not input_path.is_dir():
        _logger.error("Directory provided to Flexpart input data (used to obtain metadata) does not exist: %s ", input_path)
        raise RuntimeError(f"Directory provided to Flexpart input data {input_path} (used to obtain metadata) does not exist.")

    try:
        md = _get_input_metadata(input_path)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"No GRIB files found in the Flexpart input directory: {input_path}, cannot extract metadata."
            ) from e

    try:
        client = _create_s3_client(bucket)

        path_list = [Path(f) for f in glob.iglob(f"{directory}/**", recursive=True) if os.path.isfile(f)]

        if parent:
            path_list = [f for f in path_list if f.parent.name == parent]

        for path in path_list:
            key = f"{md.date}_{md.time}/{site}/{path.name}"
            try:
                _logger.info("Uploading file: %s to bucket: %s with key: %s", path, bucket.name, key)
                with open(path, "rb") as data:
                    client.upload_fileobj(
                        data,
                        bucket.name,
                        key,
                        ExtraArgs={"Metadata": {k:str(v) for k,v in md.model_dump().items()}})
            except ClientError as e:
                _logger.error(e)
                raise e
    except Exception as err:
        _logger.error('Error uploading directory to S3.')
        raise err


def _get_input_metadata(directory: Path) -> RunMetadata:
    """Find the first GRIB file in the specified directory and extract its metadata."""

    for file in directory.rglob('*'):
        if file.is_file():
            if _is_grib_file(file):
                md = extract_metadata_from_grib_file(file)
                # Ignore step because we are only interested in the forecast for which Flexpart was run.
                return RunMetadata(date=md.date, time=md.time)

    raise FileNotFoundError("No GRIB files found in the directory.")


def list_objs_in_bucket_via_dynamodb(table: DBTable,
                                     date: str,
                                     time: str) -> dict[str, GribMetadata]:
    """
    List objects in a DynamoDB table using the scan method with filter on the metadata.

    Args:
        table (DBTable): The DynamoDB table object.
        date (str | None): Forecast date.
        time (str | None): Forecast time.

    Returns:
        Dict[str, Any]: A dictionary of matching objects from the table, where key is the object key and value is the object metadata.
    """

    _logger.info("Fetching objects from table with the following metadata: date: %s, time: %s", date, time)

    dynamodb = boto3.resource("dynamodb", region_name=table.region)

    filter_expression = (
                         " ForecastDate = :forecastdate AND"
                         " ForecastTime = :forecasttime")

    expression_attributes_values = {
        ":forecastdate": date,
        ":forecasttime": time,
    }

    dynamo_db_table = dynamodb.Table(table.name)
    items = []

    scan_parameters = {
        "FilterExpression": filter_expression,
        "ExpressionAttributeValues": expression_attributes_values,
    }

    response = dynamo_db_table.scan(**scan_parameters)

    items.extend(response.get("Items", []))

    # Handle pagination manually for scan
    while "LastEvaluatedKey" in response:
        response = dynamo_db_table.scan(
            **scan_parameters,
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response.get("Items", []))

    matching_objects = {
        item.get('ObjectKey'): GribMetadata(
            time = item.get('ForecastTime'),
            date = item.get('ForecastDate'),
            step = item.get('Step'))
         for item in items}

    _logger.info("S3 objects matching search: %s", matching_objects.keys())

    return matching_objects

def list_objs_in_bucket_via_sqlite(table: DBTable,
                                    date: str,
                                    time: str) -> dict[str, GribMetadata]:

    conn = sqlite3.connect(table.name)
    cursor = conn.cursor()
    query = f"""
    SELECT key, forecast_ref_time, step FROM uploaded WHERE forecast_ref_time = ?
    """
    forecast_ref_time_dt = dt.strptime(date + time, "%Y%m%d%H%M")
    cursor.execute(query, (forecast_ref_time_dt,))
    items = cursor.fetchall()
    conn.close()

    # Dictionary to store unique steps
    unique_steps = {}

    # Iterate through items and add only unique steps
    matching_objects = {
        item[0]: GribMetadata(
            date=dt.strptime(item[1], "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d"),
            time=dt.strptime(item[1], "%Y-%m-%d %H:%M:%S").strftime("%H%M"),
            step=item[2],
        )
        for item in items
        if item[2] not in unique_steps and not unique_steps.update({item[2]: True})
    }
    return matching_objects

def download_keys_from_bucket(keys: list[str],
                             dst_dir: Path,
                             bucket: Bucket = CONFIG.main.aws.s3.nwp_model_data,
                             ) -> None:
    """ 
    Download object from S3 bucket.
    Filename of resulting local file is formatted value of the key.

    Args:
        key: S3 object key
        dest: Path to download file to.
        bucket: S3 bucket from where data will be fetched.
    """
    _logger.info("Downloading input data from S3 bucket.")

    client = _create_s3_client(bucket)

    _logger.info("Objects to download: %s", keys)

    for key in keys:
        path = dst_dir / Path(key).name
        if not os.path.exists( path.parent ):
            os.makedirs( path.parent )
        _logger.info('Downloading %s to %s', key, path)
        client.download_file(bucket.name, key, path )

def _create_s3_client(bucket):
    """
    Creates and configures the S3 client based on the bucket's endpoint.

    Args:
        bucket: An object containing bucket configuration attributes.
                Must include 'name', 'retries' and optionally 'endpoint_url'.

    Returns:
        A configured boto3 S3 client.
    """
    retries_config = {
        'max_attempts': bucket.retries,
        'mode': 'standard'
    }

    if bucket.platform == 'other':
        # Non-AWS configuration
        return boto3.Session().client(
            's3',
            endpoint_url=bucket.endpoint_url,
            config=Config(retries=retries_config)
        )
    elif bucket.platform == 'aws':
        # AWS S3 configuration
        return boto3.Session().client(
            's3',
            config=Config(
                region_name=bucket.region,
                retries=retries_config
            )
        )