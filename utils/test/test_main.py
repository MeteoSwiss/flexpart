
import os
import subprocess
import sys

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


_GENERATE_ARGS = ["generate", "--flexpart_dir", "/unused", "--jobs_dir", "/unused",
                  "--datetime", "202412092100", "--site", "Testerhausen", "--model", "IFS-Europe"]


def _run_cli(*args):
    return subprocess.run([sys.executable, "-m", "flexpart_ifs_utils", *args],
                          capture_output=True, text=True, check=False)


def test_generate_accepts_a_direction_option():
    result = _run_cli("generate", "--help")

    assert result.returncode == 0
    assert "--direction {forward,backward}" in result.stdout


def test_generate_rejects_an_unknown_direction():
    """argparse stops before any S3 access, so a typo in DIRECTION fails the task up front."""
    result = _run_cli(*_GENERATE_ARGS, "--direction", "sideways")

    assert result.returncode == 2
    assert "invalid choice: 'sideways'" in result.stderr


@pytest.fixture
def run_entrypoint_until_generate(tmp_path):
    """Run entrypoint.sh against a stub `python` that records its arguments and fails, so ``set -e``
    stops the script right after the generate call - nothing past it (Flexpart, upload) runs."""
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    args_file = tmp_path / "python_args"
    stub = stub_bin / "python"
    stub.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" > "$ARGS_FILE"\nexit 1\n', encoding="utf-8")
    stub.chmod(0o755)

    def run(direction=None):
        env = {k: v for k, v in os.environ.items() if k != "DIRECTION"}
        env.update({
            "PATH": f"{stub_bin}{os.pathsep}{env.get('PATH', '')}",
            "ARGS_FILE": str(args_file),
            "FLEXPART_PREFIX": "/opt/flexpart", "JOBS_DIR": str(tmp_path / "jobs"),
            "FORECAST_DATETIME": "202412092100", "RELEASE_SITE_NAME": "Testerhausen",
            "MODEL": "IFS-Europe",
        })
        if direction is not None:
            env["DIRECTION"] = direction
        result = subprocess.run(["bash", os.environ["PYTEST_ENTRYPOINT"]], env=env,
                                capture_output=True, text=True, check=False)
        assert result.returncode == 1, result.stdout + result.stderr
        return args_file.read_text(encoding="utf-8").splitlines()

    return run


@pytest.mark.parametrize("direction", ["forward", "backward"])
def test_entrypoint_passes_direction_to_generate(run_entrypoint_until_generate, direction):
    args = run_entrypoint_until_generate(direction)

    assert args[:3] == ["-m", "flexpart_ifs_utils", "generate"]
    assert args[-2:] == ["--direction", direction]


@pytest.mark.parametrize("direction", [None, ""])
def test_entrypoint_omits_direction_when_unset_or_empty(run_entrypoint_until_generate, direction):
    """No DIRECTION means the site config's own direction applies."""
    args = run_entrypoint_until_generate(direction)

    assert args[:3] == ["-m", "flexpart_ifs_utils", "generate"]
    assert "--direction" not in args
