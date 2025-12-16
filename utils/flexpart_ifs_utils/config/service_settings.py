from mchpy.audit.logger import LoggingSettings
from mchpy.config.base_settings import BaseServiceSettings
from pydantic import BaseModel
from enum import Enum


class Bucket(BaseModel):
    region: str
    name: str
    retries: int | None
    endpoint_url: str
    platform: str

class S3(BaseModel):
    nwp_model_data: Bucket
    output: Bucket

class BackendType(str, Enum):
    DYNAMODB = "dynamodb"
    SQLITE = "sqlite"

class DBTable(BaseModel):
    name: str
    region: str
    backend_type: BackendType

class DB(BaseModel):
    nwp_model_data: DBTable

class AWS(BaseModel):
    s3: S3
    db: DB

class InputSettings(BaseModel):
    step_unit: str

class OpenMPConfig(BaseModel):
    num_threads: int
    stack_size: str

class AppSettings(BaseModel):
    app_name: str
    aws: AWS
    input: InputSettings
    openmp_config: OpenMPConfig

class ServiceSettings(BaseServiceSettings):
    logging: LoggingSettings
    main: AppSettings
