import tempfile
from pathlib import Path

import pytest

from flexpart_ifs_utils import CONFIG
from flexpart_ifs_utils.config.service_settings import Bucket
from flexpart_ifs_utils.s3_utils import (
    canonicalize_output_names,
    download_keys_from_bucket,
    upload_output,
)


def test_download_keys_from_bucket(s3, model_data: Path):
    bucket = Bucket(region="us-east-1", name="test-bucket", retries=3)

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
    site = "ABC"
    datetime = "2024060712"
    run_id = "scheduled-flexpart-IFS-Global-20240607-1200"
    run_type = "scheduled"

    # when
    upload_output(model_data, run_type, run_id, site, datetime, bucket)

    # then
    assert "Contents" in s3.list_objects(Bucket=bucket.name)

    for path in model_data.iterdir():
        # check the files were uploaded as expected: the run type folder, the run id, the site,
        # with the forecast reference carried as metadata rather than as a key segment
        obj = s3.get_object(Bucket=bucket.name, Key=f"{run_type}/{run_id}/{site}/{path.name}")
        with open(path, mode="rb") as f:
            assert obj["Body"].read() == f.read()

        assert obj["Metadata"] == {
            "run-id": run_id,
            "date": "20240607",
            "time": "12",
            "site": site,
        }


def test_canonicalize_output_names(tmp_path: Path):

    # given - what Flexpart actually writes: the concentration grid stamped with the simulation
    # start, next to the other output files it leaves behind
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "grid_conc_20241210000000.nc").write_text("conc", encoding="utf-8")
    (output_dir / "header").write_text("header", encoding="utf-8")

    # when
    canonicalize_output_names(output_dir)

    # then
    assert (output_dir / "grid_conc.nc").read_text(encoding="utf-8") == "conc"
    assert not (output_dir / "grid_conc_20241210000000.nc").exists()
    assert (output_dir / "header").exists()


def test_canonicalize_output_names_renames_nest_separately(tmp_path: Path):

    # given - the nested grid also matches the plain pattern, so it must not be mistaken for it
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "grid_conc_20241210000000.nc").write_text("conc", encoding="utf-8")
    (output_dir / "grid_conc_nest_20241210000000.nc").write_text("nest", encoding="utf-8")

    # when
    canonicalize_output_names(output_dir)

    # then
    assert (output_dir / "grid_conc.nc").read_text(encoding="utf-8") == "conc"
    assert (output_dir / "grid_conc_nest.nc").read_text(encoding="utf-8") == "nest"


def test_canonicalize_output_names_requires_the_concentration_grid(tmp_path: Path):

    # given - a backward run writes grid_time_* instead, and is not wired through to rendering
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "grid_time_20241210000000.nc").write_text("time", encoding="utf-8")

    # then - fail here rather than leaving the render step pointed at a key nobody wrote
    with pytest.raises(RuntimeError, match="grid_conc"):
        canonicalize_output_names(output_dir)


def test_canonicalize_output_names_rejects_an_ambiguous_match(tmp_path: Path):

    # given
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "grid_conc_20241210000000.nc").write_text("a", encoding="utf-8")
    (output_dir / "grid_conc_20241210030000.nc").write_text("b", encoding="utf-8")

    # then
    with pytest.raises(RuntimeError, match="at most one"):
        canonicalize_output_names(output_dir)


def test_canonicalize_output_names_is_idempotent(tmp_path: Path):

    # given - a hand-run `upload` against a job directory that was already renamed
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "grid_conc.nc").write_text("conc", encoding="utf-8")

    # when
    canonicalize_output_names(output_dir)

    # then
    assert (output_dir / "grid_conc.nc").read_text(encoding="utf-8") == "conc"


def _add_files_to_bucket(bucket: Bucket, files: list[Path], s3) -> None:

    for path in files:
        s3.upload_file(path, bucket.name, path.name)
