"""Money as text — the decimal string a human types, and its inverse.

Lives with the quick-add grammar, which needs to read an amount out of a
line, and the staged-row round trip needs to write one back into it.
"""

import re

from expense.currencies import MINOR_UNIT_SCALE
from expense.number_format import NumberFormat


def _plain_number(number_format: NumberFormat) -> re.Pattern[str]:
    """A plain number in `number_format`: ASCII digits, an optional sign, thousands
    marks only between a 1-3 digit head (never starting with 0) and groups of exactly
    three digits, one optional decimal mark. No exponent, no `inf`/`nan`, no other
    script's digits."""
    group, decimal = re.escape(number_format.group), re.escape(number_format.decimal)
    whole = rf"(?:[1-9][0-9]{{0,2}}(?:{group}[0-9]{{3}})+|[0-9]+)"
    return re.compile(rf"[+-]?(?:{whole}(?:{decimal}[0-9]*)?|{decimal}[0-9]+)")


_PLAIN_NUMBERS = {f: _plain_number(f) for f in NumberFormat}


def parse_amount(text: str, number_format: NumberFormat) -> int | None:
    """`-99.92` → -9992 cents. None if unparseable. Sign is explicit.

    The format says which mark is the decimal and which groups thousands. A
    thousands mark is followed by exactly three digits (`-1,311.97`, `1,000`);
    `-1,5` and `1,23,456` are unreadable, never guessed, and so is the other
    format's decimal (`13.853,20` in `1,234.56`). Only a plain number is read:
    an exponent (`1e5`), `inf` and `nan` are unreadable. A plain number is read
    at any size, so the engine's bound shows in the engine's words (contract: "Money amounts");
    one with more digits than Python turns to text (4300) is unreadable too.
    """
    text = text.strip()
    if _PLAIN_NUMBERS[number_format].fullmatch(text) is None:
        return None
    text = text.replace(number_format.group, "").replace(number_format.decimal, ".")
    sign = -1 if text.startswith("-") else 1
    whole, _, fraction = text.lstrip("+-").partition(".")
    # Integer arithmetic, not `Decimal`, whose 28-digit context would round a larger
    # amount. A third decimal of 5 or more rounds the cents up, away from zero.
    fraction = fraction.ljust(3, "0")
    try:
        cents = int((whole or "0") + fraction[:2])
    except ValueError:  # more digits than Python turns to text
        return None
    return sign * (cents + (fraction[2] >= "5"))


def amount_to_text(cents: int) -> str:
    """Cents → an editable decimal string (no grouping): -9992 → '-99.92'."""
    major, minor = divmod(abs(cents), MINOR_UNIT_SCALE)
    sign = "-" if cents < 0 else ""
    fraction = f".{minor:02d}".rstrip("0") if minor else ""
    return f"{sign}{major}{fraction}"
