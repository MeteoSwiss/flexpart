import logging
from datetime import datetime

import pytest

from flexpart_ifs_utils.job_config import resolve_job_config
from flexpart_ifs_utils.model import Model
from flexpart_ifs_utils.site_config import load_site_config

FORECAST = "202412092100"


def _site(tmp_path, extra=""):
    text = f"""
name: Testerhausen
latitude: 47.5519
longitude: 8.2284
height_m: 100
species: 16
mass_bq: 2.8800e+10
output_interval_s: 10800
{extra}"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "site.yaml"
    path.write_text(text, encoding="utf-8")
    return load_site_config(path)


def test_resolve_job_config_applies_the_sites_offsets(tmp_path, reference_data_end):

    site = _site(tmp_path, "simulation_start_offset_h: 3\n"
                           "release_start_offset_h: 3\n"
                           "release_end_offset_h: 8\n")

    job = resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site)

    assert job.forecast_datetime == datetime(2024, 12, 9, 21)
    assert job.simulation_start == datetime(2024, 12, 10, 0)
    assert job.release_start == datetime(2024, 12, 10, 0)
    assert job.release_end == datetime(2024, 12, 10, 5)
    # No simulation_duration_h, so the window runs to the end of the available data
    assert job.simulation_end == datetime(2024, 12, 10, 5)


def test_resolve_job_config_gives_each_site_its_own_window(tmp_path, reference_data_end):
    """The point of the exercise: two sites, one run, different release windows."""

    early = _site(tmp_path / "a", "release_start_offset_h: 3\nrelease_end_offset_h: 6\n")
    late = _site(tmp_path / "b", "release_start_offset_h: 5\nrelease_end_offset_h: 8\n")

    early_job = resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, early)
    late_job = resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, late)

    assert early_job.release_start == datetime(2024, 12, 10, 0)
    assert early_job.release_end == datetime(2024, 12, 10, 3)
    assert late_job.release_start == datetime(2024, 12, 10, 2)
    assert late_job.release_end == datetime(2024, 12, 10, 5)


def test_resolve_job_config_separates_simulation_start_from_release_start(tmp_path, reference_data_end):
    """Spin-up before the release, which the retired schema could not express."""

    site = _site(tmp_path, "simulation_start_offset_h: 1\nrelease_start_offset_h: 3\n")

    job = resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site)

    assert job.simulation_start == datetime(2024, 12, 9, 22)
    assert job.release_start == datetime(2024, 12, 10, 0)


def test_resolve_job_config_honours_fractional_offsets(tmp_path, reference_data_end):

    site = _site(tmp_path, "release_start_offset_h: 2.5\nrelease_end_offset_h: 7.25\n")

    job = resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site)

    assert job.release_start == datetime(2024, 12, 9, 23, 30)
    assert job.release_end == datetime(2024, 12, 10, 4, 15)


def test_resolve_job_config_clamps_the_duration_to_available_data(tmp_path, reference_data_end):
    """Flexpart can only be driven over forecast steps that exist."""

    site = _site(tmp_path, "simulation_duration_h: 240\n")

    job = resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site)

    assert job.simulation_end == datetime(2024, 12, 10, 5)


def test_resolve_job_config_shortens_a_simulation_within_available_data(tmp_path, reference_data_end):

    site = _site(tmp_path, "simulation_duration_h: 6\n")

    job = resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site)

    assert job.simulation_end == datetime(2024, 12, 10, 3)


def test_resolve_job_config_prefers_a_payload_override(tmp_path, reference_data_end):
    """How an on-demand run asks for its own window instead of the site's default."""

    site = _site(tmp_path, "release_start_offset_h: 3\nrelease_end_offset_h: 9\n")

    job = resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site,
                             overrides={"release_start_offset_h": 1, "release_end_offset_h": 4})

    assert job.release_start == datetime(2024, 12, 9, 22)
    assert job.release_end == datetime(2024, 12, 10, 1)


def test_resolve_job_config_warns_about_unrecognised_overrides(tmp_path, reference_data_end, caplog):
    """A payload in a vocabulary this function does not read applies to nothing - not silently.

    The override reaching the container is a free-form dict carried verbatim from the run row, so a
    payload naming fields that are not site config fields resolves to exactly the site's own defaults.
    Without this log line there is no trace that a requested window was dropped.
    """

    site = _site(tmp_path, "release_start_offset_h: 3\nrelease_end_offset_h: 9\n")

    with caplog.at_level(logging.WARNING):
        job = resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site,
                                 overrides={"model": {"name": "IFS-HRES-Europe"},
                                            "release": {"duration": 6}})

    assert "Ignoring unrecognised job override(s) for Testerhausen: model, release" in caplog.text
    # ... and the site's own config still applies, unchanged.
    assert job.release_start == datetime(2024, 12, 10, 0)
    assert job.release_end == datetime(2024, 12, 10, 6)


def test_resolve_job_config_does_not_warn_about_a_recognised_override(tmp_path, reference_data_end, caplog):
    """Every scheduled run passes through here, so the check must not be a source of noise."""

    site = _site(tmp_path, "release_start_offset_h: 3\n")

    with caplog.at_level(logging.WARNING):
        resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site,
                           overrides={"release_start_offset_h": 1})

    assert "unrecognised" not in caplog.text


def test_resolve_job_config_rejects_a_reversed_release_window(tmp_path, reference_data_end):

    site = _site(tmp_path, "release_start_offset_h: 9\nrelease_end_offset_h: 3\n")

    with pytest.raises(RuntimeError, match="release_end_offset_h.*before"):
        resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site)


def test_resolve_job_config_rejects_an_empty_simulation_window(tmp_path, reference_data_end):
    """A simulation that starts after the data ends is a configuration error, not an empty run."""

    site = _site(tmp_path, "simulation_start_offset_h: 48\n")

    with pytest.raises(RuntimeError, match="empty simulation window"):
        resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site)


def test_resolve_job_config_requires_the_data_end_variables(tmp_path, monkeypatch):

    for suffix in ("YYYY", "MM", "DD", "ZZ"):
        monkeypatch.delenv(f"SIMULATION_END_{suffix}", raising=False)
    site = _site(tmp_path)

    with pytest.raises(RuntimeError, match="missing variables"):
        resolve_job_config(FORECAST, Model.IFS_HRES_EUROPE, site)


def test_resolve_job_config_rejects_a_malformed_forecast_datetime(tmp_path, reference_data_end):

    site = _site(tmp_path)

    with pytest.raises(RuntimeError, match="YYYYMMDDhhmm"):
        resolve_job_config("2024121", Model.IFS_HRES_EUROPE, site)
