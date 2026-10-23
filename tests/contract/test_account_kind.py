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
   opening balance (it goes through once that transaction is deleted, and comes before
   `HAS_RECONCILIATION`), `HAS_RECONCILIATION` on `make-person` for an account with a
   draft or a completed reconciliation (it goes through once the draft is deleted, or
   the completed one reverted and deleted), and `ACCOUNT_ARCHIVED` on both routes for an
   archived account and an archived person, returned first when another refusal also
   applies (contract: POST /v1/accounts/{account_id}/archive).
3. A person never has reconciliations: `POST /reconciliations` on one is `422`
   `VALIDATION_ERROR` with `PERSON_ACCOUNT` on `account_id`, writing nothing, and an
   archived person answers `INVALID_REFERENCE` there instead; turned back with
   `make-account`, it starts one again (`201`) (contract: "People / Person Accounts",
   "Person rules").
4. An unknown id is `404` on both routes.
5. A `make-person` sent again under the same `X-Idempotency-Key` is replayed: the same
   answer, and the account flipped once (contract: "Base Conventions", "Idempotency").

Every account and reconciliation is fresh per run (named by its UUID) and deleted at the
end, with its transactions. Gating, target resolution and the real-ledger guard live in
conftest.py.
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


def _make_reconciliation(client, recon_id: str, account_id: str, **extra) -> dict:
    return client.post(
        "/reconciliations",
        json_body={
            "id": recon_id,
            "account_id": account_id,
            "name": f"contract-kind-recon-{recon_id[:8]}",
            "date_start": "2026-04-01",
            "date_end": "2026-04-30",
            "beginning_balance_cents": 958000,
            **extra,
        },
    )


def _reconciliation_ids(client, account_id: str) -> set[str]:
    listed = client.get("/reconciliations", params={"account_id": account_id})
    return {item["id"] for item in listed["items"]}


def _assert_still_real(client, account_id: str, version: int) -> None:
    after = client.get(f"/accounts/{account_id}")
    assert after["version"] == version
    assert after["is_person"] is False


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


def test_an_account_with_a_draft_reconciliation_cannot_become_a_person(client):
    """A live draft is `HAS_RECONCILIATION`, writing nothing; a deleted one does not
    count (contract: POST /v1/accounts/{account_id}/make-person, "Refusals")."""
    account_id = str(uuid4())
    recon_id = str(uuid4())

    try:
        _make_account(client, account_id)
        _make_reconciliation(client, recon_id, account_id)
        version = client.get(f"/accounts/{account_id}")["version"]

        err = _refused(lambda: client.post(f"/accounts/{account_id}/make-person"))
        _assert_refusal(err, "HAS_RECONCILIATION")
        _assert_still_real(client, account_id, version)

        client.delete(f"/reconciliations/{recon_id}")
        person = client.post(f"/accounts/{account_id}/make-person")
        assert person["is_person"] is True
        assert person["version"] == version + 1
    finally:
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_an_account_with_a_completed_reconciliation_cannot_become_a_person(client):
    """A completed reconciliation is `HAS_RECONCILIATION` too, and so is the draft its
    revert leaves; only once that draft is deleted does the account become a person
    (contract: POST /v1/accounts/{account_id}/make-person, "Refusals")."""
    account_id = str(uuid4())
    recon_id = str(uuid4())
    tx_id = str(uuid4())

    try:
        _make_account(client, account_id)
        _make_transaction(client, tx_id, account_id, -1200)
        _make_reconciliation(client, recon_id, account_id, ending_balance_cents=956800)
        client.put(f"/transactions/{tx_id}", json_body={"reconciliation_id": recon_id})
        assert client.post(f"/reconciliations/{recon_id}/complete")["status"] == 2
        version = client.get(f"/accounts/{account_id}")["version"]

        err = _refused(lambda: client.post(f"/accounts/{account_id}/make-person"))
        _assert_refusal(err, "HAS_RECONCILIATION")
        _assert_still_real(client, account_id, version)

        assert client.post(f"/reconciliations/{recon_id}/revert")["status"] == 1
        err = _refused(lambda: client.post(f"/accounts/{account_id}/make-person"))
        _assert_refusal(err, "HAS_RECONCILIATION")
        _assert_still_real(client, account_id, version)

        client.delete(f"/reconciliations/{recon_id}")
        person = client.post(f"/accounts/{account_id}/make-person")
        assert person["is_person"] is True
        assert person["version"] == version + 1
    finally:
        _safe_post(client, f"/reconciliations/{recon_id}/revert")
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_an_opening_balance_is_refused_before_a_reconciliation(client):
    """With both an opening balance and a reconciliation, `make-person` answers
    `HAS_OPENING_BALANCE`, the earlier refusal; with the opening balance deleted, the
    reconciliation still refuses it (contract: POST
    /v1/accounts/{account_id}/make-person, "Refusals")."""
    account_id = str(uuid4())
    opening_id = str(uuid4())
    recon_id = str(uuid4())

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
        _make_reconciliation(client, recon_id, account_id)
        version = client.get(f"/accounts/{account_id}")["version"]

        err = _refused(lambda: client.post(f"/accounts/{account_id}/make-person"))
        _assert_refusal(err, "HAS_OPENING_BALANCE")
        _assert_still_real(client, account_id, version)

        client.delete(f"/transactions/{opening_id}")
        version = client.get(f"/accounts/{account_id}")["version"]
        err = _refused(lambda: client.post(f"/accounts/{account_id}/make-person"))
        _assert_refusal(err, "HAS_RECONCILIATION")
        _assert_still_real(client, account_id, version)
    finally:
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/transactions/{opening_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_a_person_cannot_start_a_reconciliation(client, statuses):
    """`POST /reconciliations` on a person is `422` `VALIDATION_ERROR` keyed on
    `account_id` alone with `PERSON_ACCOUNT`, and nothing is written: the person lists
    no reconciliation and the sent id reads `404`. An archived person answers
    `INVALID_REFERENCE` there, like any archived account (contract: POST
    /v1/reconciliations, "A person account never has reconciliations"). Turned back
    with `make-account`, the account starts one again, under the very id refused,
    which proves the refusal wrote nothing (contract: "People / Person Accounts",
    "Person rules")."""
    person_id = str(uuid4())
    converted_id = str(uuid4())
    recon_id = str(uuid4())

    def refused_on(account_id: str) -> EngineError:
        return _refused(lambda: _make_reconciliation(client, recon_id, account_id))

    try:
        _make_person(client, person_id)
        _make_account(client, converted_id)
        client.post(f"/accounts/{converted_id}/make-person")

        for target in (person_id, converted_id):
            err = refused_on(target)
            assert (err.status, err.code) == (422, "VALIDATION_ERROR"), target
            assert isinstance(err.fields, dict) and set(err.fields) == {"account_id"}
            assert err.reasons == {"account_id": "PERSON_ACCOUNT"}, target
            assert _reconciliation_ids(client, target) == set(), target
            missing = _refused(lambda: client.get(f"/reconciliations/{recon_id}"))
            assert missing.status == 404, target

        client.post(f"/accounts/{person_id}/archive")
        err = refused_on(person_id)
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert err.reasons == {"account_id": "INVALID_REFERENCE"}

        # Turned back into a bank account, it is reconciled again.
        client.post(f"/accounts/{converted_id}/make-account")
        created = _make_reconciliation(client, recon_id, converted_id)
        assert statuses[-1] == 201
        assert created["id"] == recon_id
        assert created["account_id"] == converted_id
        assert _reconciliation_ids(client, converted_id) == {recon_id}
    finally:
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_post(client, f"/accounts/{person_id}/unarchive")
        _safe_delete(client, f"/accounts/{person_id}")
        _safe_delete(client, f"/accounts/{converted_id}")


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
