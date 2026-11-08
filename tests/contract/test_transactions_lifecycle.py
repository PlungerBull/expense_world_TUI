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


def test_a_create_leaves_out_an_only_currency_and_names_one_of_several(client, scratch):
    """Left out on a soles-only account, `currency_code` is the account's only currency and
    the answer names it; left out on an account holding two it is `422` `REQUIRED` with the
    codes held, an explicit `null` is `INVALID_FORMAT`, and a currency the account does not
    hold is `CURRENCY_NOT_HELD`, each on `currency_code`; a refusal writes nothing
    (contract: POST /v1/transactions, "Fields")."""
    soles = scratch.account("PEN")
    pair = scratch.account("PEN", "USD")
    category_id = scratch.category()

    # `body` and then `del`: the helpers always set `currency_code`, and these must lack it.
    left_out = scratch.body(soles, category_id=category_id)
    del left_out["currency_code"]
    made = client.post("/transactions", json_body=left_out)
    assert (made["account_id"], made["currency_code"]) == (soles, "PEN")
    assert client.get(f"/transactions/{left_out['id']}")["currency_code"] == "PEN"

    missing = scratch.body(pair, category_id=category_id)
    del missing["currency_code"]
    err = refused(lambda: client.post("/transactions", json_body=missing))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "REQUIRED")
    assert err.fields["currency_code"] == "Must be one of the account's currencies: PEN, USD."

    err = scratch.refused_row(pair, _recent(scratch), None, category_id=category_id)
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "INVALID_FORMAT")

    err = scratch.refused_row(soles, _recent(scratch), "USD", category_id=category_id)
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "CURRENCY_NOT_HELD")
    assert err.fields["currency_code"] == "Must be a currency the account holds."
    assert client.get("/transactions/count", params={"account_id": soles}) == {"count": 1}
    assert client.get("/transactions/count", params={"account_id": pair}) == {"count": 0}


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


def test_a_batch_item_without_a_currency_takes_an_only_currency_or_is_refused(client, scratch):
    """Items left without `currency_code` on a soles-only account are created in soles, the
    answer naming it; one on an account holding two is `422` `REQUIRED` on the item's own
    key and the batch writes nothing (contract: POST /v1/transactions/batch)."""
    soles = scratch.account("PEN")
    pair = scratch.account("PEN", "USD")
    category_id = scratch.category()

    # `body` and then `del`: the helpers always set `currency_code`, and these must lack it.
    items = [scratch.body(soles, category_id=category_id) for _ in range(2)]
    for item in items:
        del item["currency_code"]
    created = client.post("/transactions/batch", json_body={"transactions": items})["created"]
    assert [(row["account_id"], row["currency_code"]) for row in created] == [(soles, "PEN")] * 2

    good = scratch.body(pair, category_id=category_id)
    bad = scratch.body(pair, category_id=category_id)
    del bad["currency_code"]
    err = refused(
        lambda: client.post("/transactions/batch", json_body={"transactions": [good, bad]})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "transactions.1.currency_code", "REQUIRED")
    assert client.get("/transactions/count", params={"account_id": pair}) == {"count": 0}
