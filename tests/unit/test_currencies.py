"""Drift trap: the USD/PEN whitelist has exactly one home.

Adding a currency engine-side (contract: "Currencies") must
mean touching expense/currencies.py only — if any client copy drifts, this
fails.
"""

from expense.currencies import SUPPORTED_CURRENCIES
from expense.import_ import mapping
from expense.tui.screens import create_forms


def test_currency_whitelist_single_source():
    assert set(dict(create_forms._CURRENCIES)) == set(SUPPORTED_CURRENCIES)
    assert mapping.VALID_CURRENCIES == frozenset(SUPPORTED_CURRENCIES)
