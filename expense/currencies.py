"""Phase-1 currency whitelist — client mirror of the engine's currency lock.

Provenance: only `PEN` and `USD` exist (contract: "Currencies"). When the
contract admits another currency, update this tuple in the same change.

Tuple order is meaningful: it drives the account-form currency picker.
"""

SUPPORTED_CURRENCIES: tuple[str, ...] = ("PEN", "USD")


# The minor-unit scale: how many minor units make one major unit. Consumed by
# quickadd/money.py (both directions), formatting.format_cents and
# commands/import_cmd.
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

# The scale stored exchange rates are expressed at — client mirror of the
# contract's `rate_e8`, "the rate × 10^8" (contract: GET /v1/exchange-rates).
# The engine's wire format is `rate_e8: int` (the rate x this), so
# commands/rates_cmd divides by it for display and never does arithmetic on the
# quotient. Same provenance rule as SUPPORTED_CURRENCIES above: if the engine
# changes the scale, this changes in the same commit.
RATE_SCALE = 100_000_000
