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
  · a whole-line write sent again under a new key finds its new parts live on the line
    and writes nothing, while a part id the line's own deleted part, another line's
    part or a line that does not exist holds is `409` `ID_EXISTS` on that
    `parts.<i>.id`, judged before the line's `404`.

Every value a test writes is fresh per run (UUIDs, an account named by one): the
practice user's data outlives a reseed. Each test builds its own account and undoes
what it wrote. Gating, target and the real-ledger guard: conftest.py.
"""

from uuid import uuid4

from expense.batch_write import RowResult, post_transaction_batch
from tests.contract.conftest import live_ids, refused


def _item(scratch, account_id: str, amount: int) -> dict:
    """A PEN row of `amount`, its id taken on by `scratch`'s cleanup."""
    item = {
        "id": str(uuid4()),
        "title": "contract sent again",
        "amount_cents": amount,
        "account_id": account_id,
        "currency_code": "PEN",
        "date": scratch.noon("2026-04-14"),
    }
    scratch.transactions.append(item["id"])
    return item


def test_a_landed_batch_sent_again_names_every_items_id(client, scratch):
    """Step 2 of a batch names every item whose id already exists, one
    `transactions.<i>.id` entry each, and a batch sent again whole answers it on
    every item (contract: POST /v1/transactions/batch). Nothing is written
    (contract: POST /v1/transactions/batch, "No partial success")."""
    account = scratch.account()
    items = [_item(scratch, account, amount) for amount in (-100, -200, -300)]
    client.post("/transactions/batch", json_body={"transactions": items})

    body = {"transactions": items}
    err = refused(lambda: client.post("/transactions/batch", json_body=body))
    assert (err.status, err.code) == (409, "CONFLICT")
    keys = [f"transactions.{i}.id" for i in range(len(items))]
    assert err.reasons == dict.fromkeys(keys, "ID_EXISTS")
    assert set(err.fields or {}) == set(keys)
    assert live_ids(client, account) == {item["id"] for item in items}


def test_the_batch_writer_settles_landed_and_new_rows_in_two_requests(client, statuses, scratch):
    """A batch mixing landed items and a new one is `409` naming only the landed
    ones (contract: POST /v1/transactions/batch); the writer counts them already
    there and sends the new one again alone, which lands."""
    account = scratch.account()
    landed = [_item(scratch, account, amount) for amount in (-100, -200)]
    fresh = _item(scratch, account, -300)
    client.post("/transactions/batch", json_body={"transactions": landed})

    err = refused(
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
    assert live_ids(client, account) == {item["id"] for item in [*landed, fresh]}


def test_a_landed_opening_balance_sent_again_answers_id_exists(client, scratch):
    """A seed sent again answers `ID_EXISTS` on its own `transaction_id` before the
    account is read, not `OPENING_BALANCE_EXISTS`
    (contract: POST /v1/accounts/{account_id}/opening-balance)
    (contract: "Base Conventions", "Which refusal comes first on a create")."""
    account = scratch.account()
    seed_id = str(uuid4())
    scratch.transactions.append(seed_id)
    path = f"/accounts/{account}/opening-balance"
    seed = {
        "transaction_id": seed_id,
        "currency_code": "PEN",
        "amount_cents": 50000,
        "date": scratch.noon("2026-04-14"),
    }
    client.post(path, json_body=seed)

    err = refused(lambda: client.post(path, json_body=seed))
    assert (err.status, err.code) == (409, "CONFLICT")
    assert err.reasons == {"transaction_id": "ID_EXISTS"}
    currencies = client.get(f"/accounts/{account}")["currencies"]
    held = next(c for c in currencies if c["currency_code"] == "PEN")
    assert held["opening_balance_transaction_id"] == seed_id


def test_a_landed_line_write_sent_again_writes_nothing_and_a_taken_part_id_is_id_exists(
    client, scratch
):
    """A whole-line write sent again under a new key finds the parts it created live on
    the line, updates them in place and, every value as held, writes nothing
    (contract: PUT /v1/bank-lines/{bank_line_id}, "A live part of this line is updated in place").
    A part id any other record holds is `409` on that `parts.<i>.id` (`ID_EXISTS`): the
    line's own transaction the first write deleted, a part of another line, and a part
    sent to a line that does not exist, which answers before the `404`
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Refusals, in order")
    (contract: "Base Conventions", "Which refusal comes first on a create"). Nothing is
    written."""
    account = scratch.account()
    parts = [{"id": str(uuid4()), "amount_cents": amount} for amount in (-6000, -4000)]
    scratch.transactions.extend(part["id"] for part in parts)
    original = _item(scratch, account, -10000)
    line = client.post("/transactions", json_body=original)["bank_line_id"]
    other = _item(scratch, account, -2500)
    client.post("/transactions", json_body=other)
    path = f"/bank-lines/{line}"
    client.put(path, json_body={"parts": parts})
    versions = {p["id"]: p["version"] for p in client.get(path)["parts"]}

    again = client.put(path, json_body={"parts": parts})
    assert (again["created_part_ids"], again["deleted_part_ids"]) == ([], [])
    assert {p["id"]: p["version"] for p in client.get(path)["parts"]} == versions

    for taken, target in [
        (original["id"], path),
        (other["id"], path),
        (parts[0]["id"], f"/bank-lines/{uuid4()}"),
    ]:
        body = {"parts": [{"id": taken, "amount_cents": -10000}]}
        err = refused(lambda target=target, body=body: client.put(target, json_body=body))
        assert (err.status, err.code) == (409, "CONFLICT"), taken
        assert err.reasons == {"parts.0.id": "ID_EXISTS"}, taken
    assert live_ids(client, account) == {other["id"], *(part["id"] for part in parts)}
    assert {p["id"]: p["version"] for p in client.get(path)["parts"]} == versions
