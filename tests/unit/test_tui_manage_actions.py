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
from expense.tui.screens.modals import ConfirmModal
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
ARCHIVED_ACCOUNT = {**ACCOUNT, "is_archived": True}
CATEGORY = {"id": "c1", "name": "COMIDA", "is_system": False, "color": None}
HASHTAG = {"id": "h1", "name": "trabajo"}


def test_archive_is_immediate_no_modal(fake_client, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([ACCOUNT]))

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("a")  # straight to the write — no ConfirmModal
        assert not isinstance(app.screen, ConfirmModal)
        await wait_for(pilot, lambda: fake_client.calls)

    run_app(scenario)
    assert ("POST", "/accounts/a1/archive") in fake_client.requests


def test_archive_on_either_row_of_a_two_currency_account_sends_one_call_and_dims_both(
    fake_client, monkeypatch
):
    """`a` on the dollars row sends one `POST /accounts/{id}/archive` with the account's
    id, never one per currency; the reload dims both rows and the cursor is back on the
    dollars row."""
    visa = account_with_currencies(
        id="visa", name="Visa", currencies=[held_currency("PEN", 100), held_currency("USD", 5)]
    )
    served = [visa]
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(list(served)))

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        cursor_list = screen.query(CursorList).first()
        cursor_list.set_cursor(cursor_list.index_of(("visa", "USD")))
        served[:] = [{**visa, "is_archived": True}]  # what the engine reads after the write
        await pilot.press("a")
        await wait_for(pilot, lambda: fake_client.calls)
        await wait_for(pilot, lambda: not screen._toggle_busy)
        cursor_list = screen.query(CursorList).first()
        assert cursor_list.cursor_key == ("visa", "USD")
        assert [row.base_style for row in cursor_list._rows] == ["dim", "dim"]

    run_app(scenario)
    assert [r for r in fake_client.requests if r[0] == "POST"] == [
        ("POST", "/accounts/visa/archive")
    ]


def _edit_two_currency_account(fake_client, monkeypatch, key, row="USD"):
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
        return {"amount_cents": 100, "date": "2026-01-01T00:00:00-05:00"}

    monkeypatch.setattr("expense.reads.fetch_transaction", fetch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([visa]))
    seen: dict = {"asked": asked}

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        cursor_list = screen.query(CursorList).first()
        cursor_list.set_cursor(cursor_list.index_of(("visa", row)))
        await pilot.press("e")
        await wait_for(pilot, lambda: isinstance(app.screen, EditAccountScreen))
        await wait_for(pilot, lambda: not app.screen._opening_loading)
        seen["name"] = app.screen._values["name"]
        seen["currency"] = app.screen._values["currency"]
        seen["opening_id"] = app.screen._opening_id
        await pilot.press(key)
        await wait_for(pilot, lambda: app.screen is screen)
        await wait_for_list(pilot, app)
        await pilot.pause()
        seen["cursor"] = screen.query(CursorList).first().cursor_key

    run_app(scenario)
    return seen


def test_e_on_the_dollars_row_edits_the_account_and_a_cancel_keeps_the_row(
    fake_client, monkeypatch
):
    seen = _edit_two_currency_account(fake_client, monkeypatch, "escape")
    assert seen["name"] == "Visa" and seen["cursor"] == ("visa", "USD")
    assert fake_client.calls == []
    # the form opened on the dollars row: its currency and its own opening balance
    assert seen["currency"] == "USD" and seen["opening_id"] == "tx-usd"
    assert seen["asked"] == ["tx-usd"]


def test_e_on_the_soles_row_opens_the_form_on_soles(fake_client, monkeypatch):
    seen = _edit_two_currency_account(fake_client, monkeypatch, "escape", row="PEN")
    assert seen["cursor"] == ("visa", "PEN")
    assert seen["currency"] == "PEN" and seen["opening_id"] == "tx-pen"
    assert seen["asked"] == ["tx-pen"]


def test_e_on_the_dollars_row_saves_the_account_by_its_id(fake_client, monkeypatch):
    _edit_two_currency_account(fake_client, monkeypatch, "ctrl+s")
    assert "/accounts/visa" in dict(fake_client.puts)


def test_unarchive_is_direct(fake_client, monkeypatch):
    """`a` on an archived row unarchives — same key, opposite verb, no prompt."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([ARCHIVED_ACCOUNT]))

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("a")
        assert not isinstance(app.screen, ConfirmModal)
        await wait_for(pilot, lambda: fake_client.calls)

    run_app(scenario)
    assert ("POST", "/accounts/a1/unarchive") in fake_client.requests


def test_archive_toggle_keeps_cursor_on_row(fake_client, monkeypatch):
    """The reload after a toggle re-selects the acted-on row (fresh CursorList
    would otherwise snap to row 0, so a second `a` would hit the wrong record)."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([ACCOUNT, ACCOUNT_2]))

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("down")  # cursor → a2
        await pilot.press("a")
        await wait_for(pilot, lambda: fake_client.calls)
        await wait_for(pilot, lambda: not screen._toggle_busy)  # reload landed
        cursor_list = screen.query(CursorList).first()
        assert cursor_list.cursor_key == ("a2", "PEN")

    run_app(scenario)
    assert ("POST", "/accounts/a2/archive") in fake_client.requests


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
        cursor_list.set_cursor(cursor_list.index_of(("a22", "PEN")))
        await pilot.press("a")
        await wait_for(pilot, lambda: fake_client.calls)
        await wait_for(pilot, lambda: not screen._toggle_busy)  # reload landed
        cursor_list = screen.query(CursorList).first()
        assert cursor_list.cursor_key == ("a22", "PEN")
        assert cursor_list.page_status == "rows 21-25 of 25 · page 2 of 2"

    run_app(scenario, size=(120, 40))
    assert ("POST", "/accounts/a22/archive") in fake_client.requests


def test_edit_prefills_and_puts(fake_client, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([ACCOUNT]))

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("e")  # → prefilled EditAccountScreen
        await wait_for(pilot, lambda: isinstance(app.screen, EditAccountScreen))
        await pilot.press("ctrl+s")  # save unchanged → PUT
        await wait_for(pilot, lambda: fake_client.calls)

    run_app(scenario)
    puts = dict(fake_client.puts)
    assert "/accounts/a1" in puts
    assert puts["/accounts/a1"]["name"] == "BCP"  # prefilled name round-trips
    assert "currency_code" not in puts["/accounts/a1"]  # currency is immutable


def test_categories_have_no_archive_action(fake_client, monkeypatch):
    """Categories have no archive: the `a`
    binding lives on AccountsScreen only, so on Categories it is inert."""
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole([CATEGORY]))

    async def scenario(pilot, app):
        screen = CategoriesScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert not hasattr(screen, "action_archive")
        assert screen.check_action("edit", ()) is True  # edit still offered
        await pilot.press("a")  # inert — no confirm, no write
        await pilot.pause()  # let the (inert) keypress settle, then assert a non-event
        assert not isinstance(app.screen, ConfirmModal)
        assert not fake_client.calls

    run_app(scenario)


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


def test_enter_is_a_noop(fake_client, monkeypatch):
    """The record detail is gone: `enter` opens nothing, mutates nothing."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([ACCOUNT]))

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("enter")
        await pilot.pause()  # let the (inert) keypress settle, then assert a non-event
        assert app.screen is screen  # nothing pushed
        assert not fake_client.calls  # nothing written

    run_app(scenario)


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


def _row_key(which, row):
    """The key of a list row: an account's rows are keyed by account and currency."""
    return (row["id"], "PEN") if which == "accounts" else row["id"]


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
    assert cursor == _row_key(which, rows[0])


@pytest.mark.parametrize("which", list(_EDIT_LISTS))
def test_a_cancelled_edit_keeps_the_row(fake_client, monkeypatch, which):
    cursor, rows = _edit_second_row(fake_client, monkeypatch, which, "escape")
    assert fake_client.calls == []
    assert cursor == _row_key(which, rows[1])
