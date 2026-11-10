"""First-time setup — the screen the app opens on with no usable settings file.

The engine is mocked with respx, so the real HTTP client (idempotency key and
all) runs. Every address typed here is `ENGINE_URL` (a public name the network
backstop would catch), never the local engine's.
"""

import ast
import json
import os
import re
import threading
from pathlib import Path

import httpx
import pytest
import respx
from textual.widgets import Input, Label, Static

from expense import config as config_module
from expense.reads import fetch_body
from expense.tui import app as tui_app
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.setup import (
    ASKING,
    FAILED_NEXT,
    REFUSED_NEXT,
    UNREACHABLE_NEXT,
    SetupScreen,
)
from tests.unit.helpers import (
    ENGINE_URL,
    error_response,
    render_text,
    run_app,
    stub_home_month,
    wait_for,
)

# A fake key: the middle is filler, so masking must show only "wxyz" at the end.
KEY = "ewe_pat_" + "a" * 12 + "wxyz"
ME = {
    "user": {"id": "u-1", "display_name": "Alex"},
    "settings": {"main_currency": "PEN", "display_timezone": "America/Lima"},
}


# ---- helpers ------------------------------------------------------------------
def _text(screen, selector: str) -> str:
    return render_text(screen.query_one(selector, Static).content, width=100)


def _label(screen) -> str:
    return str(screen.query_one("#field", Label).content)


def _bar(screen) -> Input:
    return screen.query_one("#bar", Input)


def _footer(screen) -> list[str]:
    return [
        f"{a.binding.key} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show
    ]


async def _type(pilot, screen, text: str) -> None:
    """What the owner types on the bar — replacing what it held."""
    _bar(screen).value = text
    await pilot.pause()


def _health_ok() -> respx.Route:
    return respx.get(f"{ENGINE_URL}/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )


def _settings_file():
    return config_module.config_path()


async def _address_and_key(pilot, screen, key: str = KEY) -> None:
    """Type ENGINE_URL on the address, ⏎, the key, ⏎."""
    await _type(pilot, screen, ENGINE_URL)
    await pilot.press("enter")
    await wait_for(pilot, lambda: _label(screen) == "KEY")
    await _type(pilot, screen, key)
    await pilot.press("enter")


# ---- where the app opens --------------------------------------------------------
def _launch(monkeypatch) -> dict:
    seen: dict = {}
    monkeypatch.setattr(tui_app.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tui_app.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(tui_app, "get_verbose", lambda ctx: False)
    monkeypatch.setattr(
        tui_app.ExpenseApp, "run", lambda self, **kw: seen.update(setup=self._setup)
    )
    tui_app.launch(ctx=None)
    return seen


def test_launch_opens_setup_with_no_settings_file(monkeypatch, capsys):
    assert not _settings_file().exists()  # the autouse fixture's missing file
    assert _launch(monkeypatch) == {"setup": True}


@pytest.mark.parametrize(
    "content",
    [b'{"engine_url": "https://x', b"[]", b'{"token": "t"}', b"\xff\xfe\x00garbage"],
    ids=["half-written", "not-an-object", "no-address", "not-text"],
)
def test_launch_opens_setup_when_the_settings_file_cannot_be_read(monkeypatch, capsys, content):
    _settings_file().write_bytes(content)
    assert _launch(monkeypatch) == {"setup": True}


def test_launch_opens_home_with_a_usable_settings_file(configured, monkeypatch, capsys):
    assert _launch(monkeypatch) == {"setup": False}


def test_load_usable_is_none_for_a_folder_in_the_files_place():
    _settings_file().mkdir()
    assert config_module.load_usable() is None


# ---- the first thing seen -------------------------------------------
def test_setup_opens_on_the_address_filled_with_the_local_engine():
    async def scenario(pilot, app):
        screen = app.screen
        assert isinstance(screen, SetupScreen)
        assert "◈ EXPENSE WORLD  ▸  Setup" in render_text(screen.query_one("#crumb").render())
        assert _label(screen) == "ENGINE ADDRESS"
        assert _bar(screen).value == config_module.LOCAL_ENGINE_URL
        assert _bar(screen).password is False
        assert _text(screen, "#hint").strip() == (
            "where your engine runs · enter to accept, or type another address"
        )
        summary = _text(screen, "#summary")
        assert f"address  {config_module.LOCAL_ENGINE_URL}  *" in summary
        assert "key      —  *" in summary
        assert _footer(screen) == ["escape Quit", "ctrl+s Connect", "tab Field"]

    run_app(scenario, setup=True)


def test_enter_accepts_the_offered_address_and_asks_for_the_key():
    async def scenario(pilot, app):
        screen = app.screen
        await pilot.press("enter")
        await wait_for(pilot, lambda: _label(screen) == "KEY")
        assert _bar(screen).value == ""
        assert _bar(screen).password is True  # hidden as you type
        assert "starts with ewe_pat_ · hidden as you type" in _text(screen, "#hint")
        summary = _text(screen, "#summary")
        assert f"address  {config_module.LOCAL_ENGINE_URL}\n" in summary  # accepted: no *
        assert "key      —  *" in summary
        assert not _settings_file().exists()

    with respx.mock:  # nothing may be sent by accepting an address
        run_app(scenario, setup=True)
        assert not respx.calls


# ---- the key works and the engine knows it --------------------------------
@pytest.mark.parametrize("before", [None, b"{ not json"], ids=["no-file", "damaged-file"])
def test_a_working_key_saves_the_settings_and_lands_on_home(monkeypatch, before):
    if before is not None:
        _settings_file().write_bytes(before)
    stub_home_month(monkeypatch)
    release = threading.Event()

    def me(request):
        release.wait(5)
        return httpx.Response(200, json=ME)

    async def scenario(pilot, app):
        screen = app.screen
        notes: list = []
        app.notify = lambda message, **kw: notes.append(message)
        await _address_and_key(pilot, screen)
        # "asking the engine…" while the engine answers; the key shows masked.
        await wait_for(pilot, lambda: _text(screen, "#hint").strip() == ASKING)
        assert "key      ewe_pat_****wxyz" in _text(screen, "#summary")
        if before is None:
            assert not _settings_file().exists()
        else:
            assert _settings_file().read_bytes() == before  # untouched while asking
        release.set()
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        assert notes == ["Connected."]

    with respx.mock:
        _health_ok()
        me_route = respx.get(f"{ENGINE_URL}/v1/auth/me").mock(side_effect=me)
        run_app(scenario, setup=True)
        assert me_route.calls.last.request.headers["Authorization"] == f"Bearer {KEY}"
    path = _settings_file()
    assert json.loads(path.read_text()) == {
        "engine_url": ENGINE_URL,
        "token": KEY,
        "main_currency": "PEN",
        "sheet_account_names": {},
    }
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_the_saved_settings_are_the_ones_the_next_engine_call_uses(monkeypatch):
    """Launch holds "no settings yet"; Setup's save replaces them, no restart."""
    real_ensure_loaded = config_module.ensure_loaded
    stub_home_month(monkeypatch)
    # stub_home_month stubs ensure_loaded; this test needs the real one.
    monkeypatch.setattr("expense.config.ensure_loaded", real_ensure_loaded)
    config_module.hold(None)  # what `launch` holds with no usable settings file

    async def scenario(pilot, app):
        screen = app.screen
        assert config_module.current() is None
        await _address_and_key(pilot, screen)
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        held = config_module.current()
        assert held is not None and (held.engine_url, held.token) == (ENGINE_URL, KEY)
        config_module.config_path().unlink()  # only the held copy can answer now
        fetch_body(config_module.ensure_loaded(), path="/accounts", params=None, verbose=False)

    with respx.mock:
        _health_ok()
        respx.get(f"{ENGINE_URL}/v1/auth/me").mock(return_value=httpx.Response(200, json=ME))
        accounts = respx.get(f"{ENGINE_URL}/v1/accounts").mock(
            return_value=httpx.Response(200, json={"items": []})
        )
        run_app(scenario, setup=True)
        request = accounts.calls.last.request
        assert str(request.url).startswith(ENGINE_URL)
        assert request.headers["Authorization"] == f"Bearer {KEY}"


def test_ctrl_s_connects_from_any_field(monkeypatch):
    stub_home_month(monkeypatch)

    async def scenario(pilot, app):
        screen = app.screen
        await _type(pilot, screen, ENGINE_URL)
        await pilot.press("tab")
        await _type(pilot, screen, KEY)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))

    with respx.mock:
        _health_ok()
        respx.get(f"{ENGINE_URL}/v1/auth/me").mock(return_value=httpx.Response(200, json=ME))
        run_app(scenario, setup=True)
    assert config_module.load().token == KEY


# ---- when it does not work -------------------------------------------------
@pytest.mark.parametrize("down", ["/health", "/v1/auth/me"])
def test_engine_not_answering_goes_back_to_the_address_and_keeps_the_key(down):
    """The engine does not answer the health check, or answers it and then cannot be
    reached for the key check: either way the address is asked again, the key kept."""

    async def scenario(pilot, app):
        screen = app.screen
        await _address_and_key(pilot, screen)
        await wait_for(pilot, lambda: UNREACHABLE_NEXT in _text(screen, "#hint"))
        assert _text(screen, "#hint").splitlines() == [
            f"could not reach engine at {ENGINE_URL}{down} (is it running?)",
            UNREACHABLE_NEXT,
        ]
        assert _label(screen) == "ENGINE ADDRESS"
        assert _bar(screen).value == ENGINE_URL
        summary = _text(screen, "#summary")
        assert f"address  {ENGINE_URL}  *" in summary
        assert "key      ewe_pat_****wxyz" in summary  # kept

    with respx.mock:
        if down == "/health":
            respx.get(f"{ENGINE_URL}/health").mock(side_effect=httpx.ConnectError("refused"))
            me = respx.get(f"{ENGINE_URL}/v1/auth/me")
        else:
            _health_ok()
            me = respx.get(f"{ENGINE_URL}/v1/auth/me").mock(side_effect=httpx.ConnectError("gone"))
        run_app(scenario, setup=True)
        assert me.called == (down != "/health")  # no key check when the health check fails
    assert not _settings_file().exists()


def test_a_refused_key_shows_the_engines_words_and_an_empty_key_line():
    async def scenario(pilot, app):
        screen = app.screen
        await _address_and_key(pilot, screen)
        await wait_for(pilot, lambda: REFUSED_NEXT in _text(screen, "#hint"))
        assert _text(screen, "#hint").splitlines() == [
            "UNAUTHORIZED — Token is not valid.",
            "nothing was saved · type the key again, then enter",
        ]
        assert _label(screen) == "KEY"
        assert _bar(screen).value == ""
        summary = _text(screen, "#summary")
        assert f"address  {ENGINE_URL}\n" in summary
        assert "key      —  *" in summary

    with respx.mock:
        _health_ok()
        respx.get(f"{ENGINE_URL}/v1/auth/me").mock(
            return_value=error_response(401, "UNAUTHORIZED", "Token is not valid.")
        )
        run_app(scenario, setup=True)
    assert not _settings_file().exists()


def test_not_an_address_is_refused_before_anything_is_sent():
    async def scenario(pilot, app):
        screen = app.screen
        await _type(pilot, screen, "127.0.0.1:8000")
        await pilot.press("enter")
        await wait_for(pilot, lambda: "full URL" in _text(screen, "#hint"))
        assert _text(screen, "#hint").splitlines() == [
            "engine URL must be a full URL with scheme and host,",
            f"e.g. {config_module.LOCAL_ENGINE_URL}",
        ]
        assert _label(screen) == "ENGINE ADDRESS"
        assert _bar(screen).value == "127.0.0.1:8000"
        assert "address  —  *" in _text(screen, "#summary")
        # ctrl+s is refused the same way: still nothing sent
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert _label(screen) == "ENGINE ADDRESS"

    with respx.mock:
        run_app(scenario, setup=True)
        assert not respx.calls
    assert not _settings_file().exists()


def test_esc_quits_through_the_shared_quit_and_saves_nothing(monkeypatch):
    asked: list[bool] = []

    async def scenario(pilot, app):
        real = app.action_quit

        async def action_quit():
            asked.append(True)
            await real()

        monkeypatch.setattr(app, "action_quit", action_quit)
        await pilot.press("escape")
        await wait_for(pilot, lambda: not app.is_running)

    run_app(scenario, setup=True)
    assert asked == [True]
    assert not _settings_file().exists()


# ---- a key the engine has never seen ------------------------------------------
@pytest.fixture
def lima(monkeypatch):
    monkeypatch.setattr("expense.dates.detect_timezone", lambda *a, **k: "America/Lima")


@pytest.fixture
def no_zone(monkeypatch):
    from expense.dates import TimezoneDetectionError

    def boom(*a, **k):
        raise TimezoneDetectionError("no zone")

    monkeypatch.setattr("expense.dates.detect_timezone", boom)


def _no_profile_yet() -> None:
    _health_ok()
    respx.get(f"{ENGINE_URL}/v1/auth/me").mock(
        return_value=error_response(404, "NOT_FOUND", "No profile for this user.")
    )


async def _until_name(pilot, screen) -> None:
    await _address_and_key(pilot, screen)
    await wait_for(pilot, lambda: _label(screen) == "YOUR NAME")


def test_no_profile_asks_for_the_name_then_creates_it_and_saves(lima, monkeypatch):
    stub_home_month(monkeypatch)

    async def scenario(pilot, app):
        screen = app.screen
        await _until_name(pilot, screen)
        assert "the engine has no profile for this key yet · your name creates one" in (
            _text(screen, "#hint")
        )
        summary = _text(screen, "#summary")
        assert f"address    {ENGINE_URL}\n" in summary
        assert "key        ewe_pat_****wxyz" in summary
        assert "name       —  *" in summary
        assert "time zone  America/Lima  read-only" in summary
        assert _footer(screen) == ["escape Quit", "ctrl+s Create", "tab Field"]
        assert not _settings_file().exists()  # nothing saved before the profile exists
        await _type(pilot, screen, "Alex")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))

    with respx.mock:
        _no_profile_yet()
        boot = respx.post(f"{ENGINE_URL}/v1/auth/bootstrap").mock(
            return_value=httpx.Response(200, json=ME)
        )
        run_app(scenario, setup=True)
        request = boot.calls.last.request
        assert json.loads(request.content) == {"display_name": "Alex", "timezone": "America/Lima"}
        assert request.headers["X-Idempotency-Key"]
        assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert config_module.load() == config_module.Config(
        engine_url=ENGINE_URL, token=KEY, main_currency="PEN"
    )
    assert os.stat(_settings_file()).st_mode & 0o777 == 0o600


def test_ctrl_s_creates_with_the_name_typed_but_not_entered(lima, monkeypatch):
    stub_home_month(monkeypatch)

    async def scenario(pilot, app):
        screen = app.screen
        await _until_name(pilot, screen)
        await _type(pilot, screen, "Alex")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))

    with respx.mock:
        _no_profile_yet()
        boot = respx.post(f"{ENGINE_URL}/v1/auth/bootstrap").mock(
            return_value=httpx.Response(200, json=ME)
        )
        run_app(scenario, setup=True)
        assert json.loads(boot.calls.last.request.content)["display_name"] == "Alex"


def test_an_empty_name_shows_the_engines_refusal_and_saves_nothing(lima):
    async def scenario(pilot, app):
        screen = app.screen
        await _until_name(pilot, screen)
        await pilot.press("enter")  # the name left empty, sent as typed
        await wait_for(pilot, lambda: "VALIDATION_ERROR" in _text(screen, "#hint"))
        assert _text(screen, "#hint").splitlines() == [
            "VALIDATION_ERROR — Invalid input.",
            "  display_name: Must not be empty.",
        ]
        assert _label(screen) == "YOUR NAME"
        assert _bar(screen).value == ""
        assert "name       —  *" in _text(screen, "#summary")

    with respx.mock:
        _no_profile_yet()
        boot = respx.post(f"{ENGINE_URL}/v1/auth/bootstrap").mock(
            return_value=error_response(
                422,
                "VALIDATION_ERROR",
                "Invalid input.",
                {"display_name": "Must not be empty."},
                {"display_name": "EMPTY"},
            )
        )
        run_app(scenario, setup=True)
        assert json.loads(boot.calls.last.request.content)["display_name"] == ""
    assert not _settings_file().exists()


# ---- the Mac's time zone cannot be read ---------------------------------------
def test_an_unreadable_time_zone_becomes_one_more_question(no_zone, monkeypatch):
    stub_home_month(monkeypatch)

    async def scenario(pilot, app):
        screen = app.screen
        await _until_name(pilot, screen)
        assert "time zone  —  *" in _text(screen, "#summary")
        await _type(pilot, screen, "Alex")
        await pilot.press("enter")
        await wait_for(pilot, lambda: _label(screen) == "TIME ZONE")
        assert _text(screen, "#hint").strip() == (
            "this Mac's time zone could not be read · type yours"
        )
        summary = _text(screen, "#summary")
        assert "name       Alex" in summary
        assert "time zone  —  *" in summary
        assert not _settings_file().exists()
        await _type(pilot, screen, "America/Lima")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))

    with respx.mock:
        _no_profile_yet()
        boot = respx.post(f"{ENGINE_URL}/v1/auth/bootstrap").mock(
            return_value=httpx.Response(200, json=ME)
        )
        run_app(scenario, setup=True)
        assert json.loads(boot.calls.last.request.content) == {
            "display_name": "Alex",
            "timezone": "America/Lima",
        }
    assert config_module.load().token == KEY


def test_an_unknown_time_zone_shows_the_engines_refusal_and_saves_nothing(no_zone):
    async def scenario(pilot, app):
        screen = app.screen
        await _until_name(pilot, screen)
        await _type(pilot, screen, "Alex")
        await pilot.press("enter")
        await wait_for(pilot, lambda: _label(screen) == "TIME ZONE")
        await _type(pilot, screen, "Mars/Base")
        await pilot.press("enter")
        await wait_for(pilot, lambda: "VALIDATION_ERROR" in _text(screen, "#hint"))
        assert "  timezone: Not a supported time zone." in _text(screen, "#hint")
        assert _label(screen) == "TIME ZONE"

    with respx.mock:
        _no_profile_yet()
        respx.post(f"{ENGINE_URL}/v1/auth/bootstrap").mock(
            return_value=error_response(
                422,
                "VALIDATION_ERROR",
                "Invalid input.",
                {"timezone": "Not a supported time zone."},
                {"timezone": "UNSUPPORTED_VALUE"},
            )
        )
        run_app(scenario, setup=True)
    assert not _settings_file().exists()


# ---- while asking, and the rarer failures ---------------------------------------------
def test_typing_does_nothing_while_the_engine_is_asked():
    release = threading.Event()

    def me(request):
        release.wait(5)
        return error_response(401, "UNAUTHORIZED", "Token is not valid.")

    async def scenario(pilot, app):
        screen = app.screen
        await _address_and_key(pilot, screen)
        await wait_for(pilot, lambda: _text(screen, "#hint").strip() == ASKING)
        bar = _bar(screen)
        assert bar.disabled
        before = bar.value
        await pilot.press("x", "y", "tab", "escape")
        assert bar.value == before
        assert _label(screen) == "KEY"
        assert app.is_running
        release.set()
        await wait_for(pilot, lambda: REFUSED_NEXT in _text(screen, "#hint"))
        assert not bar.disabled
        assert bar.has_focus
        await pilot.press("z")
        assert bar.value == "z"

    with respx.mock:
        _health_ok()
        respx.get(f"{ENGINE_URL}/v1/auth/me").mock(side_effect=me)
        run_app(scenario, setup=True)


def test_another_engine_failure_on_the_key_says_try_again_and_saves_nothing():
    async def scenario(pilot, app):
        screen = app.screen
        await _address_and_key(pilot, screen)
        await wait_for(pilot, lambda: FAILED_NEXT in _text(screen, "#hint"))
        lines = _text(screen, "#hint").splitlines()
        assert lines[0] == "INTERNAL_ERROR — Something went wrong."
        assert lines[-1] == "nothing was saved · enter to try again"
        assert _label(screen) == "KEY"
        assert "key      ewe_pat_****wxyz" in _text(screen, "#summary")  # kept

    with respx.mock:
        _health_ok()
        respx.get(f"{ENGINE_URL}/v1/auth/me").mock(
            return_value=error_response(500, "INTERNAL_ERROR", "Something went wrong.")
        )
        run_app(scenario, setup=True)
    assert not _settings_file().exists()


def test_a_refused_profile_shows_the_engines_words_without_the_screens_hints(lima):
    """The shared text's 401 hint points at System ▸ Config, which Setup cannot reach."""

    async def scenario(pilot, app):
        screen = app.screen
        await _until_name(pilot, screen)
        await _type(pilot, screen, "Alex")
        await pilot.press("enter")
        await wait_for(pilot, lambda: "UNAUTHORIZED" in _text(screen, "#hint"))
        hint = _text(screen, "#hint")
        assert hint.splitlines() == ["UNAUTHORIZED — Token was revoked."]
        assert "Hint" not in hint and "System" not in hint
        assert _label(screen) == "YOUR NAME"
        assert not _bar(screen).disabled

    with respx.mock:
        _no_profile_yet()
        respx.post(f"{ENGINE_URL}/v1/auth/bootstrap").mock(
            return_value=error_response(401, "UNAUTHORIZED", "Token was revoked.")
        )
        run_app(scenario, setup=True)
    assert not _settings_file().exists()


# ---- no message sends the owner to a typed command -------------------------------------
#: "run/type/use expense …", a quoted `expense <group> …` command, or an install line.
_TELLS_TO_TYPE = re.compile(
    r"\b(?:[Rr]un|[Tt]ype|[Uu]se)\b:?\s+['`\"]?expense [a-z]"
    r"|['`\"]expense [a-z]"
    r"|\bpip3? install\b"
)


def _messages(path: Path):
    """Every string literal in `path` that is not a docstring."""
    tree = ast.parse(path.read_text())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                yield node.lineno, node.value


def test_no_message_in_the_app_tells_the_owner_to_type_a_command():
    """The app is the only surface, so a remedy points at a screen, never at a
    typed `expense …` command. `expense/commands/` is the typed surface itself
    and prints its own words; everything else can reach a screen."""
    # the guard's pattern catches a typed command and leaves plain wording alone
    assert _TELLS_TO_TYPE.search("No config found. Run: expense config set --engine-url <url>")
    assert _TELLS_TO_TYPE.search("Install it with:\n    pip install openpyxl")
    assert not _TELLS_TO_TYPE.search("Error: the expense app needs an interactive terminal.")
    package = Path(config_module.__file__).parent
    offenders = [
        f"{path.relative_to(package.parent)}:{line}: {text!r}"
        for path in sorted(package.rglob("*.py"))
        if "commands" not in path.relative_to(package).parts
        for line, text in _messages(path)
        if _TELLS_TO_TYPE.search(text)
    ]
    assert not offenders, "\n".join(offenders)
