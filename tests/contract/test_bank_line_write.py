"""Contract: the whole-line write, `PUT /v1/bank-lines/{bank_line_id}`.

One write gives a bank line its fields and its complete set of parts: a kept part keeps
its id, a new id makes a new part, and a part left out is deleted
(contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"). The Edit form saves through
it, its body built by expense/bank_line_write.py, so only the engine can say what it
keeps, takes and refuses. Pinned here:

  · a part kept, one added and one dropped in one write: the kept part keeps its id
    and is updated in place, the new one is created on the line with the line's
    fields, the dropped one is deleted, and the answer is the line as read plus
    `created_part_ids` and `deleted_part_ids`;
  · a line taken back to one part, the other deleted;
  · the total: outside a completed statement the parts may add up to a new total and
    the account's balance in the line's currency moves by the difference; inside one the
    parts may be redistributed, mixing directions, a part created there joining it and
    a part dropped there deleted, while a set that misses the line's total is
    `SPLIT_TOTAL_MISMATCH` on `parts` and every `parts.<i>.amount_cents`, beside
    `SEALED_PERIOD` on the `parts.<i>.id` of a part it would create, nothing written;
  · the locked line fields on a line in a completed statement: each of `title`,
    `date`, `account_id`, `currency_code`, `operation_code` and `statement_id` sent is
    `LOCKED`, at its current value too, every one named when sent together, and the
    parts' refusal answered beside the lock; an empty `operation_code` may be filled once;
  · a move: a line moved by `currency_code` alone, by `account_id` alone and by both,
    through `PUT /bank-lines/{id}` and through `PUT /transactions/{id}`, every part and
    its money with it; `CURRENCY_NOT_HELD` on `account_id` for the account alone onto an
    account lacking the currency and on `currency_code` when it is sent; a line in a
    draft statement refused as `ASSIGNED_TO_RECONCILIATION` until the move settles its
    statement, then kept in it or left out of it;
  · a kept part's hashtags: a part sent with every value as held and no
    `hashtag_ids` is not written, one sent with its own `hashtag_ids` unchanged is,
    `[]` puts it on the pending hashtag, and the app's own `kept_part` sends the
    hashtags only when the set changed;
  · a replay under the same idempotency key answers exactly as the first send and
    writes once; the same key with another body is `409` `IDEMPOTENCY_KEY_REUSED`.

Elsewhere: `statement_line` and `statement_place` refused in its body
(test_line_codes_and_statement_lines.py), `ID_EXISTS` on a taken part id
(test_create_sent_again.py), an opening balance's line, an archived account's line and
`edit_limits` (test_bank_line_edit_limits.py, and an archived account's rows under the
transaction routes in test_resources_lifecycle.py), the pending hashtag beside another
(test_pending_hashtag.py) and the Edit form's own path (test_bank_lines.py).

Each test builds its own accounts and undoes everything (conftest.py `scratch`). Gating,
target and the real-ledger guard: conftest.py.
"""

from uuid import uuid4

import pytest

from expense.bank_line_write import kept_part, line_body
from expense.errors import EngineError
from expense.formatting import signed_cents
from expense.reads import pending_hashtag_of
from tests.contract.conftest import (
    account_balance,
    assert_refusal,
    assert_refusals,
    balance_of,
    read_signed,
    refused,
    refused_keeping,
    refused_line_write,
    under_key,
)

APRIL = ("2026-04-01", "2026-04-30")
MARCH = ("2026-03-01", "2026-03-31")

#: The keys the write's answer adds to the line as `GET /bank-lines/{id}` reads it
#: (contract: PUT /v1/bank-lines/{bank_line_id}, "Response").
ANSWER_EXTRAS = {"changed_parts", "created_part_ids", "deleted_part_ids"}


def _line(client, line_id: str) -> dict:
    return client.get(f"/bank-lines/{line_id}")


def _versions(client, line_id: str) -> dict[str, int]:
    return {p["id"]: p["version"] for p in _line(client, line_id)["parts"]}


def _write(client, line_id: str, body: dict) -> dict:
    return client.put(f"/bank-lines/{line_id}", json_body=body)


def _new_id(scratch) -> str:
    """A fresh part id, kept for cleanup before any write can create it."""
    new_id = str(uuid4())
    scratch.transactions.append(new_id)
    return new_id


def test_one_write_keeps_a_part_adds_one_and_drops_one(client, scratch):
    """The kept part keeps its id and takes the values sent, the new id is created on
    the line with the line's title, date, account, operation code and line code, and
    the part left out is deleted; the answer is the line as `GET /bank-lines/{id}`
    reads it after the write, plus the ids created and deleted, and no kept part's line
    fields changed (contract: PUT /v1/bank-lines/{bank_line_id}, "Response")."""
    account = scratch.account()
    line = scratch.line(account, "2026-03-05", -6000, -4000)
    kept, dropped = scratch.transactions[-2:]
    before = {p["id"]: p for p in _line(client, line)["parts"]}
    added = _new_id(scratch)

    answer = _write(
        client,
        line,
        {
            "parts": [
                {"id": kept, "amount_cents": -5000, "description": "kept"},
                {"id": added, "amount_cents": -5000},
            ]
        },
    )
    assert answer["created_part_ids"] == [added]
    assert answer["deleted_part_ids"] == [dropped]
    assert answer["changed_parts"] == []
    assert {k: v for k, v in answer.items() if k not in ANSWER_EXTRAS} == _line(client, line)
    assert (answer["id"], answer["line_code"]) == (line, before[kept]["line_code"])
    assert (answer["net_cents"], answer["part_count"]) == (-10000, 2)
    assert {p["id"] for p in answer["parts"]} == {kept, added}

    mine = read_signed(client, kept)
    assert (mine["amount_cents"], mine["description"]) == (-5000, "kept")
    assert mine["version"] == before[kept]["version"] + 1
    new = read_signed(client, added)
    assert new["amount_cents"] == -5000
    for key in (
        "bank_line_id",
        "line_code",
        "title",
        "date",
        "account_id",
        "currency_code",
        "operation_code",
    ):
        assert new[key] == before[kept][key], key
    err = refused(lambda: client.get(f"/transactions/{dropped}"))
    assert err.status == 404


def test_a_line_goes_back_to_one_part(client, scratch):
    """A two-part line sent one part, at the line's whole total, keeps that part and
    deletes the other: the line stays, one row under its own id
    (contract: PUT /v1/bank-lines/{bank_line_id}, "A live part not sent is deleted")."""
    account = scratch.account()
    line = scratch.line(account, "2026-03-06", -6000, -4000)
    kept, dropped = scratch.transactions[-2:]

    answer = _write(client, line, {"parts": [{"id": kept, "amount_cents": -10000}]})
    assert (answer["created_part_ids"], answer["deleted_part_ids"]) == ([], [dropped])
    assert (answer["id"], answer["part_count"], answer["net_cents"]) == (line, 1, -10000)
    assert [p["id"] for p in answer["parts"]] == [kept]
    listed = client.get("/transactions", params={"bank_line_id": line})["items"]
    assert [t["id"] for t in listed] == [kept]


def test_outside_a_completed_statement_the_total_may_change(client, scratch):
    """In a draft the parts may add up to a new total: the line takes it, and the
    account's balance in the line's currency moves by the difference
    (contract: PUT /v1/bank-lines/{bank_line_id}, "The total")."""
    account = scratch.account()
    statement = scratch.statement(account, *MARCH)["id"]
    line = scratch.line(account, "2026-03-07", -6000, -4000)
    one, two = scratch.transactions[-2:]
    scratch.assign(one, statement)
    balance = account_balance(client, account)

    answer = _write(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -7000}, {"id": two, "amount_cents": -5000}]},
    )
    assert answer["net_cents"] == -12000
    assert account_balance(client, account) == balance - 2000
    assert {p["statement_id"] for p in answer["parts"]} == {statement}


def test_inside_a_completed_statement_the_total_is_kept(client, scratch):
    """Inside a completed statement the parts' signed sum must equal the line's
    total: redistributed amounts are taken, directions may mix, a part created there
    joins the statement and a part dropped there is deleted. A set that misses the
    total is `422` `SPLIT_TOTAL_MISMATCH` on `parts` and every `parts.<i>.amount_cents`,
    the message stating both totals, and a part it would create is `SEALED_PERIOD` on
    its `parts.<i>.id`, in the same answer; nothing is written
    (contract: PUT /v1/bank-lines/{bank_line_id}, "The total")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Refusals, in order")."""
    account = scratch.account()
    line = scratch.line(account, "2026-03-08", -6000, -4000)
    one, two = scratch.transactions[-2:]
    statement = scratch.completed(account, *MARCH, one, two)["id"]

    def amounts() -> dict[str, int]:
        return {p["id"]: signed_cents(p) for p in _line(client, line)["parts"]}

    _write(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -7000}, {"id": two, "amount_cents": -3000}]},
    )
    assert amounts() == {one: -7000, two: -3000}
    _write(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -12000}, {"id": two, "amount_cents": 2000}]},
    )
    assert amounts() == {one: -12000, two: 2000}

    added = _new_id(scratch)
    answer = _write(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -5000}, {"id": added, "amount_cents": -5000}]},
    )
    assert (answer["created_part_ids"], answer["deleted_part_ids"]) == ([added], [two])
    assert client.get(f"/transactions/{added}")["statement_id"] == statement
    assert _line(client, line)["net_cents"] == -10000

    err = refused_line_write(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -8000}, {"id": added, "amount_cents": -3000}]},
    )
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "parts": "SPLIT_TOTAL_MISMATCH",
            "parts.0.amount_cents": "SPLIT_TOTAL_MISMATCH",
            "parts.1.amount_cents": "SPLIT_TOTAL_MISMATCH",
        },
    )
    assert "-10000" in err.fields["parts"] and "-11000" in err.fields["parts"]

    extra = _new_id(scratch)
    err = refused_line_write(
        client,
        line,
        {
            "parts": [
                {"id": one, "amount_cents": -5000},
                {"id": added, "amount_cents": -5000},
                {"id": extra, "amount_cents": -1000},
            ]
        },
    )
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "parts": "SPLIT_TOTAL_MISMATCH",
            "parts.0.amount_cents": "SPLIT_TOTAL_MISMATCH",
            "parts.1.amount_cents": "SPLIT_TOTAL_MISMATCH",
            "parts.2.amount_cents": "SPLIT_TOTAL_MISMATCH",
            "parts.2.id": "SEALED_PERIOD",
        },
    )


def test_a_line_in_a_completed_statement_keeps_its_line_fields(client, scratch):
    """On a line in a completed statement every line field sent is `422` `LOCKED` on its
    key, at its current value too, `account_id` and `currency_code` each on its own key
    when sent alone or together, and all of them are named when sent together; with
    `parts` the parts' refusal is answered beside the lock. A `null` `operation_code` may
    be filled, and once set it is locked like the rest. Nothing is written on a refusal
    (contract: PUT /v1/transactions/{transaction_id}, "Field locking")
    (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")."""
    account = scratch.account("PEN", "USD")
    other = scratch.account("PEN", "USD")
    line = scratch.line(account, "2026-03-09", -6000, -4000)
    one, two = scratch.transactions[-2:]
    statement = scratch.completed(account, *MARCH, one, two)["id"]
    title = _line(client, line)["parts"][0]["title"]

    code = f"OP-{uuid4().hex[:10]}"
    filled = _write(client, line, {"operation_code": code})
    assert filled["operation_code"] == code

    sent_alone = [
        ({"title": title}, "title"),
        ({"title": "renamed"}, "title"),
        ({"date": scratch.noon("2026-03-10")}, "date"),
        ({"account_id": other}, "account_id"),
        ({"account_id": account}, "account_id"),
        ({"currency_code": "USD"}, "currency_code"),
        ({"currency_code": "PEN"}, "currency_code"),
        ({"operation_code": code}, "operation_code"),
        ({"operation_code": None}, "operation_code"),
        ({"statement_id": statement}, "statement_id"),
        ({"statement_id": None}, "statement_id"),
    ]
    for body, key in sent_alone:
        err = refused_line_write(client, line, body)
        assert_refusal(err, 422, "VALIDATION_ERROR", key, "LOCKED")

    for body in (
        {"account_id": other, "currency_code": "USD"},
        {"account_id": account, "currency_code": "PEN"},
    ):
        err = refused_line_write(client, line, body)
        assert_refusals(err, 422, "VALIDATION_ERROR", dict.fromkeys(body, "LOCKED"))

    together = {
        "title": "renamed",
        "date": scratch.noon("2026-03-10"),
        "account_id": other,
        "currency_code": "USD",
        "operation_code": f"{code}-b",
        "statement_id": None,
    }
    err = refused_line_write(client, line, together)
    assert_refusals(err, 422, "VALIDATION_ERROR", dict.fromkeys(together, "LOCKED"))

    beside = {
        "title": "renamed",
        "parts": [{"id": one, "amount_cents": -8000}, {"id": two, "amount_cents": -3000}],
    }
    err = refused_line_write(client, line, beside)
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "title": "LOCKED",
            "parts": "SPLIT_TOTAL_MISMATCH",
            "parts.0.amount_cents": "SPLIT_TOTAL_MISMATCH",
            "parts.1.amount_cents": "SPLIT_TOTAL_MISMATCH",
        },
    )


def _placed(client, line_id: str) -> tuple[str, str]:
    """The line's account and currency as the line answers them, every part being on that
    pair too (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")."""
    read = _line(client, line_id)
    pair = (read["account_id"], read["currency_code"])
    assert {(p["account_id"], p["currency_code"]) for p in read["parts"]} == {pair}
    return pair


@pytest.mark.parametrize("route", ["bank-lines", "transactions"])
def test_a_line_moves_by_currency_by_account_or_both(client, scratch, route):
    """A move names where the line goes by `currency_code` alone (that currency of its own
    account), by `account_id` alone (the same currency on that account) or by both, and
    moves every part of the line, its money with it: the account's balance in each currency
    follows. The same through `PUT /bank-lines/{id}` and through `PUT /transactions/{id}`
    on one part, whose `changed_parts` lists both parts, none having left a statement
    (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction")
    (contract: PUT /v1/transactions/{transaction_id}, "Response")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Body")."""
    visa = scratch.account("PEN", "USD")
    other = scratch.account("PEN", "USD")
    line = scratch.line(visa, "2026-03-13", -6000, -4000)
    one, two = scratch.transactions[-2:]
    path = f"/bank-lines/{line}" if route == "bank-lines" else f"/transactions/{one}"
    assert _placed(client, line) == (visa, "PEN")

    here = (visa, "PEN")
    for body, there in (
        ({"currency_code": "USD"}, (visa, "USD")),
        ({"account_id": other}, (other, "USD")),
        ({"account_id": visa, "currency_code": "PEN"}, (visa, "PEN")),
    ):
        answer = client.put(path, json_body=body)
        assert _placed(client, line) == there, body
        assert {c["transaction"]["id"] for c in answer["changed_parts"]} == {one, two}, body
        assert {c["left_statement"] for c in answer["changed_parts"]} == {False}, body
        assert account_balance(client, *here) == 0, body
        assert account_balance(client, *there) == -10000, body
        here = there


@pytest.mark.parametrize("route", ["bank-lines", "transactions"])
def test_a_move_by_account_alone_onto_an_only_currency_converts_nothing(client, scratch, route):
    """`account_id` alone onto an account that lacks the line's currency but holds exactly one
    moves the line to that currency, the amount as it was, the answer naming the account and
    the new currency; both accounts' balances move by that amount. With `currency_code` sent,
    alone or beside `account_id`, a currency the account lacks is `422` `CURRENCY_NOT_HELD` on
    `currency_code` and nothing is written (contract: PUT /v1/transactions/{transaction_id},
    "Moving a transaction") (contract: PUT /v1/bank-lines/{bank_line_id}, "Body")."""
    visa = scratch.account("PEN", "USD")
    soles = scratch.account()
    dollars = scratch.line(visa, "2026-03-14", -6000, -4000, currency="USD")
    dollar_parts = scratch.transactions[-2:]
    loose = scratch.line(soles, "2026-03-14", -2000)
    loose_part = scratch.transactions[-1]

    def route_path(line: str, part: str) -> str:
        return f"/bank-lines/{line}" if route == "bank-lines" else f"/transactions/{part}"

    def balances() -> list[int]:
        return [
            account_balance(client, visa, "PEN"),
            account_balance(client, visa, "USD"),
            account_balance(client, soles),
        ]

    cases = [
        (dollars, dollar_parts[0], {"account_id": soles, "currency_code": "USD"}),
        (loose, loose_part, {"currency_code": "USD"}),
        (loose, loose_part, {"account_id": soles, "currency_code": "USD"}),
    ]
    for line, part, body in cases:
        err = refused_keeping(
            lambda line=line: (_line(client, line), balances()),
            lambda line=line, part=part, body=body: client.put(
                route_path(line, part), json_body=body
            ),
            body,
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "CURRENCY_NOT_HELD")

    before = balances()
    amounts = sorted(p["amount_cents"] for p in _line(client, dollars)["parts"])
    sent = {"account_id": soles}
    if route == "bank-lines":
        client.put(f"/bank-lines/{dollars}", json_body=sent)
    else:
        for part in dollar_parts:
            client.put(f"/transactions/{part}", json_body=sent)
    moved = _line(client, dollars)
    assert (moved["account_id"], moved["currency_code"]) == (soles, "PEN")
    assert sorted(p["amount_cents"] for p in moved["parts"]) == amounts
    assert {p["currency_code"] for p in moved["parts"]} == {"PEN"}
    # the dollars left the Visa and the same amounts, unconverted, entered the soles account
    assert balances() == [before[0], before[1] + 10000, before[2] - 10000]


def test_a_move_of_an_assigned_line_settles_its_statement(client, scratch):
    """A line in a draft statement moved to another account or currency without a
    `statement_id` is `422` `ASSIGNED_TO_RECONCILIATION` on each of `account_id` and
    `currency_code` sent, nothing written. Sent `statement_id` of its own draft, it moves
    to another currency of its account and stays in it, the draft gaining the currency's
    balances blank; sent `statement_id` `null`, it moves to another account and leaves the
    statement, each part's `left_statement` true
    (contract: "Statements", "Assigning transactions")
    (contract: PUT /v1/transactions/{transaction_id}, "Response")."""
    visa = scratch.account("PEN", "USD")
    other = scratch.account("PEN", "USD")
    statement = scratch.statement(visa, *APRIL)["id"]
    line = scratch.line(visa, "2026-04-06", -6000, -4000)
    one, two = scratch.transactions[-2:]
    scratch.assign(one, statement)

    for body in (
        {"currency_code": "USD"},
        {"account_id": other},
        {"account_id": other, "currency_code": "USD"},
    ):
        err = refused_line_write(client, line, body)
        reasons = dict.fromkeys(body, "ASSIGNED_TO_RECONCILIATION")
        assert_refusals(err, 422, "VALIDATION_ERROR", reasons)

    kept = _write(client, line, {"currency_code": "USD", "statement_id": statement})
    assert (kept["account_id"], kept["currency_code"]) == (visa, "USD")
    assert {p["statement_id"] for p in kept["parts"]} == {statement}
    assert {c["left_statement"] for c in kept["changed_parts"]} == {False}
    usd = balance_of(client.get(f"/statements/{statement}"), "USD")
    assert (usd["beginning_balance_cents"], usd["ending_balance_cents"]) == (None, None)

    left = _write(client, line, {"account_id": other, "statement_id": None})
    assert _placed(client, line) == (other, "USD")
    assert {c["transaction"]["id"] for c in left["changed_parts"]} == {one, two}
    assert {c["left_statement"] for c in left["changed_parts"]} == {True}
    assert {p["statement_id"] for p in left["parts"]} == {None}


def test_a_kept_parts_hashtags_are_written_whenever_sent(client, scratch):
    """A kept part sent with every value it holds and no `hashtag_ids` is not
    written; sent with `hashtag_ids`, even its own set, it is written, the other part
    not; `[]` puts it on the pending hashtag. So the app's `kept_part` leaves the
    hashtags out of a part whose set did not change, and that write changes nothing
    (contract: PUT /v1/bank-lines/{bank_line_id}, "A live part of this line is updated in place").
    """
    account = scratch.account()
    line = scratch.line(account, "2026-03-11", -6000, -4000)
    one, two = scratch.transactions[-2:]
    tag = str(uuid4())
    client.post("/hashtags", json_body={"id": tag, "name": f"contract-line-{tag[:8]}"})
    try:
        client.put(f"/transactions/{one}", json_body={"hashtag_ids": [tag]})
        pending = pending_hashtag_of(client.get("/hashtags")["items"])
        assert pending is not None
        pending_id = pending[0]

        as_held = [{"id": one, "amount_cents": -6000}, {"id": two, "amount_cents": -4000}]
        versions = _versions(client, line)
        _write(client, line, {"parts": as_held})
        assert _versions(client, line) == versions

        _write(client, line, {"parts": [{**as_held[0], "hashtag_ids": [tag]}, as_held[1]]})
        assert _versions(client, line) == {one: versions[one] + 1, two: versions[two]}
        assert client.get(f"/transactions/{one}")["hashtag_ids"] == [tag]

        _write(client, line, {"parts": [{**as_held[0], "hashtag_ids": []}, as_held[1]]})
        assert client.get(f"/transactions/{one}")["hashtag_ids"] == [pending_id]

        # The app's body: hashtags only when the set changed.
        def app_body(hashtags: dict[str, list[str]]) -> dict:
            held = {p["id"]: p for p in _line(client, line)["parts"]}
            return line_body(
                [
                    kept_part(
                        held[part_id],
                        amount_cents=signed_cents(held[part_id]),
                        category_id=None,
                        description=None,
                        hashtag_ids=hashtags.get(part_id, held[part_id]["hashtag_ids"]),
                        pending_hashtag_id=pending_id,
                    )
                    for part_id in (one, two)
                ]
            )

        unchanged = app_body({})
        assert all("hashtag_ids" not in part for part in unchanged["parts"])
        versions = _versions(client, line)
        _write(client, line, unchanged)
        assert _versions(client, line) == versions

        changed = app_body({one: [tag]})
        assert [("hashtag_ids" in part) for part in changed["parts"]] == [True, False]
        _write(client, line, changed)
        assert _versions(client, line) == {one: versions[one] + 1, two: versions[two]}
        assert client.get(f"/transactions/{one}")["hashtag_ids"] == [tag]
    finally:
        try:
            client.delete(f"/hashtags/{tag}")
        except EngineError:
            pass


def test_a_replay_answers_the_same_and_writes_once(client, scratch):
    """A write sent again under the same idempotency key answers exactly as the first
    send did, and the line is written once: the kept part's `version` up by one, the
    new part created once, the dropped part deleted once. The same key with another
    body is `409` on `X-Idempotency-Key` (`IDEMPOTENCY_KEY_REUSED`)
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Response")
    (contract: "Base Conventions", "Idempotency")."""
    account = scratch.account()
    line = scratch.line(account, "2026-03-12", -6000, -4000)
    kept, dropped = scratch.transactions[-2:]
    versions = _versions(client, line)
    added = _new_id(scratch)
    body = {"parts": [{"id": kept, "amount_cents": -7000}, {"id": added, "amount_cents": -3000}]}

    key = uuid4()
    with under_key(key):
        first = _write(client, line, body)
        replayed = _write(client, line, body)
        other = {"parts": [{"id": kept, "amount_cents": -10000}]}
        err = refused(lambda: _write(client, line, other))

    assert replayed == first
    assert (first["created_part_ids"], first["deleted_part_ids"]) == ([added], [dropped])
    assert _versions(client, line) == {kept: versions[kept] + 1, added: 1}
    assert_refusal(err, 409, "CONFLICT", "X-Idempotency-Key", "IDEMPOTENCY_KEY_REUSED")
