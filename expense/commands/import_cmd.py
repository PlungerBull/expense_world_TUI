"""`expense import sheet <file>` — the owner's spreadsheet, sent to the engine whole.

The engine reads the sheet and answers (expense/import_/engine.py). Its dry run opens the
app on the import's review (expense/tui/screens/import_sheet.py), which makes the accounts,
categories and hashtags and imports the rows in one write; this module only prints what stops
that before the app opens: a refused sheet, rows grouped as the LOG bar's.

`SALDO INICIAL` is a category name like any other to the app: listed, made by the review,
and an unused category to delete once only opening balances use it
(contract: POST /v1/transactions/import-sheet, "Opening balances").
"""

from pathlib import Path

import typer

from expense import config as config_module
from expense.bank_import.flow import ImportRefused, read_file
from expense.context import get_verbose
from expense.errors import (
    EngineError,
    handle_errors,
    key_field,
    key_index,
    names_its_row,
)
from expense.formatting import count_phrase, grouped_refusals
from expense.import_.engine import SheetReview, import_sheet
from expense.tui import open_app


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


@handle_errors
def run_import(
    ctx: typer.Context,
    file: str = typer.Argument(..., help="Path to the .xlsx spreadsheet to import."),
) -> None:
    """Import your spreadsheet through the engine.

    The file goes to the engine whole; the engine reads it, matches every row
    against the ledger, and writes everything or nothing. The app reads no
    cell of it.

    The engine's dry run opens the app on the import's review: each account the sheet
    names that you lack, set once (a bank account's code and last 4, a person, the cash
    account, archived or not), the categories and hashtags to make, then the engine's
    count, and one write makes them all and imports the rows. Sending the same sheet
    again writes nothing: every row is matched.

    One bad row stops the whole import, and every refused row is listed in the
    engine's words; nothing is written and the app does not open.

    Example: expense import sheet Presupuesto.xlsx
    """
    # Read once: the settings file may be a pipe.
    cfg = config_module.require(config_module.load())
    try:
        data = read_file(Path(file))
    except ImportRefused as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = import_sheet(cfg, data, verbose=get_verbose(ctx))
    if result.error is not None:
        if isinstance(result.error, EngineError) and _rows_refusal(result.error):
            for line in _refused_lines(result.error):
                typer.echo(line)
            raise typer.Exit(code=1)
        raise result.error
    open_app(ctx, SheetReview(Path(file).name, data, result.table, len(result.rows), cfg))
