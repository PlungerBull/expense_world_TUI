"""The leftover lines — a statement PDF's upload refused while bank lines sit in no statement
on days the close would seal.

The engine refuses the upload, dry run and apply alike, naming the lines by id in
`error.details` (`expense.bank_import.statement.loose_lines`;
contract: POST /v1/statements/import, "Response"). The preview opens this screen in its
place, a full screen of the upload's run:

    esc Cancel  ⏎ Edit  d Delete  r Read again

The lines are read by their ids in one read (`reads.fetch_bank_lines_by_ids`) and listed in the
order the refusal names them; a line deleted meanwhile is simply absent. `d` deletes a line
after the delete question and the lines are read again, the cursor on row 1. `⏎` opens a line in
the ledger's Edit form; a save sends the PDF again, as `r` does. `r` sends the same PDF again as a
dry run, which is the preview's own: it opens the preview once nothing is left over, and this
screen again with the new lines while some are. The refusal names at most 200 lines; past
them the head says how many there are in all and that `r` reads the paper again for the rest.
Nothing here decides which lines refuse or when the upload goes through: the lines and the
count are the engine's.
"""

from rich.console import Group, RenderableType
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.css.query import NoMatches
from textual.widgets import Static
from textual.worker import get_current_worker

from expense import reads
from expense.bank_import.flow import AccountPick
from expense.bank_import.statement import LooseLines
from expense.errors import format_error
from expense.formatting import bank_line_columns, title_or_untitled
from expense.tui.screens._base import (
    AdaptiveRowsMixin,
    EngineWriteMixin,
    NewestReadMixin,
    call_while_attached,
    relabel,
    screen_fetch_kwargs,
)
from expense.tui.screens.bank_import import NOTHING_WRITTEN, ImportRun, ImportScreen
from expense.tui.screens.statements import (
    BROWSE_GAP,
    ask_line_delete,
    line_count,
    open_edit_form,
)
from expense.tui.theme import PALETTE, TRANSACTION_RULE
from expense.tui.widgets.cells import amount_cell
from expense.tui.widgets.checklist import AMOUNT_WIDTH, TITLE_WIDTH
from expense.tui.widgets.cursor_list import CursorList
from expense.tui.widgets.footer import FittingFooter
from expense.tui.widgets.header import Breadcrumb
from expense.tui.widgets.refusal import toast, under_itself

#: The list's columns: the line's day, title, signed amount and currency.
HEADERS = ["Date", "Title", "Amount", "Cur"]

#: Lines the list spends on anything but rows: its header and its page status.
LIST_CHROME = 2

#: The words under the list: what to do with a line, one paragraph each,
#: `(bullet, words)`, then the last line. They only say which key does which step; the
#: keys, the Edit form and the engine do the steps.
FOR_EACH = "For each one:"
WAYS = (
    (
        "· ",
        "the paper prints it another way: ⏎ fix it to the paper's day and amount, and the"
        " upload takes it",
    ),
    (
        "· ",
        "the paper doesn't print it: ⏎ move it to another day, or d delete it (next month's"
        " paper brings a late transaction on its own)",
    ),
)
THEN = "Then r reads the paper again."
#: Where the list was, once every line is dealt with: what to do next.
NONE_LEFT = "Nothing is left over: r reads the paper again."
#: The lines the words take at 80 columns, until they are drawn and can be measured.
WAYS_LINES = 6

#: The least rows a page shows, however short the terminal.
FLOOR = 3


def head_lines(account: str, shown: int, loose: LooseLines) -> list[Text]:
    """The head: `Can't close the statement yet · <account>`, how many lines sit in no
    statement, and, when the refusal names fewer lines than there are (`loose.count` above
    its ids), how many it listed and what `r` does about the rest, then `Nothing was written.`.
    `shown` is the lines listed now; the count is theirs when the refusal named every line
    and the engine's when it did not, so a line fixed or deleted leaves the count too."""
    truncated = loose.count > len(loose.ids)
    n = loose.count if truncated else shown
    lines = [Text.assemble("Can't close the statement yet · ", (account, ""))]
    if n:
        verb = "sits" if n == 1 else "sit"
        lines.append(
            Text(f"{line_count(n)} in no statement {verb} on its days.", style=PALETTE.warning)
        )
    if truncated:
        lines.append(
            Text(
                f"The first {len(loose.ids)} are listed; r reads the paper again for the rest.",
                style=PALETTE.warning,
            )
        )
    lines.append(Text(NOTHING_WRITTEN, style="dim"))
    return lines


def ways() -> RenderableType:
    """The words under the list, dim: each paragraph wrapping under its own first word."""
    parts: list[RenderableType] = [Text(FOR_EACH, style="dim")]
    parts.extend(
        under_itself(Text(bullet, style="dim"), Text(words, style="dim")) for bullet, words in WAYS
    )
    parts.append(Text(THEN, style="dim"))
    return Group(*parts)


def line_rows(lines: list[dict]) -> list[tuple]:
    """One row per line, as given: its id, then its day, title, signed amount and currency."""
    rows = []
    for line in lines:
        day, title, _operation, net_cents = bank_line_columns(line)
        rows.append(
            (
                line.get("id"),
                [
                    day,
                    title_or_untitled(title),
                    amount_cell(net_cents, PALETTE, TRANSACTION_RULE),
                    line.get("currency_code") or "",
                ],
            )
        )
    return rows


class _LeftoverList(CursorList):
    """The lines' list. It takes no focus: its screen holds every key, so the footer reads
    in the screen's own order (a focused widget's keys come first in a footer)."""

    can_focus = False


class LeftoverLinesScreen(EngineWriteMixin, AdaptiveRowsMixin, NewestReadMixin, ImportScreen):
    """The lines a refused upload names, to fix, move or delete before reading the paper
    again. Opened by the preview on the refusal (`StatementPreviewScreen._failed`)."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "open", "Edit", tooltip="Open the line in its Edit form"),
        Binding("d", "delete_line", "Delete", tooltip="Delete the line, after a question"),
        Binding("r", "read_again", "Read again", tooltip="Send the same PDF again as a preview"),
        Binding("down", "move(1)", "Move", key_display="↑↓", tooltip="Down", show=False),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("pagedown", "page(1)", "Next", key_display="pgdn", show=False),
        Binding("pageup", "page(-1)", "Prev", key_display="pgup", show=False),
    ]

    def __init__(self, run: ImportRun, owner, pick: AccountPick, loose: LooseLines) -> None:
        super().__init__(run, owner)
        self._pick = pick
        self._loose = loose
        #: The lines last read, in the order listed; None until a read lands.
        self._lines: list[dict] | None = None
        self._list: CursorList | None = None

    def crumb(self) -> tuple[str, ...]:
        """`Upload › <file> › Leftover`: the upload's trail without its first part, so the
        file's name and `Leftover` fit 80 columns."""
        return (*self._run.crumb()[1:], "Leftover")

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb(), id="crumb")
        yield Static("", id="import-body")  # the head, drawn by `body` (ImportScreen)
        yield Container(id="llist")
        yield FittingFooter()

    def on_mount(self) -> None:
        relabel(self, "escape", self._run.cancel_label())
        # the list sizes itself to #llist's real height: wait for the first layout
        self.call_after_refresh(self._mount_list)

    def _mount_list(self) -> None:
        self._list = _LeftoverList(
            HEADERS,
            [],
            align_right={2},
            gap=BROWSE_GAP,
            edge=False,
            header_rule=False,
            divider=None,
            gives_way={1},
            min_widths={1: TITLE_WIDTH, 2: AMOUNT_WIDTH},
            page_size=self._page_rows(),
        )
        none = Static(Text(NONE_LEFT, style=PALETTE.success), id="lnone")
        none.display = False
        self.query_one("#llist", Container).mount(self._list, Static(ways(), id="lways"), none)
        self._load()

    def on_resize(self, _event) -> None:
        if self._list is not None and self._list.is_attached:
            self._list.set_page_size(self._page_rows())

    def _page_rows(self) -> int:
        """Rows that fit under the list's own frame and the words under it."""
        try:
            under = self.query_one("#lways", Static).outer_size.height or WAYS_LINES
        except NoMatches:
            under = WAYS_LINES
        return self.fit_rows("#llist", chrome=LIST_CHROME + under, floor=FLOOR)

    # ---- the engine ----------------------------------------------------------
    def _load(self) -> None:
        """Start a read of the lines; every read start goes through here."""
        self._read_lines(self._start_read())

    @work(thread=True, exclusive=True, group="leftover-load")
    def _read_lines(self, generation: int) -> None:
        """The refusal's lines, in one read by their ids (contract: GET /v1/bank-lines,
        "Filters"), listed in the order the refusal names them: the read answers in the
        list's own order, so each id is looked up in its answer. A failed read shows the
        engine's words and keeps what is listed."""
        from expense import config as config_module

        worker = get_current_worker()
        try:
            cfg = config_module.ensure_loaded()
            found = reads.fetch_bank_lines_by_ids(
                cfg, self._loose.ids, **screen_fetch_kwargs(self.app)
            )
            by_id = {str(line.get("id")): line for line in found}
            lines = [by_id[i] for i in self._loose.ids if i in by_id]
        except Exception as exc:  # surfaced on the screen, never a crash
            if not worker.is_cancelled:
                call_while_attached(
                    self,
                    self._if_newest,
                    generation,
                    toast,
                    self,
                    format_error(exc),
                    title="Failed",
                    severity="error",
                )
            return
        if not worker.is_cancelled:
            call_while_attached(self, self._if_newest, generation, self._populate, lines)

    def _populate(self, lines: list[dict]) -> None:
        """Paint a read, the cursor on row 1."""
        self._lines = lines
        assert self._list is not None
        self._list.set_rows(line_rows(lines))
        self._list.set_cursor(0)
        for widget, shown in (("#lways", bool(lines)), ("#lnone", not lines)):
            self.query_one(widget, Static).display = shown
        self._list.display = bool(lines)
        self._repaint()
        self.refresh_bindings()

    def body(self) -> RenderableType:
        shown = len(self._lines) if self._lines is not None else self._loose.count
        return Group(*head_lines(self._pick.name, shown, self._loose))

    # ---- keys ----------------------------------------------------------------
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("open", "delete_line", "move", "page"):
            return bool(self._lines)
        return True

    def _cursor_line(self) -> dict | None:
        key = self._list.cursor_key if self._list is not None else None
        return next((line for line in self._lines or [] if line.get("id") == key), None)

    def action_move(self, delta: int) -> None:
        if self._list is not None:
            self._list.action_move(delta)

    def action_page(self, delta: int) -> None:
        if self._list is not None:
            self._list.action_page(delta)

    def action_open(self) -> None:
        """`⏎` — the line in the ledger's Edit form; a save sends the PDF again, as `r`."""
        line = self._cursor_line()
        if line is not None:
            open_edit_form(self, line, crumb=self.crumb(), reload=self.action_read_again)

    def action_delete_line(self) -> None:
        """`d` — the line under the cursor, after the delete question; deleted, the lines
        are read again and it is gone."""
        line = self._cursor_line()
        if line is not None:
            ask_line_delete(self, line, self._pick.name, after=self._load)

    def action_read_again(self) -> None:
        """`r` — the same PDF as a dry run, through the preview, which asks on open:
        the preview when nothing is left over, a refusal in the engine's words, or this
        screen again with the new lines. Not while a delete is still being sent."""
        from expense.tui.screens.statement_upload import StatementPreviewScreen

        if self.saves_pending():
            self.notify("Writing — one moment.")
            return
        self.app.switch_screen(StatementPreviewScreen(self._run, self._owner, self._pick))

    def action_cancel(self) -> None:
        self._close()
