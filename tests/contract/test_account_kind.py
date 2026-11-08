"""Contract: an account becomes a person and back, and is archived whole, against a real engine.

`POST /accounts/{id}/make-person` turns a bank account into a person (its body the person's
`name`) and `POST /accounts/{id}/make-account` turns it back (its body a `bank_code` and a
`last4`), each acting on the account, every currency of it with it
(contract: POST /v1/accounts/{account_id}/make-person)
(contract: POST /v1/accounts/{account_id}/make-account).
Manage ▸ Accounts sends both, so only the engine can say what they keep, where the account
moves and what they refuse.

What it pins, in the order the app meets it:

1. Either way the account keeps its id, colour, statement code and currencies, each
   currency its balance and its opening balance (the same transaction, so each currency's
   `opening_balance_transaction_id` is the same before and after), `version` goes up by one,
   and it moves group: listed only with `?include_people=true` and in `/dashboard`'s `people`
   as a person, every currency in its row, listed without the flag and in `bank_accounts` as
   a bank account. Its `sort_order` joins the end of its new group.
2. Each refusal is `409` `CONFLICT` keyed on `account_id`, and nothing is written (every account
   read the same before and after), in the engine's order
   (contract: POST /v1/accounts/{account_id}/make-person, "Refusals"):
   `404`, then `ACCOUNT_ARCHIVED`, then `KIND_UNCHANGED`, then `HAS_RECONCILIATION`,
   which a draft, a completed and a deleted statement each cause.
3. `PUT /accounts/{id}` takes no `is_person`: `UNKNOWN_FIELD`, whatever its value.
4. Archive and unarchive act on the account whole, every currency at once, and on a person as
   on a bank account; a transaction in any currency of an archived account is `INVALID_REFERENCE`
   on `account_id` (contract: "Bank Accounts", "No new rows on it").
5. A person is refused `POST /statements` as `PERSON_TAKES_NO_STATEMENT` on `account_id`
   (contract: "What an account is", "Its kind").
6. A `make-person` sent again under the same `X-Idempotency-Key` is replayed: the same answer,
   and the account flipped once (contract: "Base Conventions", "Idempotency").

Every account is fresh per run (a person named by its UUID, a bank account numbered from the
suite's range) and removed by the `scratch` fixture.
Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from expense import http as http_module
from tests.contract.conftest import (
    all_accounts,
    assert_refusal,
    free_statement_codes,
    kind_change,
    live_ids,
    refused,
    refused_writing_nothing,
    statement_create_body,
)

_ROUTES = ("make-person", "make-account")
_KEPT = ("id", "name", "color", "statement_code", "is_archived", "currencies")
#: What a kind change keeps: its name is the one it is given (the person's, or the one built).
_KEPT_BY_KIND = tuple(key for key in _KEPT if key != "name")


def _ids(rows) -> set[str]:
    return {row["id"] for row in rows or []}


def _row(rows, account_id: str) -> dict:
    return next(row for row in rows if row["id"] == account_id)


def _conflict(err, reason: str) -> None:
    """A `409` `CONFLICT` keyed on `account_id` alone, carrying `reason` there."""
    assert_refusal(err, 409, "CONFLICT", "account_id", reason)


def _assert_kept(after: dict, before: dict) -> None:
    for key in _KEPT_BY_KIND:
        assert after[key] == before[key], key
    assert after["version"] == before["version"] + 1


def _assert_is_person(client, account_id: str, currencies: list[str]) -> None:
    listed = client.get("/accounts", params={"include_people": "true"})["items"]
    assert account_id in _ids(listed)
    assert account_id not in _ids(client.get("/accounts")["items"])
    dashboard = client.get("/dashboard")
    assert account_id not in _ids(dashboard["bank_accounts"])
    shown = _row(dashboard["people"], account_id)
    assert [c["currency_code"] for c in shown["currencies"]] == currencies


def _assert_is_real(client, account_id: str, currencies: list[str]) -> None:
    assert account_id in _ids(client.get("/accounts")["items"])
    dashboard = client.get("/dashboard")
    assert account_id not in _ids(dashboard["people"])
    shown = _row(dashboard["bank_accounts"], account_id)
    assert [c["currency_code"] for c in shown["currencies"]] == currencies


def test_an_account_becomes_a_person_and_back_whole(client, scratch):
    """The account holding soles and dollars, an opening balance in soles and a row in
    dollars, turns into a person and back: the keys in `_KEPT_BY_KIND` (id, colour, statement code,
    archive state and every currency with its balance) are the same, the name is the one the
    change gives (the person's sent name, then the built one), `version` is up by one
    each time, `sort_order` joins the new group's end and `updated_at` moves with the write;
    the opening balance's transaction is the same one each time
    (contract: POST /v1/accounts/{account_id}/make-person)."""
    (code,) = free_statement_codes(client, 1)
    first = scratch.account("PEN", "USD", code=code)
    second = scratch.account("PEN")
    scratch.opening_balance(first, "2026-01-01", "PEN", 50000)
    scratch.row(first, "2026-03-10", -4250, "PEN")
    scratch.row(first, "2026-03-11", 700, "USD")
    seeded = client.get(f"/accounts/{first}")
    assert seeded["is_person"] is False
    assert [c["current_balance_cents"] for c in seeded["currencies"]] == [45750, 700]
    assert seeded["currencies"][0]["opening_balance_transaction_id"] is not None
    assert seeded["currencies"][1]["opening_balance_transaction_id"] is None
    before_ids = live_ids(client, first)
    assert len(before_ids) == 3

    # To a person: everything kept, version up by one, moved to the people's group.
    people_orders = [a["sort_order"] for a in all_accounts(client) if a["is_person"]]
    person = _post(client, first, "make-person")
    assert person["is_person"] is True
    assert person["name"].startswith("contract-kind-")
    _assert_kept(person, seeded)
    assert client.get(f"/accounts/{first}") == person
    assert live_ids(client, first) == before_ids
    _assert_is_person(client, first, ["PEN", "USD"])
    assert all(person["sort_order"] > order for order in people_orders)

    # The next account to become a person lands right after it.
    second_person = _post(client, second, "make-person")
    assert second_person["sort_order"] == person["sort_order"] + 1

    # And back: the mirror, at the end of the bank accounts.
    real_orders = [a["sort_order"] for a in all_accounts(client) if not a["is_person"]]
    real = _post(client, first, "make-account")
    assert real["is_person"] is False
    assert real["name"] == f"{real['bank_code']}-{real['numbers'][0]['last4']}"
    _assert_kept(real, person)
    assert real["currencies"] == seeded["currencies"]
    assert client.get(f"/accounts/{first}") == real
    assert live_ids(client, first) == before_ids
    _assert_is_real(client, first, ["PEN", "USD"])
    assert all(real["sort_order"] > order for order in real_orders)

    second_real = _post(client, second, "make-account")
    assert second_real["sort_order"] == real["sort_order"] + 1


def test_a_person_made_by_post_accounts_converts_too(client, scratch):
    """A person created with `is_person: true` and two currencies in one write is turned
    into a bank account with both currencies, and back."""
    person_id = scratch.account("PEN", "USD", person=True)
    made = client.get(f"/accounts/{person_id}")
    assert made["is_person"] is True
    assert [c["currency_code"] for c in made["currencies"]] == ["PEN", "USD"]

    real = _post(client, person_id, "make-account")
    assert real["is_person"] is False
    _assert_kept(real, made)
    _assert_is_real(client, person_id, ["PEN", "USD"])

    again = _post(client, person_id, "make-person")
    assert again["is_person"] is True
    _assert_kept(again, real)
    _assert_is_person(client, person_id, ["PEN", "USD"])


def test_an_account_already_of_that_kind_is_kind_unchanged(client, scratch):
    account_id = scratch.account("PEN", "USD")
    person_id = scratch.account("PEN", "USD", person=True)

    for target, route in ((account_id, "make-account"), (person_id, "make-person")):
        err = refused_writing_nothing(client, lambda t=target, r=route: _post(client, t, r))
        _conflict(err, "KIND_UNCHANGED")


def _post(client, account_id: str, route: str):
    return kind_change(client, account_id, route)


def test_an_account_with_a_statement_cannot_become_a_person(client, scratch):
    """A draft, a completed and a deleted statement each make `make-person` refuse
    `HAS_RECONCILIATION`, writing nothing; a deleted one still counts because it holds the
    account's balances (contract: POST /v1/accounts/{account_id}/make-person, "Refusals").
    The same bank account sent to `make-account` is `KIND_UNCHANGED`, which comes before
    `HAS_RECONCILIATION` (contract: POST /v1/accounts/{account_id}/make-account, "Refusals")."""

    def kind_unchanged(target: str) -> None:
        err = refused_writing_nothing(client, lambda: _post(client, target, "make-account"))
        _conflict(err, "KIND_UNCHANGED")

    draft_only = scratch.account("PEN", "USD")
    scratch.statement(draft_only, "2026-04-01", "2026-04-30", "PEN")
    err = refused_writing_nothing(client, lambda: _post(client, draft_only, "make-person"))
    _conflict(err, "HAS_RECONCILIATION")
    kind_unchanged(draft_only)

    account_id = scratch.account()
    row = scratch.row(account_id, "2026-04-10", -1200)
    closed = scratch.completed(account_id, "2026-04-01", "2026-04-30", row["id"])
    assert closed["status"] == 2
    err = refused_writing_nothing(client, lambda: _post(client, account_id, "make-person"))
    _conflict(err, "HAS_RECONCILIATION")
    kind_unchanged(account_id)

    assert client.post(f"/statements/{closed['id']}/revert")["status"] == 1
    err = refused_writing_nothing(client, lambda: _post(client, account_id, "make-person"))
    _conflict(err, "HAS_RECONCILIATION")
    kind_unchanged(account_id)

    client.delete(f"/statements/{closed['id']}")
    err = refused_writing_nothing(client, lambda: _post(client, account_id, "make-person"))
    _conflict(err, "HAS_RECONCILIATION")
    kind_unchanged(account_id)
    assert client.get(f"/accounts/{account_id}")["is_person"] is False


def test_an_archived_account_keeps_its_kind_whatever_else_applies(client, scratch):
    """`ACCOUNT_ARCHIVED` comes before the others on both routes: for an archived bank account
    (where `make-account` is also `KIND_UNCHANGED`), an archived person (where `make-person` is
    also `KIND_UNCHANGED`) and an archived account with a statement (where `make-person` is
    also `HAS_RECONCILIATION` and `make-account` is also `KIND_UNCHANGED`). So only that order
    passes."""
    account_id = scratch.account("PEN", "USD")
    person_id = scratch.account("PEN", "USD", person=True)
    stated_id = scratch.account("PEN", "USD")
    scratch.statement(stated_id, "2026-04-01", "2026-04-30", "PEN")
    for target in (account_id, person_id, stated_id):
        scratch.archive(target)

    cases = [(t, r) for t in (account_id, person_id) for r in _ROUTES]
    cases += [(stated_id, "make-person"), (stated_id, "make-account")]
    for target, route in cases:
        err = refused_writing_nothing(client, lambda t=target, r=route: _post(client, t, r))
        _conflict(err, "ACCOUNT_ARCHIVED")


def test_an_unknown_or_deleted_account_is_not_found(client, scratch):
    """`404` on both routes: an unknown id, and a deleted bank account, which would be
    `KIND_UNCHANGED` on `make-account` if it were read."""
    gone = scratch.account()
    client.delete(f"/accounts/{gone}")
    for target in (str(uuid4()), gone):
        for route in _ROUTES:
            err = refused_writing_nothing(client, lambda t=target, r=route: _post(client, t, r))
            assert (err.status, err.code) == (404, "NOT_FOUND"), (target, route)


@pytest.mark.parametrize("value", [True, False])
def test_put_accounts_takes_no_kind(client, scratch, value):
    """`is_person` is not a field of `PUT /accounts/{id}`, whatever its value
    (contract: PUT /v1/accounts/{account_id})."""
    account_id = scratch.account("PEN", "USD", person=not value)
    err = refused_writing_nothing(
        client, lambda: client.put(f"/accounts/{account_id}", json_body={"is_person": value})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "is_person", "UNKNOWN_FIELD")
    assert client.get(f"/accounts/{account_id}")["is_person"] is (not value)


def test_archive_and_unarchive_act_on_every_currency_at_once(client, scratch):
    """An account of soles and dollars, and a person of both, archive and unarchive whole:
    one request, one `version` bump, both currencies kept in the row; a row in either currency
    is refused `INVALID_REFERENCE` on `account_id` while archived, on `POST /transactions` and
    in a batch alike, and lands once unarchived.
    (contract: "Bank Accounts", "No new rows on it")"""
    account_id = scratch.account("PEN", "USD")
    person_id = scratch.account("PEN", "USD", person=True)
    for target, panel in ((account_id, "archived_accounts"), (person_id, "archived_people")):
        before = client.get(f"/accounts/{target}")
        assert before["is_archived"] is False
        archived = client.post(f"/accounts/{target}/archive")
        assert archived["is_archived"] is True
        assert archived["version"] == before["version"] + 1
        assert archived["currencies"] == before["currencies"]
        for key in _KEPT:
            if key != "is_archived":
                assert archived[key] == before[key], key
        listed = client.get("/accounts", params={"include_people": "true"})["items"]
        assert target not in _ids(listed)
        kept = _row(all_accounts(client), target)
        assert kept["is_archived"] is True
        shown = client.get("/dashboard", params={"include_archived": "true"})[panel]
        assert [c["currency_code"] for c in _row(shown, target)["currencies"]] == ["PEN", "USD"]

        held = live_ids(client, target)
        for currency in ("PEN", "USD"):
            for batch in (False, True):
                err = scratch.refused_row(target, scratch.at("2026-03-10"), currency, batch=batch)
                key = "transactions.0.account_id" if batch else "account_id"
                assert_refusal(err, 422, "VALIDATION_ERROR", key, "INVALID_REFERENCE")
        assert live_ids(client, target) == held

        restored = client.post(f"/accounts/{target}/unarchive")
        assert restored["is_archived"] is False
        assert restored["version"] == archived["version"] + 1
        for currency in ("PEN", "USD"):
            scratch.row(target, "2026-03-10", -100, currency)
        assert len(live_ids(client, target)) == len(held) + 2


def test_archiving_again_and_unarchiving_a_live_account_are_allowed(client, scratch):
    """Both still bump the account's `version`
    (contract: POST /v1/accounts/{account_id}/archive)
    (contract: POST /v1/accounts/{account_id}/unarchive)."""
    account_id = scratch.account("PEN", "USD")
    version = client.get(f"/accounts/{account_id}")["version"]
    assert client.post(f"/accounts/{account_id}/unarchive")["version"] == version + 1
    scratch.archive(account_id)
    again = client.post(f"/accounts/{account_id}/archive")
    assert again["is_archived"] is True
    assert again["version"] == version + 3
    for route in ("archive", "unarchive"):
        err = refused(lambda r=route: _post(client, str(uuid4()), r))
        assert (err.status, err.code) == (404, "NOT_FOUND"), route


def test_a_person_takes_no_statement(client, scratch):
    """`POST /statements` naming a person, made with `is_person` or turned into one, is
    `422` `PERSON_TAKES_NO_STATEMENT` on `account_id`, writing nothing. The order is the
    contract's (contract: POST /v1/statements, "Order"): it comes before a currency the
    person does not hold and before the archive, so those cases pass only if the person
    refusal is first. A person turned back with `make-account` takes the very statement
    refused before, under the same id, which proves the refusal wrote nothing (contract:
    POST /v1/accounts/{account_id}/make-account, "Refusals")."""
    made = scratch.account("PEN", "USD", person=True)
    converted = scratch.account("PEN")
    _post(client, converted, "make-person")
    archived = scratch.account("PEN", person=True)
    scratch.archive(archived)
    cases = [
        (made, ["PEN", "USD"]),
        (converted, ["PEN"]),
        (archived, ["USD"]),
    ]
    bodies: list[dict] = []
    for person_id, codes in cases:
        body = statement_create_body(person_id, "2026-04-01", "2026-04-30", *codes)
        bodies.append(body)
        err = refused_writing_nothing(
            client, lambda b=body: client.post("/statements", json_body=b)
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "PERSON_TAKES_NO_STATEMENT")
        missing = refused(lambda b=body: client.get(f"/statements/{b['id']}"))
        assert missing.status == 404

    # Turned back into a bank account, the converted one takes the statement refused above.
    _post(client, converted, "make-account")
    refused_body = next(b for b in bodies if b["account_id"] == converted)
    scratch.statements.append(refused_body["id"])
    created = client.post("/statements", json_body=refused_body)
    assert (created["id"], created["account_id"]) == (refused_body["id"], converted)

    # A different account: an archived bank account holding no dollars. The held currency
    # comes before the archive, so that is the refusal there.
    plain = scratch.account("PEN")
    scratch.archive(plain)
    body = statement_create_body(plain, "2026-04-01", "2026-04-30", "USD")
    err = refused_writing_nothing(client, lambda: client.post("/statements", json_body=body))
    assert_refusal(err, 422, "VALIDATION_ERROR", "balances.0.currency_code", "CURRENCY_NOT_HELD")


def test_make_person_sent_again_under_its_key_is_replayed(client, scratch, monkeypatch):
    """The client mints one key per logical write (expense/http.py); the key is held fixed
    here, so the second send is the same logical write sent again, as a retry sends it. Not
    replayed, it would be `KIND_UNCHANGED`."""
    account_id = scratch.account("PEN", "USD")
    version = client.get(f"/accounts/{account_id}")["version"]

    key = uuid4()
    monkeypatch.setattr(http_module, "uuid", SimpleNamespace(uuid4=lambda: key))
    body = {"name": f"contract-kind-{uuid4().hex[:8]}"}
    first = client.post(f"/accounts/{account_id}/make-person", json_body=body)
    again = client.post(f"/accounts/{account_id}/make-person", json_body=body)
    monkeypatch.undo()

    assert again == first
    after = client.get(f"/accounts/{account_id}")
    assert after["is_person"] is True
    assert after["version"] == version + 1
