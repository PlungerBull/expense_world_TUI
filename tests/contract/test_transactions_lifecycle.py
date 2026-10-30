"""Contract lifecycle for transactions against a real engine.

Each test builds the supporting account/category through `scratch`, exercises the full
lifecycle, and `scratch` cleans up. Every create names its account and the currency of it
the row is in, and every answer echoes both (contract: POST /v1/transactions, "Fields").
Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from expense.errors import EngineError
from tests.contract.conftest import assert_refusal, refused


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _row(account_id: str, category_id: str, currency: str, **fields) -> dict:
    """A `POST /transactions` body under a fresh id, in `currency` of the account."""
    return {
        "id": str(uuid4()),
        "amount_cents": -500,
        "account_id": account_id,
        "currency_code": currency,
        "category_id": category_id,
        "date": _now_iso(),
        **fields,
    }


def test_transactions_lifecycle(client, scratch):
    account_id = scratch.account("PEN", "USD")
    category_id = scratch.category()
    body = _row(account_id, category_id, "USD", title="coffee")
    tx_id = body["id"]
    scratch.transactions.append(tx_id)

    created = client.post("/transactions", json_body=body)
    assert created["id"] == tx_id
    assert (created["account_id"], created["currency_code"]) == (account_id, "USD")

    fetched = client.get(f"/transactions/{tx_id}")
    assert fetched["id"] == tx_id
    assert fetched["title"] == "coffee"
    assert (fetched["account_id"], fetched["currency_code"]) == (account_id, "USD")

    listed = client.get("/transactions", params={"account_id": account_id})
    assert [(i["id"], i["currency_code"]) for i in listed["items"]] == [(tx_id, "USD")]

    updated = client.put(f"/transactions/{tx_id}", json_body={"title": "cafe latte"})
    assert updated["title"] == "cafe latte"
    assert updated["currency_code"] == "USD"

    deleted = client.delete(f"/transactions/{tx_id}")
    assert deleted["id"] == tx_id
    assert deleted.get("deleted_at") is not None
    # DELETE carries no `warnings` key. Pin the absence.
    assert "warnings" not in deleted

    # Deleted is deleted: gone from the list, 404 on
    # get, and the restore route itself is a 404.
    listed = client.get("/transactions", params={"account_id": account_id})
    assert not any(item["id"] == tx_id for item in listed["items"])
    for gone in (
        lambda: client.get(f"/transactions/{tx_id}"),
        lambda: client.post(f"/transactions/{tx_id}/restore"),
    ):
        with pytest.raises(EngineError) as excinfo:
            gone()
        assert excinfo.value.status == 404


def test_a_create_names_a_currency_the_account_holds(client, scratch):
    """A create without `currency_code` is `REQUIRED` and one in a currency the account
    does not hold is `CURRENCY_NOT_HELD`, each on `currency_code`; nothing is written
    (contract: POST /v1/transactions, "Fields")."""
    account_id = scratch.account("PEN")
    category_id = scratch.category()

    missing = _row(account_id, category_id, "PEN")
    del missing["currency_code"]
    err = refused(lambda: client.post("/transactions", json_body=missing))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "REQUIRED")

    err = refused(
        lambda: client.post("/transactions", json_body=_row(account_id, category_id, "USD"))
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "CURRENCY_NOT_HELD")
    assert err.fields["currency_code"] == "Must be a currency the account holds."
    assert client.get("/transactions/count", params={"account_id": account_id}) == {"count": 0}


def test_an_empty_description_empties_the_note_and_null_is_refused(client, scratch):
    """`""` empties a note and `null` is `422` `NOT_NULL` on `description`, so the
    Edit form sends `""` for an emptied note
    (contract: PUT /v1/transactions/{transaction_id})."""
    account_id = scratch.account()
    category_id = scratch.category()
    body = _row(account_id, category_id, "PEN", title="pharmacy", description="receta")
    tx_id = body["id"]
    scratch.transactions.append(tx_id)
    client.post("/transactions", json_body=body)

    emptied = client.put(f"/transactions/{tx_id}", json_body={"description": ""})
    assert emptied["description"] == ""
    assert client.get(f"/transactions/{tx_id}")["description"] == ""

    err = refused(lambda: client.put(f"/transactions/{tx_id}", json_body={"description": None}))
    assert_refusal(err, 422, "VALIDATION_ERROR", "description", "NOT_NULL")
    after = client.get(f"/transactions/{tx_id}")
    assert after["description"] == ""
    assert after["version"] == emptied["version"]  # nothing written


def test_batch_create(client, scratch):
    account_id = scratch.account("PEN", "USD")
    category_id = scratch.category()
    currencies = ["PEN", "USD", "PEN"]
    items = [
        _row(account_id, category_id, currency, title=title, amount_cents=-100 * n)
        for n, (title, currency) in enumerate(zip("abc", currencies, strict=True), start=1)
    ]
    scratch.transactions.extend(item["id"] for item in items)

    body = client.post("/transactions/batch", json_body={"transactions": items})

    created = body.get("created", [])
    assert {item["id"] for item in created} == {item["id"] for item in items}
    echoed = {item["id"]: (item["account_id"], item["currency_code"]) for item in created}
    assert echoed == {item["id"]: (account_id, item["currency_code"]) for item in items}


def test_a_batch_item_without_a_currency_is_refused(client, scratch):
    """A batch item missing `currency_code` is refused on the item's own key, and the
    batch writes nothing (contract: POST /v1/transactions/batch)."""
    account_id = scratch.account()
    category_id = scratch.category()
    item = _row(account_id, category_id, "PEN")
    del item["currency_code"]
    scratch.transactions.append(item["id"])

    err = refused(lambda: client.post("/transactions/batch", json_body={"transactions": [item]}))
    assert_refusal(err, 422, "VALIDATION_ERROR", "transactions.0.currency_code", "REQUIRED")
    assert client.get("/transactions/count", params={"account_id": account_id}) == {"count": 0}
