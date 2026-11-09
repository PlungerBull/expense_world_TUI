"""Contract: the user's number format, and the settings and token rules beside it.

`number_format` is `"1,234.56"`, `"1.234,56"` or `null`, no pick: `PUT /auth/settings` stores
it and `GET /auth/me` reads it back under `settings`; `null` clears a pick; any other string,
or a value that is no string, is `422` `INVALID_FORMAT` on `number_format` with the settings
unchanged (contract: PUT /v1/auth/settings). Sign-up takes no format: `POST /auth/bootstrap`
refuses it as `UNKNOWN_FIELD` and writes nothing (contract: POST /v1/auth/bootstrap). A
`display_timezone` sent in small letters is stored and answered in its listed spelling
(contract: PUT /v1/auth/settings). A token id already taken, a revoked token's included, is
`409` `ID_EXISTS` on `id` naming "a personal access token", and mints nothing: the token's
activity holds its one `CREATED` entry (contract: POST /v1/auth/pat) (contract: GET /v1/activity).

The shared practice user's `number_format` and `display_timezone` are put back after each
test, whatever happens (`settings_kept`); a token a test mints is revoked after it.
"""

from functools import partial
from uuid import uuid4

import pytest

from tests.contract.conftest import assert_refusal, refused, refused_keeping

DOT = "1,234.56"
COMMA = "1.234,56"
#: An activity entry's `action` for a creation (contract: GET /v1/activity, "Response fields").
CREATED = 1


def _settings(client) -> dict:
    return client.get("/auth/me")["settings"]


@pytest.fixture
def settings_kept(client):
    """The practice user's `number_format` and `display_timezone` put back after the test."""
    before = _settings(client)
    try:
        yield before
    finally:
        now = _settings(client)
        back = {
            key: before[key]
            for key in ("display_timezone", "number_format")
            if now[key] != before[key]
        }
        if back:
            client.put("/auth/settings", json_body=back)


@pytest.mark.parametrize("pick", [DOT, COMMA])
def test_a_pick_is_saved_and_read_back_on_me(client, settings_kept, pick):
    saved = client.put("/auth/settings", json_body={"number_format": pick})
    assert saved["number_format"] == pick
    assert _settings(client)["number_format"] == pick


def test_null_clears_the_pick(client, settings_kept):
    client.put("/auth/settings", json_body={"number_format": COMMA})
    cleared = client.put("/auth/settings", json_body={"number_format": None})
    assert cleared["number_format"] is None
    assert _settings(client)["number_format"] is None


@pytest.mark.parametrize("bad", ["1 234,56", "1,234.56 ", "", "dot", 1, True, ["1,234.56"]])
def test_an_unknown_format_is_refused_and_nothing_is_written(client, settings_kept, bad):
    client.put("/auth/settings", json_body={"number_format": COMMA})
    err = refused_keeping(
        partial(_settings, client),
        lambda: client.put("/auth/settings", json_body={"number_format": bad}),
        bad,
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "number_format", "INVALID_FORMAT")


def test_sign_up_takes_no_format(client, settings_kept):
    me = client.get("/auth/me")
    body = {
        "display_name": me["user"]["display_name"],
        "timezone": me["settings"]["display_timezone"],
        "number_format": DOT,
    }
    err = refused_keeping(
        partial(client.get, "/auth/me"), lambda: client.post("/auth/bootstrap", json_body=body)
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "number_format", "UNKNOWN_FIELD")


def test_a_timezone_in_small_letters_reads_back_in_its_listed_spelling(client, settings_kept):
    for sent, listed in (("us/eastern", "US/Eastern"), ("asia/tokyo", "Asia/Tokyo")):
        saved = client.put("/auth/settings", json_body={"display_timezone": sent})
        assert saved["display_timezone"] == listed
        assert _settings(client)["display_timezone"] == listed


def _assert_id_taken(err) -> None:
    assert_refusal(err, 409, "CONFLICT", "id", "ID_EXISTS")
    message = err.fields["id"]
    assert message.startswith("A personal access token with ")
    assert message.endswith(" already exists.")


def test_a_taken_token_id_is_refused_naming_a_personal_access_token(client):
    pat_id = str(uuid4())
    client.post("/auth/pat", json_body={"id": pat_id, "name": "contract: reused id"})
    try:

        def actions() -> list[int]:
            """The token's activity entries, newest first; the answer's echoed window moves."""
            params = {"resource_type": "personal_access_token", "resource_id": pat_id}
            return [item["action"] for item in client.get("/activity", params=params)["items"]]

        err = refused_keeping(actions, lambda: client.post("/auth/pat", json_body={"id": pat_id}))
        _assert_id_taken(err)
        assert actions() == [CREATED]

        client.delete(f"/auth/pat/{pat_id}")
        _assert_id_taken(refused(lambda: client.post("/auth/pat", json_body={"id": pat_id})))
    finally:
        try:
            client.delete(f"/auth/pat/{pat_id}")
        except Exception:  # noqa: BLE001 - already revoked above; only the cleanup is best effort
            pass
