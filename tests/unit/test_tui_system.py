"""Phase 2 System screen tests — Config + Auth & profile (fake client)."""

from textual.widgets import Static

from expense.config import Config
from expense.tui.screens.system import (
    AuthScreen,
    ConfigScreen,
    _redact_token,
)
from tests.unit.helpers import render_text, run_app, wait_for

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
    """Engine url, token, main currency — and nothing else. The client-id and
    cache-status rows went with the replica (2026-08-06)."""
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
    with a generic connection error (backlog 6.3b — the TUI half of 3.4)."""
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
        # Main currency is read-only — the engine locked it (2026-08-01);
        # the `m` set-currency flow is gone.
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


def test_bootstrap_undetectable_timezone_notifies_not_crash(fake_client, monkeypatch):
    """Timezone detection failure toasts a remedy instead of crashing the app
    through Textual's message pump (backlog 6.2d)."""
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
