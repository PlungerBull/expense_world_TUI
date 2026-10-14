"""`expense import bank <file.xlsx>` — a bank download → the ledger, under @Pendiente.

The flow: read the sheet, ask which account (every run — nothing is
remembered by file name), then hand every row to the engine's
`POST /transactions/import` in **one** call, which matches the rows against
the ledger and, under `--apply`, writes what is missing in one database
transaction. A day where the ledger holds a row of the same amount that no
file row matched is a loud warning: it is how an earlier double
entry, or a row about to be logged twice under another wording, surfaces.

The matching is the engine's, not this file's: a second copy of the rule
would drift, and every other client would need a third. What stays here is
what only a client can know — the file's lines, the account pick, and the
2026-01-01 floor.

Why the account is asked and not read: the file does not say. The bank names
the file after the product ("VISA Infinite Sapphire") and the sheet after
nothing; the card's PEN and USD rows share one file, so the pick is the card
and the currency column chooses the leg per row.
"""

from typing import NoReturn

import typer

from expense import config as config_module
from expense import reads
from expense.bank_import.engine import (
    IMPORT_FLOOR,
    RULE_LABELS,
    ExcessGroup,
    IncompleteAnswer,
    Placed,
    excess_groups,
    match_label,
    placements,
    row_refusals,
)
from expense.bank_import.flow import (
    AccountGroup,
    ImportRefused,
    Prepared,
    account_groups,
    excess_head,
    import_call,
    import_counts,
    incomplete_sentence,
    period_names,
    prepared_for,
    read_bank_file,
    sealed_lines,
)
from expense.bank_import.parse import BadRow, BankRow
from expense.commands import _resource
from expense.commands._resource import render_table
from expense.context import get_verbose
from expense.errors import EngineError, handle_errors
from expense.formatting import format_cents
from expense.http import ExpenseClient
from expense.jsonout import emit_json
from expense.reads import items_of

#: Rows the preview prints before folding the rest behind `--all`.
PREVIEW_ROWS = 8

#: The bank's currency labels, for the summary line — the reverse of parse's map.
CURRENCY_LABEL = {"PEN": "S/", "USD": "$"}


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


def _find_group(groups: list[AccountGroup], wanted: str) -> AccountGroup | None:
    """By base name or by any leg's full name, case-insensitively."""
    key = " ".join(wanted.split()).casefold()
    for g in groups:
        if g.base.casefold() == key:
            return g
    for g in groups:
        for currency, (ident, name) in g.legs.items():
            if name.casefold() == key:
                # One leg, named as the caller named it — so a refusal says
                # "BCP Signature PEN holds PEN only", not the card's base.
                return AccountGroup(name, {currency: (ident, name)})
    return None


def choose_group(
    groups: list[AccountGroup],
    *,
    account_flag: str | None,
    quiet: bool = False,
) -> AccountGroup:
    """`--account` wins; otherwise a prompt on a TTY, every run. Nothing is
    remembered: a browser re-download (`Sueldo Soles (1).xlsx`) is asked like
    any other file.

    `quiet` (JSON mode) prints nothing and never prompts — the answer has to
    come from the flag, or the run fails like a non-TTY one.
    """
    say = (lambda _text: None) if quiet else typer.echo
    if account_flag is not None:
        group = _find_group(groups, account_flag)
        if group is None:
            _fail(f"no account named {account_flag!r}. Known: " + ", ".join(g.base for g in groups))
        say(f"  Account: {group.base}")
        return group

    # Looked up through the module so the test seam (`_resource.stdin_is_tty`)
    # is the one the prompt actually consults.
    if quiet or not _resource.stdin_is_tty():
        _fail("--account is required in non-interactive mode.")
    typer.echo("")
    typer.echo("  Which account is this?")
    for i, g in enumerate(groups, start=1):
        typer.echo(f"    {i}  {g.label}")
    answer = typer.prompt(f"  Account [1-{len(groups)}]")
    try:
        picked = groups[int(answer) - 1]
    except (ValueError, IndexError):
        picked = _find_group(groups, answer)  # a name typed instead of a number
        if picked is None:
            _fail(f"{answer!r} is not one of the accounts listed.")
    return picked


def prepare(cfg, *, file: str, account_flag: str | None, quiet: bool, verbose: bool) -> Prepared:
    """Read the sheet, settle which account it belongs to, drop the rows under
    the floor and refuse a file too long for one request. Reads only.

    `quiet` suppresses the human banner and the account prompt's chatter,
    which is what `--json` wants.
    """
    try:
        rows, bad = read_bank_file(file)
    except ImportRefused as exc:
        _fail(str(exc))

    if rows and not quiet:
        typer.echo("  " + _file_banner(rows, bad))

    accounts = items_of(reads.fetch_accounts(cfg, include_people=False, verbose=verbose))
    groups = account_groups(accounts)
    if not groups:
        _fail("no accounts exist yet — create one first (expense accounts create).")
    group = choose_group(groups, account_flag=account_flag, quiet=quiet)

    try:
        return prepared_for(file, group, rows, bad)
    except ImportRefused as exc:
        if exc.list_bad:
            for b in bad:
                typer.echo(f"  ! row {b.line}: {b.reason}", err=True)
        _fail(str(exc))


def _file_banner(rows: list[BankRow], bad: list[BadRow]) -> str:
    """`23 rows · 2026-09-01 → 2026-09-12 · S/ 14 · $ 9` — what the file holds,
    before any of it is placed."""
    days = sorted(r.date_iso for r in rows)
    currencies = sorted({r.currency for r in rows})
    counts = " · ".join(
        f"{CURRENCY_LABEL.get(c, c)} {sum(1 for r in rows if r.currency == c)}" for c in currencies
    )
    codes = " · operation numbers on every row" if all(r.operation_code for r in rows) else ""
    return f"{len(rows) + len(bad)} rows · {days[0]} → {days[-1]} · {counts}{codes}"


def post_import(cfg, prepared: Prepared, *, dry_run: bool, verbose: bool) -> dict:
    """`import_call` on a client of its own."""
    with ExpenseClient(cfg, verbose=verbose) as client:
        return import_call(client, prepared, dry_run=dry_run)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def render_result(
    prepared: Prepared,
    placed: list[Placed],
    excess: list[ExcessGroup],
    names: dict[str, str],
    *,
    show_all: bool,
    applied: bool,
) -> None:
    """The table, then what did not go in and why, then the summary."""
    shown = placed if show_all else placed[:PREVIEW_ROWS]
    headers = {"n": "#", "date": "date", "title": "title", "amount": "amount"}
    headers["account"] = "→ account"
    if prepared.has_codes:
        headers["op"] = "op"
    headers["match"] = "match"
    table = [
        {
            # The file's own line, the number every message below the table
            # uses too.
            "n": str(p.sent.row.line),
            "date": p.sent.row.date_iso,
            "title": p.sent.row.title,
            "amount": format_cents(p.sent.row.amount_cents),
            "account": p.sent.account_name,
            "op": p.sent.row.operation_code or "—",
            "match": match_label(p, names),
        }
        for p in shown
    ]
    typer.echo("")
    render_table(headers, table, align_right={"n", "amount"})
    if len(placed) > len(shown):
        typer.echo(f"  … {len(placed) - len(shown)} more · pass --all to print every row")
    typer.echo("")
    typer.echo("  " + summary_line(prepared, placed, applied=applied))
    for line in sealed_lines(placed, names):
        typer.echo("  " + line)
    for line in excess_lines(excess):
        typer.echo("  " + line)
    if prepared.before_floor:
        n = len(prepared.before_floor)
        typer.echo(
            f"  {n} row{'' if n == 1 else 's'} dated before {IMPORT_FLOOR} not sent — "
            "imports start there."
        )
    for b in prepared.bad:
        typer.echo(f"  ! row {b.line}: {b.reason}")


def summary_line(prepared: Prepared, placed: list[Placed], *, applied: bool) -> str:
    counts = import_counts(prepared, placed)
    by_rule = counts.by_rule
    # Strongest rule first, always, so the breakdown reads the same for every
    # file instead of following whichever rule claimed the first row.
    detail = " · ".join(
        f"{by_rule[rule]} by {label}" for rule, label in RULE_LABELS.items() if by_rule.get(rule)
    )
    parts = [f"{counts.total} rows", f"{counts.new} new", f"{counts.matched} in the ledger"]
    if detail:
        parts[-1] += f" ({detail})"
    codes = counts.codes
    if codes:
        done = "written" if applied else "to write"
        parts.append(f"{codes} code{'' if codes == 1 else 's'} {done}")
    if counts.sealed:
        parts.append(f"{counts.sealed} in a closed period")
    if counts.before_floor:
        parts.append(f"{counts.before_floor} before {IMPORT_FLOOR.year}")
    parts.append(f"{counts.refused} refused")
    return "  ·  ".join(parts)


def legs_line(placed: list[Placed]) -> str:
    counts: dict[str, int] = {}
    for p in placed:
        counts[p.sent.account_name] = counts.get(p.sent.account_name, 0) + 1
    return " · ".join(f"{n} → {name}" for name, n in counts.items())


def excess_lines(excess: list[ExcessGroup]) -> list[str]:
    if not excess:
        return []
    # The engine's `excess`: a day and amount the file reports where the
    # ledger still holds a row no file row claimed — equal counts included,
    # since that row and a `new` one may be the same movement in two wordings.
    # One line per day, the count of unmatched ledger rows up front
    # (docs/mockups/expense-world-bank-import-10b.html).
    n = sum(e.unclaimed for e in excess)
    lines = [
        excess_head(excess),
        f"  before --apply, {'it' if n == 1 else 'one'} may be logged twice",
    ]
    for e in excess:
        where = f"{e.date_iso} · {format_cents(e.amount_cents)} · {e.account_name}"
        lines.append(f"    {e.unclaimed} on {where}")
    return lines


def render_footer(placed: list[Placed], *, applied: bool) -> None:
    """What `--apply` did, or what it would do."""
    new = [p for p in placed if p.outcome == "new"]
    codes = sum(1 for p in placed if p.backfill_code)
    typer.echo("")
    if applied:
        if new:
            typer.echo(f"  {len(new)} written · {legs_line(new)} · all under @Pendiente")
        else:
            typer.echo("  Nothing new to write — the ledger already has every row of this file.")
        if codes:
            typer.echo(
                f"  {codes} operation code{'' if codes == 1 else 's'} written onto existing rows"
            )
        if new:
            typer.echo("  Categorise them: expense world → Home → @Pendiente → ⏎")
        return
    if codes:
        rows_word = f"{codes} matched row{'' if codes == 1 else 's'}"
        typer.echo(f"  {rows_word} in the ledger have no operation code yet — --apply writes it.")
    if new:
        typer.echo("  New rows land under @Pendiente: " + legs_line(new) + ".")
        rows_word = f"{len(new)} new row{'' if len(new) == 1 else 's'}"
        typer.echo(f"  Nothing written. Pass --apply to write the {rows_word}.")
    else:
        typer.echo("  Nothing written — the ledger already has every row of this file.")


def render_refusal(err: EngineError, prepared: Prepared) -> None:
    """A `422` refuses the whole file: the envelope as the engine sent it,
    then each refused row under the FILE's line, not the engine's index."""
    typer.echo(f"Error: {err.code} — {err.message}", err=True)
    for line, field, message in row_refusals(err.fields, prepared.sent):
        where = f"row {line} ({field})" if line is not None else field
        typer.echo(f"  ! {where}: {message}", err=True)
    typer.echo("  Nothing was written.", err=True)


def _check_answer(response: dict, prepared: Prepared, *, applied: bool) -> list[Placed]:
    """Every sent row answered, or exit 1 saying so — never a count that is
    quietly short."""
    try:
        return placements(response, prepared.sent)
    except IncompleteAnswer as gap:
        typer.echo(f"Error: {incomplete_sentence(gap, prepared)}", err=True)
        for s in gap.missing:
            typer.echo(f"  ! row {s.row.line}: no answer", err=True)
        if applied:
            typer.echo(
                "  The import may have been written. Run the same file again without "
                "--apply to see what the ledger holds now.",
                err=True,
            )
        raise typer.Exit(code=1) from gap


def _stderr_notes(prepared: Prepared) -> None:
    """Under `--json`, stdout is the engine's body alone; what the client
    held back is said on stderr."""
    if prepared.before_floor:
        n = len(prepared.before_floor)
        typer.echo(f"{n} row{'' if n == 1 else 's'} dated before {IMPORT_FLOOR} not sent", err=True)
    for b in prepared.bad:
        typer.echo(f"! row {b.line}: {b.reason}", err=True)


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------
@handle_errors
def bank(
    ctx: typer.Context,
    file: str = typer.Argument(..., help="The bank's .xlsx download (sheet `data`)."),
    account: str | None = typer.Option(
        None,
        "--account",
        help="Which account the file belongs to, by name (a card's base name covers both "
        "currencies). Omit to be asked.",
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Write the new rows. Default is a dry-run preview."
    ),
    show_all: bool = typer.Option(False, "--all", help="Print every row, not the first 8."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit the engine's import response verbatim."
    ),
) -> None:
    """Import a bank download (dry-run by default); new rows land under @Pendiente.

    Reads the bank's sheet, asks which account it is (every run, unless
    --account names it), and sends every row dated 2026-01-01 or later
    to the engine, which compares it with what the ledger already holds: by
    the bank's operation number when the file has one, otherwise by day,
    amount and title, with a one-day tolerance. Only rows the ledger does not
    have are written, without a category, so they show up under @Pendiente.
    Rows inside a closed reconciliation period are listed, never written.
    At most 500 rows per file.

    Example: expense import bank ~/Downloads/"VISA Infinite Sapphire.xlsx"

    Example: expense import bank ~/Downloads/"Sueldo Soles.xlsx" --apply
    """
    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    prepared = prepare(cfg, file=file, account_flag=account, quiet=json_output, verbose=verbose)

    try:
        response = post_import(cfg, prepared, dry_run=not apply, verbose=verbose)
    except EngineError as err:
        if json_output or err.status != 422:
            raise  # handle_errors: the raw body under --json, the envelope otherwise
        render_refusal(err, prepared)
        raise typer.Exit(code=1) from err

    refused = bool(prepared.bad)
    if json_output:
        emit_json(response)
        _stderr_notes(prepared)
        _check_answer(response, prepared, applied=apply)
    else:
        placed = _check_answer(response, prepared, applied=apply)
        names, names_error = period_names(cfg, placed, verbose=verbose)
        render_result(
            prepared,
            placed,
            excess_groups(response, prepared.group.leg_names),
            names,
            show_all=show_all,
            applied=apply,
        )
        if names_error:
            typer.echo(f"  ! could not read the closed periods' names: {names_error}")
        render_footer(placed, applied=apply)
    if apply and refused:
        raise typer.Exit(code=1)
