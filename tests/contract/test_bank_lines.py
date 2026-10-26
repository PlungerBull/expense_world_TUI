"""Contract: bank lines and their parts, rewritten by `PUT /v1/bank-lines/{bank_line_id}`.

Every transaction belongs to one bank line, and the whole-line write gives a line its
complete set of parts, keeping its identity (contract: "Transactions (Ledger)", "Bank
lines"). The Edit form, its "changes every part" note and the bank upload all stand on
rules only the engine can confirm. Pinned here:

  · new parts sent alone replace the line's one transaction on the same line, each
    taking the line's title, date and account; a re-split (60 + 40 into 70 + 30) sent
    under the parts' own ids keeps both ids, creating and deleting nothing;
  · `PUT` of `title` on one part writes it onto every part, while `amount_cents`
    and `description` change only the part named;
  · the ledger's bulk keys on parts, through the app's own `bulk_writes`:
    `category_id` and `hashtag_ids` on one part leave the other part unwritten;
    `account_id` on one part moves every part; and `b` with both parts of a
    line in a draft reconciliation selected sends the second part a body built
    before the first `PUT` moved the line, which the engine accepts;
  · a statement imported, split and imported again is every row `matched`, none
    `new`: by `operation_code`, and by `same_day` for a card row with no operation code;
  · a batch whose two items share a `line_group` makes one line of two parts,
    and a dry-run import of the bank's one row for its total is `matched` on it;
  · `?bank_line_id=` on the list and the count names exactly a line's parts; an
    id naming no line lists nothing and counts 0, a malformed one is `422`
    `INVALID_FORMAT` on `bank_line_id`, and a cursor issued under one line's
    filter is `422` `INVALID_CURSOR` on `after` under another;
  · `GET /bank-lines/{id}` reads `id`, `line_code`, `account_id`,
    `operation_code`, `statement_line`, `statement_place`, the signed
    `net_cents`, `part_count`, `is_opening_balance`, `parts` and `edit_limits`,
    each part exactly the transaction
    read by id: a line in no reconciliation reads a `null` statement line and
    place, an unsplit line is one part at its signed amount, a split 60 + 40
    reads `-10000` over two parts in the ledger's order; an unknown id is
    `404`, a malformed one `422` `INVALID_FORMAT`;
  · the Edit form's own path: a line never split keeps its one transaction as
    part 1 beside a part added, one `fetch_bank_line` reads the parts and the total
    back, the parts read change nothing so the form sends nothing, a part dropped
    and one added are deleted and created in one write, and in a completed
    reconciliation a set that misses the total names parts 1 and 2;
  · the Edit form's title: a changed `title` beside `parts` gives every part that
    title, and without it every part keeps the line's; on a line in a completed
    reconciliation the title is read-only and never sent, so the parts go through,
    and a body with a changed title is `422` `LOCKED` on `title` with nothing
    written;
  · the "no batch" Edit form: its one write carries the line fields changed beside
    every part at its amount, an emptied operation clears the code and an account
    move carries every part;
  · a line is reconciled whole: `reconciliation_id` sent on one part puts every
    part in the reconciliation, and `null` on one part takes every part out;
  · a `PUT` answers with `changed_parts`, each part whose line fields it changed
    and whether it left its reconciliation: one part of a 60 + 40 line moved out
    of a draft lists both, both left; the other part sent the account it already
    has, or a body of `category_id` alone, lists none; a one-part line lists
    itself, left only when it was assigned; a replay answers the same;
  · `DELETE /bank-lines/{id}` deletes every part in one write, after which the
    line and its parts read `404` and its `operation_code` is free; a line in a
    completed reconciliation is `409` `IN_COMPLETED_RECONCILIATION` on
    `bank_line_id`, with nothing deleted;
  · `GET /bank-lines` and its count: one row per line, each the line read by
    id, newest first; the filters on whole lines, the count agreeing with the
    list, pages counted in lines that never cut a split line in two, and a
    cursor bound to its list and its filters;
  · the reconciliation batch screen's own path: its reads of a draft month
    (the batch's lines, and the account's lines in no batch inside the period)
    list a split purchase as one row of its total, and a tick on the one part
    it names moves the whole line in and out;
  · a batch `line_group` whose items differ is `LINE_GROUP_FIELDS_DIFFER` on each
    item's field.

The whole-line write's own rules (a part kept, added and dropped in one write, the
total, the locked line fields, a kept part's hashtags, a replay) are in
test_bank_line_write.py; `edit_limits` on each kind of line, and the parts of an
opening balance's line and of an archived account's line, in
test_bank_line_edit_limits.py.

Not pinned here: `SPLIT_LINE_PARTS_DIVERGE`. No route leaves a line's parts on
different accounts or dates: a part the whole-line write creates takes the line's
account and date, a `line_group` must share them, and `PUT` writes either onto every
part (contract: "Transactions (Ledger)", "Bank lines"). Such a line comes only from a
manual database repair outside the engine, so no client test can build one; the
refusal is a safety check for that case.

Each test builds its own account and undoes what it wrote. Gating, target and the
real-ledger guard: conftest.py.
"""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense import http as http_module
from expense.config import Config
from expense.errors import EngineError
from expense.formatting import signed_cents
from tests.contract.conftest import read_signed, reason_on, replace_parts


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


def _live_ids(client, account_id: str) -> set[str]:
    listed = client.get("/transactions", params={"account_id": account_id})
    return {item["id"] for item in listed["items"]}


def test_new_parts_replace_the_line_and_a_re_split_keeps_their_ids(client, statuses):
    """One whole-line write sending only new ids replaces every part on the same line,
    each new part taking the line's title, date and account
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"). A re-split of 60 + 40 into
    70 + 30 sends both parts under their own ids: each keeps its id and its own
    category and description, and nothing is created or deleted."""
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

        # Two new parts: 200, the same line, the line's title/date/account on each.
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
        body = client.put(f"/bank-lines/{line}", json_body={"parts": parts})
        assert statuses[-1] == 200
        assert (body["id"], body["line_code"]) == (line, original["line_code"])
        assert body["created_part_ids"] == [p["id"] for p in parts]
        assert body["deleted_part_ids"] == [original["id"]]
        assert {p["id"] for p in body["parts"]} == {p["id"] for p in parts}
        by_id = {p["id"]: p for p in body["parts"]}
        first = [by_id[p["id"]] for p in parts]
        assert [read_signed(client, p["id"])["amount_cents"] for p in first] == [-6000, -4000]
        assert {p["bank_line_id"] for p in first} == {line}
        for part in first:
            assert part["title"] == "SUPERMERCADO LIMA"
            assert part["account_id"] == account
            assert datetime.fromisoformat(part["date"]) == datetime.fromisoformat(date)
        assert first[0]["category_id"] == groceries
        assert first[0]["description"] == "food"
        assert _live_ids(client, account) == {p["id"] for p in parts}
        err = _refused(lambda: client.get(f"/transactions/{original['id']}"))
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
        assert _live_ids(client, account) == {p["id"] for p in first}
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
        one, two = replace_parts(client, original["bank_line_id"], [-3000, -2000], written)

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
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def _make_hashtag(client) -> str:
    new_id = str(uuid4())
    client.post("/hashtags", json_body={"id": new_id, "name": f"contract-lines-{new_id[:8]}"})
    return new_id


def _ledger_bulk(client, parts: list[dict], payload: dict) -> list[dict]:
    """The ledger's bulk key over `parts`, selected in that order, as the app sends
    it: `bulk_writes` builds each body from the rows as the ledger last read them,
    then one `PUT` per row, in order. Returns each response."""
    from expense.tui.screens.transactions import bulk_writes

    by_id = {p["id"]: p for p in parts}
    writes = bulk_writes([p["id"] for p in parts], payload, by_id)
    return [client.put(f"/transactions/{key}", json_body=body) for key, body in writes]


def test_a_parts_category_and_hashtags_stay_its_own(client):
    """`category_id` and `hashtag_ids` are a part's own: sent on one part they
    change only it, and the other part is not written, its `version` unmoved. The
    ledger's `c` and `h` with both parts selected send one `PUT` per part, and
    each is accepted (contract: PUT /v1/transactions/{transaction_id}, "Line fields")."""
    zone = _zone(client)
    account = _make_account(client)
    groceries = _make_category(client)
    food = _make_hashtag(client)
    written: list[str] = []
    try:
        original = _post_tx(client, account, _noon(zone, 2026, 4, 8), -5000, "TOTTUS")
        written.append(original["id"])
        one, two = replace_parts(client, original["bank_line_id"], [-3000, -2000], written)
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
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/hashtags/{food}")
        _safe(client.delete, f"/categories/{groceries}")
        _safe(client.delete, f"/accounts/{account}")


def test_an_account_move_on_one_part_moves_the_whole_line(client):
    """`account_id` is a line field: sent on one part, every part moves to the
    account in that one write, the other part's `version` up by one. The ledger's
    `b` with both parts of a line in a draft reconciliation selected sends each
    part `account_id` with `reconciliation_id: null`, built from the read before
    the move: the first `PUT` moves the whole line out of the reconciliation, and
    the engine accepts the second as it is, writing no other part, the part named
    taking one more `version`
    (contract: PUT /v1/transactions/{transaction_id}, "Line fields")
    (contract: PUT /v1/transactions/{transaction_id}, "Reconciliation assignment")."""
    zone = _zone(client)
    home = _make_account(client)
    away = _make_account(client)
    recon = _make_reconciliation(client, home)
    written: list[str] = []

    def both() -> list[dict]:
        return [client.get(f"/transactions/{p['id']}") for p in (one, two)]

    try:
        original = _post_tx(client, home, _noon(zone, 2026, 4, 9), -5000, "SAGA")
        written.append(original["id"])
        one, two = replace_parts(client, original["bank_line_id"], [-3000, -2000], written)

        # `b` with both parts selected, the line in a draft reconciliation.
        client.put(f"/transactions/{one['id']}", json_body={"reconciliation_id": recon})
        loaded = both()
        assert {p["reconciliation_id"] for p in loaded} == {recon}
        first, second = _ledger_bulk(client, loaded, {"account_id": away})
        assert (first["account_id"], second["account_id"]) == (away, away)
        after = both()
        assert [(p["account_id"], p["reconciliation_id"]) for p in after] == [(away, None)] * 2
        assert after[0]["version"] == loaded[0]["version"] + 1
        assert after[1]["version"] == loaded[1]["version"] + 2
        assert _live_ids(client, home) == set()

        # `b` on one part: the whole line comes back.
        loaded = both()
        (moved,) = _ledger_bulk(client, loaded[:1], {"account_id": home})
        assert moved["account_id"] == home
        after = both()
        assert [(p["account_id"], p["reconciliation_id"]) for p in after] == [(home, None)] * 2
        assert after[1]["version"] == loaded[1]["version"] + 1
        assert _live_ids(client, away) == set()
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/accounts/{away}")
        _safe(client.delete, f"/accounts/{home}")


@pytest.mark.parametrize(
    ("code", "rule"),
    [(f"OP-{uuid4().hex[:10]}", "operation_code"), (None, "same_day")],
    ids=["with-operation-code", "card-row-no-operation-code"],
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

        parts = replace_parts(client, line, [-5000, -3000], written)
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


def _make_reconciliation(client, account_id: str, *, ending: int | None = None) -> str:
    """A draft reconciliation for April 2026 on `account_id`, from a zero balance."""
    new_id = str(uuid4())
    body = {
        "id": new_id,
        "account_id": account_id,
        "name": f"contract-lines-{new_id[:8]}",
        "date_start": "2026-04-01",
        "date_end": "2026-04-30",
        "beginning_balance_cents": 0,
    }
    if ending is not None:
        body["ending_balance_cents"] = ending
    client.post("/reconciliations", json_body=body)
    return new_id


def _reconciliation_of(client, tx_id: str) -> object:
    return client.get(f"/transactions/{tx_id}")["reconciliation_id"]


def test_reconciling_one_part_assigns_and_unassigns_the_whole_line(client):
    """`reconciliation_id` is a line field: sent on one part, it puts every live
    part of the line in the reconciliation, and `null` on one part takes every
    part out (contract: PUT /v1/transactions/{transaction_id}, "Line fields")
    (contract: PUT /v1/transactions/{transaction_id}, "Reconciliation assignment")."""
    zone = _zone(client)
    account = _make_account(client)
    recon = _make_reconciliation(client, account)
    written: list[str] = []
    try:
        original = _post_tx(client, account, _noon(zone, 2026, 4, 10), -10000, "line")
        written.append(original["id"])
        one, two = replace_parts(client, original["bank_line_id"], [-6000, -4000], written)

        client.put(f"/transactions/{one['id']}", json_body={"reconciliation_id": recon})
        assert [_reconciliation_of(client, p["id"]) for p in (one, two)] == [recon, recon]
        assert client.get(f"/transactions/{two['id']}")["version"] == two["version"] + 1
        listed = client.get("/transactions", params={"reconciliation_id": recon})["items"]
        assert {t["id"] for t in listed} == {one["id"], two["id"]}

        client.put(f"/transactions/{two['id']}", json_body={"reconciliation_id": None})
        assert [_reconciliation_of(client, p["id"]) for p in (one, two)] == [None, None]
        assert client.get("/transactions", params={"reconciliation_id": recon})["items"] == []
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/accounts/{account}")


def _changed(answer: dict) -> list[tuple[str, bool]]:
    """`changed_parts` of a `PUT /transactions/{id}` answer as `(id, left_reconciliation)`."""
    return [(e["transaction"]["id"], e["left_reconciliation"]) for e in answer["changed_parts"]]


def _assert_parts_read_back(client, answer: dict, named: str) -> None:
    """Each `changed_parts` entry is its part exactly as `GET /transactions/{id}` reads it
    after the write, and the named part's entry repeats the top-level transaction."""
    top = {k: v for k, v in answer.items() if k != "changed_parts"}
    for entry in answer["changed_parts"]:
        part = entry["transaction"]
        assert part == client.get(f"/transactions/{part['id']}")
        if part["id"] == named:
            assert part == top


def test_a_move_answers_with_every_part_it_changed(client, monkeypatch):
    """`changed_parts` lists each part of the line whose line fields the write changed,
    `left_reconciliation` on each, in the order `?bank_line_id=` lists the line. One part
    of a 60 + 40 line in a draft reconciliation moved with `reconciliation_id: null`
    lists both parts, both left; the other part sent the account it already has lists
    none; a body changing only `category_id` lists none while `version` still bumps;
    and a replay under the same key answers exactly as the first send
    (contract: PUT /v1/transactions/{transaction_id}, "Response")."""
    zone = _zone(client)
    home = _make_account(client)
    away = _make_account(client)
    groceries = _make_category(client)
    recon = _make_reconciliation(client, home)
    written: list[str] = []
    try:
        original = _post_tx(client, home, _noon(zone, 2026, 4, 11), -10000, "FARMACIA")
        written.append(original["id"])
        one, two = replace_parts(client, original["bank_line_id"], [-6000, -4000], written)
        listed = client.get("/transactions", params={"bank_line_id": original["bank_line_id"]})
        order = [t["id"] for t in listed["items"]]
        assert sorted(order) == sorted([one["id"], two["id"]])
        client.put(f"/transactions/{one['id']}", json_body={"reconciliation_id": recon})

        # One part moved out of the draft: both parts listed, both left it.
        moved = client.put(
            f"/transactions/{one['id']}",
            json_body={"account_id": away, "reconciliation_id": None},
        )
        assert _changed(moved) == [(tx_id, True) for tx_id in order]
        _assert_parts_read_back(client, moved, one["id"])

        # The other part sent the account the line already has: nothing changed.
        again = client.put(
            f"/transactions/{two['id']}",
            json_body={"account_id": away, "reconciliation_id": None},
        )
        assert again["changed_parts"] == []

        # Only the category: no line field changed, but the part's version bumps.
        before = client.get(f"/transactions/{one['id']}")["version"]
        recategorised = client.put(
            f"/transactions/{one['id']}", json_body={"category_id": groceries}
        )
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
    finally:
        monkeypatch.undo()
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/categories/{groceries}")
        _safe(client.delete, f"/accounts/{away}")
        _safe(client.delete, f"/accounts/{home}")


@pytest.mark.parametrize("assigned", [True, False], ids=["in-a-draft", "in-none"])
def test_a_one_part_line_moved_lists_itself(client, assigned):
    """A line of one part moved to another account lists that part alone, flagged
    `left_reconciliation` only when it was in a reconciliation before the write
    (contract: PUT /v1/transactions/{transaction_id}, "Response")."""
    zone = _zone(client)
    home = _make_account(client)
    away = _make_account(client)
    recon = _make_reconciliation(client, home)
    written: list[str] = []
    try:
        tx = _post_tx(client, home, _noon(zone, 2026, 4, 12), -4200, "UBER *TRIP")
        written.append(tx["id"])
        if assigned:
            client.put(f"/transactions/{tx['id']}", json_body={"reconciliation_id": recon})

        moved = client.put(
            f"/transactions/{tx['id']}",
            json_body={"account_id": away, "reconciliation_id": None},
        )
        assert _changed(moved) == [(tx["id"], assigned)]
        _assert_parts_read_back(client, moved, tx["id"])
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/accounts/{away}")
        _safe(client.delete, f"/accounts/{home}")


def test_deleting_a_bank_line_deletes_every_part(client, statuses):
    """One `DELETE /bank-lines/{id}` soft-deletes every live part, answers each
    part as `DELETE /transactions/{id}` would in the ledger's order, and the line
    goes with them: it and its parts read `404`, and its `operation_code` is free
    on the account (contract: DELETE /v1/bank-lines/{bank_line_id})."""
    zone = _zone(client)
    account = _make_account(client)
    written: list[str] = []
    code = f"OP-{uuid4().hex[:10]}"
    try:
        original = client.post(
            "/transactions",
            json_body={
                "id": str(uuid4()),
                "title": "TOTTUS",
                "amount_cents": -10000,
                "account_id": account,
                "date": _noon(zone, 2026, 4, 16),
                "operation_code": code,
            },
        )
        written.append(original["id"])
        line = original["bank_line_id"]
        parts = replace_parts(client, original["bank_line_id"], [-6000, -4000], written)
        order = [p["id"] for p in client.get(f"/bank-lines/{line}")["parts"]]

        gone = client.delete(f"/bank-lines/{line}")
        assert statuses[-1] == 200
        assert set(gone) == {"parts"}
        assert [p["id"] for p in gone["parts"]] == order
        assert {p["id"] for p in gone["parts"]} == {p["id"] for p in parts}
        for part in gone["parts"]:
            assert part["deleted_at"] is not None
            assert part["hashtag_ids"] == []

        err = _refused(lambda: client.get(f"/bank-lines/{line}"))
        assert (err.status, err.code) == (404, "NOT_FOUND")
        for part in parts:
            err = _refused(lambda part=part: client.get(f"/transactions/{part['id']}"))
            assert err.status == 404
        assert _live_ids(client, account) == set()
        err = _refused(lambda: client.delete(f"/bank-lines/{line}"))
        assert (err.status, err.code) == (404, "NOT_FOUND")
        err = _refused(lambda: client.delete("/bank-lines/not-a-uuid"))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "bank_line_id") == "INVALID_FORMAT"

        # The operation code is free: a new line on the account takes it.
        again = _post_tx(client, account, _noon(zone, 2026, 4, 16), -500, "again")
        written.append(again["id"])
        client.put(f"/transactions/{again['id']}", json_body={"operation_code": code})
        assert client.get(f"/transactions/{again['id']}")["operation_code"] == code
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_line_in_a_completed_reconciliation_is_not_deleted(client):
    """A line whose parts are in a completed reconciliation is `409` on
    `bank_line_id` (`IN_COMPLETED_RECONCILIATION`), judged before anything
    changes: every part stays (contract: DELETE /v1/bank-lines/{bank_line_id})."""
    zone = _zone(client)
    account = _make_account(client)
    recon = _make_reconciliation(client, account, ending=-10000)
    written: list[str] = []
    try:
        original = _post_tx(client, account, _noon(zone, 2026, 4, 17), -10000, "held")
        written.append(original["id"])
        line = original["bank_line_id"]
        parts = replace_parts(client, original["bank_line_id"], [-6000, -4000], written)
        client.put(f"/transactions/{parts[0]['id']}", json_body={"reconciliation_id": recon})
        client.post(f"/reconciliations/{recon}/complete")

        err = _refused(lambda: client.delete(f"/bank-lines/{line}"))
        assert (err.status, err.code) == (409, "CONFLICT")
        assert reason_on(err, "bank_line_id") == "IN_COMPLETED_RECONCILIATION"
        kept = client.get(f"/bank-lines/{line}")
        assert (kept["part_count"], kept["net_cents"]) == (2, -10000)
        assert _live_ids(client, account) == {p["id"] for p in parts}
    finally:
        _safe(client.post, f"/reconciliations/{recon}/revert")
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/accounts/{account}")


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


def test_the_line_list_and_its_count(client):
    """`GET /bank-lines`: one row per live line, each exactly the line read by id,
    newest first; filters on whole lines; `limit` counts lines, so a page never
    cuts a split line; a cursor is bound to this list and its filters; and
    `GET /bank-lines/count` counts what the list's pages hold
    (contract: GET /v1/bank-lines) (contract: GET /v1/bank-lines/count)."""
    zone = _zone(client)
    account = _make_account(client)
    recon = _make_reconciliation(client, account)
    written: list[str] = []
    try:
        older = _post_tx(client, account, _noon(zone, 2026, 4, 19), -1500, "older")
        split_me = _post_tx(client, account, _noon(zone, 2026, 4, 20), -10000, "split")
        newer = _post_tx(client, account, _noon(zone, 2026, 4, 21), 2500, "newer")
        written.extend([older["id"], split_me["id"], newer["id"]])
        parts = replace_parts(client, split_me["bank_line_id"], [-6000, -4000], written)
        split_line = parts[0]["bank_line_id"]
        order = [newer["bank_line_id"], split_line, older["bank_line_id"]]

        # One row per line, newest first, each exactly `GET /bank-lines/{id}`.
        body = client.get("/bank-lines", params={"account_id": account})
        assert set(body) == {"items", "limit", "next_cursor"}
        assert (body["limit"], body["next_cursor"]) == (50, None)
        assert [row["id"] for row in body["items"]] == order
        for row in body["items"]:
            assert row == client.get(f"/bank-lines/{row['id']}")
        assert _lines_counted(client, account_id=account) == 3
        assert client.get("/transactions/count", params={"account_id": account})["count"] == 4

        # Paging counts lines: the split line is whole on its page.
        for limit in (1, 2):
            pages = _every_page(client, account_id=account, limit=limit)
            assert all(len(page) <= limit for page in pages)
            assert [row["id"] for page in pages for row in page] == order
            assert sum(len(page) for page in pages) == _lines_counted(client, account_id=account)
            (whole,) = [row for page in pages for row in page if row["id"] == split_line]
            assert {p["id"] for p in whole["parts"]} == {p["id"] for p in parts}
        # `limit` is not part of the cursor's binding.
        first = client.get("/bank-lines", params={"account_id": account, "limit": 1})
        rest = client.get(
            "/bank-lines",
            params={"account_id": account, "limit": 5, "after": first["next_cursor"]},
        )
        assert [row["id"] for row in rest["items"]] == order[1:]

        # Filters apply to whole lines, and the count reads them identically.
        client.put(f"/transactions/{parts[1]['id']}", json_body={"reconciliation_id": recon})
        cases = [
            ({"reconciliation_id": recon}, [split_line]),
            ({"account_id": account, "unreconciled": "true"}, [order[0], order[2]]),
            (
                {"account_id": account, "date_from": "2026-04-20", "date_to": "2026-04-20"},
                [split_line],
            ),
            ({"account_id": account, "date_from": "2026-04-20"}, order[:2]),
            ({"account_id": account, "date_to": "2026-04-20"}, order[1:]),
        ]
        for params, expected in cases:
            assert _lines(client, **params) == expected, params
            assert _lines_counted(client, **params) == len(expected), params
        (assigned,) = client.get("/bank-lines", params={"reconciliation_id": recon})["items"]
        assert assigned["part_count"] == 2 and assigned["net_cents"] == -10000

        # The refusals the list and the count share.
        for path in ("/bank-lines", "/bank-lines/count"):
            err = _refused(
                lambda path=path: client.get(
                    path, params={"reconciliation_id": recon, "unreconciled": "true"}
                )
            )
            assert (err.status, err.code) == (422, "VALIDATION_ERROR")
            assert reason_on(err, "unreconciled") == "CONFLICTING_PARAMETERS"
            for param, value in [
                ("search", "split"),
                ("category_id", str(uuid4())),
                ("hashtag_id", str(uuid4())),
                ("bank_line_id", split_line),
                ("debit_as_negative", "true"),
            ]:
                err = _refused(
                    lambda path=path, param=param, value=value: client.get(
                        path, params={param: value}
                    )
                )
                assert err.status == 422, (path, param)
                assert reason_on(err, param) == "UNKNOWN_PARAMETER", (path, param)
        err = _refused(lambda: client.get("/bank-lines", params={"offset": 1}))
        assert err.status == 422
        for param, value in [("limit", 1), ("after", first["next_cursor"])]:
            err = _refused(
                lambda param=param, value=value: client.get(
                    "/bank-lines/count", params={param: value}
                )
            )
            assert err.status == 422, param

        # A cursor is bound to this list and to its filters.
        foreign = client.get("/transactions", params={"account_id": account, "limit": 1})
        assert foreign["next_cursor"]
        bound = [
            ({"account_id": account, "after": foreign["next_cursor"]}),
            ({"account_id": account, "unreconciled": "true", "after": first["next_cursor"]}),
            ({"after": "not-a-cursor"}),
        ]
        for params in bound:
            err = _refused(lambda params=params: client.get("/bank-lines", params=params))
            assert (err.status, err.code) == (422, "VALIDATION_ERROR"), params
            assert reason_on(err, "after") == "INVALID_CURSOR", params
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
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


def test_a_line_group_is_one_line_and_a_re_import_matches_it(client):
    """Items sharing a `line_group` are the parts of one line, and a later import
    matches the group by its total on its account and day
    (contract: POST /v1/transactions/batch, "Line groups")."""
    zone = _zone(client)
    account = _make_account(client)
    ids = [str(uuid4()), str(uuid4())]
    date = _noon(zone, 2026, 4, 15)
    try:
        created = client.post(
            "/transactions/batch",
            json_body={
                "transactions": [
                    {
                        "id": tx_id,
                        "title": "MERCADO GRUPO",
                        "amount_cents": amount,
                        "account_id": account,
                        "date": date,
                        "line_group": "g1",
                    }
                    for tx_id, amount in zip(ids, (-6000, -4000), strict=True)
                ]
            },
        )
        items = created["created"]
        assert [t["id"] for t in items] == ids
        (line,) = {t["bank_line_id"] for t in items}
        assert line

        read = client.get(f"/bank-lines/{line}")
        assert (read["net_cents"], read["part_count"]) == (-10000, 2)
        assert {p["id"] for p in read["parts"]} == set(ids)

        dry = client.post(
            "/transactions/import",
            json_body={
                "dry_run": True,
                "rows": [
                    {
                        "id": str(uuid4()),
                        "account_id": account,
                        "date": "2026-04-15",
                        "amount_cents": -10000,
                        "title": "MERCADO GRUPO",
                    }
                ],
            },
        )
        (only,) = dry["rows"]
        assert (only["outcome"], only["rule"]) == ("matched", "same_day")
        assert only["bank_line_id"] == line
        assert (dry["counts"]["matched"], dry["counts"]["new"]) == (1, 0)
        assert _live_ids(client, account) == set(ids)
    finally:
        for tx_id in ids:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def _listed(client, **params) -> list[str]:
    return [item["id"] for item in client.get("/transactions", params=params)["items"]]


def _counted(client, **params) -> int:
    return client.get("/transactions/count", params=params)["count"]


def test_bank_line_id_lists_and_counts_exactly_a_lines_parts(client):
    zone = _zone(client)
    account = _make_account(client)
    written: list[str] = []
    try:
        split_me = _post_tx(client, account, _noon(zone, 2026, 4, 12), -10000, "split line")
        alone = _post_tx(client, account, _noon(zone, 2026, 4, 12), -2500, "lone line")
        written.extend([split_me["id"], alone["id"]])
        parts = replace_parts(client, split_me["bank_line_id"], [-6000, -4000], written)
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
            err = _refused(lambda path=path: client.get(path, params={"bank_line_id": "nope"}))
            assert (err.status, err.code) == (422, "VALIDATION_ERROR")
            assert reason_on(err, "bank_line_id") == "INVALID_FORMAT"

        # A cursor is bound to the filter it was issued under.
        page = client.get("/transactions", params={"bank_line_id": line, "limit": 1})
        assert len(page["items"]) == 1 and page["next_cursor"]
        err = _refused(
            lambda: client.get(
                "/transactions",
                params={"bank_line_id": alone["bank_line_id"], "after": page["next_cursor"]},
            )
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "after") == "INVALID_CURSOR"
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_bank_line_reads_its_figures(client):
    """`GET /bank-lines/{id}` serves every field, always present
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). A line in no
    reconciliation holds no place and reads no statement line: the engine builds one
    only for a placed line in a completed reconciliation on an account with a
    statement code (contract: "Transactions (Ledger)", "Bank lines")."""
    zone = _zone(client)
    account = _make_account(client)
    written: list[str] = []
    try:
        out = _post_tx(client, account, _noon(zone, 2026, 4, 13), -2500, "unsplit out")
        into = _post_tx(client, account, _noon(zone, 2026, 4, 13), 1800, "unsplit in")
        split_me = _post_tx(client, account, _noon(zone, 2026, 4, 13), -10000, "to split")
        written.extend([out["id"], into["id"], split_me["id"]])

        line = client.get(f"/bank-lines/{out['bank_line_id']}")
        assert set(line) == {
            "id",
            "line_code",
            "account_id",
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
        assert line["account_id"] == account
        assert line["operation_code"] is None
        assert (line["statement_line"], line["statement_place"]) == (None, None)
        assert (line["net_cents"], line["part_count"]) == (-2500, 1)
        # Each part is exactly the transaction read by id: unsigned, with its type.
        assert line["parts"] == [client.get(f"/transactions/{out['id']}")]
        (part,) = line["parts"]
        assert (part["amount_cents"], signed_cents(part)) == (2500, -2500)
        # What the Edit form pre-fills a part from.
        for key in ("amount_cents", "transaction_type", "category_id", "hashtag_ids"):
            assert key in part
        assert "description" in part

        inflow = client.get(f"/bank-lines/{into['bank_line_id']}")
        assert (inflow["net_cents"], inflow["part_count"]) == (1800, 1)

        parts = replace_parts(client, split_me["bank_line_id"], [-6000, -4000], written)
        split = client.get(f"/bank-lines/{parts[0]['bank_line_id']}")
        assert (split["net_cents"], split["part_count"]) == (-10000, 2)
        assert split["part_count"] == len(split["parts"])
        # In the order `?bank_line_id=` lists them by default.
        assert [p["id"] for p in split["parts"]] == _listed(client, bank_line_id=split["id"])
        assert {p["id"] for p in split["parts"]} == {p["id"] for p in parts}
        assert sorted(signed_cents(p) for p in split["parts"]) == [-6000, -4000]

        err = _refused(lambda: client.get(f"/bank-lines/{uuid4()}"))
        assert (err.status, err.code) == (404, "NOT_FOUND")
        err = _refused(lambda: client.get("/bank-lines/not-a-uuid"))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "bank_line_id") == "INVALID_FORMAT"
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def _edit_form(cfg, line_id: str, *, no_batch: bool = False):
    """The Edit form as `⏎` opens it on the line `line_id`, its reads done:
    the reference lists and `GET /bank-lines/{id}`, whose `edit_limits` say
    what is read-only. Built off screen, so nothing it says is shown: a
    `No changes to save.` lands in its `notes`."""
    from expense.reads import fetch_bank_line, load_quickadd_refs
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


def test_the_edit_form_splits_then_re_splits_through_its_own_reads(client):
    """The Edit form's own path, end to end, each save the one whole-line write its
    `_submit_request` builds: on a line never split its one transaction stays as part 1
    and a part added is created beside it; one `fetch_bank_line` gives the parts and
    the `net_cents` total; the parts read back change nothing, so the form sends
    nothing; a part dropped from the table is deleted and a part added is created, in
    the same write; and on a line in a completed reconciliation, parts that miss the
    total come back keyed so the form names part 1 and part 2
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "The total")."""
    from dataclasses import replace

    from expense.reads import fetch_bank_line
    from expense.tui.widgets.parts_table import Part, flagged_parts
    from tests.contract.conftest import ENGINE_URL, PAT

    cfg = Config(engine_url=ENGINE_URL, token=PAT)
    zone = _zone(client)
    account = _make_account(client)
    groceries = _make_category(client)
    recon = _make_reconciliation(client, account, ending=-10000)
    written: list[str] = []

    def line_parts(line: str) -> list[dict]:
        return fetch_bank_line(cfg, line)["parts"]

    try:
        original = _post_tx(client, account, _noon(zone, 2026, 4, 14), -10000, "TOTTUS")
        written.append(original["id"])
        line = original["bank_line_id"]

        form = _edit_form(cfg, line)
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
        assert fetch_bank_line(cfg, line)["net_cents"] == -10000

        # The parts as read change nothing: the form sends nothing.
        parts = line_parts(line)
        again = _edit_form(cfg, line)
        assert _form_save(client, again) is None
        assert again.notes == ["No changes to save."]
        reread = line_parts(line)
        assert [(p["id"], p["version"]) for p in reread] == [(p["id"], p["version"]) for p in parts]

        # One part kept at a new amount, the other dropped, a new one added.
        form = _edit_form(cfg, line)
        form._parts = [replace(form._parts[0], amount_cents=-7000), Part(-3000)]
        dropped = reread[1]["id"]
        last = _form_save(client, form, written)
        assert last["deleted_part_ids"] == [dropped]
        (added,) = last["created_part_ids"]
        assert {p["id"]: signed_cents(p) for p in line_parts(line)} == {
            reread[0]["id"]: -7000,
            added: -3000,
        }
        assert fetch_bank_line(cfg, line)["net_cents"] == -10000

        # In a completed reconciliation the total is kept: a set that misses it names
        # part 1 and part 2, and nothing changes.
        client.put(f"/transactions/{added}", json_body={"reconciliation_id": recon})
        client.post(f"/reconciliations/{recon}/complete")
        before = line_parts(line)
        form = _edit_form(cfg, line)
        form._parts = [
            replace(p, amount_cents=a) for p, a in zip(form._parts, (-6000, -3000), strict=True)
        ]
        err = _refused(lambda: _form_save(client, form))
        assert flagged_parts(err) == frozenset({0, 1})
        assert line_parts(line) == before
    finally:
        _safe(client.post, f"/reconciliations/{recon}/revert")
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/categories/{groceries}")
        _safe(client.delete, f"/accounts/{account}")


TOTTUS = "Tottus Jockey Plaza"
RENAMED = "Tottus — semana"


def _split_titled(client, cfg, line_id: str, title: str | None, written: list[str]) -> dict:
    """The Edit form on a line never split of -100.00: its part at -60.00 and
    a new part of -40.00, with `title` typed on TITLE when one is given, saved
    as its one whole-line write. Returns the form."""
    from dataclasses import replace

    from expense.tui.widgets.parts_table import Part

    form = _edit_form(cfg, line_id)
    if title is not None:
        form._values["title"] = title
    form._parts = [replace(form._parts[0], amount_cents=-6000), Part(-4000)]
    form._relock()
    form.answer = _form_save(client, form, written)
    return form


def test_the_edit_form_sends_the_title_beside_the_parts(client):
    """The Edit form's title, through its own save: a changed `title` beside
    `parts` is written onto every part, and left out every part keeps the
    line's title (contract: PUT /v1/bank-lines/{bank_line_id}, "Body")."""
    from tests.contract.conftest import ENGINE_URL, PAT

    cfg = Config(engine_url=ENGINE_URL, token=PAT)
    zone = _zone(client)
    account = _make_account(client)
    written: list[str] = []

    try:
        titled = _post_tx(client, account, _noon(zone, 2026, 4, 15), -10000, TOTTUS)
        kept = _post_tx(client, account, _noon(zone, 2026, 4, 16), -10000, TOTTUS)
        written.extend([titled["id"], kept["id"]])

        renamed = _split_titled(client, cfg, titled["bank_line_id"], RENAMED, written).answer
        assert [client.get(f"/transactions/{p['id']}")["title"] for p in renamed["parts"]] == [
            RENAMED
        ] * 2
        alone = _split_titled(client, cfg, kept["bank_line_id"], None, written).answer
        assert [client.get(f"/transactions/{p['id']}")["title"] for p in alone["parts"]] == [
            TOTTUS
        ] * 2
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_title_on_a_line_in_a_completed_reconciliation_is_read_only_and_never_sent(client):
    """On a line in a completed reconciliation the parts may be rewritten with the
    total kept, but the title is locked: the Edit form reads it read-only from the
    line's `edit_limits`, and a title set under it is never sent, so its save goes
    through, each new part joining the reconciliation under the old title. The same
    body with the changed `title` beside it is `422` `LOCKED` on `title`, nothing
    written (contract: PUT /v1/transactions/{transaction_id}, "Field locking")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")."""
    from expense.bank_line_write import line_body
    from tests.contract.conftest import ENGINE_URL, PAT

    cfg = Config(engine_url=ENGINE_URL, token=PAT)
    zone = _zone(client)
    account = _make_account(client)
    recon = _make_reconciliation(client, account, ending=-10000)
    written: list[str] = []

    try:
        original = _post_tx(client, account, _noon(zone, 2026, 4, 18), -10000, TOTTUS)
        written.append(original["id"])
        line = original["bank_line_id"]
        client.put(f"/transactions/{original['id']}", json_body={"reconciliation_id": recon})
        client.post(f"/reconciliations/{recon}/complete")

        form = _edit_form(cfg, line)
        assert {"date", "title", "account"} <= form._locked
        assert form._submit_request() is None  # nothing changed yet
        split = [
            {"id": original["id"], "amount_cents": -6000},
            {"id": str(uuid4()), "amount_cents": -4000},
        ]
        refused_body = line_body(split, {"title": RENAMED})
        err = _refused(lambda: client.put(f"/bank-lines/{line}", json_body=refused_body))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert err.reasons == {"title": "LOCKED"}
        assert _live_ids(client, account) == {original["id"]}
        assert client.get(f"/transactions/{original['id']}")["title"] == TOTTUS

        saved = _split_titled(client, cfg, line, RENAMED, written)
        assert "title" not in saved._line_fields()
        parts = saved.answer["parts"]
        assert _live_ids(client, account) == {p["id"] for p in parts}
        for part in parts:
            read = client.get(f"/transactions/{part['id']}")
            assert (read["title"], read["reconciliation_id"]) == (TOTTUS, recon)
    finally:
        _safe(client.post, f"/reconciliations/{recon}/revert")
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/accounts/{account}")


def test_the_batch_screen_lists_and_ticks_lines_through_its_own_reads(client):
    """The reconciliation batch screen's own path, end to end: a draft month's
    list is the batch's lines (`reconciliation_id=`) and the account's lines in
    no batch inside the period (`account_id`, `unreconciled=true`, the period's
    own days), read by `_fetch_all_lines`; a purchase split 60 + 40 is one row
    of its signed total with its title, day and operation code; a line late on
    the period's last day is in it and one past it is not. A tick is one `PUT`
    of `reconciliation_id` on the one part `line_rows` names, which moves the
    whole line into the batch, and `null` there takes it out
    (contract: GET /v1/bank-lines)
    (contract: PUT /v1/transactions/{transaction_id}, "Reconciliation assignment")."""
    from expense.formatting import format_short_date
    from expense.reads import fetch_bank_lines
    from expense.tui.screens.reconciliations import _fetch_all_lines, line_rows
    from tests.contract.conftest import ENGINE_URL, PAT

    cfg = Config(engine_url=ENGINE_URL, token=PAT)
    zone = _zone(client)
    account = _make_account(client)
    recon = _make_reconciliation(client, account)
    period = next(
        r
        for r in client.get("/reconciliations", params={"account_id": account})["items"]
        if r["id"] == recon
    )
    code = f"OP-{uuid4().hex[:10]}"
    written: list[str] = []

    def month() -> tuple[list, list, dict]:
        assigned = _fetch_all_lines(cfg, reconciliation=recon)
        available = _fetch_all_lines(
            cfg,
            account=account,
            unreconciled=True,
            date_from=period["date_start"],
            date_to=period["date_end"],
        )
        return line_rows(assigned, available)

    try:
        purchase = client.post(
            "/transactions",
            json_body={
                "id": str(uuid4()),
                "title": "FARMACIA",
                "amount_cents": -10000,
                "account_id": account,
                "date": _noon(zone, 2026, 4, 11),
                "operation_code": code,
            },
        )
        late = datetime(2026, 4, 30, 23, 30, tzinfo=zone).isoformat(timespec="seconds")
        last_day = _post_tx(client, account, late, -4200, "UBER *TRIP")
        after = _post_tx(client, account, _noon(zone, 2026, 5, 1), -2500, "TAXI")
        written.extend([purchase["id"], last_day["id"], after["id"]])
        parts = replace_parts(client, purchase["bank_line_id"], [-6000, -4000], written)
        split_line = parts[0]["bank_line_id"]

        rows, checked, part_of = month()
        assert checked == []
        assert [r[0] for r in rows] == [last_day["bank_line_id"], split_line]
        # the day as every list shows it: the response's own day (format_short_date)
        assert rows[0][1:] == (format_short_date(last_day["date"]), "UBER *TRIP", None, -4200)
        assert rows[1][1:] == ("2026-04-11", "FARMACIA", code, -10000)
        assert part_of[split_line] in {p["id"] for p in parts}

        # Tick: one part named, the whole line in the batch.
        client.put(f"/transactions/{part_of[split_line]}", json_body={"reconciliation_id": recon})
        rows, checked, part_of = month()
        assert checked == [split_line]
        assert [r[0] for r in rows] == [split_line, last_day["bank_line_id"]]
        assert rows[0][1:] == ("2026-04-11", "FARMACIA", code, -10000)
        for part in parts:
            assert client.get(f"/transactions/{part['id']}")["reconciliation_id"] == recon

        # Without the period's days, `unreconciled=true` on the account lists every
        # line in no batch, any date, newest first: the ticked purchase is not in it.
        no_batch = fetch_bank_lines(cfg, account=account, unreconciled=True)["items"]
        assert [line["id"] for line in no_batch] == [
            after["bank_line_id"],
            last_day["bank_line_id"],
        ]

        # Untick: `null` on the same part takes every part out.
        client.put(f"/transactions/{part_of[split_line]}", json_body={"reconciliation_id": None})
        rows, checked, _ = month()
        assert checked == []
        assert [r[0] for r in rows] == [last_day["bank_line_id"], split_line]
        for part in parts:
            assert client.get(f"/transactions/{part['id']}")["reconciliation_id"] is None
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/accounts/{account}")


def test_the_no_batch_list_reads_through_its_own_reads(client):
    """The "no batch" list's own path: the account's lines in no reconciliation,
    any day (`account_id`, `unreconciled=true`, no dates), read by
    `fetch_bank_lines` page by page and counted by `count_bank_lines` with the
    same filter. Newest first; a purchase split 60 + 40 is one row of its
    signed total and title; a line ticked into a month is in neither the list
    nor the count; and the pages add up to the count
    (contract: GET /v1/bank-lines) (contract: GET /v1/bank-lines/count)."""
    from expense.reads import count_bank_lines, fetch_bank_lines
    from expense.tui.screens.reconciliations import UNFILED_FILTER, unfiled_rows
    from tests.contract.conftest import ENGINE_URL, PAT

    cfg = Config(engine_url=ENGINE_URL, token=PAT)
    zone = _zone(client)
    account = _make_account(client)
    recon = _make_reconciliation(client, account)
    written: list[str] = []

    def no_batch(limit: int) -> list[dict]:
        lines, after = [], None
        while True:
            body = fetch_bank_lines(
                cfg, account=account, after=after, limit=limit, **UNFILED_FILTER
            )
            assert len(body["items"]) <= limit
            lines.extend(body["items"])
            after = body["next_cursor"]
            if after is None:
                return lines

    try:
        old = _post_tx(client, account, _noon(zone, 2026, 1, 3), -1500, "OLD ONE")
        ticked = _post_tx(client, account, _noon(zone, 2026, 4, 9), -700, "TICKED")
        purchase = _post_tx(client, account, _noon(zone, 2026, 6, 11), -10000, "FARMACIA")
        new = _post_tx(client, account, _noon(zone, 2026, 9, 2), 2500, "NEWEST")
        written.extend([old["id"], ticked["id"], purchase["id"], new["id"]])
        parts = replace_parts(client, purchase["bank_line_id"], [-6000, -4000], written)
        client.put(f"/transactions/{ticked['id']}", json_body={"reconciliation_id": recon})

        expected = [new["bank_line_id"], parts[0]["bank_line_id"], old["bank_line_id"]]
        count = count_bank_lines(cfg, account=account, **UNFILED_FILTER)
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
            "-100.00",
        ]
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/reconciliations/{recon}")
        _safe(client.delete, f"/accounts/{account}")


def test_the_no_batch_edit_form_writes_the_line_in_one_write_and_moves_it(client):
    """The "no batch" Edit form's own path (`BankLineEditFormScreen`): built on
    the line `GET /bank-lines/{id}` reads, its save is one `PUT /bank-lines/{id}`
    carrying the line fields changed beside every part at its current amount,
    and the engine writes date, title and operation onto every part, while each
    part keeps its own amount (contract: PUT /v1/bank-lines/{bank_line_id}, "Body").
    An emptied operation sends `null`, which clears the line's operation code, and
    an account move carries every part with it
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")."""
    from expense.reads import fetch_bank_line
    from tests.contract.conftest import ENGINE_URL, PAT

    cfg = Config(engine_url=ENGINE_URL, token=PAT)
    zone = _zone(client)
    account = _make_account(client)
    other = _make_account(client)
    code = f"op-{uuid4().hex[:10]}"
    written: list[str] = []

    def save(line_id: str, **typed) -> dict:
        form = _edit_form(cfg, line_id, no_batch=True)
        form._values.update(typed)
        request = form._submit_request()
        assert request is not None
        _method, path, payload, _busy = request
        client.put(path, json_body=payload)
        assert payload.pop("parts") == [
            {"id": p.id, "amount_cents": p.amount_cents} for p in form._parts
        ]
        return payload

    try:
        purchase = _post_tx(client, account, _noon(zone, 2026, 5, 6), -10000, "FARMACIA")
        written.append(purchase["id"])
        client.put(f"/transactions/{purchase['id']}", json_body={"operation_code": code})
        replace_parts(client, purchase["bank_line_id"], [-6000, -4000], written)
        line_id = purchase["bank_line_id"]
        before = {p["id"]: p for p in fetch_bank_line(cfg, line_id)["parts"]}

        sent = save(line_id, date="2026-05-08", title="FARMACIA CENTRAL", operation=f"{code}-b")
        assert set(sent) == {"date", "title", "operation_code"}
        moved = fetch_bank_line(cfg, line_id)
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
        assert fetch_bank_line(cfg, line_id)["operation_code"] is None

        sent = save(line_id, account=other)
        assert sent == {"account_id": other, "reconciliation_id": None}
        assert {p["account_id"] for p in fetch_bank_line(cfg, line_id)["parts"]} == {other}
    finally:
        for tx_id in written:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/accounts/{account}")
        _safe(client.delete, f"/accounts/{other}")
