"""The sheet import through the engine: `POST /transactions/import-sheet`, the names
table it answers, and the body the review sends. No typer and no printing.

The engine reads the whole workbook, matches every row against the ledger and
writes everything or nothing (contract: POST /v1/transactions/import-sheet).
The app sends the file whole, as the bank import door sends a download, and
reads no cell of it.

The engine never looks a name up: every answer lists each name the sheet uses with
a proposal, and the outcomes and counts come only with a table giving every name its
id (contract: POST /v1/transactions/import-sheet, "Names"). It makes an account,
category or hashtag only from the `create` the same request lists, all of it landing
with the rows or none of it (contract: POST /v1/transactions/import-sheet, "Create").
So the command sends the sheet as a dry run without the table (`import_sheet`), which lists
the names and refuses a bad sheet before anything else is sent, and opens the review on it
(expense/tui/screens/import_sheet.py).

The review makes what is missing: it sends `create` and `names` through `send_review`.
Every write is one `ExpenseClient.post`, which carries its own idempotency key.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import NamedTuple
from uuid import uuid4

from expense.bank_import.engine import file_field
from expense.config import Config
from expense.errors import EngineConnectionError, EngineError
from expense.formatting import signed_cents
from expense.http import ExpenseClient

#: The three kinds of name a sheet uses, as the engine lists them in `names`.
ACCOUNT = "account"
CATEGORY = "category"
HASHTAG = "hashtag"

#: kind → (its list in `names` and in `create`, the key of its id in the table).
_KINDS = {
    ACCOUNT: ("accounts", "account_id"),
    CATEGORY: ("categories", "category_id"),
    HASHTAG: ("hashtags", "hashtag_id"),
}

#: The read timeout of the import's calls: the engine reads and matches the whole
#: sheet in one request, which takes far longer than a single write.
IMPORT_READ_TIMEOUT = 300.0

IMPORT_PATH = "/transactions/import-sheet"


def request_body(
    data: bytes, *, dry_run: bool, names: dict | None = None, create: dict | None = None
) -> dict:
    """The body the engine takes: `dry_run`, the workbook's bytes (`file_field`) and,
    when given, the confirmed table (`table_body`, `review_names`) and what `create`
    makes; a dry run may leave `names` out (contract: POST /v1/transactions/import-sheet,
    "Body")."""
    body: dict = {"dry_run": dry_run, "file": file_field(data)}
    if names is not None:
        body["names"] = names
    if create is not None:
        body["create"] = create
    return body


# ---------------------------------------------------------------------------
# the names table
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Suggestion:
    """The engine's guess for an account the caller lacks, to show the owner and never
    applied by itself (contract: POST /v1/transactions/import-sheet, "Names")."""

    kind: str | None
    bank_code: str | None
    last4: str | None


@dataclass(frozen=True)
class NameEntry:
    """One name the sheet uses, as the engine lists it."""

    kind: str  # ACCOUNT, CATEGORY or HASHTAG
    name: str  # the sheet's name, as the engine lists it
    #: An account's currencies, in the engine's order; empty for a category or hashtag.
    currencies: tuple[str, ...]
    rows: int  # the rows using it, as the engine counts them
    #: The id the engine proposes: yours under that name; None for a missing name.
    target_id: str | None
    #: An account the caller lacks: the engine's guess; None beside a proposal.
    suggestion: Suggestion | None = None

    @property
    def missing(self) -> bool:
        return self.target_id is None


def create_key(entry: NameEntry) -> tuple[str, str]:
    """Two names are one when the engine would refuse the second as taken: names are
    unique case-insensitively (contract: POST /v1/categories) (contract: POST /v1/hashtags)."""
    return (entry.kind, entry.name.strip().casefold())


def made_key(entry: NameEntry) -> tuple[str, str]:
    """What a thing the review makes is kept under: an account by its name as the engine lists
    it (two spellings are two accounts), a category or hashtag by `create_key` (two spellings
    are one the engine would refuse to make twice)."""
    return (entry.kind, entry.name) if entry.kind == ACCOUNT else create_key(entry)


def _listed(answer: dict, kind: str) -> list[dict]:
    names = answer.get("names") or {}
    return list(names.get(_KINDS[kind][0]) or [])


def _suggestion(item: dict) -> Suggestion | None:
    raw = item.get("suggestion")
    if not raw:
        return None
    return Suggestion(raw.get("kind"), raw.get("bank_code"), raw.get("last4"))


def names_table(answer: dict) -> list[NameEntry]:
    """Every name the engine's answer lists, in its order (accounts, then categories,
    then hashtags), each with the id the engine proposes
    (contract: POST /v1/transactions/import-sheet, "Names")."""
    table: list[NameEntry] = []
    for kind in (ACCOUNT, CATEGORY, HASHTAG):
        for item in _listed(answer, kind):
            proposed = item.get("proposed_id")
            table.append(
                NameEntry(
                    kind,
                    str(item.get("name")),
                    tuple(str(c) for c in item.get("currencies") or ()),
                    int(item.get("rows") or 0),
                    str(proposed) if proposed else None,
                    _suggestion(item) if kind == ACCOUNT else None,
                )
            )
    return table


def missing_names(table: list[NameEntry]) -> list[NameEntry]:
    """The categories and hashtags to make, in the table's order: each missing one,
    once per name the engine would hold as one (`create_key`)."""
    out: dict[tuple[str, str], NameEntry] = {}
    for entry in table:
        if entry.missing and entry.kind != ACCOUNT:
            out.setdefault(create_key(entry), entry)
    return list(out.values())


def missing_accounts(table: list[NameEntry]) -> list[NameEntry]:
    """The sheet's accounts with no account, one per sheet name, in the table's order."""
    return [e for e in table if e.kind == ACCOUNT and e.missing]


def table_body(table: list[NameEntry]) -> dict:
    """The `names` the engine takes: every entry with the id it goes to
    (contract: POST /v1/transactions/import-sheet, "Body"). Only a table with
    no missing name is sent."""
    body: dict[str, list[dict]] = {"accounts": [], "categories": [], "hashtags": []}
    for entry in table:
        listed, id_key = _KINDS[entry.kind]
        if entry.target_id is None:
            raise ValueError(f"{entry.kind} {entry.name!r} has no id to send")
        body[listed].append({"name": entry.name, id_key: entry.target_id})
    return body


# ---------------------------------------------------------------------------
# what the review makes
# ---------------------------------------------------------------------------
def new_ids(table: list[NameEntry]) -> dict[tuple[str, str], str]:
    """An id for each thing the review makes, the client's own as on the create routes:
    one per account with no account and one per category or hashtag name
    (`missing_names`). Made once and kept, so every send of the same review carries the
    same ids."""
    return {made_key(e): str(uuid4()) for e in [*missing_accounts(table), *missing_names(table)]}


def account_entry(account_id: str, currencies: tuple[str, ...], values: Mapping[str, str]) -> dict:
    """One `create.accounts` entry from the lines the owner set (`type`, `bank`, `last4`,
    `name`, `statement_code`, `archive`, as the form holds them): a bank account's code and
    last 4, a person's name, a cash account none of the four, then the sheet's currencies
    (contract: POST /v1/transactions/import-sheet, "Create")."""
    kind = values["type"]
    entry: dict = {"id": account_id, "kind": kind}
    if kind == "person":
        entry["name"] = values["name"]
    elif kind == "bank":
        entry["bank_code"] = values["bank"]
        entry["last4"] = values["last4"]
        if values.get("statement_code"):
            entry["statement_code"] = values["statement_code"]
    entry["currencies"] = list(currencies)
    entry["archived"] = values.get("archive") == "yes"
    return entry


def review_names(table: list[NameEntry], ids: Mapping[tuple[str, str], str]) -> dict:
    """The `names` of the review: every entry to the id the engine proposed, else to the
    id the review makes it under."""
    return table_body(
        [e if e.target_id else _with_id(e, ids[made_key(e)]) for e in table],
    )


def _with_id(entry: NameEntry, target_id: str) -> NameEntry:
    return NameEntry(
        entry.kind, entry.name, entry.currencies, entry.rows, target_id, entry.suggestion
    )


def review_create(
    table: list[NameEntry],
    ids: Mapping[tuple[str, str], str],
    accounts: Mapping[str, Mapping[str, str]],
) -> dict:
    """The `create` of the review: an entry for each account with no account, in the
    table's order, from the lines set for its sheet name in `accounts`
    (`account_entry`), then the categories and the hashtags to make."""
    body: dict[str, list[dict]] = {
        "accounts": [
            account_entry(ids[made_key(e)], e.currencies, accounts[e.name])
            for e in missing_accounts(table)
        ],
        "categories": [],
        "hashtags": [],
    }
    for entry in missing_names(table):
        body[_KINDS[entry.kind][0]].append({"id": ids[made_key(entry)], "name": entry.name})
    return body


def send_review(
    client: ExpenseClient,
    data: bytes,
    table: list[NameEntry],
    ids: Mapping[tuple[str, str], str],
    accounts: Mapping[str, Mapping[str, str]],
    *,
    dry_run: bool,
) -> dict:
    """The review's one call: the dry run that judges and counts it, or the apply with
    the same body. Raises what the client raises."""
    body = request_body(
        data,
        dry_run=dry_run,
        names=review_names(table, ids),
        create=review_create(table, ids, accounts),
    )
    return client.post(IMPORT_PATH, body)


class CreateRefusal(NamedTuple):
    """One refusal keyed `create.<list>.<i>.<field>`: the list (`accounts`, `categories`
    or `hashtags`), the entry's place `i` in what was sent, the engine's field (None for
    the entry alone) and its words."""

    listed: str
    place: int
    field: str | None
    words: str


def create_refusals(err: Exception) -> list[CreateRefusal]:
    """The refusals of `err` when every key it names is a `create.<list>.<i>…` one, in the
    engine's order; else none (the refusal is of the file, the rows or the table, which
    the engine answers alone) (contract: POST /v1/transactions/import-sheet, "Create")."""
    if not isinstance(err, EngineError) or not err.fields:
        return []
    found: list[CreateRefusal] = []
    for key, words in err.fields.items():
        bits = str(key).split(".", 3)
        if (
            len(bits) < 3
            or bits[0] != "create"
            or bits[1] not in {listed for listed, _ in _KINDS.values()}
            or not bits[2].isdigit()
        ):
            return []
        found.append(
            CreateRefusal(bits[1], int(bits[2]), bits[3] if len(bits) == 4 else None, str(words))
        )
    return found


# ---------------------------------------------------------------------------
# the answer
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SheetRow:
    """One data row as the engine read it, and what it did (or, on a dry run,
    would do) with it (contract: POST /v1/transactions/import-sheet, "Response")."""

    row: int  # the spreadsheet's number; the first data row is 2
    account_id: str | None  # None on a dry run without the table
    date_iso: str
    title: str
    amount_cents: int  # signed: negative = outflow; 0 on a zero row
    outcome: str | None  # new | matched | sealed | skipped; None without the table
    is_opening_balance: bool | None
    transaction_id: str | None
    bank_line_id: str | None


def answer_rows(answer: dict) -> list[SheetRow]:
    """The answer's `rows`, in sheet order; each amount comes as a magnitude
    and a `transaction_type`, which `signed_cents` signs."""
    return [
        SheetRow(
            row=int(item.get("row") or 0),
            account_id=item.get("account_id"),
            date_iso=str(item.get("date")),
            title=str(item.get("title")),
            amount_cents=signed_cents(item),
            outcome=item.get("outcome"),
            is_opening_balance=item.get("is_opening_balance"),
            transaction_id=item.get("transaction_id"),
            bank_line_id=item.get("bank_line_id"),
        )
        for item in answer.get("rows") or []
    ]


@dataclass(frozen=True)
class SheetCounts:
    """The answer's `counts`, as the engine counted them."""

    new: int
    matched: int
    sealed: int
    skipped: int
    opening_balances: int
    split_lines: int
    split_rows: int  # the rows holding the split lines, as the engine counts them


def answer_counts(answer: dict) -> SheetCounts:
    counts = answer.get("counts") or {}
    return SheetCounts(
        **{key: int(counts.get(key) or 0) for key in SheetCounts.__dataclass_fields__}
    )


@dataclass(frozen=True)
class MadeCounts:
    """The answer's `created`: the accounts, categories and hashtags the request made
    (on a dry run, would make)."""

    accounts: int
    categories: int
    hashtags: int


def answer_created(answer: dict) -> MadeCounts:
    created = answer.get("created") or {}
    return MadeCounts(
        **{key: int(created.get(key) or 0) for key in MadeCounts.__dataclass_fields__}
    )


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
@dataclass
class SheetImport:
    """The first dry run: the engine's answer untouched and the names table built from it,
    or, when it stopped the run, `error`: an engine refusal (`EngineError`, its envelope in
    `raw_body` as sent) or the engine out of reach."""

    table: list[NameEntry] = field(default_factory=list)
    answer: dict | None = None
    error: EngineError | EngineConnectionError | None = None

    @property
    def rows(self) -> list[SheetRow]:
        return answer_rows(self.answer or {})


@dataclass(frozen=True)
class SheetReview:
    """What the app opens the review on: the sheet's file name and bytes, the names the first
    dry run listed and how many rows it read, and the settings the command read."""

    file_name: str
    data: bytes
    table: list[NameEntry]
    rows: int
    #: The settings the command read: the app uses them, never reading the file again
    #: (a pipe gives its contents once).
    cfg: Config


def import_sheet(cfg: Config, data: bytes, *, verbose: bool = False) -> SheetImport:
    """The sheet as a dry run without the table: it lists every name the sheet uses and
    refuses a bad sheet before anything else is sent. The first refusal is kept whole."""
    result = SheetImport()
    with ExpenseClient(cfg, verbose=verbose, timeout_read=IMPORT_READ_TIMEOUT) as client:
        try:
            result.answer = client.post(IMPORT_PATH, request_body(data, dry_run=True))
            result.table = names_table(result.answer)
        except (EngineError, EngineConnectionError) as err:
            result.error = err
    return result
