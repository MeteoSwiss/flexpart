"""
This module prepares input files and data for running Flexpart-IFS, a Lagrangian particle dispersion model.
The module handles the following tasks:
- Downloading the model and static input data from S3 if not available locally.
- Symlinking the necessary model and static data into the job folder.
- Configuring input namelists (such as COMMAND, AVAILABLE, RELEASES, OUTGRID) based on a set of environment variables.
- Writing the job script with the relevant paths to the input files.
- Uploading the job output to an S3 bucket.

The main script can be used with the following commands:
1. `generate`: Generate the necessary input files and setup the job directory for Flexpart.
2. `upload`: Upload the output directory to an S3 bucket.

Usage:

    python __main__.py generate
        -f <flexpart_dir>
        -j <jobs_dir>
        --datetime <YYYYMMDDHH>
        --site BEZ

    python __main__.py upload -d <jobs_dir> -i <input_directory>
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

from flexpart_ifs_utils import CONFIG
from flexpart_ifs_utils.model import EnvironmentParameters, Model
from flexpart_ifs_utils.prepare_flexpart import (_path_list,
                                                 prepare_job_directory,
                                                 render_template, select_files)
from flexpart_ifs_utils.s3_utils import (download_keys_from_bucket,
                                         upload_output)


def validate_env(data: dict[str, str | None]) -> None:
    violations: list[str] = []
    for parameter in EnvironmentParameters:
        if parameter.name not in data:
            violations.append(parameter.name)
        elif data[parameter.name] is None:
            violations.append(parameter.name)

    if violations:
        raise RuntimeError(
            "Environment is missing variables needed to prepare runtime configuration: "
            f"{violations}"
        )


def parse_env() -> dict[str, str | None]:
    return {"EMISSION_START_YYYY": os.getenv("EMISSION_START_YYYY"),
            "EMISSION_START_MM": os.getenv("EMISSION_START_MM"),
            "EMISSION_START_DD": os.getenv("EMISSION_START_DD"),
            "EMISSION_START_ZZ": os.getenv("EMISSION_START_ZZ"),
            "EMISSION_END_YYYY": os.getenv("EMISSION_END_YYYY"),
            "EMISSION_END_MM": os.getenv("EMISSION_END_MM"),
            "EMISSION_END_DD": os.getenv("EMISSION_END_DD"),
            "EMISSION_END_ZZ": os.getenv("EMISSION_END_ZZ"),
            "SIMULATION_END_YYYY": os.getenv("SIMULATION_END_YYYY"),
            "SIMULATION_END_MM": os.getenv("SIMULATION_END_MM"),
            "SIMULATION_END_DD": os.getenv("SIMULATION_END_DD"),
            "SIMULATION_END_ZZ": os.getenv("SIMULATION_END_ZZ")}


if __name__ == '__main__':

    _logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser()
    sp = parser.add_subparsers()

    p1 = sp.add_parser('upload')
    p1.add_argument('--directory',
                    help='The jobs directory containing output to upload to S3.',
                    required=True,
                    type=Path,
                    )
    p1.add_argument('--site',
                    help='Release site.',
                    required=True
                    )
    p1.add_argument('--datetime',
                    help='Forecast datetime, in format YYYYMMDDHH.',
                    required=True
                    )

    p2 = sp.add_parser('generate')
    p2.add_argument('--flexpart_dir',
                    help='Directory where the Flexpart binary lives.',
                    required=True,
                    type=Path,
                    )
    p2.add_argument('--jobs_dir',
                    help='Path of the jobs directory.',
                    required=True,
                    type=Path,
                    )
    p2.add_argument('--datetime',
                    help='Forecast datetime, in format YYYYMMDDHH.',
                    required=True
                    )
    p2.add_argument('--site',
                    help='Release site.',
                    required=True
                    )
    p2.add_argument('--model',
                    help='IFS model used by Flexpart. IFS-Global runs use nested domain over Europe (IFS-Europe).',
                    type=str,
                    choices=[m.value for m in Model],
                    required=True
                    )
    args = parser.parse_args()

    if "directory" in args:
        upload_output(args.directory, args.site, args.datetime, parent='output')
        sys.exit(0)

    FORECAST_DATETIME: str = args.datetime
    RELEASE_SITE: str = args.site
    JOBS_DIR: Path = args.jobs_dir
    FLEXPART_DIR: Path = args.flexpart_dir
    MODEL: Model = Model(args.model)

    WORKDIR: Path = Path(os.path.abspath(__file__)).parent
    CONFIG_TEMPLATE_PATH = WORKDIR / 'runtime_configuration.j2'
    CONFIG_PATH =  JOBS_DIR / (CONFIG_TEMPLATE_PATH.stem + '.yaml')

    if not os.path.exists( JOBS_DIR ):
        os.makedirs( JOBS_DIR )

    _logger.info('FLEXPART directory: %s', FLEXPART_DIR)
    _logger.info('Jobs directory: %s', JOBS_DIR)
    _logger.debug('Args: %s', args)

    environment = parse_env()

    validate_env(environment)

    render_template(CONFIG_TEMPLATE_PATH, CONFIG_PATH, [RELEASE_SITE], environment)

    with open(CONFIG_PATH, 'r', encoding="utf-8") as f:
        configs = yaml.safe_load(f)

    configs = [config for config in configs if config['name'] == RELEASE_SITE]
    if not configs:
        raise RuntimeError(f'Release site {RELEASE_SITE} does not match any known to Flexpart.')
    if len(configs) > 1:
        raise RuntimeError(f'Release site {RELEASE_SITE} matches multiple configs.')
    config = configs[0]

    DATA_DIR = JOBS_DIR / 'data'
    if not os.path.exists( DATA_DIR ):
        os.makedirs( DATA_DIR )

    # Check if data already exists for the domain
    data_paths = _path_list(DATA_DIR, MODEL)

    if not data_paths:
        # Search the db for the relevant files and download data
        keys = select_files(config['command'],
                            forecast_datetime=FORECAST_DATETIME,
                            step_unit=CONFIG.main.input.step_unit,
                            model=MODEL)

        download_keys_from_bucket(keys, DATA_DIR, CONFIG.main.aws.s3.nwp_model_data)

    job_dir = prepare_job_directory(
        config,
        JOBS_DIR,
        FLEXPART_DIR,
        DATA_DIR,
        CONFIG.main.openmp_config,
        model=MODEL)
