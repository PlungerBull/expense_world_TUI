"""The steps of a bank import: read the dropped file's bytes, list the accounts
as picks, make the one call, and name the reconciliations that stop a move.
A statement PDF takes the same read and the same picks, then its own call
(`statement_call`) and the one read of the ledger lines its answer names by id
(`statement_lines`).

No typer and no printing: a file that cannot be read from disk is
`ImportRefused`, whose message is the sentence the door shows.
"""

from dataclasses import dataclass
from pathlib import Path

from expense import reads
from expense.bank_import.engine import ImportedRow, blocking_reconciliations, request_body
from expense.errors import EngineConnectionError, EngineError, format_error

#: The card's account sent as `account_id`: the engine puts each currency's
#: rows on its own account, whichever of the two is named
#: (contract: POST /v1/transactions/import, "Accounts").
SENT_CURRENCY = "PEN"


@dataclass(frozen=True)
class AccountPick:
    """One answer to "which account": an account, or a card's two accounts.

    `accounts` are `(id, name, currency)`, in the engine's order: one, or a
    card's two, paired by the engine's `statement_partner_id`."""

    name: str
    accounts: tuple[tuple[str, str, str], ...]

    @property
    def account_id(self) -> str:
        """The account the call names: the card's soles one, else the first."""
        for ident, _name, currency in self.accounts:
            if currency == SENT_CURRENCY:
                return ident
        return self.accounts[0][0]

    @property
    def is_card(self) -> bool:
        return len(self.accounts) > 1

    @property
    def currencies(self) -> str:
        """`PEN`, or `PEN + USD` for a card."""
        return " + ".join(sorted(currency for _id, _name, currency in self.accounts))

    @property
    def account_names(self) -> dict[str, str]:
        """account id → its name, for naming the accounts of `day_mismatches`."""
        return {ident: name for ident, name, _currency in self.accounts}

    def currency_of(self, account_id: str) -> str:
        """The currency of the account the engine put a row on; `?` for an
        account the pick does not hold."""
        for ident, _name, currency in self.accounts:
            if ident == account_id:
                return currency
        return "?"


def card_name(first: tuple[str, str, str], second: tuple[str, str, str]) -> str:
    """What a card's line is called: the name its two accounts share once each
    drops its own currency code at the end (`BCP Signature PEN` and `BCP
    Signature USD` → `BCP Signature`). Two names that share none show both,
    joined by ` / `."""
    bases = []
    for _id, name, currency in (first, second):
        words = name.split()
        if len(words) > 1 and words[-1].upper() == currency.upper():
            words = words[:-1]
        bases.append(" ".join(words))
    if bases[0] == bases[1]:
        return bases[0]
    return f"{first[1]} / {second[1]}"


def account_picks(accounts: list[dict]) -> list[AccountPick]:
    """Every live, non-person account once, in the order given (the engine's:
    `sort_order` ascending, then creation time, oldest first —
    contract: GET /v1/accounts, "Ordering"), except a card's two accounts,
    which are one pick where the first of them stands. Two accounts are a card
    only when the engine names one as the other's `statement_partner_id`
    (`reads.card_partners`); a shared name pairs nothing."""
    live = [
        a for a in accounts if a.get("id") and not a.get("is_archived") and not a.get("is_person")
    ]
    partners = reads.card_partners(live)
    taken: set[str] = set()
    picks: list[AccountPick] = []
    for a in live:
        ident = str(a["id"])
        if ident in taken:
            continue
        own = (ident, str(a.get("name") or "(unnamed)"), str(a.get("currency_code") or "?"))
        taken.add(ident)
        partner = partners.get(ident)
        if partner is None or partner[0] in taken:
            picks.append(AccountPick(own[1], (own,)))
            continue
        taken.add(partner[0])
        picks.append(AccountPick(card_name(own, partner), (own, partner)))
    return picks


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
    """`POST /reconciliations/import` on a client the caller opened: the PDF
    and the pick's account, with the body of the download's call
    (`request_body`). A card's soles account is named; the engine closes both
    halves from either (contract: POST /v1/reconciliations/import). The apply
    is this one call, not a dry run followed by a write; the client's
    idempotency key covers a retry."""
    return client.post(
        "/reconciliations/import",
        json_body=request_body(pick.account_id, data, dry_run=dry_run),
    )


def statement_lines(cfg, ids: list[str], *, verbose: bool) -> tuple[dict[str, dict], str | None]:
    """bank line id → the line, for the lines a statement's answer names by id
    alone: those taken out and the near misses. One read by their ids
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


def reconciliation_names(
    cfg, rows: list[ImportedRow], *, verbose: bool
) -> tuple[dict[str, str], str | None]:
    """reconciliation id → name, for the reconciliations that stop a row's
    move to the bank's day (the response carries their id only). Each distinct
    id is read once, by its id (contract: GET /v1/reconciliations/{reconciliation_id}).
    A failed read never hides what the import does: its rows still show, the
    reconciliation unnamed, the other ids are still read, and the first
    failure's reason is returned for one line under the table."""
    names: dict[str, str] = {}
    failure: str | None = None
    for reconciliation_id in blocking_reconciliations(rows):
        try:
            body = reads.fetch_reconciliation(cfg, reconciliation_id, verbose=verbose)
        except (EngineError, EngineConnectionError) as err:
            failure = failure or format_error(err)
            continue
        names[reconciliation_id] = str(body.get("name") or reconciliation_id)
    return names, failure
