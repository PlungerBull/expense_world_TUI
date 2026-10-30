"""Contract lifecycle for log against a real engine.

Each test creates the supporting account/category, exercises the full lifecycle,
then cleans up. Gating, target resolution and the real-ledger guard live in
conftest.py.
"""

from datetime import UTC, datetime
from uuid import uuid4


def test_log_lifecycle(client, scratch):
    account_id = scratch.account()
    category_id = scratch.category()
    transaction_id = str(uuid4())
    sparse_id = str(uuid4())
    scratch.transactions.extend([transaction_id, sparse_id])

    created = client.post(
        "/transactions",
        json_body={
            "id": transaction_id,
            "title": "coffee",
            "amount_cents": -500,
            "account_id": account_id,
            "currency_code": "PEN",
            "category_id": category_id,
            "date": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
    )
    assert created["id"] == transaction_id
    assert created["title"] == "coffee"
    # Engine stores positive amount, records direction in transaction_type.
    assert created["amount_cents"] == 500
    assert created["transaction_type"] == 1  # 1 = EXPENSE

    # A sparse row — no title, no category — is a ledger row too
    # (contract: POST /v1/transactions):
    # the engine files it under @Pendiente and stores the title as null.
    sparse = client.post(
        "/transactions",
        json_body={
            "id": sparse_id,
            "amount_cents": -660,
            "account_id": account_id,
            "currency_code": "PEN",
            "date": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
    )
    assert sparse["title"] is None
    pending = client.get(f"/categories/{sparse['category_id']}")
    assert pending["system_key"] == "pending"
