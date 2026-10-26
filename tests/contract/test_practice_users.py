"""The practice engine's two practice users: the shared one (`client`, EXPENSE_PAT) and the
reserved-names one (`reserved_client`, EXPENSE_RESERVED_PAT), each key the reseed prints
(docs/runtime.md "Working against the live engine"). Gated in conftest.py."""


def test_the_reserved_names_user_is_another_user(client, reserved_client):
    """Each key signs in as its own user: two profiles with two different ids
    (contract: GET /v1/auth/me)."""
    shared = client.get("/auth/me")["user"]["id"]
    reserved = reserved_client.get("/auth/me")["user"]["id"]
    assert shared and reserved
    assert shared != reserved
