"""
__main__.py

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
    select_files)
from flexpart_ifs_utils.s3_utils import (
    download_keys_from_bucket,
    upload_directory)
from flexpart_ifs_utils import CONFIG, INPUT_DATA_PATTERNS


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
                    help='Specify the release site in short form (ie BEZ/LEI..).',
                    type=str.upper,
                    choices=['BEZ', 'LEI', 'GOE', 'MUE', 'FES', 'BUG'],
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
                    help='Specify the forecast datetime, in format YYYYMMDDhhmm.',
                    required=True
                    )
    p2.add_argument('-s', '--site',
                    help='Specify the release site in short form (ie BEZ/LEI..).',
                    type=str.upper,
                    choices=['BEZ', 'LEI', 'GOE', 'MUE', 'FES', 'BUG'],
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

    if RELEASE_SITE:
        configs = [config for config in configs if config['name'] == RELEASE_SITE]
        if not configs:
            raise RuntimeError(f'Release site {RELEASE_SITE} does not match any known to Flexpart.')

    DATA_DIR = JOBS_DIR / 'data'
    if not os.path.exists( DATA_DIR ):
        os.makedirs( DATA_DIR )

    data_paths = []

    for ftype in INPUT_DATA_PATTERNS:
        data_paths.extend(sorted(DATA_DIR.glob(ftype)) )

    # Download input data
    if not data_paths:
        keys = select_files(configs[0]['command'],
                            table = CONFIG.main.aws.db.nwp_model_data, # Could be DynamoDB table or SQLite DB path
                            forecast_datetime = FORECAST_DATETIME,
                            step_unit = CONFIG.main.input.step_unit)

        download_keys_from_bucket(keys, DATA_DIR, CONFIG.main.aws.s3.nwp_model_data)

    for config in configs:
        job_dir = prepare_job_directory(config, JOBS_DIR, FLEXPART_DIR, DATA_DIR, CONFIG.main.openmp_config)
