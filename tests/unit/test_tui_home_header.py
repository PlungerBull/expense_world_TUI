"""Home as four months — pure-function coverage (no event loop).

Home is the month grid. `home_rows`
turns the dashboard + range reads into the page's rows and `home_options`
aligns them. These lock the layout: four month columns, a category with
nothing in the window hidden, hashtag rows under a category that filter by
that hashtag, balances in their own currency, and the screen sections always
listed in full — they do not fold.
"""

from rich.text import Text

import expense.tui.screens.home as home
from expense.formatting import build_range_grid
from expense.tui.theme import Palette
from tests.unit.helpers import HOME_DASHBOARD, HOME_MONTHS, HOME_TAG_NAMES, render_text

PALETTE = Palette(success="#7fbf8f", error="#cf8d8d", warning="#d6b878")
DATA = dict(dashboard=HOME_DASHBOARD, grid=build_range_grid(HOME_MONTHS), names=HOME_TAG_NAMES)
SECTIONS = [
    "LEDGER",
    "  Transactions",
    "  Reconciliations",
    "MANAGE",
    "  Accounts",
    "  Categories",
    "  Hashtags",
    "SYSTEM",
    "  Config",
    "  Auth & profile",
]


def _render(renderable, width=100) -> str:
    return render_text(renderable, width=width)


def _live(rows):
    return [r for r in rows if r is not None]


def _plain(value) -> str:
    return value.plain if isinstance(value, Text) else str(value)


def _by_left(rows):
    return {r.left.strip(): r for r in _live(rows)}


# ---- small helpers -----------------------------------------------------------


def test_shift_month_rolls_over_years():
    assert home.shift_month(2026, 1, -1) == (2025, 12)
    assert home.shift_month(2025, 12, 1) == (2026, 1)
    assert home.shift_month(2026, 9, -3) == (2026, 6)
    assert home.shift_month(2026, 2, -14) == (2024, 12)


def test_month_labels():
    assert home.month_title((2026, 9)) == "September 2026"
    assert home.short_label("2026-09") == "Sep 2026"
    assert home.short_label("garbage") == "garbage"


def test_the_window_is_four_months():
    assert home.WINDOW_MONTHS == 4


# ---- home_rows -----------------------------------------------------------------


def test_rows_run_categories_totals_accounts_people_screens():
    lefts = [r.left.strip() for r in _live(home.home_rows(DATA, palette=PALETTE))]
    assert lefts[:3] == ["CATEGORIES", "▶ @Pendiente", "▶ WANTS"]
    assert lefts[3:7] == ["", "inflow", "outflow", "net"]
    assert lefts[7:10] == ["BANK ACCOUNTS", "BCP PEN", "BCP USD"]
    assert lefts[10:11] == ["PEOPLE"]
    assert lefts[11:] == [x.strip() for x in SECTIONS]


def test_a_category_with_nothing_in_the_window_is_hidden():
    """HOGAR spent nothing in either month."""
    assert "HOGAR" not in _by_left(home.home_rows(DATA, palette=PALETTE))


def test_the_header_marks_the_newest_month():
    header = _live(home.home_rows(DATA, palette=PALETTE))[0]
    assert [_plain(c) for c in header.right] == ["Aug 2026", "▸ Sep 2026"]


def test_category_cells_are_home_currency_with_a_dash_for_no_activity():
    rows = _by_left(home.home_rows(DATA, palette=PALETTE))
    pend = rows["▶ @Pendiente"]
    assert pend.id == "category:c-pend" and pend.name == "@Pendiente"
    assert [_plain(c) for c in pend.right] == ["-266.20", "-11,487.46"]
    assert pend.right[1].style == PALETTE.error
    assert [_plain(c) for c in rows["▶ WANTS"].right] == ["-1,608.43", "—"]
    assert [_plain(c) for c in rows["net"].right] == ["-1,874.63", "-11,487.46"]


def test_every_category_with_hashtag_rows_unfolds_pendiente_included():
    """@Pendiente's rows wait for a hashtag too, so it unfolds like the others."""
    rows = _by_left(home.home_rows(DATA, palette=PALETTE))
    assert "▶ @Pendiente" in rows
    assert "▶ WANTS" in rows


def test_a_category_with_no_hashtag_row_has_no_caret():
    """Nothing to unfold: the breakdown is empty (a hand-built grid; the engine
    counts every row under some hashtag)."""
    grid = build_range_grid(HOME_MONTHS)
    for row in grid["rows"]:
        row["breakdown"] = []
    rows = _by_left(home.home_rows({**DATA, "grid": grid}, palette=PALETTE))
    assert "@Pendiente" in rows and "WANTS" in rows


def test_unfolded_hashtag_rows_filter_by_category_and_hashtag():
    state = home.HomeState(expanded=frozenset({"c-wants"}))
    rows = _live(home.home_rows(DATA, state, PALETTE))
    lefts = [r.left.strip() for r in rows]
    i = lefts.index("▼ WANTS")
    sal, otr = rows[i + 1], rows[i + 2]
    assert (sal.left.strip(), otr.left.strip()) == ("#SALIDAS", "#OTROS")
    assert sal.id == "tag:c-wants:h-sal" and sal.hashtag == "h-sal"
    assert sal.name == "WANTS #SALIDAS" and sal.dim
    assert [_plain(c) for c in sal.right] == ["-648.50", "—"]


# ---- the pending hashtag's row ---------------------------------------------------
# A row still waiting for a hashtag counts under the built-in pending hashtag,
# which the breakdown groups like any other (contract: GET /v1/dashboard).

COMIDA_MONTHS = [
    {
        "month": {"year": 2026, "month": 10},
        "categories": [
            {
                "id": "c-com",
                "name": "COMIDA",
                "spent_home_cents": -31025,
                "unconverted_count": 0,
                "hashtag_breakdown": [
                    {"hashtag_ids": ["h-alm"], "spent_home_cents": -9675, "unconverted_count": 0},
                    {"hashtag_ids": ["h-pend"], "spent_home_cents": -1850, "unconverted_count": 0},
                    {"hashtag_ids": ["h-cas"], "spent_home_cents": -19500, "unconverted_count": 0},
                ],
            }
        ],
        "totals": {},
    }
]
COMIDA_NAMES = dict([("h-alm", "almuerzo"), ("h-cas", "casa"), ("h-pend", "Pendiente")])


def _comida_rows(names=COMIDA_NAMES):
    data = dict(dashboard={}, grid=build_range_grid(COMIDA_MONTHS), names=names)
    return _live(home.home_rows(data, home.HomeState(expanded=frozenset({"c-com"})), PALETTE))


def test_the_pending_hashtag_is_a_hashtag_row_like_the_others():
    """Under its category, in the engine's order, dim like #almuerzo and #casa,
    under the name the engine's hashtag list gives it, and it filters by its id."""
    rows = _comida_rows()
    lefts = [r.left.strip() for r in rows]
    i = lefts.index("▼ COMIDA")
    assert lefts[i + 1 : i + 4] == ["#almuerzo", "#Pendiente", "#casa"]
    alm, pend = rows[i + 1], rows[i + 2]
    assert pend.id == "tag:c-com:h-pend" and pend.hashtag == "h-pend"
    assert pend.name == "COMIDA #Pendiente"
    assert pend.dim == alm.dim is True
    assert [_plain(c) for c in pend.right] == ["-18.50"]
    alm_option, pend_option = home.home_options([alm, pend])
    assert pend_option.prompt.style == alm_option.prompt.style == "dim"
    assert pend_option.prompt.spans == alm_option.prompt.spans  # nothing set apart


def test_the_pending_row_takes_its_name_from_the_engine():
    """The label is the name `GET /hashtags` sends for the id, never a word the
    app supplies."""
    rows = _comida_rows(names={**COMIDA_NAMES, "h-pend": "Pend-from-engine"})
    assert "#Pend-from-engine" in [r.left.strip() for r in rows]


def test_no_row_reads_no_hashtags():
    """There is no "(no hashtags)" row: every breakdown row names its hashtags."""
    rows = _comida_rows() + _live(
        home.home_rows(DATA, home.HomeState(expanded=frozenset({"c-pend", "c-wants"})), PALETTE)
    )
    text = render_text(Text("\n").join(o.prompt for o in home.home_options(rows) if o), width=100)
    assert "(no hashtags)" not in text
    assert "#Pendiente" in text


def test_unfolded_pendiente_lists_its_pending_hashtag_row():
    state = home.HomeState(expanded=frozenset({"c-pend"}))
    rows = _live(home.home_rows(DATA, state, PALETTE))
    lefts = [r.left.strip() for r in rows]
    i = lefts.index("▼ @Pendiente")
    row = rows[i + 1]
    assert (row.left.strip(), row.id, row.hashtag) == ("#Pendiente", "tag:c-pend:h-pend", "h-pend")
    assert row.name == "@Pendiente #Pendiente"


def test_a_user_with_no_pending_hashtag_yet_sees_only_real_hashtags():
    """No row waits for a hashtag yet, so no breakdown names the pending
    hashtag and the hashtag list has none: nothing pending is drawn."""
    months = [dict(COMIDA_MONTHS[0])]
    cat = dict(months[0]["categories"][0])
    cat["hashtag_breakdown"] = [
        b for b in cat["hashtag_breakdown"] if b["hashtag_ids"] != ["h-pend"]
    ]
    months[0]["categories"] = [cat]
    names = dict([("h-alm", "almuerzo"), ("h-cas", "casa")])
    data = dict(dashboard={}, grid=build_range_grid(months), names=names)
    rows = _live(home.home_rows(data, home.HomeState(expanded=frozenset({"c-com"})), PALETTE))
    lefts = [r.left.strip() for r in rows]
    assert lefts[1:4] == ["▼ COMIDA", "#almuerzo", "#casa"]


def test_a_combo_of_several_hashtags_cannot_filter():
    months = [
        {
            "month": {"year": 2026, "month": 9},
            "categories": [
                {
                    "id": "c-x",
                    "name": "X",
                    "spent_home_cents": -300,
                    "unconverted_count": 0,
                    "hashtag_breakdown": [
                        {"hashtag_ids": ["h-a", "h-b"], "spent_home_cents": -300},
                    ],
                }
            ],
            "totals": {},
        }
    ]
    data = dict(
        dashboard={}, grid=build_range_grid(months), names=dict([("h-a", "A"), ("h-b", "B")])
    )
    rows = _by_left(home.home_rows(data, home.HomeState(expanded=frozenset({"c-x"}))))
    assert rows["#A + #B"].hashtag is None and rows["#A + #B"].id == "tag:c-x:#0"


def test_balances_are_native_with_the_code_beside_them():
    rows = _by_left(home.home_rows(DATA, palette=PALETTE))
    assert _plain(rows["BCP PEN"].right) == "5,145.82 PEN"
    assert _plain(rows["BCP USD"].right) == "1.30 USD"
    assert rows["BCP USD"].id == "account:a-usd"
    assert _plain(rows["BANK ACCOUNTS"].right) == "balance today"


def test_people_say_none_and_fold_the_settled():
    rows = _by_left(home.home_rows(DATA, palette=PALETTE))
    assert _plain(rows["PEOPLE"].right) == "none"
    people = [
        {"id": "p-1", "name": "Juan", "currency_code": "USD", "current_balance_cents": -4500},
        {"id": "p-2", "name": "Majo", "currency_code": "PEN", "current_balance_cents": 0},
    ]
    data = {**DATA, "dashboard": {**HOME_DASHBOARD, "people": people}}
    rows = _by_left(home.home_rows(data, palette=PALETTE))
    assert _plain(rows["Juan"].right) == "-45.00 USD" and rows["Juan"].id == "account:p-1"
    assert "Majo" not in rows and rows["▶ 1 settled"].id == home.SETTLED_ID
    rows = _by_left(home.home_rows(data, home.HomeState(settled_open=True), PALETTE))
    assert rows["Majo"].id == "account:p-2" and rows["Majo"].dim


def test_screens_stand_before_the_fetch_and_after_a_failure():
    assert [r.left for r in _live(home.home_rows(None))] == SECTIONS
    failed = _live(home.home_rows(None, error="Connection refused"))
    assert failed[0].id is None and "Connection refused" in failed[0].left
    assert [r.left for r in failed[1:]] == SECTIONS


def test_the_sections_never_fold():
    """LEDGER, MANAGE and SYSTEM are not collapsible. The
    headers are disabled rows and every screen is always a row of its own."""
    rows = _live(home.home_rows(None))
    headers = [r for r in rows if r.left in ("LEDGER", "MANAGE", "SYSTEM")]
    assert [r.id for r in headers] == [None, None, None]
    assert [r.id for r in rows if r.id] == [
        "transactions",
        "reconciliations",
        "accounts",
        "categories",
        "hashtags",
        "config",
        "auth",
    ]
    assert "open_doors" not in home.HomeState._fields


def test_the_ledger_section_no_longer_holds_overview():
    ledger = [r.left.strip() for r in _live(home.home_rows(None))][1:3]
    assert ledger == ["Transactions", "Reconciliations"]
    assert "overview" not in home._SCREENS


# ---- home_options ------------------------------------------------------------------


def test_month_columns_and_balances_end_on_the_same_column():
    rows = home.home_rows(DATA, home.HomeState(expanded=frozenset({"c-wants"})), PALETTE)
    widths = {
        row.left.strip(): len(option.prompt.plain)
        for row, option in zip(rows, home.home_options(rows), strict=True)
        if row is not None and (isinstance(row.right, list) or row.id and "account:" in row.id)
    }
    assert len(set(widths.values())) == 1, widths


def test_options_disable_exactly_the_rows_without_an_id():
    rows = home.home_rows(DATA, palette=PALETTE)
    for row, option in zip(rows, home.home_options(rows), strict=True):
        if row is None:
            assert option is None
        else:
            assert option.disabled is (row.id is None)
            assert option.id == row.id


# ---- _build_header -------------------------------------------------------------------


def test_build_header_shows_wordmark_and_month():
    out = _render(home._build_header("September 2026", PALETTE))
    assert home._BANNER in out and "September 2026" in out


def test_build_header_none_is_wordmark_only():
    assert _render(home._build_header(None, PALETTE)).strip() == home._BANNER
