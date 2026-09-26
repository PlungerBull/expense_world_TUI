import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from expense.commands import activity_cmd
from expense.commands.activity_cmd import app as activity_app
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import FakeClient, error_response, make_cli_app, page, whole

cli_app = make_cli_app(activity_app, "activity")

runner = CliRunner()


ACTIVITY_ROW = {
    "id": "11111111-1111-1111-1111-111111111111",
    "user_id": "u1",
    "resource_type": "expense_transactions",
    "resource_id": "22222222-2222-2222-2222-222222222222",
    "action": 1,
    "before_snapshot": None,
    "after_snapshot": {"id": "22222222-2222-2222-2222-222222222222", "title": "Coffee"},
    "changed_by": "u1",
    "actor_type": "user",
    "created_at": "2026-05-03T10:00:00Z",
}

LIST_RESPONSE = [ACTIVITY_ROW]


@respx.mock
def test_list_happy_no_filters(configured):
    route = respx.get(f"{BASE}/v1/activity").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    # Table columns: action name, actor_type, resource_type, UUID prefix fallback.
    assert "CREATED" in result.output
    assert "user" in result.output
    assert "expense_transactions" in result.output
    assert "22222222" in result.output  # UUID prefix fallback (name lookup missed)
    # Header row is present (table format).
    assert "Date" in result.output
    assert "Resource" in result.output

    # No filters → no params on the request
    request = route.calls.last.request
    assert request.url.params.get("resource_type") is None
    assert request.url.params.get("resource_id") is None


@respx.mock
def test_list_with_filters_and_pagination_params(configured):
    route = respx.get(f"{BASE}/v1/activity").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        [
            "activity",
            "list",
            "--resource-type",
            "expense_transactions",
            "--resource-id",
            "22222222-2222-2222-2222-222222222222",
            "--limit",
            "5",
            "--offset",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output

    request = route.calls.last.request
    assert request.url.params.get("resource_type") == "expense_transactions"
    assert request.url.params.get("resource_id") == "22222222-2222-2222-2222-222222222222"
    assert request.url.params.get("limit") == "5"
    assert request.url.params.get("offset") == "0"


@respx.mock
def test_list_pagination_hint(configured):
    paginated = page([ACTIVITY_ROW], total=5, limit=1, offset=0)
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=paginated))
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    assert "showing 1 of 5" in result.output


@respx.mock
def test_list_json_mode_passthrough(configured):
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=LIST_RESPONSE))
    result = runner.invoke(cli_app, ["activity", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == LIST_RESPONSE


@respx.mock
def test_list_empty(configured):
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=[]))
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    assert "(no activity)" in result.output


@respx.mock
def test_list_human_renderer_omits_snapshots(configured):
    """Snapshots are large nested dicts; only --json should surface them."""
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=LIST_RESPONSE))
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    assert "before_snapshot" not in result.output
    assert "after_snapshot" not in result.output
    # Snapshot contents not rendered; the live name lookup also misses (no route)
    # so "Coffee" stays out and the row falls back to the UUID prefix instead.
    assert "Coffee" not in result.output


@respx.mock
def test_list_unknown_action_code_falls_back_to_int(configured):
    weird = {**ACTIVITY_ROW, "action": 99}
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=[weird]))
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    # Action column now just shows the raw int as a string.
    assert "99" in result.output


@respx.mock
def test_list_422_bad_resource_id(configured):
    respx.get(f"{BASE}/v1/activity").mock(
        return_value=error_response(
            422, "VALIDATION_ERROR", "resource_id must be a UUID", {"resource_id": "not a UUID"}
        )
    )
    result = runner.invoke(cli_app, ["activity", "list", "--resource-id", "not-a-uuid"])
    assert result.exit_code == 1
    assert "VALIDATION_ERROR" in result.output
    assert "resource_id" in result.output


@respx.mock
def test_list_resource_name_resolved_live(configured):
    """The Resource column shows the human name fetched from the engine."""
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=LIST_RESPONSE))
    respx.get(f"{BASE}/v1/transactions/22222222-2222-2222-2222-222222222222").mock(
        return_value=httpx.Response(200, json={"id": "22222222", "title": "Latte"})
    )
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    assert "Latte" in result.output
    # Name resolved cleanly, so the UUID prefix never reaches the Resource cell.
    assert "22222222" not in result.output


@respx.mock
def test_list_resource_name_fallback_to_uuid_prefix(configured):
    """A 404 on the live lookup (deleted row) degrades to the 8-char UUID."""
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=LIST_RESPONSE))
    respx.get(f"{BASE}/v1/transactions/22222222-2222-2222-2222-222222222222").mock(
        return_value=error_response(404, "NOT_FOUND", "gone", None)
    )
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    assert "22222222" in result.output


# --- _resolve_resource_name, all six kinds (backlog 6.6a) -------------------


def _client(responses: dict) -> FakeClient:
    """A FakeClient answering the given GET paths; every other path 404s."""
    client = FakeClient()
    client.get_responses.update(responses)
    return client


@pytest.mark.parametrize(
    ("rtype", "path", "row", "expected"),
    [
        ("account", "/accounts/abc-123", {"name": "BCP"}, "BCP"),
        ("accounts", "/accounts/abc-123", {"name": "BCP"}, "BCP"),  # plural alias
        ("category", "/categories/abc-123", {"name": "Comida"}, "Comida"),
        ("categories", "/categories/abc-123", {"name": "Comida"}, "Comida"),
        ("hashtag", "/hashtags/abc-123", {"name": "viajes"}, "#viajes"),  # '#' prefix
        ("hashtags", "/hashtags/abc-123", {"name": "viajes"}, "#viajes"),
        ("transaction", "/transactions/abc-123", {"title": "Latte"}, "Latte"),
        (
            "expense_transactions",
            "/transactions/abc-123",
            {"description": "sin título"},
            "sin título",
        ),
    ],
)
def test_resolve_resource_name_per_kind(rtype, path, row, expected):
    client = _client({path: dict(row)})
    assert activity_cmd._resolve_resource_name(rtype, "abc-123", client) == expected
    assert client.requests == [("GET", path)]


def test_resolve_resource_name_miss_falls_back_to_prefix():
    """No row at that path (404) → the 8-char prefix, never an exception."""
    client = _client({})
    assert activity_cmd._resolve_resource_name("account", "0123456789ab", client) == "01234567"


def test_resolve_reconciliation_composite_labels():
    """date+account → 'date / name'; degrades to date-only, name-only, then prefix."""
    recon = {"statement_date": "2026-05-01T00:00:00Z", "account_id": "acc1"}

    client = _client({"/reconciliations/r-1": recon, "/accounts/acc1": {"name": "BCP"}})
    assert activity_cmd._resolve_resource_name("reconciliation", "r-1", client) == (
        "2026-05-01 / BCP"
    )

    client = _client({"/reconciliations/r-1": recon})  # account gone → date only
    assert activity_cmd._resolve_resource_name("reconciliations", "r-1", client) == "2026-05-01"

    client = _client(
        {"/reconciliations/r-1": {"account_id": "acc1"}, "/accounts/acc1": {"name": "BCP"}}
    )
    assert activity_cmd._resolve_resource_name("reconciliation", "r-1", client) == "BCP"  # no date

    client = _client({"/reconciliations/0123456789ab": {}})
    assert activity_cmd._resolve_resource_name("reconciliation", "0123456789ab", client) == (
        "01234567"
    )


def test_resolve_empty_name_falls_back_to_prefix():
    client = _client({"/hashtags/0123456789ab": {"name": ""}})
    assert activity_cmd._resolve_resource_name("hashtag", "0123456789ab", client) == "01234567"


def test_resolve_unknown_kind_and_bad_id():
    """Unknown kinds and null ids never reach the engine at all."""
    client = _client({})
    assert activity_cmd._resolve_resource_name("user", "0123456789ab", client) == "01234567"
    assert activity_cmd._resolve_resource_name(None, "0123456789ab", client) == "01234567"
    assert activity_cmd._resolve_resource_name("account", None, client) == "—"
    assert client.requests == []


# --- the three name maps, built once per page (A10) --------------------------
def test_the_name_maps_answer_without_touching_the_engine():
    """An account, category or hashtag row resolves off the preloaded map, so
    the per-row `GET /<kind>/<id>` never happens."""
    names = activity_cmd.NameMaps(
        accounts={"abc-123": "BCP"},
        categories={"cat-1": "Comida"},
        hashtags={"tag-1": "viajes"},
    )
    client = _client({})  # every path 404s — nothing may be read

    assert activity_cmd._resolve_resource_name("account", "abc-123", client, names) == "BCP"
    assert activity_cmd._resolve_resource_name("category", "cat-1", client, names) == "Comida"
    assert activity_cmd._resolve_resource_name("hashtag", "tag-1", client, names) == "#viajes"
    assert client.requests == []


def test_an_id_the_maps_do_not_know_still_falls_through_to_the_engine():
    """A row deleted since the list was read, or a list that failed to load —
    an empty map costs speed, never correctness."""
    names = activity_cmd.NameMaps()  # every map empty, as a failed load leaves them
    client = _client({"/accounts/abc-123": {"name": "BCP"}})

    assert activity_cmd._resolve_resource_name("account", "abc-123", client, names) == "BCP"
    assert client.requests == [("GET", "/accounts/abc-123")]


def test_a_transaction_row_is_still_a_per_row_read():
    """Transactions have no listing cheap enough to preload — the maps must
    not pretend to answer for them."""
    names = activity_cmd.NameMaps(accounts={"abc-123": "BCP"})
    client = _client({"/transactions/abc-123": {"title": "Latte"}})

    assert activity_cmd._resolve_resource_name("transaction", "abc-123", client, names) == "Latte"
    assert client.requests == [("GET", "/transactions/abc-123")]


def test_a_reconciliation_takes_its_account_name_from_the_map():
    """The second of the two reads a reconciliation row used to cost."""
    names = activity_cmd.NameMaps(accounts={"acc1": "BCP"})
    client = _client(
        {"/reconciliations/r-1": {"statement_date": "2026-05-01", "account_id": "acc1"}}
    )

    assert activity_cmd._resolve_resource_name("reconciliation", "r-1", client, names) == (
        "2026-05-01 / BCP"
    )
    assert client.requests == [("GET", "/reconciliations/r-1")]  # the account was NOT re-read


@respx.mock
def test_activity_list_reads_each_reference_list_once_for_the_whole_page(configured):
    """Five account rows used to cost five `GET /accounts/<id>`. Now the page
    costs one `GET /accounts` (plus categories and hashtags) and no per-row
    read at all."""
    rows = [
        {
            **ACTIVITY_ROW,
            "id": f"e{i}",
            "resource_type": "account",
            "resource_id": f"acc-{i}",
            "after_snapshot": None,
        }
        for i in range(5)
    ]
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=rows))
    accounts = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(
            200, json=whole([{"id": f"acc-{i}", "name": f"Account {i}"} for i in range(5)])
        )
    )
    respx.get(f"{BASE}/v1/categories").mock(return_value=httpx.Response(200, json=whole([])))
    respx.get(f"{BASE}/v1/hashtags").mock(return_value=httpx.Response(200, json=whole([])))
    per_row = [
        respx.get(f"{BASE}/v1/accounts/acc-{i}").mock(
            return_value=httpx.Response(200, json={"name": f"Account {i}"})
        )
        for i in range(5)
    ]

    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output

    assert accounts.call_count == 1  # one list read for the page
    assert [r.call_count for r in per_row] == [0] * 5  # and nothing per row
    for i in range(5):
        assert f"Account {i}" in result.output
