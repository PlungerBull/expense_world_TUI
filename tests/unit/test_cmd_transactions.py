import json
from uuid import UUID

import httpx
import pytest
import respx
from typer.testing import CliRunner

from expense.commands.transactions_cmd import app as transactions_app
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import (
    cursor_page,
    error_body,
    error_response,
    make_cli_app,
    page,
    strip_panel,
)

cli_app = make_cli_app(transactions_app, "transactions")

runner = CliRunner()


TRANSACTION_RESPONSE = {
    "id": "55555555-5555-5555-5555-555555555555",
    "user_id": "u_123",
    "title": "coffee",
    "amount_cents": 500,
    "date": "2026-04-24T12:00:00Z",
    "account_id": "acct-id",
    "category_id": "cat-id",
    "description": None,
    "transaction_type": 1,
    "hashtag_ids": [],
    "reconciliation_id": None,
    "created_at": "2026-04-24T10:00:00Z",
    "updated_at": "2026-04-24T10:00:00Z",
    "version": 1,
    "deleted_at": None,
}

LIST_RESPONSE = page([TRANSACTION_RESPONSE], total=1, limit=50, offset=0)


# The three reference lists the human list renderer joins against for names.
ACCOUNT_ROW = {"id": "acct-id", "name": "BCP Soles"}
CATEGORY_ROW = {"id": "cat-id", "name": "Food"}
HASHTAG_ROW = {"id": "h-1", "name": "lunch"}


def _reference_envelope(rows: list[dict]) -> dict:
    return page(rows, total=len(rows), limit=200, offset=0)


def _mock_name_maps() -> tuple:
    """Route the three reference lists so the renderer resolves real names.

    Without these routes the helpers swallow the unmatched request and return
    `{}`, and every reference cell degrades to an 8-char short id.
    """
    return (
        respx.get(f"{BASE}/v1/accounts").mock(
            return_value=httpx.Response(200, json=_reference_envelope([ACCOUNT_ROW]))
        ),
        respx.get(f"{BASE}/v1/categories").mock(
            return_value=httpx.Response(200, json=_reference_envelope([CATEGORY_ROW]))
        ),
        respx.get(f"{BASE}/v1/hashtags").mock(
            return_value=httpx.Response(200, json=_reference_envelope([HASHTAG_ROW]))
        ),
    )


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@respx.mock
def test_list_happy(configured):
    route = respx.get(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(cli_app, ["transactions", "list"])
    assert result.exit_code == 0, result.output
    assert "coffee" in result.output
    # Amount renders as grouped major units, not raw cents.
    assert "5.00" in result.output
    assert "500" not in result.output
    # Signed output is not opt-in; human mode adds the 20-row default (2026-07-11).
    assert dict(route.calls.last.request.url.params) == {
        "debit_as_negative": "true",
        "limit": "20",
    }


@respx.mock
def test_list_resolves_names_from_live_reference_lists(configured):
    """The renderer joins account/category/hashtag ids against live lists."""
    item = {**TRANSACTION_RESPONSE, "hashtag_ids": ["h-1"]}
    respx.get(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(200, json=page([item], total=1, limit=50, offset=0))
    )
    reference_routes = _mock_name_maps()
    result = runner.invoke(cli_app, ["transactions", "list"])
    assert result.exit_code == 0, result.output
    assert all(route.called for route in reference_routes)
    assert "BCP Soles" in result.output
    assert "Food" in result.output
    assert "lunch" in result.output


@respx.mock
def test_list_unresolvable_names_degrade_to_short_ids(configured):
    """A reference list the engine won't serve must not break the table."""
    item = {
        **TRANSACTION_RESPONSE,
        "account_id": "de37af15-0000-0000-0000-000000000000",
        "category_id": "ab99cc11-0000-0000-0000-000000000000",
        "hashtag_ids": [],
    }
    respx.get(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(200, json=page([item], total=1, limit=50, offset=0))
    )
    result = runner.invoke(cli_app, ["transactions", "list"])
    assert result.exit_code == 0, result.output
    assert "de37af15" in result.output
    assert "ab99cc11" in result.output


@respx.mock
def test_list_all_filters_pass_through(configured):
    route = respx.get(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        [
            "transactions",
            "list",
            "--account-id",
            "a-1",
            "--category-id",
            "c-1",
            "--hashtag-id",
            "h-1",
            "--reconciliation-id",
            "r-1",
            "--from",
            "2026-04-01",
            "--to",
            "2026-04-30",
            "--search",
            "coffee",
            "--limit",
            "25",
            "--offset",
            "10",
        ],
    )
    assert result.exit_code == 0, result.output

    params = dict(route.calls.last.request.url.params)
    assert params == {
        "account_id": "a-1",
        "category_id": "c-1",
        "hashtag_id": "h-1",
        "reconciliation_id": "r-1",
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
        "search": "coffee",
        "limit": "25",
        "offset": "10",
        "debit_as_negative": "true",
    }


@respx.mock
def test_list_rejects_retired_cleared_flag(configured):
    """--cleared/--no-cleared are gone from the surface entirely.

    The engine deleted the column 2026-08-16 (sql/035). This filter is the one
    surface that failed *silently*: ?cleared= stopped being honoured without
    erroring, so the command returned the full list looking like a filtered
    answer. Confirmed-at-the-bank is a reconciliation question now.
    """
    for flag in ("--cleared", "--no-cleared"):
        result = runner.invoke(cli_app, ["transactions", "list", flag])
        assert result.exit_code == 2, f"{flag} should not parse"
        assert "No such option" in result.output


def test_list_rejects_retired_include_deleted_flag(configured):
    """--include-deleted left with the engine's `?include_deleted=` (2026-09-23):
    a deleted row is invisible to every client, so there is nothing to show."""
    result = runner.invoke(cli_app, ["transactions", "list", "--include-deleted"])
    assert result.exit_code == 2
    assert "No such option: --include-deleted" in strip_panel(result.output)


@respx.mock
def test_list_pagination_hint_when_truncated(configured):
    paged = page([TRANSACTION_RESPONSE, TRANSACTION_RESPONSE], total=17, limit=2, offset=0)
    respx.get(f"{BASE}/v1/transactions").mock(return_value=httpx.Response(200, json=paged))
    result = runner.invoke(cli_app, ["transactions", "list", "--limit", "2"])
    assert result.exit_code == 0, result.output
    assert "showing 2 of 17" in result.output
    assert "--offset 2 --limit 2" in result.output


@respx.mock
def test_list_json_pass_through(configured):
    route = respx.get(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(cli_app, ["transactions", "list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == LIST_RESPONSE
    # --json keeps the raw request: no human-mode default limit (2026-07-11)
    assert route.calls.last.request.url.params.get("limit") is None


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@respx.mock
def test_get_happy(configured):
    respx.get(f"{BASE}/v1/transactions/abc").mock(
        return_value=httpx.Response(200, json=TRANSACTION_RESPONSE)
    )
    result = runner.invoke(cli_app, ["transactions", "get", "abc"])
    assert result.exit_code == 0, result.output
    assert "coffee" in result.output
    # The single-record dump formats *_cents fields as major units.
    assert "amount_cents: 5.00" in result.output


@respx.mock
def test_get_always_sends_debit_as_negative(configured):
    route = respx.get(f"{BASE}/v1/transactions/abc").mock(
        return_value=httpx.Response(200, json=TRANSACTION_RESPONSE)
    )
    result = runner.invoke(cli_app, ["transactions", "get", "abc"])
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params.get("debit_as_negative") == "true"


@respx.mock
def test_get_404(configured):
    respx.get(f"{BASE}/v1/transactions/missing").mock(
        return_value=error_response(404, "NOT_FOUND", "Transaction not found", None)
    )
    result = runner.invoke(cli_app, ["transactions", "get", "missing"])
    assert result.exit_code == 1
    assert "NOT_FOUND" in result.output


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_update_no_flags_errors(configured):
    result = runner.invoke(cli_app, ["transactions", "update", "abc"])
    assert result.exit_code == 1
    assert "No fields to update" in result.output


@respx.mock
def test_update_partial_payload(configured):
    route = respx.put(f"{BASE}/v1/transactions/abc").mock(
        return_value=httpx.Response(200, json=TRANSACTION_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        ["transactions", "update", "abc", "--title", "renamed"],
    )
    assert result.exit_code == 0, result.output

    body = json.loads(route.calls.last.request.content)
    assert body == {"title": "renamed"}


@respx.mock
def test_update_hashtag_ids_parsed_to_list(configured):
    route = respx.put(f"{BASE}/v1/transactions/abc").mock(
        return_value=httpx.Response(200, json=TRANSACTION_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        ["transactions", "update", "abc", "--hashtag-ids", "h-1, h-2,h-3"],
    )
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body == {"hashtag_ids": ["h-1", "h-2", "h-3"]}


@respx.mock
def test_update_422_reconciliation_lock_hint(configured):
    respx.put(f"{BASE}/v1/transactions/abc").mock(
        return_value=error_response(
            422,
            "VALIDATION_ERROR",
            "Field is read-only on a completed reconciliation.",
            {"amount_cents": "Locked by completed reconciliation."},
        )
    )
    result = runner.invoke(cli_app, ["transactions", "update", "abc", "--amount", "-100"])
    assert result.exit_code == 1
    assert "reconcile revert" in result.output
    assert "VALIDATION_ERROR" in result.output


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_requires_yes_in_non_tty(configured):
    result = runner.invoke(cli_app, ["transactions", "delete", "abc"])
    assert result.exit_code == 1
    assert "non-interactive" in result.output


@respx.mock
def test_delete_happy_no_warnings_channel(configured):
    # Since 2026-08-11 DELETE returns the plain transaction shape — no
    # `warnings` key.
    deleted = {**TRANSACTION_RESPONSE, "deleted_at": "2026-04-24T10:00:00Z"}
    respx.delete(f"{BASE}/v1/transactions/abc").mock(return_value=httpx.Response(200, json=deleted))
    result = runner.invoke(cli_app, ["transactions", "delete", "abc", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Warning:" not in result.output


@respx.mock
def test_delete_409_completed_reconciliation_hint(configured):
    respx.delete(f"{BASE}/v1/transactions/abc").mock(
        return_value=error_response(
            409,
            "CONFLICT",
            "Cannot delete a transaction assigned to a completed "
            "reconciliation. Revert the reconciliation to draft first.",
            None,
        )
    )
    result = runner.invoke(cli_app, ["transactions", "delete", "abc", "--yes"])
    assert result.exit_code == 1
    assert "expense reconcile revert" in result.output
    assert "CONFLICT" in result.output


@respx.mock
def test_update_reconciliation_id_lock_422_hint(configured):
    respx.put(f"{BASE}/v1/transactions/abc").mock(
        return_value=error_response(
            422,
            "VALIDATION_ERROR",
            "Field locked.",
            {"reconciliation_id": "Locked by completed reconciliation."},
        )
    )
    result = runner.invoke(cli_app, ["transactions", "update", "abc", "--reconciliation-id", "r1"])
    assert result.exit_code == 1
    assert "expense reconcile revert" in result.output
    assert "reconciliation_id" in result.output


@respx.mock
def test_delete_json_passes_through(configured):
    deleted = {**TRANSACTION_RESPONSE, "deleted_at": "2026-04-24T10:00:00Z"}
    respx.delete(f"{BASE}/v1/transactions/abc").mock(return_value=httpx.Response(200, json=deleted))
    result = runner.invoke(cli_app, ["transactions", "delete", "abc", "--yes", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == deleted


# ---------------------------------------------------------------------------
# batch
# ---------------------------------------------------------------------------


@respx.mock
def test_batch_happy_from_stdin(configured):
    items_in = [
        {
            "title": "a",
            "amount_cents": -100,
            "date": "2026-04-24T12:00:00Z",
            "account_id": "acct-1",
            "category_id": "cat-1",
        },
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "title": "b",
            "amount_cents": -200,
            "date": "2026-04-24T12:00:00Z",
            "account_id": "acct-1",
            "category_id": "cat-1",
        },
    ]
    response = {"created": [TRANSACTION_RESPONSE, TRANSACTION_RESPONSE]}
    route = respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json=response)
    )
    result = runner.invoke(cli_app, ["transactions", "batch"], input=json.dumps(items_in))
    assert result.exit_code == 0, result.output

    sent = json.loads(route.calls.last.request.content)
    assert "transactions" in sent
    assert len(sent["transactions"]) == 2
    UUID(sent["transactions"][0]["id"])
    assert sent["transactions"][1]["id"] == "11111111-1111-1111-1111-111111111111"
    assert "Created:" in result.output
    assert "Created 2 transactions." in result.output
    # The envelope must never leak as a Python repr in human mode.
    assert "created: [" not in result.output


@respx.mock
def test_batch_singular_count(configured):
    items_in = [
        {
            "title": "a",
            "amount_cents": -100,
            "date": "2026-04-24T12:00:00Z",
            "account_id": "acct-1",
            "category_id": "cat-1",
        }
    ]
    respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json={"created": [TRANSACTION_RESPONSE]})
    )
    result = runner.invoke(cli_app, ["transactions", "batch"], input=json.dumps(items_in))
    assert result.exit_code == 0, result.output
    assert "Created 1 transaction." in result.output


@respx.mock
def test_batch_json_passthrough(configured):
    items_in = [
        {
            "title": "a",
            "amount_cents": -100,
            "date": "2026-04-24T12:00:00Z",
            "account_id": "acct-1",
            "category_id": "cat-1",
        }
    ]
    response = {"created": [TRANSACTION_RESPONSE]}
    respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(201, json=response)
    )
    result = runner.invoke(cli_app, ["transactions", "batch", "--json"], input=json.dumps(items_in))
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == response


@respx.mock
def test_batch_422_surfaces_engine_envelope_without_hint(configured):
    # thin wrapper: the engine owns batch validation (e.g. category_id now
    # unconditionally required, 2026-08-10); the CLI adds no local check and
    # no hint — the envelope surfaces verbatim.
    envelope = error_body(
        "VALIDATION_ERROR",
        "Duplicate id within batch.",
        {"transactions[1].id": "Duplicate id within batch."},
    )
    respx.post(f"{BASE}/v1/transactions/batch").mock(
        return_value=httpx.Response(422, json=envelope)
    )
    items = [
        {
            "title": "a",
            "amount_cents": -100,
            "date": "2026-04-24T12:00:00Z",
            "account_id": "acct-1",
            "category_id": "cat-1",
        }
    ]
    result = runner.invoke(cli_app, ["transactions", "batch"], input=json.dumps(items))
    assert result.exit_code == 1
    assert "Duplicate id within batch." in result.output
    assert "Hint:" not in result.output


def test_batch_invalid_json_errors(configured):
    result = runner.invoke(cli_app, ["transactions", "batch"], input="not json")
    assert result.exit_code == 1
    assert "Invalid JSON" in result.output


def test_batch_empty_array_errors(configured):
    result = runner.invoke(cli_app, ["transactions", "batch"], input="[]")
    assert result.exit_code == 1
    assert "non-empty JSON array" in result.output


# ---------------------------------------------------------------------------
# fetch_transactions / count_transactions — the cursor-paged pair
# ---------------------------------------------------------------------------


@respx.mock
def test_fetch_transactions_sends_sort_and_after_never_offset(configured):
    from expense import config as config_module
    from expense.commands.transactions_cmd import fetch_transactions

    route = respx.get(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(200, json=cursor_page([TRANSACTION_RESPONSE]))
    )
    fetch_transactions(
        config_module.ensure_loaded(),
        account="acct-id",
        unreconciled=True,
        sort="date_asc",
        after="c1",
        limit=40,
    )
    assert dict(route.calls.last.request.url.params) == {
        "account_id": "acct-id",
        "unreconciled": "true",
        "sort": "date_asc",
        "after": "c1",
        "limit": "40",
        "debit_as_negative": "true",
    }


@respx.mock
def test_count_transactions_sends_the_filters_and_nothing_else(configured):
    """The count 422s on any parameter it does not declare — `debit_as_negative`,
    `sort`, `limit` and `after` are the list's own and must never reach it."""
    from expense import config as config_module
    from expense.commands.transactions_cmd import count_transactions

    route = respx.get(f"{BASE}/v1/transactions/count").mock(
        return_value=httpx.Response(200, json={"count": 1716})
    )
    count = count_transactions(
        config_module.ensure_loaded(),
        account="acct-id",
        unreconciled=True,
        date_from="2026-06-01",
    )
    assert count == 1716
    assert dict(route.calls.last.request.url.params) == {
        "account_id": "acct-id",
        "unreconciled": "true",
        "date_from": "2026-06-01",
    }


@pytest.mark.parametrize("body", [{}, {"count": None}, {"count": "3"}, {"count": True}, []])
@respx.mock
def test_count_transactions_raises_without_an_int_count(configured, body):
    """Never a guessed number: a body without an int `count` is an error."""
    from expense import config as config_module
    from expense.commands.transactions_cmd import count_transactions

    respx.get(f"{BASE}/v1/transactions/count").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(ValueError, match="without a count"):
        count_transactions(config_module.ensure_loaded(), account="acct-id")


def test_list_and_count_take_the_same_filters():
    """The engine declares one filter set for both endpoints; so do we. A filter
    added to one function and not the other is a header counting different rows
    than the list shows, with no error anywhere."""
    import inspect

    from expense.commands.transactions_cmd import count_transactions, fetch_transactions

    list_only = {"sort", "after", "limit"}
    list_params = set(inspect.signature(fetch_transactions).parameters) - list_only
    assert list_params == set(inspect.signature(count_transactions).parameters)
