"""A row shows its engine `day`, never the first ten characters of its `date`.

`2026-11-05T04:30:00Z` is the evening of the 4th in Lima; the engine says so in `day`
(contract: GET /v1/transactions) and every screen shows that.
"""

from expense.formatting import bank_line_columns, format_day
from expense.reads import QuickAddRefs
from expense.tui.screens._base import dated_transaction_line, transaction_delete_message
from expense.tui.screens.edit_form import EditFormScreen
from expense.tui.screens.log_bar import peek_rows
from expense.tui.screens.transactions import transaction_rows
from tests.unit.helpers import day_of, import_part

LATE = "2026-11-05T04:30:00Z"
ROW = {
    **import_part("tx-late", -1000, day=day_of(LATE), account_id="acc1"),
    "date": LATE,
}


def test_the_fixture_row_is_the_4th_in_lima_and_the_5th_in_utc():
    assert (ROW["date"][:10], ROW["day"]) == ("2026-11-05", "2026-11-04")


def test_format_day_reads_the_day_and_a_row_without_one_is_a_dash():
    assert format_day(ROW) == "2026-11-04"
    assert format_day({"date": LATE}) == "—"
    assert format_day(None) == "—"


def test_the_ledger_row_shows_the_day():
    ((_id, cells),) = transaction_rows([ROW], {}, {}, {})
    assert "2026-11-04" in [str(c) for c in cells]
    assert "2026-11-05" not in [str(c) for c in cells]


def test_a_statement_list_line_shows_the_day_of_its_first_part():
    day, *_ = bank_line_columns({"parts": [ROW], "net_cents": -1000})
    assert day == "2026-11-04"


def test_the_peek_shows_the_day():
    (row,) = peek_rows([ROW], QuickAddRefs([], [], [], {}, {}, {}), today="2026-11-08")
    assert str(row[0]) == "4 Nov"


def test_the_delete_question_and_a_bulk_line_show_the_day():
    assert "2026-11-04" in transaction_delete_message(ROW, "BCP")
    assert dated_transaction_line(ROW).startswith("2026-11-04 · ")


def test_the_edit_form_prefills_the_day():
    screen = EditFormScreen(record=ROW)
    assert screen._values["date"] == "2026-11-04"
