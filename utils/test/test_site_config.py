import pytest

from flexpart_ifs_utils.site_config import (Direction, HeightReference, SiteConfig,
                                            is_complete_site, load_site_config,
                                            site_from_overrides)

MINIMAL = """
name: Testerhausen
latitude: 47.5519
longitude: 8.2284
height_m: 100
species: 16
mass_bq: 2.8800e+10
output_interval_s: 10800
"""


def _write(tmp_path, text):
    path = tmp_path / "site.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_site_config(site_config_file):

    site = load_site_config(site_config_file)

    assert site.name == "Testerhausen"
    assert site.latitude == 47.5519
    assert site.longitude == 8.2284
    assert site.height_m == 100
    assert site.height_reference is HeightReference.AGL
    # A scalar in the catalog YAML reads as a one-element list - one release per nuclide.
    assert site.species == [16]
    assert site.mass_bq == [2.88e10]
    assert site.output_interval_s == 10800
    assert site.direction is Direction.FORWARD
    assert site.comment == "Testerhausen"
    assert site.simulation_start_offset_h == 3
    assert site.release_start_offset_h == 3
    assert site.release_end_offset_h == 8
    # Omitted, meaning "run to the end of the available model data"
    assert site.simulation_duration_h is None


def test_load_site_config_applies_defaults(tmp_path):

    site = load_site_config(_write(tmp_path, MINIMAL))

    assert site.height_reference is HeightReference.AGL
    assert site.direction is Direction.FORWARD
    # A site that names itself only through the catalog key still gets a namelist comment
    assert site.comment == "Testerhausen"
    # The values the run scheduler used while the window was a global constant
    assert (site.simulation_start_offset_h, site.release_start_offset_h,
            site.release_end_offset_h) == (3, 3, 9)


def test_load_site_config_derives_namelist_values(tmp_path):

    site = load_site_config(_write(tmp_path, MINIMAL + "height_reference: hpa\ndirection: backward\n"))

    assert site.zkind == 3
    assert site.direction_value == -1
    assert site.nspec == 1


def test_load_site_config_keeps_integral_heights_integral(tmp_path):
    """So the namelist renders `Z1=100`, not `Z1=100.0`."""

    assert load_site_config(_write(tmp_path, MINIMAL)).height_m == 100
    assert isinstance(load_site_config(_write(tmp_path, MINIMAL)).height_m, int)

    site = load_site_config(_write(tmp_path, MINIMAL.replace("height_m: 100", "height_m: 92.5")))
    assert site.height_m == 92.5


def test_load_site_config_rejects_the_retired_namelist_schema(tmp_path):
    """An image running against an S3 object written by an older Terraform must say so."""

    retired = """
name: Testerhausen
command:
  LDIRECT: 1
  IBDATE: "20241210"
releases:
  LON1: 8.2284
"""
    with pytest.raises(RuntimeError, match="retired namelist-shaped schema"):
        load_site_config(_write(tmp_path, retired))


def test_load_site_config_rejects_unknown_fields(tmp_path):

    with pytest.raises(RuntimeError, match=r"unknown fields: \['altitude'\]"):
        load_site_config(_write(tmp_path, MINIMAL + "altitude: 100\n"))


def test_load_site_config_rejects_missing_required_fields(tmp_path):

    without_latitude = "\n".join(l for l in MINIMAL.splitlines() if "latitude" not in l)

    with pytest.raises(RuntimeError, match=r"missing required fields: \['latitude'\]"):
        load_site_config(_write(tmp_path, without_latitude))


def test_load_site_config_rejects_a_nameless_entry(tmp_path):

    nameless = "\n".join(l for l in MINIMAL.splitlines() if not l.startswith("name:"))

    with pytest.raises(RuntimeError, match="no 'name'"):
        load_site_config(_write(tmp_path, nameless))


@pytest.mark.parametrize("field", ["simulation_start_offset_h", "release_start_offset_h",
                                   "release_end_offset_h"])
def test_load_site_config_rejects_negative_offsets(tmp_path, field):

    with pytest.raises(RuntimeError, match=f"negative {field}"):
        load_site_config(_write(tmp_path, MINIMAL + f"{field}: -2\n"))


def test_load_site_config_rejects_an_unknown_height_reference(tmp_path):

    with pytest.raises(RuntimeError, match="height_reference"):
        load_site_config(_write(tmp_path, MINIMAL + "height_reference: above_ground\n"))


def test_load_site_config_accepts_fractional_offsets(tmp_path):
    """The namelist carries HHMISS, so offsets are no longer restricted to whole hours."""

    site = load_site_config(_write(tmp_path, MINIMAL + "release_start_offset_h: 2.5\n"))

    assert site.release_start_offset_h == 2.5


def test_load_site_config_accepts_an_explicit_multi_nuclide_list(tmp_path):
    multi = MINIMAL.replace("species: 16", "species: [15, 16]").replace(
        "mass_bq: 2.8800e+10", "mass_bq: [1.0e+12, 1.0e+11]")

    site = load_site_config(_write(tmp_path, multi))

    assert site.species == [15, 16]
    assert site.mass_bq == [1e12, 1e11]
    assert site.nspec == 2


def test_load_site_config_rejects_mismatched_species_and_mass_bq_lengths(tmp_path):
    mismatched = MINIMAL.replace("species: 16", "species: [15, 16]")

    with pytest.raises(RuntimeError, match="2 species but 1 mass_bq"):
        load_site_config(_write(tmp_path, mismatched))


def test_is_complete_site_requires_every_required_field():
    complete = {
        "latitude": 47.55, "longitude": 8.18, "height_m": 100, "species": 16, "mass_bq": 1e12,
        "output_interval_s": 10800,
    }
    assert is_complete_site(complete) is True
    assert is_complete_site({"latitude": 47.55}) is False
    assert is_complete_site({}) is False


def test_site_from_overrides_builds_an_ad_hoc_site_outside_the_catalog():
    site = site_from_overrides("Fakenberg", {
        "latitude": 35.42, "longitude": 141.03, "height_m": 10, "species": [16, 39],
        "mass_bq": [1e12, 2e11], "output_interval_s": 3600, "release_start_offset_h": 0,
        "release_end_offset_h": 6,
    })

    assert isinstance(site, SiteConfig)
    assert site.name == "Fakenberg"
    assert (site.latitude, site.longitude, site.height_m) == (35.42, 141.03, 10)
    assert site.species == [16, 39]
    assert site.mass_bq == [1e12, 2e11]
    assert (site.release_start_offset_h, site.release_end_offset_h) == (0, 6)
    # Not named in the overrides -> the same built-in defaults load_site_config would apply.
    assert site.simulation_start_offset_h == 3
    assert site.comment == "Fakenberg"


def test_site_from_overrides_rejects_an_incomplete_payload():
    with pytest.raises(RuntimeError, match="missing required fields"):
        site_from_overrides("Bad", {"latitude": 35.42})


def test_overridable_fields_widened_to_the_full_site_surface():
    """job_config._OVERRIDABLE_FIELDS mirrors _REQUIRED | _OPTIONAL here - a drift test, since the two
    live in different modules (and are mirrored again in leadtime-aggregator-lambda and in the
    ``flexpart-cosmo-icon`` (ICON) repo's identical copy of this module - see job_config.py's header
    comment)."""
    from flexpart_ifs_utils.job_config import _OVERRIDABLE_FIELDS

    assert _OVERRIDABLE_FIELDS == {
        "latitude", "longitude", "height_m", "species", "mass_bq", "output_interval_s",
        "height_reference", "direction", "comment",
        "simulation_start_offset_h", "release_start_offset_h", "release_end_offset_h",
        "simulation_duration_h",
    }


def test_with_direction_returns_an_overridden_copy(site_config_file):
    """The per-run DIRECTION override (entrypoint.sh -> generate --direction) swaps only the direction."""
    site = load_site_config(site_config_file)

    backward = site.with_direction(Direction.BACKWARD)

    assert backward.direction is Direction.BACKWARD
    assert backward.direction_value == -1
    # A copy - the loaded catalog site is left as it was
    assert site.direction is Direction.FORWARD
    assert backward is not site
    # Everything else carries over untouched
    assert backward.with_direction(Direction.FORWARD) == site


def test_with_direction_can_turn_a_backward_site_forward(tmp_path):
    site = load_site_config(_write(tmp_path, MINIMAL + "direction: backward\n"))

    forward = site.with_direction(Direction.FORWARD)

    assert forward.direction is Direction.FORWARD
    assert forward.direction_value == 1
