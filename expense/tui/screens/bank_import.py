"""The import door — a dropped bank file → its account → the preview → the result.

The LOG bar recognises a line of bank files (`expense/tui/dropped.py`) and hands
the paths to `LogBarScreen.import_bank_files`, which reads every file at once
(`read_dropped`). A file that is not a BCP export never leaves the bar: the
hint says what is missing (mockup screen 5 A). Otherwise the files go, one after
the other in drop order, through three full screens:

    ImportAccountScreen   which account is this file? — asked every time
    ImportPreviewScreen   the engine's dry run, nothing written yet
    ImportResultScreen    what the apply wrote

Every step is the shared code in expense/bank_import/flow.py: the read,
the account folding, the `Prepared` rows, the one `POST /transactions/import`
(contract: POST /v1/transactions/import) and the verdicts. What is here is
only what the screens draw: the preview's table of the file's rows and the
screen after importing from docs/mockups/expense-world-import-report.html, the
days where the file and the ledger disagree and a ledger line changed while
the import ran from docs/mockups/expense-world-bank-lines-upload.html, and the
rest from docs/mockups/expense-world-import-door.html.

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
    IMPORT_FLOOR,
    IN_LEDGER,
    NEW,
    AnswerCounts,
    DayMismatch,
    IncompleteAnswer,
    Placed,
    SentRow,
    answer_counts,
    day_mismatches,
    placements,
    row_refusals,
)
from expense.bank_import.flow import (
    AccountGroup,
    FileLine,
    ImportRefused,
    Prepared,
    account_groups,
    file_lines,
    import_counts,
    incomplete_sentence,
    prepared_for,
    read_bank_file,
    reconciliation_names,
)
from expense.bank_import.parse import BadRow, BankFormatError, BankRow
from expense.errors import EngineError, engine_words, format_error, key_index
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
    """One dropped file, already read."""

    path: Path
    rows: list[BankRow]
    bad: list[BadRow]


@dataclass(frozen=True)
class FileProblem:
    """The first dropped file the import cannot read."""

    path: Path
    refused: ImportRefused


def read_dropped(paths: list[Path]) -> tuple[list[DroppedFile], FileProblem | None]:
    """Every file read, in drop order — or the first one that cannot be.

    All of them are read before any import starts, so a bad second file stops
    the run before the first is written.
    """
    files: list[DroppedFile] = []
    for path in paths:
        try:
            rows, bad = read_bank_file(str(path))
        except ImportRefused as refused:
            return [], FileProblem(path, refused)
        files.append(DroppedFile(path, rows, bad))
    return files, None


def problem_hint(problem: FileProblem, *, name_it: bool) -> Text:
    """What the LOG bar says under a file it will not import (screen 5 A).

    `not a BCP bank file · missing the columns Fecha, Monto`, and under it, dim,
    `it has: Mes, Categoria, Total`. A file that could not be read at all, or
    holds no rows, carries the reader's own sentence instead. With several
    files dropped, `name_it` puts the file's name first.
    """
    hint = Text()
    if name_it:
        hint.append(f"{problem.path.name} · ")
    hint.append("not a BCP bank file", style=PALETTE.error)
    cause = problem.refused.__cause__
    if isinstance(cause, BankFormatError):
        columns = _plural(len(cause.missing), "column", "columns")
        hint.append(f" · missing the {columns} {', '.join(cause.missing)}")
        hint.append("\n")
        hint.append(f"it has: {', '.join(cause.found) or '(no headers)'}", style="dim")
    else:
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
    groups: list[AccountGroup] | None = None
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


def movements(file: DroppedFile) -> str:
    """`14 movements` — every line of the file, read or refused."""
    n = len(file.rows) + len(file.bad)
    return f"{n} {_plural(n, 'movement', 'movements')}"


def file_banner(file: DroppedFile) -> str:
    """`14 movements · 2026-09-02 → 2026-09-15 · PEN` — what the file holds."""
    rows = file.rows
    parts = [movements(file)]
    if rows:
        days = sorted(r.date_iso for r in rows)
        parts.append(f"{days[0]} → {days[-1]}")
        parts.append(" + ".join(sorted({r.currency for r in rows})))
    return " · ".join(parts)


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
# screen 2 — which account is this file?
# ---------------------------------------------------------------------------
def account_lines(groups: list[AccountGroup], cursor: int) -> list[Text]:
    """One line per account, a card's legs folded into one (`PEN + USD`); the
    cursor row in reverse video."""
    name_w = max((len(g.name) for g in groups), default=0) + 4
    cur_w = max((len(g.currencies) for g in groups), default=0) + 6
    return [
        Text(
            f" {g.name.ljust(name_w)}{g.currencies.ljust(cur_w)}",
            style=CURSOR_STYLE if i == cursor else "",
        )
        for i, g in enumerate(groups)
    ]


class ImportAccountScreen(_ImportScreen):
    """Which account is this file? Asked every time; nothing is remembered."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
        Binding("enter", "pick", "Pick"),
    ]

    def __init__(self, run: ImportRun, owner) -> None:
        super().__init__(run, owner)
        self._cursor = 0
        self._error: str | None = None
        #: A pick the file does not fit (a currency with no leg, too many rows).
        self._refused: list[Text] = []

    def on_mount(self) -> None:
        _relabel(self, "escape", self._run.cancel_label())
        super().on_mount()
        if self._run.groups is None:
            self._load_accounts()

    @work(thread=True, exclusive=True)
    def _load_accounts(self) -> None:
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            body = reads.fetch_accounts(cfg, include_people=False, **screen_fetch_kwargs(self.app))
            groups = account_groups(items_of(body))
        except Exception as exc:  # surfaced on the screen, never a crash
            self.app.call_from_thread(self._load_failed, format_error(exc))
            return
        self.app.call_from_thread(self._loaded, groups)

    def _loaded(self, groups: list[AccountGroup]) -> None:
        self._run.groups = groups
        self.refresh_bindings()
        self._repaint()

    def _load_failed(self, message: str) -> None:
        self._error = message
        toast(self, message, title="Failed", severity="error")
        self._repaint()

    @property
    def _groups(self) -> list[AccountGroup]:
        return self._run.groups or []

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("pick", "move"):
            return bool(self._groups)
        return True

    def body(self) -> RenderableType:
        file = self._run.current
        lines: list[RenderableType] = []
        if self._run.several:
            lines.append(Text("Which account is this file?"))
            lines.append(Text(f"{file.path.name} · {movements(file)}", style="dim"))
        else:
            lines.append(
                Text.assemble("Which account is this file?   ", (file_banner(file), "dim"))
            )
        lines.append(Text(""))
        if self._error is not None:
            lines.append(Text(self._error, style=PALETTE.error))
        elif self._run.groups is None:
            lines.append(Text(LOADING_ACCOUNTS, style="dim"))
        elif not self._groups:
            lines.append(Text(NO_ACCOUNTS, style="dim"))
        else:
            lines.extend(account_lines(self._groups, self._cursor))
        if self._refused:
            lines.append(Text(""))
            lines.extend(self._refused)
        return Group(*lines)

    def action_move(self, delta: int) -> None:
        if not self._groups:
            return
        self._cursor = max(0, min(len(self._groups) - 1, self._cursor + delta))
        self._refused = []
        self._repaint()

    def action_pick(self) -> None:
        if not self._groups:
            return
        group = self._groups[self._cursor]
        file = self._run.current
        try:
            prepared = prepared_for(str(file.path), group, file.rows, file.bad)
        except ImportRefused as refused:
            lines = []
            if refused.list_bad:
                lines = [Text(f"! row {b.line}: {b.reason}", style=PALETTE.error) for b in file.bad]
            lines.append(Text(str(refused), style=PALETTE.error))
            self._refused = lines
            self._repaint()
            return
        self.app.switch_screen(ImportPreviewScreen(self._run, self._owner, prepared))

    def action_cancel(self) -> None:
        self._close()


# ---------------------------------------------------------------------------
# screen 3 (and 6 A) — the preview, as expense-world-import-report.html 1 A
# ---------------------------------------------------------------------------
#: A cell of the file the parser could not read.
UNREAD = "—"


def mark_cell(line: FileLine) -> Text:
    """✓ when the row is in the ledger after the import, ✗ when it is left out."""
    if line.kept:
        return Text("✓", style=PALETTE.success)
    return Text("✗", style=f"bold {PALETTE.error}")


def reason_cell(line: FileLine) -> Text:
    """The reason alone: a new row stands out, a row already in the ledger
    stays dim, a row left out takes the warning style."""
    if not line.kept:
        style = PALETTE.warning
    elif line.reason == NEW:
        style = PALETTE.success
    elif line.reason == IN_LEDGER:
        style = "dim"
    else:
        style = ""
    return Text(line.reason, style=style)


def preview_table(lines: list[FileLine]) -> Table:
    """`#  date  title  amount  ✓  reason`, one row per line of the file,
    numbered by its own line; the mark's column has no heading."""
    table = Table(box=None, pad_edge=False, expand=False, show_header=True)
    for header in ("#", "date", "title", "amount", "", "reason"):
        table.add_column(
            Text(header, style="dim"),
            justify="right" if header in ("#", "amount") else "left",
            no_wrap=True,
            overflow="ellipsis",
        )
    for line in lines:
        amount = (
            UNREAD
            if line.amount_cents is None
            else amount_cell(line.amount_cents, PALETTE, AMOUNT_RULE)
        )
        table.add_row(
            str(line.line),
            line.date_iso or UNREAD,
            line.title or UNREAD,
            amount,
            mark_cell(line),
            reason_cell(line),
        )
    return table


def counts_lines(prepared: Prepared, answer: AnswerCounts, *, done: bool) -> list[Text]:
    """`14 rows · 9 new · 5 in the ledger · 1 moves to the bank's day · 2 take
    the bank's title`, then, when there are any, `1 closed · 1 before 2026 · 1
    unreadable` under it. `done` says it in the past tense, as the screen after
    importing does. Every verdict's count is the engine's own (`counts`); none
    is counted off the rows."""
    counts = import_counts(prepared, answer)
    kept = Text(f"{counts.total} {_plural(counts.total, 'row', 'rows')} · ")
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
    if counts.before_floor:
        left.append(f"{counts.before_floor} before {IMPORT_FLOOR.year}")
    if counts.refused:
        left.append(f"{counts.refused} unreadable")
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
    own row, the purchase's title and the part's own amount."""

    #: The file row; None for a ledger part.
    sent: SentRow | None
    title: str
    amount_cents: int  # signed: negative = money out


def flagged_rows(day: DayMismatch, sent: list[SentRow]) -> list[FlaggedRow]:
    """The day's file rows not found, by the index each was sent under, then
    every part of its unclaimed lines in the engine's order. A part arrives as
    a magnitude and a type; `signed_cents` signs it. Nothing is added up: a
    line's `net_cents` stays the engine's."""
    rows = [
        FlaggedRow(sent[i], sent[i].row.title, sent[i].row.amount_cents)
        for i in day.unmatched_rows
        if 0 <= i < len(sent)
    ]
    rows.extend(
        FlaggedRow(None, str(part.get("title") or ""), signed_cents(part))
        for line in day.unclaimed_lines
        for part in line.parts
    )
    return rows


def day_label(day: DayMismatch, *, name_account: bool) -> str:
    """`2026-09-12`, or `2026-09-12 · BCP Signature USD` on a card file, whose
    currencies are two accounts."""
    return f"{day.date_iso} · {day.account_name}" if name_account else day.date_iso


def _amount(cents: int, width: int = 0) -> Text:
    """A signed amount, sign-coloured, right-aligned in `width`."""
    cell = amount_cell(cents, PALETTE, AMOUNT_RULE)
    text = cell if isinstance(cell, Text) else Text(cell)
    return Text(" " * max(0, width - len(text.plain))) + text


def preview_days(days: list[DayMismatch], sent: list[SentRow], *, name_account: bool) -> list[Text]:
    """The days where the file and the ledger disagree, each with its two
    totals and the rows behind it: the file's by its line, the ledger's by
    title and amount, each part of a split purchase on its own line (mockup
    expense-world-bank-lines-upload.html screen 2 B). A report only: nothing
    on it changes what `⏎` writes."""
    if not days:
        return []
    n = len(days)
    lines = [
        Text(
            f"! {n} {_plural(n, 'day', 'days')} where the file and the ledger disagree",
            style=PALETTE.warning,
        )
    ]
    labels = [day_label(d, name_account=name_account) for d in days]
    behind = [flagged_rows(d, sent) for d in days]
    every = [r for rows in behind for r in rows]
    label_w = max(len(label) for label in labels)
    file_w = max(len(format_cents(d.file_net_cents)) for d in days)
    ledger_w = max(len(format_cents(d.ledger_net_cents)) for d in days)
    tag_w = max((len(f"row {r.sent.row.line}") for r in every if r.sent), default=0)
    title_w = max((len(r.title) for r in every), default=0)
    amount_w = max((len(format_cents(r.amount_cents)) for r in every), default=0)
    for label, day, rows in zip(labels, days, behind, strict=True):
        head = Text(f"    {label.ljust(label_w)}   file ")
        head.append_text(_amount(day.file_net_cents, file_w))
        head.append(" · ledger after import ", style="dim")
        head.append_text(_amount(day.ledger_net_cents, ledger_w))
        lines.append(head)
        for r in rows:
            line = Text("      ")
            if tag_w:
                tag = f"row {r.sent.row.line}" if r.sent else ""
                line.append(tag.ljust(tag_w), style=ACCENT)
                line.append("   ")
            line.append(f"{r.title.ljust(title_w)}  ")
            line.append_text(_amount(r.amount_cents, amount_w))
            where = "in the file, not found" if r.sent else "in the ledger, not in the file"
            line.append(f"   {where}", style="dim")
            lines.append(line)
    return lines


def preview_notes(
    prepared: Prepared, days: list[DayMismatch], names_error: str | None
) -> list[Text]:
    """Everything under the counts: the days where the file and the ledger
    disagree, and why a reconciliation that stops a move goes unnamed."""
    lines = preview_days(days, prepared.sent, name_account=len(prepared.group.legs) > 1)
    if names_error:
        lines.append(
            Text(f"! could not read the reconciliations' names: {names_error}", style="dim")
        )
    return lines


def changed_while_running(err: Exception) -> bool:
    """A `409 CONFLICT` whose reason on a `rows.<index>` key is
    `CONCURRENT_CHANGE`: something changed a ledger line a file row matched
    while the import ran, and nothing was written
    (contract: POST /v1/transactions/import)."""
    return (
        isinstance(err, EngineError)
        and err.code == "CONFLICT"
        and any(
            key_index(key, "rows") is not None and reason == "CONCURRENT_CHANGE"
            for key, reason in (err.reasons or {}).items()
        )
    )


def _refused_rows(err: EngineError, prepared: Prepared) -> list[Text]:
    """`CODE — message`, then `! row 6: …` (or `! row 3 (amount_cents): …`) for
    each refused key, the file's line for the engine's index, then
    `Nothing was written.`"""
    lines = [Text(f"{err.code} — {err.message}", style=PALETTE.error)]
    for line, field, message in row_refusals(err.fields, prepared.sent):
        if line is None:
            where = str(field)
        else:
            where = f"row {line} ({field})" if field else f"row {line}"
        lines.append(Text(f"! {where}: {message}", style=PALETTE.error))
    lines.append(Text("Nothing was written.", style="dim"))
    return lines


def failure_lines(err: Exception, prepared: Prepared, *, applied: bool) -> list[Text]:
    """An engine refusal or a short answer, as the screen shows it.

    A `422` names each refused row by the file's line, like the typed import;
    so does a row changed while the import ran, with what `⏎` does next
    (screen 4 A); anything else is the app's own error text.
    """
    if isinstance(err, IncompleteAnswer):
        lines = [Text(incomplete_sentence(err, prepared), style=PALETTE.error)]
        lines.extend(
            Text(f"! row {s.row.line}: no answer", style=PALETTE.error) for s in err.missing
        )
        if applied:
            lines.append(
                Text(
                    "The import may have been written — import the same file again to see "
                    "what the ledger holds now.",
                    style="dim",
                )
            )
        return lines
    if isinstance(err, EngineError) and changed_while_running(err):
        return [*_refused_rows(err, prepared), Text(""), Text(RERUN)]
    if isinstance(err, EngineError) and err.status == 422:
        return _refused_rows(err, prepared)
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

    def __init__(self, run: ImportRun, owner, prepared: Prepared) -> None:
        super().__init__(run, owner)
        self._prepared = prepared
        self._placed: list[Placed] | None = None
        #: Every line of the file, with its mark and its reason.
        self._lines: list[FileLine] = []
        #: The engine's days that disagree and its counts, from the answer.
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
    def can_apply(self) -> bool:
        return (
            self._placed is not None
            and self.new_count > 0
            and not self._failure
            and not self._writing
        )

    @property
    def can_skip(self) -> bool:
        """Nothing new, a file after this one: `⏎` moves on, writing nothing."""
        return (
            self._placed is not None
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
                return self._start + self._page_size() < len(self._lines)
            return self._start > 0
        return True

    def _counts_lines(self) -> list[Text]:
        if self._counts is None:
            return []
        return counts_lines(self._prepared, self._counts, done=False)

    def _page_size(self) -> int:
        notes = len(self._notes()) + max(0, len(self._counts_lines()) - 1)
        notes += 1 if self._placed is not None and not self.new_count else 0
        return max(MIN_PAGE, self.size.height - PREVIEW_CHROME - notes)

    # ---- the engine ----------------------------------------------------------
    @work(thread=True, exclusive=True, group="engine-write")
    def _ask(self, dry_run: bool) -> None:
        """One `POST /transactions/import` — the dry run, or the apply. Both go
        through flow.py's one call; the client mints the
        idempotency key."""
        from expense import config as config_module
        from expense.http import ExpenseClient

        prepared = self._prepared
        try:
            cfg = config_module.ensure_loaded()
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                response = flow.import_call(client, prepared, dry_run=dry_run)
            placed = placements(response, prepared.sent)
            mismatches = day_mismatches(response, prepared.group.leg_names)
            counts = answer_counts(response)
            names_error = None
            if dry_run:
                # The one read the preview adds: the names of the
                # reconciliations that stop a move to the bank's day.
                names, names_error = reconciliation_names(cfg, placed, verbose=self.app._verbose)
                lines = file_lines(prepared, placed, names)
        except Exception as err:  # every failure is shown, none swallowed
            self.app.call_from_thread(self._failed, err, not dry_run)
            return
        if dry_run:
            self.app.call_from_thread(
                self._previewed, placed, lines, mismatches, counts, names_error
            )
        else:
            self.app.call_from_thread(self._applied, counts)

    def _previewed(
        self,
        placed: list[Placed],
        lines: list[FileLine],
        mismatches: list[DayMismatch],
        counts: AnswerCounts,
        names_error: str | None,
    ) -> None:
        self._placed, self._lines = placed, lines
        self._mismatches, self._counts = mismatches, counts
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
        self.app.switch_screen(ImportResultScreen(self._run, self._owner, self._prepared, counts))

    def _failed(self, err: Exception, applied: bool) -> None:
        self._writing = False
        self._failure = failure_lines(err, self._prepared, applied=applied)
        self._rerun = isinstance(err, EngineError) and changed_while_running(err)
        message = format_error(err)
        if isinstance(err, EngineError) and self._rerun:
            # The screen's own next step, not the one "save again" of other saves.
            _relabel(self, "enter", RERUN_KEY)
            message = f"{engine_words(err)}\n\n{RERUN}"
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
            self._placed, self._lines, self._mismatches, self._counts = None, [], [], None
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
        total = len(self._lines)
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
        if self._placed is None or self._counts is None:
            return []
        return preview_notes(self._prepared, self._mismatches, self._names_error)

    def body(self) -> RenderableType:
        title = Text(f"Preview · {self._prepared.group.name} · ")
        title.append("nothing written yet", style="dim")
        parts: list[RenderableType] = [title, Text("")]
        if self._placed is None or self._counts is None:
            if self._failure:
                parts.extend(hanging(t) for t in self._failure)
            else:
                parts.append(Text(ASKING, style="dim"))
            return Group(*parts)

        lines = self._lines
        size = self._page_size()
        window = lines[self._start : self._start + size]
        parts.append(preview_table(window))
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
# the result — expense-world-import-report.html 3: its title line and the counts
# ---------------------------------------------------------------------------
def result_head(group: AccountGroup, counts: AnswerCounts) -> Text:
    """`✓ 9 rows imported · Sueldo Soles   new ones under @Pendiente and
    #Pendiente` — the engine's `new`."""
    new = counts.new
    head = Text("✓ ", style=PALETTE.success)
    head.append(f"{new} {_plural(new, 'row', 'rows')} imported", style="bold")
    head.append(f" · {group.name}")
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

    def __init__(self, run: ImportRun, owner, prepared: Prepared, counts: AnswerCounts) -> None:
        super().__init__(run, owner)
        self._prepared = prepared
        #: The engine's counts of the apply.
        self._counts = counts

    def on_mount(self) -> None:
        if self._run.has_next:
            _relabel(self, "enter", "Next file")
        super().on_mount()

    def body(self) -> RenderableType:
        return Group(
            result_head(self._prepared.group, self._counts),
            Text(""),
            counts_block(counts_lines(self._prepared, self._counts, done=True)),
        )

    def action_next(self) -> None:
        if self._run.has_next:
            self._next_file()
            return
        self._close(home=True)

    def action_back(self) -> None:
        self._close()
