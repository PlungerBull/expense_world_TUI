"""The New account form: its lines, and its one `POST /accounts` with the openings.

A bank account has `type`, `bank`, `last 4`, `currencies`, `statement code`, `color`, then
an `opening` and `as of` line per currency picked; a person has `type`, `name`,
`currencies`, `color` and the pairs. The save is one write and every refusal lands on the
line its key names (contract: POST /v1/accounts).
"""

import threading

import httpx
import pytest
import respx
from textual.widgets import Input

from expense import config as config_module
from expense.errors import EngineError, format_error
from expense.reads import fetch_bank_codes
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.create_forms import CASH_NAME, NewAccountScreen
from tests.unit.helpers import (
    ENGINE_BANKS,
    ENGINE_CURRENCIES,
    ENGINE_URL,
    account_with_currencies,
    banks_answer,
    no_failed_toast,
    refusal_block,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

PAIRS = ["opening:PEN", "as_of:PEN", "opening:USD", "as_of:USD"]


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


def _screen(banks=ENGINE_BANKS):
    return NewAccountScreen(ENGINE_CURRENCIES, banks)


def _fill(screen, values: dict) -> None:
    """The form as if `values` were typed, bypassing the keys."""
    screen._values.update(values)


def _run(fake_client, screen, values, *, error=None, check=None):
    """Open `screen` holding `values`, `ctrl+s`, and run `check(pilot, screen)` once the
    write is answered; a refusal `error` makes the engine refuse it."""
    if error is not None:
        fake_client.errors["POST"] = error

    async def scenario(pilot, app):
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        _fill(screen, values)
        await pilot.press("ctrl+s")
        if error is None:
            await wait_for(pilot, lambda: fake_client.posts)
        else:
            await wait_for(pilot, lambda: refusal_block(screen), message="no refusal shown")
            await pilot.pause()
            assert no_failed_toast(app)
        if check:
            await check(pilot, screen)

    run_app(scenario, toasts=error is not None)


# ---- the lines -----------------------------------------------------------------------


def test_a_bank_account_has_the_lines_of_the_mockup_in_its_order():
    screen = _screen()
    assert screen._sequence() == ["type", "bank", "last4", "currencies", "statement_code", "color"]
    _fill(screen, {"currencies": ["PEN", "USD"]})
    assert screen._sequence() == [
        "type",
        "bank",
        "last4",
        "currencies",
        "statement_code",
        "color",
        *PAIRS,
    ]
    assert "name" not in screen._sequence()
    assert [screen._summary_label(k) for k in screen._sequence()] == [
        "type",
        "bank",
        "last 4",
        "currencies",
        "statement code",
        "color",
        "PEN opening",
        "PEN as of",
        "USD opening",
        "USD as of",
    ]


def test_a_person_has_no_bank_last_4_or_code_and_they_return_holding_what_was_typed():
    screen = _screen()
    _fill(screen, {"currencies": ["PEN", "USD"], "bank": "BCP", "last4": "5678"})
    _fill(screen, {"statement_code": "SIG"})
    _fill(screen, {"type": "person"})
    assert screen._sequence() == ["type", "name", "currencies", "color", *PAIRS]
    _fill(screen, {"type": "bank"})
    assert screen._sequence()[:3] == ["type", "bank", "last4"]
    assert screen._values["bank"] == "BCP"
    assert screen._values["last4"] == "5678" and screen._values["statement_code"] == "SIG"


def test_bank_offers_the_engines_banks_in_its_order_and_last_4_is_optional():
    screen = _screen(["BCP", "BBVA", "IBK"])
    assert screen._field("bank").choices == [("BCP", "BCP"), ("BBVA", "BBVA"), ("IBK", "IBK")]
    assert screen._field("bank").kind == "choice"
    assert "bank" in screen._required() and "last4" not in screen._required()
    assert screen._hint_for("last4") == "optional · the card's last 4 digits · enter to go on"


def test_the_pair_lines_are_the_edit_forms_a_day_is_required_once_an_amount_is_typed():
    screen = _screen()
    _fill(screen, {"currencies": ["PEN"], "bank": "BCP"})
    assert "as_of:PEN" not in screen._required()
    _fill(screen, {"opening:PEN": -120000})
    assert "as_of:PEN" in screen._required()
    assert screen._required_note("as_of:PEN") == "PEN as of is required."


# ---- the one write ---------------------------------------------------------------------


def test_a_bank_account_in_two_currencies_with_one_opening_is_one_whole_post(fake_client):
    screen = _screen()
    _run(
        fake_client,
        screen,
        {
            "bank": "BCP",
            "last4": "5678",
            "currencies": ["USD", "PEN"],
            "statement_code": "SIG",
            "color": "#4a90d9",
            "opening:PEN": -120000,
            "as_of:PEN": "2026-01-01",
        },
    )
    assert fake_client.requests == [("POST", "/accounts")]
    _, body = fake_client.posts[0]
    opening = body["currencies"][1]["opening_balance"]
    assert body == {
        "id": body["id"],
        "kind": "bank",
        "bank_code": "BCP",
        "last4": "5678",
        "currencies": [
            {"currency_code": "USD"},
            {
                "currency_code": "PEN",
                "opening_balance": {
                    "transaction_id": opening["transaction_id"],
                    "amount_cents": -120000,
                    "date": opening["date"],
                },
            },
        ],
        "color": "#4a90d9",
        "statement_code": "SIG",
    }
    assert opening["date"].startswith("2026-01-01T00:00:00")  # the Edit form's wire form
    assert "name" not in body


def test_a_person_sends_its_name_and_no_bank_fields(fake_client):
    screen = _screen()
    _run(
        fake_client,
        screen,
        {
            "type": "person",
            "name": "Eliana",
            "currencies": ["PEN"],
            "bank": "BCP",
            "last4": "5678",
            "statement_code": "SIG",
            "opening:PEN": 50000,
            "as_of:PEN": "2026-02-03",
        },
    )
    _, body = fake_client.posts[0]
    opening = body["currencies"][0]["opening_balance"]
    assert body == {
        "id": body["id"],
        "kind": "person",
        "name": "Eliana",
        "currencies": [
            {
                "currency_code": "PEN",
                "opening_balance": {
                    "transaction_id": opening["transaction_id"],
                    "amount_cents": 50000,
                    "date": opening["date"],
                },
            }
        ],
    }


def test_an_opening_with_no_day_is_refused_before_anything_is_sent(fake_client):
    notes: list = []

    async def scenario(pilot, app):
        screen = _screen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        _fill(screen, {"bank": "BCP", "currencies": ["PEN"], "opening:PEN": 100})
        await pilot.press("ctrl+s")
        await pilot.pause()
        notes.append(screen._required_note("as_of:PEN"))

    run_app(scenario)
    assert notes == ["PEN as of is required."]
    assert not fake_client.calls


# ---- refusals land on their line -------------------------------------------------------


def _refusal(code, status, **keyed):
    """An engine refusal naming `keyed` (`{key: (reason, words)}`)."""
    return EngineError(
        code,
        "refused",
        {key: words for key, (_, words) in keyed.items()},
        status,
        {},
        {key: reason for key, (reason, _) in keyed.items()},
    )


FULL = {
    "bank": "BCP",
    "last4": "5678",
    "currencies": ["PEN", "USD"],
    "opening:PEN": -100,
    "as_of:PEN": "2026-01-01",
    "opening:USD": 200,
    "as_of:USD": "2026-01-02",
}


@pytest.mark.parametrize(
    ("key", "reason", "status", "line"),
    [
        ("bank_code", "UNSUPPORTED_VALUE", 422, "bank"),
        ("last4", "INVALID_FORMAT", 422, "last4"),
        ("currencies", "OUT_OF_RANGE", 422, "currencies"),
        ("currencies.1.currency_code", "UNSUPPORTED_VALUE", 422, "currencies"),
        ("currencies.1.opening_balance.amount_cents", "ZERO_AMOUNT", 422, "opening:USD"),
        ("currencies.0.opening_balance.transaction_id", "DUPLICATE_IN_REQUEST", 422, "opening:PEN"),
        ("currencies.1.opening_balance.date", "FUTURE_DATE", 422, "as_of:USD"),
    ],
)
def test_a_refusal_lands_on_the_line_its_key_names_holding_what_was_typed(
    fake_client, key, reason, status, line
):
    code = "CONFLICT" if status == 409 else "VALIDATION_ERROR"
    refusal = _refusal(code, status, **{key: (reason, "the engine's words.")})

    async def check(pilot, screen):
        assert refusal_block(screen) == f"Failed\n{format_error(refusal)}"
        assert screen._key == line
        assert screen.is_attached
        assert screen._values == {"type": "bank", **FULL}

    _run(fake_client, _screen(), FULL, error=refusal, check=check)


def test_the_currency_a_key_names_is_the_one_at_its_place_in_the_body_sent(fake_client):
    """Picked USD first, then PEN: `currencies.0` is USD, so its `date` refusal is on USD's
    `as of` line."""
    refusal = _refusal(
        "VALIDATION_ERROR",
        422,
        **{"currencies.0.opening_balance.date": ("FUTURE_DATE", "No future days.")},
    )
    values = {**FULL, "currencies": ["USD", "PEN"]}

    async def check(pilot, screen):
        assert screen._key == "as_of:USD"

    _run(fake_client, _screen(), values, error=refusal, check=check)


def test_a_person_name_refusal_lands_on_name(fake_client):
    refusal = _refusal("CONFLICT", 409, name=("NAME_EXISTS", "Name already exists."))

    async def check(pilot, screen):
        assert screen._key == "name"
        assert screen.query_one("#bar", Input).value == "Eliana"

    _run(
        fake_client,
        _screen(),
        {"type": "person", "name": "Eliana", "currencies": ["PEN"]},
        error=refusal,
        check=check,
    )


def test_a_taken_id_naming_several_ids_shows_every_one(fake_client):
    refusal = _refusal(
        "CONFLICT",
        409,
        id=("ID_EXISTS", "That id is taken."),
        **{
            "currencies.0.opening_balance.transaction_id": ("ID_EXISTS", "Taken (a)."),
            "currencies.1.opening_balance.transaction_id": ("ID_EXISTS", "Taken (b)."),
        },
    )

    async def check(pilot, screen):
        shown = refusal_block(screen)
        assert shown is not None
        for words in ("That id is taken.", "Taken (a).", "Taken (b)."):
            assert words in shown
        assert screen._key == "opening:PEN"  # the first line a key names

    _run(fake_client, _screen(), FULL, error=refusal, check=check)


def test_settings_missing_shows_as_a_note_and_the_cursor_stays(fake_client):
    refusal = _refusal(
        "SETTINGS_MISSING",
        422,
        user_settings=("NOT_PROVISIONED", "Must be provisioned via POST /v1/auth/bootstrap."),
    )

    async def check(pilot, screen):
        shown = refusal_block(screen)
        assert shown is not None and "user_settings" in shown and "First-time setup" in shown
        assert screen._key == "type"
        assert screen._values == {"type": "bank", **FULL}

    _run(fake_client, _screen(), FULL, error=refusal, check=check)


# ---- the banks read --------------------------------------------------------------------


def test_the_bank_codes_are_the_engines_list_in_its_order(configured):
    """`GET /banks` is the one source: the codes come in the engine's order, and an
    entry without a code is skipped (contract: GET /v1/banks)."""
    cfg = config_module.load()
    with respx.mock() as engine:
        route = engine.get(f"{ENGINE_URL}/v1/banks")
        route.mock(httpx.Response(200, json=banks_answer(["BCP", "BBVA"])))
        assert fetch_bank_codes(cfg) == ["BCP", "BBVA"]
        route.mock(httpx.Response(200, json={"items": [{"code": "BCP", "name": "x"}, {}]}))
        assert fetch_bank_codes(cfg) == ["BCP"]


def test_the_accounts_screen_reads_the_banks_and_hands_them_to_the_new_and_edit_forms(monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_bank_codes", lambda cfg, **kw: ["BCP", "IBK"])
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen._banks == ["BCP", "IBK"]
        form = screen.new_screen()
        assert form._field("bank").choices == [("BCP", "BCP"), ("IBK", "IBK")]
        form = screen.edit_screen(account_with_currencies(id="acc-bcp", name="BCP-5678"))
        assert form._field("bank").choices == [("BCP", "BCP"), ("IBK", "IBK")]

    run_app(scenario)


# ---- the cash account -------------------------------------------------------------------


def _cash_screen():
    return NewAccountScreen(ENGINE_CURRENCIES, ENGINE_BANKS, cash_offered=True)


def _new_form_with_accounts(monkeypatch, accounts):
    """The New form the Accounts screen hands over when the engine lists `accounts`; the
    read asked for archived accounts."""
    asked: list = []

    def fetch_accounts(cfg, **kw):
        asked.append(kw)
        return whole(accounts)

    monkeypatch.setattr("expense.reads.fetch_accounts", fetch_accounts)
    monkeypatch.setattr("expense.reads.fetch_bank_codes", lambda cfg, **kw: ["BCP"])
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    forms: list = []

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        forms.append(screen.new_screen())

    run_app(scenario)
    assert asked and all(kw.get("include_archived") for kw in asked)
    return forms[0]


@pytest.mark.parametrize(
    ("accounts", "offered"),
    [
        ([], True),
        ([account_with_currencies(id="a-1", kind="bank")], True),
        ([account_with_currencies(id="c-1", kind="cash", name="Efectivo")], False),
        (
            [account_with_currencies(id="c-1", kind="cash", name="Efectivo", is_archived=True)],
            False,
        ),
    ],
    ids=["none", "a bank only", "live cash", "archived cash"],
)
def test_cash_is_offered_only_while_no_account_of_kind_cash_exists(monkeypatch, accounts, offered):
    form = _new_form_with_accounts(monkeypatch, accounts)
    values = [v for v, _ in form._field("type").choices]
    assert values == (["bank", "person", "cash"] if offered else ["bank", "person"])
    hint = form._hint_for("type")
    assert ("cash" in hint) is offered
    assert hint == (
        "bank, person or cash · enter keeps bank"
        if offered
        else "bank or person · enter keeps bank"
    )


def test_a_cash_account_has_the_lines_of_the_mockup_and_the_name_is_the_engines():
    screen = _cash_screen()
    _fill(screen, {"currencies": ["PEN", "USD"], "type": "cash"})
    assert screen._sequence() == ["type", "name", "currencies", "color", *PAIRS]
    shown = render_text(screen._summary_renderable(), width=100)
    lines = [" ".join(line.split()) for line in shown.splitlines()]
    assert lines[:2] == ["type cash", f"name {CASH_NAME}"]  # the key-driven test adds the word
    assert not any(word in shown for word in ("bank ", "last 4", "statement code"))
    assert "NAME is required" not in shown and screen._required() == ("type", "currencies")


def test_switching_the_type_back_restores_what_was_typed_on_a_bank_account():
    screen = _cash_screen()
    _fill(screen, {"bank": "BCP", "last4": "5678", "statement_code": "SIG"})
    _fill(screen, {"type": "cash"})
    assert "bank" not in screen._sequence() and "statement_code" not in screen._sequence()
    _fill(screen, {"type": "bank"})
    assert screen._sequence()[:3] == ["type", "bank", "last4"]
    assert "statement_code" in screen._sequence()
    shown = render_text(screen._summary_renderable(), width=100)
    assert "BCP" in shown and "5678" in shown and "SIG" in shown


def test_a_cash_account_is_one_whole_post_with_no_name_bank_number_or_code_and_each_opening(
    fake_client,
):
    _run(
        fake_client,
        _cash_screen(),
        {
            "type": "cash",
            "currencies": ["PEN", "USD"],
            "color": "#4a90d9",
            "bank": "BCP",
            "last4": "5678",
            "statement_code": "SIG",
            "name": "Caja",
            "opening:PEN": 23750,
            "as_of:PEN": "2026-11-01",
            "opening:USD": -4550,
            "as_of:USD": "2026-11-02",
        },
    )
    assert fake_client.requests == [("POST", "/accounts")]
    _, body = fake_client.posts[0]
    soles, dollars = (c["opening_balance"] for c in body["currencies"])
    assert soles["transaction_id"] != dollars["transaction_id"]
    assert soles["date"].startswith("2026-11-01T") and dollars["date"].startswith("2026-11-02T")
    assert body == {
        "id": body["id"],
        "kind": "cash",
        "currencies": [
            {
                "currency_code": "PEN",
                "opening_balance": {
                    "transaction_id": soles["transaction_id"],
                    "amount_cents": 23750,
                    "date": soles["date"],
                },
            },
            {
                "currency_code": "USD",
                "opening_balance": {
                    "transaction_id": dollars["transaction_id"],
                    "amount_cents": -4550,
                    "date": dollars["date"],
                },
            },
        ],
        "color": "#4a90d9",
    }


def test_a_refusal_keyed_kind_lands_on_type_in_the_engines_words(fake_client):
    refusal = _refusal("CONFLICT", 409, kind=("CASH_EXISTS", "You already hold a cash account."))
    values = {"type": "cash", "currencies": ["PEN"]}

    async def check(pilot, screen):
        assert refusal_block(screen) == f"Failed\n{format_error(refusal)}"
        assert "You already hold a cash account." in refusal_block(screen)
        assert screen._key == "type"
        assert screen._values == {"type": "cash", "currencies": ["PEN"]}

    _run(fake_client, _cash_screen(), values, error=refusal, check=check)


def test_a_cash_account_saved_says_account_created():
    assert _cash_screen()._saved_words() == "Account created."


def test_entering_cash_on_type_skips_the_read_only_name_and_the_summary_reads_it():
    screen = _cash_screen()
    shown: list = []

    async def scenario(pilot, app):
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.press("c", "a", "s", "h", "enter")
        await wait_for(pilot, lambda: screen._key == "currencies")  # `name` is skipped
        text = render_text(screen._summary_renderable(), width=100)
        shown.extend(" ".join(line.split()) for line in text.splitlines())

    run_app(scenario)
    assert shown[:2] == ["type cash", f"name {CASH_NAME} set by the engine"]


def _accounts_screen_new_form(monkeypatch, fetch_accounts, *, before_load=False):
    """The New form `n` hands over: asked once the list has loaded, or, with `before_load`,
    while the accounts read is still out."""
    release = threading.Event()

    def read(cfg, **kw):
        if before_load:
            release.wait(5)
        return fetch_accounts()

    monkeypatch.setattr("expense.reads.fetch_accounts", read)
    monkeypatch.setattr("expense.reads.fetch_bank_codes", lambda cfg, **kw: ["BCP"])
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    forms: list = []

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        if before_load:
            await pilot.pause()
            forms.append(screen.new_screen())
            release.set()
        else:
            await wait_for(pilot, lambda: app.screen.query(".error"))
            forms.append(screen.new_screen())

    run_app(scenario)
    return forms[0]


def test_cash_is_not_offered_while_the_list_is_still_loading(monkeypatch):
    form = _accounts_screen_new_form(monkeypatch, lambda: whole([]), before_load=True)
    assert [v for v, _ in form._field("type").choices] == ["bank", "person"]


def test_cash_is_not_offered_after_the_list_failed_to_load(monkeypatch):
    def refused():
        raise EngineError("UNAUTHORIZED", "Invalid or revoked token.", None, 401, {})

    form = _accounts_screen_new_form(monkeypatch, refused)
    assert [v for v, _ in form._field("type").choices] == ["bank", "person"]
