"""BankRows → the `POST /transactions/import` body, and its response → one
view per row. Pure: no HTTP, no typer, no config.

The engine does the matching against its bank lines, and reports the days
whose totals disagree (contract: POST /v1/transactions/import, "Matching").
This module only decides what is sent and how the answer reads, so the TUI
import door shows the engine's word.
"""

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from expense.bank_import.parse import BankRow

#: Nothing dated earlier is ever sent. The hand-typed rows the bank files
#: overlap are aligned to the bank's wording before the first real import
#: (todo.md, "One-time title alignment").
#: Why: docs/decisions.md "Bank downloads are matched against the ledger".
IMPORT_FLOOR = date(2026, 1, 1)

#: Rows per request, 1–500 (contract: POST /v1/transactions/import). A longer file is
#: refused whole, never split: a row in a later request could be claimed by a
#: row an earlier one had just created, and vanish without a word.
IMPORT_MAX_ROWS = 500


@dataclass(frozen=True)
class SentRow:
    """One file row as it goes to the engine: the id it was sent under and the
    leg of the card it landed on."""

    row: BankRow
    id: str
    account_id: str
    account_name: str

    def payload(self) -> dict:
        body: dict = {
            "id": self.id,
            "account_id": self.account_id,
            # The calendar day as the bank printed it — the engine reads it in
            # the user's display_timezone. Never an instant.
            "date": self.row.date_iso,
            "amount_cents": self.row.amount_cents,
            "title": self.row.title,
        }
        if self.row.operation_code is not None:
            body["operation_code"] = self.row.operation_code
        return body


@dataclass(frozen=True)
class Placed:
    """What the engine did (or would do) with one sent row."""

    sent: SentRow
    outcome: str  # new | matched | sealed
    rule: str | None
    #: The bank line a `matched` row is; None on the other outcomes.
    bank_line_id: str | None
    backfill_code: str | None
    #: On a `matched` row, whether the bank's title is (or, on a dry run,
    #: would be) written onto the line; None on the other outcomes.
    retitled: bool | None
    #: On a `matched` row, whether the line is (or would be) moved to the
    #: bank's day; None on the other outcomes.
    redated: bool | None
    #: On a `matched` row whose move a completed reconciliation stops: that
    #: reconciliation's id; None otherwise.
    redate_blocked_by: str | None
    sealed_by: str | None


@dataclass(frozen=True)
class UnclaimedLine:
    """A ledger bank line on a reported day that no file row claimed — one
    entry however many parts it is split into (contract: POST /v1/transactions/import).

    `parts` are its live transactions on that account and day, each the
    engine's whole transaction response as `GET /transactions/{id}` returns
    it, in the engine's order: everything a screen shows of them is here, so
    none is read again. Their `amount_cents` is a magnitude, the direction in
    `transaction_type`; only `net_cents` is signed."""

    bank_line_id: str
    net_cents: int  # signed: inflow positive, outflow negative
    parts: tuple[dict, ...]


@dataclass(frozen=True)
class DayMismatch:
    """One account and day the engine reports — the `day_mismatches` entry, a
    report only: its file total and ledger total (after this import) differ,
    or it holds a ledger line no file row claimed, or both
    (contract: POST /v1/transactions/import)."""

    account_id: str
    account_name: str
    date_iso: str
    file_net_cents: int  # signed: inflow positive, outflow negative
    ledger_net_cents: int  # signed, the ledger's after this import
    #: The indexes of the sent rows on this day that matched no line.
    unmatched_rows: tuple[int, ...]
    unclaimed_lines: tuple[UnclaimedLine, ...]


@dataclass(frozen=True)
class AnswerCounts:
    """The engine's own `counts` of one answer."""

    new: int
    matched: int
    sealed: int
    backfilled: int
    retitled: int
    redated: int  # the lines moved (or, on a dry run, to move) to the bank's day


def split_floor(rows: list[BankRow]) -> tuple[list[BankRow], list[BankRow]]:
    """(rows to send, rows dated before IMPORT_FLOOR)."""
    floor = IMPORT_FLOOR.isoformat()
    kept = [r for r in rows if r.date_iso >= floor]
    skipped = [r for r in rows if r.date_iso < floor]
    return kept, skipped


def sent_rows(rows: list[BankRow], legs: dict[str, tuple[str, str]]) -> list[SentRow]:
    """Each row on its currency's leg, under a fresh id. Every currency has a
    leg by now — the door refuses the file before this otherwise."""
    return [
        SentRow(
            row=r, id=str(uuid4()), account_id=legs[r.currency][0], account_name=legs[r.currency][1]
        )
        for r in rows
    ]


def request_body(sent: list[SentRow], *, dry_run: bool) -> dict:
    return {"dry_run": dry_run, "rows": [s.payload() for s in sent]}


class IncompleteAnswer(Exception):
    """The response does not answer exactly the rows that were sent."""

    def __init__(self, missing: list[SentRow], unknown: list[str]):
        self.missing = missing
        self.unknown = unknown
        super().__init__(
            f"the engine answered {len(missing)} sent row(s) too few and "
            f"{len(unknown)} it was never sent"
        )


def placements(response: dict, sent: list[SentRow]) -> list[Placed]:
    """The response's rows joined back to the file's, by the id each was sent
    under — in the file's order.

    Raises IncompleteAnswer unless every sent id comes back exactly once and
    nothing else does: a row silently missing from the answer would make
    every count under-report without a word.
    """
    by_id = {s.id: s for s in sent}
    items = response.get("rows") or []
    returned = [str(item.get("id")) for item in items]
    missing = [s for s in sent if s.id not in returned]
    unknown = [i for i in returned if i not in by_id]
    if missing or unknown or len(returned) != len(sent):
        raise IncompleteAnswer(missing, unknown)
    out: list[Placed] = []
    for item in items:
        s = by_id[str(item.get("id"))]
        out.append(
            Placed(
                sent=s,
                outcome=str(item.get("outcome")),
                rule=item.get("rule"),
                bank_line_id=item.get("bank_line_id"),
                backfill_code=item.get("backfill_code"),
                retitled=item.get("retitled"),
                redated=item.get("redated"),
                redate_blocked_by=item.get("redate_blocked_by"),
                sealed_by=item.get("sealed_by"),
            )
        )
    return out


def day_mismatches(response: dict, names: dict[str, str]) -> list[DayMismatch]:
    """The response's `day_mismatches`, in the engine's order, each account
    named by its leg (its id when the leg is unknown). The totals and each
    unclaimed line's `net_cents` stay signed as the engine sends them; a day
    can be reported with equal totals when it holds an unclaimed line."""
    out: list[DayMismatch] = []
    for e in response.get("day_mismatches") or []:
        account_id = str(e.get("account_id"))
        out.append(
            DayMismatch(
                account_id=account_id,
                account_name=names.get(account_id, account_id),
                date_iso=str(e.get("date")),
                file_net_cents=int(e.get("file_net_cents") or 0),
                ledger_net_cents=int(e.get("ledger_net_cents") or 0),
                unmatched_rows=tuple(int(i) for i in e.get("unmatched_rows") or []),
                unclaimed_lines=tuple(
                    UnclaimedLine(
                        bank_line_id=str(line.get("bank_line_id")),
                        net_cents=int(line.get("net_cents") or 0),
                        parts=tuple(dict(p) for p in line.get("parts") or []),
                    )
                    for line in e.get("unclaimed_lines") or []
                ),
            )
        )
    return out


def answer_counts(response: dict) -> AnswerCounts:
    """The response's `counts`, as the engine counted them."""
    counts = response.get("counts") or {}
    return AnswerCounts(
        new=int(counts.get("new") or 0),
        matched=int(counts.get("matched") or 0),
        sealed=int(counts.get("sealed") or 0),
        backfilled=int(counts.get("backfilled") or 0),
        retitled=int(counts.get("retitled") or 0),
        redated=int(counts.get("redated") or 0),
    )


#: The preview's reason for each row of the file, and whether that row is in
#: the ledger after the import (✓) or left out (✗).
NEW = "New"
IN_LEDGER = "Already in the ledger"
MODIFIED = "Modified existing transaction"
CLOSED = "Closed period"
BEFORE_FLOOR = f"Before {IMPORT_FLOOR.year}"
UNREADABLE = "Couldn't read the row"
#: A move a completed reconciliation stops; `{}` is its name.
NOT_MOVED = "Not moved: {} is reconciled"
#: The name in NOT_MOVED when the reconciliations could not be read.
UNNAMED_RECONCILIATION = "a reconciliation"


def row_reason(p: Placed, names: dict[str, str]) -> tuple[bool, str]:
    """(in the ledger after the import, the reason) of one answered row.

    A matched row is modified when the apply writes the bank's code, title
    or day onto its line; a move a completed reconciliation stops wins over
    the rest, named from `names` (reconciliation id → name)."""
    if p.outcome == "new":
        return True, NEW
    if p.outcome == "sealed":
        return False, CLOSED
    if p.redate_blocked_by:
        name = names.get(p.redate_blocked_by, UNNAMED_RECONCILIATION)
        return False, NOT_MOVED.format(name)
    if p.backfill_code or p.retitled or p.redated:
        return True, MODIFIED
    return True, IN_LEDGER


def blocked_accounts(placed: list[Placed]) -> list[str]:
    """The leg accounts with a row whose move a reconciliation stops, whose
    reconciliations need naming."""
    seen: list[str] = []
    for p in placed:
        if p.redate_blocked_by and p.sent.account_id not in seen:
            seen.append(p.sent.account_id)
    return seen


def row_index(key: object) -> int | None:
    """The sent row's index a refusal's key names — `rows.<index>` or
    `rows.<index>.<field>` — or None for any other key."""
    parts = str(key).split(".", 2)
    if len(parts) >= 2 and parts[0] == "rows" and parts[1].isdigit():
        return int(parts[1])
    return None


def row_refusals(fields: object, sent: list[SentRow]) -> list[tuple[int | None, str | None, str]]:
    """A refusal's `rows.<index>` and `rows.<index>.<field>` keys → (the file's
    line, field, message); the field is None when the key names the row alone.

    The engine counts the rows it was sent; the user counts the file's lines.
    A key that names no row keeps its line as None and its key as the field.
    """
    out: list[tuple[int | None, str | None, str]] = []
    if not isinstance(fields, dict):
        return out
    for key, message in fields.items():
        i = row_index(key)
        if i is not None and i < len(sent):
            parts = str(key).split(".", 2)
            out.append((sent[i].row.line, parts[2] if len(parts) == 3 else None, str(message)))
            continue
        out.append((None, str(key), str(message)))
    return out
