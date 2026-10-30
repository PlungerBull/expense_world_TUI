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
5. While its statement is completed, deleting an assigned transaction is `409`
   `IN_COMPLETED_RECONCILIATION` on `transaction_id` (contract: DELETE
   /v1/transactions/{transaction_id}), and deleting the statement is `409`
   `RECONCILIATION_NOT_DRAFT` on `statement_id` (contract: DELETE
   /v1/statements/{statement_id}, "Validation"). Completing needs every balance entered and
   adding up (contract: POST /v1/statements/{statement_id}/complete, "Validation").
6. Deleting the built-in pending hashtag (found by `system_key`) is `403`
   `SYSTEM_HASHTAG` on `hashtag_id`, and it stays (contract: DELETE
   /v1/hashtags/{hashtag_id}). It is engine-created and can never be deleted, so it
   stays behind on the practice user.

Not pinned here: `CAP_REACHED` (`LIMIT_REACHED`). The smallest cap is 100 accounts,
archived ones included (contract: "Create caps"), so provoking it means a hundred
creates on the practice user per run, each left behind as a soft-deleted row.

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from uuid import uuid4

from tests.contract.conftest import account_body, assert_refusal, refused


def _make_transaction(scratch, tx_id: str, account_id: str, category_id: str | None = None) -> dict:
    """A `-100` PEN row dated in January 2026, taken on by `scratch`'s cleanup."""
    scratch.transactions.append(tx_id)
    body = {
        "id": tx_id,
        "amount_cents": -100,
        "account_id": account_id,
        "currency_code": "PEN",
        "date": "2026-01-02T00:00:00Z",
    }
    if category_id is not None:
        body["category_id"] = category_id
    return scratch.client.post("/transactions", json_body=body)


def test_deletes_of_what_is_in_use_name_the_reason(client, scratch):
    account_id = scratch.account()
    category_id = scratch.category()
    _make_transaction(scratch, str(uuid4()), account_id, category_id)

    # 1 — an account with a live transaction.
    err = refused(lambda: client.delete(f"/accounts/{account_id}"))
    assert_refusal(err, 409, "CONFLICT", "account_id", "HAS_TRANSACTIONS")

    # 2 — a category a live transaction uses.
    err = refused(lambda: client.delete(f"/categories/{category_id}"))
    assert_refusal(err, 409, "CONFLICT", "category_id", "HAS_TRANSACTIONS")

    # 2 — a system category: a row with no category makes @Pendiente exist.
    _make_transaction(scratch, str(uuid4()), account_id)
    categories = client.get("/categories")["items"]
    pendiente = next(c for c in categories if c["system_key"] == "pending")
    err = refused(lambda: client.delete(f"/categories/{pendiente['id']}"))
    assert_refusal(err, 403, "FORBIDDEN", "category_id", "SYSTEM_CATEGORY")


def test_the_pending_hashtag_is_never_deleted(client, scratch):
    account_id = scratch.account()
    tx_id = str(uuid4())
    # 6 — a row with no hashtag makes the pending hashtag exist.
    _make_transaction(scratch, tx_id, account_id)
    hashtags = client.get("/hashtags")["items"]
    pending = next(h for h in hashtags if h["system_key"] == "pending")
    err = refused(lambda: client.delete(f"/hashtags/{pending['id']}"))
    assert_refusal(err, 403, "FORBIDDEN", "hashtag_id", "SYSTEM_HASHTAG")
    assert client.get(f"/hashtags/{pending['id']}")["system_key"] == "pending"
    assert client.get(f"/transactions/{tx_id}")["hashtag_ids"] == [pending["id"]]


def test_a_taken_name_is_name_exists(client, scratch):
    account_id = scratch.account()
    account_name = client.get(f"/accounts/{account_id}")["name"]
    category_id = str(uuid4())
    scratch.categories.append(category_id)
    category_name = f"contract-rr-{category_id[:8]}"
    client.post("/categories", json_body={"id": category_id, "name": category_name})

    # 3 — compared after trimming, case-insensitively (contract: "Error reasons").
    err = refused(
        lambda: client.post(
            "/accounts",
            json_body={**account_body(), "name": f" {account_name.upper()} "},
        )
    )
    assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")

    err = refused(
        lambda: client.post(
            "/categories",
            json_body={"id": str(uuid4()), "name": category_name.upper()},
        )
    )
    assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")


def test_a_taken_id_is_id_exists(client, scratch):
    account_id = scratch.account()
    tx_id = str(uuid4())
    batch_tx_id = str(uuid4())
    scratch.transactions.append(batch_tx_id)

    # 4 — the same id with a different body, under a fresh idempotency key.
    err = refused(
        lambda: client.post(
            "/accounts", json_body={**account_body(), "id": account_id, "name": f"rr-{account_id}"}
        )
    )
    assert_refusal(err, 409, "CONFLICT", "id", "ID_EXISTS")

    # 4 — in a batch, keyed by the item that carried it.
    _make_transaction(scratch, tx_id, account_id)
    err = refused(
        lambda: client.post(
            "/transactions/batch",
            json_body={
                "transactions": [
                    {
                        "id": batch_tx_id,
                        "amount_cents": -200,
                        "account_id": account_id,
                        "currency_code": "PEN",
                        "date": "2026-01-03T00:00:00Z",
                    },
                    {
                        "id": tx_id,
                        "amount_cents": -300,
                        "account_id": account_id,
                        "currency_code": "PEN",
                        "date": "2026-01-03T00:00:00Z",
                    },
                ]
            },
        )
    )
    assert_refusal(err, 409, "CONFLICT", "transactions.1.id", "ID_EXISTS")


def test_a_completed_statement_holds_its_rows_and_itself(client, scratch):
    account_id = scratch.account()
    tx_id = str(uuid4())
    _make_transaction(scratch, tx_id, account_id)
    statement_id = scratch.statement(account_id, "2026-01-01", "2026-01-31")["id"]
    client.put(
        f"/statements/{statement_id}",
        json_body={"balances": [{"currency_code": "PEN", "ending_balance_cents": -100}]},
    )
    scratch.assign(tx_id, statement_id)
    client.post(f"/statements/{statement_id}/complete")

    # 5 — the row in it, then the statement itself.
    err = refused(lambda: client.delete(f"/transactions/{tx_id}"))
    assert_refusal(err, 409, "CONFLICT", "transaction_id", "IN_COMPLETED_RECONCILIATION")

    err = refused(lambda: client.delete(f"/statements/{statement_id}"))
    assert_refusal(err, 409, "CONFLICT", "statement_id", "RECONCILIATION_NOT_DRAFT")
