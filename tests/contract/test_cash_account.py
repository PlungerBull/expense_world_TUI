"""Contract: the cash account, against a real engine.

A user's cash is an account of kind `cash`: made by `POST /accounts` with `kind: "cash"`, named
`Efectivo` by the engine, at no bank and with no numbers, one per user, archived or not
(contract: "What an account is", "The cash account"). The New and Edit forms and Home send it,
so only the engine can say what it refuses.

What it pins:

1. The account's shape: kind `cash`, name `Efectivo`, `bank_code` and `statement_code` null,
   `numbers` empty; its row in `/dashboard`'s `accounts` as `{id, name, kind, currencies}`, and
   in `archived_accounts` once archived, back in `accounts` once unarchived
   (contract: GET /v1/dashboard, "Field rules").
2. `CASH_EXISTS`, `409` on `kind`, for a second cash account while the first is live and while
   it is archived, writing nothing (contract: POST /v1/accounts).
3. `CASH_TAKES_NO_FIELD`, `422` on each field sent: `name`, `bank_code`, `last4` and
   `statement_code` on a create (`null` included), `name`, `bank_code`, `current_number`,
   `new_number` and `statement_code` on an update (`null` included for `name`,
   `current_number` and `statement_code`; `bank_code` and `new_number` `null` are `NOT_NULL`),
   writing nothing
   (contract: POST /v1/accounts, "Forbidden") (contract: PUT /v1/accounts/{account_id}).
4. `CASH_KIND_FIXED`, `409` on `account_id`, for `make-person` and `make-account`, live or
   archived (contract: POST /v1/accounts/{account_id}/make-person, "Refusals").
5. `CASH_NOT_DELETABLE`, `409` on `account_id`, for a delete, live or archived
   (contract: DELETE /v1/accounts/{account_id}, "Refusals").
6. `CASH_TAKES_NO_STATEMENT`, `422` on `account_id`, for `POST /statements`,
   `POST /statements/import` and `POST /transactions/import`, the two uploads on a dry run as
   on an apply, writing nothing.
7. The name is held like a person's: once the account exists a person named `Efectivo`, in any
   case, is `NAME_EXISTS` on `name`; and a user holding such a person cannot make the cash
   account, `NAME_EXISTS` keyed `kind`. The second is checked as the reserved-names practice user,
   who holds no cash account; the person goes in the same test.

What it cannot pin: the cash account is never deleted, so a practice user keeps the one the
first run makes. The create of the account itself (its `201` with no name, bank or number, its
name `Efectivo`) is asserted by the run that makes it, the first on a fresh practice user; a
later run finds the account and proves its shape (1) instead. The shared practice user is left
as found: the account stays, live or archived as it was, and the test does not fail for it
(`cash` below; `holdings` in scripts/clean_practice_user.py leaves it out of the leak check).
The reserved-names user is never given one.

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from expense.errors import EngineError
from tests.contract.conftest import (
    CURRENT_HEADER,
    PaperRow,
    all_accounts,
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
_CASH_ONLY = "Efectivo"
_NOT_CASH_FOR_KIND = "Must be an account that is not the cash account: its kind never changes."
_NOT_CASH_FOR_DELETE = "Must be an account that is not the cash account: archive it instead."
_NOT_CASH_FOR_STATEMENT = "Must not be the cash account: cash has no bank statements."


def _cash_body() -> dict:
    """A `POST /accounts` body for the cash account under a fresh id: its kind and one
    currency, nothing else (contract: POST /v1/accounts, "Required")."""
    return {"id": str(uuid4()), "kind": "cash", "currencies": [{"currency_code": "PEN"}]}


@pytest.fixture
def cash(client):
    """The shared practice user's cash account, live for the test, as `(id, made)` in a
    namespace: found among every account (archived ones included) or made once; `made` is the
    `201` answer when this test made it, else `None`. At teardown its archive state is what
    it was found in, best effort. It is never deleted: the engine refuses it."""
    found = next((a for a in all_accounts(client) if a["kind"] == "cash"), None)
    made = None
    if found is None:
        body = _cash_body()
        made = client.post("/accounts", json_body=body)
        account_id, was_archived = made["id"], False
    else:
        account_id, was_archived = found["id"], found["is_archived"]
        if was_archived:
            client.post(f"/accounts/{account_id}/unarchive")
    yield SimpleNamespace(id=account_id, made=made)
    try:
        now = client.get(f"/accounts/{account_id}")["is_archived"]
        if now != was_archived:
            client.post(f"/accounts/{account_id}/{'archive' if was_archived else 'unarchive'}")
    except EngineError:
        pass


def _both_states(client, account_id: str):
    """The cash account live, then archived, yielding each time; unarchived after, whatever
    happens in between."""
    try:
        yield "live"
        client.post(f"/accounts/{account_id}/archive")
        yield "archived"
    finally:
        client.post(f"/accounts/{account_id}/unarchive")


def test_the_cash_account_is_named_efectivo_and_has_no_bank_or_number(client, cash):
    """Made with no name, bank, number or statement code (the run that makes it also asserts the
    `201`'s answer), it reads `kind` `cash`, name `Efectivo`, `bank_code` null, `numbers` empty
    and no statement code, and is listed without `?include_people=true`
    (contract: "What an account is", "The cash account")."""
    if cash.made is not None:
        assert cash.made["kind"] == "cash"
        assert cash.made["name"] == _CASH_ONLY
        assert cash.made["currencies"][0]["currency_code"] == "PEN"
    read = client.get(f"/accounts/{cash.id}")
    assert read["kind"] == "cash"
    assert read["name"] == _CASH_ONLY
    assert read["bank_code"] is None
    assert read["numbers"] == []
    assert read["statement_code"] is None
    assert read["is_archived"] is False
    assert [a["id"] for a in client.get("/accounts")["items"]].count(cash.id) == 1


def test_the_cash_account_has_its_row_in_the_dashboard_and_archives_whole(client, cash):
    """`/dashboard` lists it in `accounts` as `{id, name, kind, currencies}` with kind `cash`;
    archived it moves, every currency in its row, to `archived_accounts`, and unarchived it
    returns (contract: GET /v1/dashboard, "Field rules")."""
    row = next(r for r in client.get("/dashboard")["accounts"] if r["id"] == cash.id)
    assert set(row) == {"id", "name", "kind", "currencies"}
    assert (row["name"], row["kind"]) == (_CASH_ONLY, "cash")
    assert [c["currency_code"] for c in row["currencies"]] == ["PEN"]

    for state in _both_states(client, cash.id):
        asked = client.get("/dashboard", params={"include_archived": "true"})
        in_live = [r["id"] for r in asked["accounts"]]
        in_archived = [r["id"] for r in asked["archived_accounts"]]
        if state == "live":
            assert cash.id in in_live and cash.id not in in_archived
        else:
            assert cash.id in in_archived and cash.id not in in_live
            moved = next(r for r in asked["archived_accounts"] if r["id"] == cash.id)
            assert (moved["name"], moved["kind"]) == (_CASH_ONLY, "cash")
            assert not any(r["id"] == cash.id for r in asked["people"])
    assert any(r["id"] == cash.id for r in client.get("/dashboard")["accounts"])


def test_a_second_cash_account_is_cash_exists_live_or_archived(client, cash):
    """With the cash account live, then archived, another `kind: "cash"` create is `409`
    `CASH_EXISTS` on `kind`, writing nothing (every account the same before and after)
    (contract: POST /v1/accounts)."""
    for state in _both_states(client, cash.id):
        body = _cash_body()
        err = refused_writing_nothing(client, lambda b=body: client.post("/accounts", json_body=b))
        assert_refusal(err, 409, "CONFLICT", "kind", "CASH_EXISTS")
        assert err.fields["kind"], state
        assert refused(lambda b=body: client.get(f"/accounts/{b['id']}")).status == 404


def test_a_create_naming_a_field_the_cash_account_never_takes_is_refused(client, cash):
    """Each of `name`, `bank_code`, `last4` and `statement_code`, with a value or `null`, is
    `422` `CASH_TAKES_NO_FIELD` on that field; all four at once are one answer naming each.
    This is judged before the second account is, so it holds with the cash account existing
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
    `statement_code` are each `422` `CASH_TAKES_NO_FIELD` on the field sent, and all of them at
    once are one answer; nothing is written. A `null` `name`, `current_number` and
    `statement_code` is the same refusal, while a `null` `bank_code` or `new_number` is
    `NOT_NULL` (a shape refusal, judged first). A `color` alone is taken and put back
    (contract: PUT /v1/accounts/{account_id})."""
    (code,) = free_statement_codes(client, 1)
    sent = {
        "name": "Mi caja",
        "bank_code": bank_code(),
        "current_number": {"start_date": "2026-04-10"},
        "new_number": {"last4": next_last4(), "start_date": "2026-04-10"},
        "statement_code": code,
    }
    cases = [{key: value} for key, value in sent.items()]
    cases += [{key: None} for key in ("name", "current_number", "statement_code")]
    cases.append(dict(sent))
    for body in cases:
        err = refused_writing_nothing(
            client, lambda b=body: client.put(f"/accounts/{cash.id}", json_body=b)
        )
        reasons = dict.fromkeys(body, "CASH_TAKES_NO_FIELD")
        assert_refusals(err, 422, "VALIDATION_ERROR", reasons)

    for key in ("bank_code", "new_number"):
        err = refused_writing_nothing(
            client, lambda k=key: client.put(f"/accounts/{cash.id}", json_body={k: None})
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", key, "NOT_NULL")

    before = client.get(f"/accounts/{cash.id}")
    changed = client.put(f"/accounts/{cash.id}", json_body={"color": "#123456"})
    assert changed["color"] == "#123456"
    client.put(f"/accounts/{cash.id}", json_body={"color": before["color"]})


def test_the_cash_accounts_kind_never_changes(client, cash):
    """`make-person` and `make-account` are each `409` `CASH_KIND_FIXED` on `account_id`
    with the contract's words, live and archived alike (the archive is not asked about),
    writing nothing (contract: POST /v1/accounts/{account_id}/make-person, "Refusals")."""
    for state in _both_states(client, cash.id):
        for route in ("make-person", "make-account"):
            err = refused_writing_nothing(client, lambda r=route: kind_change(client, cash.id, r))
            assert_refusal(err, 409, "CONFLICT", "account_id", "CASH_KIND_FIXED")
            assert err.fields["account_id"] == _NOT_CASH_FOR_KIND, (state, route)
    assert client.get(f"/accounts/{cash.id}")["kind"] == "cash"


def test_the_cash_account_is_never_deleted(client, cash):
    """A delete is `409` `CASH_NOT_DELETABLE` on `account_id` with the contract's words, live
    and archived alike, and the account is still listed after
    (contract: DELETE /v1/accounts/{account_id}, "Refusals")."""
    for state in _both_states(client, cash.id):
        err = refused_writing_nothing(client, lambda: client.delete(f"/accounts/{cash.id}"))
        assert_refusal(err, 409, "CONFLICT", "account_id", "CASH_NOT_DELETABLE")
        assert err.fields["account_id"] == _NOT_CASH_FOR_DELETE, state
        assert client.get(f"/accounts/{cash.id}")["name"] == _CASH_ONLY


def test_the_cash_account_takes_no_statement_on_any_of_the_three_writes(client, cash):
    """`POST /statements`, `POST /statements/import` and `POST /transactions/import`, each
    naming the cash account, are `422` `CASH_TAKES_NO_STATEMENT` on `account_id` with the
    contract's words; the uploads on a dry run as on an apply. Nothing is written: no
    transaction on the account, no statement under the id sent
    (contract: POST /v1/statements, "Order")
    (contract: POST /v1/statements/import, "Accounts")
    (contract: POST /v1/transactions/import, "Accounts")."""
    paper = savings_paper([PaperRow(date(2026, 3, 4), "COMPRA", -100)], before_cents=10000, **MARCH)
    rows = [CURRENT_HEADER, ["04/03/2026", "contract cash row", "S/", -1.0, "000123"]]
    held = transaction_count(client, cash.id)

    def refusal(call) -> None:
        err = refused_writing_nothing(client, call)
        assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "CASH_TAKES_NO_STATEMENT")
        assert err.fields["account_id"] == _NOT_CASH_FOR_STATEMENT
        assert transaction_count(client, cash.id) == held

    body = statement_create_body(cash.id, "2026-03-01", "2026-03-31")
    refusal(lambda: client.post("/statements", json_body=body))
    assert refused(lambda: client.get(f"/statements/{body['id']}")).status == 404
    for dry_run in (True, False):
        refusal(lambda d=dry_run: send_statement(client, cash.id, paper, dry_run=d))
        refusal(lambda d=dry_run: send_download(client, cash.id, rows, dry_run=d))
    assert client.get("/statements", params={"account_id": cash.id})["items"] == []


def test_a_person_named_efectivo_is_refused_once_the_cash_account_exists(client, cash):
    """The name is held like a person's: a create of a person named `Efectivo`, in any case, is
    `409` `NAME_EXISTS` on `name`, writing nothing
    (contract: "What an account is", "The cash account")."""
    for name in ("Efectivo", "EFECTIVO"):
        body = {
            "id": str(uuid4()),
            "kind": "person",
            "name": name,
            "currencies": [{"currency_code": "PEN"}],
        }
        err = refused_writing_nothing(client, lambda b=body: client.post("/accounts", json_body=b))
        assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")


def test_a_person_named_efectivo_keeps_the_cash_account_from_being_made(reserved_client):
    """As the reserved-names user, who holds no cash account, a person named `Efectivo` makes
    a `kind: "cash"` create `409` `NAME_EXISTS` keyed `kind` (not `name`: the cash account
    sends none), and nothing is written. The person is deleted after, and the user is left
    without a cash account (contract: POST /v1/accounts)."""
    held = all_accounts(reserved_client)
    assert not [a for a in held if a["kind"] == "cash"], (
        "the reserved-names user holds a cash account, which cannot be deleted; this test "
        "needs it to hold none"
    )
    person = str(uuid4())
    reserved_client.post(
        "/accounts",
        json_body={
            "id": person,
            "kind": "person",
            "name": _CASH_ONLY,
            "currencies": [{"currency_code": "PEN"}],
        },
    )
    try:
        body = _cash_body()
        err = refused_writing_nothing(
            reserved_client, lambda: reserved_client.post("/accounts", json_body=body)
        )
        assert_refusal(err, 409, "CONFLICT", "kind", "NAME_EXISTS")
        assert err.fields["kind"]
    finally:
        reserved_client.delete(f"/accounts/{person}")
    assert [a["id"] for a in all_accounts(reserved_client)] == [a["id"] for a in held]
