"""Contract: a real account becomes a person and back, against a real engine.

`POST /accounts/{id}/make-person` turns a real account into a person account and
`POST /accounts/{id}/make-account` turns it back, each taking no body (contract: POST
/v1/accounts/{account_id}/make-person) (contract: POST
/v1/accounts/{account_id}/make-account). Manage ▸ Accounts sends both, so only the
engine can say what they keep, where the account moves and what they refuse.

What it pins, in the order the app meets it:

1. Either way the account keeps its id, name, currency, colour, balance and transactions,
   `version` goes up by one, and it moves group: listed only with
   `?include_people=true` and in `/dashboard`'s `people` as a person, listed without
   the flag and in `bank_accounts` as a real account. Its `sort_order` joins the end of
   its new group: above every one there, and the next account to cross after it lands
   one above it. The contract counts deleted accounts too, which no read shows, so two
   conversions in a row pin the "one more" exactly.
2. Each refusal is `409` `CONFLICT` keyed on `account_id`, and nothing is written (the
   `version` re-read is unchanged): `KIND_UNCHANGED` on each route for an account
   already of that kind, `HAS_OPENING_BALANCE` on `make-person` for an account with an
   opening balance (it goes through once that transaction is deleted), and
   `ACCOUNT_ARCHIVED` on both routes for an archived account and an archived person,
   returned first when another refusal also applies (contract: POST
   /v1/accounts/{account_id}/archive).
3. An unknown id is `404` on both routes.
4. A `make-person` sent again under the same `X-Idempotency-Key` is replayed: the same
   answer, and the account flipped once (contract: "Base Conventions", "Idempotency").

Every account is fresh per run (named by its UUID) and deleted at the end, with its
transactions. Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from expense import http as http_module
from expense.errors import EngineError
from tests.contract.conftest import reason_on

_ROUTES = ("make-person", "make-account")


def _safe_delete(client, path):
    try:
        client.delete(path)
    except EngineError:
        pass


def _safe_post(client, path):
    try:
        client.post(path)
    except EngineError:
        pass


def _refused(call) -> EngineError:
    with pytest.raises(EngineError) as excinfo:
        call()
    return excinfo.value


def _assert_refusal(err: EngineError, reason: str) -> None:
    """A `409` `CONFLICT` keyed on `account_id` alone, carrying `reason` there
    (contract: "Base Conventions", "`fields` and `reasons` semantics")."""
    assert (err.status, err.code) == (409, "CONFLICT"), (err.status, err.code)
    assert isinstance(err.fields, dict) and set(err.fields) == {"account_id"}
    assert isinstance(err.reasons, dict) and set(err.reasons) == {"account_id"}
    assert reason_on(err, "account_id") == reason


def _make_account(client, new_id: str) -> None:
    client.post(
        "/accounts",
        json_body={"id": new_id, "name": f"contract-kind-{new_id[:8]}", "currency_code": "PEN"},
    )


def _make_person(client, new_id: str) -> None:
    client.post(
        "/people",
        json_body={
            "id": new_id,
            "name": f"contract-kind-person-{new_id[:8]}",
            "currency_code": "PEN",
        },
    )


def _make_transaction(client, tx_id: str, account_id: str, amount: int) -> None:
    client.post(
        "/transactions",
        json_body={
            "id": tx_id,
            "title": "contract kind",
            "amount_cents": amount,
            "account_id": account_id,
            "date": "2026-03-10T12:00:00Z",
        },
    )


def _transaction_ids(client, account_id: str) -> set[str]:
    listed = client.get("/transactions", params={"account_id": account_id})
    return {item["id"] for item in listed["items"]}


def _all_accounts(client) -> list[dict]:
    """Every account a read shows: real ones and people, archived ones included."""
    params = {"include_people": "true", "include_archived": "true"}
    return client.get("/accounts", params=params)["items"]


def _ids(rows) -> set[str]:
    return {row.get("id") for row in rows or []}


def _assert_kept(after: dict, before: dict) -> None:
    for key in ("id", "name", "currency_code", "color", "current_balance_cents"):
        assert after[key] == before[key], key
    assert after["version"] == before["version"] + 1
    assert after["is_archived"] is False


def _assert_is_person(client, account_id: str) -> None:
    assert account_id in _ids(client.get("/accounts", params={"include_people": "true"})["items"])
    assert account_id not in _ids(client.get("/accounts")["items"])
    dashboard = client.get("/dashboard")
    assert account_id in _ids(dashboard["people"])
    assert account_id not in _ids(dashboard["bank_accounts"])


def _assert_is_real(client, account_id: str) -> None:
    assert account_id in _ids(client.get("/accounts")["items"])
    with_people = client.get("/accounts", params={"include_people": "true"})["items"]
    row = next(a for a in with_people if a["id"] == account_id)
    assert row["is_person"] is False
    dashboard = client.get("/dashboard")
    assert account_id in _ids(dashboard["bank_accounts"])
    assert account_id not in _ids(dashboard["people"])


def test_an_account_becomes_a_person_and_back(client):
    first_id = str(uuid4())
    second_id = str(uuid4())
    tx_ids = [str(uuid4()), str(uuid4())]

    try:
        _make_account(client, first_id)
        _make_account(client, second_id)
        _make_transaction(client, tx_ids[0], first_id, -4250)
        _make_transaction(client, tx_ids[1], first_id, 10000)

        before = client.get(f"/accounts/{first_id}")
        assert before["is_person"] is False
        assert before["current_balance_cents"] == 5750
        assert _transaction_ids(client, first_id) == set(tx_ids)

        # 1 — to a person: everything kept, version up by one, moved to the people.
        people_orders = [a["sort_order"] for a in _all_accounts(client) if a["is_person"]]
        person = client.post(f"/accounts/{first_id}/make-person")
        assert person["is_person"] is True
        _assert_kept(person, before)
        assert client.get(f"/accounts/{first_id}") == person
        assert _transaction_ids(client, first_id) == set(tx_ids)
        _assert_is_person(client, first_id)
        assert all(person["sort_order"] > order for order in people_orders)

        # The next account to become a person lands right after it.
        second_person = client.post(f"/accounts/{second_id}/make-person")
        assert second_person["sort_order"] == person["sort_order"] + 1

        # 1 — and back: the mirror, at the end of the real accounts.
        real_orders = [a["sort_order"] for a in _all_accounts(client) if not a["is_person"]]
        real = client.post(f"/accounts/{first_id}/make-account")
        assert real["is_person"] is False
        _assert_kept(real, person)
        assert real["current_balance_cents"] == before["current_balance_cents"]
        assert client.get(f"/accounts/{first_id}") == real
        assert _transaction_ids(client, first_id) == set(tx_ids)
        _assert_is_real(client, first_id)
        assert all(real["sort_order"] > order for order in real_orders)

        second_real = client.post(f"/accounts/{second_id}/make-account")
        assert second_real["sort_order"] == real["sort_order"] + 1
    finally:
        for tx_id in tx_ids:
            _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/accounts/{first_id}")
        _safe_delete(client, f"/accounts/{second_id}")


def test_an_account_already_of_that_kind_is_kind_unchanged(client):
    account_id = str(uuid4())
    person_id = str(uuid4())

    try:
        _make_account(client, account_id)
        _make_person(client, person_id)

        for target, route in ((account_id, "make-account"), (person_id, "make-person")):
            version = client.get(f"/accounts/{target}")["version"]
            err = _refused(lambda t=target, r=route: client.post(f"/accounts/{t}/{r}"))
            _assert_refusal(err, "KIND_UNCHANGED")
            assert client.get(f"/accounts/{target}")["version"] == version, route
    finally:
        _safe_delete(client, f"/accounts/{account_id}")
        _safe_delete(client, f"/accounts/{person_id}")


def test_an_account_with_an_opening_balance_cannot_become_a_person(client):
    account_id = str(uuid4())
    opening_id = str(uuid4())

    try:
        _make_account(client, account_id)
        client.post(
            f"/accounts/{account_id}/opening-balance",
            json_body={
                "transaction_id": opening_id,
                "amount_cents": 50000,
                "date": "2026-01-01T00:00:00Z",
            },
        )
        version = client.get(f"/accounts/{account_id}")["version"]

        err = _refused(lambda: client.post(f"/accounts/{account_id}/make-person"))
        _assert_refusal(err, "HAS_OPENING_BALANCE")
        after = client.get(f"/accounts/{account_id}")
        assert after["version"] == version
        assert after["is_person"] is False

        # A deleted opening balance does not count.
        client.delete(f"/transactions/{opening_id}")
        version = client.get(f"/accounts/{account_id}")["version"]
        person = client.post(f"/accounts/{account_id}/make-person")
        assert person["is_person"] is True
        assert person["version"] == version + 1
    finally:
        _safe_delete(client, f"/transactions/{opening_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_an_archived_account_keeps_its_kind_whatever_else_applies(client):
    """`ACCOUNT_ARCHIVED` comes first on both routes: for an archived real account
    (where `make-account` would also be `KIND_UNCHANGED`), an archived person (where
    `make-person` would also be `KIND_UNCHANGED`) and an archived account with an
    opening balance (where `make-person` would also be `HAS_OPENING_BALANCE`)."""
    account_id = str(uuid4())
    person_id = str(uuid4())
    seeded_id = str(uuid4())
    opening_id = str(uuid4())

    try:
        _make_account(client, account_id)
        _make_person(client, person_id)
        _make_account(client, seeded_id)
        client.post(
            f"/accounts/{seeded_id}/opening-balance",
            json_body={
                "transaction_id": opening_id,
                "amount_cents": 20000,
                "date": "2026-01-01T00:00:00Z",
            },
        )
        for target in (account_id, person_id, seeded_id):
            client.post(f"/accounts/{target}/archive")

        cases = [(t, r) for t in (account_id, person_id) for r in _ROUTES]
        cases.append((seeded_id, "make-person"))
        for target, route in cases:
            before = client.get(f"/accounts/{target}")
            err = _refused(lambda t=target, r=route: client.post(f"/accounts/{t}/{r}"))
            _assert_refusal(err, "ACCOUNT_ARCHIVED")
            after = client.get(f"/accounts/{target}")
            assert after["version"] == before["version"], (target, route)
            assert after["is_person"] is before["is_person"], (target, route)
    finally:
        # An archived account's transactions cannot be deleted, nor can an account
        # holding one, so each is unarchived first.
        for target in (account_id, person_id, seeded_id):
            _safe_post(client, f"/accounts/{target}/unarchive")
        _safe_delete(client, f"/transactions/{opening_id}")
        for target in (account_id, person_id, seeded_id):
            _safe_delete(client, f"/accounts/{target}")


def test_an_unknown_account_is_not_found(client):
    unknown_id = str(uuid4())
    for route in _ROUTES:
        err = _refused(lambda r=route: client.post(f"/accounts/{unknown_id}/{r}"))
        assert (err.status, err.code) == (404, "NOT_FOUND"), route


def test_make_person_sent_again_under_its_key_is_replayed(client, monkeypatch):
    """The client mints one key per logical write (expense/http.py); the key is held
    fixed here, so the second send is the same logical write sent again, as a retry
    sends it. Not replayed, it would be `KIND_UNCHANGED`."""
    account_id = str(uuid4())

    try:
        _make_account(client, account_id)
        version = client.get(f"/accounts/{account_id}")["version"]

        key = uuid4()
        monkeypatch.setattr(http_module, "uuid", SimpleNamespace(uuid4=lambda: key))
        first = client.post(f"/accounts/{account_id}/make-person")
        again = client.post(f"/accounts/{account_id}/make-person")
        monkeypatch.undo()

        assert again == first
        after = client.get(f"/accounts/{account_id}")
        assert after["is_person"] is True
        assert after["version"] == version + 1
    finally:
        _safe_delete(client, f"/accounts/{account_id}")
