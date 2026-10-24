"""Turn parsed rows into an ImportPlan: distinct resources + deterministic ids.

Transaction ids are uuid5 over stable row content, so re-running the same sheet
yields the same ids — an accidental second --apply can't create duplicates.
Category/hashtag names are deduplicated case-insensitively to match the engine's
case-insensitive uniqueness. Rows sharing a ``COD_EECC`` (``ParsedRow.group_code``)
are grouped into one movement, its parts (``SplitGroup``).
"""

import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from expense.import_ import mapping
from expense.import_.parse import OpeningRow, ParsedRow, SkippedRow


@dataclass(frozen=True)
class AccountSpec:
    """One account to ensure.

    ``name`` is what the engine is told; ``source_name`` is the raw sheet cell.
    They differ when a sheet name spans several currencies — the engine gives
    every account exactly one currency, so such a name becomes several accounts
    and each needs its own display name (see ``_split_account_name``) — and
    when the owner renames a (sheet name, currency) leg (``account_names`` in
    ``build_plan``). Rows always resolve by ``source_name``, never by ``name``.
    """

    name: str
    currency: str
    source_name: str


@dataclass(frozen=True)
class SplitGroup:
    """Two or more rows sharing one ``COD_EECC``: one movement, a part per row.

    ``name`` is the ``line_group`` its rows are sent under: the first row's
    transaction id, so it is unique in the request and never longer than the
    engine takes (contract: POST /v1/transactions/batch, "Line groups"), however
    long the ``COD_EECC`` is. ``group_code`` is that ``COD_EECC``; it only groups,
    and is never sent.
    """

    group_code: str
    lines: tuple[int, ...]
    name: str


@dataclass
class ImportPlan:
    rows: list[ParsedRow]
    tx_ids: dict[int, str]  # row.line -> deterministic uuid
    accounts: list[AccountSpec]  # distinct (name, currency)
    categories: list[str]  # distinct names, first-seen casing
    hashtags: list[str]  # distinct names, first-seen casing
    openings: list[OpeningRow] = field(default_factory=list)
    opening_ids: dict[int, str] = field(default_factory=dict)  # row.line -> uuid
    skipped: list[SkippedRow] = field(default_factory=list)
    groups: list[SplitGroup] = field(default_factory=list)  # in sheet order
    #: Why each held-back group waits, in sheet order: a line per field its rows
    #: differ on (``SIG-202603-029: line 3120 is 2026-03-14, line 3122 is
    #: 2026-03-15.``), or one naming its unreadable rows (``SIG-202603-029: line
    #: 3122 can't be read, so lines 3120, 3121 wait for it.``).
    split_mismatches: list[str] = field(default_factory=list)

    @property
    def split_rows(self) -> int:
        """How many of ``rows`` are parts of a split transaction."""
        return sum(len(group.lines) for group in self.groups)

    @property
    def movements(self) -> int:
        """How many movements ``rows`` make: one per split transaction, one per
        other row."""
        return len(self.rows) - self.split_rows + len(self.groups)

    def group_of(self) -> dict[int, SplitGroup]:
        """row.line -> the split transaction it is a part of."""
        return {line: group for group in self.groups for line in group.lines}


def stable_row_key(row: ParsedRow | OpeningRow) -> str:
    """The content a transaction's id is hashed from.

    ``row.line`` is load-bearing and not removable: two genuinely identical
    purchases on the same day — same date, account, currency, amount, title —
    are byte-identical without it, so they would share an id and the second
    would be 409'd away as a re-import skip. Dropping it trades silent
    duplication for silent loss.

    It is also positional, and that is the precondition this module's
    convergence claim rests on: **the sheet must be append-only below the last
    imported row.** Insert, delete or sort a row mid-sheet and every row below
    it hashes to a new id, which imports as a second copy rather than skipping.
    The duplicate is unassigned by construction and cannot disturb a completed
    reconciliation, so it is invisible until looked for — check the account's
    "no batch" list in the app's reconciliation view over the period you
    last reconciled. Full rationale and
    the rejected alternatives: docs/decisions.md, "Importer ids are positional".
    """
    return "|".join(
        [
            row.date_iso,
            row.account.strip().casefold(),
            row.currency,
            str(row.amount_cents),
            row.title,
            str(row.line),
        ]
    )


def tx_id_for(row: ParsedRow | OpeningRow) -> str:
    return str(uuid.uuid5(mapping.IMPORT_NAMESPACE, stable_row_key(row)))


def _split_account_name(name: str, currency: str, currencies: set[str]) -> str:
    """Display name for one currency-leg of a sheet account.

    A name used under a single currency is passed through verbatim. A name that
    spans several gets each leg suffixed with its currency — "BCP Oro" holding
    both PEN and USD rows becomes "BCP Oro PEN" and "BCP Oro USD", so neither
    leg is ambiguous in a picker. Suffixing *both* rather than only the foreign
    one keeps the pair symmetric and matches how such accounts are usually
    named by hand. A name that already ends in its own currency is left alone
    rather than doubled.
    """
    if len(currencies) < 2:
        return name
    if name.casefold().endswith(f" {currency.casefold()}"):
        return name
    return f"{name} {currency}"


def account_key(name: str, currency: str) -> tuple[str, str]:
    """How a sheet account leg is identified: name case/space-insensitive,
    currency upper-case — the same key rows and openings resolve by."""
    return (name.strip().casefold(), currency.strip().upper())


def _distinct_ci(names: Iterable[str]) -> list[str]:
    """Case-insensitive distinct, keeping the first-seen original casing."""
    seen: dict[str, str] = {}
    for name in names:
        key = name.strip().casefold()
        if key not in seen:
            seen[key] = name.strip()
    return list(seen.values())


#: How a split transaction's rows must agree, each with how a value reads in a
#: mismatch line. The engine refuses a line group whose items differ on account,
#: date or title (contract: POST /v1/transactions/batch, "Line groups"), so a
#: group that does is input the sheet has to fix, caught before anything is sent.
_GROUP_FIELDS: tuple[tuple[Callable[[ParsedRow], object], Callable[[ParsedRow], str]], ...] = (
    (lambda r: account_key(r.account, r.currency), lambda r: f"{r.account} [{r.currency}]"),
    (lambda r: r.date_iso, lambda r: r.date_iso),
    (lambda r: r.title, lambda r: f'"{r.title}"'),
)


def _mismatches(code: str, rows: list[ParsedRow]) -> list[str]:
    """One line per field the rows of `code` differ on, naming the first row and
    every row whose value is not the first row's; none when they agree."""
    lines: list[str] = []
    first = rows[0]
    for key, shown in _GROUP_FIELDS:
        differ = [row for row in rows[1:] if key(row) != key(first)]
        if differ:
            said = ", ".join(f"line {row.line} is {shown(row)}" for row in [first, *differ])
            lines.append(f"{code}: {said}.")
    return lines


#: The one parse skip that does not hold a split transaction back: a zero-amount
#: part is no movement at all, so the rest of its group goes without it.
_DROPPED_PART = "zero-amount"


def _waiting(code: str, unread: list[int], waiting: list[int]) -> str:
    """The line naming a split transaction's unreadable rows and the rows that
    wait for them."""
    read = ", ".join(str(line) for line in unread)
    held = ", ".join(str(line) for line in waiting)
    cause = f"line {read} can't be read" if len(unread) == 1 else f"lines {read} can't be read"
    wait = f"line {held} waits" if len(waiting) == 1 else f"lines {held} wait"
    them = "it" if len(unread) == 1 else "them"
    return f"{code}: {cause}, so {wait} for {them}."


def _group_rows(
    parsed: list[ParsedRow], skipped: list[SkippedRow]
) -> tuple[list[ParsedRow], list[list[ParsedRow]], list[SkippedRow], list[str]]:
    """Split `parsed` by `group_code`: the rows kept, the kept groups of two
    or more rows, and the rows of a group held back, as ``split-mismatch``, with
    the lines saying why.

    A group is held back whole when the parse skipped one of its rows for any
    reason but a zero amount (the rest waits for that row, so the movement never
    lands without it), or when its rows differ on account, date or title. A
    zero-amount part is dropped and the rest goes; a group left with one row is
    that row alone.
    """
    by_code: dict[str, list[ParsedRow]] = {}
    for row in parsed:
        if row.group_code is not None:
            by_code.setdefault(row.group_code, []).append(row)
    unread: dict[str, list[int]] = {}
    for skip in skipped:
        if skip.group_code is not None and skip.reason != _DROPPED_PART:
            unread.setdefault(skip.group_code, []).append(skip.line)
    dropped: set[int] = set()
    groups: list[list[ParsedRow]] = []
    skips: list[SkippedRow] = []
    mismatches: list[str] = []
    for code, rows in sorted(
        by_code.items(), key=lambda kv: min([kv[1][0].line, *unread.get(kv[0], [])])
    ):
        if code in unread:
            said = [_waiting(code, sorted(unread[code]), [row.line for row in rows])]
        elif len(rows) < 2:
            continue
        else:
            said = _mismatches(code, rows)
        if said:
            mismatches.extend(said)
            dropped.update(row.line for row in rows)
            skips.extend(SkippedRow(row.line, "split-mismatch", code) for row in rows)
        else:
            groups.append(rows)
    kept = [row for row in parsed if row.line not in dropped]
    return kept, groups, skips, mismatches


def build_plan(
    parsed: list[ParsedRow],
    openings: list[OpeningRow],
    skipped: list[SkippedRow],
    account_names: Mapping[tuple[str, str], str] | None = None,
) -> ImportPlan:
    """``account_names`` maps a sheet leg (``account_key(sheet_name, currency)``)
    to the ledger name it is written under, replacing the derived name; a leg
    with no entry keeps the derived one, and an entry matching no leg is unused.
    """
    renames = dict(account_names or {})
    kept, grouped, group_skips, mismatches = _group_rows(parsed, skipped)
    skips = [*skipped, *group_skips]
    rows: list[ParsedRow] = []
    tx_ids: dict[int, str] = {}
    # No content-dedup here, deliberately: stable_row_key embeds row.line, so
    # ids are line-keyed and always unique — identical content on two lines
    # imports twice.
    for row in kept:
        tx_ids[row.line] = tx_id_for(row)
        rows.append(row)
    groups = [
        SplitGroup(
            group_code=str(parts[0].group_code),
            lines=tuple(row.line for row in parts),
            name=tx_ids[parts[0].line],
        )
        for parts in grouped
    ]

    # Opening balances: the engine enforces one active opening per account, so
    # a sheet with two SALDO INICIAL rows for the same (account, currency)
    # keeps only the first (lowest line) and reports the rest — deterministic
    # and visible in the dry-run rather than a surprise 409 at apply time.
    kept_openings: list[OpeningRow] = []
    opening_ids: dict[int, str] = {}
    first_by_account: dict[tuple[str, str], int] = {}
    for row in openings:
        key = (row.account.strip().casefold(), row.currency)
        if key in first_by_account:
            skips.append(
                SkippedRow(
                    row.line,
                    "duplicate-opening",
                    f"first at line {first_by_account[key]}",
                )
            )
            continue
        first_by_account[key] = row.line
        opening_ids[row.line] = tx_id_for(row)
        kept_openings.append(row)

    pairs: list[tuple[str, str]] = []
    acct_seen: set[tuple[str, str]] = set()
    # Openings can reference accounts that appear in no ordinary row — an
    # account whose only sheet entry is its SALDO INICIAL still gets created.
    for row in [*rows, *kept_openings]:
        key = (row.account.strip().casefold(), row.currency)
        if key not in acct_seen:
            acct_seen.add(key)
            pairs.append((row.account.strip(), row.currency))

    spanning: dict[str, set[str]] = {}
    for name, currency in pairs:
        spanning.setdefault(name.casefold(), set()).add(currency)
    accounts = [
        AccountSpec(
            name=renames.get(account_key(name, currency))
            or _split_account_name(name, currency, spanning[name.casefold()]),
            currency=currency,
            source_name=name,
        )
        for name, currency in pairs
    ]

    return ImportPlan(
        rows=rows,
        tx_ids=tx_ids,
        accounts=accounts,
        categories=_distinct_ci(row.category for row in rows),
        hashtags=_distinct_ci(row.hashtag for row in rows),
        openings=kept_openings,
        opening_ids=opening_ids,
        skipped=skips,
        groups=groups,
        split_mismatches=mismatches,
    )
