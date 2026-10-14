"""BankRows → the `POST /transactions/import` body, and its response → one
view per row. Pure: no HTTP, no typer, no config.

The engine does the matching (contract: POST /v1/transactions/import): by
operation code, then same day + title, then the adjacent day + title, each
ledger row claimed once. This module only decides what is sent and how the
answer reads, so the TUI import door shows the engine's word.
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
    "adjacent_day": "± 1 day",
}

#: The engine's `transaction_type` on an `excess` group: 1 outflow, 2 inflow.
OUTFLOW = 1


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
    ledger_id: str | None
    backfill_code: str | None
    sealed_by: str | None


@dataclass(frozen=True)
class ExcessGroup:
    """A day and amount the file reports where the ledger still holds a row no
    file row claimed (the engine's `excess`). Equal counts are included: that
    ledger row and a `new` file row may be one movement in two wordings."""

    account_name: str
    date_iso: str
    amount_cents: int  # signed, as everywhere else on screen
    #: The ledger rows here no file row claimed — the count the warning
    #: shows.
    unclaimed: int


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
                ledger_id=item.get("ledger_id"),
                backfill_code=item.get("backfill_code"),
                sealed_by=item.get("sealed_by"),
            )
        )
    return out


def excess_groups(response: dict, names: dict[str, str]) -> list[ExcessGroup]:
    out: list[ExcessGroup] = []
    for e in response.get("excess") or []:
        cents = int(e.get("amount_cents") or 0)
        if e.get("transaction_type") == OUTFLOW:
            cents = -cents
        account_id = str(e.get("account_id"))
        out.append(
            ExcessGroup(
                account_name=names.get(account_id, account_id),
                date_iso=str(e.get("date")),
                amount_cents=cents,
                unclaimed=len(e.get("unclaimed_ledger_ids") or []),
            )
        )
    return out


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
