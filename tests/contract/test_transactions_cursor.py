"""Contract: the engine's three list shapes.

The CLI's ledger, the "no batch" list and every flat list command are built on
these facts, and the unit suite can only mock them:

  · `GET /transactions` pages by cursor to a null `next_cursor`, with no row
    repeated; `sort=date_asc` is the exact reverse of the default; `/count`
    equals the rows walked; `offset` is a 422.
  · A bare day in `date_to` is the whole calendar day; a naive datetime is a
    422 in the standard error envelope.
  · `GET /activity` is a cursor inside a date window, and the older window
    starts from the echoed `date_from`.
  · The small lists come back whole: `{items}` and nothing else.

Every transaction test writes to its own fresh account, so the reads are scoped
to rows this file created. Gating, target and the real-ledger guard: conftest.py.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense.errors import EngineError

ROWS = 7


def _safe_delete(client, path):
    try:
        client.delete(path)
    except EngineError:
        pass


def _zone(client) -> ZoneInfo:
    return ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])


def _make_account(client) -> str:
    new_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": new_id,
            "name": f"contract-cursor-{new_id[:8]}",
            "currency_code": "PEN",
        },
    )
    return new_id


def _post_row(client, account_id: str, when: datetime, title: str = "cursor row") -> str:
    new_id = str(uuid4())
    client.post(
        "/transactions",
        json_body={
            "id": new_id,
            "title": title,
            "amount_cents": -100,
            "account_id": account_id,
            "date": when.isoformat(timespec="seconds"),
        },
    )
    return new_id


def _walk(client, params: dict, *, limit: int) -> list[str]:
    ids: list[str] = []
    after = None
    while True:
        page_params = dict(params, limit=limit)
        if after:
            page_params["after"] = after
        body = client.get("/transactions", params=page_params)
        assert set(body) == {"items", "limit", "next_cursor"}
        ids += [row["id"] for row in body["items"]]
        after = body["next_cursor"]
        if after is None:
            return ids


@pytest.fixture
def seeded(client):
    """One account holding ROWS rows, three of them sharing one date, so the
    walk crosses a tie that only `created_at` / `id` can order."""
    zone = _zone(client)
    account_id = _make_account(client)
    tx_ids: list[str] = []
    try:
        for day in (3, 5, 5, 5, 8, 9, 12):
            tx_ids.append(_post_row(client, account_id, datetime(2026, 2, day, 12, tzinfo=zone)))
        yield account_id, tx_ids
    finally:
        for tx_id in tx_ids:
            _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_the_cursor_walks_every_row_once_both_ways_and_matches_the_count(client, seeded):
    """A page of 2 over 7 rows crosses page edges inside the tie. Descending
    and ascending hold the same rows in exactly opposite orders, and the count
    agrees with the walk: the ledger's `N of M loaded` rests on that."""
    account_id, tx_ids = seeded
    desc = _walk(client, {"account_id": account_id}, limit=2)
    asc = _walk(client, {"account_id": account_id, "sort": "date_asc"}, limit=2)

    assert len(desc) == len(set(desc)) == ROWS
    assert set(desc) == set(tx_ids)
    assert asc == desc[::-1]
    assert client.get("/transactions/count", params={"account_id": account_id}) == {"count": ROWS}


def test_a_page_holding_the_rest_has_no_cursor(client, seeded):
    """The only stop is a null cursor: a page that takes every remaining row
    already comes back null, so a client never asks for an empty page."""
    account_id, _ = seeded
    body = client.get("/transactions", params={"account_id": account_id, "limit": ROWS})
    assert len(body["items"]) == ROWS
    assert body["next_cursor"] is None


def test_offset_is_refused(client):
    with pytest.raises(EngineError) as excinfo:
        client.get("/transactions", params={"offset": 0})
    assert excinfo.value.status == 422


def test_a_cursor_is_bound_to_its_sort(client, seeded):
    """Changing the sort under a cursor is a 422 on `after`, so a client that
    forgets to start over fails loudly instead of skipping rows."""
    account_id, _ = seeded
    first = client.get("/transactions", params={"account_id": account_id, "limit": 2})
    with pytest.raises(EngineError) as excinfo:
        client.get(
            "/transactions",
            params={
                "account_id": account_id,
                "limit": 2,
                "sort": "date_asc",
                "after": first["next_cursor"],
            },
        )
    assert excinfo.value.status == 422
    assert "after" in (excinfo.value.fields or {})


def test_a_bare_to_day_includes_a_row_late_on_that_day(client):
    """`transactions list --to <day>` sends the bare day; the engine
    reads it as the whole day in `display_timezone` (contract: GET /v1/transactions)."""
    zone = _zone(client)
    account_id = _make_account(client)
    late = _post_row(client, account_id, datetime(2026, 2, 20, 23, 30, tzinfo=zone))
    try:
        body = client.get(
            "/transactions",
            params={"account_id": account_id, "date_from": "2026-02-20", "date_to": "2026-02-20"},
        )
        assert [row["id"] for row in body["items"]] == [late]
    finally:
        _safe_delete(client, f"/transactions/{late}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_a_naive_datetime_filter_is_a_422_in_the_envelope(client):
    """Every request datetime needs an offset (contract: "Datetime inputs"). The CLI
    renders the envelope, so the refusal must arrive as one: code, message and
    the offending key."""
    with pytest.raises(EngineError) as excinfo:
        client.get("/transactions", params={"date_from": "2026-02-20T10:00:00"})
    err = excinfo.value
    assert err.status == 422
    assert err.code and err.message
    assert "date_from" in (err.fields or {})


def test_activity_walks_a_window_then_steps_to_the_older_one(client):
    """`expense activity list` pages inside a window and offers the older
    window from the echoed `date_from`. A create and a rename guarantee two
    entries in the current window; a page of 1 walks them to a null cursor."""
    account_id = _make_account(client)
    try:
        client.put(f"/accounts/{account_id}", json_body={"name": f"contract-act-{account_id[:8]}"})
        seen: list[str] = []
        after = None
        window = None
        while True:
            params = {"resource_id": account_id, "limit": 1}
            if after:
                params["after"] = after
            body = client.get("/activity", params=params)
            window = window or (body["date_from"], body["date_to"])
            assert (body["date_from"], body["date_to"]) == window  # travels in the cursor
            seen += [entry["id"] for entry in body["items"]]
            after = body["next_cursor"]
            if after is None:
                break
        assert len(seen) == len(set(seen)) >= 2

        older = client.get(
            "/activity",
            params={"resource_id": account_id, "date_to": window[0]},
        )
        assert "items" in older and "next_cursor" in older
        assert not set(seen) & {entry["id"] for entry in older["items"]}
    finally:
        _safe_delete(client, f"/accounts/{account_id}")


@pytest.mark.parametrize("path", ["/accounts", "/categories", "/hashtags"])
def test_a_small_list_is_whole(client, path):
    """No `limit`, `next_cursor` or `total`: the list commands print every row
    and no paging line on the strength of this, and a stale `limit` is a 422."""
    body = client.get(path)
    assert set(body) == {"items"}
    with pytest.raises(EngineError) as excinfo:
        client.get(path, params={"limit": 50})
    assert excinfo.value.status == 422
