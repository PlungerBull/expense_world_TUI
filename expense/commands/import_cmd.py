"""`expense import sheet <file>` — the owner's spreadsheet, sent to the engine whole.

The engine reads the sheet and answers (expense/import_/engine.py). A dry run opens the
app on the import's review (expense/tui/screens/import_sheet.py), which makes the accounts,
categories and hashtags and imports the rows in one write; this module prints the other
two ways in: `--apply` and `--json`.

`--json` prints the engine's answer as it sent it. One document is the app's
(docs/commands.md "Sanctioned exceptions"): `--apply --json` with a name or an account
missing is a `NAMES_MISSING` envelope (`errors.error_envelope`), nothing written.

`SALDO INICIAL` is a category name like any other to the app: listed, made by the review,
and an unused category to delete once only opening balances use it
(contract: POST /v1/transactions/import-sheet, "Opening balances").
"""

import shlex
from pathlib import Path

import typer

from expense import config as config_module
from expense.bank_import.flow import ImportRefused, read_file
from expense.context import get_verbose
from expense.errors import (
    EngineError,
    error_envelope,
    handle_errors,
    key_field,
    key_index,
    names_its_row,
)
from expense.formatting import count_phrase, grouped_refusals, rows_phrase
from expense.import_.engine import (
    SheetImport,
    SheetReview,
    Step,
    import_sheet,
)
from expense.jsonout import emit_json
from expense.tui import open_app


# ---------------------------------------------------------------------------
# the counts
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
# names still missing: what the refused apply prints
# ---------------------------------------------------------------------------
def _missing_count(result: SheetImport) -> str:
    """`5 names don't exist yet.`, or `1 name doesn't exist yet.`: the accounts,
    categories and hashtags the review makes."""
    count = len(result.missing) + len(result.missing_accounts)
    if count == 1:
        return "1 name doesn't exist yet."
    return f"{count:,} names don't exist yet."


# ---------------------------------------------------------------------------
# a refused sheet
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
    lines = [f"Refused — nothing written. {count_phrase(len(rows), 'row', 'rows')}:"]
    for first, hit, rest in grouped_refusals(refusals):
        lines.append(f"  {first} {hit}" if hit else f"  {first}")
        lines.extend(f"  {line}" for line in rest)
    return [*lines, "", "Fix the sheet and run it again."]


# ---------------------------------------------------------------------------
# --json and the apply
# ---------------------------------------------------------------------------
#: `--apply` while a name is missing, under `--json`: nothing is sent, so there is
#: no engine answer to pass through; the app's envelope (`errors.error_envelope`).
NAMES_MISSING = "NAMES_MISSING"

#: Before anything is written: the head of every refusal that writes nothing.
_NOT_IMPORTED = "Not imported — nothing written."


def _print_applied(result: SheetImport) -> None:
    """What was written, then the rows of zero and on a closed day,
    or, when rows matched and none is new or sealed, that every row is already
    in the ledger. A blank line separates the counts from what follows, and only
    when something follows."""
    for line in _counts_lines(result, "Written:"):
        typer.echo(line)
    counts = result.counts
    if counts.matched and counts.new == 0 and counts.sealed == 0:
        typer.echo("")
        typer.echo("Nothing new: every row is already in the ledger.")
        return
    lists = _row_lists(result)
    if lists:
        typer.echo("")
    for line in lists:
        typer.echo(line)


def _refuse_missing(result: SheetImport, file: str, *, json_output: bool) -> None:
    """`--apply` while a name or an account is missing writes nothing and points at the
    review, which makes them. Exit 1."""
    if json_output:
        emit_json(error_envelope(NAMES_MISSING, f"{_NOT_IMPORTED} {_missing_count(result)}"))
    else:
        typer.echo(_NOT_IMPORTED)
        typer.echo(f"{_missing_count(result)} Make them in the review:")
        typer.echo(f"  expense import sheet {shlex.quote(file)}")
    raise typer.Exit(code=1)


@handle_errors
def run_import(
    ctx: typer.Context,
    file: str = typer.Argument(..., help="Path to the .xlsx spreadsheet to import."),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Import the sheet without the review, once every name exists.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the engine's answer as JSON."),
) -> None:
    """Import your spreadsheet through the engine.

    The file goes to the engine whole; the engine reads it, matches every row
    against the ledger, and writes everything or nothing. The app reads no
    cell of it.

    Without a flag the engine's dry run opens the app on the import's review: each
    account the sheet names that you lack, set once (a bank account's code and last
    4, a person, the cash account, archived or not), the categories and hashtags to
    make, then the engine's count, and one write makes them all and imports the
    rows. Sending the same sheet again writes nothing: every row is matched.

    --apply imports without the review, once every account, category and hashtag
    exists; with one missing it is refused and writes nothing. --json prints the
    engine's answer to the dry run (the counts too, once every name exists) and
    opens nothing.

    One bad row stops the whole import, and every refused row is listed in the
    engine's words; nothing is written.

    Example: expense import sheet Presupuesto.xlsx

    Example: expense import sheet Presupuesto.xlsx --apply
    """
    # Read once: the settings file may be a pipe.
    cfg = config_module.require(config_module.load())
    try:
        data = read_file(Path(file))
    except ImportRefused as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    step = Step.APPLY if apply else Step.DRY_RUN if json_output else Step.NAMES
    result = import_sheet(cfg, data, step=step, verbose=get_verbose(ctx))

    if result.error is not None:
        if isinstance(result.error, EngineError) and _rows_refusal(result.error):
            if not json_output:
                for line in _refused_lines(result.error):
                    typer.echo(line)
                raise typer.Exit(code=1)
        raise result.error

    if step is Step.APPLY and not result.counted:
        _refuse_missing(result, file, json_output=json_output)
    if json_output:
        emit_json(result.answer)
    elif step is Step.APPLY:
        _print_applied(result)
    else:
        _review(ctx, SheetReview(Path(file).name, data, result.table, len(result.rows), cfg))


def _review(ctx: typer.Context, review: SheetReview) -> None:
    """Open the app on the review and print the one line it ends with."""
    line = open_app(ctx, review)
    if line:
        typer.echo(line)
