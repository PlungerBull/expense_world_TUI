import typer

from expense import config as config_module
from expense.commands._resource import (
    JSON_OPT,
    fetch_body,
    format_cents,
    format_month,
    query_params,
    render_category_table,
    render_table,
    render_totals,
    settled_label,
    split_settled,
)
from expense.context import get_verbose
from expense.errors import handle_errors
from expense.jsonout import emit_json


def _render_account_table(items: list[dict] | None, *, empty_message: str) -> None:
    """Render a list of accounts (bank or people) as Name / Currency / Balance.

    Balance is the native amount in the account's currency; the home-currency
    equivalent is intentionally not shown — single-currency users see only one
    meaningful number, and multi-currency users get the value in the unit they
    actually think in for that account.
    """
    if not items:
        typer.echo(empty_message)
        return
    rows = [
        {
            "name": item.get("name") or "(unnamed)",
            "currency": item.get("currency_code") or "?",
            "balance": format_cents(item.get("current_balance_cents")),
        }
        for item in items
    ]
    render_table(
        headers={"name": "Name", "currency": "Currency", "balance": "Balance"},
        rows=rows,
        align_right={"balance"},
    )


def _render_people(people: list[dict] | None) -> None:
    """The People panel: everyone still owing or owed, then `▸ 3 settled`.

    A settled person (balance exactly `0` in their own currency) is **folded, not
    dropped** — Why: docs/decisions.md "A settled person is folded, never hidden".
    A printed page cannot be unfolded; `expense accounts list --include-people`
    names them.

    The panel is skipped entirely only when there are no people at all, matching
    the pre-existing behaviour for an empty list.
    """
    if not people:
        return
    outstanding, settled = split_settled(people)
    typer.echo("People:")
    if outstanding:
        _render_account_table(outstanding, empty_message="  (no people)")
    if settled:
        typer.echo(settled_label(len(settled)))
    typer.echo("")


def _render_dashboard(body: dict, *, json_mode: bool) -> None:
    if json_mode:
        emit_json(body)
        return

    typer.echo(f"Month: {format_month(body.get('month'))}")
    typer.echo("")

    typer.echo("Bank accounts:")
    _render_account_table(body.get("bank_accounts"), empty_message="  (no bank accounts)")
    typer.echo("")

    _render_people(body.get("people"))

    render_category_table(body.get("categories"))
    typer.echo("")

    render_totals(body.get("totals"))

    # An archived *account* still holds real money, so it keeps a panel.
    archived_accounts = body.get("archived_accounts")
    if archived_accounts is not None:
        typer.echo("")
        typer.echo("Archived accounts:")
        _render_account_table(archived_accounts, empty_message="  (no archived accounts)")

    # `archived_people` is its own panel after `archived_accounts`, and is not
    # folded — Why: docs/decisions.md "A settled person is folded, never hidden".
    archived_people = body.get("archived_people")
    if archived_people is not None:
        typer.echo("")
        typer.echo("Archived people:")
        _render_account_table(archived_people, empty_message="  (no archived people)")


def fetch_dashboard(
    cfg,
    *,
    include_archived: bool = False,
    verbose: bool = False,
) -> dict:
    """GET /v1/dashboard → the raw engine body. Pure data, no rendering.

    Split from the rendering so the flat command and the TUI share one fetch.
    """
    params = query_params(include_archived=include_archived)

    return fetch_body(cfg, path="/dashboard", params=params, verbose=verbose)


@handle_errors
def dashboard(
    ctx: typer.Context,
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Add the archived-accounts and archived-people panels.",
    ),
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/dashboard. Current month overview: balances, categories, totals.

    Example: expense dashboard --include-archived
    """
    cfg = config_module.ensure_loaded()
    body = fetch_dashboard(
        cfg,
        include_archived=include_archived,
        verbose=get_verbose(ctx),
    )
    _render_dashboard(body, json_mode=json_output)
