"""Contract refusals that are not form errors carry a reason, against a real engine.

A `CONFLICT` (`409`), `FORBIDDEN` (`403`) or `LIMIT_REACHED` (`422`) always carries
`fields` and `reasons`, keyed by the thing refused: the path id, the body field that
carried it, or `X-Idempotency-Key` (contract: "Base Conventions", "`fields` and
`reasons` semantics"). The app picks its next-step line from `code` and `reasons`
alone, so only the engine can say each refusal names the reason it does.

What it pins, each refusal's status, code, keyed `fields`/`reasons` and reason:

1. Deleting an account with a live transaction is `409` `HAS_TRANSACTIONS` on
   `account_id` (contract: DELETE /v1/accounts/{account_id}).
2. Deleting a category a live transaction uses is `409` `HAS_TRANSACTIONS` on
   `category_id`; deleting a system category (`@Pendiente`, found by `system_key`) is
   `403` `SYSTEM_CATEGORY` on `category_id` (contract: DELETE /v1/categories/{category_id}).
   `@Pendiente` is engine-created and can never be deleted, so it stays behind on the
   practice user.
3. A name already taken is `409` `NAME_EXISTS` on `name`, for an account (contract:
   POST /v1/accounts, "Validation") and for a category (contract: POST /v1/categories,
   "Validation").
4. A taken `id` re-sent with a different body is `409` `ID_EXISTS` on `id`; in
   `POST /transactions/batch` it is keyed `transactions.<i>.id` (contract:
   "Client-supplied UUIDs").
5. While its reconciliation is completed, deleting an assigned transaction is `409`
   `IN_COMPLETED_RECONCILIATION` on `transaction_id` (contract: DELETE
   /v1/transactions/{transaction_id}), and deleting the reconciliation is `409`
   `RECONCILIATION_NOT_DRAFT` on `reconciliation_id` (contract: DELETE
   /v1/reconciliations/{reconciliation_id}). Completing needs an ending balance
   (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Validation").

Not pinned here: `CAP_REACHED` (`LIMIT_REACHED`). The smallest cap is 100 accounts,
archived ones included (contract: "Create caps"), so provoking it means a hundred
creates on the practice user per run, each left behind as a soft-deleted row.

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


def _refused(call) -> EngineError:
    with pytest.raises(EngineError) as excinfo:
        call()
    return excinfo.value


def _assert_refusal(err: EngineError, status: int, code: str, key: str, reason: str) -> None:
    """The refusal's status and code, `fields`/`reasons` keyed alike, and `reason` on
    `key` (contract: "Base Conventions", "`fields` and `reasons` semantics")."""
    assert (err.status, err.code) == (status, code)
    assert isinstance(err.fields, dict) and err.fields
    assert isinstance(err.reasons, dict) and err.reasons
    assert set(err.reasons) == set(err.fields)
    assert key in err.fields
    assert reason_on(err, key) == reason


def _make_account(client, account_id: str, name: str) -> None:
    client.post(
        "/accounts",
        json_body={"id": account_id, "name": name, "currency_code": "PEN"},
    )


def _make_transaction(client, tx_id: str, account_id: str, category_id: str | None) -> dict:
    body = {
        "id": tx_id,
        "amount_cents": -100,
        "account_id": account_id,
        "date": "2026-01-02T00:00:00Z",
    }
    if category_id is not None:
        body["category_id"] = category_id
    return client.post("/transactions", json_body=body)


def test_deletes_of_what_is_in_use_name_the_reason(client):
    account_id = str(uuid4())
    category_id = str(uuid4())
    tx_id = str(uuid4())
    sparse_id = str(uuid4())

    try:
        _make_account(client, account_id, f"contract-rr-{account_id[:8]}")
        client.post(
            "/categories",
            json_body={"id": category_id, "name": f"contract-rr-{category_id[:8]}"},
        )
        _make_transaction(client, tx_id, account_id, category_id)

        # 1 — an account with a live transaction.
        err = _refused(lambda: client.delete(f"/accounts/{account_id}"))
        _assert_refusal(err, 409, "CONFLICT", "account_id", "HAS_TRANSACTIONS")

        # 2 — a category a live transaction uses.
        err = _refused(lambda: client.delete(f"/categories/{category_id}"))
        _assert_refusal(err, 409, "CONFLICT", "category_id", "HAS_TRANSACTIONS")

        # 2 — a system category: a row with no category makes @Pendiente exist.
        _make_transaction(client, sparse_id, account_id, None)
        categories = client.get("/categories")["items"]
        pendiente = next(c for c in categories if c["system_key"] == "pending")
        err = _refused(lambda: client.delete(f"/categories/{pendiente['id']}"))
        _assert_refusal(err, 403, "FORBIDDEN", "category_id", "SYSTEM_CATEGORY")
    finally:
        _safe_delete(client, f"/transactions/{sparse_id}")
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/categories/{category_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_a_taken_name_is_name_exists(client):
    account_id = str(uuid4())
    category_id = str(uuid4())
    account_name = f"contract-rr-{account_id[:8]}"
    category_name = f"contract-rr-{category_id[:8]}"

    try:
        _make_account(client, account_id, account_name)
        client.post("/categories", json_body={"id": category_id, "name": category_name})

        # 3 — compared after trimming, case-insensitively (contract: "Error reasons").
        err = _refused(
            lambda: client.post(
                "/accounts",
                json_body={
                    "id": str(uuid4()),
                    "name": f" {account_name.upper()} ",
                    "currency_code": "PEN",
                },
            )
        )
        _assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")

        err = _refused(
            lambda: client.post(
                "/categories",
                json_body={"id": str(uuid4()), "name": category_name.upper()},
            )
        )
        _assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")
    finally:
        _safe_delete(client, f"/categories/{category_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_a_taken_id_is_id_exists(client):
    account_id = str(uuid4())
    tx_id = str(uuid4())
    batch_tx_id = str(uuid4())

    try:
        _make_account(client, account_id, f"contract-rr-{account_id[:8]}")

        # 4 — the same id with a different body, under a fresh idempotency key.
        err = _refused(
            lambda: _make_account(client, account_id, f"contract-rr-other-{account_id[:8]}")
        )
        _assert_refusal(err, 409, "CONFLICT", "id", "ID_EXISTS")

        # 4 — in a batch, keyed by the item that carried it.
        _make_transaction(client, tx_id, account_id, None)
        err = _refused(
            lambda: client.post(
                "/transactions/batch",
                json_body={
                    "transactions": [
                        {
                            "id": batch_tx_id,
                            "amount_cents": -200,
                            "account_id": account_id,
                            "date": "2026-01-03T00:00:00Z",
                        },
                        {
                            "id": tx_id,
                            "amount_cents": -300,
                            "account_id": account_id,
                            "date": "2026-01-03T00:00:00Z",
                        },
                    ]
                },
            )
        )
        _assert_refusal(err, 409, "CONFLICT", "transactions.1.id", "ID_EXISTS")
    finally:
        _safe_delete(client, f"/transactions/{batch_tx_id}")
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_a_completed_reconciliation_holds_its_rows_and_itself(client):
    account_id = str(uuid4())
    tx_id = str(uuid4())
    recon_id = str(uuid4())

    try:
        _make_account(client, account_id, f"contract-rr-{account_id[:8]}")
        _make_transaction(client, tx_id, account_id, None)
        client.post(
            "/reconciliations",
            json_body={
                "id": recon_id,
                "account_id": account_id,
                "name": f"contract-rr-{recon_id[:8]}",
                "date_start": "2026-01-01",
                "date_end": "2026-01-31",
                "beginning_balance_cents": 0,
                "ending_balance_cents": -100,
            },
        )
        client.put(f"/transactions/{tx_id}", json_body={"reconciliation_id": recon_id})
        client.post(f"/reconciliations/{recon_id}/complete")

        # 5 — the row in it, then the reconciliation itself.
        err = _refused(lambda: client.delete(f"/transactions/{tx_id}"))
        _assert_refusal(err, 409, "CONFLICT", "transaction_id", "IN_COMPLETED_RECONCILIATION")

        err = _refused(lambda: client.delete(f"/reconciliations/{recon_id}"))
        _assert_refusal(err, 409, "CONFLICT", "reconciliation_id", "RECONCILIATION_NOT_DRAFT")
    finally:
        try:
            client.post(f"/reconciliations/{recon_id}/revert")
        except EngineError:
            pass
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/reconciliations/{recon_id}")
        _safe_delete(client, f"/accounts/{account_id}")
