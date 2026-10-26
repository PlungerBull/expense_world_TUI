"""Contract: a transaction created straight into a reconciliation.

`POST /transactions` and each item of `POST /transactions/batch` take
`reconciliation_id`: the new bank line is created already assigned, in one write, with
no place in its statement (contract: POST /v1/transactions, "Fields"). No screen
creates into a reconciliation; the suite proves the write for every client. Pinned here:

  · a create naming a reconciliation lands in it in one write: version 1, one
    `created` activity entry carrying the reconciliation, the line listed by the
    reconciliation, no `statement_place`, and the statement's `unplaced_count` up by
    one, the order needing to be sent again;
  · its refusals on `reconciliation_id`, nothing written: `INVALID_REFERENCE` (no
    such reconciliation, or a deleted one), `ACCOUNT_MISMATCH` (another account's) and
    `RECONCILIATION_COMPLETED`, which answers before `SEALED_PERIOD` on a date inside
    that reconciliation's window;
  · a batch: an item into a reconciliation, an item into none, and a `line_group`
    whose items name one reconciliation, made one line in it; the refusals keyed
    `transactions.<i>.reconciliation_id`, every refused item and field named in one
    answer (an item dated inside a completed reconciliation's window also on its
    `date`); and a
    `line_group` whose items name two reconciliations, or one and none, is
    `LINE_GROUP_FIELDS_DIFFER` on every item's `reconciliation_id`, nothing written.

Each test builds its own accounts and undoes everything (conftest.py `scratch`). Gating,
target and the real-ledger guard: conftest.py.
"""

from uuid import uuid4

from tests.contract.conftest import (
    assert_refusal,
    free_statement_codes,
    live_ids,
    refused,
)

#: The activity action of an insert (contract: "Activity Log", "Action codes").
CREATED = 1


def _item(scratch, account: str, day: str, amount: int, **extra) -> dict:
    """A create body under a fresh id, kept for cleanup before any write can create it."""
    new_id = str(uuid4())
    scratch.transactions.append(new_id)
    return {
        "id": new_id,
        "title": "contract into reconciliation",
        "amount_cents": amount,
        "account_id": account,
        "date": scratch.noon(day),
        **extra,
    }


def test_a_create_lands_in_its_reconciliation_in_one_write_with_no_place(client, scratch):
    """The new line is created already in the reconciliation: the transaction reads it
    at `version` 1 with one `created` activity entry whose snapshot carries it, the
    reconciliation lists the line, and the line holds no place, so an ordered
    statement counts one unplaced line again
    (contract: POST /v1/transactions, "Fields")
    (contract: "Reconciliations", "A statement's order")."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account("PEN", code)
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    placed = scratch.line(account, "2026-03-04", -100, recon=recon)
    client.put(f"/reconciliations/{recon}/statement-order", json_body={"places": [placed]})
    assert client.get(f"/reconciliations/{recon}")["unplaced_count"] == 0

    body = _item(scratch, account, "2026-03-06", -2500, reconciliation_id=recon)
    made = client.post("/transactions", json_body=body)
    assert (made["reconciliation_id"], made["statement_place"]) == (recon, None)
    assert made["version"] == 1
    entries = client.get("/activity", params={"resource_id": body["id"]})["items"]
    assert [entry["action"] for entry in entries] == [CREATED]
    assert entries[0]["after_snapshot"]["reconciliation_id"] == recon

    line = made["bank_line_id"]
    assert client.get(f"/bank-lines/{line}")["statement_place"] is None
    listed = client.get("/bank-lines", params={"reconciliation_id": recon})["items"]
    assert {row["id"] for row in listed} == {placed, line}
    assert client.get(f"/reconciliations/{recon}")["unplaced_count"] == 1
    order = client.get(f"/reconciliations/{recon}/statement-order")
    assert [row["id"] for row in order["unplaced"]] == [line]


def test_a_create_into_a_reconciliation_it_cannot_join_is_refused(client, scratch):
    """`reconciliation_id` is refused as an assignment is, on `reconciliation_id`, and
    nothing is written: a reconciliation that does not exist or is deleted
    (`INVALID_REFERENCE`), another account's (`ACCOUNT_MISMATCH`), a completed one
    (`RECONCILIATION_COMPLETED`), answered before the sealed period its window makes
    (contract: POST /v1/transactions, "Validation")."""
    account = scratch.account()
    other = scratch.account()
    elsewhere = scratch.reconciliation(other, "2026-03-01", "2026-03-31")
    deleted = scratch.reconciliation(account, "2026-01-01", "2026-01-31")
    client.delete(f"/reconciliations/{deleted}")
    completed = scratch.reconciliation(account, "2026-02-01", "2026-02-28")
    scratch.line(account, "2026-02-03", -100, recon=completed)
    client.post(f"/reconciliations/{completed}/complete")
    held = live_ids(client, account)

    for recon, day, reason in (
        (str(uuid4()), "2026-03-06", "INVALID_REFERENCE"),
        (deleted, "2026-01-06", "INVALID_REFERENCE"),
        (elsewhere, "2026-03-06", "ACCOUNT_MISMATCH"),
        (completed, "2026-02-06", "RECONCILIATION_COMPLETED"),
    ):
        body = _item(scratch, account, day, -100, reconciliation_id=recon)
        err = refused(lambda body=body: client.post("/transactions", json_body=body))
        assert_refusal(err, 422, "VALIDATION_ERROR", "reconciliation_id", reason)
    assert live_ids(client, account) == held


def test_a_batch_creates_its_items_and_line_groups_into_reconciliations(client, scratch):
    """A batch item naming a reconciliation is created in it, one naming none in none,
    and a `line_group` whose items name one reconciliation is one line in it; nothing
    of the line holds a place (contract: POST /v1/transactions/batch, "Line groups")."""
    account = scratch.account()
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    items = [
        _item(scratch, account, "2026-03-07", -100, reconciliation_id=recon),
        _item(scratch, account, "2026-03-07", -200),
        _item(scratch, account, "2026-03-08", -600, reconciliation_id=recon, line_group="g"),
        _item(scratch, account, "2026-03-08", -400, reconciliation_id=recon, line_group="g"),
    ]
    created = client.post("/transactions/batch", json_body={"transactions": items})["created"]
    assert [t["reconciliation_id"] for t in created] == [recon, None, recon, recon]
    assert {t["statement_place"] for t in created} == {None}
    group = created[2]["bank_line_id"]
    assert created[3]["bank_line_id"] == group
    read = client.get(f"/bank-lines/{group}")
    assert (read["part_count"], read["net_cents"]) == (2, -1000)
    listed = client.get("/bank-lines", params={"reconciliation_id": recon})["items"]
    assert {row["id"] for row in listed} == {created[0]["bank_line_id"], group}


def test_a_batch_into_reconciliations_it_cannot_join_is_refused(client, scratch):
    """Each item's `reconciliation_id` is refused as on a single create, keyed
    `transactions.<i>.reconciliation_id`, every refused item and field named in one
    answer, so an item dated inside the completed reconciliation's window it names is
    `SEALED_PERIOD` on its `date` too; the
    items of one `line_group` name one reconciliation or none, so two reconciliations,
    or one and none, are `LINE_GROUP_FIELDS_DIFFER` on every item's
    `reconciliation_id`. Nothing is written
    (contract: POST /v1/transactions/batch, "Refusals come in four steps")
    (contract: POST /v1/transactions/batch, "Line groups")."""
    account = scratch.account()
    other = scratch.account()
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    second = scratch.reconciliation(account, "2026-04-01", "2026-04-30")
    elsewhere = scratch.reconciliation(other, "2026-03-01", "2026-03-31")
    completed = scratch.reconciliation(account, "2026-02-01", "2026-02-28")
    scratch.line(account, "2026-02-03", -100, recon=completed)
    client.post(f"/reconciliations/{completed}/complete")
    held = live_ids(client, account)

    items = [
        _item(scratch, account, "2026-03-09", -100, reconciliation_id=str(uuid4())),
        _item(scratch, account, "2026-03-09", -200, reconciliation_id=recon),
        _item(scratch, account, "2026-03-09", -300, reconciliation_id=elsewhere),
        _item(scratch, account, "2026-02-09", -400, reconciliation_id=completed),
    ]
    err = refused(lambda: client.post("/transactions/batch", json_body={"transactions": items}))
    assert (err.status, err.code) == (422, "VALIDATION_ERROR")
    assert err.reasons == {
        "transactions.0.reconciliation_id": "INVALID_REFERENCE",
        "transactions.2.reconciliation_id": "ACCOUNT_MISMATCH",
        "transactions.3.reconciliation_id": "RECONCILIATION_COMPLETED",
        "transactions.3.date": "SEALED_PERIOD",
    }

    for names in ((recon, second), (recon, None)):
        group = [
            _item(
                scratch,
                account,
                "2026-03-10",
                amount,
                line_group="g",
                **({"reconciliation_id": name} if name else {}),
            )
            for amount, name in zip((-600, -400), names, strict=True)
        ]
        body = {"transactions": group}
        err = refused(lambda body=body: client.post("/transactions/batch", json_body=body))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR"), names
        assert err.reasons == {
            "transactions.0.reconciliation_id": "LINE_GROUP_FIELDS_DIFFER",
            "transactions.1.reconciliation_id": "LINE_GROUP_FIELDS_DIFFER",
        }, names
    assert live_ids(client, account) == held
