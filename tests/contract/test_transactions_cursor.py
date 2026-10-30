"""Contract: the engine's three list shapes.

The app's ledger, the "no batch" list and the reference lists are built on
these facts, and the unit suite can only mock them:

  · `GET /transactions` pages by cursor to a null `next_cursor`, with no row
    repeated; `sort=date_asc` is the exact reverse of the default; `/count`
    equals the rows walked; `offset` is a 422.
  · A bare day in `date_to` is the whole calendar day; a naive datetime is a
    422 in the standard error envelope.
  · `GET /activity` is a cursor inside a date window, and the older window is
    read by sending the response's `previous_date_to` back unchanged as
    `date_to`; walking back that way reads no row twice, even one created at
    the very first instant of a window.
  · The small lists come back whole: `{items}` and nothing else.

Every transaction test writes to its own fresh account, so the reads are scoped
to rows this file created. Gating, target and the real-ledger guard: conftest.py.
"""

from datetime import datetime

import pytest

from expense.errors import EngineError

ROWS = 7


def _post_row(scratch, account_id: str, when: datetime, currency: str = "PEN") -> str:
    """A `-100` row of `account_id` in `currency` at `when`; its id."""
    made = scratch.row(
        account_id,
        "2026-01-01",
        -100,
        currency,
        title="cursor row",
        date=when.isoformat(timespec="seconds"),
    )
    return made["id"]


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
def seeded(scratch):
    """One account holding ROWS rows, three of them sharing one date, so the
    walk crosses a tie that only `created_at` / `id` can order. The rows are in both of
    the account's currencies: the account's list covers them all."""
    account_id = scratch.account("PEN", "USD")
    tx_ids = [
        _post_row(
            scratch,
            account_id,
            datetime(2026, 2, day, 12, tzinfo=scratch.zone),
            "USD" if day == 9 else "PEN",
        )
        for day in (3, 5, 5, 5, 8, 9, 12)
    ]
    return account_id, tx_ids


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


def test_a_bare_to_day_includes_a_row_late_on_that_day(client, scratch):
    """`GET /transactions?date_to=<day>` with a bare day: the engine
    reads it as the whole day in `display_timezone` (contract: GET /v1/transactions)."""
    account_id = scratch.account()
    late = _post_row(scratch, account_id, datetime(2026, 2, 20, 23, 30, tzinfo=scratch.zone))
    body = client.get(
        "/transactions",
        params={"account_id": account_id, "date_from": "2026-02-20", "date_to": "2026-02-20"},
    )
    assert [row["id"] for row in body["items"]] == [late]


def test_a_naive_datetime_filter_is_a_422_in_the_envelope(client):
    """Every request datetime needs an offset (contract: "Datetime inputs"). The app
    shows the envelope, so the refusal must arrive as one: code, message and
    the offending key."""
    with pytest.raises(EngineError) as excinfo:
        client.get("/transactions", params={"date_from": "2026-02-20T10:00:00"})
    err = excinfo.value
    assert err.status == 422
    assert err.code and err.message
    assert "date_from" in (err.fields or {})


def test_activity_walks_a_window_then_steps_to_the_older_one(client, scratch):
    """`GET /activity` pages inside a window, and the older window ends at the
    echoed `previous_date_to`. A create and a rename guarantee two entries in
    the current window; a page of 1 walks them to a null cursor."""
    account_id = scratch.account()
    client.put(f"/accounts/{account_id}", json_body={"name": f"contract-act-{account_id[:8]}"})
    seen: list[str] = []
    after = None
    window = None
    previous = None
    while True:
        params = {"resource_id": account_id, "limit": 1}
        if after:
            params["after"] = after
        body = client.get("/activity", params=params)
        window = window or (body["date_from"], body["date_to"])
        previous = previous or body["previous_date_to"]
        assert (body["date_from"], body["date_to"]) == window  # travels in the cursor
        seen += [entry["id"] for entry in body["items"]]
        after = body["next_cursor"]
        if after is None:
            break
    assert len(seen) == len(set(seen)) >= 2

    older = client.get(
        "/activity",
        params={"resource_id": account_id, "date_to": previous},
    )
    assert "items" in older and "next_cursor" in older
    assert not set(seen) & {entry["id"] for entry in older["items"]}


def _activity_window(client, params: dict) -> tuple[dict, list[str]]:
    """One activity window read to its null cursor: its first page, and every
    entry id in it, in order."""
    first = None
    ids: list[str] = []
    after = None
    while True:
        body = client.get("/activity", params={**params, **({"after": after} if after else {})})
        first = first or body
        ids += [entry["id"] for entry in body["items"]]
        after = body["next_cursor"]
        if after is None:
            return first, ids


def test_activity_walks_back_by_previous_date_to_and_reads_no_row_twice(client, scratch):
    """Walking back sends each response's `previous_date_to` unchanged as the
    next `date_to`, with no date arithmetic, and stops on `null` (contract:
    "Date windows").

    The first window starts at the exact `created_at` of the account's create
    entry, so that entry sits on the window's first instant: a walk that reused
    the echoed `date_from` as the next `date_to` would read it twice. Three
    windows are walked, or fewer if `previous_date_to` comes back `null`.
    """
    account_id = scratch.account()
    client.put(f"/accounts/{account_id}", json_body={"name": f"contract-walk-{account_id[:8]}"})
    _, current = _activity_window(client, {"resource_id": account_id})
    # newest first (contract: GET /v1/activity), so the create is the last entry
    entries = client.get("/activity", params={"resource_id": account_id})["items"]
    create = entries[-1]
    assert create["before_snapshot"] is None
    assert create["id"] in current

    params = {"resource_id": account_id, "date_from": create["created_at"]}
    seen: list[str] = []
    windows = 0
    while windows < 3:
        first, ids = _activity_window(client, params)
        if "date_to" in params:
            assert first["date_to"] == params["date_to"]  # sent back unchanged
        seen += ids
        windows += 1
        previous = first["previous_date_to"]
        if previous is None:
            break
        params = {"resource_id": account_id, "date_to": previous}
    assert windows >= 2
    assert len(seen) == len(set(seen))
    assert seen.count(create["id"]) == 1


@pytest.mark.parametrize("path", ["/accounts", "/categories", "/hashtags"])
def test_a_small_list_is_whole(client, path):
    """No `limit`, `next_cursor` or `total`: the app reads every row in one call
    on the strength of this, and a stale `limit` is a 422."""
    body = client.get(path)
    assert set(body) == {"items"}
    with pytest.raises(EngineError) as excinfo:
        client.get(path, params={"limit": 50})
    assert excinfo.value.status == 422
