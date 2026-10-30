"""The account form's STATEMENT CODE line, New and Edit.

The screens are docs/mockups/expense-world-statement-code-field.html: 1 A (the
line after CURRENCY, on a bank account only), 1b A (its hint), 2 A (emptied and
saved clears the code, no question), 3·1 B (small letters show as capitals while
typing), 3·2 B (a taken code gets the app's line under the engine's words) and
3·3, 3·4 (the engine's words alone). The code is optional on `POST /accounts`,
set, changed or cleared with `null` on `PUT /accounts/{id}`, and never sent for a
person (contract: "What an account is", "Statement code").
"""

import pytest
from textual import events
from textual.widgets import Input, Static

from expense.errors import EngineError
from expense.tui.screens.create_forms import EditAccountScreen, NewAccountScreen
from expense.tui.screens.modals import ConfirmModal
from tests.unit.helpers import (
    account_with_currencies,
    held_currency,
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
ELIANA = account_with_currencies(NO_CODE, id="acc-eli", name="Eliana", is_person=True)


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
    await pilot.press(*"Signature Soles", "enter")
    await pilot.press(*"PEN", "enter")
    await pilot.pause()
    assert screen._key == "statement_code"


async def _save(pilot, screen, fake_client):
    await pilot.press("ctrl+s")
    await wait_for(pilot, lambda: fake_client.calls)
    await wait_for(pilot, lambda: not screen.is_attached)


# ---- New ----------------------------------------------------------------------------


def test_new_bank_account_line_sits_after_currency_and_sends_the_code(fake_client):
    screen = NewAccountScreen()

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        assert screen._sequence() == ["type", "name", "currency", "statement_code", "color"]
        await _to_code(pilot, screen)
        assert str(screen.query_one("#field").content) == "STATEMENT CODE"
        assert _hint(screen) == NEW_HINT
        assert "statement code — (optional)" in _summary(screen)
        await pilot.press(*"SIG", "enter")
        await pilot.pause()
        assert screen._key == "color"
        assert "statement code SIG" in _summary(screen)
        await pilot.press("enter")  # COLOR, the last line: creates
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    path, body = fake_client.posts[0]
    assert path == "/accounts"
    assert body["statement_code"] == "SIG"


def test_new_bank_account_skipped_code_is_left_out_of_the_body(fake_client):
    screen = NewAccountScreen()

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _to_code(pilot, screen)
        await pilot.press("enter", "enter")  # skip the code, then COLOR creates
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    path, body = fake_client.posts[0]
    assert path == "/accounts" and "statement_code" not in body


def test_a_person_has_no_code_line_and_back_on_bank_it_holds_what_was_typed(fake_client):
    """Typed on bank, then TYPE turned to person: the line leaves the form and
    the person's `POST /accounts` carries no code; back on bank the line returns holding it."""
    screen = NewAccountScreen()

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _to_code(pilot, screen)
        await pilot.press(*"SIG", "enter")
        _on(screen, "type")
        await pilot.press(*"person", "enter")
        await pilot.pause()
        assert screen._sequence() == ["type", "name", "currency", "color"]
        assert "statement code" not in _summary(screen)
        _on(screen, "type")
        await pilot.press(*"bank", "enter")
        await pilot.pause()
        assert "statement code SIG" in _summary(screen)
        _on(screen, "statement_code")
        assert _bar(screen).value == "SIG"
        _on(screen, "type")
        await pilot.press(*"person", "enter")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    path, body = fake_client.posts[0]
    assert path == "/accounts" and body["is_person"] is True and "statement_code" not in body


# ---- capitals while typing -------------------------------------------------------------


def test_small_letters_typed_or_pasted_show_as_capitals_on_the_code_line_only(fake_client):
    screen = NewAccountScreen()

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await pilot.press("enter")  # TYPE keeps bank
        await pilot.press(*"Signature soles")
        assert _bar(screen).value == "Signature soles"  # NAME takes what is typed
        await pilot.press("enter", *"PEN", "enter")
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
    screen = EditAccountScreen(record, "PEN")
    assert "statement_code" in screen._sequence()
    assert screen._hint_for("statement_code") == EDIT_HINT
    assert screen._sequence().index("statement_code") == screen._sequence().index("currency") + 1


def test_edit_on_a_person_has_no_code_line_and_never_sends_one(fake_client):
    screen = EditAccountScreen(ELIANA, "PEN")

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        assert "statement_code" not in screen._sequence()
        await pilot.press("end", *" Vega", "enter")
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.puts == [("/accounts/acc-eli", {"name": "Eliana Vega"})]


def test_edit_opens_holding_the_code_and_unchanged_does_not_send_it(fake_client):
    screen = EditAccountScreen(SIGNATURE, "PEN")

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await pilot.press("enter")  # NAME kept
        await pilot.pause()
        assert screen._key == "statement_code"
        assert _bar(screen).value == "SGI"
        assert _hint(screen) == EDIT_HINT
        assert "statement code SGI" in _summary(screen)
        await pilot.press("enter")  # the code kept
        _on(screen, "name")
        await pilot.press("end", *" 2", "enter")  # a name change, so the save sends
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.puts == [("/accounts/acc-sig", {"name": "Signature Soles 2"})]


def test_edit_a_changed_code_is_sent(fake_client):
    screen = EditAccountScreen(SIGNATURE, "PEN")

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _on(screen, "statement_code")
        await pilot.press("backspace", "backspace", "backspace", *"sig", "enter")
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.puts == [
        ("/accounts/acc-sig", {"name": "Signature Soles", "statement_code": "SIG"})
    ]


def test_edit_a_code_given_to_an_account_without_one_is_sent(fake_client):
    screen = EditAccountScreen(NO_CODE, "PEN")

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _on(screen, "statement_code")
        assert _bar(screen).value == ""
        await pilot.press(*"pen", "enter")
        await _save(pilot, screen, fake_client)

    run_app(scenario)
    assert fake_client.puts == [
        ("/accounts/acc-sue", {"name": "Sueldo Soles", "statement_code": "PEN"})
    ]


def test_edit_an_emptied_code_is_sent_as_null_with_no_question(fake_client):
    screen = EditAccountScreen(SIGNATURE, "PEN")
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
    assert fake_client.puts == [
        ("/accounts/acc-sig", {"name": "Signature Soles", "statement_code": None})
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


@pytest.fixture
def notes(monkeypatch):
    seen: list = []

    def notify(self, message, **kw):
        seen.append((message, kw))

    monkeypatch.setattr(NewAccountScreen, "notify", notify)
    monkeypatch.setattr(EditAccountScreen, "notify", notify)
    return seen


def test_a_taken_code_on_edit_shows_the_engines_words_alone(fake_client, notes):
    """3·2 B: the note, and the cursor back on the code line with what was typed."""
    fake_client.errors["PUT"] = TAKEN
    screen = EditAccountScreen(NO_CODE, "PEN")

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _on(screen, "statement_code")
        await pilot.press(*"SIG", "enter")
        _on(screen, "name")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert screen.is_attached
        assert screen._key == "statement_code" and _bar(screen).value == "SIG"

    run_app(scenario)
    message, kw = notes[0]
    assert message == _engine_words(TAKEN)  # nothing after the engine's words
    assert kw.get("title") == "Failed" and kw.get("severity") == "error"


def test_a_taken_code_on_new_shows_the_engines_words_alone(fake_client, notes):
    fake_client.errors["POST"] = TAKEN
    screen = NewAccountScreen()

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        await _to_code(pilot, screen)
        await pilot.press(*"SIG", "enter", "enter")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert screen.is_attached

    run_app(scenario)
    assert notes[0][0] == _engine_words(TAKEN)  # nothing after the engine's words


@pytest.mark.parametrize(
    "refusal",
    [
        _refusal("VALIDATION_ERROR", "INVALID_FORMAT"),
        _refusal("VALIDATION_ERROR", "STATEMENT_MONTH_TAKEN"),
        _refusal("VALIDATION_ERROR", "COMPLETED_STATEMENT_JOINED"),
        _refusal("VALIDATION_ERROR", "PERSON_ACCOUNT"),
    ],
    ids=["shape", "3·4-month-taken", "3·3-completed-joined", "person"],
)
def test_other_code_refusals_keep_the_engines_words_alone(fake_client, notes, refusal):
    fake_client.errors["PUT"] = refusal
    screen = EditAccountScreen(NO_CODE, "PEN")

    async def scenario(pilot, app):
        await _open(pilot, app, screen)
        _on(screen, "statement_code")
        await pilot.press(*"S1G", "enter")
        _on(screen, "name")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert screen._key == "statement_code" and _bar(screen).value == "S1G"

    run_app(scenario)
    assert notes[0][0] == _engine_words(refusal)
