"""Contract: the built-in pending hashtag, found by `system_key` `pending`.

Every live transaction carries at least one hashtag; one written with none lands on
the pending hashtag (contract: "Hashtags", "The built-in pending hashtag"). Home's
"needs a hashtag" row and every hashtag write in the app stand on that. Pinned here:

  · `POST /transactions` with no `hashtag_ids` comes back on `[<pending>]`, and
    `?hashtag_id=<pending>` lists it;
  · `PUT` with `[<real>]` replaces the pending hashtag, and `PUT` with `[]` puts
    it back;
  · the refusals: the pending hashtag beside another is `PENDING_HASHTAG_NOT_ALONE`
    on `hashtag_ids` (on a split part, `parts.<i>.hashtag_ids`); any hashtag on an
    opening balance is `OPENING_BALANCE_NOT_TAGGED` on `hashtag_ids`, while `[]` on
    it is accepted; a user hashtag created or renamed `Pendiente` is
    `RESERVED_NAME` on `name`.

Deleting the pending hashtag (`SYSTEM_HASHTAG`) is pinned with the other `403`s in
test_refusal_reasons.py. The pending hashtag is engine-created and can never be
deleted, so it stays behind on the practice user.

Each test builds its own account and hashtag and undoes what it wrote. Gating,
target and the real-ledger guard: conftest.py.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense.errors import EngineError
from expense.reads import pending_hashtag_of
from tests.contract.conftest import reason_on


def _safe(call, *args):
    try:
        call(*args)
    except EngineError:
        pass


def _refused(call) -> EngineError:
    with pytest.raises(EngineError) as excinfo:
        call()
    return excinfo.value


def _date(client) -> str:
    zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
    return datetime(2026, 5, 4, 12, tzinfo=zone).isoformat(timespec="seconds")


def _make_account(client) -> str:
    new_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={"id": new_id, "name": f"contract-pending-{new_id[:8]}", "currency_code": "PEN"},
    )
    return new_id


def _make_hashtag(client) -> str:
    new_id = str(uuid4())
    client.post("/hashtags", json_body={"id": new_id, "name": f"contract-pending-{new_id[:8]}"})
    return new_id


def _post_untagged(client, account_id: str, date: str) -> dict:
    return client.post(
        "/transactions",
        json_body={
            "id": str(uuid4()),
            "amount_cents": -100,
            "account_id": account_id,
            "date": date,
        },
    )


def _pending_id(client) -> str:
    """The pending hashtag's id, by `system_key`, never by name."""
    found = pending_hashtag_of(client.get("/hashtags")["items"])
    assert found is not None, "an untagged write did not make the pending hashtag exist"
    return found[0]


def test_an_untagged_write_lands_on_pending_and_a_real_hashtag_replaces_it(client):
    account = _make_account(client)
    real = _make_hashtag(client)
    tx_id = None
    try:
        created = _post_untagged(client, account, _date(client))
        tx_id = created["id"]
        pending = _pending_id(client)
        assert created["hashtag_ids"] == [pending]
        waiting = client.get("/transactions", params={"hashtag_id": pending, "account_id": account})
        assert [item["id"] for item in waiting["items"]] == [tx_id]

        tagged = client.put(f"/transactions/{tx_id}", json_body={"hashtag_ids": [real]})
        assert tagged["hashtag_ids"] == [real]
        waiting = client.get("/transactions", params={"hashtag_id": pending, "account_id": account})
        assert waiting["items"] == []

        back = client.put(f"/transactions/{tx_id}", json_body={"hashtag_ids": []})
        assert back["hashtag_ids"] == [pending]
    finally:
        if tx_id:
            _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/hashtags/{real}")
        _safe(client.delete, f"/accounts/{account}")


def test_the_pending_hashtag_beside_another_is_pending_hashtag_not_alone(client):
    account = _make_account(client)
    real = _make_hashtag(client)
    anchor = None
    refused_id = str(uuid4())
    part_ids = [str(uuid4()), str(uuid4())]
    try:
        date = _date(client)
        anchor = _post_untagged(client, account, date)["id"]
        pending = _pending_id(client)

        # A create.
        err = _refused(
            lambda: client.post(
                "/transactions",
                json_body={
                    "id": refused_id,
                    "amount_cents": -100,
                    "account_id": account,
                    "date": date,
                    "hashtag_ids": [pending, real],
                },
            )
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "hashtag_ids") == "PENDING_HASHTAG_NOT_ALONE"

        # An edit.
        err = _refused(
            lambda: client.put(
                f"/transactions/{anchor}", json_body={"hashtag_ids": [real, pending]}
            )
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "hashtag_ids") == "PENDING_HASHTAG_NOT_ALONE"

        # A split part, keyed by the part.
        err = _refused(
            lambda: client.post(
                f"/transactions/{anchor}/split",
                json_body={
                    "parts": [
                        {"id": part_ids[0], "amount_cents": -60},
                        {"id": part_ids[1], "amount_cents": -40, "hashtag_ids": [pending, real]},
                    ]
                },
            )
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "parts.1.hashtag_ids") == "PENDING_HASHTAG_NOT_ALONE"

        # Nothing was written.
        assert client.get(f"/transactions/{anchor}")["hashtag_ids"] == [pending]
        listed = client.get("/transactions", params={"account_id": account})
        assert [item["id"] for item in listed["items"]] == [anchor]
    finally:
        for tx_id in [refused_id, *part_ids, anchor]:
            if tx_id:
                _safe(client.delete, f"/transactions/{tx_id}")
        _safe(client.delete, f"/hashtags/{real}")
        _safe(client.delete, f"/accounts/{account}")


def test_an_opening_balance_carries_no_hashtag(client):
    account = _make_account(client)
    real = _make_hashtag(client)
    opening = str(uuid4())
    try:
        created = client.post(
            f"/accounts/{account}/opening-balance",
            json_body={
                "transaction_id": opening,
                "amount_cents": 10000,
                "date": "2026-01-01T00:00:00Z",
            },
        )
        assert created["hashtag_ids"] == []

        err = _refused(
            lambda: client.put(f"/transactions/{opening}", json_body={"hashtag_ids": [real]})
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "hashtag_ids") == "OPENING_BALANCE_NOT_TAGGED"
        assert client.get(f"/transactions/{opening}")["hashtag_ids"] == []

        accepted = client.put(f"/transactions/{opening}", json_body={"hashtag_ids": []})
        assert accepted["hashtag_ids"] == []
    finally:
        _safe(client.delete, f"/transactions/{opening}")
        _safe(client.delete, f"/hashtags/{real}")
        _safe(client.delete, f"/accounts/{account}")


def test_a_user_hashtag_cannot_be_named_pendiente(client):
    refused_id = str(uuid4())
    real = _make_hashtag(client)
    try:
        # Compared after trimming, ignoring case.
        err = _refused(
            lambda: client.post("/hashtags", json_body={"id": refused_id, "name": " pendiente "})
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "name") == "RESERVED_NAME"

        err = _refused(lambda: client.put(f"/hashtags/{real}", json_body={"name": "PENDIENTE"}))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert reason_on(err, "name") == "RESERVED_NAME"
        assert client.get(f"/hashtags/{real}")["name"].startswith("contract-pending-")
    finally:
        _safe(client.delete, f"/hashtags/{refused_id}")
        _safe(client.delete, f"/hashtags/{real}")
