"""Phase-1 currency whitelist — client mirror of the engine's currency lock.

Provenance: only `PEN` and `USD` exist (contract: "Currencies"). When the
contract admits another currency, update this tuple in the same change.

Tuple order is meaningful: it drives the account-form currency picker and the
order of Manage ▸ Accounts' currency columns.
"""

from collections.abc import Sequence

SUPPORTED_CURRENCIES: tuple[str, ...] = ("PEN", "USD")


# The minor-unit scale: how many minor units make one major unit. Consumed by
# quickadd/money.py (both directions) and formatting.format_cents.
#
# ⚠️ One constant for every currency is correct ONLY because the tuple above is
# locked to {USD, PEN}, which are both exponent 2. Centralizing makes the
# assumption findable and single-edit; it does NOT make it data-driven.
# The contract states every amount as an integer number of cents and has no
# per-currency exponent (contract: "Currencies"), so admitting a currency with a
# different exponent — JPY is 0, KWD is 3 — means introducing the concept, not editing
# this number. Every call site below would have to learn which currency it is
# formatting, which none of them currently knows.
#
# The engine has no counterpart: it stores and serves integer cents and never
# converts to major units at all. This scale is a presentation concern and lives
# entirely on this side.
MINOR_UNIT_SCALE = 100


def only_currency(codes: Sequence[str]) -> str | None:
    """The one currency an account holds, when it holds exactly one, else None.

    The display rule: an account holding one currency shows it and asks no pick. The
    write fills that use it are listed in `FILLS_AN_ONLY_CURRENCY`."""
    return codes[0] if len(codes) == 1 else None


#: The three writes where the app names an account's only currency itself, because the
#: engine does not yet take it when a write names none (the ask: docs/to-engine/
#: an-accounts-only-currency-is-taken-when-a-write-names-none.md, "An account's only
#: currency is taken when a write names none"). Delete each when the engine takes it;
#: the display uses of `only_currency` stay.
FILLS_AN_ONLY_CURRENCY = (
    ("expense/quickadd/parse.py", "a line with no `%` takes the account's only currency"),
    ("expense/tui/screens/edit_form.py", "`_take_only_currency`, on an account change"),
    ("expense/tui/screens/transactions.py", "`_apply_pick`, `b` to a one-currency account"),
)
