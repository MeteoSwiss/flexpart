"""Download input files from an input manifest produced by the leadtime-aggregator.

``INPUT_MANIFEST_URI`` must be set — the container has no fallback file-selection logic.
"""
import json
import logging
import os
from pathlib import Path

import boto3

_logger = logging.getLogger(__name__)

INPUT_MANIFEST_URI_VAR = "INPUT_MANIFEST_URI"


def download_from_manifest(data_dir: Path, member: int) -> None:
    """Download input files listed in the manifest for *member*."""
    uri = os.environ.get(INPUT_MANIFEST_URI_VAR)
    if not uri:
        raise RuntimeError(f"Environment variable '{INPUT_MANIFEST_URI_VAR}' is not set")

    _logger.info("Using input manifest from %s for member %d", uri, member)
    bucket, key = _parse_s3_uri(uri)
    s3 = boto3.client("s3")

    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    manifest = json.loads(body)

    entries = manifest.get(str(member))
    if entries is None:
        raise RuntimeError(
            f"Manifest at {uri} has no entries for member {member}; "
            f"available members: {sorted(manifest.keys())}")

    data_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        dest = data_dir / entry["local_name"]
        _logger.info("Downloading s3://%s/%s → %s", entry["bucket"], entry["key"], dest)
        s3.download_file(entry["bucket"], entry["key"], str(dest))

    _logger.info("Downloaded %d files from manifest", len(entries))


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse ``s3://bucket/key`` into ``(bucket, key)``."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Expected s3:// URI, got: {uri}")
    path = uri[5:]
    bucket, _, key = path.partition("/")
    return bucket, key
