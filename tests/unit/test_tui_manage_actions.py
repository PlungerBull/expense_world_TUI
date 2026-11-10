"""Manage list actions — `e` edit and `a` archive act on the cursor row.

The list is the only surface. `a` toggles archive/unarchive immediately — no ConfirmModal, a second
`a` undoes — and the cursor stays on the acted-on row across the reload.
`enter` is a no-op. Archive is Accounts-only.
"""

import pytest

from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.categories import CategoriesScreen
from expense.tui.screens.create_forms import EditAccountScreen, EditHashtagScreen
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    account_with_currencies,
    held_currency,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

ACCOUNT = account_with_currencies(
    id="a1", name="BCP", color="#4a90d9", currencies=[held_currency("PEN", -7495)]
)
ACCOUNT_2 = {**ACCOUNT, "id": "a2", "name": "Interbank", "color": None}
HASHTAG = {"id": "h1", "name": "trabajo"}


@pytest.mark.parametrize(
    ("archived", "verb", "status", "style"),
    [(False, "archive", "archived", "dim"), (True, "unarchive", "active", "")],
)
def test_a_on_a_two_currency_account_sends_one_call_and_redraws_the_whole_row(
    fake_client, monkeypatch, archived, verb, status, style
):
    """`a` on a two-currency account's one row sends one `POST /accounts/{id}/archive`
    (or `/unarchive` on an archived row) with the account's id, never one per currency
    (contract: POST /v1/accounts/{account_id}/archive, "Every currency at once"); the
    reload draws the row whole, dimmed or not, its Status turned and both currency
    columns still holding their balances, and the cursor is back on it."""
    visa = account_with_currencies(
        id="visa",
        name="Visa",
        is_archived=archived,
        currencies=[held_currency("PEN", 100), held_currency("USD", 5)],
    )
    served = [visa]
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(list(served)))
    seen: dict = {}

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        cursor_list = screen.query(CursorList).first()
        cursor_list.set_cursor(cursor_list.index_of("visa"))
        served[:] = [{**visa, "is_archived": not archived}]  # what the engine reads after
        await pilot.press("a")
        await wait_for(pilot, lambda: fake_client.calls)
        await wait_for(pilot, lambda: not screen._toggle_busy)
        cursor_list = screen.query(CursorList).first()
        seen["key"] = cursor_list.cursor_key
        seen["styles"] = [row.base_style for row in cursor_list._rows]
        seen["cells"] = [str(cell) for cell in cursor_list._rows[0].cells]

    run_app(scenario)
    assert [r for r in fake_client.requests if r[0] == "POST"] == [
        ("POST", f"/accounts/visa/{verb}")
    ]
    assert seen["key"] == "visa"
    assert seen["styles"] == [style]
    assert seen["cells"][4:] == ["1.00", "0.05", status]


def _edit_two_currency_account(fake_client, monkeypatch, key):
    visa = account_with_currencies(
        id="visa",
        name="Visa",
        currencies=[
            held_currency("PEN", 100, opening_balance_transaction_id="tx-pen"),
            held_currency("USD", 5, opening_balance_transaction_id="tx-usd"),
        ],
    )
    asked: list = []

    def fetch(cfg, transaction_id, **kw):
        asked.append(transaction_id)
        return {"amount_cents": 100, "date": "2026-01-01T00:00:00-05:00", "day": "2026-01-01"}

    monkeypatch.setattr("expense.reads.fetch_transaction", fetch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([visa]))
    seen: dict = dict(asked=asked)

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        cursor_list = screen.query(CursorList).first()
        cursor_list.set_cursor(cursor_list.index_of("visa"))
        await pilot.press("e")
        await wait_for(pilot, lambda: isinstance(app.screen, EditAccountScreen))
        await wait_for(pilot, lambda: not app.screen._openings_loading)
        seen["sequence"] = app.screen._sequence()
        seen["opening_ids"] = {c: o.id for c, o in app.screen._openings.items()}
        await pilot.press(key)
        await wait_for(pilot, lambda: app.screen is screen)
        await wait_for_list(pilot, app)
        await pilot.pause()
        seen["cursor"] = screen.query(CursorList).first().cursor_key

    run_app(scenario)
    return seen


def test_e_edits_the_account_with_every_currencys_pair_and_a_cancel_keeps_the_row(
    fake_client, monkeypatch
):
    """`e` on a two-currency account's one row opens the form on the account: a
    pair of opening lines per currency, as the engine lists them, each with its
    own opening balance."""
    seen = _edit_two_currency_account(fake_client, monkeypatch, "escape")
    assert "name" not in seen["sequence"] and seen["cursor"] == "visa"  # a bank account: no NAME
    assert fake_client.calls == []
    assert seen["sequence"][-4:] == ["opening:PEN", "as_of:PEN", "opening:USD", "as_of:USD"]
    assert seen["opening_ids"] == {"PEN": "tx-pen", "USD": "tx-usd"}
    assert seen["asked"] == ["tx-pen", "tx-usd"]


def test_e_on_a_two_currency_account_saves_it_by_its_id(fake_client, monkeypatch):
    _edit_two_currency_account(fake_client, monkeypatch, "ctrl+s")
    assert fake_client.puts == [("/accounts/visa", {})]


def test_archive_toggle_restores_cursor_across_pages(fake_client, monkeypatch):
    """25 accounts: act on row 22 — beyond the 20-row window.
    The reload must land the cursor back on that row, on its page."""
    accounts = [
        account_with_currencies(ACCOUNT, id=f"a{i}", name=f"Acct {i:02d}") for i in range(25)
    ]
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(accounts))

    async def scenario(pilot, app):
        # tall harness: rows-per-page adapt to the terminal;
        # 40 lines keeps the manage window at the 20-row cap, so a22 is page 2
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        cursor_list = screen.query(CursorList).first()
        cursor_list.set_cursor(cursor_list.index_of("a22"))
        await pilot.press("a")
        await wait_for(pilot, lambda: fake_client.calls)
        await wait_for(pilot, lambda: not screen._toggle_busy)  # reload landed
        cursor_list = screen.query(CursorList).first()
        assert cursor_list.cursor_key == "a22"
        assert cursor_list.page_status == "rows 21-25 of 25 · page 2 of 2"

    run_app(scenario, size=(120, 40))
    assert ("POST", "/accounts/a22/archive") in fake_client.requests


def test_hashtag_edit_puts(fake_client, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([HASHTAG]))

    async def scenario(pilot, app):
        await app.push_screen(HashtagsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("e")
        await wait_for(pilot, lambda: isinstance(app.screen, EditHashtagScreen))
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.calls)

    run_app(scenario)
    puts = dict(fake_client.puts)
    assert "/hashtags/h1" in puts
    assert puts["/hashtags/h1"]["name"] == "trabajo"


# ---- after an edit: a save starts the list over, a cancel keeps the row ---------------

_CATEGORY_ROWS = [
    {"id": "c1", "name": "COMIDA", "is_system": False, "color": "#4a90d9"},
    {"id": "c2", "name": "HOGAR", "is_system": False, "color": "#5ab87a"},
]
# list screen, its rows (served whole), the reads function it calls
_EDIT_LISTS = {
    "accounts": (AccountsScreen, [ACCOUNT, ACCOUNT_2], "fetch_accounts"),
    "categories": (CategoriesScreen, _CATEGORY_ROWS, "fetch_categories"),
    "hashtags": (HashtagsScreen, [HASHTAG, {"id": "h2", "name": "viaje"}], "fetch_hashtags"),
}


def _edit_second_row(fake_client, monkeypatch, which, key):
    make, rows, fetch = _EDIT_LISTS[which]
    monkeypatch.setattr(f"expense.reads.{fetch}", lambda *a, **k: whole(rows))
    seen: dict = {}

    async def scenario(pilot, app):
        screen = make()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("down")  # cursor → row 2
        await pilot.press("e")
        await wait_for(pilot, lambda: app.screen is not screen)
        await pilot.press(key)
        await wait_for(pilot, lambda: app.screen is screen)
        await wait_for_list(pilot, app)
        await pilot.pause()
        seen["cursor"] = screen.query(CursorList).first().cursor_key

    run_app(scenario)
    return seen["cursor"], rows


@pytest.mark.parametrize("which", list(_EDIT_LISTS))
def test_a_saved_edit_reloads_the_list_from_row_1(fake_client, monkeypatch, which):
    cursor, rows = _edit_second_row(fake_client, monkeypatch, which, "ctrl+s")
    assert fake_client.puts  # the save wrote
    assert cursor == rows[0]["id"]


@pytest.mark.parametrize("which", list(_EDIT_LISTS))
def test_a_cancelled_edit_keeps_the_row(fake_client, monkeypatch, which):
    cursor, rows = _edit_second_row(fake_client, monkeypatch, which, "escape")
    assert fake_client.calls == []
    assert cursor == rows[1]["id"]
