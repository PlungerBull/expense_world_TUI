"""A screen that is left while its hand-back waits for a list to draw: the work after the
wait is dropped, and an error raised while the screen is still showing still surfaces."""

import asyncio

import pytest
from textual.app import App
from textual.widget import Widget
from textual.widgets import Static

from expense.tui.screens._base import still_attached
from expense.tui.screens.statements import (
    FlaggedLinesScreen,
    StatementScreen,
    StatementsScreen,
    _FlaggedList,
)
from expense.tui.widgets.checklist import CheckList
from tests.unit.helpers import run_app, wait_for, wait_for_list
from tests.unit.test_tui_flagged_lines import TAMBO, UBER, Lines
from tests.unit.test_tui_flagged_lines import _patch as _patch_flagged_names
from tests.unit.test_tui_statement_screen import AGOSTO, VIS_AGOSTO, _engine
from tests.unit.test_tui_statements import _patch_browse


class Leave:
    """Watches one coroutine hand-back, `screen_cls.<handback>`, and makes the screen leave
    while it waits: the first `Widget.<method>` that `hit` accepts lands, then the screen is
    popped (`how="esc"`) or the app quits (`how="quit"`), and the wait goes on only once
    the screen is no longer attached. `left` is set once that has happened; `ended`
    once the hand-back returned or raised; `errors` is every exception it raised;
    `after` counts the calls of `probe` (a method of `probe_cls` the hand-back makes
    after that wait) made after the screen left."""

    def __init__(self, monkeypatch, app: App, how: str, screen_cls, handback: str, method, hit):
        self.left = self.ended = False
        self.errors: list[BaseException] = []
        self.after = 0
        real_handback = getattr(screen_cls, handback)

        async def watched(screen, *args, **kwargs):
            self.screen = screen
            try:
                return await real_handback(screen, *args, **kwargs)
            except BaseException as err:
                self.errors.append(err)
                raise
            finally:
                self.ended = True

        monkeypatch.setattr(screen_cls, handback, watched)
        real = getattr(Widget, method)

        async def leaving(awaitable):
            result = await awaitable
            self.left = True
            leave = app.exit if how == "quit" else app.pop_screen
            leave()
            for _ in range(1000):  # yields only: no real time passes
                if not (self.screen.is_attached and not self.screen._pruning):
                    break
                await asyncio.sleep(0)
            return result

        def patched(widget, *args, **kwargs):
            awaitable = real(widget, *args, **kwargs)
            if self.left or not hit(widget, args):
                return awaitable
            return leaving(awaitable)

        monkeypatch.setattr(Widget, method, patched)

    def probe(self, monkeypatch, probe_cls, name: str) -> None:
        real = getattr(probe_cls, name)

        def counting(*args, **kwargs):
            self.after += self.left
            return real(*args, **kwargs)

        monkeypatch.setattr(probe_cls, name, counting)

    def assert_nothing_crashed(self) -> None:
        assert self.ended
        assert self.errors == []
        assert self.after == 0


def _mounts(widget_id: str):
    return lambda _container, widgets: any(w.id == widget_id for w in widgets)


def _empties(container_id: str):
    return lambda container, _args: container.id == container_id


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_the_accounts_draw_crashes_nothing(monkeypatch, how):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        leave = Leave(monkeypatch, app, how, StatementsScreen, "_show", "mount", _mounts("card"))
        leave.probe(monkeypatch, StatementsScreen, "_set_crumb")
        await app.push_screen(StatementsScreen())
        await wait_for(pilot, lambda: leave.ended)
        leave.assert_nothing_crashed()

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_a_statement_panel_draws_crashes_nothing(monkeypatch, how):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await wait_for(pilot, lambda: screen._accts_list.has_focus)  # `_show` has finished
        leave = Leave(
            monkeypatch,
            app,
            how,
            StatementsScreen,
            "_open_panel",
            "mount",
            lambda _container, widgets: widgets and widgets[0] is screen._statement_list,
        )
        leave.probe(monkeypatch, StatementsScreen, "_set_crumb")
        await pilot.press("enter")
        await wait_for(pilot, lambda: leave.ended)
        leave.assert_nothing_crashed()

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_a_statements_lines_are_cleared_crashes_nothing(
    fake_client, monkeypatch, how
):
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)

    async def scenario(pilot, app):
        leave = Leave(
            monkeypatch,
            app,
            how,
            StatementScreen,
            "_populate",
            "remove_children",
            _empties("rlist"),
        )
        leave.probe(monkeypatch, StatementScreen, "_checklist_items")
        await app.push_screen(StatementScreen(dict(VIS_AGOSTO)))
        await wait_for(pilot, lambda: leave.ended)
        leave.assert_nothing_crashed()

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_the_flagged_lines_are_cleared_crashes_nothing(fake_client, monkeypatch, how):
    _patch_flagged_names(monkeypatch)
    Lines(monkeypatch, fake_client, TAMBO, UBER)

    async def scenario(pilot, app):
        leave = Leave(
            monkeypatch,
            app,
            how,
            FlaggedLinesScreen,
            "_populate",
            "remove_children",
            _empties("flist"),
        )
        leave.probe(monkeypatch, _FlaggedList, "__init__")
        await app.push_screen(FlaggedLinesScreen("s-sig", statement="Octubre 2026"))
        await wait_for(pilot, lambda: leave.ended)
        leave.assert_nothing_crashed()

    run_app(scenario)


def test_an_error_while_the_screen_is_showing_is_not_swallowed(monkeypatch):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert still_attached(screen)

        def boom():
            raise RuntimeError("the crumb is gone")

        monkeypatch.setattr(screen, "_set_crumb", boom)
        with pytest.raises(RuntimeError, match="the crumb is gone"):
            await screen._show(dict(accounts=screen._accounts, statements=None))

    run_app(scenario)


# ---- the guards after taking the content lock, and after the draw's own awaits ---------
def _recording(monkeypatch, screen_cls, handback: str) -> list:
    """The arguments every call of `screen_cls.<handback>` gets, kept in a list."""
    real = getattr(screen_cls, handback)
    seen: list = []

    async def recording(screen, *args, **kwargs):
        seen.append((args, kwargs))
        return await real(screen, *args, **kwargs)

    monkeypatch.setattr(screen_cls, handback, recording)
    return seen


async def _left_while_waiting_for_the_lock(pilot, app, screen, how: str, handback) -> list:
    """Holds `screen`'s content lock, starts `handback()` (a coroutine hand-back that waits
    for it), makes the screen leave (`how`) while it waits, then frees the lock. Returns
    what the hand-back raised."""
    lock = screen._content_lock()
    await lock.acquire()
    task = asyncio.ensure_future(handback())
    for _ in range(5):
        await asyncio.sleep(0)  # yields only: the hand-back is parked on the lock
    assert not task.done()
    if how == "quit":
        app.exit()
    else:
        app.pop_screen()
    await wait_for(pilot, lambda: not still_attached(screen))
    lock.release()
    results = await asyncio.gather(task, return_exceptions=True)
    return [r for r in results if isinstance(r, BaseException)]


def _counting(monkeypatch, cls, name: str) -> list:
    """Every call of `cls.<name>` made, as a list (the call goes on to the real one)."""
    real = getattr(cls, name)
    calls: list = []

    def counting(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(cls, name, counting)
    return calls


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_the_draw_waits_for_the_lock_builds_nothing(monkeypatch, how):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        seen = _recording(monkeypatch, StatementsScreen, "_show")
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        built = _counting(monkeypatch, StatementsScreen, "build")
        args, kwargs = seen[0]
        cleared = _counting(monkeypatch, Widget, "remove_children")
        errors = await _left_while_waiting_for_the_lock(
            pilot, app, screen, how, lambda: screen._show(*args, **kwargs)
        )
        assert errors == []
        assert cleared == []
        assert built == []

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_the_draw_clears_the_content_builds_nothing(monkeypatch, how):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        leave = Leave(
            monkeypatch, app, how, StatementsScreen, "_show", "remove_children", _empties("content")
        )
        leave.probe(monkeypatch, StatementsScreen, "build")
        await app.push_screen(StatementsScreen())
        await wait_for(pilot, lambda: leave.ended)
        leave.assert_nothing_crashed()

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_the_error_waits_for_the_lock_shows_nothing(monkeypatch, how):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        banners = _counting(monkeypatch, Static, "__init__")
        cleared = _counting(monkeypatch, Widget, "remove_children")
        errors = await _left_while_waiting_for_the_lock(
            pilot, app, screen, how, lambda: screen._error("statements unavailable")
        )
        assert errors == []
        assert cleared == []
        assert banners == []

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_the_error_clears_the_content_shows_nothing(monkeypatch, how):
    _patch_browse(monkeypatch)

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("accounts unavailable")

    monkeypatch.setattr("expense.reads.fetch_accounts", unavailable)

    async def scenario(pilot, app):
        leave = Leave(
            monkeypatch,
            app,
            how,
            StatementsScreen,
            "_error",
            "remove_children",
            _empties("content"),
        )
        leave.probe(monkeypatch, Static, "__init__")
        await app.push_screen(StatementsScreen())
        await wait_for(pilot, lambda: leave.ended)
        leave.assert_nothing_crashed()

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_the_panel_waits_for_the_lock_builds_nothing(monkeypatch, how):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await wait_for(pilot, lambda: screen._accts_list.has_focus)
        panels = _counting(monkeypatch, StatementsScreen, "_new_statement_list")
        errors = await _left_while_waiting_for_the_lock(
            pilot, app, screen, how, lambda: screen._open_panel("acc1", [])
        )
        assert errors == []
        assert panels == []

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_a_statements_lines_wait_for_the_lock_paints_nothing(
    fake_client, monkeypatch, how
):
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)

    async def scenario(pilot, app):
        screen = StatementScreen(dict(VIS_AGOSTO))
        seen = _recording(monkeypatch, StatementScreen, "_populate")
        await app.push_screen(screen)
        await wait_for(pilot, lambda: seen and screen._list is not None)
        sized = _counting(monkeypatch, CheckList, "__init__")
        args, kwargs = seen[-1]
        cleared = _counting(monkeypatch, Widget, "remove_children")
        errors = await _left_while_waiting_for_the_lock(
            pilot, app, screen, how, lambda: screen._populate(*args, **kwargs)
        )
        assert errors == []
        assert cleared == []
        assert sized == []

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_a_statements_lines_mount_focuses_nothing(fake_client, monkeypatch, how):
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)

    async def scenario(pilot, app):
        leave = Leave(
            monkeypatch, app, how, StatementScreen, "_populate", "mount", _empties("rlist")
        )
        leave.probe(monkeypatch, CheckList, "focus")
        await app.push_screen(StatementScreen(dict(VIS_AGOSTO)))
        await wait_for(pilot, lambda: leave.ended)
        leave.assert_nothing_crashed()

    run_app(scenario)


@pytest.mark.parametrize("how", ["esc", "quit"])
def test_leaving_while_the_flagged_lines_wait_for_the_lock_paints_nothing(
    fake_client, monkeypatch, how
):
    _patch_flagged_names(monkeypatch)
    Lines(monkeypatch, fake_client, TAMBO, UBER)

    async def scenario(pilot, app):
        screen = FlaggedLinesScreen("s-sig", statement="Octubre 2026")
        seen = _recording(monkeypatch, FlaggedLinesScreen, "_populate")
        await app.push_screen(screen)
        await wait_for(pilot, lambda: seen and screen._list is not None)
        lists = _counting(monkeypatch, _FlaggedList, "__init__")
        args, kwargs = seen[-1]
        cleared = _counting(monkeypatch, Widget, "remove_children")
        errors = await _left_while_waiting_for_the_lock(
            pilot, app, screen, how, lambda: screen._populate(*args, **kwargs)
        )
        assert errors == []
        assert cleared == []
        assert lists == []

    run_app(scenario)
