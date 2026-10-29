"""The Reconciliations browse: one row per statement of the open account's holder.

Pane 1 A of docs/mockups/expense-world-card-statement.html, and its task 6 question 3 B
for a holder of one account with a code. `⏎` on an account reads
`GET /statements?holder_id=<its holder>`, every statement of the holder, and nothing
else about statements; each row is one statement, each Diff the difference of one
account of the holder, from that account's entry in `balances` (contract: GET /v1/statements)
(contract: "Statements", "Statement response"). A holder with no statement code keeps
today's list, the open account's Begin, End and Diff. On a statement's batch screen
opened from a card account, `c`, `u` and `d` each send one write.

The engine is a `FakeClient` behind the reads module's own HTTP client, so the query
each read sends is the one `expense/reads.py` builds; it answers the way the contract
says the engine does: `holder_id` lists that holder's statements, in the engine's order.
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
    StatementAccounts,
    account_view,
    order_cell,
    statement_columns,
    statement_rows,
)
from tests.unit.helpers import (
    ENGINE_URL,
    FakeClient,
    account_record,
    cursor_page,
    holder_list,
    render_text,
    run_app,
    statement_complete_answer,
    statement_delete_answer,
    statement_record,
    statement_revert_answer,
    stub_home_month,
    wait_for,
    wait_for_list,
    whole,
)


def _held(cents: int) -> dict:
    """An account's balance, in its own currency and at home alike."""
    return {"current_balance_cents": cents, "current_balance_home_cents": cents}


#: The accounts as `GET /accounts` reads them, each naming the holder it is on
#: (contract: "Holders"): a card's two on one holder, three others alone on theirs.
SIG_PEN = account_record(
    id="acc-sig-pen", **_held(-51230), name="Signature PEN", sort_order=1, holder_id="h-sig"
)
SIG_USD = account_record(
    id="acc-sig-usd",
    **_held(-6140),
    name="Signature USD",
    currency_code="USD",
    sort_order=2,
    holder_id="h-sig",
)
AHORRO = account_record(
    id="acc-ahorro", **_held(648000), name="Ahorro Soles", sort_order=3, holder_id="h-aho"
)
SUELDO = account_record(
    id="acc-sueldo", **_held(1245000), name="Sueldo Soles", sort_order=4, holder_id="h-sue"
)
DIGITAL = account_record(
    id="acc-digital",
    **_held(82015),
    name="Cuenta Digital Dólares",
    currency_code="USD",
    sort_order=5,
    holder_id="h-dig",
)
ACCOUNTS = [SIG_PEN, SIG_USD, AHORRO, SUELDO, DIGITAL]
#: The holders as `GET /holders` reads them: the card's with code SIG, Ahorro's with
#: AHO, the other two with none (contract: "Holders", "Statement code").
HOLDERS = [
    {"id": "h-sig", "statement_code": "SIG", "account_ids": ["acc-sig-pen", "acc-sig-usd"]},
    {"id": "h-aho", "statement_code": "AHO", "account_ids": ["acc-ahorro"]},
    {"id": "h-sue", "account_ids": ["acc-sueldo"]},
    {"id": "h-dig", "account_ids": ["acc-digital"]},
]
#: Each holder's statement code, as the browse keeps it.
CODES = {"h-sig": "SIG", "h-aho": "AHO", "h-sue": None, "h-dig": None}


def _statement(
    sid: str,
    holder: str,
    name: str,
    days: tuple[str, str],
    diffs: dict[str, int | None],
    *,
    status: int,
    unplaced: int | None = 0,
    shared: int | None = 0,
) -> dict:
    """A statement as `GET /statements` reads it: one balance per account of `diffs`,
    each beginning at 0 and its ending entered unless its difference is `None`."""
    return statement_record(
        {
            "id": sid,
            "holder_id": holder,
            "name": name,
            "date_start": days[0],
            "date_end": days[1],
            "status": status,
            "unplaced_count": unplaced,
            "shared_place_count": shared,
            "balances": [
                {
                    "account_id": account,
                    "ending_balance_cents": None if diff is None else 0,
                    "difference_cents": diff,
                }
                for account, diff in diffs.items()
            ],
        }
    )


JUL = ("2026-06-26", "2026-07-25")
AGO = ("2026-07-26", "2026-08-25")
SEP = ("2026-08-26", "2026-09-25")
OCT = ("2026-09-26", "2026-10-25")


def _card(diff_usd: int | None = 0) -> dict[str, int | None]:
    return {"acc-sig-pen": 0, "acc-sig-usd": diff_usd}


#: The card's four months of pane 1 A, in the engine's order: `date_start` ascending,
#: then creation time, oldest first (contract: "Statements", "Ordering"). Julio and
#: Agosto are completed; Septiembre is a draft with three lines unplaced; Octubre is a
#: draft, its dollar account off by -2.99, two lines unplaced and a place held twice.
CARD = [
    _statement("jul", "h-sig", "Julio 2026", JUL, _card(), status=2),
    _statement("ago", "h-sig", "Agosto 2026", AGO, _card(), status=2),
    _statement("sep", "h-sig", "Septiembre 2026", SEP, _card(), status=1, unplaced=3),
    _statement("oct", "h-sig", "Octubre 2026", OCT, _card(-299), status=1, unplaced=2, shared=1),
]

#: Ahorro Soles' holder holds AHO and one account (question 3 B).
AHO = [
    _statement(
        f"aho-{month}",
        "h-aho",
        f"{name} 2026",
        (f"2026-{number}-01", f"2026-{number}-{last}"),
        {"acc-ahorro": 0},
        status=status,
        unplaced=unplaced,
    )
    for month, name, number, last, status, unplaced in [
        ("ago", "Agosto", "08", "31", 2, 0),
        ("sep", "Septiembre", "09", "30", 2, 0),
        ("oct", "Octubre", "10", "31", 1, 4),
    ]
]

#: Sueldo Soles' holder has no code: both order counts null.
NO_CODE = [
    _statement(
        "sue-oct",
        "h-sue",
        "Octubre 2026",
        ("2026-10-01", "2026-10-31"),
        {"acc-sueldo": 0},
        status=1,
        unplaced=None,
        shared=None,
    )
]

STATEMENTS = [*CARD, *AHO, *NO_CODE]

CARD_TITLE = "Reconciliations · Signature PEN + Signature USD · SIG   ·   oldest → newest"
CARD_HEADERS = ["Name", "Period", "Diff PEN", "Diff USD", "Status", "Order"]

#: Pane 1 A's rows, cell by cell.
CARD_ROWS = [
    ["Julio 2026", "2026-06-26 → 2026-07-25", "—", "—", "completed", "in order"],
    ["Agosto 2026", "2026-07-26 → 2026-08-25", "—", "—", "completed", "in order"],
    ["Septiembre 2026", "2026-08-26 → 2026-09-25", "—", "—", "draft", "not in order"],
    ["Octubre 2026", "2026-09-26 → 2026-10-25", "—", "-2.99", "draft", "not in order"],
]


def _engine(monkeypatch, accounts=ACCOUNTS, items=STATEMENTS, fail=None) -> FakeClient:
    """The fake engine every read of the browse and the batch screen goes to.
    `fail`, an EngineError, is what `GET /statements` answers instead."""
    client = FakeClient()

    def get(path: str, *, auth: bool = True, params: dict | None = None):
        params = params or {}
        client.calls.append(("GET", path, params))
        if path == "/accounts":
            archived = params.get("include_archived") == "true"
            return whole([a for a in accounts if archived or not a["is_archived"]])
        if path == "/holders":
            return holder_list(HOLDERS)
        if path == "/statements":
            if fail is not None:
                raise fail
            return whole([it for it in items if it["holder_id"] == params["holder_id"]])
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


def _statement_reads(client: FakeClient) -> list[dict]:
    return [params for method, path, params in client.calls if path == "/statements"]


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
    assert _statement_reads(client) == [{"holder_id": "h-sig"}]
    assert seen["panel"].caption == CARD_TITLE
    assert seen["panel"].headers == CARD_HEADERS
    assert seen["panel"].keys == ["jul", "ago", "sep", "oct"]
    assert seen["panel"].cells == CARD_ROWS
    # a completed statement is dimmed, as a completed reconciliation is today
    assert seen["panel"].styles == ["dim", "dim", "", ""]
    assert seen["marked"] == ["▸ Signature PEN", "▸ Signature USD"]
    for word in ["Diff PEN", "Diff USD", "not in order"]:
        assert word in seen["shown"]


def test_either_card_account_shows_the_identical_list(monkeypatch):
    _engine(monkeypatch)
    lists: list = []

    async def scenario(pilot, app):
        for account in (SIG_PEN, SIG_USD):
            screen = await _open(pilot, app, account)
            lists.append(_panel(screen))
            app.pop_screen()
            await pilot.pause()

    run_app(scenario, size=(140, 50))
    assert lists[0] == lists[1]


@pytest.mark.parametrize("account", [SIG_PEN, SIG_USD], ids=["soles", "dollars"])
def test_enter_on_a_statement_opens_it_on_the_open_account(monkeypatch, account):
    """`⏎` opens the statement on the batch screen as the open account's: that
    account's balances from its entry in `balances`, in its own currency."""
    _engine(monkeypatch)
    opened: list = []

    async def scenario(pilot, app):
        screen = await _open(pilot, app, account)
        for index in (0, 3):
            screen._batch_list.set_cursor(index)
            await pilot.press("enter")
            await wait_for(pilot, lambda: isinstance(app.screen, ReconciliationDetailScreen))
            record = app.screen._record
            opened.append(
                (
                    app.screen._id,
                    app.screen._currency,
                    record["account_id"],
                    record["difference_cents"],
                )
            )
            await pilot.press("escape")
            await wait_for(pilot, lambda: app.screen is screen and screen._mode == "batches")

    run_app(scenario, size=(140, 50))
    currency, aid = account["currency_code"], account["id"]
    october = -299 if account is SIG_USD else 0
    assert opened == [("jul", currency, aid, 0), ("oct", currency, aid, october)]


def test_a_statement_opened_on_an_account_is_the_statement_and_that_accounts_balances():
    view = account_view(CARD[3], "acc-sig-usd")
    assert (view["id"], view["name"], view["status"]) == ("oct", "Octubre 2026", 1)
    assert (view["account_id"], view["difference_cents"]) == ("acc-sig-usd", -299)
    assert (view["beginning_balance_cents"], view["ending_balance_cents"]) == (0, 0)


def test_coming_back_and_r_read_the_whole_card_again_and_nothing_else(monkeypatch):
    client = _engine(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(pilot, app, SIG_USD)
        screen._batch_list.set_cursor(3)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ReconciliationDetailScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: len(_statement_reads(client)) == 2)
        await wait_for(pilot, lambda: screen._mode == "batches")
        assert screen._batch_list.cursor_key == "oct"
        assert _panel(screen).cells == CARD_ROWS
        await pilot.press("r")
        await wait_for(pilot, lambda: len(_statement_reads(client)) == 3)
        await wait_for(pilot, lambda: screen._mode == "batches")

    run_app(scenario, size=(140, 50))
    assert _statement_reads(client) == [{"holder_id": "h-sig"}] * 3


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
    assert _statement_reads(client) == [{"holder_id": "h-sig"}]


# ---- status, each account's difference and order, row by row -----------------------


COLUMNS = (("acc-sig-pen", "", "PEN"), ("acc-sig-usd", "", "USD"))


@pytest.mark.parametrize("status, word", [(2, "completed"), (1, "draft")])
def test_a_statements_status_is_its_own(status, word):
    """One status for the whole holder (contract: "Statements"); a completed one dims."""
    [(key, cells, style)] = statement_rows([{**CARD[3], "status": status}], COLUMNS)
    assert (key, cells[4]) == ("oct", word)
    assert style == ("dim" if status == 2 else "")


def test_each_diff_is_its_own_accounts_entry_whatever_the_order_of_balances():
    """The engine lists `balances` in the accounts' order; each column reads its own
    account's entry by id, so a Diff never shows another account's figure."""
    swapped = {**CARD[3], "balances": list(reversed(CARD[3]["balances"]))}
    [(_key, cells, _style)] = statement_rows([swapped], COLUMNS)
    assert [str(cell) for cell in cells[2:4]] == ["—", "-2.99"]


def test_an_account_with_no_ending_balance_shows_a_blank_diff():
    """`difference_cents` is null until the ending balance is entered, shown blank as
    today's list shows it (contract: "Statements", "`difference_cents` — the add-up check")."""
    open_usd = _statement("nov", "h-sig", "Noviembre 2026", OCT, _card(None), status=1)
    [(_key, cells, _style)] = statement_rows([open_usd], COLUMNS)
    assert [str(cell) for cell in cells[2:5]] == ["—", "", "draft"]


@pytest.mark.parametrize(
    "unplaced, shared, word",
    [(0, 0, "in order"), (2, 0, "not in order"), (0, 1, "not in order"), (2, 1, "not in order")],
)
def test_the_order_is_the_engines_two_counts(unplaced, shared, word):
    item = {**AHO[2], "unplaced_count": unplaced, "shared_place_count": shared}
    assert str(order_cell(item)) == word


def test_no_counts_show_no_order():
    """On a holder with no code the engine reads null counts: there is no order."""
    assert order_cell(NO_CODE[0]) == ""


# ---- a holder of one account with a code (question 3 B) ----------------------------


def test_a_code_on_a_holder_of_one_account_lists_its_statements_with_one_diff(monkeypatch):
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, AHORRO)
        seen["panel"] = _panel(screen)
        seen["marked"] = _marked(screen)

    run_app(scenario, size=(140, 50))
    assert _statement_reads(client) == [{"holder_id": "h-aho"}]
    assert seen["panel"].caption == "Reconciliations · Ahorro Soles · AHO   ·   oldest → newest"
    assert seen["panel"].headers == ["Name", "Period", "Diff", "Status", "Order"]
    assert seen["panel"].keys == ["aho-ago", "aho-sep", "aho-oct"]
    assert seen["panel"].cells == [
        ["Agosto 2026", "2026-08-01 → 2026-08-31", "—", "completed", "in order"],
        ["Septiembre 2026", "2026-09-01 → 2026-09-30", "—", "completed", "in order"],
        ["Octubre 2026", "2026-10-01 → 2026-10-31", "—", "draft", "not in order"],
    ]
    assert seen["marked"] == ["▸ Ahorro Soles"]


# ---- a holder with no code keeps today's list ---------------------------------------


def test_a_holder_with_no_code_keeps_todays_list(monkeypatch):
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, SUELDO)
        seen["panel"] = _panel(screen)
        seen["marked"] = _marked(screen)

    run_app(scenario, size=(140, 50))
    assert _statement_reads(client) == [{"holder_id": "h-sue"}]
    assert seen["panel"].caption == "Reconciliations · Sueldo Soles   ·   oldest → newest"
    assert seen["panel"].headers == ["Name", "Period", "Begin", "End", "Diff", "Status"]
    assert seen["panel"].cells == [
        ["Octubre 2026", "2026-10-01 → 2026-10-31", "0.00", "0.00", "—", "draft"]
    ]
    assert seen["marked"] == ["▸ Sueldo Soles"]


# ---- a refused read ----------------------------------------------------------------


def test_a_refused_read_leaves_the_panel_closed_with_the_engines_words(monkeypatch):
    err = EngineError("VALIDATION_ERROR", "Validation failed.", {"holder_id": "Bad."}, 422, {})
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
    assert _statement_reads(client) == [{"holder_id": "h-sig"}]
    assert notes == [("Failed", format_error(err))]


# ---- an archived holder ------------------------------------------------------------


def test_an_archived_holders_accounts_are_not_listed(monkeypatch):
    """A holder is archived whole, every account of it with it (contract: "Holders",
    "A holder is archived whole"): the browse reads the live accounts alone, so an
    archived card lists neither account."""
    archived = [account_record(a, is_archived=True) for a in (SIG_PEN, SIG_USD)]
    client = _engine(monkeypatch, accounts=[*archived, AHORRO, SUELDO, DIGITAL])
    seen: dict = {}

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        seen["listed"] = [str(r.cells[0]) for r in screen._accts_list._rows]

    run_app(scenario, size=(140, 50))
    assert seen["listed"] == ["Ahorro Soles", "Sueldo Soles", "Cuenta Digital Dólares"]
    assert [params for _m, path, params in client.calls if path == "/accounts"][0] == {}


# ---- the accounts a code labels ------------------------------------------------------


def test_a_statement_list_shows_every_account_of_the_holder_titled_by_its_code():
    """The columns are the open account's holder's accounts, in the accounts read's
    order, from either of them; the code is the holder's. A holder with no code has no
    statement list: None."""
    pen, usd = ("acc-sig-pen", "Signature PEN", "PEN"), ("acc-sig-usd", "Signature USD", "USD")
    for aid in ("acc-sig-pen", "acc-sig-usd"):
        assert statement_columns(aid, ACCOUNTS, CODES) == StatementAccounts("SIG", (pen, usd))
    assert statement_columns("acc-ahorro", ACCOUNTS, CODES) == StatementAccounts(
        "AHO", (("acc-ahorro", "Ahorro Soles", "PEN"),)
    )
    assert statement_columns("acc-sueldo", ACCOUNTS, CODES) is None


# ---- c, u and d on a statement opened from a card account ---------------------------


def _writing_engine(monkeypatch) -> FakeClient:
    """`_engine` over its own copy of the statements, which a write changes: the batch
    screen's write answers in the engine's shape (`FAKE_ANSWERS`), the record its path
    names as the test serves it, and that statement reads afterwards with the answer's
    status, a deleted one no longer listed."""
    items = [dict(item) for item in STATEMENTS]
    client = _engine(monkeypatch, items=items)
    client.get_responses.update({f"/statements/{item['id']}": item for item in items})

    def written(answer: dict) -> dict:
        item = next((it for it in items if it["id"] == answer["id"]), None)
        if item is not None and answer.get("deleted_at"):
            items.remove(item)
        elif item is not None:
            item["status"] = answer["status"]
        return answer

    post, delete = client.post, client.delete
    client.post = lambda path, json_body=None: written(post(path, json_body))  # type: ignore[method-assign]
    client.delete = lambda path: written(delete(path))  # type: ignore[method-assign]
    return client


#: Each status key on a statement's batch screen, opened from the dollar account on the
#: row at `row`: the statement it opens, the one write it sends, its toast, the header's
#: status after it (`None`: the screen closes), and the browse's rows after it. Octubre
#: is a draft, Agosto completed (`CARD`); a completed statement's row is dimmed.
STATUS_KEYS = {
    "c": (
        3,
        "oct",
        ("POST", "/statements/oct/complete"),
        "Reconciliation completed.",
        "completed",
        [*CARD_ROWS[:3], [*CARD_ROWS[3][:4], "completed", "not in order"]],
        ["dim", "dim", "", "dim"],
    ),
    "u": (
        1,
        "ago",
        ("POST", "/statements/ago/revert"),
        "Reconciliation reverted to draft.",
        "draft",
        [CARD_ROWS[0], [*CARD_ROWS[1][:4], "draft", "in order"], *CARD_ROWS[2:]],
        ["dim", "", "", ""],
    ),
    "d": (
        3,
        "oct",
        ("DELETE", "/statements/oct"),
        "Reconciliation deleted.",
        None,
        CARD_ROWS[:3],
        ["dim", "dim", ""],
    ),
}


@pytest.mark.parametrize("key", list(STATUS_KEYS))
def test_c_u_and_d_on_a_card_statement_send_one_write_and_the_list_shows_it(monkeypatch, key):
    """`c`, `u` and `d` on a statement opened from one card account, each confirmed
    with `y`, send one write on the statement the screen shows. The batch screen's
    header shows its new status, and back on the browse the statement's row, read
    again, shows it (a deleted statement's row gone)."""
    row, opened, write, toast, status, rows, styles = STATUS_KEYS[key]
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
    assert seen["opened"] == opened
    assert [(method, path) for method, path, _ in client.calls if method != "GET"] == [write]
    assert notes == [toast]
    if status is not None:
        assert seen["head"].endswith(f"status {status}")
    assert seen["panel"].cells == rows
    assert seen["panel"].styles == styles


@pytest.mark.parametrize("key", list(STATUS_KEYS))
def test_a_status_key_on_a_card_statement_is_one_request_under_one_key(
    configured, monkeypatch, key
):
    """Through the shared write path and the real HTTP client, each key's write on a
    statement opened from a card account is one request carrying one
    `X-Idempotency-Key`."""
    _row, opened, (method, path), toast, _status, _rows, _styles = STATUS_KEYS[key]
    statement = next(item for item in CARD if item["id"] == opened)
    record = account_view(statement, SIG_USD["id"])
    answers = {
        "c": statement_complete_answer({**statement, "status": 2}),
        "u": statement_revert_answer({**statement, "status": 1}),
        "d": statement_delete_answer(statement),
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
