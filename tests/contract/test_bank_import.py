"""Contract: `POST /transactions/import`.

`expense import bank` makes exactly this one call and prints what comes back,
so what the preview and the apply say is the engine's word. Pinned here:

  · a dry run answers `new` and writes nothing;
  · the apply writes the row, and the same file again is `matched` by
    `operation_code`, claiming that row;
  · a row not in the ledger, dated inside a completed period, is `sealed` and
    names the period: never written, never an error.

Each test builds its own account. Gating, target and the real-ledger guard:
conftest.py.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from expense.errors import EngineError


def _safe(call, *args):
    try:
        call(*args)
    except EngineError:
        pass


def _make_account(client) -> str:
    new_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={"id": new_id, "name": f"contract-import-{new_id[:8]}", "currency_code": "PEN"},
    )
    return new_id


def _row(account_id: str, day: str, code: str) -> dict:
    return {
        "id": str(uuid4()),
        "account_id": account_id,
        "date": day,
        "amount_cents": -2590,
        "title": "DLC*RIDES LIMA PE",
        "operation_code": code,
    }


def _count(client, account_id: str) -> int:
    return client.get("/transactions/count", params={"account_id": account_id})["count"]


def test_dry_run_then_apply_then_the_same_file_matches(client):
    account = _make_account(client)
    code = f"OP-{uuid4().hex[:10]}"
    created: list[str] = []
    try:
        row = _row(account, "2026-03-05", code)
        dry = client.post("/transactions/import", json_body={"dry_run": True, "rows": [row]})
        assert [r["outcome"] for r in dry["rows"]] == ["new"]
        assert dry["counts"]["new"] == 1
        assert _count(client, account) == 0

        applied = client.post("/transactions/import", json_body={"dry_run": False, "rows": [row]})
        assert [r["outcome"] for r in applied["rows"]] == ["new"]
        created.append(row["id"])
        assert _count(client, account) == 1
        assert client.get(f"/transactions/{row['id']}")["operation_code"] == code

        again = _row(account, "2026-03-05", code)
        second = client.post("/transactions/import", json_body={"dry_run": False, "rows": [again]})
        (only,) = second["rows"]
        assert only["outcome"] == "matched"
        assert only["rule"] == "operation_code"
        assert only["ledger_id"] == row["id"]
        assert _count(client, account) == 1
    finally:
        for tx_id in created:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_row_inside_a_completed_period_comes_back_sealed(client):
    zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
    account = _make_account(client)
    anchor = str(uuid4())
    period = str(uuid4())
    try:
        client.post(
            "/transactions",
            json_body={
                "id": anchor,
                "amount_cents": -100,
                "account_id": account,
                "date": datetime(2026, 2, 5, 12, tzinfo=zone).isoformat(timespec="seconds"),
            },
        )
        client.post(
            "/reconciliations",
            json_body={
                "id": period,
                "account_id": account,
                "name": f"contract-import-{period[:8]}",
                "date_start": "2026-02-01",
                "date_end": "2026-02-28",
                "beginning_balance_cents": 0,
            },
        )
        client.put(f"/transactions/{anchor}", json_body={"reconciliation_id": period})
        client.post(f"/reconciliations/{period}/complete")

        row = _row(account, "2026-02-10", f"OP-{uuid4().hex[:10]}")
        body = client.post("/transactions/import", json_body={"dry_run": False, "rows": [row]})
        (only,) = body["rows"]
        assert only["outcome"] == "sealed"
        assert only["sealed_by"] == period
        assert body["counts"]["sealed"] == 1
        assert _count(client, account) == 1  # the anchor only
    finally:
        _safe(client.post, f"/reconciliations/{period}/revert")
        _safe(client.delete, f"/reconciliations/{period}")
        _safe(client.delete, f"/transactions/{anchor}")
        _safe(client.delete, f"/accounts/{account}")
