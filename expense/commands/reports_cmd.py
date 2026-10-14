import typer

from expense import config as config_module
from expense import reads
from expense.commands._resource import JSON_OPT, render_category_table, render_table, render_totals
from expense.context import get_verbose
from expense.dates import parse_year_month
from expense.errors import handle_errors
from expense.formatting import (
    NO_ACTIVITY_MARK,
    TOTALS_KEYS,
    build_range_grid,
    cell_is_empty,
    format_aggregate,
    format_month,
)
from expense.jsonout import emit_json
from expense.reads import fetch_body, query_params

app = typer.Typer(help="Historical reports.", no_args_is_help=True)


def _render_single_month(body: dict, *, json_mode: bool) -> None:
    if json_mode:
        emit_json(body)
        return
    typer.echo(f"Month: {format_month(body.get('month'))}")
    typer.echo("")
    render_category_table(body.get("categories"))
    typer.echo("")
    render_totals(body.get("totals"))


def format_grid_cell(cell: object) -> str:
    """A grid cell as text, for the flat range table.

    A dim `—` means nothing happened that month; `3 unrated` means there was
    activity the engine could not price. Keeping the two apart is the point of
    the cell dict (`build_range_grid`).
    """
    if cell_is_empty(cell):
        return NO_ACTIVITY_MARK
    assert isinstance(cell, dict)
    return format_aggregate(cell.get("cents"), cell.get("unconverted"))


def _render_range_table(body: dict, *, json_mode: bool) -> None:
    if json_mode:
        emit_json(body)
        return

    months = body.get("months") or []
    if not months:
        typer.echo("(no months)")
        return

    grid = build_range_grid(months)
    month_labels: list[str] = grid["labels"]
    grid_rows: list[dict] = grid["rows"]
    totals: dict[str, dict] = grid["totals"]

    def month_cells(source: dict) -> dict[str, str]:
        return {label: format_grid_cell(source.get(label)) for label in month_labels}

    headers = {"name": "Category", **{label: label for label in month_labels}}
    rows = [{"name": row["name"], **month_cells(row["cells"])} for row in grid_rows]
    # inflow and outflow ride as ordinary rows and `net` stays the footer: the
    # footer is the one line `render_table` rules off, and net is the figure that
    # earns the rule.
    rows += [{"name": key, **month_cells(totals[key])} for key in TOTALS_KEYS if key != "net"]
    footer = {"name": "Totals (net)", **month_cells(totals["net"])}
    render_table(headers, rows, align_right=set(month_labels), footer=footer)


def fetch_single_month(
    cfg,
    *,
    year: int,
    month: int,
    verbose: bool = False,
) -> dict:
    """GET /v1/reports/monthly for one month → the raw engine body. No rendering."""
    params = query_params(year=year, month=month)
    return fetch_body(cfg, path="/reports/monthly", params=params, verbose=verbose)


def run_single_month(
    cfg,
    *,
    year: int,
    month: int,
    verbose: bool = False,
    json_mode: bool = False,
) -> None:
    """Fetch + render for a single month — the flat command's whole body."""
    body = fetch_single_month(
        cfg,
        year=year,
        month=month,
        verbose=verbose,
    )
    _render_single_month(body, json_mode=json_mode)


def run_range(
    cfg,
    *,
    from_ym: tuple[int, int],
    to_ym: tuple[int, int],
    verbose: bool = False,
    json_mode: bool = False,
) -> None:
    """Fetch + render for a month range — the flat command's whole body."""
    body = reads.fetch_range(cfg, from_ym=from_ym, to_ym=to_ym, verbose=verbose)
    _render_range_table(body, json_mode=json_mode)


@app.command("monthly")
@handle_errors
def monthly(
    ctx: typer.Context,
    date: str | None = typer.Option(
        None,
        "--date",
        help="Single month, YYYY-MM (e.g. 2026-04). Mutually exclusive with --from/--to.",
    ),
    date_from: str | None = typer.Option(
        None,
        "--from",
        help="Range start, YYYY-MM. Requires --to. Inclusive.",
    ),
    date_to: str | None = typer.Option(
        None,
        "--to",
        help="Range end, YYYY-MM. Requires --from. Inclusive. Max span: 24 months.",
    ),
    json_output: bool = JSON_OPT,
) -> None:
    """GET /v1/reports/monthly. Historical flow for a single month or a month range.

    Example: expense reports monthly --date 2026-03
    Example: expense reports monthly --from 2025-11 --to 2026-04
    """
    if date is not None and (date_from is not None or date_to is not None):
        raise typer.BadParameter(
            "--date is mutually exclusive with --from/--to.",
            param_hint="--date",
        )
    if (date_from is None) != (date_to is None):
        raise typer.BadParameter(
            "--from and --to must be passed together.",
            param_hint="--from/--to",
        )
    if date is None and date_from is None:
        raise typer.BadParameter(
            "Pass either --date YYYY-MM or --from YYYY-MM --to YYYY-MM.",
            param_hint="--date",
        )

    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    if date is not None:
        year, month = parse_year_month(date, param_hint="--date")
        run_single_month(
            cfg,
            year=year,
            month=month,
            verbose=verbose,
            json_mode=json_output,
        )
        return

    assert date_from is not None and date_to is not None
    from_ym = parse_year_month(date_from, param_hint="--from")
    to_ym = parse_year_month(date_to, param_hint="--to")

    run_range(
        cfg,
        from_ym=from_ym,
        to_ym=to_ym,
        verbose=verbose,
        json_mode=json_output,
    )
