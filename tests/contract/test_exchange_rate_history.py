"""Contract: exchange-rate history is a cursor inside a window of calendar days.

No screen reads `GET /exchange-rates/history`, so this file is the only client
exercising it:

  · The older window is read by sending the response's `previous_date_to` back
    unchanged as `date_to`; walking back that way reads no rate twice, even one
    dated on a window's first day (contract: "Date windows").
  · A window wider than 366 calendar days, counting both ends, is a 422
    `RANGE_TOO_WIDE` on both keys; exactly 366 is accepted.
  · A default window that would start before the calendar does is a 422
    `OUT_OF_RANGE` on `date_from`.

A rate is identified by its day and pair: there is at most one rate per pair per
day (contract: GET /v1/exchange-rates/history). The tests only read, so there is
nothing to clean up. Gating, target and the real-ledger guard: conftest.py.
"""

import pytest

from expense.errors import EngineError
from tests.contract.conftest import reason_on

PATH = "/exchange-rates/history"


def _rate_key(rate: dict) -> tuple[str, str, str]:
    return rate["rate_date"], rate["base"], rate["target"]


def _window(client, params: dict, *, limit: int = 7) -> tuple[dict, list[tuple[str, str, str]]]:
    """One window read to its null cursor: its first page, and every rate in it,
    in order. A small page makes the walk cross page edges."""
    first = None
    keys: list[tuple[str, str, str]] = []
    after = None
    while True:
        page = {**params, "limit": limit, **({"after": after} if after else {})}
        body = client.get(PATH, params=page)
        assert set(body) == {
            "items",
            "limit",
            "next_cursor",
            "date_from",
            "date_to",
            "previous_date_to",
        }
        first = first or body
        assert (body["date_from"], body["date_to"]) == (first["date_from"], first["date_to"])
        keys += [_rate_key(rate) for rate in body["items"]]
        after = body["next_cursor"]
        if after is None:
            return first, keys


def test_history_walks_back_by_previous_date_to_and_reads_no_rate_twice(client):
    """Walking back sends each response's `previous_date_to` unchanged as the
    next `date_to`, with no date arithmetic, and stops on `null` (contract:
    "Date windows").

    The first window starts on a day the engine holds rates for, taken from the
    default window, so those rates sit on the window's first day: a walk that
    reused the echoed `date_from` as the next `date_to` would read them twice.
    Three windows are walked, or fewer if `previous_date_to` comes back `null`.
    """
    default, current = _window(client, {})
    assert current, "the practice user holds no exchange rates"
    boundary = current[len(current) // 2][0]
    on_boundary = {key for key in current if key[0] == boundary}

    params: dict = {"date_from": boundary, "date_to": default["date_to"]}
    seen: list[tuple[str, str, str]] = []
    windows = 0
    older_rows = 0
    while windows < 3:
        first, keys = _window(client, params)
        assert first["date_to"] == params["date_to"]  # sent back unchanged
        if windows == 0:
            assert first["date_from"] == boundary
            assert on_boundary <= set(keys)
        else:
            older_rows += len(keys)
        seen += keys
        windows += 1
        previous = first["previous_date_to"]
        if previous is None:
            break
        params = {"date_to": previous}
    assert windows >= 2
    assert older_rows > 0, "the older windows hold no rates, so the walk proves nothing"
    assert len(seen) == len(set(seen))
    for key in on_boundary:
        assert seen.count(key) == 1


def test_a_window_on_the_calendar_s_first_day_has_no_previous_window(client):
    """`previous_date_to` is `null` only when nothing earlier exists on the
    calendar: a window starting on 0001-01-01 (contract: "Date windows")."""
    body = client.get(PATH, params={"date_from": "0001-01-01", "date_to": "0001-01-01"})
    assert "previous_date_to" in body
    assert body["previous_date_to"] is None


def test_a_window_of_367_days_is_refused_and_366_is_accepted(client):
    """The widest window is 366 calendar days counting both ends, never
    clamped, refused on both keys (contract: "Date windows")."""
    with pytest.raises(EngineError) as excinfo:
        client.get(PATH, params={"date_from": "2025-01-01", "date_to": "2026-01-02"})
    err = excinfo.value
    assert err.status == 422
    assert err.code == "VALIDATION_ERROR"
    assert reason_on(err, "date_from") == "RANGE_TOO_WIDE"
    assert reason_on(err, "date_to") == "RANGE_TOO_WIDE"

    body = client.get(PATH, params={"date_from": "2025-01-01", "date_to": "2026-01-01"})
    assert (body["date_from"], body["date_to"]) == ("2025-01-01", "2026-01-01")


def test_a_default_window_before_the_calendar_is_out_of_range(client):
    """With `date_from` left out the window is 30 days counting `date_to`, and a
    default that would start before 0001-01-01 is refused on `date_from`, never
    clamped (contract: "Date windows"). The refusal arrives in the envelope."""
    with pytest.raises(EngineError) as excinfo:
        client.get(PATH, params={"date_to": "0001-01-15"})
    err = excinfo.value
    assert err.status == 422
    assert err.code == "VALIDATION_ERROR"
    assert err.message
    assert set(err.fields or {}) == {"date_from"}
    assert reason_on(err, "date_from") == "OUT_OF_RANGE"
