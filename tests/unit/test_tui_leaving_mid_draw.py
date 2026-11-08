"""A screen that is left while its hand-back waits for a list to draw: the work after the
wait is dropped, and an error raised while the screen is still showing still surfaces."""

import asyncio

import pytest
from textual.app import App
from textual.widget import Widget

from expense.tui.screens._base import still_attached
from expense.tui.screens.statements import (
    FlaggedLinesScreen,
    StatementScreen,
    StatementsScreen,
    _FlaggedList,
)
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
            if how == "esc":
                app.pop_screen()
            else:
                app.exit()
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
            await screen._show({"accounts": screen._accounts, "statements": None})

    run_app(scenario)
