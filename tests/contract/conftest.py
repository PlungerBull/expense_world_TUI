"""Shared gating, target resolution and the real-ledger guard for tests/contract.

These tests hit a real engine and make real writes, so a contract run that would write to
the real ledger **refuses to start**. Point it at the disposable practice database
instead, or set EXPENSE_ALLOW_REAL_LEDGER=1 to say you meant it.

How to seed the practice user, start the test engine on :8002 and run this suite:
docs/cli-runtime.md "Working against the live engine".
"""

import os

import pytest

from expense import config as config_module
from expense.config import Config
from expense.errors import EngineError
from expense.http import ExpenseClient

# The default is the one real engine, the local deployment. A practice run sets
# EXPENSE_ENGINE_URL to the disposable test engine on :8002.
DEFAULT_ENGINE_URL = "http://127.0.0.1:8000"

ENGINE_URL = os.environ.get("EXPENSE_ENGINE_URL", DEFAULT_ENGINE_URL)
PAT = os.environ.get("EXPENSE_PAT")
ALLOW_REAL_LEDGER = os.environ.get("EXPENSE_ALLOW_REAL_LEDGER") == "1"

LIVE = os.environ.get("PYTEST_LIVE") == "1"


def reason_on(err: EngineError, field: str) -> str | None:
    """The engine's reason code for `field`, or None when it names no reason there
    (contract: "Error reasons")."""
    if not isinstance(err.reasons, dict):
        return None
    return err.reasons.get(field)


def pytest_collection_modifyitems(config, items):
    """Gate the whole directory on PYTEST_LIVE=1.

    This is a hook, not a module-level `pytestmark`: a `pytestmark` assigned in a
    conftest does NOT apply to tests in other modules, so relying on it lets
    `pytest tests/contract` run against the live engine and create rows. The gate
    belongs somewhere that provably covers every item.
    """
    if LIVE:
        return
    skip = pytest.mark.skip(reason="Contract tests require PYTEST_LIVE=1")
    for item in items:
        item.add_marker(skip)


_REFUSAL = """
┌────────────────────────────────────────────────────────────┐
│  REFUSING TO RUN                                           │
│  this would write to your real ledger                      │
│    engine       {url:<42}│
│    signed in as you, from ~/.expense-config                │
│    rows created here are soft-deleted, never removed       │
│                                                            │
│  practice database instead:                                │
│    ../expense_world_engine/deploy/local/seed-test-user.sh  │
│    then EXPENSE_PAT=… EXPENSE_ENGINE_URL=http://127.0.0.1:8002
│                                                            │
│  or, to mean it:                                           │
│    EXPENSE_ALLOW_REAL_LEDGER=1                             │
└────────────────────────────────────────────────────────────┘
"""


def _is_real_ledger() -> bool:
    """True when the run would write as the developer, to their own ledger.

    A PAT in the environment is the isolation signal: it is how the practice user
    is addressed. Without one, the only credential available is the developer's
    saved config — which is the real ledger by definition, whatever the URL says.
    """
    return not PAT


def pytest_sessionstart(session):
    """Refuse rather than warn — before collection, before any fixture.

    Deliberately a session hook rather than an autouse fixture: a fixture only runs
    when something requests it, and the guard must hold even if a future test
    forgets the `client` fixture entirely.
    """
    if not LIVE:
        return
    if _is_real_ledger() and not ALLOW_REAL_LEDGER:
        pytest.exit(_REFUSAL.format(url=ENGINE_URL), returncode=2)
    source = "EXPENSE_PAT" if PAT else "~/.expense-config (ALLOWED EXPLICITLY)"
    print(f"\ncontract target: {ENGINE_URL} · credential: {source}")


@pytest.fixture
def client():
    """An ExpenseClient aimed at the resolved target.

    Prefers EXPENSE_PAT + EXPENSE_ENGINE_URL so every module obeys the same target
    as the freshman walk; falls back to the developer's config only when the guard
    above has explicitly allowed it.
    """
    cfg = Config(engine_url=ENGINE_URL, token=PAT) if PAT else config_module.ensure_loaded()
    with ExpenseClient(cfg) as c:
        yield c
