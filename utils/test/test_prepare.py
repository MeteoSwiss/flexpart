import os
from pathlib import Path
from datetime import datetime
import shutil
import yaml

import pytest
from unittest.mock import patch

from flexpart_ifs_utils.prepare_flexpart import (
    render_template, _filter_config, _write_job_script, _generate_available,
    _get_valid_datetime, prepare_job_directory, _configure_namelist,
    select_files, _get_start_end, validate_env, parse_env
)
from flexpart_ifs_utils.grib_utils import GribMetadata
from test.conftest import jinja_template, references, s3, mock_config

MOCK_MD_EXTRACTION = "flexpart_ifs_utils.grib_utils.extract_metadata_from_grib_file"
MOCK_LIST_OBJS_IN_BUCKET_VIA_DB = "flexpart_ifs_utils.s3_utils.list_objs_in_bucket_via_dynamodb"

@pytest.fixture
def mock_logger(mocker):
    return mocker.patch("flexpart_ifs_utils.prepare_flexpart._logger", autospec=True)


@pytest.fixture
def mock_environment_incomplete(monkeypatch):
    # IBDATE is intentionally not set here
    monkeypatch.setenv("IBTIME", '30000')
    monkeypatch.setenv("IEDATE", '20241213')
    monkeypatch.setenv("IETIME", '60000')

def test_validate_env(mock_environment_incomplete):

    environment = parse_env()

    with pytest.raises(RuntimeError) as exc_info:
        validate_env(environment)

    assert "Environment is missing variables needed to prepare runtime configuration: ['IBDATE']" in str(exc_info.value)


def test_render_template(tmp_path, jinja_template, references):

    output_path = tmp_path / "output.txt"

    data = {
        "IBDATE" : "20241213",
        "IBTIME" : "03",
        "IEDATE" : "20241213",
        "IETIME" : "09"}

    render_template(jinja_template, output_path, ['BEZ'], data)

    assert "IBDATE: '20241213'" in output_path.read_text()
    assert 'COMMENT: Leibstadt' not in output_path.read_text()

    with open(output_path, 'r', encoding="utf-8") as f:
        actual_runtime_conf = yaml.safe_load(f)

    with open(references / 'runtime_configuration.yaml', 'r', encoding="utf-8") as f:
        expected_runtime_conf = yaml.safe_load(f)

    assert actual_runtime_conf == expected_runtime_conf


def test_filter_config(tmp_path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
    - name: BEZ
    - name: LEI
    - name: GOE
    """)

    release_sites = ["BEZ", "GOE"]
    _filter_config(yaml_file, release_sites)

    assert yaml_file.read_text() == "- name: BEZ\n- name: GOE\n"



def test_write_job_script(tmp_path, mock_config):
    from flexpart_ifs_utils import CONFIG

    data = {
        "file_path" : tmp_path / "job.sh",
        "flexpart_exe" : tmp_path / "flexpart_exe",
        "input_dir" : tmp_path / "input",
        "output_dir" : tmp_path / "output",
        "data_dir" : tmp_path / "data",
        "available_path" : tmp_path / "available"
    }

    _write_job_script(
        data["file_path"], 
        data["flexpart_exe"], 
        data["input_dir"], 
        data["output_dir"], 
        data["data_dir"], 
        data["available_path"],
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


def test_prepare_job_directory(tmp_path: Path, references):
    from flexpart_ifs_utils import CONFIG

    def side_effect(arg):
        step = int(str(arg).split('-')[-1])
        return GribMetadata(date = "20240319", time = "0900", step = step)
    
    with open(references / 'runtime_configuration.yaml', 'r', encoding="utf-8") as f:
        input_runtime_conf = yaml.safe_load(f)

    jobs_dir = tmp_path / "jobs"
    data_dir = tmp_path / "data"

    os.mkdir(jobs_dir)
    os.mkdir(data_dir)
    
    flexpart_dir = Path(os.getenv('FLEXPART_PREFIX'))

    data_paths: list[Path] = [ data_dir / f"data-lfff-{step}" for step in range(3,27) ]

    for file in data_paths:
        file.touch()

    with patch(MOCK_MD_EXTRACTION) as mock_extract_metadata:
        mock_extract_metadata.side_effect = side_effect

        for conf in input_runtime_conf:
            job_dir = prepare_job_directory(conf, jobs_dir, flexpart_dir, data_dir, CONFIG.main.openmp_config)

            assert job_dir.is_dir()
            assert job_dir.name == conf['name']
            assert (job_dir / 'input' ).is_dir()
            assert (job_dir / 'output' ).is_dir()
            assert (job_dir / 'data' ).is_symlink()
            assert (job_dir / 'job' ).exists()

            for file in ('COMMAND', 'RELEASES'):
                assert (job_dir / 'input' / file).exists()
                with open(job_dir / 'input' / file, 'r') as actual:
                    with open(references / 'BEZ/input' / file, 'r') as expected:
                        assert actual.read() == expected.read()

            # Test that the correct outgrid was used, given the model.
            assert (job_dir / 'input' / 'OUTGRID').exists()
            with open(job_dir / 'input' / "OUTGRID", 'r') as outgrid_actual:
                with open(references / 'BEZ/input' / "OUTGRID", 'r') as outgrid_expected:
                    assert outgrid_actual.read() == outgrid_expected.read()

            # Test that all the input data filenames are in the available file.
            assert (job_dir / 'input' / 'AVAILABLE').exists()
            available = (job_dir / 'input' / 'AVAILABLE').read_text()
            for path in data_paths:
                assert str(path.name) in available



def test_configure_namelist(tmp_path, references):
    command_namelist: Path = references / 'BEZ/input' / "COMMAND"
    command_copy = tmp_path / command_namelist.name
    shutil.copyfile(command_namelist, command_copy)

    with open(references / 'runtime_configuration.yaml', 'r') as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)
    
    config[0]['command']['IBDATE'] = '20250519'
    config[0]['command']['IEDATE'] = '20250520'
    config[0]['command']['IBTIME'] = '060000'
    config[0]['command']['IETIME'] = '090000'
    print(config)

    _configure_namelist(config[0], command_copy)

    assert "IBDATE=20250519," in command_copy.read_text()
    assert "IBTIME=060000," in command_copy.read_text()
    assert "IEDATE=20250520," in command_copy.read_text()
    assert "IETIME=090000," in command_copy.read_text()

    releases_namelist: Path = references / 'BEZ/input' / "RELEASES"
    releases_copy = tmp_path / releases_namelist.name
    shutil.copyfile(releases_namelist, releases_copy)

    config[0]['releases']['LAT1'] = 43.21
    config[0]['releases']['LAT2'] = 43.21
    config[0]['releases']['LON1'] = 8.567
    config[0]['releases']['LON2'] = 8.567

    _configure_namelist(config[0], releases_copy)

    assert "LAT1=43.21," in releases_copy.read_text()
    assert "LAT2=43.21," in releases_copy.read_text()
    assert "LON1=8.567," in releases_copy.read_text()
    assert "LON2=8.567," in releases_copy.read_text()


@patch(MOCK_LIST_OBJS_IN_BUCKET_VIA_DB, spec=True)
@pytest.mark.parametrize("step_unit", ["minutes", "hours"])
def test_select_files_no_constant(mock_list_bucket, tmp_path, s3, step_unit):
    from flexpart_ifs_utils import CONFIG

    CONFIG.main.input.step_unit = step_unit

    DATE="20240501"
    TIME="1200"

    RUNTIME_CONF = {"IBDATE": "20240501", "IBTIME": 120000, "IEDATE": "20240501", "IETIME": 160000}

    if step_unit == 'minutes':
        multiplier = 60
    elif step_unit == 'hours':
        multiplier = 1

    keys = [
        str(tmp_path / "data-0"),
        str(tmp_path / "data-1"),
        str(tmp_path / "data-2"),
        str(tmp_path / "data-3"),
        str(tmp_path / "data-4"),
        str(tmp_path / "data-5"),
    ]

    mock_list_bucket.return_value = {key: GribMetadata(date = DATE, time = TIME, step = int(str(key).split('-')[-1])*multiplier) for key in keys}
    
    with pytest.raises(RuntimeError) as excinfo:
        select_files(RUNTIME_CONF, 
                        table=CONFIG.main.aws.db.nwp_model_data, 
                        forecast_datetime=f"{DATE}{TIME}", 
                        step_unit=CONFIG.main.input.step_unit)
    
    assert "no constant file" in str(excinfo.value).lower()


@patch(MOCK_LIST_OBJS_IN_BUCKET_VIA_DB, spec=True)
@pytest.mark.parametrize("step_unit", ["minutes", "hours"])
def test_select_files(mock_list_bucket, tmp_path, s3, step_unit):
    from flexpart_ifs_utils import CONFIG

    CONFIG.main.input.step_unit = step_unit

    MODEL = "ICON-CH1-EPS"
    DATE="20240501"
    TIME="1200"
    ENS = "1"

    RUNTIME_CONF = {"IBDATE": "20240501", "IBTIME": 140000, "IEDATE": "20240501", "IETIME": 180000}

    if step_unit == 'minutes':
        multiplier = 60
    elif step_unit == 'hours':
        multiplier = 1

    keys = [
        str(tmp_path / "0000c"),
        str(tmp_path / "0000"),
        str(tmp_path / "1000"),
        str(tmp_path / "2000"),
        str(tmp_path / "3000"),
        str(tmp_path / "4000"),
        str(tmp_path / "5000"),
        str(tmp_path / "6000"),
    ]

    mock_list_bucket.return_value = {key: GribMetadata(
        date = DATE,
        time = TIME,
        step = int(str(key).split('/')[-1][0])*multiplier,
        ) for key in keys}

    subset = select_files(RUNTIME_CONF, 
                        table=CONFIG.main.aws.db.nwp_model_data, 
                        forecast_datetime=f"{DATE}{TIME}", 
                        step_unit=CONFIG.main.input.step_unit)
    print(subset)

    expected = set(keys)
    expected.remove(str(tmp_path / "0000"))
    assert len(subset) == 7
    assert set(subset) == expected

def test_get_start_end():
    config = {"IBDATE": "20230101", "IBTIME": 120000, "IEDATE": "20230201", "IETIME": 220000}

    start, end = _get_start_end(config)

    assert start == datetime(2023, 1, 1, 12, 0, 0)
    assert end == datetime(2023, 2, 1, 22, 0, 0)