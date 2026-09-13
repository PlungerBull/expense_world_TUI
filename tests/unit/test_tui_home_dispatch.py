"""HomeScreen dispatch — every door entry pushes its screen, every live row
pushes the filtered ledger (backlog 6.3, redrawn 2026-09-12).

Each case drives the real path — focus the menu, open the door, highlight the
entry, press enter — and asserts the pushed screen. A typo'd id would leave a
row dead with a green suite otherwise.
"""

import asyncio

import pytest
from textual.widgets import OptionList

import expense.tui.screens.home as home
from expense.commands import dashboard_cmd
from expense.tui.app import ExpenseApp
from expense.tui.screens._base import SectionScreen
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.log_bar import LogBarScreen
from expense.tui.screens.quick_log import QuickAddLogScreen
from expense.tui.screens.transactions import LedgerFilter, TransactionsScreen
from tests.unit.helpers import wait_for

_CASES = [
    ("ledger", "transactions", home.TransactionsScreen),
    ("ledger", "reconciliations", home.ReconciliationsScreen),
    ("ledger", "overview", home.OverviewScreen),
    ("manage", "accounts", home.AccountsScreen),
    ("manage", "categories", home.CategoriesScreen),
    ("manage", "hashtags", home.HashtagsScreen),
    ("system", "config", home.ConfigScreen),
    ("system", "auth", home.AuthScreen),
    ("system", "activity", home.ActivityScreen),
    ("system", "rates", home.RatesScreen),
]

BODY = {
    "month": {"year": 2026, "month": 9},
    "categories": [
        {"id": "c-pend", "name": "@Pendiente", "spent_home_cents": -1148746, "unconverted_count": 0}
    ],
    "bank_accounts": [
        {"id": "a-pen", "name": "BCP PEN", "currency_code": "PEN", "current_balance_cents": 514582}
    ],
    "people": [],
    "totals": {"net_home_cents": -1148746, "unconverted_count": 0},
}


def _stub_loaders(monkeypatch):
    """Kill every on-mount fetch: HomeScreen's dashboard worker, every
    SectionScreen worker (_load), and QuickAddLogScreen's own _load_entities."""
    monkeypatch.setattr(HomeScreen, "_load_dashboard", lambda self: None)
    monkeypatch.setattr(SectionScreen, "_load", lambda self: None)
    monkeypatch.setattr(QuickAddLogScreen, "_load_entities", lambda self: None)
    monkeypatch.setattr(LogBarScreen, "_load_entities", lambda self: None)


def _stub_dashboard(monkeypatch, body=BODY):
    monkeypatch.setattr(dashboard_cmd, "fetch_dashboard", lambda *a, **k: body)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    monkeypatch.setattr(SectionScreen, "_load", lambda self: None)


async def _select(app, pilot, option_id):
    menu = app.query_one("#menu", OptionList)
    app.set_focus(menu)
    menu.highlighted = menu.get_option_index(option_id)
    await pilot.press("enter")


async def _open_door_and_select(app, pilot, door, kind):
    await _select(app, pilot, f"door:{door}")
    await wait_for(pilot, lambda: door in app.screen._open)
    await _select(app, pilot, kind)


@pytest.mark.parametrize(("door", "kind", "screen_cls"), _CASES, ids=[k for _, k, _ in _CASES])
def test_door_entry_dispatch(monkeypatch, door, kind, screen_cls):
    _stub_loaders(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _open_door_and_select(app, pilot, door, kind)
            await wait_for(pilot, lambda: isinstance(app.screen, screen_cls))
            assert type(app.screen) is screen_cls

    asyncio.run(scenario())


def test_a_door_closes_again_on_enter(monkeypatch):
    _stub_loaders(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select(app, pilot, "door:manage")
            await wait_for(pilot, lambda: "manage" in app.screen._open)
            menu = app.query_one("#menu", OptionList)
            assert menu.get_option_index("accounts") is not None
            await _select(app, pilot, "door:manage")
            await wait_for(pilot, lambda: "manage" not in app.screen._open)
            assert isinstance(app.screen, HomeScreen)

    asyncio.run(scenario())


def test_cases_cover_every_door_entry():
    """Armor: a new door entry must get a dispatch case here (and vice versa)."""
    wired = {kind for _door, _label, entries in home._DOORS for kind, _ in entries}
    assert wired == {kind for _, kind, _ in _CASES}


def test_screens_map_covers_every_door_entry():
    """The dispatch dict must stay in lockstep with the doors: no entry left
    undispatched, no stale screen mapping."""
    wired = {kind for _door, _label, entries in home._DOORS for kind, _ in entries}
    assert set(home._SCREENS) == wired


def test_log_is_not_a_door_entry():
    """`Log a transaction` was removed from the menu on 2026-08-20 in favour of
    `+`. Guard so it is not re-added by reflex — the row and the key would be two
    doors to one form, and the menu is the slower one."""
    labels = [text for _door, _label, entries in home._DOORS for _kind, text in entries]
    assert "Log a transaction" not in labels
    assert "log" not in home._SCREENS


def test_enter_on_a_category_opens_the_ledger_filtered_to_it(monkeypatch):
    """The categorising pass: `⏎` on `@Pendiente` is the filter (2026-09-12)."""
    _stub_dashboard(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await wait_for(pilot, lambda: app.screen._body is not None)
            await _select(app, pilot, "category:c-pend")
            await wait_for(pilot, lambda: isinstance(app.screen, TransactionsScreen))
            assert app.screen._filter == LedgerFilter("category", "c-pend", "@Pendiente")
            assert app.screen.crumb == ("Ledger", "@Pendiente")

    asyncio.run(scenario())


def test_enter_on_an_account_opens_the_ledger_filtered_to_it(monkeypatch):
    _stub_dashboard(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await wait_for(pilot, lambda: app.screen._body is not None)
            await _select(app, pilot, "account:a-pen")
            await wait_for(pilot, lambda: isinstance(app.screen, TransactionsScreen))
            assert app.screen._filter == LedgerFilter("account", "a-pen", "BCP PEN")

    asyncio.run(scenario())


def test_home_keeps_the_cursor_row_across_a_reload(monkeypatch):
    """The month re-reads on every return home; the cursor must not snap back
    to the first row each time."""
    _stub_dashboard(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await wait_for(pilot, lambda: app.screen._body is not None)
            menu = app.query_one("#menu", OptionList)
            menu.highlighted = menu.get_option_index("account:a-pen")
            app.screen._set_body(BODY, None)
            await pilot.pause()
            assert menu.get_option_at_index(menu.highlighted).id == "account:a-pen"

    asyncio.run(scenario())


def test_plus_opens_the_log_form_from_home(monkeypatch):
    """`+` replaces the deleted menu row (2026-08-20). Plain `+`, no modifier —
    the numpad key and the main-row key send the same byte."""
    _stub_loaders(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("+")
            await wait_for(pilot, lambda: isinstance(app.screen, LogBarScreen))
            # the LOG bar, not the bar-cycle form: quick-add phase 4 moved the
            # create door and left the edit door alone
            assert app.screen._staged == []

    asyncio.run(scenario())


def test_q_quits_from_home(monkeypatch):
    """q is scoped to HomeScreen (backlog 4.6 B) — from home it quits."""
    _stub_loaders(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("q")
            await wait_for(pilot, lambda: not app.is_running)

    asyncio.run(scenario())


def test_q_inert_off_home(monkeypatch):
    """On a section screen q must do nothing — no App-level quit binding left."""
    _stub_loaders(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _open_door_and_select(app, pilot, "manage", "accounts")
            await wait_for(pilot, lambda: isinstance(app.screen, home.AccountsScreen))
            await pilot.press("q")
            await pilot.pause()  # let the (inert) keypress settle, then assert a non-event
            assert app.is_running
            assert isinstance(app.screen, home.AccountsScreen)

    asyncio.run(scenario())
