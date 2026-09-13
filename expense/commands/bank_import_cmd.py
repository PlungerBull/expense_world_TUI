"""`expense import bank <file.xlsx>` — a bank download → the ledger, under @Pendiente.

The flow, as drawn in docs/mockups/expense-world-bank-import.html and picked
2026-09-12: read the sheet, ask which account (remembered per file name after
the first run — option B), fetch what the ledger holds for that account over
the file's dates, place every row (expense/bank_import/match.py), show the
preview, and on `--apply` write only the new rows in one batch. A group where
the ledger holds more than the file is a loud warning (option D): it is the
one way an earlier double entry surfaces.

Why the account is asked and not read: the file does not say. The bank names
the file after the product ("VISA Infinite Sapphire") and the sheet after
nothing; the card's PEN and USD rows share one file, so the pick is the card
and the currency column chooses the leg per row.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import typer

from expense import config as config_module
from expense.bank_import.match import Excess, LedgerRow, Verdict, match_rows
from expense.bank_import.parse import SHEET_NAME, BadRow, BankFormatError, BankRow, parse_bank_sheet
from expense.batch_write import RowResult, post_transaction_batch
from expense.commands import _resource, accounts_cmd, transactions_cmd
from expense.commands._resource import fetch_all_pages, format_cents, items_of, render_table
from expense.context import get_verbose
from expense.currencies import SUPPORTED_CURRENCIES
from expense.dates import to_canonical_aware
from expense.errors import EngineError, format_error, handle_errors
from expense.http import ExpenseClient
from expense.import_.reader import ImportDependencyError, ImportFileError, read_workbook

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


def _local_date(iso_timestamp: str) -> str:
    """The calendar day a ledger row belongs to, in the machine's zone — the
    same zone the bank row's midnight is written in."""
    return (
        datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00")).astimezone().date().isoformat()
    )


def fetch_ledger(
    cfg, legs: dict[str, tuple[str, str]], rows: list[BankRow], *, verbose: bool
) -> list[LedgerRow]:
    """Every live row of the leg accounts over the file's dates ± the tolerance."""
    if not rows:
        return []
    days = [date.fromisoformat(r.date_iso) for r in rows]
    date_from = to_canonical_aware((min(days) - timedelta(days=2)).isoformat())
    date_to = to_canonical_aware(f"{(max(days) + timedelta(days=2)).isoformat()} 23:59:59")
    out: list[LedgerRow] = []
    for account_id, _name in legs.values():
        items = fetch_all_pages(
            lambda limit, offset, aid=account_id: transactions_cmd.fetch_transactions(
                cfg,
                account=aid,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
                verbose=verbose,
            )
        )
        for it in items:
            if not isinstance(it.get("id"), str) or not isinstance(it.get("date"), str):
                continue
            out.append(
                LedgerRow(
                    id=it["id"],
                    account_id=str(it.get("account_id")),
                    date_iso=_local_date(it["date"]),
                    amount_cents=int(it.get("amount_cents") or 0),
                    title=it.get("title"),
                    operation_code=it.get("operation_code"),
                )
            )
    return out


def payload_for(verdict: Verdict) -> dict:
    """`POST /transactions` body for a new row: no category (→ @Pendiente), no
    tags, the raw descriptor kept as the description."""
    row = verdict.row
    body: dict = {
        "id": str(uuid4()),
        "amount_cents": row.amount_cents,
        "account_id": verdict.account_id,
        "date": to_canonical_aware(row.date_iso),
        "title": row.title,
        "description": row.raw_title,
    }
    if row.operation_code is not None:
        body["operation_code"] = row.operation_code
    return body


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def _match_cell(v: Verdict) -> str:
    if v.new:
        return "new"
    if v.rule == "operation":
        return f"in ledger · operation {v.row.operation_code}"
    suffix = " · +code" if v.backfill_code else ""
    return f"in ledger · {v.rule}{suffix}"


def render_preview(
    verdicts: list[Verdict],
    bad: list[BadRow],
    excess: list[Excess],
    *,
    show_all: bool,
    has_codes: bool,
) -> None:
    shown = verdicts if show_all else verdicts[:PREVIEW_ROWS]
    headers = {
        "n": "#",
        "date": "date",
        "title": "title",
        "amount": "amount",
        "account": "→ account",
    }
    if has_codes:
        headers["op"] = "op"
    headers["match"] = "match"
    table: list[dict[str, str]] = []
    for i, v in enumerate(shown, start=1):
        table.append(
            {
                "n": str(i),
                "date": v.row.date_iso,
                "title": v.row.title,
                "amount": format_cents(v.row.amount_cents),
                "account": v.account_name,
                "op": v.row.operation_code or "—",
                "match": _match_cell(v),
            }
        )
    typer.echo("")
    render_table(headers, table, align_right={"n", "amount"})
    if len(verdicts) > len(shown):
        typer.echo(f"  … {len(verdicts) - len(shown)} more · pass --all to print every row")
    typer.echo("")
    typer.echo("  " + summary_line(verdicts, bad))
    new = [v for v in verdicts if v.new]
    if new:
        typer.echo("  New rows land under @Pendiente: " + legs_line(new) + ".")
    codes = sum(1 for v in verdicts if v.backfill_code)
    if codes:
        rows_word = f"{codes} matched row{'' if codes == 1 else 's'}"
        typer.echo(f"  {rows_word} in the ledger have no operation code yet — --apply writes it.")
    for line in excess_lines(excess):
        typer.echo("  " + line)
    for b in bad:
        typer.echo(f"  ! row {b.line}: {b.reason}")


def summary_line(verdicts: list[Verdict], bad: list[BadRow]) -> str:
    new = sum(1 for v in verdicts if v.new)
    matched = [v for v in verdicts if not v.new]
    by_rule: dict[str, int] = {}
    for v in matched:
        by_rule[v.rule or ""] = by_rule.get(v.rule or "", 0) + 1
    detail = " · ".join(f"{n} by {rule}" for rule, n in by_rule.items()) if matched else ""
    parts = [f"{len(verdicts) + len(bad)} rows", f"{new} new", f"{len(matched)} in the ledger"]
    if detail:
        parts[-1] += f" ({detail})"
    parts.append(f"{len(bad)} refused")
    return "  ·  ".join(parts)


def legs_line(new: list[Verdict]) -> str:
    counts: dict[str, int] = {}
    for v in new:
        counts[v.account_name] = counts.get(v.account_name, 0) + 1
    return " · ".join(f"{n} → {name}" for name, n in counts.items())


def excess_lines(excess: list[Excess]) -> list[str]:
    if not excess:
        return []
    n = len(excess)
    groups = f"{n} group{'' if n == 1 else 's'} ha{'s' if n == 1 else 've'}"
    lines = [f"! {groups} more in the ledger than in the file — a row may be logged twice"]
    for e in excess:
        where = f"{e.date_iso} · {format_cents(e.amount_cents)} · {e.account_name}"
        lines.append(f"    {where} — ledger {e.ledger_count}, file {e.file_count}")
    return lines


def _json_doc(file: str, group: AccountGroup, verdicts, bad, excess, written=None) -> dict:
    return {
        "file": file,
        "account": group.base,
        "legs": {c: {"id": i, "name": n} for c, (i, n) in group.legs.items()},
        "rows": [
            {
                "line": v.row.line,
                "date": v.row.date_iso,
                "title": v.row.title,
                "description": v.row.raw_title,
                "amount_cents": v.row.amount_cents,
                "currency": v.row.currency,
                "operation_code": v.row.operation_code,
                "account_id": v.account_id,
                "match": v.rule,
                "ledger_id": v.ledger_id,
                "backfill_code": v.backfill_code,
            }
            for v in verdicts
        ],
        "refused": [{"line": b.line, "reason": b.reason} for b in bad],
        "excess": [
            {
                "account": e.account_name,
                "date": e.date_iso,
                "amount_cents": e.amount_cents,
                "ledger": e.ledger_count,
                "file": e.file_count,
            }
            for e in excess
        ],
        "written": written,
    }


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
    json_output: bool = typer.Option(False, "--json", help="Emit the placement as JSON."),
) -> None:
    """Import a bank download (dry-run by default); new rows land under @Pendiente.

    Reads the bank's sheet, asks which account it is (remembered per file
    name after the first run), and compares every row with what the ledger
    already holds for that account: by the bank's operation number when the
    file has one, otherwise by date, amount, account and title with a one-day
    tolerance and a count per group. Only rows the ledger does not have are
    written, without a category, so they show up in the pendiente filter.

    Example: expense import bank ~/Downloads/"VISA Infinite Sapphire.xlsx"

    Example: expense import bank ~/Downloads/"Sueldo Soles.xlsx" --apply
    """
    try:
        sheet = read_workbook(file, sheet_name=SHEET_NAME)
        rows, bad = parse_bank_sheet(sheet)
    except (ImportDependencyError, ImportFileError, BankFormatError) as exc:
        _fail(str(exc))
    if not rows and not bad:
        _fail("the sheet has no rows.")

    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)
    currencies = sorted({r.currency for r in rows})
    if rows:
        days = sorted(r.date_iso for r in rows)
        counts = " · ".join(
            f"{CURRENCY_LABEL.get(c, c)} {sum(1 for r in rows if r.currency == c)}"
            for c in currencies
        )
        codes = " · operation numbers on every row" if all(r.operation_code for r in rows) else ""
        if not json_output:
            typer.echo(f"  {len(rows) + len(bad)} rows · {days[0]} → {days[-1]} · {counts}{codes}")

    accounts = items_of(accounts_cmd.fetch_accounts(cfg, include_people=False, verbose=verbose))
    groups = account_groups(accounts)
    if not groups:
        _fail("no accounts exist yet — create one first (expense accounts create).")
    file_key = Path(file).stem
    group = choose_group(
        groups, file_key=file_key, cfg=cfg, account_flag=account, quiet=json_output
    )

    missing = [c for c in currencies if c not in group.legs]
    if missing:
        held = " and ".join(sorted(group.legs)) or "nothing"
        n = sum(1 for r in rows if r.currency in missing)
        _fail(
            f"{group.base} holds {held} only, and this file has {n} row{'' if n == 1 else 's'} in "
            f"{' and '.join(missing)}. Pick the card that has both, or an account in that currency."
        )

    ledger = fetch_ledger(cfg, group.legs, rows, verbose=verbose)
    verdicts, excess = match_rows(rows, group.legs, ledger)
    has_codes = any(r.operation_code for r in rows)

    if not apply:
        if json_output:
            typer.echo(
                json.dumps(
                    _json_doc(file, group, verdicts, bad, excess), indent=2, ensure_ascii=False
                )
            )
            return
        render_preview(verdicts, bad, excess, show_all=show_all, has_codes=has_codes)
        new = sum(1 for v in verdicts if v.new)
        typer.echo("")
        if new:
            rows_word = f"{new} new row{'' if new == 1 else 's'}"
            typer.echo(f"  Nothing written. Pass --apply to write the {rows_word}.")
        else:
            typer.echo("  Nothing written — the ledger already has every row of this file.")
        return

    new = [v for v in verdicts if v.new]
    backfill = [v for v in verdicts if v.backfill_code]
    if not json_output:
        typer.echo("  " + summary_line(verdicts, bad))
        for line in excess_lines(excess):
            typer.echo("  " + line)

    # The backfill: a matched ledger row that has no code gets the file's.
    # One PUT per row — there is no batch update — and a refusal is reported
    # by row, never fatal for the rest.
    coded = 0
    code_failures: list[tuple[Verdict, str]] = []
    if backfill:
        with ExpenseClient(cfg, verbose=verbose) as client:
            for v in backfill:
                try:
                    client.put(
                        f"/transactions/{v.ledger_id}",
                        json_body={"operation_code": v.backfill_code},
                    )
                    coded += 1
                except EngineError as err:
                    code_failures.append((v, format_error(err)))
        if not json_output:
            typer.echo(
                f"  {coded} operation code{'' if coded == 1 else 's'} written onto existing rows"
            )
            for v, message in code_failures:
                typer.echo(f"  ! row {v.row.line} (code {v.backfill_code}): {message}")

    if not new:
        if json_output:
            doc = _json_doc(file, group, verdicts, bad, excess, written=0)
            doc["codes_written"] = coded
            typer.echo(json.dumps(doc, indent=2, ensure_ascii=False))
        else:
            typer.echo("  Nothing new to write — the ledger already has every row of this file.")
        if code_failures:
            raise typer.Exit(code=1)
        return

    items = [payload_for(v) for v in new]
    with ExpenseClient(cfg, verbose=verbose, timeout_read=300.0) as client:
        outcome = post_transaction_batch(client, items)

    written = outcome.count(RowResult.CREATED)
    existed = outcome.count(RowResult.EXISTED)
    failed = [(new[i], msg) for i, msg in outcome.errors.items()]
    if json_output:
        doc = _json_doc(file, group, verdicts, bad, excess, written=written)
        doc["already_there"] = existed
        doc["failed"] = [{"line": v.row.line, "error": m} for v, m in failed]
        doc["codes_written"] = coded
        typer.echo(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        typer.echo("")
        line = f"  {written} written"
        if written:
            line += " · " + legs_line(
                [v for i, v in enumerate(new) if outcome.results[i] is RowResult.CREATED]
            )
            line += " · all under @Pendiente"
        typer.echo(line)
        if existed:
            typer.echo(f"  {existed} already there — the engine holds that operation number")
        for v, message in failed:
            typer.echo(f"  ! row {v.row.line}: {message}")
        if outcome.stopped:
            typer.echo(
                f"  ! stopped: {outcome.stop_error} — {len(outcome.unsent)} rows were never sent"
            )
        if written:
            typer.echo("  Categorise them: expense world → Transactions → p")
    if failed or outcome.stopped or code_failures:
        raise typer.Exit(code=1)
