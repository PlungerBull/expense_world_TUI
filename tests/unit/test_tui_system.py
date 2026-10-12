"""System screen tests — Config + Auth & profile (fake client)."""

import pytest
from textual.widgets import Static

from expense.config import Config
from expense.errors import EngineError
from expense.tui.screens.system import (
    AuthScreen,
    ConfigScreen,
    _redact_token,
)
from tests.unit.helpers import error_body, render_text, run_app, wait_for

CFG = Config(
    engine_url="https://engine.example",
    token="ewe_pat_abcd1234wxyz",
    main_currency="PEN",
)


def _screen_text(container) -> str:
    """Every Static under `container`, rendered through a Rich console."""
    return render_text(*(child.content for child in container.query(Static)), width=100)


def test_redact_token():
    assert _redact_token(None) == "(none)"
    assert _redact_token("short") == "****"
    assert _redact_token("ewe_pat_abcd1234wxyz") == "ewe_pat_****wxyz"


def test_config_screen_shows_only_the_engine_connection(monkeypatch):
    """Engine url, token, main currency — and nothing else."""
    monkeypatch.setattr("expense.config.load", lambda: CFG)

    async def scenario(pilot, app):
        screen = ConfigScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(app.screen.query("#card")))
        card = _screen_text(app.screen.query_one("#card"))
        assert "engine url" in card and "token" in card and "main currency" in card
        assert "client id" not in card and "cache" not in card

    run_app(scenario, size=(120, 40))


def test_config_screen_reads_and_saves(monkeypatch):
    saved = {}
    monkeypatch.setattr("expense.config.load", lambda: CFG)
    monkeypatch.setattr("expense.config.save", lambda c: saved.update(cfg=c))

    async def scenario(pilot, app):
        screen = ConfigScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._cfg is not None)
        assert screen._cfg.engine_url == "https://engine.example"
        screen._save(engine_url="https://new.example")  # e-action path
        await wait_for(pilot, lambda: "cfg" in saved)
        assert saved["cfg"].engine_url == "https://new.example"
        assert saved["cfg"].token == CFG.token  # other fields preserved

    run_app(scenario)


def test_config_screen_rejects_bad_engine_url(monkeypatch):
    """A scheme-less URL must error at save time, not brick every later call
    with a generic connection error."""
    saved = {}
    monkeypatch.setattr("expense.config.load", lambda: CFG)
    monkeypatch.setattr("expense.config.save", lambda c: saved.update(cfg=c))
    notices: list = []
    monkeypatch.setattr(ConfigScreen, "notify", lambda self, message, **kw: notices.append(message))

    async def scenario(pilot, app):
        screen = ConfigScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._cfg is not None)
        screen._save(engine_url="engine.example")  # no scheme
        await wait_for(pilot, lambda: notices)  # the rejection toast
        assert not saved  # nothing written
        assert any("scheme and host" in m for m in notices)
        assert not any("Config saved" in m for m in notices)

    run_app(scenario)


def _patch_auth(fake_client, monkeypatch, *, me):
    """me=None leaves GET /auth/me unmocked → FakeClient raises 404 (not provisioned)."""
    if me is not None:
        fake_client.get_responses["/auth/me"] = me
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: CFG)
    monkeypatch.setattr("expense.config.save", lambda c: None)


def test_auth_provisioned_shows_identity(fake_client, monkeypatch):
    me = {
        "user": {"display_name": "Alex", "id": "u1"},
        "settings": {"main_currency": "PEN"},
    }
    _patch_auth(fake_client, monkeypatch, me=me)

    async def scenario(pilot, app):
        screen = AuthScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: "Alex" in _screen_text(app.screen))
        card = _screen_text(app.screen)
        assert "display name" in card and "Alex" in card
        assert "main currency" in card and "PEN" in card
        # Main currency is read-only — the engine locks it — so there is
        # no `m` set-currency flow.
        assert not hasattr(screen, "action_currency")
        assert fake_client.puts == []

    run_app(scenario)


def test_auth_not_provisioned_bootstraps(fake_client, monkeypatch):
    _patch_auth(fake_client, monkeypatch, me=None)  # 404 → not provisioned
    monkeypatch.setattr("expense.dates.detect_timezone", lambda *a, **k: "America/Lima")

    async def scenario(pilot, app):
        screen = AuthScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(app.screen.query(".legend")))
        screen.action_bootstrap()
        await wait_for(pilot, lambda: bool(app.screen.query("#prompt")))
        app.screen.query_one("#prompt").value = "Alex"
        await pilot.press("enter")  # submit display name
        await wait_for(pilot, lambda: fake_client.posts)
        path, body = fake_client.posts[0]
        assert path == "/auth/bootstrap"
        assert body == {"display_name": "Alex", "timezone": "America/Lima"}

    run_app(scenario)


async def _open_bootstrap_prompt(pilot, app) -> AuthScreen:
    screen = AuthScreen()
    await app.push_screen(screen)
    await wait_for(pilot, lambda: bool(app.screen.query(".legend")))
    screen.action_bootstrap()
    await wait_for(pilot, lambda: bool(app.screen.query("#prompt")))
    return screen


@pytest.mark.parametrize("typed", ["  Alex Tern \t", "", "   "], ids=["padded", "empty", "spaces"])
def test_bootstrap_sends_the_display_name_exactly_as_typed(fake_client, monkeypatch, typed):
    """No local trim and no local blank check: the engine trims the name and
    refuses an empty one (contract: POST /v1/auth/bootstrap)."""
    _patch_auth(fake_client, monkeypatch, me=None)
    monkeypatch.setattr("expense.dates.detect_timezone", lambda *a, **k: "America/Lima")

    async def scenario(pilot, app):
        await _open_bootstrap_prompt(pilot, app)
        app.screen.query_one("#prompt").value = typed
        await pilot.press("enter")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts == [
            ("/auth/bootstrap", {"display_name": typed, "timezone": "America/Lima"})
        ]

    run_app(scenario)


def test_bootstrap_sends_typed_keystrokes_with_their_spaces(fake_client, monkeypatch):
    """Through the keyboard rather than the widget's value: the padding survives."""
    _patch_auth(fake_client, monkeypatch, me=None)
    monkeypatch.setattr("expense.dates.detect_timezone", lambda *a, **k: "America/Lima")

    async def scenario(pilot, app):
        await _open_bootstrap_prompt(pilot, app)
        await pilot.press("space", "A", "l", "space", "enter")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts[0][1]["display_name"] == " Al "

    run_app(scenario)


def test_bootstrap_esc_cancels_and_sends_nothing(fake_client, monkeypatch):
    _patch_auth(fake_client, monkeypatch, me=None)
    monkeypatch.setattr("expense.dates.detect_timezone", lambda *a, **k: "America/Lima")
    started: list = []
    real = AuthScreen._bootstrap
    monkeypatch.setattr(
        AuthScreen, "_bootstrap", lambda self, name: (started.append(name), real(self, name))
    )

    async def scenario(pilot, app):
        screen = await _open_bootstrap_prompt(pilot, app)
        app.screen.query_one("#prompt").value = "Alex"
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()  # a non-event: the cancel starts no write
        assert started == []
        assert fake_client.posts == []

    run_app(scenario)


def test_bootstrap_prompt_wording_is_unchanged(fake_client, monkeypatch):
    _patch_auth(fake_client, monkeypatch, me=None)

    async def scenario(pilot, app):
        await _open_bootstrap_prompt(pilot, app)
        box = app.screen.query_one("#modal")
        assert (
            _screen_text(box).split()
            == (
                "Bootstrap your display name — creates your user record [enter] save [esc] cancel"
            ).split()
        )
        prompt = app.screen.query_one("#prompt")
        assert prompt.value == "" and prompt.placeholder == "" and not prompt.password

    run_app(scenario)


def test_bootstrap_blank_name_shows_the_engines_refusal(fake_client, monkeypatch):
    """The engine's `EMPTY` refusal reaches the "Bootstrap failed" toast through
    the shared error text — code, message and the field line, nothing added.

    The code, the field text and the reason are the engine's
    (contract: POST /v1/auth/bootstrap); the contract fixes no top-level
    `message`, so this one is its example's (contract: "Base Conventions", "Error format")."""
    _patch_auth(fake_client, monkeypatch, me=None)
    monkeypatch.setattr("expense.dates.detect_timezone", lambda *a, **k: "America/Lima")
    body = error_body(
        "VALIDATION_ERROR",
        "Human-readable description.",
        {"display_name": "Must not be empty."},
        {"display_name": "EMPTY"},
    )
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR",
        "Human-readable description.",
        {"display_name": "Must not be empty."},
        422,
        body,
        {"display_name": "EMPTY"},
    )
    notices: list = []
    monkeypatch.setattr(
        AuthScreen,
        "notify",
        lambda self, message, *, title, severity: notices.append((message, title, severity)),
    )

    async def scenario(pilot, app):
        await _open_bootstrap_prompt(pilot, app)
        app.screen.query_one("#prompt").value = "   "
        await pilot.press("enter")
        await wait_for(pilot, lambda: notices)
        assert fake_client.posts[0][1]["display_name"] == "   "
        assert notices == [
            (
                "VALIDATION_ERROR — Human-readable description.\n"
                "  display_name: Must not be empty.",
                "Bootstrap failed",
                "error",
            )
        ]

    run_app(scenario)


def test_bootstrap_undetectable_timezone_notifies_not_crash(fake_client, monkeypatch):
    """Timezone detection failure toasts a remedy instead of crashing the app
    through Textual's message pump."""
    from expense.dates import TimezoneDetectionError

    _patch_auth(fake_client, monkeypatch, me=None)

    def boom(*a, **k):
        raise TimezoneDetectionError("no zone")

    monkeypatch.setattr("expense.dates.detect_timezone", boom)
    notices: list = []
    monkeypatch.setattr(AuthScreen, "notify", lambda self, message, **kw: notices.append(message))

    async def scenario(pilot, app):
        screen = AuthScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(app.screen.query(".legend")))
        screen.action_bootstrap()
        await wait_for(pilot, lambda: bool(app.screen.query("#prompt")))
        app.screen.query_one("#prompt").value = "Alex"
        await pilot.press("enter")  # submit display name → detection fails
        await wait_for(pilot, lambda: notices)
        assert any("TZ environment variable" in m for m in notices)
        assert app.is_running
        assert not fake_client.posts  # nothing was sent to the engine

    run_app(scenario)


def test_system_screens_inherit_escape_and_r(monkeypatch):
    """4.5 dropped the re-declared escape/r; SectionScreen must still supply them."""
    monkeypatch.setattr("expense.config.load", lambda: CFG)

    async def scenario(pilot, app):
        screen = ConfigScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._cfg is not None)
        keys = set(screen.active_bindings)
        assert {"escape", "r", "e", "t"} <= keys
        assert screen.active_bindings["r"].binding.description == "Refresh"

    run_app(scenario)


def test_auth_screen_caches_the_home_currency_like_the_cli_does(fake_client, monkeypatch):
    """The TUI read `/auth/me` on its own and threw the settings away, so a
    TUI-only user never got a cached `main_currency` — and the header's
    stale-rate check skips entirely without one (`app.refresh_rate_status`).
    Both surfaces go through `auth_cmd.fetch_me` now."""
    saved: list = []
    fake_client.get_responses["/auth/me"] = {
        "user": {"display_name": "Alex", "id": "u1"},
        "settings": {"main_currency": "PEN"},
    }
    monkeypatch.setattr(
        "expense.config.ensure_loaded", lambda: CFG.model_copy(update={"main_currency": None})
    )
    monkeypatch.setattr("expense.config.save", lambda c: saved.append(c))

    async def scenario(pilot, app):
        await app.push_screen(AuthScreen())
        await wait_for(pilot, lambda: saved, message="main_currency was never cached")
        assert saved[-1].main_currency == "PEN"

    run_app(scenario)
