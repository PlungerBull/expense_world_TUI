"""Account commands that are *not* the shared CRUD contract.

The thirteen tests every resource shares — list/get/create/update/delete/restore
and their flags — live in test_resource_crud_contract.py, parametrized over
accounts, categories and hashtags. What is left here is what only accounts have:
people (`create-person`, and the fact that `create` refuses to make one), the
opening balance, the archive toggles no other resource kept after 2026-08-06,
the balance column, and the hints those paths print.
"""

import json
from uuid import UUID

import httpx
import respx
from typer.testing import CliRunner

from expense.commands.accounts_cmd import app as accounts_app
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, make_cli_app

cli_app = make_cli_app(accounts_app, "accounts")

runner = CliRunner()


ACCOUNT_RESPONSE = {
    "id": "11111111-1111-1111-1111-111111111111",
    "user_id": "u1",
    "name": "BCP Soles",
    "currency_code": "PEN",
    "color": "#FF0000",
    "sort_order": 1,
    "is_person": False,
    "is_archived": False,
    "deleted_at": None,
    "version": 1,
    "created_at": "2026-04-24T10:00:00Z",
    "updated_at": "2026-04-24T10:00:00Z",
    "current_balance_cents": 125000,
    "current_balance_home_cents": 125000,
}

LIST_RESPONSE = [ACCOUNT_RESPONSE]


@respx.mock
def test_list_include_archived_sends_param(configured):
    route = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(cli_app, ["accounts", "list", "--include-archived"])
    assert result.exit_code == 0, result.output
    assert "BCP Soles" in result.output

    request = route.calls.last.request
    assert request.url.params.get("include_archived") == "true"


@respx.mock
def test_list_include_people_sends_param(configured):
    person = {
        **ACCOUNT_RESPONSE,
        "id": "44444444-4444-4444-4444-444444444444",
        "name": "Alex",
        "is_person": True,
        "current_balance_cents": -4500,
    }
    route = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(200, json=[ACCOUNT_RESPONSE, person])
    )
    result = runner.invoke(cli_app, ["accounts", "list", "--include-people"])
    assert result.exit_code == 0, result.output
    assert "Alex" in result.output
    assert route.calls.last.request.url.params.get("include_people") == "true"


@respx.mock
def test_list_renders_balance_as_major_units(configured):
    cash = {
        **ACCOUNT_RESPONSE,
        "id": "22222222-2222-2222-2222-222222222222",
        "name": "Cash",
        "color": None,
        "current_balance_cents": 5000,
    }
    respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(200, json=[ACCOUNT_RESPONSE, cash])
    )
    result = runner.invoke(cli_app, ["accounts", "list"])
    assert result.exit_code == 0, result.output
    assert "BCP Soles" in result.output
    assert "Cash" in result.output
    # Balance renders as grouped major units (Cash: 5000 cents → 50.00).
    assert "50.00" in result.output
    assert "1,250.00" in result.output


@respx.mock
def test_list_human_default_sends_limit_20(configured):
    """Bare human list → the 20-row default (2026-07-11); explicit flags win."""
    route = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(cli_app, ["accounts", "list"])
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params.get("limit") == "20"
    assert route.calls.last.request.url.params.get("offset") is None

    result = runner.invoke(cli_app, ["accounts", "list", "--limit", "5"])
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params.get("limit") == "5"


@respx.mock
def test_opening_balance_happy(configured):
    route = respx.post(f"{BASE}/v1/accounts/acc-1/opening-balance").mock(
        return_value=httpx.Response(201, json={"id": "seed-1", "amount_cents": 1250000})
    )
    result = runner.invoke(
        cli_app,
        [
            "accounts",
            "opening-balance",
            "acc-1",
            "--amount",
            "1250000",
            "--date",
            "2026-01-01",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Seeded opening balance:" in result.output

    body = json.loads(route.calls.last.request.content)
    assert body["amount_cents"] == 1250000
    assert body["date"].startswith("2026-01-01")
    assert "title" not in body  # engine supplies the default
    UUID(body["transaction_id"])


PERSON_RESPONSE = {
    **ACCOUNT_RESPONSE,
    "id": "44444444-4444-4444-4444-444444444444",
    "name": "Eliana",
    "is_person": True,
    "current_balance_cents": 0,
    "current_balance_home_cents": 0,
}


@respx.mock
def test_create_person_happy(configured):
    """POST /v1/people — the only people route, and `is_person` is never sent."""
    route = respx.post(f"{BASE}/v1/people").mock(
        return_value=httpx.Response(201, json=PERSON_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        ["accounts", "create-person", "--name", "Eliana", "--currency-code", "PEN"],
    )
    assert result.exit_code == 0, result.output
    assert "Created:" in result.output

    body = json.loads(route.calls.last.request.content)
    assert body["name"] == "Eliana"
    assert body["currency_code"] == "PEN"
    UUID(body["id"])
    # The endpoint implies the flag and 422s on the field — never send it.
    assert "is_person" not in body


@respx.mock
def test_create_person_json_mode(configured):
    respx.post(f"{BASE}/v1/people").mock(return_value=httpx.Response(201, json=PERSON_RESPONSE))
    result = runner.invoke(
        cli_app,
        ["accounts", "create-person", "--name", "Eliana", "--currency-code", "PEN", "--json"],
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == PERSON_RESPONSE
    assert "Created:" not in result.output


@respx.mock
def test_create_person_conflict_explains_shared_name_list(configured):
    """A person's name collides with a *bank account's* — one name list per currency."""
    respx.post(f"{BASE}/v1/people").mock(
        return_value=error_response(
            409, "CONFLICT", "An account with this name already exists.", None
        )
    )
    result = runner.invoke(
        cli_app,
        ["accounts", "create-person", "--name", "Eliana", "--currency-code", "PEN"],
    )
    assert result.exit_code == 1
    assert "CONFLICT" in result.output
    assert "share one name list" in result.output


@respx.mock
def test_create_stays_bank_only(configured):
    """`accounts create` must never grow a person path — the engine 422s `is_person`."""
    route = respx.post(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(201, json=ACCOUNT_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        ["accounts", "create", "--name", "BCP Soles", "--currency-code", "PEN"],
    )
    assert result.exit_code == 0, result.output
    assert "is_person" not in json.loads(route.calls.last.request.content)


@respx.mock
def test_opening_balance_conflict_surfaces_error(configured):
    respx.post(f"{BASE}/v1/accounts/acc-1/opening-balance").mock(
        return_value=error_response(
            409, "CONFLICT", "This account already has an opening balance.", None
        )
    )
    result = runner.invoke(
        cli_app,
        ["accounts", "opening-balance", "acc-1", "--amount", "1000"],
    )
    assert result.exit_code == 1
    assert "CONFLICT" in result.output
    assert "already has an opening balance" in result.output


def test_update_currency_flag_rejected_locally(configured):
    result = runner.invoke(
        cli_app,
        ["accounts", "update", "abc", "--currency-code", "USD"],
    )
    assert result.exit_code != 0
    assert "Currency cannot be changed" in result.output


@respx.mock
def test_delete_409_prints_archive_hint(configured):
    respx.delete(f"{BASE}/v1/accounts/abc").mock(
        return_value=error_response(409, "CONFLICT", "Account has transactions.", None)
    )
    result = runner.invoke(cli_app, ["accounts", "delete", "abc", "--yes"])
    assert result.exit_code == 1
    assert "archive" in result.output
    assert "CONFLICT" in result.output


@respx.mock
def test_archive_happy(configured):
    archived = {**ACCOUNT_RESPONSE, "is_archived": True}
    respx.post(f"{BASE}/v1/accounts/abc/archive").mock(
        return_value=httpx.Response(200, json=archived)
    )
    result = runner.invoke(cli_app, ["accounts", "archive", "abc"])
    assert result.exit_code == 0, result.output
    assert "is_archived: True" in result.output


@respx.mock
def test_archive_is_prompt_free(configured):
    # Archive is a reversible toggle (2026-07-11): no confirmation, no --yes —
    # it succeeds bare even in non-TTY mode (CliRunner is non-TTY), where the
    # old confirm gate used to exit 1 with a "non-interactive" error.
    archived = {**ACCOUNT_RESPONSE, "is_archived": True}
    respx.post(f"{BASE}/v1/accounts/abc/archive").mock(
        return_value=httpx.Response(200, json=archived)
    )
    result = runner.invoke(cli_app, ["accounts", "archive", "abc"])
    assert result.exit_code == 0, result.output
    assert "non-interactive" not in result.output


@respx.mock
def test_unarchive_happy(configured):
    respx.post(f"{BASE}/v1/accounts/abc/unarchive").mock(
        return_value=httpx.Response(200, json=ACCOUNT_RESPONSE)
    )
    result = runner.invoke(cli_app, ["accounts", "unarchive", "abc"])
    assert result.exit_code == 0, result.output


@respx.mock
def test_archive_refusal_surfaces_the_engine_envelope(configured):
    """Archive is prompt-free because it is reversible — which makes its
    refusal the only thing that ever stops it, so the user has to see it."""
    respx.post(f"{BASE}/v1/accounts/abc/archive").mock(
        return_value=error_response(409, "CONFLICT", "Account is already archived.")
    )
    result = runner.invoke(cli_app, ["accounts", "archive", "abc"])
    assert result.exit_code == 1
    assert "CONFLICT" in result.output
    assert "Account is already archived." in result.output


@respx.mock
def test_unarchive_refusal_surfaces_the_engine_envelope(configured):
    respx.post(f"{BASE}/v1/accounts/abc/unarchive").mock(
        return_value=error_response(404, "NOT_FOUND", "Account not found.")
    )
    result = runner.invoke(cli_app, ["accounts", "unarchive", "abc"])
    assert result.exit_code == 1
    assert "NOT_FOUND" in result.output
