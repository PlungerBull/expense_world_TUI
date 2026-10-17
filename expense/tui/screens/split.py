"""The split screen — one purchase into parts, `s` on a ledger row.

Screens: docs/mockups/expense-world-split-action.html (2 B, 3, 4 B). A full
pushed screen, not a modal. On top, the purchase as the ledger has it: its
title, date and account, which every part keeps, and its signed total. Under
it, one typed line per part in the LOG bar's grammar (`±amount · @category ·
#tag · //note`): `↵` adds the part to the list, and a line naming an account, a
date or title words is refused in place (`route_part`). Every line is read by
`expense/quickadd/`, so this screen owns no grammar.

**Re-split.** On a part of a split purchase the list opens with the line's
current parts, read from `GET /transactions?bank_line_id=`, and the total is
the line's `net_cents` (contract: GET /v1/bank-lines/{bank_line_id}); a line
never split lists its one transaction, so the list opens empty. `↑↓` pick a
part, `↵` puts it in the bar to change, `ctrl+x` drops it.

**The only arithmetic is "left"**: the parts' amounts as typed, summed, against
the engine's total, as the LOG bar's staged total sums its rows. It never stops
a send: `ctrl+s` always sends the whole list in one
`POST /transactions/{id}/split`, each part under a fresh id, and the engine
decides whether the parts add up
(contract: POST /v1/transactions/{transaction_id}/split, "The total is kept").

**A refusal stays under the parts** until the list changes: the engine's words,
each `parts.<i>.<field>` key read as `part i+1 (field)`, the amounts a
`parts.<i>.amount_cents` key names in the error colour, `Nothing was split.`,
and the app's line for the refusal's reason, if it has one
(`errors.format_error`).
"""

from dataclasses import dataclass
from uuid import uuid4

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, Static

from expense import reads
from expense.dates import today_local
from expense.errors import EngineError, engine_words, format_error
from expense.formatting import format_cents, format_short_date, resolve_name
from expense.quickadd.money import amount_to_text
from expense.quickadd.parse import ParsedLine, parse
from expense.quickadd.route import Routing, describe, route_part
from expense.reads import QuickAddRefs, currency_of, hashtags_to_send, pending_label
from expense.tui.screens._base import EngineWriteMixin, call_while_attached, screen_fetch_kwargs
from expense.tui.screens.bank_import import hanging
from expense.tui.screens.log_bar import LOADING_HINT, LineHighlighter
from expense.tui.theme import ACCENT, AMOUNT_RULE, PALETTE, Palette
from expense.tui.widgets.cells import amount_cell
from expense.tui.widgets.header import Breadcrumb
from expense.tui.widgets.windowed import CURSOR_STYLE

#: The marker and the part's number share the first column (`• 1`).
HEADERS = ("", "amount", "category", "hashtags", "note")

LEGEND_LINE = "±amount · @category · #tag · //note            ↵ adds the part"
PICK_HINT = "↑↓ picks a part · ↵ puts it in the bar to change · ^x drops it"
NOTHING_SPLIT = "Nothing was split."

#: What a refused key's field reads as after `part N`.
FIELD_WORDS = {"amount_cents": "amount"}


@dataclass(frozen=True)
class Part:
    """One part in the list. `line` is what `↵` puts back in the bar: the raw
    line as typed, or for a part the engine already holds, the line that says
    the same. `category_id` None files the part under `@Pendiente`;
    `hashtag_ids` as typed or as the engine holds them."""

    line: str
    amount_cents: int
    category_id: str | None
    hashtag_ids: tuple[str, ...]
    note: str | None


def part_from_line(line: str, parsed: ParsedLine) -> Part:
    """A typed line `route_part` let through, as a part."""
    return Part(
        line=line,
        amount_cents=parsed.amount_cents or 0,
        category_id=parsed.category_id,
        hashtag_ids=parsed.hashtag_ids,
        note=parsed.note,
    )


def part_from_engine(item: dict, refs: QuickAddRefs) -> Part:
    """A part the engine holds (signed, as `fetch_line_parts` reads it), with
    the line that says the same: `@Pendiente` and the pending hashtag are what
    a line naming no category or no `#tag` means, so neither is written."""
    pending_category = refs.pending[0] if refs.pending else None
    category = item.get("category_id")
    if category == pending_category:
        category = None
    tags = tuple(str(t) for t in item.get("hashtag_ids") or ())
    amount = item.get("amount_cents")
    amount = amount if isinstance(amount, int) else 0
    note = item.get("description") or None
    words = [("+" if amount > 0 else "") + amount_to_text(amount)]
    if category:
        words.append("@" + resolve_name(category, refs.category_names))
    words.extend("#" + resolve_name(t, refs.hashtag_names) for t in real_tags(tags, refs))
    if note:
        words.append("//" + note)
    return Part(" ".join(words), amount, category, tags, note)


def real_tags(tags: tuple[str, ...] | list[str], refs: QuickAddRefs | None) -> list[str]:
    """The hashtags the save sends, without the pending one alone:
    `hashtags_to_send`, and a part with no real hashtag sends none, which the
    engine files under the pending hashtag
    (contract: POST /v1/transactions/{transaction_id}/split)."""
    pending = refs.pending_hashtag_id if refs else None
    return [t for t in hashtags_to_send(tags, pending) if t != pending]


def part_payload(part: Part, refs: QuickAddRefs | None, *, part_id: str) -> dict:
    """One entry of the split's `parts`: a fresh id and the signed amount, and
    only what the part names. Sparse by omission, as every create."""
    body: dict = {"id": part_id, "amount_cents": part.amount_cents}
    if part.category_id is not None:
        body["category_id"] = part.category_id
    tags = real_tags(part.hashtag_ids, refs)
    if tags:
        body["hashtag_ids"] = tags
    if part.note:
        body["description"] = part.note
    return body


def split_body(parts: list[Part], refs: QuickAddRefs | None) -> dict:
    """`POST /transactions/{id}/split`'s body: the whole new set, in list order,
    each part under a fresh id."""
    return {"parts": [part_payload(p, refs, part_id=str(uuid4())) for p in parts]}


# ---------------------------------------------------------------------------
# pure builders — no app, no event loop
# ---------------------------------------------------------------------------
def head_line(
    record: dict,
    total: int | None,
    refs: QuickAddRefs | None,
    *,
    part_count: int = 0,
    palette: Palette | None = None,
) -> Text:
    """`Tottus Jockey Plaza  ·  2026-10-11  ·  Sueldo Soles  ·  -100.00 PEN`, and
    `  ·  2 parts` on a purchase already split."""
    names = refs.account_names if refs else {}
    head = Text(record.get("title") or "—", style="bold")
    head.append(f"  ·  {format_short_date(record.get('date'))}", style="dim")
    head.append(f"  ·  {resolve_name(record.get('account_id'), names)}  ·  ", style="dim")
    if total is not None:
        figure = amount_cell(total, palette, AMOUNT_RULE)
        head.append_text(figure if isinstance(figure, Text) else Text(str(figure)))
    currency = currency_of(refs, record.get("account_id")) if refs else ""
    if currency:
        head.append(f" {currency}", style="dim")
    if part_count > 1:
        head.append(f"  ·  {part_count} parts", style="dim")
    return head


def _tags_cell(part: Part, refs: QuickAddRefs) -> Text:
    tags = real_tags(part.hashtag_ids, refs)
    if tags:
        return Text(" ".join("#" + resolve_name(t, refs.hashtag_names) for t in tags))
    if refs.pending_hashtag is not None:
        return Text("#" + refs.pending_hashtag[1], style="dim")
    return Text("—", style="dim")


def part_rows(
    parts: list[Part],
    refs: QuickAddRefs,
    *,
    flagged: frozenset[int] = frozenset(),
    palette: Palette | None = None,
) -> list[tuple]:
    """One cell tuple per part, in `HEADERS` order. A part with no category
    reads `@Pendiente` dim, one with no real hashtag the pending hashtag dim.
    The amount of a part in `flagged` (the refusal named it) is in the error
    colour."""
    rows: list[tuple] = []
    for index, part in enumerate(parts):
        marker = Text.assemble(("•", ACCENT if palette else ""), " ", (str(index + 1), "dim"))
        if index in flagged:
            amount: str | Text = Text(
                format_cents(part.amount_cents), style=palette.error if palette else ""
            )
        else:
            amount = amount_cell(part.amount_cents, palette, AMOUNT_RULE)
        if part.category_id:
            category = Text(resolve_name(part.category_id, refs.category_names))
        else:
            category = Text(pending_label(refs), style="dim")
        rows.append((marker, amount, category, _tags_cell(part, refs), part.note or ""))
    return rows


def parts_table(
    parts: list[Part],
    refs: QuickAddRefs,
    *,
    picked: int | None = None,
    flagged: frozenset[int] = frozenset(),
    palette: Palette | None = None,
) -> Table:
    """The parts as a table; the picked part in reverse video, like every cursor."""
    # three cells between columns, as drawn
    table = Table(box=None, pad_edge=False, expand=False, show_header=True, padding=(0, 1, 0, 2))
    for index, header in enumerate(HEADERS):
        table.add_column(
            Text(header, style="dim"), justify="right" if index == 1 else "left", no_wrap=True
        )
    for index, cells in enumerate(part_rows(parts, refs, flagged=flagged, palette=palette)):
        table.add_row(*cells, style=CURSOR_STYLE if index == picked else "")
    return table


def count_line(parts: list[Part], total: int | None, *, palette: Palette | None = None) -> Text:
    """`1 part · -60.00 of -100.00 · -40.00 left`. What is left is the parts as
    typed, summed, against the engine's total; it shows, in the error colour,
    only while it is not 0."""
    placed = sum(p.amount_cents for p in parts)
    line = Text(f"{len(parts)} {'part' if len(parts) == 1 else 'parts'} · ", style="dim")
    figure = amount_cell(placed, palette, AMOUNT_RULE)
    line.append_text(figure if isinstance(figure, Text) else Text(str(figure)))
    if total is None:
        return line
    line.append(" of ", style="dim")
    figure = amount_cell(total, palette, AMOUNT_RULE)
    line.append_text(figure if isinstance(figure, Text) else Text(str(figure)))
    left = total - placed
    if left:
        line.append(" · ", style="dim")
        line.append(format_cents(left), style=palette.error if palette else "")
        line.append(" left", style="dim")
    return line


def part_index(key: object) -> int | None:
    """The part a refusal's key names, from 0 — `parts.<i>` or
    `parts.<i>.<field>` — or None for any other key."""
    bits = str(key).split(".", 2)
    if len(bits) >= 2 and bits[0] == "parts" and bits[1].isdigit():
        return int(bits[1])
    return None


def part_key(key: object) -> str:
    """A refusal's key as the screen names it: `parts.1.amount_cents` reads
    `part 2 (amount)`, `parts.0` reads `part 1`; any other key as sent."""
    index = part_index(key)
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
        if (i := part_index(key)) is not None and str(key).endswith(".amount_cents")
    )


def refusal_lines(err: Exception, *, palette: Palette | None = None) -> list[RenderableType]:
    """The refusal kept under the parts (screen 4 B): `CODE — message`, a
    `! <key>: <words>` line per refused key, `Nothing was split.`, then the
    app's line for the reason, if any — all chosen by the engine's code and
    reasons (`format_error`), never its words. A failure that is not the
    engine's answer reads as `format_error` says it."""
    error = palette.error if palette else ""
    if not isinstance(err, EngineError):
        return [Text(format_error(err), style=error)]
    lines: list[RenderableType] = [Text(f"{err.code} — {err.message}", style=error)]
    for key, message in (err.fields or {}).items():
        lines.append(hanging(Text(f"! {part_key(key)}: {message}", style=error)))
    if err.status < 500:
        lines.append(Text(NOTHING_SPLIT, style="dim"))
    after = format_error(err)[len(engine_words(err)) :].strip("\n")
    if after:
        lines.append(Text(""))
        lines.append(Text(after))
    return lines


def preview(parsed: ParsedLine, refs: QuickAddRefs) -> str:
    """What the typed line makes of the part right now:
    `-40.00 · HOGAR · no hashtag`. A name that matches nothing, or several,
    says so in the grammar's own words (`describe`)."""
    amount = format_cents(parsed.amount_cents) if parsed.amount_cents is not None else "no amount"
    bad = {u.kind: describe(u) for u in parsed.unresolved}
    if "category" in bad:
        category = bad["category"]
    elif parsed.category_id:
        category = resolve_name(parsed.category_id, refs.category_names)
    else:
        category = "no category"
    tags = real_tags(parsed.hashtag_ids, refs)
    if "hashtag" in bad:
        hashtags = bad["hashtag"]
    elif tags:
        hashtags = " ".join("#" + resolve_name(t, refs.hashtag_names) for t in tags)
    else:
        hashtags = "no hashtag"
    return f"{amount} · {category} · {hashtags}"


# ---------------------------------------------------------------------------
# the screen
# ---------------------------------------------------------------------------
class SplitScreen(EngineWriteMixin, Screen):
    """Splits the bank line holding `record` into the parts in its list.

    Dismisses with True once the engine split it, so the ledger reads fresh;
    with False on `esc`. The bar always holds focus, so no bare letter is a
    command here and there is no `?` (a focused `Input` swallows printable
    keys), as on the LOG bar."""

    BINDINGS = [
        Binding("escape", "back", "Cancel"),
        Binding("ctrl+s", "split", "Split"),
        # `priority`: a focused `Input` binds ctrl+x to `cut`.
        Binding("ctrl+x", "drop_part", "Drop part", priority=True, show=False),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
    ]

    def __init__(self, record: dict, crumb: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._record = record
        self.crumb = (*crumb, "Split")
        self._refs: QuickAddRefs | None = None
        self._total: int | None = None
        self._line_parts = 0
        self._parts: list[Part] = []
        self._picked: int | None = None
        self._editing: int | None = None
        self._parsed: ParsedLine | None = None
        self._refused: Routing | None = None  # the last `↵` refused, until a keystroke
        self._refusal: Exception | None = None  # the engine's, until the list changes
        self._sending = False
        self._hl = LineHighlighter()

    # ---- layout ------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb, id="crumb")
        yield Static("", id="split-head")
        yield Horizontal(
            Label("PART", id="field"), Input(id="bar", highlighter=self._hl), id="inputbar"
        )
        yield Static("", id="hint")
        yield Static(Text(LEGEND_LINE, style="dim"), id="legend")
        yield Static("", id="part-refused")
        yield Static("", id="parts")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#bar", Input).focus()
        self._refresh_view()
        self._load()

    @work(thread=True, exclusive=True)
    def _load(self) -> None:
        """The reference lists, then — on a row that names its bank line — the
        line's parts and its total: `?bank_line_id=` and `GET /bank-lines/{id}`.
        A row with no bank line opens as a purchase never split, at its own
        amount."""
        from expense import config as config_module

        line_id = self._record.get("bank_line_id")
        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            refs = reads.load_quickadd_refs(cfg, **kw)
            if line_id:
                parts = reads.fetch_line_parts(cfg, str(line_id), **kw)
                total = reads.fetch_bank_line(cfg, str(line_id), **kw).get("net_cents")
            else:
                parts, total = [], self._record.get("amount_cents")
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            call_while_attached(self, self.notify, format_error(exc), severity="error")
            return
        call_while_attached(self, self._loaded, refs, parts, total)

    def _loaded(self, refs: QuickAddRefs, parts: list[dict], total: object) -> None:
        self._refs = refs
        self._total = total if isinstance(total, int) and not isinstance(total, bool) else None
        self._line_parts = len(parts)
        if len(parts) > 1:
            self._parts = [part_from_engine(item, refs) for item in parts]
        self._reparse(self.query_one("#bar", Input).value)
        self._refresh_view()

    # ---- the bar -----------------------------------------------------------
    def _reparse(self, text: str) -> None:
        self._refused = None  # any edit is a new attempt
        refs = self._refs
        if refs is None or not text.strip():
            self._parsed = None
        else:
            self._parsed = parse(
                text,
                accounts=refs.accounts,
                categories=refs.categories,
                hashtags=refs.hashtags,
                today=today_local(),
            )
        self._hl.parsed = self._parsed

    def on_input_changed(self, event: Input.Changed) -> None:
        self._reparse(event.value)
        self._refresh_view()

    def _set_bar(self, text: str) -> None:
        bar = self.query_one("#bar", Input)
        bar.value = text
        bar.cursor_position = len(text)
        self._reparse(text)

    def on_input_submitted(self, event: Input.Submitted | None = None) -> None:
        """`↵`: add the typed line as a part · put the picked part in the bar."""
        bar = self.query_one("#bar", Input)
        if bar.value.strip():
            self._add(bar.value)
        elif self._picked is not None:
            self._editing = self._picked
            self._set_bar(self._parts[self._picked].line)
        self._refresh_view()

    def _add(self, line: str) -> None:
        """The line joins the list, or replaces the part it was lifted from —
        or is refused and stays in the bar with the reason under it."""
        if self._refs is None:
            self.notify("Still loading accounts and categories.", severity="warning")
            return
        parsed = self._parsed
        if parsed is None:
            return
        routing = route_part(parsed)
        if routing.refused:
            self._refused = routing
            return
        part = part_from_line(line, parsed)
        if self._editing is not None:
            self._parts[self._editing] = part
            self._picked = self._editing
        else:
            self._parts.append(part)
            self._picked = None
        self._editing = None
        self._refusal = None  # the list changed
        self._set_bar("")

    # ---- keys --------------------------------------------------------------
    def action_move(self, delta: int) -> None:
        """`↑↓` pick a part while the bar is empty."""
        if self.query_one("#bar", Input).value or not self._parts:
            return
        if self._picked is None:
            self._picked = 0 if delta > 0 else len(self._parts) - 1
        else:
            self._picked = max(0, min(len(self._parts) - 1, self._picked + delta))
        self._refresh_view()

    def action_drop_part(self) -> None:
        """`ctrl+x`: drop the picked part."""
        picked = self._picked
        if picked is None:
            return
        del self._parts[picked]
        if self._editing == picked:
            self._editing = None
            self._set_bar("")
        elif self._editing is not None and self._editing > picked:
            self._editing -= 1
        self._picked = min(picked, len(self._parts) - 1) if self._parts else None
        self._refusal = None  # the list changed
        self._refresh_view()

    def action_back(self) -> None:
        """`esc`: leave the part being changed · unpick · leave the screen."""
        if self._sending:
            return
        if self._editing is not None:
            self._editing = None
            self._set_bar("")
        elif self._picked is not None:
            self._picked = None
        else:
            self.dismiss(False)
            return
        self._refresh_view()

    def action_split(self) -> None:
        """`ctrl+s`: send the whole list — always; the engine says whether the
        parts add up. A line still in the bar is not a part and is not sent."""
        if self._sending:
            return
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
    def _hint(self) -> str:
        if self._refs is None:
            return LOADING_HINT
        if self._parsed is not None:
            return preview(self._parsed, self._refs)
        if self._parts and not self.query_one("#bar", Input).value:
            return PICK_HINT
        return ""

    def _refresh_view(self) -> None:
        self.query_one("#split-head", Static).update(
            head_line(
                self._record,
                self._total,
                self._refs,
                part_count=self._line_parts,
                palette=PALETTE,
            )
        )
        self.query_one("#bar", Input).refresh()
        self.query_one("#hint", Static).update(Text(self._hint(), style="dim"))
        refused = self._refused
        why = self.query_one("#part-refused", Static)
        why.display = refused is not None
        why.update(
            Text("! " + ", ".join(refused.reasons), style=PALETTE.error)
            if refused is not None
            else Text("")
        )
        self.query_one("#parts", Static).update(self._parts_renderable())

    def _parts_renderable(self) -> RenderableType:
        refs = self._refs
        if refs is None:
            return Text("")
        blocks: list[RenderableType] = []
        if self._parts:
            blocks.append(
                parts_table(
                    self._parts,
                    refs,
                    picked=self._picked,
                    flagged=flagged_parts(self._refusal),
                    palette=PALETTE,
                )
            )
            blocks.append(Text(""))
        blocks.append(count_line(self._parts, self._total, palette=PALETTE))
        if self._refusal is not None:
            blocks.append(Text(""))
            blocks.extend(refusal_lines(self._refusal, palette=PALETTE))
        return Group(*blocks)
