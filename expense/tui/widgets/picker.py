"""The suggestion list both quick-add surfaces drop under their input.

The LOG bar and the bar-cycle edit form offer different things from different
sources — the bar picks a span out of a parsed line, the form picks a field's
entity — but under the input they draw the same widget: a scrolling window of
at most `PICKER_WINDOW` names, the cursor kept near the middle, and a dim
`↑ n more` / `↓ n more` when the pool runs past the edge.

Both draw through this one copy of that arithmetic: the window is a named
constant and the cursor is `CURSOR_STYLE`. The label is the only thing that
genuinely differs — one appends a currency, the other whatever third field the
entity tuple carries — so the caller formats the labels and this draws them.

What a field's list holds is `matching`'s: the edit form and the split
screen's part fields fill their lists through it, so a typed name finds the
same entities on both.
"""

from collections.abc import Collection, Sequence

from rich.console import Group, RenderableType
from rich.text import Text

from expense.quickadd.names import matches
from expense.tui.widgets.windowed import CURSOR_STYLE

#: Names visible at once. Eight fits under the bar without pushing the staged
#: list off a short terminal, and is more than any real pool needs before you
#: have typed enough to narrow it.
PICKER_WINDOW = 8

#: What an empty pool says. The wording matters: the pools are closed sets, so
#: "pick something that exists" is the actual instruction, not a consolation.
NO_MATCHES = "  no matches — pick something that exists"


def suggestion_list(
    labels: Sequence[str],
    selected: int,
    *,
    window: int = PICKER_WINDOW,
) -> RenderableType:
    """`labels` as a scrolling window with `selected` marked as the cursor.

    The window follows the cursor by centring on it and then clamping to the
    ends, so the first and last pages are full rather than half-empty.
    """
    if not labels:
        return Text(NO_MATCHES, style="dim")

    total = len(labels)
    start = 0
    if total > window:
        start = max(0, min(selected - window // 2, total - window))
    end = min(start + window, total)

    rows: list[Text] = []
    if start > 0:
        rows.append(Text(f"  ↑ {start} more", style="dim"))
    for index in range(start, end):
        line = Text(f"  {labels[index]}")
        if index == selected:
            line.stylize(CURSOR_STYLE)
        rows.append(line)
    if total > end:
        rows.append(Text(f"  ↓ {total - end} more", style="dim"))
    return Group(*rows)


def matching(entities: Sequence[tuple], typed: str, *, chosen: Collection[str] = ()) -> list[tuple]:
    """The `(id, name, …)` entities whose name holds `typed`, case- and
    accent-blind (`names.matches`), in their order, without the ids in
    `chosen` (the hashtags a field already holds). An empty `typed` holds
    every name."""
    return [e for e in entities if matches(typed, e[1]) and e[0] not in chosen]
