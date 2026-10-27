"""The statement upload — a dropped statement PDF → its account → the preview → the close.

A `.pdf` dropped on the LOG bar (alone or among downloads, each file going its
own way in drop order: `bank_import.first_screen`) goes through three full
screens of its own, in the import door's run (`bank_import.ImportRun`): its
bytes read at the drop, its account list read once per run, its way back to the
LOG bar.

    StatementAccountScreen   which account is this statement? (screen A2 of
                             docs/mockups/expense-world-statement-pdf-upload.html)
    StatementPreviewScreen   the engine's dry run, nothing written yet (screen 1
                             of docs/mockups/expense-world-statement-pdf-screens.html),
                             or a refused upload in the engine's words (screen 2)
    StatementResultScreen    the month closed, and `f` for the lines the close
                             flagged (screen 3)

The app sends the PDF whole and reads nothing in it: every row, its outcome, the
near misses, the lines taken out, the balances and every refusal are the
engine's (contract: POST /v1/reconciliations/import). The account is the one
picked; nothing is matched, added up or guessed here. The call, the account
picks and the file read are the shared steps in expense/bank_import/flow.py, how
the answer reads is expense/bank_import/statement.py; what is here is only what
the screens draw.
"""

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.screen import Screen

from expense.bank_import import flow
from expense.bank_import.flow import AccountPick
from expense.bank_import.statement import (
    EMPTY,
    MATCHED,
    NEW,
    StatementAnswer,
    StatementCounts,
    StatementRow,
    statement_answer,
)
from expense.errors import EngineError
from expense.formatting import bank_line_columns, format_cents, truncate
from expense.tui.screens._base import relabel
from expense.tui.screens.bank_import import (
    ASKING,
    MIN_PAGE,
    PENDING,
    PENDING_HASHTAG,
    PREVIEW_CHROME,
    WRITING,
    ImportAccountScreen,
    ImportRun,
    PreviewScreen,
    ResultScreen,
    padded_amount,
    plural,
)
from expense.tui.screens.reconciliations import (
    FlaggedLinesScreen,
    flagged_note,
    review_line_ids,
)
from expense.tui.theme import ACCENT, AMOUNT_RULE, BALANCE_RULE, PALETTE
from expense.tui.widgets.refusal import hanging

#: The account list's breadcrumb (screen A2).
ACCOUNT_CRUMB = ("Upload a statement",)

#: The statement's state on the preview's second line: every half created, or
#: an open draft filled (screens 1A and 1B).
A_NEW_STATEMENT = "a new statement"
A_DRAFT_FILLED = "a draft, filled from the paper"

#: Under the counts while the upload creates a line.
PENDING_NOTE = f"new ones go under {PENDING} and {PENDING_HASHTAG}"

#: The fee note after a card's undated line: interest or a fee, dated the
#: statement's last day.
FEE_NOTE = "· a fee, dated the last day"

#: The "Taken out" block's head and the words after it.
TAKEN_OUT = "Taken out"
TAKEN_OUT_NOTE = " · in the statement, not on the paper; they stay in the ledger"

#: What `⏎` does after the apply met something changed while it ran.
RERUN = "It changed while the upload ran: ⏎ checks the paper against the ledger again."

#: An empty cell: a row or a line with no title.
NO_TITLE = "—"


def pick_label(pick: AccountPick) -> str:
    """The account as the upload's screens name it: `Sueldo Soles`, or a
    card's line with its currencies, `Signature PEN + USD`."""
    return f"{pick.name} {pick.currencies}" if pick.is_card else pick.name


def changed_meanwhile(err: Exception) -> bool:
    """A `409 CONFLICT` whose reason is `CONCURRENT_CHANGE`, on any key: a
    matched line, the statement's draft or a name the upload files under
    changed while it ran, and nothing was written; it is sent again
    (contract: POST /v1/reconciliations/import, "Concurrency")."""
    return (
        isinstance(err, EngineError)
        and err.code == "CONFLICT"
        and "CONCURRENT_CHANGE" in (err.reasons or {}).values()
    )


# ---------------------------------------------------------------------------
# which account is this statement? — screen A2
# ---------------------------------------------------------------------------
class StatementAccountScreen(ImportAccountScreen):
    """Which account is this statement? The download's account list, a card's
    two accounts one line; asked every time. The pick is the account: the
    engine never picks one by the number the paper prints."""

    QUESTION = "Which account is this statement?  "

    def crumb(self) -> tuple[str, ...]:
        """`Upload a statement`, then `file 1 of 2` as a download's list reads
        it when several files were dropped."""
        if self._run.several:
            return (*ACCOUNT_CRUMB, self._run.position)
        return ACCOUNT_CRUMB

    def next_screen(self, pick: AccountPick) -> Screen:
        return StatementPreviewScreen(self._run, self._owner, pick)


# ---------------------------------------------------------------------------
# the preview — screen 1, a refused upload screen 2
# ---------------------------------------------------------------------------
#: Each outcome's mark, its reason and their style: ✓ in the ledger, + created
#: on ⏎ (accent), · a row of 0.00, nothing to look at.
OUTCOMES: dict[str, tuple[str, str, str, str]] = {
    MATCHED: ("✓", PALETTE.success, "In the ledger", "dim"),
    NEW: ("+", ACCENT, "New", ACCENT),
    EMPTY: ("·", "dim", "Empty", "dim"),
}


def row_tail(row: StatementRow) -> Text:
    """What follows a row's columns: its outcome's mark and reason, and after
    a card's undated line (`fee`) the fee note, dim."""
    mark, mark_style, reason, reason_style = OUTCOMES.get(row.outcome, ("?", "", row.outcome, ""))
    tail = Text("  ")
    tail.append(mark, style=mark_style)
    tail.append("  ")
    tail.append(reason, style=reason_style)
    if row.fee:
        tail.append(f"  {FEE_NOTE}", style="dim")
    return tail


class Columns:
    """The table's widths, from every row and every line it lists, so a page
    and the "Taken out" block line up whatever the window. The title column
    takes what the screen leaves once the widest row's mark, reason and fee
    note have their room, so no row wraps."""

    def __init__(self, answer: StatementAnswer, taken: list[dict], *, width: int) -> None:
        titles = [row.description or NO_TITLE for row in answer.rows]
        titles += [str(bank_line_columns(line)[1] or NO_TITLE) for line in taken]
        amounts = [row.amount_cents for row in answer.rows]
        amounts += [_cents(bank_line_columns(line)[3]) for line in taken]
        self.cur = answer.several_currencies
        self.number = max([2, *(len(str(row.place)) for row in answer.rows)]) + 2
        self.amount = max([len("amount"), *(len(format_cents(c)) for c in amounts)])
        tail = max((len(row_tail(row).plain) for row in answer.rows), default=0)
        rest = self.number + 2 + 10 + 2 + 2 + self.amount + (5 if self.cur else 0) + tail
        self.title = max(len("title"), min(max(map(len, titles), default=0), width - rest))

    @property
    def title_at(self) -> int:
        """Where the title column starts."""
        return self.number + 2 + 10 + 2

    def header(self) -> Text:
        words = (
            f"{'#'.rjust(self.number)}  {'date'.ljust(10)}  {'title'.ljust(self.title)}  "
            f"{'amount'.rjust(self.amount)}"
        )
        return Text(words + ("  cur" if self.cur else ""), style="dim")

    def line(
        self,
        place: str,
        day: str,
        title: str,
        cents: int,
        currency: str,
        *,
        rule: str = AMOUNT_RULE,
    ) -> Text:
        """One line of the table: its place, day, title, signed amount (coloured
        by `rule`) and, on a card's paper, its currency. Only a terminal too
        narrow for the paper's longest title cuts one, with `…`."""
        text = Text(f"{place.rjust(self.number)}  {day.ljust(10)}  ")
        text.append(truncate(title, self.title).ljust(self.title))
        text.append("  ")
        text.append_text(padded_amount(cents, self.amount, rule))
        if self.cur:
            text.append(f"  {currency}")
        return text


def _cents(value: object) -> int:
    return value if isinstance(value, int) else 0


def row_lines(row: StatementRow, columns: Columns, lines: dict[str, dict]) -> list[RenderableType]:
    """A row of the paper, its outcome's mark and reason (and the fee note on a
    card's undated line), then under a new row one `!` line per ledger line one
    day off it with its total: the engine's day, and the line's title and
    total as read by its id (the row's own amount, its total being the same,
    and `—` while the line is unread). An empty row's `0.00` is plain, as
    drawn: it is no money in or out."""
    text = columns.line(
        str(row.place),
        row.date_iso,
        row.description or NO_TITLE,
        row.amount_cents,
        row.currency,
        rule="plain" if row.outcome == EMPTY else AMOUNT_RULE,
    )
    text.append_text(row_tail(row))
    out: list[RenderableType] = [text]
    for miss in row.near_misses:
        line = lines.get(miss.bank_line_id)
        if line is not None:
            _day, title, _code, net = bank_line_columns(line)
            title, cents = str(title or NO_TITLE), _cents(net)
        else:
            title, cents = NO_TITLE, row.amount_cents
        words = Text(
            f"! {miss.date_iso} {title} {format_cents(cents)} "
            "in the ledger is one day off: not paired",
            style=PALETTE.warning,
        )
        grid = Table.grid()
        grid.add_column(width=max(0, columns.title_at - 4), no_wrap=True)
        grid.add_column()
        grid.add_row("", hanging(words))
        out.append(grid)
    return out


def taken_out_lines(
    answer: StatementAnswer, lines: dict[str, dict], columns: Columns, pick: AccountPick
) -> list[Text]:
    """The "Taken out" block: the lines in the open statement that the paper
    does not print, oldest first as the engine lists them, each read by its id
    and shown under the table's columns. Empty when none is taken out."""
    if not answer.taken_out:
        return []
    out = [Text.assemble(TAKEN_OUT, (TAKEN_OUT_NOTE, "dim"))]
    for line_id in answer.taken_out:
        line = lines.get(line_id)
        if line is None:
            continue
        day, title, _code, net = bank_line_columns(line)
        currency = pick.currency_of(str(line.get("account_id")))
        out.append(columns.line("", day, str(title or NO_TITLE), _cents(net), currency))
    return out


def balance_lines(answer: StatementAnswer) -> list[Text]:
    """`begin  end` dim, then one line per half: its currency and the paper's
    balances (contract: POST /v1/reconciliations/import, "Response")."""
    figures = [
        format_cents(c)
        for half in answer.halves
        for c in (half.beginning_balance_cents, half.ending_balance_cents)
        if c is not None
    ]
    width = max([len("begin"), *map(len, figures)]) + 2
    lines = [Text(f"{'':3}  {'begin'.rjust(width)}  {'end'.rjust(width)}", style="dim")]
    for half in answer.halves:
        line = Text(f"{half.currency.ljust(3)}  ")
        line.append_text(padded_amount(half.beginning_balance_cents, width, BALANCE_RULE))
        line.append("  ")
        line.append_text(padded_amount(half.ending_balance_cents, width, BALANCE_RULE))
        lines.append(line)
    return lines


def statement_head(answer: StatementAnswer) -> Text:
    """`SIG-202610 · 2026-09-26 → 2026-10-25 · a new statement`, or `… · a
    draft, filled from the paper` when a half fills an open draft."""
    state = A_DRAFT_FILLED if answer.fills_a_draft else A_NEW_STATEMENT
    head = Text(f"{answer.name} · {answer.date_start} → {answer.date_end} · ")
    head.append(state, style="dim")
    return head


def counts_line(counts: StatementCounts, *, done: bool) -> Text:
    """`10 rows · 5 in the ledger · 4 new · 1 empty · 1 taken out`, the empty
    and taken-out counts only when not zero; after the close, in the past
    tense: `5 were in the ledger · 4 created`. Every figure is the engine's."""
    line = Text(f"{counts.rows} {plural(counts.rows, 'row', 'rows')} · ")
    if done:
        line.append(f"{counts.matched} {plural(counts.matched, 'was', 'were')} in the ledger · ")
        line.append(f"{counts.new} created", style=ACCENT if counts.new else "")
    else:
        line.append(f"{counts.matched} in the ledger · ")
        line.append(f"{counts.new} new", style=ACCENT if counts.new else "")
    if counts.empty:
        line.append(f" · {counts.empty} empty")
    if counts.taken_out:
        line.append(f" · {counts.taken_out} taken out")
    return line


class StatementPreviewScreen(PreviewScreen):
    """The engine's dry run of this PDF on this account. Nothing is written
    until `⏎ Close <name>`, one `POST /reconciliations/import` with `dry_run`
    false; `esc` sends nothing. A refused upload shows the engine's words and
    `⏎` sends nothing; one met by the apply because something changed while it
    ran offers `⏎ Preview again`, a fresh dry run before any write."""

    RERUN_LINE = RERUN

    def __init__(self, run: ImportRun, owner, pick: AccountPick) -> None:
        super().__init__(run, owner, pick)
        #: The dry run's answer; None until it comes.
        self._answer: StatementAnswer | None = None
        #: The ledger lines the answer names by id alone, read by their ids.
        self._lines: dict[str, dict] = {}
        #: Why those lines could not be read.
        self._lines_error: str | None = None
        #: The first row of the page, and the pages before it (for `pgup`).
        self._start = 0
        self._starts: list[int] = []

    # ---- state ---------------------------------------------------------------
    @property
    def can_apply(self) -> bool:
        return self._answer is not None and not self._failure and not self._writing

    def changed(self, err: Exception) -> bool:
        return changed_meanwhile(err)

    def _forget_answer(self) -> None:
        self._answer, self._lines, self._lines_error = None, {}, None
        self._start, self._starts = 0, []

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "apply":
            return self.can_apply or self.can_rerun
        if action == "page":
            delta = parameters[0] if parameters else 1
            if delta == 1:
                return self._answer is not None and self._window_end() < len(self._answer.rows)
            return bool(self._starts)
        return True

    # ---- the engine ----------------------------------------------------------
    @work(thread=True, exclusive=True, group="engine-write")
    def _ask(self, dry_run: bool) -> None:
        """One `POST /reconciliations/import`, the dry run or the apply, through
        flow.py's one call; the client mints the idempotency key. The dry run
        then reads the lines its answer names by id alone (`statement_lines`)."""
        from expense import config as config_module
        from expense.http import ExpenseClient

        verbose = self.app._verbose
        try:
            cfg = config_module.ensure_loaded()
            with ExpenseClient(cfg, verbose=verbose) as client:
                response = flow.statement_call(
                    client, self._pick, self._run.current.data, dry_run=dry_run
                )
            answer = statement_answer(response)
            if dry_run:
                lines, lines_error = flow.statement_lines(
                    cfg, answer.lines_to_read(), verbose=verbose
                )
            else:
                flagged = review_line_ids(response.get("reconciliation") or {})
        except Exception as err:  # every failure is shown, none swallowed
            self.app.call_from_thread(self._failed, err)
            return
        if dry_run:
            self.app.call_from_thread(self._previewed, answer, lines, lines_error)
        else:
            self.app.call_from_thread(self._applied, answer, flagged)

    def _previewed(
        self, answer: StatementAnswer, lines: dict[str, dict], lines_error: str | None
    ) -> None:
        self._answer, self._lines, self._lines_error = answer, lines, lines_error
        relabel(self, "enter", f"Close {answer.name}")
        self.refresh_bindings()
        self._repaint()

    def _applied(self, answer: StatementAnswer, flagged: list[str]) -> None:
        self._writing = False
        self._run.imported += 1
        self.app.switch_screen(
            StatementResultScreen(self._run, self._owner, self._pick, answer, flagged)
        )

    # ---- keys ----------------------------------------------------------------
    def action_page(self, delta: int) -> None:
        if self._answer is None:
            return
        if delta > 0:
            end = self._window_end()
            if end >= len(self._answer.rows):
                return
            self._starts.append(self._start)
            self._start = end
        else:
            if not self._starts:
                return
            self._start = self._starts.pop()
        self.refresh_bindings()
        self._repaint()

    # ---- render --------------------------------------------------------------
    def _columns(self) -> Columns:
        assert self._answer is not None
        taken = [self._lines[i] for i in self._answer.taken_out if i in self._lines]
        return Columns(self._answer, taken, width=max(40, self.size.width - 4))

    def _under_table(self, columns: Columns) -> list[RenderableType]:
        """Everything under the table: the taken-out block, the counts, where
        new lines go, why lines went unread, and the apply's progress or
        failure."""
        answer = self._answer
        assert answer is not None
        parts: list[RenderableType] = []
        taken = taken_out_lines(answer, self._lines, columns, self._pick)
        if taken:
            parts.extend(taken)
            parts.append(Text(""))
        parts.append(counts_line(answer.counts, done=False))
        if answer.counts.new:
            parts.append(Text(PENDING_NOTE, style="dim"))
        if self._lines_error:
            parts.append(
                hanging(
                    Text(f"! could not read the ledger lines: {self._lines_error}", style="dim")
                )
            )
        if self._writing:
            parts.extend([Text(""), Text(WRITING, style="dim")])
        if self._failure:
            parts.append(Text(""))
            parts.extend(hanging(t) for t in self._failure)
        return parts

    def _budget(self) -> int:
        """Lines the table's rows may take: the screen less the import door's
        chrome and everything this preview adds above and under the table."""
        answer = self._answer
        if answer is None:
            return MIN_PAGE
        extra = 1 + 1 + len(answer.halves)  # the statement's line, the balances
        extra += (2 + len(answer.taken_out)) if answer.taken_out else 0
        extra += 1 if answer.counts.new else 0
        extra += 1 if self._lines_error else 0
        return max(MIN_PAGE, self.size.height - PREVIEW_CHROME - extra)

    def _window(self, columns: Columns) -> list[list[RenderableType]]:
        """The rows from `_start` that fit the budget, each its own lines (a
        row, then its near misses); at least one row."""
        assert self._answer is not None
        budget = self._budget()
        out: list[list[RenderableType]] = []
        used = 0
        for row in self._answer.rows[self._start :]:
            lines = row_lines(row, columns, self._lines)
            if out and used + len(lines) > budget:
                break
            out.append(lines)
            used += len(lines)
        return out

    def _window_end(self) -> int:
        if self._answer is None:
            return 0
        return self._start + len(self._window(self._columns()))

    def body(self) -> RenderableType:
        title = Text(f"Preview · {pick_label(self._pick)}")
        answer = self._answer
        if answer is None:
            if self._failure:
                # A refused upload (screen 2): its words alone, nothing written.
                return Group(title, Text(""), *(hanging(t) for t in self._failure))
            title.append(" · ")
            title.append("nothing written yet", style="dim")
            return Group(title, Text(""), Text(ASKING, style="dim"))
        title.append(" · ")
        title.append("nothing written yet", style="dim")
        parts: list[RenderableType] = [title, statement_head(answer), *balance_lines(answer)]
        parts.append(Text(""))
        columns = self._columns()
        parts.append(columns.header())
        window = self._window(columns)
        for lines in window:
            parts.extend(lines)
        after = len(answer.rows) - (self._start + len(window))
        if after > 0:
            parts.append(Text(f"… {after} more · pgdn", style="dim"))
        elif self._start > 0:
            parts.append(Text(f"… {self._start} above · pgup", style="dim"))
        parts.append(Text(""))
        parts.extend(self._under_table(columns))
        return Group(*parts)


# ---------------------------------------------------------------------------
# after ⏎ — screen 3
# ---------------------------------------------------------------------------
def result_head(answer: StatementAnswer, pick: AccountPick) -> Text:
    """`✓ SIG-202610 closed · Signature PEN + USD`, then where the created lines
    went, dim, when the close created any."""
    head = Text(f"✓ {answer.name} closed", style=PALETTE.success)
    head.append(f" · {pick_label(pick)}")
    if answer.counts.new:
        head.append(f"  new ones under {PENDING} and {PENDING_HASHTAG}", style="dim")
    return head


class StatementResultScreen(ResultScreen):
    """The month closed: its name and account, the engine's counts in the past
    tense, and, when the close flagged ledger lines dated in the month that are
    in no statement, the `⚑` line with `f` opening them (the flagged lines'
    screen). `⏎` and `esc` are every result screen's (`ResultScreen`)."""

    BINDINGS = [
        Binding("f", "flagged", "Flagged", tooltip="The lines the close flagged for review"),
    ]

    def __init__(
        self,
        run: ImportRun,
        owner,
        pick: AccountPick,
        answer: StatementAnswer,
        flagged: list[str],
    ) -> None:
        super().__init__(run, owner)
        self._pick = pick
        self._answer = answer
        #: The ids of the lines the close flagged, as the flagged lines' screen
        #: last left them.
        self._flagged = list(flagged)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "flagged":
            return bool(self._flagged)
        return True

    def body(self) -> RenderableType:
        parts: list[RenderableType] = [
            result_head(self._answer, self._pick),
            Text(""),
            counts_line(self._answer.counts, done=True),
        ]
        if self._flagged:
            parts.append(flagged_note(len(self._flagged)))
        return Group(*parts)

    def action_flagged(self) -> None:
        if self._flagged:
            self.app.push_screen(
                FlaggedLinesScreen(self._flagged, statement=self._answer.name),
                self._flagged_back,
            )

    def _flagged_back(self, ids: list[str] | None) -> None:
        """Back from the flagged lines: the ones the engine still has."""
        if ids is not None:
            self._flagged = list(ids)
            self.refresh_bindings()
            self._repaint()
