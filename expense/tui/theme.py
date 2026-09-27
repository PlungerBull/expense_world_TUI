"""TUI theme + the semantic palette for Rich-rendered content.

**The terminal supplies the colours.** Every colour here is an ANSI *slot*
(`ansi_green` is slot 2), not a hex — so the palette is whatever the user's
terminal defines, and the app reads correctly on dark, light, Solarized,
Gruvbox or anything else with no detection at startup.
Why: docs/decisions.md "The terminal supplies the palette".

Widgets reference theme variables ($accent, $secondary, $text-muted, $error) in
[app.tcss](app.tcss), so the slots below are the only place a colour is chosen.

Textual has two colour worlds that don't talk: CSS rules resolve `$accent`,
but screens also build Rich `Text`/`Table` objects inside `Static` widgets, and
Rich has never heard of `$accent` — it needs a literal like `green`. `PALETTE`
is the bridge. It holds **no app reference**, which is what lets the pure
row-builders (`account_rows`, `amount_cell`, …) be unit-tested without an app,
and lets them take `palette=None` to render unstyled.

`PALETTE` is a **constant**, not a lookup: there is one theme and no way to
change it, so reading `app.current_theme` per render would provably return the
same value every time.

It is still *derived* from the Theme rather than written out: `_rich` turns
Textual's `ansi_green` into the `green` Rich wants, so the slots above stay the
single source of truth — and no literal colour name appears in this package,
which `test_no_literal_color_styles_in_tui` requires.

The two rule constants are a product decision: amounts and
account balances are sign-colored everywhere; reconciliation statement
checkpoints (begin/end) stay plain — they're positions, not judgments.
"""

from dataclasses import dataclass
from typing import Literal

from textual.theme import Theme

EXPENSE_ANSI = Theme(
    name="expense-ansi",
    ansi=True,
    primary="ansi_blue",
    # `$secondary` carries the structural rules (header rule, list-panel border).
    # It has to be a *standard* token, not a custom `variables` entry: app.tcss is
    # parsed before on_mount registers this theme, so a custom `$rule` is an
    # undefined-variable error at startup.
    secondary="ansi_bright_black",  # structural rules, unfocused borders
    accent="ansi_blue",  # panel titles, focus borders, help keys
    foreground="ansi_default",
    background="ansi_default",
    surface="ansi_default",
    panel="ansi_default",
    success="ansi_green",  # positive amounts
    error="ansi_red",  # negative amounts / errors
    warning="ansi_default",  # see PENDING_STYLE
    dark=True,
    # An `ansi=True` theme MUST carry these: Textual's own Screen CSS references
    # `$ansi-background`, so omitting them is an undefined-variable error at
    # startup, not a missing nicety. Textual ships two sets (ansi-dark /
    # ansi-light) that disagree on every cursor and selection colour — which is
    # the light/dark split we are refusing to make. Ours sidesteps it: the
    # cursors are **reverse video** (default fg/bg, swapped), which is what
    # CursorList/CheckList already do in Rich (`cursor_list.py`), and is correct
    # on any ground by construction. Only the selections take a real colour, and
    # they take the accent, so a highlight always reads as "the app's colour".
    variables={
        "ansi-background": "ansi_default",
        "ansi-foreground": "ansi_default",
        "border": "ansi_blue",  # focused widget — the accent
        "border-blurred": "ansi_bright_black",  # unfocused — the secondary
        "block-cursor-foreground": "ansi_default",
        "block-cursor-background": "ansi_default",
        "block-cursor-text-style": "reverse",
        "input-cursor-foreground": "ansi_default",
        "input-cursor-background": "ansi_default",
        "input-cursor-text-style": "reverse",
        "input-selection-background": "ansi_blue",
        "input-selection-foreground": "ansi_bright_white",
        "screen-selection-background": "ansi_blue",
        "screen-selection-foreground": "ansi_bright_white",
        # Footer key glyphs take the accent, like panel titles, focus borders
        # and help key glyphs. Left undefined, Textual's fallback renders them
        # magenta, which is a colour this app uses nowhere else.
        "footer-key-foreground": "ansi_blue",
    },
)

# Pending states carry weight, not colour — Why: docs/decisions.md "The terminal
# supplies the palette". Not a colour string — `Palette.warning` is a Rich
# *style*, so sites use it directly.
PENDING_STYLE = "bold"

# Where each rule applies: AMOUNT_RULE — transaction amounts, account balances,
# dashboard totals; BALANCE_RULE — reconciliation begin/end checkpoints only.
AMOUNT_RULE: Literal["sign", "income-only", "plain"] = "sign"
BALANCE_RULE: Literal["sign", "plain"] = "plain"


def _rich(color: str) -> str:
    """Textual's ANSI spelling → Rich's. `ansi_green` → `green` (slot 2)."""
    return color.removeprefix("ansi_")


@dataclass(frozen=True)
class Palette:
    """Resolved, Rich-parseable styles for the current theme.

    `success`/`error` are colours; `warning` is a style with no colour at all
    (see PENDING_STYLE) — the field name is historical, the role is "pending".
    """

    success: str
    error: str
    warning: str


PALETTE = Palette(_rich(EXPENSE_ANSI.success), _rich(EXPENSE_ANSI.error), PENDING_STYLE)

# The help card's key glyphs; same story as PALETTE — one theme, so one value.
ACCENT = _rich(EXPENSE_ANSI.accent)
