"""Contract: every bank line's `line_code`, and the `statement_line` and `statement_place`
no client writes.

Every bank line carries the engine's short code, `#` and six digits, given at its
create and never sent by a client; and a statement line, the line's code in its bank
statement, which the engine builds from the account's statement code, its completed
statement's month and the line's place, and which no request carries (contract:
"Transactions (Ledger)", "Bank lines"). The place is set by the upload of the bank's PDF
statement alone, so no request body carries it either. The sheet import groups split rows
into one line and sends no statement line, so it stands on rules only the engine can
confirm. Pinned here:

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
    own key, nothing is written, and a line in no statement reads a `null`
    statement line;
  · `statement_place` is in no request body: on the same writes, beside a whole-line
    write's `parts` and alone in its body too, on `PUT /transactions/{id}` whether set
    or `null`, and on a statement's create and update, it is `422` `UNKNOWN_FIELD` under
    its own key, and nothing is written;
  · the bank download never writes either: a made-up download's apply matching a line
    of a statement the paper closed by its operation code retitles it and leaves its
    statement line, its place and its `line_code` as they were, and the row it creates
    is a new line with a code of its own and neither;
  · letter case counts: `ABC…` and `abc…` are two operation codes on one account,
    each read back as sent; only the exact same value again is `409`, nothing
    written.

Each test builds its own account and undoes what it wrote. Gating, target and the
real-ledger guard: conftest.py.
"""

import re
from datetime import date
from uuid import uuid4

from tests.contract.conftest import (
    CARD_HEADER,
    CURRENT_HEADER,
    PaperRow,
    all_accounts,
    assert_refusal,
    download_body,
    free_statement_codes,
    live_ids,
    refused,
    replace_parts,
    savings_paper,
    send_download,
    send_statement,
    statement_create_body,
)

LINE_CODE = re.compile(r"^#\d{6}$")


# ---- line_code ---------------------------------------------------------------


def test_a_line_group_reads_one_line_code_and_new_parts_keep_it(client, scratch):
    """The items of one `line_group` are the parts of one line and read one
    `line_code`; each line of the batch takes the next code in request order
    (contract: POST /v1/transactions/batch, "Line groups"). A whole-line write sending
    only new parts makes no new line: every new part reads the line's code
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts")."""
    account = scratch.account()
    when = scratch.noon("2026-04-06")
    group = [scratch._item(account, when, a, "PEN", line_group="g1") for a in (-6000, -4000)]
    single = scratch._item(account, when, -2500, "PEN")
    first, second, third = scratch._create([*group, single])
    assert first["bank_line_id"] == second["bank_line_id"] != third["bank_line_id"]
    code = first["line_code"]
    assert LINE_CODE.match(code)
    assert second["line_code"] == code
    assert third["line_code"] == f"#{int(code[1:]) + 1:06d}"
    line = first["bank_line_id"]
    read = client.get(f"/bank-lines/{line}")
    assert read["line_code"] == code
    assert {p["line_code"] for p in read["parts"]} == {code}

    parts = replace_parts(client, line, [-5000, -3000, -2000], scratch.transactions)
    assert [p["line_code"] for p in parts] == [code, code, code]
    assert {p["bank_line_id"] for p in parts} == {line}
    assert client.get(f"/bank-lines/{line}")["line_code"] == code
    for part in parts:
        assert client.get(f"/transactions/{part['id']}")["line_code"] == code


def _download_row(day: str) -> list[list]:
    """A made-up card download holding one new row on `day`'s day."""
    return [CARD_HEADER, [day, "contract line fields", "S/", -1]]


def _writes_sending(
    scratch, key: str, value: object, account: str, day: str, tx: dict
) -> list[tuple[str, str, dict, str]]:
    """Every write that takes a body naming a transaction or its line, each sending
    `key` where a client field would go: (method, path, body, refused key). The download
    has no row of the client's to carry it, so it goes beside the download's file."""
    opening = {
        "transaction_id": str(uuid4()),
        "currency_code": "PEN",
        "amount_cents": 100,
        "date": scratch.noon(day),
    }

    def item() -> dict:
        return scratch._item(account, scratch.noon(day), -100, "PEN", **{key: value})

    new_parts = [
        {"id": str(uuid4()), "amount_cents": -60, key: value},
        {"id": str(uuid4()), "amount_cents": -40},
    ]
    return [
        (
            "POST",
            "/transactions",
            item(),
            key,
        ),
        (
            "POST",
            "/transactions/batch",
            {"transactions": [item()]},
            f"transactions.0.{key}",
        ),
        (
            "POST",
            "/transactions/import",
            {**download_body(account, _download_row(day), dry_run=False), key: value},
            key,
        ),
        ("POST", f"/accounts/{account}/opening-balance", {**opening, key: value}, key),
        ("PUT", f"/bank-lines/{tx['bank_line_id']}", {"parts": new_parts}, f"parts.0.{key}"),
        ("PUT", f"/transactions/{tx['id']}", {key: value}, key),
    ]


def _line_writes_sending(key: str, value: object, tx: dict) -> list[tuple[str, str, dict, str]]:
    """The whole-line write sending `key` where a line field would go: beside new
    `parts`, and alone in its body."""
    path = f"/bank-lines/{tx['bank_line_id']}"
    parts = [{"id": str(uuid4()), "amount_cents": -60}, {"id": str(uuid4()), "amount_cents": -40}]
    return [("PUT", path, {"parts": parts, key: value}, key), ("PUT", path, {key: value}, key)]


def _take_on_ids(scratch, writes: list[tuple[str, str, dict, str]]) -> None:
    """Every client id the writes carry joins `scratch`, so cleanup reaches whatever one
    wrote."""
    for _method, _path, body, _key in writes:
        for item in [body, *body.get("transactions", [])]:
            scratch.transactions.extend(item[k] for k in ("id", "transaction_id") if k in item)
        scratch.transactions.extend(part["id"] for part in body.get("parts", []))


def _all_refused(client, writes: list[tuple[str, str, dict, str]]) -> None:
    """Each write is `422` `UNKNOWN_FIELD` under its refused key alone."""
    for method, path, body, key in writes:
        send = client.post if method == "POST" else client.put
        err = refused(lambda send=send, path=path, body=body: send(path, json_body=body))
        assert_refusal(err, 422, "VALIDATION_ERROR", key, "UNKNOWN_FIELD")


def test_line_code_is_in_no_request_body(client, scratch):
    """No client sends `line_code`: it is in no request body, so sending it is `422`
    `UNKNOWN_FIELD` like any unknown field (contract: "Transactions (Ledger)",
    "Bank lines") (contract: "Unknown request fields"), keyed by its dotted path
    inside a list, and beside a bank download's file under its own key
    (contract: POST /v1/transactions/import, "Body"). Nothing is written, and the code
    the line has stays."""
    account = scratch.account()
    original = scratch.row(account, "2026-04-07", -100, alone=True)
    writes = _writes_sending(scratch, "line_code", "#000001", account, "2026-04-07", original)
    writes += _line_writes_sending("line_code", "#000001", original)
    _take_on_ids(scratch, writes)
    before = all_accounts(client)

    _all_refused(client, writes)
    assert live_ids(client, account) == {original["id"]}
    assert all_accounts(client) == before
    assert client.get(f"/transactions/{original['id']}")["line_code"] == original["line_code"]


# ---- statement_line ----------------------------------------------------------


def test_statement_line_is_in_no_request_body(client, scratch):
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
    Nothing is written, and the line, in no statement, reads a `null`
    `statement_line` and `statement_place`
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")."""
    account = scratch.account()
    original = scratch.row(account, "2026-04-11", -100, alone=True)
    value = "SIG-202604-001"
    writes = _writes_sending(scratch, "statement_line", value, account, "2026-04-11", original)
    writes += [
        *_line_writes_sending("statement_line", value, original),
        ("PUT", f"/transactions/{original['id']}", {"statement_line": None}, "statement_line"),
    ]
    _take_on_ids(scratch, writes)
    before = all_accounts(client)

    _all_refused(client, writes)
    assert live_ids(client, account) == {original["id"]}
    assert all_accounts(client) == before
    read = client.get(f"/transactions/{original['id']}")
    assert read["version"] == original["version"]
    assert (read["statement_line"], read["statement_place"]) == (None, None)
    line = client.get(f"/bank-lines/{original['bank_line_id']}")
    assert (line["statement_line"], line["statement_place"]) == (None, None)


# ---- statement_place ---------------------------------------------------------


def test_statement_place_is_in_no_request_body(client, scratch):
    """A line's place is set by the upload of the bank's PDF statement alone, and it is in
    no request body (contract: "Statements", "A statement's order"), so every write naming a
    transaction refuses it as an unknown field (contract: "Unknown request fields"), `422`
    `UNKNOWN_FIELD` under its own key: a create, a batch item, a bank download's body beside
    its file, the opening balance, a whole-line write's part, beside its `parts` and alone
    in its body (contract: PUT /v1/bank-lines/{bank_line_id}, "Body"), and an update, set or
    `null`; and so do a statement's create and update (contract: POST /v1/statements,
    "Required"). Nothing is written, and the line reads no place."""
    account = scratch.account()
    original = scratch.row(account, "2026-04-12", -100, alone=True)
    writes = _writes_sending(scratch, "statement_place", 1, account, "2026-04-12", original)
    writes += [
        *_line_writes_sending("statement_place", 1, original),
        ("PUT", f"/transactions/{original['id']}", {"statement_place": None}, "statement_place"),
    ]
    made = scratch.statement(account, "2026-04-01", "2026-04-30")
    unwritten = statement_create_body(account, "2026-05-01", "2026-05-31", statement_place=1)
    scratch.statements.append(unwritten["id"])
    writes += [
        ("POST", "/statements", unwritten, "statement_place"),
        ("PUT", f"/statements/{made['id']}", {"statement_place": 1}, "statement_place"),
    ]
    _take_on_ids(scratch, writes)
    before = all_accounts(client)

    _all_refused(client, writes)
    assert live_ids(client, account) == {original["id"]}
    assert all_accounts(client) == before
    assert client.get(f"/transactions/{original['id']}")["version"] == original["version"]
    assert client.get(f"/bank-lines/{original['bank_line_id']}")["statement_place"] is None
    listed = client.get("/statements", params={"account_id": account})["items"]
    assert [(s["id"], s["version"]) for s in listed] == [(made["id"], made["version"])]


# ---- the bank download ----------------------------------------------------------


def test_the_download_keeps_a_lines_statement_line_and_gives_a_new_line_none(client, scratch):
    """The bank download never reads, matches on or writes a line's `statement_line` or
    `statement_place`: a created row's line has neither, and a matched line keeps its
    own; each created row is a new bank line with the next `line_code`, and a matched
    line keeps its own (contract: POST /v1/transactions/import). A line of a statement
    the paper closed, matched by its operation code, still takes the bank's title
    (contract: POST /v1/transactions/import, "The bank's title wins"), so the apply
    writes the line and leaves its statement line, place and code as they were."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account(code=code)
    operation = f"OP{uuid4().hex[:10]}"
    held = scratch.row(account, "2026-03-05", -2590, operation_code=operation)
    line = held["bank_line_id"]
    paper = savings_paper(
        [PaperRow(date(2026, 3, 5), "TIENDA", -2590)],
        start=date(2026, 3, 1),
        end=date(2026, 3, 31),
        before_cents=100000,
    )
    closed = send_statement(client, account, paper, dry_run=False)
    scratch.took(closed)
    before = client.get(f"/bank-lines/{line}")
    assert closed["rows"][0]["bank_line_id"] == line
    assert (before["statement_line"], before["statement_place"]) == (f"{code}-202603-001", 1)

    download = [
        CURRENT_HEADER,
        ["05/03/2026", "TIENDA DEL BANCO", "S/", -25.9, operation],
        ["02/04/2026", "OTRA TIENDA", "S/", -10, f"OP{uuid4().hex[:10]}"],
    ]
    answer = send_download(client, account, download, dry_run=False)
    scratch.took(answer)
    matched, new = answer["rows"]
    assert (matched["outcome"], matched["rule"]) == ("matched", "operation_code")
    assert (matched["bank_line_id"], matched["retitled"]) == (line, True)
    assert new["outcome"] == "new"

    after = client.get(f"/bank-lines/{line}")
    assert [p["title"] for p in after["parts"]] == ["TIENDA DEL BANCO"]
    kept = ("statement_line", "statement_place", "line_code")
    assert {k: after[k] for k in kept} == {k: before[k] for k in kept}
    part = client.get(f"/transactions/{held['id']}")
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


def test_an_operation_code_in_another_letter_case_is_another_code(client, scratch, statuses):
    """Two operation codes are compared letter for letter, so `ABC…` and `abc…` on
    one account are two operation codes: each creates its own bank line and reads
    back as sent, and only the exact same operation code again on that account is
    `409` `OPERATION_CODE_EXISTS`, nothing written
    (contract: POST /v1/transactions, "Case counts")."""
    account = scratch.account()
    upper = f"ABC{_upper_fragment()}"
    when = scratch.noon("2026-04-15")
    first = scratch._item(account, when, -1000, "PEN", operation_code=upper)
    second = scratch._item(account, when, -2000, "PEN", operation_code=upper.lower())
    again = [
        scratch._item(account, when, -3000, "PEN", operation_code=v) for v in (upper, upper.lower())
    ]
    scratch.transactions.extend(body["id"] for body in (first, second, *again))
    lines = []
    for body in (first, second):
        made = client.post("/transactions", json_body=body)
        assert statuses[-1] == 201
        assert (made["account_id"], made["currency_code"]) == (account, "PEN")
        lines.append(made["bank_line_id"])
    assert lines[0] != lines[1]
    for body, line in zip((first, second), lines, strict=True):
        sent = body["operation_code"]
        assert client.get(f"/transactions/{body['id']}")["operation_code"] == sent
        read = client.get(f"/bank-lines/{line}")
        assert (read["operation_code"], read["account_id"]) == (sent, account)

    for body in again:
        err = refused(lambda body=body: client.post("/transactions", json_body=body))
        assert_refusal(err, 409, "CONFLICT", "operation_code", "OPERATION_CODE_EXISTS")
    assert live_ids(client, account) == {first["id"], second["id"]}
