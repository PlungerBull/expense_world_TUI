"""WindowedList — the paging, cursor and page-indicator arithmetic both list
widgets stand on.

`CursorList` (a table with a row cursor) and `CheckList` (two-line rows with
membership toggles) look nothing alike and render nothing alike, but they page
identically: a cursor index into the full row list, a window that follows it
(`cursor // page_size`), `set_page_size` on a terminal resize, and a border
subtitle counting where you are. That arithmetic was written twice, and the
copies had already drifted — `CheckList.action_move` repainted on every
keypress including the ones that hit the end of the list, and drew its cursor
with a bare `"reverse"` literal rather than the constant documented as the
app-wide answer.

What stays with each widget is what actually differs: `_build` (the render),
and `CursorList`'s fetched-page mode, where `_rows` is one page the screen
fetched and the page keys ask it for another.
"""

from collections.abc import Iterable
from typing import Any

from rich.console import RenderableType
from textual.widgets import Static

from expense.commands._resource import DEFAULT_PAGE_ROWS


def page_indicator(
    start: int, shown: int, total: int, page_size: int, *, unit: str = "rows"
) -> str | None:
    """`rows 21-40 of 133 · page 2 of 7`, or None when one page holds it all."""
    if total <= page_size:
        return None
    page = start // page_size + 1
    pages = -(-total // page_size)  # ceil
    return f"{unit} {start + 1}-{start + shown} of {total} · page {page} of {pages}"


#: How "you are here" is drawn, app-wide: reverse video — the terminal's own
#: foreground and background, swapped. Colour-free, so it is correct on a dark,
#: light or Solarized ground by construction rather than by detection (the ANSI
#: palette decision, 2026-08-19).
#:
#: It must be applied as a **Rich style**, never as a Textual `text-style` rule.
#: Textual 8.2.7 drops `reverse` from `get_visual_style()` when foreground and
#: background are both `ansi_default` — which is exactly our theme — so a CSS
#: cursor renders identically to an unselected row. That is what made the home
#: menu cursor invisible until 2026-08-20; see `CursorOptionList`.
CURSOR_STYLE = "reverse"


class WindowedList(Static):
    """Base for a focusable list that shows one window of `_rows` at a time.

    Subclasses supply `_build()` and coerce their own row type into `_rows`.
    """

    can_focus = True

    #: What the page indicator counts. `CheckList` shows one transaction as two
    #: physical lines, so it counts items, not rows.
    PAGE_UNIT = "rows"

    def __init__(
        self,
        rows: Iterable[Any],
        *,
        empty: str,
        page_size: int = DEFAULT_PAGE_ROWS,
    ) -> None:
        super().__init__()
        self._rows: list[Any] = list(rows)
        self._empty = empty
        self._page_size = page_size
        self._cursor = 0

    # ---- the window ------------------------------------------------------
    @property
    def cursor_key(self) -> object | None:
        return self._rows[self._cursor].key if self._rows else None

    @property
    def _window_start(self) -> int:
        return (self._cursor // self._page_size) * self._page_size

    def _window(self) -> tuple[int, list[Any]]:
        """(start index, the rows to draw) — the one slice both renders take."""
        start = self._window_start
        return start, self._rows[start : start + self._page_size]

    def set_page_size(self, page_size: int) -> None:
        """Adaptive rows (2026-07-13): the screen re-measures on terminal resize
        and re-slices the window around the cursor. Row identity is by key, not
        position, so a re-slice cannot lose anything a screen is tracking."""
        if page_size < 1 or page_size == self._page_size:
            return
        self._page_size = page_size
        self._refresh()

    @property
    def page_status(self) -> str | None:
        """The border-subtitle string, or None when everything fits one page."""
        start, window = self._window()
        return page_indicator(
            start, len(window), len(self._rows), self._page_size, unit=self.PAGE_UNIT
        )

    def _refresh(self) -> None:
        self.border_subtitle = self.page_status or ""
        self.update(self._build())

    def _build(self) -> RenderableType:
        raise NotImplementedError

    # ---- movement --------------------------------------------------------
    def _move_cursor_to(self, index: int) -> None:
        """Clamp, and repaint only if the cursor actually went somewhere."""
        if not self._rows:
            return
        new = max(0, min(len(self._rows) - 1, index))
        if new == self._cursor:
            return
        self._cursor = new
        self._refresh()
        self._cursor_moved()

    def _cursor_moved(self) -> None:
        """Hook: the cursor landed on a new row. `CursorList` posts
        `Highlighted` here so a two-pane screen can follow along."""

    def action_move(self, delta: int) -> None:
        self._move_cursor_to(self._cursor + delta)

    def action_page(self, delta: int) -> None:
        self._move_cursor_to(self._cursor + delta * self._page_size)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "page":  # hide the page keys when one page holds it all
            return len(self._rows) > self._page_size
        return True
