"""Smoke tests for the `expense world` TUI.

Drives Textual headlessly via `App.run_test()` wrapped in `asyncio.run` (no
pytest-asyncio dependency). Network is never touched — the nav test stubs
`fetch_dashboard`.

The render-helper and fold tests that used to live here moved to
`test_tui_overview.py` with the 2026-08-29 merge; the ones for `CategoriesView`
went away with the widget, whose job the month grid's newest column already did.
"""

import asyncio

from textual.widgets import OptionList, Static

from expense.commands import dashboard_cmd
from expense.tui.app import ExpenseApp
from expense.tui.screens.home import HomeScreen
from tests.unit.helpers import wait_for

SAMPLE = {
    "month": {"year": 2026, "month": 3},
    "bank_accounts": [
        {"name": "BCP Soles", "currency_code": "PEN", "current_balance_cents": 1245000}
    ],
    "people": [{"name": "Socio Juan", "currency_code": "PEN", "current_balance_cents": -150000}],
    # Aggregates are home-currency only since 2026-08-05, each nullable with an
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


SAMPLE_WITH_IDS = {
    **SAMPLE,
    "bank_accounts": [{"id": "a1", **SAMPLE["bank_accounts"][0]}],
    "people": [{"id": "p1", **SAMPLE["people"][0]}],
    "categories": [{"id": f"c{i}", **cat} for i, cat in enumerate(SAMPLE["categories"], start=1)],
}


def test_app_launches_home_with_the_three_doors():
    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            option_list = app.query_one(OptionList)
            ids = [
                option_list.get_option_at_index(i).id
                for i in range(option_list.option_count)
                if option_list.get_option_at_index(i).id
            ]
            # the doors are there before any fetch lands (2026-09-12)
            assert ids == ["door:ledger", "door:manage", "door:system"]
            # both halves of the 2026-08-29 merge are gone as separate rows —
            # asserted negatively so a reflex re-add fails here, loudly
            assert "outstanding" not in ids
            assert "report" not in ids

    asyncio.run(scenario())


def test_home_month_populates_from_worker(monkeypatch):
    """Drive the real on-mount worker path end-to-end: fetch → _set_body →
    the header carries the month and the menu the live rows. The header
    Static exists from first paint; the rows arrive once the worker returns.
    (Rendering of the rows is covered in test_tui_home_header.py.)"""
    monkeypatch.setattr(dashboard_cmd, "fetch_dashboard", lambda *a, **k: SAMPLE_WITH_IDS)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            home = app.screen
            assert home.query_one("#brand", Static) is not None  # header up from first paint
            await wait_for(pilot, lambda: home._body is not None)
            await pilot.pause()
            option_list = app.query_one(OptionList)
            ids = [
                option_list.get_option_at_index(i).id
                for i in range(option_list.option_count)
                if option_list.get_option_at_index(i).id
            ]
            assert ids[:3] == ["category:c1", "category:c2", "category:c3"]
            assert "account:a1" in ids and "account:p1" in ids
            assert ids[-3:] == ["door:ledger", "door:manage", "door:system"]

    asyncio.run(scenario())


def test_home_says_so_when_the_month_cannot_load(monkeypatch):
    """Offline / unconfigured / engine-down: the doors stay, and one dim row
    carries the reason — failure was silent until 2026-09-12, when the numbers
    became the page."""

    def boom(*a, **k):
        raise RuntimeError("Connection refused")

    monkeypatch.setattr(dashboard_cmd, "fetch_dashboard", boom)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario():
        app = ExpenseApp()
        async with app.run_test() as pilot:
            home = app.screen
            await wait_for(pilot, lambda: home._error is not None)
            await pilot.pause()
            option_list = app.query_one(OptionList)
            first = option_list.get_option_at_index(0)
            assert first.disabled and "Connection refused" in first.prompt.plain
            assert option_list.get_option_index("door:ledger") is not None

    asyncio.run(scenario())
