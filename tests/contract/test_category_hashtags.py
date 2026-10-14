"""Contract: a category's tags — `GET /v1/categories/{category_id}/hashtags`.

The rules a tag picker ranked by category stands on, which a mock can only
assume:

  · the answer is `{items}` whole, each row `{id, name, uses}` and nothing else;
  · `uses` counts transactions, most-used first, a tie going to the older tag;
  · a deleted transaction stops counting, and a tag left with no use is not
    returned at all;
  · a category never tagged is an empty list, while an unknown or deleted
    category is a 404;
  · the route takes no query parameter, so `?limit=` is a 422.

Every test writes to its own fresh account, category and tags, so the counts are
of rows this file created. Gating, target and the real-ledger guard: conftest.py.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from expense.errors import EngineError
from tests.contract.conftest import reason_on


def _safe_delete(client, path):
    try:
        client.delete(path)
    except EngineError:
        pass


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _make_account(client) -> str:
    new_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": new_id,
            "name": f"contract-cattags-{new_id[:8]}",
            "currency_code": "PEN",
        },
    )
    return new_id


def _make_category(client) -> str:
    new_id = str(uuid4())
    client.post(
        "/categories",
        json_body={
            "id": new_id,
            "name": f"contract-cattags-{new_id[:8]}",
            "color": "#123456",
        },
    )
    return new_id


def _make_hashtag(client, label: str, **extra) -> dict:
    """A fresh tag, returned whole: the tests need its stored `name` and `sort_order`."""
    new_id = str(uuid4())
    return client.post(
        "/hashtags",
        json_body={"id": new_id, "name": f"contract-cattags-{label}-{new_id[:8]}", **extra},
    )


def _post_row(client, account_id: str, category_id: str, hashtag_ids: list[str]) -> str:
    new_id = str(uuid4())
    client.post(
        "/transactions",
        json_body={
            "id": new_id,
            "title": "category tags row",
            "amount_cents": -100,
            "account_id": account_id,
            "category_id": category_id,
            "date": _now_iso(),
            "hashtag_ids": hashtag_ids,
        },
    )
    return new_id


def _category_tags(client, category_id: str) -> list[dict]:
    """The category's tags, with the response shape pinned on every read.

    The body is the unpaged `{items}` and nothing else (contract: "Base Conventions",
    "Lists come in three shapes, and none of them is paged by position"), and a row
    is `{id, name, uses}` only, never a full hashtag
    (contract: GET /v1/categories/{category_id}/hashtags).
    """
    body = client.get(f"/categories/{category_id}/hashtags")
    assert set(body) == {"items"}, f"no longer the whole-list shape: {sorted(body)}"
    for row in body["items"]:
        assert set(row) == {"id", "name", "uses"}, f"row is no longer a projection: {sorted(row)}"
        assert isinstance(row["id"], str)
        assert isinstance(row["name"], str)
        assert isinstance(row["uses"], int)
    return body["items"]


def test_category_tags_count_rows_most_used_first(client):
    account_id = _make_account(client)
    category_id = _make_category(client)
    other_category_id = _make_category(client)
    # The tie below is between `older` and `newer`. The older tag takes the later
    # name and the higher `sort_order`, so only creation time can put it first.
    older = _make_hashtag(client, "z-older")
    newer = _make_hashtag(client, "a-newer", sort_order=older["sort_order"] - 1)
    top = _make_hashtag(client, "top")
    elsewhere = _make_hashtag(client, "elsewhere")
    row_ids: list[str] = []

    try:
        row_ids.append(_post_row(client, account_id, category_id, [top["id"], older["id"]]))
        row_ids.append(_post_row(client, account_id, category_id, [top["id"], newer["id"]]))
        row_ids.append(_post_row(client, account_id, category_id, [top["id"]]))
        # A tag used only on another category is not this category's: a tag never
        # used on a category is not returned (contract:
        # GET /v1/categories/{category_id}/hashtags, "The relationship is derived from the ledger").
        row_ids.append(_post_row(client, account_id, other_category_id, [elsewhere["id"]]))

        tags = _category_tags(client, category_id)

        # Three rows carry five tag links. `uses` is the rows, not the links: a row
        # with two tags adds 1 to each
        # (contract: GET /v1/categories/{category_id}/hashtags, "`uses` counts transactions").
        assert {row["id"]: row["uses"] for row in tags} == {
            top["id"]: 3,
            older["id"]: 1,
            newer["id"]: 1,
        }

        # Most-used first; the two tags tied on one use come in creation order,
        # oldest first
        # (contract: GET /v1/categories/{category_id}/hashtags, "Ordering").
        assert [row["id"] for row in tags] == [top["id"], older["id"], newer["id"]]

        # `name` is the hashtag's own name: each row is a projection of the hashtag
        # (contract: GET /v1/categories/{category_id}/hashtags).
        assert {row["id"]: row["name"] for row in tags} == {
            tag["id"]: tag["name"] for tag in (top, older, newer)
        }

        # A deleted transaction no longer uses its tags: `top` drops to two, and
        # `older`, whose only row it was, leaves the list
        # (contract: GET /v1/categories/{category_id}/hashtags, "Exclusions").
        client.delete(f"/transactions/{row_ids[0]}")
        after = _category_tags(client, category_id)
        assert [(row["id"], row["uses"]) for row in after] == [(top["id"], 2), (newer["id"], 1)]
    finally:
        for row_id in row_ids:
            _safe_delete(client, f"/transactions/{row_id}")
        for tag in (older, newer, top, elsewhere):
            _safe_delete(client, f"/hashtags/{tag['id']}")
        _safe_delete(client, f"/categories/{category_id}")
        _safe_delete(client, f"/categories/{other_category_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_category_never_tagged_is_an_empty_list(client):
    account_id = _make_account(client)
    category_id = _make_category(client)
    row_id = None

    try:
        # An empty list is not a 404, with no row in the category and with an
        # untagged one (contract: GET /v1/categories/{category_id}/hashtags).
        assert _category_tags(client, category_id) == []
        row_id = _post_row(client, account_id, category_id, [])
        assert _category_tags(client, category_id) == []
    finally:
        if row_id:
            _safe_delete(client, f"/transactions/{row_id}")
        _safe_delete(client, f"/categories/{category_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_category_tags_of_an_unknown_category_is_404(client):
    """404 on a category that does not exist or is deleted
    (contract: GET /v1/categories/{category_id}/hashtags), in the engine's envelope:
    `fields` and `reasons` are null on every code but a validation failure
    (contract: "Base Conventions", "`fields` and `reasons` semantics")."""
    category_id = _make_category(client)
    client.delete(f"/categories/{category_id}")

    for gone in (str(uuid4()), category_id):
        with pytest.raises(EngineError) as excinfo:
            client.get(f"/categories/{gone}/hashtags")
        err = excinfo.value
        assert err.status == 404
        assert err.code == "NOT_FOUND"
        assert err.message
        assert err.fields is None
        assert err.reasons is None
        assert set(err.raw_body) == {"error"}


def test_category_tags_take_no_query_parameter(client):
    """The route declares no query parameter
    (contract: GET /v1/categories/{category_id}/hashtags), so a paging flag is
    refused, not ignored: 422 with one `fields` entry per name
    (contract: "Base Conventions", "Unknown query parameters")."""
    category_id = _make_category(client)

    try:
        for param in ("limit", "offset"):
            with pytest.raises(EngineError) as excinfo:
                client.get(f"/categories/{category_id}/hashtags", params={param: 1})
            err = excinfo.value
            assert err.status == 422
            assert err.code == "VALIDATION_ERROR"
            assert set(err.fields or {}) == {param}
            assert reason_on(err, param) == "UNKNOWN_PARAMETER"
    finally:
        _safe_delete(client, f"/categories/{category_id}")
