"""A form's refused save: the engine's words in a block under the form (`FormScreen`),
never a `Failed` toast; it stays until the next key, and that key does its usual job.

Driven with real keys through the app against `FakeClient`. One test per kind of form
that saves through `FormScreen._failed`: a single-line create form, a create form of
several lines, an Edit form of the Manage screens, a Statements form (with the
cursor landing on the line the refusal names), and the half-saved account. The bank
line's Edit form and Setup show their refusal under their own lines instead
(`test_tui_edit_form.py`, `test_tui_setup.py`).
"""

from textual.widgets import Input, Static

from expense.errors import EngineError, format_error
from expense.tui.screens.create_forms import (
    EditAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from expense.tui.screens.statements import NewStatementScreen
from tests.unit.helpers import (
    ENGINE_CURRENCIES,
    account_with_currencies,
    held_currency,
    no_failed_toast,
    run_app,
    screen_lines,
    wait_for,
)

TAKEN = EngineError("CONFLICT", "that name is taken", None, 409, {})


def _block(screen) -> Static:
    return screen.query_one("#refusal", Static)


def _words(app) -> list[str]:
    """The block's lines as drawn: what follows each `▌ ` on the screen."""
    return [line.split("▌ ", 1)[1] for line in screen_lines(app) if "▌ " in line]


async def _refused(pilot, screen) -> None:
    await wait_for(
        pilot, lambda: _block(screen).display and not screen._submitting, message="no block"
    )
    await pilot.pause()


def test_a_single_line_form_shows_the_refusal_as_a_block_not_a_toast(fake_client):
    fake_client.errors["POST"] = TAKEN

    async def scenario(pilot, app):
        screen = NewHashtagScreen()
        await app.push_screen(screen)
        assert not _block(screen).display  # nothing refused yet: no block, no bar
        await pilot.press(*"groceries", "enter")  # the only line: enter saves
        await _refused(pilot, screen)
        assert _words(app) == ["Failed", format_error(TAKEN)]
        assert no_failed_toast(app)
        assert screen._values["name"] == "groceries"  # what was typed is kept
        assert screen.query_one("#bar", Input).value == "groceries"
        # the next key does its usual job, and the block goes
        await pilot.press("x")
        assert not _block(screen).display
        assert screen.query_one("#bar", Input).value == "groceriesx"
        assert _words(app) == []

    run_app(scenario, toasts=True)


def test_esc_with_a_block_up_still_cancels(fake_client):
    fake_client.errors["POST"] = TAKEN

    async def scenario(pilot, app):
        screen = NewHashtagScreen()
        await app.push_screen(screen)
        await pilot.press(*"groceries", "enter")  # the only line: enter saves
        await _refused(pilot, screen)
        await pilot.press("escape")
        await wait_for(pilot, lambda: not screen.is_attached, message="esc did not cancel")

    run_app(scenario)


def test_a_create_form_of_several_lines_keeps_what_was_typed_and_a_tab_clears_the_block(
    fake_client,
):
    err = EngineError(
        "VALIDATION_ERROR", "Request validation failed.", {"color": "Pick a swatch."}, 422, {}
    )
    fake_client.errors["POST"] = err

    async def scenario(pilot, app):
        screen = NewCategoryScreen()
        await app.push_screen(screen)
        await pilot.press(*"Mascotas", "enter", "ctrl+s")
        await _refused(pilot, screen)
        assert _words(app)[0] == "Failed"
        assert "VALIDATION_ERROR — Request validation failed." in _words(app)[1]
        assert screen._values["name"] == "Mascotas"
        assert no_failed_toast(app)
        await pilot.press("tab")  # a key that types nothing also clears it
        assert not _block(screen).display

    run_app(scenario, toasts=True)


def test_an_edit_form_shows_its_refusal_as_a_block_not_a_toast(fake_client):
    fake_client.errors["PUT"] = TAKEN
    person = account_with_currencies(id="abc", name="Eliana", kind="person")

    async def scenario(pilot, app):
        screen = EditAccountScreen(person, ENGINE_CURRENCIES)
        await app.push_screen(screen)
        await pilot.press("ctrl+s")
        await _refused(pilot, screen)
        assert _words(app) == ["Failed", format_error(TAKEN)]
        assert no_failed_toast(app)
        await pilot.press("escape")
        await wait_for(pilot, lambda: not screen.is_attached, message="esc did not cancel")

    run_app(scenario, toasts=True)


def _visa() -> NewStatementScreen:
    return NewStatementScreen(
        account_id="v1", account_name="Visa BCP", currencies=("PEN", "USD"), code="VIS"
    )


def test_a_statements_form_lands_on_the_refused_line_and_the_block_fits_80_by_24(fake_client):
    field = "USD has -30.98 at the statement's start, and the statement holds no balances for it."
    err = EngineError(
        "VALIDATION_ERROR",
        "Every currency with money at the start needs balances in the statement.",
        {"balances.USD": field},
        422,
        {},
        reasons={"balances.USD": "MONEY_AT_START_NOT_COVERED"},
    )
    fake_client.errors["POST"] = err

    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        assert (screen.size.width, screen.size.height) == (80, 24)
        for value in ("Noviembre 2026", "2026-10-26", "2026-11-25"):
            screen.query_one("#bar", Input).value = value
            screen.on_input_submitted(None)
        await pilot.press("ctrl+s")
        await _refused(pilot, screen)
        assert screen._key == "begin:USD"  # the cursor is on the refused line
        assert screen._values["name"] == "Noviembre 2026"
        assert no_failed_toast(app)
        words = _words(app)
        assert words[0] == "Failed"
        assert " ".join(words[1:]).startswith("VALIDATION_ERROR — Every currency")
        assert "statement holds no balances for it." in " ".join(words)
        lines = screen_lines(app)
        assert len(lines) == 24
        assert "esc Cancel" in lines[-1]  # the footer is still on screen, nothing cut
        await pilot.press("5")
        assert not _block(screen).display
        assert screen.query_one("#bar", Input).value == "5"

    run_app(scenario, toasts=True)


def test_the_half_saved_account_shows_which_half_went_through_in_the_block(fake_client):
    """The account saved, its opening balance was refused: the same block says which."""
    future = EngineError(
        "VALIDATION_ERROR",
        "Transaction validation failed.",
        {"date": "Must not be in the future."},
        422,
        {},
        {"date": "FUTURE_DATE"},
    )
    fake_client.errors["POST"] = future
    efectivo = account_with_currencies(
        id="acc-efe", name="Efectivo", color=None, currencies=[held_currency("PEN")]
    )

    async def scenario(pilot, app):
        screen = EditAccountScreen(efectivo, ENGINE_CURRENCIES)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")) and not screen._openings_loading)
        for key, text in (
            ("color", "green"),
            ("opening:PEN", "350.00"),
            ("as_of:PEN", "2026-11-01"),
        ):
            screen._current = screen._sequence().index(key)
            screen._refresh_bar()
            screen._refresh_view()
            screen.query_one("#bar", Input).value = text
            screen._recompute(text)
            screen.on_input_submitted(None)
        await _refused(pilot, screen)
        assert screen._key == "as_of:PEN"
        words = _words(app)
        assert words[0] == "Failed"
        assert " ".join(words[1:]).startswith(
            "The account's changes are saved. The PEN opening balance is not:"
        )
        assert "It is still in the form: fix it and save again." in " ".join(words)
        assert no_failed_toast(app)

    run_app(scenario, toasts=True)
