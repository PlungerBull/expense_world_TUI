"""Smoke tests for the `expense world` TUI.

Drives Textual headlessly through `helpers.run_app` — one shared harness for
the whole suite, and still no pytest-asyncio dependency. Network is never
touched: the nav test stubs `fetch_dashboard`.
"""

from textual.widgets import OptionList, Static

from expense import reads
from expense.tui.screens.home import HomeScreen
from tests.unit.helpers import run_app, stub_home_month, wait_for

SAMPLE = {
    "month": {"year": 2026, "month": 3},
    "bank_accounts": [
        {"name": "BCP Soles", "currency_code": "PEN", "current_balance_cents": 1245000}
    ],
    "people": [{"name": "Socio Juan", "currency_code": "PEN", "current_balance_cents": -150000}],
    # Aggregates are home-currency only, each nullable with an
    # `unconverted_count`. `Vacío` spent nothing and must not be drawn.
    "categories": [
        {
            "name": "Comida",
            "spent_home_cents": -43250,
            "unconverted_count": 0,
            "hashtag_breakdown": [
                {"hashtag_ids": ["x"], "spent_home_cents": -25000, "unconverted_count": 0}
            ],
        },
        {
            "name": "Vivienda",
            "spent_home_cents": -250000,
            "unconverted_count": 0,
            "hashtag_breakdown": [],
        },
        {"name": "Vacío", "spent_home_cents": 0, "unconverted_count": 0, "hashtag_breakdown": []},
    ],
    "totals": {
        "inflow_home_cents": 651900,
        "outflow_home_cents": -385650,
        "net_home_cents": 266250,
        "unconverted_count": 0,
    },
}


def test_app_launches_home_with_every_screen_listed():
    async def scenario(pilot, app):
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)
        option_list = app.query_one(OptionList)
        ids = [
            option_list.get_option_at_index(i).id
            for i in range(option_list.option_count)
            if option_list.get_option_at_index(i).id
        ]
        # every screen is a row before any fetch lands, never folded
        assert ids == [
            "transactions",
            "reconciliations",
            "accounts",
            "categories",
            "hashtags",
            "config",
            "auth",
        ]
        # the old outstanding and report rows are not separate rows —
        # asserted negatively so a reflex re-add fails here, loudly
        assert "outstanding" not in ids
        assert "report" not in ids

    run_app(scenario)


def test_home_month_populates_from_worker(monkeypatch):
    """Drive the real on-mount worker: the dashboard and range reads → _set_data
    → the header carries the month and the menu the live rows."""
    stub_home_month(monkeypatch)

    async def scenario(pilot, app):
        await pilot.pause()
        home = app.screen
        assert home.query_one("#brand", Static) is not None  # header up from first paint
        await wait_for(pilot, lambda: home._data is not None)
        await pilot.pause()
        option_list = app.query_one(OptionList)
        ids = [
            option_list.get_option_at_index(i).id
            for i in range(option_list.option_count)
            if option_list.get_option_at_index(i).id
        ]
        assert ids[:2] == ["category:c-pend", "category:c-wants"]
        assert "category:c-hogar" not in ids  # nothing in the window: hidden
        assert "account:a-pen" in ids and "account:a-usd" in ids
        assert ids[-7:] == [
            "transactions",
            "reconciliations",
            "accounts",
            "categories",
            "hashtags",
            "config",
            "auth",
        ]
        assert home._cursor_id() == "category:c-pend"  # the first month lands the cursor

    run_app(scenario)


def test_home_says_so_when_the_month_cannot_load(monkeypatch):
    """Offline / unconfigured / engine-down: the screens stay, and one dim row
    carries the reason, never a silent blank."""

    def boom(*a, **k):
        raise RuntimeError("Connection refused")

    monkeypatch.setattr(reads, "fetch_dashboard", boom)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        home = app.screen
        await wait_for(pilot, lambda: home._error is not None)
        await pilot.pause()
        option_list = app.query_one(OptionList)
        first = option_list.get_option_at_index(0)
        assert first.disabled and "Connection refused" in first.prompt.plain
        assert option_list.get_option_index("transactions") is not None

    run_app(scenario)
