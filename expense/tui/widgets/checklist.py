"""CheckList — a focusable one-line bank-line list with membership toggles.

Used by the reconciliation working screen: each bank line renders as one line,
the bank's columns only — checkbox, date, title, operation number, amount. A
checked row belongs to the batch; `space` toggles it and posts
`Toggled(key)`. In `read_only` mode (completed batch) there's no checkbox and
no toggle.

Rows are pure `(key, date, title, operation, amount_cents)` tuples so
formatting is unit-testable without an event loop.

Renders at most `page_size` rows — min(20, what fits the pane), the screen
calling `set_page_size` on resize — always window mode: the full batch stays
in memory, the visible window follows the cursor, and `pgdn`/`pgup` jump a
page. Membership is window-proof: `_checked` is a key-set over the whole
batch, so `c Complete` counts every checked row across all pages. Page status
renders as the list's last line (`rows 21-40 of 47 · page 2 of 3`).
"""

from collections.abc import Iterable, Sequence
from typing import NamedTuple

from rich import box
from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual.binding import Binding
from textual.message import Message

from expense.reads import DEFAULT_PAGE_ROWS
from expense.tui.theme import AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell, operation_cell
from expense.tui.widgets.cursor_list import list_cell
from expense.tui.widgets.windowed import CURSOR_STYLE, WindowedList


class Row(NamedTuple):
    """One bank-line row. ``key`` identifies it (carried on ``Toggled``); the
    rest are the bank's columns, in the order drawn."""

    key: object
    date: object
    title: object
    operation: object
    amount_cents: object

    @classmethod
    def coerce(cls, row: "RowInput") -> "Row":
        """Accept a plain ``(key, date, title, operation, amount_cents)`` tuple —
        what the pure row builders return — or an existing Row; always return a Row."""
        return row if isinstance(row, cls) else cls(*row)


# Row builders return plain tuples; the widget coerces them at its boundary.
RowInput = Row | tuple


class CheckList(WindowedList):
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
        self._palette = palette
        keys = [row.key for row in self._rows]
        if land_on is not None and land_on in keys:
            self._cursor = keys.index(land_on)

    def on_mount(self) -> None:
        self._refresh()
        if not self._read_only:
            self.focus()

    @property
    def checked(self) -> set:
        return set(self._checked)

    def _build(self) -> RenderableType:
        if not self._rows:
            return Text("  " + self._empty, style="dim")
        t = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_header=True)
        if not self._read_only:
            t.add_column("", width=3, no_wrap=True)
        t.add_column("Date", no_wrap=True)
        t.add_column("Title", no_wrap=True, overflow="ellipsis")
        t.add_column("Operation", no_wrap=True)
        t.add_column("Amount", justify="right", no_wrap=True)
        start, window = self._window()
        for i, (key, date, title, operation, amount) in enumerate(window, start=start):
            cells: list = [
                str(date or "")[:10],
                str(title or "(untitled)"),
                operation_cell(operation),
                amount_cell(amount, self._palette, AMOUNT_RULE),
            ]
            if not self._read_only:
                if key in self._checked:
                    mark = Text("[x]", style=self._palette.success)
                else:
                    mark = Text("[ ]", style="dim")
                cells = [mark, *cells]
            # The title is the bank's words: shown as typed, `[` and all.
            shown = [list_cell(c) for c in cells]
            t.add_row(*shown, style=CURSOR_STYLE if i == self._cursor else "")
        return t

    def action_toggle(self) -> None:
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
