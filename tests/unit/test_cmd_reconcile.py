import json
from uuid import UUID

import httpx
import respx
from typer.testing import CliRunner

from expense.commands.reconcile_cmd import app as reconcile_app
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, make_cli_app, page, strip_panel

cli_app = make_cli_app(reconcile_app, "reconcile")

runner = CliRunner()


RECON_DRAFT_RESPONSE = {
    "id": "11111111-1111-1111-1111-111111111111",
    "user_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "account_id": "22222222-2222-2222-2222-222222222222",
    "name": "Statement April 2026",
    "date_start": "2026-04-01T00:00:00Z",
    "date_end": "2026-04-30T23:59:59Z",
    # native cents only — the home-cent pair died with read-time conversion
    # (2026-08-05); reconciliations are single-account, so there is nothing to mix
    "beginning_balance_cents": 100000,
    "ending_balance_cents": 150000,
    "status": 1,
    # difference_cents replaced sort_order/beginning_balance_source/
    # chained_from_reconciliation_id in the 2026-08-06 de-chaining: it is
    # (ending − beginning) minus the assigned transactions, computed at read time
    "difference_cents": 0,
    "version": 1,
    "created_at": "2026-04-15T10:00:00Z",
    "updated_at": "2026-04-15T10:00:00Z",
    "deleted_at": None,
}

RECON_OFF_RESPONSE = {
    **RECON_DRAFT_RESPONSE,
    "id": "33333333-3333-3333-3333-333333333333",
    "difference_cents": -3500,
}

# A batch opened before the statement arrived. Both fields are nullable since
# the engine's sql/040 (2026-09-14) — it stopped storing a 0 ending balance as
# a stand-in for "not entered yet" and computing the add-up check against it.
RECON_UNENTERED_RESPONSE = {
    **RECON_DRAFT_RESPONSE,
    "id": "44444444-4444-4444-4444-444444444444",
    "ending_balance_cents": None,
    "difference_cents": None,
}

LIST_RESPONSE = page(
    [RECON_DRAFT_RESPONSE, RECON_OFF_RESPONSE, RECON_UNENTERED_RESPONSE],
    total=3,
    limit=50,
    offset=0,
)

DETAIL_WITH_TRANSACTIONS = {
    **RECON_DRAFT_RESPONSE,
    "transactions": [
        {
            "id": "tx-001",
            "title": "Lunch",
            "amount_cents": -1500,
            "account_id": "22222222-2222-2222-2222-222222222222",
            "category_id": "cat-food",
            "date": "2026-04-15T12:00:00Z",
            "reconciliation_id": RECON_DRAFT_RESPONSE["id"],
            "version": 1,
            "created_at": "2026-04-15T12:05:00Z",
            "updated_at": "2026-04-15T12:05:00Z",
            "deleted_at": None,
        }
    ],
    "transactions_total": 3,
    "transactions_limit": 1,
    "transactions_offset": 0,
    "transactions_truncated": True,
}

DETAIL_EMPTY_TRANSACTIONS = {
    **RECON_DRAFT_RESPONSE,
    "transactions": [],
    "transactions_total": 0,
    "transactions_limit": 50,
    "transactions_offset": 0,
    "transactions_truncated": False,
}


@respx.mock
def test_list_happy_with_account_filter(configured):
    route = respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        ["reconcile", "list", "--account-id", "22222222-2222-2222-2222-222222222222"],
    )
    assert result.exit_code == 0, result.output
    for header in (
        "Account",
        "Name",
        "Period",
        "Begin",
        "End",
        "Status",
        "Id",
    ):
        assert header in result.output
    assert "Source" not in result.output  # died with the 2026-08-06 de-chaining
    assert "Statement April 2026" in result.output
    assert "2026-04-01 → 2026-04-30" in result.output

    lines = result.output.splitlines()
    balanced_row = next(line for line in lines if RECON_DRAFT_RESPONSE["id"] in line)
    assert "draft" in balanced_row

    request = route.calls.last.request
    assert request.url.params.get("account_id") == "22222222-2222-2222-2222-222222222222"


@respx.mock
def test_list_renders_difference_column(configured):
    """The flat table always prints the number — 0.00 when the batch balances,
    the signed figure when it does not. No glyph translation: this table gets
    piped and eyeballed (Phase 3 sketch, the CLI half of option H)."""
    respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(cli_app, ["reconcile", "list"])
    assert result.exit_code == 0, result.output
    assert "Diff" in result.output

    lines = result.output.splitlines()
    balanced = next(line for line in lines if RECON_DRAFT_RESPONSE["id"] in line)
    off = next(line for line in lines if RECON_OFF_RESPONSE["id"] in line)
    assert "0.00" in balanced
    assert "-35.00" in off


@respx.mock
def test_list_renders_an_unentered_ending_balance_as_a_dash(configured):
    """A batch with no closing figure yet reads as absent, not as `(null)`.

    `ending_balance_cents` and `difference_cents` are nullable since the
    engine's sql/040: before it, an omitted ending balance was stored as 0 and
    the add-up check was computed against that placeholder, so "not entered"
    and "the statement says zero" were the same row. Now they differ on the
    wire, and this asserts they differ on the screen too — the `0.00` on the
    balanced row is the control.
    """
    respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(cli_app, ["reconcile", "list"])
    assert result.exit_code == 0, result.output

    lines = result.output.splitlines()
    unentered = next(line for line in lines if RECON_UNENTERED_RESPONSE["id"] in line)
    balanced = next(line for line in lines if RECON_DRAFT_RESPONSE["id"] in line)

    assert "(null)" not in unentered, (
        "an un-entered closing balance is an ordinary state, not a shape error"
    )
    assert "—" in unentered
    # The control: an entered figure of 0 still prints as a number, so the two
    # states stay distinguishable in the piped table.
    assert "0.00" in balanced


@respx.mock
def test_list_empty(configured):
    respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(200, json=page([], total=0, limit=50, offset=0))
    )
    result = runner.invoke(cli_app, ["reconcile", "list"])
    assert result.exit_code == 0, result.output
    assert "(no reconciliations)" in result.output


@respx.mock
def test_list_json_passthrough(configured):
    respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(cli_app, ["reconcile", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == LIST_RESPONSE


@respx.mock
def test_get_with_transactions_window(configured):
    route = respx.get(f"{BASE}/v1/reconciliations/11111111-1111-1111-1111-111111111111").mock(
        return_value=httpx.Response(200, json=DETAIL_WITH_TRANSACTIONS)
    )
    result = runner.invoke(
        cli_app,
        ["reconcile", "get", "11111111-1111-1111-1111-111111111111", "--limit", "1"],
    )
    assert result.exit_code == 0, result.output
    assert "Statement April 2026" in result.output
    assert "Transactions:" in result.output
    assert "Lunch" in result.output
    assert "more transactions" in result.output
    assert "transactions list --reconciliation" in result.output

    request = route.calls.last.request
    assert request.url.params.get("limit") == "1"
    assert request.url.params.get("debit_as_negative") == "true"


@respx.mock
def test_get_empty_transactions_hint(configured):
    respx.get(f"{BASE}/v1/reconciliations/11111111-1111-1111-1111-111111111111").mock(
        return_value=httpx.Response(200, json=DETAIL_EMPTY_TRANSACTIONS)
    )
    result = runner.invoke(cli_app, ["reconcile", "get", "11111111-1111-1111-1111-111111111111"])
    assert result.exit_code == 0, result.output
    assert "(no transactions assigned)" in result.output
    assert "transactions update <tx-id> --reconciliation-id" in result.output


@respx.mock
def test_get_404(configured):
    respx.get(f"{BASE}/v1/reconciliations/missing").mock(
        return_value=error_response(404, "NOT_FOUND", "Not found", None)
    )
    result = runner.invoke(cli_app, ["reconcile", "get", "missing"])
    assert result.exit_code == 1
    assert "NOT_FOUND" in result.output


@respx.mock
def test_create_sends_both_required_fields(configured):
    route = respx.post(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(201, json=RECON_DRAFT_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        [
            "reconcile",
            "create",
            "--account-id",
            "22222222-2222-2222-2222-222222222222",
            "--name",
            "Statement April 2026",
            "--date-start",
            "2026-04-01",
            "--date-end",
            "2026-04-30",
            "--beginning-balance",
            "100000",
            "--ending-balance",
            "150000",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created:" in result.output
    assert "Next: attach transactions" in result.output

    body = json.loads(route.calls.last.request.content)
    UUID(body["id"])
    assert body["account_id"] == "22222222-2222-2222-2222-222222222222"
    assert body["name"] == "Statement April 2026"
    assert body["beginning_balance_cents"] == 100000
    assert body["ending_balance_cents"] == 150000
    assert body["date_start"].startswith("2026-04-01")
    # both retired by the de-chaining; the request schemas are extra="forbid"
    assert "beginning_balance_source" not in body
    assert "sort_order" not in body
    assert "X-Idempotency-Key" in route.calls.last.request.headers


def test_create_without_beginning_balance_blocks_at_parse(configured):
    """Omitting it used to mean \"chain from the previous batch\"; there is no
    derived mode left, so the engine 422s. Typer refuses before the HTTP call."""
    result = runner.invoke(
        cli_app,
        [
            "reconcile",
            "create",
            "--account-id",
            "acct",
            "--name",
            "X",
            "--date-start",
            "2026-04-01",
            "--date-end",
            "2026-04-30",
        ],
    )
    assert result.exit_code == 2  # Click usage error
    assert "--beginning-balance" in strip_panel(result.output)


def test_create_without_date_end_blocks_at_parse(configured):
    """Required since 2026-09-20, and this is a CLIENT-side rule.

    The engine still accepts a half-dated draft. But completing one seals its
    window, a half-dated window seals nothing, and so a period created without
    an end date can never be completed — the refusal would arrive at closing
    time, months after the statement was in front of you. Asking for both dates
    up front moves it to the moment the answer is known.
    """
    result = runner.invoke(
        cli_app,
        [
            "reconcile",
            "create",
            "--account-id",
            "acct",
            "--name",
            "X",
            "--date-start",
            "2026-04-01",
            "--beginning-balance",
            "100000",
        ],
    )
    assert result.exit_code == 2
    assert "--date-end" in strip_panel(result.output)


def test_create_without_date_start_blocks_at_parse(configured):
    """date_start is what orders a batch since the de-chaining."""
    result = runner.invoke(
        cli_app,
        [
            "reconcile",
            "create",
            "--account-id",
            "acct",
            "--name",
            "X",
            "--date-end",
            "2026-04-30",
            "--beginning-balance",
            "100000",
        ],
    )
    assert result.exit_code == 2
    assert "--date-start" in strip_panel(result.output)


def test_create_rejects_retired_flags(configured):
    """--source and --sort-order are gone from the surface entirely."""
    for flag, value in (("--source", "chained"), ("--sort-order", "3")):
        result = runner.invoke(
            cli_app,
            [
                "reconcile",
                "create",
                "--account-id",
                "acct",
                "--name",
                "X",
                "--date-start",
                "2026-04-01",
                "--date-end",
                "2026-04-30",
                "--beginning-balance",
                "100000",
                flag,
                value,
            ],
        )
        assert result.exit_code == 2, flag
        assert "No such option" in strip_panel(result.output)


@respx.mock
def test_update_partial_payload(configured):
    route = respx.put(f"{BASE}/v1/reconciliations/11111111-1111-1111-1111-111111111111").mock(
        return_value=httpx.Response(200, json=RECON_DRAFT_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        [
            "reconcile",
            "update",
            "11111111-1111-1111-1111-111111111111",
            "--name",
            "Renamed",
            "--ending-balance",
            "200000",
        ],
    )
    assert result.exit_code == 0, result.output

    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "Renamed", "ending_balance_cents": 200000}
    assert "X-Idempotency-Key" in route.calls.last.request.headers


def test_update_rejects_retired_source_flag(configured):
    result = runner.invoke(
        cli_app,
        [
            "reconcile",
            "update",
            "11111111-1111-1111-1111-111111111111",
            "--source",
            "chained",
        ],
    )
    assert result.exit_code == 2
    assert "No such option" in strip_panel(result.output)


@respx.mock
def test_update_field_locked_422_surfaces_hint(configured):
    respx.put(f"{BASE}/v1/reconciliations/11111111-1111-1111-1111-111111111111").mock(
        return_value=error_response(
            422,
            "VALIDATION_ERROR",
            "Cannot edit locked fields on completed reconciliation.",
            {
                "ending_balance_cents": "Locked while reconciliation is completed.",
            },
        )
    )
    result = runner.invoke(
        cli_app,
        [
            "reconcile",
            "update",
            "11111111-1111-1111-1111-111111111111",
            "--ending-balance",
            "200000",
        ],
    )
    assert result.exit_code == 1
    assert "VALIDATION_ERROR" in result.output
    assert "expense reconcile revert" in result.output


def test_delete_requires_yes_in_non_tty(configured):
    result = runner.invoke(cli_app, ["reconcile", "delete", "11111111-1111-1111-1111-111111111111"])
    assert result.exit_code == 1
    assert "non-interactive" in result.output


@respx.mock
def test_delete_with_yes(configured):
    respx.delete(f"{BASE}/v1/reconciliations/11111111-1111-1111-1111-111111111111").mock(
        return_value=httpx.Response(200, json={**RECON_DRAFT_RESPONSE, "deleted_at": "now"})
    )
    result = runner.invoke(
        cli_app,
        ["reconcile", "delete", "11111111-1111-1111-1111-111111111111", "--yes"],
    )
    assert result.exit_code == 0, result.output


@respx.mock
def test_delete_409_surfaces_hint(configured):
    respx.delete(f"{BASE}/v1/reconciliations/11111111-1111-1111-1111-111111111111").mock(
        return_value=error_response(
            409, "CONFLICT", "Cannot delete a completed reconciliation.", None
        )
    )
    result = runner.invoke(
        cli_app,
        ["reconcile", "delete", "11111111-1111-1111-1111-111111111111", "--yes"],
    )
    assert result.exit_code == 1
    assert "CONFLICT" in result.output
    assert "expense reconcile revert" in result.output


# ---------------------------------------------------------------------------
# Phase 2: complete, revert (state machine)
# ---------------------------------------------------------------------------


@respx.mock
def test_complete_happy_prints_locked_count(configured):
    response_with_count = {**RECON_DRAFT_RESPONSE, "status": 2, "transactions_total": 17}
    route = respx.post(
        f"{BASE}/v1/reconciliations/11111111-1111-1111-1111-111111111111/complete"
    ).mock(return_value=httpx.Response(200, json=response_with_count))
    result = runner.invoke(
        cli_app, ["reconcile", "complete", "11111111-1111-1111-1111-111111111111"]
    )
    assert result.exit_code == 0, result.output
    assert "Locked 17 transactions." in result.output
    assert "X-Idempotency-Key" in route.calls.last.request.headers


@respx.mock
def test_complete_422_empty_batch_surfaces_hint(configured):
    respx.post(f"{BASE}/v1/reconciliations/11111111-1111-1111-1111-111111111111/complete").mock(
        return_value=error_response(
            422, "VALIDATION_ERROR", "No transactions assigned to this reconciliation.", {}
        )
    )
    result = runner.invoke(
        cli_app, ["reconcile", "complete", "11111111-1111-1111-1111-111111111111"]
    )
    assert result.exit_code == 1
    assert "VALIDATION_ERROR" in result.output
    assert "expense transactions update" in result.output


def test_revert_requires_yes_in_non_tty(configured):
    result = runner.invoke(cli_app, ["reconcile", "revert", "11111111-1111-1111-1111-111111111111"])
    assert result.exit_code == 1
    assert "non-interactive" in result.output


@respx.mock
def test_revert_with_yes_prints_unlocked_count(configured):
    response_with_count = {**RECON_DRAFT_RESPONSE, "status": 1, "transactions_total": 17}
    route = respx.post(
        f"{BASE}/v1/reconciliations/11111111-1111-1111-1111-111111111111/revert"
    ).mock(return_value=httpx.Response(200, json=response_with_count))
    result = runner.invoke(
        cli_app,
        ["reconcile", "revert", "11111111-1111-1111-1111-111111111111", "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert "Unlocked 17 transactions." in result.output
    assert "X-Idempotency-Key" in route.calls.last.request.headers


@respx.mock
def test_list_resolves_account_name_from_live_accounts(configured):
    """The Account column joins account_id against the live accounts list."""
    respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    accounts_route = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(
            200,
            json=page(
                [{"id": RECON_DRAFT_RESPONSE["account_id"], "name": "BCP Soles"}],
                total=1,
                limit=200,
                offset=0,
            ),
        )
    )
    result = runner.invoke(cli_app, ["reconcile", "list"])
    assert result.exit_code == 0, result.output
    assert accounts_route.called
    assert "BCP Soles" in result.output


@respx.mock
def test_list_unresolvable_account_degrades_to_short_id(configured):
    """A reference list the engine won't serve must not break the table."""
    respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=httpx.Response(200, json=LIST_RESPONSE)
    )
    result = runner.invoke(cli_app, ["reconcile", "list"])
    assert result.exit_code == 0, result.output
    assert "22222222" in result.output
    assert "BCP Soles" not in result.output


@respx.mock
def test_list_surfaces_an_engine_refusal(configured):
    respx.get(f"{BASE}/v1/reconciliations").mock(
        return_value=error_response(401, "UNAUTHORIZED", "Token is not valid.")
    )
    result = runner.invoke(cli_app, ["reconcile", "list"])
    assert result.exit_code == 1
    assert "UNAUTHORIZED" in result.output


# ---- sealed periods (engine, 2026-09-20) ------------------------------------
_RID = "11111111-1111-1111-1111-111111111111"
_COMPLETE = f"{BASE}/v1/reconciliations/{_RID}/complete"

#: Quoted from the engine, app/helpers/reconciliations.py. The two refusals
#: below arrive under the SAME `fields` key, which is the whole reason the CLI
#: dispatches on the message.
_UNFILED_MSG = "Cannot complete reconciliation while transactions in its period are unassigned."
_UNFILED_FIELDS = {
    "transactions": (
        "3 transaction(s) dated inside this period are not assigned to any "
        "reconciliation. Assign or delete them first."
    )
}
_EMPTY_FIELDS = {"transactions": "At least one transaction must be assigned."}


@respx.mock
def test_complete_renders_the_gap_warning(configured):
    """The warnings channel reaches the user.

    A transaction inside an uncovered stretch moves no period's arithmetic —
    `difference_cents` is two balances typed off a statement minus the rows
    that were ticked — so this message is the only thing in the system that
    will ever point at the gap.
    """
    body = {
        **RECON_DRAFT_RESPONSE,
        "status": 2,
        "transactions_total": 4,
        "warnings": [
            "2026-06-26 to 2026-07-23 on this account is covered by no completed reconciliation."
        ],
    }
    respx.post(_COMPLETE).mock(return_value=httpx.Response(200, json=body))
    result = runner.invoke(cli_app, ["reconcile", "complete", _RID])
    assert result.exit_code == 0, result.output
    assert "Warning: 2026-06-26 to 2026-07-23" in result.output
    assert "Locked 4 transactions." in result.output


@respx.mock
def test_complete_says_nothing_extra_when_there_is_no_gap(configured):
    """`warnings` is always present on this endpoint and empty on a clean
    completion — an empty list must not print a bare `Warning:` line."""
    body = {**RECON_DRAFT_RESPONSE, "status": 2, "transactions_total": 4, "warnings": []}
    respx.post(_COMPLETE).mock(return_value=httpx.Response(200, json=body))
    result = runner.invoke(cli_app, ["reconcile", "complete", _RID])
    assert result.exit_code == 0, result.output
    assert "Warning" not in result.output


@respx.mock
def test_complete_json_passes_the_warnings_through(configured):
    body = {**RECON_DRAFT_RESPONSE, "status": 2, "warnings": ["a gap"]}
    respx.post(_COMPLETE).mock(return_value=httpx.Response(200, json=body))
    result = runner.invoke(cli_app, ["reconcile", "complete", _RID, "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["warnings"] == ["a gap"]


@respx.mock
def test_complete_422_unfiled_rows_prints_a_command_that_runs(configured):
    """The engine gives the count but neither the account nor the window, so
    the CLI spends one extra read — on a call that has already failed — to
    print a line the user can paste rather than a template with three holes."""
    respx.post(_COMPLETE).mock(
        return_value=error_response(422, "VALIDATION_ERROR", _UNFILED_MSG, _UNFILED_FIELDS)
    )
    respx.get(f"{BASE}/v1/reconciliations/{_RID}").mock(
        return_value=httpx.Response(
            200,
            json={
                **RECON_DRAFT_RESPONSE,
                "account_id": "acc-1",
                "date_start": "2026-07-24T00:00:00Z",
                "date_end": "2026-08-25T00:00:00Z",
            },
        )
    )
    result = runner.invoke(cli_app, ["reconcile", "complete", _RID])
    assert result.exit_code == 1
    assert "--account-id acc-1" in result.output
    assert "--unreconciled" in result.output
    assert "--date-from 2026-07-24 --date-to 2026-08-25" in result.output
    # and the engine's own envelope is still rendered underneath the hint
    assert "3 transaction(s) dated inside this period" in result.output


@respx.mock
def test_complete_422_unfiled_rows_degrades_when_the_record_cannot_be_read(configured):
    """The extra read is a convenience, not a dependency: if it fails the user
    still gets the flags, just without the values filled in."""
    respx.post(_COMPLETE).mock(
        return_value=error_response(422, "VALIDATION_ERROR", _UNFILED_MSG, _UNFILED_FIELDS)
    )
    respx.get(f"{BASE}/v1/reconciliations/{_RID}").mock(
        return_value=error_response(404, "NOT_FOUND", "gone", None)
    )
    result = runner.invoke(cli_app, ["reconcile", "complete", _RID])
    assert result.exit_code == 1
    assert "--unreconciled" in result.output


@respx.mock
def test_the_two_complete_refusals_do_not_borrow_each_others_hint(configured):
    """Both arrive as `fields["transactions"]`; only the message separates them.

    Getting this backwards would tell someone with three untick'd rows to
    "assign at least one transaction", which is both wrong and confusing —
    they have assigned plenty.
    """
    respx.post(_COMPLETE).mock(
        return_value=error_response(422, "VALIDATION_ERROR", _UNFILED_MSG, _UNFILED_FIELDS)
    )
    respx.get(f"{BASE}/v1/reconciliations/{_RID}").mock(
        return_value=error_response(404, "NOT_FOUND", "gone", None)
    )
    unfiled = runner.invoke(cli_app, ["reconcile", "complete", _RID])
    assert "at least one transaction" not in unfiled.output

    respx.post(_COMPLETE).mock(
        return_value=error_response(
            422, "VALIDATION_ERROR", "No transactions assigned.", _EMPTY_FIELDS
        )
    )
    empty = runner.invoke(cli_app, ["reconcile", "complete", _RID])
    assert "assign at least one transaction" in empty.output
    assert "--unreconciled" not in empty.output


@respx.mock
def test_complete_422_missing_date_points_at_the_fix(configured):
    respx.post(_COMPLETE).mock(
        return_value=error_response(
            422,
            "VALIDATION_ERROR",
            "Cannot complete reconciliation without a period.",
            {"date_end": "Required to complete — a completed period seals these dates."},
        )
    )
    result = runner.invoke(cli_app, ["reconcile", "complete", _RID])
    assert result.exit_code == 1
    assert f"expense reconcile update {_RID} --date-end" in result.output


@respx.mock
def test_create_overlap_422_points_at_the_neighbours(configured):
    respx.post(f"{BASE}/v1/reconciliations").mock(
        return_value=error_response(
            422,
            "VALIDATION_ERROR",
            "Reconciliation period overlaps another on this account.",
            {
                "date_start": (
                    "Overlaps 'August 2026' (2026-07-24 to 2026-08-25). "
                    "A day belongs to one statement."
                )
            },
        )
    )
    result = runner.invoke(
        cli_app,
        [
            "reconcile",
            "create",
            "--account-id",
            "acct",
            "--name",
            "September 2026",
            "--date-start",
            "2026-08-20",
            "--date-end",
            "2026-09-25",
            "--beginning-balance",
            "100000",
        ],
    )
    assert result.exit_code == 1
    assert "a day belongs to exactly one statement" in result.output.lower()
    assert "reconcile list --account-id" in result.output
    assert "Overlaps 'August 2026'" in result.output  # the engine's own words survive


@respx.mock
def test_update_inverted_range_422_surfaces_a_hint(configured):
    respx.put(f"{BASE}/v1/reconciliations/{_RID}").mock(
        return_value=error_response(
            422,
            "VALIDATION_ERROR",
            "Reconciliation period validation failed.",
            {"date_end": "Must not be earlier than date_start."},
        )
    )
    result = runner.invoke(cli_app, ["reconcile", "update", _RID, "--date-end", "2026-01-01"])
    assert result.exit_code == 1
    assert "--date-end must not be earlier than --date-start" in result.output
