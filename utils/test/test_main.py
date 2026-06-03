
import pytest

from flexpart_ifs_utils.__main__ import parse_env, validate_env


@pytest.fixture
def mock_environment_incomplete(monkeypatch):
    # SIMULATION_END_ZZ is intentionally not set here
    monkeypatch.setenv("EMISSION_START_YYYY", '2026')
    monkeypatch.setenv("EMISSION_START_MM", '05')
    monkeypatch.setenv("EMISSION_START_DD", '15')
    monkeypatch.setenv("EMISSION_START_ZZ", '00')
    monkeypatch.setenv("EMISSION_END_YYYY", '2026')
    monkeypatch.setenv("EMISSION_END_MM", '05')
    monkeypatch.setenv("EMISSION_END_DD", '20')
    monkeypatch.setenv("EMISSION_END_ZZ", '00')
    monkeypatch.setenv("SIMULATION_END_YYYY", '2026')
    monkeypatch.setenv("SIMULATION_END_MM", '05')
    monkeypatch.setenv("SIMULATION_END_DD", '25')
    #monkeypatch.setenv("SIMULATION_END_ZZ", '00')

def test_validate_env(mock_environment_incomplete):

    environment = parse_env()

    with pytest.raises(RuntimeError) as exc_info:
        validate_env(environment)

    assert "Environment is missing variables needed to prepare runtime configuration: ['SIMULATION_END_ZZ']" in str(exc_info.value)
