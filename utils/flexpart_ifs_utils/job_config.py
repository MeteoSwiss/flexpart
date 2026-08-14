"""The run's resolved time window.

This module is the *only* place that knows how the Step Function payload encodes time. Everything
downstream - the namelist templates, the input-file selection - consumes the four datetimes on
:class:`JobConfig` and never touches an environment variable or a date string.

The offsets themselves are per site (see :mod:`flexpart_ifs_utils.site_config`), because different
release sites need different release windows. They used to be one global constant pair (+3h / +9h)
computed in the run scheduler, which is why they could not vary.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from flexpart_ifs_utils.model import EnvironmentParameters, Model
from flexpart_ifs_utils.site_config import SiteConfig

_logger = logging.getLogger(__name__)

_FORECAST_DATETIME_FORMAT = "%Y%m%d%H%M"

# The site-config fields an on-demand run's payload may override. Anything else it carries is not
# read below, so it is logged rather than dropped without trace - see _warn_unrecognised_overrides.
# Adding an overridable field means adding it here too.
_OVERRIDABLE_FIELDS = frozenset({
    "simulation_start_offset_h",
    "release_start_offset_h",
    "release_end_offset_h",
    "simulation_duration_h",
})


@dataclass(frozen=True)
class JobConfig:
    """The window this job runs over, resolved against the forecast reference time.

    ``simulation_start``/``simulation_end`` drive Flexpart's COMMAND namelist and the selection of
    input GRIB; ``release_start``/``release_end`` drive RELEASES. They are separate fields even
    though every site currently sets the simulation start equal to the release start, so a site can
    be given spin-up time before its release without another refactor.
    """

    model: Model
    forecast_datetime: datetime
    simulation_start: datetime
    simulation_end: datetime
    release_start: datetime
    release_end: datetime


def resolve_job_config(
    forecast_datetime: str,
    model: Model,
    site: SiteConfig,
    overrides: dict[str, Any] | None = None,
) -> JobConfig:
    """Build the job's window from the forecast reference time and the site's offsets.

    Resolution order for each offset: the payload's ``jobConfig`` override (how an on-demand run
    asks for its own window), then the site config, then the built-in default. ``overrides`` is read
    but nothing writes it yet - the on-demand API's ``runConfig`` is wired onto it separately.

    ``simulation_end`` is the one value that is not a free choice: Flexpart can only be driven over
    forecast steps that exist, so a site's ``simulation_duration_h`` is clamped to the end of the
    available model data, and omitting it means "run to the end of the data" - the behaviour before
    the duration was configurable.
    """
    reference = _parse_forecast_datetime(forecast_datetime)
    data_end = _data_end_from_env()
    overrides = overrides or {}
    _warn_unrecognised_overrides(overrides, site)

    simulation_start_offset = _offset(overrides, site, "simulation_start_offset_h")
    release_start_offset = _offset(overrides, site, "release_start_offset_h")
    release_end_offset = _offset(overrides, site, "release_end_offset_h")
    duration = overrides.get("simulation_duration_h", site.simulation_duration_h)

    if release_end_offset < release_start_offset:
        raise RuntimeError(
            f"Site '{site.name}' has release_end_offset_h={release_end_offset} before "
            f"release_start_offset_h={release_start_offset}"
        )

    simulation_start = reference + timedelta(hours=simulation_start_offset)
    simulation_end = data_end if duration is None else min(
        reference + timedelta(hours=float(duration)), data_end)

    if simulation_end <= simulation_start:
        raise RuntimeError(
            f"Site '{site.name}' resolves to an empty simulation window: {simulation_start} to "
            f"{simulation_end} (forecast reference {reference}, available data ends {data_end})"
        )

    job = JobConfig(
        model=model,
        forecast_datetime=reference,
        simulation_start=simulation_start,
        simulation_end=simulation_end,
        release_start=reference + timedelta(hours=release_start_offset),
        release_end=reference + timedelta(hours=release_end_offset),
    )

    _logger.info(
        "Resolved window for %s: simulation %s to %s, release %s to %s "
        "(forecast reference %s, available data ends %s)",
        site.name, job.simulation_start, job.simulation_end, job.release_start, job.release_end,
        reference, data_end,
    )
    return job


def _warn_unrecognised_overrides(overrides: dict[str, Any], site: SiteConfig) -> None:
    """Log the override keys this function does not read, which are otherwise applied to nothing.

    A warning and not an error on purpose. By the time the container runs, the run row is written and
    the execution has started, and the job fans out per site and member - rejecting a stale payload
    here would turn it into a failed task per job rather than one refused request. The eager check
    belongs at ``create_run``, which already validates ``sites`` and ``computeBackends`` before a run
    is accepted at all. This is only the trace that says a requested window was not applied.
    """
    unrecognised = sorted(set(overrides) - _OVERRIDABLE_FIELDS)
    if unrecognised:
        _logger.warning(
            "Ignoring unrecognised job override(s) for %s: %s. The site's own config applies for "
            "these; the overridable fields are %s.",
            site.name, ", ".join(unrecognised), ", ".join(sorted(_OVERRIDABLE_FIELDS)),
        )


def _offset(overrides: dict[str, Any], site: SiteConfig, field: str) -> float:
    value = overrides.get(field)
    return float(getattr(site, field) if value is None else value)


def _parse_forecast_datetime(forecast_datetime: str) -> datetime:
    try:
        return datetime.strptime(forecast_datetime, _FORECAST_DATETIME_FORMAT)
    except ValueError as exc:
        raise RuntimeError(
            f"FORECAST_DATETIME {forecast_datetime!r} is not in format YYYYMMDDhhmm"
        ) from exc


def _data_end_from_env() -> datetime:
    """The end of the available model data, as the run scheduler computed it.

    Still delivered as the four ``SIMULATION_END_*`` variables, which is what the run scheduler names
    ``forecast + last available step``. The name is a leftover from when it *was* the simulation
    boundary; it is now only the upper bound on one.
    """
    parts = {p.name: os.getenv(p.name) for p in EnvironmentParameters}

    missing = sorted(name for name, value in parts.items() if value is None)
    if missing:
        raise RuntimeError(
            f"Environment is missing variables needed to resolve the job window: {missing}"
        )

    stamp = (f"{parts['SIMULATION_END_YYYY']}{parts['SIMULATION_END_MM']}"
             f"{parts['SIMULATION_END_DD']}{parts['SIMULATION_END_ZZ']}")
    try:
        return datetime.strptime(stamp, "%Y%m%d%H")
    except ValueError as exc:
        raise RuntimeError(f"SIMULATION_END_* do not form a valid datetime: {stamp!r}") from exc
