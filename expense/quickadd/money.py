"""Money as text — the decimal string a human types, and its inverse.

Lives with the quick-add grammar, which needs to read an amount out of a
line, and the staged-row round trip needs to write one back into it.
"""

import re

from expense.currencies import MINOR_UNIT_SCALE

#: A plain number: ASCII digits with an optional sign and one optional dot. No
#: exponent, no `inf`/`nan`, no digit separator, no other script's digits.
_PLAIN_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")


def parse_amount(text: str) -> int | None:
    """`-99.92` → -9992 cents. None if unparseable. Sign is explicit.

    A comma groups thousands (`-1,311.97`) and is dropped. A comma after the
    dot (`13.853,20`) is a decimal comma: dropping it would read 13.85, so
    that amount is unreadable rather than guessed. Only a plain number is read:
    an exponent (`1e5`), `inf` and `nan` are unreadable. A plain number is read
    at any size, so the engine's bound shows in the engine's words (contract: "Money amounts");
    one with more digits than Python turns to text (4300) is unreadable too.
    """
    text = text.strip()
    if "," in text.partition(".")[2]:
        return None
    text = text.replace(",", "")
    if _PLAIN_NUMBER.fullmatch(text) is None:
        return None
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
