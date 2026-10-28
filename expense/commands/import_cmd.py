"""`expense import sheet <file>` — the owner's spreadsheet, sent to the engine whole.

The engine reads the sheet and answers (expense/import_/engine.py); this module
only prints the answer, as docs/mockups/expense-world-sheet-import-engine.html
draws it, and saves the renames `--account-name` gives.
"""

import shlex
from pathlib import Path

import click
import typer

from expense import config as config_module
from expense.bank_import.flow import ImportRefused, read_file
from expense.context import get_verbose
from expense.errors import (
    EngineError,
    error_envelope,
    exit_code_of,
    handle_errors,
    json_body,
    key_field,
    key_index,
    names_its_row,
)
from expense.formatting import grouped_refusals, rows_phrase
from expense.import_.engine import (
    ACCOUNT,
    CATEGORY,
    HASHTAG,
    NameEntry,
    RenameRefused,
    SheetImport,
    Step,
    import_sheet,
    merge_renames,
    parse_account_name,
)
from expense.jsonout import emit_json

_ACCOUNT_NAME_HINT = "'--account-name'"

#: kind → (the table's title, its noun for one, for several).
_NOUNS = {
    ACCOUNT: ("Accounts", "account", "accounts"),
    CATEGORY: ("Categories", "category", "categories"),
    HASHTAG: ("Hashtags", "hashtag", "hashtags"),
}

#: Between two columns of a names table.
_GAP = "   "


def _plural(count: int, one: str, many: str) -> str:
    return f"{count:,} {one if count == 1 else many}"


# ---------------------------------------------------------------------------
# the names tables (screens 1 and 3)
# ---------------------------------------------------------------------------
def _table_lines(kind: str, entries: list[NameEntry]) -> list[str]:
    """One kind's table: its title and count, the column heads, then a line per
    name: the sheet's name, an account's currency, its rows, and where it goes
    (a renamed account's ledger name before it)."""
    title = _NOUNS[kind][0]
    names = [e.name for e in entries]
    rows = [f"{e.rows:,}" for e in entries]
    name_w = max([len("SHEET NAME"), *map(len, names)])
    rows_w = max([len("ROWS"), *map(len, rows)])
    currency = kind == ACCOUNT

    def line(name: str, cur: str, count: str, goes: str) -> str:
        cells = [name.ljust(name_w), *([cur.ljust(3)] if currency else []), count.rjust(rows_w)]
        return "  " + _GAP.join([*cells, goes])

    out = [f"{title} ({len(entries)})", line("SHEET NAME", "CUR", "ROWS", "GOES TO")]
    for entry, count in zip(entries, rows, strict=True):
        goes = entry.goes.value
        if entry.renamed_to is not None:
            goes = f"{entry.renamed_to}  {goes}"
        out.append(line(entry.name, entry.currency or "", count, goes))
    return out


def _print_tables(result: SheetImport) -> None:
    for kind in (ACCOUNT, CATEGORY, HASHTAG):
        entries = [e for e in result.table if e.kind == kind]
        for text in _table_lines(kind, entries):
            typer.echo(text)
        typer.echo("")


# ---------------------------------------------------------------------------
# the counts (screens 3 and 4)
# ---------------------------------------------------------------------------
def _counts_lines(result: SheetImport, head: str) -> list[str]:
    """The engine's counts: `head` (`Rows: 1,961` on the dry run, `Written:`
    on the apply) and each outcome, then the opening balances and the split
    transactions with the rows they hold."""
    c = result.counts
    outcomes = (
        f"new {c.new:,} · matched {c.matched:,} · sealed {c.sealed:,} · skipped {c.skipped:,}"
    )
    splits = f"split transactions {c.split_lines:,} ({c.split_rows:,} rows)"
    return [
        f"{head} {outcomes}",
        f"Opening balances {c.opening_balances:,} · {splits}",
    ]


def _row_lists(result: SheetImport) -> list[str]:
    """The rows of zero and the rows on a closed statement's day, by their
    spreadsheet row, a line for each there is."""
    lines = []
    for outcome, label in (
        ("skipped", "Skipped, amount zero"),
        ("sealed", "Sealed, on a closed statement's day"),
    ):
        rows = [r.row for r in result.rows if r.outcome == outcome]
        if rows:
            lines.append(f"{label}: {rows_phrase(rows)}")
    return lines


# ---------------------------------------------------------------------------
# names still missing (screen 1, pick 2 A)
# ---------------------------------------------------------------------------
def _create_command(file: str) -> str:
    return f"expense import sheet {shlex.quote(file)} --create-names"


def _missing_count(result: SheetImport) -> str:
    """`9 names don't exist yet.`, or `1 name doesn't exist yet.`"""
    count = len(result.missing)
    if count == 1:
        return "1 name doesn't exist yet."
    return f"{count:,} names don't exist yet."


def _missing_lines(result: SheetImport, file: str) -> list[str]:
    them = "it" if len(result.missing) == 1 else "them"
    return [f"{_missing_count(result)} Create {them} with:", f"  {_create_command(file)}"]


# ---------------------------------------------------------------------------
# a refused sheet (screen 5)
# ---------------------------------------------------------------------------
def _rows_refusal(err: Exception) -> bool:
    """A refusal the sheet itself causes: the `422` `VALIDATION_ERROR` the
    engine answers for its rows, every refused key a `rows.<row>…` one
    (contract: POST /v1/transactions/import-sheet, "Rejected up front with `422`").
    Fixing the sheet is what clears it. Every other refusal prints as every
    engine error: a `409` such as `CONCURRENT_CHANGE`, which clears by sending
    the sheet again as it is
    (contract: POST /v1/transactions/import-sheet, "Concurrency"), or the
    `422` `LIMIT_REACHED` once the line codes are used up
    (contract: POST /v1/transactions/import-sheet, "On apply")."""
    return (
        isinstance(err, EngineError)
        and err.status == 422
        and err.code == "VALIDATION_ERROR"
        and bool(err.fields)
        and all(key_index(key, "rows") is not None for key in err.fields or {})
    )


def _refused_lines(err: EngineError) -> list[str]:
    """The refused rows, one line per kind of refusal in the engine's order:
    words that name their row (`Row 77: …`) read whole for one row, and once,
    without the row, before every row refused alike (`… rows 1958, 1959`);
    any other key reads `field: words`, then its rows."""
    fields = err.fields or {}
    reasons = err.reasons or {}
    found: list[tuple[tuple, str, str | None, int]] = []
    for key, message in fields.items():
        row = key_index(key, "rows")
        assert row is not None
        text = str(message)
        name = key_field(key, "rows")
        if names_its_row(key, text):
            words, alone = text[len(f"Row {row}:") :].strip(), text
        else:
            words, alone = (f"{name}: {text}" if name else text), None
        found.append(((name, reasons.get(key), words), words, alone, row))
    rows_of: dict[tuple, set[int]] = {}
    for kind, _words, _alone, row in found:
        rows_of.setdefault(kind, set()).add(row)
    refusals: list[tuple[object, str, list[int]]] = []
    for kind, words, alone, row in found:
        if alone is not None and len(rows_of[kind]) == 1:
            refusals.append((None, alone, []))
        else:
            refusals.append((kind, words, [row]))
    rows = {row for *_rest, row in found}
    lines = [f"Refused — nothing written. {_plural(len(rows), 'row', 'rows')}:"]
    for first, hit, rest in grouped_refusals(refusals):
        lines.append(f"  {first} {hit}" if hit else f"  {first}")
        lines.extend(f"  {line}" for line in rest)
    return [*lines, "", "Fix the sheet and run it again."]


# ---------------------------------------------------------------------------
# --json
# ---------------------------------------------------------------------------
def _created_json(result: SheetImport) -> dict:
    """The engine's answer to each create, by kind."""
    return {
        _NOUNS[kind][2]: [c.answer for c in result.created if c.kind == kind]
        for kind in (ACCOUNT, CATEGORY, HASHTAG)
    }


def _created_line(result: SheetImport) -> str:
    parts = [
        _plural(n, one, many)
        for kind, (_title, one, many) in _NOUNS.items()
        if (n := sum(1 for c in result.created if c.kind == kind))
    ]
    return f"Created {', '.join(parts)}."


#: `--apply` while a name is missing, under `--json`: nothing is sent, so there is
#: no engine answer to pass through; the app's envelope (`errors.error_envelope`).
NAMES_MISSING = "NAMES_MISSING"

#: Before anything is written: the head of every refusal that writes nothing.
_NOT_IMPORTED = "Not imported — nothing written."


def _print_dry_run(result: SheetImport, file: str) -> None:
    """Screen 1 while a name is missing, else screen 3."""
    _print_tables(result)
    if not result.counted:
        typer.echo("No counts yet: the engine counts once every name exists.")
        typer.echo("")
        for line in _missing_lines(result, file):
            typer.echo(line)
        typer.echo("Dry run — nothing written.")
        return
    for line in _counts_lines(result, f"Rows: {len(result.rows):,} ·"):
        typer.echo(line)
    typer.echo("")
    lists = _row_lists(result)
    for line in lists:
        typer.echo(line)
    if lists:
        typer.echo("")
    typer.echo("Dry run — nothing written. Run again with --apply to import.")


def _print_applied(result: SheetImport) -> None:
    """Screen 4: what was written, then the rows of zero and on a closed day,
    or, when rows matched and none is new or sealed, that every row is already
    in the ledger."""
    for line in _counts_lines(result, "Written:"):
        typer.echo(line)
    typer.echo("")
    counts = result.counts
    if counts.matched and counts.new == 0 and counts.sealed == 0:
        typer.echo("Nothing new: every row is already in the ledger.")
        return
    for line in _row_lists(result):
        typer.echo(line)


def _print_created(result: SheetImport) -> None:
    """Screen 2."""
    if not result.created:
        typer.echo("Created no names: every one is yours.")
        return
    typer.echo(_created_line(result))
    typer.echo("Nothing imported. Run the dry run again to see the counts.")


def _refuse_missing(result: SheetImport, file: str, *, json_output: bool) -> None:
    """Pick 2 A: `--apply` while a name is missing writes nothing and names
    the create step. Exit 1."""
    if json_output:
        emit_json(error_envelope(NAMES_MISSING, f"{_NOT_IMPORTED} {_missing_count(result)}"))
    else:
        typer.echo(_NOT_IMPORTED)
        for line in _missing_lines(result, file):
            typer.echo(line)
        typer.echo("then run the dry run to see the counts.")
    raise typer.Exit(code=1)


@handle_errors
def run_import(
    ctx: typer.Context,
    file: str = typer.Argument(..., help="Path to the .xlsx spreadsheet to import."),
    create_names: bool = typer.Option(
        False,
        "--create-names",
        help=(
            "Create every account, category and hashtag the sheet uses that you lack. "
            "Imports nothing."
        ),
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Import the sheet. Default is a dry run that writes nothing."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the engine's answer as JSON."),
    account_name: list[str] = typer.Option(
        [],
        "--account-name",
        metavar="SHEET_NAME:CUR=LEDGER_NAME",
        help=(
            "Put a sheet account's CUR rows on a ledger account of another name. Repeatable; "
            "remembered in the config for every later run."
        ),
    ),
) -> None:
    """Import your spreadsheet through the engine (a dry run by default).

    The file goes to the engine whole; the engine reads it, matches every row
    against the ledger, and writes everything or nothing. The app reads no
    cell of it.

    The dry run lists every account (a name in one currency), category and
    hashtag the sheet uses, its rows, and whether it is yours or missing. While
    one is missing it shows no counts, since the engine counts only once every
    name exists, and gives the command that creates them: --create-names,
    which creates every missing name and imports nothing. Once every name
    exists, the dry run shows the engine's counts, and --apply imports; with a
    name missing, --apply is refused and writes nothing. Sending the same
    sheet again writes nothing: every row is matched.

    One bad row stops the whole import, and every refused row is listed in the
    engine's words; nothing is written and no name is created.

    --account-name "SHEET_NAME:CUR=LEDGER_NAME" puts one sheet account's rows
    in that currency on a ledger account of your choosing ("BCP:PEN=Sueldo
    Soles"). It is saved to the config and applied on every later run; passing
    it again for the same account replaces the saved name. An account the
    sheet does not have, or two sheet accounts put on one, is a usage error and
    nothing is saved.

    Example: expense import sheet Presupuesto.xlsx

    Example: expense import sheet Presupuesto.xlsx --create-names

    Example: expense import sheet Presupuesto.xlsx --apply

    Example: expense import sheet Presupuesto.xlsx --account-name "BCP:PEN=Sueldo Soles"
    """
    if create_names and apply:
        raise click.UsageError(
            "--create-names creates names and imports nothing, so it never goes with --apply."
        )
    try:
        flags = [parse_account_name(value) for value in account_name]
    except RenameRefused as exc:
        raise typer.BadParameter(str(exc), param_hint=_ACCOUNT_NAME_HINT) from exc

    # Read once: the settings file may be a pipe.
    cfg = config_module.require(config_module.load())
    try:
        data = read_file(Path(file))
    except ImportRefused as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    saved = dict(cfg.sheet_account_names)
    merged, renames = merge_renames(saved, flags)
    step = Step.APPLY if apply else Step.CREATE_NAMES if create_names else Step.DRY_RUN
    try:
        result = import_sheet(
            cfg, data, step=step, renames=renames, flags=flags, verbose=get_verbose(ctx)
        )
    except RenameRefused as exc:
        raise typer.BadParameter(str(exc), param_hint=_ACCOUNT_NAME_HINT) from exc
    # Remembered once the renames were checked against this sheet, a dry run's too.
    if result.table and merged != saved:
        cfg.sheet_account_names = merged
        config_module.save(cfg)

    if result.error is not None:
        if result.created and json_output:
            emit_json({"created": _created_json(result), **json_body(result.error)})
            raise typer.Exit(code=exit_code_of(result.error))
        if result.created:
            typer.echo(_created_line(result))
        if isinstance(result.error, EngineError) and _rows_refusal(result.error):
            if not json_output:
                for line in _refused_lines(result.error):
                    typer.echo(line)
                raise typer.Exit(code=1)
        raise result.error

    if step is Step.CREATE_NAMES:
        if json_output:
            emit_json({"created": _created_json(result)})
        else:
            _print_created(result)
        return
    if step is Step.APPLY and not result.counted:
        _refuse_missing(result, file, json_output=json_output)
    if json_output:
        emit_json(result.answer)
    elif step is Step.APPLY:
        _print_applied(result)
    else:
        _print_dry_run(result, file)
