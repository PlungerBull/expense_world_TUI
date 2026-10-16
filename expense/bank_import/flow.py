"""The steps of a bank import every door shares: read the file, fold the
accounts into picks, place the rows on the pick's legs, make the one call, and
count the answer.

No typer and no printing: a refusal is `ImportRefused`, whose message is the
sentence the door shows.
"""

from dataclasses import dataclass

from expense import reads
from expense.bank_import.engine import (
    IMPORT_FLOOR,
    IMPORT_MAX_ROWS,
    IncompleteAnswer,
    Placed,
    SentRow,
    request_body,
    sealed_accounts,
    sent_rows,
    split_floor,
)
from expense.bank_import.parse import SHEET_NAME, BadRow, BankFormatError, BankRow, parse_bank_sheet
from expense.currencies import SUPPORTED_CURRENCIES
from expense.errors import EngineConnectionError, EngineError, format_error
from expense.formatting import format_cents
from expense.import_.reader import ImportFileError, read_workbook
from expense.reads import items_of


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

    @property
    def name(self) -> str:
        """What the account is called: the leg's own name, or a card's base."""
        if len(self.legs) == 1:
            return next(iter(self.legs.values()))[1]
        return self.base

    @property
    def currencies(self) -> str:
        """`PEN`, or `PEN + USD` for a card with a leg per currency."""
        return " + ".join(sorted(self.legs))

    @property
    def leg_names(self) -> dict[str, str]:
        """leg account id → its name, for naming the accounts of the engine's
        `day_mismatches`."""
        return {ident: name for ident, name in self.legs.values()}


def base_name(name: str, currency: str) -> str:
    """`BCP Signature PEN` + PEN → `BCP Signature`; a name with no currency
    suffix is its own base."""
    tokens = name.split()
    if len(tokens) > 1 and tokens[-1].upper() == currency:
        return " ".join(tokens[:-1])
    return name


def account_groups(accounts: list[dict]) -> list[AccountGroup]:
    """Live, non-person accounts folded by base name, each base where its first
    account stands in the order given — the engine's: `sort_order` ascending,
    then creation time, oldest first (contract: GET /v1/accounts, "Ordering")."""
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


# ---------------------------------------------------------------------------
# reading the file: parse, pick the account, apply the floor
# ---------------------------------------------------------------------------
class ImportRefused(Exception):
    """A file, or a file and an account pick, the import will not send.

    The message is the sentence both doors print. `list_bad` says the
    file's refused lines explain it (nothing left after the floor), so a door
    shows them before the sentence. A refused read keeps its cause
    (`BankFormatError`, `ImportFileError`, …) as `__cause__`.
    """

    def __init__(self, message: str, *, list_bad: bool = False) -> None:
        super().__init__(message)
        self.list_bad = list_bad


def read_bank_file(file: str) -> tuple[list[BankRow], list[BadRow]]:
    """The bank's sheet → (rows, refused lines). Reads only; raises
    ImportRefused when the file cannot be read or is not a bank export."""
    try:
        sheet = read_workbook(file, sheet_name=SHEET_NAME)
        rows, bad = parse_bank_sheet(sheet)
    except (ImportFileError, BankFormatError) as exc:
        raise ImportRefused(str(exc)) from exc
    if not rows and not bad:
        raise ImportRefused("the sheet has no rows.")
    return rows, bad


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


def prepared_for(
    file: str, group: AccountGroup, rows: list[BankRow], bad: list[BadRow]
) -> Prepared:
    """The file's rows on the picked account's legs, the floor applied — or
    ImportRefused when the pick has no leg for a currency, the file is too long
    for one request, or nothing is dated on or after the floor."""
    currencies = sorted({r.currency for r in rows})
    missing = [c for c in currencies if c not in group.legs]
    if missing:
        held = " and ".join(sorted(group.legs)) or "nothing"
        n = sum(1 for r in rows if r.currency in missing)
        raise ImportRefused(
            f"{group.base} holds {held} only, and this file has {n} row{'' if n == 1 else 's'} in "
            f"{' and '.join(missing)}. Pick the card that has both, or an account in that currency."
        )

    kept, before_floor = split_floor(rows)
    if len(kept) > IMPORT_MAX_ROWS:
        raise ImportRefused(
            f"this file has {len(kept)} rows to import; one import takes at most "
            f"{IMPORT_MAX_ROWS}. Export a shorter date range from the bank and import each part."
        )
    if not kept:
        raise ImportRefused(
            f"nothing to import — no row of this file is dated {IMPORT_FLOOR} or later.",
            list_bad=True,
        )
    return Prepared(
        file=file,
        group=group,
        rows=rows,
        bad=bad,
        before_floor=before_floor,
        sent=sent_rows(kept, group.legs),
    )


# ---------------------------------------------------------------------------
# the one call
# ---------------------------------------------------------------------------
def import_call(client, prepared: Prepared, *, dry_run: bool) -> dict:
    """`POST /transactions/import` on a client the caller opened — the one
    request both doors make. The apply is this one call, not a dry run
    followed by a write: its response is what happened. The client's
    idempotency key covers a retry.

    The client's default read timeout (60 s). Measured against the
    local engine: a 500-row dry run answers in 0.05 s, and an apply adds at
    most 500 inserts in one transaction."""
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
            body = reads.fetch_reconciliations(cfg, account_id=account_id, verbose=verbose)
        except (EngineError, EngineConnectionError) as err:
            return names, format_error(err)
        for item in items_of(body):
            if item.get("id"):
                names[str(item["id"])] = str(item.get("name") or item["id"])
    return names, None


@dataclass(frozen=True)
class ImportCounts:
    """What one answer adds up to — the figures both doors' summaries print."""

    total: int  # the file's lines: read, refused, and under the floor alike
    new: int
    matched: int
    by_rule: dict[str, int]
    codes: int  # matched rows the engine writes an operation code onto
    sealed: int
    before_floor: int
    refused: int


def import_counts(prepared: Prepared, placed: list[Placed]) -> ImportCounts:
    by_rule: dict[str, int] = {}
    for p in placed:
        if p.outcome == "matched":
            by_rule[p.rule or ""] = by_rule.get(p.rule or "", 0) + 1
    return ImportCounts(
        total=len(prepared.rows) + len(prepared.bad),
        new=sum(1 for p in placed if p.outcome == "new"),
        matched=sum(by_rule.values()),
        by_rule=by_rule,
        codes=sum(1 for p in placed if p.backfill_code),
        sealed=sum(1 for p in placed if p.outcome == "sealed"),
        before_floor=len(prepared.before_floor),
        refused=len(prepared.bad),
    )


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


def incomplete_sentence(gap: IncompleteAnswer, prepared: Prepared) -> str:
    """What an answer short of (or beyond) the rows sent means, in both doors."""
    n = len(prepared.sent)
    return (
        f"the engine answered {n - len(gap.missing)} of the {n} rows sent"
        + (f", plus {len(gap.unknown)} it was never sent" if gap.unknown else "")
        + " — nothing below would be complete, so nothing is shown."
    )
