"""Contract: scripts/clean_practice_user.py removes what a test left, through the engine.

A test that leaves records behind fails its own teardown (`leaves_nothing` in
conftest.py); the script is how such leftovers are then removed from the practice user.
This test leaves some on purpose, outside `Scratch`, under a name prefix of its own, and
has the script remove them by that prefix:

  · a card statement in draft across two accounts sharing a fresh statement code, a line
    created straight into one half, carrying a category and a hashtag of its own;
  · an account with no code, an opening balance and a completed reconciliation holding
    a line, then archived, so its statement must be unarchived and reverted before the
    delete (contract: POST /v1/reconciliations/{reconciliation_id}/revert);

after which the script finds nothing under the prefix, both statements read `404`, and
no account, category or hashtag of the prefix is listed. Matching by name and the
records it leaves alone are pinned in tests/unit/test_clean_practice_user.py.
"""

from uuid import uuid4

import pytest

from expense.errors import EngineError
from tests.contract.conftest import Scratch, free_statement_codes, holdings, reconciliation_body
from tests.scripts_loader import load_script


def test_the_script_removes_what_a_test_left(client):
    cleaner = load_script("clean_practice_user.py")
    prefix = f"contract-clean-{uuid4().hex[:8]}-"
    noon = Scratch(client).noon
    [code] = free_statement_codes(client, 1)

    def made(path: str, name: str, **fields) -> str:
        new_id = str(uuid4())
        client.post(path, json_body={"id": new_id, "name": f"{prefix}{name}", **fields})
        return new_id

    try:
        category = made("/categories", "c", color="#123456")
        hashtag = made("/hashtags", "h")
        pen = made("/accounts", "card-pen", currency_code="PEN", statement_code=code)
        usd = made("/accounts", "card-usd", currency_code="USD", statement_code=code)
        plain = made("/accounts", "plain", currency_code="PEN")

        card = reconciliation_body(pen, "2024-03-01", "2024-03-31", twin=usd)
        client.post("/reconciliations", json_body=card)
        line = {
            "id": str(uuid4()),
            "title": "contract clean line",
            "amount_cents": -1500,
            "account_id": pen,
            "date": noon("2024-03-10"),
            "category_id": category,
            "hashtag_ids": [hashtag],
            "reconciliation_id": card["id"],
        }
        client.post("/transactions", json_body=line)

        client.post(
            f"/accounts/{plain}/opening-balance",
            json_body={
                "transaction_id": str(uuid4()),
                "amount_cents": 50000,
                "date": noon("2024-01-01"),
            },
        )
        closed = reconciliation_body(plain, "2024-02-01", "2024-02-29")
        closed["ending_balance_cents"] = -2500
        client.post("/reconciliations", json_body=closed)
        client.post(
            "/transactions",
            json_body={
                "id": str(uuid4()),
                "title": "contract clean line",
                "amount_cents": -2500,
                "account_id": plain,
                "date": noon("2024-02-10"),
                "reconciliation_id": closed["id"],
            },
        )
        assert client.post(f"/reconciliations/{closed['id']}/complete")["status"] == 2
        client.post(f"/accounts/{plain}/archive")

        found = cleaner.plan(client, (prefix,))
        assert {a["id"] for a in found.accounts} == {pen, usd, plain}
        assert sorted(sorted(h["id"] for h in s) for s in found.statements) == sorted(
            [sorted([card["id"], card["twin"]["id"]]), [closed["id"]]]
        )
        assert [c["id"] for c in found.categories] == [category]
        assert [h["id"] for h in found.hashtags] == [hashtag]
        assert found.left == []

        assert cleaner.apply(client, found) == []

        after = cleaner.plan(client, (prefix,))
        assert (after.accounts, after.statements, after.categories, after.hashtags) == (
            [],
            [],
            [],
            [],
        )
        for recon in (card["id"], card["twin"]["id"], closed["id"]):
            with pytest.raises(EngineError) as excinfo:
                client.get(f"/reconciliations/{recon}")
            assert excinfo.value.status == 404
        assert not [label for label in holdings(client).values() if prefix in label]
    finally:
        cleaner.apply(client, cleaner.plan(client, (prefix,)))
