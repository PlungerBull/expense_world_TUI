"""`expense import sheet`: what the terminal prints and where the review opens: the dry run
hands the first answer to the app, `--apply` and `--json` print, a sheet with bad rows and the
apply refused while a name is missing exit 1.

The engine is respx: every answer is the fake engine's `sheet_import_answer`
(tests/unit/helpers.py), every refusal an envelope shaped as the practice
engine sends it. The sheet's bytes never matter to the app, so the file is any
bytes on disk. The review itself is tests/unit/test_tui_import_sheet.py.
"""

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from expense.import_.engine import SheetReview
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import (
    error_body,
    real_cli_app,
    sheet_import_answer,
    sheet_name_use,
    sheet_row,
)

runner = CliRunner()
cli_app = real_cli_app()
IMPORT = f"{BASE}/v1/transactions/import-sheet"
FILE = "libro.xlsx"
#: The two commands that read the sheet's first dry run: the review and the apply.
STEPS = [[], ["--apply"]]
STEP_IDS = ["dry", "apply"]


@pytest.fixture
def sheet(configured, tmp_path, monkeypatch):
    """A sheet file, in the working folder."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / FILE).write_bytes(b"PK\x03\x04 a made-up workbook")


def _run(*args: str, file: str = FILE):
    return runner.invoke(cli_app, ["import", "sheet", file, *args])


def _out(result) -> str:
    return result.stdout + result.stderr


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


# ---- a made-up sheet ----------------------------------------------------
def _names(*, yours: bool) -> dict:
    """The names before any exists (`yours` False), or once every one is proposed."""

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


#: The counts once every name exists: 1,961 rows, 7 of them zero.
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


def _engine(first: dict | httpx.Response, tabled: dict | httpx.Response | None = None):
    """The import route: a body without `names` answers `first`, one with them
    `tabled`."""

    def answer(request: httpx.Request) -> httpx.Response:
        reply = tabled if "names" in _body(request) else first
        assert reply is not None, "the table was sent"
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)

    return respx.post(IMPORT).mock(side_effect=answer)


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


@pytest.fixture
def review(monkeypatch):
    """The app the review opens: it records what it was opened on and ends with a line."""
    opened: list[SheetReview] = []

    def open_app(ctx, review=None):
        opened.append(review)
        return "Nothing was imported."

    monkeypatch.setattr("expense.commands.import_cmd.open_app", open_app)
    return opened


# ---- the first dry run opens the review ------------------------------------------------
@respx.mock
def test_the_dry_run_opens_the_review_on_the_first_answer_and_prints_its_line(sheet, review):
    """Only the dry run without the table is sent; the app is opened on the file's name, its
    bytes and every name the engine listed, and what the app ends with is printed."""
    _engine(_answer(yours=False))
    result = _run()
    assert result.exit_code == 0, _out(result)
    assert result.stdout == "Nothing was imported.\n"
    assert _sent() == [("/v1/transactions/import-sheet", True, False)]
    (opened,) = review
    assert (opened.file_name, opened.data, opened.rows) == (
        FILE,
        b"PK\x03\x04 a made-up workbook",
        1,
    )
    assert opened.cfg.engine_url == BASE
    assert [(e.kind, e.name, e.target_id) for e in opened.table][:2] == [
        ("account", "BCP", None),
        ("account", "Interbank", None),
    ]


@respx.mock
def test_a_sheet_of_names_all_proposed_still_opens_the_review(sheet, review):
    _engine(_answer(yours=True))
    assert _run().exit_code == 0
    assert len(review) == 1


@respx.mock
def test_an_app_that_ends_with_no_line_prints_nothing(sheet, monkeypatch):
    monkeypatch.setattr("expense.commands.import_cmd.open_app", lambda ctx, review=None: None)
    _engine(_answer(yours=False))
    result = _run()
    assert (result.exit_code, result.stdout) == (0, "")


# ---- the apply while a name is missing -----------------------------------------------
@respx.mock
def test_the_apply_while_a_name_is_missing_is_refused_and_points_at_the_review(sheet):
    _engine(_answer(yours=False))
    result = _run("--apply")
    assert result.exit_code == 1
    assert result.stdout == (
        "Not imported — nothing written.\n"
        "9 names don't exist yet. Make them in the review:\n"
        "  expense import sheet libro.xlsx\n"
    )
    assert _sent() == [("/v1/transactions/import-sheet", True, False)]


# ---- the apply, then the same sheet again --------------------------------
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
def test_an_apply_lists_the_rows_on_a_closed_statements_day_under_the_zero_rows(sheet):
    counts = {**COUNTS, "new": 1952, "sealed": 2}
    rows = _counted_rows(sealed=(40, 41))
    _engine(
        _answer(yours=True),
        _answer(yours=True, dry_run=False, rows=rows, counts=counts),
    )
    result = _run("--apply")
    assert result.exit_code == 0, _out(result)
    assert result.stdout == (
        "Written: new 1,952 · matched 0 · sealed 2 · skipped 7\n"
        "Opening balances 4 · split transactions 3 (8 rows)\n\n"
        "Skipped, amount zero: rows 14, 90, 311, 1201, 1202, 1555, 1960\n"
        "Sealed, on a closed statement's day: rows 40, 41\n"
    )


@respx.mock
def test_an_apply_with_nothing_skipped_or_sealed_ends_on_its_counts(sheet):
    counts = {**COUNTS, "new": 1961, "skipped": 0}
    rows = [sheet_row(r, outcome="new", account_id="acc-ib") for r in range(2, 1963)]
    _engine(
        _answer(yours=True),
        _answer(yours=True, dry_run=False, rows=rows, counts=counts),
    )
    result = _run("--apply")
    assert result.exit_code == 0, _out(result)
    assert result.stdout == (
        "Written: new 1,961 · matched 0 · sealed 0 · skipped 0\n"
        "Opening balances 4 · split transactions 3 (8 rows)\n"
    )


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


# ---- a sheet with bad rows -----------------------------------------------
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

BAD_ROWS_REFUSAL = """\
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
    result = _run(*step)
    assert result.exit_code == 1
    assert result.stdout == BAD_ROWS_REFUSAL
    assert _sent() == [("/v1/transactions/import-sheet", True, False)]


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
@pytest.mark.parametrize(
    ("args", "first", "then"),
    [
        ((), _answer(yours=False), None),
        (
            (),
            _answer(yours=True),
            _answer(yours=True, rows=_counted_rows(), counts=COUNTS),
        ),
        (
            ("--apply",),
            _answer(yours=True),
            _answer(yours=True, dry_run=False, rows=_counted_rows(), counts=COUNTS),
        ),
    ],
    ids=["names missing", "counted", "apply"],
)
@respx.mock
def test_json_prints_the_engines_answer_and_opens_no_review(sheet, review, args, first, then):
    _engine(first, then)
    result = _run(*args, "--json")
    assert result.exit_code == 0, _out(result)
    assert json.loads(result.stdout) == (then or first)
    assert review == []


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
            "message": ("Not imported — nothing written. 9 names don't exist yet."),
            "fields": None,
            "reasons": None,
            "details": None,
        }
    }
