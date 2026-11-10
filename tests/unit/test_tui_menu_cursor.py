"""The home menu's cursor must be *visible* — regression armor.

The bug this guards: `theme.py` gives the block cursor no colour of its own
(`block-cursor-foreground`/`-background` are both `ansi_default`) and relies
entirely on `block-cursor-text-style: reverse` for contrast. Textual 8.2.7
drops `reverse` from `get_visual_style()` when both colours are `ansi_default`,
so the highlighted menu row rendered `default on default` — byte-identical to
every unselected row. The menu had no cursor at all and nothing failed.

That is the shape of failure to defend against: not a crash, not a wrong value,
but a style silently resolving to nothing. So these tests assert on the
*rendered* style of the strip, which is the only place the difference is real —
asserting on CSS or component styles would have passed throughout the bug
(`get_component_styles` reported `text_style: reverse` the whole time).
"""

from expense.tui.widgets.cursor_list import CURSOR_STYLE, CursorOptionList
from tests.unit.helpers import run_app, stub_home_month, wait_for


def _line_of(menu, index: int) -> int:
    """The y offset of option `index` — separators take a line of their own,
    so an option's index and its line diverge below the first one."""
    return next(y for y, (option, _line) in enumerate(menu._lines) if option == index)


def _line_style(menu, index: int) -> str:
    """The rendered style of the first non-blank segment of option `index`."""
    for segment in menu.render_line(_line_of(menu, index))._segments:
        if segment.text.strip():
            return str(segment.style)
    return ""


def _stub_month(monkeypatch):
    """Home draws its rows from the month reads; give it a month so the menu
    has section headers (disabled) above live rows, as it does in use."""
    stub_home_month(monkeypatch)


async def _loaded(pilot, app):
    await wait_for(pilot, lambda: app.screen._data is not None)
    await pilot.pause()


def test_the_cursor_row_is_reversed_across_its_whole_width_and_follows_the_keyboard(monkeypatch):
    """The cursor row must not look like the rows around it, its bar covers the row's
    padding too (or it reads as a ragged blob), section headers (disabled options) never
    take it, and moving down moves the bar, not just an internal index."""
    _stub_month(monkeypatch)

    async def scenario(pilot, app):
        await _loaded(pilot, app)
        menu = app.screen.query_one("#menu", CursorOptionList)
        assert menu.has_focus, "the menu must be focused for the cursor to mean anything"
        first = menu.highlighted
        assert first is not None

        cursor_row = _line_style(menu, first)
        assert CURSOR_STYLE in cursor_row, f"cursor row is {cursor_row!r}"
        for y in (first - 1, first + 1):
            assert _line_style(menu, y) != cursor_row
        segments = menu.render_line(_line_of(menu, first))._segments
        assert segments and all(CURSOR_STYLE in str(s.style) for s in segments)
        disabled = [i for i, opt in enumerate(menu.options) if opt.disabled]
        assert disabled, "the menu is built from section headers + live rows + screen entries"
        for index in disabled:
            assert CURSOR_STYLE not in _line_style(menu, index)

        await pilot.press("down")
        await pilot.pause()
        assert menu.highlighted == first + 1
        assert CURSOR_STYLE not in _line_style(menu, first)
        assert CURSOR_STYLE in _line_style(menu, first + 1)

    run_app(scenario)
