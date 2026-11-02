"""Contract lifecycle for log against a real engine.

Each test creates the supporting account/category, exercises the full lifecycle,
then cleans up. Gating, target resolution and the real-ledger guard live in
conftest.py.
"""


def test_log_lifecycle(client, scratch):
    account_id = scratch.account()
    category_id = scratch.category()
    created = scratch.recent_row(
        account_id, -500, alone=True, title="coffee", category_id=category_id
    )
    assert created["title"] == "coffee"
    # Engine stores positive amount, records direction in transaction_type.
    assert created["amount_cents"] == 500
    assert created["transaction_type"] == 1  # 1 = EXPENSE

    # A sparse row — no title, no category — is a ledger row too
    # (contract: POST /v1/transactions):
    # the engine files it under @Pendiente and stores the title as null.
    sparse = scratch.recent_row(account_id, -660, alone=True)
    assert sparse["title"] is None
    pending = client.get(f"/categories/{sparse['category_id']}")
    assert pending["system_key"] == "pending"
