"""`expense import <file>` — bulk-import transactions from an .xlsx.

Dry-run by default: parses the sheet and prints what it would do, writing
nothing. With --apply, resolves-or-creates accounts/categories/hashtags by name
and writes transactions through the atomic batch endpoint.
"""

from collections import Counter

import typer

from expense import config as config_module
from expense.batch_write import CHUNK_SIZE, ENGINE_BATCH_MAX
from expense.context import get_verbose
from expense.currencies import MINOR_UNIT_SCALE
from expense.errors import handle_errors
from expense.http import ExpenseClient
from expense.import_ import apply as apply_mod
from expense.import_ import plan as plan_mod
from expense.import_.parse import ImportFormatError, parse_sheet
from expense.import_.reader import ImportDependencyError, ImportFileError, read_workbook
from expense.jsonout import emit_json


# sanctioned exception — see cli-spec.md "Sanctioned exceptions": import's
# --json (plan and result below) is client-composed; the pipeline aggregates
# many engine calls, so there is no single engine response to pass through.
def _render_plan(plan: plan_mod.ImportPlan, *, json_output: bool) -> None:
    if json_output:
        emit_json(
            {
                "valid_rows": len(plan.rows),
                "skipped": [
                    {"line": s.line, "reason": s.reason, "detail": s.detail} for s in plan.skipped
                ],
                "accounts": [
                    {"name": a.name, "currency": a.currency, "source_name": a.source_name}
                    for a in plan.accounts
                ],
                "categories": plan.categories,
                "hashtags": plan.hashtags,
                "opening_balances": [
                    {
                        "line": o.line,
                        "account": o.account,
                        "currency": o.currency,
                        "amount_cents": o.amount_cents,
                        "date": o.date_iso,
                    }
                    for o in plan.openings
                ],
            }
        )
        return

    typer.echo(f"Parsed {len(plan.rows)} transactions to import.")
    if plan.skipped:
        counts = Counter(s.reason for s in plan.skipped)
        detail = ", ".join(f"{reason}: {n}" for reason, n in sorted(counts.items()))
        typer.echo(f"Skipped {len(plan.skipped)} row(s) — {detail}")

    typer.echo(f"\nAccounts to ensure ({len(plan.accounts)}):")
    for spec in sorted(plan.accounts, key=lambda s: (s.name.casefold(), s.currency)):
        # A name that spans currencies is split into one account per currency
        # and renamed, and --account-name renames a leg outright; show where
        # each renamed leg came from so this list is self-explaining.
        origin = f'  (from "{spec.source_name}")' if spec.name != spec.source_name else ""
        typer.echo(f"  {spec.name} [{spec.currency}]{origin}")

    typer.echo(f"\nCategories to ensure ({len(plan.categories)}):")
    typer.echo(f"  {', '.join(sorted(plan.categories))}")
    typer.echo(f"\nHashtags to ensure ({len(plan.hashtags)}):")
    typer.echo(f"  {', '.join(sorted(plan.hashtags))}")

    if plan.openings:
        typer.echo(f"\nOpening balances to seed ({len(plan.openings)}):")
        for o in sorted(plan.openings, key=lambda r: (r.account.casefold(), r.currency)):
            sign = "-" if o.amount_cents < 0 else ""
            whole, frac = divmod(abs(o.amount_cents), MINOR_UNIT_SCALE)
            major = f"{whole:,}.{frac:02d}"
            typer.echo(f"  {o.account} [{o.currency}]: {sign}{major} on {o.date_iso}")


_ACCOUNT_NAME_HINT = "'--account-name'"


def _parse_account_name(value: str) -> tuple[str, str, str]:
    """`"BCP:PEN=Sueldo Soles"` → `("BCP", "PEN", "Sueldo Soles")`.

    The ledger name is everything after the first `=`; the currency is what
    follows the last `:` before it, so a sheet name may itself hold a colon.
    """
    left, eq, ledger = value.partition("=")
    sheet, colon, currency = left.rpartition(":")
    sheet, currency, ledger = sheet.strip(), currency.strip().upper(), ledger.strip()
    if not eq or not colon or not sheet or not currency or not ledger:
        raise typer.BadParameter(
            f'{value!r} is not SHEET_NAME:CURRENCY=LEDGER_NAME (e.g. "BCP:PEN=Sueldo Soles").',
            param_hint=_ACCOUNT_NAME_HINT,
        )
    return sheet, currency, ledger


def _key_of_saved(saved_key: str) -> tuple[str, str] | None:
    """A `sheet_account_names` key ("BCP:PEN") as a `plan.account_key`."""
    sheet, colon, currency = saved_key.rpartition(":")
    return plan_mod.account_key(sheet, currency) if colon and sheet and currency else None


def _account_names(
    saved: dict[str, str], flags: list[tuple[str, str, str]]
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """Merge the saved renames with this run's flags; a flag replaces a saved
    entry for the same sheet leg, whatever its casing. Returns the dict to
    save and the plan-side map keyed by `plan.account_key`."""
    merged = dict(saved)
    for sheet, currency, ledger in flags:
        leg = plan_mod.account_key(sheet, currency)
        for old in [k for k in merged if _key_of_saved(k) == leg]:
            del merged[old]
        merged[f"{sheet}:{currency}"] = ledger
    by_leg: dict[tuple[str, str], str] = {}
    for saved_key, ledger in merged.items():
        leg_of = _key_of_saved(saved_key)
        if leg_of is not None:
            by_leg[leg_of] = ledger
    return merged, by_leg


def _check_account_names(
    plan: plan_mod.ImportPlan,
    flags: list[tuple[str, str, str]],
    renamed: dict[tuple[str, str], str],
) -> None:
    """Refuse a flag naming a sheet leg the sheet does not have, and a rename
    that lands two sheet legs on one ledger account."""
    legs = {plan_mod.account_key(a.source_name, a.currency) for a in plan.accounts}
    for sheet, currency, _ledger in flags:
        if plan_mod.account_key(sheet, currency) not in legs:
            raise typer.BadParameter(
                f'the sheet has no account "{sheet}" in {currency}.',
                param_hint=_ACCOUNT_NAME_HINT,
            )
    seen: dict[tuple[str, str], plan_mod.AccountSpec] = {}
    for spec in plan.accounts:
        other = seen.setdefault(plan_mod.account_key(spec.name, spec.currency), spec)
        if other is spec:
            continue
        pair = {plan_mod.account_key(s.source_name, s.currency) for s in (spec, other)}
        if pair & renamed.keys():
            raise typer.BadParameter(
                f'"{other.source_name}" and "{spec.source_name}" would both be written as '
                f'"{spec.name}" [{spec.currency}].',
                param_hint=_ACCOUNT_NAME_HINT,
            )


def _render_result(result: apply_mod.ApplyResult, *, json_output: bool) -> None:
    res = result.resolve
    if json_output:
        emit_json(
            {
                "accounts_created": res.accounts_created,
                "accounts_reused": res.accounts_reused,
                "categories_created": res.categories_created,
                "categories_reused": res.categories_reused,
                "hashtags_created": res.hashtags_created,
                "hashtags_reused": res.hashtags_reused,
                "resolve_failures": res.resolve_failures,
                "tx_created": result.tx_created,
                "tx_skipped_existing": result.tx_skipped_existing,
                "tx_failed": result.tx_failed,
                "opening_created": result.opening_created,
                "opening_skipped_existing": result.opening_skipped_existing,
                "opening_failed": result.opening_failed,
                "failures": [{"chunk": c, "error": m} for c, m in result.failures],
            }
        )
        return

    typer.echo(f"Accounts:   created {res.accounts_created}, reused {res.accounts_reused}")
    typer.echo(f"Categories: created {res.categories_created}, reused {res.categories_reused}")
    typer.echo(f"Hashtags:   created {res.hashtags_created}, reused {res.hashtags_reused}")
    if res.resolve_failures:
        typer.echo(f"Resource failures ({len(res.resolve_failures)}):")
        for message in res.resolve_failures:
            typer.echo(f"  {message}")
    if result.opening_created or result.opening_skipped_existing or result.opening_failed:
        typer.echo(
            f"Opening balances: seeded {result.opening_created}, "
            f"already-present {result.opening_skipped_existing}, "
            f"failed {result.opening_failed}"
        )
    typer.echo(
        f"Transactions: created {result.tx_created}, "
        f"already-present {result.tx_skipped_existing}, failed {result.tx_failed}"
    )
    if result.failures:
        typer.echo("Failures:")
        for chunk_index, message in result.failures:
            where = "pre-flight" if chunk_index < 0 else f"chunk {chunk_index}"
            typer.echo(f"  {where}: {message}")


@handle_errors
def run_import(
    ctx: typer.Context,
    file: str = typer.Argument(..., help="Path to the .xlsx spreadsheet to import."),
    apply: bool = typer.Option(
        False, "--apply", help="Actually write to the engine. Default is a dry-run preview."
    ),
    chunk_size: int = typer.Option(
        CHUNK_SIZE,
        "--chunk-size",
        min=1,
        max=ENGINE_BATCH_MAX,
        help="Transactions per batch request.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit the plan/result as JSON."),
    account_name: list[str] = typer.Option(
        [],
        "--account-name",
        metavar="SHEET_NAME:CUR=LEDGER_NAME",
        help=(
            "Write a sheet account's CUR leg under another ledger name. Repeatable; "
            "remembered in the config for every later run."
        ),
    ),
) -> None:
    """Import transactions from an .xlsx spreadsheet (dry-run by default).

    Parses the sheet, then resolves-or-creates accounts/categories/hashtags by
    name and writes transactions in atomic batches. Without --apply it only
    prints what it would do and writes nothing.

    Rows marked "SALDO INICIAL" (case/space-insensitive) in EITHER the title or
    the category column are opening balances: they seed the account via the
    engine's opening-balance endpoint (@Opening system category, excluded from
    flow reports) instead of importing as ordinary transactions. Their
    category/hashtag cells may be blank and are discarded either way; one per
    account — extras are skipped as duplicate-opening in the preview.

    An account name used under more than one currency becomes one account per
    currency, each renamed with its currency suffix ("BCP Oro" holding PEN and
    USD rows becomes "BCP Oro PEN" and "BCP Oro USD"). The dry-run names the
    origin of every renamed leg.

    --account-name "SHEET_NAME:CUR=LEDGER_NAME" writes one sheet account's
    currency leg under a ledger name of your choosing instead ("BCP:PEN=Sueldo
    Soles"); the sheet name matches case- and space-insensitively. The rename
    is saved to the config and applied on every later run, so a re-run without
    the flag reuses the renamed account; passing it again for the same leg
    replaces the saved name. A leg the sheet does not have, or two legs landing
    on one ledger account, is a usage error and nothing is saved.

    Re-running --apply is safe for unchanged and appended sheets: transaction
    ids derive from each row's content plus its line number, so already-imported
    rows are skipped and new rows still land (a chunk mixing both falls back to
    row-by-row posts). Rows the engine rejects fall back the same way — valid
    rows land and each rejected row is reported with its sheet line. Inserting
    or deleting rows mid-sheet shifts every later line number — shifted rows get
    new ids and re-import as duplicates; append new rows at the bottom instead.
    Full re-runs of large already-imported sheets are slower (one request per
    row).

    Example: expense import sheet ~/Downloads/Presupuesto.xlsx

    Example: expense import sheet ~/Downloads/Presupuesto.xlsx --account-name "BCP:PEN=Sueldo Soles"
    """
    flags = [_parse_account_name(value) for value in account_name]
    try:
        sheet = read_workbook(file)
        parsed, openings, skipped = parse_sheet(sheet)
    except (ImportDependencyError, ImportFileError, ImportFormatError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    saved_cfg = config_module.load()
    saved = dict(saved_cfg.sheet_account_names) if saved_cfg is not None else {}
    merged, renamed = _account_names(saved, flags)
    plan = plan_mod.build_plan(parsed, openings, skipped, account_names=renamed)
    _check_account_names(plan, flags, renamed)
    # Remembered on a dry run too: the flag was checked against this sheet.
    # With no config yet there is nowhere to keep it; --apply needs one anyway.
    if saved_cfg is not None and merged != saved:
        saved_cfg.sheet_account_names = merged
        config_module.save(saved_cfg)

    if not apply:
        _render_plan(plan, json_output=json_output)
        if not json_output:
            typer.echo("\nDry run — nothing written. Re-run with --apply to write.")
        return

    cfg = config_module.ensure_loaded()
    verbose = get_verbose(ctx)
    # Batches of up to `chunk_size` rows can take a while on a cold/slow engine;
    # give the read timeout plenty of headroom beyond the 60s default.
    with ExpenseClient(cfg, verbose=verbose, timeout_read=300.0) as client:
        res = apply_mod.resolve_or_create(client, plan)
        result = apply_mod.apply_plan(client, plan, res, chunk_size=chunk_size)

    _render_result(result, json_output=json_output)
    if result.tx_failed > 0 or result.resolve.resolve_failures:
        raise typer.Exit(code=1)
