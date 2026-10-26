"""The sheet import through the engine: what is sent, the names table, and the
apply's steps (contract: POST /v1/transactions/import-sheet).

Every answer is built by the fake engine's own builders in tests/unit/helpers.py
(`sheet_import_answer`), shaped from the contract's response schema; every
refusal is the envelope the practice engine sent for the same case. The real
HTTP client runs under respx, so each write's idempotency key is seen.
"""

import ast
import base64
import json
from pathlib import Path

import httpx
import pytest
import respx

from expense import config as config_module
from expense.bank_import.engine import file_field
from expense.errors import EngineConnectionError, EngineError
from expense.import_ import engine
from expense.import_.engine import (
    ACCOUNT,
    CATEGORY,
    HASHTAG,
    Created,
    Goes,
    NameEntry,
    SheetCounts,
    Stage,
    import_sheet,
    names_table,
    rename_key,
    request_body,
    saved_renames,
    table_body,
)
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import (
    error_body,
    sheet_import_answer,
    sheet_name_use,
    sheet_row,
)

PACKAGE = Path(__file__).resolve().parents[2] / "expense"
DATA = b"PK\x03\x04 a made-up workbook"
IMPORT = f"{BASE}/v1/transactions/import-sheet"

#: The refusals as the practice engine sent them on 2026-10-26, for made-up sheets.
LAYOUT = error_body(
    "VALIDATION_ERROR",
    "The file is not the owner's sheet.",
    {"file": "Row 1 must be the header 'description | HASHTAG | …'; it is 'Descripcion | …'."},
    {"file": "UNEXPECTED_LAYOUT"},
)
ROWS_REFUSED = error_body(
    "VALIDATION_ERROR",
    "Import validation failed.",
    {
        "rows.4.amount_cents": "Row 4: MONTO holds 'abc', not a number.",
        "rows.6.amount_cents": "Row 6: MONTO -1.234 is not a whole number of cents.",
        "rows.5.date": "Must not be in the future.",
    },
    {
        "rows.4.amount_cents": "UNEXPECTED_LAYOUT",
        "rows.6.amount_cents": "NOT_WHOLE_CENTS",
        "rows.5.date": "FUTURE_DATE",
    },
)
NOT_MAPPED = error_body(
    "VALIDATION_ERROR",
    "Import validation failed.",
    {"names.categories": "Must give an id for every name the sheet uses; missing: 'food'."},
    {"names.categories": "NAME_NOT_MAPPED"},
)
INVALID_REFERENCE = error_body(
    "VALIDATION_ERROR",
    "Import validation failed.",
    {"names.accounts.0.account_id": "Must reference an active, non-archived account."},
    {"names.accounts.0.account_id": "INVALID_REFERENCE"},
)
NAME_EXISTS = error_body(
    "CONFLICT",
    "A category with this name already exists.",
    {"name": "Already taken."},
    {"name": "NAME_EXISTS"},
)


def _cfg():
    return config_module.ensure_loaded()


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


def _account(ident: str, name: str, currency: str = "PEN", **extra) -> dict:
    return {"id": ident, "name": name, "currency_code": currency, "is_archived": False, **extra}


#: A sheet using one account in two currencies, one you have; a category you have
#: and one you do not; a hashtag you do not.
DRY = sheet_import_answer(
    accounts=[
        sheet_name_use("BCP Oro", 3, "acc-oro-pen", currency_code="PEN"),
        sheet_name_use("BCP Oro", 2, None, currency_code="USD"),
    ],
    categories=[sheet_name_use("food", 4, "cat-food"), sheet_name_use("travel", 1)],
    hashtags=[sheet_name_use("trip", 5)],
    rows=[sheet_row(r) for r in range(2, 7)],
)


def _applied(names: dict) -> dict:
    """The apply's answer: each row on the account the sent table gives it."""
    account_id = names["accounts"][0]["account_id"]
    rows = [
        sheet_row(
            r,
            account_id=account_id,
            outcome="new",
            is_opening_balance=False,
            transaction_id=f"t-{r}",
            bank_line_id=f"bl-{r}",
        )
        for r in range(2, 7)
    ]
    return sheet_import_answer(
        accounts=DRY["names"]["accounts"],
        categories=DRY["names"]["categories"],
        hashtags=DRY["names"]["hashtags"],
        rows=rows,
        dry_run=False,
    )


def _engine(dry: dict | httpx.Response = DRY, apply: object = None):
    """Route the import: a body without `names` answers `dry`, one with them
    answers `apply` (by default `_applied`), a response, or raises it."""

    def answer(request: httpx.Request) -> httpx.Response:
        body = _body(request)
        if "names" not in body:
            return dry if isinstance(dry, httpx.Response) else httpx.Response(200, json=dry)
        if apply is None:
            return httpx.Response(200, json=_applied(body["names"]))
        if isinstance(apply, Exception):
            raise apply
        return apply  # type: ignore[return-value]

    return respx.post(IMPORT).mock(side_effect=answer)


def _creates() -> dict[str, respx.Route]:
    return {
        path: respx.post(f"{BASE}/v1/{path}").mock(return_value=httpx.Response(201, json={}))
        for path in ("accounts", "categories", "hashtags")
    }


def _writes() -> list[httpx.Request]:
    return [call.request for call in respx.calls if call.request.method == "POST"]


# ---- what is sent ------------------------------------------------------------------
def test_the_body_is_the_file_whole_in_base64_and_dry_run():
    """`dry_run` and the workbook's bytes, encoded as the bank import encodes a
    download; `names` only when given (contract: POST /v1/transactions/import-sheet, "Body")."""
    data = bytes(range(256)) * 50
    body = request_body(data, dry_run=True)
    assert set(body) == {"dry_run", "file"}
    assert body["file"] == file_field(data)
    assert base64.b64decode(body["file"], validate=True) == data
    names = {"accounts": [], "categories": [], "hashtags": []}
    assert request_body(data, dry_run=False, names=names) == {
        "dry_run": False,
        "file": file_field(data),
        "names": names,
    }


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_the_module_reads_no_cell_and_shares_the_bank_imports_encoding():
    """No spreadsheet library and none of the app's own sheet reader: the file
    goes to the engine as bytes, through the bank import's one encoder."""
    imported = _imports(PACKAGE / "import_" / "engine.py")
    assert "openpyxl" not in imported
    assert not imported & {
        "expense.import_.reader",
        "expense.import_.parse",
        "expense.import_.plan",
        "expense.import_.mapping",
    }
    assert "expense.bank_import.engine" in imported
    assert engine.file_field is file_field
    assert "b64encode" not in (PACKAGE / "import_" / "engine.py").read_text()


# ---- the names table ---------------------------------------------------------------
def _goes(table: list[NameEntry]) -> list[tuple]:
    return [(e.kind, e.name, e.currency, e.goes, e.target_id, e.ledger_name) for e in table]


def test_each_name_goes_to_its_proposal_else_to_a_new_one_under_the_sheets_name():
    """An account used in two currencies is two names, each its own entry, the
    new one keeping the sheet's name with no currency added."""
    table = names_table(DRY, {}, [])
    assert _goes(table) == [
        (ACCOUNT, "BCP Oro", "PEN", Goes.YOURS, "acc-oro-pen", "BCP Oro"),
        (ACCOUNT, "BCP Oro", "USD", Goes.NEW, None, "BCP Oro"),
        (CATEGORY, "food", None, Goes.YOURS, "cat-food", "food"),
        (CATEGORY, "travel", None, Goes.NEW, None, "travel"),
        (HASHTAG, "trip", None, Goes.NEW, None, "trip"),
    ]
    assert [e.rows for e in table] == [3, 2, 4, 1, 5]
    assert all(e.renamed_to is None for e in table)


def test_a_renamed_account_goes_to_yours_of_that_name_and_currency_over_the_proposal():
    """The rename wins over the proposal; your account is found by its name,
    trimmed and in any letter case, in the entry's own currency."""
    renames = {rename_key(" bcp oro ", "pen"): "Sueldo Soles"}
    accounts = [
        _account("acc-sueldo-usd", "Sueldo Soles", "USD"),
        _account("acc-sueldo-pen", " sueldo soles ", "PEN"),
    ]
    (pen, usd, *_rest) = names_table(DRY, renames, accounts)
    assert (pen.goes, pen.target_id, pen.renamed_to) == (
        Goes.YOURS,
        "acc-sueldo-pen",
        "Sueldo Soles",
    )
    assert (usd.goes, usd.target_id, usd.renamed_to) == (Goes.NEW, None, None)


def test_a_renamed_account_you_lack_in_its_currency_goes_to_a_new_one_under_the_rename():
    renames = {rename_key("BCP Oro", "USD"): "Dolares"}
    accounts = [_account("acc-dolares-pen", "Dolares", "PEN")]
    usd = names_table(DRY, renames, accounts)[1]
    assert (usd.goes, usd.target_id, usd.renamed_to, usd.ledger_name) == (
        Goes.NEW,
        None,
        "Dolares",
        "Dolares",
    )


def test_a_saved_rename_reads_as_a_flag_does():
    """`sheet_account_names` keys are `SHEET:CUR`, the currency after the last
    colon, so a sheet name may hold one."""
    assert saved_renames(
        {"BCP:PEN": "Sueldo Soles", "A:B:usd": " X ", "No colon": "Y", "C:": "Z"}
    ) == {
        ("bcp", "PEN"): "Sueldo Soles",
        ("a:b", "USD"): "X",
    }
    table = names_table(DRY, saved_renames({"BCP Oro:PEN": "Sueldo Soles"}), [])
    assert (table[0].goes, table[0].renamed_to) == (Goes.NEW, "Sueldo Soles")


def test_the_table_sent_gives_every_name_its_id():
    table = names_table(DRY, {}, [])
    ids = {
        (ACCOUNT, "bcp oro", "USD"): "new-usd",
        (CATEGORY, "travel", None): "new-travel",
        (HASHTAG, "trip", None): "new-trip",
    }
    assert table_body(table, ids) == {
        "accounts": [
            {"name": "BCP Oro", "account_id": "acc-oro-pen", "currency_code": "PEN"},
            {"name": "BCP Oro", "account_id": "new-usd", "currency_code": "USD"},
        ],
        "categories": [
            {"name": "food", "category_id": "cat-food"},
            {"name": "travel", "category_id": "new-travel"},
        ],
        "hashtags": [{"name": "trip", "hashtag_id": "new-trip"}],
    }


# ---- the run -----------------------------------------------------------------------
@respx.mock
def test_a_dry_run_is_one_call_without_the_table_and_creates_nothing(configured):
    route = _engine()
    creates = _creates()
    accounts = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    result = import_sheet(_cfg(), DATA, apply=False, renames={})
    assert route.call_count == 1
    assert _body(route.calls[0].request) == {"dry_run": True, "file": file_field(DATA)}
    assert all(r.call_count == 0 for r in creates.values())
    assert accounts.call_count == 0  # no rename: your accounts are not read
    assert (result.answer, result.error, result.stage, result.created) == (DRY, None, None, [])
    assert _goes(result.table) == _goes(names_table(DRY, {}, []))


@respx.mock
def test_a_rename_reads_your_accounts_people_and_archived_included(configured):
    _engine()
    accounts = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(
            200, json={"items": [_account("acc-sueldo", "Sueldo Soles", "PEN")]}
        )
    )
    renames = {rename_key("BCP Oro", "PEN"): "Sueldo Soles"}
    result = import_sheet(_cfg(), DATA, apply=False, renames=renames)
    assert accounts.call_count == 1
    params = accounts.calls[0].request.url.params
    assert (params["include_archived"], params["include_people"]) == ("true", "true")
    assert (result.table[0].goes, result.table[0].target_id) == (Goes.YOURS, "acc-sueldo")


@respx.mock
def test_the_apply_runs_the_dry_run_then_the_creates_then_the_table(configured):
    """A dry run without `names`, then one create per new name through its own
    route (the account under the sheet's name and currency exactly), then the
    apply with every name mapped; each write under its own idempotency key."""
    route = _engine()
    creates = _creates()
    result = import_sheet(_cfg(), DATA, apply=True, renames={})

    writes = _writes()
    assert [w.url.path for w in writes] == [
        "/v1/transactions/import-sheet",
        "/v1/accounts",
        "/v1/categories",
        "/v1/hashtags",
        "/v1/transactions/import-sheet",
    ]
    keys = [w.headers["X-Idempotency-Key"] for w in writes]
    assert len(set(keys)) == len(keys) == 5
    assert "names" not in _body(writes[0])

    account = _body(creates["accounts"].calls[0].request)
    assert set(account) == {"id", "name", "currency_code"}
    assert (account["name"], account["currency_code"]) == ("BCP Oro", "USD")
    category = _body(creates["categories"].calls[0].request)
    hashtag = _body(creates["hashtags"].calls[0].request)
    assert (set(category), category["name"]) == ({"id", "name"}, "travel")
    assert (set(hashtag), hashtag["name"]) == ({"id", "name"}, "trip")

    applied = _body(route.calls[1].request)
    assert applied["dry_run"] is False and applied["file"] == file_field(DATA)
    assert applied["names"] == {
        "accounts": [
            {"name": "BCP Oro", "account_id": "acc-oro-pen", "currency_code": "PEN"},
            {"name": "BCP Oro", "account_id": account["id"], "currency_code": "USD"},
        ],
        "categories": [
            {"name": "food", "category_id": "cat-food"},
            {"name": "travel", "category_id": category["id"]},
        ],
        "hashtags": [{"name": "trip", "hashtag_id": hashtag["id"]}],
    }
    assert result.created == [
        Created(ACCOUNT, "BCP Oro", "USD", account["id"]),
        Created(CATEGORY, "travel", None, category["id"]),
        Created(HASHTAG, "trip", None, hashtag["id"]),
    ]
    assert (result.error, result.stage) == (None, None)
    assert result.answer == _applied(applied["names"])
    assert result.counts == SheetCounts(5, 0, 0, 0, 0, 0)
    assert [(r.row, r.amount_cents, r.outcome) for r in result.rows][:1] == [(2, -1250, "new")]


@respx.mock
def test_a_renamed_account_you_lack_is_created_under_its_rename(configured):
    _engine()
    creates = _creates()
    respx.get(f"{BASE}/v1/accounts").mock(return_value=httpx.Response(200, json={"items": []}))
    renames = {rename_key("BCP Oro", "USD"): "Dolares"}
    result = import_sheet(_cfg(), DATA, apply=True, renames=renames)
    sent = _body(creates["accounts"].calls[0].request)
    assert (sent["name"], sent["currency_code"]) == ("Dolares", "USD")
    assert result.created[0] == Created(ACCOUNT, "Dolares", "USD", sent["id"])


@respx.mock
def test_names_the_engine_holds_as_one_are_created_once(configured):
    """`Travel` and `travel` are two names to the sheet but one category to the
    engine, which would refuse the second create as taken: one create, both
    mapped to it."""
    dry = sheet_import_answer(
        accounts=[sheet_name_use("BCP", 1, "acc-bcp", currency_code="PEN")],
        categories=[sheet_name_use("Travel"), sheet_name_use("travel")],
        hashtags=[sheet_name_use("trip", 1, "tag-trip")],
    )
    route = _engine(dry, apply=httpx.Response(200, json=sheet_import_answer(dry_run=False)))
    creates = _creates()
    result = import_sheet(_cfg(), DATA, apply=True, renames={})
    assert creates["categories"].call_count == 1
    (made,) = result.created
    assert _body(route.calls[1].request)["names"]["categories"] == [
        {"name": "Travel", "category_id": made.id},
        {"name": "travel", "category_id": made.id},
    ]


@pytest.mark.parametrize(
    "refusal", [LAYOUT, ROWS_REFUSED], ids=["file-refused-whole", "rows-refused"]
)
@respx.mock
def test_a_refused_sheet_creates_nothing(configured, refusal):
    """The dry run's refusal stops the apply before any create, kept as the
    engine's envelope, untouched."""
    route = _engine(httpx.Response(422, json=refusal))
    creates = _creates()
    result = import_sheet(_cfg(), DATA, apply=True, renames={})
    assert route.call_count == 1
    assert all(r.call_count == 0 for r in creates.values())
    assert isinstance(result.error, EngineError)
    assert result.error.raw_body == refusal
    assert (result.stage, result.created, result.answer, result.table) == (
        Stage.DRY_RUN,
        [],
        None,
        [],
    )


@pytest.mark.parametrize(
    "refusal", [NOT_MAPPED, INVALID_REFERENCE], ids=["name-not-mapped", "invalid-reference"]
)
@respx.mock
def test_a_table_refused_after_the_creates_reports_what_was_created(configured, refusal):
    _engine(apply=httpx.Response(422, json=refusal))
    _creates()
    result = import_sheet(_cfg(), DATA, apply=True, renames={})
    assert isinstance(result.error, EngineError)
    assert result.error.raw_body == refusal
    assert result.stage is Stage.APPLY
    assert [(c.kind, c.name, c.currency) for c in result.created] == [
        (ACCOUNT, "BCP Oro", "USD"),
        (CATEGORY, "travel", None),
        (HASHTAG, "trip", None),
    ]
    assert result.answer == DRY  # the dry run's, the last the engine answered


@respx.mock
def test_a_create_refused_stops_the_run_with_the_names_created_before_it(configured):
    route = _engine()
    creates = _creates()
    creates["categories"].mock(return_value=httpx.Response(409, json=NAME_EXISTS))
    result = import_sheet(_cfg(), DATA, apply=True, renames={})
    assert isinstance(result.error, EngineError)
    assert result.error.raw_body == NAME_EXISTS
    assert result.stage is Stage.CREATE
    assert [(c.kind, c.name) for c in result.created] == [(ACCOUNT, "BCP Oro")]
    assert creates["hashtags"].call_count == 0
    assert route.call_count == 1  # no apply sent


@respx.mock
def test_the_engine_out_of_reach_after_a_create_still_reports_it(configured):
    _engine(apply=httpx.ConnectError("connection refused"))
    _creates()
    result = import_sheet(_cfg(), DATA, apply=True, renames={})
    assert isinstance(result.error, EngineConnectionError)
    assert result.stage is Stage.APPLY
    assert len(result.created) == 3


@respx.mock
def test_a_failed_apply_is_retried_by_the_client_under_its_one_key(configured):
    """The module sends each write once; the HTTP client's bounded retry re-sends
    the apply under the same idempotency key, so a retry never double-applies."""
    answers = iter([httpx.Response(503, json=error_body("INTERNAL_ERROR", "Busy."))])

    def apply(request: httpx.Request) -> httpx.Response:
        body = _body(request)
        if "names" not in body:
            return httpx.Response(200, json=DRY)
        return next(answers, None) or httpx.Response(200, json=_applied(body["names"]))

    route = respx.post(IMPORT).mock(side_effect=apply)
    _creates()
    result = import_sheet(_cfg(), DATA, apply=True, renames={})
    assert result.error is None
    applies = [c.request for c in route.calls if "names" in _body(c.request)]
    assert len(applies) == 2
    assert applies[0].headers["X-Idempotency-Key"] == applies[1].headers["X-Idempotency-Key"]
