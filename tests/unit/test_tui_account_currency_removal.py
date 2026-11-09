"""`x` on Manage ▸ Accounts removes a currency from the account under the cursor.

`x Remove currency` opens the pick `Remove a currency · <account>`, the account on one line, the
currencies it holds and `[enter] pick    [esc] cancel`. `⏎` asks
`Remove USD from Visa Inventada?` and only `y` sends one
`DELETE /accounts/{id}/currencies/{code}`; the list then reads again with the
cursor on the same account. `LAST_CURRENCY`, `HAS_TRANSACTIONS` and `IN_LIVE_STATEMENT` (both on
`currency_code`, so without the account delete's archive line) and
`ACCOUNT_ARCHIVED` read in the engine's words alone, nothing written
(contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals").
The write goes through the real HTTP client against a respx-mocked engine, so the
idempotency key and the error envelope are the client's own; the list's read is
stubbed.
"""

import threading

import httpx
import pytest
import respx

from expense.tui.screens.accounts import (
    AccountsScreen,
    currencies_held,
    removal_question,
)
from expense.tui.screens.modals import ConfirmModal, PickModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_URL,
    account_with_currencies,
    error_response,
    held_currency,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

SIZE = (120, 40)


def _rows() -> list[dict]:
    return [
        account_with_currencies(
            id="a-visa",
            name="Visa Inventada",
            currencies=[held_currency("PEN", -234050), held_currency("USD", -18520)],
        ),
        account_with_currencies(
            id="a-prueba", name="Cuenta Prueba", currencies=[held_currency("PEN")]
        ),
        account_with_currencies(
            id="a-ana",
            name="Ana Ejemplo",
            kind="person",
            currencies=[held_currency("PEN", -15000), held_currency("USD", 4000)],
        ),
        account_with_currencies(
            id="a-viejo",
            name="Ahorro Viejo",
            is_archived=True,
            currencies=[held_currency("PEN"), held_currency("USD", 1240)],
        ),
    ]


def _record_notes(monkeypatch, screen) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        screen, "notify", lambda message, title="", **kw: notes.append((title, str(message)))
    )
    return notes


async def _open(pilot, app, monkeypatch, cursor: str):
    screen = AccountsScreen()
    notes = _record_notes(monkeypatch, screen)
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    listing = screen.query_one(CursorList)
    listing.set_cursor(listing.index_of(cursor))
    screen.refresh_bindings()
    await pilot.pause()
    return screen, notes


def _modal_text(app) -> list[str]:
    """The modal as drawn, each Static's words, top to bottom."""
    return [
        render_text(static.content, width=80).strip()
        for static in app.screen.query("#modal Static")
    ]


def _footer(screen) -> list[str]:
    return [
        f"{a.binding.key} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


async def _ask(pilot, app, *moves: str) -> None:
    """`x`, the highlight moved, `⏎`: the question is up."""
    await pilot.press("x")
    await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
    await pilot.press(*moves, "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
    await pilot.pause()


# ---- what `x` offers ------------------------------------------------------------


def test_the_currencies_held_are_the_account_s_in_the_engine_order():
    rows = {r["id"]: r for r in _rows()}
    assert currencies_held(rows["a-visa"]) == ["PEN", "USD"]
    assert currencies_held(rows["a-prueba"]) == ["PEN"]


@pytest.mark.parametrize(
    ("row", "title", "line", "choices"),
    [
        (
            "a-visa",
            "Remove a currency · Visa Inventada",
            "Visa Inventada · bank · PEN -2,340.50 · USD -185.20",
            ["PEN", "USD"],
        ),
        (
            "a-prueba",
            "Remove a currency · Cuenta Prueba",
            "Cuenta Prueba · bank · PEN 0.00",
            ["PEN"],
        ),
        # a person holds currencies too
        (
            "a-ana",
            "Remove a currency · Ana Ejemplo",
            "Ana Ejemplo · person · PEN -150.00 · USD 40.00",
            ["PEN", "USD"],
        ),
    ],
)
def test_x_lists_the_currencies_the_account_holds(
    configured, monkeypatch, row, title, line, choices
):
    """The title naming the account, the account on one line, its
    currencies, the hint; the footer says `esc Cancel`; nothing is sent."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        await _open(pilot, app, monkeypatch, row)
        await pilot.press("x")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
        await pilot.pause()
        seen["text"] = _modal_text(app)
        seen["footer"] = _footer(app.screen)

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.delete(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    shown_title, account, listed, hint = seen["text"]
    assert (shown_title, account, hint) == (title, line, "[enter] pick    [esc] cancel")
    assert listed.split() == choices
    assert seen["footer"] == ["escape Cancel"]


def test_x_sits_after_c_in_the_footer(configured, monkeypatch):
    """`c Currency  x Remove currency` before `a Archive`."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        screen, _ = await _open(pilot, app, monkeypatch, "a-visa")
        seen["footer"] = _footer(screen)

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


def test_x_is_off_on_an_empty_list(configured, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([]))
    seen: dict = {}

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        seen["check"] = screen.check_action("remove_currency", ())
        await pilot.press("x")
        await pilot.pause()
        seen["screen"] = app.screen is screen

    run_app(scenario, size=SIZE)
    assert seen["check"] is False
    assert seen["screen"]


# ---- the question ------------------------------------------------------------------


def test_the_question_names_the_account_and_the_currency():
    """The question, and its body for an account's only currency."""
    rows = {r["id"]: r for r in _rows()}
    assert removal_question(rows["a-visa"], "USD") == (
        "Remove USD from Visa Inventada?",
        "Visa Inventada · bank · USD -185.20\nVisa Inventada keeps PEN.",
    )
    assert removal_question(rows["a-prueba"], "PEN") == (
        "Remove PEN from Cuenta Prueba?",
        "Cuenta Prueba · bank · PEN 0.00\nIt is the account's only currency.",
    )


def test_enter_on_the_pick_asks_first_as_drawn(configured, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        await _open(pilot, app, monkeypatch, "a-visa")
        await _ask(pilot, app, "down")
        seen["text"] = _modal_text(app)

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.delete(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    assert seen["text"] == [
        "Remove USD from Visa Inventada?",
        "Visa Inventada · bank · USD -185.20\nVisa Inventada keeps PEN.",
        "[y] confirm    [enter / n / esc] cancel",
    ]


def test_esc_on_the_pick_sends_nothing(configured, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-visa")
        await pilot.press("x")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        seen["notes"] = list(notes)
        seen["key"] = screen.query_one(CursorList).cursor_key

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.delete(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    assert seen["notes"] == []
    assert seen["key"] == "a-visa"


@pytest.mark.parametrize("answer", ["n", "escape", "enter", "q"])
def test_only_y_removes_any_other_answer_sends_nothing(configured, monkeypatch, answer):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-visa")
        await _ask(pilot, app, "down")
        await pilot.press(answer)
        await pilot.pause()
        await pilot.pause()
        seen["notes"] = list(notes)

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.delete(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    assert seen["notes"] == []


# ---- `y` removes it --------------------------------------------------------------


def test_y_removes_the_currency_and_the_list_reads_fresh(configured, monkeypatch):
    """One `DELETE` with an idempotency key and no body; the note names the
    currency and the list reads again, the cursor on the same account, which now
    holds PEN alone."""
    rows = _rows()
    reads: list[int] = []

    def read(*_a, **_k):
        reads.append(1)
        return whole([dict(r) for r in rows])

    monkeypatch.setattr("expense.reads.fetch_accounts", read)

    def answer(_request):
        visa = next(r for r in rows if r["id"] == "a-visa")
        visa["currencies"] = [h for h in visa["currencies"] if h["currency_code"] != "USD"]
        return httpx.Response(200, json=visa)

    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-visa")
        read_before = len(reads)
        await _ask(pilot, app, "down")
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", "Currency removed: USD.") in notes)
        await wait_for(pilot, lambda: len(reads) > read_before)
        await wait_for_list(pilot, app)
        await pilot.pause()
        seen["key"] = screen.query_one(CursorList).cursor_key
        seen["held"] = currencies_held(screen.selected_record())
        seen["screen"] = app.screen is screen

    with respx.mock() as engine:
        sent = engine.delete(f"{ENGINE_URL}/v1/accounts/a-visa/currencies/USD").mock(
            side_effect=answer
        )
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    request = sent.calls.last.request
    assert request.content == b""
    assert request.headers["X-Idempotency-Key"]
    assert seen["key"] == "a-visa"
    assert seen["held"] == ["PEN"]
    assert seen["screen"]


def test_a_second_x_or_c_while_the_write_is_in_flight_does_nothing(configured, monkeypatch):
    """One currency write at a time, sharing `a` and `t`'s guard: until the
    reload lands, `x` and `c` open nothing."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        screen, _ = await _open(pilot, app, monkeypatch, "a-prueba")
        screen._toggle_busy = True  # a write in flight
        await pilot.press("x")
        await pilot.pause()
        seen["x"] = app.screen is screen
        await pilot.press("c")
        await pilot.pause()
        seen["c"] = app.screen is screen

    run_app(scenario, size=SIZE)
    assert seen == {"x": True, "c": True}


def test_the_guard_holds_until_the_engine_answers(configured, monkeypatch):
    """`y` sends; while the engine has not answered, `x` opens nothing; once the
    reload lands, `x` works again."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    release = threading.Event()
    seen: dict = {}

    def answer(_request):
        release.wait(timeout=10)
        return httpx.Response(200, json={})

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-visa")
        await _ask(pilot, app, "down")
        await pilot.press("y")
        await wait_for(pilot, lambda: screen._toggle_busy)
        await pilot.press("x")
        await pilot.pause()
        seen["blocked"] = app.screen is screen
        release.set()
        await wait_for(pilot, lambda: ("", "Currency removed: USD.") in notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)
        await wait_for_list(pilot, app)
        await pilot.press("x")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))

    with respx.mock() as engine:
        sent = engine.delete(f"{ENGINE_URL}/v1/accounts/a-visa/currencies/USD").mock(
            side_effect=answer
        )
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    assert seen["blocked"]


# ---- refusals: the engine's words alone ------------------------------------------

# the contract's own words for each refusal
# (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals")
_LAST = "Must not be the account's last currency: delete the account instead."
_HELD = "Must not be used by any active transaction in USD."
_LIVE = (
    "Must be a currency no live statement holds in PEN, draft or completed: "
    "delete the statement first."
)
_ARCHIVED = "The account is archived. Unarchive it first."

REFUSALS = [
    (
        "a-prueba",
        "PEN",
        (),
        error_response(
            409,
            "CONFLICT",
            _LAST,
            {"currency_code": _LAST},
            {"currency_code": "LAST_CURRENCY"},
        ),
        f"CONFLICT — {_LAST}\n  currency_code: {_LAST}",
    ),
    # keyed on the currency, so the account delete's archive line never meets it
    (
        "a-visa",
        "USD",
        ("down",),
        error_response(
            409,
            "CONFLICT",
            _HELD,
            {"currency_code": _HELD},
            {"currency_code": "HAS_TRANSACTIONS"},
        ),
        f"CONFLICT — {_HELD}\n  currency_code: {_HELD}",
    ),
    (
        "a-visa",
        "PEN",
        (),
        error_response(
            409,
            "CONFLICT",
            _LIVE,
            {"currency_code": _LIVE},
            {"currency_code": "IN_LIVE_STATEMENT"},
        ),
        f"CONFLICT — {_LIVE}\n  currency_code: {_LIVE}",
    ),
    # an archived account: offered, and the engine refuses it
    (
        "a-viejo",
        "USD",
        ("down",),
        error_response(
            409,
            "CONFLICT",
            _ARCHIVED,
            {"account_id": _ARCHIVED},
            {"account_id": "ACCOUNT_ARCHIVED"},
        ),
        f"CONFLICT — {_ARCHIVED}\n  account_id: {_ARCHIVED}",
    ),
    # the two path refusals come first, `404` with no `fields`
    # (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals")
    (
        "a-visa",
        "PEN",
        (),
        error_response(404, "NOT_FOUND", "account not found."),
        "NOT_FOUND — account not found.",
    ),
    (
        "a-visa",
        "PEN",
        (),
        error_response(404, "NOT_FOUND", "currency PEN not found."),
        "NOT_FOUND — currency PEN not found.",
    ),
]


@pytest.mark.parametrize(
    ("row", "code", "moves", "refusal", "shown"),
    REFUSALS,
    ids=[
        "last-currency",
        "has-transactions",
        "in-live-statement",
        "account-archived",
        "account-not-found",
        "currency-not-found",
    ],
)
def test_a_refusal_shows_the_engine_words_alone_and_the_list_stays(
    configured, monkeypatch, row, code, moves, refusal, shown
):
    """The "Failed" note is the engine's words, with no line of the app's; the
    list is not read again, nothing else is sent, and `x` works again."""
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
        await _ask(pilot, app, *moves)
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        seen["notes"] = list(notes)
        seen["same"] = screen.query_one(CursorList) is listing
        seen["key"] = listing.cursor_key
        seen["reread"] = len(reads) - read_before
        await pilot.press("x")
        await wait_for(pilot, lambda: isinstance(app.screen, PickModal))

    with respx.mock() as engine:
        removal = engine.delete(f"{ENGINE_URL}/v1/accounts/{row}/currencies/{code}").mock(refusal)
        run_app(scenario, size=SIZE)
        written = len(engine.calls)
    assert removal.call_count == 1
    assert written == 1  # nothing else written
    assert seen["notes"] == [("Failed", shown)]
    assert seen["same"]
    assert seen["key"] == row
    assert seen["reread"] == 0


def test_the_account_delete_keeps_its_archive_line(configured, monkeypatch):
    """`d` on the account, refused with `HAS_TRANSACTIONS` on `account_id`,
    still says to archive it instead: only a currency's removal drops it."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(_rows()))
    seen: dict = {}

    async def scenario(pilot, app):
        _, notes = await _open(pilot, app, monkeypatch, "a-visa")
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        seen["notes"] = list(notes)

    with respx.mock() as engine:
        engine.delete(f"{ENGINE_URL}/v1/accounts/a-visa").mock(
            error_response(
                409,
                "CONFLICT",
                "Account has transactions.",
                {"account_id": "Account has transactions."},
                {"account_id": "HAS_TRANSACTIONS"},
            )
        )
        run_app(scenario, size=SIZE)
    assert seen["notes"] == [
        (
            "Failed",
            "CONFLICT — Account has transactions.\n  account_id: Account has transactions."
            "\n\nTo retire it instead, archive it: press a.",
        )
    ]
