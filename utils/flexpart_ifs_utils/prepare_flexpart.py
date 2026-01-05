"""
The module contains functions required to setup the input files needed to run Flexpart.
This involves configurnig the input namelists (such as COMMAND, AVAILABLE, RELEASES, OUTGRID) 
based on a set of environment variables, symlinking the data into the job folder
and writing the job script with the relevent paths to the input files.
"""


import os
import shutil
import re
import logging
from pathlib import Path
from datetime import datetime, timedelta

from jinja2 import Environment, FileSystemLoader
import yaml

from flexpart_ifs_utils.model import EnvironmentParameters
from flexpart_ifs_utils.config.service_settings import DBTable, OpenMPConfig
from flexpart_ifs_utils import s3_utils, grib_utils, INPUT_DATA_PATTERNS

_logger = logging.getLogger(__name__)


def _init_job_dirs(jobs_dir: Path, name: str) -> tuple[Path, Path, Path, Path]:
    job_dir = jobs_dir / name
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    job_data_dir = job_dir / "data"
    os.makedirs(job_dir)
    os.makedirs(output_dir)
    return job_dir, input_dir, output_dir, job_data_dir


def _populate_input_dir(flexpart_dir: Path, input_dir: Path) -> None:
    options_dir = flexpart_dir / "share" / "options"
    mch_options_dir = flexpart_dir / "share" / "options.meteoswiss"
    shutil.copytree(mch_options_dir, options_dir, dirs_exist_ok=True)
    shutil.copytree(options_dir, input_dir)
    shutil.copy(options_dir / "OUTGRID.f", input_dir / "OUTGRID")


def _collect_data_paths(data_dir: Path) -> list[Path]:
    data_paths: list[Path] = []
    for ftype in INPUT_DATA_PATTERNS:
        data_paths.extend(sorted(data_dir.glob(ftype)))
    return data_paths


def _write_pathnames(job_dir: Path, input_dir: Path, output_dir: Path, job_data_dir: Path, available_path: Path) -> None:
    lines = [
        f"{input_dir}/\n",
        f"{output_dir}/\n",
        f"{job_data_dir}/\n",
        f"{available_path}\n",
        "============================================\n",
    ]
    (job_dir / "pathnames").write_text("".join(lines), encoding="utf-8")


def validate_env(data: dict[str, str | None]) -> None:
    violations: list[str] = []
    for parameter in EnvironmentParameters:
        if parameter.name not in data:
            violations.append(parameter.name)
        elif data[parameter.name] is None:
            violations.append(parameter.name)

    if violations:
        raise RuntimeError(f"Environment is missing variables needed to prepare runtime configuration: {violations}")


def parse_env() -> dict[str, str | None]:
    return {"IBDATE": os.getenv("IBDATE"),
            "IBTIME": os.getenv("IBTIME"),
            "IEDATE": os.getenv("IEDATE"),
            "IETIME": os.getenv("IETIME")}


def prepare_job_directory(configuration: dict, jobs_dir: Path, flexpart_dir: Path, data_dir: Path, openmp_config: OpenMPConfig) -> Path:
    job_dir, input_dir, output_dir, job_data_dir = _init_job_dirs(jobs_dir, configuration["name"])

    _populate_input_dir(flexpart_dir, input_dir)

    namelists: list[Path] = [input_dir / "COMMAND", *input_dir.glob("RELEASES*")]
    for nl in namelists:
        _configure_namelist(configuration, nl)

    available_path = input_dir / "AVAILABLE"
    _generate_available(available_path, _collect_data_paths(data_dir))

    os.symlink(data_dir, job_data_dir)
    _write_pathnames(job_dir, input_dir, output_dir, job_data_dir, available_path)

    _write_job_script(job_dir / "job", flexpart_dir / "bin" / "FLEXPART", openmp_config)
    return job_dir


def render_template(
        template_path: Path,
        output_path: Path,
        release_list: list[str] | None,
        data: dict[str, str | None]) -> None:
    """Fill Jinja template of runtime configuration with runtime config stored in `data`."""

    _logger.info("Rendering templates")
    with open(template_path, 'r', encoding="utf-8") as file:
        template_content = file.read()

    env = Environment(loader=FileSystemLoader(template_path.parent), autoescape=True)

    rendered_content = env.from_string(template_content).render(data=data)

    with open(output_path, 'w', encoding="utf-8") as output_file:
        output_file.write(rendered_content)

    if release_list:
        _filter_config(output_path, release_list)


def _filter_config(yaml_file: Path, release_sites: list[str]) -> None:
    """Filters the runtime configuration yaml to contain only the release site that will be run."""

    with open(yaml_file, 'r', encoding='utf-8') as file:
        data = yaml.load(file, Loader=yaml.Loader)

    filtered_sections = [section for section in data if section['name'] in release_sites]

    with open(yaml_file, 'w', encoding='utf-8') as file:
        yaml.dump(filtered_sections, file)



def _write_job_script(file_path: Path | str,
                     flexpart_exe: Path | str,
                     openmp_config: OpenMPConfig) -> None:
    """Writes the final bash script that will execute Flexpart"""

    with open(file_path, 'w', encoding="utf-8") as f:
        f.writelines([
            '#!/bin/bash\n',
            f'export OMP_NUM_THREADS={openmp_config.num_threads}\n\n',
            f'export OMP_STACKSIZE={openmp_config.stack_size}\n\n',
            'ulimit -s unlimited\n\n',
            f'export FLEXPART_EXE={flexpart_exe}\n',
            '$FLEXPART_EXE -vvv\n'])


def _generate_available(path: Path, data_paths: list[Path]) -> None:
    with open(path, 'w', encoding="utf-8") as f:
        f.writelines([
            'DATE     TIME        FILENAME\n'
            'YYYYMMDD HHMISS\n'
            '________ ______      __________________\n'
        ])
        _logger.info('Writing lines to AVAILABLE file')
        for file in data_paths:
            step_datetime = _get_valid_datetime(file)
            adate, atime = datetime.strftime(step_datetime, '%Y%m%d'), datetime.strftime(step_datetime, '%H')
            entry = f'{str(adate)} {atime:02}0000      {file.name}\n'
            f.write(entry)
            _logger.info(entry)


def _get_valid_datetime(
        path: Path,
        md: grib_utils.GribMetadata | None = None,
        step_unit: str = 'hours') -> datetime:
    """
    Using GRIB metadata (date,time,step) from within the file (path), calculate the valid time of the data.
    Valid time is the forecast start time plus the time until that certain step.
    """
    if not md:
        md = grib_utils.extract_metadata_from_grib_file(path)

    leadtime_0 = datetime.strptime(md.date + md.time, '%Y%m%d%H%M')

    if step_unit == 'minutes':
        return leadtime_0 + timedelta(minutes = md.step)

    if step_unit == 'hours':
        return leadtime_0 + timedelta(hours = md.step)

    raise ValueError(f"Steps must be provided in either minutes or hours, not {step_unit.lower()}")


def _configure_namelist(config: dict, namelist: Path) -> None:
    """Using values from the runtime configuration, modify various default values of the namelist."""

    with open(namelist, 'r', encoding="utf-8") as file:
        filedata = file.read()

    if (nl_type := namelist.name.lower().split('.')[0]) not in ('command', 'releases'):
        raise RuntimeError('Namelist to be configured must be one of COMMAND/RELEASES*')

    for key, new_value in config[nl_type].items():

        if key in ('IBTIME', 'IETIME', 'ITIME1', 'ITIME2'):
            new_value = f'{new_value:06}'
        elif key in ('COMMENT'):
            new_value = f'\"{new_value}\"'

        if key in ('LAT1', 'LON1', 'Z1'):
            keys = [key, key[:-1]+'2']
        else:
            keys = [key]

        for key in keys:
            filedata = re.sub(key+r'\s*?= *?\d*(.\d*)*,.*',
                                key+f'={new_value},', filedata)

    with open(namelist, 'w', encoding="utf-8") as file:
        file.write(filedata)


def _list_objects(table: DBTable, forecast_date: str, forecast_time: str) -> dict[str, grib_utils.GribMetadata]:
    if table.backend_type == "dynamodb":
        return s3_utils.list_objs_in_bucket_via_dynamodb(table=table, date=forecast_date, time=forecast_time)
    if table.backend_type == "sqlite":
        return s3_utils.list_objs_in_bucket_via_sqlite(table=table, date=forecast_date, time=forecast_time)
    raise ValueError(f"Unsupported backend type: {table.backend_type}")


def _select_keys_in_window(
    objs: dict[str, grib_utils.GribMetadata],
    start_dt: datetime,
    end_dt: datetime,
    step_unit: str,
) -> list[str]:
    subset: list[str] = []
    for key, metadata in objs.items():
        file_validtime = _get_valid_datetime(Path(key), metadata, step_unit)
        if start_dt <= file_validtime <= end_dt:
            subset.append(f"dispf{file_validtime.strftime('%Y%m%d%H')}")
    return subset


def _get_start_end(config: dict) -> tuple[datetime, datetime]:

    start = str(config['IBDATE']) + f"{config['IBTIME']:06}"
    end = str(config['IEDATE']) + f"{config['IETIME']:06}"

    start_dt = datetime.strptime(start, '%Y%m%d%H%M%S')
    end_dt = datetime.strptime(end, '%Y%m%d%H%M%S')

    return start_dt, end_dt


def select_files(config: dict, table: DBTable, forecast_datetime: str, step_unit: str) -> list[str]:
    step_unit = step_unit.lower()
    if step_unit not in ("minutes", "hours"):
        raise ValueError(f"Steps must be provided in either minutes or hours, not {step_unit}")

    forecast_date = forecast_datetime[:8]
    forecast_time = forecast_datetime[8:12]

    objs = _list_objects(table, forecast_date, forecast_time)
    if not objs:
        raise RuntimeError(f"There is no data in S3 matching the filter forecast datetime: {forecast_datetime}")

    start_dt, end_dt = _get_start_end(config)

    forecast_ref = datetime.strptime(forecast_date + forecast_time, "%Y%m%d%H%M")
    if start_dt > forecast_ref:
        start_dt -= timedelta(hours=1)

    subset = _select_keys_in_window(objs, start_dt, end_dt, step_unit)

    if not subset:
        raise RuntimeError(f"No S3 objects had metadata with validity time between {start_dt} and {end_dt}.")

    return subset

