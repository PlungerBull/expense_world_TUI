"""Create-form tests (new hashtag / category / account, fake client)."""

import uuid

import pytest
from textual.widgets import Input, Static

from expense.errors import EngineError, format_error
from expense.tui.screens.create_forms import (
    EditAccountScreen,
    EditCategoryScreen,
    EditHashtagScreen,
    NewAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from tests.unit.helpers import (
    ENGINE_BANKS,
    ENGINE_CURRENCIES,
    account_with_currencies,
    enter_values,
    no_failed_toast,
    refusal_block,
    render_text,
    run_app,
    wait_for,
)


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
    """The line reads optional, in the hint and the summary tag."""

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
        assert toasts == [("Pick a color.", {"severity": "error", "markup": False})]
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


@pytest.mark.parametrize(
    "make",
    [NewCategoryScreen, lambda: NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)],
    ids=["category", "account"],
)
def test_an_optional_color_list_highlights_only_what_is_matched_or_arrowed_to(fake_client, make):
    """Empty enter skips an optional colour, so no swatch looks picked; typing highlights
    the first match; arrowing highlights, and `enter` picks."""
    land = _on_color(make)

    async def scenario(pilot, app):
        screen = await land(pilot, app)
        assert screen._suggestions  # the palette is listed
        assert screen._suggest_idx == -1 and _highlighted(screen) == []
        await pilot.press("g", "r")
        await pilot.pause()
        assert _highlighted(screen) == ["██ green"]
        await pilot.press("backspace", "backspace")  # empty again: nothing highlighted
        await pilot.pause()
        assert _highlighted(screen) == []
        if isinstance(screen, NewCategoryScreen):
            screen._values["name"] = "Mascotas"
        else:
            screen._values.update(bank="BCP", currencies=["PEN"])
        await pilot.press("down")
        await pilot.pause()
        assert _highlighted(screen) == ["██ blue"]
        await pilot.press("down")
        await pilot.pause()
        assert _highlighted(screen) == ["██ green"]
        # COLOR is the last line of a category; an account's pair lines follow it
        await pilot.press(*["enter"] * (1 if isinstance(screen, NewCategoryScreen) else 3))
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
        assert toasts == [("Color is required.", {"severity": "error", "markup": False})]
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
# with nothing changed sends no colour (a category sends its name, an account `{}`), so it is
# never sent and the engine keeps it; the summary goes on showing it.


def _green_category() -> EditCategoryScreen:
    return EditCategoryScreen({"id": "c1", "name": "Ocio", "color": "#5ab87a"})


_ELIANA = account_with_currencies(id="abc", name="Eliana", kind="person")


def _edit_account(color, *, kind="bank") -> EditAccountScreen:
    """The edit form of Sueldo, a soles account or person of `color`."""
    return EditAccountScreen(
        account_with_currencies(id="abc", name="Sueldo", color=color, kind=kind),
        ENGINE_CURRENCIES,
        ENGINE_BANKS,
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


def _unchanged_body(screen) -> dict:
    """What a save with nothing changed sends: a category's name, an account's `{}`."""
    return {"name": screen._values["name"]} if isinstance(screen, EditCategoryScreen) else {}


@pytest.mark.parametrize(
    "make",
    [
        _green_category,
        lambda: _edit_account("#5ab87a"),
        lambda: _edit_account("#5ab87a", kind="person"),
    ],
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
    assert fake_client.puts[0][1] == _unchanged_body(screen)  # no colour


@pytest.mark.parametrize(
    "make",
    [_green_category, lambda: _edit_account("#5ab87a", kind="person")],
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
        # `enter` takes red; a category saves there, a person goes on through
        # its empty OPENING and AS OF and saves on the last line
        await _enter_until_saved(pilot, screen)

    run_app(scenario)
    assert fake_client.puts == [
        (_PATHS[type(screen)], {**_unchanged_body(screen), "color": "#d96a5a"})
    ]


def test_an_account_with_no_colour_starts_on_nothing_and_enter_skips_it(fake_client):
    screen = _edit_account(None)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _enter_until_color(pilot, screen)
        assert screen._suggestions and _highlighted(screen) == []
        await pilot.press("enter")
        await pilot.pause()
        assert screen._key == "opening:PEN" and "color" not in screen._values
        assert "—  (optional)" in _summary_color(screen)
        await _enter_until_saved(pilot, screen)

    run_app(scenario)
    assert fake_client.puts == [("/accounts/abc", {})]


@pytest.mark.parametrize(
    "make",
    [
        lambda: EditCategoryScreen({"id": "c1", "name": "Ocio", "color": "#123456"}),
        lambda: _edit_account("#123456"),
    ],
    ids=["category", "account"],
)
def test_a_colour_no_swatch_shows_is_kept_and_never_sent(fake_client, make):
    """A colour from outside the palette (the engine's own, on a row created with
    none) highlights no swatch and `enter` keeps it, even where COLOR is required; the
    summary shows it, and the save leaves it out of the body."""
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
    assert fake_client.puts == [(_PATHS[type(screen)], _unchanged_body(screen))]


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
    # type (empty → the prefilled bank), bank, skip last 4, PEN, empty enter goes on, skip code,
    # color and the PEN pair
    path, body = _run(
        fake_client,
        NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS),
        ["", "BCP", "", "PEN", "", "", "", "", ""],
    )
    assert path == "/accounts"
    assert body == {
        "id": body["id"],
        "kind": "bank",
        "bank_code": "BCP",
        "currencies": [{"currency_code": "PEN"}],
    }  # a skipped last 4, code, colour and opening are left out, never null
    uuid.UUID(body["id"])


def test_new_account_type_person_posts_to_accounts_as_a_person(fake_client):
    """Picking `person` sends the same body to POST /accounts, with `kind: "person"`
    (contract: POST /v1/accounts, "Optional")."""
    path, body = _run(
        fake_client,
        NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS),
        ["person", "Eliana", "PEN", "", "", "", ""],
    )
    assert path == "/accounts"
    assert body == {
        "id": body["id"],
        "name": "Eliana",
        "currencies": [{"currency_code": "PEN"}],
        "kind": "person",
    }


def test_the_currencies_line_offers_the_codes_it_is_given_in_their_order(fake_client):
    """CURRENCIES offers the engine's list as the list screen read it (a third code too),
    and a code outside it matches nothing."""
    path, body = _run(
        fake_client,
        NewAccountScreen(["EUR", "PEN", "USD"], ENGINE_BANKS),
        ["", "BCP", "", "EUR", "", "", "", "", ""],
    )
    assert body["currencies"] == [{"currency_code": "EUR"}]
    screen = NewAccountScreen(["EUR", "PEN", "USD"], ENGINE_BANKS)
    assert screen._field("currencies").choices == [("EUR", "EUR"), ("PEN", "PEN"), ("USD", "USD")]
    assert EditAccountScreen(_ELIANA, ["EUR", "PEN", "USD"], ENGINE_BANKS)._field(
        "currencies"
    ).choices == [
        ("EUR", "EUR"),
        ("PEN", "PEN"),
        ("USD", "USD"),
    ]


def test_edit_account_locks_type_and_currencies(fake_client):
    """`kind` is creation-time-only, so editing shows TYPE read-only, and
    CURRENCIES, which change with their own keys on Manage ▸ Accounts."""
    screen = EditAccountScreen(_ELIANA, ENGINE_CURRENCIES, ENGINE_BANKS)
    assert screen._locked == {"currencies", "type"}
    assert screen._values["type"] == "person"
    assert screen._submit_request()[:2] == ("PUT", "/accounts/abc")
    assert "kind" not in screen._payload()


def test_new_account_required_bank_blocks_submit(fake_client):
    async def scenario(pilot, app):
        screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)
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
# NewCategory, NewAccount, their three Edit* subclasses, NewStatementScreen
# and EditFormScreen — so a regression there is a regression in all of them.


def _run_refused(fake_client, screen, steps, check, *, verb="POST", refusal=None):
    """Drive `screen` through `steps` with the engine refusing the write, then
    run `check(pilot, screen, shown)` **inside** the pilot, `shown` being what the
    form's refusal block reads (`refusal_block`); no `Failed` toast is up.

    The check has to happen there: leaving the `run_test` block shuts the app
    down and detaches every screen, so `is_attached` and the mounted widgets can
    only be read while it is up.

    The block is what proves `_failed` ran at all — `run_write` hands `on_error`
    back to the UI thread and the callback leaves no other edge.
    """
    fake_client.errors[verb] = refusal or EngineError(
        "CONFLICT", "that name is taken", None, 409, {}
    )

    async def scenario(pilot, app):
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in steps:
            _enter(screen, text)
        await wait_for(pilot, lambda: refusal_block(screen), message="no refusal block shown")
        await pilot.pause()
        assert no_failed_toast(app)
        await check(pilot, screen, refusal_block(screen))

    run_app(scenario, toasts=True)


def test_a_refused_create_says_so_keeps_the_screen_and_can_be_submitted_again(fake_client):
    """The engine's envelope reaches the user and the form stays put.

    Dismissing on failure would throw away everything typed and leave the
    message nowhere to be read — the same rule the LOG bar follows.
    """

    async def check(pilot, screen, shown):
        assert shown == "Failed\nCONFLICT — that name is taken"
        assert screen.is_attached  # never dismissed
        # the typed text survives verbatim; the `#` is stripped in _payload(), not here
        assert screen._values["name"] == "#groceries"
        # `action_submit` put "Creating…" in the hint; the failure restores it
        hint = str(screen.query_one("#hint", Static).content)
        assert "Creating" not in hint
        assert hint == screen._hint_for(screen._key)
        # `_submitting` is released, so the form submits again
        assert screen._submitting is False
        fake_client.errors.clear()
        screen.action_submit()
        await wait_for(
            pilot,
            lambda: fake_client.posts,
            message="a second submit after a failure never reached the engine",
        )

    _run_refused(fake_client, NewHashtagScreen(), ["#groceries"], check)


def _keyed(code: str, key: str, reason: str, message: str) -> EngineError:
    """A refusal keyed by the thing refused (contract: "Error reasons")."""
    status = 422 if code in ("LIMIT_REACHED", "VALIDATION_ERROR") else 409
    return EngineError(code, message, {key: "stand-in field words"}, status, {}, {key: reason})


def _eliana() -> EditAccountScreen:
    return EditAccountScreen(_ELIANA, ENGINE_CURRENCIES, ENGINE_BANKS)


@pytest.mark.parametrize(
    ("make", "steps", "verb", "refusal", "line"),
    [
        (
            _eliana,
            ["Eliana Vega", "", "", ""],  # name, colour, opening, as of
            "PUT",
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
        # a user category or hashtag cannot take a system row's name
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
        "name-exists",
        "cap-reached",
        "reserved-category-name-rename",
    ],
)
def test_a_refusal_on_a_form_ends_with_its_next_step(fake_client, make, steps, verb, refusal, line):
    """The refusal block is the engine's words, then the line picked for its
    reason; the form stays open with what was typed."""

    async def check(pilot, screen, shown):
        key = next(iter(refusal.fields))
        assert shown == (
            f"Failed\n{refusal.code} — {refusal.message}\n  {key}: stand-in field words\n\n{line}"
        )
        assert screen.is_attached

    _run_refused(fake_client, make(), steps, check, verb=verb, refusal=refusal)


#: The engine's words on a renamed system row
#: (contract: PUT /v1/categories/{category_id}, "A system category keeps its name")
#: (contract: PUT /v1/hashtags/{hashtag_id}, "The pending hashtag keeps its name").
_NAME_FIXED = "Must be the current name: a system record keeps its name."


@pytest.mark.parametrize(
    ("make", "steps", "path"),
    [
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
    ids=["opening", "pending-hashtag"],
)
def test_a_system_rows_rename_shows_the_engines_words(fake_client, make, steps, path):
    """A system category or the pending hashtag keeps its name: the engine
    refuses a rename with `SYSTEM_NAME_FIXED` on `name`. Manage offers no `e`
    on these rows, so only a form opened another way meets it. The block is the
    engine's words whole, then the built-in hashtag's line, and the
    form stays open with what was typed."""
    refusal = EngineError(
        "VALIDATION_ERROR",
        "Request validation failed.",
        {"name": _NAME_FIXED},
        422,
        {},
        {"name": "SYSTEM_NAME_FIXED"},
    )

    async def check(pilot, screen, shown):
        assert shown == (
            f"Failed\nVALIDATION_ERROR — Request validation failed.\n  name: {_NAME_FIXED}\n\n"
            "Built-in names never change: press esc to leave it as it is."
        )
        assert screen.is_attached
        assert screen._values["name"] == steps[0]
        assert ("PUT", path) in fake_client.requests

    _run_refused(fake_client, make(), steps, check, verb="PUT", refusal=refusal)


# ---------------------------------------------------------------------------
# field navigation — the shared `form_bindings` keymap, pressed for real
# ---------------------------------------------------------------------------
#
# EditAccountScreen is the form with read-only fields: TYPE and CURRENCY are
# locked, so the editable sequence is a bank account's STATEMENT CODE (plain text; a
# person's form starts on NAME), COLOR (a palette list), then OPENING
# and AS OF (plain text), on a bank account and a person alike. Every bar form takes the same keymap
# from FormScreen.

_ACCOUNT = account_with_currencies(id="abc", name="Eliana")  # a bank account: no NAME line


def _land(screen, key):
    """Put the cursor on `key`."""
    screen._current = screen._sequence().index(key)
    screen._refresh_bar()
    screen._refresh_view()


def _navigate(steps, start="statement_code"):
    """Push the account edit form, then run each `(key, expected field)` step."""

    async def scenario(pilot, app):
        screen = EditAccountScreen(_ACCOUNT, ENGINE_CURRENCIES, ENGINE_BANKS)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        assert screen._key == "bank"  # the first editable field
        _land(screen, start)
        for key, expected in steps:
            await pilot.press(key)
            await pilot.pause()
            assert screen._key == expected, f"after {key}: {screen._key}"
            # the form's binding wins over the screen's focus-cycling: the bar
            # still has focus after every key.
            assert app.focused is screen.query_one("#bar", Input)

    run_app(scenario)


def test_tab_and_shift_tab_move_fields_skipping_read_only_ones():
    """tab → next editable field, shift+tab → previous; both stop at the ends; the
    ctrl arrows move the same way."""
    _navigate(
        [
            ("ctrl+down", "color"),
            ("ctrl+up", "statement_code"),
            ("tab", "color"),
            ("tab", "opening:PEN"),
            ("tab", "as_of:PEN"),
            ("tab", "as_of:PEN"),  # no editable field further on: stays
            ("shift+tab", "opening:PEN"),
            ("shift+tab", "color"),
            ("shift+tab", "statement_code"),
            ("shift+tab", "new_card"),  # skips locked CURRENCIES
            ("shift+tab", "since"),
            ("shift+tab", "last4"),
            ("shift+tab", "bank"),
            ("shift+tab", "bank"),  # TYPE is locked: stays
        ]
    )


def test_plain_arrows_walk_a_list_and_move_fields_without_one():
    """STATEMENT CODE has no list, so `↓` moves on; COLOR's palette
    list takes `↑`/`↓` until it empties, and then `↑` moves back."""

    async def scenario(pilot, app):
        screen = EditAccountScreen(_ACCOUNT, ENGINE_CURRENCIES, ENGINE_BANKS)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        _land(screen, "statement_code")
        assert screen._suggestions == []
        await pilot.press("down")  # STATEMENT CODE: no list → next field
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
        # on COLOR the palette list is open; tab and shift+tab still move fields
        await pilot.press("tab")
        await pilot.pause()
        assert screen._key == "color" and screen._suggestions
        await pilot.press("shift+tab")
        await pilot.pause()
        assert screen._key == "statement_code"

    run_app(scenario)


# ---------------------------------------------------------------------------
# New account's CURRENCIES — picked as the Edit form's HASHTAGS picks hashtags, the
# account and its currencies sent as one `POST /accounts`
# (contract: POST /v1/accounts, "Required").
# ---------------------------------------------------------------------------


def _summary_lines(screen) -> list[str]:
    text = render_text(screen._summary_renderable(), width=100)
    return [" ".join(line.split()) for line in text.splitlines()]


def _listed(screen) -> list[str]:
    rendered = screen._suggest_renderable()
    return [
        line.plain.strip()
        for line in getattr(rendered, "renderables", [rendered])
        if line.plain.strip()
    ]


def test_new_bank_account_in_two_currencies_is_one_post_with_both(fake_client):
    """A BCP account in PEN and USD with its code: one `POST /accounts` holding both
    currencies in the order picked, the code and no name; nothing else is sent."""
    screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("enter")  # TYPE keeps bank
        await pilot.press("enter", "enter")  # BANK takes BCP, LAST 4 skipped
        assert screen._key == "currencies"
        assert str(screen.query_one("#field").content) == "CURRENCIES"
        assert str(screen.query_one("#hint", Static).content) == (
            "type a code · ↑↓ highlight · enter adds & stays · empty enter = done"
        )
        await pilot.press(*"pen", "enter")  # adds PEN, stays for another
        await pilot.pause()
        assert screen._key == "currencies"
        assert screen.query_one("#bar", Input).value == ""
        assert _listed(screen) == ["USD"] and _highlighted(screen) == ["USD"]
        assert "currencies PEN" in _summary_lines(screen)
        await pilot.press("u", "enter")  # adds USD: nothing left to list
        await pilot.pause()
        assert _listed(screen) == []
        assert "currencies PEN · USD" in _summary_lines(screen)
        await pilot.press("enter")  # an empty enter goes on
        await pilot.pause()
        assert screen._key == "statement_code"
        # the code, COLOR, then the two pairs: the last `as of` line creates
        await pilot.press(*"VIS", *["enter"] * 6)
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    assert fake_client.requests == [("POST", "/accounts")]
    path, body = fake_client.posts[0]
    assert body == {
        "id": body["id"],
        "kind": "bank",
        "bank_code": "BCP",
        "currencies": [{"currency_code": "PEN"}, {"currency_code": "USD"}],
        "statement_code": "VIS",
    }


def test_new_person_is_one_post_with_kind_person_and_no_code_line(fake_client):
    """Ana Ejemplo, a person in PEN: no STATEMENT CODE line, one `POST /accounts`
    with `kind: "person"` and no code; nothing goes to `/people`."""
    screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await enter_values(pilot, "person")
        assert screen._sequence() == ["type", "name", "currencies", "color"]
        await enter_values(pilot, "Ana Ejemplo", "PEN", "")
        await pilot.pause()
        assert screen._key == "color"  # past CURRENCIES, straight to COLOR
        await pilot.press("enter", "enter", "enter")  # COLOR, then the PEN pair: creates
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    assert fake_client.requests == [("POST", "/accounts")]
    path, body = fake_client.posts[0]
    assert body == {
        "id": body["id"],
        "name": "Ana Ejemplo",
        "currencies": [{"currency_code": "PEN"}],
        "kind": "person",
    }
    assert "currency_code" not in body


def test_an_unmatched_code_adds_nothing_and_the_bar_stays(fake_client, monkeypatch):
    notes: list = []
    monkeypatch.setattr(NewAccountScreen, "notify", lambda self, m, **kw: notes.append(m))

    async def scenario(pilot, app):
        screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("enter", "enter", "enter", *"EUR", "enter")
        await pilot.pause()
        assert screen._key == "currencies"
        assert screen.query_one("#bar", Input).value == "EUR"
        assert "currencies" not in screen._values

    run_app(scenario)
    assert notes == ["No currencies match “EUR”."]


def _save_with_typed_currencies(fake_client, typed: list[str], after=None):
    """Open the New account form, pick BCP, type `typed` on CURRENCIES (each
    entry followed by `enter` except the last, which stays typed), then `ctrl+s`."""

    async def scenario(pilot, app):
        screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("enter", "enter", "enter")
        for code in typed[:-1]:
            await pilot.press(*code, "enter")
        await pilot.press(*typed[-1], "ctrl+s")
        await pilot.pause()
        if after:
            after(screen)

    run_app(scenario)


def test_a_typed_code_follows_earlier_picks_on_ctrl_s(fake_client):
    _save_with_typed_currencies(fake_client, ["USD", "PEN"])
    assert fake_client.posts[0][1]["currencies"] == [
        {"currency_code": "USD"},
        {"currency_code": "PEN"},
    ]


def test_a_typed_code_matching_nothing_refuses_ctrl_s(fake_client, monkeypatch):
    notes: list = []
    monkeypatch.setattr(NewAccountScreen, "notify", lambda self, m, **kw: notes.append(m))
    bars: list = []
    _save_with_typed_currencies(
        fake_client, ["PEN", "EUR"], lambda sc: bars.append(sc.query_one("#bar", Input).value)
    )
    assert bars == ["EUR"]
    assert notes == ["No currencies match “EUR”."]
    assert not fake_client.calls


def test_no_currency_picked_blocks_the_save(fake_client, monkeypatch):
    """CURRENCIES is a required line, as BANK is: an empty enter goes on, and
    the save stops at the form's one required check, sending nothing."""
    notes: list = []
    monkeypatch.setattr(NewAccountScreen, "notify", lambda self, m, **kw: notes.append(m))

    async def scenario(pilot, app):
        screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("enter", "enter", "enter", "enter")
        await pilot.pause()
        assert screen._key == "statement_code"
        assert "currencies — *" in _summary_lines(screen)
        await pilot.press("ctrl+s")
        await pilot.pause()

    run_app(scenario)
    assert notes == ["Currencies is required."]
    assert not fake_client.calls


@pytest.mark.parametrize(
    ("refusal", "line", "bar"),
    [
        (
            _keyed(
                "VALIDATION_ERROR",
                "currencies.1.currency_code",
                "DUPLICATE_CURRENCY",
                "stand-in",
            ),
            "currencies",
            "",
        ),
        (
            _keyed("VALIDATION_ERROR", "currencies", "OUT_OF_RANGE", "stand-in"),
            "currencies",
            "",
        ),
        (
            _keyed("CONFLICT", "last4", "NAME_EXISTS", "An account named 'BCP-5678' exists."),
            "last4",
            "5678",
        ),
    ],
    ids=["duplicate-currency", "currencies", "last4"],
)
def test_a_refusal_on_new_lands_on_its_line_in_the_engines_words(fake_client, refusal, line, bar):
    """The block is the engine's words as every failed write reads them, and the
    cursor goes back on the line the refusal names, holding what was typed."""

    async def check(pilot, screen, shown):
        assert shown == f"Failed\n{format_error(refusal)}"
        assert screen.is_attached
        assert screen._key == line
        assert screen.query_one("#bar", Input).value == bar
        assert screen._values["currencies"] == ["PEN", "USD"]

    steps = ["", "BCP", "5678", "PEN", "USD", "", "", "", "", "", "", ""]
    _run_refused(
        fake_client,
        NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS),
        steps,
        check,
        refusal=refusal,
    )


def test_a_color_refusal_on_new_lands_on_color_in_the_engines_words(fake_client):
    """Saved from BANK with ctrl+s, the refusal moves the cursor to COLOR; the
    block is the engine's words and the colour picked is still held."""
    refusal = _keyed("VALIDATION_ERROR", "color", "INVALID_COLOR", "Color must be a hex.")
    fake_client.errors["POST"] = refusal
    screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in ["", "BCP", "", "PEN", "USD", "", ""]:
            _enter(screen, text)
        assert screen._key == "color"
        screen._values["color"] = "#5ab87a"
        screen._current = screen._sequence().index("bank")
        screen._refresh_bar()
        assert screen._key == "bank"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen), message="no refusal block shown")
        await pilot.pause()
        assert refusal_block(screen) == f"Failed\n{format_error(refusal)}"
        assert no_failed_toast(app)
        assert screen.is_attached
        assert screen._key == "color"
        assert screen._values["color"] == "#5ab87a"
        assert _highlighted(screen) == ["██ green"]

    run_app(scenario, toasts=True)
