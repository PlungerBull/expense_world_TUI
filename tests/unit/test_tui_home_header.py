"""Home as the month — pure-function coverage (no event loop).

Home became a live list on 2026-09-12 (docs/mockups/expense-world-home-as-
ledger.html, picks A and C): `home_rows` turns one dashboard body into the
page's rows and `home_options` aligns them into menu options. These lock the
contract: categories in the home currency with a `net` line, accounts and
people in their own currency with the code beside the figure, the People
section folding to `none`, the three doors always present (even before the
fetch lands, even when it fails), and every colour from the palette.
"""

import io

from rich.console import Console
from rich.text import Text

import expense.tui.screens.home as home
from expense.tui.theme import Palette

PALETTE = Palette(success="#7fbf8f", error="#cf8d8d", warning="#d6b878")

BODY = {
    "month": {"year": 2026, "month": 9},
    "categories": [
        {
            "id": "c-pend",
            "name": "@Pendiente",
            "spent_home_cents": -1148746,
            "unconverted_count": 0,
        },
        {"id": "c-ing", "name": "INGRESOS", "spent_home_cents": 0, "unconverted_count": 0},
        {"id": "c-x", "name": "VIAJES", "spent_home_cents": None, "unconverted_count": 3},
    ],
    "bank_accounts": [
        {"id": "a-pen", "name": "BCP PEN", "currency_code": "PEN", "current_balance_cents": 514582},
        {"id": "a-usd", "name": "BCP USD", "currency_code": "USD", "current_balance_cents": 130},
    ],
    "people": [],
    "totals": {"net_home_cents": -1148746, "unconverted_count": 0},
}


def _render(renderable, width=100) -> str:
    con = Console(file=io.StringIO(), width=width)
    con.print(renderable)
    return con.file.getvalue()


def _live(rows):
    return [r for r in rows if r is not None]


def _plain(value) -> str:
    return value.plain if isinstance(value, Text) else str(value)


# ---- month_label -----------------------------------------------------------


def test_month_label_names_the_month():
    assert home.month_label({"year": 2026, "month": 9}) == "September 2026"
    assert home.month_label({"year": 2026, "month": 13}) == ""
    assert home.month_label(None) == ""


# ---- home_rows -------------------------------------------------------------


def test_rows_carry_categories_then_net_then_accounts_then_people_then_doors():
    rows = _live(home.home_rows(BODY, set(), PALETTE))
    lefts = [r.left for r in rows]
    assert lefts[:5] == ["CATEGORIES", "@Pendiente", "INGRESOS", "VIAJES", "net"]
    assert lefts[5:8] == ["BANK ACCOUNTS", "BCP PEN", "BCP USD"]
    assert lefts[8:9] == ["PEOPLE"]
    assert lefts[9:] == ["LEDGER ▸", "MANAGE ▸", "SYSTEM ▸"]


def test_category_rows_are_home_currency_figures_and_filters():
    rows = {r.left: r for r in _live(home.home_rows(BODY, set(), PALETTE))}
    pend = rows["@Pendiente"]
    assert pend.id == "category:c-pend" and pend.name == "@Pendiente"
    assert _plain(pend.right) == "-11,487.46"
    assert pend.right.style == PALETTE.error  # sign-coloured, from the palette
    # nothing spent is a dim 0.00, not a green one
    assert _plain(rows["INGRESOS"].right) == "0.00" and rows["INGRESOS"].right.style == "dim"
    # a category the engine could not price says so
    assert _plain(rows["VIAJES"].right) == "3 unrated"
    assert _plain(rows["net"].right) == "-11,487.46" and rows["net"].id is None


def test_account_rows_are_native_with_the_code_beside_them():
    """Pick A (2026-09-12): the balance you act on is the native one, so every
    account carries its own code — PEN is PEN and USD is USD."""
    rows = {r.left: r for r in _live(home.home_rows(BODY, set(), PALETTE))}
    assert _plain(rows["BCP PEN"].right) == "5,145.82 PEN"
    assert _plain(rows["BCP USD"].right) == "1.30 USD"
    assert rows["BCP USD"].id == "account:a-usd"


def test_people_fold_to_none_and_are_account_filters_when_present():
    rows = {r.left: r for r in _live(home.home_rows(BODY, set(), PALETTE))}
    assert _plain(rows["PEOPLE"].right) == "none"
    body = {
        **BODY,
        "people": [
            {"id": "p1", "name": "Juan", "currency_code": "USD", "current_balance_cents": -4500}
        ],
    }
    rows = {r.left: r for r in _live(home.home_rows(body, set(), PALETTE))}
    assert _plain(rows["PEOPLE"].right) == "owed"
    assert rows["Juan"].id == "account:p1" and _plain(rows["Juan"].right) == "-45.00 USD"


def test_doors_are_there_before_the_fetch_and_after_a_failure():
    before = _live(home.home_rows(None, set()))
    assert [r.left for r in before] == ["LEDGER ▸", "MANAGE ▸", "SYSTEM ▸"]
    failed = _live(home.home_rows(None, set(), error="Connection refused"))
    assert failed[0].id is None and "Connection refused" in failed[0].left
    assert [r.left for r in failed[1:]] == ["LEDGER ▸", "MANAGE ▸", "SYSTEM ▸"]


def test_an_open_door_lists_its_entries_under_it():
    rows = _live(home.home_rows(None, {"manage"}))
    lefts = [r.left for r in rows]
    assert lefts == [
        "LEDGER ▸",
        "MANAGE ▾",
        "  Accounts",
        "  Categories",
        "  Hashtags",
        "SYSTEM ▸",
    ]
    assert [r.id for r in rows[2:5]] == ["accounts", "categories", "hashtags"]


def test_headers_and_notes_are_never_selectable():
    for row in _live(home.home_rows(BODY, set(), PALETTE)):
        if row.left in ("CATEGORIES", "net", "BANK ACCOUNTS", "PEOPLE"):
            assert row.id is None and row.dim


# ---- home_options ----------------------------------------------------------


def test_options_align_the_amount_column_across_rows():
    options = [o for o in home.home_options(home.home_rows(BODY, set(), PALETTE)) if o]
    ends = {}
    for option in options:
        plain = option.prompt.plain
        if plain.rstrip().endswith(("PEN", "USD", ".46", ".00", "unrated")):
            ends[plain.strip().split()[0]] = len(plain.rstrip())
    # every figure ends on the same column
    assert len(set(ends.values())) == 1, ends


def test_options_disable_exactly_the_rows_without_an_id():
    rows = home.home_rows(BODY, set(), PALETTE)
    options = home.home_options(rows)
    for row, option in zip(rows, options, strict=True):
        if row is None:
            assert option is None  # a separator
        else:
            assert option.disabled is (row.id is None)
            assert option.id == row.id


# ---- _build_header ---------------------------------------------------------


def test_build_header_shows_wordmark_and_month():
    out = _render(home._build_header("September 2026", PALETTE))
    assert home._BANNER in out and "September 2026" in out


def test_build_header_none_is_wordmark_only():
    out = _render(home._build_header(None, PALETTE))
    assert home._BANNER in out
    assert out.strip() == home._BANNER
