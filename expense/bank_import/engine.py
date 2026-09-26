"""BankRows → the `POST /transactions/import` body, and its response → one
view per row. Pure: no HTTP, no typer, no config.

The engine does the matching (engine-spec `POST /transactions/import`): by
operation code, then same day + title, then the adjacent day + title, each
ledger row claimed once. This module only decides what is sent and how the
answer reads, so the flat command and the TUI import door show the same thing.
"""

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from expense.bank_import.parse import BankRow

#: Nothing dated earlier is ever sent (file-import-plan §6, owner 2026-09-20).
#: The only floor since 2026-09-26: the one-time `--since` was dropped once the
#: hand-typed rows the bank files overlap are aligned to the bank's wording
#: before the first real import (todo.md, "One-time title alignment").
IMPORT_FLOOR = date(2026, 1, 1)

#: Rows per request (engine `constants.IMPORT_MAX_ROWS`). A longer file is
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
    """A day where the ledger holds more rows of one amount than the file."""

    account_name: str
    date_iso: str
    amount_cents: int  # signed, as everywhere else on screen
    file_count: int
    ledger_count: int


def split_floor(rows: list[BankRow]) -> tuple[list[BankRow], list[BankRow]]:
    """(rows to send, rows dated before IMPORT_FLOOR)."""
    floor = IMPORT_FLOOR.isoformat()
    kept = [r for r in rows if r.date_iso >= floor]
    skipped = [r for r in rows if r.date_iso < floor]
    return kept, skipped


def sent_rows(rows: list[BankRow], legs: dict[str, tuple[str, str]]) -> list[SentRow]:
    """Each row on its currency's leg, under a fresh id. Every currency has a
    leg by now — the command refuses the file before this otherwise."""
    return [
        SentRow(
            row=r, id=str(uuid4()), account_id=legs[r.currency][0], account_name=legs[r.currency][1]
        )
        for r in rows
    ]


def request_body(sent: list[SentRow], *, dry_run: bool) -> dict:
    return {"dry_run": dry_run, "rows": [s.payload() for s in sent]}


def placements(response: dict, sent: list[SentRow]) -> list[Placed]:
    """The response's rows joined back to the file's, by the id each was sent
    under — in the file's order."""
    by_id = {s.id: s for s in sent}
    out: list[Placed] = []
    for item in response.get("rows") or []:
        s = by_id.get(str(item.get("id")))
        if s is None:
            continue
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
                file_count=int(e.get("file_count") or 0),
                ledger_count=int(e.get("ledger_count") or 0),
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
