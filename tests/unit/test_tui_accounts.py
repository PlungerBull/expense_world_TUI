"""Smoke tests for the Accounts TUI screen + CursorList enhancements."""

from rich.text import Text

from expense.tui.screens.accounts import AccountsScreen, account_rows
from expense.tui.screens.create_forms import EditAccountScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_NAMES,
    in_order,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

ITEMS = [
    {
        "id": "a1",
        "name": "BCP Soles",
        "is_person": False,
        "is_archived": False,
        "currency_code": "PEN",
        "color": "#4a90d9",
        "current_balance_cents": 1245000,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "a2",
        "name": "Socio Juan",
        "is_person": True,
        "is_archived": False,
        "currency_code": "PEN",
        "color": None,
        "current_balance_cents": -150000,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "a3",
        "name": "Old BCP",
        "is_person": False,
        "is_archived": True,
        "currency_code": "PEN",
        "color": "#888888",
        "current_balance_cents": 0,
        "opening_balance_transaction_id": None,
    },
]


def test_account_rows_type_balance_status_and_swatch():
    by_id = {r[0]: r for r in account_rows(ITEMS)}
    # bank, formatted balance, active status, colored swatch Text
    _key, cells, style = by_id["a1"]
    assert cells[1] == "bank" and cells[4] == "12,450.00" and cells[5] == "active"
    assert isinstance(cells[3], Text) and cells[3].style == "#4a90d9"
    assert style == ""
    # person row
    assert by_id["a2"][1][1] == "person"
    # archived → dim base style + status archived
    _k, cells3, style3 = by_id["a3"]
    assert cells3[5] == "archived" and style3 == "dim"


def test_accounts_screen_lists_and_edits(monkeypatch):
    import expense.reads as ac

    monkeypatch.setattr(ac, "fetch_accounts", lambda *a, **k: whole(ITEMS))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        cl = app.screen.query(CursorList).first()
        assert cl is not None
        await pilot.press("e")  # edit the cursor row — no detail hop
        await wait_for(pilot, lambda: isinstance(app.screen, EditAccountScreen))

    run_app(scenario)


def test_accounts_screen_shows_the_engines_order(monkeypatch):
    """Rows stand exactly as `GET /accounts?include_people=true` lists them —
    not alphabetical, not by `sort_order`, the person after every bank."""
    import expense.reads as ac

    monkeypatch.setattr(ac, "fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_ACCOUNTS))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        cl = app.screen.query(CursorList).first()
        assert [row.key for row in cl._rows] == [a["id"] for a in ENGINE_ORDER_ACCOUNTS]
        shown = render_text(cl._build(), width=120)
        assert in_order(shown, ENGINE_ORDER_NAMES)

    run_app(scenario)
