"""Contract: scripts/clean_practice_user.py removes what a test left, through the engine.

A test that leaves records behind fails its own teardown (`leaves_nothing` in
conftest.py); the script is how such leftovers are then removed from the practice user.
This test leaves some on purpose, built with `Scratch` but never cleaned up by it, renamed
under a name prefix of its own, and has the script remove them by that prefix:

  · an account of two currencies (PEN and USD) with no statement code, an opening balance
    and a line in each currency, a completed statement holding a line in each currency and
    a draft statement of another month, then archived, so the script must unarchive it and
    revert the completed statement before the deletes
    (contract: POST /v1/statements/{statement_id}/revert);
  · a category and a hashtag;

after which the script finds nothing under the prefix, both statements read `404`, and
no account, category or hashtag of the prefix is listed. Matching by name and the
records it leaves alone are pinned in tests/unit/test_clean_practice_user.py.
"""

from uuid import uuid4

import pytest

from expense.errors import EngineError
from tests.contract.conftest import CLEANER, Scratch


def test_the_script_removes_what_a_test_left(client):
    prefix = f"contract-clean-{uuid4().hex[:8]}-"
    scratch = Scratch(client)
    try:
        category = scratch.category()
        hashtag = scratch.hashtag()
        account = scratch.account("PEN", "USD")
        for path in (f"/categories/{category}", f"/hashtags/{hashtag}", f"/accounts/{account}"):
            client.put(path, json_body={"name": f"{prefix}{path.split('/')[1]}"})
        for currency in ("PEN", "USD"):
            scratch.opening_balance(account, "2026-01-01", currency)

        closed = scratch.statement(account, "2026-02-01", "2026-02-28", "PEN", "USD")["id"]
        lines = len(scratch.transactions)
        for currency in ("PEN", "USD"):
            scratch.line(account, "2026-02-10", 2500, currency=currency)
            scratch.line(account, "2026-02-11", -2500, currency=currency)
        for tx in scratch.transactions[lines:]:
            scratch.assign(tx, closed)
        draft = scratch.statement(account, "2026-03-01", "2026-03-31", "PEN", "USD")["id"]
        assert client.post(f"/statements/{closed}/complete")["status"] == 2
        client.post(f"/accounts/{account}/archive")

        found = CLEANER.plan(client, (prefix,))
        assert [a["id"] for a in found.accounts] == [account]
        assert {s["id"] for s in found.statements} == {closed, draft}
        assert found.transactions[account] == len(scratch.transactions)
        assert [c["id"] for c in found.categories] == [category]
        assert [h["id"] for h in found.hashtags] == [hashtag]

        assert CLEANER.apply(client, found) == []

        after = CLEANER.plan(client, (prefix,))
        assert (after.accounts, after.statements, after.categories, after.hashtags) == (
            [],
            [],
            [],
            [],
        )
        for statement in (closed, draft):
            with pytest.raises(EngineError) as excinfo:
                client.get(f"/statements/{statement}")
            assert excinfo.value.status == 404
        assert not [label for label in CLEANER.holdings(client).values() if prefix in label]
    finally:
        CLEANER.apply(client, CLEANER.plan(client, (prefix,)))
