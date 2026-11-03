"""The Statements browse: one row per bank account, and an account's statements.

Panes 2 and 3 of docs/mockups/expense-world-statements-screens.html. The browse lists
every bank account once, with its currencies and a balance in each, and reads no
statements. `⏎` on an account reads `GET /statements?account_id=<its id>`, its
statements whole, and nothing else about statements (contract: GET /v1/statements,
"`?account_id=<id>` is required"); each row is one statement, a Diff per currency the
account holds from that currency's entry in `balances` (contract: "Statements"), its
status and, on an account with a statement code, its order (contract: "What an
account is", "Statement code"). A currency the statement does not cover shows nothing
(question 2 B), and a difference not checked yet stays blank (question 3 B). On a
statement's screen opened from the account, `c`, `u` and `d` each send one write.

The engine is a `FakeClient` behind the reads module's own HTTP client, so the query
each read sends is the one `expense/reads.py` builds; it answers the way the contract
says the engine does: `account_id` lists that account's statements, in the engine's order.
"""

import re
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
    browse_accounts,
    order_cell,
    statement_headers,
    statement_rows,
)
from tests.unit.helpers import (
    ENGINE_URL,
    FakeClient,
    account_with_currencies,
    cursor_page,
    held_currency,
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

pytestmark = pytest.mark.usefixtures("no_flagged_lines")

#: The accounts as `GET /accounts` reads them (contract: "Bank Accounts"): a Visa
#: holding soles and dollars with its own statement code, another holding both with
#: none, and two holding one currency each.
VISA = account_with_currencies(
    id="acc-visa",
    name="Visa BCP",
    sort_order=1,
    statement_code="VIS",
    currencies=[held_currency("PEN", -23420), held_currency("USD", -3098)],
)
IBK = account_with_currencies(
    id="acc-ibk",
    name="IBK Visa",
    sort_order=2,
    currencies=[held_currency("PEN", -51290), held_currency("USD", -2499)],
)
SUELDO = account_with_currencies(
    id="acc-sueldo",
    name="Sueldo Soles",
    sort_order=3,
    currencies=[held_currency("PEN", 1245000)],
)
DIGITAL = account_with_currencies(
    id="acc-digital",
    name="BBVA Dólares",
    sort_order=4,
    currencies=[held_currency("USD", 82015)],
)
ACCOUNTS = [VISA, IBK, SUELDO, DIGITAL]


def _statement(
    sid: str,
    account: str,
    name: str,
    days: tuple[str, str],
    diffs: dict[str, int | None],
    *,
    status: int,
    unplaced: int | None = 0,
    shared: int | None = 0,
    blank: tuple[str, ...] = (),
) -> dict:
    """A statement as `GET /statements` reads it: one balance per currency of `diffs`,
    each beginning at 0 and its ending entered unless its difference is `None`; a
    currency of `blank` has both balances not entered (`null`)."""
    return statement_record(
        {
            "id": sid,
            "account_id": account,
            "name": name,
            "date_start": days[0],
            "date_end": days[1],
            "status": status,
            "unplaced_count": unplaced,
            "shared_place_count": shared,
            "balances": [
                {
                    "currency_code": code,
                    "beginning_balance_cents": None if code in blank else 0,
                    "ending_balance_cents": None if diff is None or code in blank else 0,
                    "difference_cents": diff,
                }
                for code, diff in diffs.items()
            ],
        }
    )


AGO = ("2026-07-26", "2026-08-25")
SEP = ("2026-08-26", "2026-09-25")
OCT = ("2026-09-26", "2026-10-25")

#: Visa BCP's three statements of pane 3, in the engine's order: `date_start` ascending,
#: then creation time, oldest first (contract: "Statements", "Ordering"). Septiembre had
#: no dollar line and no dollars owed, so it covers soles alone. Octubre is a draft, its
#: dollars off by -2.99, two lines unplaced and a place held twice.
VISA_STATEMENTS = [
    _statement("vis-ago", "acc-visa", "[VIS] Agosto", AGO, {"PEN": 0, "USD": 0}, status=2),
    _statement("vis-sep", "acc-visa", "VIS-202609", SEP, {"PEN": 0}, status=2),
    _statement(
        "vis-oct",
        "acc-visa",
        "VIS-202610",
        OCT,
        {"PEN": 0, "USD": -299},
        status=1,
        unplaced=2,
        shared=1,
    ),
]

#: IBK Visa has no statement code, so both order counts are null. Octubre's dollar
#: balances are blank, a dollar line ticked into a soles-only draft.
IBK_STATEMENTS = [
    _statement(
        "ibk-ago", "acc-ibk", "Agosto 2026", AGO, {"PEN": 0, "USD": 0}, status=2,
        unplaced=None, shared=None,
    ),
    _statement(
        "ibk-sep", "acc-ibk", "Septiembre 2026", SEP, {"PEN": 0}, status=2,
        unplaced=None, shared=None,
    ),
    _statement(
        "ibk-oct", "acc-ibk", "Octubre 2026", OCT, {"PEN": 0, "USD": None}, status=1,
        unplaced=None, shared=None, blank=("USD",),
    ),
]  # fmt: skip

#: Sueldo Soles holds one currency and no code.
SUELDO_STATEMENTS = [
    _statement(
        "sue-oct", "acc-sueldo", "Octubre 2026", OCT, {"PEN": 0}, status=1,
        unplaced=None, shared=None,
    )
]  # fmt: skip

STATEMENTS = [*VISA_STATEMENTS, *IBK_STATEMENTS, *SUELDO_STATEMENTS]

VISA_TITLE = "Statements · Visa BCP · PEN + USD · VIS   ·   oldest → newest"
VISA_HEADERS = ["Name", "Period", "Diff PEN", "Diff USD", "Status", "Order"]

#: Pane 3's rows for Visa BCP, cell by cell: Septiembre's dollar cell is empty, the
#: currency not being covered.
VISA_ROWS = [
    ["[VIS] Agosto", "2026-07-26 → 2026-08-25", "—", "—", "completed", "in order"],
    ["VIS-202609", "2026-08-26 → 2026-09-25", "—", "", "completed", "in order"],
    ["VIS-202610", "2026-09-26 → 2026-10-25", "—", "-2.99", "draft", "not in order"],
]


def _engine(monkeypatch, accounts=ACCOUNTS, items=STATEMENTS, fail=None) -> FakeClient:
    """The fake engine every read of the browse and the statement's screen goes to.
    `fail`, an EngineError, is what `GET /statements` answers instead."""
    client = FakeClient()

    def get(path: str, *, auth: bool = True, params: dict | None = None):
        params = params or {}
        client.calls.append(("GET", path, params))
        if path == "/accounts":
            archived = params.get("include_archived") == "true"
            return whole([a for a in accounts if archived or not a["is_archived"]])
        if path == "/statements":
            if fail is not None:
                raise fail
            return whole([it for it in items if it["account_id"] == params["account_id"]])
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


def _paths(client: FakeClient) -> list[str]:
    return [path for _method, path, _params in client.calls]


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


# ---- the browse: one row per bank account, its name and its currencies ---------------


def test_the_browse_lists_one_row_per_bank_account_with_its_currencies_and_balances(
    monkeypatch,
):
    """Pane 2: every bank account once under its own name, its currencies as
    `PEN + USD` and a balance in each, never added together. Nothing about statements is
    read until `⏎`."""
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        seen["headers"] = list(screen._accts_list._headers)
        seen["cells"] = [[str(c) for c in r.cells] for r in screen._accts_list._rows]
        seen["shown"] = render_text(screen._accts_list._build(), width=120)

    run_app(scenario, size=(140, 50))
    assert seen["headers"] == ["  Account", "Currencies", "Balances"]
    # a name stands two cells in, after the gutter the open account's `▸` takes; the
    # first figures are padded to end in one place
    assert seen["cells"] == [
        ["  Visa BCP", "PEN + USD", "  -234.20 PEN   -30.98 USD"],
        ["  IBK Visa", "PEN + USD", "  -512.90 PEN   -24.99 USD"],
        ["  Sueldo Soles", "PEN", "12,450.00 PEN"],
        ["  BBVA Dólares", "USD", "   820.15 USD"],
    ]
    for word in ("Visa BCP", "PEN + USD", "-234.20 PEN"):
        assert word in seen["shown"]
    assert _statement_reads(client) == []


def test_the_browse_leaves_people_out_and_reads_the_accounts_currencies_as_sent():
    person = account_with_currencies(id="per-ana", name="Ana", is_person=True)
    nameless = account_with_currencies(id="acc-x", name=None, currencies=[])
    rows = browse_accounts([VISA, person, nameless, {"name": "no id"}])
    assert [(r.id, r.name, r.codes, r.code) for r in rows] == [
        ("acc-visa", "Visa BCP", ("PEN", "USD"), "VIS"),
        ("acc-x", "(unnamed)", (), None),
    ]
    assert rows[0].currencies == (("PEN", -23420), ("USD", -3098))


def test_an_archived_accounts_row_is_not_listed(monkeypatch):
    """The browse reads the live accounts alone, so an archived account is not
    offered until it is unarchived."""
    archived = account_with_currencies(VISA, is_archived=True)
    client = _engine(monkeypatch, accounts=[archived, IBK, SUELDO, DIGITAL])
    seen: dict = {}

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        seen["listed"] = [str(r.cells[0]) for r in screen._accts_list._rows]

    run_app(scenario, size=(140, 50))
    assert [name.strip() for name in seen["listed"]] == ["IBK Visa", "Sueldo Soles", "BBVA Dólares"]
    assert [params for _m, path, params in client.calls if path == "/accounts"][0] == {}


# ---- an account's statements: one read, a Diff per currency --------------------------


def test_an_account_with_a_code_lists_its_statements_from_one_read_by_account(monkeypatch):
    """Pane 3, Visa BCP: one `GET /statements?account_id=`, no other read, a
    row per statement with a Diff per currency, its status and its order."""
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, VISA)
        seen["panel"] = _panel(screen)
        seen["marked"] = _marked(screen)
        seen["shown"] = render_text(screen._batch_list._build(), width=120)

    run_app(scenario, size=(140, 50))
    assert _statement_reads(client) == [{"account_id": "acc-visa"}]
    assert "/holders" not in _paths(client)
    assert all("holder_id" not in params for _m, _p, params in client.calls)
    assert seen["panel"].caption == VISA_TITLE
    assert seen["panel"].headers == VISA_HEADERS
    assert seen["panel"].keys == ["vis-ago", "vis-sep", "vis-oct"]
    assert seen["panel"].cells == VISA_ROWS
    # a completed statement is dimmed
    assert seen["panel"].styles == ["dim", "dim", ""]
    assert seen["marked"] == ["▸ Visa BCP"]
    for word in ("Diff PEN", "Diff USD", "not in order"):
        assert word in seen["shown"]


def test_a_currency_the_statement_does_not_cover_shows_nothing(monkeypatch):
    """Question 2 B: VIS-202609 had no dollar line and no dollars owed, so it holds no
    dollar balances and its Diff USD is simply empty, not a row or a figure."""
    _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        seen["panel"] = _panel(await _open(pilot, app, VISA))

    run_app(scenario, size=(140, 50))
    september = seen["panel"].cells[1]
    assert (september[2], september[3]) == ("—", "")


def test_an_account_without_a_code_has_no_order_column_and_a_blank_balance_a_blank_diff(
    monkeypatch,
):
    """Pane 3, IBK Visa: no statement code, so the engine sends no order and the list has
    no Order column. Octubre's dollar balances are blank (question 3 B): its Diff USD is
    blank, not a figure."""
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, IBK)
        seen["panel"] = _panel(screen)

    run_app(scenario, size=(140, 50))
    assert _statement_reads(client) == [{"account_id": "acc-ibk"}]
    assert seen["panel"].caption == "Statements · IBK Visa · PEN + USD   ·   oldest → newest"
    assert seen["panel"].headers == ["Name", "Period", "Diff PEN", "Diff USD", "Status"]
    assert seen["panel"].cells == [
        ["Agosto 2026", "2026-07-26 → 2026-08-25", "—", "—", "completed"],
        ["Septiembre 2026", "2026-08-26 → 2026-09-25", "—", "", "completed"],
        ["Octubre 2026", "2026-09-26 → 2026-10-25", "—", "", "draft"],
    ]


def test_an_account_of_one_currency_has_one_diff_column(monkeypatch):
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        seen["panel"] = _panel(await _open(pilot, app, SUELDO))

    run_app(scenario, size=(140, 50))
    assert _statement_reads(client) == [{"account_id": "acc-sueldo"}]
    assert seen["panel"].caption == "Statements · Sueldo Soles · PEN   ·   oldest → newest"
    assert seen["panel"].headers == ["Name", "Period", "Diff", "Status"]
    assert seen["panel"].cells == [["Octubre 2026", "2026-09-26 → 2026-10-25", "—", "draft"]]


def test_the_headers_follow_the_accounts_currencies_and_code():
    assert statement_headers(("PEN", "USD"), with_order=True) == (
        VISA_HEADERS,
        {2, 3},
    )
    assert statement_headers(("USD",), with_order=False) == (
        ["Name", "Period", "Diff", "Status"],
        {2},
    )
    assert statement_headers((), with_order=False) == (["Name", "Period", "Status"], set())


# ---- opening a statement ------------------------------------------------------------


def test_enter_on_a_statement_opens_the_whole_statement(monkeypatch):
    _engine(monkeypatch)
    opened: list = []

    async def scenario(pilot, app):
        screen = await _open(pilot, app, VISA)
        for index in (0, 2):
            screen._batch_list.set_cursor(index)
            await pilot.press("enter")
            await wait_for(pilot, lambda: isinstance(app.screen, ReconciliationDetailScreen))
            record = app.screen._record
            code = app.screen._statement_code
            opened.append((app.screen._id, record["account_id"], record["balances"], code))
            await pilot.press("escape")
            await wait_for(pilot, lambda: app.screen is screen and screen._mode == "batches")

    run_app(scenario, size=(140, 50))
    assert opened == [
        (item["id"], "acc-visa", item["balances"], "VIS")  # the account's own statement code
        for item in (VISA_STATEMENTS[i] for i in (0, 2))
    ]


def test_a_blank_balance_reads_as_a_dim_dash_on_the_statements_head(monkeypatch):
    """Question 3 B: a blank beginning balance is a dim `—`, as an empty ending balance
    reads, and its difference stays blank."""
    _engine(monkeypatch)
    statement = IBK_STATEMENTS[2]
    seen: dict = {}

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(statement)
        await app.push_screen(screen)
        head = screen.query_one("#rhead", Static).visual
        seen["head"] = str(head)
        seen["dim"] = [span.style for span in head.spans if "—" in str(head)[span.start : span.end]]

    run_app(scenario, size=(140, 50))
    lines = seen["head"].splitlines()
    assert lines[0].endswith("status draft")
    assert [ln.split() for ln in lines[2:]] == [["PEN", "0.00", "0.00", "—"], ["USD", "—", "—"]]
    assert seen["dim"] and all(style.dim for style in seen["dim"])


def test_coming_back_and_r_read_the_account_again_and_nothing_else(monkeypatch):
    client = _engine(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(pilot, app, VISA)
        screen._batch_list.set_cursor(2)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ReconciliationDetailScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: len(_statement_reads(client)) == 2)
        await wait_for(pilot, lambda: screen._mode == "batches")
        assert screen._batch_list.cursor_key == "vis-oct"
        assert _panel(screen).cells == VISA_ROWS
        await pilot.press("r")
        await wait_for(pilot, lambda: len(_statement_reads(client)) == 3)
        await wait_for(pilot, lambda: screen._mode == "batches")

    run_app(scenario, size=(140, 50))
    assert _statement_reads(client) == [{"account_id": "acc-visa"}] * 3


def test_the_footer_and_u_stay_as_today(monkeypatch):
    _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        await _open(pilot, app, VISA)
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
    """`u` swaps the panel to the open account's rows in no batch; `esc` swaps the
    statements back, their columns and title with them."""
    client = _engine(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, VISA)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and not screen._unfiled_busy)
        await pilot.press("escape")
        await wait_for(pilot, lambda: screen._mode == "batches")
        seen["panel"] = _panel(screen)

    run_app(scenario, size=(140, 50))
    lines = [params for _m, path, params in client.calls if path == "/bank-lines"]
    assert [params.get("account_id") for params in lines] == [VISA["id"]]
    assert seen["panel"].caption == VISA_TITLE
    assert seen["panel"].headers == VISA_HEADERS
    assert seen["panel"].cells == VISA_ROWS
    assert _statement_reads(client) == [{"account_id": "acc-visa"}]


# ---- status, each currency's difference and order, row by row -------------------------


@pytest.mark.parametrize("status, word", [(2, "completed"), (1, "draft")])
def test_a_statements_status_is_its_own(status, word):
    """One status for the whole statement (contract: "Statements"); a completed one dims."""
    [(key, cells, style)] = statement_rows(
        [{**VISA_STATEMENTS[2], "status": status}], ("PEN", "USD"), with_order=True
    )
    assert (key, cells[4]) == ("vis-oct", word)
    assert style == ("dim" if status == 2 else "")


def test_each_diff_is_its_own_currencys_entry_whatever_the_order_of_balances():
    """Each column reads its own currency's entry by `currency_code`, so a Diff never
    shows another currency's figure."""
    swapped = {**VISA_STATEMENTS[2], "balances": list(reversed(VISA_STATEMENTS[2]["balances"]))}
    [(_key, cells, _style)] = statement_rows([swapped], ("PEN", "USD"), with_order=True)
    assert [str(cell) for cell in cells[2:4]] == ["—", "-2.99"]


def test_a_difference_not_checked_yet_is_blank():
    """`difference_cents` is null until the ending balance is entered, shown blank
    (contract: "Statements", "`difference_cents` — the add-up check")."""
    diffs = {"PEN": 0, "USD": None}
    open_usd = _statement("nov", "acc-visa", "Noviembre 2026", OCT, diffs, status=1)
    [(_key, cells, _style)] = statement_rows([open_usd], ("PEN", "USD"), with_order=False)
    assert [str(cell) for cell in cells[2:5]] == ["—", "", "draft"]


@pytest.mark.parametrize(
    "unplaced, shared, word",
    [(0, 0, "in order"), (2, 0, "not in order"), (0, 1, "not in order"), (2, 1, "not in order")],
)
def test_the_order_is_the_engines_two_counts(unplaced, shared, word):
    item = {**VISA_STATEMENTS[2], "unplaced_count": unplaced, "shared_place_count": shared}
    assert str(order_cell(item)) == word


def test_no_counts_show_no_order():
    """On an account with no code the engine reads null counts: there is no order."""
    assert order_cell(IBK_STATEMENTS[0]) == ""


# ---- a refused read ----------------------------------------------------------------


def test_a_refused_read_leaves_the_panel_closed_with_the_engines_words(monkeypatch):
    err = EngineError("VALIDATION_ERROR", "Validation failed.", {"account_id": "Bad."}, 422, {})
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
    assert _statement_reads(client) == [{"account_id": "acc-visa"}]
    assert notes == [("Failed", format_error(err))]


# ---- c, u and d on a statement opened from an account --------------------------------


def _writing_engine(monkeypatch) -> FakeClient:
    """`_engine` over its own copy of the statements, which a write changes: the
    statement screen's write answers in the engine's shape (`FAKE_ANSWERS`), the record
    its path names as the test serves it, and that statement reads afterwards with the
    answer's status, a deleted one no longer listed."""
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


#: Each status key on a statement's screen, opened from Visa BCP on the row at `row`: the
#: statement it opens, the one write it sends, its toast, the header's status after it
#: (`None`: the screen closes), and the browse's rows after it. Octubre is a draft,
#: Agosto completed (`VISA_ROWS`); `c` is sent from Sueldo Soles, whose Octubre is a draft with
#: every balance and no statement code to wait for; a completed statement's row is dimmed.
STATUS_KEYS = {
    "c": (
        0,
        "sue-oct",
        ("POST", "/statements/sue-oct/complete"),
        "Statement completed.",
        "completed",
        [["Octubre 2026", "2026-09-26 → 2026-10-25", "—", "completed"]],
        ["dim"],
    ),
    "u": (
        0,
        "vis-ago",
        ("POST", "/statements/vis-ago/revert"),
        "Statement reverted to draft.",
        "draft",
        [[*VISA_ROWS[0][:4], "draft", "in order"], *VISA_ROWS[1:]],
        ["", "dim", ""],
    ),
    "d": (
        2,
        "vis-oct",
        ("DELETE", "/statements/vis-oct"),
        "Statement deleted.",
        None,
        VISA_ROWS[:2],
        ["dim", "dim"],
    ),
}


@pytest.mark.parametrize("key", list(STATUS_KEYS))
def test_c_u_and_d_send_one_write_and_the_list_shows_it(monkeypatch, key):
    """`c`, `u` and `d` on a statement opened from an account, each confirmed with `y`,
    send one write on the statement the screen shows. The statement's header shows its
    new status, and back on the browse the statement's row, read again, shows it (a
    deleted statement's row gone)."""
    row, opened, write, toast, status, rows, styles = STATUS_KEYS[key]
    account = SUELDO if key == "c" else VISA  # a draft of an account with a code waits for its PDF
    client = _writing_engine(monkeypatch)
    notes: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notes.append(message)
    )
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, account)
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
        assert seen["head"].splitlines()[0].endswith(f"status {status}")
    assert seen["panel"].cells == rows
    assert seen["panel"].styles == styles


@pytest.mark.parametrize("key", list(STATUS_KEYS))
def test_a_status_key_is_one_request_under_one_key(configured, monkeypatch, key):
    """Through the shared write path and the real HTTP client, each key's write on a
    statement opened from an account is one request carrying one `X-Idempotency-Key`."""
    _row, opened, (method, path), toast, _status, _rows, _styles = STATUS_KEYS[key]
    statement = next(item for item in STATEMENTS if item["id"] == opened)
    record = statement
    answers = {
        "c": statement_complete_answer({**statement, "status": 2}),
        "u": statement_revert_answer({**statement, "status": 1}),
        "d": statement_delete_answer(statement),
    }
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map",
        lambda: {VISA["id"]: VISA["name"]},
    )
    notes: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notes.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(record))
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


# ---- the screen at 80 columns, as panes 2 and 3 of the mockup draw it ---------------


def _screen_lines(app) -> list[str]:
    """The screen as the user reads it: the text of each terminal line, rstripped."""
    strips = app.screen._compositor.render_strips()
    return ["".join(segment.text for segment in strip).rstrip() for strip in strips]


#: Pane 3's three Visa BCP statements: Septiembre had no dollar line and no dollars owed,
#: so it covers soles alone; all three are in order.
PANE_3_VISA = [
    _statement("p-ago", "acc-visa", "[VIS] Agosto", AGO, {"PEN": 0, "USD": 0}, status=2),
    _statement("p-sep", "acc-visa", "VIS-202609", SEP, {"PEN": 0}, status=2),
    _statement("p-oct", "acc-visa", "VIS-202610", OCT, {"PEN": 0, "USD": 0}, status=2),
]


def _at_80(
    monkeypatch, account: dict, items: list[dict], *, open_panel: bool = True, width: int = 80
) -> list[str]:
    _engine(monkeypatch, items=items)
    seen: list[str] = []

    async def scenario(pilot, app):
        if open_panel:
            await _open(pilot, app, account)
        else:
            await app.push_screen(ReconciliationsScreen())
            await wait_for_list(pilot, app)
        await pilot.pause()
        seen.extend(_screen_lines(app))

    run_app(scenario, size=(width, 30))
    return seen


def _row(lines: list[str], name: str) -> str:
    """The account's row: not the crumb or the panel's title, which name it too."""
    return next(line for line in lines if name in line and "◈" not in line and "·" not in line)


FIGURE = re.compile(r"-?[\d,]+\.\d\d (?:PEN|USD)")


def test_the_browse_at_80_columns_keeps_each_accounts_first_figure_in_one_place(monkeypatch):
    """Pane 2: every account's first figure ends in one column (`-234.20 PEN`,
    `12,450.00 PEN`, `820.15 USD` under each other) and the second follows it three cells
    on; the names stand in one column, the header over them."""
    lines = _at_80(monkeypatch, VISA, STATEMENTS, open_panel=False)
    rows = {name: _row(lines, name) for name in ("Visa BCP", "IBK Visa", "Sueldo", "BBVA")}
    assert len({line.index(name) for name, line in rows.items()}) == 1
    firsts = {name: FIGURE.search(line) for name, line in rows.items()}
    assert len({match.end() for match in firsts.values()}) == 1
    visa = rows["Visa BCP"]
    assert re.search(r"PEN {3}-30\.98 USD$", visa)
    assert "…" not in "".join(lines)
    header = _row(lines, "Currencies")
    assert header.index("Account") == visa.index("Visa BCP")
    assert "  Statements — pick an account" in lines
    assert visa.index("Visa BCP") == 4


def test_the_open_accounts_marker_stands_in_a_gutter_and_no_name_moves(monkeypatch):
    """Pane 2 and 3: `▸` before the open account's name, names aligned with the ones
    without it."""
    closed = _at_80(monkeypatch, VISA, STATEMENTS, open_panel=False)
    opened = _at_80(monkeypatch, VISA, STATEMENTS)
    for name in ("Visa BCP", "IBK Visa", "Sueldo", "BBVA"):
        assert _row(opened, name).index(name) == _row(closed, name).index(name)
    visa = _row(opened, "Visa BCP")
    assert visa[visa.index("Visa BCP") - 2 : visa.index("Visa BCP")] == "▸ "
    assert visa.index("▸") == 2
    assert not any("▸" in _row(opened, name) for name in ("IBK Visa", "Sueldo", "BBVA"))


def test_visa_bcps_statements_at_80_columns_are_pane_3_whole(monkeypatch):
    """Pane 3, Visa BCP: every cell whole at 80 columns, the Diff headers telling PEN
    from USD, the statement that does not cover dollars empty under Diff USD."""
    lines = _at_80(monkeypatch, VISA, PANE_3_VISA)
    assert "  Statements — pick an account" in lines
    assert "  Statements · Visa BCP · PEN + USD · VIS   ·   oldest → newest" in lines
    ours = ("  Name", "  [VIS]", "  VIS-")
    assert [line for line in lines if line.startswith(ours)] == [
        "  Name          Period                   Diff PEN  Diff USD  Status     Order",
        "  [VIS] Agosto  2026-07-26 → 2026-08-25         —         —  completed  in order",
        "  VIS-202609    2026-08-26 → 2026-09-25         —            completed  in order",
        "  VIS-202610    2026-09-26 → 2026-10-25         —         —  completed  in order",
    ]
    assert "  ▸ Visa BCP      PEN + USD     -234.20 PEN   -30.98 USD" in lines
    assert "    IBK Visa      PEN + USD     -512.90 PEN   -24.99 USD" in lines
    assert "…" not in "".join(lines)


def test_ibk_visas_statements_at_80_columns_are_pane_3_whole(monkeypatch):
    """Pane 3, IBK Visa: no statement code, so no Order column; Octubre's blank dollar
    balances leave its Diff USD empty."""
    lines = _at_80(monkeypatch, IBK, IBK_STATEMENTS)
    assert "  Statements · IBK Visa · PEN + USD   ·   oldest → newest" in lines
    ours = ("  Name", "  Agosto", "  Sept", "  Octubre")
    assert [line for line in lines if line.startswith(ours)] == [
        "  Name             Period                   Diff PEN  Diff USD  Status",
        "  Agosto 2026      2026-07-26 → 2026-08-25         —         —  completed",
        "  Septiembre 2026  2026-08-26 → 2026-09-25         —            completed",
        "  Octubre 2026     2026-09-26 → 2026-10-25         —            draft",
    ]
    assert "…" not in "".join(lines)


def test_a_list_keeps_three_cells_between_columns_unless_it_asks_for_fewer():
    """The shared table's gap is three; the browse's lists ask for two, and no other
    list changes."""
    from expense.tui.widgets.cursor_list import list_table

    def gap(width_gap: int | None) -> int:
        table = list_table(["A", "B"], [("k", ["x", "y"])], gap=width_gap, flex={1: 1}, edge=False)
        row = render_text(table, width=20).splitlines()[2]
        return row.index("y") - row.index("x") - 1

    assert (gap(None), gap(2), gap(1)) == (3, 2, 1)


def test_a_not_in_order_row_shows_whole_when_the_terminal_is_wide_enough(monkeypatch):
    """`not in order` is a whole word in the Order column at 90 columns."""
    stray = _statement("p-nov", "acc-visa", "VIS-202611", OCT, {"PEN": 0, "USD": 0}, status=2)
    stray["unplaced_count"] = 2
    lines = _at_80(monkeypatch, VISA, [*PANE_3_VISA, stray], width=90)
    row = next(line for line in lines if line.startswith("  VIS-202611"))
    assert row.endswith("completed  not in order")
