"""The number format: which mark is the decimal and which groups thousands.

Two formats exist, `1,234.56` and `1.234,56`. A session holds one current
format here, and every reader and writer of a typed amount asks `current_format()`
rather than naming a format itself, so changing it changes them all.
"""

from enum import Enum


class NumberFormat(Enum):
    """A format is its `(decimal, group)` marks; `example` is how it is named to the user."""

    DOT_DECIMAL = (".", ",")  # 1,234.56
    COMMA_DECIMAL = (",", ".")  # 1.234,56

    @property
    def decimal(self) -> str:
        return self.value[0]

    @property
    def group(self) -> str:
        return self.value[1]

    @property
    def example(self) -> str:
        return f"1{self.group}234{self.decimal}56"


#: The format when nothing else decides: the machine's region (expense/region.py)
#: gives the session's format at launch, and this stands when it cannot be read.
DEFAULT_FORMAT = NumberFormat.DOT_DECIMAL

_current = DEFAULT_FORMAT


def current_format() -> NumberFormat:
    """The session's format; every typed amount is read in it."""
    return _current


def set_current_format(number_format: NumberFormat) -> None:
    global _current
    _current = number_format


def amounts_are(number_format: NumberFormat | None = None) -> str:
    """The format as a clause: `amounts are 1,234.56`; the current format when none is given."""
    return f"amounts are {(number_format or _current).example}"


def amounts_sentence() -> str:
    """The format as the closing sentence of a field's refusal: `Amounts are 1,234.56.`"""
    return f"Amounts are {_current.example}."
