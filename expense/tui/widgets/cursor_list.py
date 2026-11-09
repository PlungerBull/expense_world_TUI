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
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.segment import Segment
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
    Called by `list_table`, the statement tick list (checklist.py) and
    the LOG bar's staged rows (`staged_table` in screens/log_bar.py)."""
    return value if isinstance(value, Text) else Text(str(value))


def _past_mark(columns: set[int]) -> set[int]:
    """`list_table(lead=True)`: the columns' indices once the mark joins the second column."""
    return {i - 1 for i in columns if i >= 1}


def _with_mark_joined(row: "Row") -> "Row":
    """`list_table(lead=True)`: the row with its mark and second cell in one cell."""
    mark = list_cell(row.cells[0]).copy()
    mark.pad_right(max(1 - mark.cell_len, 0))
    joined = Text.assemble(mark, " ", list_cell(row.cells[1]))
    return row._replace(cells=[joined, *row.cells[2:]])


def _check_header_rule(header_rule: bool, header_rule_span: tuple[int, int] | None) -> None:
    """A rule of its own (`header_rule_span`) stands where the table's would; both is a
    mistake."""
    if header_rule and header_rule_span is not None:
        raise ValueError("header_rule_span needs header_rule=False")


class RuleUnderHeader:
    """A table drawn with a rule of its own under its header row: `width` cells of `─`
    starting `indent` cells in, whatever the table's width (the rule of a table's box always
    spans the table). Cut to the room there is."""

    def __init__(self, table: Table, *, indent: int, width: int) -> None:
        self._table, self._indent, self._width = table, indent, width

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        lines = console.render_lines(self._table, options, pad=False)
        rule = max(min(self._width, options.max_width - self._indent), 0)
        for number, line in enumerate(lines):
            yield from line
            yield Segment.line()
            if number == 0:
                yield Segment(" " * self._indent)
                yield Segment("─" * rule, console.get_style("dim"))
                yield Segment.line()


def list_table(
    headers: Sequence[str],
    rows: Iterable[RowInput],
    *,
    align_right: Iterable[int] = (),
    flex: Mapping[int, int] | None = None,
    cursor: int | None = None,
    edge: bool = True,
    gap: int | None = None,
    header_rule: bool = True,
    gives_way: Iterable[int] = (),
    min_widths: Mapping[int, int] | None = None,
    lead: bool = False,
) -> Table:
    """The table a `CursorList` draws, for `rows` as given: one column per
    header, right-aligned where `align_right` says, `flex` as `CursorList`
    takes it, each row in its base style and the row at index `cursor` (None:
    no row) as the cursor. Also the ledger's rows drawn where no list is, over
    the bulk pick's bar (`changed_rows` in screens/transactions.py), so they
    read in the ledger's own columns; `edge=False` drops the blank line above
    the header and below the last row, for a table under a caption. `gap` is the
    blank cells between two columns; left out, the table's own three. `header_rule=False`
    draws no line under the header (and, with it, no edge lines either). A column in
    `gives_way` is the one that narrows when the row is too wide, its cells cut with `…`,
    before any other column loses a letter; without one, Rich narrows the widest columns.
    With one the table does not stretch to the room (so `flex` is left out): the others sit
    at their natural width and only that column is cut. `min_widths` maps a column index to the
    least width it is drawn at. `lead=True` makes the first column a one-cell mark (a flag, or
    nothing) drawn right before the second, one blank between, in the second's column: the
    mark is packed to the date it flags, whatever `gap` is between the other columns. Every
    column index above stands for the columns as given, the mark's included."""
    right = set(align_right)
    yields = set(gives_way)
    ratios = dict(flex or {})
    least = dict(min_widths or {})
    rows = list(rows)
    if lead:
        headers = [" " * (max(len(headers[0]), 1) + 1) + headers[1], *headers[2:]]
        rows = [_with_mark_joined(Row.coerce(r)) for r in rows]
        right, yields = _past_mark(right), _past_mark(yields)
        ratios = {i - 1: v for i, v in ratios.items() if i >= 1}
        least = {i - 1: v for i, v in least.items() if i >= 1}
    # the box's one blank cell between columns goes with the box, so the padding makes it up
    t = Table(
        box=box.SIMPLE if header_rule else None, expand=not yields, pad_edge=False, show_edge=edge
    )
    between = 0 if header_rule else 1
    if gap is not None:
        t.padding = (0, 0, 0, max(gap - 1, 0) + between)
    elif not header_rule:
        t.padding = (0, 1, 0, 2)
    for i, header in enumerate(headers):
        t.add_column(
            header,
            justify="right" if i in right else "left",
            no_wrap=i not in yields,
            overflow="ellipsis",
            ratio=ratios.get(i),
            min_width=least.get(i),
        )
    for r, item in enumerate(rows):
        row = Row.coerce(item)
        style = CURSOR_STYLE if r == cursor else row.base_style
        cells = [list_cell(c) for c in row.cells]
        for i in yields & set(range(len(cells))):
            cells[i] = cells[i].copy()
            cells[i].no_wrap, cells[i].overflow = True, "ellipsis"
        t.add_row(*cells, style=style)
    return t


#: Every action a `CursorList` binds, for a list whose `?` card lists none while it is empty.
LIST_KEYS = frozenset({"move", "select", "toggle", "more", "page"})


def waits_for_a_row(owner, action: str) -> bool:
    """True when `owner` (a list widget or the screen around one) names `action` in its
    `CARD_NEEDS_A_ROW` class frozenset and its `has_rows` is false: the footer's
    `check_action` drops the key and the `?` card does not list it. Both ask this one test."""
    return action in getattr(owner, "CARD_NEEDS_A_ROW", ()) and not owner.has_rows


class CursorList(WindowedList):
    #: No list key, card or footer, while the list is empty (`waits_for_a_row`, help.py).
    CARD_NEEDS_A_ROW: frozenset[str] = LIST_KEYS

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
        gap: int | None = None,
        edge: bool = True,
        header_rule: bool = True,
        divider: str | None = "rule",
        gives_way: Iterable[int] = (),
        min_widths: Mapping[int, int] | None = None,
        lead: bool = False,
        header_rule_span: tuple[int, int] | None = None,
    ) -> None:
        """``header_rule=False`` draws no line under the header; ``header_rule_span`` is the
        ``(indent, width)`` of a rule drawn there on its own, at that width whatever the
        table's (`RuleUnderHeader`), and needs ``header_rule=False``; ``divider`` is what stands
        between the caption and the rows (`WindowedList.set_divider`).
        ``gap`` is the blank cells between two columns, three when left out.
        ``edge=False`` draws the table without its one-cell side edge (see `list_table`).
        ``gives_way`` names the columns that narrow first when the row is too wide.
        ``min_widths`` and ``lead`` are `list_table`'s.
        ``flex`` maps a column index to a Rich ``ratio``. Columns named there are
        free text: the others take their natural width first and the flex
        columns share whatever the terminal has left, in ratio, each cell cut by
        the table at the edge of the column it actually has — so a cell is never
        pre-truncated shorter than its column. Left empty (every `CursorList` but
        the ledger's), Rich spreads the slack over every column in proportion to
        the content it measured."""
        super().__init__(
            [Row.coerce(r) for r in rows], empty=empty, page_size=page_size, caption=caption
        )
        self._headers = list(headers)
        self._align = set(align_right)
        self._flex = dict(flex or {})
        self._gap = gap
        self._edge = edge
        _check_header_rule(header_rule, header_rule_span)
        self._header_rule = header_rule
        self._divider = divider
        self._gives_way = set(gives_way)
        self._min_widths = dict(min_widths or {})
        self._lead = lead
        self._header_rule_span = header_rule_span
        self._more: bool | None = None  # None: not growing; else "more rows exist"

    def set_growth(self, *, more: bool | None) -> None:
        """Enter growing mode and say whether the engine has rows past these;
        `None` leaves it (a pane that swaps back to listing something whole)."""
        self._more = more
        self.refresh_bindings()

    def append_rows(self, rows: Iterable[RowInput], *, more: bool) -> None:
        """Add rows at the end and put the cursor on the first new one.
        An empty page leaves the cursor where it was."""
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

    def set_headers(
        self,
        headers: Sequence[str],
        *,
        align_right: Iterable[int] = (),
        gap: int | None = None,
        flex: Mapping[int, int] | None = None,
        edge: bool = True,
        header_rule: bool = True,
        gives_way: Iterable[int] = (),
        min_widths: Mapping[int, int] | None = None,
        lead: bool = False,
        header_rule_span: tuple[int, int] | None = None,
    ) -> None:
        """Relabel the columns in place — for a pane that lists two different
        things (the Statements lower pane: statements, or the account's rows in
        no statement). Rebuilding the widget instead would drop the
        caption, the page size the screen computed and the focus. `align_right`, `gap`,
        `flex`, `edge`, `header_rule`, `gives_way`, `min_widths`, `lead` and `header_rule_span`
        are set afresh: one left out falls back to its default, it does not keep the earlier
        headers' value.
        """
        _check_header_rule(header_rule, header_rule_span)
        self._headers = list(headers)
        self._align = set(align_right)
        self._gap = gap
        self._flex = dict(flex or {})
        self._edge = edge
        self._header_rule = header_rule
        self._gives_way = set(gives_way)
        self._min_widths = dict(min_widths or {})
        self._lead = lead
        self._header_rule_span = header_rule_span
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
        table = list_table(
            self._headers,
            window,
            align_right=self._align,
            flex=self._flex,
            cursor=self._cursor - start,
            gap=self._gap,
            edge=self._edge,
            header_rule=self._header_rule,
            gives_way=self._gives_way,
            min_widths=self._min_widths,
            lead=self._lead,
        )
        if self._header_rule_span is None:
            return table
        indent, width = self._header_rule_span
        return RuleUnderHeader(table, indent=indent, width=width)

    def _cursor_moved(self) -> None:
        self.post_message(self.Highlighted(self, self.cursor_key, self._cursor))

    def action_more(self) -> None:
        if self._more:
            self.post_message(self.MoreRequested(self))

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if waits_for_a_row(self, action):
            return False  # no row to act on: the key leaves the footer, and returns with the first
        if action == "more":
            return bool(self._more)
        if action == "page":  # the base's rule: none on one page, no `pgup` on page 1
            if self._more is not None and parameters and parameters[0] > 0:
                return False  # growing: pgdn is "more", never "next page"
            return super().check_action(action, parameters)
        if action == "toggle":  # only where a screen owns a selection
            try:
                host = self.screen
            except Exception:
                return False
            # False = neither live nor in the footer (Textual 8: None would
            # keep the row, greyed — a key that says "not here" every time)
            return hasattr(host, "on_cursor_list_toggled")
        return True

    @property
    def has_rows(self) -> bool:
        """Whether the list holds a row now."""
        return bool(self._rows)

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
