import pytest

from flexpart_ifs_utils.site_config import (Direction, HeightReference,
                                            load_site_config)

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
    assert site.species == 16
    assert site.mass_bq == 2.88e10
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
