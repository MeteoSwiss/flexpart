
import logging
from pathlib import Path

from eccodes import codes_grib_new_from_file, codes_get_string, codes_count_in_file, codes_release, CodesInternalError
from pydantic import BaseModel

_logger = logging.getLogger(__name__)

class RunMetadata(BaseModel):
    date: str
    time: str

class GribMetadata(RunMetadata):
    step: float


def extract_metadata_from_grib_file(path: Path) -> GribMetadata:
    """ This function assumes all GRIB messages in the file have the same forecast datetime, step."""

    with open(path, "rb") as f:
        gid = codes_grib_new_from_file(f)
        if gid is None:
            msg = f"Could not read grib file {path}."
            _logger.exception(msg)
            raise RuntimeError(msg)

        fcst_date = codes_get_string(gid, 'mars.date')
        fcst_time = codes_get_string(gid, 'mars.time')
        step = codes_get_string(gid, 'mars.step').split('-')[-1]
        step_units = codes_get_string(gid, 'stepUnits')

        # If step units is in minutes convert to hours.
        # See https://github.com/ecmwf/eccodes/blob/develop/definitions/stepUnits.table
        if step_units == 'm':
            step_hr = int(step)/60.0
        elif step_units == 'h':
            step_hr = float(step)
        else:
            raise RuntimeError('Only hour and minute step units supported.')

        codes_release(gid)

    return GribMetadata(
        date = fcst_date,
        time = fcst_time,
        step = step_hr)


def _is_grib_file(file_path: Path) -> bool:
    """Check if a file is a GRIB file using eccodes."""

    try:
        with open(file_path, 'rb') as f:
            gid = codes_count_in_file(f)
            if not gid:
                return False
    except CodesInternalError:
        return False
    return True
