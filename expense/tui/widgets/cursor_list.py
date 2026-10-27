"""CursorList — a focusable, keyboard-navigable table list with a row cursor.

Reused by every list screen (transactions, accounts, categories...).
Rows are `(key, cells)` pairs: `key` identifies the row (e.g. a record id) and
is carried on the `Selected` message; `cells` are the column values, plain
strings or Rich `Text` (`list_cell` says how each is drawn). `_build()` is
pure, so formatting is unit-testable without an event loop.

Every list renders at most `page_size` rows — min(20, what fits the terminal)
(the screen measures and calls `set_page_size` on resize); `pgdn`/`pgup` page. Two modes share the
one widget:

- window mode (default): `_rows` holds the full dataset and the visible
  window follows the cursor (`cursor // page_size`), so `↑`/`↓` walk straight
  through page boundaries and cursor-restore-after-write lands on the right
  page for free.
- growing mode (`set_growth(more=…)`): `_rows` is every row loaded so far
  and the window follows the cursor, as in window mode. `pgdn` does not turn a
  page: it posts `MoreRequested`, the screen fetches the next `GROW_STEP` rows
  by cursor and appends them (`append_rows`), and the cursor lands on the first
  new one. The engine hands out "the rows after this one", never "row 41", so
  a list that only ever grows at the end is the shape that fits it (see
  `GrowingRead` in `screens/_growing.py`).

No border (app.tcss): an optional caption above a rule, and the page status
as the list's last line — `rows 21-40 of 133 · page 2 of 7`.
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

from expense.reads import DEFAULT_PAGE_ROWS
from expense.tui.widgets.windowed import CURSOR_STYLE, WindowedList, page_indicator

__all__ = [
    "CURSOR_STYLE",
    "GROW_STEP",
    "CursorList",
    "CursorOptionList",
    "Row",
    "RowInput",
    "list_cell",
    "list_table",
    "page_indicator",
]

#: How many rows one `pgdn` adds to a growing list — ten at a time. The
#: first load is the same size.
GROW_STEP = 10


class Row(NamedTuple):
    """One list row.

    ``key`` identifies the row (carried on ``Selected``/``Highlighted``);
    ``cells`` are the column values — plain strings, shown as the words they
    hold (never read as markup), or Rich ``Text`` the app styled itself, like a
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


def list_cell(value: object) -> Text:
    """A list cell as its table draws it. A `Text` (a swatch, a coloured
    amount, a mark: the app's own styling) is drawn as built; anything else is
    words, a name or a title as the engine holds it, drawn as `Text` so a
    `[like this]`, a `[/]` or a lone `[` shows as it is, never read as markup.
    Called by `list_table`, the reconciliation tick list (checklist.py) and
    the LOG bar's staged rows (`staged_table` in screens/log_bar.py)."""
    return value if isinstance(value, Text) else Text(str(value))


def list_table(
    headers: Sequence[str],
    rows: Iterable[RowInput],
    *,
    align_right: Iterable[int] = (),
    flex: Mapping[int, int] | None = None,
    cursor: int | None = None,
    edge: bool = True,
) -> Table:
    """The table a `CursorList` draws, for `rows` as given: one column per
    header, right-aligned where `align_right` says, `flex` as `CursorList`
    takes it, each row in its base style and the row at index `cursor` (None:
    no row) as the cursor. Also the ledger's rows drawn where no list is, over
    the bulk pick's bar (`changed_rows` in screens/transactions.py), so they
    read in the ledger's own columns; `edge=False` drops the blank line above
    the header and below the last row, for a table under a caption."""
    right = set(align_right)
    ratios = dict(flex or {})
    t = Table(box=box.SIMPLE, expand=True, pad_edge=False, show_edge=edge)
    for i, header in enumerate(headers):
        t.add_column(
            header,
            justify="right" if i in right else "left",
            no_wrap=True,
            ratio=ratios.get(i),
        )
    for r, item in enumerate(rows):
        row = Row.coerce(item)
        style = CURSOR_STYLE if r == cursor else row.base_style
        t.add_row(*[list_cell(c) for c in row.cells], style=style)
    return t


class CursorList(WindowedList):
    BINDINGS = [
        # Not shown in the footer: "the arrow keys move the cursor" is not worth a
        # footer slot — it is obvious and only occupies space. The keys are
        # unchanged and the `?` card still lists them, which is where a key that
        # needs explaining belongs.
        Binding("down", "move(1)", "Navigate", tooltip="Down", show=False),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("enter", "select", "Open"),
        # Row selection for bulk edits. The widget only posts `Toggled`; it is live — key and
        # footer both — only on a screen that handles the message, the same
        # gate `enter` goes through in help.py (`check_action` below).
        Binding("space", "toggle", "Select", tooltip="Select / unselect the cursor row"),
        # Two bindings on one key: Textual tries the next when `check_action`
        # refuses the first, so a growing list reads "10 more" and every other
        # list keeps "Next".
        Binding(
            "pagedown",
            "more",
            f"{GROW_STEP} more",
            key_display="pgdn",
            tooltip=f"Load the next {GROW_STEP} rows under these",
        ),
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
            CursorLists must filter by source."""
            return self._control

    class MoreRequested(Message):
        """Growing mode: `pgdn` asks the screen for the next rows."""

        def __init__(self, control: "CursorList") -> None:
            super().__init__()
            self._control = control

        @property
        def control(self) -> "CursorList":
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
            CursorLists must filter by source."""
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

    def __init__(
        self,
        headers: Sequence[str],
        rows: Iterable[RowInput],
        *,
        align_right: Iterable[int] = (),
        empty: str = "(empty)",
        caption: str | None = None,
        page_size: int = DEFAULT_PAGE_ROWS,
        flex: Mapping[int, int] | None = None,
    ) -> None:
        """``flex`` maps a column index to a Rich ``ratio``. Columns named there are
        free text: the others take their natural width first and the flex
        columns share whatever the terminal has left, in ratio, each cell cut by
        the table at the edge of the column it actually has — so a cell is never
        pre-truncated shorter than its column. Left empty (every list but the
        ledger), Rich spreads the slack over every column in proportion to the
        content it measured, as before."""
        super().__init__(
            [Row.coerce(r) for r in rows], empty=empty, page_size=page_size, caption=caption
        )
        self._headers = list(headers)
        self._align = set(align_right)
        self._flex = dict(flex or {})
        self._more: bool | None = None  # None: not growing; else "more rows exist"

    def set_growth(self, *, more: bool | None) -> None:
        """Enter growing mode and say whether the engine has rows past these;
        `None` leaves it (a pane that swaps back to listing something whole)."""
        self._more = more
        self.refresh_bindings()

    def append_rows(self, rows: Iterable[RowInput], *, more: bool) -> None:
        """Add rows at the end and put the cursor on the first new one.
        An empty batch leaves the cursor where it was."""
        first_new = len(self._rows)
        self._rows.extend(Row.coerce(r) for r in rows)
        self._more = more
        if len(self._rows) > first_new:
            self._cursor = first_new
            self._cursor_moved()
        self._refresh()
        self.refresh_bindings()

    def on_mount(self) -> None:
        self._refresh()
        self.focus()

    def set_rows(self, rows: Iterable[RowInput]) -> None:
        self._rows = [Row.coerce(r) for r in rows]
        self._cursor = min(self._cursor, max(0, len(self._rows) - 1))
        self._refresh()

    def set_headers(self, headers: Sequence[str], *, align_right: Iterable[int] = ()) -> None:
        """Relabel the columns in place — for a pane that lists two different
        things (the Reconciliations lower pane: batches, or the account's rows in
        no batch). Rebuilding the widget instead would drop the
        caption, the page size the screen computed and the focus.
        """
        self._headers = list(headers)
        self._align = set(align_right)
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
        """The page-status line, or None when everything fits one page."""
        if self._more is not None:
            # "rows 11-20 of 20" would count what is loaded, not what exists;
            # a growing list's screen states `N of M loaded` itself.
            return None
        return super().page_status

    def _build(self) -> RenderableType:
        if not self._rows:
            return Text("  " + self._empty, style="dim")
        start, window = self._window()
        return list_table(
            self._headers,
            window,
            align_right=self._align,
            flex=self._flex,
            cursor=self._cursor - start,
        )

    def _cursor_moved(self) -> None:
        self.post_message(self.Highlighted(self, self.cursor_key, self._cursor))

    def action_more(self) -> None:
        if self._more:
            self.post_message(self.MoreRequested(self))

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "more":
            return bool(self._more)
        if action == "page":  # hide the page keys when one page holds it all
            if self._more is not None and parameters and parameters[0] > 0:
                return False  # growing: pgdn is "more", never "next page"
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
    no visible cursor at all. Overriding the rule in
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
