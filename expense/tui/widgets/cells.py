"""Shared cell renderables for list rows."""

from rich.text import Text

from expense.formatting import format_aggregate, format_cents, unconverted_of, whole_number
from expense.tui.theme import Palette


def swatch(color: object) -> Text:
    """A ` ██ ` color swatch in the given `#RRGGBB`, or a dim em-dash if unset."""
    if isinstance(color, str) and len(color) == 7 and color.startswith("#"):
        return Text("██", style=color)
    return Text("—", style="dim")


def code_cell(code: object) -> str | Text:
    """A code column's cell: the code, or a dim `—` when there is none."""
    return str(code) if code else Text("—", style="dim")


def operation_cell(code: object) -> str | Text:
    """A bank line's `operation_code` as every reconciliation list shows it:
    the operation code, or a dim `—` when the line has none."""
    return code_cell(code)


def difference_cell(cents: object, palette: Palette | None) -> str | Text:
    """A reconciliation's `difference_cents`, in three distinguishable states.

    | value | cell | means |
    |---|---|---|
    | `0` | dim em-dash | checked, and the batch adds up |
    | non-zero | sign-colored figure | checked, and it is off by this much |
    | `None` | **blank** | not checked — no ending balance has been entered |

    Zero is the goal state, so it reads as "nothing to see" rather than as a
    number to check. A non-zero difference is sign-colored like every other
    amount in the TUI — the sign says which way to look.

    ⚠️ **`None` must not share the em-dash.** A null difference says *nobody has
    entered the closing figure yet*, which is the opposite of "it balances" —
    and the em-dash is designed to read as "nothing to see, move on". Non-int
    junk goes to the blank too: whatever it is, the one thing this cell must
    not do is assert that the batch balances. Why, with the rejected
    renderings: docs/decisions.md "A null difference is blank, a zero
    difference is the em-dash".
    """
    if whole_number(cents) is None:
        return ""
    if cents == 0:
        return Text("—", style="dim")
    return amount_cell(cents, palette, "sign")


def amount_cell(cents: object, palette: Palette | None, rule: str) -> str | Text:
    """`format_cents`, sign-colored per `rule` when a palette is given.

    Returns the plain string under rule="plain", palette=None, or non-int cents,
    so palette-less callers (and their equality-asserting tests) see today's
    output unchanged. "sign" colors both directions; "income-only" only ≥ 0.

    `None` is a dim em-dash, not `format_cents`'s literal `(null)` — the TUI's
    mark for an absent value, the same one `format_short_date` already uses.
    Only one caller can actually hand this a null today (a reconciliation's
    `ending_balance_cents`, nullable in the engine); the rest —
    account balances, transaction amounts, beginning balances — are non-null by
    engine guarantee. Handling it here rather than at that one call site means
    no column can ever start printing `(null)` at a user if another field turns
    nullable later.
    """
    if cents is None:
        return Text("—", style="dim") if palette is not None else "—"
    text = format_cents(cents)
    if palette is None or rule == "plain" or not isinstance(cents, int):
        return text
    if cents >= 0:
        return Text(text, style=palette.success)
    return Text(text, style=palette.error) if rule == "sign" else text


def aggregate_cell(
    cents: object,
    unconverted_count: object,
    palette: Palette | None,
    rule: str,
) -> str | Text:
    """A home-currency aggregate cell: the sign-colored amount, or `3 unrated`.

    The engine returns `None` plus an `unconverted_count` when
    any row in the group falls on a date with no resolvable rate. That is not a
    zero and not a blank, so it renders as its own warning-colored figure rather
    than as an amount — warning, because unpriced
    rows are work to go do, not something broken.

    A present amount is delegated to `amount_cell`, so aggregates stay colored
    exactly like every other amount in the TUI.
    """
    if whole_number(cents) is not None:
        return amount_cell(cents, palette, rule)
    text = format_aggregate(cents, unconverted_count)
    if palette is None or unconverted_of({"unconverted_count": unconverted_count}) == 0:
        return text
    return Text(text, style=palette.warning)
