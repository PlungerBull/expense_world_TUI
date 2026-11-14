"""A bank account's Edit form: its number lines, `bank`, `last 4` and `since`.

The lines come after `type`; the save is one `PUT /accounts/{id}` carrying only what
changed, the number's part as `current_number`; emptying `last 4` asks before it removes the
number, and is refused on an account with one number; each refusal lands on the line its key names
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
#: A two-number account whose PEN has an opening balance, and that row.
OPENED = account_with_currencies(
    REPLACED, currencies=[held_currency("PEN", opening_balance_transaction_id="tx-open")]
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


def test_a_first_cards_lines_hints_and_bank_pick():
    async def body(pilot, app, screen):
        assert screen._key == "bank"  # opens on the account's bank
        assert screen.query_one("#bar", Input).value == "BCP" and not screen._suggests("bank")
        await pilot.press("enter")
        assert screen._values["bank"] == "BCP" and screen._key == "last4"
        assert screen._sequence()[:8] == [
            "type",
            "bank",
            "last4",
            "since",
            "new_card",
            "currencies",
            "statement_code",
            "color",
        ]
        assert _summary(screen)[:6] == [
            "type bank read-only",
            "bank BCP",
            "last 4 5678",
            "since first card",
            "new card — (optional)",
            "currencies PEN read-only",
        ]
        assert not {"bank", "last4", "since"} & screen._locked
        _on(screen, "last4")  # the only number: required, never emptied
        assert _hint(screen) == "the card's last 4 digits · enter to go on"
        _on(screen, "since")
        assert _hint(screen) == "YYYY-MM-DD · this card's first day · enter to go on"

    _form(FIRST, body)


def test_a_replaced_cards_lines_and_the_new_card_lines():
    async def body(pilot, app, screen):
        assert screen._sequence()[:8] == [
            "type",
            "bank",
            "last4",
            "since",
            "cards_before",
            "new_card",
            "currencies",
            "statement_code",
        ]
        assert _summary(screen)[:7] == [
            "type bank read-only",
            "bank BCP",
            "last 4 5678",
            "since 2026-08-15",
            "cards before 1234 until 2026-08-14",
            "new card — (optional)",
            "currencies PEN read-only",
        ]
        _on(screen, "last4")  # another number stays: emptying it removes the current one
        assert _hint(screen) == "the card's last 4 digits · empty removes it · enter to go on"
        _on(screen, "since")
        assert screen.query_one("#bar", Input).value == "2026-08-15"
        assert "new_card_from" not in screen._sequence()
        _on(screen, "new_card")
        assert _hint(screen) == "optional · the replacement card's last 4 digits · enter to go on"
        _type(screen, "new_card", "9012")
        seq = screen._sequence()
        assert seq[seq.index("new_card") + 1] == "new_card_from"
        assert "new card from — *" in _summary(screen)
        assert screen._key == "new_card_from"  # enter went on to it
        assert _hint(screen) == "YYYY-MM-DD · the new card's first day · enter to go on"
        _type(screen, "new_card", "")
        assert "new_card_from" not in screen._sequence()

    _form(REPLACED, body)


#: Two earlier numbers, then the current one.
TWICE = account_with_currencies(
    FIRST,
    numbers=[
        {"last4": "1111", "start_date": None, "end_date": "2026-03-31"},
        {"last4": "1234", "start_date": "2026-04-01", "end_date": "2026-08-14"},
        {"last4": "5678", "start_date": "2026-08-15", "end_date": None},
    ],
)


def test_cards_before_lists_every_earlier_number_oldest_first():
    async def body(pilot, app, screen):
        assert "cards before 1111 until 2026-03-31 · 1234 until 2026-08-14" in _summary(screen)
        assert "cards_before" in screen._locked

    _form(TWICE, body)


def test_with_no_number_there_is_no_since_and_no_new_card_line():
    async def body(pilot, app, screen):
        assert screen._sequence()[:4] == ["type", "bank", "last4", "currencies"]
        assert "last 4 — *" in _summary(screen)

    _form(NUMBERLESS, body)


def test_last_4_on_an_account_with_one_number_is_required_and_nothing_is_sent_or_asked(
    fake_client, monkeypatch
):
    notes: list[str] = []
    monkeypatch.setattr(
        EditAccountScreen, "notify", lambda self, message, **kw: notes.append(message)
    )

    async def body(pilot, app, screen):
        _type(screen, "last4", "")
        assert screen._key == "last4" and notes == ["Last 4 is required."]
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.screen is screen  # no question to remove the only number

    _form(FIRST, body)
    assert fake_client.requests == []


def test_a_persons_form_has_none_of_the_number_lines():
    async def body(pilot, app, screen):
        assert screen._sequence()[:3] == ["type", "name", "currencies"]

    _form(PERSON, body)


# ---- the save: one PUT, only what changed ----------------------------------------


def _typed(*pairs):
    def edit(screen):
        for key, text in pairs:
            _type(screen, key, text)

    return edit


def _first_card_reads_first_card(screen):
    _type(screen, "since", "")
    assert "since first card" in _summary(screen)


_NEW = {"last4": "9012", "start_date": "2026-09-01"}
_NEW_CARD = (("new_card", "9012"), ("new_card_from", "2026-09-01"))


@pytest.mark.parametrize(
    ("record", "edit", "body"),
    [
        (REPLACED, lambda screen: None, {}),
        (FIRST, _typed(("bank", "BBVA")), {"bank_code": "BBVA"}),
        (REPLACED, _typed(("last4", "9012")), {"current_number": {"last4": "9012"}}),
        (
            REPLACED,
            _typed(("last4", "9012"), ("since", "2026-08-20")),
            {"current_number": {"last4": "9012", "start_date": "2026-08-20"}},
        ),
        # a day typed on a first number goes for the engine to judge
        (FIRST, _typed(("since", "2026-08-20")), {"current_number": {"start_date": "2026-08-20"}}),
        (NUMBERLESS, _typed(("last4", "5678")), {"current_number": {"last4": "5678"}}),
        (REPLACED, _typed(("since", "")), {"current_number": {"start_date": None}}),
        (FIRST, _first_card_reads_first_card, {}),
        (
            REPLACED,
            _typed(*_NEW_CARD, ("color", "green")),
            {"color": "#5ab87a", "new_number": _NEW},
        ),
        (
            REPLACED,
            _typed(("last4", "7777"), *_NEW_CARD),
            {"current_number": {"last4": "7777"}, "new_number": _NEW},
        ),
    ],
    ids=[
        "nothing-changed",
        "bank",
        "digits",
        "digits-and-since",
        "since-on-a-first-number",
        "first-number",
        "since-emptied",
        "since-emptied-on-a-first-number",
        "replacement-with-colour",
        "replacement-with-digits",
    ],
)
def test_the_save_sends_one_put_with_only_what_changed(fake_client, record, edit, body):
    assert _save(record, fake_client, edit) == body


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


def test_the_question_names_the_number_and_y_sends_it_removed(fake_client):
    asked = _remove(REPLACED, fake_client, "y")
    assert asked == {
        "title": "Remove card 5678 from BCP-5678?",
        "message": "1234 is its number again. No screen can bring 5678 back.",
    }
    assert fake_client.puts == [("/accounts/acc-bcp", {"current_number": None})]


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


@pytest.mark.parametrize("answer", ["escape", "enter"])
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
        ("bank_code", "INVALID_FORMAT", 422, "bank", ("bank", "IB")),
        ("current_number.last4", "NAME_EXISTS", 409, "last4", ("last4", "9012")),
        ("current_number", "NUMBER_IN_COMPLETED_STATEMENT", 409, "last4", ("last4", "9012")),
        (
            "current_number.start_date",
            "NUMBER_START_NOT_LATER",
            422,
            "since",
            ("since", "2026-08-01"),
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


# ---- a replacement card ---------------------------------------------------


def test_a_replacement_with_a_removal_sends_both_after_the_question(fake_client):
    async def body(pilot, app, screen):
        _type(screen, "last4", "")
        _type(screen, "new_card", "9012")
        _type(screen, "new_card_from", "2026-09-01")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(REPLACED, body)
    assert fake_client.puts == [
        (
            "/accounts/acc-bcp",
            {
                "current_number": None,
                "new_number": {"last4": "9012", "start_date": "2026-09-01"},
            },
        )
    ]


def test_new_card_without_its_day_says_so_on_enter_and_on_save_and_sends_nothing(
    fake_client, monkeypatch
):
    notes: list[str] = []
    monkeypatch.setattr(
        EditAccountScreen, "notify", lambda self, message, **kw: notes.append(message)
    )

    async def body(pilot, app, screen):
        _type(screen, "new_card", "9012")
        _type(screen, "new_card_from", "")  # enter on the empty day stays on it
        assert screen._key == "new_card_from"
        assert notes == ["New card from is required."]
        _on(screen, "color")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert screen.is_attached

    _form(REPLACED, body)
    assert fake_client.requests == []
    assert notes == ["New card from is required."] * 2


@pytest.mark.parametrize(
    "key, code, status, line",
    [
        ("new_number.last4", "INVALID_FORMAT", 422, "new_card"),
        ("new_number.start_date", "NUMBER_START_NOT_LATER", 422, "new_card_from"),
        ("new_number", "NUMBER_IN_COMPLETED_STATEMENT", 409, "new_card_from"),
        ("new_number", "NO_NUMBER", 422, "new_card"),
    ],
)
def test_a_replacements_refusal_lands_on_its_line_holding_what_was_typed(
    fake_client, key, code, status, line
):
    fake_client.errors["PUT"] = _refusal(key, code, status)

    async def body(pilot, app, screen):
        _type(screen, "new_card", "9012")
        _type(screen, "new_card_from", "2026-09-01")
        _on(screen, "color")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen) is not None)
        assert "The engine's words." in refusal_block(screen)
        assert screen._key == line
        assert screen.query_one("#bar", Input).value == screen._values[line]
        assert screen._values["new_card"] == "9012"
        assert screen._values["new_card_from"] == "2026-09-01"

    _form(REPLACED, body)
