import json
import sys
from uuid import uuid4

import typer

from expense import config as config_module
from expense.commands._resource import (
    INCLUDE_DELETED_OPT,
    JSON_OPT,
    LIMIT_OPT,
    OFFSET_OPT,
    YES_OPT,
    build_update_payload,
    effective_limit,
    fetch_body,
    format_bool,
    format_cents,
    format_hashtag_cell,
    format_short_date,
    items_of,
    load_account_name_map,
    load_category_name_map,
    load_hashtag_name_map,
    parse_hashtag_ids,
    print_warnings,
    query_params,
    render_pagination_hint,
    render_record,
    render_table,
    resolve_name,
    run_delete,
    truncate,
)
from expense.context import get_verbose
from expense.dates import to_canonical_aware
from expense.errors import EngineError, error_haystack, handle_errors
from expense.http import ExpenseClient
from expense.jsonout import emit_json

app = typer.Typer(
    help="Ledger transactions: list, view, edit, delete, restore, batch.",
    no_args_is_help=True,
)

_RESOURCE = "transactions"

_RECONCILIATION_LOCK_HINT = (
    "Hint: This transaction is in a completed reconciliation. "
    "amount_cents/account_id/title/date/reconciliation_id are read-only — "
    "revert the reconciliation to draft first ('expense reconcile revert <id>')."
)


def _render_transaction_list(body: dict, *, json_mode: bool, show_deleted: bool = False) -> None:
    """Print the ledger table.

    `show_deleted` mirrors the caller's `--include-deleted`, not the data: the
    column is what explains why a deleted row is in the table at all, and its
    only real use is picking the id to hand to `transactions restore`. Keying it
    to the flag rather than to "is anything actually deleted" keeps the column
    set stable for a given command line — the same invocation always prints the
    same header, whatever the ledger happens to hold that day.
    """
    if json_mode:
        emit_json(body)
        return
    items = items_of(body)
    if not items:
        typer.echo("(no transactions)")
        return

    accounts = load_account_name_map()
    categories = load_category_name_map()
    hashtags = load_hashtag_name_map()
    rows = [
        {
            "title": truncate(item.get("title") or "—", 24),
            "description": truncate(item.get("description"), 24),
            "amount": format_cents(item.get("amount_cents")),
            "date": format_short_date(item.get("date")),
            "account": resolve_name(item.get("account_id"), accounts),
            "category": resolve_name(item.get("category_id"), categories),
            "hashtags": format_hashtag_cell(item.get("hashtag_ids"), hashtags, max_width=24),
            **({"deleted": format_bool(item.get("deleted_at"))} if show_deleted else {}),
        }
        for item in items
    ]
    headers = {
        "title": "Title",
        "description": "Description",
        "amount": "Amount",
        "date": "Date",
        "account": "Account",
        "category": "Category",
        "hashtags": "Hashtags",
    }
    if show_deleted:
        # Last, matching accounts/categories/hashtags.
        headers["deleted"] = "Deleted"
    render_table(
        headers=headers,
        rows=rows,
        align_right={"amount"},
    )
    render_pagination_hint(body, items)


def _update_hint_for(err: EngineError) -> str | None:
    haystack = error_haystack(err)
    if "reconciliation" in haystack and (
        "complete" in haystack or "lock" in haystack or "read-only" in haystack
    ):
        return _RECONCILIATION_LOCK_HINT
    return None


def _filter_params(
    *,
    account: str | None,
    category: str | None,
    hashtag: str | None,
    reconciliation: str | None,
    unreconciled: bool,
    date_from: str | None,
    date_to: str | None,
    search: str | None,
) -> dict:
    """The filters `GET /transactions` and `/transactions/count` share — one copy.

    The engine declares them once for both endpoints, so the list and its count
    describe the same rows by construction; this mirrors that. Filters only:
    paging, `sort` and `debit_as_negative` are the list's own, and the count
    422s on any parameter it does not declare.
    """
    return query_params(
        account_id=account,
        category_id=category,
        hashtag_id=hashtag,
        reconciliation_id=reconciliation,
        unreconciled=unreconciled,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )


def fetch_transactions(
    cfg,
    *,
    account: str | None = None,
    category: str | None = None,
    hashtag: str | None = None,
    reconciliation: str | None = None,
    unreconciled: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    sort: str | None = None,
    after: str | None = None,
    limit: int | None = None,
    verbose: bool = False,
) -> dict:
    """GET /v1/transactions → the raw engine body. Pure data, no render.

    Cursor-paged: pass the previous page's `next_cursor` as `after`; `null`
    means the last page. There is no `offset` and no `total` — the count is
    `count_transactions`. A cursor belongs to one filter + sort, so a caller
    that changes either starts again from `after=None`.

    Shared by the flat `transactions list` command and the TUI screens.
    """
    params = {
        **_filter_params(
            account=account,
            category=category,
            hashtag=hashtag,
            reconciliation=reconciliation,
            unreconciled=unreconciled,
            date_from=date_from,
            date_to=date_to,
            search=search,
        ),
        **query_params(
            sort=sort,
            after=after,
            limit=limit,
            # Always signed: every CLI/TUI surface renders debits negative, so the
            # request pins the flag rather than depending on the engine default.
            debit_as_negative=True,
        ),
    }
    return fetch_body(
        cfg,
        path=f"/{_RESOURCE}",
        params=params,
        verbose=verbose,
    )


def count_transactions(
    cfg,
    *,
    account: str | None = None,
    category: str | None = None,
    hashtag: str | None = None,
    reconciliation: str | None = None,
    unreconciled: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    verbose: bool = False,
) -> int:
    """GET /v1/transactions/count → how many rows the same filters match.

    Raises when the body carries no int `count`. A count that falls back to a
    guess (`len(items)`) is how two panes showed "1 to file" over 1,716 rows
    with no error; a pane that cannot get the number fails instead.
    """
    body = fetch_body(
        cfg,
        path=f"/{_RESOURCE}/count",
        params=_filter_params(
            account=account,
            category=category,
            hashtag=hashtag,
            reconciliation=reconciliation,
            unreconciled=unreconciled,
            date_from=date_from,
            date_to=date_to,
            search=search,
        ),
        verbose=verbose,
    )
    count = body.get("count") if isinstance(body, dict) else None
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError(f"GET /transactions/count answered without a count: {body!r}")
    return count


@app.command("list")
@handle_errors
def list_(
    ctx: typer.Context,
    account: str | None = typer.Option(None, "--account-id", help="Filter by account_id."),
    category: str | None = typer.Option(None, "--category-id", help="Filter by category_id."),
    hashtag: str | None = typer.Option(None, "--hashtag-id", help="Filter by hashtag_id."),
    reconciliation: str | None = typer.Option(
        None, "--reconciliation-id", help="Filter by reconciliation_id."
    ),
    unreconciled: bool = typer.Option(
        False,
        "--unreconciled",
        help="Only transactions assigned to no reconciliation. "
        "Over a reconciled period, these are the rows the statement never accounted for.",
    ),
    date_from: str | None = typer.Option(None, "--from", help="ISO 8601 lower bound (inclusive)."),
    date_to: str | None = typer.Option(None, "--to", help="ISO 8601 upper bound (inclusive)."),
    search: str | None = typer.Option(
        None, "--search", help="Full-text search on title/description."
    ),
    limit: int | None = LIMIT_OPT,
    offset: int | None = OFFSET_OPT,
    include_deleted: bool = INCLUDE_DELETED_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/transactions.

    Example: expense transactions list --account-id <id> --from 2026-04-01 --to 2026-04-30

    Run after every import, over the period you last reconciled:

        expense transactions list --account-id <id> --from 2026-08-01 --to 2026-08-31 --unreconciled

    Empty means the period holds nothing the statement did not account for. Rows
    mean look — a re-import after a mid-sheet edit lands duplicates here, and a
    completed reconciliation cannot see them (docs/decisions.md, "Importer ids
    are positional").
    """
    cfg = config_module.ensure_loaded()
    limit = effective_limit(limit, json_mode=json_output)
    body = fetch_transactions(
        cfg,
        account=account,
        category=category,
        hashtag=hashtag,
        reconciliation=reconciliation,
        unreconciled=unreconciled,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
        verbose=get_verbose(ctx),
    )
    _render_transaction_list(body, json_mode=json_output, show_deleted=include_deleted)


@app.command("get")
@handle_errors
def get(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/transactions/{id}.

    See a transaction's activity history via
    'expense activity list --resource-type transaction --resource-id <id>'.

    Example: expense transactions get <transaction-id>
    """
    cfg = config_module.ensure_loaded()
    body = fetch_body(
        cfg,
        path=f"/{_RESOURCE}/{id_}",
        params={"debit_as_negative": "true"},
        verbose=get_verbose(ctx),
    )
    render_record(body, json_mode=json_output)


@app.command("update")
@handle_errors
def update(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    title: str | None = typer.Option(None, "--title"),
    amount: int | None = typer.Option(None, "--amount", help="Signed cents."),
    date: str | None = typer.Option(None, "--date"),
    account_id: str | None = typer.Option(None, "--account-id"),
    category_id: str | None = typer.Option(None, "--category-id"),
    description: str | None = typer.Option(None, "--description"),
    hashtag_ids: str | None = typer.Option(
        None, "--hashtag-ids", help="Comma-separated list; replaces the existing set."
    ),
    reconciliation_id: str | None = typer.Option(None, "--reconciliation-id"),
    json_output: bool = JSON_OPT,
) -> None:
    """PUT /v1/transactions/{id}. Partial update.

    Example: expense transactions update <transaction-id> --title "Renamed"
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    payload = build_update_payload(
        {
            "title": title,
            "amount_cents": amount,
            "date": to_canonical_aware(date) if date is not None else None,
            "account_id": account_id,
            "category_id": category_id,
            "description": description,
            "hashtag_ids": parse_hashtag_ids(hashtag_ids) if hashtag_ids is not None else None,
            "reconciliation_id": reconciliation_id,
        }
    )

    with ExpenseClient(cfg, verbose=verbose) as client:
        try:
            body = client.put(f"/{_RESOURCE}/{id_}", json_body=payload)
        except EngineError as err:
            if err.status == 422:
                hint = _update_hint_for(err)
                if hint is not None:
                    typer.echo(hint, err=True)
            raise
    render_record(body, json_mode=json_output)


@app.command("delete")
@handle_errors
def delete(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    yes: bool = YES_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """DELETE /v1/transactions/{id}. Soft-delete.

    Example: expense transactions delete <transaction-id> --yes
    """
    run_delete(
        ctx,
        resource=_RESOURCE,
        id_=id_,
        confirm=f"Delete transaction {id_}?",
        yes=yes,
        json_output=json_output,
        hints={
            409: (
                "Hint: This transaction is assigned to a completed reconciliation "
                "and cannot be deleted — revert the reconciliation to draft first "
                "('expense reconcile revert <id>')."
            )
        },
    )


@app.command("restore")
@handle_errors
def restore(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    json_output: bool = JSON_OPT,
) -> None:
    """POST /v1/transactions/{id}/restore.

    Re-applies the balance impact.

    Example: expense transactions restore <transaction-id>
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    with ExpenseClient(cfg, verbose=verbose) as client:
        try:
            body = client.post(f"/{_RESOURCE}/{id_}/restore")
        except EngineError as err:
            if err.status == 422:
                typer.echo(
                    "Hint: An account, category, or hashtag referenced by this transaction "
                    "is no longer active. Unarchive or restore the offending row, then retry.",
                    err=True,
                )
            raise
    render_record(body, json_mode=json_output)
    if not json_output:
        print_warnings(body)


@app.command("batch")
@handle_errors
def batch(
    ctx: typer.Context,
    file: str | None = typer.Option(
        None, "--file", help="Path to a JSON array of transactions. Defaults to stdin."
    ),
    json_output: bool = JSON_OPT,
) -> None:
    """POST /v1/transactions/batch. Atomic multi-create.

    Example: cat transactions.json | expense transactions batch
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    if file is not None:
        with open(file, encoding="utf-8") as handle:
            raw = handle.read()
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        typer.echo("Error: No input. Pipe a JSON array to stdin or pass --file.", err=True)
        raise typer.Exit(code=1)

    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"Error: Invalid JSON input: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not isinstance(items, list) or not items:
        typer.echo("Error: Input must be a non-empty JSON array of transaction objects.", err=True)
        raise typer.Exit(code=1)

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            typer.echo(f"Error: items[{index}] is not an object.", err=True)
            raise typer.Exit(code=1)
        if "id" not in item:
            item["id"] = str(uuid4())

    with ExpenseClient(cfg, verbose=verbose) as client:
        body = client.post(f"/{_RESOURCE}/batch", json_body={"transactions": items})
    if json_output:
        emit_json(body)
        return

    created_items = body.get("created", []) if isinstance(body, dict) else []
    for item in created_items:
        if isinstance(item, dict) and "id" in item:
            typer.echo(f"Created: {item['id']}")
    count = len(created_items)
    typer.echo(f"Created {count} transaction{'s' if count != 1 else ''}.")


__all__ = ["app"]
