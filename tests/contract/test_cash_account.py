"""Contract: the cash account, against a real engine.

A user's cash is an account of kind `cash`: made by `POST /accounts` with `kind: "cash"`, named
`CASH-<n>` by the engine, at no bank and with no numbers, and a user may hold several, archived or
not (contract: "What an account is", "The cash account"). The New and Edit forms and Home send it,
so only the engine can say what it refuses.

What it pins:

1. The account's shape: kind `cash`, a name `CASH-` and four digits, each create's number higher
   than the last, `bank_code` and `statement_code` null, `numbers` empty; its row in
   `/dashboard`'s `accounts` as `{id, name, kind, currencies}`, and in `archived_accounts` once
   archived, back in `accounts` once unarchived (contract: GET /v1/dashboard, "Field rules").
2. A number is never reused, and a number another live account's name holds is skipped
   (contract: POST /v1/accounts).
3. `CASH_TAKES_NO_FIELD`, `422` on each field sent: `name`, `bank_code`, `last4` and
   `statement_code` on a create (`null` included), `name`, `bank_code`, `current_number`,
   `new_number` and `statement_code` on an update (`null` included), writing nothing
   (contract: POST /v1/accounts, "Forbidden") (contract: PUT /v1/accounts/{account_id}).
4. `CASH_KIND_FIXED`, `409` on `account_id`, for `make-person` and `make-account`, live or
   archived (contract: POST /v1/accounts/{account_id}/make-person, "Refusals").
5. A delete takes a cash account holding no transaction and refuses one holding any, its opening
   balance included, `409` `HAS_TRANSACTIONS` on `account_id`
   (contract: DELETE /v1/accounts/{account_id}, "Refusals").
6. `CASH_TAKES_NO_STATEMENT`, `422` on `account_id`, for `POST /statements`,
   `POST /statements/import` and `POST /transactions/import`, the two uploads on a dry run as
   on an apply, writing nothing.
7. `Efectivo` is no held name: a person may be named it.

Every cash account a test makes is the test's own (`made_cash`), deleted by the scratch cleanup
with its opening balances; the practice user holds none between tests. Gating, target resolution
and the real-ledger guard live in conftest.py.
"""

import re
from datetime import date
from uuid import uuid4

import pytest

from tests.contract.conftest import (
    CURRENT_HEADER,
    PaperRow,
    assert_refusal,
    assert_refusals,
    bank_code,
    free_statement_codes,
    kind_change,
    next_last4,
    refused,
    refused_writing_nothing,
    savings_paper,
    send_download,
    send_statement,
    statement_create_body,
    transaction_count,
)

MARCH = {"start": date(2026, 3, 1), "end": date(2026, 3, 31)}
_CASH_NAME = re.compile(r"CASH-(\d{4})")


_OPENINGS = {"PEN": 23750, "USD": -4550}
_OPENING_DAY = "2026-01-01T12:00:00-05:00"


def _cash_body(*, opening: bool = True) -> dict:
    """A `POST /accounts` body for a cash account under a fresh id: its kind and soles and
    dollars, each with an opening balance (none with `opening` false), nothing else
    (contract: POST /v1/accounts, "Required"). The two opening transactions' ids are in the dict
    this function returns."""
    if not opening:
        return {
            "id": str(uuid4()),
            "kind": "cash",
            "currencies": [{"currency_code": code} for code in _OPENINGS],
        }
    currencies = [
        {
            "currency_code": code,
            "opening_balance": {
                "transaction_id": str(uuid4()),
                "amount_cents": cents,
                "date": _OPENING_DAY,
            },
        }
        for code, cents in _OPENINGS.items()
    ]
    return {"id": str(uuid4()), "kind": "cash", "currencies": currencies}


def _number(account: dict) -> int:
    """The number in the cash account's name, `CASH-` and four digits."""
    named = _CASH_NAME.fullmatch(account["name"])
    assert named, account["name"]
    return int(named.group(1))


@pytest.fixture
def made_cash(client, scratch):
    """Makes a cash account under a fresh id, kept for cleanup before the call, and returns the
    engine's `201` answer with the body sent under `body`; `opening` as in `_cash_body`."""

    def make(*, opening: bool = True) -> dict:
        body = _cash_body(opening=opening)
        scratch.accounts.append(body["id"])
        scratch.transactions += [
            c["opening_balance"]["transaction_id"] for c in body["currencies"] if opening
        ]
        return {**client.post("/accounts", json_body=body), "body": body}

    return make


@pytest.fixture
def cash(made_cash):
    """A cash account made for the test, with its opening balances."""
    return made_cash()


def _both_states(client, account_id: str):
    """The account live, then archived, yielding each time; unarchived after, whatever
    happens in between."""
    try:
        yield "live"
        client.post(f"/accounts/{account_id}/archive")
        yield "archived"
    finally:
        client.post(f"/accounts/{account_id}/unarchive")


def test_each_cash_create_makes_a_new_account_named_higher_than_the_last(client, made_cash):
    """Three creates are three accounts, each kind `cash` named `CASH-` and four digits higher
    than the previous, with no bank, number or statement code, the opening balances as sent, and
    each listed once without `?include_people=true`
    (contract: "What an account is", "The cash account")."""
    made = [made_cash() for _ in range(3)]

    numbers = [_number(a) for a in made]
    assert numbers == sorted(set(numbers))
    for account in made:
        assert account["kind"] == "cash"
        sent = {c["currency_code"]: c["opening_balance"] for c in account["body"]["currencies"]}
        assert [
            (c["currency_code"], c["current_balance_cents"], c["opening_balance_transaction_id"])
            for c in account["currencies"]
        ] == [(code, _OPENINGS[code], sent[code]["transaction_id"]) for code in _OPENINGS]
        read = client.get(f"/accounts/{account['id']}")
        assert read["name"] == account["name"]
        assert read["bank_code"] is None
        assert read["numbers"] == []
        assert read["statement_code"] is None
        assert read["is_archived"] is False
        assert [a["id"] for a in client.get("/accounts")["items"]].count(account["id"]) == 1


def test_a_cash_number_is_never_reused_and_one_another_account_is_named_is_skipped(
    client, scratch, made_cash
):
    """After the highest-numbered cash account is deleted, the next create is named higher still;
    a person named for the next number, in other letters, makes the create skip it
    (contract: POST /v1/accounts). That person cannot carry the `contract-` prefix, since its
    name is what the test checks; `leaves_nothing` still flags it if teardown fails."""
    first = made_cash(opening=False)
    client.delete(f"/accounts/{first['id']}")
    second = made_cash()
    assert _number(second) > _number(first)

    taken = _number(second) + 1
    scratch.account("PEN", person=True, name=f"cash-{taken:04d}")
    third = made_cash()
    assert _number(third) > taken


def test_the_cash_account_has_its_row_in_the_dashboard_and_archives_whole(client, cash):
    """`/dashboard` lists it in `accounts` as `{id, name, kind, currencies}` with kind `cash`;
    archived it moves, every currency in its row, to `archived_accounts`, and unarchived it
    returns (contract: GET /v1/dashboard, "Field rules")."""
    account_id = cash["id"]
    row = next(r for r in client.get("/dashboard")["accounts"] if r["id"] == account_id)
    assert set(row) == {"id", "name", "kind", "currencies"}
    assert (row["name"], row["kind"]) == (cash["name"], "cash")
    assert {c["currency_code"] for c in row["currencies"]} >= {"PEN"}

    for state in _both_states(client, account_id):
        asked = client.get("/dashboard", params={"include_archived": "true"})
        in_live = [r["id"] for r in asked["accounts"]]
        in_archived = [r["id"] for r in asked["archived_accounts"]]
        if state == "live":
            assert account_id in in_live and account_id not in in_archived
        else:
            assert account_id in in_archived and account_id not in in_live
            moved = next(r for r in asked["archived_accounts"] if r["id"] == account_id)
            assert (moved["name"], moved["kind"]) == (cash["name"], "cash")
            assert not any(r["id"] == account_id for r in asked["people"])
    assert any(r["id"] == account_id for r in client.get("/dashboard")["accounts"])


def test_a_create_naming_a_field_the_cash_account_never_takes_is_refused(client):
    """Each of `name`, `bank_code`, `last4` and `statement_code`, with a value or `null`, is
    `422` `CASH_TAKES_NO_FIELD` on that field; all four at once are one answer naming each
    (contract: POST /v1/accounts, "Forbidden")."""
    (code,) = free_statement_codes(client, 1)
    sent = {
        "name": "Mi caja",
        "bank_code": bank_code(),
        "last4": next_last4(),
        "statement_code": code,
    }
    cases = [{key: value} for key, value in sent.items()]
    cases += [{key: None} for key in sent]
    cases.append(dict(sent))
    for extra in cases:
        body = {**_cash_body(), **extra}
        err = refused_writing_nothing(client, lambda b=body: client.post("/accounts", json_body=b))
        assert_refusals(err, 422, "VALIDATION_ERROR", dict.fromkeys(extra, "CASH_TAKES_NO_FIELD"))
        assert refused(lambda b=body: client.get(f"/accounts/{b['id']}")).status == 404


def test_an_update_naming_a_field_the_cash_account_never_takes_is_refused(client, cash):
    """On `PUT /accounts/{id}`, `name`, `bank_code`, `current_number`, `new_number` and
    `statement_code` are each `422` `CASH_TAKES_NO_FIELD` on the field sent, a `null` included,
    and all of them at once are one answer; nothing is written. A `color` alone is taken and put
    back (contract: PUT /v1/accounts/{account_id})."""
    account_id = cash["id"]
    (code,) = free_statement_codes(client, 1)
    sent = {
        "name": "Mi caja",
        "bank_code": bank_code(),
        "current_number": {"start_date": "2026-04-10"},
        "new_number": {"last4": next_last4(), "start_date": "2026-04-10"},
        "statement_code": code,
    }
    cases = [{key: value} for key, value in sent.items()]
    cases += [{key: None} for key in sent]
    cases.append(dict(sent))
    for body in cases:
        err = refused_writing_nothing(
            client, lambda b=body: client.put(f"/accounts/{account_id}", json_body=b)
        )
        assert_refusals(err, 422, "VALIDATION_ERROR", dict.fromkeys(body, "CASH_TAKES_NO_FIELD"))

    before = client.get(f"/accounts/{account_id}")
    changed = client.put(f"/accounts/{account_id}", json_body={"color": "#123456"})
    assert changed["color"] == "#123456"
    client.put(f"/accounts/{account_id}", json_body={"color": before["color"]})


def test_the_cash_accounts_kind_never_changes(client, cash):
    """`make-person` and `make-account` are each `409` `CASH_KIND_FIXED` on `account_id`, live
    and archived alike (the archive is not asked about), writing nothing
    (contract: POST /v1/accounts/{account_id}/make-person, "Refusals")."""
    account_id = cash["id"]
    for _state in _both_states(client, account_id):
        for route in ("make-person", "make-account"):
            err = refused_writing_nothing(
                client, lambda r=route: kind_change(client, account_id, r)
            )
            assert_refusal(err, 409, "CONFLICT", "account_id", "CASH_KIND_FIXED")
    assert client.get(f"/accounts/{account_id}")["kind"] == "cash"


def test_an_empty_cash_account_is_deleted_and_one_holding_a_transaction_is_not(
    client, scratch, made_cash
):
    """A cash account with no transaction is deleted, live or archived, and then reads `404`;
    one holding only its opening balances is refused `409` `HAS_TRANSACTIONS` on `account_id`,
    live and archived alike, and stays whole (contract: DELETE /v1/accounts/{account_id},
    "Refusals")."""
    empty = made_cash(opening=False)
    client.delete(f"/accounts/{empty['id']}")
    assert refused(lambda: client.get(f"/accounts/{empty['id']}")).status == 404
    archived = made_cash(opening=False)
    client.post(f"/accounts/{archived['id']}/archive")
    client.delete(f"/accounts/{archived['id']}")
    assert refused(lambda: client.get(f"/accounts/{archived['id']}")).status == 404

    held = made_cash()
    for _state in _both_states(client, held["id"]):
        err = refused_writing_nothing(client, lambda: client.delete(f"/accounts/{held['id']}"))
        assert_refusal(err, 409, "CONFLICT", "account_id", "HAS_TRANSACTIONS")
    assert client.get(f"/accounts/{held['id']}")["currencies"] == held["currencies"]


def test_the_cash_account_takes_no_statement_on_any_of_the_three_writes(client, cash):
    """`POST /statements`, `POST /statements/import` and `POST /transactions/import`, each
    naming a cash account, are `422` `CASH_TAKES_NO_STATEMENT` on `account_id`; the uploads on a
    dry run as on an apply. Nothing is written: no transaction on the account, no statement
    under the id sent
    (contract: POST /v1/statements, "Order")
    (contract: POST /v1/statements/import, "Accounts")
    (contract: POST /v1/transactions/import, "Accounts")."""
    account_id = cash["id"]
    paper = savings_paper([PaperRow(date(2026, 3, 4), "COMPRA", -100)], before_cents=10000, **MARCH)
    rows = [CURRENT_HEADER, ["04/03/2026", "contract cash row", "S/", -1.0, "000123"]]
    held = transaction_count(client, account_id)

    def refusal(call) -> None:
        err = refused_writing_nothing(client, call)
        assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "CASH_TAKES_NO_STATEMENT")
        assert transaction_count(client, account_id) == held

    body = statement_create_body(account_id, "2026-03-01", "2026-03-31")
    refusal(lambda: client.post("/statements", json_body=body))
    assert refused(lambda: client.get(f"/statements/{body['id']}")).status == 404
    for dry_run in (True, False):
        refusal(lambda d=dry_run: send_statement(client, account_id, paper, dry_run=d))
        refusal(lambda d=dry_run: send_download(client, account_id, rows, dry_run=d))
    assert client.get("/statements", params={"account_id": account_id})["items"] == []


def test_a_person_may_be_named_efectivo_beside_a_cash_account(client, scratch, cash):
    """`Efectivo` is no held name: a person named `Efectivo` is created
    (contract: "What an account is", "The cash account"). The person cannot carry the
    `contract-` prefix, since its name is what the test checks; `leaves_nothing` still flags it
    if teardown fails."""
    person = scratch.account("PEN", person=True, name="Efectivo")
    assert client.get(f"/accounts/{person}")["name"] == "Efectivo"


def test_no_other_account_may_take_a_held_cash_name(client, scratch, cash):
    """A person named for a live cash account's name in other letters is `409` `NAME_EXISTS`
    on `name`, writing nothing (contract: "What an account is", "The cash account"). The name
    cannot carry the `contract-` prefix, since it is what the test checks."""
    body = {
        "id": str(uuid4()),
        "kind": "person",
        "name": cash["name"].lower(),
        "currencies": [{"currency_code": "PEN"}],
    }
    scratch.accounts.append(body["id"])
    err = refused_writing_nothing(client, lambda: client.post("/accounts", json_body=body))
    assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")
