# Dockerfile to build Flexpart-IFS into an image, also containing the python module to prepare the input data.
FROM dockerhub.apps.cp.meteoswiss.ch/mch/python/builder AS python-builder

COPY utils/poetry.lock utils/pyproject.toml /scratch

RUN cd /scratch \
    && poetry export --without-hashes -o requirements.txt \
    && poetry export --without-hashes --with dev -o requirements_dev.txt

#  FROM ${container_registry}/numericalweatherpredictions/dispersionmodelling/flexpart-ifs/flexpart-base:${base_tag} as spack-builder
FROM localhost/base-0612:latest as spack-builder

ARG TOKEN
ENV TOKEN=$TOKEN 
# RUN git config --global url."https://x-access-token:${TOKEN}@github.com/MeteoSwiss/".insteadOf "git@github.com:MeteoSwiss/"
ARG COMMIT
ENV COMMIT=$COMMIT

# Add Flexpart-IFS source code
# RUN git clone git@github.com:MeteoSwiss/flexpart.git /scratch/flexpart && cd /scratch/flexpart && git checkout $COMMIT 
COPY  --chown=default_user:default_user ../flexpart-ifs /scratch/flexpart
RUN chmod -R 777 /scratch/flexpart
RUN cd /scratch

# Install Flexpart-IFS
RUN cd spack-env && \
    . $SPACK_ROOT/share/spack/setup-env.sh && \
    spack -e . -vv install -j1 --fail-fast && \
    spack gc -y

RUN git clone --depth 1 --branch 2.25.0 https://github.com/ecmwf/eccodes.git

FROM docker-all-nexus.meteoswiss.ch/mch/ubuntu-jammy AS runner

RUN apt-get -yqq update \
    && apt-get -yqq install --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    python3.11-minimal \
    python3.11 \
    python3-pip \
    libnetcdf-dev \
    libnetcdff-dev \
    libopenjp2-7-dev \
    libeccodes-dev \
    flex \
    bison

RUN mkdir -p \
    /scratch/output/ \
    /scratch/flexpart_ifs_utils/ \
    /scratch/jobs/ \
    /scratch/eccodes/definitions \
    /scratch/db/

COPY --from=python-builder /scratch/requirements.txt /scratch/requirements.txt
COPY --from=spack-builder /scratch/spack-root/ /scratch/spack-root/
COPY --from=spack-builder /scratch/spack-view/ /scratch/spack-view/
COPY --from=spack-builder /scratch/eccodes/definitions /scratch/eccodes/definitions


ENV GRIB_DEFINITION_PATH=/scratch/eccodes/definitions
ENV PATH="/scratch/spack-view/bin:$PATH"
ENV JOBS_DIR=/scratch/jobs/
ENV FLEXPART_PREFIX=/scratch/spack-root/flexpart-ifs/

WORKDIR /scratch

COPY utils/flexpart_ifs_utils/ flexpart_ifs_utils/
COPY entrypoint.sh entrypoint.sh
COPY data/IGBP_int1.dat $JOBS_DIR

COPY utils/pip.conf /etc/pip.conf

COPY utils/pyproject.toml /scratch
RUN python3.11 -m pip install -r requirements.txt && \
    python3.11 -m pip install .

RUN chmod -R a+rwx /scratch

ARG USERNAME=default_user
ARG USER_UID=1000
ARG USER_GID=$USER_UID
# Create the user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME
USER $USERNAME

ENTRYPOINT ["/bin/bash", "/scratch/entrypoint.sh"]

CMD [""]