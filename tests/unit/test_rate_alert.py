"""The exchange-rate staleness indicator — resolution, fetch, and rendering.

The header shows a `!` when today has no exchange rate of its own, so every
home-currency figure on screen is priced at an older day's rate. There is no
bespoke engine field behind it: `GET /exchange-rates` returns the day you asked
about (`date`) and the day it actually used (`rate_date`), and the whole signal
is `rate_date < date` (contract: GET /v1/exchange-rates, "Staleness").
These lock the three halves that can independently rot: the comparison,
what happens on an engine error, and the render.

The property that matters most here is the *silent* one. Unknown (offline,
unconfigured, pre-fetch, unexpected shape) must render nothing at all. An
indicator that fires when it cannot reach the engine is reporting on the
connection, and one that cries wolf gets ignored on the day it is right.
"""

import httpx
import pytest
import respx
from textual.widgets import Static

import expense.tui.screens.home as home
from expense.reads import fetch_rate_staleness, rate_is_stale
from expense.tui.theme import Palette
from expense.tui.widgets.header import RATE_ALERT_MARK, Breadcrumb, rate_alert
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, render_text, run_app

PALETTE = Palette(success="#7fbf8f", error="#cf8d8d", warning="#d6b878")


def _render(renderable, width=100) -> str:
    return render_text(renderable, width=width)


def _painted(widget) -> str:
    """What a mounted widget actually puts on screen, line by line.

    `Static.render()` returns a Visual wrapper in this Textual version, not the
    renderable handed to `update()`, so printing it yields a repr. Reading the
    rendered strips asserts against the real painted output instead — which is
    the point of these tests: that the mark reaches the screen.
    """
    return "\n".join(widget.render_line(y).text for y in range(widget.size.height))


# ---- rate_is_stale -------------------------------------------------------


@pytest.mark.parametrize(
    ("row", "stale"),
    [
        ({"date": "2026-08-13", "rate_date": "2026-08-11"}, True),  # an older day's row
        ({"date": "2026-08-13", "rate_date": "2026-08-13"}, False),  # the day itself
        ({"date": "2026-08-01", "rate_date": "2026-08-13"}, False),  # ahead is not staleness
        # a shape change must go quiet rather than light the header permanently
        ({"date": "2026-08-13"}, None),
        ({"rate_date": "2026-08-13"}, None),
        ({}, None),
        ({"date": "2026-08-13", "rate_date": None}, None),
    ],
)
def test_a_rate_is_stale_only_when_an_older_days_row_answered(row, stale):
    assert rate_is_stale(row) is stale


# ---- fetch_rate_staleness ------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "stale"),
    [
        (httpx.Response(200, json={"date": "2026-08-13", "rate_date": "2026-08-11"}), True),
        # 404 is the same condition at its extreme: nothing on or before today
        (error_response(404, "NOT_FOUND", "no rate", None), True),
        # a 422 is a question about the request, not an answer about the rate
        (
            error_response(
                422,
                "VALIDATION_ERROR",
                "bad",
                {"target": "'XXX' is not a valid currency code."},
                {"target": "UNSUPPORTED_VALUE"},
            ),
            None,
        ),
    ],
    ids=["carried-forward", "no-rate", "other-refusal"],
)
@respx.mock
def test_fetch_reads_staleness_off_the_engines_answer(configured, answer, stale):
    from expense import config as config_module

    respx.get(f"{BASE}/v1/exchange-rates").mock(return_value=answer)
    assert fetch_rate_staleness(config_module.ensure_loaded(), target="PEN") is stale


# ---- rate_alert ----------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "palette", "mark"),
    [
        (True, PALETTE, RATE_ALERT_MARK),
        (True, None, RATE_ALERT_MARK),
        (False, PALETTE, ""),
        (None, PALETTE, ""),
    ],
)
def test_alert_is_the_mark_only_when_stale(state, palette, mark):
    """No palette is the Breadcrumb outside a running app."""
    assert rate_alert(state, palette).plain == mark


@pytest.mark.parametrize(
    ("month", "state", "marked"),
    [
        ("September 2026", True, True),
        ("September 2026", False, False),
        ("September 2026", None, False),
        (None, True, True),  # the two fetches race: no month yet
    ],
)
def test_home_header_shows_the_mark_beside_the_month(month, state, marked):
    out = _render(home._build_header(month, PALETTE, state))
    assert (RATE_ALERT_MARK in out) is marked
    assert month is None or month in out, "the alert must not displace the month"


def test_alert_takes_the_pending_style_from_the_palette():
    """Warning, not error: a carried-forward rate is the engine's designed
    fallback, so the figures are roughly right. Palette-sourced, never a literal
    style — the no-literal-color guard in test_tui_theme.py depends on it.

    The emphasis lives in the palette, not here: the palette makes the
    pending role `bold` with no colour, so a call site that prepended its own
    "bold " would render "bold bold". Asserted with the REAL palette, since the
    synthetic one above is a plain colour triple.
    """
    from expense.tui.theme import PALETTE

    assert str(rate_alert(True, PALETTE).style) == PALETTE.warning  # palette-sourced
    assert str(rate_alert(True, PALETTE).style) == "bold"  # ...and it is emphasis


# ---- the two header hosts ------------------------------------------------


def test_breadcrumb_outside_an_app_renders_the_trail_and_no_mark():
    """`self.app` raises when unmounted, so the widget must degrade to silence
    rather than to a traceback — this is also what lets it be unit-tested."""
    out = _render(Breadcrumb(("System", "Config")).render())
    assert "System" in out and "Config" in out
    assert RATE_ALERT_MARK not in out


# ---- the app wiring, end to end ------------------------------------------
#
# The two tests above cover the render given a value; these cover the value
# reaching the render. That wiring is the part that rots silently — a screen
# pushed after the startup fetch reads `app.rate_stale` itself, while one
# already on screen has to be told, and those are two different code paths.


def test_breadcrumb_mounted_in_the_app_follows_rate_stale():
    async def scenario(pilot, app):
        await pilot.pause()
        crumb = Breadcrumb(("System", "Config"))
        await app.screen.mount(crumb)
        await pilot.pause()

        # Unconfigured in tests, so the startup fetch bails and leaves None.
        assert app.rate_stale is None
        assert RATE_ALERT_MARK not in _painted(crumb)

        app._set_rate_stale(True)
        await pilot.pause()
        assert RATE_ALERT_MARK in _painted(crumb)

    run_app(scenario)


def test_home_header_repaints_when_the_rate_status_lands():
    """The `repaint_header` hook. Home builds its own header instead of using
    Breadcrumb, so the app's blanket breadcrumb refresh does not reach it — and
    home is the first screen you see, so missing this means the `!` only ever
    appears after navigating somewhere else."""

    async def scenario(pilot, app):
        await pilot.pause()
        brand = app.query_one("#brand", Static)
        assert RATE_ALERT_MARK not in _painted(brand)

        app._set_rate_stale(True)
        await pilot.pause()
        assert RATE_ALERT_MARK in _painted(brand)

    run_app(scenario)


@respx.mock
def test_startup_fetch_is_silent_before_first_time_setup(configured):
    """A user whose settings do not exist yet gets `SETTINGS_MISSING` from the rate
    read (contract: GET /v1/exchange-rates). That is a question about the account,
    not an answer about the rate: no mark, no toast, and the app keeps running."""
    from expense import config as config_module

    cfg = config_module.ensure_loaded()
    cfg.main_currency = "PEN"
    config_module.save(cfg)

    refusal = error_response(
        422,
        "SETTINGS_MISSING",
        "User settings have not been provisioned.",
        {"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
        {"user_settings": "NOT_PROVISIONED"},
    )
    rate = respx.get(f"{BASE}/v1/exchange-rates").mock(return_value=refusal)
    respx.route().mock(return_value=refusal)

    async def scenario(pilot, app):
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert rate.called
        assert app.rate_stale is None
        assert not list(app._notifications)
        assert app.is_running

    run_app(scenario)


def test_a_crumb_on_a_pushed_screen_is_repainted():
    """A section screen pushed over home: `app.query` does not reach a pushed screen,
    so the rate landing while one is open must walk the screen stack."""
    from expense.tui.screens.statements import StatementsScreen
    from tests.unit.helpers import screen_lines

    async def scenario(pilot, app):
        await app.push_screen(StatementsScreen())
        await pilot.pause()
        assert RATE_ALERT_MARK not in screen_lines(app)[0]
        app._set_rate_stale(True)
        await pilot.pause()
        assert screen_lines(app)[0].endswith(RATE_ALERT_MARK)

    run_app(scenario)
