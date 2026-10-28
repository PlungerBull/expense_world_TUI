"""Contract lifecycle for an account's opening balance against a real engine.

The account Edit form reads the opening balance through the account's
`opening_balance_transaction_id` and changes it through the transaction routes. Only
the engine can say that id stays current, and that an opening balance never moves
to another account or out of `@Opening` (contract: PUT /v1/transactions/{transaction_id},
"Opening balances stay put").

What it pins, in the order the form meets it:

1. A new bank account names no opening balance (`null`); `POST
   /accounts/{id}/opening-balance` makes one and the account then names its id.
2. Editing its amount and date keeps the same id on the account.
3. A different `account_id` is `422` `OPENING_BALANCE_ACCOUNT_FIXED`; a different
   `category_id` (`@Pendiente`) is `422` `OPENING_BALANCE_CATEGORY_FIXED`; both in
   one body report both. Resending its own account and category is accepted.
4. A second opening balance is `409` `OPENING_BALANCE_EXISTS` on `account_id`
   (contract: POST /v1/accounts/{account_id}/opening-balance).
5. Deleting it leaves the account naming none (`null`) again.
6. A person from `POST /people` takes one too, under `@Opening` and named by its
   `opening_balance_transaction_id`, and a second is `409` `OPENING_BALANCE_EXISTS` on
   `account_id`, as on a bank account (contract: POST /v1/accounts/{account_id}/opening-balance).

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from uuid import uuid4

import pytest

from expense.errors import EngineError
from tests.contract.conftest import reason_on


def _safe_delete(client, path):
    try:
        client.delete(path)
    except EngineError:
        pass


def _make_account(client) -> str:
    new_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={"id": new_id, "name": f"contract-ob-{new_id[:8]}", "currency_code": "PEN"},
    )
    return new_id


def _pendiente_id(client, account_id: str) -> str:
    """The `@Pendiente` category's id, read off a sparse row the engine files there
    (contract: POST /v1/transactions). The row is deleted before returning."""
    sparse_id = str(uuid4())
    sparse = client.post(
        "/transactions",
        json_body={
            "id": sparse_id,
            "amount_cents": -100,
            "account_id": account_id,
            "date": "2026-01-02T00:00:00Z",
        },
    )
    client.delete(f"/transactions/{sparse_id}")
    assert client.get(f"/categories/{sparse['category_id']}")["system_key"] == "pending"
    return sparse["category_id"]


def _refused(call) -> EngineError:
    with pytest.raises(EngineError) as excinfo:
        call()
    return excinfo.value


def test_opening_balance_lifecycle(client):
    account_id = _make_account(client)
    other_account_id = _make_account(client)
    tx_id = str(uuid4())

    try:
        # 1 — none yet, then the account names the one just made.
        assert client.get(f"/accounts/{account_id}")["opening_balance_transaction_id"] is None

        seeded = client.post(
            f"/accounts/{account_id}/opening-balance",
            json_body={
                "transaction_id": tx_id,
                "amount_cents": 150000,
                "date": "2026-01-01T00:00:00Z",
            },
        )
        assert seeded["id"] == tx_id
        opening_category_id = seeded["category_id"]
        assert client.get(f"/categories/{opening_category_id}")["system_key"] == ("opening_balance")
        assert client.get(f"/accounts/{account_id}")["opening_balance_transaction_id"] == tx_id
        listed = client.get("/accounts")
        row = next(a for a in listed["items"] if a["id"] == account_id)
        assert row["opening_balance_transaction_id"] == tx_id

        # 2 — amount and date stay editable; the account names the same row.
        edited = client.put(
            f"/transactions/{tx_id}",
            json_body={"amount_cents": -2500, "date": "2026-01-03T00:00:00Z"},
        )
        assert edited["id"] == tx_id
        assert edited["amount_cents"] == 2500
        assert edited["transaction_type"] == 1
        assert edited["date"].startswith("2026-01-03")
        assert client.get(f"/accounts/{account_id}")["opening_balance_transaction_id"] == tx_id

        # 3 — it never changes account and never leaves @Opening.
        err = _refused(
            lambda: client.put(f"/transactions/{tx_id}", json_body={"account_id": other_account_id})
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "account_id") == "OPENING_BALANCE_ACCOUNT_FIXED"

        pendiente_id = _pendiente_id(client, other_account_id)
        err = _refused(
            lambda: client.put(f"/transactions/{tx_id}", json_body={"category_id": pendiente_id})
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "category_id") == "OPENING_BALANCE_CATEGORY_FIXED"

        err = _refused(
            lambda: client.put(
                f"/transactions/{tx_id}",
                json_body={"account_id": other_account_id, "category_id": pendiente_id},
            )
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "account_id") == "OPENING_BALANCE_ACCOUNT_FIXED"
        assert reason_on(err, "category_id") == "OPENING_BALANCE_CATEGORY_FIXED"

        unchanged = client.get(f"/transactions/{tx_id}")
        assert unchanged["account_id"] == account_id
        assert unchanged["category_id"] == opening_category_id

        # Resending what it already has is not a move.
        resent = client.put(
            f"/transactions/{tx_id}",
            json_body={"account_id": account_id, "category_id": opening_category_id},
        )
        assert resent["account_id"] == account_id
        assert resent["category_id"] == opening_category_id

        # 4 — one opening balance per account.
        err = _refused(
            lambda: client.post(
                f"/accounts/{account_id}/opening-balance",
                json_body={
                    "transaction_id": str(uuid4()),
                    "amount_cents": 1000,
                    "date": "2026-01-01T00:00:00Z",
                },
            )
        )
        assert (err.status, err.code) == (409, "CONFLICT")
        assert reason_on(err, "account_id") == "OPENING_BALANCE_EXISTS"

        # 5 — deleted, the account names none again.
        client.delete(f"/transactions/{tx_id}")
        assert client.get(f"/accounts/{account_id}")["opening_balance_transaction_id"] is None
    finally:
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/accounts/{other_account_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_a_person_takes_one_opening_balance(client, statuses):
    person_id = str(uuid4())
    tx_id = str(uuid4())
    created = client.post(
        "/people",
        json_body={
            "id": person_id,
            "name": f"contract-ob-person-{person_id[:8]}",
            "currency_code": "PEN",
        },
    )
    try:
        assert created["is_person"] is True
        assert created["opening_balance_transaction_id"] is None

        seeded = client.post(
            f"/accounts/{person_id}/opening-balance",
            json_body={
                "transaction_id": tx_id,
                "amount_cents": -42000,
                "date": "2026-01-01T00:00:00Z",
            },
        )
        assert statuses[-1] == 201
        assert seeded["id"] == tx_id
        assert seeded["account_id"] == person_id
        assert client.get(f"/categories/{seeded['category_id']}")["system_key"] == (
            "opening_balance"
        )
        assert client.get(f"/accounts/{person_id}")["opening_balance_transaction_id"] == tx_id

        err = _refused(
            lambda: client.post(
                f"/accounts/{person_id}/opening-balance",
                json_body={
                    "transaction_id": str(uuid4()),
                    "amount_cents": 1000,
                    "date": "2026-01-01T00:00:00Z",
                },
            )
        )
        assert (err.status, err.code) == (409, "CONFLICT")
        assert err.reasons == {"account_id": "OPENING_BALANCE_EXISTS"}
        assert client.get(f"/accounts/{person_id}")["opening_balance_transaction_id"] == tx_id
    finally:
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/accounts/{person_id}")
