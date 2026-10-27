"""A month's statement PDF → how the engine's answer reads. Pure: no HTTP, no
typer, no config.

The engine reads the PDF, matches each of its rows to a ledger line, and
answers what closing the month from it does, or did
(contract: POST /v1/reconciliations/import). The app sends the file whole
(`request_body` in engine.py, the body of both uploads) and reads nothing in
it; this module only says how the answer reads, so the screens show the
engine's word. Nothing here matches, adds up or picks an account.
"""

from dataclasses import dataclass

from expense.formatting import signed_cents

#: A row's outcomes (contract: POST /v1/reconciliations/import, "Response").
MATCHED = "matched"
NEW = "new"
EMPTY = "empty"


@dataclass(frozen=True)
class NearMiss:
    """A ledger line one day off a new row with its total, which the engine
    never pairs with it: its id and its day."""

    bank_line_id: str
    date_iso: str


@dataclass(frozen=True)
class StatementRow:
    """One row of the paper as the engine read it, and what closing does (or,
    on a dry run, would do) with it."""

    #: Its place in the statement, counting from 1: the paper's number.
    place: int
    account_id: str
    currency: str
    #: The day it is matched and created on.
    date_iso: str
    description: str | None
    #: A card's undated line: interest or a fee, dated the statement's last day.
    fee: bool
    amount_cents: int  # signed: negative = money out; 0 on an empty row
    outcome: str  # matched | new | empty
    near_misses: tuple[NearMiss, ...]


def statement_rows(response: dict) -> list[StatementRow]:
    """The answer's `rows`, in the paper's order. Each amount comes as a
    magnitude and a `transaction_type`; `signed_cents` signs it."""
    return [
        StatementRow(
            place=int(item.get("place") or 0),
            account_id=str(item.get("account_id")),
            currency=str(item.get("currency") or "?"),
            date_iso=str(item.get("date")),
            description=item.get("description"),
            fee=bool(item.get("fee")),
            amount_cents=signed_cents(item),
            outcome=str(item.get("outcome")),
            near_misses=tuple(
                NearMiss(str(miss.get("bank_line_id")), str(miss.get("date")))
                for miss in item.get("near_misses") or []
            ),
        )
        for item in response.get("rows") or []
    ]


@dataclass(frozen=True)
class StatementHalf:
    """One reconciliation the statement fills or creates: on a card, one per
    currency, the named account's first."""

    account_id: str
    currency: str
    #: True when closing creates it; False when it fills an open draft.
    creates: bool
    beginning_balance_cents: int | None
    ending_balance_cents: int | None


def statement_halves(response: dict) -> list[StatementHalf]:
    """The answer's `halves`, in its order, with the paper's balances."""
    return [
        StatementHalf(
            account_id=str(half.get("account_id")),
            currency=str(half.get("currency") or "?"),
            creates=bool(half.get("creates")),
            beginning_balance_cents=half.get("beginning_balance_cents"),
            ending_balance_cents=half.get("ending_balance_cents"),
        )
        for half in response.get("halves") or []
    ]


@dataclass(frozen=True)
class StatementCounts:
    """What one answer adds up to: how many rows the paper holds, then the
    engine's own `counts`."""

    rows: int
    matched: int
    new: int
    empty: int
    taken_out: int


def statement_counts(response: dict) -> StatementCounts:
    """The answer's `counts`, as the engine counted them, and its rows."""
    counts = response.get("counts") or {}
    return StatementCounts(
        rows=len(response.get("rows") or []),
        matched=int(counts.get("matched") or 0),
        new=int(counts.get("new") or 0),
        empty=int(counts.get("empty") or 0),
        taken_out=int(counts.get("taken_out") or 0),
    )


@dataclass(frozen=True)
class StatementAnswer:
    """The answer as the screens read it: the statement's name and days, its
    halves, its rows, the ids of the lines taken out, and the counts."""

    name: str
    date_start: str
    date_end: str
    halves: tuple[StatementHalf, ...]
    rows: tuple[StatementRow, ...]
    #: The lines in the open statement that the paper does not print, oldest
    #: first: taken out of it, never changed or deleted.
    taken_out: tuple[str, ...]
    counts: StatementCounts

    @property
    def fills_a_draft(self) -> bool:
        """True when any half fills an open draft rather than being created."""
        return any(not half.creates for half in self.halves)

    @property
    def several_currencies(self) -> bool:
        """A card's paper: one half per currency."""
        return len(self.halves) > 1

    def lines_to_read(self) -> list[str]:
        """The ids the answer names a ledger line by alone, each once: the lines
        taken out, then every near miss, in the rows' order."""
        ids: list[str] = []
        for line_id in [
            *self.taken_out,
            *(miss.bank_line_id for row in self.rows for miss in row.near_misses),
        ]:
            if line_id not in ids:
                ids.append(line_id)
        return ids


def statement_answer(response: dict) -> StatementAnswer:
    """The whole answer, every part as the engine sent it."""
    return StatementAnswer(
        name=str(response.get("name") or ""),
        date_start=str(response.get("date_start") or ""),
        date_end=str(response.get("date_end") or ""),
        halves=tuple(statement_halves(response)),
        rows=tuple(statement_rows(response)),
        taken_out=tuple(str(i) for i in response.get("taken_out") or []),
        counts=statement_counts(response),
    )
