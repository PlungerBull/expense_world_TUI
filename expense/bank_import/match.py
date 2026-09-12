"""BankRows against the ledger → a Verdict per row. Pure.

The duplicate protection is a **match against what the ledger already holds**,
not a hash of the file (owner decision 2026-09-12; the why and the rejected
alternatives are in docs/decisions.md "Bank downloads are matched against the
ledger"). Four rules, tried in order, each ledger row claimed at most once:

    1  operation code       both sides carry one → exact, on the account
    2  same day + title     account, date, amount, cleaned title
    3  ±1 day + title       as 2, the ledger row one day either side
    4  ±1 day, amount only  account and amount within a day, title ignored —
                            the owner's count rule: three rows of 3.50 in the
                            file and one in the ledger leave two unmatched

Rows 2–4 prefer an exact-date candidate over a neighbour, so a Tuesday file
row claims Tuesday's ledger row before Monday's. Because every ledger row is
claimed once, a group of identical file rows against fewer ledger rows leaves
the difference unmatched — that IS the count, with no counting step.

What no rule can see: a card row that moves by more than a day between
downloads, or changes amount at settlement. Those import twice, and the
unreconciled check over the statement period is the backstop.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from expense.bank_import.parse import BankRow

RULE_OPERATION = "operation"
RULE_SAME_DAY_TITLE = "same day + title"
RULE_NEAR_DAY_TITLE = "±1 day + title"
RULE_NEAR_DAY_AMOUNT = "±1 day, amount only"
RULES = (RULE_OPERATION, RULE_SAME_DAY_TITLE, RULE_NEAR_DAY_TITLE, RULE_NEAR_DAY_AMOUNT)


@dataclass(frozen=True)
class LedgerRow:
    """What the matcher needs of a ledger transaction. `amount_cents` is
    SIGNED — the CLI always reads with `debit_as_negative`."""

    id: str
    account_id: str
    date_iso: str
    amount_cents: int
    title: str | None
    operation_code: str | None


@dataclass(frozen=True)
class Verdict:
    """One file row, placed. `rule` and `ledger_id` are set iff it matched."""

    row: BankRow
    account_id: str
    account_name: str
    rule: str | None = None
    ledger_id: str | None = None

    @property
    def new(self) -> bool:
        return self.rule is None


@dataclass(frozen=True)
class Excess:
    """A (account, date, amount) group where the ledger holds more rows than
    the file does — the one thing the count rule can detect that nothing else
    can: an earlier double entry. Reported, never acted on."""

    account_name: str
    date_iso: str
    amount_cents: int
    ledger_count: int
    file_count: int


def norm_title(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def _near(date_iso: str, days: int) -> list[str]:
    """`date_iso` and its neighbours within `days`, exact date first."""
    d = date.fromisoformat(date_iso)
    out = [date_iso]
    for step in range(1, days + 1):
        out.append((d - timedelta(days=step)).isoformat())
        out.append((d + timedelta(days=step)).isoformat())
    return out


def match_rows(
    rows: list[BankRow],
    legs: dict[str, tuple[str, str]],
    ledger: list[LedgerRow],
    *,
    tolerance_days: int = 1,
) -> tuple[list[Verdict], list[Excess]]:
    """Place every file row.

    `legs` maps a currency code to the `(account_id, account_name)` it lands
    in; every row's currency must have a leg (the command refuses the file
    before calling this otherwise). `ledger` is every live row of those
    accounts over the file's date range, plus the tolerance either side.
    """
    claimed: set[str] = set()
    # Index the ledger three ways, each per account.
    by_code: dict[tuple[str, str], LedgerRow] = {}
    by_day_amount_title: dict[tuple[str, str, int, str], list[LedgerRow]] = defaultdict(list)
    by_day_amount: dict[tuple[str, str, int], list[LedgerRow]] = defaultdict(list)
    for lr in ledger:
        if lr.operation_code:
            by_code[(lr.account_id, lr.operation_code)] = lr
        by_day_amount_title[
            (lr.account_id, lr.date_iso, lr.amount_cents, norm_title(lr.title))
        ].append(lr)
        by_day_amount[(lr.account_id, lr.date_iso, lr.amount_cents)].append(lr)

    def claim(candidates: list[LedgerRow]) -> LedgerRow | None:
        for lr in candidates:
            if lr.id not in claimed:
                claimed.add(lr.id)
                return lr
        return None

    placed: dict[int, Verdict] = {}

    # Rule 1 — the operation code decides, matched or not.
    pending: list[BankRow] = []
    for row in rows:
        account_id, account_name = legs[row.currency]
        if row.operation_code is not None:
            hit = by_code.get((account_id, row.operation_code))
            if hit is not None and hit.id not in claimed:
                claimed.add(hit.id)
                placed[row.line] = Verdict(row, account_id, account_name, RULE_OPERATION, hit.id)
            else:
                placed[row.line] = Verdict(row, account_id, account_name)
            continue
        pending.append(row)

    # Rules 2–4, one pass each so an exact match anywhere in the file beats a
    # looser one elsewhere.
    def pass_over(rule: str, keyer) -> None:
        nonlocal pending
        left: list[BankRow] = []
        for row in pending:
            account_id, account_name = legs[row.currency]
            hit = None
            for key in keyer(row, account_id):
                hit = claim(by_day_amount_title[key] if len(key) == 4 else by_day_amount[key])
                if hit is not None:
                    break
            if hit is None:
                left.append(row)
            else:
                placed[row.line] = Verdict(row, account_id, account_name, rule, hit.id)
        pending = left

    pass_over(
        RULE_SAME_DAY_TITLE,
        lambda r, a: [(a, r.date_iso, r.amount_cents, norm_title(r.title))],
    )
    pass_over(
        RULE_NEAR_DAY_TITLE,
        lambda r, a: [
            (a, d, r.amount_cents, norm_title(r.title)) for d in _near(r.date_iso, tolerance_days)
        ],
    )
    pass_over(
        RULE_NEAR_DAY_AMOUNT,
        lambda r, a: [(a, d, r.amount_cents) for d in _near(r.date_iso, tolerance_days)],
    )
    for row in pending:
        account_id, account_name = legs[row.currency]
        placed[row.line] = Verdict(row, account_id, account_name)

    verdicts = [placed[row.line] for row in rows]

    # Groups where the ledger holds MORE on the exact day than the file does.
    file_groups: Counter = Counter()
    for v in verdicts:
        file_groups[(v.account_id, v.row.date_iso, v.row.amount_cents)] += 1
    names = {account_id: name for account_id, name in legs.values()}
    excess: list[Excess] = []
    for key, file_count in sorted(file_groups.items(), key=lambda kv: (kv[0][1], kv[0][2])):
        ledger_count = len(by_day_amount.get(key, []))
        if ledger_count > file_count:
            account_id, date_iso, amount = key
            excess.append(Excess(names[account_id], date_iso, amount, ledger_count, file_count))
    return verdicts, excess
