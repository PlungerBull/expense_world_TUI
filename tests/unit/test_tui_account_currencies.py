"""`c` on Manage ▸ Accounts adds a currency to the account under the cursor.

Pane 6 A of docs/mockups/expense-world-currencies-accounts-picks.html: `c Currency`
opens the pick `Add a currency`, the account on one line, the supported currencies
it does not hold in `SUPPORTED_CURRENCIES` order and `[enter] add    [esc] cancel`.
`⏎` sends one `POST /accounts/{id}/currencies` naming the picked currency, with no
question, and the list reads again with the cursor on the same account
(contract: POST /v1/accounts/{account_id}/currencies). A refusal, the currency
already held or the account archived, reads in the engine's words alone
(contract: POST /v1/accounts/{account_id}/currencies, "Refusals"). The write goes
through the real HTTP client against a respx-mocked engine, so the idempotency key
and the error envelope are the client's own; the list's read is stubbed.
"""

import json

import httpx
import pytest
import respx

from expense.tui.screens.accounts import AccountsScreen, currencies_to_add
from expense.tui.screens.modals import ConfirmModal, PickModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_URL,
    account_with_currencies,
    error_response,
    held_currency,
    render_text,
    run_app,
    toasts_shown,
    wait_for,
    wait_for_list,
    whole,
)

SIZE = (120, 40)


def _rows() -> list[dict]:
    return [
        account_with_currencies(
            id="a-caja", name="Caja Chica", currencies=[held_currency("PEN", 35000)]
        ),
        account_with_currencies(
            id="a-visa",
            name="Visa Inventada",
            currencies=[held_currency("PEN", -234050), held_currency("USD", -18520)],
        ),
        account_with_currencies(
            id="a-dolares", name="Ahorro Dólares", currencies=[held_currency("USD", 1240)]
        ),
        account_with_currencies(
            id="a-ana", name="Ana Ejemplo", is_person=True, currencies=[held_currency("PEN")]
        ),
        account_with_currencies(
            id="a-viejo",
            name="Ahorro Viejo",
            is_archived=True,
            currencies=[held_currency("PEN")],
        ),
    ]


def _record_notes(monkeypatch, screen) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        screen, "notify", lambda message, title="", **kw: notes.append((title, str(message)))
    )
    return notes


async def _open(pilot, app, monkeypatch, cursor: str, *, record: bool = True):
    screen = AccountsScreen()
    notes = _record_notes(monkeypatch, screen) if record else []
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    listing = screen.query_one(CursorList)
    listing.set_cursor(listing.index_of(cursor))
    screen.refresh_bindings()
    await pilot.pause()
    return screen, notes


def _pick_text(app) -> list[str]:
    """The pick as drawn, each Static's words, top to bottom."""
    return [
        render_text(static.content, width=80).strip()
        for static in app.screen.query("#modal Static")
    ]


# ---- what `c` offers ----------------------------------------------------------


def test_the_currencies_to_add_are_the_supported_ones_not_held_in_order():
    rows = {r["id"]: r for r in _rows()}
    assert currencies_to_add(rows["a-caja"]) == ["USD"]
    assert currencies_to_add(rows["a-dolares"]) == ["PEN"]
    assert currencies_to_add(rows["a-visa"]) == []
    assert currencies_to_add(account_with_currencies(currencies=[])) == ["PEN", "USD"]


@pytest.mark.parametrize(
    ("row", "line", "choices"),
    [
        ("a-caja", "Caja Chica · bank · PEN 350.00", ["USD"]),
        ("a-dolares", "Ahorro Dólares · bank · USD 12.40", ["PEN"]),
        # a person holds currencies too
        ("a-ana", "Ana Ejemplo · person · PEN 0.00", ["USD"]),
    ],
)
def test_c_lists_the_currencies_the_account_does_not_hold(
    configured, monkeypatch, row, line, choices
):
    """Pane 6 A: the title, the account on one line, the choices, the hint; the
    footer says `esc Cancel`; nothing is sent until `⏎`."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        await _open(pilot, app, monkeypatch, row)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
        await pilot.pause()
        seen["text"] = _pick_text(app)
        seen["footer"] = [
            f"{a.binding.key} {a.binding.description}"
            for a in app.screen.active_bindings.values()
            if a.binding.show and a.enabled
        ]

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.post(url__startswith=ENGINE_URL).mock(httpx.Response(201, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    title, account, listed, hint = seen["text"]
    assert title == "Add a currency"
    assert account == line
    assert listed.split() == choices
    assert hint == "[enter] add    [esc] cancel"
    assert seen["footer"] == ["escape Cancel"]


def test_c_sits_after_e_in_the_footer(configured, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        screen, _ = await _open(pilot, app, monkeypatch, "a-caja")
        seen["footer"] = [
            f"{a.binding.key} {a.binding.description}"
            for a in screen.active_bindings.values()
            if a.binding.show and a.enabled
        ]

    run_app(scenario, size=SIZE)
    assert seen["footer"][-6:] == [
        "n New",
        "e Edit",
        "c Currency",
        "a Archive",
        "t Make person",
        "d Delete",
    ]


# ---- `⏎` adds it --------------------------------------------------------------


def test_enter_adds_the_picked_currency_and_the_list_reads_fresh(configured, monkeypatch):
    """One `POST` with the picked code and an idempotency key, no question; the
    note names the currency and the list reads again, the cursor on the same
    account, now holding USD."""
    rows = _rows()
    reads: list[int] = []

    def read(*_a, **_k):
        reads.append(1)
        return whole([dict(r) for r in rows])

    monkeypatch.setattr("expense.reads.fetch_accounts", read)

    def answer(_request):
        caja = next(r for r in rows if r["id"] == "a-caja")
        caja["currencies"] = [*caja["currencies"], held_currency("USD")]
        return httpx.Response(201, json=held_currency("USD"))

    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-caja")
        read_before = len(reads)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
        await pilot.press("enter")
        assert not isinstance(app.screen, ConfirmModal)
        await wait_for(pilot, lambda: ("", "Currency added: USD.") in notes)
        await wait_for(pilot, lambda: len(reads) > read_before)
        await wait_for_list(pilot, app)
        await pilot.pause()
        seen["key"] = screen.query_one(CursorList).cursor_key
        seen["held"] = [h["currency_code"] for h in screen.selected_record()["currencies"]]
        seen["screen"] = app.screen is screen

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-caja/currencies").mock(side_effect=answer)
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    request = sent.calls.last.request
    assert json.loads(request.content) == {"currency_code": "USD"}
    assert request.headers["X-Idempotency-Key"]
    assert seen == {"key": "a-caja", "held": ["PEN", "USD"], "screen": True}


def test_the_highlight_moves_and_enter_takes_the_highlighted_one(configured, monkeypatch):
    """An account holding none is offered both, PEN first; `↓` then `⏎` adds USD."""
    rows = [account_with_currencies(id="a-nada", name="Prueba", currencies=[])]
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(rows))

    async def scenario(pilot, app):
        await _open(pilot, app, monkeypatch, "a-nada")
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: not isinstance(app.screen, PickModal))
        await pilot.pause()

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-nada/currencies").mock(
            httpx.Response(201, json=held_currency("USD"))
        )
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    assert json.loads(sent.calls.last.request.content) == {"currency_code": "USD"}


def test_esc_leaves_the_list_as_it_was_and_sends_nothing(configured, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-caja")
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        seen["notes"] = list(notes)
        seen["key"] = screen.query_one(CursorList).cursor_key

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.post(url__startswith=ENGINE_URL).mock(httpx.Response(201, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    assert seen == {"notes": [], "key": "a-caja"}


# ---- an account holding every currency ------------------------------------------


def test_c_on_an_account_holding_every_currency_says_so_and_writes_nothing(configured, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-visa")
        await pilot.press("c")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        seen["notes"] = list(notes)
        seen["screen"] = app.screen is screen

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.post(url__startswith=ENGINE_URL).mock(httpx.Response(201, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    assert seen == {"notes": [("", "Visa Inventada already holds every currency.")], "screen": True}


def test_the_note_shows_a_bracketed_name_whole(configured, monkeypatch):
    """The account's name is the owner's words: a toast reads it as text."""
    rows = [
        account_with_currencies(
            id="a-x",
            name="Visa [vieja]",
            currencies=[held_currency("PEN"), held_currency("USD")],
        )
    ]
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(rows))

    async def scenario(pilot, app):
        await _open(pilot, app, monkeypatch, "a-x", record=False)
        await pilot.press("c")
        await wait_for(
            pilot,
            lambda: any(
                "Visa [vieja] already holds every currency." in shown for shown in toasts_shown(app)
            ),
        )

    run_app(scenario, size=SIZE, toasts=True)


def test_c_is_off_on_an_empty_list(configured, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([]))
    seen: dict = {}

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        seen["check"] = screen.check_action("add_currency", ())
        await pilot.press("c")
        await pilot.pause()
        seen["screen"] = app.screen is screen

    run_app(scenario, size=SIZE)
    assert seen == {"check": None, "screen": True}


# ---- refusals: the engine's words alone ------------------------------------------

_DUPLICATE = "account already holds currency USD."
_ARCHIVED = "account is archived."

REFUSALS = [
    # the account got the currency meanwhile
    (
        "a-caja",
        error_response(
            409,
            "CONFLICT",
            _DUPLICATE,
            {"currency_code": _DUPLICATE},
            {"currency_code": "DUPLICATE_CURRENCY"},
        ),
        f"CONFLICT — {_DUPLICATE}\n  currency_code: {_DUPLICATE}",
    ),
    # an archived account: offered, and the engine refuses it
    (
        "a-viejo",
        error_response(
            422,
            "VALIDATION_ERROR",
            _ARCHIVED,
            {"account_id": _ARCHIVED},
            {"account_id": "INVALID_REFERENCE"},
        ),
        f"VALIDATION_ERROR — {_ARCHIVED}\n  account_id: {_ARCHIVED}",
    ),
]


@pytest.mark.parametrize(("row", "refusal", "shown"), REFUSALS, ids=["duplicate", "archived"])
def test_a_refusal_shows_the_engine_words_and_the_list_stays(
    configured, monkeypatch, row, refusal, shown
):
    """The "Failed" note is the engine's words, with no line of the app's; the
    list is not read again and `c` works again."""
    rows = _rows()
    reads: list[int] = []

    def read(*_a, **_k):
        reads.append(1)
        return whole(list(rows))

    monkeypatch.setattr("expense.reads.fetch_accounts", read)
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, row)
        listing = screen.query_one(CursorList)
        read_before = len(reads)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
        await pilot.press("enter")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        seen["notes"] = list(notes)
        seen["same"] = screen.query_one(CursorList) is listing
        seen["reread"] = len(reads) - read_before
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/{row}/currencies").mock(refusal)
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    assert seen["notes"] == [("Failed", shown)]
    assert seen["same"]
    assert seen["reread"] == 0
