"""A month's statement PDF → how the engine's answer reads. Pure: no HTTP, no
typer, no config.

The engine reads the PDF, matches each of its rows to a ledger line, and
answers what closing the month from it does, or did
(contract: POST /v1/statements/import). The app sends the file whole
(`request_body` in engine.py, the body of both uploads) and reads nothing in
it; this module only says how the answer reads, so the screens show the
engine's word. Nothing here matches, adds up or picks an account or a currency.
"""

from dataclasses import dataclass

from expense.formatting import signed_cents

#: A row's outcomes (contract: POST /v1/statements/import, "Response").
MATCHED = "matched"
NEW = "new"
EMPTY = "empty"


@dataclass(frozen=True)
class StatementRow:
    """One row of the paper as the engine read it, and what closing does (or,
    on a dry run, would do) with it."""

    #: Its place in the statement, counting from 1: the paper's number.
    place: int
    #: The currency of the account the row is on (`currency_code`).
    currency: str
    #: The day it is matched and created on.
    date_iso: str
    description: str | None
    #: A card's undated line: interest or a fee, dated the statement's last day.
    fee: bool
    amount_cents: int  # signed: negative = money out; 0 on an empty row
    outcome: str  # matched | new | empty
    #: Its line was matched one day off and is moved to the row's day (on a dry
    #: run, would be) (contract: POST /v1/statements/import, "The bank's day wins").
    redated: bool


def statement_rows(response: dict) -> list[StatementRow]:
    """The answer's `rows`, in the paper's order. Each amount comes as a
    magnitude and a `transaction_type`; `signed_cents` signs it."""
    return [
        StatementRow(
            place=int(item.get("place") or 0),
            currency=str(item.get("currency_code") or "?"),
            date_iso=str(item.get("date")),
            description=item.get("description"),
            fee=bool(item.get("fee")),
            amount_cents=signed_cents(item),
            outcome=str(item.get("outcome")),
            redated=bool(item.get("redated")),
        )
        for item in response.get("rows") or []
    ]


@dataclass(frozen=True)
class StatementBalance:
    """One currency's balances in the statement, as the paper gives them: one per
    currency the statement covers, a card's soles and its dollars each."""

    currency: str
    beginning_balance_cents: int | None
    ending_balance_cents: int | None


def statement_balances(response: dict) -> list[StatementBalance]:
    """The answer's `balances`, in its order: one per currency the statement
    covers, in the account's currency order (contract: POST /v1/statements/import,
    "Response"). A currency the paper does not cover has none."""
    return [
        StatementBalance(
            currency=str(balance.get("currency_code") or "?"),
            beginning_balance_cents=balance.get("beginning_balance_cents"),
            ending_balance_cents=balance.get("ending_balance_cents"),
        )
        for balance in response.get("balances") or []
    ]


def review_line_ids(statement: dict) -> list[str]:
    """The ids of the bank lines a close flagged for review: each balance's
    `review_lines`, in the balances' order, then those of each `not_covered`
    currency, the account's currencies the statement holds no balances for. A
    statement upload's apply answers its close as the completed statement,
    `statement` (contract: POST /v1/statements/{statement_id}/complete, "Response")."""
    ids: list[str] = []
    for entry in [*(statement.get("balances") or []), *(statement.get("not_covered") or [])]:
        named = entry.get("review_lines")
        if isinstance(named, list):
            ids.extend(str(line_id) for line_id in named if line_id)
    return ids


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
    """The answer as the screens read it: the statement's name and days,
    whether closing creates it, its balances, its rows, the ids of the lines
    taken out, and the counts."""

    name: str
    date_start: str
    date_end: str
    #: True when closing creates the statement; False when it fills an open draft.
    creates: bool
    balances: tuple[StatementBalance, ...]
    rows: tuple[StatementRow, ...]
    #: The lines in the open statement that the paper does not print, oldest
    #: first: taken out of it, never changed or deleted.
    taken_out: tuple[str, ...]
    counts: StatementCounts

    @property
    def fills_a_draft(self) -> bool:
        """True when the upload fills an open draft rather than creating it."""
        return not self.creates

    @property
    def several_currencies(self) -> bool:
        """A card's paper: one balance per currency."""
        return len(self.balances) > 1

    def lines_to_read(self) -> list[str]:
        """The ids the answer names a ledger line by alone, each once: the lines
        taken out, in the engine's order."""
        return list(dict.fromkeys(self.taken_out))


def statement_answer(response: dict) -> StatementAnswer:
    """The whole answer, every part as the engine sent it."""
    return StatementAnswer(
        name=str(response.get("name") or ""),
        date_start=str(response.get("date_start") or ""),
        date_end=str(response.get("date_end") or ""),
        creates=bool(response.get("creates")),
        balances=tuple(statement_balances(response)),
        rows=tuple(statement_rows(response)),
        taken_out=tuple(str(i) for i in response.get("taken_out") or []),
        counts=statement_counts(response),
    )
