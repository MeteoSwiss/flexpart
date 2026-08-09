from enum import Enum


class EnvironmentParameters(Enum):
    """Time-related variables the state machine still puts on the ECS task.

    Only the end of the available model data arrives this way now. The eight ``EMISSION_*`` variables
    that used to accompany it encoded a globally-computed release window; that window is now derived
    inside the container from the site's own offsets (with an on-demand run's ``JOB_OVERRIDES``, if
    any, taking precedence - see :func:`flexpart_ifs_utils.job_config.resolve_job_config`), so they are
    no longer emitted by the run scheduler or forwarded by the state machine at all.
    """

    SIMULATION_END_YYYY = 1
    SIMULATION_END_MM = 2
    SIMULATION_END_DD = 3
    SIMULATION_END_ZZ = 4


class Model(Enum):
    IFS_HRES = 'IFS-Global'
    IFS_HRES_EUROPE = 'IFS-Europe'

MODEL_PREFIX: dict[Model, str] = {
    Model.IFS_HRES: "dispc*",
    Model.IFS_HRES_EUROPE: "dispf*",
}
