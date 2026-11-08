"""The New statement form: a starting and an ending balance line for each currency of
the account, each optional, one `POST /statements`, and the engine's refusals landing on
the currency's line."""

from textual.widgets import Input, Label, Static

from expense.errors import EngineError, format_error
from expense.tui.screens.statements import NewStatementScreen
from tests.unit.helpers import (
    account_with_currencies,
    held_currency,
    no_failed_toast,
    refusal_block,
    render_text,
    run_app,
    wait_for,
    whole,
)

OPENING_NOTE = "0.00 if it holds the account's opening balance, which already counts it"


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


def _visa() -> NewStatementScreen:
    return NewStatementScreen(
        account_id="v1", account_name="Visa BCP", currencies=("PEN", "USD"), code="VIS"
    )


def _head(screen) -> None:
    """Name and the two days, so the cursor is on the first currency's starting balance."""
    _enter(screen, "Noviembre 2026")
    _enter(screen, "2026-10-26")
    _enter(screen, "2026-11-25")


def _refused(code, message, field, reason, status=422):
    return EngineError(
        code, message, {field: f"Words of {field}."}, status, {}, reasons={field: reason}
    )


def _notices(monkeypatch) -> list:
    notices: list = []
    monkeypatch.setattr(
        NewStatementScreen,
        "notify",
        lambda self, message, title="", **kw: notices.append((title, str(message))),
    )
    return notices


def test_a_one_currency_account_has_one_pair_of_lines_and_a_two_currency_one_two():
    one = NewStatementScreen(account_id="a", account_name="BCP", currencies=("PEN",))
    assert one._sequence() == ["name", "date_start", "date_end", "begin:PEN", "end:PEN"]
    assert _visa()._sequence() == [
        "name",
        "date_start",
        "date_end",
        "begin:PEN",
        "end:PEN",
        "begin:USD",
        "end:USD",
    ]
    assert not {"begin:PEN", "end:PEN"} & set(one._required())  # every balance is optional
    assert not any(k.startswith(("begin", "end")) for k in _visa()._required())


def test_the_form_reads_at_80_columns(fake_client):
    """Each currency's lines named by it, the starting balance's second hint line on each,
    the account stated in the summary and never edited."""

    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        assert screen.size.width == 80
        _head(screen)
        _enter(screen, "-234.20")
        assert screen._key == "end:PEN"
        screen.action_field(1)  # begin:USD
        assert str(screen.query_one("#field", Label).render()) == "BEGIN BALANCE USD"
        hint = screen.query_one("#hint", Static)
        shown = render_text(hint.content, width=hint.content_size.width).splitlines()
        assert shown == [
            "signed decimal · the statement's opening balance in USD · optional",
            OPENING_NOTE,
        ]
        summary = render_text(screen._summary_renderable(), width=80).splitlines()
        assert [line.split() for line in summary] == [
            ["name", "Noviembre", "2026"],
            ["account", "Visa", "BCP", "·", "PEN", "+", "USD", "·", "VIS"],
            ["date", "start", "2026-10-26"],
            ["date", "end", "2026-11-25"],
            ["begin", "balance", "PEN", "-234.20"],
            ["end", "balance", "PEN", "—", "(optional)"],
            ["begin", "balance", "USD", "—", "(optional)"],
            ["end", "balance", "USD", "—", "(optional)"],
        ]

    run_app(scenario)


def test_the_last_ending_balance_says_enter_saves_and_no_other_does():
    screen = _visa()
    assert "saves" in screen._hint_for("end:USD")
    assert not any("sav" in screen._hint_for(k) for k in screen._sequence()[:-1])


def test_a_currency_left_empty_is_not_sent(fake_client):
    """Only PEN typed on a two-currency account: one entry, the end left out where none
    was typed; the body is exactly StatementCreateRequest's."""

    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        _head(screen)
        _enter(screen, "-234.20")  # begin PEN
        _enter(screen, "")  # end PEN
        _enter(screen, "")  # begin USD
        _enter(screen, "")  # end USD → saves
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(path, body)] = fake_client.posts
    assert path == "/statements"
    assert set(body) == {"id", "account_id", "name", "date_start", "date_end", "balances"}
    assert body["account_id"] == "v1"
    assert body["balances"] == [{"currency_code": "PEN", "beginning_balance_cents": -23420}]


def test_both_currencies_typed_send_one_entry_each(fake_client):
    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        _head(screen)
        for text in ("-234.20", "-250.00", "-30.98", ""):
            _enter(screen, text)
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(_path, body)] = fake_client.posts
    assert body["balances"] == [
        {"currency_code": "PEN", "beginning_balance_cents": -23420, "ending_balance_cents": -25000},
        {"currency_code": "USD", "beginning_balance_cents": -3098},
    ]


def test_nothing_typed_sends_an_empty_balances_for_the_engine_to_judge(fake_client):
    async def scenario(pilot, app):
        screen = NewStatementScreen(account_id="a", account_name="BCP", currencies=("PEN",))
        await app.push_screen(screen)
        _head(screen)
        _enter(screen, "")
        _enter(screen, "")
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    assert fake_client.posts[0][1]["balances"] == []


def test_an_ending_balance_without_its_starting_one_is_not_sent(fake_client, monkeypatch):
    """An entry takes `beginning_balance_cents` always, so the input is not well-formed:
    the cursor goes to that starting balance and nothing is sent."""
    notices = _notices(monkeypatch)

    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        _head(screen)
        _enter(screen, "-234.20")
        _enter(screen, "")
        _enter(screen, "")  # begin USD empty
        _enter(screen, "-30.00")  # end USD → saves
        await pilot.pause()
        assert screen._key == "begin:USD" and not screen._submitting

    run_app(scenario)
    assert fake_client.posts == []
    assert notices == [("", "Begin balance USD: an end balance needs it too.")]


def test_money_at_start_not_covered_lands_on_that_currencys_starting_balance(
    fake_client, monkeypatch
):
    """Nothing is created: the form keeps what was typed, the cursor goes to the named
    currency's starting balance, and the engine's words show whole."""
    err = _refused(
        "VALIDATION_ERROR", "Every currency with money at the start needs balances.",
        "balances.USD", "MONEY_AT_START_NOT_COVERED",
    )  # fmt: skip
    fake_client.errors["POST"] = err
    shown: list = []

    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        _head(screen)
        _enter(screen, "-234.20")
        typed = dict(screen._values)
        _enter(screen, "")  # end PEN
        _enter(screen, "")  # begin USD
        _enter(screen, "")  # end USD → saves
        await wait_for(pilot, lambda: refusal_block(screen) and not screen._submitting)
        assert no_failed_toast(app)
        shown.append(refusal_block(screen))
        assert screen._key == "begin:USD"
        assert screen.query_one("#bar", Input).value == ""
        assert screen._values == typed

    run_app(scenario, toasts=True)
    assert shown == [f"Failed\n{format_error(err)}"]
    assert "Words of balances.USD." in shown[0]


def test_a_currency_not_held_lands_on_the_entry_it_names(fake_client, monkeypatch):
    """`balances.<i>.currency_code` is the i-th entry sent: here the second, USD."""
    err = _refused(
        "VALIDATION_ERROR", "Statement validation failed.",
        "balances.1.currency_code", "CURRENCY_NOT_HELD",
    )  # fmt: skip
    fake_client.errors["POST"] = err
    shown: list = []

    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        _head(screen)
        for text in ("-234.20", "", "-30.98", ""):
            _enter(screen, text)
        await wait_for(pilot, lambda: refusal_block(screen) and not screen._submitting)
        assert no_failed_toast(app)
        shown.append(refusal_block(screen))
        assert screen._key == "begin:USD"
        assert screen.query_one("#bar", Input).value == "-30.98"

    run_app(scenario, toasts=True)
    assert shown == [f"Failed\n{format_error(err)}"]
    assert "balances.1.currency_code: Words of balances.1.currency_code." in shown[0]


def test_a_currency_joining_or_leaving_mid_write_says_save_again(fake_client, monkeypatch):
    """`CONCURRENT_CHANGE` on `account_id`: the engine's words and the app's existing line
    ending `save again.`; no currency's line is named, so the cursor stays."""
    err = _refused("CONFLICT", "The account changed.", "account_id", "CONCURRENT_CHANGE", 409)
    fake_client.errors["POST"] = err
    shown: list = []

    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        _head(screen)
        for text in ("-234.20", "", "", ""):
            _enter(screen, text)
        await wait_for(pilot, lambda: refusal_block(screen) and not screen._submitting)
        assert no_failed_toast(app)
        shown.append(refusal_block(screen))
        assert screen._key == "end:USD"

    run_app(scenario, toasts=True)
    [block] = shown
    text = block.removeprefix("Failed\n")
    assert block == f"Failed\n{format_error(err)}"
    assert "The account changed." in text
    assert text.endswith("It changed at the same moment: save again.")


def test_the_picker_lists_each_account_by_its_name_alone(fake_client, monkeypatch):
    """No code after a name, no `?`; the
    pick gives the form its currencies' lines and the account line."""
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole(
            [
                account_with_currencies(id="a1", name="Visa BCP", statement_code="VIS"),
                account_with_currencies(id="a2", name="Soles", currencies=[held_currency("PEN")]),
                account_with_currencies(id="a3", name="Dollars", currencies=[held_currency("USD")]),
            ]
        ),
    )

    async def scenario(pilot, app):
        screen = NewStatementScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._accounts)
        _enter(screen, "Octubre")
        assert screen._key == "account"
        assert [len(s) for s in screen._suggestions] == [2, 2, 2]
        shown = render_text(screen._suggest_renderable(), width=80)
        assert [line.strip() for line in shown.splitlines()] == ["Visa BCP", "Soles", "Dollars"]
        assert "?" not in shown
        _enter(screen, "Dollars")
        assert screen._sequence()[-2:] == ["begin:USD", "end:USD"]
        assert screen._display["account"] == "Dollars · USD"

    run_app(scenario)


def test_a_refused_index_counts_the_entries_sent_not_the_currencies_of_the_account(
    fake_client, monkeypatch
):
    """PEN left empty, so USD is entry 0 of `balances`: `balances.0.currency_code` names USD."""
    err = _refused(
        "VALIDATION_ERROR", "Statement validation failed.",
        "balances.0.currency_code", "CURRENCY_NOT_HELD",
    )  # fmt: skip
    fake_client.errors["POST"] = err
    shown: list = []

    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        _head(screen)
        for text in ("", "", "-30.98", ""):
            _enter(screen, text)
        await wait_for(pilot, lambda: refusal_block(screen) and not screen._submitting)
        assert no_failed_toast(app)
        shown.append(refusal_block(screen))
        assert screen._key == "begin:USD"

    run_app(scenario, toasts=True)
    assert shown == [f"Failed\n{format_error(err)}"]
    assert "Words of balances.0.currency_code." in shown[0]


def test_every_hint_fits_one_row_at_80_columns(fake_client):
    """Each line's hint, one currency or two, wraps onto no second row."""

    async def scenario(pilot, app):
        for currencies in (("PEN",), ("PEN", "USD")):
            screen = NewStatementScreen(
                account_id="a", account_name="Visa BCP", currencies=currencies
            )
            await app.push_screen(screen)
            hint = screen.query_one("#hint", Static)
            assert screen.size.width == 80
            for key in screen._sequence():
                for row in screen._hint_for(key).split("\n"):
                    assert len(row) <= hint.content_size.width, (key, row)
            await app.pop_screen()

    run_app(scenario)


def test_an_unreadable_balance_names_its_currency_on_a_two_currency_form(fake_client):
    """The note carries the code the line's label carries, so USD's reads as USD's."""

    async def scenario(pilot, app):
        screen = _visa()
        await app.push_screen(screen)
        notes: list[str] = []
        screen.notify = lambda message, **kw: notes.append(str(message))
        _head(screen)
        _enter(screen, "abc")  # begin:PEN
        assert screen._key == "begin:PEN"
        screen.action_field(1)  # end:PEN
        screen.action_field(1)  # begin:USD
        assert screen._key == "begin:USD"
        _enter(screen, "abc")
        screen.action_field(1)  # end:USD
        assert screen._key == "end:USD"
        _enter(screen, "abc")
        assert notes == [
            "Begin balance PEN: a signed decimal, e.g. 9580.00",
            "Begin balance USD: a signed decimal, e.g. 9580.00",
            "End balance USD: a signed decimal, e.g. 9460.00",
        ]

    run_app(scenario)
