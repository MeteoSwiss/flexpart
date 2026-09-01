
import pytest

from flexpart_ifs_utils.job_config import _data_end_from_env


@pytest.fixture
def mock_environment_incomplete(monkeypatch):
    # SIMULATION_END_ZZ is intentionally not set here
    monkeypatch.setenv("SIMULATION_END_YYYY", '2026')
    monkeypatch.setenv("SIMULATION_END_MM", '05')
    monkeypatch.setenv("SIMULATION_END_DD", '25')
    monkeypatch.delenv("SIMULATION_END_ZZ", raising=False)


def test_missing_data_end_variable(mock_environment_incomplete):

    with pytest.raises(RuntimeError) as exc_info:
        _data_end_from_env()

    assert "['SIMULATION_END_ZZ']" in str(exc_info.value)
