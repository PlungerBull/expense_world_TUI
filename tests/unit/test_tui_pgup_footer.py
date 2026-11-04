"""`pgup Prev` stands in the footer only where a page lies before the one shown.

The rule lives in the shared list widgets (`WindowedList.check_action`, the footer
re-checked as the page moves); it is proved on the drawn footer of a real screen of
each: a statement's `CheckList` and a Manage `CursorList`.
"""

from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.screens.reconciliations import ReconciliationDetailScreen
from tests.unit.helpers import run_app, screen_lines, wait_for, wait_for_list, whole
from tests.unit.test_tui_statement_screen import AGOSTO, VIS_AGOSTO, _engine


def _footer(app) -> str:
    return next(line for line in reversed(screen_lines(app)) if line.strip())


async def _drawn(pilot, app, *, paged: bool = True) -> str:
    """The footer once the list's own keys are on it: `pgdn Next` for a list of pages,
    `esc Back` for a one-page list (that key is also in the loading footer, so it proves
    only that a footer was drawn). Neither is the text a test asserts absent."""
    key = "pgdn Next" if paged else "esc Back"
    await wait_for(pilot, lambda: key in _footer(app), message=f"the footer never showed {key}")
    return _footer(app)


async def _settled(pilot, app, *, prev: bool | None) -> str:
    """The footer once it shows `pgup Prev` or not, as asked (`None`: whatever it shows
    after a beat): the footer repaints a beat after the key."""
    await pilot.pause()
    if prev is not None:
        await wait_for(pilot, lambda: ("pgup Prev" in _footer(app)) == prev)
    return _footer(app)


def _tags(count: int) -> list[dict]:
    return [{"id": f"h{i}", "name": f"tag{i:02}", "system_key": None} for i in range(count)]


def _statement_footers(fake_client, monkeypatch, lines, size, *, paged=True):
    _engine(fake_client, monkeypatch, statement_lines=lines, statement=VIS_AGOSTO)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(VIS_AGOSTO), statement_code="VIS")
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        seen = [await _drawn(pilot, app, paged=paged)]
        for key, prev in (("pagedown", True), ("pageup", False)):
            await pilot.press(key)
            seen.append(await _settled(pilot, app, prev=prev if paged else None))
        return seen

    return run_app(scenario, size=size)


def test_a_statements_list_shows_pgup_only_past_its_first_page(fake_client, monkeypatch):
    first, second, back = _statement_footers(fake_client, monkeypatch, AGOSTO, (100, 19))
    assert "pgdn Next" in first and "pgup Prev" not in first
    assert "pgup Prev" in second
    assert "pgup Prev" not in back and "pgdn Next" in back


def test_a_statement_of_one_page_never_shows_pgup(fake_client, monkeypatch):
    for footer in _statement_footers(fake_client, monkeypatch, AGOSTO[:2], (100, 30), paged=False):
        assert "pgup" not in footer and "pgdn" not in footer


def test_a_manage_list_shows_pgup_only_past_its_first_page_and_loses_it_on_reload(monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole(_tags(40)))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        screen = HashtagsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        seen = [await _drawn(pilot, app)]
        for key, prev in (("pagedown", True), ("pageup", False), ("pagedown", True), ("r", False)):
            await pilot.press(key)
            seen.append(await _settled(pilot, app, prev=prev))
        await wait_for_list(pilot, app)
        seen.append(await _drawn(pilot, app))
        return seen

    first, second, back, again, reloaded, listed = run_app(scenario, size=(100, 24))
    assert "pgdn Next" in first and "pgup Prev" not in first
    assert "pgup Prev" in second
    assert "pgup Prev" not in back and "pgdn Next" in back
    assert "pgup Prev" in again
    assert "pgup Prev" not in reloaded
    assert "pgup Prev" not in listed and "pgdn Next" in listed


def test_a_manage_list_of_one_page_never_shows_pgup(monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole(_tags(3)))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        screen = HashtagsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await _drawn(pilot, app, paged=False)
        await pilot.press("pagedown")
        await pilot.pause()
        return _footer(app)

    footer = run_app(scenario, size=(100, 24))
    assert "pgup" not in footer and "pgdn" not in footer
