from uuid import uuid4

import typer

from expense import config as config_module
from expense.commands._resource import (
    JSON_OPT,
    LIMIT_OPT,
    OFFSET_OPT,
    YES_OPT,
    build_update_payload,
    effective_limit,
    fetch_body,
    items_of,
    query_params,
    render_pagination_hint,
    render_record,
    render_table,
    run_delete,
)
from expense.context import get_verbose
from expense.errors import handle_errors
from expense.http import ExpenseClient
from expense.jsonout import emit_json

app = typer.Typer(help="Hashtags.", no_args_is_help=True)

_RESOURCE = "hashtags"


def _render_hashtag_list(body: dict, *, json_mode: bool) -> None:
    if json_mode:
        emit_json(body)
        return
    items = items_of(body)
    if not items:
        typer.echo("(no hashtags)")
        return

    rows = [
        {
            "name": item.get("name") or "(unnamed)",
        }
        for item in items
    ]
    render_table(
        headers={
            "name": "Name",
        },
        rows=rows,
    )
    render_pagination_hint(body, items)


def fetch_hashtags(
    cfg,
    *,
    limit: int | None = None,
    offset: int | None = None,
    verbose: bool = False,
) -> dict:
    """GET /v1/hashtags → the raw engine body. Pure data, no render.

    Shared by the flat `hashtags list` command and the TUI's Hashtags screen.
    """
    params = query_params(limit=limit, offset=offset)
    return fetch_body(
        cfg,
        path=f"/{_RESOURCE}",
        params=params,
        verbose=verbose,
    )


@app.command("list")
@handle_errors
def list_(
    ctx: typer.Context,
    limit: int | None = LIMIT_OPT,
    offset: int | None = OFFSET_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/hashtags.

    Example: expense hashtags list
    """
    cfg = config_module.ensure_loaded()
    limit = effective_limit(limit, json_mode=json_output)
    body = fetch_hashtags(
        cfg,
        limit=limit,
        offset=offset,
        verbose=get_verbose(ctx),
    )
    _render_hashtag_list(body, json_mode=json_output)


@app.command("get")
@handle_errors
def get(
    ctx: typer.Context,
    id_: str = typer.Argument(..., metavar="ID"),
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/hashtags/{id}.

    Example: expense hashtags get <hashtag-id>
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
    name: str = typer.Option(..., "--name", help="Hashtag name (case-insensitive unique)."),
    sort_order: int | None = typer.Option(None, "--sort-order"),
    json_output: bool = JSON_OPT,
) -> None:
    """POST /v1/hashtags. Hashtags are NOT auto-created on transaction use.

    Example: expense hashtags create --name lunch
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    new_id = str(uuid4())
    payload: dict = {"id": new_id, "name": name}
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
    sort_order: int | None = typer.Option(None, "--sort-order"),
    json_output: bool = JSON_OPT,
) -> None:
    """PUT /v1/hashtags/{id}.

    Example: expense hashtags update <hashtag-id> --name lunch-work
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    payload = build_update_payload({"name": name, "sort_order": sort_order})

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
    """DELETE /v1/hashtags/{id}. Cascades soft-delete to junction rows; a delete cannot be undone.

    Example: expense hashtags delete <hashtag-id> --yes
    """
    run_delete(
        ctx,
        resource=_RESOURCE,
        id_=id_,
        confirm=(
            f"Delete hashtag {id_}? Junction rows on transactions will be cascaded "
            "(a delete cannot be undone)."
        ),
        yes=yes,
        json_output=json_output,
    )
