"""`c` on Manage ▸ Accounts adds a currency to the account under the cursor.

Pane 6 A of docs/mockups/expense-world-currencies-accounts-picks.html: `c Currency`
opens the pick `Add a currency · <account>`, the account on one line, the supported currencies
it does not hold in `SUPPORTED_CURRENCIES` order and `[enter] add    [esc] cancel`.
`⏎` sends one `POST /accounts/{id}/currencies` naming the picked currency, with no
question, and the list reads again with the cursor on the same account
(contract: POST /v1/accounts/{account_id}/currencies). A refusal, the currency
already held or the account archived, reads in the engine's words alone
(contract: POST /v1/accounts/{account_id}/currencies, "Refusals"). The write goes
through the real HTTP client against a respx-mocked engine, so the idempotency key
and the error envelope are the client's own; the list's read is stubbed.
"""

import asyncio
import json
import threading

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
    assert title == f"Add a currency · {line.split(' · ')[0]}"
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
    assert seen["footer"][-7:] == [
        "n New",
        "e Edit",
        "c Currency",
        "x Remove currency",
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
    assert seen["key"] == "a-caja"
    assert seen["held"] == ["PEN", "USD"]
    assert seen["screen"]


def test_a_second_c_while_the_add_is_in_flight_offers_nothing(configured, monkeypatch):
    """`⏎` sends and the engine has not answered: `c` opens no pick, so the same
    currency is not added twice; once the reload lands, `c` works again."""
    rows = _rows()
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole([dict(r) for r in rows])
    )
    release = threading.Event()
    seen: dict = {}

    def answer(_request):
        release.wait(timeout=10)
        caja = next(r for r in rows if r["id"] == "a-caja")
        caja["currencies"] = [*caja["currencies"], held_currency("USD")]
        return httpx.Response(201, json=held_currency("USD"))

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-caja")
        try:
            await pilot.press("c")
            await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
            await pilot.press("enter")
            await wait_for(pilot, lambda: screen._toggle_busy)
            await pilot.press("c")
            await pilot.pause()
            seen["blocked"] = app.screen is screen
        finally:
            release.set()
        await wait_for(pilot, lambda: ("", "Currency added: USD.") in notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)
        await wait_for_list(pilot, app)
        await pilot.press("c")
        await pilot.pause()
        seen["after"] = app.screen is screen
        seen["note"] = ("", "Caja Chica already holds every currency.") in notes

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-caja/currencies").mock(side_effect=answer)
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    assert (seen["blocked"], seen["after"], seen["note"]) == (True, True, True)


def test_a_reload_while_the_add_is_unanswered_keeps_the_guard(configured, monkeypatch):
    """`r` lands a reload (stale rows) while the POST waits; `c` still offers
    nothing, so the same currency is not sent twice."""
    rows = _rows()
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole([dict(r) for r in rows])
    )
    release = threading.Event()
    seen: dict = {}

    def answer(_request):
        release.wait(timeout=10)
        return httpx.Response(201, json=held_currency("USD"))

    async def scenario(pilot, app):
        screen, _ = await _open(pilot, app, monkeypatch, "a-caja")
        try:
            await pilot.press("c")
            await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
            await pilot.press("enter")
            await wait_for(pilot, lambda: screen._toggle_busy)
            await pilot.press("r")
            await wait_for_list(pilot, app)
            await pilot.pause()
            seen["busy"] = screen._toggle_busy
            await pilot.press("c")
            await pilot.pause()
            seen["blocked"] = app.screen is screen
        finally:
            release.set()
        await wait_for(pilot, lambda: not screen._toggle_busy)

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-caja/currencies").mock(side_effect=answer)
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    assert (seen["busy"], seen["blocked"]) == (True, True)


def test_a_refused_queued_delete_does_not_leave_the_guard_set(configured, monkeypatch):
    """`c` is held, `d` + `y` queues a DELETE behind it; the add lands, the DELETE
    is refused (a toast, no reload of its own): `c` works again afterwards."""
    rows = _rows()
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole([dict(r) for r in rows])
    )
    release = threading.Event()
    seen: dict = {}

    def answer(_request):
        release.wait(timeout=10)
        return httpx.Response(201, json=held_currency("USD"))

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-caja")
        try:
            await pilot.press("c")
            await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
            await pilot.press("enter")
            await wait_for(pilot, lambda: screen._toggle_busy)
            await pilot.press("d")
            await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
            await pilot.press("y")
            await wait_for(pilot, lambda: len(screen.writes_unanswered()) == 2)
        finally:
            release.set()
        await wait_for(pilot, lambda: any(t == "Failed" for t, _ in notes))
        await wait_for(pilot, lambda: not screen._toggle_busy)
        await wait_for_list(pilot, app)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
        seen["offered"] = True

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-caja/currencies").mock(side_effect=answer)
        engine.delete(f"{ENGINE_URL}/v1/accounts/a-caja").mock(
            return_value=error_response(409, "ACCOUNT_HAS_TRANSACTIONS")
        )
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    assert seen["offered"] is True


def test_a_queued_toggle_dropped_by_a_refusal_does_not_leave_the_guard_set(configured, monkeypatch):
    """`d` + `y` is in flight, `a` queues behind it and the DELETE is refused: the
    archive is never sent, and `a` works again."""
    rows = _rows()
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole([dict(r) for r in rows])
    )
    release = threading.Event()

    def refuse(_request):
        release.wait(timeout=10)
        return error_response(409, "ACCOUNT_HAS_TRANSACTIONS")

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-caja")
        try:
            await pilot.press("d")
            await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
            await pilot.press("y")
            await wait_for(pilot, lambda: screen.writes_unanswered())
            await pilot.press("a")
            await wait_for(pilot, lambda: screen._toggle_busy)
        finally:
            release.set()
        await wait_for(pilot, lambda: not screen._toggle_busy)

    with respx.mock(assert_all_called=False) as engine:
        engine.delete(f"{ENGINE_URL}/v1/accounts/a-caja").mock(side_effect=refuse)
        archive = engine.post(f"{ENGINE_URL}/v1/accounts/a-caja/archive").mock(
            return_value=httpx.Response(200, json={})
        )
        run_app(scenario, size=SIZE)
    assert archive.call_count == 0


async def _answered_add_with_its_reload_held(pilot, app, monkeypatch, rows, reads, gate):
    """`c` ⏎ on Caja Chica, the POST answered, the write's own reload still
    reading (its fetch held on `gate`)."""

    def fetch(*a, **k):
        reads["n"] += 1
        if reads["n"] == 2:
            gate.wait(timeout=10)
        return whole([dict(r) for r in rows])

    monkeypatch.setattr("expense.reads.fetch_accounts", fetch)
    screen, _ = await _open(pilot, app, monkeypatch, "a-caja")
    await pilot.press("c")
    await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
    await pilot.press("enter")
    await wait_for(pilot, lambda: reads["n"] == 2 and not screen.writes_unanswered())
    return screen


def test_a_stale_build_after_the_add_was_answered_keeps_the_guard(configured, monkeypatch):
    """A build from a read that began before the answer lands (stale rows, no
    USD) while the write's own reload is still reading: the guard stays, and
    `c` offers nothing."""
    rows = _rows()
    gate = threading.Event()
    seen: dict = {}

    async def scenario(pilot, app):
        try:
            screen = await _answered_add_with_its_reload_held(
                pilot, app, monkeypatch, rows, {"n": 0}, gate
            )
            await screen._show([dict(r) for r in rows], screen._guard_from - 1)
            seen["busy"] = screen._toggle_busy
            await pilot.press("c")
            await pilot.pause()
            seen["blocked"] = app.screen is screen
        finally:
            gate.set()
        await wait_for(pilot, lambda: not screen._toggle_busy)  # its own reload lifts it

    with respx.mock() as engine:
        engine.post(f"{ENGINE_URL}/v1/accounts/a-caja/currencies").mock(
            return_value=httpx.Response(201, json=held_currency("USD"))
        )
        run_app(scenario, size=SIZE)
    assert (seen["busy"], seen["blocked"]) == (True, True)


def test_a_stale_build_racing_a_fresh_one_does_not_read_its_stamp(configured, monkeypatch):
    """Two builds land together, the stale one first, the fresh one while it
    waits on the content swap: each build reads its own read's stamp, so the
    stale build leaves the guard set and only the fresh one lifts it."""
    rows = _rows()
    gate = threading.Event()
    after_build: list[tuple[bool, bool]] = []  # (the build was the fresh one, guard set)

    async def scenario(pilot, app):
        try:
            screen = await _answered_add_with_its_reload_held(
                pilot, app, monkeypatch, rows, {"n": 0}, gate
            )
            real_build = screen.build

            def build(items):
                out = real_build(items)
                after_build.append((len(items[0]["currencies"]) == 2, screen._toggle_busy))
                return out

            monkeypatch.setattr(screen, "build", build)
            stale = [dict(r) for r in rows]
            fresh = [dict(r) for r in rows]
            fresh[0]["currencies"] = [*fresh[0]["currencies"], held_currency("USD")]
            await asyncio.gather(
                screen._show(stale, screen._guard_from - 1),
                screen._show(fresh, screen._guard_from),
            )
        finally:
            gate.set()

    with respx.mock() as engine:
        engine.post(f"{ENGINE_URL}/v1/accounts/a-caja/currencies").mock(
            return_value=httpx.Response(201, json=held_currency("USD"))
        )
        run_app(scenario, size=SIZE)
    assert (False, True) in after_build  # the stale build left the guard set
    assert (True, False) in after_build  # the fresh build lifted it


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
    assert seen["notes"] == []
    assert seen["key"] == "a-caja"


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
    assert seen["notes"] == [("", "Visa Inventada already holds every currency.")]
    assert seen["screen"]


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
    assert seen["check"] is None
    assert seen["screen"]


# ---- refusals: the engine's words alone ------------------------------------------

# the contract's own words for each refusal
# (contract: POST /v1/accounts/{account_id}/currencies, "Refusals")
_DUPLICATE = "Must be a currency the account does not hold."
_ARCHIVED = "Must reference an active, non-archived account."

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
