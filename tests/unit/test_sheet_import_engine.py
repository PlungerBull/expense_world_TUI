"""The sheet import through the engine: what is sent, the names table, the
renames, and each step's calls (contract: POST /v1/transactions/import-sheet).

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
    RenameRefused,
    SheetCounts,
    Stage,
    Step,
    check_renames,
    import_sheet,
    merge_renames,
    missing_names,
    names_table,
    parse_account_name,
    rename_key,
    request_body,
    saved_renames,
    table_body,
)
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import (
    account_with_currencies,
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
        "rows.5.date": "Row 5: Must not be in the future.",
    },
    {
        "rows.4.amount_cents": "UNEXPECTED_LAYOUT",
        "rows.6.amount_cents": "NOT_WHOLE_CENTS",
        "rows.5.date": "FUTURE_DATE",
    },
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


#: A sheet using one account name in two currencies, which you lack; a category you have
#: and one you do not; a hashtag you do not.
DRY = sheet_import_answer(
    accounts=[sheet_name_use("BCP Oro", 5, None, currencies=["PEN", "USD"])],
    categories=[sheet_name_use("food", 4, "cat-food"), sheet_name_use("travel", 1)],
    hashtags=[sheet_name_use("trip", 5)],
    rows=[sheet_row(r) for r in range(2, 7)],
)

#: The same sheet once every name is yours.
ALL_YOURS = sheet_import_answer(
    accounts=[sheet_name_use("BCP Oro", 5, "acc-oro", currencies=["PEN", "USD"])],
    categories=[sheet_name_use("food", 4, "cat-food"), sheet_name_use("travel", 1, "cat-trv")],
    hashtags=[sheet_name_use("trip", 5, "tag-trip")],
    rows=[sheet_row(r) for r in range(2, 7)],
)


def _answered(body: dict) -> dict:
    """The answer to a body with the table: each row on the table's first
    account, new, as a dry run or an apply."""
    account_id = body["names"]["accounts"][0]["account_id"]
    applied = body["dry_run"] is False
    rows = [
        sheet_row(
            r,
            account_id=account_id,
            outcome="new",
            is_opening_balance=False,
            transaction_id=f"t-{r}" if applied else None,
            bank_line_id=f"bl-{r}" if applied else None,
        )
        for r in range(2, 7)
    ]
    return sheet_import_answer(
        accounts=ALL_YOURS["names"]["accounts"],
        categories=ALL_YOURS["names"]["categories"],
        hashtags=ALL_YOURS["names"]["hashtags"],
        rows=rows,
        dry_run=body["dry_run"],
    )


def _engine(dry: dict | httpx.Response = DRY, tabled: object = None):
    """Route the import: a body without `names` answers `dry`, one with them
    answers `tabled` (by default `_answered`), a response, or raises it."""

    def answer(request: httpx.Request) -> httpx.Response:
        body = _body(request)
        if "names" not in body:
            return dry if isinstance(dry, httpx.Response) else httpx.Response(200, json=dry)
        if tabled is None:
            return httpx.Response(200, json=_answered(body))
        if isinstance(tabled, Exception):
            raise tabled
        return tabled  # type: ignore[return-value]

    return respx.post(IMPORT).mock(side_effect=answer)


def _made(request: httpx.Request) -> httpx.Response:
    """A create's answer: the resource under the sent id and name."""
    return httpx.Response(201, json={**_body(request), "is_archived": False})


def _creates() -> dict[str, respx.Route]:
    return {
        path: respx.post(f"{BASE}/v1/{path}").mock(side_effect=_made)
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


def test_nothing_in_the_app_reads_a_cell_of_a_workbook():
    """No spreadsheet library anywhere in the app: the sheet goes to the engine
    as bytes, through the bank import's one encoder."""
    for path in sorted(PACKAGE.rglob("*.py")):
        imported = _imports(path)
        assert not any(n == "openpyxl" or n.startswith("openpyxl.") for n in imported), path
    assert sorted(p.name for p in (PACKAGE / "import_").glob("*.py")) == [
        "__init__.py",
        "engine.py",
    ]
    assert "expense.bank_import.engine" in _imports(PACKAGE / "import_" / "engine.py")
    assert engine.file_field is file_field
    assert "b64encode" not in (PACKAGE / "import_" / "engine.py").read_text()


def test_openpyxl_is_a_test_dependency_only():
    """The tests build made-up sheets with it; the app never imports it."""
    import tomllib

    project = tomllib.loads((PACKAGE.parent / "pyproject.toml").read_text())["project"]
    assert not any(dep.startswith("openpyxl") for dep in project["dependencies"])
    assert any(dep.startswith("openpyxl") for dep in project["optional-dependencies"]["dev"])


# ---- renames -----------------------------------------------------------------------
def test_an_account_name_flag_reads_sheet_name_and_ledger_name():
    """The ledger name is everything after the first `=`; the sheet's name may
    hold a colon."""
    assert parse_account_name(" BCP = Sueldo Soles ") == ("BCP", "Sueldo Soles")
    assert parse_account_name("A:B=X=Y") == ("A:B", "X=Y")


@pytest.mark.parametrize("value", ["BCP", "BCP:PEN", "=X", "BCP= ", " =X"])
def test_a_malformed_account_name_is_refused_in_words(value):
    with pytest.raises(RenameRefused, match="is not SHEET_NAME=LEDGER_NAME"):
        parse_account_name(value)


def test_a_saved_rename_is_keyed_by_the_sheets_name():
    """`sheet_account_names` keys are sheet names, trimmed and case-insensitive;
    an older `NAME:CUR` key is just a name no sheet uses, so it renames nothing."""
    assert saved_renames({"BCP": "Sueldo Soles", " A:B ": " X ", "Empty": " ", " ": "Z"}) == {
        rename_key("bcp"): "Sueldo Soles",
        "a:b": "X",
    }
    table = names_table(DRY, saved_renames({"BCP Oro:PEN": "Old"}), [])
    assert table[0].renamed_to is None


def test_a_flag_replaces_the_saved_rename_of_its_account_in_any_letter_case():
    merged, renames = merge_renames(
        {"Bcp": "Old", "Interbank": "Dolares"}, [("BCP", "Sueldo Soles")]
    )
    assert merged == {"Interbank": "Dolares", "BCP": "Sueldo Soles"}
    assert renames == {rename_key("Interbank"): "Dolares", rename_key("BCP"): "Sueldo Soles"}


# ---- the names table ---------------------------------------------------------------
def _goes(table: list[NameEntry]) -> list[tuple]:
    return [(e.kind, e.name, e.currencies, e.goes, e.target_id, e.ledger_name) for e in table]


def test_each_name_goes_to_its_proposal_else_it_is_missing_under_the_sheets_name():
    """An account used in two currencies is one name, one entry holding both
    currencies in the engine's order, missing under the sheet's name."""
    table = names_table(DRY, {}, [])
    assert _goes(table) == [
        (ACCOUNT, "BCP Oro", ("PEN", "USD"), Goes.MISSING, None, "BCP Oro"),
        (CATEGORY, "food", (), Goes.YOURS, "cat-food", "food"),
        (CATEGORY, "travel", (), Goes.MISSING, None, "travel"),
        (HASHTAG, "trip", (), Goes.MISSING, None, "trip"),
    ]
    assert [e.rows for e in table] == [5, 4, 1, 5]
    assert all(e.renamed_to is None for e in table)
    assert [g.value for g in Goes] == ["yours", "missing"]


def test_a_renamed_account_goes_to_yours_of_that_name_over_the_proposal():
    """The rename wins over the proposal; your account is found by its name,
    trimmed and in any letter case."""
    renames = {rename_key(" bcp oro "): "Sueldo Soles"}
    accounts = [
        account_with_currencies(id="acc-other", name="Other"),
        account_with_currencies(id="acc-sueldo", name=" sueldo soles "),
    ]
    account = names_table(ALL_YOURS, renames, accounts)[0]
    assert (account.goes, account.target_id, account.renamed_to) == (
        Goes.YOURS,
        "acc-sueldo",
        "Sueldo Soles",
    )


def test_a_renamed_account_you_lack_is_missing_under_the_rename():
    renames = {rename_key("BCP Oro"): "Dolares"}
    accounts = [account_with_currencies(id="acc-other", name="Other")]
    account = names_table(ALL_YOURS, renames, accounts)[0]
    assert (account.goes, account.target_id, account.renamed_to, account.ledger_name) == (
        Goes.MISSING,
        None,
        "Dolares",
        "Dolares",
    )


def test_missing_names_are_one_per_name_the_engine_holds_as_one():
    """`Travel` and `travel` are two names to the sheet but one category to the
    engine, which would refuse the second create as taken; two account names it
    holds as one are created once, holding the currencies of both."""
    answer = sheet_import_answer(
        accounts=[
            sheet_name_use("BCP", 1, currencies=["PEN"]),
            sheet_name_use("bcp", 1, currencies=["USD", "PEN"]),
        ],
        categories=[sheet_name_use("Travel"), sheet_name_use("travel"), sheet_name_use("Food")],
        hashtags=[sheet_name_use("trip", 1, "tag-trip")],
    )
    missing = missing_names(names_table(answer, {}, []))
    assert [(e.kind, e.name, e.currencies) for e in missing] == [
        (ACCOUNT, "BCP", ("PEN", "USD")),
        (CATEGORY, "Travel", ()),
        (CATEGORY, "Food", ()),
    ]


def test_the_table_sent_gives_every_name_its_id_and_an_account_no_currency():
    """One `{name, account_id}` per account name, however many currencies it holds."""
    assert table_body(names_table(ALL_YOURS, {}, [])) == {
        "accounts": [{"name": "BCP Oro", "account_id": "acc-oro"}],
        "categories": [
            {"name": "food", "category_id": "cat-food"},
            {"name": "travel", "category_id": "cat-trv"},
        ],
        "hashtags": [{"name": "trip", "hashtag_id": "tag-trip"}],
    }
    with pytest.raises(ValueError, match="BCP Oro"):
        table_body(names_table(DRY, {}, []))


# ---- checking the renames against the sheet ----------------------------------------
TWO_ACCOUNTS = sheet_import_answer(
    accounts=[
        sheet_name_use("BCP", 2, currencies=["PEN"]),
        sheet_name_use("Interbank", 1, "acc-ib", currencies=["PEN"]),
        sheet_name_use("bcp", 1, currencies=["PEN"]),
    ]
)


def test_a_flag_for_an_account_the_sheet_lacks_is_refused():
    table = names_table(TWO_ACCOUNTS, {}, [])
    with pytest.raises(RenameRefused, match='the sheet has no account "Nope".'):
        check_renames(table, [("Nope", "Dolares")])
    check_renames(table, [(" interbank ", "Sueldo")])  # trimmed, any letter case


def test_a_rename_putting_two_sheet_accounts_on_one_is_refused():
    renames = {rename_key("BCP"): "interbank"}
    table = names_table(TWO_ACCOUNTS, renames, [])
    with pytest.raises(RenameRefused) as refused:
        check_renames(table, [("BCP", "interbank")])
    assert str(refused.value) == '"BCP" and "Interbank" would both be written as "Interbank".'


def test_names_one_rename_covers_are_one_account_not_two():
    """`BCP` and `bcp` are one account to the rename: no clash."""
    renames = {rename_key("BCP"): "Sueldo Soles"}
    table = names_table(TWO_ACCOUNTS, renames, [])
    check_renames(table, [("BCP", "Sueldo Soles")])
    assert missing_names(table)[0].ledger_name == "Sueldo Soles"
    assert len([e for e in missing_names(table) if e.kind == ACCOUNT]) == 1


# ---- the run -----------------------------------------------------------------------
@respx.mock
def test_a_dry_run_with_a_name_missing_is_one_call_without_the_table(configured):
    route = _engine()
    creates = _creates()
    accounts = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    result = import_sheet(_cfg(), DATA, step=Step.DRY_RUN, renames={})
    assert route.call_count == 1
    assert _body(route.calls[0].request) == {"dry_run": True, "file": file_field(DATA)}
    assert all(r.call_count == 0 for r in creates.values())
    assert accounts.call_count == 0  # no rename: your accounts are not read
    assert (result.answer, result.counted, result.error, result.stage) == (DRY, False, None, None)
    assert [(e.kind, e.name) for e in result.missing] == [
        (ACCOUNT, "BCP Oro"),
        (CATEGORY, "travel"),
        (HASHTAG, "trip"),
    ]


@respx.mock
def test_a_dry_run_with_every_name_yours_asks_again_with_the_table_for_the_counts(configured):
    route = _engine(ALL_YOURS)
    _creates()
    result = import_sheet(_cfg(), DATA, step=Step.DRY_RUN, renames={})
    bodies = [_body(c.request) for c in route.calls]
    assert [(b["dry_run"], "names" in b) for b in bodies] == [(True, False), (True, True)]
    assert bodies[1]["names"] == table_body(result.table)
    assert result.counted and result.missing == []
    assert result.answer == _answered(bodies[1])
    assert result.counts == SheetCounts(5, 0, 0, 0, 0, 0, 0)
    assert [w.url.path for w in _writes()] == ["/v1/transactions/import-sheet"] * 2


@respx.mock
def test_a_rename_reads_your_accounts_people_and_archived_included(configured):
    _engine()
    accounts = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(
            200, json={"items": [account_with_currencies(id="acc-sueldo", name="Sueldo Soles")]}
        )
    )
    renames = {rename_key("BCP Oro"): "Sueldo Soles"}
    result = import_sheet(_cfg(), DATA, step=Step.DRY_RUN, renames=renames)
    assert accounts.call_count == 1
    params = accounts.calls[0].request.url.params
    assert (params["include_archived"], params["include_people"]) == ("true", "true")
    assert (result.table[0].goes, result.table[0].target_id) == (Goes.YOURS, "acc-sueldo")


@respx.mock
def test_a_rename_refused_stops_the_run_before_anything_else_is_sent(configured):
    route = _engine()
    creates = _creates()
    with pytest.raises(RenameRefused):
        import_sheet(_cfg(), DATA, step=Step.CREATE_NAMES, renames={}, flags=[("Nope", "X")])
    assert route.call_count == 1
    assert all(r.call_count == 0 for r in creates.values())


@respx.mock
def test_the_create_step_creates_each_missing_name_and_imports_nothing(configured):
    """A dry run without `names`, then one create per missing name through its
    own route (the account under the sheet's name holding both currencies), each
    under its own idempotency key; no import is sent."""
    route = _engine()
    creates = _creates()
    result = import_sheet(_cfg(), DATA, step=Step.CREATE_NAMES, renames={})

    writes = _writes()
    assert [w.url.path for w in writes] == [
        "/v1/transactions/import-sheet",
        "/v1/accounts",
        "/v1/categories",
        "/v1/hashtags",
    ]
    keys = [w.headers["X-Idempotency-Key"] for w in writes]
    assert len(set(keys)) == len(keys) == 4
    assert route.call_count == 1 and "names" not in _body(writes[0])

    account = _body(creates["accounts"].calls[0].request)
    assert account == {
        "id": account["id"],
        "name": "BCP Oro",
        "currencies": [{"currency_code": "PEN"}, {"currency_code": "USD"}],
    }
    category = _body(creates["categories"].calls[0].request)
    hashtag = _body(creates["hashtags"].calls[0].request)
    assert (set(category), category["name"]) == ({"id", "name"}, "travel")
    assert (set(hashtag), hashtag["name"]) == ({"id", "name"}, "trip")
    assert result.created == [
        Created(ACCOUNT, "BCP Oro", ("PEN", "USD"), account["id"]),
        Created(CATEGORY, "travel", (), category["id"]),
        Created(HASHTAG, "trip", (), hashtag["id"]),
    ]
    assert result.created[0].answer == {**account, "is_archived": False}
    assert (result.error, result.stage, result.counted, result.answer) == (None, None, False, DRY)


@respx.mock
def test_the_create_step_with_nothing_missing_creates_nothing(configured):
    route = _engine(ALL_YOURS)
    creates = _creates()
    result = import_sheet(_cfg(), DATA, step=Step.CREATE_NAMES, renames={})
    assert route.call_count == 1
    assert all(r.call_count == 0 for r in creates.values())
    assert result.created == [] and result.error is None


@respx.mock
def test_a_renamed_account_you_lack_is_created_under_its_rename(configured):
    _engine()
    creates = _creates()
    respx.get(f"{BASE}/v1/accounts").mock(return_value=httpx.Response(200, json={"items": []}))
    renames = {rename_key("BCP Oro"): "Dolares"}
    result = import_sheet(_cfg(), DATA, step=Step.CREATE_NAMES, renames=renames)
    sent = _body(creates["accounts"].calls[0].request)
    assert (sent["name"], sent["currencies"]) == (
        "Dolares",
        [{"currency_code": "PEN"}, {"currency_code": "USD"}],
    )
    assert result.created[0] == Created(ACCOUNT, "Dolares", ("PEN", "USD"), sent["id"])


@respx.mock
def test_the_apply_with_a_name_missing_sends_nothing_more(configured):
    route = _engine()
    creates = _creates()
    result = import_sheet(_cfg(), DATA, step=Step.APPLY, renames={})
    assert route.call_count == 1
    assert all(r.call_count == 0 for r in creates.values())
    assert (result.counted, result.error, result.stage, result.answer) == (False, None, None, DRY)
    assert len(result.missing) == 3


@respx.mock
def test_the_apply_with_every_name_yours_sends_the_table(configured):
    route = _engine(ALL_YOURS)
    creates = _creates()
    result = import_sheet(_cfg(), DATA, step=Step.APPLY, renames={})
    bodies = [_body(c.request) for c in route.calls]
    assert [(b["dry_run"], "names" in b) for b in bodies] == [(True, False), (False, True)]
    assert bodies[1]["file"] == file_field(DATA)
    assert all(r.call_count == 0 for r in creates.values())
    assert result.counted and result.answer == _answered(bodies[1])
    assert [(r.row, r.amount_cents, r.outcome, r.transaction_id) for r in result.rows][:1] == [
        (2, -1250, "new", "t-2")
    ]


@pytest.mark.parametrize("step", list(Step), ids=lambda s: s.value)
@pytest.mark.parametrize(
    "refusal", [LAYOUT, ROWS_REFUSED], ids=["file-refused-whole", "rows-refused"]
)
@respx.mock
def test_a_refused_sheet_creates_nothing_on_any_step(configured, refusal, step):
    """The first dry run's refusal stops every step before anything else,
    kept as the engine's envelope, untouched."""
    route = _engine(httpx.Response(422, json=refusal))
    creates = _creates()
    result = import_sheet(_cfg(), DATA, step=step, renames={})
    assert route.call_count == 1
    assert all(r.call_count == 0 for r in creates.values())
    assert isinstance(result.error, EngineError)
    assert result.error.raw_body == refusal
    assert (result.stage, result.created, result.answer, result.table) == (
        Stage.NAMES,
        [],
        None,
        [],
    )


@pytest.mark.parametrize(
    ("step", "stage"), [(Step.DRY_RUN, Stage.COUNTS), (Step.APPLY, Stage.APPLY)]
)
@respx.mock
def test_a_table_refused_is_kept_with_its_stage(configured, step, stage):
    """An archived account the engine proposed is refused in the table."""
    _engine(ALL_YOURS, tabled=httpx.Response(422, json=INVALID_REFERENCE))
    result = import_sheet(_cfg(), DATA, step=step, renames={})
    assert isinstance(result.error, EngineError)
    assert result.error.raw_body == INVALID_REFERENCE
    assert (result.stage, result.counted, result.answer) == (stage, False, ALL_YOURS)


@respx.mock
def test_a_create_refused_stops_the_run_with_the_names_created_before_it(configured):
    _engine()
    creates = _creates()
    creates["categories"].mock(return_value=httpx.Response(409, json=NAME_EXISTS))
    result = import_sheet(_cfg(), DATA, step=Step.CREATE_NAMES, renames={})
    assert isinstance(result.error, EngineError)
    assert result.error.raw_body == NAME_EXISTS
    assert result.stage is Stage.CREATE
    assert [(c.kind, c.name) for c in result.created] == [(ACCOUNT, "BCP Oro")]
    assert creates["hashtags"].call_count == 0


@respx.mock
def test_the_engine_out_of_reach_after_a_create_still_reports_it(configured):
    _engine()
    creates = _creates()
    creates["hashtags"].mock(side_effect=httpx.ConnectError("connection refused"))
    result = import_sheet(_cfg(), DATA, step=Step.CREATE_NAMES, renames={})
    assert isinstance(result.error, EngineConnectionError)
    assert result.stage is Stage.CREATE
    assert len(result.created) == 2


@respx.mock
def test_a_failed_apply_is_retried_by_the_client_under_its_one_key(configured):
    """The module sends each write once; the HTTP client's bounded retry re-sends
    the apply under the same idempotency key, so a retry never double-applies."""
    answers = iter([httpx.Response(503, json=error_body("INTERNAL_ERROR", "Busy."))])

    def apply(request: httpx.Request) -> httpx.Response:
        body = _body(request)
        if "names" not in body:
            return httpx.Response(200, json=ALL_YOURS)
        return next(answers, None) or httpx.Response(200, json=_answered(body))

    route = respx.post(IMPORT).mock(side_effect=apply)
    result = import_sheet(_cfg(), DATA, step=Step.APPLY, renames={})
    assert result.error is None
    applies = [c.request for c in route.calls if "names" in _body(c.request)]
    assert len(applies) == 2
    assert applies[0].headers["X-Idempotency-Key"] == applies[1].headers["X-Idempotency-Key"]
