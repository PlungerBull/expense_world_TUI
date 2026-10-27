"""Phase-1 currency whitelist — client mirror of the engine's currency lock.

Provenance: only `PEN` and `USD` exist (contract: "Currencies"). When the
contract admits another currency, update this tuple in the same change.

Tuple order is meaningful: it drives the account-form currency picker.
"""

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
