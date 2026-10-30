"""`expense import sheet`: what the terminal prints, screen by screen, as
docs/mockups/expense-world-sheet-import-engine.html draws it (screens 1 to 5,
pick 1 A `--create-names`, pick 2 A the apply refused while a name is missing).

The engine is respx: every answer is the fake engine's `sheet_import_answer`
(tests/unit/helpers.py), every refusal an envelope shaped as the practice
engine sends it. The sheet's bytes never matter to the app, so the file is any
bytes on disk.
"""

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from expense import config as config_module
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import (
    account_with_currencies,
    error_body,
    real_cli_app,
    sheet_import_answer,
    sheet_name_use,
    sheet_row,
    strip_panel,
)

runner = CliRunner()
cli_app = real_cli_app()
IMPORT = f"{BASE}/v1/transactions/import-sheet"
FILE = "libro.xlsx"
#: The three commands: the dry run, the create step, the apply.
STEPS = [[], ["--create-names"], ["--apply"]]
STEP_IDS = ["dry", "create", "apply"]


@pytest.fixture
def sheet(configured, tmp_path, monkeypatch):
    """A file named as the mockup names it, in the working folder."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / FILE).write_bytes(b"PK\x03\x04 a made-up workbook")


def _run(*args: str, file: str = FILE):
    return runner.invoke(cli_app, ["import", "sheet", file, *args])


def _out(result) -> str:
    return result.stdout + result.stderr


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


# ---- the mockup's made-up sheet ----------------------------------------------------
def _names(*, yours: bool) -> dict:
    """Screen 1's names (`yours` False, `BCP` renamed to `Sueldo Soles`), or
    screen 3's, every one proposed."""

    def p(ident: str) -> str | None:
        return ident if yours else None

    return {
        "accounts": [
            sheet_name_use("BCP", 1515, p("acc-bcp"), currencies=["PEN", "USD"]),
            sheet_name_use("Interbank", 402, p("acc-ib"), currencies=["PEN"]),
            sheet_name_use("Visa", 261, p("acc-visa"), currencies=["PEN", "USD"]),
            sheet_name_use("Ana", 44, p("acc-ana"), currencies=["PEN", "USD"]),
        ],
        "categories": [
            sheet_name_use("Comida", 1010, p("cat-comida")),
            sheet_name_use("Transporte", 435, p("cat-transporte")),
            sheet_name_use("Casa", 512, "cat-casa"),
            sheet_name_use("SALDO INICIAL", 4, p("cat-saldo")),
        ],
        "hashtags": [
            sheet_name_use("Personal", 1722, p("tag-personal")),
            sheet_name_use("Trabajo", 239, p("tag-trabajo")),
        ],
    }


def _answer(*, yours: bool, dry_run: bool = True, rows=None, counts=None) -> dict:
    return sheet_import_answer(
        **_names(yours=yours),
        rows=rows if rows is not None else [sheet_row(2)],
        dry_run=dry_run,
        counts=counts,
    )


#: Screen 3's counts: 1,961 rows, 7 of them zero.
SKIPPED = [14, 90, 311, 1201, 1202, 1555, 1960]
COUNTS = {
    "new": 1954,
    "matched": 0,
    "sealed": 0,
    "skipped": 7,
    "opening_balances": 4,
    "split_lines": 3,
    "split_rows": 8,
}


def _counted_rows(outcome: str = "new", *, sealed: tuple[int, ...] = ()) -> list[dict]:
    rows = []
    for r in range(2, 1963):
        if r in SKIPPED:
            rows.append(sheet_row(r, 0, outcome="skipped", account_id="acc-ib"))
        elif r in sealed:
            rows.append(sheet_row(r, outcome="sealed", account_id="acc-ib"))
        else:
            rows.append(sheet_row(r, outcome=outcome, account_id="acc-ib"))
    return rows


#: The renamed account as `GET /accounts` lists it once it exists.
SUELDO = account_with_currencies(id="acc-sueldo", name="Sueldo Soles")


def _engine(first: dict | httpx.Response, tabled: dict | httpx.Response | None = None):
    """The import route: a body without `names` answers `first`, one with them
    `tabled`."""

    def answer(request: httpx.Request) -> httpx.Response:
        reply = tabled if "names" in _body(request) else first
        assert reply is not None, "the table was sent"
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)

    return respx.post(IMPORT).mock(side_effect=answer)


def _accounts(items: list[dict]) -> respx.Route:
    return respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(200, json={"items": items})
    )


def _made(request: httpx.Request) -> httpx.Response:
    return httpx.Response(201, json={**_body(request), "is_archived": False})


def _creates() -> dict[str, respx.Route]:
    return {
        path: respx.post(f"{BASE}/v1/{path}").mock(side_effect=_made)
        for path in ("accounts", "categories", "hashtags")
    }


def _sent() -> list[tuple[str, bool | None, bool]]:
    """Every POST: its path, and for the import its `dry_run` and whether the
    table went with it."""
    out = []
    for call in respx.calls:
        if call.request.method != "POST":
            continue
        body = _body(call.request)
        out.append((call.request.url.path, body.get("dry_run"), "names" in body))
    return out


def _saved() -> dict[str, str]:
    return config_module.ensure_loaded().sheet_account_names


SCREEN_1 = """\
Accounts (4)
  SHEET NAME   CUR          ROWS   GOES TO
  BCP          PEN + USD   1,515   Sueldo Soles  missing
  Interbank    PEN           402   missing
  Visa         PEN + USD     261   missing
  Ana          PEN + USD      44   missing

Categories (4)
  SHEET NAME       ROWS   GOES TO
  Comida          1,010   missing
  Transporte        435   missing
  Casa              512   yours
  SALDO INICIAL       4   missing

Hashtags (2)
  SHEET NAME    ROWS   GOES TO
  Personal     1,722   missing
  Trabajo        239   missing

No counts yet: the engine counts once every name exists.

9 names don't exist yet. Create them with:
  expense import sheet libro.xlsx --create-names
Dry run — nothing written.
"""


# ---- screen 1: the first dry run ---------------------------------------------------
@respx.mock
def test_the_first_dry_run_lists_every_name_and_the_step_that_creates_the_missing(sheet):
    """Screen 1 with --account-name: the renamed account shows its new name,
    `SALDO INICIAL` is a name like any other, no counts, the create step's
    command line; only the dry run without the table is sent, and the rename
    is remembered."""
    route = _engine(_answer(yours=False))
    accounts = _accounts([])
    creates = _creates()
    result = _run("--account-name", "BCP=Sueldo Soles")
    assert result.exit_code == 0, _out(result)
    assert result.stdout == SCREEN_1
    assert _sent() == [("/v1/transactions/import-sheet", True, False)]
    assert route.call_count == 1 and accounts.call_count == 1
    assert all(r.call_count == 0 for r in creates.values())
    assert _saved() == {"BCP": "Sueldo Soles"}


@respx.mock
def test_the_create_steps_command_line_keeps_the_file_as_typed(sheet, tmp_path):
    """Without a rename the account keeps the sheet's name and your accounts
    are not read; a path with a space is quoted so it can be pasted."""
    (tmp_path / "mi libro.xlsx").write_bytes(b"made up")
    _engine(_answer(yours=False))
    accounts = _accounts([])
    result = _run(file="mi libro.xlsx")
    assert result.exit_code == 0, _out(result)
    assert "  BCP          PEN + USD   1,515   missing\n" in result.stdout
    assert "  expense import sheet 'mi libro.xlsx' --create-names\n" in result.stdout
    assert "9 names don't exist yet. Create them with:\n" in result.stdout
    assert accounts.call_count == 0


@respx.mock
def test_one_missing_name_reads_in_the_singular(sheet):
    answer = sheet_import_answer(
        accounts=[sheet_name_use("BCP", 2, "acc-bcp", currencies=["PEN"])],
        categories=[sheet_name_use("Comida", 2, "cat-comida")],
        hashtags=[sheet_name_use("Nuevo", 2)],
    )
    _engine(answer)
    result = _run()
    assert result.exit_code == 0, _out(result)
    assert result.stdout.endswith(
        "1 name doesn't exist yet. Create it with:\n"
        "  expense import sheet libro.xlsx --create-names\n"
        "Dry run — nothing written.\n"
    )


# ---- screen 2: creating the names --------------------------------------------------
@respx.mock
def test_the_create_step_creates_every_missing_name_and_imports_nothing(sheet):
    """Screen 2: the renamed account is created under its new name; the sheet
    goes only as a dry run without the table, first."""
    config_module.save(
        config_module.ensure_loaded().model_copy(
            update={"sheet_account_names": {"BCP": "Sueldo Soles"}}
        )
    )
    _engine(_answer(yours=False))
    _accounts([])
    creates = _creates()
    result = _run("--create-names")
    assert result.exit_code == 0, _out(result)
    assert result.stdout == (
        "Created 4 accounts, 3 categories, 2 hashtags.\n"
        "Nothing imported. Run the dry run again to see the counts.\n"
    )
    assert _sent()[0] == ("/v1/transactions/import-sheet", True, False)
    assert [path for path, *_ in _sent()[1:]] == ["/v1/accounts"] * 4 + ["/v1/categories"] * 3 + [
        "/v1/hashtags"
    ] * 2
    sent = [_body(c.request) for c in creates["accounts"].calls]
    both = [{"currency_code": "PEN"}, {"currency_code": "USD"}]
    made = [(a["name"], a["currencies"]) for a in sent]
    assert made == [
        ("Sueldo Soles", both),
        ("Interbank", [{"currency_code": "PEN"}]),
        ("Visa", both),
        ("Ana", both),
    ]
    categories = [_body(c.request)["name"] for c in creates["categories"].calls]
    assert categories == ["Comida", "Transporte", "SALDO INICIAL"]


@respx.mock
def test_the_create_step_run_again_creates_nothing(sheet):
    _engine(_answer(yours=True))
    creates = _creates()
    result = _run("--create-names")
    assert result.exit_code == 0, _out(result)
    assert result.stdout == "Created no names: every one is yours.\n"
    assert all(r.call_count == 0 for r in creates.values())


@respx.mock
def test_one_name_of_one_kind_created_reads_in_the_singular(sheet):
    answer = sheet_import_answer(
        accounts=[sheet_name_use("BCP", 2, currencies=["PEN"])],
        categories=[sheet_name_use("Comida", 2, "cat-comida")],
        hashtags=[sheet_name_use("Casa", 2, "tag-casa")],
    )
    _engine(answer)
    _creates()
    result = _run("--create-names")
    assert result.stdout.splitlines()[0] == "Created 1 account."


@respx.mock
def test_the_create_step_with_the_apply_is_a_usage_error(sheet):
    result = _run("--create-names", "--apply")
    assert result.exit_code == 2, _out(result)
    words = strip_panel(_out(result))
    assert "Invalid value" not in words
    assert (
        "Error --create-names creates names and imports nothing, so it never goes with --apply."
        in words
    )
    assert not respx.calls


@respx.mock
def test_a_create_refused_part_way_says_what_was_created_then_the_engines_words(sheet):
    answer = sheet_import_answer(
        accounts=[sheet_name_use("BCP", 2, currencies=["PEN"])],
        categories=[sheet_name_use("@Opening", 2)],
        hashtags=[sheet_name_use("Casa", 2, "tag-casa")],
    )
    _engine(answer)
    creates = _creates()
    creates["categories"].mock(
        return_value=httpx.Response(
            422,
            json=error_body(
                "VALIDATION_ERROR",
                "Invalid input.",
                {"name": "This name is reserved."},
                {"name": "RESERVED_NAME"},
            ),
        )
    )
    result = _run("--create-names")
    assert result.exit_code == 1
    assert result.stdout == "Created 1 account.\n"
    assert result.stderr == (
        "Error: VALIDATION_ERROR — Invalid input.\n  name: This name is reserved.\n"
    )


# ---- screen 3: the dry run once every name exists ----------------------------------
SCREEN_3 = """\
Accounts (4)
  SHEET NAME   CUR          ROWS   GOES TO
  BCP          PEN + USD   1,515   Sueldo Soles  yours
  Interbank    PEN           402   yours
  Visa         PEN + USD     261   yours
  Ana          PEN + USD      44   yours

Categories (4)
  SHEET NAME       ROWS   GOES TO
  Comida          1,010   yours
  Transporte        435   yours
  Casa              512   yours
  SALDO INICIAL       4   yours

Hashtags (2)
  SHEET NAME    ROWS   GOES TO
  Personal     1,722   yours
  Trabajo        239   yours

Rows: 1,961 · new 1,954 · matched 0 · sealed 0 · skipped 7
Opening balances 4 · split transactions 3 (8 rows)

Skipped, amount zero: rows 14, 90, 311, 1201, 1202, 1555, 1960

Dry run — nothing written. Run again with --apply to import.
"""


@respx.mock
def test_the_dry_run_once_every_name_exists_shows_the_engines_counts(sheet):
    """Screen 3: the remembered rename finds your account; the dry run goes
    again with the table, still a dry run, and nothing is created."""
    config_module.save(
        config_module.ensure_loaded().model_copy(
            update={"sheet_account_names": {"BCP": "Sueldo Soles"}}
        )
    )
    route = _engine(_answer(yours=True), _answer(yours=True, rows=_counted_rows(), counts=COUNTS))
    _accounts([SUELDO])
    creates = _creates()
    result = _run()
    assert result.exit_code == 0, _out(result)
    assert result.stdout == SCREEN_3
    assert _sent() == [("/v1/transactions/import-sheet", True, False)] + [
        ("/v1/transactions/import-sheet", True, True)
    ]
    sent = _body(route.calls[1].request)["names"]["accounts"]
    assert sent == [
        {"name": "BCP", "account_id": "acc-sueldo"},
        {"name": "Interbank", "account_id": "acc-ib"},
        {"name": "Visa", "account_id": "acc-visa"},
        {"name": "Ana", "account_id": "acc-ana"},
    ]
    assert all(r.call_count == 0 for r in creates.values())


@respx.mock
def test_rows_on_a_closed_statements_day_are_listed_under_the_zero_rows(sheet):
    counts = {**COUNTS, "new": 1952, "sealed": 2}
    rows = _counted_rows(sealed=(40, 41))
    _engine(_answer(yours=True), _answer(yours=True, rows=rows, counts=counts))
    result = _run()
    assert result.exit_code == 0, _out(result)
    assert (
        "Opening balances 4 · split transactions 3 (8 rows)\n\n"
        "Skipped, amount zero: rows 14, 90, 311, 1201, 1202, 1555, 1960\n"
        "Sealed, on a closed statement's day: rows 40, 41\n\n"
        "Dry run — nothing written. Run again with --apply to import.\n"
    ) in result.stdout


@respx.mock
def test_a_dry_run_with_no_zero_or_closed_rows_lists_none(sheet):
    rows = [sheet_row(2, outcome="new", account_id="acc-ib")]
    _engine(_answer(yours=True), _answer(yours=True, rows=rows))
    result = _run()
    assert result.stdout.endswith(
        "Rows: 1 · new 1 · matched 0 · sealed 0 · skipped 0\n"
        "Opening balances 0 · split transactions 0 (0 rows)\n\n"
        "Dry run — nothing written. Run again with --apply to import.\n"
    )


@respx.mock
def test_a_table_the_engine_refuses_prints_as_every_engine_error(sheet):
    """An archived account the engine proposed is refused in the table."""
    refusal = error_body(
        "VALIDATION_ERROR",
        "Import validation failed.",
        {"names.accounts.0.account_id": "Must reference an active, non-archived account."},
        {"names.accounts.0.account_id": "INVALID_REFERENCE"},
    )
    _engine(_answer(yours=True), httpx.Response(422, json=refusal))
    result = _run()
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Error: VALIDATION_ERROR — Import validation failed.\n"
        "  names.accounts.0.account_id: Must reference an active, non-archived account.\n"
    )


@respx.mock
def test_a_currency_the_account_does_not_hold_prints_in_the_engines_words(sheet):
    """`CURRENCY_NOT_HELD` on the table entry (contract: POST /v1/transactions/import-sheet,
    "Names"): the account a name goes to lacks a currency its rows are in."""
    refusal = error_body(
        "VALIDATION_ERROR",
        "Import validation failed.",
        {"names.accounts.0.account_id": "The account holds no USD."},
        {"names.accounts.0.account_id": "CURRENCY_NOT_HELD"},
    )
    _engine(_answer(yours=True), httpx.Response(422, json=refusal))
    result = _run()
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Error: VALIDATION_ERROR — Import validation failed.\n"
        "  names.accounts.0.account_id: The account holds no USD.\n"
    )


# ---- pick 2 A: the apply while a name is missing -----------------------------------
@respx.mock
def test_the_apply_while_a_name_is_missing_is_refused_and_names_the_step(sheet):
    _engine(_answer(yours=False))
    creates = _creates()
    result = _run("--apply")
    assert result.exit_code == 1
    assert result.stdout == (
        "Not imported — nothing written.\n"
        "9 names don't exist yet. Create them with:\n"
        "  expense import sheet libro.xlsx --create-names\n"
        "then run the dry run to see the counts.\n"
    )
    assert _sent() == [("/v1/transactions/import-sheet", True, False)]
    assert all(r.call_count == 0 for r in creates.values())


# ---- screen 4: the apply, then the same sheet again --------------------------------
@respx.mock
def test_the_apply_writes_and_says_what_was_written(sheet):
    _engine(
        _answer(yours=True),
        _answer(yours=True, dry_run=False, rows=_counted_rows(), counts=COUNTS),
    )
    result = _run("--apply")
    assert result.exit_code == 0, _out(result)
    assert result.stdout == (
        "Written: new 1,954 · matched 0 · sealed 0 · skipped 7\n"
        "Opening balances 4 · split transactions 3 (8 rows)\n\n"
        "Skipped, amount zero: rows 14, 90, 311, 1201, 1202, 1555, 1960\n"
    )
    assert _sent() == [
        ("/v1/transactions/import-sheet", True, False),
        ("/v1/transactions/import-sheet", False, True),
    ]


@respx.mock
def test_the_same_sheet_applied_again_matches_every_row_and_writes_nothing_new(sheet):
    counts = {**COUNTS, "new": 0, "matched": 1954}
    _engine(
        _answer(yours=True),
        _answer(yours=True, dry_run=False, rows=_counted_rows("matched"), counts=counts),
    )
    result = _run("--apply")
    assert result.exit_code == 0, _out(result)
    assert result.stdout == (
        "Written: new 0 · matched 1,954 · sealed 0 · skipped 7\n"
        "Opening balances 4 · split transactions 3 (8 rows)\n\n"
        "Nothing new: every row is already in the ledger.\n"
    )


@respx.mock
def test_a_sheet_of_zero_rows_only_applied_lists_them_and_never_says_nothing_new(sheet):
    rows = [sheet_row(r, 0, outcome="skipped", account_id="acc-ib") for r in (2, 3)]
    _engine(_answer(yours=True), _answer(yours=True, dry_run=False, rows=rows))
    result = _run("--apply")
    assert result.exit_code == 0, _out(result)
    assert result.stdout == (
        "Written: new 0 · matched 0 · sealed 0 · skipped 2\n"
        "Opening balances 0 · split transactions 0 (0 rows)\n\n"
        "Skipped, amount zero: rows 2, 3\n"
    )


# ---- screen 5: a sheet with bad rows -----------------------------------------------
ROWS_REFUSED = error_body(
    "VALIDATION_ERROR",
    "Import validation failed.",
    {
        "rows.77.date": "Row 77: FECHA is empty.",
        "rows.120.amount_cents": "Row 120: MONTO is not a whole number of cents.",
        "rows.1958.date": "Row 1958: The day is after today.",
        "rows.1959.date": "Row 1959: The day is after today.",
    },
    {
        "rows.77.date": "UNEXPECTED_LAYOUT",
        "rows.120.amount_cents": "NOT_WHOLE_CENTS",
        "rows.1958.date": "FUTURE_DATE",
        "rows.1959.date": "FUTURE_DATE",
    },
)

SCREEN_5 = """\
Refused — nothing written. 4 rows:
  Row 77: FECHA is empty.
  Row 120: MONTO is not a whole number of cents.
  The day is after today. rows 1958, 1959

Fix the sheet and run it again.
"""


@pytest.mark.parametrize("step", STEPS, ids=STEP_IDS)
@respx.mock
def test_a_bad_row_stops_every_step_and_lists_each_refusal_by_row(sheet, step):
    _engine(httpx.Response(422, json=ROWS_REFUSED))
    creates = _creates()
    result = _run(*step)
    assert result.exit_code == 1
    assert result.stdout == SCREEN_5
    assert _sent() == [("/v1/transactions/import-sheet", True, False)]
    assert all(r.call_count == 0 for r in creates.values())


@pytest.mark.parametrize("step", STEPS, ids=STEP_IDS)
@respx.mock
def test_a_file_refused_whole_prints_as_every_engine_error(sheet, step):
    refusal = error_body(
        "VALIDATION_ERROR",
        "The file is not the sheet's layout.",
        {"file": "Row 1 must be the twelve headers description … COD_EECC."},
        {"file": "UNEXPECTED_LAYOUT"},
    )
    _engine(httpx.Response(422, json=refusal))
    result = _run(*step)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Error: VALIDATION_ERROR — The file is not the sheet's layout.\n"
        "  file: Row 1 must be the twelve headers description … COD_EECC.\n"
    )


@respx.mock
def test_a_row_refusal_whose_words_do_not_name_its_row_keeps_its_field(sheet):
    """Two rows that would both be one account's opening balance."""
    refusal = error_body(
        "VALIDATION_ERROR",
        "Import validation failed.",
        {
            "rows.2.category": "Another row is this account's opening balance.",
            "rows.9.category": "Another row is this account's opening balance.",
        },
        dict.fromkeys(["rows.2.category", "rows.9.category"], "DUPLICATE_IN_REQUEST"),
    )
    _engine(_answer(yours=True), httpx.Response(422, json=refusal))
    result = _run("--apply")
    assert result.exit_code == 1
    assert result.stdout == (
        "Refused — nothing written. 2 rows:\n"
        "  category: Another row is this account's opening balance. rows 2, 9\n\n"
        "Fix the sheet and run it again.\n"
    )


#: Row refusals fixing the sheet does not clear, each as the contract keys it
#: (contract: POST /v1/transactions/import-sheet, "Concurrency")
#: (contract: POST /v1/transactions/import-sheet, "Opening balances")
#: (contract: POST /v1/transactions/import-sheet, "On apply").
NOT_THE_SHEETS = {
    "concurrent-change": (
        409,
        "CONFLICT",
        "rows.12",
        "Row 12: Its line changed while the import ran; send it again.",
        "CONCURRENT_CHANGE",
    ),
    "opening-balance-exists": (
        409,
        "CONFLICT",
        "rows.2.account_id",
        "The account already has an opening balance on another day.",
        "OPENING_BALANCE_EXISTS",
    ),
    "line-codes-exhausted": (
        422,
        "LIMIT_REACHED",
        "rows.5.transaction_id",
        "Every bank line code has been given.",
        "LINE_CODES_EXHAUSTED",
    ),
}


@pytest.mark.parametrize(
    ("status", "code", "key", "words", "reason"),
    list(NOT_THE_SHEETS.values()),
    ids=list(NOT_THE_SHEETS),
)
@respx.mock
def test_a_row_refusal_the_sheet_does_not_cause_prints_as_every_engine_error(
    sheet, status, code, key, words, reason
):
    refusal = error_body(code, "The import was refused.", {key: words}, {key: reason})
    _engine(_answer(yours=True), httpx.Response(status, json=refusal))
    result = _run("--apply")
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == f"Error: {code} — The import was refused.\n  {key}: {words}\n"
    assert "Fix the sheet" not in _out(result)


@respx.mock
def test_one_refused_row_reads_in_the_singular(sheet):
    refusal = error_body(
        "VALIDATION_ERROR",
        "Import validation failed.",
        {"rows.77.date": "Row 77: FECHA is empty."},
        {"rows.77.date": "UNEXPECTED_LAYOUT"},
    )
    _engine(httpx.Response(422, json=refusal))
    result = _run()
    assert result.stdout.splitlines()[:2] == [
        "Refused — nothing written. 1 row:",
        "  Row 77: FECHA is empty.",
    ]


@respx.mock
def test_the_engine_out_of_reach_exits_6(sheet):
    respx.post(IMPORT).mock(side_effect=httpx.ConnectError("connection refused"))
    result = _run()
    assert result.exit_code == 6
    assert "could not reach engine" in result.stderr


# ---- --json ------------------------------------------------------------------------
@respx.mock
def test_json_prints_the_engines_answer_on_the_dry_run(sheet):
    first = _answer(yours=False)
    _engine(first)
    result = _run("--json")
    assert result.exit_code == 0, _out(result)
    assert json.loads(result.stdout) == first


@respx.mock
def test_json_prints_the_counted_answer_once_every_name_exists(sheet):
    counted = _answer(yours=True, rows=_counted_rows(), counts=COUNTS)
    _engine(_answer(yours=True), counted)
    result = _run("--json")
    assert json.loads(result.stdout) == counted


@respx.mock
def test_json_prints_the_apply_answer(sheet):
    applied = _answer(yours=True, dry_run=False, rows=_counted_rows(), counts=COUNTS)
    _engine(_answer(yours=True), applied)
    result = _run("--apply", "--json")
    assert result.exit_code == 0, _out(result)
    assert json.loads(result.stdout) == applied


@respx.mock
def test_json_prints_the_engines_answer_to_each_name_created(sheet):
    _engine(_answer(yours=False))
    creates = _creates()
    result = _run("--create-names", "--json")
    assert result.exit_code == 0, _out(result)
    printed = json.loads(result.stdout)
    assert list(printed) == ["created"]
    answers = {
        kind: [json.loads(_made(c.request).content) for c in creates[kind].calls]
        for kind in ("accounts", "categories", "hashtags")
    }
    assert printed["created"] == answers
    assert [a["name"] for a in printed["created"]["accounts"]] == [
        "BCP",
        "Interbank",
        "Visa",
        "Ana",
    ]


@respx.mock
def test_json_on_a_create_refused_part_way_keeps_the_names_created_and_the_refusal(sheet):
    answer = sheet_import_answer(
        accounts=[sheet_name_use("BCP", 2, currencies=["PEN"])],
        categories=[sheet_name_use("@Opening", 2)],
        hashtags=[sheet_name_use("Casa", 2, "tag-casa")],
    )
    refusal = error_body(
        "VALIDATION_ERROR",
        "Invalid input.",
        {"name": "This name is reserved."},
        {"name": "RESERVED_NAME"},
    )
    _engine(answer)
    creates = _creates()
    creates["categories"].mock(return_value=httpx.Response(422, json=refusal))
    result = _run("--create-names", "--json")
    assert result.exit_code == 1
    account = json.loads(_made(creates["accounts"].calls[0].request).content)
    assert json.loads(result.stdout) == {
        "created": {"accounts": [account], "categories": [], "hashtags": []},
        **refusal,
    }
    assert result.stderr == ""


@respx.mock
def test_json_on_the_engine_out_of_reach_part_way_keeps_the_names_created(sheet):
    answer = sheet_import_answer(
        accounts=[sheet_name_use("BCP", 2, currencies=["PEN"])],
        categories=[sheet_name_use("Comida", 2)],
        hashtags=[sheet_name_use("Casa", 2, "tag-casa")],
    )
    _engine(answer)
    creates = _creates()
    creates["categories"].mock(side_effect=httpx.ConnectError("connection refused"))
    result = _run("--create-names", "--json")
    assert result.exit_code == 6
    printed = json.loads(result.stdout)
    assert [a["name"] for a in printed["created"]["accounts"]] == ["BCP"]
    assert printed["error"]["code"] == "CONNECTION_ERROR"


@respx.mock
def test_json_on_a_refused_sheet_is_the_engines_body(sheet):
    _engine(httpx.Response(422, json=ROWS_REFUSED))
    result = _run("--apply", "--json")
    assert result.exit_code == 1
    assert json.loads(result.stdout) == ROWS_REFUSED


@respx.mock
def test_json_on_the_apply_while_a_name_is_missing_is_an_error_envelope(sheet):
    _engine(_answer(yours=False))
    result = _run("--apply", "--json")
    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "NAMES_MISSING",
            "message": "Not imported — nothing written. 9 names don't exist yet.",
            "fields": None,
            "reasons": None,
        }
    }


# ---- --account-name ----------------------------------------------------------------
@respx.mock
def test_a_rename_is_remembered_by_name_and_a_flag_replaces_it(sheet):
    _engine(_answer(yours=False))
    _accounts([])
    assert _run("--account-name", "Bcp=Old").exit_code == 0
    assert _saved() == {"Bcp": "Old"}
    result = _run("--account-name", "BCP=Sueldo Soles")
    assert result.exit_code == 0, _out(result)
    assert _saved() == {"BCP": "Sueldo Soles"}
    result = _run()
    assert "  BCP          PEN + USD   1,515   Sueldo Soles  missing\n" in result.stdout


def _save_names(names):
    config_module.save(
        config_module.ensure_loaded().model_copy(update={"sheet_account_names": names})
    )


@respx.mock
def test_saved_renames_with_a_currency_going_to_one_ledger_name_are_one_rename(sheet):
    _save_names({"BCP:PEN": "Sueldo Soles", "BCP:USD": "Sueldo Soles"})
    _engine(_answer(yours=False))
    _accounts([])
    result = _run()
    assert result.exit_code == 0, _out(result)
    assert "  BCP          PEN + USD   1,515   Sueldo Soles  missing\n" in result.stdout


@pytest.mark.parametrize("step", STEPS, ids=STEP_IDS)
@respx.mock
def test_saved_renames_of_one_name_going_to_two_ledger_names_stop_the_run(sheet, step):
    _save_names({"BCP:PEN": "Sueldo Soles", "BCP:USD": "Sueldo Dólares"})
    _engine(_answer(yours=False))
    _accounts([])
    creates = _creates()
    before = config_module.config_path().read_text()
    result = _run(*step)
    assert result.exit_code == 2, _out(result)
    words = strip_panel(_out(result))
    assert "Invalid value" not in words
    assert (
        'Your saved renames send "BCP" to both "Sueldo Soles" and "Sueldo Dólares". '
        'Choose one with --account-name "BCP=<ledger name>".'
    ) in " ".join(words.split())
    assert config_module.config_path().read_text() == before
    assert _sent() == [("/v1/transactions/import-sheet", True, False)]
    assert all(r.call_count == 0 for r in creates.values())


@respx.mock
def test_a_sheet_account_named_with_a_currency_cannot_be_renamed(sheet):
    """A trailing `:` and three capital letters reads as a currency, so the
    flag names `Caja`, which the sheet lacks; nothing is saved."""
    answer = sheet_import_answer(accounts=[sheet_name_use("Caja:USD", 3, currencies=["USD"])])
    _engine(answer)
    _accounts([])
    result = _run("--account-name", "Caja:USD=Efectivo")
    assert result.exit_code == 2, _out(result)
    assert 'the sheet has no account "Caja:USD".' in strip_panel(_out(result))
    assert _saved() == {}


@respx.mock
def test_a_flag_replaces_every_saved_key_of_its_name_and_ends_the_stop(sheet):
    _save_names({"BCP:PEN": "Sueldo Soles", "BCP:USD": "Sueldo Dólares", "bcp": "Old"})
    _engine(_answer(yours=False))
    _accounts([])
    result = _run("--account-name", "BCP=Sueldo Soles")
    assert result.exit_code == 0, _out(result)
    assert _saved() == {"BCP": "Sueldo Soles"}


@pytest.mark.parametrize("value", ["BCP", "BCP:PEN", "BCP=", "=Sueldo"])
@respx.mock
def test_a_malformed_rename_is_a_usage_error_before_anything_is_sent(sheet, value):
    before = config_module.config_path().read_text()
    result = _run("--account-name", value)
    assert result.exit_code == 2, _out(result)
    assert "is not SHEET_NAME=LEDGER_NAME" in strip_panel(_out(result))
    assert config_module.config_path().read_text() == before
    assert not respx.calls


@respx.mock
def test_two_sheet_names_renamed_onto_one_account_go_with_the_same_account_id(sheet):
    """The engine decides what may share an account."""
    answer = _answer(yours=True)
    route = _engine(answer, _answer(yours=True, dry_run=False))
    _accounts([account_with_currencies(id="acc-sueldo", name="Sueldo")])
    result = _run("--account-name", "BCP=Sueldo", "--account-name", "Interbank=sueldo", "--apply")
    assert result.exit_code == 0, _out(result)
    sent = json.loads(route.calls[-1].request.content)["names"]["accounts"]
    assert sent[:2] == [
        {"name": "BCP", "account_id": "acc-sueldo"},
        {"name": "Interbank", "account_id": "acc-sueldo"},
    ]


@respx.mock
def test_a_rename_for_an_account_the_sheet_lacks_is_a_usage_error(sheet):
    _engine(_answer(yours=False))
    _accounts([])
    result = _run("--account-name", "Nope=Euros")
    assert result.exit_code == 2, _out(result)
    assert 'the sheet has no account "Nope".' in strip_panel(_out(result))
    assert _saved() == {}


# ---- the file and the settings -----------------------------------------------------
@respx.mock
def test_a_missing_file_is_refused_before_anything_is_sent(sheet):
    result = _run(file="gone.xlsx")
    assert result.exit_code == 1
    assert result.stderr == "Error: File not found: gone.xlsx\n"
    assert not respx.calls


def test_no_settings_file_exits_3(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPENSE_CONFIG", str(tmp_path / "none"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / FILE).write_bytes(b"made up")
    result = _run()
    assert result.exit_code == 3
    assert "No config found" in result.stderr


@respx.mock
def test_the_settings_file_is_read_once(sheet, monkeypatch):
    """The settings file may be a pipe (docs/runtime.md "Working against the
    live engine"), readable once."""
    reads = []
    real = config_module.load

    def counting():
        reads.append(1)
        return real()

    monkeypatch.setattr(config_module, "load", counting)
    _engine(_answer(yours=True), _answer(yours=True, dry_run=False))
    result = _run("--apply")
    assert result.exit_code == 0, _out(result)
    assert len(reads) == 1
