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
        --datetime <YYYYMMDDhhmm>
        --site <site>

    python __main__.py upload -d <jobs_dir> -i <input_directory>
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from flexpart_ifs_utils import CONFIG
from flexpart_ifs_utils.job_config import resolve_job_config
from flexpart_ifs_utils.model import Model
from flexpart_ifs_utils.prepare_flexpart import (_path_list,
                                                 prepare_job_directory,
                                                 select_files)
from flexpart_ifs_utils.s3_utils import (canonicalize_output_names,
                                         download_keys_from_bucket,
                                         upload_output)
from flexpart_ifs_utils.site_config import load_site_config

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
                    help='Forecast reference datetime, in format YYYYMMDDhhmm.',
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
                    help='Forecast reference datetime, in format YYYYMMDDhhmm.',
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
        # Rename before upload, so the object key never carries Flexpart's simulation-start stamp -
        # that stamp is what forced the render step and the ensemble aggregator to re-derive the
        # release offset, and it is why the offset could not vary per site.
        canonicalize_output_names(args.directory / args.site / 'output')
        upload_output(args.directory, args.site, args.datetime, parent='output')
        sys.exit(0)

    FORECAST_DATETIME: str = args.datetime
    RELEASE_SITE: str = args.site
    JOBS_DIR: Path = args.jobs_dir
    FLEXPART_DIR: Path = args.flexpart_dir
    MODEL: Model = Model(args.model)

    if not os.path.exists( JOBS_DIR ):
        os.makedirs( JOBS_DIR )

    _logger.info('FLEXPART directory: %s', FLEXPART_DIR)
    _logger.info('Jobs directory: %s', JOBS_DIR)
    _logger.debug('Args: %s', args)

    # The site catalog is owned by dispersionmodelling-deployment and published to S3 by
    # Terraform, one object per site actually configured for this environment - an unknown
    # RELEASE_SITE_NAME fails here (S3 404) rather than matching against a locally-packaged
    # catalog that could silently be stale relative to Terraform's config.
    site_config_key = f'{CONFIG.main.runtime_config.site_config_key_prefix}{RELEASE_SITE}.yaml'
    download_keys_from_bucket([site_config_key], JOBS_DIR, CONFIG.main.aws.s3.site_config)

    # Plain declarative site data - no longer a Jinja template of the namelist, so there is nothing
    # to render here and no intermediate file. The namelist templates live in the image.
    site = load_site_config(JOBS_DIR / f'{RELEASE_SITE}.yaml')
    # On-demand runs may override the site's own offsets for this one job; scheduled runs leave
    # this empty, in which case the site's config applies. See resolve_job_config.
    overrides = json.loads(os.getenv('JOB_OVERRIDES', '{}'))
    job = resolve_job_config(FORECAST_DATETIME, MODEL, site, overrides)

    DATA_DIR = JOBS_DIR / 'data'
    if not os.path.exists( DATA_DIR ):
        os.makedirs( DATA_DIR )

    # Check if data already exists for the domain
    data_paths = _path_list(DATA_DIR, MODEL)

    if not data_paths:
        # Search the db for the relevant files and download data
        keys = select_files(job,
                            step_unit=CONFIG.main.input.step_unit,
                            model=MODEL)

        download_keys_from_bucket(keys, DATA_DIR, CONFIG.main.aws.s3.nwp_model_data)

    job_dir = prepare_job_directory(
        site,
        job,
        JOBS_DIR,
        FLEXPART_DIR,
        DATA_DIR,
        CONFIG.main.openmp_config,
        model=MODEL)
