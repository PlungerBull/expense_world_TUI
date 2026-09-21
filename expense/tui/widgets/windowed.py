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

from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.text import Text
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
        caption: str | None = None,
    ) -> None:
        super().__init__()
        self._rows: list[Any] = list(rows)
        self._empty = empty
        self._page_size = page_size
        self._cursor = 0
        # A line of content above the rule, not a border title. Only a caption
        # that *disambiguates* earns one — see docs/tui.md §3.
        self._caption = caption

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
        """`rows 21-40 of 133 · page 2 of 7`, or None when one page holds it all.

        Rendered as the list's last line since 2026-09-20. It was the panel's
        `border_subtitle` until the borders went; the string is unchanged, and
        every test that reads it reads this property rather than the border.
        """
        start, window = self._window()
        return page_indicator(
            start, len(window), len(self._rows), self._page_size, unit=self.PAGE_UNIT
        )

    @property
    def caption(self) -> str | None:
        return self._caption

    def set_caption(self, caption: str | None) -> None:
        """Change the caption and repaint.

        A border title repainted itself when assigned; a caption is ordinary
        content and does not, so the Reconciliations browse — which rewrites
        its lower caption every time the account cursor moves — must come
        through here rather than assigning the attribute.
        """
        if caption == self._caption:
            return
        self._caption = caption
        self._refresh()

    def _refresh(self) -> None:
        self.update(self.framed())

    def framed(self) -> RenderableType:
        """Caption, rule, the subclass's render, page status.

        The panel border carried the caption on its top edge and the page
        status on its bottom until 2026-09-20, when the owner's rule — no
        cards, no vertical lines, horizontal rules divide sections
        (docs/tui.md §2) — took the box away. Both become ordinary content
        here, in the one place every repaint of both list widgets passes
        through, so neither subclass's `_build` had to change.

        **The status line is always drawn, blank when there is nothing to
        say.** `page_status` is None on a single page, and a line that came
        and went would make the widget's height depend on how many rows it
        holds — which is exactly what `AdaptiveRowsMixin` measures in order to
        decide how many rows to ask for. A constant frame is what keeps that
        arithmetic honest; see `LIST_FRAME_LINES`.

        **`Rule` is given an explicit style.** Rich's own default is
        `rule.line`, which resolves to a literal green, and
        `test_no_literal_color_styles_in_tui` greps *source* — it cannot see a
        library default. `test_the_frame_draws_no_colour` pins it by render.

        A named method rather than an expression inlined into `_refresh`: it
        takes no app and no layout, so `LIST_FRAME_LINES` can be derived from
        what is actually drawn. That is the test the 2026-08-29 miscount
        needed and did not have.
        """
        parts: list[RenderableType] = []
        if self._caption:
            parts.append(Text(self._caption, style="dim"))
        parts.append(Rule(style="dim"))
        parts.append(self._build())
        parts.append(Text(self.page_status or "", style="dim"))
        return Group(*parts)

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
