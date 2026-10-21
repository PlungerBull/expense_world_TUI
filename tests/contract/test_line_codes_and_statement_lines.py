"""Contract: every bank line's `line_code`, and the `statement_line` a client writes on it.

Every bank line carries the engine's short code, `#` and six digits, given at its
create and never sent by a client; and an optional statement line, the client's
reference to the bank statement line the movement was checked against (contract:
"Transactions (Ledger)", "Bank lines"). The sheet import groups split rows into one
line and sends each line's statement line, so it stands on rules only the engine can
confirm. Pinned here:

  · a batch whose `line_group` holds two items makes one line whose parts read one
    `line_code`, and the next line of the batch takes the next code; a split of that
    line keeps its code on every new part;
  · `line_code` is in no request body: on `POST /transactions`, each item of
    `POST /transactions/batch`, each row of `POST /transactions/import`, the
    opening balance, each part of a split and `PUT /transactions/{id}` it is `422`
    `UNKNOWN_FIELD` under its own key, and nothing is written;
  · `statement_line` round-trips: trimmed on a create, written onto every part of a
    batch group, written by a `PUT` on one part onto every part of the line, and
    cleared by `null`; the line read by id reads it too;
  · one statement line is one bank line: a second live line with it is `409`
    `STATEMENT_LINE_EXISTS`, on a create, a batch item and a `PUT`; two lines with it
    in one batch are `422` `DUPLICATE_IN_REQUEST`; a deleted line frees it;
  · the items of one `line_group` differing on `statement_line` are `422`
    `LINE_GROUP_FIELDS_DIFFER` on each item, nothing written;
  · the opening balance, the split (a part, and beside `parts`) and the bank upload
    take no `statement_line`: `422` `UNKNOWN_FIELD`, nothing written;
  · in a completed reconciliation a set `statement_line` is locked, `422` `LOCKED`
    whether changed, cleared or resent as it is, while an empty one is filled once.

Every statement line a test writes carries a fragment of a fresh UUID: the practice
user's data outlives a reseed, so a value from an earlier run must never collide.
Each test builds its own account and undoes what it wrote. Gating, target and the
real-ledger guard: conftest.py.
"""

import re
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense.errors import EngineError
from tests.contract.conftest import reason_on

LINE_CODE = re.compile(r"^#\d{6}$")


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
        json_body={"id": new_id, "name": f"contract-sl-{new_id[:8]}", "currency_code": "PEN"},
    )
    return new_id


def _statement_line() -> str:
    """A statement line no earlier run of this suite has written."""
    return f"CT-{uuid4().hex[:12]}"


def _tx_body(account_id: str, date: str, amount: int, **extra) -> dict:
    return {
        "id": str(uuid4()),
        "title": "contract statement line",
        "amount_cents": amount,
        "account_id": account_id,
        "date": date,
        **extra,
    }


def _live_ids(client, account_id: str) -> set[str]:
    listed = client.get("/transactions", params={"account_id": account_id})
    return {item["id"] for item in listed["items"]}


def _cleanup(client, tx_ids: list[str], account_id: str) -> None:
    for tx_id in tx_ids:
        _safe(client.delete, f"/transactions/{tx_id}")
    _safe(client.delete, f"/accounts/{account_id}")


# ---- line_code ---------------------------------------------------------------


def test_a_line_group_reads_one_line_code_and_a_split_keeps_it(client):
    """The items of one `line_group` are the parts of one line and read one
    `line_code`; each line of the batch takes the next code in request order
    (contract: POST /v1/transactions/batch, "Line groups"). A split makes no new
    line: every new part reads the line's code
    (contract: POST /v1/transactions/{transaction_id}/split, "On success (atomic)")."""
    zone = _zone(client)
    account = _make_account(client)
    date = _noon(zone, 2026, 4, 6)
    group = [_tx_body(account, date, a, line_group="g1") for a in (-6000, -4000)]
    single = _tx_body(account, date, -2500)
    written = [item["id"] for item in [*group, single]]
    try:
        created = client.post("/transactions/batch", json_body={"transactions": [*group, single]})
        first, second, third = created["created"]
        assert first["bank_line_id"] == second["bank_line_id"] != third["bank_line_id"]
        code = first["line_code"]
        assert LINE_CODE.match(code)
        assert second["line_code"] == code
        assert third["line_code"] == f"#{int(code[1:]) + 1:06d}"
        line = first["bank_line_id"]
        read = client.get(f"/bank-lines/{line}")
        assert read["line_code"] == code
        assert {p["line_code"] for p in read["parts"]} == {code}

        parts = [{"id": str(uuid4()), "amount_cents": a} for a in (-5000, -3000, -2000)]
        written.extend(p["id"] for p in parts)
        split = client.post(f"/transactions/{second['id']}/split", json_body={"parts": parts})
        assert [p["line_code"] for p in split["parts"]] == [code, code, code]
        assert {p["bank_line_id"] for p in split["parts"]} == {line}
        assert client.get(f"/bank-lines/{line}")["line_code"] == code
        for part in parts:
            assert client.get(f"/transactions/{part['id']}")["line_code"] == code
    finally:
        _cleanup(client, written, account)


def _line_code_writes(account: str, date: str, tx_id: str) -> list[tuple[str, str, dict, str]]:
    """Every write that takes a body naming a transaction or its line, each sending
    `line_code` where a client field would go: (method, path, body, refused key)."""
    code = "#000001"
    return [
        ("POST", "/transactions", _tx_body(account, date, -100, line_code=code), "line_code"),
        (
            "POST",
            "/transactions/batch",
            {"transactions": [_tx_body(account, date, -100, line_code=code)]},
            "transactions.0.line_code",
        ),
        (
            "POST",
            "/transactions/import",
            {
                "dry_run": False,
                "rows": [
                    {
                        "id": str(uuid4()),
                        "account_id": account,
                        "date": date[:10],
                        "amount_cents": -100,
                        "line_code": code,
                    }
                ],
            },
            "rows.0.line_code",
        ),
        (
            "POST",
            f"/accounts/{account}/opening-balance",
            {"transaction_id": str(uuid4()), "amount_cents": 100, "date": date, "line_code": code},
            "line_code",
        ),
        (
            "POST",
            f"/transactions/{tx_id}/split",
            {
                "parts": [
                    {"id": str(uuid4()), "amount_cents": -60, "line_code": code},
                    {"id": str(uuid4()), "amount_cents": -40},
                ]
            },
            "parts.0.line_code",
        ),
        ("PUT", f"/transactions/{tx_id}", {"line_code": code}, "line_code"),
    ]


def test_line_code_is_in_no_request_body(client):
    """No client sends `line_code`: it is in no request body, so sending it is `422`
    `UNKNOWN_FIELD` like any unknown field (contract: "Transactions (Ledger)",
    "Bank lines") (contract: "Unknown request fields"), keyed by its dotted path
    inside a list. Nothing is written, and the code the line has stays."""
    zone = _zone(client)
    account = _make_account(client)
    date = _noon(zone, 2026, 4, 7)
    original = client.post("/transactions", json_body=_tx_body(account, date, -100))
    writes = _line_code_writes(account, date, original["id"])
    written = [original["id"]]
    for _method, _path, body, _key in writes:
        for item in [body, *body.get("transactions", []), *body.get("rows", [])]:
            for key in ("id", "transaction_id"):
                if key in item:
                    written.append(item[key])
        written.extend(part["id"] for part in body.get("parts", []))
    try:
        for method, path, body, key in writes:
            send = client.post if method == "POST" else client.put
            err = _refused(lambda send=send, path=path, body=body: send(path, json_body=body))
            assert (err.status, err.code) == (422, "VALIDATION_ERROR"), (method, path)
            assert reason_on(err, key) == "UNKNOWN_FIELD", (method, path, err.reasons)
        assert _live_ids(client, account) == {original["id"]}
        assert client.get(f"/transactions/{original['id']}")["line_code"] == original["line_code"]
    finally:
        _cleanup(client, written, account)


# ---- statement_line round trip -----------------------------------------------


def test_statement_line_round_trips_on_create_batch_and_put(client):
    """`statement_line` is trimmed and stored on the transaction's line
    (contract: POST /v1/transactions, "Fields"); a batch group's is written onto
    every part (contract: POST /v1/transactions/batch, "Line groups"); a `PUT` on
    one part writes it onto every live part of the line, and `null` clears it
    (contract: PUT /v1/transactions/{transaction_id}, "Line fields")."""
    zone = _zone(client)
    account = _make_account(client)
    date = _noon(zone, 2026, 4, 8)
    single_line, group_line, replaced = _statement_line(), _statement_line(), _statement_line()
    single = _tx_body(account, date, -1500, statement_line=f"  {single_line}  ")
    group = [
        _tx_body(account, date, a, line_group="g1", statement_line=group_line)
        for a in (-6000, -4000)
    ]
    written = [single["id"], *(item["id"] for item in group)]
    try:
        made = client.post("/transactions", json_body=single)
        assert made["statement_line"] == single_line
        assert client.get(f"/transactions/{single['id']}")["statement_line"] == single_line
        assert client.get(f"/bank-lines/{made['bank_line_id']}")["statement_line"] == single_line

        one, two = client.post("/transactions/batch", json_body={"transactions": group})["created"]
        assert [one["statement_line"], two["statement_line"]] == [group_line, group_line]
        line = one["bank_line_id"]
        assert client.get(f"/bank-lines/{line}")["statement_line"] == group_line

        edited = client.put(f"/transactions/{one['id']}", json_body={"statement_line": replaced})
        assert edited["statement_line"] == replaced
        assert client.get(f"/transactions/{two['id']}")["statement_line"] == replaced
        assert client.get(f"/bank-lines/{line}")["statement_line"] == replaced

        cleared = client.put(f"/transactions/{two['id']}", json_body={"statement_line": None})
        assert cleared["statement_line"] is None
        assert client.get(f"/transactions/{one['id']}")["statement_line"] is None
        assert client.get(f"/bank-lines/{line}")["statement_line"] is None
    finally:
        _cleanup(client, written, account)


# ---- one statement line is one bank line --------------------------------------


def test_a_statement_line_names_one_live_line(client):
    """A second live line of the caller's with the same statement line, on any
    account, is `409` `STATEMENT_LINE_EXISTS` on `statement_line`, nothing written,
    and a deleted line frees it (contract: POST /v1/transactions, "Fields"). In a
    batch the item already in the ledger is keyed `transactions.<i>.statement_line`,
    and two lines with one statement line are `422` `DUPLICATE_IN_REQUEST`
    (contract: POST /v1/transactions/batch). A `PUT` follows the create's `409`
    (contract: PUT /v1/transactions/{transaction_id})."""
    zone = _zone(client)
    account, other_account = _make_account(client), _make_account(client)
    date = _noon(zone, 2026, 4, 9)
    taken, fresh = _statement_line(), _statement_line()
    first = _tx_body(account, date, -1000, statement_line=taken)
    second = _tx_body(other_account, date, -1000, statement_line=taken)
    in_batch = _tx_body(other_account, date, -1000, statement_line=taken)
    twins = [_tx_body(account, date, a, statement_line=fresh) for a in (-100, -200)]
    plain = _tx_body(other_account, date, -300)
    later = _tx_body(other_account, date, -1000, statement_line=taken)
    written = [b["id"] for b in (first, second, in_batch, *twins, plain, later)]
    try:
        client.post("/transactions", json_body=first)

        err = _refused(lambda: client.post("/transactions", json_body=second))
        assert (err.status, err.code) == (409, "CONFLICT")
        assert reason_on(err, "statement_line") == "STATEMENT_LINE_EXISTS"

        err = _refused(
            lambda: client.post("/transactions/batch", json_body={"transactions": [in_batch]})
        )
        assert (err.status, err.code) == (409, "CONFLICT")
        assert reason_on(err, "transactions.0.statement_line") == "STATEMENT_LINE_EXISTS"

        err = _refused(
            lambda: client.post("/transactions/batch", json_body={"transactions": twins})
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "transactions.1.statement_line") == "DUPLICATE_IN_REQUEST"

        client.post("/transactions", json_body=plain)
        err = _refused(
            lambda: client.put(f"/transactions/{plain['id']}", json_body={"statement_line": taken})
        )
        assert (err.status, err.code) == (409, "CONFLICT")
        assert reason_on(err, "statement_line") == "STATEMENT_LINE_EXISTS"
        assert client.get(f"/transactions/{plain['id']}")["statement_line"] is None

        assert _live_ids(client, account) == {first["id"]}
        assert _live_ids(client, other_account) == {plain["id"]}

        client.delete(f"/transactions/{first['id']}")
        assert client.post("/transactions", json_body=later)["statement_line"] == taken
    finally:
        _cleanup(client, written, account)
        _safe(client.delete, f"/accounts/{other_account}")


@pytest.mark.parametrize("second_sends", ["another", "none"], ids=["differs", "missing"])
def test_a_line_group_differing_on_statement_line_is_refused(client, second_sends):
    """The items of one `line_group` share the line's statement line, compared after
    trimming, and one sent on one item and missing on another differs: every item
    of the group is `422` `LINE_GROUP_FIELDS_DIFFER` on `statement_line`, nothing
    written (contract: POST /v1/transactions/batch, "Line groups")."""
    zone = _zone(client)
    account = _make_account(client)
    date = _noon(zone, 2026, 4, 10)
    first = _tx_body(account, date, -100, line_group="g1", statement_line=_statement_line())
    second = _tx_body(account, date, -200, line_group="g1")
    if second_sends == "another":
        second["statement_line"] = _statement_line()
    try:
        err = _refused(
            lambda: client.post("/transactions/batch", json_body={"transactions": [first, second]})
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        for key in ("transactions.0.statement_line", "transactions.1.statement_line"):
            assert reason_on(err, key) == "LINE_GROUP_FIELDS_DIFFER"
        assert _live_ids(client, account) == set()
    finally:
        _cleanup(client, [first["id"], second["id"]], account)


# ---- the writes that take no statement line -----------------------------------


def test_the_opening_balance_the_split_and_the_upload_take_no_statement_line(client):
    """`statement_line` is forbidden on the opening balance
    (contract: POST /v1/accounts/{account_id}/opening-balance), on a split's part and
    beside its `parts` (contract: POST /v1/transactions/{transaction_id}/split), and
    on a bank upload's row (contract: POST /v1/transactions/import): each `422`
    `UNKNOWN_FIELD`, and nothing is written."""
    zone = _zone(client)
    account = _make_account(client)
    date = _noon(zone, 2026, 4, 11)
    value = _statement_line()
    original = client.post("/transactions", json_body=_tx_body(account, date, -100))
    opening_id, import_id = str(uuid4()), str(uuid4())
    part_ids = [str(uuid4()) for _ in range(4)]
    refusals = [
        (
            f"/accounts/{account}/opening-balance",
            {
                "transaction_id": opening_id,
                "amount_cents": 500,
                "date": date,
                "statement_line": value,
            },
            "statement_line",
        ),
        (
            f"/transactions/{original['id']}/split",
            {
                "parts": [
                    {"id": part_ids[0], "amount_cents": -60, "statement_line": value},
                    {"id": part_ids[1], "amount_cents": -40},
                ]
            },
            "parts.0.statement_line",
        ),
        (
            f"/transactions/{original['id']}/split",
            {
                "parts": [
                    {"id": part_ids[2], "amount_cents": -60},
                    {"id": part_ids[3], "amount_cents": -40},
                ],
                "statement_line": value,
            },
            "statement_line",
        ),
        (
            "/transactions/import",
            {
                "dry_run": False,
                "rows": [
                    {
                        "id": import_id,
                        "account_id": account,
                        "date": date[:10],
                        "amount_cents": -2500,
                        "statement_line": value,
                    }
                ],
            },
            "rows.0.statement_line",
        ),
    ]
    try:
        for path, body, key in refusals:
            err = _refused(lambda path=path, body=body: client.post(path, json_body=body))
            assert (err.status, err.code) == (422, "VALIDATION_ERROR"), path
            assert reason_on(err, key) == "UNKNOWN_FIELD", (path, err.reasons)
        assert _live_ids(client, account) == {original["id"]}
        assert client.get(f"/accounts/{account}")["opening_balance_transaction_id"] is None
        assert client.get(f"/transactions/{original['id']}")["statement_line"] is None
    finally:
        _cleanup(client, [original["id"], opening_id, import_id, *part_ids], account)


# ---- the field lock -----------------------------------------------------------


def test_a_set_statement_line_is_locked_and_an_empty_one_fills(client):
    """While its reconciliation is completed, `statement_line` is read-only: a set
    one is `422` `LOCKED` whether changed, cleared or resent as it is, and an empty
    one may be filled, after which it is locked too
    (contract: PUT /v1/transactions/{transaction_id}, "Field locking")."""
    zone = _zone(client)
    account = _make_account(client)
    recon = str(uuid4())
    held, filled = _statement_line(), _statement_line()
    coded = _tx_body(account, _noon(zone, 2026, 4, 12), -1000, statement_line=held)
    empty = _tx_body(account, _noon(zone, 2026, 4, 13), -2000)
    try:
        client.post(
            "/reconciliations",
            json_body={
                "id": recon,
                "account_id": account,
                "name": f"contract-sl-{recon[:8]}",
                "date_start": "2026-04-01",
                "date_end": "2026-04-30",
                "beginning_balance_cents": 0,
                "ending_balance_cents": -3000,
            },
        )
        for body in (coded, empty):
            client.post("/transactions", json_body=body)
            client.put(f"/transactions/{body['id']}", json_body={"reconciliation_id": recon})
        client.post(f"/reconciliations/{recon}/complete")

        for sent in (_statement_line(), None, held):
            err = _refused(
                lambda sent=sent: client.put(
                    f"/transactions/{coded['id']}", json_body={"statement_line": sent}
                )
            )
            assert (err.status, err.code) == (422, "VALIDATION_ERROR")
            assert reason_on(err, "statement_line") == "LOCKED"
        assert client.get(f"/transactions/{coded['id']}")["statement_line"] == held

        done = client.put(f"/transactions/{empty['id']}", json_body={"statement_line": filled})
        assert done["statement_line"] == filled
        err = _refused(
            lambda: client.put(
                f"/transactions/{empty['id']}", json_body={"statement_line": _statement_line()}
            )
        )
        assert reason_on(err, "statement_line") == "LOCKED"
        assert client.get(f"/transactions/{empty['id']}")["statement_line"] == filled
    finally:
        _safe(client.post, f"/reconciliations/{recon}/revert")
        _safe(client.delete, f"/transactions/{coded['id']}")
        _safe(client.delete, f"/transactions/{empty['id']}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/accounts/{account}")
