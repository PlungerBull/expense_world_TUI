"""Contract: a brand-new user's first walk, straight against the engine (live).

    settings file → health → bootstrap → me
    → account create → category create → transaction create → dashboard → cleanup

Every step is one engine call through the app's own HTTP client, built from a
settings file saved and read back the way the app's setup screen does it.

Hits a real engine. Gated on PYTEST_LIVE=1 and EXPENSE_PAT; the target and the
real-ledger guard come from conftest.py. Redirects EXPENSE_CONFIG to a temp dir so
the developer's own install is untouched.

Uses a USD account regardless of the user's main_currency, to walk the
cross-currency path. A write never resolves a rate at all —
conversion happens at read time — so RATE_UNAVAILABLE cannot fire here; a
missing rate surfaces as a null aggregate plus an unconverted count on the
read side instead.
"""

import os
from uuid import uuid4

import pytest

from expense import config as config_module
from expense.dates import detect_timezone, now_local_iso
from expense.errors import EngineError
from expense.http import ExpenseClient
from tests.contract.conftest import ENGINE_URL, PAT, account_body

pytestmark = pytest.mark.skipif(
    os.environ.get("PYTEST_LIVE") != "1" or not PAT,
    reason="Freshman flow requires PYTEST_LIVE=1 and EXPENSE_PAT",
)


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPENSE_CONFIG", str(tmp_path / "config"))
    return tmp_path


def _safe_delete(client: ExpenseClient, path: str) -> None:
    try:
        client.delete(path)
    except EngineError:
        pass


def test_freshman_flow(isolated_env):
    config_file = isolated_env / "config"

    config_module.save(config_module.Config(engine_url=ENGINE_URL, token=PAT))
    assert config_file.exists(), "config file was not created at the EXPENSE_CONFIG path"
    cfg = config_module.ensure_loaded()

    with ExpenseClient(cfg) as client:
        health = client.get("/health", auth=False)
        assert isinstance(health, dict), f"/health did not answer with an object: {health}"

        # Bootstrap is an idempotent re-login for an already-provisioned PAT user
        # and never overwrites their display_name.
        client.post(
            "/auth/bootstrap",
            json_body={"display_name": "Freshman Gate", "timezone": detect_timezone()},
        )

        me = client.get("/auth/me")
        assert me.get("user", {}).get("id"), f"/auth/me missing user.id: {me}"

        account_id = None
        category_id = None
        transaction_id = None
        suffix = uuid4().hex[:8]
        try:
            body = {**account_body("USD"), "name": f"freshman-{suffix}"}
            account = client.post("/accounts", json_body=body)
            account_id = account["id"]

            new_id = str(uuid4())
            category = client.post(
                "/categories",
                json_body={
                    "id": new_id,
                    "name": f"freshman-cat-{suffix}",
                    "color": "#4ECDC4",  # required by the engine (categories carry a color hint)
                },
            )
            category_id = category["id"]

            new_id = str(uuid4())
            transaction = client.post(
                "/transactions",
                json_body={
                    "id": new_id,
                    "title": "freshman smoke",
                    "amount_cents": -100,
                    "account_id": account_id,
                    "currency_code": "USD",
                    "category_id": category_id,
                    "date": now_local_iso(),
                },
            )
            transaction_id = transaction["id"]

            dashboard = client.get("/dashboard")
            assert any(key in dashboard for key in ("totals", "accounts", "bank_accounts")), (
                f"/dashboard missing expected keys; got: {sorted(dashboard.keys())}"
            )
        finally:
            # Best-effort cleanup; reverse dependency order. Ignore failures.
            if transaction_id:
                _safe_delete(client, f"/transactions/{transaction_id}")
            if category_id:
                _safe_delete(client, f"/categories/{category_id}")
            if account_id:
                _safe_delete(client, f"/accounts/{account_id}")
