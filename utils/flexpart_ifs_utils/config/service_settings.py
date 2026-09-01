from mchpy.audit.logger import LoggingSettings
from mchpy.config.base_settings import BaseServiceSettings
from pydantic import BaseModel


class Bucket(BaseModel):
    region: str
    name: str
    retries: int | None

class S3(BaseModel):
    nwp_model_data: Bucket
    output: Bucket
    site_config: Bucket

class AWS(BaseModel):
    s3: S3

class InputSettings(BaseModel):
    step_unit: str

class OpenMPConfig(BaseModel):
    num_threads: int
    stack_size: str

class RuntimeConfigSettings(BaseModel):
    site_config_key_prefix: str

class AppSettings(BaseModel):
    app_name: str
    aws: AWS
    input: InputSettings
    openmp_config: OpenMPConfig
    runtime_config: RuntimeConfigSettings

class ServiceSettings(BaseServiceSettings):
    logging: LoggingSettings
    main: AppSettings
