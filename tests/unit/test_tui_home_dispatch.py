"""HomeScreen dispatch — every screen entry pushes its screen, every live row
pushes the filtered ledger, and the page keys walk the month window.

Each case drives the real path — focus the menu, open what needs opening,
highlight the row, press the key — and asserts the result.
"""

import pytest
from textual.widgets import OptionList

import expense.tui.screens.home as home
from expense.tui.screens._base import SectionScreen
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.log_bar import LogBarScreen
from expense.tui.screens.quick_log import QuickAddLogScreen
from expense.tui.screens.transactions import LedgerFilter, TransactionsScreen
from tests.unit.helpers import run_app, stub_home_month, wait_for

_CASES = [
    ("ledger", "transactions", home.TransactionsScreen),
    ("ledger", "reconciliations", home.ReconciliationsScreen),
    ("manage", "accounts", home.AccountsScreen),
    ("manage", "categories", home.CategoriesScreen),
    ("manage", "hashtags", home.HashtagsScreen),
    ("system", "config", home.ConfigScreen),
    ("system", "auth", home.AuthScreen),
]


def _stub_loaders(monkeypatch):
    """Kill every on-mount fetch: Home's month worker, every SectionScreen
    worker (_load), and the capture screens' entity loads."""
    monkeypatch.setattr(HomeScreen, "_load_month", lambda self: None)
    monkeypatch.setattr(SectionScreen, "_load", lambda self: None)
    monkeypatch.setattr(QuickAddLogScreen, "_load_entities", lambda self: None)
    monkeypatch.setattr(LogBarScreen, "_load_entities", lambda self: None)


def _stub_month(monkeypatch, calls=None):
    stub_home_month(monkeypatch, calls=calls)
    monkeypatch.setattr(SectionScreen, "_load", lambda self: None)


async def _highlight(app, option_id):
    menu = app.query_one("#menu", OptionList)
    app.set_focus(menu)
    menu.highlighted = menu.get_option_index(option_id)


async def _select(app, pilot, option_id):
    await _highlight(app, option_id)
    await pilot.press("enter")


async def _month_loaded(app, pilot):
    await wait_for(pilot, lambda: app.screen._data is not None)


@pytest.mark.parametrize(("section", "kind", "screen_cls"), _CASES, ids=[k for _, k, _ in _CASES])
def test_section_entry_dispatch(monkeypatch, section, kind, screen_cls):
    _stub_loaders(monkeypatch)

    async def scenario(pilot, app):
        await pilot.pause()
        await _select(app, pilot, kind)  # always listed: nothing to open first
        await wait_for(pilot, lambda: isinstance(app.screen, screen_cls))
        assert type(app.screen) is screen_cls

    run_app(scenario, size=(100, 40))


def test_left_and_right_on_a_screen_entry_change_nothing(monkeypatch):
    """The sections are not collapsible."""
    _stub_loaders(monkeypatch)

    async def scenario(pilot, app):
        await pilot.pause()
        menu = app.query_one("#menu", OptionList)
        count = menu.option_count
        await _highlight(app, "accounts")
        await pilot.press("left")
        await pilot.press("right")
        await pilot.pause()
        assert menu.option_count == count
        assert app.screen._cursor_id() == "accounts"
        assert isinstance(app.screen, HomeScreen)

    run_app(scenario, size=(100, 40))


def test_cases_cover_every_section_entry():
    """Armor: a new section entry must get a dispatch case here (and vice versa)."""
    wired = {kind for _section, _label, entries in home._SECTIONS for kind, _ in entries}
    assert wired == {kind for _, kind, _ in _CASES}


def test_screens_map_covers_every_section_entry():
    wired = {kind for _section, _label, entries in home._SECTIONS for kind, _ in entries}
    assert set(home._SCREENS) == wired


def test_log_is_not_a_section_entry():
    """`Log a transaction` is not a menu row — `+` logs; guard the reflex re-add."""
    labels = [text for _section, _label, entries in home._SECTIONS for _kind, text in entries]
    assert "Log a transaction" not in labels
    assert "log" not in home._SCREENS


def test_the_overview_screen_is_gone():
    """There is no Overview screen: Home is the month grid."""
    import importlib.util

    assert importlib.util.find_spec("expense.tui.screens.overview") is None


def test_enter_on_a_category_filters_the_ledger_by_it(monkeypatch):
    _stub_month(monkeypatch)

    async def scenario(pilot, app):
        await _month_loaded(app, pilot)
        await _select(app, pilot, "category:c-pend")
        await wait_for(pilot, lambda: isinstance(app.screen, TransactionsScreen))
        assert app.screen._filter == LedgerFilter("category", "c-pend", "@Pendiente")

    run_app(scenario)


def test_enter_on_a_hashtag_filters_by_category_and_hashtag(monkeypatch):
    _stub_month(monkeypatch)

    async def scenario(pilot, app):
        await _month_loaded(app, pilot)
        await _highlight(app, "category:c-wants")
        await pilot.press("right")
        await wait_for(pilot, lambda: "c-wants" in app.screen._state.expanded)
        await _select(app, pilot, "tag:c-wants:h-sal")
        await wait_for(pilot, lambda: isinstance(app.screen, TransactionsScreen))
        assert app.screen._filter == LedgerFilter(
            "category", "c-wants", "WANTS #SALIDAS", hashtag_id="h-sal"
        )
        assert app.screen.crumb == ("Ledger", "WANTS #SALIDAS")

    run_app(scenario, size=(100, 40))


def test_left_on_a_hashtag_row_folds_its_category_and_lands_on_it(monkeypatch):
    _stub_month(monkeypatch)

    async def scenario(pilot, app):
        await _month_loaded(app, pilot)
        await _highlight(app, "category:c-wants")
        await pilot.press("right")
        await wait_for(pilot, lambda: "c-wants" in app.screen._state.expanded)
        await _highlight(app, "tag:c-wants:h-otr")
        await pilot.press("left")
        await wait_for(pilot, lambda: "c-wants" not in app.screen._state.expanded)
        assert app.screen._cursor_id() == "category:c-wants"

    run_app(scenario, size=(100, 40))


def test_esc_from_a_filtered_ledger_is_home_again(monkeypatch):
    """⏎ on a category or a hashtag, then esc,
    lands on Home — not on the unfiltered ledger."""
    _stub_month(monkeypatch)

    async def scenario(pilot, app):
        await _month_loaded(app, pilot)
        home_screen = app.screen
        await _select(app, pilot, "category:c-pend")
        await wait_for(pilot, lambda: isinstance(app.screen, TransactionsScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is home_screen)
        await _highlight(app, "category:c-wants")
        await pilot.press("right")
        await wait_for(pilot, lambda: "c-wants" in app.screen._state.expanded)
        await _select(app, pilot, "tag:c-wants:h-sal")
        await wait_for(pilot, lambda: isinstance(app.screen, TransactionsScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is home_screen)

    run_app(scenario, size=(100, 40))


def test_enter_on_an_account_filters_the_ledger_by_it(monkeypatch):
    _stub_month(monkeypatch)

    async def scenario(pilot, app):
        await _month_loaded(app, pilot)
        await _select(app, pilot, "account:a-pen")
        await wait_for(pilot, lambda: isinstance(app.screen, TransactionsScreen))
        assert app.screen._filter == LedgerFilter("account", "a-pen", "BCP PEN")

    run_app(scenario)


def test_pgdn_walks_the_window_back_and_pgup_stops_at_this_month(monkeypatch):
    """The page keys beat the OptionList's own page scroll (priority=True)."""
    calls: list = []
    _stub_month(monkeypatch, calls=calls)

    async def scenario(pilot, app):
        await _month_loaded(app, pilot)
        screen = app.screen
        today = screen._today
        assert calls[-1] == (home.shift_month(*today, -3), today)
        await pilot.press("pagedown")
        back = home.shift_month(*today, -1)
        await wait_for(pilot, lambda: calls[-1][1] == back)
        assert calls[-1][0] == home.shift_month(*back, -3)
        await pilot.press("pageup")
        await wait_for(pilot, lambda: calls[-1][1] == today)
        count = len(calls)
        await pilot.press("pageup")  # already at this month
        await pilot.pause()
        assert len(calls) == count and screen._end == today

    run_app(scenario, size=(100, 20))


def test_home_keeps_the_cursor_row_across_a_reload(monkeypatch):
    _stub_month(monkeypatch)

    async def scenario(pilot, app):
        await _month_loaded(app, pilot)
        await _highlight(app, "account:a-pen")
        app.screen._set_data(app.screen._data, None)
        await pilot.pause()
        assert app.screen._cursor_id() == "account:a-pen"

    run_app(scenario)


def test_plus_opens_the_log_form_from_home(monkeypatch):
    _stub_loaders(monkeypatch)

    async def scenario(pilot, app):
        await pilot.pause()
        await pilot.press("+")
        await wait_for(pilot, lambda: isinstance(app.screen, LogBarScreen))
        assert app.screen._staged == []

    run_app(scenario)


def test_q_quits_from_home(monkeypatch):
    _stub_loaders(monkeypatch)

    async def scenario(pilot, app):
        await pilot.pause()
        await pilot.press("q")
        await wait_for(pilot, lambda: not app.is_running)

    run_app(scenario)


def test_q_inert_off_home(monkeypatch):
    _stub_loaders(monkeypatch)

    async def scenario(pilot, app):
        await pilot.pause()
        await _select(app, pilot, "accounts")
        await wait_for(pilot, lambda: isinstance(app.screen, home.AccountsScreen))
        await pilot.press("q")
        await pilot.pause()
        assert app.is_running
        assert isinstance(app.screen, home.AccountsScreen)

    run_app(scenario, size=(100, 40))
