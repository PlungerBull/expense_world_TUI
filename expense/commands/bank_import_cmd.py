"""`expense import bank <file.xlsx>` — a bank download → the ledger, under @Pendiente.

The flow: read the sheet, ask which account (remembered
per file name after the first run), then hand every row to the engine's
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

from dataclasses import dataclass
from pathlib import Path

import typer

from expense import config as config_module
from expense.bank_import.engine import (
    IMPORT_FLOOR,
    IMPORT_MAX_ROWS,
    RULE_LABELS,
    ExcessGroup,
    IncompleteAnswer,
    Placed,
    SentRow,
    excess_groups,
    match_label,
    placements,
    request_body,
    row_refusals,
    sealed_accounts,
    sent_rows,
    split_floor,
)
from expense.bank_import.parse import SHEET_NAME, BadRow, BankFormatError, BankRow, parse_bank_sheet
from expense.commands import _resource, accounts_cmd, reconcile_cmd
from expense.commands._resource import format_cents, items_of, render_table
from expense.context import get_verbose
from expense.currencies import SUPPORTED_CURRENCIES
from expense.errors import EngineConnectionError, EngineError, format_error, handle_errors
from expense.http import ExpenseClient
from expense.import_.reader import ImportDependencyError, ImportFileError, read_workbook
from expense.jsonout import emit_json

#: Rows the preview prints before folding the rest behind `--all`.
PREVIEW_ROWS = 8

#: The bank's currency labels, for the summary line — the reverse of parse's map.
CURRENCY_LABEL = {"PEN": "S/", "USD": "$"}


@dataclass(frozen=True)
class AccountGroup:
    """One answer to "which account": a bare account, or a card with a leg per
    currency. `legs` maps currency → (id, name)."""

    base: str
    legs: dict[str, tuple[str, str]]

    @property
    def label(self) -> str:
        if len(self.legs) == 1:
            return next(iter(self.legs.values()))[1]
        return f"{self.base}     {' + '.join(sorted(self.legs))}"


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


def base_name(name: str, currency: str) -> str:
    """`BCP Signature PEN` + PEN → `BCP Signature`; a name with no currency
    suffix is its own base."""
    tokens = name.split()
    if len(tokens) > 1 and tokens[-1].upper() == currency:
        return " ".join(tokens[:-1])
    return name


def account_groups(accounts: list[dict]) -> list[AccountGroup]:
    """Live, non-person accounts folded by base name, in their sort order."""
    order: list[str] = []
    legs: dict[str, dict[str, tuple[str, str]]] = {}
    for a in accounts:
        if not a.get("id") or a.get("is_archived") or a.get("is_person"):
            continue
        currency = str(a.get("currency_code") or "").upper()
        if currency not in SUPPORTED_CURRENCIES:
            continue
        base = base_name(str(a.get("name") or ""), currency)
        if base not in legs:
            legs[base] = {}
            order.append(base)
        # First one wins on a collision — two PEN accounts sharing a base is
        # a naming accident the picker cannot resolve; the second stays
        # reachable under its full name via --account.
        legs[base].setdefault(currency, (a["id"], a.get("name") or base))
    return [AccountGroup(base, legs[base]) for base in order]


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
    file_key: str,
    cfg,
    account_flag: str | None,
    quiet: bool = False,
) -> AccountGroup:
    """`--account` wins; then the remembered pick for this file name; then a
    prompt on a TTY. Whatever was chosen is remembered for next time.

    `quiet` (JSON mode) prints nothing and never prompts — the answer has to
    come from the flag or the memory, or the run fails like a non-TTY one.
    """
    say = (lambda _text: None) if quiet else typer.echo
    if account_flag is not None:
        group = _find_group(groups, account_flag)
        if group is None:
            _fail(f"no account named {account_flag!r}. Known: " + ", ".join(g.base for g in groups))
        _remember(cfg, file_key, account_flag)
        say(f"  Account: {group.base}")
        return group

    remembered = (cfg.bank_files or {}).get(file_key)
    if remembered:
        group = _find_group(groups, remembered)
        if group is not None:
            say(
                f'  Account: {group.base} (remembered for "{file_key}"; pass --account to override)'
            )
            return group
        say(f"  (the remembered account {remembered!r} no longer exists)")

    # Looked up through the module so the test seam (`_resource.stdin_is_tty`)
    # is the one the prompt actually consults.
    if quiet or not _resource.stdin_is_tty():
        _fail(
            "--account is required in non-interactive mode (nothing is remembered for this file)."
        )
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
    _remember(cfg, file_key, picked.base)
    return picked


def _remember(cfg, file_key: str, base: str) -> None:
    files = dict(cfg.bank_files or {})
    if files.get(file_key) == base:
        return
    files[file_key] = base
    cfg.bank_files = files
    config_module.save(cfg)


# ---------------------------------------------------------------------------
# reading the file: parse, pick the account, apply the floor
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Prepared:
    """Everything decided before the engine is asked: the rows that go, and
    the ones that do not (refused by the parser, or under the floor)."""

    file: str
    group: AccountGroup
    rows: list[BankRow]
    bad: list[BadRow]
    before_floor: list[BankRow]
    sent: list[SentRow]

    @property
    def has_codes(self) -> bool:
        return any(r.operation_code for r in self.rows)


def prepare(cfg, *, file: str, account_flag: str | None, quiet: bool, verbose: bool) -> Prepared:
    """Read the sheet, settle which account it belongs to, drop the rows under
    the floor and refuse a file too long for one request. Reads only.

    `quiet` suppresses the human banner and the account prompt's chatter,
    which is what `--json` wants.
    """
    try:
        sheet = read_workbook(file, sheet_name=SHEET_NAME)
        rows, bad = parse_bank_sheet(sheet)
    except (ImportDependencyError, ImportFileError, BankFormatError) as exc:
        _fail(str(exc))
    if not rows and not bad:
        _fail("the sheet has no rows.")

    currencies = sorted({r.currency for r in rows})
    if rows and not quiet:
        typer.echo("  " + _file_banner(rows, bad))

    accounts = items_of(accounts_cmd.fetch_accounts(cfg, include_people=False, verbose=verbose))
    groups = account_groups(accounts)
    if not groups:
        _fail("no accounts exist yet — create one first (expense accounts create).")
    group = choose_group(
        groups, file_key=Path(file).stem, cfg=cfg, account_flag=account_flag, quiet=quiet
    )

    missing = [c for c in currencies if c not in group.legs]
    if missing:
        held = " and ".join(sorted(group.legs)) or "nothing"
        n = sum(1 for r in rows if r.currency in missing)
        _fail(
            f"{group.base} holds {held} only, and this file has {n} row{'' if n == 1 else 's'} in "
            f"{' and '.join(missing)}. Pick the card that has both, or an account in that currency."
        )

    kept, before_floor = split_floor(rows)
    if len(kept) > IMPORT_MAX_ROWS:
        _fail(
            f"this file has {len(kept)} rows to import; one import takes at most "
            f"{IMPORT_MAX_ROWS}. Export a shorter date range from the bank and import each part."
        )
    if not kept:
        for b in bad:
            typer.echo(f"  ! row {b.line}: {b.reason}", err=True)
        _fail(f"nothing to import — no row of this file is dated {IMPORT_FLOOR} or later.")
    return Prepared(
        file=file,
        group=group,
        rows=rows,
        bad=bad,
        before_floor=before_floor,
        sent=sent_rows(kept, group.legs),
    )


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


# ---------------------------------------------------------------------------
# the one call
# ---------------------------------------------------------------------------
def post_import(cfg, prepared: Prepared, *, dry_run: bool, verbose: bool) -> dict:
    """`POST /transactions/import`. The apply is this one call, not a dry run
    followed by a write: its response is what happened. The client's
    idempotency key covers a retry.

    The client's default read timeout (60 s). Measured against the
    local engine: a 500-row dry run answers in 0.05 s, and an apply adds at
    most 500 inserts in one transaction."""
    with ExpenseClient(cfg, verbose=verbose) as client:
        return client.post(
            "/transactions/import", json_body=request_body(prepared.sent, dry_run=dry_run)
        )


def period_names(cfg, placed: list[Placed], *, verbose: bool) -> tuple[dict[str, str], str | None]:
    """reconciliation id → name, for the legs with a row inside a closed
    period (the response carries ids only). A failed read never hides what
    the import did: the rows still print, under "a closed period", and the
    reason is returned for one line under the table."""
    names: dict[str, str] = {}
    for account_id in sealed_accounts(placed):
        try:
            body = reconcile_cmd.fetch_reconciliations(cfg, account_id=account_id, verbose=verbose)
        except (EngineError, EngineConnectionError) as err:
            return names, format_error(err)
        for item in items_of(body):
            if item.get("id"):
                names[str(item["id"])] = str(item.get("name") or item["id"])
    return names, None


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
    total = len(prepared.rows) + len(prepared.bad)
    new = sum(1 for p in placed if p.outcome == "new")
    matched = [p for p in placed if p.outcome == "matched"]
    sealed = sum(1 for p in placed if p.outcome == "sealed")
    by_rule: dict[str, int] = {}
    for p in matched:
        by_rule[p.rule or ""] = by_rule.get(p.rule or "", 0) + 1
    # Strongest rule first, always, so the breakdown reads the same for every
    # file instead of following whichever rule claimed the first row.
    detail = " · ".join(
        f"{by_rule[rule]} by {label}" for rule, label in RULE_LABELS.items() if by_rule.get(rule)
    )
    parts = [f"{total} rows", f"{new} new", f"{len(matched)} in the ledger"]
    if detail:
        parts[-1] += f" ({detail})"
    codes = sum(1 for p in placed if p.backfill_code)
    if codes:
        done = "written" if applied else "to write"
        parts.append(f"{codes} code{'' if codes == 1 else 's'} {done}")
    if sealed:
        parts.append(f"{sealed} in a closed period")
    if prepared.before_floor:
        parts.append(f"{len(prepared.before_floor)} before {IMPORT_FLOOR.year}")
    parts.append(f"{len(prepared.bad)} refused")
    return "  ·  ".join(parts)


def legs_line(placed: list[Placed]) -> str:
    counts: dict[str, int] = {}
    for p in placed:
        counts[p.sent.account_name] = counts.get(p.sent.account_name, 0) + 1
    return " · ".join(f"{n} → {name}" for name, n in counts.items())


def sealed_lines(placed: list[Placed], names: dict[str, str]) -> list[str]:
    """Rows inside a closed period, as their own block: never written, and
    shown so a bank restating something in a closed month is noticed."""
    sealed = [p for p in placed if p.outcome == "sealed"]
    if not sealed:
        return []
    n = len(sealed)
    lines = [
        f"! {n} row{'' if n == 1 else 's'} fall{'s' if n == 1 else ''} inside a closed "
        f"period and never go{'es' if n == 1 else ''} in — revert the period to add them"
    ]
    for p in sealed:
        row = p.sent.row
        period = names.get(p.sealed_by or "", "a closed period")
        lines.append(
            f"    row {row.line} · {row.date_iso} · {row.title} · "
            f"{format_cents(row.amount_cents)} · {p.sent.account_name} — {period}"
        )
    return lines


def excess_lines(excess: list[ExcessGroup]) -> list[str]:
    if not excess:
        return []
    # The engine's `excess`: a day and amount the file reports where the
    # ledger still holds a row no file row claimed — equal counts included,
    # since that row and a `new` one may be the same movement in two wordings.
    # One line per day, the count of unmatched ledger rows up front
    # (docs/mockups/expense-world-bank-import-10b.html).
    n = sum(e.unclaimed for e in excess)
    rows_word = f"{n} ledger row{'' if n == 1 else 's'}"
    lines = [
        f"! {rows_word} no file row matched — check",
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
        n = len(prepared.sent)
        typer.echo(
            f"Error: the engine answered {n - len(gap.missing)} of the {n} rows sent"
            + (f", plus {len(gap.unknown)} it was never sent" if gap.unknown else "")
            + " — nothing below would be complete, so nothing is shown.",
            err=True,
        )
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
        "currencies). Remembered per file name; omit to reuse or be asked.",
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

    Reads the bank's sheet, asks which account it is (remembered per file
    name after the first run), and sends every row dated 2026-01-01 or later
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
        legs = {i: n for i, n in prepared.group.legs.values()}
        render_result(
            prepared,
            placed,
            excess_groups(response, legs),
            names,
            show_all=show_all,
            applied=apply,
        )
        if names_error:
            typer.echo(f"  ! could not read the closed periods' names: {names_error}")
        render_footer(placed, applied=apply)
    if apply and refused:
        raise typer.Exit(code=1)
