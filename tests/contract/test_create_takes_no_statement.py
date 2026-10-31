"""Contract: a create takes no `statement_id`.

A transaction is created in no statement: `POST /transactions` and each item of
`POST /transactions/batch` refuse `statement_id`, a real draft's id and `null` alike, as an
unknown field, and nothing is written. It joins a statement by `PUT /transactions/{id}` or
`PUT /bank-lines/{id}` (contract: POST /v1/transactions, "No `statement_id`"). No screen
creates into a statement; the suite proves the refusal for every client.

Each test builds its own account and undoes everything (conftest.py `scratch`). Gating,
target and the real-ledger guard: conftest.py.
"""

from tests.contract.conftest import assert_refusal, live_ids, transaction_count


def test_statement_id_on_a_create_and_on_a_batch_item_is_an_unknown_field(client, scratch):
    """Naming a real draft of the row's own account, or `null`, `statement_id` is `422`
    `UNKNOWN_FIELD` on `statement_id` for a single create and on
    `transactions.0.statement_id` for a batch item; the account holds no row after, and a
    plain create of the same row lands in no statement."""
    account = scratch.account()
    draft = scratch.statement(account, "2026-03-01", "2026-03-31")["id"]
    held = live_ids(client, account)
    when = scratch.at("2026-03-06")

    for value in (draft, None):
        err = scratch.refused_row(account, when, statement_id=value)
        assert_refusal(err, 422, "VALIDATION_ERROR", "statement_id", "UNKNOWN_FIELD")
        err = scratch.refused_row(account, when, batch=True, statement_id=value)
        assert_refusal(err, 422, "VALIDATION_ERROR", "transactions.0.statement_id", "UNKNOWN_FIELD")

    assert live_ids(client, account) == held
    assert transaction_count(client, account) == 0
    assert scratch.row(account, "2026-03-06", -2500)["statement_id"] is None
