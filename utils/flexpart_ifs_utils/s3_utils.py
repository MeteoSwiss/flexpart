import glob
import logging
import os
import re
from pathlib import Path

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from flexpart_ifs_utils import CONFIG
from flexpart_ifs_utils.config.service_settings import Bucket

_logger = logging.getLogger(__name__)

# (pattern, canonical name, required). The nested pattern is listed first and matched exclusively,
# because `grid_conc_nest_<stamp>.nc` also satisfies the plain concentration pattern.
_OUTPUT_NAME_PATTERNS: tuple[tuple[re.Pattern[str], str, bool], ...] = (
    (re.compile(r"^grid_conc_nest_\d+\.nc$"), "grid_conc_nest.nc", False),
    (re.compile(r"^grid_conc_\d+\.nc$"), "grid_conc.nc", True),
)


def canonicalize_output_names(output_dir: Path) -> None:
    """Strip the simulation-start timestamp out of Flexpart's NetCDF filenames.

    Flexpart names its concentration output ``grid_conc_<ibdate><ibtime>.nc`` from the *simulation
    start* (see ``netcdf_output_mod.f90``), so every consumer that wants to address the file has to
    re-derive that timestamp. Three of them did, each hard-coding ``forecast + 3h``, which held only
    while every release site shared one offset. The S3 key already carries date, hour and site, so the
    timestamp inside the filename is pure duplication: dropping it collapses all three consumers to a
    constant and lets the release window vary per site.

    A missing or ambiguous concentration file raises rather than being skipped - the failure would
    otherwise surface much later, as a render step pointed at a key that was never written. Backward
    runs (``LDIRECT=-1``) write ``grid_time_*.nc`` instead and are not wired through to rendering;
    they fail here, deliberately.

    Idempotent, so a hand-run ``upload`` on an already-renamed job directory still works.
    """
    if not output_dir.is_dir():
        raise RuntimeError(f"Flexpart output directory does not exist: {output_dir}")

    for pattern, canonical_name, required in _OUTPUT_NAME_PATTERNS:
        matches = sorted(p for p in output_dir.iterdir() if pattern.match(p.name))

        if len(matches) > 1:
            raise RuntimeError(
                f"Expected at most one {pattern.pattern} in {output_dir}, found {[p.name for p in matches]}"
            )
        if not matches:
            if (output_dir / canonical_name).exists():
                _logger.info("Flexpart output already named %s, nothing to rename", canonical_name)
                continue
            if required:
                raise RuntimeError(
                    f"No Flexpart output matching {pattern.pattern} in {output_dir}; "
                    f"found {sorted(p.name for p in output_dir.iterdir())}"
                )
            continue

        source = matches[0]
        target = output_dir / canonical_name
        _logger.info("Renaming Flexpart output %s to %s", source.name, target.name)
        source.rename(target)


def upload_output(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    directory: Path,
    run_type: str,
    run_id: str,
    site: str,
    forecast_datetime: str,
    bucket: Bucket = CONFIG.main.aws.s3.output,
    parent: str | None = None,
) -> None:
    """
    Uploads the contents of the Flexpart output directory to an S3 bucket.

    Uploads files from the specified directory to the provided S3 bucket,
    with metadata of forecast datetime and site attached. If a parent directory is specified, only files
    within that parent directory are uploaded.

    The object key is rooted at ``run_type``, then ``run_id``, and carries nothing below that but
    the release site, this
    application's only fan-out dimension. The run id is a deterministic composite that already
    encodes the run type, application, model and forecast reference, so repeating the forecast
    reference as a key segment would say the same thing twice - it is still recorded as object
    metadata, where it is searchable without being part of the identity.
    """

    if not directory.is_dir():
        _logger.error("Directory is empty, cannot upload: %s", directory)
        raise RuntimeError("Directory provided to upload does not exist.")

    try:
        client = _create_s3_client(bucket)

        path_list = [Path(f) for f in glob.iglob(f"{directory}/**", recursive=True) if os.path.isfile(f)]

        if parent:
            path_list = [p for p in path_list if p.parent.name == parent]

        for path in path_list:
            key = f"{run_type}/{run_id}/{site}/{path.name}"
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
                        ExtraArgs={
                            "Metadata": {
                                # Hyphenated to match flexpart-cosmo-icon, where an underscored
                                # metadata key is lost by the moto server its tests run against; the
                                # two flexpart applications describe their output with one vocabulary.
                                "run-id": run_id,
                                "date": forecast_datetime[:8],
                                "time": forecast_datetime[8:],
                                "site": site,
                            }
                        },
                    )
            except ClientError as exc:
                _logger.error("Upload failed for %s: %s", path, exc)
                raise
    except Exception as err:
        _logger.error("Error uploading directory to S3.")
        raise err


def download_keys_from_bucket(
    keys: list[str],
    dst_dir: Path,
    bucket: Bucket,
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
