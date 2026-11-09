"""The account form's STATEMENT CODE line, New and Edit.

The line sits after CURRENCIES, on a bank account only, with a hint; emptied and
saved it clears the code, no question; small letters show as capitals while
typing; and every refusal of a code, a taken one (`STATEMENT_CODE_EXISTS`)
included, in the engine's words alone. The code is optional on
`POST /accounts`, set, changed or cleared with `null` on `PUT /accounts/{id}` in the
same write as the name and the colour, and never sent for a person
(contract: "What an account is", "Statement code")
(contract: PUT /v1/accounts/{account_id}, "`statement_code`").
"""

import pytest
from textual import events
from textual.widgets import Input, Static

from expense.errors import EngineError
from expense.tui.screens.create_forms import EditAccountScreen, NewAccountScreen
from expense.tui.screens.modals import ConfirmModal
from tests.unit.helpers import (
    ENGINE_BANKS,
    ENGINE_CURRENCIES,
    account_with_currencies,
    held_currency,
    no_failed_toast,
    refusal_block,
    render_text,
    run_app,
    wait_for,
)

NEW_HINT = "optional · three capital letters, e.g. SIG · enter to go on"
EDIT_HINT = "optional · three capital letters, e.g. SIG · empty clears it · enter to go on"

#: Accounts with the statement code the form's STATEMENT CODE line reads off an
#: account, or null for none.
SIGNATURE = account_with_currencies(
    id="acc-sig", name="Signature Soles", color=None, statement_code="SGI"
)
NO_CODE = account_with_currencies(SIGNATURE, id="acc-sue", name="Sueldo Soles", statement_code=None)
WITH_OPENING = account_with_currencies(
    SIGNATURE, currencies=[held_currency("PEN", opening_balance_transaction_id="tx-open")]
)
ELIANA = account_with_currencies(NO_CODE, id="acc-eli", name="Eliana", kind="person")


def _bar(screen) -> Input:
    return screen.query_one("#bar", Input)


def _hint(screen) -> str:
    return str(screen.query_one("#hint", Static).content)


def _summary(screen) -> str:
    """The summary, one line per field, its spacing squeezed to single spaces."""
    text = render_text(screen._summary_renderable(), width=100)
    return "\n".join(" ".join(line.split()) for line in text.splitlines())


def _on(screen, key):
    screen._current = screen._sequence().index(key)
    screen._refresh_bar()
    screen._refresh_view()


async def _open(pilot, app, screen):
    await app.push_screen(screen)
    await wait_for(pilot, lambda: bool(screen.query("#bar")))


async def _to_code(pilot, screen):
    """A new bank account, typed up to its STATEMENT CODE line."""
    await pilot.press("enter")  # TYPE keeps bank
    await pilot.press("enter", "enter")  # BANK takes BCP, LAST 4 skipped
    await pilot.press(*"PEN", "enter", "enter")  # PEN, then an empty enter goes on
    await pilot.pause()
    assert screen._key == "statement_code"


async def _save(pilot, screen, fake_client):
    await pilot.press("ctrl+s")
    await wait_for(pilot, lambda: fake_client.calls)
    await wait_for(pilot, lambda: not screen.is_attached)


# ---- New ----------------------------------------------------------------------------


def test_new_bank_account_line_sits_after_currencies_and_sends_the_code(fake_client):
    screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        assert screen._sequence() == [
            "type",
            "bank",
            "last4",
            "currencies",
            "statement_code",
            "color",
        ]
        await _to_code(pilot, screen)
        assert str(screen.query_one("#field").content) == "STATEMENT CODE"
        assert _hint(screen) == NEW_HINT
        assert "statement code — (optional)" in _summary(screen)
        await pilot.press(*"SIG", "enter")
        await pilot.pause()
        assert screen._key == "color"
        assert "statement code SIG" in _summary(screen)
        await pilot.press("enter", "enter", "enter")  # COLOR, then the PEN pair: creates
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    path, body = fake_client.posts[0]
    assert path == "/accounts"
    assert body["statement_code"] == "SIG"


def test_new_bank_account_skipped_code_is_left_out_of_the_body(fake_client):
    screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _to_code(pilot, screen)
        await pilot.press(*["enter"] * 4)  # skip the code, COLOR and the PEN pair: creates
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    path, body = fake_client.posts[0]
    assert path == "/accounts" and "statement_code" not in body


def test_a_person_has_no_code_line_and_back_on_bank_it_holds_what_was_typed(fake_client):
    """Typed on bank, then TYPE turned to person: the line leaves the form and
    the person's `POST /accounts` carries no code; back on bank the line returns holding it."""
    screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _to_code(pilot, screen)
        await pilot.press(*"SIG", "enter")
        _on(screen, "type")
        await pilot.press(*"person", "enter")
        await pilot.pause()
        assert screen._sequence() == [
            "type",
            "name",
            "currencies",
            "color",
            "opening:PEN",
            "as_of:PEN",
        ]
        assert "statement code" not in _summary(screen)
        _on(screen, "type")
        await pilot.press(*"bank", "enter")
        await pilot.pause()
        assert "statement code SIG" in _summary(screen)
        _on(screen, "statement_code")
        assert _bar(screen).value == "SIG"
        _on(screen, "type")
        await pilot.press(*"person", "enter", *"Eliana", "enter")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    path, body = fake_client.posts[0]
    assert path == "/accounts" and body["kind"] == "person" and "statement_code" not in body


# ---- capitals while typing -------------------------------------------------------------


def test_small_letters_typed_or_pasted_show_as_capitals_on_the_code_line_only(fake_client):
    screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await pilot.press("enter")  # TYPE keeps bank
        await pilot.press("enter")  # BANK takes BCP
        await pilot.press(*"ab 12")
        assert _bar(screen).value == "ab 12"  # LAST 4 takes what is typed
        await pilot.press("enter", *"PEN", "enter", "enter")
        await pilot.pause()
        await pilot.press(*"sig")
        assert _bar(screen).value == "SIG"
        assert _bar(screen).cursor_position == 3
        await pilot.press("backspace", "backspace", "backspace")
        _bar(screen).post_message(events.Paste("pen"))
        await pilot.pause()
        assert _bar(screen).value == "PEN"
        await pilot.press(*"1")  # no shape check here: the engine judges it
        await pilot.press("enter")
        await pilot.pause()
        assert screen._values["statement_code"] == "PEN1"

    run_app(scenario)


# ---- Edit ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "record", [SIGNATURE, NO_CODE, WITH_OPENING], ids=["code", "no-code", "opening-balance"]
)
def test_edit_hint_says_empty_clears_it_with_or_without_an_opening_balance(record):
    screen = EditAccountScreen(record, ENGINE_CURRENCIES, ENGINE_BANKS)
    assert "statement_code" in screen._sequence()
    assert screen._hint_for("statement_code") == EDIT_HINT
    assert screen._sequence().index("statement_code") == screen._sequence().index("currencies") + 1


def test_edit_on_a_person_has_no_code_line_and_never_sends_one(fake_client):
    screen = EditAccountScreen(ELIANA, ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        assert "statement_code" not in screen._sequence()
        await pilot.press("end", *" Vega", "enter")
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.puts == [("/accounts/acc-eli", {"name": "Eliana Vega"})]


def test_edit_opens_holding_the_code_and_unchanged_does_not_send_it(fake_client):
    screen = EditAccountScreen(SIGNATURE, ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        assert screen._key == "bank"  # a bank account has no NAME line
        _on(screen, "statement_code")
        assert _bar(screen).value == "SGI"
        assert _hint(screen) == EDIT_HINT
        assert "statement code SGI" in _summary(screen)
        await pilot.press("enter")  # the code kept
        _type(screen, "color", "green")  # a colour change, so the save sends
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.puts == [("/accounts/acc-sig", {"color": "#5ab87a"})]


def test_edit_a_changed_code_is_sent(fake_client):
    screen = EditAccountScreen(SIGNATURE, ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _on(screen, "statement_code")
        await pilot.press("backspace", "backspace", "backspace", *"sig", "enter")
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.puts == [("/accounts/acc-sig", {"statement_code": "SIG"})]


def test_edit_a_code_given_to_an_account_without_one_is_sent(fake_client):
    screen = EditAccountScreen(NO_CODE, ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _on(screen, "statement_code")
        assert _bar(screen).value == ""
        await pilot.press(*"pen", "enter")
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.puts == [("/accounts/acc-sue", {"statement_code": "PEN"})]


def test_edit_an_emptied_code_is_sent_as_null_with_no_question(fake_client):
    screen = EditAccountScreen(SIGNATURE, ENGINE_CURRENCIES, ENGINE_BANKS)
    asked: list = []

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _on(screen, "statement_code")
        await pilot.press("backspace", "backspace", "backspace", "enter")
        await pilot.pause()
        assert "statement code — (optional)" in _summary(screen)
        await pilot.press("ctrl+s")
        await pilot.pause()
        asked.extend(s for s in app.screen_stack if isinstance(s, ConfirmModal))
        await wait_for(pilot, lambda: not screen.is_attached)

    run_app(scenario)
    assert asked == []
    assert fake_client.puts == [("/accounts/acc-sig", {"statement_code": None})]


def _type(screen, key, text):
    """Land on `key`, type `text`, press enter."""
    _on(screen, key)
    _bar(screen).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


def test_edit_colour_and_code_go_in_one_put(fake_client):
    screen = EditAccountScreen(SIGNATURE, ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _type(screen, "statement_code", "SIG")
        _type(screen, "color", "green")
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.calls == [
        (
            "PUT",
            "/accounts/acc-sig",
            {"color": "#5ab87a", "statement_code": "SIG"},
        )
    ]


def test_edit_an_emptied_code_rides_in_the_same_put_as_the_colour(fake_client):
    screen = EditAccountScreen(SIGNATURE, ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _type(screen, "statement_code", "")
        _type(screen, "color", "green")
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.calls == [
        (
            "PUT",
            "/accounts/acc-sig",
            {"color": "#5ab87a", "statement_code": None},
        )
    ]


# ---- refusals ------------------------------------------------------------------------

#: A second live account with one code is `409` on `statement_code` (contract:
#: "What an account is", "One account per code"); the contract prints the rule, not
#: the message, so these words are a stand-in.
TAKEN = EngineError(
    "CONFLICT",
    "Another account already has the statement code 'SIG'.",
    {"statement_code": "Must not be a statement code another account has."},
    409,
    {},
    {"statement_code": "STATEMENT_CODE_EXISTS"},
)
_FIELD_WORDS = "stand-in field words"


def _refusal(code: str, reason: str) -> EngineError:
    status = 409 if code == "CONFLICT" else 422
    return EngineError(
        code,
        "Request validation failed.",
        {"statement_code": _FIELD_WORDS},
        status,
        {},
        {"statement_code": reason},
    )


def _engine_words(err: EngineError) -> str:
    field, words = next(iter(err.fields.items()))
    return f"{err.code} — {err.message}\n  {field}: {words}"


def test_a_taken_code_on_edit_shows_the_engines_words_alone(fake_client):
    """The engine's words alone, and the cursor back on the code line with what was typed."""
    fake_client.errors["PUT"] = TAKEN
    screen = EditAccountScreen(NO_CODE, ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _on(screen, "statement_code")
        await pilot.press(*"SIG", "enter")
        _on(screen, "color")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen.is_attached
        assert screen._key == "statement_code" and _bar(screen).value == "SIG"
        assert no_failed_toast(app)
        shown.append(refusal_block(screen))

    shown: list = []
    run_app(scenario, toasts=True)
    assert shown == [f"Failed\n{_engine_words(TAKEN)}"]  # nothing after the engine's words


def test_a_taken_code_on_new_shows_the_engines_words_alone(fake_client):
    fake_client.errors["POST"] = TAKEN
    screen = NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _to_code(pilot, screen)
        await pilot.press(*"SIG", *["enter"] * 4)
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen.is_attached
        assert screen._key == "statement_code" and _bar(screen).value == "SIG"
        assert no_failed_toast(app)
        shown.append(refusal_block(screen))

    shown: list = []
    run_app(scenario, toasts=True)
    assert shown == [f"Failed\n{_engine_words(TAKEN)}"]  # nothing after the engine's words


@pytest.mark.parametrize(
    "refusal",
    [
        _refusal("VALIDATION_ERROR", "INVALID_FORMAT"),
        _refusal("VALIDATION_ERROR", "STATEMENT_MONTH_TAKEN"),
        _refusal("VALIDATION_ERROR", "COMPLETED_STATEMENT_JOINED"),
        _refusal("VALIDATION_ERROR", "PERSON_ACCOUNT"),
    ],
    ids=["shape", "month-taken", "completed-joined", "person"],
)
def test_other_code_refusals_keep_the_engines_words_alone(fake_client, refusal):
    fake_client.errors["PUT"] = refusal
    screen = EditAccountScreen(NO_CODE, ENGINE_CURRENCIES, ENGINE_BANKS)

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _on(screen, "statement_code")
        await pilot.press(*"S1G", "enter")
        _on(screen, "color")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen._key == "statement_code" and _bar(screen).value == "S1G"
        assert no_failed_toast(app)
        shown.append(refusal_block(screen))

    shown: list = []
    run_app(scenario, toasts=True)
    assert shown == [f"Failed\n{_engine_words(refusal)}"]
