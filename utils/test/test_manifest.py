import io
import json
import os
import threading

import pytest
from botocore.exceptions import ClientError, ResponseStreamingError

from flexpart_ifs_utils import CONFIG, manifest
from flexpart_ifs_utils.manifest import (
    INPUT_MANIFEST_URI_VAR,
    _get_object_to_file,
    _parse_s3_uri,
    download_from_manifest,
)

# Generic bucket created by the ``s3`` fixture in conftest.py. Manifest entries carry their own
# bucket name, so the tests don't depend on any bucket from CONFIG.
TEST_BUCKET = "test-bucket"


class TestParseS3Uri:
    def test_valid_uri(self):
        assert _parse_s3_uri("s3://my-bucket/path/to/key") == ("my-bucket", "path/to/key")

    def test_valid_uri_single_key(self):
        assert _parse_s3_uri("s3://my-bucket/key") == ("my-bucket", "key")

    def test_missing_scheme(self):
        with pytest.raises(ValueError, match="Expected s3:// URI"):
            _parse_s3_uri("https://my-bucket/key")


class TestDownloadFromManifest:
    def test_missing_env_var_raises(self, monkeypatch, tmp_path):
        monkeypatch.delenv(INPUT_MANIFEST_URI_VAR, raising=False)

        with pytest.raises(RuntimeError, match="not set"):
            download_from_manifest(tmp_path / "data", member=-1)

    def test_missing_member_raises(self, monkeypatch, tmp_path, s3):
        _put_manifest(s3, monkeypatch, {"1": [{"bucket": TEST_BUCKET, "key": "k", "local_name": "f"}]})

        with pytest.raises(RuntimeError, match="no entries for member -1"):
            download_from_manifest(tmp_path / "data", member=-1)

    def test_downloads_files_and_creates_data_dir(self, monkeypatch, tmp_path, s3):
        s3.put_object(Bucket=TEST_BUCKET, Key="ifs/a.grib", Body=b"content_a")
        s3.put_object(Bucket=TEST_BUCKET, Key="ifs/b.grib", Body=b"content_b")
        _put_manifest(
            s3,
            monkeypatch,
            {
                "-1": [
                    {"bucket": TEST_BUCKET, "key": "ifs/a.grib", "local_name": "dispf2024060712"},
                    {"bucket": TEST_BUCKET, "key": "ifs/b.grib", "local_name": "dispf2024060715"},
                ]
            },
        )

        data_dir = tmp_path / "nested" / "data"
        download_from_manifest(data_dir, member=-1)

        assert (data_dir / "dispf2024060712").read_bytes() == b"content_a"
        assert (data_dir / "dispf2024060715").read_bytes() == b"content_b"

    def test_downloads_several_files_in_parallel(self, monkeypatch, tmp_path, s3):
        """Every file must be in flight at the same time: each download waits on a barrier that only
        opens once all of them have started, so a sequential loop would time out on the first one."""
        n_files = 6
        payloads = {f"ifs/{i}.grib": os.urandom(1024) for i in range(n_files)}
        for key, payload in payloads.items():
            s3.put_object(Bucket=TEST_BUCKET, Key=key, Body=payload)
        _put_manifest(
            s3,
            monkeypatch,
            {"-1": [{"bucket": TEST_BUCKET, "key": key, "local_name": f"f{i}"} for i, key in enumerate(payloads)]},
        )
        monkeypatch.setattr(CONFIG.main.aws.s3.input_manifest, "max_concurrent_downloads", n_files)

        barrier = threading.Barrier(n_files, timeout=10)
        threads: set[str] = set()
        real_get = manifest._get_object_to_file

        def get_after_all_started(*args):
            threads.add(threading.current_thread().name)
            barrier.wait()
            return real_get(*args)

        monkeypatch.setattr(manifest, "_get_object_to_file", get_after_all_started)

        data_dir = tmp_path / "data"
        download_from_manifest(data_dir, member=-1)

        assert len(threads) == n_files
        for i, payload in enumerate(payloads.values()):
            assert (data_dir / f"f{i}").read_bytes() == payload

    def test_one_shared_client_and_one_get_per_file(self, monkeypatch, tmp_path, s3):
        """A file above boto3's 8 MiB multipart threshold must still cost a single GetObject and no
        HeadObject, and all downloads must go through the one client."""
        big = os.urandom(20 * 1024 * 1024)
        s3.put_object(Bucket=TEST_BUCKET, Key="ifs/big.grib", Body=big)
        s3.put_object(Bucket=TEST_BUCKET, Key="ifs/small.grib", Body=b"small")
        _put_manifest(
            s3,
            monkeypatch,
            {
                "-1": [
                    {"bucket": TEST_BUCKET, "key": "ifs/big.grib", "local_name": "big"},
                    {"bucket": TEST_BUCKET, "key": "ifs/small.grib", "local_name": "small"},
                ]
            },
        )

        clients = []
        operations: list[str] = []
        real_create = manifest._create_client

        def recording_client():
            client = real_create()
            client.meta.events.register("before-call.s3.*", lambda model, **_: operations.append(model.name))
            clients.append(client)
            return client

        monkeypatch.setattr(manifest, "_create_client", recording_client)

        download_from_manifest(tmp_path, member=-1)

        assert len(clients) == 1
        # manifest itself + one per file
        assert sorted(operations) == ["GetObject"] * 3
        assert (tmp_path / "big").read_bytes() == big
        assert (tmp_path / "small").read_bytes() == b"small"

    def test_client_uses_configured_region_retries_and_pool(self):
        settings = CONFIG.main.aws.s3.input_manifest
        client = manifest._create_client()

        assert client.meta.region_name == settings.region
        # botocore normalises max_attempts (retries) to total_max_attempts (first try + retries)
        assert client.meta.config.retries == {"total_max_attempts": settings.retries + 1, "mode": "standard"}
        assert client.meta.config.max_pool_connections == settings.max_concurrent_downloads

    def test_missing_object_raises(self, monkeypatch, tmp_path, s3):
        _put_manifest(s3, monkeypatch, {"-1": [{"bucket": TEST_BUCKET, "key": "missing", "local_name": "f"}]})

        with pytest.raises(ClientError):
            download_from_manifest(tmp_path, member=-1)


class _Body(io.BytesIO):
    """Stands in for botocore's StreamingBody; optionally breaks after the first read."""

    def __init__(self, data: bytes, broken: bool = False):
        super().__init__(data)
        self._broken = broken

    def read(self, size=-1):
        if self._broken:
            raise ResponseStreamingError(error="connection reset")
        return super().read(size)


class _FakeClient:
    def __init__(self, bodies: list[_Body]):
        self._bodies = bodies
        self.calls = 0

    def get_object(self, **_kwargs):
        body = self._bodies[self.calls]
        self.calls += 1
        return {"Body": body}


class TestGetObjectToFile:
    def test_retries_a_broken_stream(self, monkeypatch, tmp_path):
        monkeypatch.setattr(manifest, "_STREAM_RETRY_DELAY_S", 0)
        client = _FakeClient([_Body(b"", broken=True), _Body(b"ABCD")])

        size = _get_object_to_file(client, TEST_BUCKET, "k", tmp_path / "f")

        assert client.calls == 2
        assert size == 4
        assert (tmp_path / "f").read_bytes() == b"ABCD"

    def test_gives_up_after_max_attempts(self, monkeypatch, tmp_path):
        monkeypatch.setattr(manifest, "_STREAM_RETRY_DELAY_S", 0)
        client = _FakeClient([_Body(b"", broken=True) for _ in range(manifest._STREAM_ATTEMPTS)])

        with pytest.raises(ResponseStreamingError):
            _get_object_to_file(client, TEST_BUCKET, "k", tmp_path / "f")

        assert client.calls == manifest._STREAM_ATTEMPTS


def _put_manifest(s3, monkeypatch, content: dict) -> None:
    s3.put_object(Bucket=TEST_BUCKET, Key="manifest.json", Body=json.dumps(content).encode())
    monkeypatch.setenv(INPUT_MANIFEST_URI_VAR, f"s3://{TEST_BUCKET}/manifest.json")
