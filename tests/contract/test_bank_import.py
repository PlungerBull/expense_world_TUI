"""Contract: `POST /transactions/import`.

The TUI import door makes exactly this one call and draws what comes back,
so what the preview and the apply say is the engine's word. Pinned here:

  · a dry run answers `new` and writes nothing;
  · the apply writes the row, and the same file again is `matched` by
    `operation_code`, naming that row's bank line, not retitled (the title is
    the bank's already), and with no day whose totals disagree;
  · a day where the ledger holds a line the file does not is a
    `day_mismatches` entry: both totals signed, and the leftover line as
    exactly `bank_line_id`, its signed `net_cents` and its `parts`, each the
    response `GET /transactions/{id}` returns;
  · a split line no file row claimed is one entry holding every part, its
    `net_cents` their signed sum;
  · a day whose totals agree is still reported when it holds a line no file
    row claimed;
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
        written = client.get(f"/transactions/{row['id']}")
        assert written["operation_code"] == code

        again = _row(account, "2026-03-05", code)
        second = client.post("/transactions/import", json_body={"dry_run": False, "rows": [again]})
        (only,) = second["rows"]
        assert only["outcome"] == "matched"
        assert only["rule"] == "operation_code"
        assert only["bank_line_id"] == written["bank_line_id"]
        assert only["retitled"] is False
        assert second["counts"]["retitled"] == 0
        assert second["day_mismatches"] == []
        assert _count(client, account) == 1
    finally:
        for tx_id in created:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_leftover_ledger_line_is_reported_on_its_day(client):
    zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
    account = _make_account(client)
    ledger = [str(uuid4()), str(uuid4())]
    try:
        for tx_id in ledger:
            client.post(
                "/transactions",
                json_body={
                    "id": tx_id,
                    "amount_cents": -2590,
                    "account_id": account,
                    "date": datetime(2026, 3, 9, 12, tzinfo=zone).isoformat(timespec="seconds"),
                },
            )
        row = _row(account, "2026-03-09", "")
        del row["operation_code"]  # a card line: no code, matched by day and total
        body = client.post("/transactions/import", json_body={"dry_run": True, "rows": [row]})
        (only,) = body["rows"]
        assert only["outcome"] == "matched" and only["rule"] == "same_day"
        (day,) = body["day_mismatches"]
        assert day["account_id"] == account and day["date"] == "2026-03-09"
        assert (day["file_net_cents"], day["ledger_net_cents"]) == (-2590, -5180)
        assert day["unmatched_rows"] == []
        (line,) = day["unclaimed_lines"]
        assert set(line) == {"bank_line_id", "net_cents", "parts"}
        assert line["net_cents"] == -2590
        (part,) = line["parts"]
        assert part["id"] in ledger
        # The part is the transaction response itself: a magnitude, the direction
        # in `transaction_type` (contract: "Base Conventions", "Sign convention — responses").
        assert part == client.get(f"/transactions/{part['id']}")
        assert (part["amount_cents"], part["transaction_type"]) == (2590, 1)
        assert line["bank_line_id"] == part["bank_line_id"]
        assert only["bank_line_id"] != line["bank_line_id"]
    finally:
        for tx_id in ledger:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def _post_at_noon(client, zone: ZoneInfo, account: str, day: int, amount: int) -> str:
    tx_id = str(uuid4())
    client.post(
        "/transactions",
        json_body={
            "id": tx_id,
            "amount_cents": amount,
            "account_id": account,
            "date": datetime(2026, 3, day, 12, tzinfo=zone).isoformat(timespec="seconds"),
        },
    )
    return tx_id


def test_a_split_unclaimed_line_is_one_entry_with_every_part(client):
    zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
    account = _make_account(client)
    written: list[str] = []
    try:
        whole = _post_at_noon(client, zone, account, 12, -10000)
        written.append(whole)
        parts = [{"id": str(uuid4()), "amount_cents": a} for a in (-6000, -4000)]
        written.extend(p["id"] for p in parts)
        client.post(f"/transactions/{whole}/split", json_body={"parts": parts})

        row = _row(account, "2026-03-12", "")
        del row["operation_code"]
        body = client.post("/transactions/import", json_body={"dry_run": True, "rows": [row]})
        (only,) = body["rows"]
        assert only["outcome"] == "new"
        (day,) = body["day_mismatches"]
        assert (day["file_net_cents"], day["ledger_net_cents"]) == (-2590, -12590)
        assert day["unmatched_rows"] == [0]
        (line,) = day["unclaimed_lines"]
        assert set(line) == {"bank_line_id", "net_cents", "parts"}
        assert line["net_cents"] == -10000
        assert {p["id"] for p in line["parts"]} == {p["id"] for p in parts}
        assert {p["bank_line_id"] for p in line["parts"]} == {line["bank_line_id"]}
        assert sorted(p["amount_cents"] for p in line["parts"]) == [4000, 6000]
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_day_whose_totals_agree_is_reported_for_its_unclaimed_lines(client):
    """A +50 and a -50 the file does not have cancel out, and the day is still
    reported (contract: POST /v1/transactions/import)."""
    zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
    account = _make_account(client)
    written: list[str] = []
    try:
        matched = _post_at_noon(client, zone, account, 13, -2590)
        plus = _post_at_noon(client, zone, account, 13, 5000)
        minus = _post_at_noon(client, zone, account, 13, -5000)
        written.extend([matched, plus, minus])

        row = _row(account, "2026-03-13", "")
        del row["operation_code"]
        body = client.post("/transactions/import", json_body={"dry_run": True, "rows": [row]})
        (only,) = body["rows"]
        assert only["outcome"] == "matched" and only["rule"] == "same_day"
        (day,) = body["day_mismatches"]
        assert day["date"] == "2026-03-13"
        assert day["file_net_cents"] == day["ledger_net_cents"] == -2590
        assert day["unmatched_rows"] == []
        lines = day["unclaimed_lines"]
        assert all(set(line) == {"bank_line_id", "net_cents", "parts"} for line in lines)
        assert sorted(line["net_cents"] for line in lines) == [-5000, 5000]
        assert sorted(p["id"] for line in lines for p in line["parts"]) == sorted([plus, minus])
    finally:
        for tx_id in written:
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
                "ending_balance_cents": -100,
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
