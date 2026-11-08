"""The account Edit form's opening balances — a pair of lines per currency,
`PEN opening` and `PEN as of`, then the next currency's.

A person's form has the same pair. Each
currency of the account names its opening balance by id
(contract: "Bank Accounts", "Opening balance"); the form reads that row signed
with one `GET /transactions/{id}`
(contract: "Base Conventions", "Sign convention — responses") and writes it
through `POST /accounts/{id}/opening-balance`, `PUT /transactions/{id}` and
`DELETE /transactions/{id}`.
"""

import threading

import pytest
from rich.color import ColorSystem
from rich.style import Style
from textual.widgets import Input, Label, Static

from expense.dates import to_canonical_aware
from expense.errors import EngineError
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.create_forms import EditAccountScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.theme import PALETTE
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_CURRENCIES,
    LOCK_MESSAGES,
    LOCKED_WORDS,
    account_with_currencies,
    held_currency,
    refusal_block,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

EFECTIVO = account_with_currencies(
    id="acc-efe", name="Efectivo", color=None, currencies=[held_currency("PEN")]
)
SUELDO = account_with_currencies(
    EFECTIVO,
    id="acc-sue",
    name="Sueldo Soles",
    color="#4a90d9",
    currencies=[held_currency("PEN", opening_balance_transaction_id="tx-open")],
)
ELIANA = account_with_currencies(EFECTIVO, id="acc-eli", name="Eliana", is_person=True)
#: A person who has an opening balance, and that row as the engine returns it.
ELIANA_OPENED = account_with_currencies(
    ELIANA, currencies=[held_currency("PEN", opening_balance_transaction_id="tx-eli")]
)
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


def _no_failed_toast(notes) -> None:
    """The refusal was a block under the form: no `Failed` note went to `notify`."""
    assert not [m for m, kw in notes if kw.get("title") == "Failed"]


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


def _sgr(style: str) -> str:
    """The escape codes a rendered `style` opens with, for a test reading ansi output."""
    return Style.parse(style).render("x", color_system=ColorSystem.EIGHT_BIT).split("x")[0]


def _hint(screen) -> str:
    return str(screen.query_one("#hint", Static).content)


def _word(screen) -> str:
    """The word on the bar's right."""
    return str(screen.query_one("#bar-word", Label).content)


def _form(record, body):
    """Push the Edit form for `record`, after its reads if it has any, then run
    `body(pilot, app, screen)`."""

    async def scenario(pilot, app):
        screen = EditAccountScreen(record, ENGINE_CURRENCIES)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await wait_for(pilot, lambda: not screen._openings_loading)
        return await body(pilot, app, screen)

    return run_app(scenario)


@pytest.fixture
def reads_log(monkeypatch):
    """`reads.fetch_transaction` answering `reads_log.rows[id]`, else
    `reads_log.row` (OPENING_ROW unless set); logs each id it is asked for.
    Set `reads_log.error` to make it raise instead."""

    class Log(list):
        error: Exception | None = None
        row: dict = OPENING_ROW
        rows: dict = {}  # id → row, for an id other than `row`'s

    log = Log()

    def fetch(cfg, transaction_id, **kw):
        log.append(transaction_id)
        if log.error is not None:
            raise log.error
        return log.rows.get(transaction_id, log.row)

    monkeypatch.setattr("expense.reads.fetch_transaction", fetch)
    return log


# ---- an account with no opening balance ------------------------------------


def test_two_empty_lines_after_colour_and_no_read(fake_client):
    async def body(pilot, app, screen):
        assert screen._sequence() == [
            "type",
            "name",
            "currencies",
            "statement_code",
            "color",
            "opening:PEN",
            "as_of:PEN",
        ]
        text = _summary(screen)
        assert "PEN opening — (optional)" in text
        assert "PEN as of — (optional)" in text
        assert _hint(screen) == "free text · enter to go on"

    _form(EFECTIVO, body)
    assert fake_client.calls == []  # null id: nothing to read


def test_left_empty_the_save_is_the_account_alone(fake_client, notes):
    async def body(pilot, app, screen):
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(EFECTIVO, body)
    assert fake_client.requests == [("PUT", "/accounts/acc-efe")]
    assert ("Saved.", {}) in notes


# ---- typing the amount, then the date ----------------------------------------


def test_no_hint_under_the_amount_and_the_star_once_there_is_one(fake_client):
    async def body(pilot, app, screen):
        _on(screen, "opening:PEN")
        assert _hint(screen) == ""  # no line under the amount
        _type(screen, "opening:PEN", "350.00")
        assert screen._key == "as_of:PEN"
        assert _hint(screen) == "YYYY-MM-DD · the day the account held this"
        assert screen.query_one("#bar", Input).value == ""  # the date starts empty
        text = _summary(screen)
        assert "PEN opening 350.00" in text
        assert "PEN as of — *" in text

    _form(EFECTIVO, body)


def test_the_amount_is_taken_as_typed_in_its_currency(fake_client):
    async def body(pilot, app, screen):
        assert screen._label("opening:USD") == "USD OPENING"
        _type(screen, "opening:USD", "-350.00")
        assert screen._values["opening:USD"] == -35000  # never flipped
        _type(screen, "opening:USD", "350")
        assert screen._values["opening:USD"] == 35000  # never flipped either way

    _form(account_with_currencies(EFECTIVO, currencies=[held_currency("USD")]), body)


def test_an_unreadable_amount_or_day_stays_on_its_line(fake_client, notes):
    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "lots")
        assert screen._key == "opening:PEN" and "opening:PEN" not in screen._values
        _type(screen, "opening:PEN", "-1.234,5")  # a comma after the dot: never -1.23
        assert screen._key == "opening:PEN" and "opening:PEN" not in screen._values
        _type(screen, "opening:PEN", "350.00")
        _type(screen, "as_of:PEN", "01/01/2026")
        assert screen._key == "as_of:PEN" and "as_of:PEN" not in screen._values
        _type(screen, "as_of:PEN", "")  # an amount needs its day
        assert "as_of:PEN" not in screen._values

    _form(EFECTIVO, body)
    assert [m for m, _ in notes] == [
        "PEN opening: a signed decimal, e.g. -350.00",
        "PEN opening: a signed decimal, e.g. -350.00",
        "PEN as of: use YYYY-MM-DD.",
        "PEN as of is required.",
    ]
    assert fake_client.calls == []


# ---- the word on the right: debt, credit or nothing --------------------------------


@pytest.mark.parametrize("record", ["bank", "person"])
@pytest.mark.parametrize(
    ("typed", "word"),
    [("-150.00", "debt"), ("150.00", "credit"), ("", ""), ("0.00", ""), ("0", ""), ("-", "")],
    ids=["negative", "positive", "empty", "zero", "bare-zero", "unreadable"],
)
def test_the_word_on_the_right_follows_the_sign_as_typed(fake_client, record, typed, word):
    """`debt` below zero, `credit` above it, nothing while empty or at zero, the
    same on a bank account and a person, with no currency after it; it follows
    the bar as it is typed, before `⏎`."""

    async def body(pilot, app, screen):
        _on(screen, "opening:PEN")
        assert _word(screen) == ""
        screen.query_one("#bar", Input).value = typed
        await pilot.pause()
        assert _word(screen) == word
        _on(screen, "name")
        assert _word(screen) == ""  # no other line has a word

    _form(ELIANA if record == "person" else EFECTIVO, body)


def test_the_word_shows_on_landing_on_a_filled_amount(fake_client, reads_log):
    async def body(pilot, app, screen):
        _on(screen, "opening:PEN")
        assert _word(screen) == "debt"  # -3,200.00, read
        _on(screen, "as_of:PEN")
        assert _word(screen) == ""

    _form(SUELDO, body)


def test_a_new_opening_balance_posts_signed_with_no_title(fake_client, notes):
    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-350.00")
        _type(screen, "as_of:PEN", "2026-01-01")  # last line: enter saves
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(EFECTIVO, body)
    # the account did not change, so the save is the opening balance alone
    assert fake_client.requests == [("POST", "/accounts/acc-efe/opening-balance")]
    (_path, sent) = fake_client.posts[0]
    # the title is the engine's to name
    assert set(sent) == {"transaction_id", "currency_code", "amount_cents", "date"}
    assert sent["currency_code"] == "PEN"
    assert sent["amount_cents"] == -35000
    assert sent["date"] == to_canonical_aware("2026-01-01")
    assert len(sent["transaction_id"]) == 36
    assert ("Saved.", {}) in notes


#: The Visa as the engine reads it: soles with an opening balance of its own, dollars
#: with none (contract: "Bank Accounts", "`currencies`").
VISA = account_with_currencies(
    id="acc-visa",
    name="Visa",
    color="#4a90d9",
    currencies=[
        held_currency("PEN", opening_balance_transaction_id="tx-open"),
        held_currency("USD"),
    ],
)
#: The same, its dollars with an opening balance too, and that row.
VISA_BOTH = account_with_currencies(
    VISA,
    currencies=[
        held_currency("PEN", opening_balance_transaction_id="tx-open"),
        held_currency("USD", opening_balance_transaction_id="tx-usd"),
    ],
)
USD_ROW = {**OPENING_ROW, "id": "tx-usd", "amount_cents": 4000, "date": "2026-02-01T00:00:00-05:00"}


def test_each_currency_has_its_pair_in_the_engines_order(fake_client, reads_log):
    async def body(pilot, app, screen):
        assert screen._sequence()[-4:] == ["opening:PEN", "as_of:PEN", "opening:USD", "as_of:USD"]
        assert [screen._label(k) for k in screen._sequence()[-4:]] == [
            "PEN OPENING",
            "PEN AS OF",
            "USD OPENING",
            "USD AS OF",
        ]
        assert [line for line in _summary(screen).splitlines() if line] == [
            "type bank read-only",
            "name Visa",
            "currencies PEN · USD read-only",
            "statement code — (optional)",
            "color ██ blue",
            "PEN opening -3,200.00",
            "PEN as of 2026-01-01",
            "USD opening — (optional)",
            "USD as of — (optional)",
        ]

    _form(VISA, body)
    assert reads_log == ["tx-open"]  # the dollars name none: nothing to read


def test_the_summary_colours_each_opening_amount_by_sign(fake_client, reads_log):
    reads_log.rows = {"tx-usd": USD_ROW}

    async def body(pilot, app, screen):
        out = render_text(screen._summary_renderable(), width=100, ansi=True)
        lines = {line.split()[0] + " " + line.split()[1]: line for line in out.splitlines() if line}
        assert _sgr(PALETTE.error) + "-3,200.00" in lines["PEN opening"]
        assert _sgr(PALETTE.success) + "40.00" in lines["USD opening"]
        # the day lines carry no sign colour
        assert _sgr(PALETTE.error) not in lines["PEN as"]
        assert _sgr(PALETTE.success) not in lines["USD as"]

    _form(VISA_BOTH, body)


def test_each_pair_reads_its_own_opening_balance(fake_client, reads_log):
    reads_log.rows = {"tx-usd": USD_ROW}

    async def body(pilot, app, screen):
        assert (screen._openings["PEN"].id, screen._openings["USD"].id) == ("tx-open", "tx-usd")
        assert screen._values["opening:PEN"] == -320000
        assert screen._values["as_of:PEN"] == "2026-01-01"
        assert screen._values["opening:USD"] == 4000
        assert screen._values["as_of:USD"] == "2026-02-01"

    _form(VISA_BOTH, body)
    assert reads_log == ["tx-open", "tx-usd"]


def test_changing_only_the_dollars_sends_one_request_with_usd(fake_client, reads_log):
    async def body(pilot, app, screen):
        _type(screen, "opening:USD", "-45.50")
        _type(screen, "as_of:USD", "2026-01-01")  # last line: enter saves
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA, body)
    assert fake_client.requests == [("POST", "/accounts/acc-visa/opening-balance")]
    (_path, sent) = fake_client.posts[0]
    assert sent["currency_code"] == "USD" and sent["amount_cents"] == -4550
    assert not fake_client.puts and not fake_client.deletes


def test_the_account_goes_first_then_the_dollars_alone(fake_client, reads_log):
    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening:USD", "-45.50")
        _type(screen, "as_of:USD", "2026-01-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA, body)
    assert fake_client.requests == [
        ("PUT", "/accounts/acc-visa"),
        ("POST", "/accounts/acc-visa/opening-balance"),
    ]
    assert "currency_code" not in fake_client.puts[0][1]
    assert fake_client.posts[0][1]["currency_code"] == "USD"


def test_changing_both_sends_one_request_per_currency_in_order(fake_client, reads_log):
    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-3000.00")
        _type(screen, "opening:USD", "40.00")
        _type(screen, "as_of:USD", "2026-01-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA, body)
    assert fake_client.requests == [
        ("PUT", "/transactions/tx-open"),
        ("POST", "/accounts/acc-visa/opening-balance"),
    ]
    assert fake_client.puts == [("/transactions/tx-open", {"amount_cents": -300000})]
    assert fake_client.posts[0][1]["currency_code"] == "USD"
    assert fake_client.posts[0][1]["amount_cents"] == 4000


def test_the_soles_pair_changes_the_soles_opening_balance_only(fake_client, reads_log):
    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-3000.00")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA, body)
    assert reads_log == ["tx-open"]
    assert fake_client.puts == [("/transactions/tx-open", {"amount_cents": -300000})]
    assert not fake_client.posts


def test_emptying_the_dollars_asks_then_deletes_the_dollars_row(fake_client, reads_log):
    reads_log.rows = {"tx-usd": USD_ROW}
    asked: dict = {}

    async def body(pilot, app, screen):
        _type(screen, "opening:USD", "")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        asked["title"], asked["message"] = app.screen._title, app.screen._message
        await pilot.press("y")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA_BOTH, body)
    assert asked == {
        "title": "Delete this opening balance?",
        "message": "Visa · USD · 40.00 · 2026-02-01\n"
        "It leaves the account's balance, and no screen can bring it back.",
    }
    assert fake_client.requests == [("DELETE", "/transactions/tx-usd")]


def test_emptying_both_asks_once_naming_each(fake_client, reads_log):
    reads_log.rows = {"tx-usd": USD_ROW}
    asked: dict = {}

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "")
        _type(screen, "opening:USD", "")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        asked["title"], asked["message"] = app.screen._title, app.screen._message
        await pilot.press("y")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA_BOTH, body)
    assert asked == {
        "title": "Delete these opening balances?",
        "message": "Visa · PEN · -3,200.00 · 2026-01-01\n"
        "Visa · USD · 40.00 · 2026-02-01\n"
        "They leave the account's balance, and no screen can bring them back.",
    }
    assert fake_client.requests == [
        ("DELETE", "/transactions/tx-open"),
        ("DELETE", "/transactions/tx-usd"),
    ]


def test_a_refusal_on_the_dollars_lands_on_usd_opening_and_resends_only_it(
    fake_client, notes, reads_log
):
    """The soles' change goes through, the dollars' is refused for a reason
    naming no line: the cursor lands on `USD opening`, and the next save sends
    the dollars alone."""
    fake_client.errors["POST"] = EXISTS
    seen: dict = {}

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-3000.00")
        _type(screen, "opening:USD", "40.00")
        screen._values["as_of:USD"] = "2026-01-01"
        _on(screen, "name")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        seen["key"] = screen._key
        seen["bar"] = screen.query_one("#bar", Input).value
        seen["block"] = refusal_block(screen)
        seen["first"] = list(fake_client.requests)
        fake_client.errors.clear()
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA, body)
    assert (seen["key"], seen["bar"]) == ("opening:USD", "40")
    assert seen["block"].startswith("Failed\nCONFLICT — Account already has an opening balance.")
    _no_failed_toast(notes)
    assert seen["first"] == [
        ("PUT", "/transactions/tx-open"),
        ("POST", "/accounts/acc-visa/opening-balance"),
    ]
    assert fake_client.requests[2:] == [("POST", "/accounts/acc-visa/opening-balance")]


def test_a_dated_refusal_on_the_dollars_lands_on_usd_as_of(fake_client, notes, reads_log):
    fake_client.errors["POST"] = FUTURE

    async def body(pilot, app, screen):
        _type(screen, "opening:USD", "40.00")
        screen._values["as_of:USD"] = "2026-11-01"
        _on(screen, "name")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen._key == "as_of:USD"
        assert screen.query_one("#bar", Input).value == "2026-11-01"

    _form(VISA, body)


def test_a_refusal_stops_the_currency_behind_it(fake_client, notes, reads_log):
    """The queue's rule: a refused write drops those behind it."""
    fake_client.errors["PUT"] = EngineError(
        "VALIDATION_ERROR",
        LOCKED_WORDS,
        {"amount_cents": LOCK_MESSAGES["LOCKED"]},
        422,
        {},
        {"amount_cents": "LOCKED"},
    )

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-3000.00")
        _type(screen, "opening:USD", "40.00")
        screen._values["as_of:USD"] = "2026-01-01"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen._key == "opening:PEN"

    _form(VISA, body)
    assert fake_client.requests == [("PUT", "/transactions/tx-open")]


def test_a_failed_read_locks_its_currency_and_the_other_pair_stays_editable(
    fake_client, notes, monkeypatch
):
    def fetch(cfg, transaction_id, **kw):
        if transaction_id == "tx-usd":
            raise EngineError("NOT_FOUND", "transaction not found.", None, 404, {})
        return OPENING_ROW

    monkeypatch.setattr("expense.reads.fetch_transaction", fetch)

    async def body(pilot, app, screen):
        assert {"opening:USD", "as_of:USD"} <= screen._locked
        assert not {"opening:PEN", "as_of:PEN"} & screen._locked
        assert screen._values["opening:PEN"] == -320000
        _type(screen, "opening:PEN", "-3000.00")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA_BOTH, body)
    assert "NOT_FOUND" in notes[0][0]
    assert fake_client.requests == [("PUT", "/transactions/tx-open")]


#: The soles with no opening balance yet, the dollars with one.
VISA_USD_OPENED = account_with_currencies(
    VISA,
    currencies=[
        held_currency("PEN"),
        held_currency("USD", opening_balance_transaction_id="tx-usd"),
    ],
)


def test_a_posted_opening_balance_is_changed_by_its_id_on_the_next_save(
    fake_client, notes, reads_log
):
    """The soles' POST goes through, the dollars' PUT is refused: the form
    stays, and a later change of the soles sends a PUT on the id the POST sent,
    never a second POST."""
    reads_log.rows = {"tx-usd": USD_ROW}
    fake_client.errors["PUT"] = EngineError(
        "VALIDATION_ERROR",
        LOCKED_WORDS,
        {"amount_cents": LOCK_MESSAGES["LOCKED"]},
        422,
        {},
        {"amount_cents": "LOCKED"},
    )

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-100.00")
        screen._values["as_of:PEN"] = "2026-01-01"
        _type(screen, "opening:USD", "50.00")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen.is_attached and screen._key == "opening:USD"
        fake_client.errors.clear()
        _type(screen, "opening:PEN", "-120.00")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA_USD_OPENED, body)
    (_path, posted) = fake_client.posts[0]
    assert posted["currency_code"] == "PEN"
    assert fake_client.requests == [
        ("POST", "/accounts/acc-visa/opening-balance"),
        ("PUT", "/transactions/tx-usd"),
        ("PUT", f"/transactions/{posted['transaction_id']}"),
        ("PUT", "/transactions/tx-usd"),
    ]
    assert fake_client.puts[1] == (
        f"/transactions/{posted['transaction_id']}",
        {"amount_cents": -12000},
    )


def test_one_save_sends_the_account_first_then_the_opening_balance(fake_client):
    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening:PEN", "350.00")
        _type(screen, "as_of:PEN", "2026-01-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(EFECTIVO, body)
    assert fake_client.requests == [
        ("PUT", "/accounts/acc-efe"),
        ("POST", "/accounts/acc-efe/opening-balance"),
    ]
    assert fake_client.puts[0][1] == {"name": "Efectivo", "color": "#5ab87a"}


# ---- an account that already has one -------------------------------------------


def test_the_lines_open_filled_from_one_signed_read(fake_client, reads_log):

    async def body(pilot, app, screen):
        assert screen._values["opening:PEN"] == -320000  # the signed amount, not the type's
        assert screen._values["as_of:PEN"] == "2026-01-01"
        text = _summary(screen)
        assert "opening -3,200.00" in text
        assert "as of 2026-01-01" in text
        _on(screen, "opening:PEN")
        assert screen.query_one("#bar", Input).value == "-3200"

    _form(SUELDO, body)
    # one read of the named row — no category lookup, no filtered transaction list
    assert reads_log == ["tx-open"]
    assert fake_client.calls == []


def test_a_changed_amount_puts_only_the_amount(fake_client, reads_log):

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-3000")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert fake_client.puts == [("/transactions/tx-open", {"amount_cents": -300000})]


def test_a_changed_date_puts_only_the_date(fake_client, reads_log):

    async def body(pilot, app, screen):
        _type(screen, "as_of:PEN", "2026-02-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert fake_client.puts == [
        ("/transactions/tx-open", {"date": to_canonical_aware("2026-02-01")})
    ]


def test_unchanged_the_save_is_the_account_alone(fake_client, reads_log):

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
        screen = EditAccountScreen(SUELDO, ENGINE_CURRENCIES)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        screen.action_submit()
        assert fake_client.calls == []
        release.set()
        await wait_for(pilot, lambda: not screen._openings_loading)

    run_app(scenario)
    assert (
        "The PEN opening balance is still loading.",
        {"severity": "error", "markup": False},
    ) in notes


def test_the_loading_note_names_the_currency_still_loading(fake_client, notes, monkeypatch):
    """Soles with no opening balance, dollars with one being read: the note
    names the dollars, the first currency still loading, not the first one."""
    release = threading.Event()

    def slow(cfg, transaction_id, **kw):
        release.wait(2)
        return USD_ROW

    monkeypatch.setattr("expense.reads.fetch_transaction", slow)

    async def scenario(pilot, app):
        screen = EditAccountScreen(VISA_USD_OPENED, ENGINE_CURRENCIES)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        screen.action_submit()
        assert fake_client.calls == []
        release.set()
        await wait_for(pilot, lambda: not screen._openings_loading)

    run_app(scenario)
    assert (
        "The USD opening balance is still loading.",
        {"severity": "error", "markup": False},
    ) in notes


def test_a_read_that_fails_leaves_the_lines_read_only(fake_client, notes, reads_log):
    reads_log.error = EngineError("NOT_FOUND", "transaction not found.", None, 404, {})

    async def body(pilot, app, screen):
        assert {"opening:PEN", "as_of:PEN"} <= screen._locked
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
        (EFECTIVO, ["name", "statement_code", "color", "opening:PEN", "as_of:PEN"]),
        (SUELDO, ["name", "statement_code", "color", "opening:PEN", "as_of:PEN"]),
        (ELIANA, ["name", "color", "opening:PEN", "as_of:PEN"]),
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
    reads_log.error = EngineError("NOT_FOUND", "transaction not found.", None, 404, {})

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


# ---- emptying the amount and saving -----------------------------------------------


def _empty_and_save(fake_client, answer, record=SUELDO):
    asked: dict = {}

    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening:PEN", "")
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


def test_emptying_the_amount_asks_first(fake_client, reads_log):
    asked = _empty_and_save(fake_client, "y")
    assert asked == {
        "title": "Delete this opening balance?",
        "message": "Sueldo Soles · PEN · -3,200.00 · 2026-01-01\n"
        "It leaves the account's balance, and no screen can bring it back.",
    }


def test_y_saves_the_account_then_deletes(fake_client, reads_log):
    _empty_and_save(fake_client, "y")
    assert fake_client.requests == [
        ("PUT", "/accounts/acc-sue"),
        ("DELETE", "/transactions/tx-open"),
    ]


@pytest.mark.parametrize("answer", ["n", "escape", "enter"])
def test_any_other_answer_saves_nothing(fake_client, reads_log, answer):
    _empty_and_save(fake_client, answer)
    assert fake_client.requests == []


# ---- a person ----------------------------------------------------------------------


def test_a_person_has_both_lines_after_colour_and_no_code_line(fake_client):
    async def body(pilot, app, screen):
        assert screen._sequence() == [
            "type",
            "name",
            "currencies",
            "color",
            "opening:PEN",
            "as_of:PEN",
        ]
        assert [line for line in _summary(screen).splitlines() if line] == [
            "type person read-only",
            "name Eliana",
            "currencies PEN read-only",
            "color — (optional)",
            "PEN opening — (optional)",
            "PEN as of — (optional)",
        ]

    _form(ELIANA, body)
    assert fake_client.calls == []  # null id: nothing to read


def test_a_person_adds_an_opening_balance(fake_client, notes):
    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening:PEN", "-150.00")
        _type(screen, "as_of:PEN", "2025-12-31")  # last line: enter saves
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(ELIANA, body)
    assert fake_client.requests == [
        ("PUT", "/accounts/acc-eli"),
        ("POST", "/accounts/acc-eli/opening-balance"),
    ]
    assert fake_client.puts[0][1] == {"name": "Eliana", "color": "#5ab87a"}  # no code
    (_path, sent) = fake_client.posts[0]
    assert set(sent) == {"transaction_id", "currency_code", "amount_cents", "date"}
    assert sent["currency_code"] == "PEN" and sent["amount_cents"] == -15000
    assert sent["date"] == to_canonical_aware("2025-12-31")
    assert ("Saved.", {}) in notes


def test_a_person_who_has_one_opens_with_both_lines_filled(fake_client, reads_log):
    reads_log.row = ELIANA_ROW

    async def body(pilot, app, screen):
        assert [line for line in _summary(screen).splitlines() if line] == [
            "type person read-only",
            "name Eliana",
            "currencies PEN read-only",
            "color — (optional)",
            "PEN opening -150.00",
            "PEN as of 2025-12-31",
        ]

    _form(ELIANA_OPENED, body)
    assert reads_log == ["tx-eli"]
    assert fake_client.calls == []


def test_a_person_changes_its_opening_balance(fake_client, reads_log):
    reads_log.row = ELIANA_ROW

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-200.00")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(ELIANA_OPENED, body)
    assert fake_client.puts == [("/transactions/tx-eli", {"amount_cents": -20000})]


def test_a_person_empties_its_opening_balance(fake_client, reads_log):
    reads_log.row = ELIANA_ROW
    asked = _empty_and_save(fake_client, "y", ELIANA_OPENED)
    assert asked == {
        "title": "Delete this opening balance?",
        "message": "Eliana · PEN · -150.00 · 2025-12-31\n"
        "It leaves the account's balance, and no screen can bring it back.",
    }
    assert fake_client.requests == [
        ("PUT", "/accounts/acc-eli"),
        ("DELETE", "/transactions/tx-eli"),
    ]
    assert fake_client.puts[0][1] == {"name": "Eliana", "color": "#5ab87a"}  # no code


# ---- the account saves, the opening balance is refused -----------------------------

FUTURE = EngineError(
    "VALIDATION_ERROR",
    "Transaction validation failed.",
    {"date": "Must not be in the future."},
    422,
    {},
    {"date": "FUTURE_DATE"},
)


def test_the_note_says_which_half_went_through_and_resends_only_the_opening(fake_client, notes):
    fake_client.errors["POST"] = FUTURE
    seen: dict = {}

    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening:PEN", "350.00")
        _type(screen, "as_of:PEN", "2026-11-01")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen.is_attached and screen._key == "as_of:PEN"
        seen["block"] = refusal_block(screen)
        assert screen.query_one("#bar", Input).value == "2026-11-01"  # still in the form
        assert (screen._values["opening:PEN"], screen._values["as_of:PEN"]) == (35000, "2026-11-01")
        seen["first"] = list(fake_client.requests)
        fake_client.errors.clear()
        _type(screen, "as_of:PEN", "2026-01-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(EFECTIVO, body)
    _no_failed_toast(notes)
    assert seen["block"] == (
        "Failed\nThe account's changes are saved. The PEN opening balance is not:\n"
        "VALIDATION_ERROR — Transaction validation failed.\n"
        "  date: Must not be in the future.\n\n"
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
    ids=["reserved-name", "opening-balance-exists", "concurrent-change"],
)
def test_a_half_refusal_with_a_next_step_ends_with_its_line(fake_client, notes, key, reason, line):
    """The account saved, the opening balance was refused for a reason that has
    its own line: the block is the half sentence, the engine's words, then that
    line, which takes the place of the form's own closing line."""
    fake_client.errors["POST"] = EngineError(
        "CONFLICT", "stand-in", {key: "stand-in field words"}, 409, {}, {key: reason}
    )

    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening:PEN", "350.00")
        _type(screen, "as_of:PEN", "2026-01-01")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        seen["block"] = refusal_block(screen)

    seen: dict = {}
    _form(EFECTIVO, body)
    _no_failed_toast(notes)
    assert seen["block"] == (
        "Failed\nThe account's changes are saved. The PEN opening balance is not:\n"
        f"CONFLICT — stand-in\n  {key}: stand-in field words\n\n{line}"
    )


def test_esc_after_one_opening_saved_and_another_refused_starts_the_list_over(fake_client, notes):
    """Only the opening balances are written: the dollars' is refused after the
    soles' landed. A write went through, so `esc` closes the form with `True`,
    the answer that makes the list reload. That the list then starts on row 1 is
    pinned in test_tui_manage_actions.py ("after an edit")."""
    plain = account_with_currencies(VISA, currencies=[held_currency("PEN"), held_currency("USD")])
    sent = fake_client.post

    def post(path, json_body=None):
        if json_body and json_body.get("currency_code") == "USD":
            fake_client.calls.append(("POST", path, json_body))
            raise FUTURE
        return sent(path, json_body)

    fake_client.post = post
    result: list = []

    async def scenario(pilot, app):
        screen = EditAccountScreen(plain, ENGINE_CURRENCIES)
        await app.push_screen(screen, result.append)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await wait_for(pilot, lambda: not screen._openings_loading)
        _type(screen, "opening:PEN", "350.00")
        _type(screen, "as_of:PEN", "2026-01-01")
        _type(screen, "opening:USD", "40.00")
        _type(screen, "as_of:USD", "2026-11-01")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen.is_attached
        await pilot.press("escape")
        await wait_for(pilot, lambda: result)

    run_app(scenario)
    assert [c[0:2] for c in fake_client.calls if c[0] == "POST"] == [
        ("POST", "/accounts/acc-visa/opening-balance"),
        ("POST", "/accounts/acc-visa/opening-balance"),
    ]
    assert result == [True]


def test_the_half_saved_block_names_the_currency_refused(fake_client, notes):
    """The account saves, the soles' opening balance lands and the dollars' is
    refused: the block names the dollars."""
    plain = account_with_currencies(VISA, currencies=[held_currency("PEN"), held_currency("USD")])
    sent = fake_client.post

    def post(path, json_body=None):
        if json_body and json_body.get("currency_code") == "USD":
            raise FUTURE
        return sent(path, json_body)

    fake_client.post = post

    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening:PEN", "350.00")
        _type(screen, "as_of:PEN", "2026-01-01")
        _type(screen, "opening:USD", "40.00")
        _type(screen, "as_of:USD", "2026-11-01")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        seen["block"] = refusal_block(screen)

    seen: dict = {}
    _form(plain, body)
    _no_failed_toast(notes)
    assert seen["block"].startswith(
        "Failed\nThe account's changes are saved. The USD opening balance is not:\n"
    )


def test_esc_just_leaves_with_the_account_saved(fake_client, notes):
    fake_client.errors["POST"] = FUTURE
    result: list = []

    async def scenario(pilot, app):
        screen = EditAccountScreen(EFECTIVO, ENGINE_CURRENCIES)
        await app.push_screen(screen, result.append)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        _type(screen, "color", "green")
        _type(screen, "opening:PEN", "350.00")
        _type(screen, "as_of:PEN", "2026-11-01")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: result)

    run_app(scenario)
    assert result == [True]  # a write went through: the list starts over
    assert len(fake_client.calls) == 2  # leaving sends nothing more


# ---- when the engine says no -------------------------------------------------------


@pytest.mark.parametrize(
    ("record", "steps", "verb", "error"),
    [
        (
            EFECTIVO,
            [("opening:PEN", "350.00"), ("as_of:PEN", "2026-11-01")],
            "POST",
            FUTURE,
        ),
        (
            EFECTIVO,
            [("opening:PEN", "0"), ("as_of:PEN", "2026-01-01")],
            "POST",
            EngineError(
                "VALIDATION_ERROR",
                "Transaction validation failed.",
                {"amount_cents": "Must not be zero."},
                422,
                {},
                {"amount_cents": "ZERO_AMOUNT"},
            ),
        ),
        (
            SUELDO,
            [("as_of:PEN", "2026-03-20")],
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
            [("opening:PEN", "350.00"), ("as_of:PEN", "2026-01-01")],
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
            [("opening:PEN", "-3000")],
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
def test_each_refusal_shows_in_the_engines_words(
    fake_client, notes, reads_log, record, steps, verb, error
):
    fake_client.errors[verb] = error
    typed: dict = {}

    async def body(pilot, app, screen):
        for key, text in steps:
            _type(screen, key, text)
        if screen.is_attached and not refusal_block(screen):
            await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen.is_attached  # nothing saved, the form stays
        typed.update(screen._values)
        typed["block"] = refusal_block(screen)

    _form(record, body)
    _no_failed_toast(notes)
    message = typed.pop("block")
    assert message.startswith(f"Failed\n{error.code} — {error.message}")
    for field, words in (error.fields or {}).items():
        assert f"  {field}: {words}" in message
    assert "account's changes" not in message  # the account was not part of this save
    for key, _text in steps:
        assert key in typed  # what was typed is still there


# ---- after a successful save -------------------------------------------------------


def _list_then_edit(fake_client, monkeypatch, steps, *, save: bool):
    # the list reads an account holding its currencies; the form is opened on the row's account
    accounts = [SUELDO, EFECTIVO]
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


def test_a_save_reloads_the_list_from_row_1_with_the_note(fake_client, notes, monkeypatch):
    steps = [("opening:PEN", "350.00"), ("as_of:PEN", "2026-01-01")]
    seen = _list_then_edit(fake_client, monkeypatch, steps, save=True)
    assert seen["cursor"] == "acc-sue"  # first page, cursor on row 1
    assert ("Saved.", {}) in notes
    assert ("POST", "/accounts/acc-efe/opening-balance") in fake_client.requests


def test_leaving_without_a_save_keeps_the_row(fake_client, notes, monkeypatch):
    seen = _list_then_edit(fake_client, monkeypatch, [], save=False)
    assert seen["cursor"] == "acc-efe"
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
    "Transaction validation failed.",
    {"amount_cents": "Must not be zero."},
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
        (ZERO, False, "opening:PEN", "0"),  # plain refusal → the amount line
        (FUTURE, True, "as_of:PEN", "2026-11-01"),  # half refusal → the date line
        (EXISTS, False, "opening:PEN", "350"),  # names no line: its currency's amount
    ],
    ids=["plain-amount", "half-date", "no-line-its-amount"],
)
def test_a_refusal_saved_from_another_line_lands_on_the_line_it_names(
    fake_client, notes, error, change_colour, lands_on, bar
):
    fake_client.errors["POST"] = error

    async def body(pilot, app, screen):
        if change_colour:
            _type(screen, "color", "green")  # enter here moves on, it does not save
        _type(screen, "opening:PEN", "0" if error is ZERO else "350.00")
        # the date set without enter on the last line, which would save from there
        screen._values["as_of:PEN"] = "2026-11-01" if error is FUTURE else "2026-01-01"
        _on(screen, "name")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        half = "The account's changes are saved." in refusal_block(screen)
        assert half is change_colour
        assert screen._key == lands_on
        assert screen.query_one("#bar", Input).value == bar  # what was typed

    _form(EFECTIVO, body)
