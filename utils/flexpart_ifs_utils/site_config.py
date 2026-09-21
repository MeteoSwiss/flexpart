"""The per-site release configuration, as published to S3 by Terraform.

The site config used to *be* a Jinja template of the Flexpart namelists: its keys were namelist keys
(``IBDATE``, ``SPECNUM_REL``, ``LON1``, ...) split into ``command:``/``releases:`` sections, six of
which were ``{{ data.EMISSION_START_YYYY }}``-style expressions filled from ECS environment
variables. That coupled the deployment repo's config format to Flexpart's namelist vocabulary and to
its date-string encoding, and it pinned the release window to whole hours.

Now the config is plain declarative site data in domain terms, the namelist vocabulary lives only in
``templates/{COMMAND,RELEASES}.j2``, and the time window is derived from per-site offsets - see
:mod:`flexpart_ifs_utils.job_config`.

This module is near-byte-identical to ``flexpart_utils/site_config.py`` in the ``flexpart-cosmo-icon``
repo - the ICON image has its own copy of the same vocabulary. There is no shared package between the
two repos, so a change here needs the same edit there; ``test_site_config.py``'s drift test only
catches a change that is forgotten entirely, not one applied differently on each side.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

# Namelist keys and section names from the retired schema. Recognised purely so a stale S3 object
# fails with a message that says what is wrong rather than "missing key 'latitude'".
_RETIRED_KEYS = frozenset({
    "command", "releases",
    "LDIRECT", "IBDATE", "IBTIME", "IEDATE", "IETIME", "LOUTSTEP",
    "NSPEC", "SPECNUM_REL", "IDATE1", "ITIME1", "IDATE2", "ITIME2",
    "LON1", "LON2", "LAT1", "LAT2", "Z1", "Z2", "ZKIND", "MASS", "COMMENT",
})


class HeightReference(Enum):
    """Vertical reference for the release height. Values match the on-demand API's ``Height.unit``."""

    AGL = "agl"
    MSL = "msl"
    HPA = "hpa"

    @property
    def zkind(self) -> int:
        """The namelist's ZKIND encoding: 1=above ground, 2=above sea level, 3=pressure in hPa."""
        return {HeightReference.AGL: 1, HeightReference.MSL: 2, HeightReference.HPA: 3}[self]


class Direction(Enum):
    """Simulation direction in time."""

    FORWARD = "forward"
    BACKWARD = "backward"

    @property
    def ldirect(self) -> int:
        return 1 if self is Direction.FORWARD else -1


@dataclass(frozen=True)
class SiteConfig:
    """One release site, as the deployment repo declares it.

    ``comment`` defaults to the site name and the offsets default to the values the pipeline used
    when they were still a global constant in the run scheduler, so an entry that omits them behaves
    exactly as it did before they were configurable.
    """

    name: str
    latitude: float
    longitude: float
    height_m: float
    species: list[int]
    """One entry per released nuclide, same order and same length as ``mass_bq`` - one release per
    nuclide. A scalar in the catalog YAML (every entry today) reads as a one-element list."""
    mass_bq: list[float]
    output_interval_s: int
    height_reference: HeightReference = HeightReference.AGL
    direction: Direction = Direction.FORWARD
    comment: str | None = None
    simulation_start_offset_h: float = 3
    release_start_offset_h: float = 3
    release_end_offset_h: float = 9
    # None means "run to the end of the available model data" - the window Flexpart can actually be
    # driven over is bounded by which forecast steps exist, not by preference.
    simulation_duration_h: float | None = None

    # -- derived values the namelist templates render ---------------------------------------------

    @property
    def zkind(self) -> int:
        return self.height_reference.zkind

    @property
    def direction_value(self) -> int:
        return self.direction.ldirect

    @property
    def nspec(self) -> int:
        """Number of species - derived from ``species`` so the namelist and the species list can
        never disagree."""
        return len(self.species)


_REQUIRED = ("latitude", "longitude", "height_m", "species", "mass_bq", "output_interval_s")

_OPTIONAL = ("height_reference", "direction", "comment", "simulation_start_offset_h",
             "release_start_offset_h", "release_end_offset_h", "simulation_duration_h")


def is_complete_site(fields: dict[str, Any]) -> bool:
    """True when ``fields`` (a ``JOB_OVERRIDES`` payload) defines every field a release site needs on
    its own - see :func:`site_from_overrides`.

    Mirrors ``common.domain.overrides.is_complete_site`` in leadtime-aggregator-lambda, which is
    what licenses an on-demand run to name a site outside the model's configured catalog in the first
    place. That is a different repo, so this cannot import it - kept in step by hand; see
    ``job_config._OVERRIDABLE_FIELDS`` for the same twin-repo note."""
    return set(_REQUIRED).issubset(fields)


def load_site_config(path: Path) -> SiteConfig:
    """Read and validate the site object Terraform published for this run's RELEASE_SITE_NAME.

    Validates here rather than trusting the object: Terraform passes the catalog through as opaque
    data, so the shape of an individual entry is only checked at plan time by variable validation.
    An entry that slipped through, or an image running against an S3 object written by an older
    Terraform, must fail with a message that names the problem.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"Site config {path} is not a mapping: {type(raw).__name__}")

    name = raw.get("name")
    if not name:
        raise RuntimeError(f"Site config {path} has no 'name'")

    fields = {k: v for k, v in raw.items() if k != "name"}

    retired = sorted(_RETIRED_KEYS.intersection(fields))
    if retired:
        raise RuntimeError(
            f"Site config for '{name}' uses the retired namelist-shaped schema (found {retired}). "
            "The namelist keys now live in templates/{COMMAND,RELEASES}.j2; the site config carries "
            "domain fields and offsets. Republish the site catalog from dispersionmodelling-deployment."
        )

    unknown = sorted(set(fields) - set(_REQUIRED) - set(_OPTIONAL))
    if unknown:
        raise RuntimeError(f"Site config for '{name}' has unknown fields: {unknown}")

    missing = [k for k in _REQUIRED if fields.get(k) is None]
    if missing:
        raise RuntimeError(f"Site config for '{name}' is missing required fields: {missing}")

    return _build_site(name, fields)


def site_from_overrides(name: str, overrides: dict[str, Any]) -> SiteConfig:
    """Build a whole release site from a ``JOB_OVERRIDES`` payload, for an on-demand run whose
    location is not in the Terraform-published catalog - see :func:`is_complete_site`.

    Takes the same coercion path as :func:`load_site_config` (via ``_build_site``), so an ad-hoc
    release is validated exactly as a catalog entry would be - minus the retired-schema check, which
    only concerns objects Terraform once published in the old namelist-shaped format.
    """
    fields = {k: v for k, v in overrides.items() if k in _REQUIRED or k in _OPTIONAL}
    missing = [k for k in _REQUIRED if fields.get(k) is None]
    if missing:
        raise RuntimeError(f"Ad-hoc site '{name}' is missing required fields: {missing}")
    return _build_site(name, fields)


def _build_site(name: str, fields: dict[str, Any]) -> SiteConfig:
    """Coerce a field mapping - from the S3 catalog or from an ad-hoc ``JOB_OVERRIDES`` payload - into
    a :class:`SiteConfig`, applying the same defaults and type coercion either way."""
    species = _as_int_list(fields["species"])
    mass_bq = _as_float_list(fields["mass_bq"])
    if len(species) != len(mass_bq):
        raise RuntimeError(
            f"Site config for '{name}' has {len(species)} species but {len(mass_bq)} mass_bq "
            "value(s); one release per nuclide.")
    return SiteConfig(
        name=str(name),
        latitude=float(fields["latitude"]),
        longitude=float(fields["longitude"]),
        height_m=_as_number(fields["height_m"]),
        species=species,
        mass_bq=mass_bq,
        output_interval_s=int(fields["output_interval_s"]),
        height_reference=_as_enum(HeightReference, fields, "height_reference", name,
                                 HeightReference.AGL),
        direction=_as_enum(Direction, fields, "direction", name, Direction.FORWARD),
        comment=str(fields.get("comment") or name),
        simulation_start_offset_h=_as_offset(fields, "simulation_start_offset_h", name, 3),
        release_start_offset_h=_as_offset(fields, "release_start_offset_h", name, 3),
        release_end_offset_h=_as_offset(fields, "release_end_offset_h", name, 9),
        simulation_duration_h=(None if fields.get("simulation_duration_h") is None
                               else _as_offset(fields, "simulation_duration_h", name, 0)),
    )


def _as_number(value: Any) -> float:
    """Keep integral values integral, so the namelist renders `Z1=100` and not `Z1=100.0`."""
    number = float(value)
    return int(number) if number.is_integer() else number


def _as_int_list(value: Any) -> list[int]:
    """A scalar or list of species numbers, always returned as a list - one release per nuclide."""
    values = value if isinstance(value, list) else [value]
    return [int(v) for v in values]


def _as_float_list(value: Any) -> list[float]:
    """A scalar or list of masses, always returned as a list, same length as ``species``."""
    values = value if isinstance(value, list) else [value]
    return [float(v) for v in values]


def _as_enum(enum: type[Enum], fields: dict[str, Any], field: str, site: str, default: Enum) -> Any:
    raw = fields.get(field)
    if raw is None:
        return default
    try:
        return enum(str(raw).lower())
    except ValueError as exc:
        allowed = [e.value for e in enum]
        raise RuntimeError(
            f"Site config for '{site}' has {field}={raw!r}; expected one of {allowed}"
        ) from exc


def _as_offset(fields: dict[str, Any], field: str, site: str, default: float) -> float:
    raw = fields.get(field)
    if raw is None:
        return default
    try:
        offset = float(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Site config for '{site}' has non-numeric {field}={raw!r}") from exc
    if offset < 0:
        raise RuntimeError(f"Site config for '{site}' has negative {field}={raw!r}")
    return int(offset) if offset.is_integer() else offset
