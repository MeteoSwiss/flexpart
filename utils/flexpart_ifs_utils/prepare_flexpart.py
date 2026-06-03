"""
The module contains functions required to setup the input files needed to run Flexpart.
This involves configuring the input namelists (such as COMMAND, AVAILABLE, RELEASES, OUTGRID)
based on a set of environment variables, symlinking the data into the job folder
and writing the job script with the relevent paths to the input files.
"""

import logging
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from flexpart_ifs_utils.config.service_settings import OpenMPConfig
from flexpart_ifs_utils.grib_utils import _get_valid_datetime
from flexpart_ifs_utils.model import MODEL_PREFIX, Model
from flexpart_ifs_utils.s3_utils import list_objs_in_bucket, _select_keys_in_window

_logger = logging.getLogger(__name__)


def _init_job_dirs(jobs_dir: Path, name: str) -> tuple[Path, Path, Path, Path]:
    job_dir = jobs_dir / name
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    job_data_dir = job_dir / "data"
    os.makedirs(job_dir)
    os.makedirs(output_dir)
    return job_dir, input_dir, output_dir, job_data_dir


def _populate_input_dir(flexpart_dir: Path, input_dir: Path, model: Model) -> None:
    options_dir = flexpart_dir / "share" / "options"
    mch_options_dir = flexpart_dir / "share" / "options.meteoswiss"
    shutil.copytree(options_dir, input_dir)
    shutil.copytree(mch_options_dir, input_dir, dirs_exist_ok=True)
    if model == model.IFS_HRES:
        shutil.copy(input_dir / "OUTGRID.g", input_dir / "OUTGRID")
    elif model == model.IFS_HRES_EUROPE:
        shutil.copy(input_dir / "OUTGRID.f", input_dir / "OUTGRID")
    else:
        raise ValueError(f"Unsupported model: {model}")


def _path_list(data_dir: Path, model: Model) -> list[Path]:
    """Return a sorted list of data files for the given domain."""
    return sorted(data_dir.glob(MODEL_PREFIX[model]))


def _write_pathnames(
    job_dir: Path,
    input_dir: Path,
    output_dir: Path,
    job_data_dir: Path,
    available_path: Path,
    available_path_nested: Path | None = None,
) -> None:
    lines = [
        f"{input_dir}/\n",
        f"{output_dir}/\n",
        f"{job_data_dir}/\n",
        f"{available_path}\n",
    ]
    if available_path_nested:
        lines.append(f"{job_data_dir}/\n")
        lines.append(f"{available_path_nested}\n")
    lines.append("============================================\n")

    (job_dir / "pathnames").write_text("".join(lines), encoding="utf-8")

    _logger.info(
        "Written pathnames file with the following content:\n%s",
        "".join(lines),
    )

def prepare_job_directory(
    configuration: dict,
    jobs_dir: Path,
    flexpart_dir: Path,
    data_dir: Path,
    openmp_config: OpenMPConfig,
    model: Model,
) -> Path:
    job_dir, input_dir, output_dir, job_data_dir = _init_job_dirs(
        jobs_dir, configuration["name"]
    )

    _populate_input_dir(flexpart_dir, input_dir, model)

    namelists: list[Path] = [input_dir / "COMMAND", *input_dir.glob("RELEASES*")]
    for nl in namelists:
        _configure_namelist(configuration, nl)

    available_path = input_dir / "AVAILABLE"
    _generate_available(available_path, _path_list(data_dir, model=model))
    available_path_nested = None
    if model == Model.IFS_HRES:
        available_path_nested = input_dir / "AVAILABLE_NESTED"
        _generate_available(available_path_nested, _path_list(data_dir, model=Model.IFS_HRES_EUROPE))

    os.symlink(data_dir, job_data_dir)
    _write_pathnames(job_dir, input_dir, output_dir, job_data_dir, available_path, available_path_nested)

    _write_job_script(
        job_dir / "job",
        flexpart_dir / "bin" / "FLEXPART",
        openmp_config,
    )
    return job_dir


def render_template(
    template_path: Path,
    output_path: Path,
    release_list: list[str] | None,
    data: dict[str, str | None],
) -> None:
    """Fill Jinja template of runtime configuration with runtime config stored in `data`."""
    _logger.info("Rendering templates")
    template_content = template_path.read_text(encoding="utf-8")

    env = Environment(loader=FileSystemLoader(template_path.parent), autoescape=True)
    rendered_content = env.from_string(template_content).render(data=data)

    output_path.write_text(rendered_content, encoding="utf-8")

    if release_list:
        _filter_config(output_path, release_list)


def _filter_config(yaml_file: Path, release_sites: list[str]) -> None:
    """Filters the runtime configuration yaml to contain only the release site that will be run."""
    with open(yaml_file, "r", encoding="utf-8") as file:
        data = yaml.load(file, Loader=yaml.Loader)

    filtered_sections = [section for section in data if section["name"] in release_sites]

    with open(yaml_file, "w", encoding="utf-8") as file:
        yaml.dump(filtered_sections, file)


def _write_job_script(
    file_path: Path | str,
    flexpart_exe: Path | str,
    openmp_config: OpenMPConfig,
) -> None:
    """Writes the final bash script that will execute Flexpart"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(
            [
                "#!/bin/bash\n",
                f"export OMP_NUM_THREADS={openmp_config.num_threads}\n\n",
                f"export OMP_STACKSIZE={openmp_config.stack_size}\n\n",
                "ulimit -s unlimited\n\n",
                f"export FLEXPART_EXE={flexpart_exe}\n",
                "$FLEXPART_EXE -vvv\n",
            ]
        )


def _generate_available(path: Path, data_paths: list[Path]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(
            [
                "DATE     TIME        FILENAME\n"
                "YYYYMMDD HHMISS\n"
                "________ ______      __________________\n"
            ]
        )
        _logger.info("Writing lines to %s file", path.name)
        for file in data_paths:
            step_datetime = _get_valid_datetime(file)
            adate = step_datetime.strftime("%Y%m%d")
            atime = step_datetime.strftime("%H")
            entry = f"{adate} {int(atime):02}0000      {file.name}\n"
            f.write(entry)
            _logger.info(entry)


def _configure_namelist(config: dict, namelist: Path) -> None:
    """Using values from the runtime configuration, modify various default values of the namelist."""
    filedata = namelist.read_text(encoding="utf-8")

    nl_type = namelist.name.lower().split(".")[0]
    if nl_type not in ("command", "releases"):
        raise RuntimeError("Namelist to be configured must be one of COMMAND/RELEASES*")

    for key, new_value in config[nl_type].items():
        if key in ("IBTIME", "IETIME", "ITIME1", "ITIME2"):
            new_value = f"{new_value:06}"
        elif key == "COMMENT":
            new_value = f"\"{new_value}\""

        keys = [key, key[:-1] + "2"] if key in ("LAT1", "LON1", "Z1") else [key]

        for key_ in keys:
            filedata = re.sub(
                key_ + r"\s*?= *?\d*(.\d*)*,.*",
                key_ + f"={new_value},",
                filedata,
            )

    namelist.write_text(filedata, encoding="utf-8")


def _get_start_end(config: dict) -> tuple[datetime, datetime]:
    start = str(config["IBDATE"]) + f"{config['IBTIME']:06}"
    end = str(config["IEDATE"]) + f"{config['IETIME']:06}"

    start_dt = datetime.strptime(start, "%Y%m%d%H%M%S")
    end_dt = datetime.strptime(end, "%Y%m%d%H%M%S")

    return start_dt, end_dt


def select_files(
    config: dict,
    forecast_datetime: str,
    step_unit: str,
    model: Model,
) -> list[str]:

    step_unit = step_unit.lower()
    if step_unit not in ("minutes", "hours"):
        raise ValueError(
            "Steps must be provided in either minutes or hours, not "
            f"{step_unit}"
        )

    start_dt, end_dt = _get_start_end(config)

    forecast_ref = datetime.strptime(forecast_datetime, "%Y%m%d%H%M")

    if start_dt > forecast_ref:
        if model == Model.IFS_HRES:
            start_dt -= timedelta(hours=3)
        elif model == Model.IFS_HRES_EUROPE:
            start_dt -= timedelta(hours=1)
        else:
            raise ValueError(f"Unsupported model: {model}")

    objs = list_objs_in_bucket(
        start_time=start_dt,
        end_time=end_dt,
    )

    filtered_objs = _select_keys_in_window(objs, start_dt, end_dt, step_unit)

    if not filtered_objs:
        raise RuntimeError(
            f"There are no s3 objects for valid times between {start_dt} and {end_dt}"
        )

    return filtered_objs
