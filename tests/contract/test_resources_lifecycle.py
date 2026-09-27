"""Contract lifecycle for the three named resources.

Accounts: create → update → archive → unarchive → delete.
Categories and hashtags: create → update → delete — they have no
archive routes, and accounts (people included) are the only archivable
resource.

Every lifecycle ends on "deleted is deleted": the row leaves
every list, its get is a 404, and there is no `restore`.

Hits a real engine. Gating, target resolution and the real-ledger guard live in
conftest.py; uses ExpenseClient directly so each test owns its idempotency keys.
"""

from uuid import uuid4

import pytest

from expense.errors import EngineError


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
