"""CursorList — a focusable, keyboard-navigable table list with a row cursor.

Reused by every list screen (transactions, accounts, categories...).
Rows are `(key, cells)` pairs: `key` identifies the row (e.g. a record id) and
is carried on the `Selected` message; `cells` are the column strings. `_build()`
is pure, so formatting is unit-testable without an event loop.

Every list renders at most `page_size` rows — min(20, what fits the terminal)
since 2026-07-13 (adaptive rows, pick A + cap 20; the screen measures and calls
`set_page_size` on resize); `pgdn`/`pgup` page. Two modes share the
one widget:

- window mode (default): `_rows` holds the full dataset and the visible
  window follows the cursor (`cursor // page_size`), so `↑`/`↓` walk straight
  through page boundaries and cursor-restore-after-write lands on the right
  page for free.
- fetched-page mode (`page_meta=(offset, total)`): `_rows` is one page a
  screen fetched with real limit/offset; the page keys post `PageRequested`
  and the screen refetches (see `PagedListMixin`). `↑`/`↓` clamp at the edge —
  paging is always a deliberate keypress (mockup pick A).

The widget is its own quiet-border panel (app.tcss): screens name it via
`title` (border title) and the page status renders in the border subtitle
(mockup pick B) — `rows 21-40 of 133 · page 2 of 7`.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import NamedTuple

from rich import box
from rich.console import RenderableType
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.strip import Strip
from textual.widgets import OptionList

from expense.commands._resource import DEFAULT_PAGE_ROWS
from expense.tui.widgets.windowed import CURSOR_STYLE, WindowedList, page_indicator

__all__ = ["CURSOR_STYLE", "CursorList", "CursorOptionList", "Row", "RowInput", "page_indicator"]


class Row(NamedTuple):
    """One list row.

    ``key`` identifies the row (carried on ``Selected``/``Highlighted``);
    ``cells`` are the column values — plain strings or Rich renderables like a
    colored swatch; ``base_style`` is the Rich style applied when the row is not
    the cursor (e.g. ``"dim"`` for archived rows).
    """

    key: object
    cells: Sequence[object]
    base_style: str = ""

    @classmethod
    def coerce(cls, row: "RowInput") -> "Row":
        """Accept a plain ``(key, cells[, base_style])`` tuple — what the pure row
        builders return — or an existing Row; always return a Row."""
        return row if isinstance(row, cls) else cls(*row)


# Row builders return plain tuples; the widget coerces them at its boundary.
RowInput = Row | tuple


class CursorList(WindowedList):
    BINDINGS = [
        # Not shown in the footer: "the arrow keys move the cursor" is not worth a
        # footer slot (user, 2026-08-20 — "its obvious and it just occupies space
        # unnecessarily"). The keys are unchanged and the `?` card still lists them,
        # which is where a key that needs explaining belongs.
        Binding("down", "move(1)", "Navigate", tooltip="Down", show=False),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("enter", "select", "Open"),
        # Row selection for bulk edits (2026-09-12, mockup expense-world-home-as-
        # ledger.html). The widget only posts `Toggled`; it is live — key and
        # footer both — only on a screen that handles the message, the same
        # gate `enter` goes through in help.py (`check_action` below).
        Binding("space", "toggle", "Select", tooltip="Select / unselect the cursor row"),
        Binding("pagedown", "page(1)", "Next", key_display="pgdn", tooltip="Next page"),
        Binding("pageup", "page(-1)", "Prev", key_display="pgup", tooltip="Previous page"),
    ]

    class Selected(Message):
        def __init__(self, control: "CursorList", key: object, index: int) -> None:
            super().__init__()
            self._control = control
            self.key = key
            self.index = index

        @property
        def control(self) -> "CursorList":
            """The list that posted this — handlers on screens with several
            CursorLists must filter by source (backlog 6.2c)."""
            return self._control

    class Highlighted(Message):
        """Posted when the row cursor moves (live), carrying the new row's key.
        Lets a parent react as you navigate (e.g. a master→detail two-pane)."""

        def __init__(self, control: "CursorList", key: object, index: int) -> None:
            super().__init__()
            self._control = control
            self.key = key
            self.index = index

        @property
        def control(self) -> "CursorList":
            """The list that posted this — handlers on screens with several
            CursorLists must filter by source (backlog 6.2c)."""
            return self._control

    class Toggled(Message):
        """Posted on `space`: the screen owns the selection set and re-marks
        the rows; the widget keeps no selection state of its own, so paging
        and reloads cannot desynchronise it."""

        def __init__(self, control: "CursorList", key: object, index: int) -> None:
            super().__init__()
            self._control = control
            self.key = key
            self.index = index

        @property
        def control(self) -> "CursorList":
            return self._control

    class PageRequested(Message):
        """Posted in fetched-page mode when a page key needs data beyond the
        fetched window; the screen refetches (see PagedListMixin)."""

        def __init__(self, control: "CursorList", delta: int) -> None:
            super().__init__()
            self._control = control
            self.delta = delta

        @property
        def control(self) -> "CursorList":
            """The list that posted this — handlers on screens with several
            CursorLists must filter by source (backlog 6.2c)."""
            return self._control

    def __init__(
        self,
        headers: Sequence[str],
        rows: Iterable[RowInput],
        *,
        align_right: Iterable[int] = (),
        empty: str = "(empty)",
        title: str | None = None,
        page_size: int = DEFAULT_PAGE_ROWS,
        page_meta: tuple[int, int] | None = None,
        flex: Mapping[int, int] | None = None,
    ) -> None:
        """``flex`` maps a column index to a Rich ``ratio`` (2026-09-12, mockup
        expense-world-ledger-column-fit.html, option A). Columns named there are
        free text: the others take their natural width first and the flex
        columns share whatever the terminal has left, in ratio, each cell cut by
        the table at the edge of the column it actually has — so a cell is never
        pre-truncated shorter than its column. Left empty (every list but the
        ledger), Rich spreads the slack over every column in proportion to the
        content it measured, as before."""
        super().__init__([Row.coerce(r) for r in rows], empty=empty, page_size=page_size)
        self._headers = list(headers)
        self._align = set(align_right)
        self._flex = dict(flex or {})
        self._page_meta = page_meta
        if title is not None:
            self.border_title = title

    def on_mount(self) -> None:
        self._refresh()
        self.focus()

    def set_rows(self, rows: Iterable[RowInput]) -> None:
        self._rows = [Row.coerce(r) for r in rows]
        self._cursor = min(self._cursor, max(0, len(self._rows) - 1))
        self._refresh()

    def index_of(self, key: object) -> int:
        for i, row in enumerate(self._rows):
            if row.key == key:
                return i
        return 0

    def set_cursor(self, index: int) -> None:
        if self._rows:
            self._cursor = max(0, min(len(self._rows) - 1, index))
            self._refresh()

    @property
    def page_status(self) -> str | None:
        """The border-subtitle string, or None when everything fits one page.

        Fetched-page mode counts against the engine's total, not the page in
        hand: `_rows` is one page, and `rows 21-40 of 40` would claim the list
        ends where the fetch did.
        """
        if self._page_meta is not None:
            offset, total = self._page_meta
            return page_indicator(offset, len(self._rows), total, self._page_size)
        return super().page_status

    @staticmethod
    def _cell(value: object) -> object:
        # pass Rich renderables (e.g. a Text swatch) through; stringify the rest.
        return value if isinstance(value, (str, Text)) else str(value)

    def _build(self) -> RenderableType:
        if not self._rows:
            return Text("  " + self._empty, style="dim")
        t = Table(box=box.SIMPLE, expand=True, pad_edge=False)
        for i, header in enumerate(self._headers):
            t.add_column(
                header,
                justify="right" if i in self._align else "left",
                no_wrap=True,
                ratio=self._flex.get(i),
            )
        start, window = self._window()
        for r, row in enumerate(window, start=start):
            style = CURSOR_STYLE if r == self._cursor else row.base_style
            t.add_row(*[self._cell(c) for c in row.cells], style=style)
        return t

    def _cursor_moved(self) -> None:
        self.post_message(self.Highlighted(self, self.cursor_key, self._cursor))

    def action_page(self, delta: int) -> None:
        if self._page_meta is not None:
            # fetched-page mode: the screen owns the data; ask it to turn.
            self.post_message(self.PageRequested(self, delta))
            return
        super().action_page(delta)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "page":  # hide the page keys when one page holds it all
            if self._page_meta is not None:
                return self._page_meta[1] > self._page_size
            return len(self._rows) > self._page_size
        if action == "toggle":  # only where a screen owns a selection
            try:
                host = self.screen
            except Exception:
                return False
            # False = neither live nor in the footer (Textual 8: None would
            # keep the row, greyed — a key that says "not here" every time)
            return hasattr(host, "on_cursor_list_toggled")
        return True

    def action_select(self) -> None:
        if self._rows:
            self.post_message(self.Selected(self, self._rows[self._cursor].key, self._cursor))

    def action_toggle(self) -> None:
        if self._rows:
            self.post_message(self.Toggled(self, self._rows[self._cursor].key, self._cursor))


class CursorOptionList(OptionList):
    """An `OptionList` whose highlighted row is reverse video, like every other list.

    Textual draws `OptionList`'s highlight through CSS
    (`.option-list--option-highlighted`), and under this app's ANSI theme that
    path is a dead end: `block-cursor-foreground` and `block-cursor-background`
    are both `ansi_default`, so all the contrast has to come from
    `text-style: reverse` — and Textual 8.2.7 drops `reverse` when both colours
    are `ansi_default`. Measured, the highlighted row rendered
    `default on default`, byte-identical to its neighbours, so the home menu had
    no visible cursor at all (reported 2026-08-20). Overriding the rule in
    `app.tcss` does not help; the style is dropped there too.

    So the cursor is applied to the finished strip instead, which is the same
    place `CursorList` applies it — a Rich style, not a CSS one. Disabled
    options (the group headers) are skipped: they are never the cursor.

    `_lines` is Textual-internal, and deliberately so — it is the same mapping
    `OptionList.render_line` itself uses to turn a y offset into an option
    index, and there is no public equivalent. `test_tui_menu_cursor.py` asserts
    the highlighted row renders differently from its neighbours, so a Textual
    bump that moves this breaks a test rather than silently blinding the menu
    the way the original regression did.
    """

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        try:
            option_index, _offset = self._lines[self.scroll_offset.y + y]
        except IndexError:
            return strip
        if option_index != self.highlighted or self.options[option_index].disabled:
            return strip
        return strip.apply_style(Style(reverse=True))
