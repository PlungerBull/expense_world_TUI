"""`t` on Manage ▸ Accounts turns an account into a person and back.

Screens 1 A, 2 A, 3 and 5 B of docs/mockups/expense-world-account-to-person.html.
`t Make person` on a bank account's row sends `POST /accounts/{id}/make-person`,
`t Make bank` on a person's sends `POST /accounts/{id}/make-account`, each with no
body and no question (contract: POST /v1/accounts/{account_id}/make-person)
(contract: POST /v1/accounts/{account_id}/make-account). The write goes through the
real HTTP client against a respx-mocked engine, so the idempotency key and the error
envelope are the client's own; the list's read is stubbed and plays the engine's
order: every real account first, then every person, a turned account at the end of
its new group.
"""

import threading

import httpx
import pytest
import respx

import expense.config as config_module
import expense.tui.screens.home as home
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_URL,
    error_response,
    run_app,
    stub_home_month,
    wait_for,
    wait_for_list,
    whole,
)

SIZE = (120, 40)


def _account(ident: str, name: str, *, person: bool = False, archived: bool = False) -> dict:
    return {
        "id": ident,
        "name": name,
        "is_person": person,
        "is_archived": archived,
        "currency_code": "PEN",
        "color": None,
        "statement_code": None,
        "current_balance_cents": 125000,
        "opening_balance_transaction_id": None,
    }


def _rows() -> list[dict]:
    """Manage ▸ Accounts as screen 1 draws it, plus a second person; Sueldo
    Soles holds a statement code."""
    return [
        {**_account("a-sueldo", "Sueldo Soles"), "statement_code": "SJN"},
        {**_account("a-efectivo", "Efectivo"), "opening_balance_transaction_id": "t-open"},
        _account("a-alejo", "ALEJO PEN"),
        _account("a-alejo-usd", "ALEJO USD"),
        _account("a-eliana", "Eliana", person=True),
        _account("a-juan", "Juan", person=True),
        _account("a-viejo", "Ahorro viejo", archived=True),
    ]


def _engine_order(rows: list[dict]) -> None:
    """The engine's order: active real accounts, then people, then the archived;
    within a group, in the order they joined it."""
    rows.sort(key=lambda r: (r["is_archived"], r["is_person"]))


def _stub_list(monkeypatch, rows: list[dict]) -> None:
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(list(rows)))


def _turns(rows: list[dict], ident: str, person: bool):
    """A respx side effect playing the engine's turn: the account changes kind
    and moves to the end of its new group; the answer is the account."""

    def answer(_request):
        row = next(r for r in rows if r["id"] == ident)
        rows.remove(row)
        row["is_person"] = person
        rows.append(row)
        _engine_order(rows)
        return httpx.Response(200, json=row)

    return answer


def _record_notes(monkeypatch, screen) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        screen, "notify", lambda message, title="", **kw: notes.append((title, str(message)))
    )
    return notes


def _footer(screen) -> list[str]:
    """The footer's entries, in order, as `key Description`."""
    return [
        f"{a.binding.key} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


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


# ---- 1 A and 2 A · both directions ------------------------------------------

TURNS = [
    # cursor row, route, the row's kind after, the note, its index after, the label after
    ("a-alejo", "make-person", True, "Now a person.", 5, "t Make bank"),
    # an account with an opening balance turns too, keeping it
    # (contract: POST /v1/accounts/{account_id}/make-person)
    ("a-efectivo", "make-person", True, "Now a person.", 5, "t Make bank"),
    ("a-juan", "make-account", False, "Now a bank account.", 4, "t Make person"),
]


@pytest.mark.parametrize(("ident", "route", "person", "note", "index", "label"), TURNS)
def test_t_turns_the_account_at_once_and_the_cursor_follows_it(
    configured, monkeypatch, ident, route, person, note, index, label
):
    """`t` sends the one route with no body and an idempotency key, asks
    nothing, and the reload keeps the cursor on the turned account in its new
    place, the note saying what it is now and the footer offering the way back,
    its opening balance, if any, still on it."""
    rows = _rows()
    opening = next(r for r in rows if r["id"] == ident)["opening_balance_transaction_id"]
    _stub_list(monkeypatch, rows)
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, ident)
        before = screen.query_one(CursorList).cursor_index
        await pilot.press("t")
        assert not isinstance(app.screen, ConfirmModal)
        await wait_for(pilot, lambda: ("", note) in notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)  # the reload landed
        await pilot.pause()
        listing = screen.query_one(CursorList)
        seen.update(before=before, after=listing.cursor_index, key=listing.cursor_key)
        seen["footer"] = _footer(screen)
        seen["kind"] = screen.selected_record()["is_person"]
        seen["opening"] = screen.selected_record()["opening_balance_transaction_id"]

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/{ident}/{route}").mock(
            side_effect=_turns(rows, ident, person)
        )
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    request = sent.calls.last.request
    assert request.content == b""
    assert request.headers["X-Idempotency-Key"]
    assert seen["key"] == ident
    assert seen["after"] == index != seen["before"]
    assert seen["kind"] is person
    assert seen["opening"] == opening
    assert label in seen["footer"]


def test_the_label_follows_the_cursor_row_and_t_sits_before_d(configured, monkeypatch):
    """Screen 1 A: `t Make person` on a bank account, `t Make bank` on a person,
    between `a Archive` and `d Delete`, which stays last."""
    _stub_list(monkeypatch, _rows())
    footers: dict = {}

    async def scenario(pilot, app):
        screen, _ = await _open(pilot, app, monkeypatch, "a-alejo-usd")
        footers["bank"] = _footer(screen)
        await pilot.press("down")  # → Eliana, a person
        await pilot.pause()
        footers["person"] = _footer(screen)
        await pilot.press("up")
        await pilot.pause()
        footers["back"] = _footer(screen)

    run_app(scenario, size=SIZE)
    tail = ["n New", "e Edit", "a Archive"]
    assert footers["bank"][-5:] == [*tail, "t Make person", "d Delete"]
    assert footers["person"][-5:] == [*tail, "t Make bank", "d Delete"]
    assert footers["back"] == footers["bank"]


# ---- 5 B · an archived row --------------------------------------------------


def test_t_leaves_the_footer_on_an_archived_row_and_sends_nothing(configured, monkeypatch):
    _stub_list(monkeypatch, _rows())
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-viejo")
        seen["footer"] = _footer(screen)
        seen["checks"] = [screen.check_action(a, ()) for a in ("make_person", "make_bank")]
        await pilot.press("t")
        await pilot.pause()
        screen.action_make_person()  # not even called directly
        screen.action_make_bank()
        await pilot.pause()
        seen["notes"] = list(notes)
        seen["busy"] = screen._toggle_busy

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.post(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    assert seen["footer"][-4:] == ["n New", "e Edit", "a Archive", "d Delete"]
    assert not any(entry.startswith("t ") for entry in seen["footer"])
    assert seen["checks"] == [False, False]
    assert seen["notes"] == [] and seen["busy"] is False


def test_t_is_unavailable_on_an_empty_list(configured, monkeypatch):
    """As `a` is: shown, but nothing to act on."""
    _stub_list(monkeypatch, [])
    seen: dict = {}

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        seen["checks"] = [
            screen.check_action(a, ()) for a in ("archive", "make_person", "make_bank")
        ]
        await pilot.press("t")
        await pilot.pause()
        seen["screen"] = app.screen is screen

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.post(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    assert seen["checks"] == [None, None, None]
    assert seen["screen"]


# ---- one at a time ----------------------------------------------------------


def test_a_second_t_while_one_is_in_flight_does_nothing(configured, monkeypatch):
    rows = _rows()
    _stub_list(monkeypatch, rows)
    asked, release = threading.Event(), threading.Event()
    turn = _turns(rows, "a-alejo", True)

    def held(request):
        asked.set()
        release.wait(timeout=5)
        return turn(request)

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-alejo")
        try:
            await pilot.press("t")
            await wait_for(pilot, asked.is_set)  # the write is in flight
            await pilot.press("t")
            await pilot.press("a")  # nor does an archive toggle
            await pilot.pause()
        finally:
            release.set()
        await wait_for(pilot, lambda: ("", "Now a person.") in notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-alejo/make-person").mock(side_effect=held)
        other = engine.post(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    assert not other.called


# ---- the engine's refusals --------------------------------------------------

_ARCHIVED_WORDS = "The account is archived. Unarchive it first."
_RECON_WORDS = (
    "The account has a reconciliation, which a person account cannot have. "
    "Delete its reconciliations first."
)
_RECON_FIELD = "Must be an account without reconciliations: a person cannot have one."
_RECON_LINE = (
    "On Reconciliations, press d on each of its reconciliations; a completed one needs u first."
)
_CODE_WORDS = (
    "The account has the statement code 'SJN', which a person account cannot carry. "
    "Clear the code first."
)
_CODE_FIELD = "Must be an account without a statement code: a person cannot carry one."

REFUSALS = [
    # cursor row, route, the engine's message, field words, reason, the whole note
    (
        "a-alejo",
        "make-person",
        _RECON_WORDS,
        _RECON_FIELD,
        "HAS_RECONCILIATION",
        f"CONFLICT — {_RECON_WORDS}\n  account_id: {_RECON_FIELD}\n\n{_RECON_LINE}",
    ),
    (
        "a-alejo",
        "make-person",
        "The account is already a person account.",
        "Must be a real account: this one is already a person.",
        "KIND_UNCHANGED",
        "CONFLICT — The account is already a person account.\n"
        "  account_id: Must be a real account: this one is already a person.",
    ),
    (
        "a-eliana",
        "make-account",
        "The account is already a real account.",
        "Must be a person account: this one is already a real account.",
        "KIND_UNCHANGED",
        "CONFLICT — The account is already a real account.\n"
        "  account_id: Must be a person account: this one is already a real account.",
    ),
    (
        "a-alejo",
        "make-person",
        _ARCHIVED_WORDS,
        _ARCHIVED_WORDS,
        "ACCOUNT_ARCHIVED",
        f"CONFLICT — {_ARCHIVED_WORDS}\n  account_id: {_ARCHIVED_WORDS}",
    ),
    (
        "a-sueldo",
        "make-person",
        _CODE_WORDS,
        _CODE_FIELD,
        "HAS_STATEMENT_CODE",
        f"CONFLICT — {_CODE_WORDS}\n  account_id: {_CODE_FIELD}",
    ),
]


@pytest.mark.parametrize(
    ("ident", "route", "message", "field", "reason", "shown"),
    REFUSALS,
    ids=[
        "reconciliation",
        "already-person",
        "already-bank",
        "archived",
        "statement-code",
    ],
)
def test_a_refusal_shows_the_engine_words_and_t_works_again(
    configured, monkeypatch, ident, route, message, field, reason, shown
):
    """The "Failed" note is the engine's words whole; only `HAS_RECONCILIATION`
    adds the app's line, chosen by the reason; the rest,
    `HAS_STATEMENT_CODE` among them, show the engine's words alone
    (contract: POST /v1/accounts/{account_id}/make-person, "Refusals"). Nothing
    changes: the account keeps its kind (`_by_id` holds `is_person`) and the list
    is not read again. Nothing
    but the turn is sent, and `t` sends again."""
    rows = _rows()
    reads: list[int] = []

    def read(*_a, **_k):
        reads.append(1)
        return whole(list(rows))

    monkeypatch.setattr("expense.reads.fetch_accounts", read)
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, ident)
        listing = screen.query_one(CursorList)
        before = (listing, listing.cursor_key, dict(screen._by_id))
        read_before = len(reads)
        await pilot.press("t")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        listing = screen.query_one(CursorList)
        seen["same"] = before == (listing, listing.cursor_key, screen._by_id)
        seen["reread"] = len(reads) - read_before
        seen["notes"] = list(notes)
        await pilot.press("t")
        await wait_for(pilot, lambda: len(notes) == 2)

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/{ident}/{route}").mock(
            error_response(409, "CONFLICT", message, {"account_id": field}, {"account_id": reason})
        )
        run_app(scenario, size=SIZE)
    assert seen["notes"] == [("Failed", shown)]
    assert seen["same"]
    assert seen["reread"] == 0
    assert sent.call_count == 2


# ---- person-reconciliations 1 A · refused until its reconciliations go ------


def test_an_account_with_a_reconciliation_stays_bank_until_they_are_deleted(
    configured, monkeypatch
):
    """Screen 1 A of expense-world-person-reconciliations.html: `t Make person`
    on a bank account with a reconciliation, draft or completed, is refused
    with the engine's words and the app's line on how, and the account stays a
    bank account where it was (contract: POST /v1/accounts/{account_id}/make-person,
    "Refusals"). Once its reconciliations are deleted the engine no longer
    refuses, and `t` makes it a person."""
    rows = _rows()
    _stub_list(monkeypatch, rows)
    turn = _turns(rows, "a-alejo", True)
    answers = iter(
        [
            lambda _request: error_response(
                409,
                "CONFLICT",
                _RECON_WORDS,
                {"account_id": _RECON_FIELD},
                {"account_id": "HAS_RECONCILIATION"},
            ),
            turn,
        ]
    )
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, "a-alejo")
        listing = screen.query_one(CursorList)
        before = (listing, listing.cursor_index, dict(screen._by_id))
        await pilot.press("t")
        await wait_for(pilot, lambda: notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)
        await pilot.pause()
        listing = screen.query_one(CursorList)
        seen["same"] = before == (listing, listing.cursor_index, screen._by_id)
        seen["refused"] = list(notes)
        seen["kind"] = screen.selected_record()["is_person"]
        seen["footer"] = _footer(screen)
        await pilot.press("t")  # its reconciliations are deleted meanwhile
        await wait_for(pilot, lambda: ("", "Now a person.") in notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)
        await pilot.pause()
        seen["after"] = screen.selected_record()
        seen["after_footer"] = _footer(screen)

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-alejo/make-person").mock(
            side_effect=lambda request: next(answers)(request)
        )
        run_app(scenario, size=SIZE)
    assert seen["refused"] == [
        ("Failed", f"CONFLICT — {_RECON_WORDS}\n  account_id: {_RECON_FIELD}\n\n{_RECON_LINE}")
    ]
    assert seen["same"]
    assert seen["kind"] is False
    assert "t Make person" in seen["footer"]
    assert sent.call_count == 2
    assert seen["after"]["id"] == "a-alejo" and seen["after"]["is_person"] is True
    assert "t Make bank" in seen["after_footer"]


# ---- 3 · Home shows it in its new group --------------------------------------


def _dashboard(rows: list[dict]) -> dict:
    """`/dashboard` as the engine gives it: real accounts and people apart."""

    def entry(r: dict) -> dict:
        keys = ("id", "name", "currency_code", "current_balance_cents")
        return {k: r[k] for k in keys}

    live = [r for r in rows if not r["is_archived"]]
    return {
        "month": {"year": 2026, "month": 10},
        "bank_accounts": [entry(r) for r in live if not r["is_person"]],
        "people": [entry(r) for r in live if r["is_person"]],
        "categories": [],
        "totals": {"net_home_cents": 0, "unconverted_count": 0},
    }


def _groups(data: dict) -> tuple[list[str], list[str]]:
    """The names Home draws under BANK ACCOUNTS and under PEOPLE."""
    lefts = [r.left.strip() for r in home.home_rows(data) if r is not None]
    banks = lefts[lefts.index("BANK ACCOUNTS") + 1 : lefts.index("PEOPLE")]
    people = lefts[lefts.index("PEOPLE") + 1 : lefts.index("LEDGER")]
    return banks, people


@pytest.mark.parametrize(
    ("ident", "route", "person"),
    [("a-alejo", "make-person", True), ("a-juan", "make-account", False)],
)
def test_home_shows_the_turned_account_in_its_new_group(
    configured, monkeypatch, ident, route, person
):
    """Back on Home after `t`, the account stands under its new group, read
    from `/dashboard` again on Home's resume."""
    rows = _rows()
    _stub_list(monkeypatch, rows)
    saved_config = config_module.ensure_loaded
    stub_home_month(monkeypatch)
    # Home's reads are stubbed; the write goes to the mocked engine with the saved config.
    monkeypatch.setattr("expense.config.ensure_loaded", saved_config)
    monkeypatch.setattr("expense.reads.fetch_dashboard", lambda *a, **k: _dashboard(rows))
    name = next(r["name"] for r in rows if r["id"] == ident)
    seen: dict = {}

    async def scenario(pilot, app):
        homes = app.screen
        assert isinstance(homes, HomeScreen)
        await wait_for(pilot, lambda: homes._data is not None)
        seen["before"] = _groups(homes._data)
        screen, notes = await _open(pilot, app, monkeypatch, ident)
        await pilot.press("t")
        await wait_for(pilot, lambda: not screen._toggle_busy and notes)
        homes._data = None
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is homes and homes._data is not None)
        seen["after"] = _groups(homes._data)

    with respx.mock() as engine:
        engine.post(f"{ENGINE_URL}/v1/accounts/{ident}/{route}").mock(
            side_effect=_turns(rows, ident, person)
        )
        run_app(scenario, size=SIZE)
    (banks_before, people_before), (banks_after, people_after) = seen["before"], seen["after"]
    assert (name in banks_before, name in people_before) == (person is True, person is False)
    assert (name in banks_after, name in people_after) == (person is False, person is True)
