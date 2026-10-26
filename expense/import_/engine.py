"""The sheet import through the engine: `POST /transactions/import-sheet`, its
names table, and the apply's steps. No typer and no printing.

The engine reads the whole workbook, matches every row against the ledger and
writes everything or nothing (contract: POST /v1/transactions/import-sheet).
The app sends the file whole, as the bank import door sends a download, and
reads no cell of it.

The engine never looks a name up and never creates one: every answer lists
each name the sheet uses with a proposal, and the apply is written only with a
table giving every name its id (contract: POST /v1/transactions/import-sheet, "Names").
This module builds that table (`names_table`) and runs the import
(`import_sheet`): an apply is first a dry run without the table, so a refused
sheet creates nothing; then each name the table sends to a new one is created
through its own route; then the apply goes with the full table. Every write is
one `ExpenseClient.post`, which carries its own idempotency key.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from expense import reads
from expense.bank_import.engine import file_field
from expense.config import Config
from expense.errors import EngineConnectionError, EngineError
from expense.formatting import signed_cents
from expense.http import ExpenseClient

#: The three kinds of name a sheet uses, as the engine lists them in `names`.
ACCOUNT = "account"
CATEGORY = "category"
HASHTAG = "hashtag"

#: kind → (its list in `names`, the key of its id in the table, its create route).
_KINDS = {
    ACCOUNT: ("accounts", "account_id", "/accounts"),
    CATEGORY: ("categories", "category_id", "/categories"),
    HASHTAG: ("hashtags", "hashtag_id", "/hashtags"),
}

#: The read timeout of the import's calls: the engine reads and matches the whole
#: sheet in one request, which takes far longer than a single write.
IMPORT_READ_TIMEOUT = 300.0


def request_body(data: bytes, *, dry_run: bool, names: dict | None = None) -> dict:
    """The body the engine takes: `dry_run`, the workbook's bytes (`file_field`)
    and, when given, the confirmed table (`table_body`); a dry run may leave
    `names` out (contract: POST /v1/transactions/import-sheet, "Body")."""
    body: dict = {"dry_run": dry_run, "file": file_field(data)}
    if names is not None:
        body["names"] = names
    return body


# ---------------------------------------------------------------------------
# renames: --account-name and the config's `sheet_account_names`
# ---------------------------------------------------------------------------
def rename_key(name: str, currency: str) -> tuple[str, str]:
    """How a renamed sheet account is found: its name trimmed and
    case-insensitive, its currency upper-case."""
    return (name.strip().casefold(), currency.strip().upper())


def saved_renames(saved: Mapping[str, str]) -> dict[tuple[str, str], str]:
    """The config's `sheet_account_names` (`"BCP:PEN"` → `"Sueldo Soles"`, the
    currency after the last `:`) keyed by `rename_key`; a key without both a
    name and a currency is left out."""
    out: dict[tuple[str, str], str] = {}
    for key, ledger in saved.items():
        sheet, colon, currency = key.rpartition(":")
        if colon and sheet.strip() and currency.strip() and ledger.strip():
            out[rename_key(sheet, currency)] = ledger.strip()
    return out


# ---------------------------------------------------------------------------
# the names table
# ---------------------------------------------------------------------------
class Goes(Enum):
    """Where one name of the sheet goes."""

    YOURS = "yours"  # an account, category or hashtag you have
    NEW = "new"  # one the apply creates


@dataclass(frozen=True)
class NameEntry:
    """One name the sheet uses, as the engine lists it, and where it goes."""

    kind: str  # ACCOUNT, CATEGORY or HASHTAG
    name: str  # the sheet's name, as the engine lists it
    currency: str | None  # an account's; None for a category or hashtag
    rows: int  # the rows using it, as the engine counts them
    goes: Goes
    #: The id it goes to: the engine's proposal, or your account of its rename;
    #: None for a name the apply creates, until it is.
    target_id: str | None
    #: The ledger name a renamed account goes to (`--account-name`, or a saved
    #: rename); None when it keeps the sheet's name.
    renamed_to: str | None = None

    @property
    def ledger_name(self) -> str:
        """The name it is written under: its rename, else the sheet's own,
        with no currency added."""
        return self.renamed_to or self.name


def _create_key(entry: NameEntry) -> tuple[str, str, str | None]:
    """Two names the apply creates are one when the engine would refuse the
    second as taken: names are unique case-insensitively, an account's per
    currency (contract: POST /v1/accounts, "Validation")
    (contract: POST /v1/categories) (contract: POST /v1/hashtags)."""
    return (entry.kind, entry.ledger_name.strip().casefold(), entry.currency)


def _listed(answer: dict, kind: str) -> list[dict]:
    names = answer.get("names") or {}
    return list(names.get(_KINDS[kind][0]) or [])


def renamed_accounts(answer: dict, renames: Mapping[tuple[str, str], str]) -> bool:
    """Whether any account the answer lists has a rename: only then are your
    accounts read."""
    return any(
        rename_key(str(a.get("name")), str(a.get("currency_code"))) in renames
        for a in _listed(answer, ACCOUNT)
    )


def names_table(
    answer: dict,
    renames: Mapping[tuple[str, str], str],
    accounts: list[dict],
) -> list[NameEntry]:
    """Every name the engine's answer lists, in its order (accounts, then
    categories, then hashtags), and where each goes.

    - A renamed account (`renames`, keyed by `rename_key`) goes to your
      account of the rename's name in its currency, when `accounts` (your
      accounts as `GET /accounts` lists them, archived and people included)
      holds one, compared as the engine compares account names; else to a new
      one under the rename (contract: POST /v1/accounts, "Validation").
    - Any other name goes to the engine's `proposed_id`, yours under that name
      (contract: POST /v1/transactions/import-sheet, "Names").
    - A name with neither goes to a new one under the sheet's name: an account
      in the sheet's currency, never with the currency added to its name.
    """
    yours = {
        (str(a.get("name") or "").strip().casefold(), str(a.get("currency_code") or "")): str(
            a["id"]
        )
        for a in accounts
        if a.get("id")
    }
    table: list[NameEntry] = []
    for kind in (ACCOUNT, CATEGORY, HASHTAG):
        for item in _listed(answer, kind):
            name = str(item.get("name"))
            currency = str(item.get("currency_code")) if kind == ACCOUNT else None
            rows = int(item.get("rows") or 0)
            renamed = renames.get(rename_key(name, currency)) if currency is not None else None
            if renamed is not None:
                target = yours.get((renamed.strip().casefold(), str(currency)))
            else:
                proposed = item.get("proposed_id")
                target = str(proposed) if proposed else None
            goes = Goes.YOURS if target else Goes.NEW
            table.append(NameEntry(kind, name, currency, rows, goes, target, renamed))
    return table


def table_body(table: list[NameEntry], ids: Mapping[tuple[str, str, str | None], str]) -> dict:
    """The `names` the apply sends: every entry with its id, its target or the
    one created for it (`ids`, keyed by `_create_key`)
    (contract: POST /v1/transactions/import-sheet, "Body")."""
    body: dict[str, list[dict]] = {"accounts": [], "categories": [], "hashtags": []}
    for entry in table:
        listed, id_key, _route = _KINDS[entry.kind]
        target = entry.target_id or ids[_create_key(entry)]
        sent = {"name": entry.name, id_key: target}
        if entry.currency is not None:
            sent["currency_code"] = entry.currency
        body[listed].append(sent)
    return body


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


def answer_counts(answer: dict) -> SheetCounts:
    counts = answer.get("counts") or {}
    return SheetCounts(
        **{key: int(counts.get(key) or 0) for key in SheetCounts.__dataclass_fields__}
    )


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
class Stage(Enum):
    """The step a run stopped at."""

    DRY_RUN = "dry_run"  # the dry run without the table: nothing created
    ACCOUNTS = "accounts"  # reading your accounts for a rename: nothing created
    CREATE = "create"  # creating a name: those before it were created
    APPLY = "apply"  # the apply with the table: every name new to it was created


@dataclass(frozen=True)
class Created:
    """One name the apply created, and its id."""

    kind: str
    name: str  # the name it was created under: the sheet's, or its rename
    currency: str | None  # an account's
    id: str


@dataclass
class SheetImport:
    """What one run of the sheet import comes to.

    `answer` is the engine's last answer, untouched: the apply's when it was
    written, else the dry run's (a run stopped after the dry run included);
    None when the dry run was refused. `error` is
    what stopped the run, an engine refusal (`EngineError`, its envelope in
    `raw_body` as sent) or the engine out of reach; `stage` is where.
    `created` lists every name the run created, a run stopped after some
    creates included."""

    applied: bool  # an apply was asked for
    table: list[NameEntry] = field(default_factory=list)
    answer: dict | None = None
    created: list[Created] = field(default_factory=list)
    error: EngineError | EngineConnectionError | None = None
    stage: Stage | None = None

    @property
    def rows(self) -> list[SheetRow]:
        return answer_rows(self.answer or {})

    @property
    def counts(self) -> SheetCounts:
        return answer_counts(self.answer or {})


def _create_body(entry: NameEntry, new_id: str) -> dict:
    """A name's create: an account under its ledger name in the sheet's
    currency (contract: POST /v1/accounts); a category or hashtag under the
    sheet's name, with no colour
    (contract: POST /v1/categories) (contract: POST /v1/hashtags)."""
    body = {"id": new_id, "name": entry.ledger_name}
    if entry.currency is not None:
        body["currency_code"] = entry.currency
    return body


def import_sheet(
    cfg: Config,
    data: bytes,
    *,
    apply: bool,
    renames: Mapping[tuple[str, str], str],
    verbose: bool = False,
) -> SheetImport:
    """Run the sheet import on the workbook's bytes.

    A dry run without the table first: a refused sheet stops here, nothing
    created. Your accounts are read only when an account the sheet uses has a
    rename (`reads.fetch_accounts`). Without `apply` that is all. With it, each
    name the table sends to a new one is created, one create per name the
    engine would hold as one (`_create_key`), then the apply goes with every
    name mapped; its answer is what happened. The first refusal stops the run
    and is kept whole, with what was created before it."""
    result = SheetImport(applied=apply)
    with ExpenseClient(cfg, verbose=verbose, timeout_read=IMPORT_READ_TIMEOUT) as client:
        try:
            result.stage = Stage.DRY_RUN
            answer = client.post("/transactions/import-sheet", request_body(data, dry_run=True))
            result.answer = answer
            accounts: list[dict] = []
            if renamed_accounts(answer, renames):
                result.stage = Stage.ACCOUNTS
                accounts = reads.items_of(
                    reads.fetch_accounts(
                        cfg, include_archived=True, include_people=True, verbose=verbose
                    )
                )
            result.table = names_table(answer, renames, accounts)
            if not apply:
                result.stage = None
                return result

            result.stage = Stage.CREATE
            ids: dict[tuple[str, str, str | None], str] = {}
            for entry in result.table:
                key = _create_key(entry)
                if entry.goes is not Goes.NEW or key in ids:
                    continue
                new_id = str(uuid4())
                client.post(_KINDS[entry.kind][2], _create_body(entry, new_id))
                ids[key] = new_id
                result.created.append(
                    Created(entry.kind, entry.ledger_name, entry.currency, new_id)
                )

            result.stage = Stage.APPLY
            result.answer = client.post(
                "/transactions/import-sheet",
                request_body(data, dry_run=False, names=table_body(result.table, ids)),
            )
            result.stage = None
        except (EngineError, EngineConnectionError) as err:
            result.error = err
    return result
