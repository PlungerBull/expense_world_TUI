"""Contract lifecycle for log against a real engine.

Each test creates the supporting account/category, exercises the full lifecycle,
then cleans up. Gating, target resolution and the real-ledger guard live in
conftest.py.
"""

from datetime import UTC, datetime
from uuid import uuid4

from expense.errors import EngineError


def _safe_delete(client, path):
    try:
        client.delete(path)
    except EngineError:
        pass


def _make_account(client, currency_code="PEN"):
    new_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": new_id,
            "name": f"contract-acct-{new_id[:8]}",
            "currency_code": currency_code,
        },
    )
    return new_id


def _make_category(client):
    new_id = str(uuid4())
    client.post(
        "/categories",
        json_body={
            "id": new_id,
            "name": f"contract-cat-{new_id[:8]}",
            "color": "#123456",
        },
    )
    return new_id


def _make_hashtag(client):
    new_id = str(uuid4())
    client.post(
        "/hashtags",
        json_body={"id": new_id, "name": f"contract-tag-{new_id[:8]}"},
    )
    return new_id


def test_log_lifecycle(client):
    account_id = _make_account(client)
    category_id = _make_category(client)
    transaction_id = str(uuid4())

    try:
        created = client.post(
            "/transactions",
            json_body={
                "id": transaction_id,
                "title": "coffee",
                "amount_cents": -500,
                "account_id": account_id,
                "category_id": category_id,
                "date": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            },
        )
        assert created["id"] == transaction_id
        assert created["title"] == "coffee"
        # Engine stores positive amount, records direction in transaction_type.
        assert created["amount_cents"] == 500
        assert created["transaction_type"] == 1  # 1 = EXPENSE

        # A sparse row — no title, no category — is a ledger row too (sql/038):
        # the engine files it under @Pendiente and stores the title as null.
        sparse_id = str(uuid4())
        sparse = client.post(
            "/transactions",
            json_body={
                "id": sparse_id,
                "amount_cents": -660,
                "account_id": account_id,
                "date": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            },
        )
        try:
            assert sparse["title"] is None
            pending = client.get(f"/categories/{sparse['category_id']}")
            assert pending["system_key"] == "pending"
        finally:
            _safe_delete(client, f"/transactions/{sparse_id}")
    finally:
        _safe_delete(client, f"/transactions/{transaction_id}")
        _safe_delete(client, f"/categories/{category_id}")
        _safe_delete(client, f"/accounts/{account_id}")
