"""Contract lifecycle for transactions against a real engine.

Each test builds the supporting account/category through `scratch`, exercises the full
lifecycle, and `scratch` cleans up. Every create names its account and the currency of it
the row is in, and every answer echoes both (contract: POST /v1/transactions, "Fields").
Gating, target resolution and the real-ledger guard live in conftest.py.
"""

import pytest

from expense.errors import EngineError
from tests.contract.conftest import assert_refusal, refused


def _recent(scratch) -> str:
    """A minute ago in the display timezone, as `recent_row` dates a row, for the bodies
    built from `scratch._item` and for a refused create."""
    return scratch.recent_moment().isoformat(timespec="seconds")


def test_transactions_lifecycle(client, scratch):
    account_id = scratch.account("PEN", "USD")
    category_id = scratch.category()
    created = scratch.recent_row(
        account_id, -500, "USD", alone=True, category_id=category_id, title="coffee"
    )
    tx_id = created["id"]
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

    # `_item` and not `refused_row`: the body must lack `currency_code`, which every helper sets.
    missing = scratch._item(account_id, _recent(scratch), -500, "PEN", category_id=category_id)
    del missing["currency_code"]
    scratch.transactions.append(missing["id"])
    err = refused(lambda: client.post("/transactions", json_body=missing))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "REQUIRED")

    err = scratch.refused_row(account_id, _recent(scratch), "USD", category_id=category_id)
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "CURRENCY_NOT_HELD")
    assert err.fields["currency_code"] == "Must be a currency the account holds."
    assert client.get("/transactions/count", params={"account_id": account_id}) == {"count": 0}


def test_an_empty_description_empties_the_note_and_null_is_refused(client, scratch):
    """`""` empties a note and `null` is `422` `NOT_NULL` on `description`, so the
    Edit form sends `""` for an emptied note
    (contract: PUT /v1/transactions/{transaction_id})."""
    account_id = scratch.account()
    category_id = scratch.category()
    tx_id = scratch.recent_row(
        account_id,
        -500,
        alone=True,
        category_id=category_id,
        title="pharmacy",
        description="receta",
    )["id"]

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
    # Three rows in one batch: `_create` sends a list, `recent_row` only one row.
    when = _recent(scratch)
    items = [
        scratch._item(account_id, when, -100 * n, currency, category_id=category_id, title=title)
        for n, (title, currency) in enumerate(zip("abc", currencies, strict=True), start=1)
    ]

    created = scratch._create(items)
    assert {item["id"] for item in created} == {item["id"] for item in items}
    echoed = {item["id"]: (item["account_id"], item["currency_code"]) for item in created}
    assert echoed == {item["id"]: (account_id, item["currency_code"]) for item in items}


def test_a_batch_item_without_a_currency_is_refused(client, scratch):
    """A batch item missing `currency_code` is refused on the item's own key, and the
    batch writes nothing (contract: POST /v1/transactions/batch)."""
    account_id = scratch.account()
    category_id = scratch.category()
    # `_item`: the item must lack `currency_code`, which every helper sets.
    item = scratch._item(account_id, _recent(scratch), -500, "PEN", category_id=category_id)
    del item["currency_code"]
    scratch.transactions.append(item["id"])

    err = refused(lambda: client.post("/transactions/batch", json_body={"transactions": [item]}))
    assert_refusal(err, 422, "VALIDATION_ERROR", "transactions.0.currency_code", "REQUIRED")
    assert client.get("/transactions/count", params={"account_id": account_id}) == {"count": 0}
