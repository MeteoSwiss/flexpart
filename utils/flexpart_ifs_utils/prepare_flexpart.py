"""
The module contains functions required to setup the input files needed to run Flexpart.
This involves configuring the input namelists (such as COMMAND, AVAILABLE, RELEASES, OUTGRID)
based on a set of environment variables, symlinking the data into the job folder
and writing the job script with the relevent paths to the input files.
"""

import logging
import os
import shutil
from datetime import timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from flexpart_ifs_utils.config.service_settings import OpenMPConfig
from flexpart_ifs_utils.grib_utils import _get_valid_datetime
from flexpart_ifs_utils.job_config import JobConfig
from flexpart_ifs_utils.model import MODEL_PREFIX, Model
from flexpart_ifs_utils.site_config import SiteConfig
from flexpart_ifs_utils.s3_utils import list_objs_in_bucket, _select_keys_in_window

_logger = logging.getLogger(__name__)

# The namelists rendered from templates/, rather than copied from the packaged options directories.
_NAMELIST_TEMPLATES = ("COMMAND", "RELEASES")


def _init_job_dirs(jobs_dir: Path, name: str) -> tuple[Path, Path, Path, Path]:
    job_dir = jobs_dir / name
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    job_data_dir = job_dir / "data"
    os.makedirs(job_dir)
    os.makedirs(output_dir)
    return job_dir, input_dir, output_dir, job_data_dir


def _populate_input_dir(flexpart_dir: Path, input_dir: Path, model: Model) -> None:
    # COMMAND and RELEASES are rendered from templates/, so the packaged skeletons are skipped -
    # and with them the archived per-site RELEASES.bez/.goe/.cherno/... variants, which the old
    # regex-substitution pass used to patch and leave behind in the job's input directory.
    skip_namelists = shutil.ignore_patterns(*_NAMELIST_TEMPLATES, "RELEASES.*")
    options_dir = flexpart_dir / "share" / "options"
    mch_options_dir = flexpart_dir / "share" / "options.meteoswiss"
    shutil.copytree(options_dir, input_dir, ignore=skip_namelists)
    shutil.copytree(mch_options_dir, input_dir, dirs_exist_ok=True, ignore=skip_namelists)
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
    site: SiteConfig,
    job: JobConfig,
    jobs_dir: Path,
    flexpart_dir: Path,
    data_dir: Path,
    openmp_config: OpenMPConfig,
    model: Model,
) -> Path:
    job_dir, input_dir, output_dir, job_data_dir = _init_job_dirs(jobs_dir, site.name)

    _populate_input_dir(flexpart_dir, input_dir, model)

    render_namelists(flexpart_dir / "share" / "templates", input_dir, site, job)

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


def _fp_date(moment: "object") -> str:
    """Flexpart's namelist date encoding, YYYYMMDD."""
    return moment.strftime("%Y%m%d")  # type: ignore[attr-defined]


def _fp_time(moment: "object") -> str:
    """Flexpart's namelist time encoding, HHMISS.

    Six digits, so minute and second resolution is expressible. The retired site-config templates
    concatenated an hour with a literal '0000', which is why offsets could only ever be whole hours.
    """
    return moment.strftime("%H%M%S")  # type: ignore[attr-defined]


def _fortran_real(value: float) -> str:
    """Format a mass as the Fortran real literal the namelist has always carried, e.g. 2.8800E10.

    The site config holds the mass as a number, so it cannot silently mean two different things
    depending on whether someone quoted it in YAML. Fortran's namelist reader accepts an exponent
    with or without a sign; the unsigned form is kept to match what the namelist held before.
    """
    return f"{value:.4E}".replace("E+", "E")


def render_namelists(
    templates_dir: Path,
    input_dir: Path,
    site: SiteConfig,
    job: JobConfig,
) -> None:
    """Render COMMAND and RELEASES from the packaged control-file templates.

    Replaces a regex-substitution pass over the packaged skeletons, which could only set keys that
    already appeared in them and silently ignored anything else. ``StrictUndefined`` makes the
    equivalent mistake here - referencing a field the config does not carry - a hard failure.

    The rendered files are logged in full: this is the only way to confirm from a task's logs that the
    S3 site object, the offsets and the template composed into the namelist that Flexpart actually ran.
    """
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["fp_date"] = _fp_date
    env.filters["fp_time"] = _fp_time
    env.filters["fortran_real"] = _fortran_real

    for name in _NAMELIST_TEMPLATES:
        rendered = env.get_template(f"{name}.j2").render(site=site, job=job)
        (input_dir / name).write_text(rendered, encoding="utf-8")
        _logger.info("Rendered %s namelist for site %s:\n%s", name, site.name, rendered)


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


def select_files(
    job: JobConfig,
    step_unit: str,
    model: Model,
) -> list[str]:
    """Pick the input GRIB whose valid times cover the job's simulation window."""

    step_unit = step_unit.lower()
    if step_unit not in ("minutes", "hours"):
        raise ValueError(
            "Steps must be provided in either minutes or hours, not "
            f"{step_unit}"
        )

    start_dt = job.simulation_start

    if start_dt > job.forecast_datetime:
        # Flexpart de-accumulates precipitation across steps, so it needs the step before the
        # simulation start as well.
        if model == Model.IFS_HRES:
            start_dt -= timedelta(hours=3)
        elif model == Model.IFS_HRES_EUROPE:
            start_dt -= timedelta(hours=1)
        else:
            raise ValueError(f"Unsupported model: {model}")

    objs = list_objs_in_bucket(
        start_time=start_dt,
        end_time=job.simulation_end,
    )

    filtered_objs = _select_keys_in_window(objs, start_dt, job.simulation_end, step_unit)

    if not filtered_objs:
        raise RuntimeError(
            f"There are no s3 objects for valid times between {start_dt} and {job.simulation_end}"
        )

    return filtered_objs
