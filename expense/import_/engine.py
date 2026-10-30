"""The sheet import through the engine: `POST /transactions/import-sheet`, its
names table, the step that creates the names the sheet lacks, and the renames
of `--account-name`. No typer and no printing.

The engine reads the whole workbook, matches every row against the ledger and
writes everything or nothing (contract: POST /v1/transactions/import-sheet).
The app sends the file whole, as the bank import door sends a download, and
reads no cell of it.

The engine never looks a name up and never creates one: every answer lists
each name the sheet uses with a proposal, and the outcomes and counts come
only with a table giving every name its id
(contract: POST /v1/transactions/import-sheet, "Names"). So a run is one of
three steps (`Step`), each first a dry run without the table, which lists the
names and refuses a bad sheet before anything else is sent:

- the dry run: once every name has an id, a second dry run with the table
  answers the counts; while one lacks it, nothing more is sent;
- the create step: each missing name is created through its own route, and
  nothing is imported;
- the apply: written with the table, only once every name has an id.

Every write is one `ExpenseClient.post`, which carries its own idempotency key.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
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
class RenameRefused(ValueError):
    """A rename the import cannot take: malformed, or naming an account the sheet
    lacks. The message is the sentence the command shows."""


#: One `--account-name`: the sheet's name and the ledger name.
Rename = tuple[str, str]


def rename_key(name: str) -> str:
    """How a renamed sheet account is found: its name trimmed and
    case-insensitive."""
    return name.strip().casefold()


def parse_account_name(value: str) -> Rename:
    """`"BCP=Sueldo Soles"` → `("BCP", "Sueldo Soles")`.

    The ledger name is everything after the first `=`; the sheet's name is
    what comes before it (it may itself hold a colon; one ending in `:` and
    three capital letters is read as written with a currency, `saved_name`).
    """
    sheet, eq, ledger = value.partition("=")
    sheet, ledger = sheet.strip(), ledger.strip()
    if not eq or not sheet or not ledger:
        raise RenameRefused(f'{value!r} is not SHEET_NAME=LEDGER_NAME (e.g. "BCP=Sueldo Soles").')
    return sheet, ledger


_CURRENCY_SUFFIX = re.compile(r":[A-Z]{3}$")


def saved_name(saved_key: str) -> str:
    """The sheet name a saved key stands for: a saved key ending in `:` and an
    upper-case code (`"BCP:PEN"`) is read as its name written with a currency,
    so as `"BCP"`. A `--account-name` is read the same way, so a sheet account
    whose own name ends in `:` and three capital letters cannot be renamed."""
    return _CURRENCY_SUFFIX.sub("", saved_key.strip())


def saved_renames(saved: Mapping[str, str]) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """The config's `sheet_account_names` (`"BCP"` → `"Sueldo Soles"`) as
    `(renames, disputed)`, both keyed by `rename_key` of the sheet's name; a key
    with no name, or a rename with no ledger name, is left out.

    The keys of one name (`"BCP:PEN"`, `"BCP:USD"`, `"BCP"`) that go to one
    ledger name (compared as the engine compares account names) are one
    rename. Keys that go to different ledger names put the name in `disputed`
    with each ledger name once, in the order saved, and out of `renames`."""
    found: dict[str, list[str]] = {}
    for saved_key, ledger in saved.items():
        name, ledger = saved_name(saved_key), ledger.strip()
        if name and ledger:
            ledgers = found.setdefault(rename_key(name), [])
            if all(rename_key(ledger) != rename_key(seen) for seen in ledgers):
                ledgers.append(ledger)
    renames = {key: ledgers[0] for key, ledgers in found.items() if len(ledgers) == 1}
    disputed = {key: tuple(ledgers) for key, ledgers in found.items() if len(ledgers) > 1}
    return renames, disputed


def merge_renames(
    saved: Mapping[str, str], flags: Iterable[Rename]
) -> tuple[dict[str, str], dict[str, str], dict[str, tuple[str, ...]]]:
    """The saved renames with this run's flags: a flag replaces every saved key
    of the same sheet account, whatever its letter case and whether or not the
    key carries a currency. Returns the `sheet_account_names` to save, the
    renames and the disputed names (`saved_renames`). A flag's name is read like
    a saved key (`saved_name`)."""
    merged = dict(saved)
    for sheet, ledger in flags:
        for old in [
            k for k in merged if rename_key(saved_name(k)) == rename_key(saved_name(sheet))
        ]:
            del merged[old]
        merged[sheet] = ledger
    renames, disputed = saved_renames(merged)
    return merged, renames, disputed


class SavedRenamesDisputed(RenameRefused):
    """The saved renames send one sheet name to different ledger names: a usage
    error of the run, not of any `--account-name` typed."""


def check_disputed(table: list["NameEntry"], disputed: Mapping[str, tuple[str, ...]]) -> None:
    """Refuse (`SavedRenamesDisputed`) a sheet name the saved renames send to
    different ledger names; only the sheet's own accounts count."""
    for entry in table:
        ledgers = disputed.get(rename_key(entry.name)) if entry.kind == ACCOUNT else None
        if ledgers:
            quoted = [f'"{ledger}"' for ledger in ledgers]
            both = f"{', '.join(quoted[:-1])} and {quoted[-1]}"
            raise SavedRenamesDisputed(
                f'Your saved renames send "{entry.name}" to both {both}. '
                f'Choose one with --account-name "{entry.name}=<ledger name>".'
            )


# ---------------------------------------------------------------------------
# the names table
# ---------------------------------------------------------------------------
class Goes(Enum):
    """Where one name of the sheet goes."""

    YOURS = "yours"  # an account, category or hashtag you have
    MISSING = "missing"  # one you lack, which the create step creates


@dataclass(frozen=True)
class NameEntry:
    """One name the sheet uses, as the engine lists it, and where it goes."""

    kind: str  # ACCOUNT, CATEGORY or HASHTAG
    name: str  # the sheet's name, as the engine lists it
    #: An account's currencies, in the engine's order; empty for a category or hashtag.
    currencies: tuple[str, ...]
    rows: int  # the rows using it, as the engine counts them
    goes: Goes
    #: The id it goes to: the engine's proposal, or your account of its rename;
    #: None for a missing name.
    target_id: str | None
    #: The ledger name a renamed account goes to (`--account-name`, or a saved
    #: rename); None when it keeps the sheet's name.
    renamed_to: str | None = None

    @property
    def ledger_name(self) -> str:
        """The name it is written under: its rename, else the sheet's own,
        with no currency added."""
        return self.renamed_to or self.name


def _create_key(entry: NameEntry) -> tuple[str, str]:
    """Two missing names are one when the engine would refuse the second as
    taken: names are unique case-insensitively
    (contract: POST /v1/accounts, "Validation")
    (contract: POST /v1/categories) (contract: POST /v1/hashtags)."""
    return (entry.kind, entry.ledger_name.strip().casefold())


def _listed(answer: dict, kind: str) -> list[dict]:
    names = answer.get("names") or {}
    return list(names.get(_KINDS[kind][0]) or [])


def renamed_accounts(answer: dict, renames: Mapping[str, str]) -> bool:
    """Whether any account the answer lists has a rename: only then are your
    accounts read."""
    return any(rename_key(str(a.get("name"))) in renames for a in _listed(answer, ACCOUNT))


def names_table(
    answer: dict,
    renames: Mapping[str, str],
    accounts: list[dict],
) -> list[NameEntry]:
    """Every name the engine's answer lists, in its order (accounts, then
    categories, then hashtags), and where each goes.

    - A renamed account (`renames`, keyed by `rename_key`) goes to your
      account of the rename's name, when `accounts` (your accounts as
      `GET /accounts` lists them, archived and people included) holds one,
      compared as the engine compares account names; else it is missing, to
      be created under the rename (contract: POST /v1/accounts, "Validation").
    - Any other name goes to the engine's `proposed_id`, yours under that name
      (contract: POST /v1/transactions/import-sheet, "Names").
    - A name with neither is missing, to be created under the sheet's name,
      holding the currencies its rows are in.
    """
    yours = {
        str(a.get("name") or "").strip().casefold(): str(a["id"]) for a in accounts if a.get("id")
    }
    table: list[NameEntry] = []
    for kind in (ACCOUNT, CATEGORY, HASHTAG):
        for item in _listed(answer, kind):
            name = str(item.get("name"))
            currencies = tuple(str(c) for c in item.get("currencies") or ())
            rows = int(item.get("rows") or 0)
            renamed = renames.get(rename_key(name)) if kind == ACCOUNT else None
            if renamed is not None:
                target = yours.get(renamed.strip().casefold())
            else:
                proposed = item.get("proposed_id")
                target = str(proposed) if proposed else None
            goes = Goes.YOURS if target else Goes.MISSING
            table.append(NameEntry(kind, name, currencies, rows, goes, target, renamed))
    return table


def check_renames(table: list[NameEntry], flags: Iterable[Rename]) -> None:
    """Refuse (`RenameRefused`) a flag naming an account the sheet does not
    have. Two of the sheet's names renamed onto one account are sent as they
    are, with the same `account_id`: the engine decides what may share one
    (contract: POST /v1/transactions/import-sheet, "Names")."""
    listed = {rename_key(e.name) for e in table if e.kind == ACCOUNT}
    for sheet, _ledger in flags:
        if rename_key(saved_name(sheet)) not in listed:
            raise RenameRefused(f'the sheet has no account "{sheet}".')


def missing_names(table: list[NameEntry]) -> list[NameEntry]:
    """The names the create step creates, in the table's order: each missing
    entry, once per name the engine would hold as one (`_create_key`); an
    account that stands for several sheet names holds the currencies of all
    of them."""
    out: dict[tuple[str, str], NameEntry] = {}
    for entry in table:
        if entry.goes is not Goes.MISSING:
            continue
        key = _create_key(entry)
        first = out.get(key)
        if first is None:
            out[key] = entry
        else:
            extra = tuple(c for c in entry.currencies if c not in first.currencies)
            out[key] = replace(first, currencies=(*first.currencies, *extra))
    return list(out.values())


def table_body(table: list[NameEntry]) -> dict:
    """The `names` the engine takes: every entry with the id it goes to
    (contract: POST /v1/transactions/import-sheet, "Body"). Only a table with
    no missing name is sent."""
    body: dict[str, list[dict]] = {"accounts": [], "categories": [], "hashtags": []}
    for entry in table:
        listed, id_key, _route = _KINDS[entry.kind]
        if entry.target_id is None:
            raise ValueError(f"{entry.kind} {entry.name!r} has no id to send")
        body[listed].append({"name": entry.name, id_key: entry.target_id})
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
    split_rows: int  # the rows holding the split lines, as the engine counts them


def answer_counts(answer: dict) -> SheetCounts:
    counts = answer.get("counts") or {}
    return SheetCounts(
        **{key: int(counts.get(key) or 0) for key in SheetCounts.__dataclass_fields__}
    )


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
class Step(Enum):
    """What a run is asked to do."""

    DRY_RUN = "dry_run"  # show the names, and the counts once every name exists
    CREATE_NAMES = "create_names"  # create the missing names; import nothing
    APPLY = "apply"  # import, once every name exists


class Stage(Enum):
    """The call a run stopped at."""

    NAMES = "names"  # the dry run without the table: nothing created
    ACCOUNTS = "accounts"  # reading your accounts for a rename: nothing created
    COUNTS = "counts"  # the dry run with the table: nothing written
    CREATE = "create"  # creating a name: those before it were created
    APPLY = "apply"  # the apply with the table: nothing written


@dataclass(frozen=True)
class Created:
    """One name the create step created: its kind, the name it was created
    under (the sheet's, or its rename), an account's currencies, its id, and
    the engine's answer to the create, untouched."""

    kind: str
    name: str
    currencies: tuple[str, ...]
    id: str
    answer: dict = field(default_factory=dict, compare=False)


@dataclass
class SheetImport:
    """What one run of the sheet import comes to.

    `answer` is the engine's last answer, untouched: the dry run's with the
    table, or the apply's, when one was sent (`counted`), else the first dry
    run's; None when that was refused. `error` is what stopped the run, an
    engine refusal (`EngineError`, its envelope in `raw_body` as sent) or the
    engine out of reach; `stage` is where. `created` lists every name the
    create step created, one stopped part way included."""

    step: Step
    table: list[NameEntry] = field(default_factory=list)
    answer: dict | None = None
    counted: bool = False  # `answer` came with the table: it holds outcomes
    created: list[Created] = field(default_factory=list)
    error: EngineError | EngineConnectionError | None = None
    stage: Stage | None = None

    @property
    def missing(self) -> list[NameEntry]:
        return missing_names(self.table)

    @property
    def rows(self) -> list[SheetRow]:
        return answer_rows(self.answer or {})

    @property
    def counts(self) -> SheetCounts:
        return answer_counts(self.answer or {})


def _create_body(entry: NameEntry, new_id: str) -> dict:
    """A name's create: an account under its ledger name holding the
    currencies, as the sheet's rows use them (contract: POST /v1/accounts,
    "Required"); a category or hashtag under the sheet's name, with no colour
    (contract: POST /v1/categories) (contract: POST /v1/hashtags)."""
    body: dict = {"id": new_id, "name": entry.ledger_name}
    if entry.kind == ACCOUNT:
        body["currencies"] = [{"currency_code": code} for code in entry.currencies]
    return body


IMPORT_PATH = "/transactions/import-sheet"


def import_sheet(
    cfg: Config,
    data: bytes,
    *,
    step: Step,
    renames: Mapping[str, str],
    flags: Iterable[Rename] = (),
    disputed: Mapping[str, tuple[str, ...]] | None = None,
    verbose: bool = False,
) -> SheetImport:
    """Run one step of the sheet import on the workbook's bytes.

    A dry run without the table first: a refused sheet stops here, nothing
    created. Your accounts are read only when an account the sheet uses has a
    rename (`reads.fetch_accounts`), the `disputed` saved names the sheet uses
    (`check_disputed`) and this run's `flags` (`check_renames`) are checked
    against the sheet, each raising `RenameRefused` before anything else is
    sent. Then, by `step`:

    - `DRY_RUN`: with no name missing, the dry run again with the table, for
      the counts; with one missing, nothing more.
    - `CREATE_NAMES`: each missing name created, one create per name the
      engine would hold as one (`missing_names`); nothing imported.
    - `APPLY`: with no name missing, the apply with the table, whose answer
      is what happened; with one missing, nothing is sent.

    The first refusal stops the run and is kept whole, with what was created
    before it."""
    result = SheetImport(step=step)
    with ExpenseClient(cfg, verbose=verbose, timeout_read=IMPORT_READ_TIMEOUT) as client:
        try:
            result.stage = Stage.NAMES
            answer = client.post(IMPORT_PATH, request_body(data, dry_run=True))
            result.answer = answer
            accounts: list[dict] = []
            if renamed_accounts(answer, renames):
                result.stage = Stage.ACCOUNTS
                accounts = reads.items_of(
                    reads.fetch_accounts(
                        cfg, include_archived=True, include_people=True, verbose=verbose
                    )
                )
            table = names_table(answer, renames, accounts)
            check_disputed(table, disputed or {})
            check_renames(table, flags)
            result.table = table
            missing = result.missing

            if step is Step.CREATE_NAMES:
                result.stage = Stage.CREATE
                for entry in missing:
                    new_id = str(uuid4())
                    made = client.post(_KINDS[entry.kind][2], _create_body(entry, new_id))
                    result.created.append(
                        Created(entry.kind, entry.ledger_name, entry.currencies, new_id, made)
                    )
            elif not missing:
                result.stage = Stage.APPLY if step is Step.APPLY else Stage.COUNTS
                result.answer = client.post(
                    IMPORT_PATH,
                    request_body(data, dry_run=step is not Step.APPLY, names=table_body(table)),
                )
                result.counted = True
            result.stage = None
        except (EngineError, EngineConnectionError) as err:
            result.error = err
    return result
