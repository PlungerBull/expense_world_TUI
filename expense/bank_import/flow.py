"""The steps of a bank import: read the dropped file's bytes, list the accounts
as picks, make the one call, and name the statements that stop a move.
A statement PDF takes the same read and the same picks, then its own call
(`statement_call`) and the one read of the ledger lines its answer names by id
(`statement_lines`).

No typer and no printing: a file that cannot be read from disk is
`ImportRefused`, whose message is the sentence the door shows.
"""

from dataclasses import dataclass
from pathlib import Path

from expense import reads
from expense.bank_import.engine import ImportedRow, blocking_statements, request_body
from expense.errors import EngineConnectionError, EngineError, format_error
from expense.formatting import currencies_phrase


@dataclass(frozen=True)
class AccountPick:
    """One answer to "which account": a bank account and the currencies it
    holds (contract: "Bank Accounts", "`currencies`"). The call names the
    account by its id alone; the engine puts each row on the currency the
    row's own `Moneda` names (contract: POST /v1/transactions/import,
    "Accounts")."""

    name: str
    account_id: str
    currency_codes: tuple[str, ...]

    @property
    def holds_two(self) -> bool:
        """The account holds more than one currency, so its file's rows and
        days each name theirs."""
        return len(self.currency_codes) > 1

    @property
    def currencies(self) -> str:
        """`PEN`, or `PEN + USD` for an account holding both, in the order the
        engine lists them (contract: "Bank Accounts", "`currencies`")."""
        return currencies_phrase(self.currency_codes)


def account_picks(accounts: list[dict]) -> list[AccountPick]:
    """Every live, non-person account once, in the order given (the engine's:
    every real account first, `sort_order` ascending, then creation time,
    oldest first — contract: GET /v1/accounts, "Ordering"), each with the
    currencies it holds, its `currencies` (contract: "Bank Accounts", "`currencies`")."""
    return [
        AccountPick(
            str(a.get("name") or "(unnamed)"),
            str(a["id"]),
            tuple(str(c.get("currency_code") or "?") for c in a.get("currencies") or []),
        )
        for a in accounts
        if a.get("id") and not a.get("is_archived") and not a.get("is_person")
    ]


# ---------------------------------------------------------------------------
# reading the file: its bytes, nothing more
# ---------------------------------------------------------------------------
class ImportRefused(Exception):
    """A dropped file the app cannot send: it is gone, or cannot be read from
    disk. The message is the sentence the door shows; the cause is the
    `OSError`."""


def read_file(path: Path) -> bytes:
    """The file's bytes, as the bank gave them. Every cell is the engine's to
    read; this only reads the disk."""
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise ImportRefused(f"File not found: {path}") from exc
    except OSError as exc:
        raise ImportRefused(f"Could not open {path}: {exc.strerror or exc}") from exc


# ---------------------------------------------------------------------------
# the one call
# ---------------------------------------------------------------------------
def import_call(client, pick: AccountPick, data: bytes, *, dry_run: bool) -> dict:
    """`POST /transactions/import` on a client the caller opened: the file and
    the pick's account, the one request the door makes. The apply is this one
    call, not a dry run followed by a write: its response is what happened.
    The client's idempotency key covers a retry, under the client's default
    read timeout (60 s)."""
    return client.post(
        "/transactions/import", json_body=request_body(pick.account_id, data, dry_run=dry_run)
    )


def statement_call(client, pick: AccountPick, data: bytes, *, dry_run: bool) -> dict:
    """`POST /statements/import` on a client the caller opened: the PDF and
    the pick's account, with the body of the download's call (`request_body`).
    The engine closes the account's statement, every currency the paper covers
    together (contract: POST /v1/statements/import, "Accounts"). The apply is
    this one call, not a dry run followed by a write; the client's idempotency
    key covers a retry."""
    return client.post(
        "/statements/import",
        json_body=request_body(pick.account_id, data, dry_run=dry_run),
    )


def statement_lines(cfg, ids: list[str], *, verbose: bool) -> tuple[dict[str, dict], str | None]:
    """bank line id → the line, for the lines a statement's answer names by id
    alone: those taken out. One read by their ids
    (`reads.fetch_bank_lines_by_ids`), never while drawing; none when there are
    no ids. A failed read never hides what the upload does: the reason is
    returned for one line under the counts, and the lines go unread."""
    if not ids:
        return {}, None
    try:
        lines = reads.fetch_bank_lines_by_ids(cfg, ids, verbose=verbose)
    except (EngineError, EngineConnectionError) as err:
        return {}, format_error(err)
    return {str(line.get("id")): line for line in lines}, None


def statement_names(
    cfg, rows: list[ImportedRow], *, verbose: bool
) -> tuple[dict[str, str], str | None]:
    """statement id → name, for the completed statements that stop a row's
    move to the bank's day (the answer's `redate_blocked_by` carries their id
    only). Each distinct id is read once, by its id
    (contract: GET /v1/statements/{statement_id}). A failed read never hides
    what the import does: its rows still show, the statement unnamed, the
    other ids are still read, and the first failure's reason is returned for
    one line under the table."""
    names: dict[str, str] = {}
    failure: str | None = None
    for statement_id in blocking_statements(rows):
        try:
            body = reads.fetch_statement(cfg, statement_id, verbose=verbose)
        except (EngineError, EngineConnectionError) as err:
            failure = failure or format_error(err)
            continue
        names[statement_id] = str(body.get("name") or statement_id)
    return names, failure
