#!/bin/bash

set -e

workdir=$(pwd)

. $SPACK_ROOT/share/spack/setup-env.sh
spack env activate spack-env

flexpart_prefix=`spack location -i flexpart-ifs`

# Copy the contents of MCH options into to the shared options directory.
cp -r ${flexpart_prefix}/share/options.meteoswiss/* ${flexpart_prefix}/share/options

./sandbox_generator.py --flexpart_dir ${flexpart_prefix} --sandbox_dir ${workdir}/sandbox;

cd ${workdir}/sandbox

#Run Flexpart job
bash job

# Upload results to S3 Bucket

cd ${workdir}
./upload_s3.py --directory ${workdir}/sandbox/output


# Additionally move results to mounted NFS
mv ${workdir}/sandbox ${workdir}/flexpart_output/$(date '+%d%m%y%H%M%S')
