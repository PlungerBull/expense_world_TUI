"""The list actions finish after their screen has left (`left_behind`).

Manage ▸ Accounts' `a`, `t`, `c`, `x` and `d`, `d` on Categories and Hashtags, and
Auth's bootstrap each carry the first line of their refusal. Left with the engine
still answering, a write ends as a toast on the app: the screen's own success
words, or its own refusal words under the left-behind line for 10 seconds.
The "no statement" list's and the flagged lines' `d` are in test_tui_statements.py
and test_tui_flagged_lines.py. The ledger's `d` is in test_tui_delete.py; the queue
itself in test_tui_writes.py.
"""

import pytest

from expense.errors import EngineError, format_error
from expense.tui.screens._base import list_refusal_text
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.categories import CategoriesScreen
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.screens.modals import ConfirmModal, PickModal
from expense.tui.screens.system import AuthScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    LateAnswer,
    account_with_currencies,
    app_notes,
    held_currency,
    leave_then_answer,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

REFUSAL = EngineError("CONFLICT", "stand-in [not markup]", None, 409, {})

ACCOUNTS = [
    account_with_currencies(id="a-caja", name="Caja Chica", currencies=[held_currency("PEN")]),
    account_with_currencies(
        id="a-ana", name="Ana Ejemplo", is_person=True, currencies=[held_currency("PEN")]
    ),
    account_with_currencies(
        id="a-viejo", name="Ahorro Viejo", is_archived=True, currencies=[held_currency("PEN")]
    ),
]
CATEGORIES = [{"id": "c-1", "name": "COMIDA", "is_system": False, "color": None}]
HASHTAGS = [{"id": "h-1", "name": "viaje", "system_key": None}]

ADD = [("c", PickModal), ("enter", None)]
REMOVE = [("x", PickModal), ("enter", ConfirmModal), ("y", None)]
DELETE = [("d", ConfirmModal), ("y", None)]

# (screen, rows read, the row the cursor goes to, keys, verb, success words, first line,
#  the refusal words' function)
SITES = {
    "archive account": (
        AccountsScreen, ACCOUNTS, "a-caja", [("a", None)], "post",
        "Archived.", "Not archived · Account Caja Chica", list_refusal_text,
    ),
    "unarchive account": (
        AccountsScreen, ACCOUNTS, "a-viejo", [("a", None)], "post",
        "Unarchived.", "Not unarchived · Account Ahorro Viejo", list_refusal_text,
    ),
    "make person": (
        AccountsScreen, ACCOUNTS, "a-caja", [("t", None)], "post",
        "Now a person.", "Not made a person · Account Caja Chica", list_refusal_text,
    ),
    "make bank": (
        AccountsScreen, ACCOUNTS, "a-ana", [("t", None)], "post",
        "Now a bank account.", "Not made a bank account · Person Ana Ejemplo", list_refusal_text,
    ),
    "add currency": (
        AccountsScreen, ACCOUNTS, "a-caja", ADD, "post",
        "Currency added: USD.", "Not added · USD on Caja Chica", list_refusal_text,
    ),
    "remove currency": (
        AccountsScreen, ACCOUNTS, "a-caja", REMOVE, "delete",
        "Currency removed: PEN.", "Not removed · PEN on Caja Chica", list_refusal_text,
    ),
    "delete account": (
        AccountsScreen, ACCOUNTS, "a-caja", DELETE, "delete",
        "Account deleted.", "Not deleted · Account Caja Chica", list_refusal_text,
    ),
    "delete person": (
        AccountsScreen, ACCOUNTS, "a-ana", DELETE, "delete",
        "Account deleted.", "Not deleted · Person Ana Ejemplo", list_refusal_text,
    ),
    "delete category": (
        CategoriesScreen, CATEGORIES, "c-1", DELETE, "delete",
        "Category deleted.", "Not deleted · Category COMIDA", list_refusal_text,
    ),
    "delete hashtag": (
        HashtagsScreen, HASHTAGS, "h-1", DELETE, "delete",
        "Hashtag deleted.", "Not deleted · Hashtag #viaje", list_refusal_text,
    ),
}  # fmt: skip

FETCH = {
    AccountsScreen: "fetch_accounts",
    CategoriesScreen: "fetch_categories",
    HashtagsScreen: "fetch_hashtags",
}


def _left_list(fake_client, monkeypatch, site: str, refusal: Exception | None) -> tuple:
    """Run `site`'s keys on its list, leave the list before the engine answers, and
    return `(the app's toasts, the site's row of SITES)`."""
    make, rows, key, keys, verb, *_ = SITES[site]
    monkeypatch.setattr(f"expense.reads.{FETCH[make]}", lambda *a, **k: whole(list(rows)))
    late = LateAnswer(fake_client, verb, refusal)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = make()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        listing = screen.query_one(CursorList)
        listing.set_cursor(listing.index_of(key))
        screen.refresh_bindings()
        await pilot.pause()
        for pressed, modal in keys:
            await pilot.press(pressed)
            if modal is not None:
                await wait_for(pilot, lambda m=modal: isinstance(app.screen, m))
        await leave_then_answer(pilot, app, screen, late, notes)
        result.extend(notes)

    run_app(scenario, size=(120, 40))
    return result, SITES[site]


@pytest.mark.parametrize("site", sorted(SITES))
def test_a_list_action_answered_after_leaving_shows_its_success_words(
    fake_client, monkeypatch, site
):
    notes, (*_, success, _first_line, _text) = _left_list(fake_client, monkeypatch, site, None)
    assert [(title, message) for title, message, _ in notes] == [("", success)]


@pytest.mark.parametrize("site", sorted(SITES))
def test_a_list_action_refused_after_leaving_names_what_did_not_happen(
    fake_client, monkeypatch, site
):
    notes, (*_, _success, first_line, text) = _left_list(fake_client, monkeypatch, site, REFUSAL)
    [(title, message, options)] = notes
    assert title == first_line
    assert message == text(REFUSAL)
    assert message.startswith("CONFLICT — stand-in [not markup]")
    assert options["severity"] == "error"
    assert options["timeout"] == 10
    assert options["markup"] is False


def test_a_list_action_with_the_list_open_still_toasts_failed(fake_client, monkeypatch):
    """Not left: the refusal keeps its own title, `Failed`, and the left-behind line is unused."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(list(ACCOUNTS)))
    LateAnswer(fake_client, "post", REFUSAL).release.set()

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("a")
        await wait_for(pilot, lambda: notes, timeout=3)
        assert [(title, message) for title, message, _ in notes] == [
            ("Failed", list_refusal_text(REFUSAL))
        ]

    run_app(scenario, size=(120, 40))


# ---- Auth's bootstrap ---------------------------------------------------------


def _left_bootstrap(fake_client, monkeypatch, refusal: Exception | None) -> list:
    fake_client.get_responses.pop("/auth/me", None)  # 404: not provisioned
    monkeypatch.setattr("expense.dates.detect_timezone", lambda *a, **k: "America/Lima")
    monkeypatch.setattr("expense.config.save", lambda c: None)
    late = LateAnswer(fake_client, "post", refusal)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = AuthScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(app.screen.query(".legend")))
        screen.action_bootstrap()
        await wait_for(pilot, lambda: bool(app.screen.query("#prompt")))
        app.screen.query_one("#prompt").value = "Alex"
        await pilot.press("enter")
        await leave_then_answer(pilot, app, screen, late, notes)
        result.extend(notes)

    run_app(scenario)
    return result


def test_a_bootstrap_answered_after_leaving_says_it_provisioned(fake_client, monkeypatch):
    notes = _left_bootstrap(fake_client, monkeypatch, None)
    assert [(title, message) for title, message, _ in notes] == [("", "Provisioned.")]


def test_a_bootstrap_refused_after_leaving_says_not_provisioned(fake_client, monkeypatch):
    [(title, message, options)] = _left_bootstrap(fake_client, monkeypatch, REFUSAL)
    assert title == "Not provisioned"
    assert message == format_error(REFUSAL)
    assert options["severity"] == "error"
    assert options["timeout"] == 10
    assert options["markup"] is False
