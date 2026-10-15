"""Create-form tests (new hashtag / category / account, fake client)."""

import pytest
from textual.widgets import Input, Static

from expense.errors import EngineError
from expense.tui.screens.create_forms import (
    EditAccountScreen,
    NewAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from tests.unit.helpers import run_app, wait_for


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


def _run(fake_client, screen, steps):
    async def scenario(pilot, app):
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in steps:
            _enter(screen, text)
        await wait_for(pilot, lambda: fake_client.posts)
        return fake_client.posts[0]

    return run_app(scenario)


def test_new_hashtag_posts_name(fake_client):
    path, body = _run(fake_client, NewHashtagScreen(), ["#groceries"])  # last field → submits
    assert path == "/hashtags"
    assert body["name"] == "groceries" and "id" in body  # leading # stripped


def test_new_category_requires_color_then_posts(fake_client):
    # name, then pick a color (type 'green' → matches the palette)
    path, body = _run(fake_client, NewCategoryScreen(), ["Educación", "green"])
    assert path == "/categories"
    assert body["name"] == "Educación" and body["color"] == "#5ab87a"


def test_new_account_defaults_to_bank_on_empty_type(fake_client):
    """Empty enter on TYPE keeps `bank` — adding an account costs no extra decision."""
    # type (empty → the prefilled bank), name, currency PEN, skip color
    path, body = _run(fake_client, NewAccountScreen(), ["", "Interbank Sueldo", "PEN", ""])
    assert path == "/accounts"
    assert body["name"] == "Interbank Sueldo" and body["currency_code"] == "PEN"
    assert "color" not in body
    # `is_person` is a 422 on both routes — the endpoint is the flag, never a field.
    assert "is_person" not in body


def test_new_account_type_person_posts_to_people(fake_client):
    """Picking `person` routes the same fields to POST /people."""
    path, body = _run(fake_client, NewAccountScreen(), ["person", "Eliana", "PEN", ""])
    assert path == "/people"
    assert body["name"] == "Eliana" and body["currency_code"] == "PEN"
    assert "is_person" not in body


@pytest.mark.parametrize(
    ("type_step", "path"),
    [("", "/accounts"), ("person", "/people")],
    ids=["bank", "person"],
)
def test_new_account_without_color_omits_color_and_sort_order(fake_client, type_step, path):
    """A skipped COLOR leaves the key out of the body, and the form has no
    order field, so the engine applies both defaults; an explicit `null` on
    either is a 422 (contract: POST /v1/accounts) (contract: POST /v1/people)."""
    posted_path, body = _run(fake_client, NewAccountScreen(), [type_step, "Eliana", "PEN", ""])
    assert posted_path == path
    assert "color" not in body
    assert "sort_order" not in body
    assert None not in body.values()


def test_edit_account_locks_type_and_currency(fake_client):
    """`is_person` is creation-time-only, so editing shows TYPE read-only."""
    screen = EditAccountScreen(
        {
            "id": "abc",
            "name": "Eliana",
            "currency_code": "PEN",
            "is_person": True,
            "opening_balance_transaction_id": None,
        }
    )
    assert screen._locked == {"currency", "type"}
    assert screen._values["type"] == "person"
    assert screen._submit_request()[:2] == ("PUT", "/accounts/abc")
    assert "is_person" not in screen._payload()


def test_new_account_required_name_blocks_submit(fake_client):
    async def scenario(pilot, app):
        screen = NewAccountScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        screen.action_submit()  # nothing entered
        await pilot.pause()  # let the blocked submit settle, then assert a non-event
        assert not fake_client.calls

    run_app(scenario)


# ---------------------------------------------------------------------------
# the failure path — FormScreen._failed
# ---------------------------------------------------------------------------
#
# Every create and edit form routes its refusals through one three-line method
# on the base class; the six tests above all let the write succeed. Eight
# screens depend on it — NewHashtag,
# NewCategory, NewAccount, their three Edit* subclasses, NewReconciliationScreen
# and EditFormScreen — so a regression there is a regression in all of them.


def _run_refused(fake_client, monkeypatch, screen, steps, check, *, verb="POST"):
    """Drive `screen` through `steps` with the engine refusing the write, then
    run `check(pilot, screen, toasts)` **inside** the pilot.

    The check has to happen there: leaving the `run_test` block shuts the app
    down and detaches every screen, so `is_attached` and the mounted widgets can
    only be read while it is up.

    The captured toast is what proves `_failed` ran at all — `run_write` hands
    `on_error` back to the UI thread and the callback leaves no other edge.
    """
    fake_client.errors[verb] = EngineError("CONFLICT", "that name is taken", None, 409, {})
    toasts: list = []
    monkeypatch.setattr(
        type(screen), "notify", lambda self, message, **kw: toasts.append((message, kw))
    )

    async def scenario(pilot, app):
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in steps:
            _enter(screen, text)
        await wait_for(pilot, lambda: toasts, message="the form never reported the failure")
        await pilot.pause()
        await check(pilot, screen, toasts)

    run_app(scenario)


def test_a_refused_create_says_so_and_keeps_the_screen(fake_client, monkeypatch):
    """The engine's envelope reaches the user and the form stays put.

    Dismissing on failure would throw away everything typed and leave the
    message nowhere to be read — the same rule the LOG bar follows.
    """

    async def check(pilot, screen, toasts):
        message, kw = toasts[0]
        assert "CONFLICT — that name is taken" in message
        assert kw.get("title") == "Failed" and kw.get("severity") == "error"
        assert screen.is_attached  # never dismissed
        # the typed text survives verbatim; the `#` is stripped in _payload(), not here
        assert screen._values["name"] == "#groceries"

    _run_refused(fake_client, monkeypatch, NewHashtagScreen(), ["#groceries"], check)


def test_a_refused_create_restores_the_hint_the_busy_text_replaced(fake_client, monkeypatch):
    """`action_submit` overwrites #hint with "Creating…" before the write.

    Without `_refresh_view()` in the failure path the form would sit there
    claiming to still be creating, under a toast saying it had failed.
    """

    async def check(pilot, screen, toasts):
        hint = str(screen.query_one("#hint", Static).content)
        assert "Creating" not in hint
        assert hint == screen._hint_for(screen._key)

    _run_refused(fake_client, monkeypatch, NewHashtagScreen(), ["#groceries"], check)


def test_a_refused_create_can_be_submitted_again(fake_client, monkeypatch):
    """`_submitting` is the double-submit latch — a failure has to release it.

    Left set, the first refusal would freeze the form for good: every later
    submit would return at the guard, silently, with the toast as the only clue.
    """

    async def check(pilot, screen, toasts):
        assert screen._submitting is False
        fake_client.errors.clear()
        screen.action_submit()
        await wait_for(
            pilot,
            lambda: fake_client.posts,
            message="a second submit after a failure never reached the engine",
        )

    _run_refused(fake_client, monkeypatch, NewHashtagScreen(), ["#groceries"], check)


def test_a_refused_edit_reports_through_the_same_path(fake_client, monkeypatch):
    """The Edit* screens differ only in `_submit_request` — PUT, not POST."""
    screen = EditAccountScreen(
        {
            "id": "abc",
            "name": "Eliana",
            "currency_code": "PEN",
            "is_person": True,
            "opening_balance_transaction_id": None,
        }
    )

    async def check(pilot, screen, toasts):
        message, kw = toasts[0]
        assert "CONFLICT — that name is taken" in message
        assert kw.get("title") == "Failed"
        assert screen.is_attached
        assert ("PUT", "/accounts/abc") in [(m, p) for m, p, _ in fake_client.calls]

    _run_refused(fake_client, monkeypatch, screen, ["Eliana Vega", ""], check, verb="PUT")


# ---------------------------------------------------------------------------
# field navigation — the shared `form_bindings` keymap, pressed for real
# ---------------------------------------------------------------------------
#
# EditAccountScreen is the form with read-only fields: TYPE and CURRENCY are
# locked, so the editable sequence is NAME (a plain text field, no list), COLOR
# (a palette list), then a bank account's OPENING and AS OF (plain text). Every
# bar form takes the same keymap from FormScreen.

_ACCOUNT = {
    "id": "abc",
    "name": "Eliana",
    "currency_code": "PEN",
    "is_person": False,
    "opening_balance_transaction_id": None,
}


def _navigate(steps):
    """Push the account edit form, then run each `(key, expected field)` step."""

    async def scenario(pilot, app):
        screen = EditAccountScreen(dict(_ACCOUNT))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        assert screen._key == "name"  # the first editable field
        for key, expected in steps:
            await pilot.press(key)
            await pilot.pause()
            assert screen._key == expected, f"after {key}: {screen._key}"
            # the form's binding wins over the screen's focus-cycling: the bar
            # still has focus after every key.
            assert app.focused is screen.query_one("#bar", Input)

    run_app(scenario)


def test_tab_and_shift_tab_move_fields_skipping_read_only_ones():
    """tab → next editable field, shift+tab → previous; both stop at the ends."""
    _navigate(
        [
            ("tab", "color"),  # skips locked CURRENCY
            ("tab", "opening"),
            ("tab", "as_of"),
            ("tab", "as_of"),  # no editable field further on: stays
            ("shift+tab", "opening"),
            ("shift+tab", "color"),
            ("shift+tab", "name"),
            ("shift+tab", "name"),  # TYPE is locked: stays
        ]
    )


def test_tab_moves_fields_while_a_suggestion_list_is_open():
    """On COLOR the palette list is open; tab and shift+tab still move fields."""

    async def scenario(pilot, app):
        screen = EditAccountScreen(dict(_ACCOUNT))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("tab")
        await pilot.pause()
        assert screen._key == "color" and screen._suggestions  # list open
        await pilot.press("shift+tab")
        await pilot.pause()
        assert screen._key == "name"

    run_app(scenario)


def test_plain_arrows_walk_a_list_and_move_fields_without_one():
    """NAME has no list, so `↓` moves on; COLOR's palette list takes `↑`/`↓`
    until it empties, and then `↑` moves back."""

    async def scenario(pilot, app):
        screen = EditAccountScreen(dict(_ACCOUNT))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("down")  # NAME: no list → next field
        await pilot.pause()
        assert screen._key == "color" and len(screen._suggestions) > 2
        await pilot.press("down", "down")
        await pilot.pause()
        assert (screen._key, screen._suggest_idx) == ("color", 2)
        await pilot.press("up")
        await pilot.pause()
        assert (screen._key, screen._suggest_idx) == ("color", 1)
        # type a word nothing matches: the list empties, so `↑` moves fields
        screen.query_one("#bar", Input).value = "zzzz"
        await pilot.pause()
        assert screen._suggestions == []
        await pilot.press("up")
        await pilot.pause()
        assert screen._key == "name"

    run_app(scenario)


def test_ctrl_arrows_still_move_fields():
    _navigate([("ctrl+down", "color"), ("ctrl+up", "name")])
