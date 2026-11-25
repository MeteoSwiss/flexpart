"""Download input files from an input manifest produced by the leadtime-aggregator.

``INPUT_MANIFEST_URI`` must be set — the container has no fallback file-selection logic.
"""

import json
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import (
    EndpointConnectionError,
    IncompleteReadError,
    ReadTimeoutError,
    ResponseStreamingError,
)

from . import CONFIG

_logger = logging.getLogger(__name__)

INPUT_MANIFEST_URI_VAR = "INPUT_MANIFEST_URI"

# The client's retry config covers the request itself, not a body stream that breaks halfway, so a
# broken stream is retried here.
_STREAM_ATTEMPTS = 3
_STREAM_RETRY_DELAY_S = 0.5
_STREAM_ERRORS = (EndpointConnectionError, IncompleteReadError, ReadTimeoutError, ResponseStreamingError)


def download_from_manifest(data_dir: Path, member: int) -> None:
    """Download input files listed in the manifest for *member*, in parallel over one shared client."""
    uri = os.environ.get(INPUT_MANIFEST_URI_VAR)
    if not uri:
        raise RuntimeError(f"Environment variable '{INPUT_MANIFEST_URI_VAR}' is not set")

    _logger.info("Using input manifest from %s for member %d", uri, member)
    bucket, key = _parse_s3_uri(uri)
    settings = CONFIG.main.aws.s3.input_manifest
    s3 = _create_client()

    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    manifest = json.loads(body)

    entries = manifest.get(str(member))
    if not entries:
        raise RuntimeError(
            f"Manifest at {uri} has no entries for member {member}; available members: {sorted(manifest.keys())}"
        )

    data_dir.mkdir(parents=True, exist_ok=True)
    workers = max(1, min(settings.max_concurrent_downloads, len(entries)))
    start = time.monotonic()
    total_bytes = _download_entries(s3, entries, data_dir, workers)
    elapsed = time.monotonic() - start

    mib = total_bytes / 2**20
    _logger.info(
        "Downloaded %d files (%.1f MiB) from manifest in %.1f s (%.1f MiB/s, %d threads)",
        len(entries),
        mib,
        elapsed,
        mib / elapsed if elapsed > 0 else 0.0,
        workers,
    )


def _create_client() -> BaseClient:
    """One client shared by all download threads (boto3 clients are thread-safe). Its pool must hold a
    connection per thread; botocore's default of 10 would make the extra threads wait."""
    settings = CONFIG.main.aws.s3.input_manifest
    return boto3.client(
        "s3",
        config=Config(
            region_name=settings.region,
            retries={"max_attempts": settings.retries, "mode": "standard"},
            max_pool_connections=max(1, settings.max_concurrent_downloads),
        ),
    )


def _download_entries(client: BaseClient, entries: list[dict], data_dir: Path, workers: int) -> int:
    """Download all *entries* with *workers* threads and return the bytes written. The first failure
    cancels the downloads that have not started yet and is re-raised."""
    if not entries:
        return 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="manifest-download") as pool:
        futures = [
            pool.submit(_get_object_to_file, client, entry["bucket"], entry["key"], data_dir / entry["local_name"])
            for entry in entries
        ]
        try:
            return sum(future.result() for future in as_completed(futures))
        except BaseException:
            pool.shutdown(cancel_futures=True)
            raise


def _get_object_to_file(client: BaseClient, bucket: str, key: str, path: Path) -> int:
    """Stream one object to *path* with a single GetObject and return its size.

    Each request is billed, and input files run to several hundred MB, so this deliberately avoids
    boto3's managed transfer (``download_file``), which sends a HeadObject and then splits any file over
    8 MiB into 8 MiB ranged GETs.

    Writes to a hidden ``.<name>.part`` (outside the ``dispc*``/``dispf*`` globs), renamed when complete."""
    chunk_size = CONFIG.main.aws.s3.download_chunk_size_bytes
    path.parent.mkdir(parents=True, exist_ok=True)
    part_path = path.with_name(f".{path.name}.part")
    _logger.info("Downloading s3://%s/%s → %s", bucket, key, path)

    try:
        for attempt in range(1, _STREAM_ATTEMPTS + 1):
            try:
                body = client.get_object(Bucket=bucket, Key=key)["Body"]
                with body, open(part_path, "wb") as f:
                    shutil.copyfileobj(body, f, chunk_size)
                    size = f.tell()
                os.replace(part_path, path)
                return size
            except _STREAM_ERRORS as e:
                if attempt == _STREAM_ATTEMPTS:
                    _logger.error("Failed after %d download attempts: s3://%s/%s", _STREAM_ATTEMPTS, bucket, key)
                    raise
                _logger.info("Retrying download of s3://%s/%s due to %r", bucket, key, e)
                time.sleep(_STREAM_RETRY_DELAY_S * 2 ** (attempt - 1))
        raise AssertionError("unreachable")
    finally:
        part_path.unlink(missing_ok=True)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse ``s3://bucket/key`` into ``(bucket, key)``."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Expected s3:// URI, got: {uri}")
    path = uri[5:]
    bucket, _, key = path.partition("/")
    return bucket, key
