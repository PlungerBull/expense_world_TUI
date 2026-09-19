from dataclasses import dataclass, field

import typer

from expense import config as config_module
from expense.commands._resource import (
    JSON_OPT,
    LIMIT_OPT,
    OFFSET_OPT,
    effective_limit,
    fetch_body,
    items_of,
    load_account_name_map,
    load_category_name_map,
    load_hashtag_name_map,
    query_params,
    render_pagination_hint,
    render_table,
)
from expense.context import get_verbose
from expense.errors import EngineError, handle_errors
from expense.http import ExpenseClient
from expense.jsonout import emit_json

app = typer.Typer(help="Activity log (audit trail).", no_args_is_help=True)

_RESOURCE = "activity"

_ACTION_NAMES = {1: "CREATED", 2: "UPDATED", 3: "DELETED", 4: "RESTORED"}


def _action_label(action: object) -> str:
    if isinstance(action, int) and action in _ACTION_NAMES:
        return _ACTION_NAMES[action]
    return str(action)


def _split_date_time(created_at: object) -> tuple[str, str]:
    if not isinstance(created_at, str) or len(created_at) < 19:
        return "—", "—"
    return created_at[:10], created_at[11:19]


def _short_id(resource_id: object) -> str:
    if not isinstance(resource_id, str) or not resource_id:
        return "—"
    return resource_id[:8]


# The engine writes activity `resource_type` in the singular ("transaction",
# "account", …). Map both the engine's actual strings and the older plural
# guesses to the resource's collection path so name resolution is robust to
# either.
_RESOURCE_PATH = {
    "transaction": "transactions",
    "expense_transactions": "transactions",
    "account": "accounts",
    "accounts": "accounts",
    "category": "categories",
    "categories": "categories",
    "hashtag": "hashtags",
    "hashtags": "hashtags",
    "reconciliation": "reconciliations",
    "reconciliations": "reconciliations",
}


@dataclass(frozen=True)
class NameMaps:
    """Id → name for the three reference lists an activity page keeps naming.

    A page of activity is mostly rows about accounts, categories and hashtags,
    and resolving each one alone costs a live `GET /<kind>/<id>` — two for a
    reconciliation, which also reads its account. The three whole lists are
    small and bounded, so reading them once per page costs three engine reads
    instead of one-to-two per row.

    Not a general cache: transactions and reconciliations have no listing
    cheap enough to preload and still resolve one read at a time, and an id
    missing from a map (a row deleted since, a list that failed to load) falls
    through to that same per-row read. Every map is independently
    failure-silent — an empty one costs speed, never correctness.
    """

    accounts: dict[str, str] = field(default_factory=dict)
    categories: dict[str, str] = field(default_factory=dict)
    hashtags: dict[str, str] = field(default_factory=dict)

    def lookup(self, path: str, resource_id: str) -> str | None:
        """The display name for one id, or None to fall through to the engine."""
        table = {
            "accounts": self.accounts,
            "categories": self.categories,
            "hashtags": self.hashtags,
        }.get(path)
        if table is None:
            return None
        name = table.get(resource_id)
        if name is None:
            return None
        return f"#{name}" if path == "hashtags" else name


def load_name_maps() -> NameMaps:
    """The three maps, read once — build this before rendering a page of rows.

    Failure-silent by construction (`_load_name_map` returns `{}` on anything
    going wrong), so a caller never has to guard it.
    """
    return NameMaps(
        accounts=load_account_name_map(),
        categories=load_category_name_map(),
        hashtags=load_hashtag_name_map(),
    )


def _display_name(
    path: str,
    row: dict,
    resource_id: str,
    client: ExpenseClient,
    names: NameMaps | None = None,
) -> str:
    """The human handle for one fetched row, per resource kind."""
    if path == "transactions":
        return row.get("title") or row.get("description") or _short_id(resource_id)
    if path == "hashtags":
        name = row.get("name")
        return f"#{name}" if name else _short_id(resource_id)
    if path == "reconciliations":
        date = row.get("statement_date") or row.get("date")
        account_id = row.get("account_id")
        account_name = None
        if isinstance(account_id, str):
            # The batch's account comes from the preloaded map when there is
            # one — this is the second of the two reads a reconciliation row
            # used to cost.
            account_name = names.accounts.get(account_id) if names else None
        if account_name is None and isinstance(account_id, str):
            try:
                account_name = client.get(f"/accounts/{account_id}").get("name")
            except EngineError:
                account_name = None
        if isinstance(date, str) and account_name:
            return f"{date[:10]} / {account_name}"
        if isinstance(date, str):
            return date[:10]
        if account_name:
            return account_name
        return _short_id(resource_id)
    return row.get("name") or _short_id(resource_id)


def _resolve_resource_name(
    resource_type: object,
    resource_id: object,
    client: ExpenseClient,
    names: NameMaps | None = None,
) -> str:
    """Look up a human name for the row: the preloaded maps first, then a live
    engine read.

    Returns the short 8-char UUID prefix on any miss / error so deleted
    records still have a usable handle.
    """
    if not isinstance(resource_id, str) or not resource_id:
        return "—"
    if not isinstance(resource_type, str):
        return _short_id(resource_id)
    path = _RESOURCE_PATH.get(resource_type)
    if path is None:
        return _short_id(resource_id)
    if names is not None:
        hit = names.lookup(path, resource_id)
        if hit is not None:
            return hit
    try:
        row = client.get(f"/{path}/{resource_id}")
    except EngineError:
        return _short_id(resource_id)
    except Exception:
        return _short_id(resource_id)
    if not isinstance(row, dict):
        return _short_id(resource_id)
    try:
        return _display_name(path, row, resource_id, client, names)
    except Exception:
        return _short_id(resource_id)


def activity_display_cells(
    item: dict, client: ExpenseClient, names: NameMaps | None = None
) -> list[str]:
    """The 6 human cells for one activity row: date, time, action, actor, type, resource.

    Shared by the CLI table renderer and the TUI Activity list screen so both
    resolve resource names and map action codes identically. `client` is an
    open engine client — callers rendering many rows share one connection.

    `names` is `load_name_maps()`, built ONCE per page: pass it and an account,
    category or hashtag row costs no engine read at all. Omitting it is
    correct but slow, and is what the per-row unit tests do.
    """
    date_part, time_part = _split_date_time(item.get("created_at"))
    return [
        date_part,
        time_part,
        _action_label(item.get("action")),
        str(item.get("actor_type") or "—"),
        str(item.get("resource_type") or "—"),
        _resolve_resource_name(item.get("resource_type"), item.get("resource_id"), client, names),
    ]


def _render_activity_rows(
    items: list[dict], client: ExpenseClient, names: NameMaps | None = None
) -> None:
    """Render activity rows as a 6-column table (Date · Time · Action · Actor · Type · Resource).

    Module-level so alternate front doors (e.g. the TUI) can reuse it. Snapshots
    and `changed_by` are deliberately omitted from the table; both remain
    accessible via --json.
    """
    keys = ("date", "time", "action", "actor", "type", "resource")
    rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(dict(zip(keys, activity_display_cells(item, client, names), strict=True)))
    render_table(
        headers={
            "date": "Date",
            "time": "Time",
            "action": "Action",
            "actor": "Actor",
            "type": "Type",
            "resource": "Resource",
        },
        rows=rows,
    )


def _render_list(body: object, *, json_mode: bool, cfg, verbose: bool) -> None:
    if json_mode:
        emit_json(body)
        return
    items = items_of(body)
    if not items:
        typer.echo("(no activity)")
        return
    names = load_name_maps()  # three reads for the page, not one or two per row
    with ExpenseClient(cfg, verbose=verbose) as client:
        _render_activity_rows(items, client, names)
    render_pagination_hint(body, items)


def fetch_activity(
    cfg,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    verbose: bool = False,
) -> dict:
    """GET /v1/activity (engine-direct). Returns the raw response body.

    Extracted so the TUI Activity screen and the typer command share one
    fetch path — the CLI thin-wrapper rule (no logic duplicated in the TUI).
    """
    params = query_params(
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
        offset=offset,
    )

    return fetch_body(cfg, path=f"/{_RESOURCE}", params=params, verbose=verbose)


@app.command("list")
@handle_errors
def list_(
    ctx: typer.Context,
    resource_type: str | None = typer.Option(
        None,
        "--resource-type",
        help="Filter by resource_type (e.g. transaction).",
    ),
    resource_id: str | None = typer.Option(
        None,
        "--resource-id",
        help="Filter by resource_id (UUID; engine validates).",
    ),
    limit: int | None = LIMIT_OPT,
    offset: int | None = OFFSET_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/activity. Engine-direct (not cached).

    Snapshots are omitted from the human renderer; pass --json to see
    before_snapshot / after_snapshot.

    Example: expense activity list --resource-type transaction --limit 5
    """
    cfg = config_module.ensure_loaded()
    limit = effective_limit(limit, json_mode=json_output)
    body = fetch_activity(
        cfg,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
        offset=offset,
        verbose=get_verbose(ctx),
    )
    _render_list(body, json_mode=json_output, cfg=cfg, verbose=get_verbose(ctx))
