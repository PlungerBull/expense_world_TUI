"""On an empty list the footer shows only the keys that work, at 80 columns, and each key
comes back with the first row; a pressed key does nothing and sends nothing."""

import pytest

from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.categories import CategoriesScreen
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.screens.statements import StatementsScreen
from expense.tui.screens.transactions import TransactionsScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    account_with_currencies,
    fake_ledger,
    held_currency,
    run_app,
    screen_lines,
    wait_for,
    wait_for_list,
    whole,
)
from tests.unit.test_tui_fitting_footer import ROWS, _footer, _stub_ledger

SIZE = (80, 24)
ACCOUNT = account_with_currencies(id="a1", name="BCP", currencies=[held_currency("PEN", 100)])
TAG = {"id": "h1", "name": "trabajo", "system_key": None}
CAT = {"id": "c1", "name": "Comida", "color": None, "is_system": False, "system_key": None}

#: name -> (screen class, the read it makes, one row of it, the footer with a row)
MANAGE = {
    "accounts": (AccountsScreen, "fetch_accounts", ACCOUNT),
    "categories": (CategoriesScreen, "fetch_categories", CAT),
    "hashtags": (HashtagsScreen, "fetch_hashtags", TAG),
}
#: The footers with one row, as before the empty ones left out their row keys.
WITH_A_ROW = {
    "accounts": "⏎ Open esc Back r Refresh ? Keys n New e Edit c Currency x Remove currency",
    "categories": "⏎ Open  esc Back  r Refresh  ? Keys  n New  e Edit  d Delete",
    "hashtags": "⏎ Open  esc Back  r Refresh  ? Keys  n New  e Edit  d Delete",
}
EMPTY_MANAGE = "esc Back  r Refresh  ? Keys  n New"


def _serve(monkeypatch, name: str, items: list) -> list:
    """Manage's read answers from `items`, read on every call so a test can change it."""
    _screen, read, _row = MANAGE[name]
    monkeypatch.setattr(f"expense.reads.{read}", lambda *a, **k: whole(items))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    return items


def _line(app) -> str:
    return _footer(app).strip()


@pytest.mark.parametrize("name", sorted(MANAGE))
def test_a_manage_list_with_a_row_keeps_its_open_key(monkeypatch, name):
    _serve(monkeypatch, name, [MANAGE[name][2]])

    async def scenario(pilot, app):
        await app.push_screen(MANAGE[name][0]())
        await wait_for_list(pilot, app)
        await pilot.pause()
        return _line(app)

    assert run_app(scenario, size=SIZE) == WITH_A_ROW[name]


@pytest.mark.parametrize("name", sorted(MANAGE))
def test_manage_keys_return_with_the_first_row_and_leave_with_the_last(monkeypatch, name):
    items = _serve(monkeypatch, name, [])

    async def scenario(pilot, app):
        screen = MANAGE[name][0]()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.pause()
        empty = _line(app)
        items.append(MANAGE[name][2])
        await pilot.press("r")
        await wait_for(pilot, lambda: _line(app).startswith("⏎ Open"))
        with_row = _line(app)
        items.clear()  # the last row went: a delete reloads from the engine
        await pilot.press("r")
        await wait_for(pilot, lambda: _line(app) == EMPTY_MANAGE)
        return empty, with_row, _line(app)

    empty, with_row, emptied = run_app(scenario, size=SIZE)
    assert empty == emptied == EMPTY_MANAGE
    assert "e Edit" in with_row


def test_the_ledger_keys_return_with_the_first_row_and_leave_with_the_last(monkeypatch):
    _stub_ledger(monkeypatch)
    rows: list = []
    fake_ledger(monkeypatch, rows)

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        screen.query_one(CursorList).focus()
        await pilot.pause()
        empty = _line(app)
        rows.append(ROWS[0])
        await pilot.press("r")
        await wait_for(pilot, lambda: _line(app).startswith("⏎ Open"))
        screen.query_one(CursorList).focus()
        with_row = _line(app)
        rows.clear()  # the last row deleted
        await pilot.press("r")
        await wait_for(pilot, lambda: _line(app) == empty)
        return empty, with_row

    empty, with_row = run_app(scenario, size=SIZE)
    assert with_row == "⏎ Open space Select esc Back r Refresh ? Keys + Add a All/none c Category"
    assert empty == "esc Back  r Refresh  ? Keys  + Add"


def test_an_empty_statements_account_list_shows_only_the_keys_that_work(monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(StatementsScreen())
        await wait_for_list(pilot, app)
        await pilot.pause()
        return _line(app)

    assert run_app(scenario, size=SIZE) == EMPTY_MANAGE


def test_statements_account_list_with_an_account_keeps_its_statements_key(monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([ACCOUNT]))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(StatementsScreen())
        await wait_for_list(pilot, app)
        await pilot.pause()
        return _line(app)

    footer = run_app(scenario, size=SIZE)
    assert footer == "⏎ Its statements  esc Back  r Refresh  ? Keys  n New"


@pytest.mark.parametrize("name", sorted(MANAGE))
def test_keys_pressed_on_an_empty_manage_list_do_nothing(monkeypatch, name):
    _serve(monkeypatch, name, [])
    sent: list = []
    monkeypatch.setattr("expense.http.ExpenseClient._request", lambda *a, **k: sent.append(a))

    async def scenario(pilot, app):
        screen = MANAGE[name][0]()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.pause()
        before = screen_lines(app)
        for key in ("enter", "e", "c", "x", "a", "t", "d"):
            await pilot.press(key)
        await pilot.pause()
        assert app.screen is screen
        return before, screen_lines(app)

    before, after = run_app(scenario, size=SIZE)
    assert before == after
    assert sent == []


def test_keys_pressed_on_an_empty_ledger_do_nothing(monkeypatch):
    _stub_ledger(monkeypatch)
    reads, counts = fake_ledger(monkeypatch, [])
    sent: list = []
    monkeypatch.setattr("expense.http.ExpenseClient._request", lambda *a, **k: sent.append(a))

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        screen.query_one(CursorList).focus()
        await pilot.pause()
        before, read = screen_lines(app), (len(reads), len(counts))
        for key in "enter space a c b h m s d up down pagedown pageup".split():
            await pilot.press(key)
        await pilot.pause()
        assert app.screen is screen
        return before, screen_lines(app), read, (len(reads), len(counts))

    before, after, read, read_after = run_app(scenario, size=SIZE)
    assert before == after
    assert read == read_after
    assert sent == []


def test_keys_pressed_on_an_empty_statements_account_list_do_nothing(monkeypatch):
    reads: list = []
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: reads.append(a) or whole([])
    )
    monkeypatch.setattr(
        "expense.reads.fetch_statements", lambda *a, **k: reads.append(a) or whole([])
    )
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    sent: list = []
    monkeypatch.setattr("expense.http.ExpenseClient._request", lambda *a, **k: sent.append(a))

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.pause()
        before, read = screen_lines(app), len(reads)
        for key in "enter space up down pagedown".split():
            await pilot.press(key)
        await pilot.pause()
        assert app.screen is screen
        return before, screen_lines(app), read, len(reads)

    before, after, read, read_after = run_app(scenario, size=SIZE)
    assert before == after
    assert read == read_after
    assert sent == []
