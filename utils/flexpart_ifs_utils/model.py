from enum import Enum


class EnvironmentParameters(Enum):
    # Time-related variables the state machine still puts on the ECS task.
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
