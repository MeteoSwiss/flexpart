#!/bin/bash

# This entrypoint script is the default script run by the Flexpart-IFS container at runtime.
#
# The script calls the flexpart_ifs_utils library first to generate the Flexpart input data in the job folder $JOBS_DIR.
# This involves configurnig the input namelists (such as COMMAND, AVAILABLE, RELEASES, OUTGRID) based on a set of environment variables,
# symlinking the data into the job folder, and writing the job script with the relevent paths to the input files.
#
# Then the job for RELEASE_SITE_NAME is run - this runs Flexpart.
#
# Finally the flexpart_ifs_utils library is called to upload the output of Flexpart to an S3 bucket.

set -e


SCRIPT_DIR=$(realpath "$(dirname "$0")")
echo "Current working directory '$SCRIPT_DIR'"

# Prepare input files for Flexpart-IFS
python -m flexpart_ifs_utils generate \
    --flexpart_dir $FLEXPART_PREFIX \
    --jobs_dir $JOBS_DIR \
    --datetime $FORECAST_DATETIME \
    --site $RELEASE_SITE_NAME \
    --model $MODEL

echo JOBS_DIR: $JOBS_DIR

echo Running Flexpart IFS for release site: $RELEASE_SITE_NAME
cd $JOBS_DIR/$RELEASE_SITE_NAME
# Run Flexpart-IFS
bash job

cd $SCRIPT_DIR
# Upload output files of Flexpart-IFS to S3 bucket.
python -m flexpart_ifs_utils upload \
    --directory $JOBS_DIR \
    --site $RELEASE_SITE_NAME \
    --datetime $FORECAST_DATETIME \
    --run-id $RUN_ID
