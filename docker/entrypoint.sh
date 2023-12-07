#!/bin/bash

set -e

workdir=$(pwd)

fdb_jenkins="false"
s3_flag=""
fdb_flag=""

die() {
  printf '%s\n' "$1" >&2
  exit 1
}


while true; do
  case "$1" in
    -f|--fdb)
      fdb_jenkins="true"
      fdb_flag='--fdb'
      fdb_schema_dir=$workdir/fdb_schema
      if [ -f "$fdb_schema_dir" ]; then
        printf 'FDB Schema: %s\n' $fdb_schema_dir
      else
        die 'ERROR: "fdb_schema" cannot be found.'
      fi
      shift;;
    -s|--fdb-schema)
      if [ "$2" ]; then
        fdb_flag='--fdb'
        fdb_schema_dir=$2
        if [ -f "$fdb_schema_dir" ]; then
          printf 'FDB Schema: %s\n' $fdb_schema_dir
        else
          die 'ERROR: "fdb_schema" cannot be found in any mounted volume.'
        fi
        shift 2
      else
        die 'ERROR: "--fdb_schema" requires a non-empty argument.'
      fi;;
    --s3)
      s3_flag='--s3'
      shift;;
    -s|--fdb-schema?*)
      fdb_schema_dir=${1#*=} # Delete everything up to "=" and assign the remainder.
      printf 'FDB Schema: %s\n' $fdb_schema_dir 
      shift
      ;;
    --)
      shift
      break;;
    -?*)
      printf 'WARN: Unknown option (ignored): %s\n' "$1" >&2
      ;;
     *)
      break
  esac
done

. $SPACK_ROOT/share/spack/setup-env.sh
spack env activate spack-env


if [ -z ${fdb_schema_dir+x} ]; then 
echo "Not using FDB, rather GRIB file input."; 
else 
echo "Using FDB for input."
#FDB config
cat > $workdir/fdb_config.yml <<EOF
type: local
engine: toc
schema: $fdb_schema_dir
spaces:
- handler: Default
  roots:
  - path: /fdb_root/
EOF

export FDB5_CONFIG_FILE=$workdir/fdb_config.yml

export PATH=$PATH:`spack location -i fdb-fortran`
export PATH=$PATH:`spack location -i fdb`/bin

fdb-info --all
fi


if [ $fdb_jenkins == true ]; then

for f in /data/disp*;
    do 
    echo "Archiving $f" ; 
    fdbf-write --keys=generatingProcessIdentifier,productionStatusOfProcessedData,discipline,parameterCategory,dataDate,dataTime,endStep,productDefinitionTemplateNumber,typeOfFirstFixedSurface,level,parameterNumber $f
done

fi

flexpart_prefix=`spack location -i flexpart-ifs`

./sandbox_generator.py --flexpart_dir ${flexpart_prefix} --sandbox_dir ${workdir}/sandbox ${fdb_flag} ${s3_flag}; 

cd ${workdir}/sandbox

#Run Flexpart job
bash job

# Upload results to S3 Bucket

if [ $fdb_jenkins == false ]; then
  cd ${workdir}
  ./upload_s3.py --directory ${workdir}/sandbox/output
fi

# Additionally move results to mounted NFS
mv ${workdir}/sandbox ${workdir}/flexpart_output/$(date '+%d%m%y%H%M%S')
