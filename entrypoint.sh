#!/bin/bash

# This entrypoint script is the default script run by the Flexpart-IFS container at runtime.
#
# The script calls the flexpart_ifs_utils library first to generate the Flexpart input data in the job folder $JOBS_DIR. 
# This involves configurnig the input namelists (such as COMMAND, AVAILABLE, RELEASES, OUTGRID) based on a set of environment variables, 
# symlinking the data into the job folder, and writing the job script with the relevent paths to the input files.
#
# Then the job files for each release site in runtime_configuration.yaml are run - this runs Flexpart.
#
# Finally the flexpart_ifs_utils library is called to upload the output of Flexpart to an S3 bucket.

set -e

# First unset the proxy environment variables if running at AWS or CSCS
if [ "$DEPLOY_SITE" == "AWS" ] || [ "$DEPLOY_SITE" == "CSCS" ]; then
    echo "Deploy location is $DEPLOY_SITE. Unsetting proxy environment variables..."

    unset http_proxy
    unset https_proxy
    unset ftp_proxy
    unset no_proxy

    unset HTTP_PROXY
    unset HTTPS_PROXY
    unset FTP_PROXY
    unset NO_PROXY

    echo "Proxy environment variables have been unset."
else
    echo "Deploy location is not AWS or CSCS. Proxy environment variables remain set."
fi

# Prepare input files for Flexpart-IFS
python3.11 -m flexpart_ifs_utils generate \
    --flexpart_dir $FLEXPART_PREFIX \
    --jobs_dir $JOBS_DIR \
    --datetime $FORECAST_DATETIME \
    --site $RELEASE_SITE_NAME

echo JOBS_DIR: $JOBS_DIR

# Extract names from generated YAML config
names=$(grep -oP 'name: \K.*' $JOBS_DIR/runtime_configuration.yaml)

for name in $names; do
    echo Running Flexpart IFS for release site: $name
    cd $JOBS_DIR/$name
    # Run Flexpart-IFS
    bash job
done

# Upload output files of Flexpart-IFS to S3 bucket.
python3.11 -m flexpart_ifs_utils upload \
    --directory $JOBS_DIR \
    --input ${JOBS_DIR}/data \
    --site $RELEASE_SITE_NAME
