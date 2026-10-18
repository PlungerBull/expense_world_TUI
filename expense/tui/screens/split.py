"""The split screen — one transaction into parts, `s` on a ledger row.

Screens 1 to 3 of docs/mockups/expense-world-split-screen.html. A full pushed
screen, not a modal. On top, the line every part keeps: the date, the account
and the line's signed total; under it the TITLE line, the transaction's title,
shown and not yet editable. Then the table of the parts (amount, category,
hashtags, note), `+ add a part`, and the line adding the parts up against the
total. `↑↓` move the cursor through the parts and `+ add a part`.

**The fields below.** `⏎` on a part opens its fields under the table, one per
line: AMOUNT, CATEGORY, HASHTAGS, NOTE, the part marked in the table. They are
the bar form's (`FormScreen` in _form.py): one input on the field the cursor
is on, `↑↓`, `⏎` or `⇥` move between fields, and on CATEGORY and HASHTAGS the
suggestion list (`picker.py`) shows as you type, `↑↓` moving in it while it is
open. A field is kept when you leave it, whichever key leaves it, and shows in
the table at once; `⏎` on NOTE goes back to the table, cursor on the part, and
`esc` goes back keeping every field already left, only the one being typed
going back to what it was. `⏎` on `+ add a part` adds an empty part and opens
it on AMOUNT. A part left with nothing in it drops again.

**Re-split.** The screen opens a transaction with one `GET /bank-lines/{id}`
read: on a part of a split transaction the table opens with the line's
`parts`, and the total is the line's `net_cents`
(contract: GET /v1/bank-lines/{bank_line_id}); a line never split has one
part, its transaction, so the table opens empty.

**The only arithmetic is "left"**: the parts' amounts summed against the
engine's total. It never stops a send: `ctrl+s` always sends every part in one
`POST /transactions/{id}/split`, each part under a fresh id, and the engine
decides whether the parts add up
(contract: POST /v1/transactions/{transaction_id}/split, "The total is kept").

**A refusal stays under the parts** until a part changes: the engine's words,
each `parts.<i>.<field>` key read as `part i+1 (field)`, the amounts a
`parts.<i>.amount_cents` key names in the error colour, `Nothing was split.`,
and the app's line for the refusal's reason, if it has one (`app_lines`).
"""

from dataclasses import dataclass, replace
from uuid import uuid4

from rich.console import Group, RenderableType
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Input, Label, Static

from expense import reads
from expense.errors import EngineError, app_lines, format_error, key_index
from expense.formatting import (
    bank_line_part_count,
    format_cents,
    format_short_date,
    resolve_name,
    signed_cents,
    whole_number,
)
from expense.quickadd.money import amount_to_text, parse_amount
from expense.reads import QuickAddRefs, currency_of, hashtags_to_send
from expense.tui.screens._base import call_while_attached, screen_fetch_kwargs
from expense.tui.screens._form import FormScreen, form_bindings
from expense.tui.screens.log_bar import LOADING_HINT
from expense.tui.theme import ACCENT, AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell
from expense.tui.widgets.header import Breadcrumb
from expense.tui.widgets.picker import matching, suggestion_list
from expense.tui.widgets.refusal import hanging
from expense.tui.widgets.windowed import CURSOR_STYLE

HEAD_NOTE = "every part keeps this date and account"
TITLE_NOTE = "same on every part"
ADD_PART = "add a part"
NOTHING_SPLIT = "Nothing was split."
#: A cell with nothing in it, as drawn.
EMPTY = "—"

#: The part's fields, in the order the cursor moves through them.
FIELDS = ("amount", "category", "hashtags", "note")
LABELS = {"amount": "AMOUNT", "category": "CATEGORY", "hashtags": "HASHTAGS", "note": "NOTE"}
#: The fields that show the suggestion list as you type.
PICKED = frozenset({"category", "hashtags"})

#: What a refused key's field reads as after `part N`.
FIELD_WORDS = {"amount_cents": "amount"}

#: Columns of the table, as drawn: the marker and number, then each cell at
#: least as wide as its header leaves room for, and the gap after each.
HEADERS = ("amount", "category", "hashtags", "note")
MIN_WIDTHS = (7, 11, 12, 0)
MARKER_GAP = "  "
GAP = "    "
#: The label column of the fields below: `▌ ` and the label, padded.
LABEL_WIDTH = 10
#: The rule over the fields below.
RULE_WIDTH = 78


@dataclass(frozen=True)
class Part:
    """One part in the table. `amount_cents` None until one is typed;
    `category_id` None files the part under `@Pendiente`; `hashtag_ids` as
    picked or as the engine holds them, the pending hashtag among them."""

    amount_cents: int | None = None
    category_id: str | None = None
    hashtag_ids: tuple[str, ...] = ()
    note: str | None = None

    @property
    def empty(self) -> bool:
        """Nothing typed in it: it drops when its fields close."""
        return self == Part()


def part_from_engine(item: dict, refs: QuickAddRefs) -> Part:
    """A part the engine holds, as `GET /bank-lines/{id}` lists it: a
    magnitude and its `transaction_type`, signed by `signed_cents`. The
    `@Pendiente` category is what a part naming none means, so it reads as
    none."""
    pending_category = refs.pending[0] if refs.pending else None
    category = item.get("category_id")
    return Part(
        amount_cents=signed_cents(item),
        category_id=None if category == pending_category else category,
        hashtag_ids=tuple(str(t) for t in item.get("hashtag_ids") or ()),
        note=item.get("description") or None,
    )


def real_hashtags(part: Part, refs: QuickAddRefs | None) -> list[str]:
    """The part's hashtags the split sends: never the pending one, alone or
    not, so a part with no real hashtag sends none and the engine files it
    under the pending hashtag (contract: POST /v1/transactions/{transaction_id}/split)."""
    pending = refs.pending_hashtag_id if refs else None
    return hashtags_to_send(part.hashtag_ids, pending, pending_alone=False)


def part_payload(part: Part, refs: QuickAddRefs | None, *, part_id: str) -> dict:
    """One entry of the split's `parts`: a fresh id and only what the part
    holds — its signed amount, `category_id`, `hashtag_ids` and
    `description`. Sparse by omission, as every create."""
    body: dict = {"id": part_id}
    if part.amount_cents is not None:
        body["amount_cents"] = part.amount_cents
    if part.category_id is not None:
        body["category_id"] = part.category_id
    tags = real_hashtags(part, refs)
    if tags:
        body["hashtag_ids"] = tags
    if part.note:
        body["description"] = part.note
    return body


def split_body(parts: list[Part], refs: QuickAddRefs | None) -> dict:
    """`POST /transactions/{id}/split`'s body: every part, in table order,
    each under a fresh id."""
    return {"parts": [part_payload(p, refs, part_id=str(uuid4())) for p in parts]}


# ---------------------------------------------------------------------------
# pure builders — no app, no event loop
# ---------------------------------------------------------------------------
def _figure(cents: object, palette: Palette | None) -> Text:
    figure = amount_cell(cents, palette, AMOUNT_RULE)
    return figure if isinstance(figure, Text) else Text(str(figure))


def head_line(
    record: dict, total: int | None, refs: QuickAddRefs | None, *, palette: Palette | None = None
) -> Text:
    """`2026-10-11  ·  Sueldo Soles  ·  -100.00 PEN  ·  every part keeps this
    date and account`."""
    names = refs.account_names if refs else {}
    head = Text(format_short_date(record.get("date")), style="dim")
    head.append(f"  ·  {resolve_name(record.get('account_id'), names)}  ·  ", style="dim")
    if total is not None:
        head.append_text(_figure(total, palette))
    currency = currency_of(refs, record.get("account_id")) if refs else ""
    if currency:
        head.append(f" {currency}", style="dim")
    head.append(f"  ·  {HEAD_NOTE}", style="dim")
    return head


def title_line(record: dict) -> Text:
    """`TITLE      Tottus Jockey Plaza          same on every part`."""
    title = record.get("title") or EMPTY
    line = Text("TITLE".ljust(11), style="dim")
    line.append(title.ljust(43) + "  ")
    line.append(TITLE_NOTE, style="dim")
    return line


def _category_cell(part: Part, refs: QuickAddRefs) -> str:
    return resolve_name(part.category_id, refs.category_names) if part.category_id else ""


def _hashtags_cell(part: Part, refs: QuickAddRefs) -> str:
    return " ".join("#" + resolve_name(t, refs.hashtag_names) for t in real_hashtags(part, refs))


def part_cells(part: Part, refs: QuickAddRefs) -> tuple[str, str, str, str]:
    """A part's four cells as words: amount, category, hashtags, note. A part
    with no amount, category or real hashtag reads `—` there; no note reads
    blank."""
    amount = format_cents(part.amount_cents) if part.amount_cents is not None else EMPTY
    return (
        amount,
        _category_cell(part, refs) or EMPTY,
        _hashtags_cell(part, refs) or EMPTY,
        part.note or "",
    )


def parts_lines(
    parts: list[Part],
    refs: QuickAddRefs,
    *,
    cursor: int | None = None,
    editing: int | None = None,
    flagged: frozenset[int] = frozenset(),
    palette: Palette | None = None,
) -> list[Text]:
    """The table: its header, one line per part, then `+  add a part`.

    The line under `cursor` (a part, or `len(parts)` for `+ add a part`) is in
    the cursor style; the part being edited reads `▌ 2 …` in the accent, bold.
    An amount reads in its sign's colour, and in the error colour when the
    refusal names it (`flagged`)."""
    cells = [part_cells(p, refs) for p in parts]
    widths = [
        max([minimum, len(header), *(len(row[i]) for row in cells)])
        for i, (minimum, header) in enumerate(zip(MIN_WIDTHS, HEADERS, strict=True))
    ]
    width = 3 + len(MARKER_GAP) + sum(widths[:3]) + 3 * len(GAP) + widths[3]

    def row(marker: str, row_cells: tuple[str, ...], amount: Text | None = None) -> Text:
        line = Text(marker + MARKER_GAP)
        if amount is None:
            line.append(row_cells[0].rjust(widths[0]))
        else:
            line.append(" " * (widths[0] - len(amount.plain)))
            line.append_text(amount)
        for i in (1, 2):
            line.append(GAP + row_cells[i].ljust(widths[i]))
        line.append(GAP + row_cells[3])
        return line

    lines = [row("   ", HEADERS)]
    lines[0].stylize("dim")
    for index, (part, row_cells) in enumerate(zip(parts, cells, strict=True)):
        number = str(index + 1).rjust(2)
        if index == editing:
            line = row("▌" + number, row_cells)
            line.stylize(f"bold {ACCENT}" if palette else "bold")
        else:
            if part.amount_cents is None:
                amount = Text(EMPTY)
            elif index in flagged:
                amount = Text(row_cells[0], style=palette.error if palette else "")
            else:
                amount = _figure(part.amount_cents, palette)
            line = row(" " + number, row_cells, amount)
            if index == cursor:
                line.pad_right(width - len(line.plain))
                line.stylize(CURSOR_STYLE)
        lines.append(line)
    add = Text(f"  +  {ADD_PART}", style="dim")
    if cursor == len(parts):
        add.pad_right(width - len(add.plain))
        add.stylize(CURSOR_STYLE)
    lines.append(add)
    for line in lines:
        line.no_wrap = True
        line.overflow = "crop"
    return lines


def count_line(parts: list[Part], total: int | None, *, palette: Palette | None = None) -> Text:
    """`2 parts  ·  -100.00 of -100.00  ✓`, or `…  ·  -10.00 left` in the error
    colour while the parts do not reach the total. The parts' amounts summed
    against the engine's total; a part with no amount adds nothing."""
    placed = sum(p.amount_cents for p in parts if p.amount_cents is not None)
    line = Text(f"{len(parts)} {'part' if len(parts) == 1 else 'parts'}  ·  ")
    line.append_text(_figure(placed, palette))
    if total is None:
        return line
    line.append(" of ")
    line.append_text(_figure(total, palette))
    left = total - placed
    if left:
        line.append("  ·  ")
        line.append(f"{format_cents(left)} left", style=palette.error if palette else "")
    else:
        line.append("  ✓", style=palette.success if palette else "")
    return line


def field_value(key: str, part: Part, refs: QuickAddRefs) -> str:
    """What a field below holds, as its line shows it when the cursor is not
    on it: the amount, the category's name, the real hashtags, the note."""
    if key == "amount":
        return format_cents(part.amount_cents) if part.amount_cents is not None else ""
    if key == "category":
        return _category_cell(part, refs)
    if key == "hashtags":
        return _hashtags_cell(part, refs)
    return part.note or ""


def field_line(key: str, part: Part, refs: QuickAddRefs) -> Text:
    """`  AMOUNT    -40.00`: a field the cursor is not on."""
    line = Text("  ")
    line.append(LABELS[key].ljust(LABEL_WIDTH), style="dim")
    line.append(field_value(key, part, refs))
    return line


def field_label(key: str) -> Text:
    """`▌ CATEGORY  `: the label of the field the cursor is on, its input after it."""
    return Text.assemble(("▌", ACCENT), " ", (LABELS[key].ljust(LABEL_WIDTH), f"bold {ACCENT}"))


def part_key(key: object) -> str:
    """A refusal's key as the screen names it: `parts.1.amount_cents` reads
    `part 2 (amount)`, `parts.0` reads `part 1`; any other key as sent."""
    index = key_index(key, "parts")
    if index is None:
        return str(key)
    bits = str(key).split(".", 2)
    if len(bits) == 3:
        return f"part {index + 1} ({FIELD_WORDS.get(bits[2], bits[2])})"
    return f"part {index + 1}"


def flagged_parts(err: Exception | None) -> frozenset[int]:
    """The parts whose amount a refusal names (`parts.<i>.amount_cents`)."""
    if not isinstance(err, EngineError) or not isinstance(err.fields, dict):
        return frozenset()
    return frozenset(
        i
        for key in err.fields
        if (i := key_index(key, "parts")) is not None and str(key).endswith(".amount_cents")
    )


def refusal_lines(err: Exception, *, palette: Palette | None = None) -> list[RenderableType]:
    """The refusal kept under the parts: `CODE — message`, a `! <key>: <words>`
    line per refused key, `Nothing was split.`, then the app's line for the
    reason, if any — chosen by the engine's code and reasons (`app_lines`),
    never its words. A failure that is not the engine's answer reads as
    `format_error` says it."""
    error = palette.error if palette else ""
    if not isinstance(err, EngineError):
        return [Text(format_error(err), style=error)]
    lines: list[RenderableType] = [Text(f"{err.code} — {err.message}", style=error)]
    for key, message in (err.fields or {}).items():
        lines.append(hanging(Text(f"! {part_key(key)}: {message}", style=error)))
    if err.status < 500:
        lines.append(Text(NOTHING_SPLIT, style="dim"))
    for line in app_lines(err):
        lines.append(Text(""))
        lines.append(Text(line))
    return lines


# ---------------------------------------------------------------------------
# the screen
# ---------------------------------------------------------------------------
def _bindings() -> list[Binding | tuple[str, str, str]]:
    """The bar form's keymap with the table's keys. `esc` is two bindings,
    `check_action` showing one: `Cancel` on the table, `Back to the parts` in
    the fields. `⏎ Edit` and `^x Drop part` are the table's, `⇥ Field` the
    fields'."""
    form = [b for b in form_bindings("Split") if not (isinstance(b, tuple) and b[0] == "escape")]
    return [
        Binding("escape", "cancel", "Cancel"),
        Binding("escape", "back", "Back to the parts"),
        *form,
        Binding("enter", "edit", "Edit", key_display="⏎"),
        Binding("ctrl+x", "drop_part", "Drop part"),
    ]


class SplitScreen(FormScreen):
    """Splits the bank line holding `record` into the parts in its table.

    Dismisses with True once the engine split it, so the ledger reads fresh;
    with False on `esc`. On the table nothing is focused, so `⏎`, `↑↓` and
    `^x` are the screen's; in the fields below, the input holds focus."""

    BINDINGS = _bindings()

    def __init__(self, record: dict, crumb: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._record = record
        self.crumb = (*crumb, "Split")
        self._refs: QuickAddRefs | None = None
        self._total: int | None = None
        self._parts: list[Part] = []
        self._cursor = 0  # a part, or len(parts) for `+ add a part`
        self._editing: int | None = None  # the part whose fields are open
        self._refusal: Exception | None = None  # the engine's, until a part changes
        self._sending = False

    # ---- layout ------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb, id="crumb")
        yield Static("", id="split-head")
        yield Static("", id="split-title")
        yield Static("", id="parts")
        with Vertical(id="part-fields"):
            yield Static("", id="part-head")
            yield Static("", id="fields-above")
            with Horizontal(id="part-inputbar"):
                yield Label("", id="part-field")
                # off while the fields are closed, so nothing is focused on the table
                yield Input(id="bar", compact=True, disabled=True)
            yield Static("", id="part-suggest")
            yield Static("", id="fields-below")
        yield Footer()

    def _after_mount(self) -> None:
        self._load()

    @work(thread=True, exclusive=True)
    def _load(self) -> None:
        """The reference lists, then — on a row that names its bank line — the
        line, its parts and its total, in one `GET /bank-lines/{id}`. A row
        with no bank line opens as a transaction never split, at its own
        amount."""
        from expense import config as config_module

        line_id = self._record.get("bank_line_id")
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            refs = reads.load_quickadd_refs(cfg, **kw)
            if line_id:
                line = reads.fetch_bank_line(cfg, str(line_id), **kw)
            else:
                line = {"net_cents": self._record.get("amount_cents"), "parts": []}
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            call_while_attached(self, self.notify, format_error(exc), severity="error")
            return
        call_while_attached(self, self._loaded, refs, line)

    def _loaded(self, refs: QuickAddRefs, line: dict) -> None:
        self._refs = refs
        self._total = whole_number(line.get("net_cents"))
        if bank_line_part_count(line) > 1:
            self._parts = [part_from_engine(item, refs) for item in line.get("parts") or []]
        self._cursor = 0
        self._refresh_view()

    # ---- FormScreen hooks --------------------------------------------------
    def _sequence(self) -> list[str]:
        return list(FIELDS)

    def _label(self, key: str) -> str:
        return LABELS[key]

    def _suggests(self, key: str) -> bool:
        return key in PICKED

    def _bar_value(self, key: str) -> str:
        """Amount and note open on what the part holds; category and hashtags
        open empty and are picked afresh, as on the Edit form."""
        part = self._part
        if key == "amount" and part.amount_cents is not None:
            return amount_to_text(part.amount_cents)
        if key == "note":
            return part.note or ""
        return ""

    def _recompute(self, text: str) -> None:
        """The suggestion list, once something is typed on CATEGORY or
        HASHTAGS; the hashtags the part holds are not offered again."""
        typed = text.strip()
        refs = self._refs
        key = self._key
        if not typed or refs is None or key not in PICKED:
            self._suggestions = []
        elif key == "category":
            self._suggestions = matching(refs.categories, typed)
        else:
            self._suggestions = matching(
                refs.hashtags, typed.lstrip("#"), chosen=self._part.hashtag_ids
            )
        self._suggest_idx = 0

    def _refresh_bar(self) -> None:
        key = self._key
        self.query_one("#part-field", Label).update(field_label(key))
        bar = self.query_one("#bar", Input)
        bar.value = self._bar_value(key)
        bar.cursor_position = len(bar.value)
        self._recompute(bar.value)

    # ---- the part being edited ----------------------------------------------
    @property
    def _part(self) -> Part:
        return self._parts[self._editing] if self._editing is not None else Part()

    def _set_part(self, part: Part) -> None:
        if self._editing is None or part == self._parts[self._editing]:
            return
        self._parts[self._editing] = part
        self._refusal = None  # a part changed

    def _keep_field(self) -> bool:
        """Keep what is typed in the field the cursor is on. False, with a
        note saying why, when it cannot be kept; the cursor then stays."""
        text = self.query_one("#bar", Input).value.strip()
        part = self._part
        key = self._key
        if key == "amount":
            cents = parse_amount(text) if text else None
            if text and cents is None:
                self.notify("Amount: a signed decimal, e.g. -99.92", severity="error")
                return False
            self._set_part(replace(part, amount_cents=cents))
        elif key == "note":
            self._set_part(replace(part, note=text or None))
        elif text:  # category or hashtags: empty keeps what the part holds
            picked = self._suggestions[self._suggest_idx] if self._suggestions else None
            if picked is None:
                name = "category" if key == "category" else "hashtag"
                self.notify(f"No {name} matches “{text}”.", severity="error")
                return False
            if key == "category":
                self._set_part(replace(part, category_id=picked[0]))
            else:
                pending = self._refs.pending_hashtag_id if self._refs else None
                tags = hashtags_to_send([*part.hashtag_ids, picked[0]], pending)
                self._set_part(replace(part, hashtag_ids=tuple(tags)))
        return True

    def _open_fields(self, index: int) -> None:
        self._editing = index
        self._cursor = index
        self._current = 0
        self.query_one("#part-fields").display = True
        self._refresh_bar()
        bar = self.query_one("#bar", Input)
        bar.disabled = False
        bar.focus()
        self.refresh_bindings()
        self._refresh_view()

    def _close_fields(self) -> None:
        """Back to the table, the cursor on the part; a part with nothing in it
        drops."""
        index = self._editing
        if index is None:
            return
        self._editing = None
        if self._parts[index].empty:
            del self._parts[index]
        self._cursor = min(index, len(self._parts))
        self._suggestions = []
        self.query_one("#part-fields").display = False
        self.query_one("#bar", Input).disabled = True
        self.set_focus(None)
        self.refresh_bindings()
        self._refresh_view()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """`⏎` in the fields: keep the field and move to the next, or back to
        the table from NOTE. On HASHTAGS a typed name adds the hashtag and
        stays for another, as on the Edit form; `⏎` with nothing typed moves
        on."""
        if self._editing is None:
            return
        typed = event.value.strip()
        if not self._keep_field():
            return
        if self._key == "hashtags" and typed:
            self.query_one("#bar", Input).value = ""
            self._recompute("")
            self._refresh_view()
        elif self._current >= len(FIELDS) - 1:
            self._close_fields()
        else:
            super().action_field(1)

    # ---- keys --------------------------------------------------------------
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """The table's keys on the table, the fields' keys in the fields."""
        editing = self._editing is not None
        if action in ("cancel", "edit", "drop_part"):
            return not editing
        if action in ("back", "field"):
            return editing
        return True

    def action_arrow(self, delta: int) -> None:
        """`↑↓`: the cursor on the table; in the fields, the suggestion list
        while it is open, else the field."""
        if self._editing is not None:
            super().action_arrow(delta)
            return
        if self._refs is None:
            return
        self._cursor = max(0, min(len(self._parts), self._cursor + delta))
        self._refresh_view()

    def action_field(self, delta: int) -> None:
        """Leave the field for the next or previous one, keeping it."""
        if self._editing is None or not self._keep_field():
            return
        super().action_field(delta)

    def action_edit(self) -> None:
        """`⏎` on the table: open the part's fields, or add an empty part and
        open it."""
        if self._refs is None or self._sending:
            return
        if self._cursor >= len(self._parts):
            self._parts.append(Part())
            self._cursor = len(self._parts) - 1
        self._open_fields(self._cursor)

    def action_back(self) -> None:
        """`esc` in the fields: back to the table, the field being typed as it
        was."""
        self._close_fields()

    def action_drop_part(self) -> None:
        """`ctrl+x`: drop the part under the cursor."""
        if self._sending or self._cursor >= len(self._parts):
            return
        del self._parts[self._cursor]
        if self._cursor == len(self._parts) and self._parts:
            self._cursor -= 1
        self._refusal = None  # a part changed
        self._refresh_view()

    def action_cancel(self) -> None:
        """`esc` on the table: leave, nothing sent."""
        if not self._sending:
            self.dismiss(False)

    def action_submit(self) -> None:
        """`ctrl+s`: send every part — always; the engine says whether they add
        up. In the fields, the field being typed is kept first and the table
        comes back."""
        if self._sending or self._refs is None:
            return
        if self._editing is not None:
            if not self._keep_field():
                return
            self._close_fields()
        self._sending = True
        self._refusal = None
        self._refresh_view()
        self.run_write(
            "POST",
            f"/transactions/{self._record.get('id')}/split",
            json_body=split_body(self._parts, self._refs),
            on_success=self._split_done,
            on_failure=self._split_refused,
        )

    def _split_done(self) -> None:
        self._sending = False
        self.dismiss(True)

    def _split_refused(self, err: Exception) -> None:
        self._sending = False
        self._refusal = err
        self._refresh_view()

    # ---- render ------------------------------------------------------------
    def _refresh_view(self) -> None:
        refs = self._refs
        self.query_one("#split-head", Static).update(
            head_line(self._record, self._total, refs, palette=PALETTE)
        )
        self.query_one("#split-title", Static).update(title_line(self._record))
        self.query_one("#parts", Static).update(self._parts_renderable())
        if self._editing is None or refs is None:
            return
        part = self._part
        current = self._current
        rule = Text("─" * RULE_WIDTH, style="dim", no_wrap=True, overflow="crop")
        self.query_one("#part-head", Static).update(
            Group(rule, Text(f"PART {self._editing + 1}", style="bold"))
        )
        above = self.query_one("#fields-above", Static)
        above.display = current > 0
        above.update(Group(*(field_line(k, part, refs) for k in FIELDS[:current])))
        below = self.query_one("#fields-below", Static)
        below.display = current < len(FIELDS) - 1
        below.update(Group(*(field_line(k, part, refs) for k in FIELDS[current + 1 :])))
        suggest = self.query_one("#part-suggest", Static)
        typed = self.query_one("#bar", Input).value.strip()
        suggest.display = self._key in PICKED and bool(typed)
        suggest.update(suggestion_list([e[1] for e in self._suggestions], self._suggest_idx))

    def _parts_renderable(self) -> RenderableType:
        refs = self._refs
        if refs is None:
            return Text(LOADING_HINT, style="dim")
        blocks: list[RenderableType] = [
            *parts_lines(
                self._parts,
                refs,
                cursor=self._cursor if self._editing is None else None,
                editing=self._editing,
                flagged=flagged_parts(self._refusal),
                palette=PALETTE,
            ),
            Text(""),
            count_line(self._parts, self._total, palette=PALETTE),
        ]
        if self._refusal is not None:
            blocks.append(Text(""))
            blocks.extend(refusal_lines(self._refusal, palette=PALETTE))
        return Group(*blocks)
