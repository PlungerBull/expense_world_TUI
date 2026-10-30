"""SectionScreen failure paths — error banner, reload recovery, write failure.
Uses AccountsScreen as the concrete SectionScreen; nothing here
is accounts-specific.
"""

from textual.widgets import Static

from expense.errors import EngineError
from expense.tui.screens.accounts import AccountsScreen
from tests.unit.helpers import (
    account_with_currencies,
    render_text,
    run_app,
    section_settled,
    wait_for,
    wait_for_list,
    whole,
)

ACCOUNTS = [account_with_currencies(id="a1", name="BCP", color=None)]


def _text(renderable) -> str:
    return render_text(renderable, width=80)


def test_fetch_error_renders_banner(fake_client, monkeypatch):
    """_load catches the fetch exception and mounts the 'Could not load.' banner."""

    def boom(*a, **k):
        raise EngineError("INTERNAL", "engine exploded", None, 500, {})

    monkeypatch.setattr("expense.reads.fetch_accounts", boom)

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for(pilot, lambda: app.screen.query(".error"))
        banner = _text(app.screen.query_one(".error", Static).content)
        assert "Could not load." in banner
        assert "INTERNAL — engine exploded" in banner  # canonical format_error text

    run_app(scenario)


def test_action_reload_recovers_after_error(fake_client, monkeypatch):
    """`r` remounts the spinner, re-runs fetch, and replaces the banner with data."""
    attempts = []

    def flaky(*a, **k):
        attempts.append(1)
        if len(attempts) == 1:
            raise EngineError("INTERNAL", "first call fails", None, 500, {})
        return whole(ACCOUNTS)

    monkeypatch.setattr("expense.reads.fetch_accounts", flaky)

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for(pilot, lambda: app.screen.query(".error"))
        await pilot.press("r")  # action_reload
        await wait_for(pilot, lambda: section_settled(app) and app.screen.query("#card"))
        assert not app.screen.query(".error")
        assert len(attempts) == 2

    run_app(scenario)


def test_run_write_failure_notifies_and_skips_after_write(fake_client, monkeypatch):
    """A failing write toasts title='Failed' and never fires the success/reload path.

    Archive lives on the Manage list itself (`a` on the cursor row, immediate),
    which shares EngineWriteMixin.run_write with every screen — same failure path.
    """
    fake_client.errors["POST"] = EngineError("CONFLICT", "cannot archive", None, 409, {})
    seen: list = []
    monkeypatch.setattr(
        AccountsScreen, "notify", lambda self, message, **kw: seen.append((message, kw))
    )
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(ACCOUNTS))

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("a")  # immediate archive → run_write → POST raises
        await wait_for(pilot, lambda: seen)
        message, kw = seen[0]
        assert "CONFLICT — cannot archive" in message
        assert kw.get("title") == "Failed" and kw.get("severity") == "error"
        assert len(seen) == 1  # no success toast, no reload (_after_write skipped)

    run_app(scenario)


def test_a_load_that_lands_as_the_app_closes_builds_nothing(fake_client, monkeypatch):
    """A section read still in flight when the app begins to close is dropped,
    not built into a screen whose widgets are being taken down.

    Same order as the log bar's peek test: the app is told to exit, and only
    then does the read hand its answer back, while the screen is still linked.
    """
    import threading

    release = threading.Event()
    submitted = threading.Event()
    returned = threading.Event()
    asked: list = []
    built: list = []

    def held(*a, **k):
        asked.append(1)
        release.wait(timeout=5)
        return whole(ACCOUNTS)

    monkeypatch.setattr("expense.reads.fetch_accounts", held)
    real_build = AccountsScreen.build
    monkeypatch.setattr(
        AccountsScreen, "build", lambda self, data: built.append(1) or real_build(self, data)
    )

    async def scenario(pilot, app):
        real_call = app.call_from_thread

        def spy(callback, *args, **kwargs):
            submitted.set()
            try:
                return real_call(callback, *args, **kwargs)
            finally:
                returned.set()

        monkeypatch.setattr(app, "call_from_thread", spy)
        await app.push_screen(AccountsScreen())
        await wait_for(pilot, lambda: asked, message="the screen never read")
        app.exit()
        release.set()
        assert submitted.wait(timeout=5), "the load never handed back"
        await wait_for(pilot, returned.is_set, message="the hand-back never returned")
        assert built == []  # the answer was dropped, not built

    run_app(scenario)
