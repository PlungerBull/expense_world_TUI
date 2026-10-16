"""Shared by tests/unit and tests/contract: keep every live run in one process.

pyproject's addopts give every run `-n auto` (pytest-xdist). A live run (PYTEST_LIVE=1)
includes the contract tests, which share one practice user and make real writes, so they
must not be spread over workers. tests/contract/conftest.py already does this for runs
started in tests/contract; this hook covers runs started above it (a bare `pytest`, or
`pytest tests`), where that conftest loads too late for xdist's question.
"""

import os

import pytest


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config):
    """Zero workers (one process) for a live run; otherwise xdist's own count.
    An explicit `-n N` is never asked about, so it still gets N workers."""
    if os.environ.get("PYTEST_LIVE") == "1":
        return 0
    return None
