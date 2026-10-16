"""Guard: the unit suite runs in parallel by default, the live contract suite never does.

`addopts` in pyproject.toml gives every pytest run `-n auto` (pytest-xdist), so the tests
gate, CI and hand runs of `pytest tests/unit` all spread over one worker per core; `-n0`
forces one process. tests/contract/conftest.py turns "auto" into zero workers because its
tests share one practice user and make real writes (CLAUDE.md "Dev loop").
"""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_pyproject_runs_the_suite_on_one_worker_per_core():
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert pyproject["tool"]["pytest"]["ini_options"]["addopts"] == ["-n", "auto"]


def test_a_plain_contract_run_stays_in_one_process(tmp_path):
    """Not live (no PYTEST_LIVE), so every contract test skips and nothing is called."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_LIVE", "EXPENSE_PAT")}
    env["EXPENSE_CONFIG"] = str(tmp_path / "config")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/contract", "-p", "no:cacheprovider"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "skipped" in out, out
    assert "workers" not in out, "the contract suite must not start xdist workers"


def _run_copy_of_tests_conftest(tmp_path, live: bool) -> str:
    """A bare `pytest` over a copy of tests/conftest.py plus one trivial test.

    The copy holds no contract test, so PYTEST_LIVE=1 here only feeds the worker-count
    decision; running the real tree live would send real writes to an engine."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text((REPO / "tests" / "conftest.py").read_text())
    (tests / "test_ok.py").write_text("def test_ok():\n    pass\n")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_LIVE", "EXPENSE_PAT")}
    env["EXPENSE_CONFIG"] = str(tmp_path / "config")
    if live:
        env["PYTEST_LIVE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-n", "auto", "-p", "no:cacheprovider"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "1 passed" in out, out
    return out


def test_a_live_run_started_above_tests_contract_stays_in_one_process(tmp_path):
    assert "workers" not in _run_copy_of_tests_conftest(tmp_path, live=True)


def test_a_run_that_is_not_live_still_uses_workers(tmp_path):
    assert "workers" in _run_copy_of_tests_conftest(tmp_path, live=False)
