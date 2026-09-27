import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from expense.commands import activity_cmd
from expense.commands.activity_cmd import app as activity_app
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import FakeClient, error_response, make_cli_app, whole, window_page

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

# The window the engine echoes when none is sent: now, and 30 days before.
FROM = "2026-04-03T10:00:00.123456-05:00"
TO = "2026-05-03T10:00:00.123456-05:00"


def wpage(items: list, *, next_cursor: str | None = None) -> dict:
    return window_page(items, date_from=FROM, date_to=TO, next_cursor=next_cursor)


LIST_RESPONSE = wpage([ACTIVITY_ROW])


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
def test_list_with_filters_window_and_cursor(configured):
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
            "--from",
            "2026-09-01T00:00:00Z",
            "--to",
            "2026-09-25T12:00:00-05:00",
            "--after",
            "c1",
            "--limit",
            "5",
        ],
    )
    assert result.exit_code == 0, result.output

    params = route.calls.last.request.url.params
    assert params.get("resource_type") == "expense_transactions"
    assert params.get("resource_id") == "22222222-2222-2222-2222-222222222222"
    # times that already carry an offset pass through as typed
    assert params.get("date_from") == "2026-09-01T00:00:00Z"
    assert params.get("date_to") == "2026-09-25T12:00:00-05:00"
    assert params.get("after") == "c1"
    assert params.get("limit") == "5"
    assert "offset" not in params


@respx.mock
def test_list_sends_bare_days_as_typed(configured):
    """The engine reads a bare day as that whole day in `display_timezone`
    (engine `aaee6bf`), so the CLI converts nothing and reads no zone."""
    route = respx.get(f"{BASE}/v1/activity").mock(
        return_value=httpx.Response(
            200,
            json=window_page(
                [],
                date_from="2026-09-01T00:00:00-05:00",
                date_to="2026-09-25T23:59:59.999999-05:00",
            ),
        )
    )
    result = runner.invoke(
        cli_app, ["activity", "list", "--from", "2026-09-01", "--to", "2026-09-25"]
    )
    assert result.exit_code == 0, result.output
    params = route.calls.last.request.url.params
    assert params.get("date_from") == "2026-09-01"
    assert params.get("date_to") == "2026-09-25"
    assert not any("/auth/me" in str(c.request.url) for c in respx.calls)
    # the window reads in the user's own day, to the minute
    assert "(2026-09-01 00:00 → 2026-09-25 23:59 · older: pass --to 2026-09-01T00:00:00-05:00)" in (
        result.output
    )


@respx.mock
def test_list_surfaces_the_engines_refusal_of_a_bad_day(configured):
    respx.get(f"{BASE}/v1/activity").mock(
        return_value=error_response(
            422, "VALIDATION_ERROR", "Request validation failed.", {"date_from": "Invalid day."}
        )
    )
    result = runner.invoke(cli_app, ["activity", "list", "--from", "2026-02-30"])
    assert result.exit_code == 1
    assert "VALIDATION_ERROR" in result.output
    assert "date_from" in result.output


def test_list_has_no_offset(configured):
    result = runner.invoke(cli_app, ["activity", "list", "--offset", "0"])
    assert result.exit_code == 2


@respx.mock
def test_list_says_how_to_reach_the_rest_of_the_window(configured):
    respx.get(f"{BASE}/v1/activity").mock(
        return_value=httpx.Response(200, json=wpage([ACTIVITY_ROW], next_cursor="c2"))
    )
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    assert "(2026-04-03 10:00 → 2026-05-03 10:00 · more in this window: pass --after c2)" in (
        result.output
    )


@respx.mock
def test_list_on_the_windows_last_page_names_the_exact_older_bound(configured):
    """The echoed `date_from` goes back verbatim: a bare day would widen to the
    whole day and show that day's rows twice."""
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=LIST_RESPONSE))
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    assert f"(2026-04-03 10:00 → 2026-05-03 10:00 · older: pass --to {FROM})" in result.output


@respx.mock
def test_list_json_mode_passthrough(configured):
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=LIST_RESPONSE))
    result = runner.invoke(cli_app, ["activity", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == LIST_RESPONSE


@respx.mock
def test_list_empty(configured):
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=wpage([])))
    result = runner.invoke(cli_app, ["activity", "list"])
    assert result.exit_code == 0, result.output
    # an empty window still says which window it was — never "no history"
    assert "(no activity in this window)" in result.output
    assert f"older: pass --to {FROM}" in result.output


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
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=wpage([weird])))
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


# --- _resolve_resource_name, all six kinds -------------------


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


def test_resolve_reconciliation_labels_come_from_the_snapshot():
    """name + account → 'name / account'; degrades to either half, then the
    prefix. Never a read of the reconciliation: the engine has none by id."""
    snap = {"name": "August 2026", "account_id": "acc1"}

    client = _client({"/accounts/acc1": {"name": "BCP"}})
    assert activity_cmd._resolve_resource_name("reconciliation", "r-1", client, snapshot=snap) == (
        "August 2026 / BCP"
    )
    assert client.requests == [("GET", "/accounts/acc1")]

    client = _client({})  # account gone → name only
    assert (
        activity_cmd._resolve_resource_name("reconciliations", "r-1", client, snapshot=snap)
        == "August 2026"
    )

    client = _client({"/accounts/acc1": {"name": "BCP"}})
    no_name = {"account_id": "acc1"}
    assert (
        activity_cmd._resolve_resource_name("reconciliation", "r-1", client, snapshot=no_name)
        == "BCP"
    )

    client = _client({})
    assert activity_cmd._resolve_resource_name("reconciliation", "0123456789ab", client) == (
        "01234567"
    )
    assert client.requests == []


def test_a_deleted_reconciliation_is_named_from_its_before_snapshot():
    """A delete's `after_snapshot` is empty; the row still gets its name."""
    names = activity_cmd.NameMaps(accounts={"acc1": "BCP"})
    item = {
        "resource_type": "reconciliation",
        "resource_id": "r-1",
        "action": 3,
        "created_at": "2026-09-24T18:02:00Z",
        "before_snapshot": {"name": "August 2026", "account_id": "acc1"},
        "after_snapshot": None,
    }
    client = _client({})
    assert activity_cmd.activity_display_cells(item, client, names)[-1] == "August 2026 / BCP"
    assert client.requests == []


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


# --- the three name maps, built once per page --------------------------------
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
    """With the maps built, a reconciliation row costs no read at all."""
    names = activity_cmd.NameMaps(accounts={"acc1": "BCP"})
    client = _client({})
    snap = {"name": "August 2026", "account_id": "acc1"}

    assert activity_cmd._resolve_resource_name(
        "reconciliation", "r-1", client, names, snapshot=snap
    ) == ("August 2026 / BCP")
    assert client.requests == []


@respx.mock
def test_activity_list_reads_each_reference_list_once_for_the_whole_page(configured):
    """Five account rows never cost five `GET /accounts/<id>`: the page
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
    respx.get(f"{BASE}/v1/activity").mock(return_value=httpx.Response(200, json=wpage(rows)))
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


def test_activity_resolves_singular_resource_types(fake_client):
    # The engine writes resource_type in the SINGULAR ("transaction", …); the
    # resolver must map those (and the older plural forms) to the collection
    # path it reads live.
    import expense.commands.activity_cmd as ac

    fake_client.get_responses["/transactions/abc-123"] = {"title": "Groceries"}
    fake_client.get_responses["/accounts/def-456"] = {"name": "BCP Soles"}
    assert ac._resolve_resource_name("transaction", "abc-123", fake_client) == "Groceries"
    alias = ac._resolve_resource_name("expense_transactions", "abc-123", fake_client)
    assert alias == "Groceries"
    assert ac._resolve_resource_name("account", "def-456", fake_client) == "BCP Soles"
    # unknown type → short id, never a crash (and never an engine read)
    assert ac._resolve_resource_name("user", "0123456789ab", fake_client) == "01234567"
    assert not any(path.startswith("/users") for _, path in fake_client.requests)
    # a routed miss (deleted record → 404) also degrades to the short id
    assert ac._resolve_resource_name("account", "0123456789ab", fake_client) == "01234567"
