"""Every amount the app writes follows the session's number format (`number_format.py`).

The writers are `format_cents`, `format_cents_with_plus` and `amount_to_text`; the
examples in notes are written through them too. The reading side is in
[test_quickadd_parse.py](test_quickadd_parse.py); the Edit form's own amount line in
[test_tui_edit_form.py](test_tui_edit_form.py).
"""

import ast
import re
from pathlib import Path

import pytest

import expense.tui.screens.home as home
from expense.formatting import build_range_grid, format_cents, format_cents_with_plus
from expense.number_format import NumberFormat, set_current_format
from expense.quickadd.money import amount_to_text, parse_amount
from expense.tui.screens.log_bar import example_line
from expense.tui.screens.statements import unreadable_note
from expense.tui.theme import Palette
from expense.tui.widgets.cells import amount_cell
from tests.unit.helpers import HOME_DASHBOARD, HOME_MONTHS, HOME_TAG_NAMES, render_text

DOT, COMMA = NumberFormat.DOT_DECIMAL, NumberFormat.COMMA_DECIMAL
PALETTE = Palette(success="#7fbf8f", error="#cf8d8d", warning="#d6b878")

CASES = [
    (123456, "1,234.56", "1.234,56"),
    (651900, "6,519.00", "6.519,00"),
    (-1850, "-18.50", "-18,50"),
    (0, "0.00", "0,00"),
    (5, "0.05", "0,05"),
    (-123456789, "-1,234,567.89", "-1.234.567,89"),
]


@pytest.mark.parametrize(("cents", "dot", "comma"), CASES)
def test_format_cents_writes_the_session_format(cents, dot, comma):
    assert format_cents(cents) == dot
    set_current_format(COMMA)
    assert format_cents(cents) == comma


def test_an_ungrouped_figure_keeps_only_the_decimal_mark(comma_format):
    assert format_cents(958000, grouped=False) == "9580,00"
    assert format_cents(-35000, grouped=False) == "-350,00"


def test_the_plus_sign_and_the_null_are_the_same_in_both_formats(comma_format):
    assert format_cents_with_plus(651900) == "+6.519,00"
    assert format_cents_with_plus(-1850) == "-18,50"
    assert format_cents_with_plus(0) == "0,00"
    assert format_cents(None) == "(null)"


@pytest.mark.parametrize("number_format", [DOT, COMMA])
def test_amount_to_text_round_trips_through_parse_amount(number_format):
    set_current_format(number_format)
    for cents in [0, 1, 5, 10, 99, 100, 101, 1850, 9992, 35000, 123456, 99999999999]:
        for signed in (cents, -cents):
            text = amount_to_text(signed)
            assert parse_amount(text, number_format) == signed, text
            assert number_format.group not in text


def test_amount_to_text_under_comma_is_ungrouped_with_a_comma_decimal(comma_format):
    assert amount_to_text(-9992) == "-99,92"
    assert amount_to_text(123456) == "1234,56"
    assert amount_to_text(-35000) == "-350"


def test_a_ledger_cell_follows_the_format(comma_format):
    assert amount_cell(651900, None, "plus-sign") == "+6.519,00"
    assert amount_cell(-1850, None, "plain") == "-18,50"
    assert render_text(amount_cell(123456, PALETTE, "sign")).strip() == "1.234,56"


def _home_text() -> str:
    data = dict(dashboard=HOME_DASHBOARD, grid=build_range_grid(HOME_MONTHS), names=HOME_TAG_NAMES)
    rows = home.home_rows(data, home.FOLDED, PALETTE)
    return "\n".join(
        f"{r.left} {render_text(r.right) if r.right is not None else ''}"
        for r in rows
        if r is not None
    )


@pytest.mark.parametrize(
    ("number_format", "balance", "other"),
    [(DOT, "5,145.82", "5.145,82"), (COMMA, "5.145,82", "5,145.82")],
)
def test_home_shows_its_balances_in_the_session_format(number_format, balance, other):
    set_current_format(number_format)
    out = _home_text()
    assert balance in out and other not in out


@pytest.mark.parametrize(
    ("number_format", "example", "begin", "end"),
    [
        (DOT, "-38.60", "9580.00", "9460.00"),
        (COMMA, "-38,60", "9580,00", "9460,00"),
    ],
)
def test_every_note_example_follows_the_format(number_format, example, begin, end):
    set_current_format(number_format)
    assert example_line() == f"e.g.  tottus {example} $signature @korakuen #caja hoy"
    assert f"e.g. {begin}." in unreadable_note("begin", "PEN")
    assert f"e.g. {end}." in unreadable_note("end", "PEN")
    assert (
        f"Amounts are {'1.234,56' if number_format is COMMA else '1,234.56'}."
        in unreadable_note("end", "PEN")
    )


_AMOUNT_LITERAL = re.compile(r"(?<![\d.,])\d{1,3}(?:[.,]\d{3})*[.,]\d{2}(?![\d.])")


def test_no_string_in_the_app_holds_an_amount_written_in_one_format():
    """A string literal (not a docstring or comment) with `38.60` or `13,853.20` in it
    is an amount that ignores the session's format; write it through `format_cents`."""
    found = []
    files = sorted((Path(__file__).resolve().parents[2] / "expense").rglob("*.py"))
    assert len(files) > 20
    for path in files:
        tree = ast.parse(path.read_text())
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and _AMOUNT_LITERAL.search(node.value)
            ):
                found.append(f"{path}:{node.lineno}: {node.value!r}")
    assert not found, "\n".join(found)
