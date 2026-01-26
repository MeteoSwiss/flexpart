# ==============================================================
# Dockerfile to build an image with the dependencies of
# Flexpart-IFS installed in an environment via spack.
# ==============================================================

# =============================================================
# Build spack
# =============================================================

FROM docker-all-nexus.meteoswiss.ch/mch/ubuntu-noble AS spack-builder


WORKDIR /opt

# Basics: spack dependencies
RUN apt-get update && apt-get install -y -q --no-install-recommends \
    file bzip2 ca-certificates g++-11 gcc-11 gfortran-11 build-essential git gzip \
    lsb-release patch python3 tar unzip xz-utils zstd curl rsync make cmake m4 \
    && rm -rf /var/lib/apt/lists/*

# Spack checkout
# Note: Use spack v1.2 once released, and clone with '--depth 1'. In the meantime, we need a specific commit
#       that fixes an authentication bug for using the spack build cache on nexus.
RUN curl -L https://github.com/spack/spack/archive/8ca06da.zip -o repo.zip && \
    mkdir -p /opt/spack && \
    unzip -q repo.zip -d /opt && \
    mv /opt/spack-8ca06da*/* /opt/spack/ && \
    rm -rf /opt/spack-8ca06da* repo.zip

# Spack setup: Update builtin repo, find externals and add the Nexus mirror (buildcache)
# Notes: * For the builtin repo, a newer commit is used that includes eccodes-cosmo-resources,
#          eccodes 2.36.4, and a compiler wrapper bugfix. This will be included in spack 1.2, once released.
#        * For pushing to the spack buildcache, we do not use '--autopush' since this triggers a spack bug
#          related to multiprocessing (fixed in next release). Instead, we do a manual push after the installs.
#        * The oci username & password environment variables need to be set whenever spack should push, see below.
RUN . /opt/spack/share/spack/setup-env.sh && \
    spack repo update --commit a5ec6ab0dbf87f671a917bce29bf16284ebf0dac builtin && \
    spack external find && \
    spack mirror add spack-build-cache \
        --unsigned \
        --oci-username-variable BUILDCACHE_USER \
        --oci-password-variable BUILDCACHE_PASSWORD \
        oci://docker-intern-nexus.meteoswiss.ch/numericalweatherpredictions/spack-build-cache

# =============================================================
# Build flexpart
# =============================================================

# copy flexpart code, including spack recipes and spack.yaml
# We need to copy in multiple stages because mchbuild does not preserve the folder
# structure otherwise when it forms the .ctx directory
COPY options /opt/options
COPY options.meteoswiss /opt/options.meteoswiss
COPY spack_env /opt/spack_env
COPY spack_repo /opt/spack_repo
COPY src /opt/src
COPY entrypoint.sh /opt/entrypoint.sh
COPY test_meteoswiss /opt/test_meteoswiss
COPY pathnames /opt/pathnames

# Install
# Note: For pushing to the spack buildcache, we do not use '--autopush' since this seems to trigger
#       a weird bug in spack related to multiprocessing. Instead, we do a manual push after the install
RUN --mount=type=secret,id=spack_buildcache_user,target=/run/secrets/spack_buildcache_user \
    --mount=type=secret,id=spack_buildcache_password,target=/run/secrets/spack_buildcache_password \
    export BUILDCACHE_USER="$(cat /run/secrets/spack_buildcache_user)" && \
    export BUILDCACHE_PASSWORD="$(cat /run/secrets/spack_buildcache_password)" && \
    . /opt/spack/share/spack/setup-env.sh && \
    spack env activate spack_env && \
    spack repo list && \
    spack concretize -f && \
    spack install --fail-fast && \
    # pushing the fieldextra spec with --only=dependencies means everything except flexpart
    (spack buildcache push --update-index --only=dependencies --fail-fast spack-build-cache flexpart-ifs \
     || echo "Spack buildcache push failed, continuing anyway") && \
    spack gc -y && \
    spack clean -a


##########################################
# Python builder stage to prepare requirements files
##########################################

FROM dockerhub.apps.cp.meteoswiss.ch/mch/python/builder AS python-builder

COPY utils/poetry.lock utils/pyproject.toml /scratch

RUN cd /scratch \
    && poetry export --without-hashes -o requirements.txt \
    && poetry export --without-hashes --with dev -o requirements_dev.txt


##########################################
# Runner stage to run Flexpart-IFS with the built spack environment
##########################################

FROM docker-all-nexus.meteoswiss.ch/mch/ubuntu-noble AS runner

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
    /scratch/db/

COPY --from=python-builder /scratch/requirements.txt /scratch/requirements.txt
COPY --from=spack-builder /scratch/spack-root/ /scratch/spack-root/
COPY --from=spack-builder /scratch/spack-view/ /scratch/spack-view/

ENV PATH="/scratch/spack-view/bin:$PATH"
ENV JOBS_DIR=/scratch/jobs
ENV FLEXPART_PREFIX=/scratch/spack-root/flexpart-ifs

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

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME
USER $USERNAME

ENTRYPOINT ["/bin/bash", "/scratch/entrypoint.sh"]

CMD [""]

##########################################
# Tester stage to run tests on the built image
##########################################

FROM runner AS tester

USER root

COPY --from=python-builder /scratch/requirements_dev.txt /scratch/requirements_dev.txt
RUN python3.11 -m pip install -r /scratch/requirements_dev.txt

RUN mkdir test_reports && chmod -R a+rwx test_reports
COPY utils/pyproject.toml utils/test_ci.sh /scratch/
RUN chmod +x /scratch/test_ci.sh
COPY utils/test /scratch/test

# This environment tells pytest that the tests are occuring in a container.
ENV PYTEST_ENTRYPOINT=/scratch/entrypoint.sh
ENV FLEXPART_PREFIX=/scratch/spack-root/flexpart-ifs/
ENV PATH="/scratch/spack-view/bin:$PATH"
ENV JOBS_DIR=/scratch/jobs/

ARG USERNAME=default_user
USER $USERNAME

ENTRYPOINT []

CMD ["/bin/bash", "-c", "source ./test_ci.sh && run_ci_tools"]
