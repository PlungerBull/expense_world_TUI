"""Contract lifecycle for the three named resources.

Accounts: create → update → archive → unarchive → delete.
Categories and hashtags: create → update → delete — they have no
archive routes, and accounts (people included) are the only archivable
resource.

Every lifecycle ends on "deleted is deleted": the row leaves
every list, its get is a 404, and there is no `restore`.

An archived account's transactions stay editable, splittable and deletable, but
a `PUT` that sends the archived account's id as `account_id` is refused, even
unchanged (contract: POST /v1/accounts/{account_id}/archive).

An account or a category created with no `color` comes back with the engine's
default colour.

Hits a real engine. Gating, target resolution and the real-ledger guard live in
conftest.py; uses ExpenseClient directly so each test owns its idempotency keys.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from expense.errors import EngineError
from tests.contract.conftest import reason_on


def _list_all(client, resource: str, **flags) -> list[dict]:
    """The whole collection, in one read.

    The engine returns accounts, categories and hashtags whole
    as `{items}` and refuses `limit`/`offset` with a 422 — so this also pins
    that a plain read is the entire list, not a default page.
    """
    params = {flag: "true" for flag, on in flags.items() if on}
    body = client.get(f"/{resource}", params=params or None)
    assert set(body) == {"items"}, f"/{resource} is no longer the whole-list shape: {sorted(body)}"
    return body["items"]


def _assert_gone(client, resource: str, row_id: str) -> None:
    """A deleted row is invisible: absent from the list, 404 on get and restore."""
    assert not any(r["id"] == row_id for r in _list_all(client, resource))
    with pytest.raises(EngineError) as got:
        client.get(f"/{resource}/{row_id}")
    assert got.value.status == 404
    with pytest.raises(EngineError) as restored:
        client.post(f"/{resource}/{row_id}/restore")
    assert restored.value.status == 404


def test_accounts_lifecycle(client):
    new_id = str(uuid4())
    name = f"contract-account-{new_id[:8]}"

    created = client.post(
        "/accounts",
        json_body={"id": new_id, "name": name, "currency_code": "USD"},
    )
    try:
        assert created["id"] == new_id
        assert created["name"] == name

        fetched = client.get(f"/accounts/{new_id}")
        assert fetched["id"] == new_id

        updated = client.put(f"/accounts/{new_id}", json_body={"name": f"{name}-renamed"})
        assert updated["name"] == f"{name}-renamed"

        active = _list_all(client, "accounts")
        assert any(a["id"] == new_id for a in active)

        client.post(f"/accounts/{new_id}/archive")
        active_after = _list_all(client, "accounts")
        assert not any(a["id"] == new_id for a in active_after)

        archived = _list_all(client, "accounts", include_archived=True)
        assert any(a["id"] == new_id for a in archived)

        client.post(f"/accounts/{new_id}/unarchive")
        client.delete(f"/accounts/{new_id}")
        _assert_gone(client, "accounts", new_id)
    finally:
        # Best-effort cleanup; ignore if already deleted.
        try:
            client.delete(f"/accounts/{new_id}")
        except Exception:
            pass


def test_categories_lifecycle(client):
    new_id = str(uuid4())
    name = f"contract-cat-{new_id[:8]}"

    created = client.post(
        "/categories",
        json_body={"id": new_id, "name": name, "color": "#123456"},
    )
    try:
        assert created["id"] == new_id

        fetched = client.get(f"/categories/{new_id}")
        assert fetched["id"] == new_id

        updated = client.put(f"/categories/{new_id}", json_body={"name": f"{name}-renamed"})
        assert updated["name"] == f"{name}-renamed"

        # No archive/unarchive arm: those routes 404. Pin the
        # deletion so a silent re-introduction would be caught.
        active = _list_all(client, "categories")
        assert any(c["id"] == new_id for c in active)

        client.delete(f"/categories/{new_id}")
        _assert_gone(client, "categories", new_id)
    finally:
        try:
            client.delete(f"/categories/{new_id}")
        except Exception:
            pass


def test_hashtags_lifecycle(client):
    new_id = str(uuid4())
    name = f"contract-tag-{new_id[:8]}"

    created = client.post("/hashtags", json_body={"id": new_id, "name": name})
    try:
        assert created["id"] == new_id

        fetched = client.get(f"/hashtags/{new_id}")
        assert fetched["id"] == new_id

        updated = client.put(f"/hashtags/{new_id}", json_body={"name": f"{name}-renamed"})
        assert updated["name"] == f"{name}-renamed"

        # Same as categories — no archive routes.
        active = _list_all(client, "hashtags")
        assert any(h["id"] == new_id for h in active)

        client.delete(f"/hashtags/{new_id}")
        _assert_gone(client, "hashtags", new_id)
    finally:
        try:
            client.delete(f"/hashtags/{new_id}")
        except Exception:
            pass


def test_an_archived_accounts_transaction_stays_editable_but_refuses_its_account_id(client):
    """On a transaction whose account is archived, a `PUT` of `category_id` and of
    `description`, a split and a delete each go through; a `PUT` sending the
    archived account's own `account_id`, unchanged, is `422` `INVALID_REFERENCE`
    on `account_id` and writes nothing (contract: POST /v1/accounts/{account_id}/archive).
    So the Edit form sends `account_id` only when it changes, and no picker offers
    an archived account."""
    account_id = str(uuid4())
    category_id = str(uuid4())
    tx_id = str(uuid4())
    part_ids = [str(uuid4()), str(uuid4())]
    client.post(
        "/accounts",
        json_body={
            "id": account_id,
            "name": f"contract-arch-{account_id[:8]}",
            "currency_code": "PEN",
        },
    )
    try:
        client.post(
            "/categories",
            json_body={"id": category_id, "name": f"contract-cat-{category_id[:8]}"},
        )
        client.post(
            "/transactions",
            json_body={
                "id": tx_id,
                "title": "archived-row",
                "amount_cents": -1000,
                "account_id": account_id,
                "date": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
        client.post(f"/accounts/{account_id}/archive")
        assert client.get(f"/accounts/{account_id}")["is_archived"] is True

        recategorised = client.put(f"/transactions/{tx_id}", json_body={"category_id": category_id})
        assert recategorised["category_id"] == category_id
        noted = client.put(f"/transactions/{tx_id}", json_body={"description": "still editable"})
        assert noted["description"] == "still editable"

        before = client.get(f"/transactions/{tx_id}")
        with pytest.raises(EngineError) as refused:
            client.put(f"/transactions/{tx_id}", json_body={"account_id": account_id})
        assert refused.value.status == 422
        assert reason_on(refused.value, "account_id") == "INVALID_REFERENCE"
        assert client.get(f"/transactions/{tx_id}") == before  # nothing written

        split = client.post(
            f"/transactions/{tx_id}/split",
            json_body={
                "parts": [
                    {"id": part_ids[0], "amount_cents": -600, "category_id": category_id},
                    {"id": part_ids[1], "amount_cents": -400},
                ]
            },
        )
        assert [p["id"] for p in split["parts"]] == part_ids
        assert {p["account_id"] for p in split["parts"]} == {account_id}

        deleted = client.delete(f"/transactions/{part_ids[0]}")
        assert deleted["deleted_at"] is not None
    finally:
        for path in (
            *(f"/transactions/{i}" for i in (*part_ids, tx_id)),
            f"/categories/{category_id}",
            f"/accounts/{account_id}",
        ):
            try:
                client.delete(path)
            except EngineError:
                pass


#: The colour a create gives when `color` is left out (contract: "Colour format").
DEFAULT_COLOR = "#3b82f6"


@pytest.mark.parametrize(
    ("resource", "extra"),
    [("accounts", {"currency_code": "PEN"}), ("categories", {})],
)
def test_a_create_without_a_colour_gets_the_engine_default(client, resource, extra):
    """A body with no `color` key comes back with the engine's default, on the
    create and on a read."""
    new_id = str(uuid4())
    try:
        created = client.post(
            f"/{resource}",
            json_body={"id": new_id, "name": f"contract-color-{new_id[:8]}", **extra},
        )
        assert created["color"] == DEFAULT_COLOR
        assert client.get(f"/{resource}/{new_id}")["color"] == DEFAULT_COLOR
    finally:
        try:
            client.delete(f"/{resource}/{new_id}")
        except EngineError:
            pass
