"""Contract: what a bank line says a write would refuse and whether it is an opening
balance, and the whole-line write's `parts` on the two kinds of line that keep their
parts.

Every bank line the engine returns carries `edit_limits`: the line fields a write
would refuse; whether the total and the parts are fixed; and, per part, the part fields
a write would refuse. Each field named is `{reason, message}`, exactly two strings: the
reason the write gives it in `reasons` and its sentence in `fields`, word for word. It
is worked out on every read from the line's state, a completed reconciliation, an
archived account or an opening balance
(contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). The Edit form draws
those fields read-only before anyone types, so only the engine can say what each
state closes. Pinned here, the reasons read from each entry's `reason`, and for every
reason drawn a write changing those fields refused on each with that reason and the
read's `message` as its words:

  · a line nothing closes reads every key of `edit_limits` empty or `false`, on
    `GET /bank-lines/{id}`, on its row of `GET /bank-lines` and on the write's answer;
  · a line in a completed reconciliation: every line field `LOCKED` but an
    `operation_code` empty on every part, which is listed once filled; the total
    fixed and the parts not; the one part of a line of one part `SPLIT_TOTAL_MISMATCH`
    on `amount_cents`, no part of a split line; after a revert the next read is open;
  · a line on an archived account: every line field but the empty `operation_code`
    `ACCOUNT_ARCHIVED`, the total and the parts fixed, each part `ACCOUNT_ARCHIVED` on
    `amount_cents`; after an unarchive the next read is open;
  · an opening balance's line: `account_id` `OPENING_BALANCE_ACCOUNT_FIXED`, the parts
    fixed and the total not, its part `OPENING_BALANCE_CATEGORY_FIXED` on
    `category_id` and `OPENING_BALANCE_NOT_TAGGED` on `hashtag_ids`;
  · `is_opening_balance`, `true` on the opening balance's line and `false` on every
    other, on the read by id, each list row, the statement order's read and write, and
    the whole-line write's answer;
  · `parts` on an opening balance's line: its amount and note change in one write
    under its own id, its own category `@Opening` sent as is is no change, `[]` leaves
    it with no hashtag; another category is `OPENING_BALANCE_CATEGORY_FIXED` on
    `parts.0.category_id`, a hashtag (the pending one included)
    `OPENING_BALANCE_NOT_TAGGED` on `parts.0.hashtag_ids`, and a part added or left out
    `OPENING_BALANCE_NOT_SPLIT` on `parts`;
  · `parts` on an archived account's split line: both parts re-categorised and a note
    changed in one write, each sent its current amount, every id kept; an amount
    changed, the same size in the other direction included, is `ACCOUNT_ARCHIVED` on
    that part's `parts.<i>.amount_cents`, and a part added or left out
    `ACCOUNT_ARCHIVED` on `parts`.

Every refusal writes nothing: the line reads as it did, and a part it would have
created does not exist. An opening balance's line holds one part, so leaving it out
always comes with another part sent: `parts` holds at least one
(contract: PUT /v1/bank-lines/{bank_line_id}, "Parts").

The whole-line write's other rules are in test_bank_line_write.py; an archived
account's rows under the transaction routes are in test_resources_lifecycle.py.

Each test builds its own accounts and undoes everything (conftest.py `scratch`).
Gating, target and the real-ledger guard: conftest.py.
"""

from uuid import uuid4

from expense.formatting import signed_cents
from expense.reads import pending_hashtag_of
from tests.contract.conftest import assert_refusals, free_statement_codes, read_signed, refused

#: `edit_limits` of a line nothing closes: every key present, nothing in it
#: (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields").
OPEN = {"locked_fields": {}, "total_fixed": False, "parts_fixed": False, "locked_part_fields": {}}


def _reason_of(entry: dict) -> str:
    """A named field's reason, the entry being exactly `{reason, message}`, two strings
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")."""
    assert set(entry) == {"reason", "message"}, entry
    assert isinstance(entry["reason"], str) and isinstance(entry["message"], str), entry
    return entry["reason"]


def _reasons(limits: dict) -> dict:
    """`limits` with each named field read down to its `reason`."""
    by_part = limits["locked_part_fields"]
    return {
        **limits,
        "locked_fields": {k: _reason_of(v) for k, v in limits["locked_fields"].items()},
        "locked_part_fields": {
            part: {k: _reason_of(v) for k, v in fields.items()} for part, fields in by_part.items()
        },
    }


def _assert_the_writes_words(client, line_id: str, body: dict, reasons: dict, said: dict) -> None:
    """`body` sent to the line is `422` `VALIDATION_ERROR` with exactly `reasons`, and on
    each key of `said` the refusal's words are that `edit_limits` entry's `message`, its
    reason the entry's `reason`
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")."""
    err = refused(lambda: client.put(f"/bank-lines/{line_id}", json_body=body))
    assert_refusals(err, 422, "VALIDATION_ERROR", reasons)
    for key, entry in said.items():
        assert (err.reasons[key], err.fields[key]) == (entry["reason"], entry["message"]), key


def _line(client, line_id: str) -> dict:
    return client.get(f"/bank-lines/{line_id}")


def _limits(client, line_id: str) -> dict:
    return _line(client, line_id)["edit_limits"]


def _write(client, line_id: str, parts: list[dict]) -> dict:
    return client.put(f"/bank-lines/{line_id}", json_body={"parts": parts})


def _new_id(scratch) -> str:
    """A fresh part id, kept for cleanup before any write can create it."""
    new_id = str(uuid4())
    scratch.transactions.append(new_id)
    return new_id


def _assert_writes_nothing(client, line_id: str, parts: list[dict], reasons: dict) -> None:
    """`parts` sent to the line is `422` `VALIDATION_ERROR` with exactly `reasons`, and
    nothing is written: the line reads as it did, and no part it named under a new id
    exists (contract: PUT /v1/bank-lines/{bank_line_id}, "Refusals, in order")."""
    before = _line(client, line_id)
    held = {p["id"] for p in before["parts"]}
    err = refused(lambda: _write(client, line_id, parts))
    assert_refusals(err, 422, "VALIDATION_ERROR", reasons)
    assert _line(client, line_id) == before
    for part in parts:
        if part["id"] not in held:
            err = refused(lambda part=part: client.get(f"/transactions/{part['id']}"))
            assert err.status == 404, part


# ---- edit_limits, on each kind of line --------------------------------------------


def test_a_line_nothing_closes_has_no_limits(client, scratch):
    """A line of one part and a split line, in no reconciliation, on an active
    account: `edit_limits` names nothing, on the read by id, on the line's row of
    `GET /bank-lines` and on the write's answer, which is the line as read
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Response")."""
    account = scratch.account()
    single = scratch.line(account, "2026-05-04", -2500)
    split = scratch.line(account, "2026-05-05", -6000, -4000)

    listed = client.get("/bank-lines", params={"account_id": account})["items"]
    rows = {row["id"]: row for row in listed}
    for line_id in (single, split):
        assert _limits(client, line_id) == OPEN, line_id
        assert rows[line_id]["edit_limits"] == OPEN, line_id

    held = _line(client, split)["parts"]
    parts = [{"id": p["id"], "amount_cents": signed_cents(p)} for p in held]
    assert _write(client, split, parts)["edit_limits"] == OPEN


def test_a_completed_reconciliations_line_is_locked_until_reverted(client, scratch):
    """In a completed reconciliation every line field is `LOCKED` but an
    `operation_code` empty on every part, which may be filled and is listed once it is;
    the total is fixed and the parts are not; the one part of a line of one part is
    `SPLIT_TOTAL_MISMATCH` on `amount_cents`, while a split line lists no part. After
    the revert the next read names nothing
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")
    (contract: POST /v1/reconciliations/{reconciliation_id}/revert)."""
    account = scratch.account()
    recon = scratch.reconciliation(account, "2026-05-01", "2026-05-31")
    single = scratch.line(account, "2026-05-06", -2500, recon=recon)
    (single_part,) = scratch.transactions[-1:]
    split = scratch.line(account, "2026-05-07", -6000, -4000, recon=recon)
    client.post(f"/reconciliations/{recon}/complete")

    locked = dict.fromkeys(("title", "date", "account_id", "reconciliation_id"), "LOCKED")
    limits = _limits(client, single)
    assert _reasons(limits) == {
        "locked_fields": locked,
        "total_fixed": True,
        "parts_fixed": False,
        "locked_part_fields": {single_part: {"amount_cents": "SPLIT_TOTAL_MISMATCH"}},
    }
    assert _reasons(_limits(client, split)) == {
        "locked_fields": locked,
        "total_fixed": True,
        "parts_fixed": False,
        "locked_part_fields": {},
    }

    line_fields = limits["locked_fields"]
    moved = {
        "title": "contract moved title",
        "date": scratch.noon("2026-05-20"),
        "account_id": scratch.account(),
        "reconciliation_id": None,
    }
    _assert_the_writes_words(client, single, moved, locked, line_fields)
    amount = limits["locked_part_fields"][single_part]["amount_cents"]
    _assert_the_writes_words(
        client,
        single,
        {"parts": [{"id": single_part, "amount_cents": -3000}]},
        {"parts": "SPLIT_TOTAL_MISMATCH", "parts.0.amount_cents": "SPLIT_TOTAL_MISMATCH"},
        {"parts.0.amount_cents": amount},
    )

    client.put(f"/bank-lines/{single}", json_body={"operation_code": f"OP-{uuid4().hex[:10]}"})
    filled = _limits(client, single)["locked_fields"]
    assert {k: _reason_of(v) for k, v in filled.items()} == {**locked, "operation_code": "LOCKED"}
    _assert_the_writes_words(
        client,
        single,
        {"operation_code": f"OP-{uuid4().hex[:10]}"},
        {"operation_code": "LOCKED"},
        {"operation_code": filled["operation_code"]},
    )

    client.post(f"/reconciliations/{recon}/revert")
    assert _limits(client, single) == OPEN
    assert _limits(client, split) == OPEN


def test_an_archived_accounts_line_is_frozen_until_unarchived(client, scratch):
    """On an archived account every line field is `ACCOUNT_ARCHIVED` but an
    `operation_code` empty on every part; the total and the parts are fixed, and each
    part is `ACCOUNT_ARCHIVED` on `amount_cents`, its category, hashtags and note left
    open. After the unarchive the next read names nothing
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")
    (contract: POST /v1/accounts/{account_id}/unarchive)."""
    account = scratch.account()
    line = scratch.line(account, "2026-05-08", -6000, -4000)
    one, two = scratch.transactions[-2:]
    scratch.archive(account)

    archived = {"amount_cents": "ACCOUNT_ARCHIVED"}
    line_fields = dict.fromkeys(
        ("title", "date", "account_id", "reconciliation_id"), "ACCOUNT_ARCHIVED"
    )
    limits = _limits(client, line)
    assert _reasons(limits) == {
        "locked_fields": line_fields,
        "total_fixed": True,
        "parts_fixed": True,
        "locked_part_fields": {one: archived, two: archived},
    }

    moved = {
        "title": "contract moved title",
        "date": scratch.noon("2026-05-20"),
        "account_id": account,
        "reconciliation_id": None,
    }
    _assert_the_writes_words(client, line, moved, line_fields, limits["locked_fields"])
    _assert_the_writes_words(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -5000}, {"id": two, "amount_cents": -3000}]},
        {"parts.0.amount_cents": "ACCOUNT_ARCHIVED", "parts.1.amount_cents": "ACCOUNT_ARCHIVED"},
        {
            "parts.0.amount_cents": limits["locked_part_fields"][one]["amount_cents"],
            "parts.1.amount_cents": limits["locked_part_fields"][two]["amount_cents"],
        },
    )

    client.post(f"/accounts/{account}/unarchive")
    assert _limits(client, line) == OPEN


def test_an_opening_balances_line_keeps_its_account_and_its_parts(client, scratch):
    """An opening balance's line: `account_id` is `OPENING_BALANCE_ACCOUNT_FIXED`, the
    parts are fixed and the total is not, and its part is
    `OPENING_BALANCE_CATEGORY_FIXED` on `category_id` and `OPENING_BALANCE_NOT_TAGGED`
    on `hashtag_ids`, its amount and note left open
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")."""
    account = scratch.account()
    line = scratch.opening_balance(account, "2026-01-01")
    (opening,) = scratch.transactions[-1:]

    limits = _limits(client, line)
    part_fields = {
        "category_id": "OPENING_BALANCE_CATEGORY_FIXED",
        "hashtag_ids": "OPENING_BALANCE_NOT_TAGGED",
    }
    assert _reasons(limits) == {
        "locked_fields": {"account_id": "OPENING_BALANCE_ACCOUNT_FIXED"},
        "total_fixed": False,
        "parts_fixed": True,
        "locked_part_fields": {opening: part_fields},
    }

    _assert_the_writes_words(
        client,
        line,
        {"account_id": scratch.account()},
        {"account_id": "OPENING_BALANCE_ACCOUNT_FIXED"},
        limits["locked_fields"],
    )
    amount = read_signed(client, opening)["amount_cents"]
    sent = {"category_id": scratch.category(), "hashtag_ids": [scratch.hashtag()]}
    _assert_the_writes_words(
        client,
        line,
        {"parts": [{"id": opening, "amount_cents": amount, **sent}]},
        {f"parts.0.{field}": reason for field, reason in part_fields.items()},
        {
            f"parts.0.{field}": entry
            for field, entry in limits["locked_part_fields"][opening].items()
        },
    )


# ---- is_opening_balance, on every bank-line read ----------------------------------


def _flags(lines: list[dict]) -> dict[str, bool]:
    return {line["id"]: line["is_opening_balance"] for line in lines}


def test_a_line_says_whether_it_is_its_accounts_opening_balance(client, scratch):
    """`is_opening_balance` is `true` on the account's opening balance and `false` on
    every other line, a split one included, never `null`: on the read by id, on each
    row of `GET /bank-lines` in either order, on the statement order's `places` and
    `unplaced` as its read and its write answer them, and on the whole-line write's
    answer (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")
    (contract: GET /v1/bank-lines)
    (contract: GET /v1/reconciliations/{reconciliation_id}/statement-order, "Response")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Response"). The opening balance is
    the line the statement's order never places, so it stays under `unplaced`; a list
    naming it is refused (test_statement_order.py, `OPENING_BALANCE_NOT_PLACED`)."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account("PEN", code)
    recon = scratch.reconciliation(account, "2026-05-01", "2026-05-31")
    opening = scratch.opening_balance(account, "2026-05-01", recon)
    single = scratch.line(account, "2026-05-04", -2500, recon=recon)
    split = scratch.line(account, "2026-05-05", -6000, -4000, recon=recon)
    expected = {opening: True, single: False, split: False}

    for line_id, flag in expected.items():
        assert _line(client, line_id)["is_opening_balance"] is flag, line_id
    for params in ({"account_id": account}, {"reconciliation_id": recon, "sort": "statement"}):
        assert _flags(client.get("/bank-lines", params=params)["items"]) == expected, params

    order = client.get(f"/reconciliations/{recon}/statement-order")
    assert _flags(order["unplaced"]) == expected
    sent = client.put(
        f"/reconciliations/{recon}/statement-order", json_body={"places": [single, split]}
    )
    assert _flags([entry["bank_line"] for entry in sent["places"]]) == {single: False, split: False}
    assert _flags(sent["unplaced"]) == {opening: True}

    for line_id, flag in expected.items():
        held = _line(client, line_id)["parts"]
        parts = [{"id": p["id"], "amount_cents": signed_cents(p)} for p in held]
        assert _write(client, line_id, parts)["is_opening_balance"] is flag, line_id


# ---- parts on an opening balance's line ------------------------------------------


def test_an_opening_balances_line_takes_its_amount_and_note_in_one_write(client, scratch):
    """The whole-line write changes an opening balance's amount and note in one write,
    the part keeping its id; its own category, `@Opening`, sent as it is at its current
    amount is no change and writes nothing; `hashtag_ids` `[]` is taken and leaves it
    with no hashtag
    (contract: PUT /v1/bank-lines/{bank_line_id},
    "A line holding an opening balance keeps its parts")."""
    account = scratch.account()
    line = scratch.opening_balance(account, "2026-01-01")
    (opening,) = scratch.transactions[-1:]
    held = read_signed(client, opening)
    category = held["category_id"]
    assert client.get(f"/categories/{category}")["system_key"] == "opening_balance"

    answer = _write(client, line, [{"id": opening, "amount_cents": 42000, "description": "paper"}])
    assert (answer["created_part_ids"], answer["deleted_part_ids"]) == ([], [])
    assert [p["id"] for p in answer["parts"]] == [opening]
    assert answer["net_cents"] == 42000
    edited = read_signed(client, opening)
    assert (edited["amount_cents"], edited["description"]) == (42000, "paper")
    assert (edited["category_id"], edited["version"]) == (category, held["version"] + 1)

    _write(client, line, [{"id": opening, "amount_cents": 42000, "category_id": category}])
    assert read_signed(client, opening) == edited

    _write(client, line, [{"id": opening, "amount_cents": 42000, "hashtag_ids": []}])
    tagged = read_signed(client, opening)
    assert (tagged["hashtag_ids"], tagged["category_id"]) == ([], category)
    assert [p["id"] for p in _line(client, line)["parts"]] == [opening]


def test_an_opening_balances_line_refuses_another_category_a_hashtag_and_a_new_set(client, scratch):
    """On an opening balance's line another category is `OPENING_BALANCE_CATEGORY_FIXED`
    on `parts.0.category_id`; a hashtag, the pending one included, is
    `OPENING_BALANCE_NOT_TAGGED` on `parts.0.hashtag_ids`; a part added beside it, or
    the part left out for another, is `OPENING_BALANCE_NOT_SPLIT` on `parts`. Each
    writes nothing
    (contract: PUT /v1/bank-lines/{bank_line_id},
    "A line holding an opening balance keeps its parts")."""
    account = scratch.account()
    line = scratch.opening_balance(account, "2026-01-01")
    (opening,) = scratch.transactions[-1:]
    amount = read_signed(client, opening)["amount_cents"]
    pending = pending_hashtag_of(client.get("/hashtags")["items"])
    assert pending is not None

    kept = {"id": opening, "amount_cents": amount}
    _assert_writes_nothing(
        client,
        line,
        [{**kept, "category_id": scratch.category()}],
        {"parts.0.category_id": "OPENING_BALANCE_CATEGORY_FIXED"},
    )
    for tags in ([scratch.hashtag()], [pending[0]]):
        _assert_writes_nothing(
            client,
            line,
            [{**kept, "hashtag_ids": tags}],
            {"parts.0.hashtag_ids": "OPENING_BALANCE_NOT_TAGGED"},
        )
    _assert_writes_nothing(
        client,
        line,
        [kept, {"id": _new_id(scratch), "amount_cents": 1000}],
        {"parts": "OPENING_BALANCE_NOT_SPLIT"},
    )
    _assert_writes_nothing(
        client,
        line,
        [{"id": _new_id(scratch), "amount_cents": amount}],
        {"parts": "OPENING_BALANCE_NOT_SPLIT"},
    )


# ---- parts on an archived account's line ------------------------------------------


def test_an_archived_accounts_line_is_re_categorised_in_one_write(client, scratch):
    """On an archived account's split line both parts take a new category, and one a
    note, in one write that sends each part its current amount: every part keeps its
    id, none is created or deleted, and the amounts stay
    (contract: PUT /v1/bank-lines/{bank_line_id},
    "A line with a part on an archived account keeps its parts and their amounts")."""
    account = scratch.account()
    line = scratch.line(account, "2026-05-09", -6000, -4000)
    one, two = scratch.transactions[-2:]
    first, second = scratch.category(), scratch.category()
    versions = {p["id"]: p["version"] for p in _line(client, line)["parts"]}
    scratch.archive(account)

    answer = _write(
        client,
        line,
        [
            {"id": one, "amount_cents": -6000, "category_id": first, "description": "kept"},
            {"id": two, "amount_cents": -4000, "category_id": second},
        ],
    )
    assert (answer["created_part_ids"], answer["deleted_part_ids"]) == ([], [])
    assert {p["id"] for p in answer["parts"]} == {one, two}
    mine, other = read_signed(client, one), read_signed(client, two)
    assert (mine["amount_cents"], mine["category_id"], mine["description"]) == (
        -6000,
        first,
        "kept",
    )
    assert (other["amount_cents"], other["category_id"]) == (-4000, second)
    assert {one: mine["version"], two: other["version"]} == {
        one: versions[one] + 1,
        two: versions[two] + 1,
    }


def test_an_archived_accounts_line_refuses_a_new_amount_and_a_new_set(client, scratch):
    """On an archived account's split line a kept part sent another amount, the same
    size in the other direction included, is `ACCOUNT_ARCHIVED` on that part's
    `parts.<i>.amount_cents`; a part added, or one left out, is `ACCOUNT_ARCHIVED` on
    `parts`. Each writes nothing
    (contract: PUT /v1/bank-lines/{bank_line_id},
    "A line with a part on an archived account keeps its parts and their amounts")."""
    account = scratch.account()
    line = scratch.line(account, "2026-05-10", -6000, -4000)
    one, two = scratch.transactions[-2:]
    scratch.archive(account)

    archived = "ACCOUNT_ARCHIVED"
    for parts, key in (
        ([{"id": one, "amount_cents": -5000}, {"id": two, "amount_cents": -4000}], "parts.0"),
        ([{"id": one, "amount_cents": 6000}, {"id": two, "amount_cents": -4000}], "parts.0"),
        ([{"id": one, "amount_cents": -6000}, {"id": two, "amount_cents": -3000}], "parts.1"),
    ):
        _assert_writes_nothing(client, line, parts, {f"{key}.amount_cents": archived})
    _assert_writes_nothing(
        client,
        line,
        [
            {"id": one, "amount_cents": -6000},
            {"id": two, "amount_cents": -4000},
            {"id": _new_id(scratch), "amount_cents": -1000},
        ],
        {"parts": archived},
    )
    _assert_writes_nothing(client, line, [{"id": one, "amount_cents": -6000}], {"parts": archived})
