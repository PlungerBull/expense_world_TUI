"""Contract: a leftover account fails the test that left it.

The leftover check makes an account outside `scratch`, reads the cleaner's `holdings` around
it and deletes it. What `scratch` builds is cleaned up by every test that uses it, each
failing on a leftover. Gating and target: conftest.py.
"""

from tests.contract.conftest import CLEANER, account_body, left_behind


def test_a_left_account_is_reported_by_name(client):
    body = account_body("PEN", "USD")
    name = f"{body['bank_code']}-{body['last4']}"
    before = CLEANER.holdings(client)
    try:
        client.post("/accounts", json_body=body)
        after = CLEANER.holdings(client)
    finally:
        client.delete(f"/accounts/{body['id']}")

    assert left_behind(before, after) == [f"account {name!r}"]
    assert CLEANER.holdings(client) == before
