"""The account Edit form's opening balance — the two lines OPENING and AS OF.

The screens are docs/mockups/expense-world-opening-balance.html's; a person's
form is pane A of docs/mockups/expense-world-person-opening-balance.html. The
account names its opening balance by id
(contract: "Bank Accounts", "Opening balance"); the form reads that row signed
with one `GET /transactions/{id}`
(contract: "Base Conventions", "Sign convention — responses") and writes it
through `POST /accounts/{id}/opening-balance`, `PUT /transactions/{id}` and
`DELETE /transactions/{id}`.
"""

import threading

import pytest
from textual.widgets import Input, Static

from expense.dates import to_canonical_aware
from expense.errors import EngineError
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.create_forms import EditAccountScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    LOCK_MESSAGES,
    LOCKED_WORDS,
    account_with_currencies,
    held_currency,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

EFECTIVO = {
    "id": "acc-efe",
    "name": "Efectivo",
    "is_person": False,
    "is_archived": False,
    "currency_code": "PEN",
    "color": None,
    "current_balance_cents": 0,
    "opening_balance_transaction_id": None,
}
SUELDO = {
    **EFECTIVO,
    "id": "acc-sue",
    "name": "Sueldo Soles",
    "color": "#4a90d9",
    "opening_balance_transaction_id": "tx-open",
}
ELIANA = {**EFECTIVO, "id": "acc-eli", "name": "Eliana", "is_person": True}
#: A person who has an opening balance, and that row as the engine returns it.
ELIANA_OPENED = {**ELIANA, "opening_balance_transaction_id": "tx-eli"}
ELIANA_ROW = {
    "id": "tx-eli",
    "account_id": "acc-eli",
    "amount_cents": -15000,
    "transaction_type": 1,
    "date": "2025-12-31T00:00:00-05:00",
    "line_code": "#000002",
    "statement_line": None,
    "statement_place": None,
}
#: The opening-balance row as `GET /transactions/{id}?debit_as_negative=true`
#: returns it. `transaction_type` says inflow while the signed amount is
#: negative: the form must show the signed amount, never a sign read off the type.
OPENING_ROW = {
    "id": "tx-open",
    "account_id": "acc-sue",
    "amount_cents": -320000,
    "transaction_type": 2,
    "date": "2026-01-01T00:00:00-05:00",
    "line_code": "#000001",
    "statement_line": None,
    "statement_place": None,
}


@pytest.fixture
def notes(monkeypatch):
    """Every note the account Edit form shows, as (message, kwargs)."""
    seen: list = []
    monkeypatch.setattr(
        EditAccountScreen, "notify", lambda self, message, **kw: seen.append((message, kw))
    )
    return seen


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


def _summary(screen) -> str:
    """The summary, one line per field, its spacing squeezed to single spaces."""
    text = render_text(screen._summary_renderable(), width=100)
    return "\n".join(" ".join(line.split()) for line in text.splitlines())


def _hint(screen) -> str:
    return str(screen.query_one("#hint", Static).content)


def _form(record, body, *, opening_row=None):
    """Push the Edit form for `record` (after its read, if it has one), then
    run `body(pilot, app, screen)`."""

    async def scenario(pilot, app):
        screen = EditAccountScreen(dict(record))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        if record.get("opening_balance_transaction_id"):
            await wait_for(pilot, lambda: not screen._opening_loading)
        return await body(pilot, app, screen)

    return run_app(scenario)


@pytest.fixture
def reads_log(monkeypatch):
    """`reads.fetch_transaction` answering `reads_log.row` (OPENING_ROW unless
    set); logs each id it is asked for. Set `reads_log.error` to make it raise
    instead."""

    class Log(list):
        error: Exception | None = None
        row: dict = OPENING_ROW

    log = Log()

    def fetch(cfg, transaction_id, **kw):
        log.append(transaction_id)
        if log.error is not None:
            raise log.error
        return log.row

    monkeypatch.setattr("expense.reads.fetch_transaction", fetch)
    return log


# ---- 1 · an account with no opening balance ------------------------------------


def test_screen_1_two_empty_lines_after_colour_and_no_read(fake_client):
    async def body(pilot, app, screen):
        assert screen._sequence() == [
            "type",
            "name",
            "currency",
            "statement_code",
            "color",
            "opening",
            "as_of",
        ]
        text = _summary(screen)
        assert "opening — (optional)" in text
        assert "as of — (optional)" in text
        assert _hint(screen) == "free text · enter to go on"

    _form(EFECTIVO, body)
    assert fake_client.calls == []  # null id: nothing to read


def test_screen_1_left_empty_the_save_is_the_account_alone(fake_client, notes):
    async def body(pilot, app, screen):
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(EFECTIVO, body)
    assert fake_client.requests == [("PUT", "/accounts/acc-efe")]
    assert ("Saved.", {}) in notes


# ---- 2 · typing the amount, then the date ----------------------------------------


def test_screen_2_the_hints_and_the_star_once_there_is_an_amount(fake_client):
    async def body(pilot, app, screen):
        _on(screen, "opening")
        assert _hint(screen) == (
            "signed · 350.00 is money you have · -350.00 is money you owe · in PEN · optional"
        )
        _type(screen, "opening", "350.00")
        assert screen._key == "as_of"
        assert _hint(screen) == "YYYY-MM-DD · the day the account held this"
        assert screen.query_one("#bar", Input).value == ""  # the date starts empty
        text = _summary(screen)
        assert "opening 350.00" in text
        assert "as of — *" in text

    _form(EFECTIVO, body)


def test_screen_2_the_amount_is_taken_as_typed_in_the_accounts_currency(fake_client):
    async def body(pilot, app, screen):
        _on(screen, "opening")
        assert "in USD" in _hint(screen)
        _type(screen, "opening", "-350.00")
        assert screen._values["opening"] == -35000  # never flipped
        _type(screen, "opening", "350")
        assert screen._values["opening"] == 35000  # never flipped either way

    _form({**EFECTIVO, "currency_code": "USD"}, body)


def test_screen_2_an_unreadable_amount_or_day_stays_on_its_line(fake_client, notes):
    async def body(pilot, app, screen):
        _type(screen, "opening", "lots")
        assert screen._key == "opening" and "opening" not in screen._values
        _type(screen, "opening", "-1.234,5")  # a comma after the dot: never -1.23
        assert screen._key == "opening" and "opening" not in screen._values
        _type(screen, "opening", "350.00")
        _type(screen, "as_of", "01/01/2026")
        assert screen._key == "as_of" and "as_of" not in screen._values
        _type(screen, "as_of", "")  # an amount needs its day
        assert "as_of" not in screen._values

    _form(EFECTIVO, body)
    assert [m for m, _ in notes] == [
        "Opening: a signed decimal, e.g. -350.00",
        "Opening: a signed decimal, e.g. -350.00",
        "As of: use YYYY-MM-DD.",
        "As Of is required.",
    ]
    assert fake_client.calls == []


def test_screen_2_a_new_opening_balance_posts_signed_with_no_title(fake_client, notes):
    async def body(pilot, app, screen):
        _type(screen, "opening", "-350.00")
        _type(screen, "as_of", "2026-01-01")  # last line: enter saves
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(EFECTIVO, body)
    # the account did not change, so the save is the opening balance alone
    assert fake_client.requests == [("POST", "/accounts/acc-efe/opening-balance")]
    (_path, sent) = fake_client.posts[0]
    assert set(sent) == {"transaction_id", "amount_cents", "date"}  # title: the engine's
    assert sent["amount_cents"] == -35000
    assert sent["date"] == to_canonical_aware("2026-01-01")
    assert len(sent["transaction_id"]) == 36
    assert ("Saved.", {}) in notes


def test_one_save_sends_the_account_first_then_the_opening_balance(fake_client):
    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening", "350.00")
        _type(screen, "as_of", "2026-01-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(EFECTIVO, body)
    assert fake_client.requests == [
        ("PUT", "/accounts/acc-efe"),
        ("POST", "/accounts/acc-efe/opening-balance"),
    ]
    assert fake_client.puts[0][1] == {"name": "Efectivo", "color": "#5ab87a"}


# ---- 3 · an account that already has one -------------------------------------------


def test_screen_3_the_lines_open_filled_from_one_signed_read(fake_client, reads_log):

    async def body(pilot, app, screen):
        assert screen._values["opening"] == -320000  # the signed amount, not the type's
        assert screen._values["as_of"] == "2026-01-01"
        text = _summary(screen)
        assert "opening -3,200.00" in text
        assert "as of 2026-01-01" in text
        _on(screen, "opening")
        assert screen.query_one("#bar", Input).value == "-3200"

    _form(SUELDO, body)
    # one read of the named row — no category lookup, no filtered transaction list
    assert reads_log == ["tx-open"]
    assert fake_client.calls == []


def test_screen_3_a_changed_amount_puts_only_the_amount(fake_client, reads_log):

    async def body(pilot, app, screen):
        _type(screen, "opening", "-3000")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert fake_client.puts == [("/transactions/tx-open", {"amount_cents": -300000})]


def test_screen_3_a_changed_date_puts_only_the_date(fake_client, reads_log):

    async def body(pilot, app, screen):
        _type(screen, "as_of", "2026-02-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert fake_client.puts == [
        ("/transactions/tx-open", {"date": to_canonical_aware("2026-02-01")})
    ]


def test_screen_3_unchanged_the_save_is_the_account_alone(fake_client, reads_log):

    async def body(pilot, app, screen):
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert fake_client.requests == [("PUT", "/accounts/acc-sue")]


def test_a_save_waits_for_the_read(fake_client, notes, monkeypatch):
    release = threading.Event()

    def slow(cfg, transaction_id, **kw):
        release.wait(2)
        return OPENING_ROW

    monkeypatch.setattr("expense.reads.fetch_transaction", slow)

    async def scenario(pilot, app):
        screen = EditAccountScreen(dict(SUELDO))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        screen.action_submit()
        assert fake_client.calls == []
        release.set()
        await wait_for(pilot, lambda: not screen._opening_loading)

    run_app(scenario)
    assert ("The opening balance is still loading.", {"severity": "error"}) in notes


def test_a_read_that_fails_leaves_the_lines_read_only(fake_client, notes, reads_log):
    reads_log.error = EngineError("NOT_FOUND", "Transaction not found.", None, 404, {})

    async def body(pilot, app, screen):
        assert {"opening", "as_of"} <= screen._locked
        assert "read-only" in _summary(screen)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert notes[0][1] == {"title": "Failed", "severity": "error", "markup": False}
    assert "NOT_FOUND" in notes[0][0]
    assert fake_client.requests == [("PUT", "/accounts/acc-sue")]


# ---- ⏎ moves one line, and saves when no line ahead can change -----------------


@pytest.mark.parametrize(
    "record, lines",
    [
        (EFECTIVO, ["name", "statement_code", "color", "opening", "as_of"]),
        (SUELDO, ["name", "statement_code", "color", "opening", "as_of"]),
        (ELIANA, ["name", "color", "opening", "as_of"]),
    ],
    ids=["no-opening", "read-opening", "person"],
)
def test_each_enter_moves_one_line_and_the_last_saves(fake_client, reads_log, record, lines):
    """Real `⏎` presses through Textual's dispatch: the form's own handler and the
    bar form's under it run once per press, so each moves exactly one line (TYPE
    and CURRENCY are read-only and skipped), and nothing is sent until the last."""

    async def body(pilot, app, screen):
        visited = []
        for _ in lines[:-1]:
            visited.append(screen._key)
            await pilot.press("enter")
            await pilot.pause()
            assert fake_client.calls == []
        visited.append(screen._key)
        assert visited == lines
        await pilot.press("enter")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(record, body)
    assert fake_client.requests == [("PUT", f"/accounts/{record['id']}")]


def test_after_a_failed_read_enter_on_colour_saves(fake_client, notes, reads_log):
    """OPENING and AS OF are read-only once their read fails, so COLOR has no line
    ahead that can change: `⏎` there sends the save, with the colour typed."""
    reads_log.error = EngineError("NOT_FOUND", "Transaction not found.", None, 404, {})

    async def body(pilot, app, screen):
        assert screen._key == "name"
        await pilot.press("enter", "enter")
        await pilot.pause()
        assert screen._key == "color"
        await pilot.press(*"green")
        await pilot.press("enter")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert fake_client.puts == [("/accounts/acc-sue", {"name": "Sueldo Soles", "color": "#5ab87a"})]
    assert ("Saved.", {}) in notes


# ---- 4 · emptying the amount and saving -----------------------------------------------


def _empty_and_save(fake_client, answer, record=SUELDO):
    asked: dict = {}

    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening", "")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        asked["title"], asked["message"] = app.screen._title, app.screen._message
        await pilot.press(answer)
        await pilot.pause()
        if answer == "y":
            await wait_for(pilot, lambda: not screen.is_attached)
        else:
            assert app.screen is screen  # back on the form
            await pilot.pause()

    _form(record, body)
    return asked


def test_screen_4_emptying_the_amount_asks_first(fake_client, reads_log):
    asked = _empty_and_save(fake_client, "y")
    assert asked == {
        "title": "Delete this opening balance?",
        "message": "Sueldo Soles · -3,200.00 · 2026-01-01\n"
        "It leaves the account's balance, and no screen can bring it back.",
    }


def test_screen_4_y_saves_the_account_then_deletes(fake_client, reads_log):
    _empty_and_save(fake_client, "y")
    assert fake_client.requests == [
        ("PUT", "/accounts/acc-sue"),
        ("DELETE", "/transactions/tx-open"),
    ]


@pytest.mark.parametrize("answer", ["n", "escape", "enter"])
def test_screen_4_any_other_answer_saves_nothing(fake_client, reads_log, answer):
    _empty_and_save(fake_client, answer)
    assert fake_client.requests == []


# ---- a person: pane A of expense-world-person-opening-balance.html ----------------------


def test_pane_a1_a_person_has_both_lines_after_colour_and_no_code_line(fake_client):
    async def body(pilot, app, screen):
        assert screen._sequence() == ["type", "name", "currency", "color", "opening", "as_of"]
        assert [line for line in _summary(screen).splitlines() if line] == [
            "type person read-only",
            "name Eliana",
            "currency PEN read-only",
            "color — (optional)",
            "opening — (optional)",
            "as of — (optional)",
        ]

    _form(ELIANA, body)
    assert fake_client.calls == []  # null id: nothing to read


def test_pane_a1_a_person_adds_an_opening_balance(fake_client, notes):
    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening", "-150.00")
        _type(screen, "as_of", "2025-12-31")  # last line: enter saves
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(ELIANA, body)
    assert fake_client.requests == [
        ("PUT", "/accounts/acc-eli"),
        ("POST", "/accounts/acc-eli/opening-balance"),
    ]
    assert fake_client.puts[0][1] == {"name": "Eliana", "color": "#5ab87a"}  # no code
    (_path, sent) = fake_client.posts[0]
    assert set(sent) == {"transaction_id", "amount_cents", "date"}
    assert sent["amount_cents"] == -15000
    assert sent["date"] == to_canonical_aware("2025-12-31")
    assert ("Saved.", {}) in notes


def test_pane_a2_a_person_who_has_one_opens_with_both_lines_filled(fake_client, reads_log):
    reads_log.row = ELIANA_ROW

    async def body(pilot, app, screen):
        assert [line for line in _summary(screen).splitlines() if line] == [
            "type person read-only",
            "name Eliana",
            "currency PEN read-only",
            "color — (optional)",
            "opening -150.00",
            "as of 2025-12-31",
        ]

    _form(ELIANA_OPENED, body)
    assert reads_log == ["tx-eli"]
    assert fake_client.calls == []


def test_pane_a2_a_person_changes_its_opening_balance(fake_client, reads_log):
    reads_log.row = ELIANA_ROW

    async def body(pilot, app, screen):
        _type(screen, "opening", "-200.00")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(ELIANA_OPENED, body)
    assert fake_client.puts == [("/transactions/tx-eli", {"amount_cents": -20000})]


def test_pane_a2_a_person_empties_its_opening_balance(fake_client, reads_log):
    reads_log.row = ELIANA_ROW
    asked = _empty_and_save(fake_client, "y", ELIANA_OPENED)
    assert asked == {
        "title": "Delete this opening balance?",
        "message": "Eliana · -150.00 · 2025-12-31\n"
        "It leaves the account's balance, and no screen can bring it back.",
    }
    assert fake_client.requests == [
        ("PUT", "/accounts/acc-eli"),
        ("DELETE", "/transactions/tx-eli"),
    ]
    assert fake_client.puts[0][1] == {"name": "Eliana", "color": "#5ab87a"}  # no code


# ---- 6 · the account saves, the opening balance is refused -----------------------------

FUTURE = EngineError(
    "VALIDATION_ERROR",
    "Validation failed",
    {"date": "Date cannot be in the future."},
    422,
    {},
    {"date": "FUTURE_DATE"},
)


def test_screen_6_the_note_says_which_half_went_through_and_resends_only_the_opening(
    fake_client, notes
):
    fake_client.errors["POST"] = FUTURE
    seen: dict = {}

    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening", "350.00")
        _type(screen, "as_of", "2026-11-01")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert screen.is_attached and screen._key == "as_of"
        assert screen.query_one("#bar", Input).value == "2026-11-01"  # still in the form
        assert (screen._values["opening"], screen._values["as_of"]) == (35000, "2026-11-01")
        seen["first"] = list(fake_client.requests)
        fake_client.errors.clear()
        _type(screen, "as_of", "2026-01-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(EFECTIVO, body)
    message, kw = notes[0]
    assert kw == {"title": "Failed", "severity": "error", "markup": False}
    assert message == (
        "The account's changes are saved. The opening balance is not:\n"
        "VALIDATION_ERROR — Validation failed\n"
        "  date: Date cannot be in the future.\n\n"
        "It is still in the form: fix it and save again."
    )
    assert seen["first"] == [
        ("PUT", "/accounts/acc-efe"),
        ("POST", "/accounts/acc-efe/opening-balance"),
    ]
    # the second save sends only the opening balance
    assert fake_client.requests[2:] == [("POST", "/accounts/acc-efe/opening-balance")]


@pytest.mark.parametrize(
    ("key", "reason", "line"),
    [
        (
            "account_id",
            "OPENING_BALANCE_EXISTS",
            "It got one meanwhile: close the form and open it again to change it.",
        ),
        (
            "category_id",
            "RESERVED_NAME_HELD",
            "One of your categories has a built-in category's name: "
            "rename it on Manage ▸ Categories, then save again.",
        ),
        ("category_id", "CONCURRENT_CHANGE", "It changed at the same moment: save again."),
    ],
    ids=["screen-7", "screen-6B", "screen-5A-form"],
)
def test_a_half_refusal_with_a_next_step_ends_with_its_line(fake_client, notes, key, reason, line):
    """The account saved, the opening balance was refused for a reason that has
    its own line: the note is the half sentence, the engine's words, then that
    line, which takes the place of the form's own closing line."""
    fake_client.errors["POST"] = EngineError(
        "CONFLICT", "stand-in", {key: "stand-in field words"}, 409, {}, {key: reason}
    )

    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening", "350.00")
        _type(screen, "as_of", "2026-01-01")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()

    _form(EFECTIVO, body)
    message, kw = notes[0]
    assert kw == {"title": "Failed", "severity": "error", "markup": False}
    assert message == (
        "The account's changes are saved. The opening balance is not:\n"
        f"CONFLICT — stand-in\n  {key}: stand-in field words\n\n{line}"
    )


def test_screen_6_esc_just_leaves_with_the_account_saved(fake_client, notes):
    fake_client.errors["POST"] = FUTURE
    result: list = []

    async def scenario(pilot, app):
        screen = EditAccountScreen(dict(EFECTIVO))
        await app.push_screen(screen, result.append)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        _type(screen, "color", "green")
        _type(screen, "opening", "350.00")
        _type(screen, "as_of", "2026-11-01")
        await wait_for(pilot, lambda: notes)
        await pilot.press("escape")
        await wait_for(pilot, lambda: result)

    run_app(scenario)
    assert result == [True]  # a write went through: the list starts over
    assert len(fake_client.calls) == 2  # leaving sends nothing more


# ---- 7 · when the engine says no -------------------------------------------------------


@pytest.mark.parametrize(
    ("record", "steps", "verb", "error"),
    [
        (
            EFECTIVO,
            [("opening", "350.00"), ("as_of", "2026-11-01")],
            "POST",
            FUTURE,
        ),
        (
            EFECTIVO,
            [("opening", "0"), ("as_of", "2026-01-01")],
            "POST",
            EngineError(
                "VALIDATION_ERROR",
                "Validation failed",
                {"amount_cents": "Amount cannot be zero."},
                422,
                {},
                {"amount_cents": "ZERO_AMOUNT"},
            ),
        ),
        (
            SUELDO,
            [("as_of", "2026-03-20")],
            "PUT",
            EngineError(
                "VALIDATION_ERROR",
                "Transaction falls inside a sealed statement period.",
                {
                    "date": "Period 2026-03-01 to 2026-03-30 is sealed by completed statement "
                    "'Marzo 2026'. Revert it to draft to change anything inside it."
                },
                422,
                {},
                {"date": "SEALED_PERIOD"},
            ),
        ),
        (
            EFECTIVO,
            [("opening", "350.00"), ("as_of", "2026-01-01")],
            "POST",
            EngineError(
                "CONFLICT",
                "Account already has an opening balance.",
                {"account_id": "Account already has an opening balance."},
                409,
                {},
                {"account_id": "OPENING_BALANCE_EXISTS"},
            ),
        ),
        (
            SUELDO,
            [("opening", "-3000")],
            "PUT",
            EngineError(
                "VALIDATION_ERROR",
                LOCKED_WORDS,
                {"amount_cents": LOCK_MESSAGES["LOCKED"]},
                422,
                {},
                {"amount_cents": "LOCKED"},
            ),
        ),
    ],
    ids=[
        "FUTURE_DATE",
        "ZERO_AMOUNT",
        "SEALED_PERIOD",
        "OPENING_BALANCE_EXISTS",
        "LOCKED",
    ],
)
def test_screen_7_each_refusal_shows_in_the_engines_words(
    fake_client, notes, reads_log, record, steps, verb, error
):
    fake_client.errors[verb] = error
    typed: dict = {}

    async def body(pilot, app, screen):
        for key, text in steps:
            _type(screen, key, text)
        if screen.is_attached and not notes:
            await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert screen.is_attached  # nothing saved, the form stays
        typed.update(screen._values)

    _form(record, body)
    message, kw = notes[0]
    assert kw == {"title": "Failed", "severity": "error", "markup": False}
    assert message.startswith(f"{error.code} — {error.message}")
    for field, words in (error.fields or {}).items():
        assert f"  {field}: {words}" in message
    assert "account's changes" not in message  # the account was not part of this save
    for key, _text in steps:
        assert key in typed  # what was typed is still there


# ---- 8 · after a successful save -------------------------------------------------------


def _list_then_edit(fake_client, monkeypatch, steps, *, save: bool):
    # the list reads an account holding its currencies; the form is opened on that row's account
    accounts = [
        account_with_currencies(
            id=a["id"],
            name=a["name"],
            color=a["color"],
            currencies=[
                held_currency(
                    "PEN", 0, opening_balance_transaction_id=a["opening_balance_transaction_id"]
                )
            ],
        )
        for a in (SUELDO, EFECTIVO)
    ]
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(accounts))
    seen: dict = {}

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("down")  # cursor → Efectivo
        await pilot.press("e")
        await wait_for(pilot, lambda: isinstance(app.screen, EditAccountScreen))
        form = app.screen
        for key, text in steps:
            _type(form, key, text)
        if save:
            await wait_for(pilot, lambda: not form.is_attached)
        else:
            await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await wait_for_list(pilot, app)
        await pilot.pause()
        seen["cursor"] = screen.query(CursorList).first().cursor_key

    run_app(scenario)
    return seen


def test_screen_8_a_save_reloads_the_list_from_row_1_with_the_note(fake_client, notes, monkeypatch):
    seen = _list_then_edit(
        fake_client, monkeypatch, [("opening", "350.00"), ("as_of", "2026-01-01")], save=True
    )
    assert seen["cursor"] == ("acc-sue", "PEN")  # first page, cursor on row 1
    assert ("Saved.", {}) in notes
    assert ("POST", "/accounts/acc-efe/opening-balance") in fake_client.requests


def test_leaving_without_a_save_keeps_the_row(fake_client, notes, monkeypatch):
    seen = _list_then_edit(fake_client, monkeypatch, [], save=False)
    assert seen["cursor"] == ("acc-efe", "PEN")
    assert fake_client.requests == []


# ---- guards ----------------------------------------------------------------------------


def _string_keys(paths) -> set[str]:
    """Every string literal used in code (docstrings and comments aside, a key
    read is one of these) under `paths`."""
    import ast
    from pathlib import Path

    found: set[str] = set()
    for path in paths:
        for file in [path] if path.is_file() else sorted(path.rglob("*.py")):
            for node in ast.walk(ast.parse(Path(file).read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    found.add(node.value)
    return found


def test_no_sign_from_the_type_and_no_lookup_through_the_opening_category():
    """Nothing in the app reads `transaction_type` but `formatting.signed_cents`,
    the one place a sign is read off the type, and the
    account Edit form never looks its opening balance up through the @Opening
    category; the account names it. The category's `system_key` has one home,
    `reads.OPENING_SYSTEM_KEY`, which the live contract suite reads to find the
    category; what an opening balance's line keeps is its `edit_limits`."""
    import ast
    from pathlib import Path

    import expense

    root = Path(expense.__file__).parent
    elsewhere = [file for file in sorted(root.rglob("*.py")) if file != root / "formatting.py"]
    assert "transaction_type" not in _string_keys(elsewhere)
    assert "transaction_type" in _string_keys([root / "formatting.py"])  # signed_cents
    assert "opening_balance" not in _string_keys([root / "tui"])
    reads_tree = ast.parse((root / "reads.py").read_text())
    literals = [
        node
        for node in ast.walk(reads_tree)
        if isinstance(node, ast.Constant) and node.value == "opening_balance"
    ]
    assert len(literals) == 1  # OPENING_SYSTEM_KEY, nowhere else
    account_form = (root / "tui" / "screens" / "create_forms.py").read_text()
    assert _opening_category_reads(account_form) == set()


#: What reading the @Opening category through the shared reads looks like.
_OPENING_CATEGORY_READS = {"OPENING_SYSTEM_KEY", "load_quickadd_refs"}


def _opening_category_reads(source: str) -> set[str]:
    """The @Opening-category reads `source` makes: one of the names above,
    bare (`load_quickadd_refs(...)`) or through a module (`reads.load_quickadd_refs`)."""
    import ast

    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    return _OPENING_CATEGORY_READS & (names | attrs)


def test_the_opening_category_guard_sees_reads_through_a_module():
    """The guard above trips on each way the account form could reach it."""
    assert _opening_category_reads("from expense import reads\nreads.load_quickadd_refs(cfg)") == {
        "load_quickadd_refs"
    }
    assert _opening_category_reads("x = reads.OPENING_SYSTEM_KEY") == {"OPENING_SYSTEM_KEY"}
    assert _opening_category_reads("self._opening_id = 1") == set()


# ---- a refusal lands on the line it names ----------------------------------------------

ZERO = EngineError(
    "VALIDATION_ERROR",
    "Validation failed",
    {"amount_cents": "Amount cannot be zero."},
    422,
    {},
    {"amount_cents": "ZERO_AMOUNT"},
)
EXISTS = EngineError(
    "CONFLICT",
    "Account already has an opening balance.",
    {"account_id": "Account already has an opening balance."},
    409,
    {},
    {"account_id": "OPENING_BALANCE_EXISTS"},
)


@pytest.mark.parametrize(
    ("error", "change_colour", "lands_on", "bar"),
    [
        (ZERO, False, "opening", "0"),  # plain refusal → the amount line
        (FUTURE, True, "as_of", "2026-11-01"),  # half refusal → the date line
        (EXISTS, False, "name", "Efectivo"),  # names no line of the form: stays
    ],
    ids=["plain-amount", "half-date", "no-line-stays"],
)
def test_a_refusal_saved_from_another_line_lands_on_the_line_it_names(
    fake_client, notes, error, change_colour, lands_on, bar
):
    fake_client.errors["POST"] = error

    async def body(pilot, app, screen):
        if change_colour:
            _type(screen, "color", "green")  # enter here moves on, it does not save
        _type(screen, "opening", "0" if error is ZERO else "350.00")
        # the date set without enter on the last line, which would save from there
        screen._values["as_of"] = "2026-11-01" if error is FUTURE else "2026-01-01"
        _on(screen, "name")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        half = "The account's changes are saved." in notes[0][0]
        assert half is change_colour
        assert screen._key == lands_on
        assert screen.query_one("#bar", Input).value == bar  # what was typed

    _form(EFECTIVO, body)
