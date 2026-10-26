"""Create-form tests (new hashtag / category / account, fake client)."""

import pytest
from textual.widgets import Input, Static

from expense.errors import EngineError
from expense.tui.screens.create_forms import (
    EditAccountScreen,
    EditCategoryScreen,
    EditHashtagScreen,
    NewAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from tests.unit.helpers import render_text, run_app, wait_for


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


def test_new_category_with_a_color_posts_it(fake_client):
    # name, then pick a color (type 'green' → matches the palette)
    path, body = _run(fake_client, NewCategoryScreen(), ["Educación", "green"])
    assert path == "/categories"
    assert body["name"] == "Educación" and body["color"] == "#5ab87a"


def test_new_category_without_a_color_omits_the_key(fake_client):
    """Empty enter on COLOR saves with no `color` key, not a null: the engine
    gives its default (contract: POST /v1/categories)."""
    path, body = _run(fake_client, NewCategoryScreen(), ["Mascotas", ""])
    assert path == "/categories"
    assert body["name"] == "Mascotas" and "id" in body
    assert "color" not in body
    assert None not in body.values()


def test_new_category_ctrl_s_on_the_name_line_saves_without_a_color(fake_client):
    async def scenario(pilot, app):
        screen = NewCategoryScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        _enter(screen, "Mascotas")
        await pilot.press("shift+tab")  # back on the name line, COLOR never touched
        await pilot.pause()
        assert screen._key == "name"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.posts)
        path, body = fake_client.posts[0]
        assert path == "/categories" and "color" not in body

    run_app(scenario)


def test_new_category_color_line_reads_optional(fake_client):
    """Mockup Part 2: the line reads optional, in the hint and the summary tag."""

    async def scenario(pilot, app):
        screen = NewCategoryScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        assert screen._sequence() == ["name", "color"]
        _enter(screen, "Mascotas")
        await pilot.pause()
        assert screen._key == "color"
        assert (
            str(screen.query_one("#hint", Static).content)
            == "optional · enter to save · ↑↓ another swatch"
        )
        summary = screen.query_one("#summary", Static).content
        assert "—  (optional)" in render_text(summary, width=80)
        assert screen._required() == ("name",)

    run_app(scenario)


def test_new_category_unknown_color_is_still_refused(fake_client, monkeypatch):
    """A word no swatch matches gets the existing "Pick a color." note; nothing is sent."""
    toasts: list = []
    monkeypatch.setattr(
        NewCategoryScreen, "notify", lambda self, message, **kw: toasts.append((message, kw))
    )

    async def scenario(pilot, app):
        screen = NewCategoryScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        _enter(screen, "Mascotas")
        _enter(screen, "zzzz")
        await pilot.pause()
        assert toasts == [("Pick a color.", {"severity": "error"})]
        assert screen._key == "color" and "color" not in screen._values
        assert not fake_client.posts

    run_app(scenario)


def _on_color(make):
    """Push `make()`, fill every line before COLOR, return a scenario helper."""

    async def land(pilot, app):
        screen = make()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        while screen._key != "color":
            await pilot.press("tab")
            await pilot.pause()
        return screen

    return land


def _highlighted(screen) -> list[str]:
    """The suggestion rows drawn reversed (the highlight)."""
    rendered = screen._suggest_renderable()
    return [
        line.plain.strip()
        for line in getattr(rendered, "renderables", [rendered])
        if any(str(span.style) == "reverse" for span in line.spans)
    ]


@pytest.mark.parametrize("make", [NewCategoryScreen, NewAccountScreen], ids=["category", "account"])
def test_an_empty_optional_color_line_highlights_nothing(fake_client, make):
    """Empty enter skips an optional colour, so no swatch may look picked."""
    land = _on_color(make)

    async def scenario(pilot, app):
        screen = await land(pilot, app)
        assert screen._suggestions  # the palette is listed
        assert screen._suggest_idx == -1 and _highlighted(screen) == []

    run_app(scenario)


@pytest.mark.parametrize("make", [NewCategoryScreen, NewAccountScreen], ids=["category", "account"])
def test_typing_on_an_optional_color_line_highlights_the_first_match(fake_client, make):
    land = _on_color(make)

    async def scenario(pilot, app):
        screen = await land(pilot, app)
        await pilot.press("g", "r")
        await pilot.pause()
        assert _highlighted(screen) == ["██ green"]
        await pilot.press("backspace", "backspace")  # empty again: nothing highlighted
        await pilot.pause()
        assert _highlighted(screen) == []

    run_app(scenario)


@pytest.mark.parametrize("make", [NewCategoryScreen, NewAccountScreen], ids=["category", "account"])
def test_arrowing_into_an_optional_color_list_highlights_and_enter_picks(fake_client, make):
    land = _on_color(make)

    async def scenario(pilot, app):
        screen = await land(pilot, app)
        if isinstance(screen, NewCategoryScreen):
            screen._values["name"] = "Mascotas"
        else:
            screen._values.update(name="Sueldo", currency="PEN")
        await pilot.press("down")
        await pilot.pause()
        assert _highlighted(screen) == ["██ blue"]
        await pilot.press("down")
        await pilot.pause()
        assert _highlighted(screen) == ["██ green"]
        await pilot.press("enter")  # the last line: saves with the highlighted swatch
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts[0][1]["color"] == "#5ab87a"

    run_app(scenario)


def test_a_required_color_line_still_highlights_when_empty(fake_client):
    """Edit Category keeps COLOR required: holding no colour, its first swatch is
    highlighted."""

    async def scenario(pilot, app):
        screen = EditCategoryScreen({"id": "c1", "name": "Ocio", "color": None})
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("tab")
        await pilot.pause()
        assert screen._key == "color" and _highlighted(screen) == ["██ blue"]

    run_app(scenario)


def test_edit_category_keeps_color_required_and_never_sends_null(fake_client):
    """The engine refuses `color: null` on PUT (contract: PUT /v1/categories/{category_id}):
    Edit category keeps COLOR required, and its body never carries a null; the
    category's own colour is left out, so the engine keeps it."""

    async def scenario(pilot, app):
        screen = EditCategoryScreen({"id": "c1", "name": "Ocio", "color": "#b07cd9"})
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        assert screen._required() == ("name", "color")
        assert screen._hint_for("color") == "pick a swatch"
        _enter(screen, "Ocio y viajes")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)
        path, body = fake_client.puts[0]
        assert path == "/categories/c1"
        assert body == {"name": "Ocio y viajes"}
        assert None not in body.values()

    run_app(scenario)


def test_edit_category_without_a_color_is_refused_before_any_put(fake_client, monkeypatch):
    toasts: list = []
    monkeypatch.setattr(
        EditCategoryScreen, "notify", lambda self, message, **kw: toasts.append((message, kw))
    )

    async def scenario(pilot, app):
        screen = EditCategoryScreen({"id": "c1", "name": "Ocio", "color": None})
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert toasts == [("Color is required.", {"severity": "error"})]
        assert not fake_client.puts

    run_app(scenario)


def test_edit_category_unknown_color_is_refused_and_nothing_is_sent(fake_client, monkeypatch):
    toasts: list = []
    monkeypatch.setattr(
        EditCategoryScreen, "notify", lambda self, message, **kw: toasts.append((message, kw))
    )

    async def scenario(pilot, app):
        screen = EditCategoryScreen({"id": "c1", "name": "Ocio", "color": "#b07cd9"})
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        _enter(screen, "Ocio")
        _enter(screen, "zzzz")
        await pilot.pause()
        assert toasts == [("Pick a color.", {"severity": "error"})]
        assert not fake_client.puts

    run_app(scenario)


def test_edit_category_with_no_color_cannot_save_a_null(fake_client):
    screen = EditCategoryScreen({"id": "c1", "name": "Ocio", "color": None})
    assert "color" not in screen._payload()
    assert None not in screen._payload().values()


# ---------------------------------------------------------------------------
# the Edit screens' COLOR line starts on the row's own colour
# ---------------------------------------------------------------------------
#
# Stepping through a form never changes it (decisions.md): `enter` down every
# line of a category's or an account's Edit screen keeps its colour. A save
# with nothing changed is the form's usual one, the name alone, so the colour is
# never sent and the engine keeps it; the summary goes on showing it.


def _green_category() -> EditCategoryScreen:
    return EditCategoryScreen({"id": "c1", "name": "Ocio", "color": "#5ab87a"})


def _account(color, *, is_person=False) -> EditAccountScreen:
    return EditAccountScreen(
        {
            "id": "abc",
            "name": "Sueldo",
            "currency_code": "PEN",
            "color": color,
            "statement_code": None,
            "is_person": is_person,
            "opening_balance_transaction_id": None,
        }
    )


def _summary_color(screen) -> str:
    """The summary's colour row (drawn from the form's state, so it reads the
    same once the save has closed the screen)."""
    text = render_text(screen._summary_renderable(), width=80)
    return next(line for line in text.splitlines() if line.startswith("color"))


async def _open(pilot, app, screen):
    await app.push_screen(screen)
    await wait_for(pilot, lambda: bool(screen.query("#bar")))


async def _enter_until_color(pilot, screen):
    """`enter` with nothing typed, line by line, until the bar is on COLOR;
    one press per line at most, so a form that never gets there fails."""
    for _ in range(len(screen._sequence()) + 1):
        if screen._key == "color":
            return
        await pilot.press("enter")
        await pilot.pause()
    pytest.fail(f"enter never reached COLOR: the bar is on {screen._key}")


async def _enter_until_saved(pilot, screen):
    """`enter` on, line by line, until the save (the last line's) closes it;
    one press per line at most, so a form that never saves fails."""
    for _ in range(len(screen._sequence()) + 1):
        if not screen.is_attached:
            return
        await pilot.press("enter")
        await pilot.pause()
    await wait_for(pilot, lambda: not screen.is_attached, message="enter never saved the form")


_PATHS = {EditCategoryScreen: "/categories/c1", EditAccountScreen: "/accounts/abc"}


@pytest.mark.parametrize(
    "make",
    [_green_category, lambda: _account("#5ab87a"), lambda: _account("#5ab87a", is_person=True)],
    ids=["category", "bank-account", "person"],
)
def test_enter_down_every_line_keeps_the_rows_colour_and_never_sends_it(fake_client, make):
    screen = make()

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _enter_until_color(pilot, screen)
        assert _highlighted(screen) == ["██ green"]  # the row's own swatch
        assert "██ green" in _summary_color(screen)
        await _enter_until_saved(pilot, screen)

    run_app(scenario)
    assert screen._values["color"] == "#5ab87a"
    assert "██ green" in _summary_color(screen)
    assert fake_client.requests == [("PUT", _PATHS[type(screen)])]
    assert fake_client.puts[0][1] == {"name": screen._values["name"]}  # no colour


@pytest.mark.parametrize(
    "make",
    [_green_category, lambda: _account("#5ab87a", is_person=True)],
    ids=["category", "person"],
)
def test_another_swatch_picked_with_the_arrows_is_sent(fake_client, make):
    screen = make()

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _enter_until_color(pilot, screen)
        await pilot.press("down")  # from green, one on: red
        await pilot.pause()
        assert _highlighted(screen) == ["██ red"]
        await pilot.press("enter")  # COLOR is the last line: it saves
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    assert fake_client.puts == [
        (_PATHS[type(screen)], {"name": screen._values["name"], "color": "#d96a5a"})
    ]


def test_an_account_with_no_colour_starts_on_nothing_and_enter_skips_it(fake_client):
    screen = _account(None)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _enter_until_color(pilot, screen)
        assert screen._suggestions and _highlighted(screen) == []
        await pilot.press("enter")
        await pilot.pause()
        assert screen._key == "opening" and "color" not in screen._values
        assert "—  (optional)" in _summary_color(screen)
        await _enter_until_saved(pilot, screen)

    run_app(scenario)
    assert fake_client.puts == [("/accounts/abc", {"name": "Sueldo"})]


@pytest.mark.parametrize(
    "make",
    [
        lambda: EditCategoryScreen({"id": "c1", "name": "Ocio", "color": "#123456"}),
        lambda: _account("#123456"),
    ],
    ids=["category", "account"],
)
def test_a_colour_no_swatch_shows_is_kept_and_never_sent(fake_client, make):
    """A colour from outside the palette (the sheet import's, say) highlights no
    swatch and `enter` keeps it, even where COLOR is required; the summary shows
    it, and the save leaves it out of the body."""
    screen = make()

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _enter_until_color(pilot, screen)
        assert screen._suggestions and _highlighted(screen) == []
        assert "#123456" in _summary_color(screen)
        await _enter_until_saved(pilot, screen)

    run_app(scenario)
    assert screen._values["color"] == "#123456"
    assert "#123456" in _summary_color(screen)
    assert fake_client.puts == [(_PATHS[type(screen)], {"name": screen._values["name"]})]


def test_after_the_account_half_saves_the_old_colour_picked_again_is_sent(fake_client, monkeypatch):
    """green → red: the account's PUT lands, the opening balance is refused and
    the form stays open. Red is now the account's own, so picking green again is
    a change: the next save sends it, with the opening balance."""
    screen = _account("#5ab87a")
    monkeypatch.setattr(EditAccountScreen, "notify", lambda self, message, **kw: None)
    fake_client.errors["POST"] = EngineError("CONFLICT", "it got one meanwhile", None, 409, {})

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _enter_until_color(pilot, screen)
        await pilot.press("down")  # green → red
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press(*"350")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press(*"2026-01-01")
        await pilot.press("enter")  # the last line: saves both halves
        await wait_for(pilot, lambda: len(fake_client.calls) == 2)
        await wait_for(pilot, lambda: not screen._submitting)
        assert screen.is_attached and screen._account_saved
        fake_client.errors.clear()
        for _ in range(len(screen._sequence())):
            if screen._key == "color":
                break
            await pilot.press("shift+tab")
            await pilot.pause()
        assert screen._key == "color"
        assert _highlighted(screen) == ["██ red"]
        await pilot.press("up")  # red → green, the colour the form opened on
        await pilot.pause()
        assert _highlighted(screen) == ["██ green"]
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    run_app(scenario)
    assert fake_client.requests == [
        ("PUT", "/accounts/abc"),
        ("POST", "/accounts/abc/opening-balance"),
        ("PUT", "/accounts/abc"),
        ("POST", "/accounts/abc/opening-balance"),
    ]
    assert [body for _path, body in fake_client.puts] == [
        {"name": "Sueldo", "color": "#d96a5a"},
        {"name": "Sueldo", "color": "#5ab87a"},
    ]


def test_an_emptied_colour_bar_goes_back_to_the_rows_own_swatch(fake_client):
    screen = _green_category()

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _enter_until_color(pilot, screen)
        await pilot.press("p", "u")
        await pilot.pause()
        assert _highlighted(screen) == ["██ purple"]
        await pilot.press("backspace", "backspace")
        await pilot.pause()
        assert _highlighted(screen) == ["██ green"]

    run_app(scenario)


def test_new_account_defaults_to_bank_on_empty_type(fake_client):
    """Empty enter on TYPE keeps `bank` — adding an account costs no extra decision."""
    # type (empty → the prefilled bank), name, currency PEN, skip color
    path, body = _run(fake_client, NewAccountScreen(), ["", "Interbank Sueldo", "PEN", "", ""])
    assert path == "/accounts"
    assert body["name"] == "Interbank Sueldo" and body["currency_code"] == "PEN"
    assert "color" not in body
    assert "statement_code" not in body  # skipped: left out, never null
    # `is_person` is a 422 on both routes — the endpoint is the flag, never a field.
    assert "is_person" not in body


def test_new_account_type_person_posts_to_people(fake_client):
    """Picking `person` routes the same fields to POST /people."""
    path, body = _run(fake_client, NewAccountScreen(), ["person", "Eliana", "PEN", ""])
    assert path == "/people"
    assert body["name"] == "Eliana" and body["currency_code"] == "PEN"
    assert "is_person" not in body


@pytest.mark.parametrize(
    ("steps", "path"),
    [(["", "Eliana", "PEN", "", ""], "/accounts"), (["person", "Eliana", "PEN", ""], "/people")],
    ids=["bank", "person"],
)
def test_new_account_without_color_omits_color_and_sort_order(fake_client, steps, path):
    """A skipped COLOR leaves the key out of the body, and the form has no
    order field, so the engine applies both defaults; an explicit `null` on
    either is a 422 (contract: POST /v1/accounts) (contract: POST /v1/people).
    A bank account's STATEMENT CODE is skipped too, one line before COLOR."""
    posted_path, body = _run(fake_client, NewAccountScreen(), steps)
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
            "statement_code": None,
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


def _run_refused(fake_client, monkeypatch, screen, steps, check, *, verb="POST", refusal=None):
    """Drive `screen` through `steps` with the engine refusing the write, then
    run `check(pilot, screen, toasts)` **inside** the pilot.

    The check has to happen there: leaving the `run_test` block shuts the app
    down and detaches every screen, so `is_attached` and the mounted widgets can
    only be read while it is up.

    The captured toast is what proves `_failed` ran at all — `run_write` hands
    `on_error` back to the UI thread and the callback leaves no other edge.
    """
    fake_client.errors[verb] = refusal or EngineError(
        "CONFLICT", "that name is taken", None, 409, {}
    )
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
            "statement_code": None,
        }
    )

    async def check(pilot, screen, toasts):
        message, kw = toasts[0]
        assert "CONFLICT — that name is taken" in message
        assert kw.get("title") == "Failed"
        assert screen.is_attached
        assert ("PUT", "/accounts/abc") in [(m, p) for m, p, _ in fake_client.calls]

    _run_refused(fake_client, monkeypatch, screen, ["Eliana Vega", ""], check, verb="PUT")


def _keyed(code: str, key: str, reason: str, message: str) -> EngineError:
    """A refusal keyed by the thing refused (contract: "Error reasons")."""
    status = 422 if code in ("LIMIT_REACHED", "VALIDATION_ERROR") else 409
    return EngineError(code, message, {key: "stand-in field words"}, status, {}, {key: reason})


def _eliana() -> EditAccountScreen:
    return EditAccountScreen(
        {
            "id": "abc",
            "name": "Eliana",
            "currency_code": "PEN",
            "is_person": True,
            "opening_balance_transaction_id": None,
            "statement_code": None,
        }
    )


@pytest.mark.parametrize(
    ("make", "steps", "verb", "refusal", "line"),
    [
        (
            _eliana,
            ["Eliana Vega", ""],
            "PUT",
            _keyed("CONFLICT", "name", "NAME_EXISTS", "Name already exists."),
            "That name is taken: pick another.",
        ),
        (
            NewCategoryScreen,
            ["Mascotas", ""],
            "POST",
            _keyed("CONFLICT", "name", "NAME_EXISTS", "Name already exists."),
            "That name is taken: pick another.",
        ),
        (
            NewHashtagScreen,
            ["viaje-lima"],
            "POST",
            _keyed("LIMIT_REACHED", "id", "CAP_REACHED", "Hashtag limit reached."),
            "Delete one first.",
        ),
        (
            NewHashtagScreen,
            ["salud"],
            "POST",
            _keyed("CONFLICT", "id", "ID_EXISTS", "ID already exists."),
            "Not your mistake: the app sent it wrong and nothing was saved. "
            "Try again; if it happens again, report it.",
        ),
        # a user hashtag, new or renamed, cannot take the pending hashtag's name
        # (pending-hashtag-manage 4 B, one line for every system row)
        (
            NewHashtagScreen,
            ["pendiente"],
            "POST",
            _keyed(
                "VALIDATION_ERROR",
                "name",
                "RESERVED_NAME",
                "Pendiente is reserved for the pending hashtag.",
            ),
            "That name belongs to a system row: pick another.",
        ),
        (
            lambda: EditHashtagScreen({"id": "h1", "name": "viaje"}),
            ["PENDIENTE"],
            "PUT",
            _keyed(
                "VALIDATION_ERROR",
                "name",
                "RESERVED_NAME",
                "Pendiente is reserved for the pending hashtag.",
            ),
            "That name belongs to a system row: pick another.",
        ),
        # a user category, new or renamed, cannot take a system category's name
        (
            NewCategoryScreen,
            ["@pendiente", ""],
            "POST",
            _keyed(
                "VALIDATION_ERROR",
                "name",
                "RESERVED_NAME",
                "@Pendiente is reserved for a system category.",
            ),
            "That name belongs to a system row: pick another.",
        ),
        (
            lambda: EditCategoryScreen(
                {"id": "c1", "name": "Mascotas", "color": "#b07cd9", "is_system": False}
            ),
            ["@pendiente", ""],
            "PUT",
            _keyed(
                "VALIDATION_ERROR",
                "name",
                "RESERVED_NAME",
                "@Pendiente is reserved for a system category.",
            ),
            "That name belongs to a system row: pick another.",
        ),
    ],
    ids=[
        "screen-2",
        "category-no-color",
        "screen-3A",
        "screen-9A",
        "reserved-name-new",
        "reserved-name-rename",
        "reserved-category-name-new",
        "reserved-category-name-rename",
    ],
)
def test_a_refusal_on_a_form_ends_with_its_next_step(
    fake_client, monkeypatch, make, steps, verb, refusal, line
):
    """The "Failed" note is the engine's words, then the line picked for its
    reason; the form stays open with what was typed."""

    async def check(pilot, screen, toasts):
        message, kw = toasts[0]
        key = next(iter(refusal.fields))
        assert message == (
            f"{refusal.code} — {refusal.message}\n  {key}: stand-in field words\n\n{line}"
        )
        assert kw.get("title") == "Failed"
        assert screen.is_attached

    _run_refused(fake_client, monkeypatch, make(), steps, check, verb=verb, refusal=refusal)


#: The engine's words on a renamed system row
#: (contract: PUT /v1/categories/{category_id}, "A system category keeps its name")
#: (contract: PUT /v1/hashtags/{hashtag_id}, "The pending hashtag keeps its name").
_NAME_FIXED = "Must be the current name: a system record keeps its name."


@pytest.mark.parametrize(
    ("make", "steps", "path"),
    [
        (
            lambda: EditCategoryScreen(
                {"id": "pend", "name": "@Pendiente", "color": "#b07cd9", "is_system": True}
            ),
            ["@pendiente", ""],
            "/categories/pend",
        ),
        (
            lambda: EditCategoryScreen(
                {"id": "open", "name": "@Opening", "color": "#b07cd9", "is_system": True}
            ),
            ["Apertura", ""],
            "/categories/open",
        ),
        (
            lambda: EditHashtagScreen({"id": "h-pend", "name": "Pendiente"}),
            ["Por revisar"],
            "/hashtags/h-pend",
        ),
    ],
    ids=["pendiente-case-only", "opening", "pending-hashtag"],
)
def test_a_system_rows_rename_shows_the_engines_words(fake_client, monkeypatch, make, steps, path):
    """A system category or the pending hashtag keeps its name: the engine
    refuses a rename with `SYSTEM_NAME_FIXED` on `name`. Manage offers no `e`
    on these rows, so only a form opened another way meets it. The note is the
    engine's words whole, then the line of pending-hashtag-manage 5 B, and the
    form stays open with what was typed."""
    refusal = EngineError(
        "VALIDATION_ERROR",
        "Request validation failed.",
        {"name": _NAME_FIXED},
        422,
        {},
        {"name": "SYSTEM_NAME_FIXED"},
    )

    async def check(pilot, screen, toasts):
        message, kw = toasts[0]
        assert message == (
            f"VALIDATION_ERROR — Request validation failed.\n  name: {_NAME_FIXED}\n\n"
            "Built-in names never change: press esc to leave it as it is."
        )
        assert kw.get("title") == "Failed" and kw.get("severity") == "error"
        assert screen.is_attached
        assert screen._values["name"] == steps[0]
        assert ("PUT", path) in fake_client.requests

    _run_refused(fake_client, monkeypatch, make(), steps, check, verb="PUT", refusal=refusal)


# ---------------------------------------------------------------------------
# field navigation — the shared `form_bindings` keymap, pressed for real
# ---------------------------------------------------------------------------
#
# EditAccountScreen is the form with read-only fields: TYPE and CURRENCY are
# locked, so the editable sequence is NAME (a plain text field, no list), a bank
# account's STATEMENT CODE (plain text), COLOR (a palette list), then a bank
# account's OPENING and AS OF (plain text). Every bar form takes the same keymap
# from FormScreen.

_ACCOUNT = {
    "id": "abc",
    "name": "Eliana",
    "currency_code": "PEN",
    "is_person": False,
    "opening_balance_transaction_id": None,
    "statement_code": None,
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


def test_a_forms_own_enter_handler_stops_the_ones_under_it():
    """Textual runs the `on_input_submitted` of every class in a screen's MRO on
    one `⏎` unless the message's default is prevented. A form whose handler
    overrides one it inherits calls that one itself, so it must prevent the
    default, or one `⏎` commits twice and moves two lines."""
    import inspect

    from expense.tui.screens import create_forms, edit_form, reconciliations, setup
    from expense.tui.screens._form import FormScreen

    assert create_forms and edit_form and reconciliations and setup  # all loaded

    def every(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from every(sub)

    overriding = []
    for form in every(FormScreen):
        handler = form.__dict__.get("on_input_submitted")
        if handler is None:
            continue
        if any("on_input_submitted" in base.__dict__ for base in form.__mro__[1:]):
            overriding.append(form.__name__)
            assert "event.prevent_default()" in inspect.getsource(handler), form.__name__
    assert "EditAccountScreen" in overriding


def test_tab_and_shift_tab_move_fields_skipping_read_only_ones():
    """tab → next editable field, shift+tab → previous; both stop at the ends."""
    _navigate(
        [
            ("tab", "statement_code"),  # skips locked CURRENCY
            ("tab", "color"),
            ("tab", "opening"),
            ("tab", "as_of"),
            ("tab", "as_of"),  # no editable field further on: stays
            ("shift+tab", "opening"),
            ("shift+tab", "color"),
            ("shift+tab", "statement_code"),
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
        await pilot.press("tab", "tab")
        await pilot.pause()
        assert screen._key == "color" and screen._suggestions  # list open
        await pilot.press("shift+tab")
        await pilot.pause()
        assert screen._key == "statement_code"

    run_app(scenario)


def test_plain_arrows_walk_a_list_and_move_fields_without_one():
    """NAME and STATEMENT CODE have no list, so `↓` moves on; COLOR's palette
    list takes `↑`/`↓` until it empties, and then `↑` moves back."""

    async def scenario(pilot, app):
        screen = EditAccountScreen(dict(_ACCOUNT))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("down")  # NAME: no list → next field
        await pilot.pause()
        assert screen._key == "statement_code" and screen._suggestions == []
        await pilot.press("down")
        await pilot.pause()
        assert screen._key == "color" and len(screen._suggestions) > 2
        assert screen._suggest_idx == -1  # optional and empty: nothing highlighted
        await pilot.press("down", "down", "down")
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
        assert screen._key == "statement_code"

    run_app(scenario)


def test_ctrl_arrows_still_move_fields():
    _navigate([("ctrl+down", "statement_code"), ("ctrl+up", "name")])
