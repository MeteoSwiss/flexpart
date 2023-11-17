ARG container_registry
FROM ${container_registry}/flexpart-poc/spack-dependencies:v0.0.0 as intermediate

ARG TOKEN_FLEXPART
ARG SPACK_TAG=v0.18.1.12

# Prevent docker to cache git clones if the are changes in repo
ADD https://x-access-token:${TOKEN_FLEXPART}@api.github.com/repos/MeteoSwiss-APN/flexpart-fdb/git/refs/heads/fdb version_flexpart.json
ADD https://api.github.com/repos/C2SM/spack-c2sm/git/refs/tags/${SPACK_TAG} version_c2sm.json
RUN git config --global url."https://x-access-token:${TOKEN_FLEXPART}@github.com/MeteoSwiss-APN/".insteadOf "ssh://git@github.com/MeteoSwiss-APN/"

RUN mkdir -p /scratch/spack-env/ 
COPY spack.yaml /scratch/spack-env/spack.yaml
RUN  spack env create spack-env /scratch/spack-env/spack.yaml

RUN apt-get -yqq update \
    && apt-get -yqq install --no-install-recommends \
    zlib1g && spack external find

RUN spack env activate -p spack-env && spack concretize && spack install

FROM ${container_registry}/flexpart-poc/spack-dependencies:v0.0.0

RUN mkdir -p \
    /opt/spack/ \
    /root/c2sm-spack/ \
    /scratch/flexpart_output \
    /fdb_root/fdb_root \
    /data

COPY --from=intermediate /opt/spack/ /opt/spack/
COPY --from=intermediate /root/c2sm-spack/ /root/c2sm-spack/
COPY --from=intermediate /scratch /scratch


WORKDIR /scratch
COPY entrypoint.sh /scratch/entrypoint.sh 
COPY sandbox_generator.py /scratch/sandbox_generator.py
COPY upload_s3.py /scratch/upload_s3.py
RUN ["chmod", "+x", "/scratch/sandbox_generator.py"]
RUN ["chmod", "+x", "/scratch/upload_s3.py"]
COPY genconf.yml /scratch/genconf.yml
COPY fdb_schema /scratch/fdb_schema
COPY IGBP_int1.dat /data/IGBP_int1.dat

RUN pip3 install pyyaml boto3

# Unset proxy
ENV HTTP_PROXY= \
   http_proxy= \
   HTTPS_PROXY= \
   https_proxy= \
   NO_PROXY= \
   no_proxy= 

ENTRYPOINT ["/bin/bash", "/scratch/entrypoint.sh"]

CMD [""]
