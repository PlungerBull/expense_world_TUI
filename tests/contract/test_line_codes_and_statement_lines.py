"""Contract: every bank line's `line_code`, and the `statement_line` and `statement_place`
no client writes.

Every bank line carries the engine's short code, `#` and six digits, given at its
create and never sent by a client; and a statement line, the line's code in its bank
statement, which the engine builds from the account's statement code, its
reconciliation's month and the line's place, and which no request carries (contract:
"Transactions (Ledger)", "Bank lines"). The sheet import groups split rows into one
line and sends no statement line, so it stands on rules only the engine can confirm.
Pinned here:

  · a batch whose `line_group` holds two items makes one line whose parts read one
    `line_code`, and the next line of the batch takes the next code; a whole-line
    write replacing that line's parts keeps its code on every new part;
  · `line_code` is in no request body: on `POST /transactions`, each item of
    `POST /transactions/batch`, `POST /transactions/import` beside a made-up
    download's file, the opening balance, each part of a whole-line write and beside
    its `parts`, and `PUT /transactions/{id}`, it is `422` `UNKNOWN_FIELD` under its
    own key, and nothing is written;
  · `statement_line` is in no request body either: on the same writes, beside a
    whole-line write's `parts` and alone in its body too, and on `PUT
    /transactions/{id}` whether set or `null`, it is `422` `UNKNOWN_FIELD` under its
    own key, nothing is written, and a line in no reconciliation reads a `null`
    statement line;
  · `statement_place`, set only by a statement's order, is in no other request body:
    on the same writes, beside a whole-line write's `parts` and alone in its body too,
    and on `PUT /transactions/{id}` whether set or `null`, and on a reconciliation's
    create and update, it is `422` `UNKNOWN_FIELD` under its own key, and nothing is
    written;
  · the bank import never writes either: a made-up download's apply matching a line
    of a completed statement by its operation code retitles it and leaves its
    statement line, its place and its `line_code` as they were, and the row it creates
    is a new line with a code of its own and neither;
  · letter case counts: `ABC…` and `abc…` are two operation codes on one account,
    each read back as sent; only the exact same value again is `409`, nothing
    written.

Each test builds its own account and undoes what it wrote. Gating, target and the
real-ledger guard: conftest.py.
"""

# ruff: noqa: E402
import pytest

pytest.skip(
    "on the holder model until "
    "docs/specs/catch-up-currencies-4-live-suite-upload-lines-kinds.md "
    "(its tasks) rewrites it",
    allow_module_level=True,
)

import re
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense.errors import EngineError
from tests.contract.conftest import (
    CARD_HEADER,
    CURRENT_HEADER,
    download_body,
    free_statement_codes,
    live_ids,
    reason_on,
    replace_parts,
    send_download,
    send_order,
)

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


def _tx_body(account_id: str, date: str, amount: int, **extra) -> dict:
    return {
        "id": str(uuid4()),
        "title": "contract line fields",
        "amount_cents": amount,
        "account_id": account_id,
        "date": date,
        **extra,
    }


def _cleanup(client, tx_ids: list[str], account_id: str) -> None:
    for tx_id in tx_ids:
        _safe(client.delete, f"/transactions/{tx_id}")
    _safe(client.delete, f"/accounts/{account_id}")


# ---- line_code ---------------------------------------------------------------


def test_a_line_group_reads_one_line_code_and_new_parts_keep_it(client):
    """The items of one `line_group` are the parts of one line and read one
    `line_code`; each line of the batch takes the next code in request order
    (contract: POST /v1/transactions/batch, "Line groups"). A whole-line write sending
    only new parts makes no new line: every new part reads the line's code
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts")."""
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

        parts = replace_parts(client, line, [-5000, -3000, -2000], written)
        assert [p["line_code"] for p in parts] == [code, code, code]
        assert {p["bank_line_id"] for p in parts} == {line}
        assert client.get(f"/bank-lines/{line}")["line_code"] == code
        for part in parts:
            assert client.get(f"/transactions/{part['id']}")["line_code"] == code
    finally:
        _cleanup(client, written, account)


def _download_row(date: str) -> list[list]:
    """A made-up card download holding one new row on `date`'s day."""
    return [CARD_HEADER, [date[:10], "contract line fields", "S/", -1]]


def _writes_sending(
    key: str, value: object, account: str, date: str, tx: dict
) -> list[tuple[str, str, dict, str]]:
    """Every write that takes a body naming a transaction or its line, each sending
    `key` where a client field would go: (method, path, body, refused key). The import
    has no row of the client's to carry it, so it goes beside the download's file."""
    return [
        ("POST", "/transactions", _tx_body(account, date, -100, **{key: value}), key),
        (
            "POST",
            "/transactions/batch",
            {"transactions": [_tx_body(account, date, -100, **{key: value})]},
            f"transactions.0.{key}",
        ),
        (
            "POST",
            "/transactions/import",
            {**download_body(account, _download_row(date), dry_run=False), key: value},
            key,
        ),
        (
            "POST",
            f"/accounts/{account}/opening-balance",
            {"transaction_id": str(uuid4()), "amount_cents": 100, "date": date, key: value},
            key,
        ),
        (
            "PUT",
            f"/bank-lines/{tx['bank_line_id']}",
            {
                "parts": [
                    {"id": str(uuid4()), "amount_cents": -60, key: value},
                    {"id": str(uuid4()), "amount_cents": -40},
                ]
            },
            f"parts.0.{key}",
        ),
        ("PUT", f"/transactions/{tx['id']}", {key: value}, key),
    ]


def _line_writes_sending(key: str, value: object, tx: dict) -> list[tuple[str, str, dict, str]]:
    """The whole-line write sending `key` where a line field would go: beside new
    `parts`, and alone in its body."""
    path = f"/bank-lines/{tx['bank_line_id']}"
    parts = [{"id": str(uuid4()), "amount_cents": -60}, {"id": str(uuid4()), "amount_cents": -40}]
    return [("PUT", path, {"parts": parts, key: value}, key), ("PUT", path, {key: value}, key)]


def _ids_in(writes: list[tuple[str, str, dict, str]]) -> list[str]:
    """Every client id the writes carry, so cleanup reaches whatever one wrote."""
    ids: list[str] = []
    for _method, _path, body, _key in writes:
        for item in [body, *body.get("transactions", [])]:
            ids.extend(item[key] for key in ("id", "transaction_id") if key in item)
        ids.extend(part["id"] for part in body.get("parts", []))
    return ids


def test_line_code_is_in_no_request_body(client):
    """No client sends `line_code`: it is in no request body, so sending it is `422`
    `UNKNOWN_FIELD` like any unknown field (contract: "Transactions (Ledger)",
    "Bank lines") (contract: "Unknown request fields"), keyed by its dotted path
    inside a list, and beside a bank download's file under its own key
    (contract: POST /v1/transactions/import, "Body"). Nothing is written, and the code
    the line has stays."""
    zone = _zone(client)
    account = _make_account(client)
    date = _noon(zone, 2026, 4, 7)
    original = client.post("/transactions", json_body=_tx_body(account, date, -100))
    writes = _writes_sending("line_code", "#000001", account, date, original)
    writes += _line_writes_sending("line_code", "#000001", original)
    written = [original["id"], *_ids_in(writes)]
    try:
        for method, path, body, key in writes:
            send = client.post if method == "POST" else client.put
            err = _refused(lambda send=send, path=path, body=body: send(path, json_body=body))
            assert (err.status, err.code) == (422, "VALIDATION_ERROR"), (method, path)
            assert reason_on(err, key) == "UNKNOWN_FIELD", (method, path, err.reasons)
        assert live_ids(client, account) == {original["id"]}
        assert client.get(f"/transactions/{original['id']}")["line_code"] == original["line_code"]
    finally:
        _cleanup(client, written, account)


# ---- statement_line ----------------------------------------------------------


def test_statement_line_is_in_no_request_body(client):
    """No client sends `statement_line`: the engine builds it and it is read-only
    (contract: "Transactions (Ledger)", "Bank lines"), so every write refuses it as
    an unknown field (contract: "Unknown request fields"), `422` `UNKNOWN_FIELD`
    under its own key: a create (contract: POST /v1/transactions, "Forbidden"), a
    batch item (contract: POST /v1/transactions/batch), a bank download's body beside
    its file (contract: POST /v1/transactions/import, "Body"), the opening balance
    (contract: POST /v1/accounts/{account_id}/opening-balance, "Forbidden"), a
    whole-line write's part (contract: PUT /v1/bank-lines/{bank_line_id}, "Forbidden"),
    beside its `parts` and alone in its body
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Body"), and an update, set or
    `null` (contract: PUT /v1/transactions/{transaction_id}, "Updatable").
    Nothing is written, and the line, in no reconciliation, reads a `null`
    `statement_line` and `statement_place`
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")."""
    zone = _zone(client)
    account = _make_account(client)
    date = _noon(zone, 2026, 4, 11)
    value = "SIG-202604-001"
    original = client.post("/transactions", json_body=_tx_body(account, date, -100))
    writes = _writes_sending("statement_line", value, account, date, original)
    writes += [
        *_line_writes_sending("statement_line", value, original),
        ("PUT", f"/transactions/{original['id']}", {"statement_line": None}, "statement_line"),
    ]
    written = [original["id"], *_ids_in(writes)]
    try:
        for method, path, body, key in writes:
            send = client.post if method == "POST" else client.put
            err = _refused(lambda send=send, path=path, body=body: send(path, json_body=body))
            assert (err.status, err.code) == (422, "VALIDATION_ERROR"), (method, path)
            assert reason_on(err, key) == "UNKNOWN_FIELD", (method, path, err.reasons)
        assert live_ids(client, account) == {original["id"]}
        assert client.get(f"/accounts/{account}")["opening_balance_transaction_id"] is None
        read = client.get(f"/transactions/{original['id']}")
        assert read["version"] == original["version"]
        assert (read["statement_line"], read["statement_place"]) == (None, None)
        line = client.get(f"/bank-lines/{original['bank_line_id']}")
        assert (line["statement_line"], line["statement_place"]) == (None, None)
    finally:
        _cleanup(client, written, account)


# ---- statement_place ---------------------------------------------------------


def test_statement_place_is_in_no_request_body_but_the_order(client):
    """A line's place is set only by the statement order's list; it is in no other
    request body (contract: "Transactions (Ledger)", "Bank lines"), so every write
    naming a transaction refuses it as an unknown field
    (contract: "Unknown request fields"), `422` `UNKNOWN_FIELD` under its own key: a
    create, a batch item, a bank download's body beside its file, the opening balance, a
    whole-line write's part,
    beside its `parts` and alone in its body
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Body"), and an update, set or
    `null`; and so do a reconciliation's create and update. The order's own body takes no
    `statement_place` either (test_statement_order.py). Nothing is written, and the
    line reads no place."""
    zone = _zone(client)
    account = _make_account(client)
    date = _noon(zone, 2026, 4, 12)
    original = client.post("/transactions", json_body=_tx_body(account, date, -100))
    writes = _writes_sending("statement_place", 1, account, date, original)
    writes += [
        *_line_writes_sending("statement_place", 1, original),
        ("PUT", f"/transactions/{original['id']}", {"statement_place": None}, "statement_place"),
    ]
    recon = str(uuid4())
    period = {"date_start": "2026-04-01", "date_end": "2026-04-30"}
    made = client.post(
        "/reconciliations",
        json_body={
            "id": recon,
            "account_id": account,
            "name": f"contract-sl-{recon[:8]}",
            "beginning_balance_cents": 0,
            **period,
        },
    )
    unwritten = str(uuid4())
    writes += [
        (
            "POST",
            "/reconciliations",
            {
                "id": unwritten,
                "account_id": account,
                "name": f"contract-sl-{unwritten[:8]}",
                "beginning_balance_cents": 0,
                "statement_place": 1,
                **period,
            },
            "statement_place",
        ),
        ("PUT", f"/reconciliations/{recon}", {"statement_place": 1}, "statement_place"),
    ]
    written = [original["id"], *_ids_in(writes)]
    try:
        for method, path, body, key in writes:
            send = client.post if method == "POST" else client.put
            err = _refused(lambda send=send, path=path, body=body: send(path, json_body=body))
            assert (err.status, err.code) == (422, "VALIDATION_ERROR"), (method, path)
            assert reason_on(err, key) == "UNKNOWN_FIELD", (method, path, err.reasons)
        assert live_ids(client, account) == {original["id"]}
        assert client.get(f"/accounts/{account}")["opening_balance_transaction_id"] is None
        assert client.get(f"/transactions/{original['id']}")["version"] == original["version"]
        line = client.get(f"/bank-lines/{original['bank_line_id']}")
        assert line["statement_place"] is None
        recons = client.get("/reconciliations", params={"account_id": account})["items"]
        assert [(r["id"], r["version"]) for r in recons] == [(recon, made["version"])]
    finally:
        _safe(client.delete, f"/reconciliations/{unwritten}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _cleanup(client, written, account)


# ---- the bank import ------------------------------------------------------------


def test_the_import_keeps_a_lines_statement_line_and_gives_a_new_line_none(client, scratch):
    """The import never reads, matches on or writes a line's `statement_line` or
    `statement_place`: a created row's line has neither, and a matched line keeps its
    own; each created row is a new bank line with the next `line_code`, and a matched
    line keeps its own (contract: POST /v1/transactions/import). A line of a completed
    statement, matched by its operation code, still takes the bank's title
    (contract: POST /v1/transactions/import, "The bank's title wins"), so the apply
    writes the line and leaves its statement line, place and code as they were."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account("PEN", code)
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    operation = f"OP{uuid4().hex[:10]}"
    held = str(uuid4())
    scratch.transactions.append(held)
    made = client.post(
        "/transactions",
        json_body={
            **_tx_body(account, scratch.noon("2026-03-05"), -2590, operation_code=operation),
            "id": held,
            "reconciliation_id": recon,
        },
    )
    line = made["bank_line_id"]
    send_order(client, recon, [line])
    assert client.post(f"/reconciliations/{recon}/complete")["status"] == 2
    before = client.get(f"/bank-lines/{line}")
    assert (before["statement_line"], before["statement_place"]) == (f"{code}-202603-001", 1)

    download = [
        CURRENT_HEADER,
        ["05/03/2026", "TIENDA DEL BANCO", "S/", -25.9, operation],
        ["02/04/2026", "OTRA TIENDA", "S/", -10, f"OP{uuid4().hex[:10]}"],
    ]
    answer = send_download(client, account, download, dry_run=False)
    scratch.transactions.extend(r["transaction_id"] for r in answer["rows"] if r["transaction_id"])
    matched, new = answer["rows"]
    assert (matched["outcome"], matched["rule"]) == ("matched", "operation_code")
    assert (matched["bank_line_id"], matched["retitled"]) == (line, True)
    assert new["outcome"] == "new"

    after = client.get(f"/bank-lines/{line}")
    assert [p["title"] for p in after["parts"]] == ["TIENDA DEL BANCO"]
    kept = ("statement_line", "statement_place", "line_code")
    assert {k: after[k] for k in kept} == {k: before[k] for k in kept}
    part = client.get(f"/transactions/{held}")
    assert {k: part[k] for k in kept} == {k: before[k] for k in kept}

    created = client.get(f"/transactions/{new['transaction_id']}")
    fresh = client.get(f"/bank-lines/{created['bank_line_id']}")
    assert fresh["id"] != line
    assert (fresh["statement_line"], fresh["statement_place"]) == (None, None)
    assert LINE_CODE.match(fresh["line_code"]) and fresh["line_code"] != before["line_code"]


# ---- letter case counts -------------------------------------------------------


def _upper_fragment() -> str:
    """Upper-case hex no earlier run of this suite has written; the caller's prefix
    holds letters, so the value's lower-case form always differs from it."""
    return uuid4().hex[:12].upper()


def test_an_operation_code_in_another_letter_case_is_another_code(client, statuses):
    """Two operation codes are compared letter for letter, so `ABC…` and `abc…` on
    one account are two operation codes: each creates its own bank line and reads
    back as sent, and only the exact same operation code again on that account is
    `409` `OPERATION_CODE_EXISTS`, nothing written
    (contract: POST /v1/transactions, "Case counts")."""
    zone = _zone(client)
    account = _make_account(client)
    date = _noon(zone, 2026, 4, 15)
    upper = f"ABC{_upper_fragment()}"
    first = _tx_body(account, date, -1000, operation_code=upper)
    second = _tx_body(account, date, -2000, operation_code=upper.lower())
    again = [_tx_body(account, date, -3000, operation_code=v) for v in (upper, upper.lower())]
    written = [b["id"] for b in (first, second, *again)]
    try:
        lines = []
        for body in (first, second):
            made = client.post("/transactions", json_body=body)
            assert statuses[-1] == 201
            assert made["account_id"] == account
            lines.append(made["bank_line_id"])
        assert lines[0] != lines[1]
        for body, line in zip((first, second), lines, strict=True):
            sent = body["operation_code"]
            assert client.get(f"/transactions/{body['id']}")["operation_code"] == sent
            read = client.get(f"/bank-lines/{line}")
            assert (read["operation_code"], read["account_id"]) == (sent, account)

        for body in again:
            err = _refused(lambda body=body: client.post("/transactions", json_body=body))
            assert (err.status, err.code) == (409, "CONFLICT")
            assert reason_on(err, "operation_code") == "OPERATION_CODE_EXISTS"
        assert live_ids(client, account) == {first["id"], second["id"]}
    finally:
        _cleanup(client, written, account)
