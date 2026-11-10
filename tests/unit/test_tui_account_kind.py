"""`t` on Manage ▸ Accounts turns an account into a person and back.

`t Make person` on a bank account's row asks the person's name and sends
`POST /accounts/{id}/make-person`, `t Make bank` on a person's asks the bank and sends
`POST /accounts/{id}/make-account` (contract: POST /v1/accounts/{account_id}/make-person)
(contract: POST /v1/accounts/{account_id}/make-account). The question's own tests are in
`test_tui_account_question.py`. The write goes through the
real HTTP client against a respx-mocked engine, so the idempotency key and the error
envelope are the client's own; the list's read is stubbed and plays the engine's
order: every real account first, then every person, a turned account at the end of
its new group.
"""

import json
import threading

import httpx
import pytest
import respx

import expense.config as config_module
import expense.tui.screens.home as home
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.modals import QuestionModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_URL,
    account_with_currencies,
    error_response,
    held_currency,
    run_app,
    stub_home_month,
    wait_for,
    wait_for_list,
    whole,
)

SIZE = (120, 40)


def _rows() -> list[dict]:
    """Manage ▸ Accounts as the Accounts screen lists it, plus a second person."""

    def held(*codes: str, opening: str | None = None) -> list[dict]:
        return [held_currency(c, 125000, opening_balance_transaction_id=opening) for c in codes]

    return [
        account_with_currencies(id="a-sueldo", name="Sueldo Soles", currencies=held("PEN")),
        account_with_currencies(
            id="a-efectivo", name="Efectivo", currencies=held("PEN", opening="t-open")
        ),
        account_with_currencies(id="a-alejo", name="ALEJO", currencies=held("PEN", "USD")),
        account_with_currencies(
            id="a-eliana", name="Eliana", kind="person", currencies=held("PEN")
        ),
        account_with_currencies(id="a-juan", name="Juan", kind="person", currencies=held("PEN")),
        account_with_currencies(
            id="a-viejo", name="Ahorro viejo", is_archived=True, currencies=held("PEN")
        ),
    ]


def _engine_order(rows: list[dict]) -> None:
    """The engine's order: active real accounts, then people, then the archived;
    within a group, in the order they joined it."""
    rows.sort(key=lambda r: (r["is_archived"], r["kind"] == "person"))


def _stub_list(monkeypatch, rows: list[dict]) -> None:
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(list(rows)))


def _turns(rows: list[dict], ident: str, person: bool):
    """A respx side effect playing the engine's turn: the account changes kind
    and moves to the end of its new group; the answer is the account."""

    def answer(_request):
        row = next(r for r in rows if r["id"] == ident)
        rows.remove(row)
        row["kind"] = "person" if person else "bank"
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


def _cells(screen) -> list[str]:
    """The cursor row's cells as the list draws them, each as its words."""
    listing = screen.query_one(CursorList)
    return [str(cell) for cell in listing._rows[listing.cursor_index].cells]


async def _open(pilot, app, monkeypatch, cursor: str):
    """Open the list with the cursor on an account's row."""
    screen = AccountsScreen()
    notes = _record_notes(monkeypatch, screen)
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    listing = screen.query_one(CursorList)
    listing.set_cursor(listing.index_of(cursor))
    screen.refresh_bindings()
    await pilot.pause()
    return screen, notes


async def _answer(pilot, app, route: str) -> None:
    """Answer `t`'s question: a name for `make-person`, the one bank for `make-account`."""
    await wait_for(pilot, lambda: isinstance(app.screen, QuestionModal))
    if route == "make-person":
        app.screen.query_one("#line-name").value = "Mamá"
    await pilot.press("enter")


# ---- both directions ------------------------------------------

TURNS = [
    # cursor row, route, the row's kind after, the note, its index after, the label after;
    # a two-currency account is turned on its one row and the cursor stays on it
    ("a-alejo", "make-person", True, "Now a person.", 4, "t Make bank"),
    ("a-juan", "make-account", False, "Now a bank account.", 3, "t Make person"),
]


@pytest.mark.parametrize(("row", "route", "person", "note", "index", "label"), TURNS)
def test_t_asks_then_turns_the_account_and_the_cursor_follows_it(
    configured, monkeypatch, row, route, person, note, index, label
):
    """`t` asks, then sends the one route with the answer as its body and an idempotency
    key, and the reload keeps the cursor on the turned account in its new
    place, the note saying what it is now and the footer offering the way back."""
    ident = row
    rows = _rows()
    _stub_list(monkeypatch, rows)
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _open(pilot, app, monkeypatch, row)
        before = screen.query_one(CursorList).cursor_index
        seen["cells_before"] = _cells(screen)
        await pilot.press("t")
        await _answer(pilot, app, route)
        await wait_for(pilot, lambda: ("", note) in notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)  # the reload landed
        await pilot.pause()
        listing = screen.query_one(CursorList)
        seen.update(before=before, after=listing.cursor_index, key=listing.cursor_key)
        seen["footer"] = _footer(screen)
        seen["cells"] = _cells(screen)
        seen["kind"] = screen.selected_record()["kind"] == "person"

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/{ident}/{route}").mock(
            side_effect=_turns(rows, ident, person)
        )
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    request = sent.calls.last.request
    assert json.loads(request.content) == (
        {"name": "Mamá"} if route == "make-person" else {"bank_code": "BCP"}
    )
    assert request.headers["X-Idempotency-Key"]
    assert seen["key"] == row
    assert seen["after"] == index != seen["before"]
    assert seen["kind"] is person
    # the whole account turned on its one row: its Type changed, every currency
    # column (PEN, USD) holding the balance it held before
    assert seen["cells"][1] == ("person" if person else "bank") != seen["cells_before"][1]
    assert seen["cells"][4:6] == seen["cells_before"][4:6]
    assert seen["cells"][0] == seen["cells_before"][0]
    assert label in seen["footer"]


def test_the_label_follows_the_cursor_row_and_t_sits_before_d(configured, monkeypatch):
    """`t Make person` on a bank account, `t Make bank` on a person,
    between `a Archive` and `d Delete`, which stays last."""
    _stub_list(monkeypatch, _rows())
    footers: dict = {}

    async def scenario(pilot, app):
        screen, _ = await _open(pilot, app, monkeypatch, "a-alejo")
        footers["bank"] = _footer(screen)
        await pilot.press("down")  # → Eliana, a person
        await pilot.pause()
        footers["person"] = _footer(screen)
        await pilot.press("up")
        await pilot.pause()
        footers["back"] = _footer(screen)

    run_app(scenario, size=SIZE)
    tail = ["n New", "e Edit", "c Currency", "x Remove currency", "a Archive"]
    assert footers["bank"][-7:] == [*tail, "t Make person", "d Delete"]
    assert footers["person"][-7:] == [*tail, "t Make bank", "d Delete"]
    assert footers["back"] == footers["bank"]


# ---- an archived row --------------------------------------------------


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
    assert seen["footer"][-6:] == [
        "n New",
        "e Edit",
        "c Currency",
        "x Remove currency",
        "a Archive",
        "d Delete",
    ]
    assert not any(entry.startswith("t ") for entry in seen["footer"])
    assert seen["checks"] == [False, False]
    assert seen["notes"] == [] and seen["busy"] is False


def test_t_is_unavailable_on_an_empty_list(configured, monkeypatch):
    """As `a` is: out of the footer, nothing to act on."""
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
    assert seen["checks"] == [False, False, False]
    assert seen["screen"]


# ---- one at a time ----------------------------------------------------------


def test_a_second_enter_while_one_is_in_flight_does_nothing(configured, monkeypatch):
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
            await _answer(pilot, app, "make-person")
            await wait_for(pilot, asked.is_set)  # the write is in flight
            await pilot.press("enter")
            await pilot.pause()
        finally:
            release.set()
        await wait_for(pilot, lambda: ("", "Now a person.") in notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)
        assert app.screen is screen  # the question closed with the write

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-alejo/make-person").mock(side_effect=held)
        other = engine.post(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    assert not other.called


# ---- the engine's refusals --------------------------------------------------

_ARCHIVED_WORDS = "The account is archived. Unarchive it first."
_STATEMENT_WORDS = (
    "The account has a reconciliation, which a person account cannot have. "
    "Delete its reconciliations first."
)
_STATEMENT_FIELD = "Must be an account without reconciliations: a person cannot have one."


# ---- refused until its statements go ------


def test_an_account_with_a_statement_stays_bank_until_they_are_deleted(configured, monkeypatch):
    """`t Make person` on a bank account with a statement, draft or completed, is refused
    with the engine's words alone (a refusal on `account_id` closes the question), the list
    is not read again, and the account stays a bank account where it was (contract: POST
    /v1/accounts/{account_id}/make-person, "Refusals"). Once its statements are deleted the
    engine no longer refuses, and `t` makes it a person."""
    rows = _rows()
    _stub_list(monkeypatch, rows)
    turn = _turns(rows, "a-alejo", True)
    answers = iter(
        [
            lambda _request: error_response(
                409,
                "CONFLICT",
                _STATEMENT_WORDS,
                {"account_id": _STATEMENT_FIELD},
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
        await _answer(pilot, app, "make-person")
        await wait_for(pilot, lambda: notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)
        await pilot.pause()
        listing = screen.query_one(CursorList)
        seen["same"] = before == (listing, listing.cursor_index, screen._by_id)
        seen["refused"] = list(notes)
        seen["kind"] = screen.selected_record()["kind"] == "person"
        seen["footer"] = _footer(screen)
        await pilot.press("t")  # its statements are deleted meanwhile
        await _answer(pilot, app, "make-person")
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
        ("Failed", f"CONFLICT — {_STATEMENT_WORDS}\n  account_id: {_STATEMENT_FIELD}")
    ]
    assert seen["same"]
    assert seen["kind"] is False
    assert "t Make person" in seen["footer"]
    assert sent.call_count == 2
    assert seen["after"]["id"] == "a-alejo" and seen["after"]["kind"] == "person"
    assert "t Make bank" in seen["after_footer"]


# ---- Home shows it in its new group --------------------------------------


def _dashboard(rows: list[dict]) -> dict:
    """`/dashboard` as the engine gives it: real accounts and people apart."""

    def entry(r: dict) -> dict:
        held = [
            {k: c[k] for k in ("currency_code", "current_balance_cents")} for c in r["currencies"]
        ]
        return {"id": r["id"], "name": r["name"], "kind": r["kind"], "currencies": held}

    live = [r for r in rows if not r["is_archived"]]
    return {
        "month": {"year": 2026, "month": 10},
        "accounts": [entry(r) for r in live if r["kind"] != "person"],
        "people": [entry(r) for r in live if r["kind"] == "person"],
        "categories": [],
        "totals": {"net_home_cents": 0, "unconverted_count": 0},
    }


def _groups(data: dict) -> tuple[list[str], list[str]]:
    """The names Home draws under ACCOUNTS and under PEOPLE."""
    rows = [r for r in home.home_rows(data) if r is not None]
    lefts = [r.left.strip() for r in rows]
    heads = [r.left.strip() if r.id and r.id.count(":") == 1 else "" for r in rows]
    banks = heads[lefts.index("ACCOUNTS") + 1 : lefts.index("PEOPLE")]
    people = heads[lefts.index("PEOPLE") + 1 : lefts.index("LEDGER")]
    return [n for n in banks if n], [n for n in people if n]


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
        await _answer(pilot, app, route)
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


@pytest.mark.parametrize(("ident", "route"), [("a-alejo", "archive"), ("a-viejo", "unarchive")])
def test_a_concurrent_change_refusal_says_to_press_r(configured, monkeypatch, ident, route):
    """`a` (archive and unarchive) refused with `CONCURRENT_CHANGE` reads in the engine's
    words and the list's `press r, then try again`."""
    rows = _rows()
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(list(rows)))
    seen: dict = {}

    async def scenario(pilot, app):
        _screen, notes = await _open(pilot, app, monkeypatch, ident)
        await pilot.press("a")
        await wait_for(pilot, lambda: notes)
        seen["notes"] = list(notes)

    fields = {"account_id": "stand-in field words"}
    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/{ident}/{route}").mock(
            error_response(
                409,
                "CONFLICT",
                "Changed by another request.",
                fields,
                {"account_id": "CONCURRENT_CHANGE"},
            )
        )
        run_app(scenario, size=SIZE)
    assert seen["notes"] == [
        (
            "Failed",
            "CONFLICT — Changed by another request.\n  account_id: stand-in field words\n\n"
            "It changed at the same moment: press r, then try again.",
        )
    ]
    assert sent.call_count == 1


def test_kind_alone_tells_a_person_from_a_bank_or_cash_account():
    """A `kind: "person"` account is a person; `bank` and `cash` are accounts, in the
    readers that split people out; the line and the row name a cash account `cash`."""
    from expense import reads
    from expense.tui.screens.accounts import account_line, account_rows

    person = account_with_currencies(id="p", name="Ana", kind="person")
    bank = account_with_currencies(id="b", name="BCP", kind="bank")
    cash = account_with_currencies(id="c", name="Efectivo", kind="cash")
    assert " · person · " in account_line(person)
    assert " · bank · " in account_line(bank) and " · cash · " in account_line(cash)
    kinds = [cells[1] for _, cells, *_ in account_rows([person, bank, cash], ["PEN"])]
    assert kinds == ["person", "bank", "cash"]
    names = [n for _, n, _ in reads.held_currencies([person, bank, cash], include_people=False)]
    assert names == ["BCP", "Efectivo"]
    assert len(reads.held_currencies([person, bank, cash])) == 3
