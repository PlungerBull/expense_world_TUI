"""The Manage forms finish after they have been left (`left_behind`).

New and Edit for hashtags and categories, and New account. Saved with the engine still
answering, the form is left (esc); the answer then ends as a toast on the app (the form's
own success words, or its refusal under a first line naming what was not done, ending,
only under a status below 500, `Nothing was saved: open it again to fix it.`), and the list the
form belongs to, when it is the screen shown, reads again from its first page. The queue
itself is in test_tui_writes.py.
"""

import pytest
from textual.widgets import Input

from expense.errors import EngineConnectionError, EngineError, format_error
from expense.tui.screens._form import may_have_landed
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.categories import CategoriesScreen
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    LateAnswer,
    app_notes,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

REFUSAL = EngineError("CONFLICT", "stand-in [not markup]", None, 409, {})
LAST = "Nothing was saved: open it again to fix it."

HASHTAGS = [
    {"id": "h-1", "name": "primero", "system_key": None},
    {"id": "h-2", "name": "viaje", "system_key": None},
]
CATEGORIES = [
    {"id": "c-1", "name": "AAA", "is_system": False, "color": "#4a90d9"},
    {"id": "c-2", "name": "COMIDA", "is_system": False, "color": "#4a90d9"},
]
ACCOUNTS = [
    {
        "id": "a-1",
        "name": "Caja",
        "kind": "bank",
        "is_archived": False,
        "currencies": [{"currency_code": "PEN"}],
    },
]

# site: (list screen, rows, fetch, key opening the form, the row the cursor goes to,
#        what is typed, verb, success words, first line)
SITES = {
    "new hashtag": (
        HashtagsScreen, HASHTAGS, "fetch_hashtags", "n", None, ["#nuevo"],
        "post", "Hashtag created.", "Not created · Hashtag #nuevo",
    ),
    "new category": (
        CategoriesScreen, CATEGORIES, "fetch_categories", "n", None, ["Ropa", ""],
        "post", "Category created.", "Not created · Category Ropa",
    ),
    "new account": (
        AccountsScreen, ACCOUNTS, "fetch_accounts", "n", None,
        ["", "BCP", "5678", "PEN", "", "", "", "", ""],
        "post", "Account created.", "Not created · Account (unnamed)",
    ),
    "new cash account": (
        AccountsScreen, ACCOUNTS, "fetch_accounts", "n", None,
        ["cash", "PEN", "", "", "", ""],
        "post", "Account created.", "Not created · Account Efectivo",
    ),
    "new person": (
        AccountsScreen, ACCOUNTS, "fetch_accounts", "n", None,
        ["person", "Eli", "PEN", "", "", "", ""],
        "post", "Person created.", "Not created · Person Eli",
    ),
    "edit hashtag": (
        HashtagsScreen, HASHTAGS, "fetch_hashtags", "e", "h-2", ["otro"],
        "put", "Saved.", "Not saved · Hashtag #viaje",
    ),
    "edit category": (
        CategoriesScreen, CATEGORIES, "fetch_categories", "e", "c-2", ["Otra", ""],
        "put", "Saved.", "Not saved · Category COMIDA",
    ),
}  # fmt: skip


def _left_form(fake_client, monkeypatch, site: str, refusal: Exception | None) -> tuple:
    """Open `site`'s form from its list, type it, leave the form before the engine
    answers, let it answer, and return `(the app's toasts, the list's reads, the cursor
    key of the list as it ends)`."""
    make, rows, fetch, key, row, typed, verb, *_ = SITES[site]
    reads: list[int] = []

    def fetch_rows(*a, **k):
        reads.append(1)
        return whole(list(rows))

    monkeypatch.setattr(f"expense.reads.{fetch}", fetch_rows)
    late = LateAnswer(fake_client, verb, refusal)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        listing_screen = make()
        await app.push_screen(listing_screen)
        await wait_for_list(pilot, app)
        listing = listing_screen.query_one(CursorList)
        if row is not None:
            listing.set_cursor(listing.index_of(row))
        await pilot.press(key)
        form = app.screen
        assert form is not listing_screen
        await wait_for(pilot, lambda: bool(form.query("#bar")))
        for text in typed:
            form.query_one("#bar", Input).value = text
            form._recompute(text)
            form.on_input_submitted(None)
        await wait_for(pilot, late.started.is_set)
        await app.pop_screen()  # the form is left: popped, so its dismiss callback never runs
        await wait_for(pilot, lambda: app.screen is listing_screen)
        await wait_for_list(pilot, app)
        reads_before = len(reads)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.pause()
        if refusal is None or may_have_landed(refusal):
            await wait_for(pilot, lambda: len(reads) > reads_before, timeout=3)
            await wait_for_list(pilot, app)
        else:
            assert len(reads) == reads_before  # a clear refusal changed nothing: nothing is read
        result.extend([notes, len(reads) - reads_before, listing_screen.query_one(CursorList)])
        result[2] = result[2].cursor_key

    run_app(scenario, size=(120, 40))
    return tuple(result)


@pytest.mark.parametrize("site", sorted(SITES))
def test_a_form_saved_after_leaving_shows_its_message_and_the_list_starts_over(
    fake_client, monkeypatch, site
):
    notes, new_reads, cursor_key = _left_form(fake_client, monkeypatch, site, None)
    assert [(title, message) for title, message, _ in notes] == [("", SITES[site][7])]
    assert new_reads == 1
    assert cursor_key == SITES[site][1][0]["id"]  # row 1


@pytest.mark.parametrize("site", sorted(SITES))
def test_a_form_refused_after_leaving_names_what_was_not_done_and_ends_with_the_way_back(
    fake_client, monkeypatch, site
):
    notes, new_reads, _ = _left_form(fake_client, monkeypatch, site, REFUSAL)
    [(title, message, options)] = notes
    assert title == SITES[site][8]
    # the engine's words whole, `[not markup]` and all, then the app's last line, dim
    assert message == f"{format_error(REFUSAL).replace('[', chr(92) + '[')}\n[dim]{LAST}"
    assert "stand-in \\[not markup]" in message
    assert options["severity"] == "error"
    assert options["timeout"] == 10
    assert options["markup"] is True
    assert new_reads == 0


SERVER_ERROR = EngineError("INTERNAL_ERROR", "Went wrong [on our side].", None, 500, {})
NO_ANSWER = EngineConnectionError(url="https://x.invalid", original=Exception("refused"))


@pytest.mark.parametrize("failure", [SERVER_ERROR, NO_ANSWER], ids=["5xx", "no answer"])
@pytest.mark.parametrize("site", sorted(SITES))
def test_a_form_whose_ending_is_not_known_ends_with_the_engines_words_only_and_the_list_starts_over(
    fake_client, monkeypatch, site, failure
):
    notes, new_reads, cursor_key = _left_form(fake_client, monkeypatch, site, failure)
    [(title, message, options)] = notes
    assert title == SITES[site][8]
    assert "open it again" not in message
    assert message == format_error(failure)  # as sent, no markup
    assert options["markup"] is False
    assert options["severity"] == "error"
    assert new_reads == 1  # it may have landed: the list reads again, as after a save
    assert cursor_key == SITES[site][1][0]["id"]  # row 1


def test_a_form_saved_after_leaving_for_another_screen_reads_nothing_more(fake_client, monkeypatch):
    """Left for some other screen than its list: the message shows and nothing else happens."""
    reads: list[int] = []

    def fetch_rows(*a, **k):
        reads.append(1)
        return whole(list(HASHTAGS))

    monkeypatch.setattr("expense.reads.fetch_hashtags", fetch_rows)
    late = LateAnswer(fake_client, "post", None)

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        listing_screen = HashtagsScreen()
        await app.push_screen(listing_screen)
        await wait_for_list(pilot, app)
        await pilot.press("n")
        form = app.screen
        await wait_for(pilot, lambda: bool(form.query("#bar")))
        form.query_one("#bar", Input).value = "nuevo"
        form._recompute("nuevo")
        form.on_input_submitted(None)
        await wait_for(pilot, late.started.is_set)
        await app.pop_screen()
        await wait_for_list(pilot, app)
        await app.push_screen(CategoriesScreen())  # elsewhere than the hashtags list
        await wait_for(pilot, lambda: isinstance(app.screen, CategoriesScreen))
        before = len(reads)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.pause()
        assert [message for _, message, _ in notes] == ["Hashtag created."]
        assert len(reads) == before

    run_app(scenario, size=(120, 40))


def test_the_real_esc_leaves_a_saving_form_and_its_late_answer_still_shows(
    fake_client, monkeypatch
):
    """`esc` pressed on the form (not the screen popped) while its save is unanswered."""
    reads: list[int] = []

    def fetch_rows(*a, **k):
        reads.append(1)
        return whole(list(HASHTAGS))

    monkeypatch.setattr("expense.reads.fetch_hashtags", fetch_rows)
    late = LateAnswer(fake_client, "post", None)

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        listing_screen = HashtagsScreen()
        await app.push_screen(listing_screen)
        await wait_for_list(pilot, app)
        await pilot.press("n")
        form = app.screen
        await wait_for(pilot, lambda: bool(form.query("#bar")))
        form.query_one("#bar", Input).value = "nuevo"
        form._recompute("nuevo")
        form.on_input_submitted(None)
        await wait_for(pilot, late.started.is_set)
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is listing_screen)
        await wait_for_list(pilot, app)
        before = len(reads)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await wait_for(pilot, lambda: len(reads) > before, timeout=3)
        await wait_for_list(pilot, app)
        assert [(title, message) for title, message, _ in notes] == [("", "Hashtag created.")]
        assert listing_screen.query_one(CursorList).cursor_key == HASHTAGS[0]["id"]

    run_app(scenario, size=(120, 40))
