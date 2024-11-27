# Dockerfile to build Flexpart-IFS into an image
ARG container_registry=dockerhub.apps.cp.meteoswiss.ch
ARG base_tag=v0.2.1

#  FROM ${container_registry}/numericalweatherpredictions/dispersionmodelling/flexpart-ifs/flexpart-base:${base_tag} as spack-builder
FROM my-base-image:local as spack-builder

ARG TOKEN
ENV TOKEN=$TOKEN 
# RUN git config --global url."https://x-access-token:${TOKEN}@github.com/MeteoSwiss/".insteadOf "git@github.com:MeteoSwiss/"
ARG COMMIT
ENV COMMIT=$COMMIT

# Add Flexpart-IFS source code
RUN git clone git@github.com:MeteoSwiss/flexpart.git /scratch/flexpart && cd /scratch/flexpart && git checkout $COMMIT 

# Install Flexpart-IFS
RUN cd spack-env && \
    . $SPACK_ROOT/share/spack/setup-env.sh && \
    spack -e . -vv install -j1 --fail-fast && \
    # Spack garbage collection 
    spack gc -y

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

COPY --from=spack-builder /scratch/spack-root/ /scratch/spack-root/
COPY --from=spack-builder /scratch/spack-view/ /scratch/spack-view/

ENV PATH="/scratch/spack-view/bin:$PATH"
ENV GRIB_DEFINITION_PATH=/scratch/eccodes-cosmo-resources/definitions:/scratch/eccodes/definitions
ENV JOBS_DIR=/scratch/jobs/
ENV FLEXPART_PREFIX=/scratch/spack-root/flexpart-cosmo/

WORKDIR /scratch

COPY utils/flexpart_utils/ flexpart_utils/
COPY entrypoint.sh entrypoint.sh

COPY utils/pip.conf /etc/pip.conf

COPY utils/pyproject.toml /scratch
# RUN python3.11 -m pip install -r requirements.txt && \
#  python3.11 -m pip install .

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