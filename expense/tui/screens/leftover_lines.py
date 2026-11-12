"""The leftover lines — bank lines in no statement on days a close would seal, to deal with
before closing. Two screens share one body (`LeftoverLines`):

- `LeftoverLinesScreen`: a statement PDF's upload refused (dry run and apply alike). The
  engine names the lines by id in `error.details` (`expense.bank_import.statement.loose_lines`;
  contract: POST /v1/statements/import, "Response"). The preview opens the screen in its
  place, a full screen of the upload's run: `esc Cancel  ⏎ Edit  d Delete  r Read again`.
  `r`, and a save from the Edit form, send the same PDF again as a dry run, which is the
  preview's own: it opens the preview once nothing is left over, and this screen again with
  the new lines while some are.
- `StatementLeftoverScreen`: `c` refused on a statement closed by hand, the same
  `details` on `statement_id`. The statement's screen pushes it over itself:
  `esc Back  space Put in <statement>  ⏎ Edit  d Delete  c Close`. `space` puts the line in the
  statement (`statements.run_assignment`, the checklist's own write) and only lines the read
  gives no statement are listed; `c` goes back and the statement asks "Complete statement?"
  again, a refusal for loose lines opening a fresh screen; `esc` asks nothing.

The lines are read by their ids in one read (`reads.fetch_bank_lines_by_ids`) and listed in the
order the refusal names them; a line deleted meanwhile is simply absent. `d` deletes a line
after the delete question and the lines are read again, the cursor on row 1. The refusal names
at most 200 lines; past them the head says how many there are in all and what reads the rest.
Nothing here decides which lines refuse or when a close goes through: the lines and the count
are the engine's.
"""

from rich.console import Group, RenderableType
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.css.query import NoMatches
from textual.screen import Screen
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
    list_refusal_text,
    relabel,
    screen_fetch_kwargs,
    self_reading_refusal_text,
)
from expense.tui.screens.bank_import import NOTHING_WRITTEN, ImportRun, ImportScreen
from expense.tui.screens.statements import (
    BROWSE_GAP,
    CLOSE_AGAIN,
    ask_line_delete,
    first_part,
    line_count,
    open_edit_form,
    run_assignment,
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
#: The same for a statement closed by hand, and the words under its list; `{name}` is the
#: statement's name as the app shows it.
STATEMENT_NONE_LEFT = "Nothing is left over: c closes {name}."
STATEMENT_WAYS = "For each one: space puts it in {name}, ⏎ fixes or moves it, d deletes it."
STATEMENT_THEN = "Then c closes {name} again."
#: The lines the words take at 80 columns, until they are drawn and can be measured.
WAYS_LINES = 6

#: The least rows a page shows, however short the terminal.
FLOOR = 3


def head_lines(lead: str, account: str, shown: int, loose: LooseLines, *, again: str) -> list[Text]:
    """The head: `lead` in bold (`Can't close <the statement> yet`), then ` · <account>`, how
    many lines sit in no statement, and, when the refusal names fewer lines than there are
    (`loose.count` above its ids), how many it listed and what `again` (`r`, `c`) does about
    the rest, then `Nothing was written.`. `shown` is the lines listed now; the count is theirs
    when the refusal named every line and the engine's when it did not, so a line fixed or
    deleted leaves the count too."""
    truncated = loose.count > len(loose.ids)
    n = loose.count if truncated else shown
    lines = [Text.assemble((lead, "bold"), f" · {account}")]
    if n:
        verb = "sits" if n == 1 else "sit"
        lines.append(
            Text(f"{line_count(n)} in no statement {verb} on its days.", style=PALETTE.warning)
        )
    if truncated:
        lines.append(
            Text(
                f"The first {len(loose.ids)} are listed; {again} for the rest.",
                style=PALETTE.warning,
            )
        )
    lines.append(Text(NOTHING_WRITTEN, style="dim"))
    return lines


def upload_ways() -> RenderableType:
    """The words under an upload's list, dim: each paragraph wrapping under its own first
    word."""
    parts: list[RenderableType] = [Text(FOR_EACH, style="dim")]
    parts.extend(
        under_itself(Text(bullet, style="dim"), Text(words, style="dim")) for bullet, words in WAYS
    )
    parts.append(Text(THEN, style="dim"))
    return Group(*parts)


def statement_ways(name: str) -> RenderableType:
    """The words under a statement's list, dim."""
    return Group(
        Text(STATEMENT_WAYS.format(name=name), style="dim"),
        Text(STATEMENT_THEN.format(name=name), style="dim"),
    )


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


class LeftoverLines(EngineWriteMixin, AdaptiveRowsMixin, NewestReadMixin):
    """What both leftover screens share: the head, the list of lines read by their ids in
    the order the refusal names them, `⏎` to edit, `d` to delete, the words under the list
    and what stands in the list's place once every line is dealt with. A plain mixin: each
    screen is its own `Screen`, with its own bindings, and calls `_start_lines` on mount and
    `_resized` on resize (Textual hands a handler only to the classes it knows).

    A screen says what differs: `crumb`, `_lead` (the head's first words), `_ways_words`,
    `_none_left_words`, `_again` (what the head says reads the rest), `_keep` (which of
    the lines read are listed), `_after_edit` (what a save from the Edit form does) and
    `_account_name`."""

    _loose: LooseLines
    #: How a refused write of the screen reads: with `r` in the line for a list, unless the
    #: screen has none.
    REFUSAL_TEXT = staticmethod(list_refusal_text)
    #: The lines last read, in the order listed; None until a read lands.
    _lines: list[dict] | None = None
    _list: CursorList | None = None

    def _lead(self) -> str:
        raise NotImplementedError

    def _ways_words(self) -> RenderableType:
        raise NotImplementedError

    def _none_left_words(self) -> str:
        raise NotImplementedError

    def _again(self) -> str:
        raise NotImplementedError

    def _account_name(self) -> str:
        raise NotImplementedError

    def _after_edit(self) -> None:
        raise NotImplementedError

    def _keep(self, line: dict) -> bool:
        """Whether a line the read returned is listed."""
        return True

    def crumb(self) -> tuple[str, ...]:
        raise NotImplementedError

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb(), id="crumb")
        yield Static("", id="import-body")  # the head, drawn by `body`
        yield Container(id="llist")
        yield FittingFooter()

    def _repaint(self) -> None:
        self.query_one("#import-body", Static).update(self.body())

    def _start_lines(self) -> None:
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
        none = Static(Text(self._none_left_words(), style=PALETTE.success), id="lnone")
        none.display = False
        ways_widget = Static(self._ways_words(), id="lways")
        self.query_one("#llist", Container).mount(self._list, ways_widget, none)
        self._load()

    def _resized(self) -> None:
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
        lines = [line for line in lines if self._keep(line)]
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
        return Group(
            *head_lines(self._lead(), self._account_name(), shown, self._loose, again=self._again())
        )

    # ---- keys ----------------------------------------------------------------
    def _needs_a_line(self, action: str) -> bool:
        return action in ("open", "delete_line", "move", "page")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if self._needs_a_line(action):
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
        """`⏎` — the line in the ledger's Edit form; a save does what the screen's own
        `_after_edit` says."""
        line = self._cursor_line()
        if line is not None:
            open_edit_form(self, line, crumb=self.crumb(), reload=self._after_edit)

    def action_delete_line(self) -> None:
        """`d` — the line under the cursor, after the delete question; deleted, the lines
        are read again and it is gone."""
        line = self._cursor_line()
        if line is not None:
            ask_line_delete(
                self, line, self._account_name(), after=self._load, error_text=self.REFUSAL_TEXT
            )

    def _writing(self) -> bool:
        """True, with the note, while a write of this screen is still being sent: what
        asks the engine again waits for it."""
        if self.saves_pending():
            self.notify("Writing — one moment.")
            return True
        return False


class LeftoverLinesScreen(LeftoverLines, ImportScreen):
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

    def crumb(self) -> tuple[str, ...]:
        """`Upload › <file> › Leftover`: the upload's trail without its first part, so the
        file's name and `Leftover` fit 80 columns."""
        return (*self._run.crumb()[1:], "Leftover")

    def _lead(self) -> str:
        return "Can't close the statement yet"

    def _ways_words(self) -> RenderableType:
        return upload_ways()

    def _none_left_words(self) -> str:
        return NONE_LEFT

    def _again(self) -> str:
        return "r reads the paper again"

    def _account_name(self) -> str:
        return self._pick.name

    def _after_edit(self) -> None:
        self.action_read_again()

    def on_mount(self) -> None:
        relabel(self, "escape", self._run.cancel_label())
        self._start_lines()

    def on_resize(self) -> None:
        self._resized()

    def action_read_again(self) -> None:
        """`r` — the same PDF as a dry run, through the preview, which asks on open:
        the preview when nothing is left over, a refusal in the engine's words, or this
        screen again with the new lines. Not while a delete is still being sent."""
        from expense.tui.screens.statement_upload import StatementPreviewScreen

        if self._writing():
            return
        self.app.switch_screen(StatementPreviewScreen(self._run, self._owner, self._pick))

    def action_cancel(self) -> None:
        self._close()


class StatementLeftoverScreen(LeftoverLines, Screen):
    """The lines a refused `c` names on a statement closed by hand, pushed over the
    statement's screen (`StatementScreen._action_failed`). `space` puts the line in the
    statement, the checklist's own write (`run_assignment`); the lines are read again by
    id and only those the read gives no statement are listed. `c` hands `CLOSE_AGAIN` back, and
    the statement asks "Complete statement?" again; `esc` hands back nothing. Either way
    the statement reads itself again."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("space", "put_in", "Put in statement", tooltip="Put the line in the statement"),
        Binding("enter", "open", "Edit", tooltip="Open the line in its Edit form"),
        Binding("d", "delete_line", "Delete", tooltip="Delete the line, after a question"),
        Binding("c", "close", "Close", tooltip="Complete the statement again"),
        Binding("down", "move(1)", "Move", key_display="↑↓", tooltip="Down", show=False),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("pagedown", "page(1)", "Next", key_display="pgdn", show=False),
        Binding("pageup", "page(-1)", "Prev", key_display="pgup", show=False),
    ]

    REFUSAL_TEXT = staticmethod(self_reading_refusal_text)

    def __init__(
        self,
        statement_id: str | None,
        *,
        name: str,
        account: str,
        crumb: tuple[str, ...],
        loose: LooseLines,
    ) -> None:
        """`name` is the statement's name as its screen shows it, `account` its account's
        name and `crumb` the statement screen's trail."""
        super().__init__()
        self._statement_id = statement_id
        self._name: str = name
        self._account = account
        self._trail = crumb
        self._loose = loose

    def crumb(self) -> tuple[str, ...]:
        return (*self._trail, "Leftover")

    def _lead(self) -> str:
        return f"Can't close {self._name} yet"

    def _ways_words(self) -> RenderableType:
        return statement_ways(self._name)

    def _none_left_words(self) -> str:
        return STATEMENT_NONE_LEFT.format(name=self._name)

    def _again(self) -> str:
        return f"c closes {self._name} again"

    def _account_name(self) -> str:
        return self._account

    def _after_edit(self) -> None:
        self._load()

    def _keep(self, line: dict) -> bool:
        """Only a line the read gives no statement (`statement_id` is the same on every
        part of a line): one put in the statement leaves the list."""
        part = first_part(line)
        return part is None or not part.get("statement_id")

    def _needs_a_line(self, action: str) -> bool:
        return action == "put_in" or super()._needs_a_line(action)

    def on_mount(self) -> None:
        relabel(self, "space", f"Put in {self._name}")
        self._repaint()
        self._start_lines()

    def on_resize(self, _event) -> None:
        self._resized()

    def action_put_in(self) -> None:
        """`space` — the line under the cursor into the statement, the write the
        checklist's `space` sends; the lines are read again after it, and after a refusal
        too (the engine's words in the `Couldn't update` note)."""
        line = self._cursor_line()
        part = first_part(line) if line is not None else None
        if line is None or part is None:
            return
        _day, title, _operation, net_cents = bank_line_columns(line)
        run_assignment(
            self,
            part["id"],
            self._statement_id,
            not_done=f"Not put in {self._name}",
            words=(title, net_cents),
            error_text=self.REFUSAL_TEXT,
            on_success=self._load,
            on_error=self._put_in_failed,
        )

    def _put_in_failed(self, message: str) -> None:
        toast(self, message, title="Couldn't update", severity="error")

    def action_close(self) -> None:
        """`c` — back to the statement, which asks "Complete statement?" again."""
        if not self._writing():
            self.dismiss(CLOSE_AGAIN)

    def _writes_dropped(self, failed, dropped) -> None:
        """A refused write (`space`, `d`) leaves the list as the engine now has it: the lines
        are read again."""
        self._load()

    def action_back(self) -> None:
        self.dismiss(None)
