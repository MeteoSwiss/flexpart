ARG container_registry
ARG base_tag=v0.2.0

FROM ${container_registry}/flexpart-poc/spack-dependencies:${base_tag} as intermediate

RUN mkdir -p /scratch/spack-env/ 
COPY spack.yaml /scratch/spack-env/spack.yaml
RUN  spack env create spack-env /scratch/spack-env/spack.yaml

RUN apt-get -yqq update \
    && apt-get -yqq install --no-install-recommends \
    zlib1g && spack external find

RUN spack env activate -p spack-env && spack concretize && spack install

FROM ${container_registry}/flexpart-poc/spack-dependencies:${base_tag}

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

# Unset proxy for use outside MCH
ENV HTTP_PROXY= \
   http_proxy= \
   HTTPS_PROXY= \
   https_proxy= \
   NO_PROXY= \
   no_proxy= 

ENTRYPOINT ["/bin/bash", "/scratch/entrypoint.sh"]

CMD [""]
