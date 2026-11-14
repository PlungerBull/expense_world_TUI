"""`expense import sheet`: the dry run hands the first answer to the app; a sheet the engine
refuses prints each refusal by row, exits 1 and opens no app.

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


def _answer(*, yours: bool) -> dict:
    return sheet_import_answer(**_names(yours=yours), rows=[sheet_row(2)])


def _engine(first: dict | httpx.Response):
    """The import route answers `first`."""
    reply = first if isinstance(first, httpx.Response) else httpx.Response(200, json=first)
    return respx.post(IMPORT).mock(return_value=reply)


def _sent() -> list[tuple[str, bool | None, bool]]:
    """Every POST: its path, and its `dry_run` and whether the table went with it."""
    out = []
    for call in respx.calls:
        if call.request.method != "POST":
            continue
        body = _body(call.request)
        out.append((call.request.url.path, body.get("dry_run"), "names" in body))
    return out


@pytest.fixture
def review(monkeypatch):
    """The app the review opens: it records what it was opened on."""
    opened: list[SheetReview] = []

    def open_app(ctx, review=None):
        opened.append(review)
        return None

    monkeypatch.setattr("expense.commands.import_cmd.open_app", open_app)
    return opened


# ---- the first dry run opens the review ------------------------------------------------
@respx.mock
def test_the_dry_run_opens_the_review_on_the_first_answer(sheet, review):
    """Only the dry run without the table is sent; the app is opened on the file's name, its
    bytes and every name the engine listed; the command prints nothing."""
    _engine(_answer(yours=False))
    result = _run()
    assert result.exit_code == 0, _out(result)
    assert result.stdout == ""
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


@respx.mock
def test_a_bad_row_stops_the_command_and_lists_each_refusal_by_row(sheet, review):
    _engine(httpx.Response(422, json=ROWS_REFUSED))
    result = _run()
    assert result.exit_code == 1
    assert result.stdout == BAD_ROWS_REFUSAL
    assert review == []  # the app is not opened
    assert _sent() == [("/v1/transactions/import-sheet", True, False)]


@respx.mock
def test_a_file_refused_whole_prints_as_every_engine_error(sheet):
    refusal = error_body(
        "VALIDATION_ERROR",
        "The file is not the sheet's layout.",
        {"file": "Row 1 must be the twelve headers description … COD_EECC."},
        {"file": "UNEXPECTED_LAYOUT"},
    )
    _engine(httpx.Response(422, json=refusal))
    result = _run()
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
    _engine(httpx.Response(422, json=refusal))
    result = _run()
    assert result.exit_code == 1
    assert result.stdout == (
        "Refused — nothing written. 2 rows:\n"
        "  category: Another row is this account's opening balance. rows 2, 9\n\n"
        "Fix the sheet and run it again.\n"
    )


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
