"""The import door — a dropped bank file → its account → the preview → the result.

The LOG bar recognises a line of bank files (`expense/tui/dropped.py`) and hands
the paths to `LogBarScreen.import_bank_files`, which reads every file's bytes at
once (`read_dropped`). A file that cannot be read from disk never leaves the
bar: the hint says why. Otherwise the files go, one after the other in drop
order, through three full screens:

    ImportAccountScreen   which account is this file? — asked every time
    ImportPreviewScreen   the engine's dry run, nothing written yet
    ImportResultScreen    what the apply wrote

The app reads no cell of the file: it sends the file whole, and every row, its
outcome and every refusal is the engine's (contract: POST /v1/transactions/import).
Every step is the shared code in expense/bank_import/: the read, the account
picks and the one call in flow.py, how the answer reads in engine.py. What is
here is only what the screens draw, from
docs/mockups/expense-world-import-whole-file.html (the account list, a skipped
row, a card's `cur` column, a refused file, the result), with the rest of the
preview and the result from docs/mockups/expense-world-import-report.html, the
days where the file and the ledger disagree and a ledger line changed while
the import ran from docs/mockups/expense-world-bank-lines-upload.html, and the
several-files words from docs/mockups/expense-world-import-door.html.

The screens replace one another (`switch_screen`), so the stack is always
`… → LOG bar → the current import screen`, and leaving any of them lands on
the LOG bar, which decides what happens next (`LogBarScreen.import_closed`).
"""

from dataclasses import dataclass, replace
from pathlib import Path

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static

from expense import reads
from expense.bank_import import flow
from expense.bank_import.engine import (
    AnswerCounts,
    DayMismatch,
    ImportedRow,
    PreviewLine,
    Verdict,
    answer_counts,
    answer_rows,
    day_mismatches,
    preview_line,
)
from expense.bank_import.flow import (
    AccountPick,
    ImportRefused,
    account_picks,
    read_file,
    reconciliation_names,
)
from expense.errors import (
    EngineError,
    app_lines,
    engine_words,
    format_error,
    is_keyed_refusal,
    key_index,
    names_its_row,
)
from expense.formatting import format_cents, signed_cents
from expense.reads import items_of
from expense.tui.screens._base import screen_fetch_kwargs
from expense.tui.theme import ACCENT, AMOUNT_RULE, PALETTE
from expense.tui.widgets.cells import amount_cell
from expense.tui.widgets.header import Breadcrumb
from expense.tui.widgets.refusal import hanging, toast
from expense.tui.widgets.windowed import CURSOR_STYLE

#: The breadcrumb's trail before the file part.
CRUMB = ("Capture & ledger", "Import")

#: Where the new rows land — the category and the hashtag an import never sets.
PENDING = "@Pendiente"
PENDING_HASHTAG = "#Pendiente"

LOADING_ACCOUNTS = "loading accounts…"
NO_ACCOUNTS = "no accounts exist yet — create one in Manage › Accounts first."
ASKING = "asking the engine what the ledger already holds…"
WRITING = "writing…"
NOTHING_NEW = "nothing to import"
#: Under every refusal: the engine writes nothing when it refuses.
NOTHING_WRITTEN = "Nothing was written."
#: What `⏎` does after the apply met a ledger line changed while it ran (mockup
#: expense-world-bank-lines-upload.html screen 4 A), and its footer word.
RERUN = "It changed while the import ran: ⏎ checks the file against the ledger again."
RERUN_KEY = "Preview again"

#: Lines the preview spends on everything but its rows: the breadcrumb (4 with
#: its padding and rule), the body's padding (2), the title and the blank under
#: it, the table's header, the `… more` line, the blank and the counts' first
#: line under the table, and the footer. The counts' second line and the notes
#: under them are counted per screen.
PREVIEW_CHROME = 13

#: The fewest rows a page shows, however short the terminal.
MIN_PAGE = 3


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


# ---------------------------------------------------------------------------
# reading the dropped files — before any screen opens
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DroppedFile:
    """One dropped file and its bytes, read from disk and nothing more."""

    path: Path
    data: bytes


@dataclass(frozen=True)
class FileProblem:
    """The first dropped file that cannot be read from disk."""

    path: Path
    refused: ImportRefused


def read_dropped(paths: list[Path]) -> tuple[list[DroppedFile], FileProblem | None]:
    """Every file's bytes, in drop order — or the first file that cannot be
    read.

    All of them are read before any import starts, so a missing second file
    stops the run before the first is written. Nothing in a file is looked at:
    whether it is a bank download is the engine's to say.
    """
    files: list[DroppedFile] = []
    for path in paths:
        try:
            data = read_file(path)
        except ImportRefused as refused:
            return [], FileProblem(path, refused)
        files.append(DroppedFile(path, data))
    return files, None


def problem_hint(problem: FileProblem, *, name_it: bool) -> Text:
    """What the LOG bar says under a file it cannot send:
    `can't read the file · File not found: …`. With several files dropped,
    `name_it` puts the file's name first."""
    hint = Text()
    if name_it:
        hint.append(f"{problem.path.name} · ")
    hint.append("can't read the file", style=PALETTE.error)
    hint.append(f" · {problem.refused}")
    return hint


# ---------------------------------------------------------------------------
# the run — the files of one drop, imported one after the other
# ---------------------------------------------------------------------------
@dataclass
class ImportRun:
    """One drop's files and where the run is in them."""

    files: list[DroppedFile]
    index: int = 0
    #: The account list, read once per run.
    picks: list[AccountPick] | None = None
    #: How many of the files have been written.
    imported: int = 0

    @property
    def current(self) -> DroppedFile:
        return self.files[self.index]

    @property
    def several(self) -> bool:
        return len(self.files) > 1

    @property
    def has_next(self) -> bool:
        return self.index + 1 < len(self.files)

    def crumb(self) -> tuple[str, ...]:
        """`… › Import › <file name>`, or `… › Import › file 1 of 2`."""
        if self.several:
            return (*CRUMB, f"file {self.index + 1} of {len(self.files)}")
        return (*CRUMB, self.current.path.name)

    @property
    def left(self) -> int:
        """The files still to come, the current one included."""
        return len(self.files) - self.index

    def cancel_label(self) -> str:
        """esc's word before a file is written: it stops this file and every
        file after it (screen 7 B), so it counts them — `Cancel all` (three or
        more), `Cancel both` (two), `Cancel` (this one alone)."""
        if self.left >= 3:
            return "Cancel all"
        return "Cancel both" if self.left == 2 else "Cancel"


def _relabel(screen: Screen, key: str, description: str) -> None:
    """Give one of the screen's own bindings a footer word decided at run time
    (`Cancel both`, `Import 9 rows`). The screen's binding map is its own copy,
    so this touches no other screen."""
    bindings = screen._bindings.key_to_bindings.get(key)
    if bindings:
        screen._bindings.key_to_bindings[key] = [
            replace(b, description=description) for b in bindings
        ]
        screen.refresh_bindings()


class _ImportScreen(Screen):
    """What the three screens share: the breadcrumb, one body, the footer, and
    the way back to the LOG bar."""

    def __init__(self, run: ImportRun, owner) -> None:
        super().__init__()
        self._run = run
        #: The LOG bar the drop came from — `import_closed` is told how it ended.
        self._owner = owner

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self._run.crumb(), id="crumb")
        yield Static("", id="import-body")
        yield Footer()

    def on_mount(self) -> None:
        self._repaint()

    def on_resize(self) -> None:
        self._repaint()

    def _repaint(self) -> None:
        self.query_one("#import-body", Static).update(self.body())

    def body(self) -> RenderableType:
        raise NotImplementedError

    def _next_file(self) -> None:
        """On to the next file's account list; nothing is written here."""
        self._run.index += 1
        self.app.switch_screen(ImportAccountScreen(self._run, self._owner))

    def _close(self, *, home: bool = False) -> None:
        """Back to the LOG bar; it decides what the bar and the stack do next."""
        self.dismiss()
        self._owner.import_closed(self._run, home=home)


# ---------------------------------------------------------------------------
# which account is this file? — expense-world-import-whole-file.html 1
# ---------------------------------------------------------------------------
def account_lines(picks: list[AccountPick], cursor: int) -> list[Text]:
    """One line per pick, a card's two accounts one line (`PEN + USD`); the
    cursor row in reverse video."""
    name_w = max((len(p.name) for p in picks), default=0) + 4
    cur_w = max((len(p.currencies) for p in picks), default=0) + 6
    return [
        Text(
            f" {p.name.ljust(name_w)}{p.currencies.ljust(cur_w)}",
            style=CURSOR_STYLE if i == cursor else "",
        )
        for i, p in enumerate(picks)
    ]


class ImportAccountScreen(_ImportScreen):
    """Which account is this file? Asked every time; nothing is remembered."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "pick", "Pick"),
        Binding("down", "move(1)", "Move", key_display="↑↓", tooltip="Down"),
        Binding("up", "move(-1)", "Up", show=False),
    ]

    def __init__(self, run: ImportRun, owner) -> None:
        super().__init__(run, owner)
        self._cursor = 0
        self._error: str | None = None

    def on_mount(self) -> None:
        _relabel(self, "escape", self._run.cancel_label())
        super().on_mount()
        if self._run.picks is None:
            self._load_accounts()

    @work(thread=True, exclusive=True)
    def _load_accounts(self) -> None:
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            body = reads.fetch_accounts(cfg, include_people=False, **screen_fetch_kwargs(self.app))
            picks = account_picks(items_of(body))
        except Exception as exc:  # surfaced on the screen, never a crash
            self.app.call_from_thread(self._load_failed, format_error(exc))
            return
        self.app.call_from_thread(self._loaded, picks)

    def _loaded(self, picks: list[AccountPick]) -> None:
        self._run.picks = picks
        self.refresh_bindings()
        self._repaint()

    def _load_failed(self, message: str) -> None:
        self._error = message
        toast(self, message, title="Failed", severity="error")
        self._repaint()

    @property
    def _picks(self) -> list[AccountPick]:
        return self._run.picks or []

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("pick", "move"):
            return bool(self._picks)
        return True

    def body(self) -> RenderableType:
        lines: list[RenderableType] = [
            Text.assemble("Which account is this file?   ", (self._run.current.path.name, "dim")),
            Text(""),
        ]
        if self._error is not None:
            lines.append(Text(self._error, style=PALETTE.error))
        elif self._run.picks is None:
            lines.append(Text(LOADING_ACCOUNTS, style="dim"))
        elif not self._picks:
            lines.append(Text(NO_ACCOUNTS, style="dim"))
        else:
            lines.extend(account_lines(self._picks, self._cursor))
        return Group(*lines)

    def action_move(self, delta: int) -> None:
        if not self._picks:
            return
        self._cursor = max(0, min(len(self._picks) - 1, self._cursor + delta))
        self._repaint()

    def action_pick(self) -> None:
        if not self._picks:
            return
        pick = self._picks[self._cursor]
        self.app.switch_screen(ImportPreviewScreen(self._run, self._owner, pick))

    def action_cancel(self) -> None:
        self._close()


# ---------------------------------------------------------------------------
# the preview — expense-world-import-report.html 1 A, with a skipped row (2 B)
# and a card's `cur` column (3 B) from expense-world-import-whole-file.html
# ---------------------------------------------------------------------------
#: An empty cell: a row with no title.
EMPTY = "—"

#: Each verdict's mark and its style: ✓ in the ledger after the import, ✗ left
#: out, · a row of 0, nothing to look at.
MARKS: dict[Verdict, tuple[str, str]] = {
    Verdict.NEW: ("✓", PALETTE.success),
    Verdict.IN_LEDGER: ("✓", PALETTE.success),
    Verdict.MODIFIED: ("✓", PALETTE.success),
    Verdict.NOT_MOVED: ("✗", f"bold {PALETTE.error}"),
    Verdict.CLOSED: ("✗", f"bold {PALETTE.error}"),
    Verdict.SKIPPED: ("·", "dim"),
}

#: Each verdict's reason style: a new row stands out, a row already in the
#: ledger and a skipped one stay dim, a row left out takes the warning style.
REASON_STYLES: dict[Verdict, str] = {
    Verdict.NEW: PALETTE.success,
    Verdict.IN_LEDGER: "dim",
    Verdict.MODIFIED: "",
    Verdict.NOT_MOVED: PALETTE.warning,
    Verdict.CLOSED: PALETTE.warning,
    Verdict.SKIPPED: "dim",
}


def mark_cell(line: PreviewLine) -> Text:
    mark, style = MARKS[line.verdict]
    return Text(mark, style=style)


def reason_cell(line: PreviewLine) -> Text:
    return Text(line.reason, style=REASON_STYLES[line.verdict])


def preview_table(lines: list[PreviewLine], pick: AccountPick) -> Table:
    """`#  date  title  amount  ✓  reason`, one row per row the engine read,
    numbered by its spreadsheet row; the mark's column has no heading. On a
    card, `cur` after the amount: the currency of the account the engine put
    the row on."""
    headers = ["#", "date", "title", "amount", *(["cur"] if pick.is_card else []), "", "reason"]
    table = Table(box=None, pad_edge=False, expand=False, show_header=True)
    for header in headers:
        table.add_column(
            Text(header, style="dim"),
            justify="right" if header in ("#", "amount") else "left",
            no_wrap=True,
            overflow="ellipsis",
        )
    for line in lines:
        row = line.row
        cells: list[RenderableType] = [
            str(row.row),
            row.date_iso,
            Text(row.title or EMPTY),  # the engine's words, never read as markup
            amount_cell(row.amount_cents, PALETTE, AMOUNT_RULE),
        ]
        if pick.is_card:
            cells.append(pick.currency_of(row.account_id))
        cells.extend([mark_cell(line), reason_cell(line)])
        table.add_row(*cells)
    return table


def counts_lines(counts: AnswerCounts, *, done: bool) -> list[Text]:
    """`14 rows · 9 new · 5 in the ledger · 1 moves to the bank's day · 2 take
    the bank's title`, then, when there are any, `1 closed · 1 skipped` under
    it. `done` says it in the past tense, as the screen after importing does.
    Every figure is the engine's: its `counts`, and its rows for the total."""
    kept = Text(f"{counts.rows} {_plural(counts.rows, 'row', 'rows')} · ")
    kept.append(f"{counts.new} new", style=PALETTE.success if counts.new else "")
    kept.append(f" · {counts.matched} in the ledger")
    if counts.redated:
        verb = "moved" if done else _plural(counts.redated, "moves", "move")
        kept.append(f" · {counts.redated} {verb} to the bank's day")
    if counts.retitled:
        verb = "took" if done else _plural(counts.retitled, "takes", "take")
        kept.append(f" · {counts.retitled} {verb} the bank's title")
    left: list[str] = []
    if counts.sealed:
        left.append(f"{counts.sealed} closed")
    if counts.skipped:
        left.append(f"{counts.skipped} skipped")
    return [kept, Text(" · ".join(left))] if left else [kept]


def counts_block(lines: list[Text]) -> RenderableType:
    """The counts, the second line under the first count, not under `14 rows`."""
    if len(lines) == 1:
        return lines[0]
    first = lines[0]
    lead = first.plain.index(" · ") + 3
    grid = Table.grid()
    grid.add_column(no_wrap=True)
    grid.add_column()
    rest = first[lead:]
    rest.append("\n")
    rest.append_text(lines[1])
    grid.add_row(first[:lead], rest)
    return grid


@dataclass(frozen=True)
class FlaggedRow:
    """One row behind a day the engine reports: a file row no ledger line
    matched, or one part of a ledger line no file row claimed — each part its
    own row, the transaction's title and the part's own amount."""

    #: The file row's spreadsheet number; None for a ledger part.
    row: int | None
    title: str
    amount_cents: int  # signed: negative = money out


def flagged_rows(day: DayMismatch, rows: dict[int, ImportedRow]) -> list[FlaggedRow]:
    """The day's file rows not found, by their spreadsheet row (`rows`: row
    number → the row the engine read), then every part of its unclaimed lines
    in the engine's order. A part arrives as a magnitude and a type;
    `signed_cents` signs it. Nothing is added up."""
    flagged = [
        FlaggedRow(n, rows[n].title or "", rows[n].amount_cents)
        for n in day.unmatched_rows
        if n in rows
    ]
    flagged.extend(
        FlaggedRow(None, str(part.get("title") or ""), signed_cents(part))
        for part in day.unclaimed_parts
    )
    return flagged


def day_label(day: DayMismatch, *, name_account: bool) -> str:
    """`2026-09-12`, or `2026-09-12 · BCP Signature USD` on a card file, whose
    currencies are two accounts."""
    return f"{day.date_iso} · {day.account_name}" if name_account else day.date_iso


def _amount(cents: int, width: int = 0) -> Text:
    """A signed amount, sign-coloured, right-aligned in `width`."""
    cell = amount_cell(cents, PALETTE, AMOUNT_RULE)
    text = cell if isinstance(cell, Text) else Text(cell)
    return Text(" " * max(0, width - len(text.plain))) + text


def preview_days(
    days: list[DayMismatch], rows: list[ImportedRow], *, name_account: bool
) -> list[Text]:
    """The days where the file and the ledger disagree, each with its two
    totals and the rows behind it: the file's by its spreadsheet row, the
    ledger's by title and amount, each part of a split transaction on its own
    line (mockup expense-world-bank-lines-upload.html screen 2 B). A report
    only: nothing on it changes what `⏎` writes."""
    if not days:
        return []
    n = len(days)
    lines = [
        Text(
            f"! {n} {_plural(n, 'day', 'days')} where the file and the ledger disagree",
            style=PALETTE.warning,
        )
    ]
    by_row = {r.row: r for r in rows}
    labels = [day_label(d, name_account=name_account) for d in days]
    behind = [flagged_rows(d, by_row) for d in days]
    every = [r for flagged in behind for r in flagged]
    label_w = max(len(label) for label in labels)
    file_w = max(len(format_cents(d.file_net_cents)) for d in days)
    ledger_w = max(len(format_cents(d.ledger_net_cents)) for d in days)
    tag_w = max((len(f"row {r.row}") for r in every if r.row is not None), default=0)
    title_w = max((len(r.title) for r in every), default=0)
    amount_w = max((len(format_cents(r.amount_cents)) for r in every), default=0)
    for label, day, flagged in zip(labels, days, behind, strict=True):
        head = Text(f"    {label.ljust(label_w)}   file ")
        head.append_text(_amount(day.file_net_cents, file_w))
        head.append(" · ledger after import ", style="dim")
        head.append_text(_amount(day.ledger_net_cents, ledger_w))
        lines.append(head)
        for r in flagged:
            line = Text("      ")
            if tag_w:
                tag = f"row {r.row}" if r.row is not None else ""
                line.append(tag.ljust(tag_w), style=ACCENT)
                line.append("   ")
            line.append(f"{r.title.ljust(title_w)}  ")
            line.append_text(_amount(r.amount_cents, amount_w))
            where = (
                "in the file, not found" if r.row is not None else "in the ledger, not in the file"
            )
            line.append(f"   {where}", style="dim")
            lines.append(line)
    return lines


def changed_while_running(err: Exception) -> bool:
    """A `409 CONFLICT` whose reason on a `rows.<row>` key is
    `CONCURRENT_CHANGE`: something changed a ledger line a file row matched
    while the import ran, and nothing was written
    (contract: POST /v1/transactions/import, "Concurrency")."""
    return (
        isinstance(err, EngineError)
        and err.code == "CONFLICT"
        and any(
            key_index(key, "rows") is not None and reason == "CONCURRENT_CHANGE"
            for key, reason in (err.reasons or {}).items()
        )
    )


def refusal_lines(err: EngineError) -> list[Text]:
    """A refusal as the preview shows it (expense-world-import-whole-file.html
    4): `CODE — message`, then a `!` line per refused key in the engine's
    order, then `Nothing was written.` A row's words that begin with its
    spreadsheet row (`Row 12: …`) show alone; any other key (`file`,
    `account_id`, a row whose words do not name it) shows before its words."""
    lines = [Text(f"{err.code} — {err.message}", style=PALETTE.error)]
    for key, message in (err.fields or {}).items():
        words = str(message) if names_its_row(key, str(message)) else f"{key}: {message}"
        lines.append(Text(f"! {words}", style=PALETTE.error))
    lines.append(Text(NOTHING_WRITTEN, style="dim"))
    return lines


def failure_lines(err: Exception) -> list[Text]:
    """An engine refusal, or any other failure, as the screen shows it.

    A refusal naming what it refused is `refusal_lines`, then, after a blank
    line, what `⏎` does next when a row changed while the import ran (screen
    4 A), or else the app's line for the refusal when it has one (`app_lines`);
    anything else is the app's own error text."""
    if isinstance(err, EngineError) and is_keyed_refusal(err):
        lines = refusal_lines(err)
        after = [RERUN] if changed_while_running(err) else app_lines(err)
        if after:
            lines.append(Text(""))
            lines.extend(Text(line) for line in after)
        return lines
    return [Text(format_error(err), style=PALETTE.error)]


class ImportPreviewScreen(_ImportScreen):
    """The engine's dry run of this file on this account. Nothing is written
    until `⏎`. With nothing new (screen 6 A), `⏎` opens the next file's
    account list when a file follows, and does nothing on the last one. When
    the apply meets a ledger line changed while it ran, `⏎ Preview again`
    asks for a fresh dry run; nothing is sent again without one."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "apply", "Import"),
        Binding("pagedown", "page(1)", "More rows", key_display="pgdn", show=False),
        Binding("pageup", "page(-1)", "Earlier rows", key_display="pgup", show=False),
    ]

    def __init__(self, run: ImportRun, owner, pick: AccountPick) -> None:
        super().__init__(run, owner)
        self._pick = pick
        #: Every row the engine read, with its verdict and reason; None until
        #: the dry run answers.
        self._lines: list[PreviewLine] | None = None
        #: The engine's days that disagree and its counts, from the dry run.
        self._mismatches: list[DayMismatch] = []
        self._counts: AnswerCounts | None = None
        #: Why the reconciliations that stop a move could not be named.
        self._names_error: str | None = None
        self._failure: list[Text] = []
        self._writing = False
        #: The apply met a ledger line changed while it ran: `⏎` previews again.
        self._rerun = False
        self._start = 0

    def on_mount(self) -> None:
        _relabel(self, "escape", self._run.cancel_label())
        super().on_mount()
        self._ask(dry_run=True)

    # ---- state ---------------------------------------------------------------
    @property
    def new_count(self) -> int:
        """The engine's count of new rows."""
        return self._counts.new if self._counts is not None else 0

    @property
    def _answered(self) -> bool:
        return self._lines is not None and self._counts is not None

    @property
    def can_apply(self) -> bool:
        return self._answered and self.new_count > 0 and not self._failure and not self._writing

    @property
    def can_skip(self) -> bool:
        """Nothing new, a file after this one: `⏎` moves on, writing nothing."""
        return (
            self._answered
            and self.new_count == 0
            and not self._failure
            and not self._writing
            and self._run.has_next
        )

    @property
    def can_rerun(self) -> bool:
        """The apply met a ledger line changed while it ran: `⏎` previews again."""
        return self._rerun and not self._writing

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "apply":
            return self.can_apply or self.can_skip or self.can_rerun
        if action == "page":
            delta = parameters[0] if parameters else 1
            if delta == 1:
                return self._start + self._page_size() < len(self._lines or [])
            return self._start > 0
        return True

    def _counts_lines(self) -> list[Text]:
        if self._counts is None:
            return []
        return counts_lines(self._counts, done=False)

    def _page_size(self) -> int:
        notes = len(self._notes()) + max(0, len(self._counts_lines()) - 1)
        notes += 1 if self._answered and not self.new_count else 0
        return max(MIN_PAGE, self.size.height - PREVIEW_CHROME - notes)

    # ---- the engine ----------------------------------------------------------
    @work(thread=True, exclusive=True, group="engine-write")
    def _ask(self, dry_run: bool) -> None:
        """One `POST /transactions/import` — the dry run, or the apply. Both go
        through flow.py's one call; the client mints the idempotency key. The
        apply's answer is read for its counts alone: the screen after importing
        shows nothing else."""
        from expense import config as config_module
        from expense.http import ExpenseClient

        try:
            cfg = config_module.ensure_loaded()
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                response = flow.import_call(
                    client, self._pick, self._run.current.data, dry_run=dry_run
                )
            counts = answer_counts(response)
            if dry_run:
                rows = answer_rows(response)
                mismatches = day_mismatches(response, self._pick.account_names)
                # The one read the preview adds: the names of the
                # reconciliations that stop a move to the bank's day.
                names, names_error = reconciliation_names(cfg, rows, verbose=self.app._verbose)
                lines = [preview_line(r, names) for r in rows]
        except Exception as err:  # every failure is shown, none swallowed
            self.app.call_from_thread(self._failed, err)
            return
        if dry_run:
            self.app.call_from_thread(self._previewed, lines, mismatches, counts, names_error)
        else:
            self.app.call_from_thread(self._applied, counts)

    def _previewed(
        self,
        lines: list[PreviewLine],
        mismatches: list[DayMismatch],
        counts: AnswerCounts,
        names_error: str | None,
    ) -> None:
        self._lines, self._mismatches, self._counts = lines, mismatches, counts
        self._names_error = names_error
        new = self.new_count
        if new:
            _relabel(self, "enter", f"Import {new} {_plural(new, 'row', 'rows')}")
        elif self._run.has_next:
            # Nothing to write, a file still to come: ⏎ moves on to it, and
            # esc still stops this file and the ones after it.
            _relabel(self, "enter", "Next file")
        else:
            # Nothing to write and no file after: esc only goes back (screen 6 A).
            _relabel(self, "escape", "Back")
        self.refresh_bindings()
        self._repaint()

    def _applied(self, counts: AnswerCounts) -> None:
        self._writing = False
        self._run.imported += 1
        self.app.switch_screen(ImportResultScreen(self._run, self._owner, self._pick, counts))

    def _failed(self, err: Exception) -> None:
        self._writing = False
        self._failure = failure_lines(err)
        self._rerun = changed_while_running(err)
        message = format_error(err)
        if isinstance(err, EngineError) and self._rerun:
            # The screen's own next step, not the one "save again" of other saves.
            _relabel(self, "enter", RERUN_KEY)
            message = f"{engine_words(err)}\n\n{RERUN}"
        elif not self._run.has_next:
            # Nothing of this file can be written: esc only goes back (pane 4).
            _relabel(self, "escape", "Back")
        toast(self, message, title="Failed", severity="error")
        self.refresh_bindings()
        self._repaint()

    # ---- keys ----------------------------------------------------------------
    def action_apply(self) -> None:
        if self.can_rerun:
            # The ledger moved under the apply: what is new may have moved too,
            # so the file is checked again before anything is written.
            self._rerun = False
            self._failure = []
            self._lines, self._mismatches, self._counts = None, [], None
            self._start = 0
            self.refresh_bindings()
            self._repaint()
            self._ask(dry_run=True)
            return
        if self.can_skip:
            self._next_file()
            return
        if not self.can_apply:
            return
        self._writing = True
        self.refresh_bindings()
        self._repaint()
        self._ask(dry_run=False)

    def action_page(self, delta: int) -> None:
        total = len(self._lines or [])
        size = self._page_size()
        if (delta > 0 and self._start + size >= total) or (delta < 0 and self._start == 0):
            return
        self._start = max(0, self._start + delta * size)
        self.refresh_bindings()
        self._repaint()

    def action_cancel(self) -> None:
        if self._writing:
            self.notify("Writing — one moment.")
            return
        self._close()

    # ---- render --------------------------------------------------------------
    def _notes(self) -> list[Text]:
        """Everything under the counts: the days where the file and the ledger
        disagree, and why a reconciliation that stops a move goes unnamed."""
        if self._lines is None:
            return []
        lines = preview_days(
            self._mismatches, [line.row for line in self._lines], name_account=self._pick.is_card
        )
        if self._names_error:
            lines.append(
                Text(
                    f"! could not read the reconciliations' names: {self._names_error}", style="dim"
                )
            )
        return lines

    def body(self) -> RenderableType:
        title = Text(f"Preview · {self._pick.name} · ")
        title.append("nothing written yet", style="dim")
        parts: list[RenderableType] = [title, Text("")]
        if self._lines is None or self._counts is None:
            if self._failure:
                parts.extend(hanging(t) for t in self._failure)
            else:
                parts.append(Text(ASKING, style="dim"))
            return Group(*parts)

        lines = self._lines
        size = self._page_size()
        window = lines[self._start : self._start + size]
        parts.append(preview_table(window, self._pick))
        after = len(lines) - (self._start + len(window))
        if after > 0:
            parts.append(Text(f"… {after} more · pgdn", style="dim"))
        elif self._start > 0:
            parts.append(Text(f"… {self._start} above · pgup", style="dim"))
        parts.append(Text(""))
        parts.append(counts_block(self._counts_lines()))
        parts.extend(hanging(t) for t in self._notes())
        if not self.new_count:
            parts.append(Text(NOTHING_NEW, style="dim"))
        if self._writing:
            parts.extend([Text(""), Text(WRITING, style="dim")])
        if self._failure:
            parts.append(Text(""))
            parts.extend(hanging(t) for t in self._failure)
        return Group(*parts)


# ---------------------------------------------------------------------------
# the result — expense-world-import-whole-file.html 5: its title line and the counts
# ---------------------------------------------------------------------------
def result_head(pick: AccountPick, counts: AnswerCounts) -> Text:
    """`✓ 9 rows imported · Sueldo Soles   new ones under @Pendiente and
    #Pendiente` — the engine's `new`."""
    new = counts.new
    head = Text("✓ ", style=PALETTE.success)
    head.append(f"{new} {_plural(new, 'row', 'rows')} imported", style="bold")
    head.append(f" · {pick.name}")
    head.append(f"   new ones under {PENDING} and {PENDING_HASHTAG}", style="dim")
    return head


class ImportResultScreen(_ImportScreen):
    """What the apply wrote: its title line and the engine's counts, in the
    past tense. `⏎` opens the next file's account list, or goes Home after the
    last; `esc` returns to the LOG bar."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("enter", "next", "Home"),
    ]

    def __init__(self, run: ImportRun, owner, pick: AccountPick, counts: AnswerCounts) -> None:
        super().__init__(run, owner)
        self._pick = pick
        #: The engine's counts of the apply.
        self._counts = counts

    def on_mount(self) -> None:
        if self._run.has_next:
            _relabel(self, "enter", "Next file")
        super().on_mount()

    def body(self) -> RenderableType:
        return Group(
            result_head(self._pick, self._counts),
            Text(""),
            counts_block(counts_lines(self._counts, done=True)),
        )

    def action_next(self) -> None:
        if self._run.has_next:
            self._next_file()
            return
        self._close(home=True)

    def action_back(self) -> None:
        self._close()
