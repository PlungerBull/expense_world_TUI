"""The currency helpers, and the one read of the engine's currency list."""

from pathlib import Path

import httpx
import respx

from expense import config as config_module
from expense.currencies import only_currency
from expense.reads import fetch_currency_codes
from tests.unit.helpers import ENGINE_URL, currencies_answer


def test_the_currency_codes_are_the_engines_list_in_its_order(configured):
    """`GET /currencies` is the one source: a third code the engine lists is read, in the
    engine's order, and an entry without a code is skipped
    (contract: GET /v1/currencies)."""
    cfg = config_module.load()
    with respx.mock() as engine:
        route = engine.get(f"{ENGINE_URL}/v1/currencies")
        route.mock(httpx.Response(200, json=currencies_answer(["EUR", "PEN", "USD"])))
        assert fetch_currency_codes(cfg) == ["EUR", "PEN", "USD"]
        route.mock(httpx.Response(200, json={"items": [{"currency_code": "PEN"}, {}]}))
        assert fetch_currency_codes(cfg) == ["PEN"]


def test_no_copy_of_the_currency_list_lives_in_the_client():
    """No module under expense/ keeps its own list of codes: the `PEN`, `USD` pair
    appears in none (the engine's list is read, `reads.fetch_currency_codes`)."""
    root = Path(__file__).resolve().parents[2] / "expense"
    pair = ('"PEN", "USD"', "('PEN', 'USD')", '"USD", "PEN"')
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if any(p in path.read_text() for p in pair)
    ]
    assert not offenders, offenders


def test_only_currency_is_the_one_code_an_account_holds_and_none_otherwise():
    assert only_currency(("PEN",)) == "PEN"
    assert only_currency(("PEN", "USD")) is None
    assert only_currency(()) is None
