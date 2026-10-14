import typer

from expense import config as config_module
from expense import reads
from expense.commands._resource import (
    JSON_OPT,
    LIMIT_OPT,
    effective_limit,
    render_pagination_hint,
    render_table,
)
from expense.context import get_verbose
from expense.currencies import RATE_SCALE
from expense.errors import handle_errors
from expense.jsonout import emit_json
from expense.reads import fetch_body, items_of, query_params

app = typer.Typer(help="Exchange rates.", no_args_is_help=True)


# Display precision, in decimal places. The engine stores 8 (RATE_SCALE); the
# display shows 4, which is where a USD/PEN rate stops being meaningful
# to read. Kept separate from RATE_SCALE because they answer different
# questions — one is storage fidelity, the other is how much of it is worth
# rendering.
_RATE_DISPLAY_PLACES = 4
_RATE_DISPLAY_DIVISOR = RATE_SCALE // (10**_RATE_DISPLAY_PLACES)


def format_rate(value: object) -> str:
    """4-decimal display for the engine's `rate_e8` integers: 335187273 → `3.3519`.

    Integer arithmetic throughout — no float division — matching
    `formatting.format_cents`. The engine's wire field is `rate_e8: int`, the rate
    × 10^8 (contract: GET /v1/exchange-rates), so there is nothing to convert
    from and nothing to lose here: the halving-and-rounding happens on integers
    and the result is assembled as text.

    The engine never stores a non-positive rate (contract: "Rate ingestion:
    implausible rates are refused, not stored"), so no sign handling. A non-int
    value is echoed rather than guessed at — including a float, which breaks the
    contract and should be visible, not quietly formatted as if nothing were
    wrong.
    """
    if value is None:
        return "—"
    if isinstance(value, bool) or not isinstance(value, int):
        return str(value)
    # Round half-up to the display places, then split. `+ divisor // 2` is the
    # half-up step; it is exact because both operands are integers.
    units = (value + _RATE_DISPLAY_DIVISOR // 2) // _RATE_DISPLAY_DIVISOR
    whole, frac = divmod(units, 10**_RATE_DISPLAY_PLACES)
    return f"{whole}.{frac:0{_RATE_DISPLAY_PLACES}d}"


def _render_rate(body: object) -> None:
    """Human-mode renderer for /v1/exchange-rates responses.

    Generic key/value iteration so additional engine fields (provider,
    source, fetched_at, …) render without a code change.

    `rate_e8` is the one key that gets special handling, because it is the one
    key whose raw form is unreadable: the engine sends the rate x RATE_SCALE
    (contract: GET /v1/exchange-rates), so generic echo would print
    `rate_e8: 335187273`. It renders as
    `rate: 3.3519`. `--json` is unaffected and still shows the raw integer.
    """
    if isinstance(body, dict):
        for key, value in body.items():
            if key == "rate_e8":
                typer.echo(f"  rate: {format_rate(value)}")
                continue
            display = value if value is not None else "(null)"
            typer.echo(f"  {key}: {display}")
    else:
        emit_json(body)


def fetch_rates_history(
    cfg,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    after: str | None = None,
    limit: int | None = None,
    verbose: bool = False,
) -> dict:
    """GET /v1/exchange-rates/history (engine-direct). Raw response body.

    Stored daily rates, newest first (`rate_date DESC, base, target`), one row
    per pair per day, inside one date window (contract: "Date windows"): plain ISO
    days, both inclusive; omitted bounds are the engine's (today in the user's
    zone, and 30 days before). One day is `date_from == date_to`.
    """
    params = query_params(date_from=date_from, date_to=date_to, after=after, limit=limit)

    return fetch_body(cfg, path="/exchange-rates/history", params=params, verbose=verbose)


@app.command("list")
@handle_errors
def list_(
    ctx: typer.Context,
    date: str | None = typer.Option(
        None,
        "--date",
        help="One day (YYYY-MM-DD). Same as --from X --to X; not with either.",
    ),
    date_from: str | None = typer.Option(
        None,
        "--from",
        help="Window start day (YYYY-MM-DD, inclusive). Default: 30 days before --to.",
    ),
    date_to: str | None = typer.Option(
        None,
        "--to",
        help="Window end day (YYYY-MM-DD, inclusive). Default: today. At most 366 days wide.",
    ),
    after: str | None = typer.Option(
        None,
        "--after",
        help="The next_cursor from the previous page; repeat the same window.",
    ),
    limit: int | None = LIMIT_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/exchange-rates/history. Engine-direct (not cached).

    Stored daily rates, newest first, one row per currency pair per day. Reads
    one date window: the last 30 days unless --date or --from / --to say
    otherwise. The line under the table names the cursor for the rest of the
    window, or the --to that reaches further back.

    Example: expense rates list --date 2026-07-04
    """
    if date is not None:
        if date_from is not None or date_to is not None:
            raise typer.BadParameter(
                "--date is one day; use it alone, or --from / --to for a range.",
                param_hint="--date",
            )
        date_from = date_to = date
    cfg = config_module.ensure_loaded()
    limit = effective_limit(limit, json_mode=json_output)
    body = fetch_rates_history(
        cfg,
        date_from=date_from,
        date_to=date_to,
        after=after,
        limit=limit,
        verbose=get_verbose(ctx),
    )
    if json_output:
        emit_json(body)
        return
    items = items_of(body)
    if not items:
        typer.echo("(no rates in this window)")
    else:
        render_table(
            {"rate_date": "Date", "base": "Base", "target": "Target", "rate": "Rate"},
            [
                {
                    "rate_date": str(it.get("rate_date") or "—"),
                    "base": str(it.get("base") or "—"),
                    "target": str(it.get("target") or "—"),
                    "rate": format_rate(it.get("rate_e8")),
                }
                for it in items
            ],
            align_right={"rate"},
        )
    render_pagination_hint(body, note="newest first", older="day_before")


@app.command("get")
@handle_errors
def get(
    ctx: typer.Context,
    target: str = typer.Option(..., "--target", help="Target currency code (e.g. EUR)."),
    base: str | None = typer.Option(
        None,
        "--base",
        help="Base currency code. Engine default is USD.",
    ),
    date: str | None = typer.Option(
        None,
        "--date",
        help=(
            "ISO date (YYYY-MM-DD). Engine defaults to today; falls back to "
            "the most recent prior rate."
        ),
    ),
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/exchange-rates. Engine-direct (not cached).

    Example: expense rates get --target EUR --date 2026-04-01
    """
    cfg = config_module.ensure_loaded()
    body = reads.fetch_rate(cfg, target=target, base=base, date=date, verbose=get_verbose(ctx))

    if json_output:
        emit_json(body)
        return
    _render_rate(body)
