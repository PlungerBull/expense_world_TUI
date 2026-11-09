"""A bank account's Edit form: its number lines, `bank`, `last 4` and `since`.

The lines come after `type`; the save is one `PUT /accounts/{id}` carrying only what
changed, the number's part as `current_number`; emptying `last 4` asks before it removes the
number; each refusal lands on the line its key names
(contract: PUT /v1/accounts/{account_id}, "The numbers").
"""

import pytest
from textual.widgets import Input, Static

from expense.errors import EngineError
from expense.tui.screens.create_forms import EditAccountScreen
from expense.tui.screens.modals import ConfirmModal
from tests.unit.helpers import (
    ENGINE_CURRENCIES,
    account_with_currencies,
    held_currency,
    refusal_block,
    render_text,
    run_app,
    wait_for,
)

BANKS = ["BCP", "BBVA"]
#: One number, the first: no start day.
FIRST = account_with_currencies(id="acc-bcp", name="BCP-5678", color="#4a90d9")
#: A replacement card: 1234 until 2026-08-14, then 5678 from 2026-08-15 (the current one).
REPLACED = account_with_currencies(
    FIRST,
    numbers=[
        {"last4": "1234", "start_date": None, "end_date": "2026-08-14"},
        {"last4": "5678", "start_date": "2026-08-15", "end_date": None},
    ],
)
#: An account with no number: named by its bank alone.
NUMBERLESS = account_with_currencies(FIRST, name="BCP", numbers=[])
PERSON = account_with_currencies(FIRST, id="acc-eli", name="Eliana", kind="person", numbers=[])
#: An account whose PEN has an opening balance, and that row.
OPENED = account_with_currencies(
    FIRST, currencies=[held_currency("PEN", opening_balance_transaction_id="tx-open")]
)
OPENING_ROW = {"id": "tx-open", "amount_cents": -320000, "day": "2026-01-01"}


def _on(screen, key):
    screen._current = screen._sequence().index(key)
    screen._refresh_bar()
    screen._refresh_view()


def _type(screen, key, text):
    """Land on `key`, type `text`, press enter."""
    _on(screen, key)
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


def _summary(screen) -> list[str]:
    text = render_text(screen._summary_renderable(), width=100)
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _hint(screen) -> str:
    return str(screen.query_one("#hint", Static).content)


def _form(record, body):
    async def scenario(pilot, app):
        screen = EditAccountScreen(record, ENGINE_CURRENCIES, BANKS)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await wait_for(pilot, lambda: not screen._openings_loading)
        return await body(pilot, app, screen)

    return run_app(scenario)


def _save(record, fake_client, edit):
    """Open `record`'s form, run `edit(screen)`, save; the one `PUT`'s body."""

    async def body(pilot, app, screen):
        edit(screen)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(record, body)
    assert fake_client.requests == [("PUT", f"/accounts/{record['id']}")]
    return fake_client.puts[0][1]


# ---- the lines -----------------------------------------------------------------


def test_a_bank_accounts_lines_in_order_with_first_card():
    async def body(pilot, app, screen):
        assert screen._sequence()[:7] == [
            "type",
            "bank",
            "last4",
            "since",
            "currencies",
            "statement_code",
            "color",
        ]
        assert _summary(screen)[:5] == [
            "type bank read-only",
            "bank BCP",
            "last 4 5678",
            "since first card",
            "currencies PEN read-only",
        ]
        assert not {"bank", "last4", "since"} & screen._locked

    _form(FIRST, body)


def test_since_holds_a_later_numbers_first_day():
    async def body(pilot, app, screen):
        assert "since 2026-08-15" in _summary(screen)
        _on(screen, "since")
        assert screen.query_one("#bar", Input).value == "2026-08-15"

    _form(REPLACED, body)


def test_with_no_number_since_is_not_on_the_form():
    async def body(pilot, app, screen):
        assert "since" not in screen._sequence()
        assert screen._sequence()[:4] == ["type", "bank", "last4", "currencies"]
        assert "last 4 — (optional)" in _summary(screen)

    _form(NUMBERLESS, body)


def test_a_persons_form_has_none_of_the_number_lines():
    async def body(pilot, app, screen):
        assert screen._sequence()[:3] == ["type", "name", "currencies"]

    _form(PERSON, body)


def test_the_hints_of_last_4_and_since():
    async def body(pilot, app, screen):
        _on(screen, "last4")
        assert _hint(screen) == "the card's last 4 digits · empty removes it · enter to go on"
        _on(screen, "since")
        assert _hint(screen) == "YYYY-MM-DD · this card's first day · enter to go on"

    _form(FIRST, body)


def test_bank_opens_on_the_accounts_bank_and_enter_keeps_it(fake_client):
    async def body(pilot, app, screen):
        assert screen._key == "bank"
        assert screen._suggestions[screen._suggest_idx][0] == "BCP"
        await pilot.press("enter")
        assert screen._values["bank"] == "BCP"
        assert screen._key == "last4"

    _form(FIRST, body)


# ---- the save: one PUT, only what changed ----------------------------------------


def test_nothing_changed_sends_an_empty_body(fake_client):
    assert _save(REPLACED, fake_client, lambda screen: None) == {}


def test_a_bank_change_sends_bank_code(fake_client):
    body = _save(FIRST, fake_client, lambda screen: _type(screen, "bank", "BBVA"))
    assert body == {"bank_code": "BBVA"}


def test_fixed_digits_send_current_number_last4(fake_client):
    body = _save(REPLACED, fake_client, lambda screen: _type(screen, "last4", "9012"))
    assert body == {"current_number": {"last4": "9012"}}


def test_a_moved_since_sends_a_bare_start_date(fake_client):
    body = _save(REPLACED, fake_client, lambda screen: _type(screen, "since", "2026-08-20"))
    assert body == {"current_number": {"start_date": "2026-08-20"}}


def test_digits_and_since_share_one_current_number(fake_client):
    def edit(screen):
        _type(screen, "last4", "9012")
        _type(screen, "since", "2026-08-20")

    assert _save(REPLACED, fake_client, edit) == {
        "current_number": {"last4": "9012", "start_date": "2026-08-20"}
    }


def test_a_first_number_on_a_numberless_account_sends_no_start(fake_client):
    body = _save(NUMBERLESS, fake_client, lambda screen: _type(screen, "last4", "5678"))
    assert body == {"current_number": {"last4": "5678"}}


def test_a_numberless_account_left_empty_sends_nothing(fake_client):
    assert _save(NUMBERLESS, fake_client, lambda screen: _type(screen, "last4", "")) == {}


def test_a_day_typed_on_a_first_number_is_sent_for_the_engine_to_judge(fake_client):
    body = _save(FIRST, fake_client, lambda screen: _type(screen, "since", "2026-08-20"))
    assert body == {"current_number": {"start_date": "2026-08-20"}}


def test_since_emptied_on_a_later_number_sends_null(fake_client):
    body = _save(REPLACED, fake_client, lambda screen: _type(screen, "since", ""))
    assert body == {"current_number": {"start_date": None}}


def test_since_emptied_on_a_first_number_reads_first_card_and_sends_nothing(fake_client):
    def edit(screen):
        _type(screen, "since", "")
        assert "since first card" in _summary(screen)

    assert _save(FIRST, fake_client, edit) == {}


def test_the_number_changes_ride_with_the_other_fields(fake_client):
    def edit(screen):
        _type(screen, "bank", "BBVA")
        _type(screen, "last4", "9012")
        _type(screen, "color", "green")

    assert _save(REPLACED, fake_client, edit) == {
        "bank_code": "BBVA",
        "current_number": {"last4": "9012"},
        "color": "#5ab87a",
    }


# ---- removing a number -------------------------------------------------------------


def _remove(record, fake_client, answer):
    """Empty `last 4`, save, answer the question with `answer`; what was asked."""
    asked: dict = {}

    async def body(pilot, app, screen):
        _type(screen, "last4", "")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert fake_client.requests == []  # asked before anything is sent
        asked["title"], asked["message"] = app.screen._title, app.screen._message
        await pilot.press(answer)
        await pilot.pause()
        if answer == "y":
            await wait_for(pilot, lambda: not screen.is_attached)
        else:
            assert app.screen is screen  # back on the form, the line still empty
            assert "last4" not in screen._values

    _form(record, body)
    return asked


def test_the_question_names_the_number_before_it(fake_client):
    assert _remove(REPLACED, fake_client, "y") == {
        "title": "Remove card 5678 from BCP-5678?",
        "message": "1234 is its number again. No screen can bring 5678 back.",
    }


def test_the_question_with_no_number_before_it(fake_client):
    assert _remove(FIRST, fake_client, "y") == {
        "title": "Remove card 5678 from BCP-5678?",
        "message": "No screen can bring 5678 back.",
    }


def test_a_removal_drops_a_changed_since(fake_client):
    """The day belonged to the number removed: `null` carries no `start_date`."""

    async def body(pilot, app, screen):
        _type(screen, "since", "2026-08-20")
        _type(screen, "last4", "")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(REPLACED, body)
    assert fake_client.puts == [("/accounts/acc-bcp", {"current_number": None})]


def test_y_sends_current_number_null_in_one_put(fake_client):
    _remove(REPLACED, fake_client, "y")
    assert fake_client.puts == [("/accounts/acc-bcp", {"current_number": None})]


@pytest.mark.parametrize("answer", ["n", "escape", "enter"])
def test_any_other_answer_sends_nothing(fake_client, answer):
    _remove(REPLACED, fake_client, answer)
    assert fake_client.requests == []


def test_a_removal_and_a_cleared_opening_ask_one_after_the_other(fake_client, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_transaction", lambda cfg, tid, **kw: OPENING_ROW)
    titles: list[str] = []

    async def body(pilot, app, screen):
        _type(screen, "last4", "")
        _type(screen, "opening:PEN", "")
        await pilot.press("ctrl+s")
        for _ in range(2):
            await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
            titles.append(app.screen._title)
            assert fake_client.requests == []
            await pilot.press("y")
            await pilot.pause()
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(OPENED, body)
    assert titles == ["Remove card 5678 from BCP-5678?", "Delete this opening balance?"]
    assert fake_client.puts == [
        ("/accounts/acc-bcp", {"current_number": None, "opening_balances": {"PEN": None}})
    ]


def test_no_to_the_first_question_asks_no_second_and_sends_nothing(fake_client, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_transaction", lambda cfg, tid, **kw: OPENING_ROW)

    async def body(pilot, app, screen):
        _type(screen, "last4", "")
        _type(screen, "opening:PEN", "")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("n")
        await pilot.pause()
        assert app.screen is screen

    _form(OPENED, body)
    assert fake_client.requests == []


# ---- refusals land on their line ---------------------------------------------------


def _refusal(key: str, code: str, status: int) -> EngineError:
    words = "The engine's words."
    name = "CONFLICT" if status == 409 else "VALIDATION_ERROR"
    return EngineError(name, "Validation failed.", {key: words}, status, {}, {key: code})


@pytest.mark.parametrize(
    "key, code, status, line, edit",
    [
        ("bank_code", "UNSUPPORTED_VALUE", 422, "bank", ("bank", "BBVA")),
        ("current_number.last4", "NAME_EXISTS", 409, "last4", ("last4", "9012")),
        ("current_number.last4", "INVALID_FORMAT", 422, "last4", ("last4", "9012")),
        ("current_number", "NUMBER_IN_COMPLETED_STATEMENT", 409, "last4", ("last4", "9012")),
        ("current_number", "NO_NUMBER", 422, "last4", ("last4", "9012")),
        (
            "current_number.start_date",
            "NUMBER_START_NOT_LATER",
            422,
            "since",
            ("since", "2026-08-01"),
        ),
        (
            "current_number.start_date",
            "FIRST_NUMBER_HAS_NO_START",
            422,
            "since",
            ("since", "2026-08-20"),
        ),
    ],
)
def test_a_refusal_lands_on_its_line_holding_what_was_typed(
    fake_client, key, code, status, line, edit
):
    fake_client.errors["PUT"] = _refusal(key, code, status)

    async def body(pilot, app, screen):
        _type(screen, *edit)
        _on(screen, "color")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen) is not None)
        assert "The engine's words." in refusal_block(screen)
        assert screen._key == line
        if line != "bank":  # a choice line's bar is empty: its pick shows in the summary
            assert screen.query_one("#bar", Input).value == edit[1]
        assert screen._values[edit[0]] == edit[1]

    _form(REPLACED, body)


def test_a_removal_refused_lands_on_last_4_empty(fake_client):
    fake_client.errors["PUT"] = _refusal("current_number", "NUMBER_IN_COMPLETED_STATEMENT", 409)

    async def body(pilot, app, screen):
        _type(screen, "last4", "")
        _on(screen, "color")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: refusal_block(screen) is not None)
        assert screen._key == "last4"
        assert screen.query_one("#bar", Input).value == ""

    _form(REPLACED, body)
