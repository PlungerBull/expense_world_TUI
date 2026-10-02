"""The import door — a dropped bank file → its account → the preview → the result.

The LOG bar recognises a line of bank files (`expense/tui/dropped.py`) and hands
the paths to `LogBarScreen.import_bank_files`, which reads every file at once
(`read_dropped`). A file that is not a BCP export never leaves the bar: the
hint says what is missing (mockup screen 5 A). Otherwise the files go, one after
the other in drop order, through three full screens:

    ImportAccountScreen   which account is this file? — asked every time
    ImportPreviewScreen   the engine's dry run, nothing written yet
    ImportResultScreen    what the apply wrote, and the days to check

Every step is the typed `expense import bank`'s own code
(expense/commands/bank_import_cmd.py): the same read, the same account
folding, the same `Prepared` rows, the same one `POST /transactions/import`
(contract: POST /v1/transactions/import) and the same verdicts. What is here is
only what the screens draw, from docs/mockups/expense-world-import-door.html.

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

from expense.bank_import.engine import (
    ExcessGroup,
    IncompleteAnswer,
    Placed,
    excess_groups,
    match_label,
    placements,
    row_refusals,
)
from expense.bank_import.parse import BadRow, BankFormatError, BankRow
from expense.commands import accounts_cmd, bank_import_cmd
from expense.commands._resource import format_cents, items_of
from expense.commands.bank_import_cmd import (
    IMPORT_FLOOR,
    AccountGroup,
    ImportRefused,
    Prepared,
    account_groups,
    excess_head,
    import_counts,
    incomplete_sentence,
    period_names,
    prepared_for,
    read_bank_file,
    sealed_lines,
)
from expense.errors import EngineError, format_error
from expense.tui.screens._base import screen_fetch_kwargs
from expense.tui.theme import AMOUNT_RULE, PALETTE
from expense.tui.widgets.cells import amount_cell
from expense.tui.widgets.header import Breadcrumb
from expense.tui.widgets.windowed import CURSOR_STYLE

#: The breadcrumb's trail before the file part.
CRUMB = ("Capture & ledger", "Import")

#: Where the new rows land — the category an import never sets.
PENDING = "@Pendiente"

LOADING_ACCOUNTS = "loading accounts…"
NO_ACCOUNTS = "no accounts exist yet — create one in Manage › Accounts first."
ASKING = "asking the engine what the ledger already holds…"
WRITING = "writing…"
NOTHING_NEW = "nothing to import"

#: Lines the preview spends on everything but its rows: the breadcrumb (4 with
#: its padding and rule), the body's padding (2), the title and the blank under
#: it, the table's header, the `… more` line, the blank and the summary under
#: the table, and the footer. The notes under the summary are counted per
#: screen.
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
            body = accounts_cmd.fetch_accounts(
                cfg, include_people=False, **screen_fetch_kwargs(self.app)
            )
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
        self.notify(message, title="Failed", severity="error")
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
# screen 3 (and 6 A) — the preview
# ---------------------------------------------------------------------------
def match_cell(p: Placed, names: dict[str, str]) -> Text:
    """The typed import's verdict; a new row stands out, the rest stay dim."""
    label = match_label(p, names)
    return Text(label, style=PALETTE.success if p.outcome == "new" else "dim")


def preview_table(placed: list[Placed], names: dict[str, str]) -> Table:
    """`#  date  title  amount  match`, numbered by the file's own line."""
    table = Table(box=None, pad_edge=False, expand=False, show_header=True)
    for header in ("#", "date", "title", "amount", "match"):
        table.add_column(
            Text(header, style="dim"),
            justify="right" if header in ("#", "amount") else "left",
            no_wrap=True,
            overflow="ellipsis",
        )
    for p in placed:
        row = p.sent.row
        table.add_row(
            str(row.line),
            row.date_iso,
            row.title,
            amount_cell(row.amount_cents, PALETTE, AMOUNT_RULE),
            match_cell(p, names),
        )
    return table


def preview_summary(prepared: Prepared, placed: list[Placed]) -> Text:
    """`14 rows · 9 new · 5 in the ledger`, then the closed, pre-floor and
    refused counts when there are any."""
    counts = import_counts(prepared, placed)
    line = Text(f"{counts.total} {_plural(counts.total, 'row', 'rows')} · ")
    line.append(f"{counts.new} new", style=PALETTE.success if counts.new else "")
    line.append(f" · {counts.matched} in the ledger")
    if counts.sealed:
        line.append(f" · {counts.sealed} in a closed period")
    if counts.before_floor:
        line.append(f" · {counts.before_floor} before {IMPORT_FLOOR.year}")
    if counts.refused:
        line.append(f" · {counts.refused} refused")
    return line


def preview_excess_lines(excess: list[ExcessGroup]) -> list[Text]:
    """The typed preview's warning, one line per day and amount under it:
    `2026-09-10 · -28.00 · 1 unmatched`."""
    if not excess:
        return []
    lines = [Text(excess_head(excess), style=PALETTE.warning)]
    for e in excess:
        lines.append(
            Text(
                f"    {e.date_iso} · {format_cents(e.amount_cents)} · {e.unclaimed} unmatched",
                style=PALETTE.warning,
            )
        )
    return lines


def preview_notes(
    prepared: Prepared,
    placed: list[Placed],
    excess: list[ExcessGroup],
    names: dict[str, str],
    names_error: str | None,
) -> list[Text]:
    """Everything under the summary: the unmatched ledger rows, the closed
    period's rows, the rows under the floor, the refused lines — the typed
    preview's own sentences."""
    lines = preview_excess_lines(excess)
    lines.extend(Text(line, style=PALETTE.warning) for line in sealed_lines(placed, names))
    if names_error:
        lines.append(
            Text(f"! could not read the closed periods' names: {names_error}", style="dim")
        )
    if prepared.before_floor:
        n = len(prepared.before_floor)
        lines.append(
            Text(
                f"{n} {_plural(n, 'row', 'rows')} dated before {IMPORT_FLOOR} not sent — "
                "imports start there.",
                style="dim",
            )
        )
    lines.extend(Text(f"! row {b.line}: {b.reason}", style=PALETTE.error) for b in prepared.bad)
    return lines


def failure_lines(err: Exception, prepared: Prepared, *, applied: bool) -> list[Text]:
    """An engine refusal or a short answer, as the screen shows it.

    A `422` names each refused row by the file's line, like the typed import;
    anything else is the app's own error text.
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
    if isinstance(err, EngineError) and err.status == 422:
        lines = [Text(f"{err.code} — {err.message}", style=PALETTE.error)]
        for line, field, message in row_refusals(err.fields, prepared.sent):
            where = f"row {line} ({field})" if line is not None else field
            lines.append(Text(f"! {where}: {message}", style=PALETTE.error))
        lines.append(Text("Nothing was written.", style="dim"))
        return lines
    return [Text(format_error(err), style=PALETTE.error)]


class ImportPreviewScreen(_ImportScreen):
    """The engine's dry run of this file on this account. Nothing is written
    until `⏎`. With nothing new (screen 6 A), `⏎` opens the next file's
    account list when a file follows, and does nothing on the last one."""

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
        self._excess: list[ExcessGroup] = []
        self._names: dict[str, str] = {}
        self._names_error: str | None = None
        self._failure: list[Text] = []
        self._writing = False
        self._start = 0

    def on_mount(self) -> None:
        _relabel(self, "escape", self._run.cancel_label())
        super().on_mount()
        self._ask(dry_run=True)

    # ---- state ---------------------------------------------------------------
    @property
    def new_count(self) -> int:
        return sum(1 for p in self._placed or [] if p.outcome == "new")

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

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "apply":
            return self.can_apply or self.can_skip
        if action == "page":
            delta = parameters[0] if parameters else 1
            if delta == 1:
                return self._start + self._page_size() < len(self._placed or [])
            return self._start > 0
        return True

    def _page_size(self) -> int:
        notes = len(self._notes()) + (1 if self._placed is not None and not self.new_count else 0)
        return max(MIN_PAGE, self.size.height - PREVIEW_CHROME - notes)

    # ---- the engine ----------------------------------------------------------
    @work(thread=True, exclusive=True, group="engine-write")
    def _ask(self, dry_run: bool) -> None:
        """One `POST /transactions/import` — the dry run, or the apply. Both go
        through the typed command's own call; the client mints the
        idempotency key."""
        from expense import config as config_module
        from expense.http import ExpenseClient

        prepared = self._prepared
        try:
            cfg = config_module.ensure_loaded()
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                response = bank_import_cmd.import_call(client, prepared, dry_run=dry_run)
            placed = placements(response, prepared.sent)
            excess = excess_groups(response, prepared.group.leg_names)
            names: dict[str, str] = {}
            names_error = None
            if dry_run:
                names, names_error = period_names(cfg, placed, verbose=self.app._verbose)
        except Exception as err:  # every failure is shown, none swallowed
            self.app.call_from_thread(self._failed, err, not dry_run)
            return
        if dry_run:
            self.app.call_from_thread(self._previewed, placed, excess, names, names_error)
        else:
            self.app.call_from_thread(self._applied, placed, excess)

    def _previewed(
        self,
        placed: list[Placed],
        excess: list[ExcessGroup],
        names: dict[str, str],
        names_error: str | None,
    ) -> None:
        self._placed, self._excess = placed, excess
        self._names, self._names_error = names, names_error
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

    def _applied(self, placed: list[Placed], excess: list[ExcessGroup]) -> None:
        self._writing = False
        self._run.imported += 1
        self.app.switch_screen(
            ImportResultScreen(self._run, self._owner, self._prepared.group, placed, excess)
        )

    def _failed(self, err: Exception, applied: bool) -> None:
        self._writing = False
        self._failure = failure_lines(err, self._prepared, applied=applied)
        self.notify(format_error(err), title="Failed", severity="error")
        self.refresh_bindings()
        self._repaint()

    # ---- keys ----------------------------------------------------------------
    def action_apply(self) -> None:
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
        total = len(self._placed or [])
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
        if self._placed is None:
            return []
        return preview_notes(
            self._prepared, self._placed, self._excess, self._names, self._names_error
        )

    def body(self) -> RenderableType:
        title = Text(f"Preview · {self._prepared.group.name} · ")
        title.append("nothing written yet", style="dim")
        parts: list[RenderableType] = [title, Text("")]
        if self._placed is None:
            if self._failure:
                parts.extend(hanging(t) for t in self._failure)
            else:
                parts.append(Text(ASKING, style="dim"))
            return Group(*parts)

        placed = self._placed
        size = self._page_size()
        window = placed[self._start : self._start + size]
        parts.append(preview_table(window, self._names))
        after = len(placed) - (self._start + len(window))
        if after > 0:
            parts.append(Text(f"… {after} more · pgdn", style="dim"))
        elif self._start > 0:
            parts.append(Text(f"… {self._start} above · pgup", style="dim"))
        parts.append(Text(""))
        parts.append(preview_summary(self._prepared, placed))
        parts.extend(hanging(t) for t in self._notes())
        if not self.new_count:
            parts.append(Text(NOTHING_NEW, style="dim"))
        if self._writing:
            parts.extend([Text(""), Text(WRITING, style="dim")])
        if self._failure:
            parts.append(Text(""))
            parts.extend(hanging(t) for t in self._failure)
        return Group(*parts)


def hanging(line: Text) -> RenderableType:
    """A `! …` line wraps under its own words, not under the `!` (mockup
    screen 4 B); any other line is itself."""
    if not line.plain.startswith("! "):
        return line
    grid = Table.grid()
    grid.add_column(no_wrap=True)
    grid.add_column()
    grid.add_row(line[:2], line[2:])
    return grid


# ---------------------------------------------------------------------------
# screen 4 B — the result
# ---------------------------------------------------------------------------
def result_lines(
    group: AccountGroup, placed: list[Placed], excess: list[ExcessGroup]
) -> list[Text]:
    """`✓ 9 rows imported · Sueldo Soles`, `under @Pendiente`, and the days
    where the ledger may now hold one movement twice (screen 4 B).

    The engine computes `excess` before it writes
    (contract: POST /v1/transactions/import), so on such a day a row the apply
    just wrote as `new` may be the same movement the ledger already had under
    another wording — hence "may now hold".
    """
    new = sum(1 for p in placed if p.outcome == "new")
    head = Text(f"✓ {new} {_plural(new, 'row', 'rows')} imported", style=PALETTE.success)
    head.append(f" · {group.name}", style="")
    lines = [head, Text(f"  under {PENDING}", style="dim")]
    if excess:
        days = len({e.date_iso for e in excess})
        lines.append(Text(""))
        lines.append(
            Text(
                f"! {days} {_plural(days, 'day', 'days')} where the ledger may now hold the "
                f"same movement twice — check {_plural(days, 'it', 'them')} and delete the "
                f"extra {_plural(days, 'one', 'ones')}",
                style=PALETTE.warning,
            )
        )
        lines.extend(
            Text(f"    {e.date_iso} · {format_cents(e.amount_cents)}", style=PALETTE.warning)
            for e in excess
        )
    return lines


class ImportResultScreen(_ImportScreen):
    """What the apply wrote. `⏎` opens the next file's account list, or goes
    Home after the last; `esc` returns to the LOG bar."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("enter", "next", "Home"),
    ]

    def __init__(
        self,
        run: ImportRun,
        owner,
        group: AccountGroup,
        placed: list[Placed],
        excess: list[ExcessGroup],
    ) -> None:
        super().__init__(run, owner)
        self._group = group
        self._placed = placed
        self._excess = excess

    def on_mount(self) -> None:
        if self._run.has_next:
            _relabel(self, "enter", "Next file")
        super().on_mount()

    def body(self) -> RenderableType:
        return Group(*(hanging(t) for t in result_lines(self._group, self._placed, self._excess)))

    def action_next(self) -> None:
        if self._run.has_next:
            self._next_file()
            return
        self._close(home=True)

    def action_back(self) -> None:
        self._close()
