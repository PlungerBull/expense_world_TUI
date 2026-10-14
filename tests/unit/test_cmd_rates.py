import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from expense.commands.rates_cmd import app as rates_app
from expense.commands.rates_cmd import format_rate
from expense.currencies import RATE_SCALE
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, make_cli_app, strip_panel, window_page

cli_app = make_cli_app(rates_app, "rates")

runner = CliRunner()


# The engine sends `rate_e8: int` — the rate x RATE_SCALE (contract: GET /v1/exchange-rates).
# 92340000 is 0.9234, which is what the human-mode renderer must still print.
RATE_RESPONSE = {
    "base": "USD",
    "target": "EUR",
    "date": "2026-05-03",
    "rate_e8": 92340000,
}


@respx.mock
def test_get_happy_default_base_and_date(configured):
    route = respx.get(f"{BASE}/v1/exchange-rates").mock(
        return_value=httpx.Response(200, json=RATE_RESPONSE)
    )
    result = runner.invoke(cli_app, ["rates", "get", "--target", "EUR"])
    assert result.exit_code == 0, result.output
    assert "EUR" in result.output
    assert "0.9234" in result.output

    request = route.calls.last.request
    assert request.url.params.get("target") == "EUR"
    # base and date omitted client-side so engine defaults apply
    assert request.url.params.get("base") is None
    assert request.url.params.get("date") is None


@respx.mock
def test_get_explicit_base_and_date(configured):
    route = respx.get(f"{BASE}/v1/exchange-rates").mock(
        return_value=httpx.Response(
            200,
            json={**RATE_RESPONSE, "base": "GBP", "date": "2026-04-01"},
        )
    )
    result = runner.invoke(
        cli_app,
        [
            "rates",
            "get",
            "--target",
            "EUR",
            "--base",
            "GBP",
            "--date",
            "2026-04-01",
        ],
    )
    assert result.exit_code == 0, result.output

    request = route.calls.last.request
    assert request.url.params.get("target") == "EUR"
    assert request.url.params.get("base") == "GBP"
    assert request.url.params.get("date") == "2026-04-01"


@respx.mock
def test_get_json_mode_passthrough(configured):
    respx.get(f"{BASE}/v1/exchange-rates").mock(
        return_value=httpx.Response(200, json=RATE_RESPONSE)
    )
    result = runner.invoke(cli_app, ["rates", "get", "--target", "EUR", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == RATE_RESPONSE


@respx.mock
def test_get_unsupported_currency_surfaces_engine_error(configured):
    """An unsupported code is a 422 field error, not a missing-rate error.

    A bad currency code is field-scoped `VALIDATION_ERROR` on `base`/`target`
    (pinned against the live engine).
    """
    respx.get(f"{BASE}/v1/exchange-rates").mock(
        return_value=error_response(
            422,
            "VALIDATION_ERROR",
            "Invalid currency code.",
            {"target": "'EUR' is not a valid currency code."},
            {"target": "UNSUPPORTED_VALUE"},
        )
    )
    result = runner.invoke(cli_app, ["rates", "get", "--target", "EUR"])
    assert result.exit_code == 1
    assert "VALIDATION_ERROR" in result.output
    assert "target" in result.output


@respx.mock
def test_get_no_rate_for_date_surfaces_not_found(configured):
    """404 now means exactly one thing: supported pair, no rate row on/before the date.

    Verified against the live engine — `fields` is null, so the renderer
    must survive a `fields: null` envelope, not just a missing key.
    """
    respx.get(f"{BASE}/v1/exchange-rates").mock(
        return_value=error_response(404, "NOT_FOUND", "exchange rate for USD->PEN not found.", None)
    )
    result = runner.invoke(cli_app, ["rates", "get", "--target", "PEN", "--date", "2020-01-01"])
    assert result.exit_code == 1
    assert "NOT_FOUND" in result.output


def test_get_target_required(configured):
    """Without --target, Typer should bail before any HTTP call."""
    result = runner.invoke(cli_app, ["rates", "get"])
    assert result.exit_code != 0
    assert "target" in result.output.lower()


HISTORY_RESPONSE = window_page(
    [
        {"base": "USD", "target": "PEN", "rate_date": "2026-07-05", "rate_e8": 360000000},
        {"base": "EUR", "target": "PEN", "rate_date": "2026-07-05", "rate_e8": 460000000},
        {"base": "USD", "target": "PEN", "rate_date": "2026-07-04", "rate_e8": 359000000},
    ],
    date_from="2026-06-05",
    date_to="2026-07-05",
)


@respx.mock
def test_list_renders_table_newest_first(configured):
    route = respx.get(f"{BASE}/v1/exchange-rates/history").mock(
        return_value=httpx.Response(200, json=HISTORY_RESPONSE)
    )
    result = runner.invoke(cli_app, ["rates", "list"])
    assert result.exit_code == 0, result.output
    assert "3.6000" in result.output and "4.6000" in result.output  # 4-decimal display
    # the window's last page: rate days are inclusive, so older starts the day before
    assert "(2026-06-05 → 2026-07-05 · newest first · older: pass --to 2026-06-04)" in (
        result.output
    )
    # bare human list → the 20-row default limit; no window sent, so the engine's applies
    params = route.calls.last.request.url.params
    assert params.get("limit") == "20"
    for gone in ("date", "offset", "date_from", "date_to", "after"):
        assert gone not in params


@respx.mock
def test_list_date_is_a_one_day_window(configured):
    route = respx.get(f"{BASE}/v1/exchange-rates/history").mock(
        return_value=httpx.Response(
            200, json=window_page([], date_from="2026-07-04", date_to="2026-07-04")
        )
    )
    result = runner.invoke(cli_app, ["rates", "list", "--date", "2026-07-04", "--limit", "10"])
    assert result.exit_code == 0, result.output
    # an empty window still says which window it was — never "no history"
    assert "(no rates in this window)" in result.output
    assert "(2026-07-04 → 2026-07-04 · newest first · older: pass --to 2026-07-03)" in (
        result.output
    )
    params = route.calls.last.request.url.params
    assert params.get("date_from") == "2026-07-04"
    assert params.get("date_to") == "2026-07-04"
    assert params.get("limit") == "10"
    assert "date" not in params and "offset" not in params


@respx.mock
def test_list_passes_the_window_and_cursor_through(configured):
    route = respx.get(f"{BASE}/v1/exchange-rates/history").mock(
        return_value=httpx.Response(200, json=HISTORY_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        ["rates", "list", "--from", "2026-01-01", "--to", "2026-03-31", "--after", "c1"],
    )
    assert result.exit_code == 0, result.output
    params = route.calls.last.request.url.params
    assert params.get("date_from") == "2026-01-01"  # plain days, sent unconverted
    assert params.get("date_to") == "2026-03-31"
    assert params.get("after") == "c1"


@pytest.mark.parametrize("extra", [["--from", "2026-07-01"], ["--to", "2026-07-05"]])
def test_list_refuses_date_with_a_range(configured, extra):
    result = runner.invoke(cli_app, ["rates", "list", "--date", "2026-07-04", *extra])
    assert result.exit_code == 2
    assert "--date" in strip_panel(result.output)


def test_list_has_no_offset(configured):
    result = runner.invoke(cli_app, ["rates", "list", "--offset", "5"])
    assert result.exit_code == 2


@respx.mock
def test_list_json_mode_passthrough(configured):
    respx.get(f"{BASE}/v1/exchange-rates/history").mock(
        return_value=httpx.Response(200, json=HISTORY_RESPONSE)
    )
    result = runner.invoke(cli_app, ["rates", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == HISTORY_RESPONSE


# --- format_rate ----------------------------------------------------------
# The engine's wire field is `rate_e8: int` (contract: GET /v1/exchange-rates),
# an integer, never a float. These pin that the CLI side formats it on integers
# — nothing here divides.


def test_format_rate_renders_four_decimals_from_the_scaled_integer():
    assert format_rate(360000000) == "3.6000"
    assert format_rate(335187273) == "3.3519"  # rounds up at the 5th place
    assert format_rate(29834068) == "0.2983"  # the PEN->USD inversion
    assert format_rate(RATE_SCALE) == "1.0000"


def test_format_rate_rounds_half_up_on_integers():
    """Half-up, matching every other rounding decision on the money path.

    Python's round() is banker's rounding and would send the first of these to
    3.3752 — the same class of one-off the engine hit as bug 1.7-round.
    """
    assert format_rate(337515000) == "3.3752"  # exact .5 in the 5th place
    assert format_rate(337525000) == "3.3753"


def test_format_rate_does_no_float_arithmetic():
    """A float on the wire means the engine regressed — show it, do not format it.

    Silently formatting would hide exactly the wire-format drift this field
    change was meant to make visible.
    """
    assert format_rate(3.6) == "3.6"
    assert format_rate(None) == "—"
    assert format_rate(True) == "True"
    assert format_rate("3.6") == "3.6"


def test_format_rate_never_loses_the_low_digits_to_binary():
    """The property the integer path buys: exactness at any magnitude.

    A rate whose scaled form exceeds 2**53 cannot round-trip through a float,
    so this asserts the arithmetic really is integer end to end.
    """
    big = 9_007_199_254_740_993 * (RATE_SCALE // 100_000_000)  # 2**53 + 1
    assert format_rate(big) == "90071992.5474"


@respx.mock
def test_list_says_how_to_reach_the_rest_of_the_window(configured):
    respx.get(f"{BASE}/v1/exchange-rates/history").mock(
        return_value=httpx.Response(200, json={**HISTORY_RESPONSE, "next_cursor": "c2"})
    )
    result = runner.invoke(cli_app, ["rates", "list"])
    assert result.exit_code == 0, result.output
    assert "(2026-06-05 → 2026-07-05 · newest first · more in this window: pass --after c2)" in (
        result.output
    )


@respx.mock
def test_list_surfaces_an_engine_refusal(configured):
    """Rates come from an upstream provider, so this list has a failure mode the
    other lists do not: the engine reached the provider and the provider said no.
    """
    respx.get(f"{BASE}/v1/exchange-rates/history").mock(
        return_value=error_response(502, "UPSTREAM_ERROR", "Rate provider is unavailable.")
    )
    result = runner.invoke(cli_app, ["rates", "list"])
    assert result.exit_code == 1
    assert "UPSTREAM_ERROR" in result.output
    assert "Rate provider is unavailable." in result.output


# A user who has not run first-time setup: the settings do not exist yet, which is
# `SETTINGS_MISSING` (contract: "Error codes"). Both rate reads list it among the codes
# they can return (contract: GET /v1/exchange-rates) (contract: GET /v1/exchange-rates/history).
SETTINGS_MISSING = (
    422,
    "SETTINGS_MISSING",
    "User settings have not been provisioned.",
    {"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
    {"user_settings": "NOT_PROVISIONED"},
)
SETTINGS_MISSING_HUMAN = (
    "Error: SETTINGS_MISSING — User settings have not been provisioned.\n"
    "  user_settings: Must be provisioned via POST /v1/auth/bootstrap.\n"
    "\n"
    "Hint: First-time setup is not done yet. "
    "Open System ▸ Auth & profile and press b.\n"
)


@respx.mock
def test_get_settings_missing_shows_the_error_and_the_setup_hint(configured):
    respx.get(f"{BASE}/v1/exchange-rates").mock(return_value=error_response(*SETTINGS_MISSING))
    result = runner.invoke(cli_app, ["rates", "get", "--target", "PEN"])
    assert result.exit_code == 1
    assert result.output == SETTINGS_MISSING_HUMAN


@respx.mock
def test_list_settings_missing_shows_the_error_and_the_setup_hint(configured):
    respx.get(f"{BASE}/v1/exchange-rates/history").mock(
        return_value=error_response(*SETTINGS_MISSING)
    )
    result = runner.invoke(cli_app, ["rates", "list"])
    assert result.exit_code == 1
    assert result.output == SETTINGS_MISSING_HUMAN


@respx.mock
@pytest.mark.parametrize(
    ("path", "args"),
    [
        ("/v1/exchange-rates", ["rates", "get", "--target", "PEN", "--json"]),
        ("/v1/exchange-rates/history", ["rates", "list", "--json"]),
    ],
)
def test_settings_missing_json_is_the_raw_body_without_the_hint(configured, path, args):
    response = error_response(*SETTINGS_MISSING)
    respx.get(f"{BASE}{path}").mock(return_value=response)
    result = runner.invoke(cli_app, args)
    assert result.exit_code == 1
    assert json.loads(result.stdout) == response.json()
    assert "Hint" not in result.output
