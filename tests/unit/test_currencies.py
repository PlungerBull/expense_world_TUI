"""Drift trap: the USD/PEN whitelist has exactly one home.

Adding a currency engine-side (contract: "Currencies") must
mean touching expense/currencies.py only — if any client copy drifts, this
fails.
"""

from pathlib import Path

from expense.currencies import FILLS_AN_ONLY_CURRENCY, SUPPORTED_CURRENCIES, only_currency
from expense.tui.screens import create_forms


def test_currency_whitelist_single_source():
    assert set(dict(create_forms._CURRENCIES)) == set(SUPPORTED_CURRENCIES)


def test_only_currency_is_the_one_code_an_account_holds_and_none_otherwise():
    assert only_currency(("PEN",)) == "PEN"
    assert only_currency(("PEN", "USD")) is None
    assert only_currency(()) is None


def test_every_fill_of_an_only_currency_is_listed_and_points_at_the_list():
    """Each listed file exists and carries a pointer to `FILLS_AN_ONLY_CURRENCY`, and no
    other file under expense/ does, so removing the fills when the engine takes the only
    currency finds every one."""
    root = Path(__file__).resolve().parents[2]
    listed = {path for path, _what in FILLS_AN_ONLY_CURRENCY}
    for path in listed:
        assert "FILLS_AN_ONLY_CURRENCY" in (root / path).read_text(), path
    pointing = {
        str(f.relative_to(root))
        for f in (root / "expense").rglob("*.py")
        if "FILLS_AN_ONLY_CURRENCY" in f.read_text()
    } - {"expense/currencies.py"}
    assert pointing == listed
