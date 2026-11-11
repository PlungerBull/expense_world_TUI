"""The account Edit form's opening balances — a pair of lines per currency,
`PEN opening` and `PEN as of`, then the next currency's.

A person's form has the same pair. Each
currency of the account names its opening balance by id
(contract: "Bank Accounts", "Opening balance"); the form reads that row signed
with one `GET /transactions/{id}`
(contract: "Base Conventions", "Sign convention — responses") and writes every
change in one `PUT /accounts/{id}`, its `opening_balances` keyed by currency code
(contract: PUT /v1/accounts/{account_id}, "`opening_balances`").
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
    ENGINE_BANKS,
    ENGINE_CURRENCIES,
    account_with_currencies,
    held_currency,
    refusal_block,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

CAJA = account_with_currencies(
    id="acc-caja", name="Caja", color=None, currencies=[held_currency("PEN")]
)
SUELDO = account_with_currencies(
    CAJA,
    id="acc-sue",
    name="Sueldo Soles",
    color="#4a90d9",
    currencies=[held_currency("PEN", opening_balance_transaction_id="tx-open")],
)
ELIANA = account_with_currencies(CAJA, id="acc-eli", name="Eliana", kind="person")
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
    "day": "2025-12-31",
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
    "day": "2026-01-01",
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
        screen = EditAccountScreen(record, ENGINE_CURRENCIES, ENGINE_BANKS)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await wait_for(pilot, lambda: not screen._openings_loading)
        return await body(pilot, app, screen)

    return run_app(scenario)


def _only_put(fake_client, account_id: str) -> dict:
    """The save was exactly one `PUT /accounts/{id}`: its body."""
    assert fake_client.requests == [("PUT", f"/accounts/{account_id}")]
    return fake_client.puts[0][1]


def _set_entry(entry: dict, cents: int, day: str) -> None:
    """`entry` is a set: a fresh `transaction_id`, the amount and the day, no title."""
    assert set(entry) == {"transaction_id", "amount_cents", "date"}
    assert len(entry["transaction_id"]) == 36
    assert (entry["amount_cents"], entry["date"]) == (cents, to_canonical_aware(day))


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
            "bank",
            "last4",
            "since",
            "new_card",
            "currencies",
            "statement_code",
            "color",
            "opening:PEN",
            "as_of:PEN",
        ]
        text = _summary(screen)
        assert "PEN opening — (optional)" in text
        assert "PEN as of — (optional)" in text
        assert screen._key == "bank"  # a bank account has no NAME line

    _form(CAJA, body)
    assert fake_client.calls == []  # null id: nothing to read


def test_nothing_changed_sends_one_put_with_an_empty_body(fake_client, notes):
    async def body(pilot, app, screen):
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(CAJA, body)
    assert _only_put(fake_client, "acc-caja") == {}
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

    _form(CAJA, body)


def test_the_amount_is_taken_as_typed_in_its_currency(fake_client):
    async def body(pilot, app, screen):
        assert screen._label("opening:USD") == "USD OPENING"
        _type(screen, "opening:USD", "-350.00")
        assert screen._values["opening:USD"] == -35000  # never flipped
        _type(screen, "opening:USD", "350")
        assert screen._values["opening:USD"] == 35000  # never flipped either way

    _form(account_with_currencies(CAJA, currencies=[held_currency("USD")]), body)


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

    _form(CAJA, body)
    assert [m for m, _ in notes] == [
        "PEN opening: a signed decimal, e.g. -350.00. Amounts are 1,234.56.",
        "PEN opening: a signed decimal, e.g. -350.00. Amounts are 1,234.56.",
        "PEN as of: use YYYY-MM-DD.",
        "PEN as of is required.",
    ]
    assert fake_client.calls == []


# ---- the word on the right: debt, credit or nothing --------------------------------


@pytest.mark.parametrize("record", ["bank", "person"])
def test_the_word_on_the_right_follows_the_sign_as_typed(fake_client, record):
    """`debt` below zero, `credit` above it, nothing while empty, at zero or unreadable,
    the same on a bank account and a person, with no currency after it; it follows
    the bar as it is typed, before `⏎`."""
    cases = [
        ("-150.00", "debt"),
        ("150.00", "credit"),
        ("", ""),
        ("0.00", ""),
        ("0", ""),
        ("-", ""),
    ]

    async def body(pilot, app, screen):
        for typed, word in cases:
            _on(screen, "opening:PEN")
            assert _word(screen) == ""
            screen.query_one("#bar", Input).value = typed
            await pilot.pause()
            assert _word(screen) == word
            _on(screen, "color")
            assert _word(screen) == ""  # no other line has a word

    _form(ELIANA if record == "person" else CAJA, body)


def test_the_word_shows_on_landing_on_a_filled_amount(fake_client, reads_log):
    async def body(pilot, app, screen):
        _on(screen, "opening:PEN")
        assert _word(screen) == "debt"  # -3,200.00, read
        _on(screen, "as_of:PEN")
        assert _word(screen) == ""

    _form(SUELDO, body)


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
USD_ROW = {
    **OPENING_ROW,
    "id": "tx-usd",
    "amount_cents": 4000,
    "date": "2026-02-01T00:00:00-05:00",
    "day": "2026-02-01",
}


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
            "bank BCP",
            "last 4 5678",
            "since first card",
            "new card — (optional)",
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


def test_changing_only_the_dollars_sets_the_dollars_alone(fake_client, reads_log):
    async def body(pilot, app, screen):
        _type(screen, "opening:USD", "-45.50")
        _type(screen, "as_of:USD", "2026-01-01")  # last line: enter saves
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA, body)
    body = _only_put(fake_client, "acc-visa")
    assert list(body) == ["opening_balances"] and list(body["opening_balances"]) == ["USD"]
    _set_entry(body["opening_balances"]["USD"], -4550, "2026-01-01")


def test_a_colour_and_one_currencys_set_go_in_one_put(fake_client, reads_log):
    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening:USD", "-45.50")
        _type(screen, "as_of:USD", "2026-01-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA, body)
    body = _only_put(fake_client, "acc-visa")
    assert set(body) == {"color", "opening_balances"} and body["color"] == "#5ab87a"
    assert list(body["opening_balances"]) == ["USD"]
    _set_entry(body["opening_balances"]["USD"], -4550, "2026-01-01")


def test_a_change_of_only_the_amount_sends_no_date_and_no_id(fake_client, reads_log):
    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-3000.00")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA, body)
    assert reads_log == ["tx-open"]
    assert _only_put(fake_client, "acc-visa") == {
        "opening_balances": {"PEN": {"amount_cents": -300000}}
    }


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
    assert _only_put(fake_client, "acc-visa") == {"opening_balances": {"PEN": None, "USD": None}}


def _keyed(key: str, reason: str, words: str = "stand-in field words", *, status: int = 422):
    """A refusal of the account's `PUT` naming one key
    (contract: PUT /v1/accounts/{account_id}, "Keys")."""
    code = "CONFLICT" if status == 409 else "VALIDATION_ERROR"
    return EngineError(code, "stand-in", {key: words}, status, {}, {key: reason})


def _refused_save(fake_client, error, record, steps, *, then_on="color"):
    """Type `steps`, save from `then_on` (a line that is not a pair's last), and read
    where the cursor, the bar and the block ended up."""
    fake_client.errors["PUT"] = error
    seen: dict = {}

    async def body(pilot, app, screen):
        for key, text in steps:
            if key.startswith("as_of:"):
                # a day is stored as typed; set without `⏎`, which on a pair's last
                # line would save from there
                screen._values[key] = text
            else:
                _type(screen, key, text)
        _on(screen, then_on)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen.is_attached  # nothing saved, the form stays
        seen["key"] = screen._key
        seen["bar"] = screen.query_one("#bar", Input).value
        seen["block"] = refusal_block(screen)
        seen["values"] = dict(screen._values)

    _form(record, body)
    assert len(fake_client.requests) == 1  # no retry beyond the client's own
    return seen


def test_a_date_refusal_lands_on_that_currencys_as_of_with_two_currencies(
    fake_client, notes, reads_log
):
    """USD's `date` is refused: the cursor is on `USD as of`, not `PEN as of`, holding
    what was typed, and PEN's typed pair stays in the form."""
    error = _keyed("opening_balances.USD.date", "FUTURE_DATE", "Must not be in the future.")
    seen = _refused_save(
        fake_client,
        error,
        account_with_currencies(VISA, currencies=[held_currency("PEN"), held_currency("USD")]),
        [
            ("opening:PEN", "100.00"),
            ("as_of:PEN", "2026-01-01"),
            ("opening:USD", "40.00"),
            ("as_of:USD", "2026-11-01"),
        ],
    )
    assert (seen["key"], seen["bar"]) == ("as_of:USD", "2026-11-01")
    assert "opening_balances.USD.date: Must not be in the future." in seen["block"]
    assert seen["values"]["opening:PEN"] == 10000 and seen["values"]["as_of:PEN"] == "2026-01-01"
    _no_failed_toast(notes)


def test_every_other_part_of_an_entry_lands_on_its_opening_line(fake_client, notes, reads_log):
    part = "title"
    error = _keyed(f"opening_balances.USD.{part}", "ZERO_AMOUNT")
    seen = _refused_save(
        fake_client,
        error,
        VISA,
        [("opening:USD", "0"), ("as_of:USD", "2026-01-01")],
    )
    assert (seen["key"], seen["bar"]) == ("opening:USD", "0")
    assert f"opening_balances.USD.{part}: stand-in field words" in seen["block"]


def test_a_refused_clear_lands_on_its_opening_line(fake_client, notes, reads_log):
    """NO_OPENING_BALANCE after `y`: the question was answered, one PUT went out, the
    line is the currency's `opening`, and the typed (emptied) bar is kept."""
    reads_log.rows = {"tx-usd": USD_ROW}
    fake_client.errors["PUT"] = _keyed("opening_balances.USD", "NO_OPENING_BALANCE")
    seen: dict = {}

    async def body(pilot, app, screen):
        _type(screen, "opening:USD", "")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        seen["key"] = screen._key
        seen["bar"] = screen.query_one("#bar", Input).value

    _form(VISA_BOTH, body)
    assert fake_client.puts == [("/accounts/acc-visa", {"opening_balances": {"USD": None}})]
    assert seen == {"key": "opening:USD", "bar": ""}


def test_an_archived_account_naming_two_codes_lands_on_the_first_in_the_forms_order(
    fake_client, notes, reads_log
):
    """ACCOUNT_ARCHIVED names every code sent: the cursor goes to the first in the
    form's order, wherever the engine lists it, and the block shows the engine's words
    whole, both keys."""
    words = "The account is archived. Unarchive it first."
    error = EngineError(
        "VALIDATION_ERROR",
        words,
        {"opening_balances.USD": words, "opening_balances.PEN": words},
        422,
        {},
        {"opening_balances.USD": "ACCOUNT_ARCHIVED", "opening_balances.PEN": "ACCOUNT_ARCHIVED"},
    )
    seen = _refused_save(
        fake_client,
        error,
        account_with_currencies(VISA, currencies=[held_currency("PEN"), held_currency("USD")]),
        [
            ("opening:PEN", "100.00"),
            ("as_of:PEN", "2026-01-01"),
            ("opening:USD", "40.00"),
            ("as_of:USD", "2026-01-01"),
        ],
    )
    assert (seen["key"], seen["bar"]) == ("opening:PEN", "100")
    assert f"  opening_balances.USD: {words}" in seen["block"]
    assert f"  opening_balances.PEN: {words}" in seen["block"]
    assert seen["block"].startswith(f"Failed\nVALIDATION_ERROR — {words}")


def test_missing_settings_shows_as_a_note_with_the_cursor_where_it_was(
    fake_client, notes, reads_log
):
    """`user_settings` is no line of the form: the block shows the engine's words and
    its hint, and the cursor stays."""
    error = EngineError(
        "SETTINGS_MISSING",
        "Settings are missing.",
        {"user_settings": "Settings are missing."},
        422,
        {},
        {"user_settings": "SETTINGS_MISSING"},
    )
    seen = _refused_save(
        fake_client,
        error,
        CAJA,
        [("opening:PEN", "350.00"), ("as_of:PEN", "2026-01-01")],
        then_on="color",
    )
    assert seen["key"] == "color"
    assert seen["block"].startswith("Failed\nSETTINGS_MISSING — Settings are missing.")
    assert "  user_settings: Settings are missing." in seen["block"]
    assert "Hint: First-time setup is not done yet." in seen["block"]
    _no_failed_toast(notes)


def test_a_bank_accounts_form_has_no_name_line_and_never_sends_a_name(fake_client, reads_log):
    async def body(pilot, app, screen):
        assert "name" not in screen._sequence() and "name" not in screen._values
        _type(screen, "color", "green")
        _type(screen, "statement_code", "SIG")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert _only_put(fake_client, "acc-sue") == {"color": "#5ab87a", "statement_code": "SIG"}


def test_a_name_refusal_on_a_bank_account_lands_on_no_line(fake_client, notes):
    """The form never sends a bank account's `name`; were one refused (`NAME_BUILT`),
    the form has no line for it and the cursor stays."""
    error = _keyed("name", "NAME_BUILT", "A bank account's name is the engine's.")
    seen = _refused_save(fake_client, error, CAJA, [("color", "green")])
    assert seen["key"] == "color"
    assert "  name: A bank account's name is the engine's." in seen["block"]


def test_a_persons_name_is_sent_only_when_changed_and_its_refusal_lands_on_it(fake_client, notes):
    error = _keyed("name", "NAME_EXISTS", "That name is taken.", status=409)
    seen = _refused_save(fake_client, error, ELIANA, [("name", "Eliana Vega")], then_on="color")
    assert fake_client.puts == [("/accounts/acc-eli", {"name": "Eliana Vega"})]
    assert (seen["key"], seen["bar"]) == ("name", "Eliana Vega")  # holding what was typed
    assert "  name: That name is taken." in seen["block"]


def test_a_refusal_keeps_everything_typed_and_the_next_save_sends_it_all_again(
    fake_client, notes, reads_log
):
    """Nothing was written: the same one body goes again, its set with a new id."""
    fake_client.errors["PUT"] = _keyed("opening_balances.PEN.date", "FUTURE_DATE")

    async def body(pilot, app, screen):
        _type(screen, "color", "green")
        _type(screen, "opening:PEN", "350.00")
        _type(screen, "as_of:PEN", "2026-11-01")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        fake_client.errors.clear()
        _type(screen, "as_of:PEN", "2026-01-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(CAJA, body)
    assert fake_client.requests == [("PUT", "/accounts/acc-caja")] * 2
    second = fake_client.puts[1][1]
    assert second["color"] == "#5ab87a"
    _set_entry(second["opening_balances"]["PEN"], 35000, "2026-01-01")


def test_a_second_refusal_after_a_fix_is_shown_again(fake_client, notes):
    """One write per save, so a form refused twice reads the second refusal."""
    fake_client.errors["PUT"] = _keyed("opening_balances.PEN.amount_cents", "ZERO_AMOUNT")

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "0")
        _type(screen, "as_of:PEN", "2026-01-01")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        fake_client.errors["PUT"] = _keyed("opening_balances.PEN.date", "FUTURE_DATE")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: "date:" in refusal_block(screen))
        await pilot.pause()
        assert screen._key == "as_of:PEN"

    _form(CAJA, body)


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
    assert _only_put(fake_client, "acc-visa") == {
        "opening_balances": {"PEN": {"amount_cents": -300000}}  # USD is never named
    }


#: The soles with no opening balance yet, the dollars with one.
VISA_USD_OPENED = account_with_currencies(
    VISA,
    currencies=[
        held_currency("PEN"),
        held_currency("USD", opening_balance_transaction_id="tx-usd"),
    ],
)


def test_a_set_and_a_change_of_two_currencies_go_in_one_put(fake_client, reads_log):
    """The soles have no opening balance, the dollars have one: PEN is a set, USD a
    change of only the amount."""
    reads_log.rows = {"tx-usd": USD_ROW}

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-100.00")
        _type(screen, "as_of:PEN", "2026-01-01")
        _type(screen, "opening:USD", "50.00")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(VISA_USD_OPENED, body)
    entries = _only_put(fake_client, "acc-visa")["opening_balances"]
    assert list(entries) == ["PEN", "USD"]
    _set_entry(entries["PEN"], -10000, "2026-01-01")
    assert entries["USD"] == {"amount_cents": 5000}


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


def test_a_changed_date_sends_only_the_date(fake_client, reads_log):
    async def body(pilot, app, screen):
        _type(screen, "as_of:PEN", "2026-02-01")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert _only_put(fake_client, "acc-sue") == {
        "opening_balances": {"PEN": {"date": to_canonical_aware("2026-02-01")}}
    }


def test_unchanged_the_save_is_one_put_with_an_empty_body(fake_client, reads_log):
    async def body(pilot, app, screen):
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert _only_put(fake_client, "acc-sue") == {}


def test_the_loading_note_names_the_currency_still_loading(fake_client, notes, monkeypatch):
    """Soles with no opening balance, dollars with one being read: the note
    names the dollars, the first currency still loading, not the first one."""
    release = threading.Event()

    def slow(cfg, transaction_id, **kw):
        release.wait(2)
        return USD_ROW

    monkeypatch.setattr("expense.reads.fetch_transaction", slow)

    async def scenario(pilot, app):
        screen = EditAccountScreen(VISA_USD_OPENED, ENGINE_CURRENCIES, ENGINE_BANKS)
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
    assert _only_put(fake_client, "acc-sue") == {}


# ---- ⏎ moves one line, and saves when no line ahead can change -----------------


@pytest.mark.parametrize(
    "record, lines",
    [
        (
            SUELDO,
            [
                "bank",
                "last4",
                "since",
                "new_card",
                "statement_code",
                "color",
                "opening:PEN",
                "as_of:PEN",
            ],
        ),
        (ELIANA, ["name", "color", "opening:PEN", "as_of:PEN"]),
    ],
    ids=["read-opening", "person"],
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
        _on(screen, "statement_code")
        await pilot.press("enter")
        await pilot.pause()
        assert screen._key == "color"
        await pilot.press(*"green")
        await pilot.press("enter")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(SUELDO, body)
    assert fake_client.puts == [("/accounts/acc-sue", {"color": "#5ab87a"})]
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


def test_emptying_the_amount_asks_first_then_y_sends_the_colour_and_the_clear(
    fake_client, reads_log
):
    asked = _empty_and_save(fake_client, "y")
    assert asked == {
        "title": "Delete this opening balance?",
        "message": "Sueldo Soles · PEN · -3,200.00 · 2026-01-01\n"
        "It leaves the account's balance, and no screen can bring it back.",
    }
    assert _only_put(fake_client, "acc-sue") == {
        "color": "#5ab87a",
        "opening_balances": {"PEN": None},
    }


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
    body = _only_put(fake_client, "acc-eli")
    assert set(body) == {"color", "opening_balances"}  # no name, no code
    _set_entry(body["opening_balances"]["PEN"], -15000, "2025-12-31")
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
    assert _only_put(fake_client, "acc-eli") == {
        "opening_balances": {"PEN": {"amount_cents": -20000}}
    }


def test_a_person_empties_its_opening_balance(fake_client, reads_log):
    reads_log.row = ELIANA_ROW
    asked = _empty_and_save(fake_client, "y", ELIANA_OPENED)
    assert asked == {
        "title": "Delete this opening balance?",
        "message": "Eliana · PEN · -150.00 · 2025-12-31\n"
        "It leaves the account's balance, and no screen can bring it back.",
    }
    assert _only_put(fake_client, "acc-eli") == {
        "color": "#5ab87a",
        "opening_balances": {"PEN": None},
    }


FUTURE = EngineError(
    "VALIDATION_ERROR",
    "Transaction validation failed.",
    {"opening_balances.PEN.date": "Must not be in the future."},
    422,
    {},
    {"opening_balances.PEN.date": "FUTURE_DATE"},
)


ZERO = EngineError(
    "VALIDATION_ERROR",
    "Transaction validation failed.",
    {"opening_balances.PEN.amount_cents": "Must not be zero."},
    422,
    {},
    {"opening_balances.PEN.amount_cents": "ZERO_AMOUNT"},
)
EXISTS = EngineError(
    "CONFLICT",
    "Account already has an opening balance.",
    {"opening_balances.PEN": "Account already has an opening balance."},
    409,
    {},
    {"opening_balances.PEN": "OPENING_BALANCE_EXISTS"},
)


def test_a_refusal_with_a_next_step_ends_with_its_line(fake_client, notes):
    """A reason that has its own line (`errors.next_step`) ends the block with it,
    after the engine's words; the cursor is on the line the key names."""
    key = "opening_balances.PEN.category_id"
    error = _keyed(key, "CONCURRENT_CHANGE", status=409)
    seen = _refused_save(
        fake_client, error, CAJA, [("opening:PEN", "350.00"), ("as_of:PEN", "2026-01-01")]
    )
    assert seen["key"] == "opening:PEN"
    words = f"{error.code} — stand-in\n  {key}: stand-in field words"
    assert seen["block"] == f"Failed\n{words}\n\nIt changed at the same moment: save again."
    _no_failed_toast(notes)


# ---- after a successful save -------------------------------------------------------


def _list_then_edit(fake_client, monkeypatch, steps, *, save: bool):
    # the list reads an account holding its currencies; the form is opened on the row's account
    accounts = [SUELDO, CAJA]
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(accounts))
    seen: dict = {}

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("down")  # cursor → Caja
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
    assert fake_client.requests == [("PUT", "/accounts/acc-caja")]


def test_leaving_without_a_save_keeps_the_row(fake_client, notes, monkeypatch):
    seen = _list_then_edit(fake_client, monkeypatch, [], save=False)
    assert seen["cursor"] == "acc-caja"
    assert fake_client.requests == []


# ---- a refusal lands on the line it names ----------------------------------------------


@pytest.mark.parametrize(
    ("error", "lands_on", "bar"),
    [
        (ZERO, "opening:PEN", "0"),  # the amount's key → the amount line
        (FUTURE, "as_of:PEN", "2026-11-01"),  # the date's key → the date line
        (EXISTS, "opening:PEN", "350"),  # the whole entry's key → its amount line
    ],
    ids=["amount", "date", "whole-entry"],
)
def test_a_refusal_saved_from_another_line_lands_on_the_line_it_names(
    fake_client, notes, error, lands_on, bar
):
    """The engine's words are the block under the form, whole, and what was typed stays."""
    fake_client.errors["PUT"] = error

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "0" if error is ZERO else "350.00")
        # the date set without enter on the last line, which would save from there
        screen._values["as_of:PEN"] = "2026-11-01" if error is FUTURE else "2026-01-01"
        _on(screen, "color")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen))
        await pilot.pause()
        assert screen.is_attached  # nothing saved, the form stays
        assert screen._key == lands_on
        assert screen.query_one("#bar", Input).value == bar  # what was typed
        block = refusal_block(screen)
        assert block.startswith(f"Failed\n{error.code} — {error.message}")
        for field, words in error.fields.items():
            assert f"  {field}: {words}" in block

    _form(CAJA, body)
    _no_failed_toast(notes)


def test_an_exponent_inf_or_nan_is_unreadable_and_sends_nothing(fake_client, notes):
    typed = ["1e5000", "1e5", "inf", "nan", "-Infinity"]

    async def body(pilot, app, screen):
        for text in typed:
            _type(screen, "opening:PEN", text)
            assert screen._key == "opening:PEN" and "opening:PEN" not in screen._values

    _form(CAJA, body)
    assert [m for m, _ in notes] == [
        "PEN opening: a signed decimal, e.g. -350.00. Amounts are 1,234.56."
    ] * len(typed)
    assert fake_client.calls == []


def test_a_plain_amount_past_the_bound_is_kept_to_be_sent_and_shown(fake_client, notes):
    """The form adds no bound: the engine refuses what is past its own. The summary
    prints a 25-digit amount, negative too, without raising."""

    async def body(pilot, app, screen):
        _type(screen, "opening:PEN", "-1000000000.00")
        assert screen._values["opening:PEN"] == -100000000000
        _type(screen, "opening:PEN", "9" * 25)
        assert screen._values["opening:PEN"] == int("9" * 25) * 100
        assert "9,999,999,999,999,999,999,999,999.00" in _summary(screen)
        _type(screen, "opening:PEN", "-" + "9" * 25)
        assert "-9,999,999,999,999,999,999,999,999.00" in _summary(screen)

    _form(CAJA, body)
    assert notes == []
