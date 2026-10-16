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

#: The engine's rule → the preview's words, strongest first.
RULE_LABELS = {
    "operation_code": "operation",
    "same_day": "same day",
}


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
    sealed_by: str | None


@dataclass(frozen=True)
class UnclaimedLine:
    """A ledger line on a disagreeing day that no file row claimed: the line,
    and its live transactions on that account and day."""

    bank_line_id: str
    transaction_ids: tuple[str, ...]


@dataclass(frozen=True)
class DayMismatch:
    """One account and day whose file total and ledger total (after this
    import) differ — the engine's `day_mismatches` entry, a report only."""

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
                sealed_by=item.get("sealed_by"),
            )
        )
    return out


def day_mismatches(response: dict, names: dict[str, str]) -> list[DayMismatch]:
    """The response's `day_mismatches`, in the engine's order, each account
    named by its leg (its id when the leg is unknown). Both totals stay signed
    as the engine sends them."""
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
                        transaction_ids=tuple(str(t) for t in line.get("transaction_ids") or []),
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
    )


def match_label(p: Placed, period_names: dict[str, str]) -> str:
    """The preview's `match` cell."""
    if p.outcome == "new":
        return "new"
    if p.outcome == "sealed":
        return f"closed · {period_names.get(p.sealed_by or '', 'a closed period')}"
    label = f"in ledger · {RULE_LABELS.get(p.rule or '', p.rule or '?')}"
    if p.backfill_code:
        label += " · +code"
    return label


def sealed_accounts(placed: list[Placed]) -> list[str]:
    """The leg accounts with a sealed row, whose periods need naming."""
    seen: list[str] = []
    for p in placed:
        if p.outcome == "sealed" and p.sent.account_id not in seen:
            seen.append(p.sent.account_id)
    return seen


def row_refusals(fields: object, sent: list[SentRow]) -> list[tuple[int | None, str, str]]:
    """A `422`'s `rows.<index>.<field>` keys → (the file's line, field, message).

    The engine counts the rows it was sent; the user counts the file's lines.
    A key that names no row keeps its line as None and its key as the field.
    """
    out: list[tuple[int | None, str, str]] = []
    if not isinstance(fields, dict):
        return out
    for key, message in fields.items():
        parts = str(key).split(".", 2)
        if len(parts) == 3 and parts[0] == "rows" and parts[1].isdigit():
            i = int(parts[1])
            if i < len(sent):
                out.append((sent[i].row.line, parts[2], str(message)))
                continue
        out.append((None, str(key), str(message)))
    return out
