""" Initializations """
import os

from mchpy.audit import logger
from flexpart_ifs_utils.config.service_settings import ServiceSettings

CONFIG = ServiceSettings('settings.yaml', os.path.join(os.path.dirname(__file__), 'config'))

# Configure logger
logger.apply_logging_settings(CONFIG.logging)

INPUT_DATA_PATTERNS = ('dispf*')
