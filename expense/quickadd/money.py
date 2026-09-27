"""Money as text — the decimal string a human types, and its inverse.

Lives with the quick-add grammar, which needs to read an amount out of a
line, and the staged-row round trip needs to write one back into it.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from expense.currencies import MINOR_UNIT_SCALE


def parse_amount(text: str) -> int | None:
    """`-99.92` → -9992 cents. None if unparseable. Sign is explicit."""
    text = text.strip().replace(",", "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if not value.is_finite():
        # `Decimal` accepts "nan", "inf" and "-Infinity"; `int()` on any of them
        # raises. A form field must warn on an unreadable amount, not crash, so
        # they leave here as None like every other thing that isn't a number.
        return None
    return int((value * MINOR_UNIT_SCALE).to_integral_value(rounding=ROUND_HALF_UP))


def amount_to_text(cents: int) -> str:
    """Cents → an editable decimal string (no grouping): -9992 → '-99.92'."""
    return str(Decimal(cents) / MINOR_UNIT_SCALE)
