"""CheckList — a focusable one-line bank-line list with membership toggles.

Used by the statement's screen: each bank line renders as one line, the bank's
columns only — checkbox, date, title, operation number, currency, amount. A
checked row belongs to the statement; `space` toggles it and posts
`Toggled(key)`. In `read_only` mode (completed statement) there's no checkbox
and no toggle, and a `numbered` list leads with the line's number on the paper
(`#`, a dim `—` on a row with none). Rows marked `apart` (an account's opening
balance, no row of the bank's paper) are listed last, under their own label.

Rows are pure `(key, date, title, operation, amount_cents[, currency, number,
apart])` tuples so formatting is unit-testable without an event loop.

Renders at most `page_size` rows — min(20, what fits the pane), the screen
calling `set_page_size` on resize — always window mode: the full statement stays
in memory, the visible window follows the cursor, and `pgdn`/`pgup` jump a
page. Membership is window-proof: `_checked` is a key-set over the whole
statement, so `c Complete` counts every checked row across all pages. Page status
renders as the list's last line (`rows 21-40 of 47 · page 2 of 3`).
"""

from collections.abc import Callable, Iterable, Sequence
from typing import NamedTuple

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from textual.binding import Binding
from textual.message import Message

from expense.formatting import title_or_untitled
from expense.reads import DEFAULT_PAGE_ROWS
from expense.tui.theme import PALETTE, TRANSACTION_RULE, Palette
from expense.tui.widgets.cells import amount_cell, operation_cell
from expense.tui.widgets.cursor_list import list_cell
from expense.tui.widgets.windowed import CURSOR_STYLE, WindowedList

#: The label over the rows that hold no place on the bank's paper.
APART_LABEL = "Not on the paper"
#: Blank cells between two columns; the title's and the amount's least width.
GAP = 2
#: Blank cells before the first column, beside the list's one-cell gutter (`app.tcss`).
INDENT = 1
TITLE_WIDTH = 24
AMOUNT_WIDTH = 9


class _Listing:
    """A renderable that draws itself at the width it is given: `draw(width)`."""

    def __init__(self, draw: Callable[[int], RenderableType]) -> None:
        self._draw = draw

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self._draw(options.max_width)


class Row(NamedTuple):
    """One bank-line row. ``key`` identifies it (carried on ``Toggled``); the
    rest are the bank's columns, in the order drawn."""

    key: object
    date: object
    title: object
    operation: object
    amount_cents: object
    currency: object = None
    number: object = None
    apart: bool = False

    @classmethod
    def coerce(cls, row: "RowInput") -> "Row":
        """Accept a plain tuple of the fields above — what the pure row builders
        return — or an existing Row; always return a Row."""
        return row if isinstance(row, cls) else cls(*row)


# Row builders return plain tuples; the widget coerces them at its boundary.
RowInput = Row | tuple


class CheckList(WindowedList):
    #: Lines drawn around the rows: the blank line above the header, the header,
    #: and the page status line.
    FRAME_LINES = 3

    BINDINGS = [
        # Not shown in the footer: "the arrow keys move the cursor" is not worth a
        # footer slot — it is obvious and only occupies space. The keys are
        # unchanged and the `?` card still lists them, which is where a key that
        # needs explaining belongs.
        Binding("down", "move(1)", "Navigate", tooltip="Down", show=False),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("space", "toggle", "Toggle"),
        Binding("pagedown", "page(1)", "Next", key_display="pgdn", tooltip="Next page"),
        Binding("pageup", "page(-1)", "Prev", key_display="pgup", tooltip="Previous page"),
    ]

    class Toggled(Message):
        def __init__(self, key: object, checked: bool) -> None:
            super().__init__()
            self.key = key
            self.checked = checked

    def __init__(
        self,
        rows: Iterable[RowInput],
        checked: Sequence[object] = (),
        *,
        read_only: bool = False,
        numbered: bool = False,
        empty: str = "(no transactions)",
        palette: Palette = PALETTE,  # value object: _build must stay app-less
        page_size: int = DEFAULT_PAGE_ROWS,
        land_on: object | None = None,
    ) -> None:
        """`land_on` is the key of the row the cursor starts on; the first row
        when it is absent or names no row."""
        super().__init__([Row.coerce(r) for r in rows], empty=empty, page_size=page_size)
        self._checked: set = set(checked)
        self._read_only = read_only
        self._numbered = numbered and read_only
        self._varied = any(r.apart for r in self._rows)
        self._palette = palette
        keys = [row.key for row in self._rows]
        if land_on is not None and land_on in keys:
            self._cursor = keys.index(land_on)

    #: The `?` card lists `space` only while `check_action` allows it (help.py).
    CARD_FOLLOWS_CHECK = frozenset({"toggle"})

    def on_mount(self) -> None:
        self._refresh()
        self.focus()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """`space` exists only on a list that ticks: False, not None, so a read-only
        list hides it from the footer as well as leaving it dead."""
        if action == "toggle":
            return not self._read_only
        return super().check_action(action, parameters)

    @property
    def checked(self) -> set:
        return set(self._checked)

    def _extra_lines(self, first: int, stop: int) -> int:
        """A page holding rows of both kinds also draws the blank line and the label
        between them (rows are listed in order, the `apart` ones last); a page of one
        kind draws neither, the label of an apart-only page standing where the header
        stands."""
        mixed = not self._rows[first].apart and self._rows[stop - 1].apart
        return 2 if mixed else 0

    def framed(self) -> RenderableType:
        """The list as the statement's screen draws it: no rule above it (the
        screen's own head sits over it), the page status as the last line, blank
        when one page holds every row. `FRAME_LINES` counts what is drawn around
        the rows."""
        return Group(self._build(), Text(self.page_status or "", style="dim"))

    def _build(self) -> RenderableType:
        if not self._rows:
            return Text("  " + self._empty, style="dim")
        return _Listing(self._listing)

    def _lead_header(self) -> str | None:
        if not self._read_only:
            return ""
        return "#" if self._numbered else None

    def _listing(self, width: int) -> RenderableType:
        """A blank line, then the header and the window's rows; the rows `apart`
        come after their label. Every column but the title is as wide as its
        longest cell over the window, so the two groups line up under one header;
        the title is as wide as its longest, at least `TITLE_WIDTH`, and gives way
        (an ellipsis) only when the line would not fit `width`."""
        start, window = self._window()
        indexed = list(enumerate(window, start=start))
        main = [(i, row) for i, row in indexed if not row.apart]
        apart = [(i, row) for i, row in indexed if row.apart]
        widths = self._widths(window)
        widths["title"] = self._title_width(window, widths, width)
        parts: list[RenderableType] = [Text("")]
        if main:
            parts.append(self._table(main, widths, header=True))
        if apart:
            lead = self._lead_header()
            indent = INDENT + (widths["lead"] + GAP if lead is not None else 0)
            if main:
                parts.append(Text(""))
            parts.append(Text(" " * indent + APART_LABEL, style="dim"))
            parts.append(self._table(apart, widths, header=False))
        return Group(*parts)

    def _widths(self, window: list[Row]) -> dict[str, int]:
        def longest(header: str, cells: list[object]) -> int:
            return max([len(header), *(len(list_cell(c).plain) for c in cells)])

        return {
            "lead": 3,
            "date": 10,
            "operation": longest("Operation", [operation_cell(r.operation) for r in window]),
            "cur": longest("Cur", [r.currency or "" for r in window]),
            "amount": max(
                AMOUNT_WIDTH,
                longest(
                    "Amount", [amount_cell(r.amount_cents, None, TRANSACTION_RULE) for r in window]
                ),
            ),
        }

    def _title_width(self, window: list[Row], widths: dict[str, int], width: int) -> int:
        lead = self._lead_header()
        fixed = INDENT + sum(
            GAP + widths[key]
            for key in (
                "date",
                "operation",
                "cur",
                "amount",
                *(("lead",) if lead is not None else ()),
            )
        )
        longest = max([TITLE_WIDTH, *(len(title_or_untitled(r.title)) for r in window)])
        return max(min(longest, width - fixed - GAP), 8)

    def _table(
        self, rows: list[tuple[int, Row]], widths: dict[str, int], *, header: bool
    ) -> Padding:
        t = Table(
            box=None,
            show_edge=False,
            pad_edge=False,
            expand=False,
            padding=(0, GAP, 0, 0),
            show_header=header,
            header_style="dim",
        )
        lead = self._lead_header()
        if lead is not None:
            t.add_column(lead, width=widths["lead"], no_wrap=True, justify="right")
        t.add_column("Date", width=widths["date"], no_wrap=True)
        t.add_column("Title", width=widths["title"], no_wrap=True, overflow="ellipsis")
        t.add_column("Operation", width=widths["operation"], no_wrap=True)
        t.add_column("Cur", width=widths["cur"], no_wrap=True)
        t.add_column("Amount", width=widths["amount"], justify="right", no_wrap=True)
        for i, row in rows:
            cells: list = [
                str(row.date or ""),
                title_or_untitled(row.title),
                operation_cell(row.operation),
                row.currency or "",
                amount_cell(row.amount_cents, self._palette, TRANSACTION_RULE),
            ]
            if not self._read_only:
                if row.key in self._checked:
                    mark = Text("[x]", style=self._palette.success)
                else:
                    mark = Text("[ ]", style="dim")
                cells = [mark, *cells]
            elif self._numbered:
                cells = [
                    Text("—", style="dim") if row.number is None else str(row.number),
                    *cells,
                ]
            # The title is the bank's words: shown as typed, `[` and all.
            shown = [list_cell(c) for c in cells]
            t.add_row(*shown, style=CURSOR_STYLE if i == self._cursor else "")
        return Padding(t, (0, 0, 0, INDENT))

    # Textual's DOMNode has its own `action_toggle(attribute_name)`; the `toggle` binding here
    # is a different action, and mypy cannot express that a subclass may shadow it.
    def action_toggle(self) -> None:  # type: ignore[override]
        if self._read_only or not self._rows:
            return
        key = self.cursor_key
        now_checked = key not in self._checked
        if now_checked:
            self._checked.add(key)
        else:
            self._checked.discard(key)
        self._refresh()
        self.post_message(self.Toggled(key, now_checked))
