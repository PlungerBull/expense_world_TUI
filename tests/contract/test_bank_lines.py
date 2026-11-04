"""Contract: bank lines and their parts, on an account that holds its currencies.

Every transaction belongs to one bank line, and a line is on one account in one currency,
which the line and each of its parts read as `account_id` and `currency_code`; the whole-line
write gives a line its complete set of parts, keeping its identity (contract: "Transactions
(Ledger)", "Bank lines"). The Edit form, its "changes every part" note and the bank upload all
stand on rules only the engine can confirm. Pinned here:

  · new parts sent alone replace the line's one transaction on the same line, each
    taking the line's title, date, account and currency; a re-split (60 + 40 into 70 + 30)
    sent under the parts' own ids keeps both ids, creating and deleting nothing;
  · `PUT` of `title` on one part writes it onto every part, while `amount_cents`
    and `description` change only the part named;
  · the ledger's bulk keys on parts, through the app's own `bulk_writes`:
    `category_id` and `hashtag_ids` on one part leave the other part unwritten;
    `account_id` on one part moves every part; and `b` with both parts of a
    line in a draft statement selected sends the second part a body built
    before the first `PUT` moved the line, which the engine accepts;
  · a made-up download imported, its line split, and imported again is every row
    `matched`, none `new`: by `operation_code`, and by `same_day` for a card row with no
    operation code;
  · a batch whose two items share a `line_group` makes one line of two parts, and a
    dry run of a made-up download whose one row is its total is `matched` on it;
  · `?bank_line_id=` on the list and the count names exactly a line's parts; an
    id naming no line lists nothing and counts 0, a malformed one is `422`
    `INVALID_FORMAT` on `bank_line_id`, and a cursor issued under one line's
    filter is `422` `INVALID_CURSOR` on `after` under another;
  · `GET /bank-lines/{id}` reads `id`, `line_code`, `account_id`, `currency_code`,
    `operation_code`, `statement_line`, `statement_place`, the signed
    `net_cents`, `part_count`, `is_opening_balance`, `parts` and `edit_limits`,
    each part exactly the transaction read by id: a line in no statement reads a `null`
    statement line and place, an unsplit line is one part at its signed amount, a split
    60 + 40 reads `-10000` over two parts in the ledger's order; an unknown id is
    `404`, a malformed one `422` `INVALID_FORMAT`;
  · the Edit form's own path: a line never split keeps its one transaction as
    part 1 beside a part added, one `fetch_bank_line` reads the parts and the total
    back, the parts read change nothing so the form sends nothing, a part dropped
    and one added are deleted and created in one write, and in a completed
    statement a set that misses the total names parts 1 and 2;
  · the Edit form's title: a changed `title` beside `parts` gives every part that
    title, and without it every part keeps the line's; on a line in a completed
    statement the title is read-only and never sent, so the parts go through,
    and a body with a changed title is `422` `LOCKED` on `title` with nothing
    written;
  · the "no batch" Edit form: its one write carries the line fields changed beside
    every part at its amount, an emptied operation clears the code and an account
    move carries every part;
  · a line is in a statement whole: `statement_id` sent on one part puts every part in
    the statement, and `null` on one part takes every part out;
  · a `PUT` answers with `changed_parts`, each part whose line fields it changed
    and whether it left its statement: one part of a 60 + 40 line moved to another
    account out of a draft lists both, both left; the other part sent the account it
    already has, or a body of `category_id` alone, lists none; a one-part line lists
    itself, left only when it was assigned; a replay answers the same;
  · `DELETE /bank-lines/{id}` deletes every part in one write, after which the
    line and its parts read `404` and its `operation_code` is free; a line in a
    completed statement is `409` `IN_COMPLETED_RECONCILIATION` on
    `bank_line_id`, with nothing deleted;
  · `GET /bank-lines` and its count: one row per line, each the line read by
    id, newest first; `?account_id=` lists every currency of the account, `?currency_code=`
    narrows it or, alone, lists that currency on every account, and a code that is not
    supported is `422` `UNSUPPORTED_VALUE` on both; the filters on whole lines, the count
    agreeing with the list, pages counted in lines that never cut a split line in two, and a
    cursor bound to its list and its filters;
  · the statement's review list, `?unassigned_in_period_of=` with `sort=statement`, on a
    draft and on a completed statement: the lines in no statement dated from the previous
    statement's last day to the statement's last day, in every currency of the account
    (a dollar line on a soles-only statement's days included), the same before and after the
    close, dropped when assigned; it is taken alone and in no other order;
  · the flagged lines' screen's own reads of the review list (the count and every page in
    the statement's order): on a draft the count is the list's length, and after the close
    the list is the draft's, oldest first across both currencies, each currency's
    `review_lines` being that list's lines in that currency, in its order;
  · the statement screen's own reads of a draft month (the statement's lines, and the
    account's lines in no statement inside the period) list a split purchase as one row of
    its total, and a tick on the one part it names moves the whole line in and out;
  · a batch `line_group` whose items differ is `LINE_GROUP_FIELDS_DIFFER` on each
    item's field.

The whole-line write's own rules (a part kept, added and dropped in one write, the
total, the locked line fields, a kept part's hashtags, a replay) are in
test_bank_line_write.py; `edit_limits` on each kind of line, and the parts of an
opening balance's line and of an archived account's line, in
test_bank_line_edit_limits.py; the lines read by `ids` and oldest first in
test_bank_lines_by_ids.py.

Not pinned here: `SPLIT_LINE_PARTS_DIVERGE`. No route leaves a line's parts on
different accounts or dates: a part the whole-line write creates takes the line's
account and date, a `line_group` must share them, and `PUT` writes either onto every
part (contract: "Transactions (Ledger)", "Bank lines"). Such a line comes only from a
manual database repair outside the engine, so no client test can build one; the
refusal is a safety check for that case.

Each test builds its own accounts and undoes what it wrote (conftest.py `scratch`). Gating,
target and the real-ledger guard: conftest.py.
"""

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from expense import http as http_module
from expense.formatting import signed_cents
from expense.reads import count_bank_lines, fetch_bank_line, fetch_bank_lines
from tests.contract.conftest import (
    CARD_HEADER,
    CURRENT_HEADER,
    assert_refusal,
    balance_of,
    live_ids,
    read_signed,
    reason_on,
    refused,
    replace_parts,
    send_download,
)

APRIL = ("2026-04-01", "2026-04-30")
MARCH = ("2026-03-01", "2026-03-31")


def _pen(ending: int, beginning: int = 0) -> list[dict]:
    """The soles balances of a statement made by `scratch.statement`."""
    return [
        {
            "currency_code": "PEN",
            "beginning_balance_cents": beginning,
            "ending_balance_cents": ending,
        }
    ]


def _noon_of(scratch, day: str) -> datetime:
    return datetime.fromisoformat(scratch.noon(day))


def test_new_parts_replace_the_line_and_a_re_split_keeps_their_ids(client, statuses, scratch):
    """One whole-line write sending only new ids replaces every part on the same line,
    each new part taking the line's title, date, account and currency
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"). A re-split of 60 + 40 into
    70 + 30 sends both parts under their own ids: each keeps its id and its own
    category and description, and nothing is created or deleted."""
    account = scratch.account("PEN", "USD")
    groceries = scratch.category()
    original = scratch.row(account, "2026-04-06", -10000, "USD", title="SUPERMERCADO LIMA")
    line = original["bank_line_id"]
    assert line

    # Two new parts: the same line, the line's title/date/account/currency on each.
    parts = [
        {
            "id": str(uuid4()),
            "amount_cents": -6000,
            "category_id": groceries,
            "description": "food",
        },
        {"id": str(uuid4()), "amount_cents": -4000},
    ]
    scratch.transactions.extend(p["id"] for p in parts)
    body = client.put(f"/bank-lines/{line}", json_body={"parts": parts})
    assert statuses[-1] == 200
    assert (body["id"], body["line_code"]) == (line, original["line_code"])
    assert (body["account_id"], body["currency_code"]) == (account, "USD")
    assert body["created_part_ids"] == [p["id"] for p in parts]
    assert body["deleted_part_ids"] == [original["id"]]
    assert {p["id"] for p in body["parts"]} == {p["id"] for p in parts}
    by_id = {p["id"]: p for p in body["parts"]}
    first = [by_id[p["id"]] for p in parts]
    assert [read_signed(client, p["id"])["amount_cents"] for p in first] == [-6000, -4000]
    assert {p["bank_line_id"] for p in first} == {line}
    for part in first:
        assert part["title"] == "SUPERMERCADO LIMA"
        assert (part["account_id"], part["currency_code"]) == (account, "USD")
        assert datetime.fromisoformat(part["date"]) == _noon_of(scratch, "2026-04-06")
    assert first[0]["category_id"] == groceries
    assert first[0]["description"] == "food"
    assert live_ids(client, account) == {p["id"] for p in parts}
    err = refused(lambda: client.get(f"/transactions/{original['id']}"))
    assert err.status == 404

    # Re-split 60 + 40 into 70 + 30: both parts sent under their own ids.
    again = client.put(
        f"/bank-lines/{line}",
        json_body={
            "parts": [
                {"id": first[0]["id"], "amount_cents": -7000},
                {"id": first[1]["id"], "amount_cents": -3000},
            ]
        },
    )
    assert (again["created_part_ids"], again["deleted_part_ids"]) == ([], [])
    kept = [read_signed(client, p["id"]) for p in first]
    assert [p["amount_cents"] for p in kept] == [-7000, -3000]
    assert [p["version"] for p in kept] == [p["version"] + 1 for p in first]
    assert (kept[0]["category_id"], kept[0]["description"]) == (groceries, "food")
    assert {p["bank_line_id"] for p in kept} == {line}
    assert live_ids(client, account) == {p["id"] for p in first}


def test_a_line_field_reaches_every_part_and_the_rest_stay_own(client, scratch):
    account = scratch.account()
    original = scratch.row(account, "2026-04-07", -5000, title="FARMACIA")
    one, two = replace_parts(client, original["bank_line_id"], [-3000, -2000], scratch.transactions)

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
    mine = read_signed(client, one["id"])
    assert (mine["amount_cents"], mine["description"]) == (-3500, "vitamins")
    after = read_signed(client, two["id"])
    assert after["amount_cents"] == -2000
    assert after["description"] == before["description"]
    assert after["version"] == before["version"]


def _ledger_bulk(client, parts: list[dict], payload: dict) -> list[dict]:
    """The ledger's bulk key over `parts`, selected in that order, as the app sends
    it: `bulk_writes` builds each body from the rows as the ledger last read them,
    then one `PUT` per row, in order. Returns each response."""
    from expense.tui.screens.transactions import bulk_writes

    by_id = {p["id"]: p for p in parts}
    writes = bulk_writes([p["id"] for p in parts], payload, by_id)
    return [client.put(f"/transactions/{key}", json_body=body) for key, body in writes]


def test_a_parts_category_and_hashtags_stay_its_own(client, scratch):
    """`category_id` and `hashtag_ids` are a part's own: sent on one part they
    change only it, and the other part is not written, its `version` unmoved. The
    ledger's `c` and `h` with both parts selected send one `PUT` per part, and
    each is accepted (contract: PUT /v1/transactions/{transaction_id}, "Line fields")."""
    account = scratch.account()
    groceries = scratch.category()
    food = scratch.hashtag()
    original = scratch.row(account, "2026-04-08", -5000, title="TOTTUS")
    one, two = replace_parts(client, original["bank_line_id"], [-3000, -2000], scratch.transactions)
    before = client.get(f"/transactions/{two['id']}")

    mine = client.put(f"/transactions/{one['id']}", json_body={"category_id": groceries})
    assert mine["category_id"] == groceries
    mine = client.put(f"/transactions/{one['id']}", json_body={"hashtag_ids": [food]})
    assert mine["hashtag_ids"] == [food]
    other = client.get(f"/transactions/{two['id']}")
    assert other["category_id"] == before["category_id"] != groceries
    assert other["hashtag_ids"] == before["hashtag_ids"] != [food]
    assert other["version"] == before["version"]

    # Both parts selected: one PUT each, both accepted, each part its own value.
    parts = [client.get(f"/transactions/{p['id']}") for p in (one, two)]
    _ledger_bulk(client, parts, {"category_id": groceries})
    parts = [client.get(f"/transactions/{p['id']}") for p in (one, two)]
    _ledger_bulk(client, parts, {"hashtag_ids": [food]})
    for part in (one, two):
        read = client.get(f"/transactions/{part['id']}")
        assert (read["category_id"], read["hashtag_ids"]) == (groceries, [food])


def test_an_account_move_on_one_part_moves_the_whole_line(client, scratch):
    """`account_id` is a line field: sent on one part, every part moves to the
    account in that one write, the other part's `version` up by one. The ledger's
    `b` with both parts of a line in a draft statement selected sends each part
    `account_id` with `statement_id: null`, built from the read before the move: the
    first `PUT` moves the whole line out of the statement, and the engine accepts the
    second as it is, writing no other part, the part named taking one more `version`
    (contract: PUT /v1/transactions/{transaction_id}, "Line fields")
    (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction")."""
    home = scratch.account()
    away = scratch.account()
    draft = scratch.statement(home, *APRIL)["id"]

    def both() -> list[dict]:
        return [client.get(f"/transactions/{p['id']}") for p in (one, two)]

    original = scratch.row(home, "2026-04-09", -5000, title="SAGA")
    one, two = replace_parts(client, original["bank_line_id"], [-3000, -2000], scratch.transactions)

    # `b` with both parts selected, the line in a draft statement.
    scratch.assign(one["id"], draft)
    loaded = both()
    assert {p["statement_id"] for p in loaded} == {draft}
    first, second = _ledger_bulk(client, loaded, {"account_id": away})
    assert (first["account_id"], second["account_id"]) == (away, away)
    after = both()
    assert [(p["account_id"], p["currency_code"], p["statement_id"]) for p in after] == [
        (away, "PEN", None)
    ] * 2
    assert after[0]["version"] == loaded[0]["version"] + 1
    assert after[1]["version"] == loaded[1]["version"] + 2
    assert live_ids(client, home) == set()

    # `b` on one part: the whole line comes back.
    loaded = both()
    (moved,) = _ledger_bulk(client, loaded[:1], {"account_id": home})
    assert moved["account_id"] == home
    after = both()
    assert [(p["account_id"], p["currency_code"], p["statement_id"]) for p in after] == [
        (home, "PEN", None)
    ] * 2
    assert after[1]["version"] == loaded[1]["version"] + 1
    assert live_ids(client, away) == set()


@pytest.mark.parametrize(
    ("code", "rule"),
    [(f"OP-{uuid4().hex[:10]}", "operation_code"), (None, "same_day")],
    ids=["with-operation-code", "card-row-no-operation-code"],
)
def test_a_split_line_is_matched_on_re_import(client, scratch, code, rule):
    """A made-up download, a current account's with an operation number or a card's
    without one, imported, its line split, and imported again: the row is `matched` on
    the split line and nothing new is written
    (contract: POST /v1/transactions/import, "Bank lines, not rows")."""
    account = scratch.account()
    if code is None:
        statement = [CARD_HEADER, ["2026-04-08", "TIENDA LIMA PE", "S/", -80]]
    else:
        statement = [CURRENT_HEADER, ["08/04/2026", "TIENDA LIMA PE", "S/", -80, code]]

    first = send_download(client, account, statement, dry_run=False)
    scratch.took(first)
    assert [r["outcome"] for r in first["rows"]] == ["new"]
    line = client.get(f"/transactions/{first['rows'][0]['transaction_id']}")["bank_line_id"]

    parts = replace_parts(client, line, [-5000, -3000], scratch.transactions)
    assert {p["bank_line_id"] for p in parts} == {line}

    again = send_download(client, account, statement, dry_run=False)
    scratch.took(again)
    (only,) = again["rows"]
    assert only["outcome"] == "matched"
    assert only["rule"] == rule
    assert only["bank_line_id"] == line
    assert again["counts"]["new"] == 0
    assert again["counts"]["matched"] == 1
    assert again["day_mismatches"] == []
    assert live_ids(client, account) == {p["id"] for p in parts}


def test_assigning_one_part_assigns_and_unassigns_the_whole_line(client, scratch):
    """`statement_id` is a line field: sent on one part, it puts every live part of the
    line in the statement, and `null` on one part takes every part out
    (contract: PUT /v1/transactions/{transaction_id}, "Line fields")
    (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment")."""
    account = scratch.account()
    draft = scratch.statement(account, *APRIL)["id"]
    original = scratch.row(account, "2026-04-10", -10000, title="line")
    one, two = replace_parts(client, original["bank_line_id"], [-6000, -4000], scratch.transactions)

    def statements() -> list:
        return [client.get(f"/transactions/{p['id']}")["statement_id"] for p in (one, two)]

    scratch.assign(one["id"], draft)
    assert statements() == [draft, draft]
    assert client.get(f"/transactions/{two['id']}")["version"] == two["version"] + 1
    listed = client.get("/transactions", params={"statement_id": draft})["items"]
    assert {t["id"] for t in listed} == {one["id"], two["id"]}

    scratch.assign(two["id"], None)
    assert statements() == [None, None]
    assert client.get("/transactions", params={"statement_id": draft})["items"] == []


def _changed(answer: dict) -> list[tuple[str, bool]]:
    """`changed_parts` of a `PUT /transactions/{id}` answer as `(id, left_statement)`."""
    return [(e["transaction"]["id"], e["left_statement"]) for e in answer["changed_parts"]]


def _assert_parts_read_back(client, answer: dict, named: str) -> None:
    """Each `changed_parts` entry is its part exactly as `GET /transactions/{id}` reads it
    after the write, and the named part's entry repeats the top-level transaction."""
    top = {k: v for k, v in answer.items() if k != "changed_parts"}
    for entry in answer["changed_parts"]:
        part = entry["transaction"]
        assert part == client.get(f"/transactions/{part['id']}")
        if part["id"] == named:
            assert part == top


def test_a_move_answers_with_every_part_it_changed(client, scratch, monkeypatch):
    """`changed_parts` lists each part of the line whose line fields the write changed,
    `left_statement` on each, in the order `?bank_line_id=` lists the line. One part
    of a 60 + 40 line in a draft statement moved to another account with
    `statement_id: null` lists both parts, both left; the other part sent the account the
    line already has lists none; a body changing only `category_id` lists none while
    `version` still bumps; and a replay under the same key answers exactly as the first
    send (contract: PUT /v1/transactions/{transaction_id}, "Response")."""
    home = scratch.account()
    away = scratch.account()
    groceries = scratch.category()
    draft = scratch.statement(home, *APRIL)["id"]
    original = scratch.row(home, "2026-04-11", -10000, title="FARMACIA")
    one, two = replace_parts(client, original["bank_line_id"], [-6000, -4000], scratch.transactions)
    listed = client.get("/transactions", params={"bank_line_id": original["bank_line_id"]})
    order = [t["id"] for t in listed["items"]]
    assert sorted(order) == sorted([one["id"], two["id"]])
    scratch.assign(one["id"], draft)

    # One part moved out of the draft: both parts listed, both left it.
    moved = client.put(
        f"/transactions/{one['id']}", json_body={"account_id": away, "statement_id": None}
    )
    assert _changed(moved) == [(tx_id, True) for tx_id in order]
    _assert_parts_read_back(client, moved, one["id"])

    # The other part sent the account the line already has: nothing changed.
    again = client.put(
        f"/transactions/{two['id']}", json_body={"account_id": away, "statement_id": None}
    )
    assert again["changed_parts"] == []

    # Only the category: no line field changed, but the part's version bumps.
    before = client.get(f"/transactions/{one['id']}")["version"]
    recategorised = client.put(f"/transactions/{one['id']}", json_body={"category_id": groceries})
    assert recategorised["changed_parts"] == []
    assert recategorised["version"] == before + 1

    # A replay under the same key answers exactly as the first send did.
    key = uuid4()
    monkeypatch.setattr(http_module, "uuid", SimpleNamespace(uuid4=lambda: key))
    first = client.put(f"/transactions/{one['id']}", json_body={"account_id": home})
    replayed = client.put(f"/transactions/{one['id']}", json_body={"account_id": home})
    monkeypatch.undo()
    assert _changed(first) == [(tx_id, False) for tx_id in order]
    assert replayed == first


@pytest.mark.parametrize("assigned", [True, False], ids=["in-a-draft", "in-none"])
def test_a_one_part_line_moved_lists_itself(client, scratch, assigned):
    """A line of one part moved to another account lists that part alone, flagged
    `left_statement` only when it was in a statement before the write
    (contract: PUT /v1/transactions/{transaction_id}, "Response")."""
    home = scratch.account()
    away = scratch.account()
    draft = scratch.statement(home, *APRIL)["id"]
    tx = scratch.row(home, "2026-04-12", -4200, title="UBER *TRIP")
    if assigned:
        scratch.assign(tx["id"], draft)

    moved = client.put(
        f"/transactions/{tx['id']}", json_body={"account_id": away, "statement_id": None}
    )
    assert _changed(moved) == [(tx["id"], assigned)]
    _assert_parts_read_back(client, moved, tx["id"])


def test_deleting_a_bank_line_deletes_every_part(client, statuses, scratch):
    """One `DELETE /bank-lines/{id}` soft-deletes every live part, answers each
    part as `DELETE /transactions/{id}` would in the ledger's order, and the line
    goes with them: it and its parts read `404`, and its `operation_code` is free
    on the account (contract: DELETE /v1/bank-lines/{bank_line_id})."""
    account = scratch.account()
    code = f"OP-{uuid4().hex[:10]}"
    original = scratch.row(account, "2026-04-16", -10000, title="TOTTUS", operation_code=code)
    line = original["bank_line_id"]
    parts = replace_parts(client, line, [-6000, -4000], scratch.transactions)
    order = [p["id"] for p in client.get(f"/bank-lines/{line}")["parts"]]

    gone = client.delete(f"/bank-lines/{line}")
    assert statuses[-1] == 200
    assert set(gone) == {"parts"}
    assert [p["id"] for p in gone["parts"]] == order
    assert {p["id"] for p in gone["parts"]} == {p["id"] for p in parts}
    for part in gone["parts"]:
        assert part["deleted_at"] is not None
        assert part["hashtag_ids"] == []

    err = refused(lambda: client.get(f"/bank-lines/{line}"))
    assert (err.status, err.code) == (404, "NOT_FOUND")
    for part in parts:
        err = refused(lambda part=part: client.get(f"/transactions/{part['id']}"))
        assert err.status == 404
    assert live_ids(client, account) == set()
    err = refused(lambda: client.delete(f"/bank-lines/{line}"))
    assert (err.status, err.code) == (404, "NOT_FOUND")
    err = refused(lambda: client.delete("/bank-lines/not-a-uuid"))
    assert_refusal(err, 422, "VALIDATION_ERROR", "bank_line_id", "INVALID_FORMAT")

    # The operation code is free: a new line on the account takes it.
    again = scratch.row(account, "2026-04-16", -500, title="again")
    client.put(f"/transactions/{again['id']}", json_body={"operation_code": code})
    assert client.get(f"/transactions/{again['id']}")["operation_code"] == code


def test_a_line_in_a_completed_statement_is_not_deleted(client, scratch):
    """A line whose parts are in a completed statement is `409` on
    `bank_line_id` (`IN_COMPLETED_RECONCILIATION`), judged before anything
    changes: every part stays (contract: DELETE /v1/bank-lines/{bank_line_id})."""
    account = scratch.account()
    draft = scratch.statement(account, *APRIL, balances=_pen(-10000))["id"]
    original = scratch.row(account, "2026-04-17", -10000, title="held")
    line = original["bank_line_id"]
    parts = replace_parts(client, line, [-6000, -4000], scratch.transactions)
    scratch.assign(parts[0]["id"], draft)
    client.post(f"/statements/{draft}/complete")

    err = refused(lambda: client.delete(f"/bank-lines/{line}"))
    assert_refusal(err, 409, "CONFLICT", "bank_line_id", "IN_COMPLETED_RECONCILIATION")
    kept = client.get(f"/bank-lines/{line}")
    assert (kept["part_count"], kept["net_cents"]) == (2, -10000)
    assert live_ids(client, account) == {p["id"] for p in parts}


def _lines(client, **params) -> list[str]:
    return [row["id"] for row in client.get("/bank-lines", params=params)["items"]]


def _lines_counted(client, **params) -> int:
    return client.get("/bank-lines/count", params=params)["count"]


def _every_page(client, **params) -> list[list[dict]]:
    pages, after = [], None
    while True:
        page = client.get("/bank-lines", params={**params, **({"after": after} if after else {})})
        pages.append(page["items"])
        after = page["next_cursor"]
        if after is None:
            return pages


def test_the_line_list_and_its_count(client, scratch):
    """`GET /bank-lines`: one row per live line, each exactly the line read by id,
    newest first; filters on whole lines; `limit` counts lines, so a page never
    cuts a split line; a cursor is bound to this list and its filters; and
    `GET /bank-lines/count` counts what the list's pages hold
    (contract: GET /v1/bank-lines) (contract: GET /v1/bank-lines/count)."""
    both = scratch.account("PEN", "USD")
    elsewhere = scratch.account()
    draft = scratch.statement(both, *APRIL, "PEN", "USD")["id"]
    older = scratch.line(both, "2026-04-19", -1500)
    split_line = scratch.line(both, "2026-04-20", -6000, -4000)
    dollars = scratch.line(both, "2026-04-21", -700, currency="USD")
    newer = scratch.line(both, "2026-04-22", 2500)
    other = scratch.line(elsewhere, "2026-04-20", -300)
    order = [newer, dollars, split_line, older]
    split_parts = client.get(f"/bank-lines/{split_line}")["parts"]

    # One row per line, newest first, each exactly `GET /bank-lines/{id}`.
    body = client.get("/bank-lines", params={"account_id": both})
    assert set(body) == {"items", "limit", "next_cursor"}
    assert (body["limit"], body["next_cursor"]) == (50, None)
    assert [row["id"] for row in body["items"]] == order
    for row in body["items"]:
        assert row == client.get(f"/bank-lines/{row['id']}")
        assert row["account_id"] == both
        assert row["currency_code"] == ("USD" if row["id"] == dollars else "PEN")
        for part in row["parts"]:
            assert (part["account_id"], part["currency_code"]) == (both, row["currency_code"])
    assert _lines_counted(client, account_id=both) == 4
    assert client.get("/transactions/count", params={"account_id": both})["count"] == 5

    # `?account_id=` lists every currency of the account; `?currency_code=` narrows it,
    # and alone lists that currency on every account.
    assert _lines(client, account_id=both, currency_code="USD") == [dollars]
    assert _lines(client, account_id=both, currency_code="PEN") == [newer, split_line, older]
    assert _lines(client, account_id=elsewhere) == [other]
    assert _lines(client, account_id=elsewhere, currency_code="USD") == []
    for params, expected in (
        ({"account_id": both, "currency_code": "USD"}, 1),
        ({"account_id": both, "currency_code": "PEN"}, 3),
        ({"account_id": elsewhere, "currency_code": "USD"}, 0),
    ):
        assert _lines_counted(client, **params) == expected, params
    for code, mine in (("USD", {dollars}), ("PEN", {newer, split_line, older, other})):
        pages = _every_page(client, currency_code=code, limit=200)
        listed = [row for page in pages for row in page]
        assert {row["currency_code"] for row in listed} == {code}
        assert mine <= {row["id"] for row in listed}
        assert len(listed) == _lines_counted(client, currency_code=code)
    # An id naming no account, and an account's per-currency listing, never `404`.
    unknown = str(uuid4())
    assert _lines(client, account_id=unknown) == []
    assert _lines_counted(client, account_id=unknown) == 0
    # A code that is not supported is refused, never an empty list.
    for path in ("/bank-lines", "/bank-lines/count"):
        for params in ({"currency_code": "ZZZ"}, {"account_id": both, "currency_code": "ZZZ"}):
            err = refused(lambda path=path, params=params: client.get(path, params=params))
            assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "UNSUPPORTED_VALUE")
        err = refused(lambda path=path: client.get(path, params={"account_id": "not-a-uuid"}))
        assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "INVALID_FORMAT")

    # Paging counts lines: the split line is whole on its page.
    for limit in (1, 2):
        pages = _every_page(client, account_id=both, limit=limit)
        assert all(len(page) <= limit for page in pages)
        assert [row["id"] for page in pages for row in page] == order
        assert sum(len(page) for page in pages) == _lines_counted(client, account_id=both)
        (whole,) = [row for page in pages for row in page if row["id"] == split_line]
        assert {p["id"] for p in whole["parts"]} == {p["id"] for p in split_parts}
    # `limit` is not part of the cursor's binding.
    first = client.get("/bank-lines", params={"account_id": both, "limit": 1})
    rest = client.get(
        "/bank-lines", params={"account_id": both, "limit": 5, "after": first["next_cursor"]}
    )
    assert [row["id"] for row in rest["items"]] == order[1:]

    # Filters apply to whole lines, and the count reads them identically.
    scratch.assign(split_parts[1]["id"], draft)
    cases = [
        ({"statement_id": draft}, [split_line]),
        ({"account_id": both, "unreconciled": "true"}, [newer, dollars, older]),
        (
            {"account_id": both, "date_from": "2026-04-20", "date_to": "2026-04-20"},
            [split_line],
        ),
        ({"account_id": both, "date_from": "2026-04-21"}, order[:2]),
        ({"account_id": both, "date_to": "2026-04-20"}, order[2:]),
        ({"account_id": both, "currency_code": "USD", "unreconciled": "true"}, [dollars]),
    ]
    for params, expected in cases:
        assert _lines(client, **params) == expected, params
        assert _lines_counted(client, **params) == len(expected), params
    (assigned,) = client.get("/bank-lines", params={"statement_id": draft})["items"]
    assert assigned["part_count"] == 2 and assigned["net_cents"] == -10000

    # The refusals the list and the count share.
    for path in ("/bank-lines", "/bank-lines/count"):
        err = refused(
            lambda path=path: client.get(
                path, params={"statement_id": draft, "unreconciled": "true"}
            )
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "unreconciled", "CONFLICTING_PARAMETERS")
        for param, value in [
            ("search", "split"),
            ("category_id", str(uuid4())),
            ("hashtag_id", str(uuid4())),
            ("bank_line_id", split_line),
            ("debit_as_negative", "true"),
        ]:
            err = refused(
                lambda path=path, param=param, value=value: client.get(path, params={param: value})
            )
            assert_refusal(err, 422, "VALIDATION_ERROR", param, "UNKNOWN_PARAMETER")
    err = refused(lambda: client.get("/bank-lines", params={"offset": 1}))
    assert_refusal(err, 422, "VALIDATION_ERROR", "offset", "RETIRED_PARAMETER")
    for param, value in [("limit", 1), ("after", first["next_cursor"]), ("sort", "date_asc")]:
        err = refused(
            lambda param=param, value=value: client.get("/bank-lines/count", params={param: value})
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", param, "UNKNOWN_PARAMETER")

    # A cursor is bound to this list and to its filters.
    foreign = client.get("/transactions", params={"account_id": both, "limit": 1})
    assert foreign["next_cursor"]
    bound = [
        ({"account_id": both, "after": foreign["next_cursor"]}),
        ({"account_id": both, "unreconciled": "true", "after": first["next_cursor"]}),
        ({"after": "not-a-cursor"}),
    ]
    for params in bound:
        err = refused(lambda params=params: client.get("/bank-lines", params=params))
        assert_refusal(err, 422, "VALIDATION_ERROR", "after", "INVALID_CURSOR")


def _review(client, statement: str) -> list[str]:
    """The statement's review list, in the one order it is read in."""
    return _lines(client, unassigned_in_period_of=statement, sort="statement")


def test_the_review_list_reads_every_currency_of_the_account_before_and_after_the_close(
    client, scratch
):
    """`?unassigned_in_period_of=` is the statement's review list: the lines in no statement
    dated from the previous statement's last day to the statement's last day, in every
    currency of its account, so a dollar line in no statement dated on a soles-only
    statement's days is listed beside the soles line; oldest first, whatever the
    currency (a dollar line dated before a soles line comes first), and the count agrees. The
    previous statement's last day is on both lists, and an `@Opening` seed is never
    listed. On a draft it is the lines a close sent now would flag; after the close (the soles
    balance's and `not_covered`'s `review_lines`) it lists the same lines. A line is assigned
    only into a draft, so the statement is reverted to show a line dropping out once
    assigned (contract: GET /v1/bank-lines, "The rule, on every currency of the statement's
    account") (contract: GET /v1/bank-lines/count)."""
    account = scratch.account("PEN", "USD")
    march = scratch.statement(account, *MARCH, balances=_pen(-1000))["id"]
    inside = scratch.row(account, "2026-03-12", -1000)
    scratch.assign(inside["id"], march)
    pen_loose = scratch.row(account, "2026-03-20", -200)["bank_line_id"]
    scratch.opening_balance(account, "2026-03-02", "USD")
    usd_loose = scratch.row(account, "2026-03-15", -300, "USD")["bank_line_id"]
    edge = scratch.row(account, "2026-03-31", -100, "USD")["bank_line_id"]
    scratch.row(account, "2026-02-10", -400)  # before March's days, with no statement before it
    april_line = scratch.row(account, "2026-04-05", -500, "USD")["bank_line_id"]

    # A draft: the lines oldest first across the currencies; the assigned line, the earlier
    # one and the opening balance left out.
    expected = [usd_loose, pen_loose, edge]
    assert _review(client, march) == expected
    assert _lines_counted(client, unassigned_in_period_of=march) == 3
    listed = client.get(
        "/bank-lines", params={"unassigned_in_period_of": march, "sort": "statement"}
    )["items"]
    for row in listed:
        assert row == client.get(f"/bank-lines/{row['id']}")
        assert row["account_id"] == account
    assert [row["currency_code"] for row in listed] == ["USD", "PEN", "USD"]

    # The next statement's list starts on March's last day.
    # (the dollars are held at its start, so it holds their balances too)
    april = scratch.statement(
        account,
        *APRIL,
        balances=[
            *_pen(0),
            {
                "currency_code": "USD",
                "beginning_balance_cents": -400,
                "ending_balance_cents": -400,
            },
        ],
    )["id"]
    assert _review(client, april) == [edge, april_line]
    assert _lines_counted(client, unassigned_in_period_of=april) == 2

    # The close flags the same lines: the soles balance's and `not_covered`'s review lines.
    done = client.post(f"/statements/{march}/complete")
    (dollars,) = done["not_covered"]
    flagged = [*balance_of(done, "PEN")["review_lines"], *dollars["review_lines"]]
    assert sorted(flagged) == sorted(expected)
    assert (balance_of(done, "PEN")["review_lines"], dollars["review_lines"]) == (
        [pen_loose],
        [usd_loose, edge],
    )
    assert _review(client, march) == expected
    assert _lines_counted(client, unassigned_in_period_of=march) == 3

    # A line assigned to a statement drops out of the list (only a draft takes a line).
    client.post(f"/statements/{march}/revert")
    scratch.assign(client.get(f"/bank-lines/{pen_loose}")["parts"][0]["id"], march)
    assert _review(client, march) == [usd_loose, edge]
    assert _lines_counted(client, unassigned_in_period_of=march) == 2


def test_the_flagged_screens_own_reads_list_the_close_flagged_lines(client, target, scratch):
    """The flagged lines' screen counts the review list with `count_bank_lines(review_of=)`
    and lists every page of it with `_fetch_all_lines(review_of=, sort="statement")`, the
    reads the statement screen and the upload's result count with too. On an account of
    two currencies the count is the list's length on a draft, and after the close the list
    is the draft's, oldest first across the currencies: each currency's `review_lines`
    is that list's lines in that currency, in its order
    (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it")
    (contract: POST /v1/statements/{statement_id}/complete, "`review_lines`")."""
    from expense.tui.screens.reconciliations import _fetch_all_lines

    def screen_reads(statement: str) -> tuple[list[str], int]:
        count = count_bank_lines(target, review_of=statement)
        lines = _fetch_all_lines(target, review_of=statement, sort="statement")
        return [line["id"] for line in lines], count

    account = scratch.account("PEN", "USD")
    march = scratch.statement(account, *MARCH, balances=_pen(-1000))["id"]
    scratch.assign(scratch.row(account, "2026-03-12", -1000)["id"], march)
    pen_loose = scratch.row(account, "2026-03-20", -200)["bank_line_id"]
    scratch.opening_balance(account, "2026-03-02", "USD")
    usd_loose = scratch.row(account, "2026-03-15", -300, "USD")["bank_line_id"]
    edge = scratch.row(account, "2026-03-31", -100, "USD")["bank_line_id"]

    listed, count = screen_reads(march)
    assert listed == [usd_loose, pen_loose, edge]
    assert count == len(listed)

    done = client.post(f"/statements/{march}/complete")
    (dollars,) = done["not_covered"]
    soles = balance_of(done, "PEN")["review_lines"]
    assert (soles, dollars["review_lines"]) == ([pen_loose], [usd_loose, edge])
    listed, count = screen_reads(march)
    assert listed == [usd_loose, pen_loose, edge]
    assert count == len(listed)
    for review in (soles, dollars["review_lines"]):
        assert [line for line in listed if line in review] == review


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("account_id", str(uuid4())),
        ("currency_code", "PEN"),
        ("ids", str(uuid4())),
        ("statement_id", str(uuid4())),
        ("unreconciled", "true"),
        ("date_from", "2026-03-01"),
        ("date_to", "2026-03-31"),
    ],
)
def test_the_review_list_is_taken_alone(client, scratch, param, value):
    """`?unassigned_in_period_of=` sets the lines, the accounts, the days and the assignment
    itself, so beside `account_id`, `currency_code`, `ids`, `statement_id`, `unreconciled`,
    `date_from` or `date_to` it is `422` on `unassigned_in_period_of`
    (`CONFLICTING_PARAMETERS`), on the list and on the count
    (contract: GET /v1/bank-lines, "Taken alone")."""
    account = scratch.account("PEN", "USD")
    statement = scratch.statement(account, *MARCH, "PEN")["id"]
    for path in ("/bank-lines", "/bank-lines/count"):
        params = {"unassigned_in_period_of": statement, param: value}
        if path == "/bank-lines":
            params["sort"] = "statement"
        err = refused(lambda path=path, params=params: client.get(path, params=params))
        assert_refusal(
            err, 422, "VALIDATION_ERROR", "unassigned_in_period_of", "CONFLICTING_PARAMETERS"
        )


def test_the_review_list_is_read_with_sort_statement_only(client, scratch):
    """The review list takes `sort=statement` and no other order: `date_desc`, `date_asc`
    and no `sort` (which reads as `date_desc`) are `422` on `sort`
    (`CONFLICTING_PARAMETERS`, "Must be statement with unassigned_in_period_of."), judged
    before the statement is looked up. `sort=statement` with neither a `statement_id` nor
    an `unassigned_in_period_of` is `422` on `statement_id` (`REQUIRED`); an id naming no
    live statement is `INVALID_REFERENCE` and one that is not a UUID `INVALID_FORMAT`, on
    `unassigned_in_period_of` (contract: GET /v1/bank-lines, "Read in the statement's order,
    and only in it")."""
    account = scratch.account("PEN", "USD")
    statement = scratch.statement(account, *MARCH, "PEN")["id"]
    for sort in (None, "date_desc", "date_asc"):
        for known in (statement, str(uuid4())):
            params = {"unassigned_in_period_of": known, **({"sort": sort} if sort else {})}
            err = refused(lambda params=params: client.get("/bank-lines", params=params))
            assert_refusal(err, 422, "VALIDATION_ERROR", "sort", "CONFLICTING_PARAMETERS")
            assert err.fields["sort"] == "Must be statement with unassigned_in_period_of."
    err = refused(lambda: client.get("/bank-lines", params={"sort": "statement"}))
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_id", "REQUIRED")
    gone = scratch.statement(account, "2026-04-01", "2026-04-30", "PEN")["id"]
    client.delete(f"/statements/{gone}")
    scratch.row(account, "2026-03-05", -1000)
    before = _review(client, statement), client.get(f"/statements/{statement}")
    for value, reason in (
        (str(uuid4()), "INVALID_REFERENCE"),
        (gone, "INVALID_REFERENCE"),
        ("not-a-uuid", "INVALID_FORMAT"),
    ):
        # The list is read in the statement's order; the count takes no `sort`.
        for path, extra in (("/bank-lines", {"sort": "statement"}), ("/bank-lines/count", {})):
            params = {"unassigned_in_period_of": value, **extra}
            err = refused(lambda path=path, params=params: client.get(path, params=params))
            assert_refusal(err, 422, "VALIDATION_ERROR", "unassigned_in_period_of", reason)
    err = refused(
        lambda: client.get(
            "/bank-lines/count", params={"unassigned_in_period_of": statement, "sort": "statement"}
        )
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "sort", "UNKNOWN_PARAMETER")
    # A refused read changes nothing: the statement and its list read as before.
    assert (_review(client, statement), client.get(f"/statements/{statement}")) == before


def test_a_line_group_whose_items_differ_is_line_group_fields_differ(client, scratch):
    account = scratch.account()
    date = scratch.noon("2026-04-11")
    items = [
        scratch._item(account, date, amount, "PEN", title=title, line_group="g1")
        for title, amount in (("CHARGE A", -100), ("CHARGE B", -200))
    ]
    scratch.transactions.extend(item["id"] for item in items)
    err = refused(lambda: client.post("/transactions/batch", json_body={"transactions": items}))
    assert (err.status, err.code) == (422, "VALIDATION_ERROR")
    for key in ("transactions.0.title", "transactions.1.title"):
        assert reason_on(err, key) == "LINE_GROUP_FIELDS_DIFFER"
    assert live_ids(client, account) == set()


def test_a_line_group_is_one_line_and_a_re_import_matches_it(client, scratch):
    """Items sharing a `line_group` are the parts of one line, and a later import
    matches the group by its total on its account and day
    (contract: POST /v1/transactions/batch, "Line groups")."""
    account = scratch.account()
    date = scratch.noon("2026-04-15")
    sent = [
        scratch._item(account, date, amount, "PEN", title="MERCADO GRUPO", line_group="g1")
        for amount in (-6000, -4000)
    ]
    ids = [item["id"] for item in sent]
    items = scratch._create(sent)
    assert [t["id"] for t in items] == ids
    (line,) = {t["bank_line_id"] for t in items}
    assert line

    read = client.get(f"/bank-lines/{line}")
    assert (read["net_cents"], read["part_count"]) == (-10000, 2)
    assert (read["account_id"], read["currency_code"]) == (account, "PEN")
    assert {p["id"] for p in read["parts"]} == set(ids)

    download = [CARD_HEADER, ["2026-04-15", "MERCADO GRUPO", "S/", -100]]
    dry = send_download(client, account, download, dry_run=True)
    (only,) = dry["rows"]
    assert (only["outcome"], only["rule"]) == ("matched", "same_day")
    assert only["bank_line_id"] == line
    assert (dry["counts"]["matched"], dry["counts"]["new"]) == (1, 0)
    assert live_ids(client, account) == set(ids)


def _listed(client, **params) -> list[str]:
    return [item["id"] for item in client.get("/transactions", params=params)["items"]]


def _counted(client, **params) -> int:
    return client.get("/transactions/count", params=params)["count"]


def test_bank_line_id_lists_and_counts_exactly_a_lines_parts(client, scratch):
    account = scratch.account()
    split_me = scratch.row(account, "2026-04-12", -10000, title="split line")
    alone = scratch.row(account, "2026-04-12", -2500, title="lone line")
    parts = replace_parts(client, split_me["bank_line_id"], [-6000, -4000], scratch.transactions)
    line = parts[0]["bank_line_id"]

    assert set(_listed(client, bank_line_id=line)) == {p["id"] for p in parts}
    assert _counted(client, bank_line_id=line) == 2
    assert _listed(client, bank_line_id=alone["bank_line_id"]) == [alone["id"]]
    assert _counted(client, bank_line_id=alone["bank_line_id"]) == 1

    # An id naming no line lists nothing; it is never a 404.
    unknown = str(uuid4())
    assert _listed(client, bank_line_id=unknown) == []
    assert _counted(client, bank_line_id=unknown) == 0

    for path in ("/transactions", "/transactions/count"):
        err = refused(lambda path=path: client.get(path, params={"bank_line_id": "nope"}))
        assert_refusal(err, 422, "VALIDATION_ERROR", "bank_line_id", "INVALID_FORMAT")

    # A cursor is bound to the filter it was issued under.
    page = client.get("/transactions", params={"bank_line_id": line, "limit": 1})
    assert len(page["items"]) == 1 and page["next_cursor"]
    err = refused(
        lambda: client.get(
            "/transactions",
            params={"bank_line_id": alone["bank_line_id"], "after": page["next_cursor"]},
        )
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "after", "INVALID_CURSOR")


def test_a_bank_line_reads_its_figures(client, scratch):
    """`GET /bank-lines/{id}` serves every field, always present
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"), the account and the
    currency the line is in among them. A line in no statement holds no place and reads no
    statement line: the engine builds one only for a placed line in a completed statement
    on an account with a statement code (contract: "Transactions (Ledger)", "Bank lines")."""
    account = scratch.account("PEN", "USD")
    out = scratch.row(account, "2026-04-13", -2500, title="unsplit out")
    into = scratch.row(account, "2026-04-13", 1800, "USD", title="unsplit in")
    split_me = scratch.row(account, "2026-04-13", -10000, title="to split")

    line = client.get(f"/bank-lines/{out['bank_line_id']}")
    assert set(line) == {
        "id",
        "line_code",
        "account_id",
        "currency_code",
        "operation_code",
        "statement_line",
        "statement_place",
        "net_cents",
        "part_count",
        "is_opening_balance",
        "parts",
        "edit_limits",
    }
    assert line["id"] == out["bank_line_id"]
    assert line["line_code"] == out["line_code"]
    assert (line["account_id"], line["currency_code"]) == (account, "PEN")
    assert line["operation_code"] is None
    assert (line["statement_line"], line["statement_place"]) == (None, None)
    assert (line["net_cents"], line["part_count"]) == (-2500, 1)
    # Each part is exactly the transaction read by id: unsigned, with its type.
    assert line["parts"] == [client.get(f"/transactions/{out['id']}")]
    (part,) = line["parts"]
    assert (part["amount_cents"], signed_cents(part)) == (2500, -2500)
    assert (part["account_id"], part["currency_code"]) == (account, "PEN")
    # What the Edit form pre-fills a part from.
    for key in ("amount_cents", "transaction_type", "category_id", "hashtag_ids"):
        assert key in part
    assert "description" in part

    inflow = client.get(f"/bank-lines/{into['bank_line_id']}")
    assert (inflow["net_cents"], inflow["part_count"]) == (1800, 1)
    assert (inflow["account_id"], inflow["currency_code"]) == (account, "USD")

    parts = replace_parts(client, split_me["bank_line_id"], [-6000, -4000], scratch.transactions)
    split = client.get(f"/bank-lines/{parts[0]['bank_line_id']}")
    assert (split["net_cents"], split["part_count"]) == (-10000, 2)
    assert (split["account_id"], split["currency_code"]) == (account, "PEN")
    assert split["part_count"] == len(split["parts"])
    # In the order `?bank_line_id=` lists them by default.
    assert [p["id"] for p in split["parts"]] == _listed(client, bank_line_id=split["id"])
    assert {p["id"] for p in split["parts"]} == {p["id"] for p in parts}
    assert sorted(signed_cents(p) for p in split["parts"]) == [-6000, -4000]

    err = refused(lambda: client.get(f"/bank-lines/{uuid4()}"))
    assert (err.status, err.code) == (404, "NOT_FOUND")
    err = refused(lambda: client.get("/bank-lines/not-a-uuid"))
    assert_refusal(err, 422, "VALIDATION_ERROR", "bank_line_id", "INVALID_FORMAT")


def _edit_form(cfg, line_id: str, *, no_batch: bool = False):
    """The Edit form as `⏎` opens it on the line `line_id`, its reads done:
    the reference lists and `GET /bank-lines/{id}`, whose `edit_limits` say
    what is read-only. Built off screen, so nothing it says is shown: a
    `No changes to save.` lands in its `notes`."""
    from expense.reads import load_quickadd_refs
    from expense.tui.screens.edit_form import BankLineEditFormScreen, EditFormScreen

    line = fetch_bank_line(cfg, line_id)
    if no_batch:
        form = BankLineEditFormScreen(line=line)
    else:
        form = EditFormScreen(record={**line["parts"][0], "bank_line_id": line_id})
        form._take_line(line)
    form._take_refs(load_quickadd_refs(cfg))
    form.notes = []
    form.notify = lambda message, **kw: form.notes.append(str(message))
    return form


def _form_save(client, form, written: list[str] | None = None) -> dict | None:
    """The form's one save, sent as the app sends it; None when the form has
    nothing to send. The ids of the parts it creates join `written` first."""
    request = form._submit_request()
    if request is None:
        return None
    method, path, body, _busy = request
    assert (method, path) == ("PUT", f"/bank-lines/{form._line['id']}")
    if written is not None:
        written.extend(p["id"] for p in body["parts"])
    return client.put(path, json_body=body)


def test_the_edit_form_splits_then_re_splits_through_its_own_reads(client, target, scratch):
    """The Edit form's own path, end to end, each save the one whole-line write its
    `_submit_request` builds: on a line never split its one transaction stays as part 1
    and a part added is created beside it; one `fetch_bank_line` gives the parts and
    the `net_cents` total; the parts read back change nothing, so the form sends
    nothing; a part dropped from the table is deleted and a part added is created, in
    the same write; and on a line in a completed statement, parts that miss the
    total come back keyed so the form names part 1 and part 2
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "The total")."""
    from expense.tui.widgets.parts_table import Part, flagged_parts

    account = scratch.account()
    groceries = scratch.category()
    statement = scratch.statement(account, *APRIL, balances=_pen(-10000))["id"]
    written = scratch.transactions

    def line_parts(line: str) -> list[dict]:
        return fetch_bank_line(target, line)["parts"]

    original = scratch.row(account, "2026-04-14", -10000, title="TOTTUS")
    line = original["bank_line_id"]

    form = _edit_form(target, line)
    assert [p.id for p in form._parts] == [original["id"]]
    assert form._total == -10000
    form._parts = [
        replace(form._parts[0], amount_cents=-6000, category_id=groceries, note="verduras"),
        Part(-4000),
    ]
    first = _form_save(client, form, written)
    assert first["deleted_part_ids"] == []
    (created,) = first["created_part_ids"]
    assert {p["id"]: signed_cents(p) for p in line_parts(line)} == {
        original["id"]: -6000,
        created: -4000,
    }
    assert fetch_bank_line(target, line)["net_cents"] == -10000

    # The parts as read change nothing: the form sends nothing.
    parts = line_parts(line)
    again = _edit_form(target, line)
    assert _form_save(client, again) is None
    assert again.notes == ["No changes to save."]
    reread = line_parts(line)
    assert [(p["id"], p["version"]) for p in reread] == [(p["id"], p["version"]) for p in parts]

    # One part kept at a new amount, the other dropped, a new one added.
    form = _edit_form(target, line)
    form._parts = [replace(form._parts[0], amount_cents=-7000), Part(-3000)]
    dropped = reread[1]["id"]
    last = _form_save(client, form, written)
    assert last["deleted_part_ids"] == [dropped]
    (added,) = last["created_part_ids"]
    assert {p["id"]: signed_cents(p) for p in line_parts(line)} == {
        reread[0]["id"]: -7000,
        added: -3000,
    }
    assert fetch_bank_line(target, line)["net_cents"] == -10000

    # In a completed statement the total is kept: a set that misses it names
    # part 1 and part 2, and nothing changes.
    scratch.assign(added, statement)
    client.post(f"/statements/{statement}/complete")
    before = line_parts(line)
    form = _edit_form(target, line)
    form._parts = [
        replace(p, amount_cents=a) for p, a in zip(form._parts, (-6000, -3000), strict=True)
    ]
    err = refused(lambda: _form_save(client, form))
    assert flagged_parts(err) == frozenset({0, 1})
    assert line_parts(line) == before


TOTTUS = "Tottus Jockey Plaza"
RENAMED = "Tottus — semana"


def _split_titled(client, cfg, line_id: str, title: str | None, written: list[str]):
    """The Edit form on a line never split of -100.00: its part at -60.00 and
    a new part of -40.00, with `title` typed on TITLE when one is given, saved
    as its one whole-line write. Returns the form."""
    from expense.tui.widgets.parts_table import Part

    form = _edit_form(cfg, line_id)
    if title is not None:
        form._values["title"] = title
    form._parts = [replace(form._parts[0], amount_cents=-6000), Part(-4000)]
    form._relock()
    form.answer = _form_save(client, form, written)
    return form


def test_the_edit_form_sends_the_title_beside_the_parts(client, target, scratch):
    """The Edit form's title, through its own save: a changed `title` beside
    `parts` is written onto every part, and left out every part keeps the
    line's title (contract: PUT /v1/bank-lines/{bank_line_id}, "Body")."""
    account = scratch.account()
    titled = scratch.row(account, "2026-04-15", -10000, title=TOTTUS)
    kept = scratch.row(account, "2026-04-16", -10000, title=TOTTUS)

    renamed = _split_titled(
        client, target, titled["bank_line_id"], RENAMED, scratch.transactions
    ).answer
    assert [client.get(f"/transactions/{p['id']}")["title"] for p in renamed["parts"]] == [
        RENAMED
    ] * 2
    alone = _split_titled(client, target, kept["bank_line_id"], None, scratch.transactions).answer
    assert [client.get(f"/transactions/{p['id']}")["title"] for p in alone["parts"]] == [TOTTUS] * 2


def test_a_title_on_a_line_in_a_completed_statement_is_read_only_and_never_sent(
    client, target, scratch
):
    """On a line in a completed statement the parts may be rewritten with the
    total kept, but the title is locked: the Edit form reads it read-only from the
    line's `edit_limits`, and a title set under it is never sent, so its save goes
    through, each new part joining the statement under the old title. The same
    body with the changed `title` beside it is `422` `LOCKED` on `title`, nothing
    written (contract: PUT /v1/transactions/{transaction_id}, "Field locking")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")."""
    from expense.bank_line_write import line_body

    account = scratch.account()
    statement = scratch.statement(account, *APRIL, balances=_pen(-10000))["id"]
    original = scratch.row(account, "2026-04-18", -10000, title=TOTTUS)
    line = original["bank_line_id"]
    scratch.assign(original["id"], statement)
    client.post(f"/statements/{statement}/complete")

    form = _edit_form(target, line)
    assert {"date", "title", "account"} <= form._locked
    assert form._submit_request() is None  # nothing changed yet
    split = [
        {"id": original["id"], "amount_cents": -6000},
        {"id": str(uuid4()), "amount_cents": -4000},
    ]
    refused_body = line_body(split, {"title": RENAMED})
    err = refused(lambda: client.put(f"/bank-lines/{line}", json_body=refused_body))
    assert_refusal(err, 422, "VALIDATION_ERROR", "title", "LOCKED")
    assert live_ids(client, account) == {original["id"]}
    assert client.get(f"/transactions/{original['id']}")["title"] == TOTTUS

    saved = _split_titled(client, target, line, RENAMED, scratch.transactions)
    assert "title" not in saved._line_fields()
    parts = saved.answer["parts"]
    assert live_ids(client, account) == {p["id"] for p in parts}
    for part in parts:
        read = client.get(f"/transactions/{part['id']}")
        assert (read["title"], read["statement_id"]) == (TOTTUS, statement)


def test_the_statement_screen_lists_and_ticks_lines_through_its_own_reads(client, target, scratch):
    """The statement screen's own path, end to end: a draft month's list is the
    statement's lines (`reconciliation=`, `account=`, `sort=statement`: the statement's
    order) and the account's lines in no statement inside the period (`account_id`,
    `unreconciled=true`, the period's own days, `sort=date_asc`: oldest first), both read
    by `fetch_month_lines`, the screen's own function; a purchase split 60 + 40 is one
    row of its signed total with its title, day and operation code; a line late on the
    period's last day is in it and one past it is not. A tick is one `PUT` of `statement_id`
    on the one part `line_rows` names, which moves the whole line into the statement, and
    `null` there takes it out
    (contract: GET /v1/bank-lines)
    (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment")."""
    from expense.formatting import format_short_date
    from expense.tui.screens.reconciliations import fetch_month_lines, line_rows

    account = scratch.account()
    statement = scratch.statement(account, *APRIL)
    recon = statement["id"]
    code = f"OP-{uuid4().hex[:10]}"

    def month() -> tuple[list, list, dict]:
        assigned, available = fetch_month_lines(
            target,
            recon,
            account,
            statement["date_start"],
            statement["date_end"],
            with_available=True,
        )
        return line_rows(assigned, available)

    purchase = scratch.row(account, "2026-04-11", -10000, title="FARMACIA", operation_code=code)
    late = scratch.at("2026-04-30", 23, 30)
    last_day = scratch.row_at(account, late, -4200, title="UBER *TRIP")
    after = scratch.row(account, "2026-05-01", -2500, title="TAXI")
    parts = replace_parts(client, purchase["bank_line_id"], [-6000, -4000], scratch.transactions)
    split_line = parts[0]["bank_line_id"]

    rows, checked, part_of = month()
    assert checked == []
    # lines in no statement, oldest first: the 11th, then the 30th
    assert [r[0] for r in rows] == [split_line, last_day["bank_line_id"]]
    # the day as every list shows it: the response's own day (format_short_date)
    assert rows[1][1:] == (
        format_short_date(last_day["date"]),
        "UBER *TRIP",
        None,
        -4200,
        "PEN",
        2,
        False,
    )
    assert rows[0][1:] == ("2026-04-11", "FARMACIA", code, -10000, "PEN", 1, False)
    assert part_of[split_line] in {p["id"] for p in parts}

    # Tick: one part named, the whole line in the statement.
    scratch.assign(part_of[split_line], recon)
    rows, checked, part_of = month()
    assert checked == [split_line]
    assert [r[0] for r in rows] == [split_line, last_day["bank_line_id"]]
    assert rows[0][1:] == ("2026-04-11", "FARMACIA", code, -10000, "PEN", 1, False)
    for part in parts:
        assert client.get(f"/transactions/{part['id']}")["statement_id"] == recon

    # Without the period's days, `unreconciled=true` on the account lists every
    # line in no statement, any date, oldest first (`sort=date_asc`): the ticked
    # purchase is not in it.
    no_statement = fetch_bank_lines(target, account=account, unreconciled=True, sort="date_asc")[
        "items"
    ]
    assert [line["id"] for line in no_statement] == [
        last_day["bank_line_id"],
        after["bank_line_id"],
    ]

    # Untick: `null` on the same part takes every part out.
    scratch.assign(part_of[split_line], None)
    rows, checked, _ = month()
    assert checked == []
    assert [r[0] for r in rows] == [split_line, last_day["bank_line_id"]]
    for part in parts:
        assert client.get(f"/transactions/{part['id']}")["statement_id"] is None


def test_the_no_batch_list_reads_through_its_own_reads(client, target, scratch):
    """The "no batch" list's own path: the account's lines in no statement,
    any day (`account_id`, `unreconciled=true`, no dates), read by
    `fetch_bank_lines` page by page and counted by `count_bank_lines` with the
    same filter. Oldest first (`UNFILED_SORT`); a purchase split 60 + 40 is one row of its
    signed total and title; a line ticked into a month is in neither the list
    nor the count; and the pages add up to the count
    (contract: GET /v1/bank-lines) (contract: GET /v1/bank-lines/count)."""
    from expense.tui.screens.reconciliations import UNFILED_FILTER, UNFILED_SORT, unfiled_rows

    account = scratch.account()
    statement = scratch.statement(account, *APRIL)["id"]

    def no_batch(limit: int) -> list[dict]:
        lines, after = [], None
        while True:
            body = fetch_bank_lines(
                target,
                account=account,
                after=after,
                limit=limit,
                sort=UNFILED_SORT,
                **UNFILED_FILTER,
            )
            assert len(body["items"]) <= limit
            lines.extend(body["items"])
            after = body["next_cursor"]
            if after is None:
                return lines

    old = scratch.row(account, "2026-01-03", -1500, title="OLD ONE")
    ticked = scratch.row(account, "2026-04-09", -700, title="TICKED")
    purchase = scratch.row(account, "2026-06-11", -10000, title="FARMACIA")
    new = scratch.row(account, "2026-09-02", 2500, title="NEWEST")
    parts = replace_parts(client, purchase["bank_line_id"], [-6000, -4000], scratch.transactions)
    scratch.assign(ticked["id"], statement)

    expected = [old["bank_line_id"], parts[0]["bank_line_id"], new["bank_line_id"]]
    count = count_bank_lines(target, account=account, **UNFILED_FILTER)
    assert count == 3
    for limit in (1, 2, 10):
        lines = no_batch(limit)
        assert [line["id"] for line in lines] == expected, limit
        assert len(lines) == count
    rows = unfiled_rows(no_batch(10), [])
    assert [[str(c) for c in cells] for _key, cells in rows][1] == [
        "",
        "2026-06-11",
        "FARMACIA",
        "—",
        "PEN",
        "-100.00",
    ]


def test_the_no_batch_edit_form_writes_the_line_in_one_write_and_moves_it(client, target, scratch):
    """The "no batch" Edit form's own path (`BankLineEditFormScreen`): built on
    the line `GET /bank-lines/{id}` reads, its save is one `PUT /bank-lines/{id}`
    carrying the line fields changed beside every part at its current amount,
    and the engine writes date, title and operation onto every part, while each
    part keeps its own amount (contract: PUT /v1/bank-lines/{bank_line_id}, "Body").
    An emptied operation sends `null`, which clears the line's operation code, and
    an account move carries every part with it
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")."""
    account = scratch.account()
    other = scratch.account()
    code = f"op-{uuid4().hex[:10]}"

    def save(line_id: str, **typed) -> dict:
        form = _edit_form(target, line_id, no_batch=True)
        form._values.update(typed)
        request = form._submit_request()
        assert request is not None
        _method, path, payload, _busy = request
        client.put(path, json_body=payload)
        assert payload.pop("parts") == [
            {"id": p.id, "amount_cents": p.amount_cents} for p in form._parts
        ]
        return payload

    purchase = scratch.row(account, "2026-05-06", -10000, title="FARMACIA")
    client.put(f"/transactions/{purchase['id']}", json_body={"operation_code": code})
    replace_parts(client, purchase["bank_line_id"], [-6000, -4000], scratch.transactions)
    line_id = purchase["bank_line_id"]
    before = {p["id"]: p for p in fetch_bank_line(target, line_id)["parts"]}

    sent = save(line_id, date="2026-05-08", title="FARMACIA CENTRAL", operation=f"{code}-b")
    assert set(sent) == {"date", "title", "operation_code"}
    moved = fetch_bank_line(target, line_id)
    assert moved["operation_code"] == f"{code}-b"
    assert {p["title"] for p in moved["parts"]} == {"FARMACIA CENTRAL"}
    days = {p["date"] for p in moved["parts"]}
    assert len(days) == 1 and days != {p["date"] for p in before.values()}
    # each part keeps its own amount; the total is the engine's
    assert sorted(signed_cents(p) for p in moved["parts"]) == [-6000, -4000]
    assert moved["net_cents"] == -10000
    for part in moved["parts"]:
        assert part["version"] == before[part["id"]]["version"] + 1

    assert save(line_id, operation=None) == {"operation_code": None}
    assert fetch_bank_line(target, line_id)["operation_code"] is None

    # `currency` stands in for the form's fill of `other`'s only currency (it holds PEN alone);
    # it is not sent, because the line is already in PEN
    sent = save(line_id, account=other, currency="PEN")
    assert sent == {"account_id": other, "statement_id": None}
    moved = fetch_bank_line(target, line_id)
    assert {(p["account_id"], p["currency_code"]) for p in moved["parts"]} == {(other, "PEN")}
    assert (moved["account_id"], moved["currency_code"]) == (other, "PEN")
