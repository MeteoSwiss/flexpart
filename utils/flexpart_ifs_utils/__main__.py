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

import os
import sys
import argparse
import logging
from pathlib import Path

import yaml
from flexpart_ifs_utils.prepare_flexpart import (
    validate_env,
    parse_env,
    prepare_job_directory,
    render_template,
    select_files,
    _path_list)
from flexpart_ifs_utils.s3_utils import (
    download_keys_from_bucket,
    upload_directory)
from flexpart_ifs_utils.model import Domain
from flexpart_ifs_utils import CONFIG


if __name__ == '__main__':

    _logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser()
    sp = parser.add_subparsers()

    p1 = sp.add_parser('upload')
    p1.add_argument('-d', '--directory',
                    help='Specify the jobs directory containing output to upload to S3.',
                    required=True,
                    type=Path,
                    )
    p1.add_argument('-i', '--input',
                    help='Specify the path to the input data from which the output S3 object metadata can be defined.',
                    required=True,
                    type=Path,
                    )
    p1.add_argument('-s', '--site',
                    help='Specify the release site.',
                    required=True
                    )

    p2 = sp.add_parser('generate')
    p2.add_argument('-f', '--flexpart_dir',
                    help='Specify the Flexpart directory.',
                    required=True,
                    type=Path,
                    )
    p2.add_argument('-j', '--jobs_dir',
                    help='Specify the jobs directory.',
                    required=True,
                    type=Path,
                    )
    p2.add_argument('-d', '--datetime',
                    help='Specify the forecast datetime, in format YYYYMMDDHH.',
                    required=True
                    )
    p2.add_argument('-s', '--site',
                    help='Specify the release site.',
                    required=True
                    )
    p2.add_argument('--domain',
                    help='Specify the domain of the Flexpart run. Global domain runs use nested domain over Europe.',
                    type=str.upper,
                    choices=[d.name for d in Domain],
                    required=True
                    )
    args = parser.parse_args()

    if "directory" in args:
        upload_directory(args.directory, args.input, args.site, parent='output')
        sys.exit(0)

    FORECAST_DATETIME: str = args.datetime
    RELEASE_SITE: str = args.site
    JOBS_DIR: Path = args.jobs_dir
    FLEXPART_DIR: Path = args.flexpart_dir
    DOMAIN: Domain = Domain[args.domain]

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

    data_paths = []

    # Check if data already exists for the domain
    if DOMAIN == Domain.GLOBAL:
        data_paths.extend(_path_list(DATA_DIR, domain=DOMAIN) )
    elif DOMAIN == Domain.EUROPE:
        data_paths.extend(_path_list(DATA_DIR, domain=DOMAIN) )

    if not data_paths:
        # Search the db for the relevant files and download data
        keys = select_files(config['command'],
                            table=CONFIG.main.aws.db_table,
                            forecast_datetime=FORECAST_DATETIME,
                            step_unit=CONFIG.main.input.step_unit,
                            domain=DOMAIN)

        download_keys_from_bucket(keys, DATA_DIR, CONFIG.main.aws.s3.nwp_model_data)

    job_dir = prepare_job_directory(
        config,
        JOBS_DIR,
        FLEXPART_DIR,
        DATA_DIR,
        CONFIG.main.openmp_config,
        domain=DOMAIN)
