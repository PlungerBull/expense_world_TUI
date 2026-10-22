"""Contract: a create sent again answers `ID_EXISTS` on its own id, before anything else.

Every create judges a request in steps and answers with the first that refuses it: what
the request alone shows, then a taken `id`, then everything that reads the ledger
(contract: "Base Conventions", "Which refusal comes first on a create"). The batch
writer (expense/batch_write.py) and the sheet import's opening balances stand on it: a
row refused only for its own taken id is already in the ledger, so a re-run counts it
as already there instead of failing it. Pinned here:

  · a landed batch sent again whole is `409` `ID_EXISTS` on every item's
    `transactions.<i>.id`, one entry per item, and nothing new is written;
  · a batch mixing landed items and a new one names only the landed ones, and the
    batch writer settles it in two requests: the landed rows already there, the new
    one created;
  · a landed opening balance sent again is `409` `ID_EXISTS` on `transaction_id`, not
    `OPENING_BALANCE_EXISTS`, though the account holds it;
  · a landed split sent again is `409` `ID_EXISTS` on each `parts.<i>.id`.

Every value a test writes is fresh per run (UUIDs, an account named by one): the
practice user's data outlives a reseed. Each test builds its own account and undoes
what it wrote. Gating, target and the real-ledger guard: conftest.py.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from expense.batch_write import RowResult, post_transaction_batch
from expense.errors import EngineError


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
    return datetime(2026, 4, 14, 12, tzinfo=zone).isoformat(timespec="seconds")


def _make_account(client, new_id: str) -> None:
    """Create the account `new_id`, minted before the test's `try` so its cleanup
    can delete it whichever setup step fails."""
    client.post(
        "/accounts",
        json_body={"id": new_id, "name": f"contract-again-{new_id[:8]}", "currency_code": "PEN"},
    )


def _item(account_id: str, date: str, amount: int) -> dict:
    return {
        "id": str(uuid4()),
        "title": "contract sent again",
        "amount_cents": amount,
        "account_id": account_id,
        "date": date,
    }


def _live_ids(client, account_id: str) -> set[str]:
    listed = client.get("/transactions", params={"account_id": account_id})
    return {item["id"] for item in listed["items"]}


def _cleanup(client, tx_ids: list[str], account_id: str) -> None:
    for tx_id in tx_ids:
        _safe(client.delete, f"/transactions/{tx_id}")
    _safe(client.delete, f"/accounts/{account_id}")


def test_a_landed_batch_sent_again_names_every_items_id(client):
    """Step 2 of a batch names every item whose id already exists, one
    `transactions.<i>.id` entry each, and a batch sent again whole answers it on
    every item (contract: POST /v1/transactions/batch). Nothing is written
    (contract: POST /v1/transactions/batch, "No partial success")."""
    account = str(uuid4())
    items: list[dict] = []
    try:
        _make_account(client, account)
        date = _date(client)
        items = [_item(account, date, amount) for amount in (-100, -200, -300)]
        client.post("/transactions/batch", json_body={"transactions": items})

        body = {"transactions": items}
        err = _refused(lambda: client.post("/transactions/batch", json_body=body))
        assert (err.status, err.code) == (409, "CONFLICT")
        keys = [f"transactions.{i}.id" for i in range(len(items))]
        assert err.reasons == dict.fromkeys(keys, "ID_EXISTS")
        assert set(err.fields or {}) == set(keys)
        assert _live_ids(client, account) == {item["id"] for item in items}
    finally:
        _cleanup(client, [item["id"] for item in items], account)


def test_the_batch_writer_settles_landed_and_new_rows_in_two_requests(client, statuses):
    """A batch mixing landed items and a new one is `409` naming only the landed
    ones (contract: POST /v1/transactions/batch); the writer counts them already
    there and sends the new one again alone, which lands."""
    account = str(uuid4())
    written: list[dict] = []
    try:
        _make_account(client, account)
        date = _date(client)
        landed = [_item(account, date, amount) for amount in (-100, -200)]
        fresh = _item(account, date, -300)
        written = [*landed, fresh]
        client.post("/transactions/batch", json_body={"transactions": landed})

        err = _refused(
            lambda: client.post(
                "/transactions/batch", json_body={"transactions": [landed[0], fresh, landed[1]]}
            )
        )
        assert err.reasons == {
            "transactions.0.id": "ID_EXISTS",
            "transactions.2.id": "ID_EXISTS",
        }

        statuses.clear()
        outcome = post_transaction_batch(client, [landed[0], fresh, landed[1]])
        assert outcome.results == [RowResult.EXISTED, RowResult.CREATED, RowResult.EXISTED]
        assert statuses == [409, 201]  # one request, then one more for the new row
        assert _live_ids(client, account) == {item["id"] for item in [*landed, fresh]}
    finally:
        _cleanup(client, [item["id"] for item in written], account)


def test_a_landed_opening_balance_sent_again_answers_id_exists(client):
    """A seed sent again answers `ID_EXISTS` on its own `transaction_id` before the
    account is read, not `OPENING_BALANCE_EXISTS`
    (contract: POST /v1/accounts/{account_id}/opening-balance)
    (contract: "Base Conventions", "Which refusal comes first on a create")."""
    account = str(uuid4())
    seed_id = str(uuid4())
    path = f"/accounts/{account}/opening-balance"
    try:
        _make_account(client, account)
        seed = {"transaction_id": seed_id, "amount_cents": 50000, "date": _date(client)}
        client.post(path, json_body=seed)

        err = _refused(lambda: client.post(path, json_body=seed))
        assert (err.status, err.code) == (409, "CONFLICT")
        assert err.reasons == {"transaction_id": "ID_EXISTS"}
        held = client.get(f"/accounts/{account}")["opening_balance_transaction_id"]
        assert held == seed["transaction_id"]
    finally:
        _cleanup(client, [seed_id], account)


def test_a_landed_split_sent_again_answers_id_exists_on_each_part(client):
    """A split sent again is `409` on each taken `parts.<i>.id` (`ID_EXISTS`), though
    the split deleted its `{id}` (contract: POST /v1/transactions/{transaction_id}/split)."""
    account = str(uuid4())
    original_id = str(uuid4())
    parts = [{"id": str(uuid4()), "amount_cents": amount} for amount in (-6000, -4000)]
    path = f"/transactions/{original_id}/split"
    try:
        _make_account(client, account)
        original = {**_item(account, _date(client), -10000), "id": original_id}
        client.post("/transactions", json_body=original)
        client.post(path, json_body={"parts": parts})

        err = _refused(lambda: client.post(path, json_body={"parts": parts}))
        assert (err.status, err.code) == (409, "CONFLICT")
        assert err.reasons == {"parts.0.id": "ID_EXISTS", "parts.1.id": "ID_EXISTS"}
        assert _live_ids(client, account) == {part["id"] for part in parts}
    finally:
        _cleanup(client, [original_id, *(part["id"] for part in parts)], account)
