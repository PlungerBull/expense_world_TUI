"""The import's review — `expense import sheet <file>`, the screen named "Import sheet".

The command sends the sheet's first dry run and, once the engine answers, opens the app
here. Every sheet account the engine has no account for is one row: the sheet's name, its
currencies, its rows and what the review makes of it (`makes_cell`), from the engine's
`suggestion` until the owner sets it. `⏎` opens the New account form on the row
(`SheetAccountScreen`), `a` toggles its archive, and `^s` is held while any row says `?`.

`^s` then sends the dry run carrying `create` (every account with an id made here once and
kept across sends, the categories and hashtags missing) and `names` pointing at those ids
(`engine.review_create`, `engine.review_names`), and asks the engine's count as one
question: only `y` sends the apply with the same body. Nothing is written before it. A
refusal keyed `create.<list>.<i>.<field>` marks the row it names (`create_refusals`); every
other one reads in the engine's words under the table.

The screen ends in `_leave`, the one place the app's way out of the review is decided: the
app closes and the command prints the line.
"""

from contextlib import nullcontext
from dataclasses import dataclass

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.types import NoActiveAppError
from textual.widgets import Static

from expense import reads
from expense.errors import format_error
from expense.formatting import count_phrase, currencies_phrase
from expense.import_.engine import (
    CATEGORY,
    HASHTAG,
    IMPORT_READ_TIMEOUT,
    MadeCounts,
    NameEntry,
    SheetReview,
    Suggestion,
    answer_counts,
    answer_created,
    create_refusals,
    missing_accounts,
    missing_names,
    new_ids,
    send_review,
)
from expense.tui.screens._base import (
    call_while_attached,
    counted_save,
    screen_fetch_kwargs,
)
from expense.tui.screens._form import form_bindings, may_have_landed
from expense.tui.screens.create_forms import Field, NewAccountScreen
from expense.tui.screens.help import HelpBindingMixin
from expense.tui.screens.modals import ConfirmModal
from expense.tui.theme import PALETTE
from expense.tui.widgets.footer import FittingFooter
from expense.tui.widgets.header import Breadcrumb
from expense.tui.widgets.refusal import hanging, toast
from expense.tui.widgets.windowed import CURSOR_STYLE

CRUMB = ("Import sheet",)
#: The width of the Categories and Hashtags labels, so their names line up.
LIST_LABEL = len("Categories")

#: What the app ends with when the owner leaves the review, and after the apply.
NOTHING_IMPORTED = "Nothing was imported."
#: Under every refusal that wrote nothing.
NOTHING_WRITTEN = "Nothing was written."
ASKING = "asking the engine…"
WRITING = "writing…"
#: The least rows the table shows, however short the terminal.
MIN_ROWS = 3
#: Lines the review spends on everything but the table's rows: the breadcrumb (2 with
#: its rule), the body's padding (2), the head, the table's header, the `… more` line, the
#: Categories and Hashtags lines, the count of what is missing and the footer.
CHROME = 11

ARCHIVE_HINT = "yes or no · enter is done"
#: TYPE's hint while the row has no kind: `⏎` picks the highlighted one.
NO_KIND_HINT = "bank, person or cash · enter picks the highlighted one"
#: What `missing_piece` names → the form line that fills it.
ASKED_LINE = {"a kind": "type", "a bank": "bank", "a last 4": "last4"}
YES_NO = [("no", "no"), ("yes", "yes")]


def initial_values(suggestion: Suggestion | None, sheet_name: str) -> dict[str, str]:
    """The lines of the account's form as the engine's guess fills them: the kind, the bank
    code and the last 4 it read; a person's name is the sheet's name. Nothing is guessed that
    the engine did not say."""
    values = {"name": sheet_name, "archive": "no"}
    if suggestion is not None:
        for key, guess in (
            ("type", suggestion.kind),
            ("bank", suggestion.bank_code),
            ("last4", suggestion.last4),
        ):
            if guess:
                values[key] = guess
    return values


def missing_piece(values: dict[str, str]) -> str | None:
    """What the row still asks the owner for, as the count line names it: `a kind`, or, on a
    bank account, `a bank` or `a last 4`; None when the row can be sent."""
    kind = values.get("type")
    if kind is None:
        return "a kind"
    if kind == "bank":
        if not values.get("bank"):
            return "a bank"
        if not values.get("last4"):
            return "a last 4"
    return None


def makes_cell(values: dict[str, str]) -> Text:
    """What the review makes of the row: `bank · BCP · 1234`, `person · ALEJO`, `cash`, and
    each piece it lacks as `? …` in the warning style."""
    warn = PALETTE.warning
    kind = values.get("type")
    if kind is None:
        return Text("? pick a kind", style=warn)
    if kind == "person":
        return Text(f"person · {values.get('name', '')}")
    if kind == "cash":
        return Text("cash")
    cell = Text("bank · ")
    cell.append(values["bank"] if values.get("bank") else Text("? bank", style=warn))
    cell.append(" · ")
    cell.append(values["last4"] if values.get("last4") else Text("? last 4", style=warn))
    return cell


def still_needed(rows: list["AccountRow"]) -> str | None:
    """`5 accounts still need a last 4, 13 a kind.`: how many rows ask for each piece, the
    bank first and the kind last; None when none asks."""
    asked = [row for row in rows if missing_piece(row.values)]
    if not asked:
        return None
    parts = [
        (n, what)
        for what in ("a bank", "a last 4", "a kind")
        if (n := sum(1 for r in asked if missing_piece(r.values) == what))
    ]
    first, what = parts[0]
    need = "needs" if first == 1 else "need"
    line = f"{count_phrase(first, 'account', 'accounts')} still {need} {what}"
    return line + "".join(f", {n:,} {what}" for n, what in parts[1:]) + "."


def made_phrase(counts: MadeCounts) -> str:
    """`18 accounts, 3 categories and 2 hashtags`."""
    return (
        f"{count_phrase(counts.accounts, 'account', 'accounts')}, "
        f"{count_phrase(counts.categories, 'category', 'categories')} and "
        f"{count_phrase(counts.hashtags, 'hashtag', 'hashtags')}"
    )


def ready_question(answer: dict) -> str:
    """The engine's count of the dry run as the one question's first line: what is made,
    the rows imported and, only when there are any, the rows already in the ledger, on a
    closed statement's day and of zero."""
    counts = answer_counts(answer)
    parts = [count_phrase(counts.new, "row", "rows") + " imported"]
    for count, words in (
        (counts.matched, "already in the ledger"),
        (counts.sealed, "on a closed statement's day"),
        (counts.skipped, "of zero skipped"),
    ):
        if count:
            parts.append(f"{count_phrase(count, 'row', 'rows')} {words}")
    done = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    return f"Ready: {made_phrase(answer_created(answer))} made; {done}."


def imported_line(answer: dict) -> str:
    """The line the app ends with after the apply."""
    counts = answer_counts(answer)
    made = made_phrase(answer_created(answer))
    return f"Imported {count_phrase(counts.new, 'row', 'rows')} · {made} made."


@dataclass
class AccountRow:
    """One account to make: the sheet's entry, the lines set for it (the form's keys) and
    the engine's refusal of it, as `(its field, its words)`."""

    entry: NameEntry
    values: dict[str, str]
    refusal: tuple[str | None, str] | None = None


class SheetAccountScreen(NewAccountScreen):
    """The New account form on one row of the review, as Manage ▸ Accounts ▸ New draws it,
    its lines filled from the row. The currencies are the sheet's and read-only, since its rows
    need each one; the account takes no colour or opening balance here (the engine makes the
    opening balance from the sheet and refuses a colour on `create`), and ends with an
    `archive` line. BANK, LAST 4 and the statement code line follow New's rules.

    `^s` writes nothing: it dismisses with the lines as set (`_payload`) for the review to
    keep. `esc` dismisses with None. A refusal the review brought (`refusal`, the engine's
    field and words) opens with the cursor on the line it names and the words shown."""

    BINDINGS = form_bindings("Done")
    FIELDS = [
        *(f for f in NewAccountScreen.FIELDS if f.key != "color"),
        Field("archive", "ARCHIVE", "choice", choices=YES_NO, required=True, hint=ARCHIVE_HINT),
    ]

    def __init__(
        self,
        sheet_name: str,
        currencies: tuple[str, ...],
        values: dict[str, str],
        statement_banks: list[str],
        refusal: tuple[str | None, str] | None = None,
    ) -> None:
        super().__init__(list(currencies), statement_banks)
        self.crumb = (*CRUMB, sheet_name)
        self._values = {**values, "currencies": list(currencies)}
        self._locked = {"currencies"}
        self._refusal = refusal

    def _sequence(self) -> list[str]:
        code = ["statement_code"] if self._takes_code else []
        return ["type", *self._identity_lines(), "currencies", *code, "archive"]

    def _locked_word(self, key: str) -> str:
        return "the sheet's"

    def _first_editable(self) -> int:
        """The form opens on the line the row's `?` names (`missing_piece`), else on the
        first line that can change."""
        line = ASKED_LINE.get(missing_piece(self._values) or "")
        sequence = self._sequence()
        return sequence.index(line) if line in sequence else super()._first_editable()

    def _hint_for(self, key: str) -> str:
        if key == "type" and "type" not in self._values:
            return NO_KIND_HINT  # nothing is kept: the row has no kind yet
        return super()._hint_for(key)

    def _recompute(self, text: str) -> None:
        super()._recompute(text)
        if self._key == "archive" and not text.strip():
            self._suggest_idx = max(0, self._held_index("archive"))  # `⏎` keeps what it holds

    def _after_mount(self) -> None:
        if self._refusal is None:
            return
        field, words = self._refusal
        line = self._line_named(field) if field else None
        if line in self._sequence() and line not in self._locked:
            self._refused_line = line
            self._land_on_refused_line()
        self._show_refusal(words)

    def _payload(self) -> dict:
        """The lines as set; a statement code the form has no line for is dropped."""
        keys = ["type", "bank", "last4", "name", "archive"]
        if self._takes_code:
            keys.append("statement_code")
        return {key: str(self._values[key]) for key in keys if key in self._values}

    def _send_save(self) -> None:
        self.dismiss(self._payload())


class ImportSheetScreen(HelpBindingMixin, Screen):
    """The review: see the module docstring. `esc` leaves with nothing written, except
    while the apply is on its way."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "edit", "Edit"),
        Binding("a", "archive", "Archive"),
        Binding("ctrl+s", "import", "Import"),
        Binding("down", "move(1)", "Move", key_display="↑↓", show=False),
        Binding("up", "move(-1)", "Up", show=False),
        *HelpBindingMixin.BINDINGS,
    ]

    def __init__(self, review: SheetReview) -> None:
        super().__init__()
        self._review = review
        self._ids = new_ids(review.table)
        self._rows = [
            AccountRow(entry, initial_values(entry.suggestion, entry.name))
            for entry in missing_accounts(review.table)
        ]
        self._categories = [e.name for e in missing_names(review.table) if e.kind == CATEGORY]
        self._hashtags = [e.name for e in missing_names(review.table) if e.kind == HASHTAG]
        self._cursor = 0
        self._top = 0
        #: The banks whose statements the engine reads; None until read.
        self._statement_banks: list[str] | None = None
        self._busy = False  # a call is out
        self._applying = False  # the apply is out: nothing leaves
        #: The words under the table: the refusal of a list (`categories`, `hashtags`) and
        #: any other refusal, and whether the engine wrote nothing.
        self._list_refusals: dict[str, list[str]] = {}
        self._other_refusal: str | None = None
        self._refused = False

    # ---- layout ------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Breadcrumb((*CRUMB, self._review.file_name), id="crumb")
        yield Static("", id="import-body")
        yield FittingFooter()

    def on_mount(self) -> None:
        self._repaint()
        self._read_banks()

    def on_resize(self) -> None:
        self._repaint()

    @work(thread=True, exclusive=True)
    def _read_banks(self) -> None:
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            banks = reads.fetch_bank_codes(cfg, **screen_fetch_kwargs(self.app))
        except Exception as exc:  # the form is then without a statement code line
            call_while_attached(self, self._banks_failed, format_error(exc))
            return
        call_while_attached(self, self._banks_read, banks)

    def _banks_read(self, banks: list[str]) -> None:
        self._statement_banks = banks
        self.refresh_bindings()

    def _banks_failed(self, message: str) -> None:
        self._statement_banks = []
        toast(self, message, title="Failed", severity="error")
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("edit", "archive", "move"):
            return (
                bool(self._rows)
                and not self._busy
                and (action != "edit" or self._statement_banks is not None)
            )
        if action == "import":
            return not self._busy
        return True

    # ---- render ------------------------------------------------------------
    def _repaint(self) -> None:
        self.query_one("#import-body", Static).update(self._body())

    def _table(self, room: int) -> tuple[Table, int, int]:
        """The table of the rows that fit, the cursor row in reverse video, and how many rows
        lie above and below it."""
        if self._cursor < self._top:
            self._top = self._cursor
        elif self._cursor >= self._top + room:
            self._top = self._cursor - room + 1
        window = range(self._top, min(len(self._rows), self._top + room))
        table = Table(box=None, pad_edge=False, padding=(0, 3, 0, 0))
        table.add_column("SHEET NAME", no_wrap=True)
        table.add_column("CUR", no_wrap=True)
        table.add_column("ROWS", justify="right", no_wrap=True)
        table.add_column("MAKES", no_wrap=True)
        table.add_column("ARCHIVE", no_wrap=True)
        for i in window:
            row = self._rows[i]
            makes = makes_cell(row.values)
            if row.refusal is not None:
                makes = Text.assemble(("! ", PALETTE.error), makes)
            table.add_row(
                row.entry.name,
                currencies_phrase(row.entry.currencies),
                f"{row.entry.rows:,}",
                makes,
                "archive" if row.values.get("archive") == "yes" else "",
                style=CURSOR_STYLE if i == self._cursor else "",
            )
        return table, self._top, len(self._rows) - window.stop

    def _head(self) -> Text:
        made = MadeCounts(len(self._rows), len(self._categories), len(self._hashtags))
        rows = count_phrase(self._review.rows, "row", "rows")
        return Text(f"{rows} · {made_phrase(made)} to make")

    def _list_line(self, label: str, names: list[str], key: str) -> list[RenderableType]:
        if not names:
            return []
        lines: list[RenderableType] = [Text(f"{label.ljust(LIST_LABEL)}   {' · '.join(names)}")]
        for words in self._list_refusals.get(key, []):
            lines.append(hanging(Text(f"! {words}", style=PALETTE.error)))
        return lines

    def _notes(self) -> list[RenderableType]:
        """Under the lists: what the rows still ask for, then each refusal and that nothing
        was written."""
        notes: list[RenderableType] = []
        if line := still_needed(self._rows):
            notes.append(Text(line, style=PALETTE.warning))
        for row in self._rows:
            if row.refusal is not None:
                words = f"! {row.entry.name}: {row.refusal[1]}"
                notes.append(hanging(Text(words, style=PALETTE.error)))
        if self._other_refusal is not None:
            notes.append(hanging(Text(f"! {self._other_refusal}", style=PALETTE.error)))
        if self._refused:
            notes.append(Text(NOTHING_WRITTEN, style="dim"))
        if self._applying:
            notes.append(Text(WRITING, style="dim"))
        elif self._busy:
            notes.append(Text(ASKING, style="dim"))
        return notes

    def _body(self) -> RenderableType:
        notes = self._notes()
        room = max(MIN_ROWS, self.size.height - CHROME - len(notes))
        parts: list[RenderableType] = [self._head()]
        if self._rows:
            table, above, below = self._table(room)
            parts.append(table)
            if below:
                parts.append(Text(f"… {below} more", style="dim"))
            elif above:
                parts.append(Text(f"… {above} above", style="dim"))
        parts += self._list_line("Categories", self._categories, "categories")
        parts += self._list_line("Hashtags", self._hashtags, "hashtags")
        return Group(*parts, *notes)

    # ---- keys --------------------------------------------------------------
    def action_move(self, delta: int) -> None:
        self._cursor = max(0, min(len(self._rows) - 1, self._cursor + delta))
        self._repaint()

    def action_archive(self) -> None:
        values = self._rows[self._cursor].values
        values["archive"] = "no" if values.get("archive") == "yes" else "yes"
        self._repaint()

    def action_edit(self) -> None:
        row = self._rows[self._cursor]
        form = SheetAccountScreen(
            row.entry.name,
            row.entry.currencies,
            row.values,
            self._statement_banks or [],
            row.refusal,
        )
        self.app.push_screen(form, self._set)

    def _set(self, values: dict[str, str] | None) -> None:
        """The form's answer: the row holds the lines as set and its refusal is gone;
        `esc` returns None and leaves the row as it was."""
        if values is None:
            return
        row = self._rows[self._cursor]
        row.values = values
        row.refusal = None
        self._repaint()

    def action_cancel(self) -> None:
        if self._applying:
            self.notify("Writing — one moment.")
            return
        self._leave(NOTHING_IMPORTED)

    def _leave(self, line: str) -> None:
        """The one way out of the review, after the import and on `esc`: the app closes and
        the command prints `line`."""
        self.app.exit(line)

    # ---- the engine --------------------------------------------------------
    def action_import(self) -> None:
        """`^s`: held while any row says `?`; else the dry run, then the question."""
        if self._busy:
            return
        if line := still_needed(self._rows):
            toast(self, line, severity="error")
            return
        self._clear_refusals()
        self._busy = True
        self.refresh_bindings()
        self._repaint()
        self._ask(dry_run=True)

    def _clear_refusals(self) -> None:
        for row in self._rows:
            row.refusal = None
        self._list_refusals = {}
        self._other_refusal = None
        self._refused = False

    @work(thread=True, exclusive=True, group="engine-write")
    def _ask(self, dry_run: bool) -> None:
        """The apply is one save while it runs, its hand-back included (`counted_save`);
        the dry run writes nothing."""
        try:
            save = nullcontext() if dry_run else counted_save(self.app)
        except NoActiveAppError:  # a screen that has left cannot name its app
            return
        with save:
            self._call(dry_run)

    def _call(self, dry_run: bool) -> None:
        from expense import config as config_module
        from expense.http import ExpenseClient

        accounts = {row.entry.name: row.values for row in self._rows}
        try:
            cfg = config_module.ensure_loaded()
            with ExpenseClient(
                cfg, timeout_read=IMPORT_READ_TIMEOUT, **screen_fetch_kwargs(self.app)
            ) as client:
                answer = send_review(
                    client,
                    self._review.data,
                    self._review.table,
                    self._ids,
                    accounts,
                    dry_run=dry_run,
                )
        except Exception as err:  # every failure is shown, none swallowed
            call_while_attached(self, self._failed, err, dry_run)
            return
        call_while_attached(self, self._answered if dry_run else self._applied, answer)

    def _answered(self, answer: dict) -> None:
        """The dry run's count, asked as one question; only `y` sends the apply."""
        self._busy = False
        self.refresh_bindings()
        self._repaint()
        question = ConfirmModal(ready_question(answer), "Import? Only y imports.")
        self.app.push_screen(question, self._confirmed)

    def _confirmed(self, ok: bool | None) -> None:
        if not ok:
            return
        self._busy = self._applying = True
        self.refresh_bindings()
        self._repaint()
        self._ask(dry_run=False)

    def _applied(self, answer: dict) -> None:
        self._busy = self._applying = False
        self._leave(imported_line(answer))

    def _failed(self, err: Exception, dry_run: bool) -> None:
        """A refusal or any other failure, back on the review: a `create` refusal marks the
        row or list it names, any other reads in the engine's words under the table."""
        self._busy = self._applying = False
        self._clear_refusals()
        self._refused = dry_run or not may_have_landed(err)
        refusals = create_refusals(err)
        if not refusals:
            self._other_refusal = format_error(err)
        marked: list[int] = []
        for refusal in refusals:
            if refusal.listed == "accounts" and refusal.place < len(self._rows):
                row = self._rows[refusal.place]
                if row.refusal is None:
                    row.refusal = (refusal.field, refusal.words)
                    marked.append(refusal.place)
            elif refusal.listed in ("categories", "hashtags"):
                self._list_refusals.setdefault(refusal.listed, []).append(refusal.words)
        if marked:
            self._cursor = min(marked)
        self.refresh_bindings()
        self._repaint()
