"""WindowedList — the paging, cursor and page-indicator arithmetic both list
widgets stand on.

`CursorList` (a table with a row cursor) and `CheckList` (bank-line rows with
membership toggles) look nothing alike and render nothing alike, but they page
identically: a cursor index into the full row list, a window that follows it
(`cursor // page_size`), `set_page_size` on a terminal resize, and a page
status line counting where you are. That arithmetic lives here once.

What stays with each widget is what actually differs: `_build` (the render),
and `CursorList`'s growing mode, where `pgdn` asks the screen for more rows
instead of turning a page.
"""

from collections.abc import Iterable
from typing import Any

from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.text import Text
from textual.widgets import Static

from expense.reads import DEFAULT_PAGE_ROWS


def page_indicator(
    start: int, shown: int, total: int, page_size: int, starts: list[int] | None = None
) -> str | None:
    """`rows 21-40 of 133 · page 2 of 7`, or None when one page holds it all.
    `starts`, when given, are the pages' first rows (pages of unequal height)."""
    if starts is not None:
        if len(starts) <= 1:
            return None
        page, pages = starts.index(start) + 1, len(starts)
    elif total <= page_size:
        return None
    else:
        page = start // page_size + 1
        pages = -(-total // page_size)  # ceil
    return f"rows {start + 1}-{start + shown} of {total} · page {page} of {pages}"


#: How "you are here" is drawn, app-wide: reverse video — the terminal's own
#: foreground and background, swapped. Colour-free, so it is correct on a dark,
#: light or Solarized ground by construction rather than by detection.
#:
#: It must be applied as a **Rich style**, never as a Textual `text-style` rule.
#: Textual 8.2.7 drops `reverse` from `get_visual_style()` when foreground and
#: background are both `ansi_default` — which is exactly our theme — so a CSS
#: cursor renders identically to an unselected row; see `CursorOptionList`.
CURSOR_STYLE = "reverse"


class WindowedList(Static):
    """Base for a focusable list that shows one window of `_rows` at a time.

    Subclasses supply `_build()` and coerce their own row type into `_rows`.
    """

    can_focus = True

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
        #: True for a list whose rows may cost more than a line (`_extra_lines`).
        self._varied = False
        # A line of content above the rule. Only a caption
        # that *disambiguates* earns one — see docs/tui.md §3.
        self._caption = caption
        self._divider: str | None = "rule"
        self._status_line = True
        #: The first row of the page last drawn; the footer is re-checked when it moves.
        self._shown_from = 0

    # ---- the window ------------------------------------------------------
    @property
    def cursor_key(self) -> object | None:
        return self._rows[self._cursor].key if self._rows else None

    @property
    def cursor_index(self) -> int:
        return self._cursor

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def _extra_lines(self, first: int, stop: int) -> int:
        """Lines rows `first` up to `stop` cost beyond one each, drawn around them
        on one page (a section label, say). Zero unless a list says otherwise."""
        return 0

    def _page_starts(self) -> list[int] | None:
        """The first row of every page when pages are not all `page_size` rows
        (some rows cost more than a line: `_extra_lines`); None when they are.
        A page takes rows while their lines fit `page_size`, one row at least."""
        if not self._varied:
            return None
        starts, i, n = [], 0, len(self._rows)
        while i < n:
            starts.append(i)
            j = i + 1
            while j < n and (j + 1 - i) + self._extra_lines(i, j + 1) <= self._page_size:
                j += 1
            i = j
        return starts or [0]

    def _page_bounds(self) -> tuple[int, int]:
        """(start, stop) of the page the cursor is on."""
        starts = self._page_starts()
        if starts is None:
            start = (self._cursor // self._page_size) * self._page_size
            return start, start + self._page_size
        start = max(s for s in starts if s <= self._cursor)
        later = [s for s in starts if s > start]
        return start, later[0] if later else len(self._rows)

    @property
    def _window_start(self) -> int:
        return self._page_bounds()[0]

    def _window(self) -> tuple[int, list[Any]]:
        """(start index, the rows to draw) — the one slice both renders take."""
        start, stop = self._page_bounds()
        return start, self._rows[start:stop]

    def set_page_size(self, page_size: int) -> None:
        """Adaptive rows: the screen re-measures on terminal resize
        and re-slices the window around the cursor. Row identity is by key, not
        position, so a re-slice cannot lose anything a screen is tracking."""
        if page_size < 1 or page_size == self._page_size:
            return
        self._page_size = page_size
        self._refresh()

    @property
    def page_status(self) -> str | None:
        """`rows 21-40 of 133 · page 2 of 7`, or None when one page holds it all.

        Rendered as the list's last line; tests read this property rather than
        the render.
        """
        start, window = self._window()
        return page_indicator(
            start, len(window), len(self._rows), self._page_size, self._page_starts()
        )

    @property
    def caption(self) -> str | None:
        return self._caption

    def set_caption(self, caption: str | None) -> None:
        """Change the caption and repaint.

        A caption is ordinary content and does not repaint on assignment, so
        the statements browse — which rewrites
        its lower caption every time the account cursor moves — must come
        through here rather than assigning the attribute.
        """
        if caption == self._caption:
            return
        self._caption = caption
        self._refresh()

    def set_divider(self, divider: str | None) -> None:
        """What stands between the caption and the rows: `"rule"` (the default), `"blank"`
        (an empty line) or `None` (nothing, one line shorter)."""
        if divider == self._divider:
            return
        self._divider = divider
        self._refresh()

    def set_status_line(self, shown: bool) -> None:
        """Whether the page-status line stands under the rows. A list that never has a
        status to say (a growing one, whose caption counts what is loaded) draws without it
        and is one line shorter."""
        if shown == self._status_line:
            return
        self._status_line = shown
        self._refresh()

    def _refresh(self) -> None:
        self.update(self.framed())
        first = self._page_bounds()[0]
        if first != self._shown_from and self.is_attached:
            self.refresh_bindings()  # `pgup` shows only where a page lies before
        self._shown_from = first

    def framed(self) -> RenderableType:
        """Caption, rule, the subclass's render, page status.

        No box — horizontal rules divide sections (docs/tui.md §2) — so the
        caption and page status are ordinary content, drawn here, in the one
        place every repaint of a `CursorList` passes through (`CheckList` draws
        its own frame: no rule, no caption).

        **The status line is drawn, blank when there is nothing to say,
        unless the list was told to leave it out (`set_status_line`).**
        `page_status` is None on a single page, and a line that came and
        went with the rows would make the widget's height depend on how many
        it holds; it is fixed per list or mode, never by row count. That is
        what `AdaptiveRowsMixin` measures in order to
        decide how many rows to ask for. A constant frame is what keeps that
        arithmetic honest; see `LIST_FRAME_LINES`.

        **`Rule` is given an explicit style.** Rich's own default is
        `rule.line`, which resolves to a literal green, and
        `test_no_literal_color_styles_in_tui` greps *source* — it cannot see a
        library default. `test_the_frame_draws_no_colour` pins it by render.

        A named method rather than an expression inlined into `_refresh`: it
        takes no app and no layout, so `LIST_FRAME_LINES` can be derived from
        what is actually drawn.
        """
        parts: list[RenderableType] = []
        if self._caption:
            parts.append(Text(self._caption, style="dim"))
        if self._divider == "rule":
            parts.append(Rule(style="dim"))
        elif self._divider == "blank":
            parts.append(Text(""))
        parts.append(self._build())
        if self._status_line:
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
        starts = self._page_starts()
        if starts is None:
            self._move_cursor_to(self._cursor + delta * self._page_size)
            return
        here = starts.index(self._page_bounds()[0])
        self._move_cursor_to(starts[max(0, min(len(starts) - 1, here + delta))])

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "page":  # no page key when one page holds it all; no `pgup` on page 1
            if parameters and parameters[0] < 0:  # `pgup`: only with a page before this one
                return self._page_bounds()[0] > 0
            starts = self._page_starts()
            return len(starts) > 1 if starts is not None else len(self._rows) > self._page_size
        return True
