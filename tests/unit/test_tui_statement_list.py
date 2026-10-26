"""The Reconciliations browse on an account with a statement code: one row per statement.

Pane 1 A of docs/mockups/expense-world-card-statement.html, and its task 6 question 3 B
for a code no other account holds. `⏎` on an account with a code reads
`GET /reconciliations?statement_of=<its id>`, the reconciliations of every account
holding the code, and nothing else about reconciliations; each row is an item and the
item its `twin_id` names in the same answer (contract: GET /v1/reconciliations). An
account with no code keeps today's read and list. On a card half's batch screen, `c`, `u`
and `d` each send one write, which the engine applies to both halves.

The engine is a `FakeClient` behind the reads module's own HTTP client, so the query
each read sends is the one `expense/reads.py` builds; it answers the way the contract
says the engine does: `statement_of` lists every account holding the named account's
code, an archived one included, in the engine's order, `account_id` one account alone.
"""

from typing import NamedTuple

import httpx
import pytest
import respx
from textual.widgets import Static

from expense.errors import EngineError, format_error
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.reconciliations import (
    ReconciliationDetailScreen,
    ReconciliationsScreen,
    order_cell,
    statement_rows,
)
from tests.unit.helpers import (
    ENGINE_URL,
    FakeClient,
    complete_answer,
    cursor_page,
    delete_answer,
    render_text,
    revert_answer,
    run_app,
    stub_home_month,
    wait_for,
    wait_for_list,
    whole,
)


def _account(
    aid: str,
    name: str,
    currency: str,
    code: str | None,
    balance: int,
    order: int,
    partner: str | None = None,
):
    """An account as `GET /accounts` reads it, every field it serves: `partner` is its
    `statement_partner_id`, the card's other account, null on any account that is not
    half of a live card (contract: "Bank Accounts", "Statement partner")."""
    return {
        "id": aid,
        "user_id": "u-1",
        "name": name,
        "currency_code": currency,
        "is_person": False,
        "color": None,
        "statement_code": code,
        "statement_partner_id": partner,
        "current_balance_cents": balance,
        "current_balance_home_cents": balance,
        "opening_balance_transaction_id": None,
        "is_archived": False,
        "sort_order": order,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "version": 1,
        "deleted_at": None,
    }


SIG_PEN = _account("acc-sig-pen", "Signature PEN", "PEN", "SIG", -51230, 1, "acc-sig-usd")
SIG_USD = _account("acc-sig-usd", "Signature USD", "USD", "SIG", -6140, 2, "acc-sig-pen")
AHORRO = _account("acc-ahorro", "Ahorro Soles", "PEN", "AHO", 648000, 3)
SUELDO = _account("acc-sueldo", "Sueldo Soles", "PEN", None, 1245000, 4)
DIGITAL = _account("acc-digital", "Cuenta Digital Dólares", "USD", None, 82015, 5)
ACCOUNTS = [SIG_PEN, SIG_USD, AHORRO, SUELDO, DIGITAL]


def _half(
    rid: str,
    account: dict,
    name: str,
    days: tuple[str, str],
    *,
    status: int,
    diff: int | None = 0,
    twin: str | None = None,
    unplaced: int | None = 0,
    shared: int | None = 0,
) -> dict:
    """A reconciliation as `GET /reconciliations` reads it, every field it serves."""
    return {
        "id": rid,
        "user_id": "u-1",
        "account_id": account["id"],
        "name": name,
        "date_start": days[0],
        "date_end": days[1],
        "status": status,
        "beginning_balance_cents": 0,
        "ending_balance_cents": None if diff is None else 0,
        "difference_cents": diff,
        "twin_id": twin,
        "unplaced_count": unplaced,
        "shared_place_count": shared,
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
        "version": 1,
        "deleted_at": None,
    }


JUL = ("2026-06-26", "2026-07-25")
AGO = ("2026-07-26", "2026-08-25")
SEP = ("2026-08-26", "2026-09-25")
OCT = ("2026-09-26", "2026-10-25")

#: The card's four months of pane 1 A, in the engine's order: `date_start` ascending,
#: then the accounts' order, oldest first (contract: "Reconciliations", "Ordering").
#: Julio has only a soles half; Agosto is completed; Septiembre's soles half is
#: completed and its dollar half a draft; Octubre is open, the dollar half off by -2.99.
#: Both halves read the same two counts (contract: "Reconciliations", "A statement's order").
CARD = [
    _half("jul-pen", SIG_PEN, "Julio 2026", JUL, status=2),
    _half("ago-pen", SIG_PEN, "Agosto 2026", AGO, status=2, twin="ago-usd"),
    _half("ago-usd", SIG_USD, "Agosto 2026", AGO, status=2, twin="ago-pen"),
    _half("sep-pen", SIG_PEN, "Septiembre 2026", SEP, status=2, twin="sep-usd", unplaced=3),
    _half("sep-usd", SIG_USD, "Septiembre 2026", SEP, status=1, twin="sep-pen", unplaced=3),
    _half("oct-pen", SIG_PEN, "Octubre 2026", OCT, status=1, twin="oct-usd", unplaced=2, shared=1),
    _half(
        "oct-usd",
        SIG_USD,
        "Octubre 2026",
        OCT,
        status=1,
        diff=-299,
        twin="oct-pen",
        unplaced=2,
        shared=1,
    ),
]

#: Ahorro Soles holds AHO alone (question 3 B): no item has a twin.
AHO = [
    _half("aho-ago", AHORRO, "Agosto 2026", ("2026-08-01", "2026-08-31"), status=2),
    _half("aho-sep", AHORRO, "Septiembre 2026", ("2026-09-01", "2026-09-30"), status=2),
    _half("aho-oct", AHORRO, "Octubre 2026", ("2026-10-01", "2026-10-31"), status=1, unplaced=4),
]

#: Sueldo Soles has no code: all three fields null.
NO_CODE = [
    {
        **_half("sue-oct", SUELDO, "Octubre 2026", ("2026-10-01", "2026-10-31"), status=1),
        "twin_id": None,
        "unplaced_count": None,
        "shared_place_count": None,
    }
]

RECONCILIATIONS = [*CARD, *AHO, *NO_CODE]

CARD_TITLE = "Reconciliations · Signature PEN + Signature USD · SIG   ·   oldest → newest"
CARD_HEADERS = ["Name", "Period", "Diff PEN", "Diff USD", "Status", "Order"]

#: Pane 1 A's rows, cell by cell.
CARD_ROWS = [
    ["Julio 2026", "2026-06-26 → 2026-07-25", "—", "no half", "completed", "in order"],
    ["Agosto 2026", "2026-07-26 → 2026-08-25", "—", "—", "completed", "in order"],
    ["Septiembre 2026", "2026-08-26 → 2026-09-25", "—", "—", "half completed", "not in order"],
    ["Octubre 2026", "2026-09-26 → 2026-10-25", "—", "-2.99", "draft", "not in order"],
]


def _answer(params: dict, accounts: list[dict], items: list[dict]) -> list[dict]:
    """`GET /reconciliations` as the contract says the engine answers it."""
    if "statement_of" in params:
        named = next((a for a in accounts if a["id"] == params["statement_of"]), None)
        code = named and named["statement_code"]
        if not code:
            on = {params["statement_of"]}
        else:
            on = {a["id"] for a in accounts if a["statement_code"] == code}
    else:
        on = {params["account_id"]}
    return [it for it in items if it["account_id"] in on]


def _engine(monkeypatch, accounts=ACCOUNTS, items=RECONCILIATIONS, fail=None) -> FakeClient:
    """The fake engine every read of the browse and the batch screen goes to.
    `fail`, an EngineError, is what `GET /reconciliations` answers instead."""
    client = FakeClient()

    def get(path: str, *, auth: bool = True, params: dict | None = None):
        params = params or {}
        client.calls.append(("GET", path, params))
        if path == "/accounts":
            archived = params.get("include_archived") == "true"
            return whole([a for a in accounts if archived or not a["is_archived"]])
        if path == "/reconciliations":
            if fail is not None:
                raise fail
            return whole(_answer(params, accounts, items))
        if path == "/bank-lines":
            return cursor_page([])
        if path == "/bank-lines/count":
            return {"count": 0}
        raise EngineError("NOT_FOUND", f"no fake response for GET {path}", None, 404, {})

    client.get = get  # type: ignore[method-assign]
    stub_home_month(monkeypatch)
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: client)
    monkeypatch.setattr("expense.http.ExpenseClient", lambda *a, **k: client)
    return client


def _reconciliation_reads(client: FakeClient) -> list[dict]:
    return [params for method, path, params in client.calls if path == "/reconciliations"]


async def _open(pilot, app, account: dict) -> ReconciliationsScreen:
    """The browse, the cursor on `account`, `⏎`."""
    screen = ReconciliationsScreen()
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    screen._accts_list.set_cursor(screen._accts_list.index_of(account["id"]))
    screen._acct_idx = screen._accts_list.index_of(account["id"])
    await pilot.press("enter")
    await wait_for(pilot, lambda: screen._mode == "batches")
    return screen


class Panel(NamedTuple):
    """What the panel shows: its title, its headers, each row's key, cells as text
    and style."""

    caption: str | None
    headers: list[str]
    keys: list
    cells: list[list[str]]
    styles: list[str]


def _panel(screen) -> Panel:
    lst = screen._batch_list
    return Panel(
        lst._caption,
        list(lst._headers),
        [row.key for row in lst._rows],
        [[str(cell) for cell in row.cells] for row in lst._rows],
        [row.base_style for row in lst._rows],
    )


def _marked(screen) -> list[str]:
    return [str(r.cells[0]) for r in screen._accts_list._rows if str(r.cells[0]).startswith("▸")]


# ---- one read, one row per statement, the same from either card account ----------


@pytest.mark.parametrize("account", [SIG_PEN, SIG_USD], ids=["soles", "dollars"])
def test_a_card_lists_one_row_per_statement_from_one_read(monkeypatch, account):
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, account)
        seen["panel"] = _panel(screen)
        seen["marked"] = _marked(screen)
        seen["shown"] = render_text(screen._batch_list._build(), width=120)

    run_app(scenario, size=(140, 50))
    assert _reconciliation_reads(client) == [{"statement_of": account["id"]}]
    assert seen["panel"].caption == CARD_TITLE
    assert seen["panel"].headers == CARD_HEADERS
    assert seen["panel"].cells == CARD_ROWS
    # a completed statement is dimmed, as a completed reconciliation is today
    assert seen["panel"].styles == ["dim", "dim", "", ""]
    assert seen["marked"] == ["▸ Signature PEN", "▸ Signature USD"]
    for word in ["Diff PEN", "Diff USD", "no half", "half completed", "not in order"]:
        assert word in seen["shown"]


def test_either_card_account_shows_the_identical_list(monkeypatch):
    _engine(monkeypatch)
    lists: list = []

    async def scenario(pilot, app):
        for account in (SIG_PEN, SIG_USD):
            screen = await _open(pilot, app, account)
            lists.append(_panel(screen)._replace(keys=[]))
            app.pop_screen()
            await pilot.pause()

    run_app(scenario, size=(140, 50))
    assert lists[0] == lists[1]


@pytest.mark.parametrize(
    "account, keys",
    [
        (SIG_PEN, ["jul-pen", "ago-pen", "sep-pen", "oct-pen"]),
        (SIG_USD, ["jul-pen", "ago-usd", "sep-usd", "oct-usd"]),
    ],
    ids=["soles", "dollars"],
)
def test_enter_on_a_statement_opens_the_open_accounts_half_else_the_other(
    monkeypatch, account, keys
):
    """Each row stands for the open account's half, or the other half on a month with
    none there; `⏎` opens that half on the batch screen, in its own currency."""
    _engine(monkeypatch)
    opened: list = []

    async def scenario(pilot, app):
        screen = await _open(pilot, app, account)
        assert [row.key for row in screen._batch_list._rows] == keys
        for index in (0, 3):
            screen._batch_list.set_cursor(index)
            await pilot.press("enter")
            await wait_for(pilot, lambda: isinstance(app.screen, ReconciliationDetailScreen))
            opened.append((app.screen._id, app.screen._currency))
            await pilot.press("escape")
            await wait_for(pilot, lambda: app.screen is screen and screen._mode == "batches")

    run_app(scenario, size=(140, 50))
    currency = account["currency_code"]
    assert opened == [("jul-pen", "PEN"), (keys[3], currency)]


def test_coming_back_and_r_read_the_whole_card_again_and_nothing_else(monkeypatch):
    client = _engine(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(pilot, app, SIG_USD)
        screen._batch_list.set_cursor(3)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ReconciliationDetailScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: len(_reconciliation_reads(client)) == 2)
        await wait_for(pilot, lambda: screen._mode == "batches")
        assert screen._batch_list.cursor_key == "oct-usd"
        assert _panel(screen).cells == CARD_ROWS
        await pilot.press("r")
        await wait_for(pilot, lambda: len(_reconciliation_reads(client)) == 3)
        await wait_for(pilot, lambda: screen._mode == "batches")

    run_app(scenario, size=(140, 50))
    assert _reconciliation_reads(client) == [{"statement_of": SIG_USD["id"]}] * 3


def test_the_footer_and_u_stay_as_today_on_a_card(monkeypatch):
    _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        await _open(pilot, app, SIG_PEN)
        active = app.screen.active_bindings
        seen["footer"] = {
            key: active[key].binding.description
            for key in ("enter", "escape", "r", "n", "u")
            if key in active and active[key].enabled
        }

    run_app(scenario, size=(140, 50))
    assert seen["footer"] == {
        "enter": "Open",
        "escape": "Close the panel",
        "r": "Refresh",
        "n": "New",
        "u": "No batch",
    }


def test_u_then_esc_brings_the_statements_back(monkeypatch):
    """`u` swaps the panel to the open account's rows in no batch, as today; `esc`
    swaps the statements back, their columns and title with them."""
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, SIG_PEN)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and not screen._unfiled_busy)
        await pilot.press("escape")
        await wait_for(pilot, lambda: screen._mode == "batches")
        seen["panel"] = _panel(screen)

    run_app(scenario, size=(140, 50))
    lines = [params for _m, path, params in client.calls if path == "/bank-lines"]
    assert [params.get("account_id") for params in lines] == [SIG_PEN["id"]]
    assert seen["panel"].caption == CARD_TITLE
    assert seen["panel"].headers == CARD_HEADERS
    assert seen["panel"].cells == CARD_ROWS
    assert _reconciliation_reads(client) == [{"statement_of": SIG_PEN["id"]}]


# ---- status and order, row by row -------------------------------------------------


@pytest.mark.parametrize(
    "statuses, word",
    [
        ((2, 2), "completed"),
        ((1, 1), "draft"),
        ((2, 1), "half completed"),
        ((1, 2), "half completed"),
        ((2,), "completed"),
        ((1,), "draft"),
    ],
)
def test_a_statements_status_is_its_halves(statuses, word):
    halves = [
        _half(f"h{i}", account, "Octubre 2026", OCT, status=status)
        for i, (account, status) in enumerate(zip((SIG_PEN, SIG_USD), statuses, strict=False))
    ]
    if len(halves) == 2:
        halves[0]["twin_id"], halves[1]["twin_id"] = "h1", "h0"
    columns = (("acc-sig-pen", "", "PEN"), ("acc-sig-usd", "", "USD"))
    [(_key, cells, style)] = statement_rows(halves, columns, "acc-sig-pen")
    assert cells[4] == word
    assert style == ("dim" if word == "completed" else "")
    assert ("no half" in cells) is (len(halves) == 1)


def test_a_one_half_month_on_the_other_account_says_no_half_where_it_lacks_one():
    usd_only = [_half("nov-usd", SIG_USD, "Noviembre 2026", OCT, status=1, diff=None)]
    columns = (("acc-sig-pen", "", "PEN"), ("acc-sig-usd", "", "USD"))
    [(key, cells, _style)] = statement_rows(usd_only, columns, "acc-sig-pen")
    assert key == "nov-usd"
    # no ending balance on the dollar half: its Diff is blank, as today's list shows it
    assert cells[2:5] == ["no half", "", "draft"]


@pytest.mark.parametrize(
    "unplaced, shared, word",
    [(0, 0, "in order"), (2, 0, "not in order"), (0, 1, "not in order"), (2, 1, "not in order")],
)
def test_the_order_is_the_engines_two_counts(unplaced, shared, word):
    item = _half("r", AHORRO, "Octubre 2026", OCT, status=1, unplaced=unplaced, shared=shared)
    assert str(order_cell(item)) == word


def test_no_counts_show_no_order():
    """On an account with no code the engine reads null counts: there is no order."""
    assert order_cell(NO_CODE[0]) == ""


# ---- a code no other account holds (question 3 B) ----------------------------------


def test_a_code_with_no_other_account_lists_its_statements_with_one_diff(monkeypatch):
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, AHORRO)
        seen["panel"] = _panel(screen)
        seen["marked"] = _marked(screen)

    run_app(scenario, size=(140, 50))
    assert _reconciliation_reads(client) == [{"statement_of": AHORRO["id"]}]
    assert seen["panel"].caption == "Reconciliations · Ahorro Soles · AHO   ·   oldest → newest"
    assert seen["panel"].headers == ["Name", "Period", "Diff", "Status", "Order"]
    assert seen["panel"].keys == ["aho-ago", "aho-sep", "aho-oct"]
    assert seen["panel"].cells == [
        ["Agosto 2026", "2026-08-01 → 2026-08-31", "—", "completed", "in order"],
        ["Septiembre 2026", "2026-09-01 → 2026-09-30", "—", "completed", "in order"],
        ["Octubre 2026", "2026-10-01 → 2026-10-31", "—", "draft", "not in order"],
    ]
    assert seen["marked"] == ["▸ Ahorro Soles"]


# ---- an account with no code keeps today's list -------------------------------------


def test_an_account_with_no_code_keeps_todays_read_and_list(monkeypatch):
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, SUELDO)
        seen["panel"] = _panel(screen)
        seen["marked"] = _marked(screen)

    run_app(scenario, size=(140, 50))
    assert _reconciliation_reads(client) == [{"account_id": SUELDO["id"]}]
    assert seen["panel"].caption == "Reconciliations · Sueldo Soles   ·   oldest → newest"
    assert seen["panel"].headers == ["Name", "Period", "Begin", "End", "Diff", "Status"]
    assert seen["panel"].cells == [
        ["Octubre 2026", "2026-10-01 → 2026-10-31", "0.00", "0.00", "—", "draft"]
    ]
    assert seen["marked"] == ["▸ Sueldo Soles"]


# ---- a refused read ----------------------------------------------------------------


def test_a_refused_read_leaves_the_panel_closed_with_the_engines_words(monkeypatch):
    err = EngineError("VALIDATION_ERROR", "Validation failed.", {"statement_of": "Bad."}, 422, {})
    client = _engine(monkeypatch, fail=err)
    notes: list = []
    monkeypatch.setattr(
        ReconciliationsScreen,
        "notify",
        lambda self, message, title="", **kw: notes.append((title, message)),
    )

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("enter")
        await wait_for(pilot, lambda: notes)
        assert screen._mode == "accts" and screen._batch_list is None

    run_app(scenario, size=(140, 50))
    assert _reconciliation_reads(client) == [{"statement_of": SIG_PEN["id"]}]
    assert notes == [("Failed", format_error(err))]


# ---- an archived card account --------------------------------------------------------


def test_an_archived_card_accounts_halves_still_show_under_its_column(monkeypatch):
    """The engine's whole-card list holds an archived card account's halves
    (contract: GET /v1/reconciliations), though neither account names the other while
    one is archived (contract: "Bank Accounts", "While one of the two accounts is archived");
    the browse lists no archived account, yet the accounts read names its column and the
    title, so every half shows where it belongs."""
    live_pen = {**SIG_PEN, "statement_partner_id": None}
    archived_usd = {**SIG_USD, "statement_partner_id": None, "is_archived": True}
    accounts = [live_pen, archived_usd, AHORRO, SUELDO, DIGITAL]
    client = _engine(monkeypatch, accounts=accounts)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, SIG_PEN)
        seen["panel"] = _panel(screen)
        seen["listed"] = [str(r.cells[0]) for r in screen._accts_list._rows]

    run_app(scenario, size=(140, 50))
    assert _reconciliation_reads(client) == [{"statement_of": SIG_PEN["id"]}]
    assert seen["listed"] == [
        "▸ Signature PEN",
        "Ahorro Soles",
        "Sueldo Soles",
        "Cuenta Digital Dólares",
    ]
    assert seen["panel"].caption == CARD_TITLE
    assert seen["panel"].headers == CARD_HEADERS
    assert seen["panel"].cells == CARD_ROWS


# ---- the shared read and the accounts a code labels ---------------------------------


@pytest.mark.parametrize(
    "kw", [{}, {"account_id": "a", "statement_of": "a"}], ids=["neither", "both"]
)
def test_the_list_read_takes_exactly_one_of_its_two_parameters(kw):
    """The engine refuses neither and both (contract: GET /v1/reconciliations)."""
    from expense.reads import fetch_reconciliations

    with pytest.raises(ValueError):
        fetch_reconciliations(object(), **kw)


def test_a_statement_shows_the_account_its_partner_and_every_account_it_has_a_half_on():
    """The columns are the open account, the account the engine names on it, and
    every account the `statement_of` answer has a half on, in the accounts read's
    order; never another account found by its code."""
    from expense.tui.screens.reconciliations import StatementAccounts, statement_columns

    pen, usd = ("acc-sig-pen", "Signature PEN", "PEN"), ("acc-sig-usd", "Signature USD", "USD")
    accounts = [SIG_PEN, SIG_USD, AHORRO, SUELDO]
    assert statement_columns("acc-sig-usd", accounts, []) == StatementAccounts("SIG", (pen, usd))
    unnamed_pen = {**SIG_PEN, "statement_partner_id": None}
    archived_usd = {**SIG_USD, "statement_partner_id": None, "is_archived": True}
    accounts = [unnamed_pen, archived_usd, AHORRO, SUELDO]
    assert statement_columns("acc-sig-pen", accounts, CARD) == StatementAccounts("SIG", (pen, usd))
    assert statement_columns("acc-sig-pen", accounts, []) == StatementAccounts("SIG", (pen,))
    assert statement_columns("acc-ahorro", accounts, AHO) == StatementAccounts(
        "AHO", (("acc-ahorro", "Ahorro Soles", "PEN"),)
    )
    assert statement_columns("acc-sueldo", accounts, NO_CODE) is None


# ---- c, u and d on a card half's batch screen act on both halves --------------------


def _writing_engine(monkeypatch) -> FakeClient:
    """`_engine` over its own copy of the reconciliations, which a write changes as the
    engine does: the write answers in the engine's shape (`FAKE_ANSWERS`), the half the
    path names and its `twin`, and each half that answer names reads afterwards with
    the answer's status, a deleted half no longer listed
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response")
    (contract: POST /v1/reconciliations/{reconciliation_id}/revert)
    (contract: DELETE /v1/reconciliations/{reconciliation_id}, "Response")."""
    items = [dict(item) for item in RECONCILIATIONS]
    client = _engine(monkeypatch, items=items)
    client.get_responses.update({f"/reconciliations/{item['id']}": item for item in items})

    def written(answer: dict) -> dict:
        for half in (answer, answer.get("twin")):
            item = next((it for it in items if half and it["id"] == half["id"]), None)
            if item is None:
                continue
            if half.get("deleted_at"):
                items.remove(item)
            else:
                item["status"] = half["status"]
        return answer

    post, delete = client.post, client.delete
    client.post = lambda path, json_body=None: written(post(path, json_body))  # type: ignore[method-assign]
    client.delete = lambda path: written(delete(path))  # type: ignore[method-assign]
    return client


#: Each status key on a card half's batch screen, opened from the dollar account on the
#: row at `row`: the half it opens, the one write it sends, its toast, the header's status
#: after it (`None`: the screen closes), and the browse's rows after it. Octubre is a
#: draft, Agosto completed (`CARD`); a completed statement's row is dimmed.
STATUS_KEYS = {
    "c": (
        3,
        "oct-usd",
        ("POST", "/reconciliations/oct-usd/complete"),
        "Reconciliation completed.",
        "completed",
        [*CARD_ROWS[:3], [*CARD_ROWS[3][:4], "completed", "not in order"]],
        ["dim", "dim", "", "dim"],
    ),
    "u": (
        1,
        "ago-usd",
        ("POST", "/reconciliations/ago-usd/revert"),
        "Reconciliation reverted to draft.",
        "draft",
        [CARD_ROWS[0], [*CARD_ROWS[1][:4], "draft", "in order"], *CARD_ROWS[2:]],
        ["dim", "", "", ""],
    ),
    "d": (
        3,
        "oct-usd",
        ("DELETE", "/reconciliations/oct-usd"),
        "Reconciliation deleted.",
        None,
        CARD_ROWS[:3],
        ["dim", "dim", ""],
    ),
}


@pytest.mark.parametrize("key", list(STATUS_KEYS))
def test_c_u_and_d_on_a_card_half_send_one_write_and_both_halves_show_it(monkeypatch, key):
    """`c`, `u` and `d` on one half of a card statement, each confirmed with `y`, send
    one write on the half the screen shows, never one per half: the engine completes,
    reverts or deletes the whole statement from either half
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete)
    (contract: POST /v1/reconciliations/{reconciliation_id}/revert)
    (contract: DELETE /v1/reconciliations/{reconciliation_id}). The batch screen's
    header shows its half's new status, and back on the browse the statement's row,
    read again, shows both halves' (a deleted statement's row gone)."""
    row, half, write, toast, status, rows, styles = STATUS_KEYS[key]
    client = _writing_engine(monkeypatch)
    notes: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notes.append(message)
    )
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, SIG_USD)
        screen._batch_list.set_cursor(row)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ReconciliationDetailScreen))
        detail = app.screen
        seen["opened"] = detail._id
        await wait_for(pilot, lambda: detail._list is not None)
        listed = screen._batch_list
        await pilot.press(key)
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        if status is not None:
            seen["head"] = str(detail.query_one("#rhead", Static).visual)
            await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen and screen._batch_list is not listed)
        await wait_for(pilot, lambda: screen._batch_list is not None)
        seen["panel"] = _panel(screen)

    run_app(scenario, size=(140, 50))
    assert seen["opened"] == half
    assert [(method, path) for method, path, _ in client.calls if method != "GET"] == [write]
    assert notes == [toast]
    if status is not None:
        assert seen["head"].endswith(f"status {status}")
    assert seen["panel"].cells == rows
    assert seen["panel"].styles == styles


@pytest.mark.parametrize("key", list(STATUS_KEYS))
def test_a_status_key_on_a_card_half_is_one_request_under_one_key(configured, monkeypatch, key):
    """Through the shared write path and the real HTTP client, each key's write on a
    card half is one request carrying one `X-Idempotency-Key`, and nothing is sent on
    the other half's path."""
    row, half, (method, path), toast, _status, _rows, _styles = STATUS_KEYS[key]
    record = next(item for item in CARD if item["id"] == half)
    twin = next(item for item in CARD if item["id"] == record["twin_id"])
    answers = {
        "c": complete_answer({**record, "status": 2}, twin={**twin, "status": 2}),
        "u": revert_answer({**record, "status": 1}, twin={**twin, "status": 1}),
        "d": delete_answer(record, twin=twin),
    }
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map",
        lambda: {SIG_USD["id"]: SIG_USD["name"]},
    )
    notes: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notes.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(record), currency="USD")
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.press(key)
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)

    with respx.mock() as mock:
        mock.get(f"{ENGINE_URL}/v1/bank-lines").mock(httpx.Response(200, json=cursor_page([])))
        route = mock.request(method, f"{ENGINE_URL}/v1{path}").mock(
            httpx.Response(200, json=answers[key])
        )
        run_app(scenario)
        writes = [call.request for call in mock.calls if call.request.method != "GET"]
    assert notes == [toast]
    assert route.call_count == 1
    assert writes == [route.calls.last.request]
    assert writes[0].headers["X-Idempotency-Key"]
