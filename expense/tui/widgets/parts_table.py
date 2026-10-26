"""The parts of a bank line, as the Edit form draws them under its shared fields.

Pure builders, no app and no event loop: the part model the form edits, the
table of the parts (amount, category, hashtags, note), the dim `read-only` lines
under it, the line adding the parts up against the line's total, and a refused
save's lines. Screens of mockups/expense-world-split-transaction-screen.html.

**The only arithmetic is the count line**: the parts' amounts summed against
the engine's own `net_cents`. It never stops a save; the engine decides whether
the parts add up (contract: PUT /v1/bank-lines/{bank_line_id}, "The total").
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace

from rich.console import RenderableType
from rich.text import Text

from expense.errors import EngineError, app_lines, format_error, key_field, key_index
from expense.formatting import format_cents, resolve_name, signed_cents
from expense.reads import QuickAddRefs, hashtags_to_send
from expense.tui.theme import ACCENT, AMOUNT_RULE, Palette
from expense.tui.widgets.cells import amount_text
from expense.tui.widgets.refusal import hanging

#: A cell with nothing in it, as drawn.
EMPTY = "—"
#: Under a refused save, unless the engine failed (a `5xx`).
NOTHING_SAVED = "Nothing was saved."

#: A part's fields, in the order the bar moves through them, and the table's
#: column for each; the column's word names the field in a `read-only` line.
FIELDS = ("amount", "category", "hashtags", "note")
HEADERS = FIELDS
#: The engine's name for each part field (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts").
ENGINE_FIELDS = {
    "amount": "amount_cents",
    "category": "category_id",
    "hashtags": "hashtag_ids",
    "note": "description",
}
#: What a refused key's field reads as after `part N`: the table's column word for
#: the engine's field, `parts.0.category_id` reading `part 1 (category)`.
FIELD_WORDS = {engine: field for field, engine in ENGINE_FIELDS.items()}

#: Columns of the table, as drawn: the marker and number, then each cell at
#: least as wide as its header leaves room for, and the gap after each.
MIN_WIDTHS = (7, 11, 12, 0)
MARKER_GAP = "  "
GAP = "    "


@dataclass(frozen=True)
class Part:
    """One part in the table. `amount_cents` None until one is typed;
    `category_id` None on a new part with none picked, which the engine files
    under `@Pendiente`; `hashtag_ids` as picked or as the engine holds them,
    the pending hashtag among them; `id` the engine's on a part read from the
    line, which is sent under it; None on a part added in the form."""

    amount_cents: int | None = None
    category_id: str | None = None
    hashtag_ids: tuple[str, ...] = ()
    note: str | None = None
    id: str | None = None


def part_from_engine(item: Mapping) -> Part:
    """A part as `GET /bank-lines/{id}` lists it: a magnitude and its
    `transaction_type`, signed by `signed_cents`, under its own id."""
    category = item.get("category_id")
    return Part(
        amount_cents=signed_cents(dict(item)),
        category_id=str(category) if category else None,
        hashtag_ids=tuple(str(t) for t in item.get("hashtag_ids") or ()),
        note=item.get("description") or None,
        id=str(item["id"]),
    )


def real_hashtags(part: Part, pending_hashtag_id: str | None) -> list[str]:
    """The part's hashtags but the pending one, alone or not: what a new part
    sends, and what the table shows
    (contract: PUT /v1/bank-lines/{bank_line_id}, "An id no record holds creates a part")."""
    return hashtags_to_send(part.hashtag_ids, pending_hashtag_id, pending_alone=False)


def part_empty(part: Part, pending_hashtag_id: str | None) -> bool:
    """A part added in the form with nothing in it a save would send: no
    amount, category or note, and no hashtag but the pending one. A save
    leaves such a part out; a part read from the line is never empty."""
    if part.id is not None:
        return False
    return replace(part, hashtag_ids=tuple(real_hashtags(part, pending_hashtag_id))) == Part()


def _category_cell(part: Part, refs: QuickAddRefs) -> str:
    """The category's name; none, or `@Pendiente`, reads empty: the part
    waits for a category."""
    pending = refs.pending[0] if refs.pending else None
    if not part.category_id or part.category_id == pending:
        return ""
    return resolve_name(part.category_id, refs.category_names)


def _hashtags_cell(part: Part, refs: QuickAddRefs) -> str:
    tags = real_hashtags(part, refs.pending_hashtag_id)
    return " ".join("#" + resolve_name(t, refs.hashtag_names) for t in tags)


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


def _cell_style(field: str, closed: frozenset[str], base: str) -> str:
    """A cell's style: dim when its field is read-only, else the line's own."""
    return "dim" if field in closed else base


def parts_lines(
    parts: list[Part],
    refs: QuickAddRefs,
    *,
    editing: int | None = None,
    locked: Mapping[int, frozenset[str]] | None = None,
    flagged: frozenset[int] = frozenset(),
    palette: Palette | None = None,
) -> list[Text]:
    """The table: its header, dim, then one line per part, numbered.

    The part the bar is on (`editing`) reads `▌ 2 …` in the accent, bold. An
    amount reads in its sign's colour, and in the error colour, bold, when the
    refusal names it (`flagged`). A cell `locked` names for its part
    (`FIELDS` words) is dimmed, on the marked line too."""
    locked = locked or {}
    cells = [part_cells(p, refs) for p in parts]
    widths = [
        max([minimum, len(header), *(len(row[i]) for row in cells)])
        for i, (minimum, header) in enumerate(zip(MIN_WIDTHS, HEADERS, strict=True))
    ]
    header = Text("   " + MARKER_GAP + HEADERS[0].rjust(widths[0]), style="dim")
    for i in (1, 2):
        header.append(GAP + HEADERS[i].ljust(widths[i]))
    header.append(GAP + HEADERS[3])
    lines = [header]
    for index, (part, row_cells) in enumerate(zip(parts, cells, strict=True)):
        marked = index == editing
        base = (f"bold {ACCENT}" if palette else "bold") if marked else ""
        closed = locked.get(index, frozenset())
        number = ("▌" if marked else " ") + str(index + 1).rjust(2)
        line = Text()
        line.append(number + MARKER_GAP, style=base)
        if part.amount_cents is None:
            amount = Text(EMPTY, style=_cell_style("amount", closed, base))
        elif "amount" in closed:
            amount = Text(row_cells[0], style="dim")
        elif index in flagged:
            amount = Text(row_cells[0], style=f"bold {palette.error}" if palette else "bold")
        elif marked:
            amount = Text(row_cells[0], style=base)
        else:
            amount = amount_text(part.amount_cents, palette, AMOUNT_RULE)
        line.append(" " * (widths[0] - len(amount.plain)), style=base)
        line.append_text(amount)
        for i, field in ((1, "category"), (2, "hashtags")):
            line.append(GAP, style=base)
            line.append(row_cells[i], style=_cell_style(field, closed, base))
            line.append(" " * (widths[i] - len(row_cells[i])), style=base)
        line.append(GAP, style=base)
        line.append(row_cells[3], style=_cell_style("note", closed, base))
        line.rstrip()
        lines.append(line)
    for line in lines:
        line.no_wrap = True
        line.overflow = "crop"
    return lines


def readonly_lines(locked: Mapping[int, frozenset[str]]) -> list[Text]:
    """`amount  read-only`, dim, for each part field read-only on any part,
    in the table's column order."""
    closed = set().union(*locked.values()) if locked else set()
    return [Text(f"{field}  read-only", style="dim") for field in FIELDS if field in closed]


def count_line(parts: list[Part], total: int | None, *, palette: Palette | None = None) -> Text:
    """`2 parts  ·  -100.00 of -100.00  ✓`, or `…  ·  -10.00 left` in the error
    colour while the parts do not reach the total. The parts' amounts summed
    against the engine's total; a part with no amount adds nothing."""
    placed = sum(p.amount_cents for p in parts if p.amount_cents is not None)
    line = Text(f"{len(parts)} {'part' if len(parts) == 1 else 'parts'}  ·  ")
    line.append_text(amount_text(placed, palette, AMOUNT_RULE))
    if total is None:
        return line
    line.append(" of ")
    line.append_text(amount_text(total, palette, AMOUNT_RULE))
    left = total - placed
    if left:
        line.append("  ·  ")
        line.append(f"{format_cents(left)} left", style=palette.error if palette else "")
    else:
        line.append("  ✓", style=palette.success if palette else "")
    return line


def key_words(key: object) -> str:
    """A refusal's key as the form names it: `parts.1.amount_cents` reads
    `part 2 (amount)` and `parts.1.hashtag_ids` `part 2 (hashtags)`, each part
    field by its column's word (`FIELD_WORDS`), a field the table has no column
    for as sent; `parts.0` reads `part 1`; any other key as sent."""
    index = key_index(key, "parts")
    if index is None:
        return str(key)
    field = key_field(key, "parts")
    if field is not None:
        return f"part {index + 1} ({FIELD_WORDS.get(field, field)})"
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
    line per refused key, `Nothing was saved.`, then the app's line for the
    reason, if any — chosen by the engine's code and reasons (`app_lines`),
    never its words. A failure that is not the engine's answer reads as
    `format_error` says it."""
    error = palette.error if palette else ""
    if not isinstance(err, EngineError):
        return [Text(format_error(err), style=error)]
    lines: list[RenderableType] = [Text(f"{err.code} — {err.message}", style=error)]
    for key, message in (err.fields or {}).items():
        lines.append(hanging(Text(f"! {key_words(key)}: {message}", style=error)))
    if err.status < 500:
        lines.append(Text(NOTHING_SAVED, style="dim"))
    for line in app_lines(err):
        lines.append(Text(""))
        lines.append(Text(line))
    return lines
