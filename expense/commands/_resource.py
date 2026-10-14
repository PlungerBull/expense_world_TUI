"""Shared helpers for resource sub-apps (accounts, categories, hashtags)."""

import os
import sys
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, Literal

import typer

from expense import config as config_module
from expense.config import Config
from expense.context import get_verbose
from expense.errors import EngineError
from expense.formatting import (
    UNRATED_SUFFIX,
    format_aggregate,
    format_cents,
    has_aggregate,
    unconverted_of,
    visible_len,
)
from expense.http import ExpenseClient
from expense.jsonout import emit_json
from expense.reads import DEFAULT_PAGE_ROWS, load_hashtag_name_map

# Shared option declarations — one wording for flags repeated across command
# modules. Never mutate these; a command whose flag means something different
# declares it inline (e.g. `import sheet --json` emits the plan, not a body).
JSON_OPT = typer.Option(False, "--json", help="Output the raw engine response as JSON.")
LIMIT_OPT = typer.Option(
    None,
    "--limit",
    help="Max rows per page (human output defaults to 20; --json sends no default).",
)
INCLUDE_ARCHIVED_OPT = typer.Option(False, "--include-archived", help="Include archived rows.")
YES_OPT = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt.")


def pad_left(text: str, width: int) -> str:
    """Left-align `text` (pad spaces on the right) to `width` visible cols."""
    return text + " " * max(width - visible_len(text), 0)


def pad_right(text: str, width: int) -> str:
    """Right-align `text` (pad spaces on the left) to `width` visible cols."""
    return " " * max(width - visible_len(text), 0) + text


def stdin_is_tty() -> bool:
    """Is there a human at the other end to answer a prompt?

    Its own function so a test can be run through `CliRunner` and still take
    the interactive branch: the runner swaps `sys.stdin` out for the duration
    of the call, so patching the stream itself never reaches `require_yes`.
    """
    return sys.stdin.isatty()


def color_supported() -> bool:
    """True iff stdout is a TTY and NO_COLOR env var is unset.

    Honors the de-facto NO_COLOR convention (https://no-color.org/).
    """
    return sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""


def color_swatch(hex_value: object, *, color: bool) -> str:
    """Render a 2-char ANSI swatch for `#RRGGBB`, or fall back to the hex.

    Returns `(none)` when the input is None. Invalid hex falls through to
    the raw string. Set `color=False` to always render the hex literally
    (e.g. when piping to a file).
    """
    if hex_value is None:
        return "(none)"
    if not isinstance(hex_value, str):
        return str(hex_value)
    if not color:
        return hex_value
    if len(hex_value) != 7 or not hex_value.startswith("#"):
        return hex_value
    try:
        r = int(hex_value[1:3], 16)
        g = int(hex_value[3:5], 16)
        b = int(hex_value[5:7], 16)
    except ValueError:
        return hex_value
    return f"\x1b[38;2;{r};{g};{b}m██\x1b[0m"


def format_cents_or_dash(value: object) -> str:
    """`format_cents`, but an absent amount is `—` rather than `(null)`.

    For fields where null is a *meaningful state the user will actually see*,
    not a shape error worth shouting about. `(null)` is the right output when a
    null means something went wrong — it is deliberately ugly so it gets
    noticed. It is the wrong output for a reconciliation's `ending_balance_cents`,
    which is null whenever you have opened a batch and not yet read the closing
    figure off the statement (contract: "An omitted ending balance is `null`,
    never zero"): a normal, expected,
    every-month state that should not read as a defect.

    `—` is already this repo's mark for an absent value — see `format_short_date`
    above, and `amount_cell` in the TUI. `0` still renders as `0.00`, because an
    entered zero is a real statement balance and telling those two apart is the
    entire point of the engine change this pairs with.
    """
    return "—" if value is None else format_cents(value)


def format_field_value(key: object, value: object) -> str:
    """Render one `key: value` line for the single-resource `get` dumps.

    Money fields (keys ending in `_cents`) render as grouped major units via
    `format_cents` so a raw dump is as readable as the list tables; every other
    field is its literal value, or `(null)` when None.
    """
    if isinstance(key, str) and key.endswith("_cents"):
        return format_cents(value)
    return "(null)" if value is None else str(value)


def render_record(body: dict, *, json_mode: bool, skip: tuple[str, ...] = ()) -> None:
    """Dump one resource record: raw JSON in json_mode, else `  key: value` lines.

    The canonical renderer behind every `<resource> get` command. `skip` hides
    keys from the human dump only — `--json` stays the verbatim engine body.
    """
    if json_mode:
        emit_json(body)
        return
    for key, value in body.items():
        if key in skip:
            continue
        typer.echo(f"  {key}: {format_field_value(key, value)}")


def format_bool(value: object) -> str:
    """Human cell for booleans and truthy markers."""
    return "yes" if bool(value) else "no"


def effective_limit(limit: int | None, *, json_mode: bool) -> int | None:
    """The limit a list command sends: DEFAULT_PAGE_ROWS in human mode unless
    the user passed --limit. `--json` requests are left untouched (no default),
    so the raw body stays exactly what the engine returns today."""
    return DEFAULT_PAGE_ROWS if limit is None and not json_mode else limit


def parse_hashtag_ids(raw: str) -> list[str]:
    """`"a, b ,,c"` → `["a", "b", "c"]`. Shared by every command taking `--hashtag-ids`.

    Two behaviours here are load-bearing, not incidental:

    * **No client-side UUID validation.** A bad id is the engine's 422 on
      `hashtag_ids`: `INVALID_FORMAT` when it is not a UUID, `INVALID_REFERENCE` when it
      names no active hashtag (missing, deleted or archived), so the engine owns the
      archived-hashtag rule too
      (contract: POST /v1/transactions, "Validation") (contract: "Error reasons") —
      the thin-wrapper rule says we don't second-guess it.
    * **`""` → `[]`, not `None`.** An empty string is an explicit *clear*, so callers
      must pass the result to `build_update_payload` only when the flag was supplied;
      `[]` is a real value the engine acts on, while a dropped key means "leave alone".

    Consumers: `transactions update`, `log`.
    """
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def render_table(
    headers: dict[str, str],
    rows: list[dict[str, str]],
    *,
    align_right: set[str] | frozenset[str] = frozenset(),
    sep: str = "  ",
    footer: dict[str, str] | None = None,
) -> None:
    """Render an ASCII table. Cells must be pre-formatted strings.

    `headers` is an ordered dict of {column-key: column-label}.
    Each `row` is a dict keyed by the same column keys.
    Cells listed in `align_right` are right-padded; the rest are left-padded.
    Width per column = max(header label, max(visible_len(cell) for cell in column)).

    `footer` (optional) is one summary row keyed like a data row; when given, it
    is printed below a second separator rule and its cells seed the column widths
    so the totals line stays aligned. A footer prints even when `rows` is empty.
    """
    if not rows and footer is None:
        return
    extra = [footer] if footer is not None else []
    widths = {
        key: max([len(headers[key])] + [visible_len(row.get(key, "")) for row in rows + extra])
        for key in headers
    }

    def fmt(text: str, key: str) -> str:
        return pad_right(text, widths[key]) if key in align_right else pad_left(text, widths[key])

    def rule() -> None:
        typer.echo(sep.join("-" * widths[key] for key in headers))

    typer.echo(sep.join(fmt(headers[key], key) for key in headers))
    rule()
    for row in rows:
        typer.echo(sep.join(fmt(row.get(key, ""), key) for key in headers))
    if footer is not None:
        rule()
        typer.echo(sep.join(fmt(footer.get(key, ""), key) for key in headers))


def require_yes(yes: bool, prompt_text: str, *, aborted_text: str = "Aborted.") -> None:
    """Enforce explicit confirmation before a write.

    Mirrors the pattern from `auth settings`: in non-TTY mode, --yes is mandatory;
    in TTY mode, prompt the user unless --yes was already passed.

    Destructive commands (the original callers) take the default wording.
    `expense log "<line>"` passes its own: nothing is being destroyed there —
    the prompt exists because a typed line is *parsed*, and the parse is what
    you are agreeing to.
    """
    if yes:
        return
    if not stdin_is_tty():
        typer.echo(
            "Error: --yes is required for this operation in non-interactive mode.",
            err=True,
        )
        raise typer.Exit(code=1)
    if not typer.confirm(prompt_text):
        typer.echo(aborted_text)
        raise typer.Exit(code=1)


def print_warnings(body: dict) -> None:
    """Render an engine `warnings` envelope to stderr, one line each.

    The warnings channel is deliberately per-endpoint rather than uniform: the
    key exists exactly where a warning can occur (contract: "Warnings
    channel"). One endpoint carries it: `POST /reconciliations/{id}/complete`
    where it reports a stretch of days no completed period
    covers.

    Worth not dropping: a transaction inside an uncovered stretch moves no
    period's arithmetic, because `difference_cents` is two balances typed off
    a statement minus the rows that were ticked. It is not hidden — it shows
    in reports and balances like any other row — but nothing else in the
    system will ever point at it.

    Human mode only; `--json` already passes the engine body through verbatim.
    """
    warnings = body.get("warnings") if isinstance(body, dict) else None
    if isinstance(warnings, list):
        for warning in warnings:
            typer.echo(f"Warning: {warning}", err=True)


def build_update_payload(items: dict[str, Any]) -> dict[str, Any]:
    """Drop None values; exit if nothing is left to update."""
    payload = {key: value for key, value in items.items() if value is not None}
    if not payload:
        typer.echo("Error: No fields to update; pass at least one flag.", err=True)
        raise typer.Exit(code=1)
    return payload


def render_totals(totals: dict | None) -> None:
    """Render the canonical inflow/outflow/net block.

    Shared by `dashboard` and `reports monthly` (single-month view) — both
    surface the same `{inflow, outflow, net}_home_cents` + `unconverted_count`
    shape. Empty/missing totals print '(no totals)'.

    Home-currency only: a sum across accounts in different currencies is a
    number in no currency at all.

    The three figures share a single `unconverted_count`, so they fail together
    — an unpriceable month collapses the whole block to one line rather than
    repeating the same count three times.
    """
    typer.echo("Totals:")
    if not isinstance(totals, dict):
        typer.echo("  (no totals)")
        return
    unconverted = unconverted_of(totals)
    if unconverted > 0:
        typer.echo(f"  {unconverted} {UNRATED_SUFFIX} — no totals this month")
        return
    for label in ("inflow", "outflow", "net"):
        amount = format_aggregate(totals.get(f"{label}_home_cents"), unconverted)
        typer.echo(f"  {label}: {amount}")


def hashtag_label(ids: list[str], name_map: dict[str, str]) -> str:
    """Format a hashtag-combo label, resolving ids via name_map.

    Empty ids -> `(no hashtags)`. Otherwise joins resolved names (or raw id
    fallback for any unresolved entry) with ` + `.
    """
    if not ids:
        return "(no hashtags)"
    return " + ".join(name_map.get(hid, hid) for hid in ids)


def render_category_table(categories: list[dict] | None) -> None:
    """Render the Categories block as Name / Home, with indented hashtag sub-rows.

    Shared by `dashboard` and `reports monthly` (single-month view), which are
    read side by side and so must agree.

    The amount is `spent_home_cents` -- the only cross-account figure (a sum
    across currencies is a number in no currency). The
    column is called `Home`.

    Categories and hashtag combinations with nothing spent are **not drawn**:
    the engine returns every non-deleted category whether or not it has
    activity, and a report is not a category list. One that could not be priced
    keeps its row and says `3 unrated` (`has_aggregate`).
    """
    typer.echo("Categories:")
    if not categories:
        typer.echo("  (no categories)")
        return

    name_map = load_hashtag_name_map()
    rows: list[dict[str, str]] = []
    for cat in categories:
        cat_unconverted = unconverted_of(cat)
        if not has_aggregate(cat.get("spent_home_cents"), cat_unconverted):
            continue
        rows.append(
            {
                "name": cat.get("name") or "(unnamed)",
                "home": format_aggregate(cat.get("spent_home_cents"), cat_unconverted),
            }
        )
        for sub in cat.get("hashtag_breakdown") or []:
            sub_unconverted = unconverted_of(sub)
            if not has_aggregate(sub.get("spent_home_cents"), sub_unconverted):
                continue
            ids = sub.get("hashtag_ids") or []
            rows.append(
                {
                    "name": "  " + hashtag_label(ids, name_map),
                    "home": format_aggregate(sub.get("spent_home_cents"), sub_unconverted),
                }
            )

    if not rows:
        typer.echo("  (no categories)")
        return

    render_table(
        headers={"name": "Name", "home": "Home"},
        rows=rows,
        align_right={"home"},
    )


def render_pagination_hint(
    body: Any,
    *,
    note: str = "",
    older: Literal["instant", "day_before"] = "instant",
) -> None:
    """Print how to reach the rest of a paged list, when there is a rest.

    Two shapes page (contract: "Base Conventions", "Lists come in three shapes, and none
    of them is paged by position"), each with its own line;
    anything else — a whole list, a missing envelope — prints nothing.

    A cursor-paged body (`transactions list`) has no total: when it carries a
    `next_cursor` the line says how to pass it back, and on the last page
    (`null`) nothing is printed. The cursor is bound to the filters *and* the
    sort, so the line names both.

    A body that echoes a date window (`date_from` / `date_to` — `activity list`
    and `rates list`) also carries `next_cursor`, but its line shows the window,
    and no `--sort`, which neither command has. The transactions line must never
    print for it. Its line is always printed, even under an empty table, so an
    empty window never reads as "no history": `(from → to · more in this window:
    pass --after <c>)`, or on the window's last page how to go further back.
    `older` says how: `"instant"` (activity) passes the echoed `date_from` back
    exactly, since a bare day would widen to the whole day and repeat rows;
    `"day_before"` (rates, whose dates are inclusive days) passes the day before
    it. `note` rides on this line, for a list whose order is worth stating.
    """
    if not isinstance(body, dict):
        return
    cursor = body.get("next_cursor")
    windowed = "date_from" in body or "date_to" in body
    if windowed:
        _render_window_hint(body, cursor, note=note, older=older)
        return
    if isinstance(cursor, str) and cursor:
        typer.echo(f"\n(more: pass --after {cursor} with the same filters and --sort)")


def _window_bound(value: object) -> str:
    """`2026-09-25T23:59:59.999999-05:00` → `2026-09-25 23:59`; a day stays a day."""
    text = str(value)
    return text if len(text) <= 10 else text[:16].replace("T", " ")


def _render_window_hint(
    body: dict, cursor: object, *, note: str, older: Literal["instant", "day_before"]
) -> None:
    """The date-window line of `render_pagination_hint` (contract: "Date windows").

    Rates' bounds are days and print as they are. Activity's are instants the
    engine already renders in the user's `display_timezone` (contract: GET /v1/activity),
    so they are only cut to date and minute (`2026-09-25 23:59`), with no zone
    math here. The `--to` in the "older" part is the echoed value, uncut.
    """
    date_from, date_to = body.get("date_from"), body.get("date_to")
    span = f"{_window_bound(date_from)} → {_window_bound(date_to)}"
    if note:
        span += f" · {note}"
    if isinstance(cursor, str) and cursor:
        typer.echo(f"\n({span} · more in this window: pass --after {cursor})")
        return
    if not isinstance(date_from, str) or not date_from:
        typer.echo(f"\n({span})")
        return
    back = date_from
    if older == "day_before":
        back = (date.fromisoformat(date_from[:10]) - timedelta(days=1)).isoformat()
    typer.echo(f"\n({span} · older: pass --to {back})")


def run_toggle(
    ctx: typer.Context,
    *,
    resource: str,
    id_: str,
    verb: str,
    json_output: bool,
    render_human: Callable[[dict], None],
    hints: dict[int, str] | None = None,
) -> None:
    """Execute one of the {archive, unarchive} toggle verbs.

    Both are POST /{resource}/{id}/{verb} with no body and an identical
    response shape (the resource row).

    `hints` maps HTTP status code → stderr hint string. When the engine
    raises an EngineError whose `.status` matches a key, the hint is
    printed before the error envelope renders. This lets archive/unarchive
    on resources with domain-specific 403/409 conditions (e.g. system
    categories, name conflicts) keep their friendly recovery prompts
    without forking the call site.
    """
    cfg: Config = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    with ExpenseClient(cfg, verbose=verbose) as client:
        body = _hinted(lambda: client.post(f"/{resource}/{id_}/{verb}"), hints)

    if json_output:
        emit_json(body)
    else:
        render_human(body)


def run_delete(
    ctx: typer.Context,
    *,
    resource: str,
    id_: str,
    confirm: str,
    yes: bool,
    json_output: bool,
    hints: dict[int, str] | None = None,
    skip: tuple[str, ...] = (),
) -> None:
    """Execute one `delete` command: confirm, DELETE /{resource}/{id}, render.

    The sibling of `run_toggle`, and written for the same reason. That one's
    docstring says `hints` exists so a resource with a domain-specific 403/409
    can "keep their friendly recovery prompts without forking the call site" —
    but only the toggle verbs ever got the helper, so all five deletes forked
    anyway, each re-spelling the same confirm → open → try → hint → render.

    What stays with the resource is what differs: `confirm` is its own warning
    (a hashtag cascades to junction rows, a reconciliation unassigns its
    transactions), `hints` its own recovery prompts, and `skip` the fields its
    record view drops. Everything else is plumbing.
    """
    require_yes(yes, confirm)

    cfg: Config = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    with ExpenseClient(cfg, verbose=verbose) as client:
        body = _hinted(lambda: client.delete(f"/{resource}/{id_}"), hints)

    render_record(body, json_mode=json_output, skip=skip)


def _hinted(call: Callable[[], dict], hints: dict[int, str] | None) -> dict:
    """Run one engine call; on an EngineError whose status has a hint, print it
    to stderr before letting the error out to `handle_errors`.

    The hint goes first because the error envelope below it is the engine's
    words, and the recovery prompt is ours.
    """
    try:
        return call()
    except EngineError as err:
        if hints and err.status in hints:
            typer.echo(hints[err.status], err=True)
        raise
