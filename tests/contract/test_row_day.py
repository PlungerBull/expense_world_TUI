"""Contract: every transaction an answer carries has a `day`.

`day` is a bare `YYYY-MM-DD`, never null: the calendar day of `date` in the user's
`display_timezone`, the day every day filter counts the row on. `date` stays an instant
in UTC. `day` is read-only and moves with the time zone on the next read, with no write
(contract: GET /v1/transactions).

The practice user's time zone is read first and put back after: a test that moves it
restores it whatever happens.
"""

import pytest

from tests.contract.conftest import assert_refusal, refused

LIMA = "America/Lima"
TOKYO = "Asia/Tokyo"
#: 23:30 on the 4th in Lima (UTC-5), the early hours of the 5th in UTC
SENT = "2026-11-04T23:30:00-05:00"
UTC_INSTANT = "2026-11-05T04:30:00Z"


@pytest.fixture
def lima(client):
    """The practice user's `display_timezone` set to Lima for the test and put back after."""
    before = client.get("/auth/me")["settings"]["display_timezone"]
    if before != LIMA:
        client.put("/auth/settings", json_body={"display_timezone": LIMA})
    try:
        yield
    finally:
        if client.get("/auth/me")["settings"]["display_timezone"] != before:
            client.put("/auth/settings", json_body={"display_timezone": before})


def _ids_on(client, account_id: str, day: str) -> list[str]:
    body = client.get(
        "/transactions",
        params={"account_id": account_id, "date_from": day, "date_to": day},
    )
    return [row["id"] for row in body["items"]]


def test_a_row_carries_its_day_in_the_users_zone_on_every_read(client, scratch, lima):
    account_id = scratch.account()
    made = scratch.row_at(account_id, SENT, -100, "PEN", alone=True)
    assert (made["date"], made["day"]) == (UTC_INSTANT, "2026-11-04")

    one = client.get(f"/transactions/{made['id']}")
    assert (one["date"], one["day"]) == (UTC_INSTANT, "2026-11-04")

    listed = client.get("/transactions", params={"account_id": account_id})["items"]
    assert [(r["id"], r["date"], r["day"]) for r in listed] == [
        (made["id"], UTC_INSTANT, "2026-11-04")
    ]

    assert _ids_on(client, account_id, "2026-11-04") == [made["id"]]
    assert _ids_on(client, account_id, "2026-11-05") == []


def test_day_sent_on_a_write_is_unknown(client, scratch, lima):
    account_id = scratch.account()
    made = scratch.row_at(account_id, SENT, -100, "PEN", alone=True)

    err = refused(
        lambda: client.post(
            "/transactions",
            json_body=scratch.body(account_id, -100, "PEN", when=SENT, day="2026-11-04"),
        )
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "day", "UNKNOWN_FIELD")

    err = refused(
        lambda: client.put(f"/transactions/{made['id']}", json_body={"day": "2026-11-05"})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "day", "UNKNOWN_FIELD")
    assert client.get(f"/transactions/{made['id']}")["day"] == "2026-11-04"


def test_day_follows_a_time_zone_change_with_no_write(client, scratch, lima):
    account_id = scratch.account()
    made = scratch.row_at(account_id, SENT, -100, "PEN", alone=True)
    before = client.get(f"/transactions/{made['id']}")
    assert before["day"] == "2026-11-04"

    client.put("/auth/settings", json_body={"display_timezone": TOKYO})
    after = client.get(f"/transactions/{made['id']}")
    assert (after["date"], after["day"]) == (UTC_INSTANT, "2026-11-05")
    assert _ids_on(client, account_id, "2026-11-05") == [made["id"]]
    assert _ids_on(client, account_id, "2026-11-04") == []
    assert after["updated_at"] == before["updated_at"]
