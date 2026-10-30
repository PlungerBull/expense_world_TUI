"""Contract: what `Scratch` builds on the practice user is all cleaned up, and a leftover
account fails the test that left it.

The two-currency account and person are made the shared way (contract: POST /v1/accounts,
"Required"); each test passing means `leaves_nothing` found nothing after the `scratch`
cleanup. The leftover check makes an account outside `scratch`, reads the cleaner's
`holdings` around it and deletes it. Gating and target: conftest.py.
"""

from uuid import uuid4

from tests.contract.conftest import CLEANER, account_body, free_statement_codes, left_behind


def test_two_currency_account_with_opening_balances_and_statements_leaves_nothing(client, scratch):
    account = scratch.account("PEN", "USD", code=free_statement_codes(client, 1)[0])
    scratch.opening_balance(account, "2026-01-01", "PEN")
    scratch.opening_balance(account, "2026-01-01", "USD")
    scratch.line(account, "2026-01-10", -1000, currency="USD")
    statement = scratch.statement(account, "2026-01-01", "2026-01-31", "PEN", "USD")["id"]

    read = client.get(f"/statements/{statement}")
    assert {b["currency_code"] for b in read["balances"]} == {"PEN", "USD"}
    held = client.get(f"/accounts/{account}")
    assert {c["currency_code"] for c in held["currencies"]} == {"PEN", "USD"}


def test_two_currency_person_leaves_nothing(client, scratch):
    person = scratch.account("PEN", "USD", person=True)

    held = client.get(f"/accounts/{person}")
    assert held["is_person"] is True
    assert {c["currency_code"] for c in held["currencies"]} == {"PEN", "USD"}


def test_a_left_account_is_reported_by_name(client):
    name = f"contract-stmt-{uuid4().hex[:8]}"
    body = {**account_body("PEN", "USD"), "name": name}
    before = CLEANER.holdings(client)
    try:
        client.post("/accounts", json_body=body)
        after = CLEANER.holdings(client)
    finally:
        client.delete(f"/accounts/{body['id']}")

    assert left_behind(before, after) == [f"account {name!r}"]
    assert CLEANER.holdings(client) == before
