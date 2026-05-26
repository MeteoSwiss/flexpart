import glob
import logging
import os
from datetime import datetime
from pathlib import Path

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from flexpart_ifs_utils import CONFIG
from flexpart_ifs_utils.config.service_settings import Bucket
from flexpart_ifs_utils.grib_utils import (GribMetadata, RunMetadata,
                                           _is_grib_file,
                                           extract_metadata_from_grib_file,
                                           _get_valid_datetime)

_logger = logging.getLogger(__name__)


def upload_directory(
    directory: Path,
    input_path: Path,
    site: str,
    bucket: Bucket = CONFIG.main.aws.s3.output,
    parent: str | None = None,
) -> None:
    """
    Uploads the contents of a specified directory to an S3 bucket.

    Verifies directories, extracts metadata from the Flexpart input directory,
    and uploads files from the specified directory to the provided S3 bucket,
    with metadata attached. If a parent directory is specified, only files
    within that parent directory are uploaded.
    """

    if not directory.is_dir():
        _logger.error("Directory is empty, cannot upload: %s", directory)
        raise RuntimeError("Directory provided to upload does not exist.")

    if not input_path.is_dir():
        _logger.error(
            "Directory provided to Flexpart input data (used to obtain metadata) "
            "does not exist: %s",
            input_path,
        )
        raise RuntimeError(
            "Directory provided to Flexpart input data "
            f"{input_path} (used to obtain metadata) does not exist."
        )

    try:
        md = _get_input_metadata(input_path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "No GRIB files found in the Flexpart input directory: "
            f"{input_path}, cannot extract metadata."
        ) from exc

    try:
        client = _create_s3_client(bucket)

        path_list = [
            Path(f)
            for f in glob.iglob(f"{directory}/**", recursive=True)
            if os.path.isfile(f)
        ]

        if parent:
            path_list = [p for p in path_list if p.parent.name == parent]

        for path in path_list:
            key = f"{md.date}_{md.time[:2]}/{site}/{path.name}"
            _logger.info(
                "Uploading file: %s to bucket: %s with key: %s",
                path,
                bucket.name,
                key,
            )
            try:
                with open(path, "rb") as data:
                    client.upload_fileobj(
                        data,
                        bucket.name,
                        key,
                        ExtraArgs={"Metadata": {k: str(v) for k, v in md.model_dump().items()}},
                    )
            except ClientError as exc:
                _logger.error("Upload failed for %s: %s", path, exc)
                raise
    except Exception as err:
        _logger.error("Error uploading directory to S3.")
        raise err


def _get_input_metadata(directory: Path) -> RunMetadata:
    """Find the first GRIB file in the specified directory and extract its metadata."""
    for file in directory.rglob("*"):
        if file.is_file() and _is_grib_file(file):
            md = extract_metadata_from_grib_file(file)
            # Ignore step because we only care about forecast reference time.
            return RunMetadata(date=md.date, time=md.time)

    raise FileNotFoundError("No GRIB files found in the directory.")



def _select_keys_in_window(
    objs: dict[str, GribMetadata],
    start_dt: datetime,
    end_dt: datetime,
    step_unit: str,
) -> list[str]:
    subset: list[str] = []
    for key, metadata in objs.items():
        file_validtime = _get_valid_datetime(Path(key), metadata, step_unit)
        if start_dt <= file_validtime <= end_dt:
            subset.append(key)
    return subset


def list_objs_in_bucket(
    start_time: datetime,
    end_time: datetime,
    bucket: Bucket = CONFIG.main.aws.s3.nwp_model_data,
) -> dict[str, GribMetadata]:
    """
    List objects in a S3 bucket with a filter on metadata.
    """
    _logger.info(
        "Fetching objects from S3 with valid time between: start_date=%s, end_date=%s",
        start_time,
        end_time,
    )

    client = _create_s3_client(bucket)

    try:
        paginator = client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(Bucket=bucket.name)

        items: dict[str, GribMetadata] = {}
        for page in page_iterator:
            for obj in page.get("Contents", []):
                head = client.head_object(Bucket=bucket.name, Key=obj["Key"])
                metadata = head.get("Metadata", {})
                items[obj["Key"]] = GribMetadata(
                    time=metadata.get("time", ""),
                    date=metadata.get("date", ""),
                    step=float(metadata.get("step", "-1")),
                )
    except ClientError as exc:
        _logger.error("Error listing objects in bucket: %s", exc)
        raise exc

    return items


def download_keys_from_bucket(
    keys: list[str],
    dst_dir: Path,
    bucket: Bucket = CONFIG.main.aws.s3.nwp_model_data,
) -> None:
    """Download objects from an S3 bucket to dst_dir."""
    _logger.info("Downloading input data from S3 bucket.")
    client = _create_s3_client(bucket)

    _logger.info("Objects to download: %s", keys)

    for key in keys:
        path = dst_dir / Path(key).name
        os.makedirs(path.parent, exist_ok=True)
        _logger.info("Downloading %s to %s", key, path)
        client.download_file(bucket.name, key, str(path))


def _create_s3_client(bucket: Bucket) -> BaseClient:

    retries_config = {"max_attempts": bucket.retries, "mode": "standard"}

    return boto3.Session().client(
        "s3",
        config=Config(
            region_name=bucket.region,
            retries=retries_config,
        ),
    )
