# ==============================================================
# Dockerfile to build an image with the dependencies of
# Flexpart-IFS installed in an environment via spack.
# ==============================================================

# =============================================================
# Build spack
# =============================================================

FROM dockerhub.apps.cp.meteoswiss.ch/dispersionmodelling/spack-base-image:0.1.0 AS spack-builder
ARG VERSION
LABEL ch.meteoswiss.project=flexpart-ifs-${VERSION}

WORKDIR /opt

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
    # pushing the flexpart-ifs spec with --only=dependencies means everything except flexpart-ifs
    (spack buildcache push --update-index --only=dependencies --fail-fast spack-build-cache flexpart-ifs \
     || echo "Spack buildcache push failed, continuing anyway") && \
    spack gc -y && \
    spack clean -a


##########################################
# Python builder stage to prepare requirements files
##########################################
FROM dockerhub.apps.cp.meteoswiss.ch/mch/python-3.13:latest AS python-builder
ARG VERSION
LABEL ch.meteoswiss.project=flexpart-ifs-${VERSION}

COPY utils/poetry.lock utils/pyproject.toml /src/app-root/

WORKDIR /src/app-root

RUN poetry export -o requirements.txt \
    && poetry export --with dev -o requirements_dev.txt

##########################################
# Runner stage to run Flexpart-IFS with the built spack environment
##########################################

FROM dockerhub.apps.cp.meteoswiss.ch/mch/python-3.13:latest-slim AS runner
ARG VERSION
LABEL ch.meteoswiss.project=flexpart-ifs-${VERSION}

COPY --from=python-builder /src/app-root/requirements.txt /opt/requirements.txt
COPY --from=spack-builder /opt/spack-root/ /opt/spack-root/
COPY --from=spack-builder /opt/spack-view/ /opt/spack-view/

RUN pip install -r /opt/requirements.txt --no-cache-dir --no-deps --root-user-action=ignore

ENV VERSION=$VERSION
ENV PATH="/opt/spack-view/bin:$PATH"
ENV JOBS_DIR=/scratch/jobs
ENV FLEXPART_PREFIX=/opt/spack-view
ENV ECCODES_DIR=/opt/spack-view
# we must ensure that eccodes uses the version installed with SPACK instead of the one installed with pip
ENV FINDLIBS_DISABLE_PACKAGE=yes
ENV FINDLIBS_DISABLE_PYTHON=yes

WORKDIR /scratch

RUN mkdir -p \
    output \
    jobs \
    db

COPY utils/flexpart_ifs_utils flexpart_ifs_utils
COPY entrypoint.sh entrypoint.sh
COPY data/IGBP_int1.dat $JOBS_DIR

RUN chmod -R a+rwx /scratch /opt/spack-view /opt/spack-root

ARG USERNAME=default_user
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME
USER $USERNAME

ENTRYPOINT ["/bin/bash", "entrypoint.sh"]

CMD [""]

##########################################
# Tester stage to run tests on the built image
##########################################

FROM runner AS tester

USER root

WORKDIR /scratch

COPY --from=python-builder /src/app-root/requirements_dev.txt /src/app-root/requirements_dev.txt
RUN pip install -r /src/app-root/requirements_dev.txt --no-cache-dir --no-deps --root-user-action=ignore

COPY utils/pyproject.toml utils/test_ci.sh /scratch/
COPY utils/test test

RUN mkdir test_reports && chmod -R a+rwx test_reports
RUN chmod +x test_ci.sh

# This environment tells pytest that the tests are occuring in a container.
ENV PYTEST_ENTRYPOINT=/scratch/entrypoint.sh
# Point pylint and mypy to the config inside the image; /scratch is not bind-mounted
# during the lint stage so this path is always visible.
ENV PYLINTRC=/scratch/pyproject.toml
ENV MYPY_CONFIG_FILE=/scratch/pyproject.toml

ENTRYPOINT []

CMD ["/bin/bash", "-c", "source ./test_ci.sh && run_ci_tools"]
