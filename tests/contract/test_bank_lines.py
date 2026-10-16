"""Contract: bank lines and splits — `POST /v1/transactions/{transaction_id}/split`.

Every transaction belongs to one bank line, and a split turns one line into several
parts that keep its identity (contract: "Transactions (Ledger)", "Bank lines"). The
split screen, the edit form's "reaches every part" note and the bank upload all
stand on rules only the engine can confirm. Pinned here:

  · a split into two parts is `201` with the parts in request order, all on the
    line's `bank_line_id`, each taking the line's title, date and account;
  · a re-split (60 + 40 into 70 + 30), sent by the id of one part, replaces the
    line's whole set on the same line;
  · `PUT` of `title` on one part writes it onto every part, while `amount_cents`
    and `description` change only the part named;
  · a statement imported, split and imported again is every row `matched`, none
    `new`: by `operation_code`, and by `same_day` for a card row with no code;
  · the split refusals: `SPLIT_TOTAL_MISMATCH` on `parts` and every
    `parts.<i>.amount_cents`, `SPLIT_RECONCILIATION_MIXED` and
    `OPENING_BALANCE_NOT_SPLIT` on `transaction_id`; and a batch `line_group`
    whose items differ is `LINE_GROUP_FIELDS_DIFFER` on each item's field.

Not pinned here: `SPLIT_LINE_PARTS_DIVERGE`. No route leaves a line's parts on
different accounts or dates: a split gives every part the line's account and
date, a `line_group` must share them, and `PUT` writes either onto every part
(contract: "Transactions (Ledger)", "Bank lines"). Only rows from before the
engine kept lines could show it, and the practice user has none.

Each test builds its own account and undoes what it wrote. Gating, target and the
real-ledger guard: conftest.py.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense.errors import EngineError
from tests.contract.conftest import reason_on


def _safe(call, *args):
    try:
        call(*args)
    except EngineError:
        pass


def _refused(call) -> EngineError:
    with pytest.raises(EngineError) as excinfo:
        call()
    return excinfo.value


def _zone(client) -> ZoneInfo:
    return ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])


def _noon(zone: ZoneInfo, y: int, m: int, d: int) -> str:
    return datetime(y, m, d, 12, tzinfo=zone).isoformat(timespec="seconds")


def _make_account(client) -> str:
    new_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={"id": new_id, "name": f"contract-lines-{new_id[:8]}", "currency_code": "PEN"},
    )
    return new_id


def _make_category(client) -> str:
    new_id = str(uuid4())
    client.post(
        "/categories",
        json_body={"id": new_id, "name": f"contract-lines-{new_id[:8]}", "color": "#123456"},
    )
    return new_id


def _post_tx(client, account_id: str, date: str, amount: int, title: str) -> dict:
    return client.post(
        "/transactions",
        json_body={
            "id": str(uuid4()),
            "title": title,
            "amount_cents": amount,
            "account_id": account_id,
            "date": date,
        },
    )


def _split(client, tx_id: str, amounts: list[int], written: list[str], **extra) -> list[dict]:
    """Split the line holding `tx_id` into parts of `amounts`; every part id is kept
    in `written` before the call, so cleanup reaches whatever the engine created."""
    parts = [{"id": str(uuid4()), "amount_cents": a, **extra} for a in amounts]
    written.extend(p["id"] for p in parts)
    return client.post(f"/transactions/{tx_id}/split", json_body={"parts": parts})["parts"]


def _signed(client, tx_id: str) -> dict:
    """The transaction read signed, negative for money out: write responses carry
    the magnitude and `transaction_type`
    (contract: "Base Conventions", "Sign convention — responses")."""
    return client.get(f"/transactions/{tx_id}", params={"debit_as_negative": "true"})


def _live_ids(client, account_id: str) -> set[str]:
    listed = client.get("/transactions", params={"account_id": account_id})
    return {item["id"] for item in listed["items"]}


@pytest.fixture
def statuses(client):
    """The HTTP status of every response `client` receives, in order. The client
    returns only the body on success, so the `201` is read off httpx's own hook on
    the repo client's transport."""
    seen: list[int] = []
    hooks = client._client.event_hooks
    hooks["response"] = [*hooks.get("response", []), lambda r: seen.append(r.status_code)]
    return seen


def test_split_then_re_split_keep_the_line(client, statuses):
    zone = _zone(client)
    account = _make_account(client)
    groceries = _make_category(client)
    written: list[str] = []
    try:
        date = _noon(zone, 2026, 4, 6)
        original = _post_tx(client, account, date, -10000, "SUPERMERCADO LIMA")
        written.append(original["id"])
        line = original["bank_line_id"]
        assert line

        # Split into two: 201, request order, one line, the line's title/date/account.
        parts = [
            {
                "id": str(uuid4()),
                "amount_cents": -6000,
                "category_id": groceries,
                "description": "food",
            },
            {"id": str(uuid4()), "amount_cents": -4000},
        ]
        written.extend(p["id"] for p in parts)
        body = client.post(f"/transactions/{original['id']}/split", json_body={"parts": parts})
        assert statuses[-1] == 201
        first = body["parts"]
        assert [p["id"] for p in first] == [p["id"] for p in parts]
        assert [_signed(client, p["id"])["amount_cents"] for p in first] == [-6000, -4000]
        assert {p["bank_line_id"] for p in first} == {line}
        for part in first:
            assert part["title"] == "SUPERMERCADO LIMA"
            assert part["account_id"] == account
            assert datetime.fromisoformat(part["date"]) == datetime.fromisoformat(date)
        assert first[0]["category_id"] == groceries
        assert first[0]["description"] == "food"
        assert _live_ids(client, account) == {p["id"] for p in parts}

        # Re-split 60 + 40 into 70 + 30, by the id of the second part.
        second = _split(client, first[1]["id"], [-7000, -3000], written)
        assert [_signed(client, p["id"])["amount_cents"] for p in second] == [-7000, -3000]
        assert {p["bank_line_id"] for p in second} == {line}
        assert _live_ids(client, account) == {p["id"] for p in second}
        for gone in first:
            err = _refused(lambda gone=gone: client.get(f"/transactions/{gone['id']}"))
            assert err.status == 404
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/categories/{groceries}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_line_field_reaches_every_part_and_the_rest_stay_own(client):
    zone = _zone(client)
    account = _make_account(client)
    written: list[str] = []
    try:
        original = _post_tx(client, account, _noon(zone, 2026, 4, 7), -5000, "FARMACIA")
        written.append(original["id"])
        one, two = _split(client, original["id"], [-3000, -2000], written)

        # A line field: written onto every part, the response is the part named.
        edited = client.put(f"/transactions/{one['id']}", json_body={"title": "FARMACIA CENTRAL"})
        assert edited["id"] == one["id"]
        assert edited["title"] == "FARMACIA CENTRAL"
        other = client.get(f"/transactions/{two['id']}")
        assert other["title"] == "FARMACIA CENTRAL"
        assert other["version"] > two["version"]

        # A part's own fields: only the part named changes.
        before = client.get(f"/transactions/{two['id']}")
        client.put(
            f"/transactions/{one['id']}",
            json_body={"amount_cents": -3500, "description": "vitamins"},
        )
        mine = _signed(client, one["id"])
        assert (mine["amount_cents"], mine["description"]) == (-3500, "vitamins")
        after = _signed(client, two["id"])
        assert after["amount_cents"] == -2000
        assert after["description"] == before["description"]
        assert after["version"] == before["version"]
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


@pytest.mark.parametrize(
    ("code", "rule"),
    [(f"OP-{uuid4().hex[:10]}", "operation_code"), (None, "same_day")],
    ids=["with-operation-code", "card-row-no-code"],
)
def test_a_split_line_is_matched_on_re_import(client, code, rule):
    account = _make_account(client)
    written: list[str] = []

    def statement() -> list[dict]:
        row = {
            "id": str(uuid4()),
            "account_id": account,
            "date": "2026-04-08",
            "amount_cents": -8000,
            "title": "TIENDA LIMA PE",
        }
        if code is not None:
            row["operation_code"] = code
        return [row]

    try:
        rows = statement()
        first = client.post("/transactions/import", json_body={"dry_run": False, "rows": rows})
        assert [r["outcome"] for r in first["rows"]] == ["new"]
        written.append(rows[0]["id"])
        line = client.get(f"/transactions/{rows[0]['id']}")["bank_line_id"]

        parts = _split(client, rows[0]["id"], [-5000, -3000], written)
        assert {p["bank_line_id"] for p in parts} == {line}

        again = client.post(
            "/transactions/import", json_body={"dry_run": False, "rows": statement()}
        )
        (only,) = again["rows"]
        assert only["outcome"] == "matched"
        assert only["rule"] == rule
        assert only["bank_line_id"] == line
        assert again["counts"]["new"] == 0
        assert again["counts"]["matched"] == 1
        assert again["day_mismatches"] == []
        assert _live_ids(client, account) == {p["id"] for p in parts}
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def test_split_parts_that_miss_the_total_are_split_total_mismatch(client):
    zone = _zone(client)
    account = _make_account(client)
    written: list[str] = []
    try:
        original = _post_tx(client, account, _noon(zone, 2026, 4, 9), -10000, "line")
        written.append(original["id"])
        err = _refused(lambda: _split(client, original["id"], [-6000, -3000], written))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        for key in ("parts", "parts.0.amount_cents", "parts.1.amount_cents"):
            assert reason_on(err, key) == "SPLIT_TOTAL_MISMATCH"
        # The message gives both totals in cents.
        assert "-10000" in err.fields["parts"] and "-9000" in err.fields["parts"]
        assert _live_ids(client, account) == {original["id"]}
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_line_in_two_reconciliations_is_split_reconciliation_mixed(client):
    zone = _zone(client)
    account = _make_account(client)
    recon = str(uuid4())
    written: list[str] = []
    try:
        original = _post_tx(client, account, _noon(zone, 2026, 4, 10), -10000, "line")
        written.append(original["id"])
        one, two = _split(client, original["id"], [-6000, -4000], written)
        client.post(
            "/reconciliations",
            json_body={
                "id": recon,
                "account_id": account,
                "name": f"contract-lines-{recon[:8]}",
                "date_start": "2026-04-01",
                "date_end": "2026-04-30",
                "beginning_balance_cents": 0,
            },
        )
        # `reconciliation_id` settles the part named alone, so the line is now mixed.
        client.put(f"/transactions/{one['id']}", json_body={"reconciliation_id": recon})

        err = _refused(lambda: _split(client, two["id"], [-5000, -5000], written))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "transaction_id") == "SPLIT_RECONCILIATION_MIXED"
        assert _live_ids(client, account) == {one["id"], two["id"]}
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/accounts/{account}")


def test_an_opening_balance_is_not_split(client):
    account = _make_account(client)
    opening = str(uuid4())
    written: list[str] = []
    try:
        client.post(
            f"/accounts/{account}/opening-balance",
            json_body={
                "transaction_id": opening,
                "amount_cents": 10000,
                "date": "2026-01-01T00:00:00Z",
            },
        )
        err = _refused(lambda: _split(client, opening, [6000, 4000], written))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "transaction_id") == "OPENING_BALANCE_NOT_SPLIT"
        assert _live_ids(client, account) == {opening}
    finally:
        for tx_id in [*written, opening]:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_line_group_whose_items_differ_is_line_group_fields_differ(client):
    zone = _zone(client)
    account = _make_account(client)
    ids = [str(uuid4()), str(uuid4())]
    date = _noon(zone, 2026, 4, 11)
    try:
        err = _refused(
            lambda: client.post(
                "/transactions/batch",
                json_body={
                    "transactions": [
                        {
                            "id": ids[0],
                            "title": "CHARGE A",
                            "amount_cents": -100,
                            "account_id": account,
                            "date": date,
                            "line_group": "g1",
                        },
                        {
                            "id": ids[1],
                            "title": "CHARGE B",
                            "amount_cents": -200,
                            "account_id": account,
                            "date": date,
                            "line_group": "g1",
                        },
                    ]
                },
            )
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        for key in ("transactions.0.title", "transactions.1.title"):
            assert reason_on(err, key) == "LINE_GROUP_FIELDS_DIFFER"
        assert _live_ids(client, account) == set()
    finally:
        for tx_id in ids:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")
