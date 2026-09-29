from uuid import uuid4

import typer

from expense import config as config_module
from expense.commands._resource import (
    JSON_OPT,
    YES_OPT,
    build_update_payload,
    color_supported,
    color_swatch,
    fetch_body,
    format_bool,
    items_of,
    render_record,
    render_table,
    run_delete,
)
from expense.context import get_verbose
from expense.errors import handle_errors
from expense.http import ExpenseClient
from expense.jsonout import emit_json

app = typer.Typer(help="Categories.", no_args_is_help=True)

_RESOURCE = "categories"
SYSTEM_HINT = "System categories can be renamed but not deleted."


def _render_category_list(body: dict, *, json_mode: bool) -> None:
    if json_mode:
        emit_json(body)
        return
    items = items_of(body)
    if not items:
        typer.echo("(no categories)")
        return

    color = color_supported()
    rows = [
        {
            "name": item.get("name") or "(unnamed)",
            "color": color_swatch(item.get("color"), color=color),
            "system": format_bool(item.get("is_system")),
        }
        for item in items
    ]
    render_table(
        headers={
            "name": "Name",
            "color": "Color",
            "system": "System",
        },
        rows=rows,
    )


def fetch_categories(
    cfg,
    *,
    verbose: bool = False,
) -> dict:
    """GET /v1/categories → the raw engine body. Pure data, no render.

    Shared by the flat `categories list` command and the TUI's Categories screen.
    The engine returns every row as `{items}` and refuses `limit`/`offset`
    — there is no page to ask for.
    """
    return fetch_body(cfg, path=f"/{_RESOURCE}", params=None, verbose=verbose)


@app.command("list")
@handle_errors
def list_(
    ctx: typer.Context,
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/categories.

    Example: expense categories list
    """
    cfg = config_module.ensure_loaded()
    body = fetch_categories(cfg, verbose=get_verbose(ctx))
    _render_category_list(body, json_mode=json_output)


@app.command("get")
@handle_errors
def get(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/categories/{id}.

    Example: expense categories get <category-id>
    """
    cfg = config_module.ensure_loaded()
    body = fetch_body(
        cfg,
        path=f"/{_RESOURCE}/{id_}",
        params=None,
        verbose=get_verbose(ctx),
    )
    render_record(body, json_mode=json_output)


@app.command("create")
@handle_errors
def create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Category name (case-insensitive unique)."),
    color: str = typer.Option(..., "--color", help="6-digit hex color, e.g. #3b82f6. Required."),
    sort_order: int | None = typer.Option(None, "--sort-order"),
    json_output: bool = JSON_OPT,
) -> None:
    """POST /v1/categories.

    Example: expense categories create --name Food --color "#FF6B6B"
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    new_id = str(uuid4())
    payload: dict = {
        "id": new_id,
        "name": name,
        "color": color,
    }
    if sort_order is not None:
        payload["sort_order"] = sort_order

    with ExpenseClient(cfg, verbose=verbose) as client:
        body = client.post(f"/{_RESOURCE}", json_body=payload)
    if not json_output:
        typer.echo(f"Created: {new_id}")
    render_record(body, json_mode=json_output)


@app.command("update")
@handle_errors
def update(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    name: str | None = typer.Option(None, "--name"),
    color: str | None = typer.Option(None, "--color", help="6-digit hex color, e.g. #3b82f6."),
    sort_order: int | None = typer.Option(None, "--sort-order"),
    json_output: bool = JSON_OPT,
) -> None:
    """PUT /v1/categories/{id}. System categories CAN be renamed.

    Example: expense categories update <category-id> --name "Food & Drink"
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    payload = build_update_payload({"name": name, "color": color, "sort_order": sort_order})

    with ExpenseClient(cfg, verbose=verbose) as client:
        body = client.put(f"/{_RESOURCE}/{id_}", json_body=payload)
    render_record(body, json_mode=json_output)


@app.command("delete")
@handle_errors
def delete(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    yes: bool = YES_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """DELETE /v1/categories/{id}. Soft-delete, for cleanup/mistakes only.

    Example: expense categories delete <category-id> --yes
    """
    run_delete(
        ctx,
        resource=_RESOURCE,
        id_=id_,
        confirm=f"Delete category {id_}? This is for cleanup/mistakes only.",
        yes=yes,
        json_output=json_output,
        hints={
            403: f"Hint: {SYSTEM_HINT}",
            409: (
                "Hint: This category has transactions and cannot be deleted. "
                "Recategorize them first if you want to retire it."
            ),
        },
    )
