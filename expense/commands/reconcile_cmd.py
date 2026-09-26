from uuid import uuid4

import typer

from expense import config as config_module
from expense.commands._resource import (
    JSON_OPT,
    YES_OPT,
    build_update_payload,
    fetch_body,
    format_cents,
    format_cents_or_dash,
    items_of,
    load_account_name_map,
    print_warnings,
    query_params,
    render_record,
    render_table,
    require_yes,
    resolve_name,
    run_delete,
    run_toggle,
)
from expense.context import get_verbose
from expense.errors import EngineError, error_haystack, handle_errors
from expense.http import ExpenseClient
from expense.jsonout import emit_json

app = typer.Typer(help="Reconciliations.", no_args_is_help=True)

_RESOURCE = "reconciliations"


STATUS_LABELS = {1: "draft", 2: "completed"}


def format_status(value: object) -> str:
    """Human label for the engine's integer status. Shared by flat table + TUI."""
    if value is None:
        return "—"
    return STATUS_LABELS.get(value, str(value))


def format_period(item: dict) -> str:
    """`date_start → date_end`, both already calendar days on the wire (engine
    `5922bbf`). Shared by flat table + TUI."""
    ds = item.get("date_start") or ""
    de = item.get("date_end") or ""
    if ds and de:
        return f"{ds} → {de}"
    if ds:
        return f"{ds} → …"
    if de:
        return f"… → {de}"
    return "—"


def fetch_reconciliations(cfg, *, account_id: str, verbose: bool = False) -> dict:
    """GET /v1/reconciliations?account_id= → the raw engine body. Pure data.

    Shared by the flat `reconcile list` command and the TUI's Reconciliations
    screens. The engine lists one account at a time (since 2026-09-23): the
    account is required, the list comes back whole as `{items}` — no `limit`,
    no `offset`, no `total` — in period order, `date_start ASC NULLS LAST,
    created_at ASC`. There is no read by id; a row not in its account's list
    has been deleted.
    """
    return fetch_body(
        cfg,
        path=f"/{_RESOURCE}",
        params=query_params(account_id=account_id),
        verbose=verbose,
    )


_FIELD_LOCKED_HINT = (
    "Hint: this reconciliation is completed. "
    "Use 'expense reconcile revert <id> --yes' to unlock fields."
)
_DELETE_LOCKED_HINT = (
    "Hint: this reconciliation is completed and cannot be deleted. "
    "Use 'expense reconcile revert <id> --yes' first."
)
_COMPLETE_EMPTY_HINT = (
    "Hint: assign at least one transaction to this reconciliation before completing. "
    "Use 'expense transactions update <tx-id> --reconciliation-id <recon-id>'."
)
#: The three 422s `complete` can now answer with, and the two `create`/`update`
#: can. Matched on the engine's **message**, never on the `fields` key: the
#: empty-batch refusal and the unfiled-rows refusal both arrive under
#: `fields["transactions"]`, so the key cannot tell them apart. The substrings
#: below are quoted from app/helpers/reconciliations.py and periods.py.
_MISSING_DATE_HINT = (
    "Hint: both dates are required to complete — a completed period seals them, "
    "and a half-dated one seals nothing.\n"
    "  expense reconcile update {id} --date-end <YYYY-MM-DD>"
)
_UNASSIGNED_HINT_BARE = (
    "Hint: some rows inside this period are in no batch. Find them with "
    "'expense transactions list --account-id <id> --unreconciled "
    "--from <start> --to <end>'."
)
_INVERTED_HINT = "Hint: --date-end must not be earlier than --date-start."
_OVERLAP_HINT = (
    "Hint: a day belongs to exactly one statement. See the neighbours in "
    "statement order with 'expense reconcile list --account-id <id>'."
)


def _render_reconciliation_list(body: dict, *, json_mode: bool) -> None:
    if json_mode:
        emit_json(body)
        return
    items = items_of(body)
    if not items:
        typer.echo("(no reconciliations)")
        return

    account_names = load_account_name_map()
    rows = [
        {
            "account": resolve_name(item.get("account_id"), account_names),
            "name": item.get("name") or "(unnamed)",
            "period": format_period(item),
            "begin": format_cents(item.get("beginning_balance_cents")),
            # Both nullable since the engine's sql/040 — an ending balance the
            # user has not entered yet, and the add-up check that therefore has
            # no answer. `—` rather than `(null)`; `0.00` still means a real
            # entered zero, which is the distinction sql/040 exists to preserve.
            "end": format_cents_or_dash(item.get("ending_balance_cents")),
            "diff": format_cents_or_dash(item.get("difference_cents")),
            "status": format_status(item.get("status")),
            "id": item.get("id") or "—",
        }
        for item in items
    ]
    render_table(
        headers={
            "account": "Account",
            "name": "Name",
            "period": "Period",
            "begin": "Begin",
            "end": "End",
            "diff": "Diff",
            "status": "Status",
            "id": "Id",
        },
        rows=rows,
        align_right={"begin", "end", "diff"},
    )


def _complete_hint(id_: str, err: EngineError) -> str | None:
    """The recovery line for a refused `complete`, or None.

    Three refusals, and **two of them share a `fields` key** — the pre-existing
    "At least one transaction must be assigned." and the 2026-09-20
    "N transaction(s) dated inside this period are not assigned to any
    reconciliation." both arrive as `fields["transactions"]`. Only the message
    separates them, which is why this reads the haystack rather than the key.
    """
    if err.status != 422:
        return None
    haystack = error_haystack(err)
    if "unassigned" in haystack or "not assigned to any" in haystack:
        # The bare form, with placeholders: the refusal names neither the
        # account nor the window, and the read by id that used to fill them
        # in is gone from the engine (owner accepted the generic hint,
        # 2026-09-23). The unfiled pane is the real way to find these rows.
        return _UNASSIGNED_HINT_BARE
    if "without a period" in haystack or "required to complete" in haystack:
        return _MISSING_DATE_HINT.format(id=id_)
    if "transaction" in haystack and (
        "no " in haystack or "empty" in haystack or "at least" in haystack
    ):
        return _COMPLETE_EMPTY_HINT
    return None


def _period_hint(err: EngineError) -> str | None:
    """The recovery line for a refused `create`/`update` window, or None.

    Both rules arrived 2026-09-20, when completing a reconciliation started
    sealing its window and the dates stopped being labels.
    """
    if err.status != 422:
        return None
    haystack = error_haystack(err)
    if "overlaps another" in haystack:
        return _OVERLAP_HINT
    if "earlier than date_start" in haystack:
        return _INVERTED_HINT
    return None


def _is_field_locked_422(err: EngineError) -> bool:
    if err.status != 422 or not isinstance(err.fields, dict):
        return False
    return any(
        isinstance(message, str) and "locked" in message.lower() for message in err.fields.values()
    )


@app.command("list")
@handle_errors
def list_(
    ctx: typer.Context,
    account: str = typer.Option(
        ...,
        "--account-id",
        help="The account whose reconciliations to list (required: the engine lists "
        "one account at a time). Every one comes back, in period order.",
    ),
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/reconciliations?account_id=. One account's reconciliations, whole.

    A reconciliation's own rows are `expense transactions list --reconciliation-id <id>`.

    Example: expense reconcile list --account-id <account-id>
    """
    cfg = config_module.ensure_loaded()
    body = fetch_reconciliations(cfg, account_id=account, verbose=get_verbose(ctx))
    _render_reconciliation_list(body, json_mode=json_output)


@app.command("create")
@handle_errors
def create(
    ctx: typer.Context,
    account_id: str = typer.Option(..., "--account-id", help="Owning account UUID."),
    name: str = typer.Option(..., "--name", help="Human-readable label (e.g. 'April 2026')."),
    date_start: str = typer.Option(
        ...,
        "--date-start",
        help="Required — the statement's first day, YYYY-MM-DD; it orders the batch.",
    ),
    date_end: str = typer.Option(
        ...,
        "--date-end",
        help="Required — the statement's last day, YYYY-MM-DD.",
    ),
    beginning_balance: int = typer.Option(
        ...,
        "--beginning-balance",
        help="Required — signed cents, the statement's opening balance.",
    ),
    ending_balance: int | None = typer.Option(None, "--ending-balance", help="Signed cents."),
    json_output: bool = JSON_OPT,
) -> None:
    """POST /v1/reconciliations. Create a draft reconciliation batch.

    Both balances are typed off the statement — the engine deleted derived
    (chained) beginning balances on 2026-08-06, so `beginning_balance_cents` is
    required. `--date-start` is required too: it is what orders the batch.

    `--date-end` became required here on 2026-09-20, a caller-side choice: the
    engine still accepts a half-dated draft, but such a period can never be
    completed, because a completed reconciliation seals its window and a
    half-dated one has no window to seal. Asking for both dates up front means
    the refusal arrives while the statement is in front of you rather than at
    closing time.

    Both dates are calendar days and go to the engine as typed: no timezone is
    attached, and a malformed day is the engine's 422 on that field.

    Example: expense reconcile create --account-id <id> --name "April 2026"
             --date-start 2026-04-01 --date-end 2026-04-30
             --beginning-balance 958000 --ending-balance 946000
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    new_id = str(uuid4())
    payload: dict = {
        "id": new_id,
        "account_id": account_id,
        "name": name,
        "date_start": date_start,
        "date_end": date_end,
        "beginning_balance_cents": beginning_balance,
    }
    if ending_balance is not None:
        payload["ending_balance_cents"] = ending_balance

    with ExpenseClient(cfg, verbose=verbose) as client:
        try:
            body = client.post(f"/{_RESOURCE}", json_body=payload)
        except EngineError as err:
            hint = _period_hint(err)
            if hint is not None:
                typer.echo(hint, err=True)
            raise
    if not json_output:
        typer.echo(f"Created: {new_id}")
    render_record(body, json_mode=json_output, skip=("transactions",))
    if not json_output:
        typer.echo(
            "\nNext: attach transactions with "
            f"'expense transactions update <tx-id> --reconciliation-id {new_id}'"
        )


@app.command("update")
@handle_errors
def update(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    name: str | None = typer.Option(None, "--name"),
    date_start: str | None = typer.Option(
        None, "--date-start", help="The statement's first day, YYYY-MM-DD."
    ),
    date_end: str | None = typer.Option(
        None, "--date-end", help="The statement's last day, YYYY-MM-DD."
    ),
    beginning_balance: int | None = typer.Option(None, "--beginning-balance", help="Signed cents."),
    ending_balance: int | None = typer.Option(None, "--ending-balance"),
    json_output: bool = JSON_OPT,
) -> None:
    """PUT /v1/reconciliations/{id}. Partial update.

    `--date-start` is also how you reposition a batch: since the 2026-08-06
    de-chaining, an account's batches are ordered by their statement start date.

    Example: expense reconcile update <id> --name "March 2026" --ending-balance 12500
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    payload = build_update_payload(
        {
            "name": name,
            "date_start": date_start,
            "date_end": date_end,
            "beginning_balance_cents": beginning_balance,
            "ending_balance_cents": ending_balance,
        }
    )

    with ExpenseClient(cfg, verbose=verbose) as client:
        try:
            body = client.put(f"/{_RESOURCE}/{id_}", json_body=payload)
        except EngineError as err:
            if _is_field_locked_422(err):
                typer.echo(_FIELD_LOCKED_HINT, err=True)
            else:
                hint = _period_hint(err)
                if hint is not None:
                    typer.echo(hint, err=True)
            raise
    render_record(body, json_mode=json_output, skip=("transactions",))


@app.command("delete")
@handle_errors
def delete(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    yes: bool = YES_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """DELETE /v1/reconciliations/{id}. Soft-delete; cascade-unassigns attached transactions.

    Only allowed in draft. Completed reconciliations must be reverted first.

    Example: expense reconcile delete <id> --yes
    """
    run_delete(
        ctx,
        resource=_RESOURCE,
        id_=id_,
        confirm=(f"Delete reconciliation {id_}? This cascade-unassigns all attached transactions."),
        yes=yes,
        json_output=json_output,
        hints={409: _DELETE_LOCKED_HINT},
        skip=("transactions",),
    )


def _render_after_state_change(body: dict, *, lock_verb: str) -> None:
    render_record(body, json_mode=False, skip=("transactions",))
    transactions_total = body.get("transactions_total")
    if isinstance(transactions_total, int):
        typer.echo(f"\n{lock_verb} {transactions_total} transactions.")


@app.command("complete")
@handle_errors
def complete(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    json_output: bool = JSON_OPT,
) -> None:
    """POST /v1/reconciliations/{id}/complete.

    Locks amount_cents/account_id/title/date on every assigned transaction and
    locks the reconciliation's own balance/date fields. 422 if no transactions
    are assigned.

    Example: expense reconcile complete <id>
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    with ExpenseClient(cfg, verbose=verbose) as client:
        try:
            body = client.post(f"/{_RESOURCE}/{id_}/complete")
        except EngineError as err:
            hint = _complete_hint(id_, err)
            if hint is not None:
                typer.echo(hint, err=True)
            raise
    if json_output:
        emit_json(body)
    else:
        _render_after_state_change(body, lock_verb="Locked")
        # The gap report. `--json` needs no branch: the engine body goes
        # through verbatim and carries `warnings` with it.
        print_warnings(body)


@app.command("revert")
@handle_errors
def revert(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    yes: bool = YES_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """POST /v1/reconciliations/{id}/revert.

    Unlocks all assigned transactions and the reconciliation's own balance/date
    fields. A meaningful audit event — requires --yes.

    Example: expense reconcile revert <id> --yes
    """
    require_yes(
        yes,
        f"Revert reconciliation {id_}? This unlocks all assigned transactions "
        "and is a meaningful audit event.",
    )

    def _render(body: dict) -> None:
        _render_after_state_change(body, lock_verb="Unlocked")

    run_toggle(
        ctx,
        resource=_RESOURCE,
        id_=id_,
        verb="revert",
        json_output=json_output,
        render_human=_render,
    )
