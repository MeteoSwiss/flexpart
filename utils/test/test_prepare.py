import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from flexpart_ifs_utils.grib_utils import GribMetadata
from flexpart_ifs_utils.job_config import JobConfig, resolve_job_config
from flexpart_ifs_utils.model import Model
from flexpart_ifs_utils.prepare_flexpart import (_generate_available,
                                                 _get_valid_datetime,
                                                 _write_job_script,
                                                 prepare_job_directory,
                                                 render_namelists, select_files)
from flexpart_ifs_utils.site_config import load_site_config

MOCK_MD_EXTRACTION = "flexpart_ifs_utils.grib_utils.extract_metadata_from_grib_file"
MOCK_LIST_OBJS_IN_BUCKET = "flexpart_ifs_utils.prepare_flexpart.list_objs_in_bucket"

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

@pytest.fixture
def mock_logger(mocker):
    return mocker.patch("flexpart_ifs_utils.prepare_flexpart._logger", autospec=True)


def test_render_namelists(tmp_path, site_config_file, references,
                          reference_forecast_datetime, reference_data_end):
    """The site object plus the resolved window must reproduce the reference namelists exactly.

    This is the contract that replaced the regex-substitution pass: everything Flexpart reads comes
    from templates/{COMMAND,RELEASES}.j2 filled from the site config and the job window.
    """
    site = load_site_config(site_config_file)
    job = resolve_job_config(reference_forecast_datetime, Model.IFS_HRES_EUROPE, site)

    render_namelists(TEMPLATES_DIR, tmp_path, site, job)

    for name in ("COMMAND", "RELEASES"):
        expected = (references / "Testerhausen/input" / name).read_text(encoding="utf-8")
        assert (tmp_path / name).read_text(encoding="utf-8") == expected


def test_render_namelists_follows_the_sites_offsets(tmp_path, site_config_file,
                                                    reference_forecast_datetime, reference_data_end):
    """Change a site's release offset and the namelist follows - nothing else re-derives it."""
    site = load_site_config(site_config_file)
    job = resolve_job_config(reference_forecast_datetime, Model.IFS_HRES_EUROPE, site,
                             overrides={"release_start_offset_h": 4, "release_end_offset_h": 6})

    render_namelists(TEMPLATES_DIR, tmp_path, site, job)

    releases = (tmp_path / "RELEASES").read_text(encoding="utf-8")
    assert "IDATE1=20241210," in releases
    assert "ITIME1=010000," in releases
    assert "ITIME2=030000," in releases


def test_render_namelists_renders_sub_hour_windows(tmp_path, site_config_file,
                                                   reference_forecast_datetime, reference_data_end):
    """HHMISS, not HH + a literal '0000' - fractional offsets are expressible now."""
    site = load_site_config(site_config_file)
    job = resolve_job_config(reference_forecast_datetime, Model.IFS_HRES_EUROPE, site,
                             overrides={"release_start_offset_h": 2.5})

    render_namelists(TEMPLATES_DIR, tmp_path, site, job)

    assert "ITIME1=233000," in (tmp_path / "RELEASES").read_text(encoding="utf-8")


def test_write_job_script(tmp_path, mock_config):
    from flexpart_ifs_utils import CONFIG

    data = {
        "file_path" : tmp_path / "job.sh",
        "flexpart_exe" : tmp_path / "flexpart_exe",
    }

    _write_job_script(
        data["file_path"],
        data["flexpart_exe"],
        CONFIG.main.openmp_config
    )

    job = Path(data["file_path"])

    assert job.exists()
    run_command = "$FLEXPART_EXE"
    assert run_command in job.read_text()

    openmp_expected_1 = "export OMP_NUM_THREADS=5"
    openmp_expected_2 = "export OMP_STACKSIZE=1000M"
    assert openmp_expected_1 in job.read_text()
    assert openmp_expected_2 in job.read_text()

    for i in run_command.split(' '):
        assert f"export {i[1:]}={data[i[1:].lower()]}" in job.read_text()


def test_generate_available(tmp_path):

    def side_effect(arg):
        step = int(str(arg).split('-')[-1])
        return GribMetadata(date = "20240401", time = "1800", step = step)

    data_paths: list[Path] = [
        tmp_path / "data-0",
        tmp_path / "data-1",
        tmp_path / "data-2",
        tmp_path / "data-3",
        tmp_path / "data-4",
        tmp_path / "data-5",
        tmp_path / "data-6",
        tmp_path / "data-7",
    ]

    path = tmp_path / "available.txt"

    with patch(MOCK_MD_EXTRACTION) as mock_extract_metadata:
        mock_extract_metadata.side_effect = side_effect

        _generate_available(path, data_paths)

    assert path.exists()
    assert "YYYYMMDD HHMISS" in path.read_text()

    assert f"20240401 180000      data-0" in path.read_text()
    assert f"20240401 190000      data-1" in path.read_text()
    assert f"20240401 200000      data-2" in path.read_text()
    assert f"20240401 210000      data-3" in path.read_text()
    assert f"20240401 220000      data-4" in path.read_text()
    assert f"20240401 230000      data-5" in path.read_text()
    assert f"20240402 000000      data-6" in path.read_text()
    assert f"20240402 010000      data-7" in path.read_text()

def test_get_valid_datetime(tmp_path):
    grib_file = tmp_path / "test.grib"
    grib_file.touch()

    with patch(MOCK_MD_EXTRACTION) as mock_extract_metadata:
        mock_extract_metadata.return_value = GribMetadata(date = "20240101", time = "1200", step = 1)
        dt = _get_valid_datetime(grib_file)
        assert dt == datetime(2024, 1, 1, 13)

        mock_extract_metadata.return_value = GribMetadata(date = "20240101", time = "1800", step = 8)
        dt = _get_valid_datetime(grib_file)
        assert dt == datetime(2024, 1, 2, 2)


def test_get_valid_datetime_with_metadata(tmp_path):
    grib_file = tmp_path / "test.grib"

    md = GribMetadata(date = "20240101", time = "1200", step = 1)

    dt = _get_valid_datetime(grib_file, md)
    assert dt == datetime(2024, 1, 1, 13)

    md.time = '1800'
    md.step = 8

    dt = _get_valid_datetime(grib_file, md)
    assert dt == datetime(2024, 1, 2, 2)


def test_prepare_job_directory(tmp_path: Path, references, site_config_file,
                               reference_forecast_datetime, reference_data_end):
    from flexpart_ifs_utils import CONFIG

    def side_effect(arg):
        step = int(str(arg).split('-')[-1])
        return GribMetadata(date = "20240319", time = "0900", step = step)

    site = load_site_config(site_config_file)
    job = resolve_job_config(reference_forecast_datetime, Model.IFS_HRES_EUROPE, site)

    jobs_dir = tmp_path / "jobs"
    data_dir = tmp_path / "data"

    os.mkdir(jobs_dir)
    os.mkdir(data_dir)

    flexpart_dir = Path(os.environ['FLEXPART_PREFIX'])

    data_paths: list[Path] = [ data_dir / f"dispf-{step}" for step in range(3,27) ]

    for file in data_paths:
        file.touch()

    with patch(MOCK_MD_EXTRACTION) as mock_extract_metadata:
        mock_extract_metadata.side_effect = side_effect

        job_dir = prepare_job_directory(site, job, jobs_dir, flexpart_dir, data_dir, CONFIG.main.openmp_config, model=Model.IFS_HRES_EUROPE)

        assert job_dir.is_dir()
        assert job_dir.name == site.name
        assert (job_dir / 'input' ).is_dir()
        assert (job_dir / 'output' ).is_dir()
        assert (job_dir / 'data' ).is_symlink()
        assert (job_dir / 'job' ).exists()

        for file in ('COMMAND', 'RELEASES'):
            assert (job_dir / 'input' / file).exists()
            with open(job_dir / 'input' / file, 'r') as actual:
                with open(references / 'Testerhausen/input' / file, 'r') as expected:
                    assert actual.read() == expected.read()

        # The packaged skeletons and the archived per-site variants are no longer copied in: the
        # only RELEASES in the job directory is the one that was rendered for this site.
        assert [p.name for p in job_dir.glob('input/RELEASES*')] == ['RELEASES']

        # Test that the correct outgrid was used, given the model.
        assert (job_dir / 'input' / 'OUTGRID').exists()
        with open(job_dir / 'input' / "OUTGRID", 'r') as outgrid_actual:
            with open(references / 'Testerhausen/input' / "OUTGRID", 'r') as outgrid_expected:
                assert outgrid_actual.read() == outgrid_expected.read()

        # Test that all the input data filenames are in the available file.
        assert (job_dir / 'input' / 'AVAILABLE').exists()
        assert not (job_dir / 'input' / 'AVAILABLE_NESTED').exists()
        available = (job_dir / 'input' / 'AVAILABLE').read_text()
        for path in data_paths:
            assert str(path.name) in available



@pytest.mark.parametrize("step_unit", [("minutes"), ("hours")])
def test_select_files(tmp_path, step_unit):
    from flexpart_ifs_utils import CONFIG

    CONFIG.main.input.step_unit = step_unit

    DATE="20240501"
    TIME="1200"

    # A simulation window of 14:00 to 18:00 against a 12:00 forecast reference. The window arrives as
    # datetimes now, rather than being re-parsed out of the namelist's date strings.
    job = JobConfig(
        model=Model.IFS_HRES_EUROPE,
        forecast_datetime=datetime(2024, 5, 1, 12),
        simulation_start=datetime(2024, 5, 1, 14),
        simulation_end=datetime(2024, 5, 1, 18),
        release_start=datetime(2024, 5, 1, 14),
        release_end=datetime(2024, 5, 1, 16),
    )

    if step_unit == 'minutes':
        multiplier = 60
    elif step_unit == 'hours':
        multiplier = 1

    keys = [
        str(tmp_path / "0000"),
        str(tmp_path / "1000"),
        str(tmp_path / "2000"),
        str(tmp_path / "3000"),
        str(tmp_path / "4000"),
        str(tmp_path / "5000"),
        str(tmp_path / "6000"),
        str(tmp_path / "7000"),
        str(tmp_path / "8000"),
        str(tmp_path / "9000"),
    ]

    with patch(MOCK_LIST_OBJS_IN_BUCKET, spec=True) as mock_list_bucket:
        mock_list_bucket.return_value = {key: GribMetadata(
            date = DATE,
            time = TIME,
            step = int(str(key).split('/')[-1][0])*multiplier,
            ) for key in keys}
        subset = select_files(job,
                            step_unit=CONFIG.main.input.step_unit,
                            model=Model.IFS_HRES_EUROPE)

        # Starts at 13:00, not 14:00: the simulation starts after the forecast reference, so the
        # preceding step is pulled in for precipitation de-accumulation.
        expected = {
            str(tmp_path / "1000"),
            str(tmp_path / "2000"),
            str(tmp_path / "3000"),
            str(tmp_path / "4000"),
            str(tmp_path / "5000"),
            str(tmp_path / "6000")
        }
        assert len(subset) == 6
        assert set(subset) == expected
