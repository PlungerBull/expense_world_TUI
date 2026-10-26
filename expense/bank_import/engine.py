"""The bank's download → the `POST /transactions/import` body, and its answer →
what the import door shows. Pure: no HTTP, no typer, no config.

The engine reads the file, matches its rows against its bank lines, and
reports the days whose totals disagree (contract: POST /v1/transactions/import).
The app sends the file whole and reads no cell of it; this module only says
what is sent and how the answer reads, so the door shows the engine's word.
"""

import base64
from dataclasses import dataclass
from enum import Enum

from expense.formatting import signed_cents


def request_body(account_id: str, data: bytes, *, dry_run: bool) -> dict:
    """Exactly the three keys the engine takes: the account the download is
    from, and the file's bytes in standard base64 (the RFC 4648 alphabet,
    padded, no line breaks) (contract: POST /v1/transactions/import, "Body")."""
    return {
        "dry_run": dry_run,
        "account_id": account_id,
        "file": base64.b64encode(data).decode("ascii"),
    }


@dataclass(frozen=True)
class ImportedRow:
    """One data row of the file as the engine read it, and what it did (or, on
    a dry run, would do) with it."""

    #: The row's number in the spreadsheet; the first data row is 2.
    row: int
    #: The account the engine puts the row on: on a card's download, the
    #: account of the row's currency.
    account_id: str
    date_iso: str
    title: str | None
    amount_cents: int  # signed: negative = outflow; 0 on a skipped row
    outcome: str  # new | matched | sealed | skipped
    #: On a `matched` row, the operation code the apply writes onto its line.
    backfill_code: str | None
    #: On a `matched` row, whether the bank's title is (or would be) written
    #: onto the line.
    retitled: bool | None
    #: On a `matched` row, whether the line is (or would be) moved to the
    #: bank's day.
    redated: bool | None
    #: On a `matched` row whose move a completed reconciliation stops: that
    #: reconciliation's id.
    redate_blocked_by: str | None


def answer_rows(response: dict) -> list[ImportedRow]:
    """The answer's `rows`, in the file's order. Each amount comes as a
    magnitude and a `transaction_type`; `signed_cents` signs it."""
    return [
        ImportedRow(
            row=int(item.get("row") or 0),
            account_id=str(item.get("account_id")),
            date_iso=str(item.get("date")),
            title=item.get("title"),
            amount_cents=signed_cents(item),
            outcome=str(item.get("outcome")),
            backfill_code=item.get("backfill_code"),
            retitled=item.get("retitled"),
            redated=item.get("redated"),
            redate_blocked_by=item.get("redate_blocked_by"),
        )
        for item in response.get("rows") or []
    ]


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
    #: The spreadsheet rows on this day that matched no line.
    unmatched_rows: tuple[int, ...]
    #: Every part of the day's lines no file row claimed, line after line in
    #: the engine's order, each the engine's whole transaction response: a
    #: magnitude in `amount_cents`, the direction in `transaction_type`.
    unclaimed_parts: tuple[dict, ...]


def day_mismatches(response: dict, names: dict[str, str]) -> list[DayMismatch]:
    """The answer's `day_mismatches`, in the engine's order, each account
    named from `names` (account id → name; its id when it is not there). The
    totals stay signed as the engine sends them; a day can be reported with
    equal totals when it holds an unclaimed line."""
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
                unclaimed_parts=tuple(
                    dict(part)
                    for line in e.get("unclaimed_lines") or []
                    for part in line.get("parts") or []
                ),
            )
        )
    return out


@dataclass(frozen=True)
class AnswerCounts:
    """What one answer adds up to: how many rows the engine read, then its own
    `counts`."""

    rows: int  # one per data row of the file
    new: int
    matched: int
    sealed: int
    skipped: int
    retitled: int
    redated: int  # the lines moved (or, on a dry run, to move) to the bank's day


def answer_counts(response: dict) -> AnswerCounts:
    """The answer's `counts`, as the engine counted them, and its rows."""
    counts = response.get("counts") or {}
    return AnswerCounts(
        rows=len(response.get("rows") or []),
        new=int(counts.get("new") or 0),
        matched=int(counts.get("matched") or 0),
        sealed=int(counts.get("sealed") or 0),
        skipped=int(counts.get("skipped") or 0),
        retitled=int(counts.get("retitled") or 0),
        redated=int(counts.get("redated") or 0),
    )


class Verdict(Enum):
    """What one row comes to, from the engine's outcome: the preview's mark and
    the style of its reason follow from it, never from the reason's words."""

    NEW = "new"  # created on apply
    IN_LEDGER = "in_ledger"  # matched, and the apply writes nothing onto its line
    MODIFIED = "modified"  # matched, and the apply writes onto its line
    NOT_MOVED = "not_moved"  # matched, its move to the bank's day stopped
    CLOSED = "closed"  # sealed: never created
    SKIPPED = "skipped"  # a row of 0: never matched or created


#: The preview's reason for each verdict.
NEW = "New"
IN_LEDGER = "Already in the ledger"
MODIFIED = "Modified existing transaction"
CLOSED = "Closed period"
SKIPPED = "Skipped: amount 0"
#: A move a completed reconciliation stops; `{}` is its name.
NOT_MOVED = "Not moved: {} is reconciled"
#: The name in NOT_MOVED when the reconciliations could not be read.
UNNAMED_RECONCILIATION = "a reconciliation"


@dataclass(frozen=True)
class PreviewLine:
    """One row of the preview: the row as the engine read it, its verdict and
    its reason."""

    row: ImportedRow
    verdict: Verdict
    reason: str


def row_verdict(row: ImportedRow) -> Verdict:
    """The row's verdict from its outcome. A matched row is modified when the
    apply writes the bank's operation code, title or day onto its line; a move
    a completed reconciliation stops wins over the rest."""
    if row.outcome == "new":
        return Verdict.NEW
    if row.outcome == "sealed":
        return Verdict.CLOSED
    if row.outcome == "skipped":
        return Verdict.SKIPPED
    if row.redate_blocked_by:
        return Verdict.NOT_MOVED
    if row.backfill_code or row.retitled or row.redated:
        return Verdict.MODIFIED
    return Verdict.IN_LEDGER


def preview_line(row: ImportedRow, names: dict[str, str]) -> PreviewLine:
    """The row with its verdict and reason; a stopped move names its
    reconciliation from `names` (reconciliation id → name)."""
    verdict = row_verdict(row)
    if verdict is Verdict.NOT_MOVED:
        name = names.get(str(row.redate_blocked_by), UNNAMED_RECONCILIATION)
        return PreviewLine(row, verdict, NOT_MOVED.format(name))
    reasons = {
        Verdict.NEW: NEW,
        Verdict.IN_LEDGER: IN_LEDGER,
        Verdict.MODIFIED: MODIFIED,
        Verdict.CLOSED: CLOSED,
        Verdict.SKIPPED: SKIPPED,
    }
    return PreviewLine(row, verdict, reasons[verdict])


def blocking_reconciliations(rows: list[ImportedRow]) -> list[str]:
    """The distinct ids of the reconciliations that stop a row's move to the
    bank's day, in the rows' order: the ones that need naming."""
    seen: list[str] = []
    for r in rows:
        if r.redate_blocked_by and r.redate_blocked_by not in seen:
            seen.append(r.redate_blocked_by)
    return seen
