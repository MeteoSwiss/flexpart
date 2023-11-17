#/bin/bash

podman pull $IMAGE_INTERN
mkdir -p ctx/data && cd ctx/data
mkdir -p ctx/output
data_dir=$(pwd)
wget -q https://nexus.meteoswiss.ch/nexus/repository/app-artifacts-mch/nwp-rzplus/flexpart-poc/flexpart/dispf2023091806
wget -q https://nexus.meteoswiss.ch/nexus/repository/app-artifacts-mch/nwp-rzplus/flexpart-poc/flexpart/dispf2023091807
wget -q https://nexus.meteoswiss.ch/nexus/repository/app-artifacts-mch/nwp-rzplus/flexpart-poc/flexpart/dispf2023091808
wget -q https://nexus.meteoswiss.ch/nexus/repository/app-artifacts-mch/nwp-rzplus/flexpart-poc/flexpart/dispf2023091809
wget -q https://nexus.meteoswiss.ch/nexus/repository/app-artifacts-mch/nwp-rzplus/flexpart-poc/flexpart/dispf2023091810
wget -q https://nexus.meteoswiss.ch/nexus/repository/app-artifacts-mch/nwp-rzplus/flexpart-poc/flexpart/IGBP_int1.dat


podman run --name flexpart-container-test-$BRANCH_NAME -v ${data_dir}:/data:ro $IMAGE_INTERN --fdb
podman cp flexpart-container-test-$BRANCH_NAME:/scratch/flexpart_output ctx/output
[ "$(find ctx/output -name grid_*.nc)" ] && find ctx/output -name grid_*.nc || (echo "No data found in flexpart output folder" && exit 1)
