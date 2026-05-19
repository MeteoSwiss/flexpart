from enum import Enum

class EnvironmentParameters(Enum):
    EMISSION_START_YYYY = 1
    EMISSION_START_MM = 2
    EMISSION_START_DD = 3
    EMISSION_START_ZZ = 4
    EMISSION_END_YYYY = 5
    EMISSION_END_MM = 6
    EMISSION_END_DD = 7
    EMISSION_END_ZZ = 8
    SIMULATION_END_YYYY = 9
    SIMULATION_END_MM = 10
    SIMULATION_END_DD = 11
    SIMULATION_END_ZZ = 12

class Model(Enum):
    IFS_HRES = 'IFS-HRES'
    IFS_HRES_EUROPE = 'IFS-HRES-Europe'

MODEL_PREFIX: dict[Model, str] = {
    Model.IFS_HRES: "dispc*",
    Model.IFS_HRES_EUROPE: "dispf*",
}
