"""The number format setting: read at launch, shown and asked on System ▸ Auth & profile,
saved through `PUT /auth/settings` (contract: PUT /v1/auth/settings)."""

import httpx
import pytest
import respx
from textual.widgets import Static

from expense import reads
from expense import region as region_module
from expense.config import Config, load
from expense.errors import EngineError, format_error
from expense.http import ExpenseClient
from expense.number_format import NumberFormat, current_format
from expense.reads import fetch_number_format  # bound before the conftest pins the module name
from expense.tui import app as tui_app
from expense.tui.screens.help import HelpModal
from expense.tui.screens.modals import QuestionModal
from expense.tui.screens.system import AuthScreen
from tests.unit.helpers import (
    ENGINE_URL,
    LateAnswer,
    app_notes,
    error_body,
    leave_then_answer,
    render_text,
    run_app,
    screen_lines,
    stub_home_month,
    wait_for,
)

DOT = NumberFormat.DOT_DECIMAL
COMMA = NumberFormat.COMMA_DECIMAL
CFG = Config(engine_url="https://engine.example", token="ewe_pat_test123", main_currency="PEN")
FOLLOW = "Follow this Mac"


def _me(number_format) -> dict:
    return {
        "user": {"display_name": "Alex", "id": "u1"},
        "settings": {"main_currency": "PEN", "number_format": number_format},
    }


def _auth(fake_client, monkeypatch, number_format=None) -> None:
    fake_client.get_responses["/auth/me"] = _me(number_format)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: CFG)
    monkeypatch.setattr("expense.config.save", lambda c: None)


def _text(app) -> str:
    """The screen as drawn, each run of spaces one space: a table's padding is not the test."""
    return " ".join("\n".join(screen_lines(app)).split())


async def _open_auth(pilot, app) -> AuthScreen:
    screen = AuthScreen()
    await app.push_screen(screen)
    await wait_for(pilot, lambda: "number format" in _text(app))
    return screen


async def _ask(pilot, app) -> QuestionModal:
    await pilot.press("f")
    await wait_for(pilot, lambda: isinstance(app.screen, QuestionModal))
    return app.screen


# ---- the launch --------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [("1,234.56", DOT), ("1.234,56", COMMA), (None, None), ("1 234,56", None)],
)
def test_the_accounts_setting_is_read_from_auth_me(configured, value, expected):
    with respx.mock:
        respx.get(f"{ENGINE_URL}/v1/auth/me").respond(json=_me(value))
        assert fetch_number_format(load()) is expected


def test_no_read_of_the_setting_is_no_pick(configured):
    with respx.mock:
        respx.get(f"{ENGINE_URL}/v1/auth/me").respond(404, json=error_body("NOT_FOUND"))
        assert fetch_number_format(load()) is None


def _launch(monkeypatch, region_format) -> NumberFormat:
    monkeypatch.setattr(tui_app.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tui_app.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(tui_app, "get_verbose", lambda ctx: False)
    monkeypatch.setattr(tui_app.ExpenseApp, "run", lambda self, **kw: None)
    monkeypatch.setattr(region_module, "read_region_format", lambda: region_format)
    monkeypatch.setattr(reads, "fetch_number_format", fetch_number_format)
    tui_app.launch(ctx=None)
    return current_format()


@pytest.mark.parametrize(
    ("value", "region_format", "expected"),
    [
        ("1.234,56", DOT, COMMA),
        ("1,234.56", COMMA, DOT),
        (None, COMMA, COMMA),
        (None, DOT, DOT),
    ],
    ids=["comma-setting", "dot-setting", "null-follows-comma-region", "null-follows-dot-region"],
)
def test_the_launch_sets_the_session_format(
    configured, monkeypatch, capsys, value, region_format, expected
):
    with respx.mock:
        respx.get(f"{ENGINE_URL}/v1/auth/me").respond(json=_me(value))
        assert _launch(monkeypatch, region_format) is expected


def test_an_engine_that_cannot_be_read_leaves_the_region(configured, monkeypatch, capsys):
    with respx.mock:
        respx.get(f"{ENGINE_URL}/v1/auth/me").respond(500, json=error_body("INTERNAL"))
        assert _launch(monkeypatch, COMMA) is COMMA


def test_no_settings_file_leaves_the_region(monkeypatch, capsys):
    assert _launch(monkeypatch, COMMA) is COMMA


# ---- the row -----------------------------------------------------------------
@pytest.mark.parametrize(
    ("setting", "region_format", "region_name", "shown", "hidden"),
    [
        (
            None,
            DOT,
            "English (Peru)",
            "number format 1,234.56 · follows this Mac (English (Peru))",
            None,
        ),
        (
            None,
            COMMA,
            "Spanish (Spain)",
            "number format 1.234,56 · follows this Mac (Spanish (Spain))",
            None,
        ),
        (None, DOT, None, "number format 1,234.56 · follows this Mac", "follows this Mac ("),
        (
            "1.234,56",
            DOT,
            "English (Peru)",
            "number format 1.234,56 · your setting",
            "follows this Mac",
        ),
    ],
    ids=["follows-the-region", "in-its-own-format", "region-with-no-name", "setting"],
)
def test_the_row_shows_the_format_and_where_it_comes_from(
    fake_client, monkeypatch, setting, region_format, region_name, shown, hidden
):
    _auth(fake_client, monkeypatch, setting)
    monkeypatch.setattr(region_module, "read_region_format", lambda: region_format)
    monkeypatch.setattr(region_module, "read_region_name", lambda: region_name)

    async def scenario(pilot, app):
        await _open_auth(pilot, app)
        assert shown in _text(app)
        assert hidden is None or hidden not in _text(app)

    run_app(scenario)


def test_f_is_in_the_footer_and_the_card(fake_client, monkeypatch):
    _auth(fake_client, monkeypatch)

    async def scenario(pilot, app):
        await _open_auth(pilot, app)
        await wait_for(pilot, lambda: "f Number format" in screen_lines(app)[-1])
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: isinstance(app.screen, HelpModal))
        assert "Number format" in render_text(app.screen.query_one("#help-card", Static).content)

    run_app(scenario, size=(100, 32))


# ---- the question ------------------------------------------------------------
def _modal_text(app) -> str:
    return render_text(*(s.content for s in app.screen.query_one("#modal").query(Static)), width=60)


def test_f_asks_with_the_three_choices_as_drawn(fake_client, monkeypatch):
    _auth(fake_client, monkeypatch)

    async def scenario(pilot, app):
        await _open_auth(pilot, app)
        await _ask(pilot, app)
        text = _modal_text(app)
        assert "Number format" in text
        assert "Follow this Mac      1,234.56 now" in text
        assert "1,234.56             dot for decimals" in text
        assert "1.234,56             comma for decimals" in text
        assert "⏎ Save  esc Cancel" in text

    run_app(scenario)


@pytest.mark.parametrize(
    ("setting", "cursor"), [(None, FOLLOW), ("1,234.56", "dot"), ("1.234,56", "comma")]
)
def test_the_cursor_opens_on_the_current_choice(fake_client, monkeypatch, setting, cursor):
    _auth(fake_client, monkeypatch, setting)

    async def scenario(pilot, app):
        await _open_auth(pilot, app)
        modal = await _ask(pilot, app)
        picked = modal.values()["number_format"]
        assert cursor in picked

    run_app(scenario)


@pytest.mark.parametrize(
    ("downs", "body", "after"),
    [
        (0, {"number_format": None}, DOT),
        (1, {"number_format": "1,234.56"}, DOT),
        (2, {"number_format": "1.234,56"}, COMMA),
    ],
    ids=["follow-this-mac", "dot", "comma"],
)
def test_enter_saves_one_put_with_the_exact_body(fake_client, monkeypatch, downs, body, after):
    _auth(fake_client, monkeypatch, "1.234,56" if downs == 0 else None)

    async def scenario(pilot, app):
        await _open_auth(pilot, app)
        await _ask(pilot, app)
        # the cursor opens on the account's pick: go to the top, then down
        await pilot.press("up", "up")
        await pilot.press(*["down"] * downs)
        await pilot.press("enter")
        await wait_for(pilot, lambda: fake_client.puts)
        await wait_for(pilot, lambda: not isinstance(app.screen, QuestionModal))
        assert fake_client.puts == [("/auth/settings", body)]
        assert current_format() is after

    run_app(scenario)


@respx.mock
def test_the_save_goes_through_the_shared_write_path_with_a_key(configured, monkeypatch):
    respx.get(f"{ENGINE_URL}/v1/auth/me").respond(json=_me(None))
    put = respx.put(f"{ENGINE_URL}/v1/auth/settings").respond(json=_me("1.234,56")["settings"])

    async def scenario(pilot, app):
        await _open_auth(pilot, app)
        await _ask(pilot, app)
        await pilot.press("down", "down", "enter")
        await wait_for(pilot, lambda: put.called)
        assert put.call_count == 1
        request = put.calls.last.request
        assert request.headers["X-Idempotency-Key"]
        assert request.content == b'{"number_format":"1.234,56"}'

    run_app(scenario)


def test_esc_sends_nothing_and_changes_nothing(fake_client, monkeypatch):
    _auth(fake_client, monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_auth(pilot, app)
        await _ask(pilot, app)
        await pilot.press("down", "escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert fake_client.puts == []
        assert current_format() is DOT

    run_app(scenario)


# ---- the effect --------------------------------------------------------------
def test_home_draws_its_amounts_in_the_saved_format(fake_client, monkeypatch):
    stub_home_month(monkeypatch)
    _auth(fake_client, monkeypatch)

    async def scenario(pilot, app):
        await wait_for(pilot, lambda: "5,145.82" in _text(app))
        home_screen = app.screen
        await _open_auth(pilot, app)
        await _ask(pilot, app)
        await pilot.press("down", "down", "enter")
        await wait_for(pilot, lambda: not isinstance(app.screen, QuestionModal))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is home_screen)
        await wait_for(pilot, lambda: "5.145,82" in _text(app))
        assert "5,145.82" not in _text(app)

    run_app(scenario, size=(120, 40))


# ---- the launch bound ----------------------------------------------------------
class _Spy(ExpenseClient):
    built: list = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _Spy.built.append(self._client.timeout)


@pytest.mark.parametrize("error", [httpx.ConnectTimeout, httpx.ReadTimeout])
def test_the_launch_read_waits_three_seconds_and_a_timeout_leaves_the_region(
    configured, monkeypatch, error
):
    _Spy.built = []
    monkeypatch.setattr(reads, "ExpenseClient", _Spy)
    with respx.mock:
        respx.get(f"{ENGINE_URL}/v1/auth/me").mock(side_effect=error("slow"))
        assert fetch_number_format(load()) is None
    assert _Spy.built
    assert all(t.connect == 3.0 and t.read == 3.0 for t in _Spy.built)


# ---- a save left behind --------------------------------------------------------
def _leave_after_saving(fake_client, monkeypatch, refusal) -> list:
    _auth(fake_client, monkeypatch)
    late = LateAnswer(fake_client, "put", refusal)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = await _open_auth(pilot, app)
        await _ask(pilot, app)
        await pilot.press("down", "down", "enter")
        await leave_then_answer(pilot, app, screen, late, notes)
        result.extend(notes)

    run_app(scenario)
    return result


def test_a_save_answered_after_leaving_still_sets_the_format_and_says_so(fake_client, monkeypatch):
    notes = _leave_after_saving(fake_client, monkeypatch, None)
    assert [(title, message) for title, message, _ in notes] == [("", "Number format saved.")]
    assert current_format() is COMMA


def test_a_save_refused_after_leaving_says_not_saved_in_the_engines_words(fake_client, monkeypatch):
    refusal = EngineError("VALIDATION_ERROR", "Invalid request.", None, 422, {})
    [(title, message, options)] = _leave_after_saving(fake_client, monkeypatch, refusal)
    assert title == "Not saved · Number format"
    assert message == format_error(refusal)
    assert options["severity"] == "error"
    assert current_format() is DOT


# ---- not provisioned -----------------------------------------------------------
def test_f_asks_nothing_and_is_not_in_the_footer_before_the_account_exists(
    fake_client, monkeypatch
):
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: CFG)  # /auth/me 404s

    async def scenario(pilot, app):
        screen = AuthScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: "Bootstrap" in screen_lines(app)[-1])
        assert "Number format" not in screen_lines(app)[-1]
        await pilot.press("f")
        await pilot.pause()
        assert app.screen is screen and fake_client.puts == []

    run_app(scenario, size=(100, 32))


# ---- a refusal ---------------------------------------------------------------
def test_a_refusal_shows_in_the_engines_words_and_changes_nothing(fake_client, monkeypatch):
    """`INVALID_FORMAT` on `number_format`, the engine's own words under the question."""
    _auth(fake_client, monkeypatch)
    words = 'Must be "1,234.56", "1.234,56" or null.'
    fake_client.errors["PUT"] = EngineError(
        "VALIDATION_ERROR",
        "Invalid request.",
        {"number_format": words},
        422,
        error_body("VALIDATION_ERROR", "Invalid request.", {"number_format": words}),
        {"number_format": "INVALID_FORMAT"},
    )

    async def scenario(pilot, app):
        await _open_auth(pilot, app)
        modal = await _ask(pilot, app)
        await pilot.press("down", "down", "enter")
        await wait_for(pilot, lambda: "Must be" in _modal_text(app))
        assert app.screen is modal  # still asking
        assert "VALIDATION_ERROR" in _modal_text(app)
        assert current_format() is DOT  # nothing changed
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, QuestionModal))
        assert "follows this Mac" in _text(app)

    run_app(scenario)
