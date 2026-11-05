"""Reconciliation working-screen tests — the bank-line checklist + assign/complete.

Every list reads `GET /bank-lines`: a purchase split into parts is one row with
its total, and a tick is one `PUT` of `statement_id` on one of its parts
(contract: GET /v1/bank-lines)
(contract: PUT /v1/transactions/{transaction_id}, "Statement assignment"). Complete,
revert and delete act on the whole statement under `/statements/{id}`, and the
ending balance is saved in its `balances` (contract: PUT /v1/statements/{statement_id})."""

import json
import threading

import httpx
import pytest
import respx
from textual.widgets import Static

from expense.errors import EngineError, format_error
from expense.formatting import bank_line_columns
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.reconciliations import (
    ReconciliationDetailScreen,
    balance_of,
    balances_body,
    line_rows,
)
from expense.tui.widgets.checklist import CheckList
from tests.unit.helpers import (
    ARCHIVED_FIELD_WORDS,
    ARCHIVED_PUT_WORDS,
    ENGINE_URL,
    archived_refusal,
    bank_line_row,
    complete_refusal,
    cursor_page,
    edit_limits,
    error_body,
    error_response,
    import_part,
    put_answer,
    refusal_text,
    render_text,
    run_app,
    shown,
    statement_complete_answer,
    statement_put_answer,
    statement_record,
    wait_for,
)

pytestmark = pytest.mark.usefixtures("no_flagged_lines")


def _part(tx_id: str, cents: int, *, line: str, day: str, title: str, recon=None) -> dict:
    return {
        **import_part(tx_id, cents, account_id="acc1", line=line, day=day, title=title),
        "statement_id": recon,
        "category_id": "c1",
        "hashtag_ids": ["h1"],
        "description": "a note the list never shows",
    }


#: The batch's one line, ticked: a purchase never split.
NETFLIX = bank_line_row(
    "l1",
    [_part("t1", -4490, line="l1", day="2026-04-14", title="NETFLIX.COM", recon="r1")],
    net_cents=-4490,
    operation_code="48213907",
    account_id="acc1",
)
#: A purchase split 60 + 40: one row of -100.00, its title alone.
FARMACIA = bank_line_row(
    "l2",
    [
        _part("t2a", -6000, line="l2", day="2026-04-11", title="FARMACIA"),
        _part("t2b", -4000, line="l2", day="2026-04-11", title="FARMACIA"),
    ],
    net_cents=-10000,
    operation_code="48201764",
    account_id="acc1",
)
#: A line typed in by hand: no operation code.
UBER = bank_line_row(
    "l3",
    [_part("t3", -4200, line="l3", day="2026-04-12", title="UBER *TRIP")],
    net_cents=-4200,
    account_id="acc1",
)
ASSIGNED = [NETFLIX]
AVAILABLE = [UBER, FARMACIA]  # the engine's order: newest first


def test_a_lines_columns_are_the_banks_own():
    """Date and title come off the parts, the amount is the engine's signed
    `net_cents` — never a sum of the parts' magnitudes."""
    assert bank_line_columns(FARMACIA) == ("2026-04-11", "FARMACIA", "48201764", -10000)
    assert bank_line_columns(UBER) == ("2026-04-12", "UBER *TRIP", None, -4200)


def test_line_rows_lists_a_split_purchase_once_and_ticks_by_one_part():
    rows, checked, part_of = line_rows(ASSIGNED, [*AVAILABLE, NETFLIX])
    assert [r[0] for r in rows] == ["l1", "l3", "l2"]  # the batch first; l1 once
    assert checked == ["l1"]
    assert part_of == {"l1": "t1", "l3": "t3", "l2": "t2a"}
    # a currency and a number on the paper, 1, 2, 3 with no gaps, and not apart
    assert rows[2] == ("l2", "2026-04-11", "FARMACIA", "48201764", -10000, "PEN", 3, False)


def test_an_opening_balance_is_listed_apart_and_takes_no_number():
    """It holds no place on the paper (contract: "Statements", "A statement's order"),
    so it comes after the numbered rows, whichever place the read gave it, and
    the numbers go on 1, 2, 3 around it."""
    opening = bank_line_row(
        "op",
        [_part("t0", -120410, line="op", day="2026-04-01", title="Opening balance")],
        net_cents=-120410,
        account_id="acc1",
        is_opening_balance=True,
    )
    rows, _, _ = line_rows([opening, NETFLIX, UBER], [])
    assert [(r[0], r[5], r[6], r[7]) for r in rows] == [
        ("l1", "PEN", 1, False),
        ("l3", "PEN", 2, False),
        ("op", "PEN", None, True),
    ]


def _rendered(checklist: CheckList, width: int = 100) -> str:
    return render_text(checklist._build(), width=width)


def test_a_row_is_one_line_of_bank_columns():
    """Date · title · operation · currency · amount, in that order, one line per row;
    a row without an operation code shows `—`; no category, hashtag, note or part
    count, and nothing marks a row as split."""
    rows, checked, _ = line_rows(ASSIGNED, AVAILABLE)
    text = _rendered(CheckList(rows, checked))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = lines[0]
    names = ("Date", "Title", "Operation", "Cur", "Amount")
    assert header.split() == list(names)
    assert [header.index(w) for w in names] == sorted(header.index(w) for w in names)
    body = [ln for ln in lines if "[" in ln]
    assert len(body) == 3  # one physical line per row
    farmacia = next(ln for ln in body if "FARMACIA" in ln)
    assert farmacia.split() == ["[", "]", "2026-04-11", "FARMACIA", "48201764", "PEN", "-100.00"]
    uber = next(ln for ln in body if "UBER" in ln)
    assert uber.split()[-3:] == ["—", "PEN", "-42.00"]
    assert "[x]" in next(ln for ln in body if "NETFLIX.COM" in ln)
    for hidden in ("Vivienda", "#", "note", "-60.00", "-40.00", "part"):
        assert hidden not in "\n".join(body), hidden


def test_a_completed_list_has_no_tick_box():
    rows, checked, _ = line_rows(ASSIGNED, [])
    text = _rendered(CheckList(rows, checked, read_only=True))
    assert "[" not in text
    header = next(ln for ln in text.splitlines() if ln.strip())
    assert header.split() == ["Date", "Title", "Operation", "Cur", "Amount"]
    assert "2026-04-14" in text and "48213907" in text and "-44.90" in text


def test_checklist_toggle_emits_and_tracks():
    rows = [("l1", "2026-04-03", "Alquiler", "001", -250000)]
    cl = CheckList(rows, checked=[])
    assert cl.cursor_key == "l1" and cl.checked == set()
    # simulate a toggle (no event loop): action_toggle posts a message + flips state
    cl.action_toggle()
    assert cl.checked == {"l1"}
    cl.action_toggle()
    assert cl.checked == set()


def test_checklist_lands_on_the_row_it_is_given():
    rows = [(f"l{i}", "2026-04-03", f"row {i}", None, -100) for i in range(5)]
    assert CheckList(rows, land_on="l3").cursor_key == "l3"
    assert CheckList(rows, land_on="gone").cursor_key == "l0"


def test_checklist_colors_come_from_palette():
    """Amounts + checked marks use the injected palette, never literal colors (4.2)."""
    from expense.tui.theme import PALETTE

    rows = [
        ("l1", "2026-04-03", "Alquiler", None, -250000),
        ("l2", "2026-04-09", "Refund", "77", 5620),
    ]
    # app-less, PALETTE palette: the listing is a blank line, then the table in its indent
    table = CheckList(rows, checked=["l1"])._listing(100).renderables[1].renderable
    marks, ops, amounts = table.columns[0]._cells, table.columns[3]._cells, table.columns[5]._cells
    assert marks[0].style == PALETTE.success and marks[1].style == "dim"  # [x] vs [ ]
    assert ops[0].style == "dim"  # the — of a line with no operation code
    assert amounts[0].style == PALETTE.error  # -2,500.00
    assert amounts[1].style == PALETTE.success  # +56.20


def test_status_span_maps_completed_and_draft():
    from expense.tui.screens.reconciliations import _status_span
    from expense.tui.theme import Palette

    palette = Palette("#0f0", "#f00", "#ff0")
    assert _status_span("completed", palette) == ("completed", palette.success)
    assert _status_span("draft", palette) == ("draft", palette.warning)


def _statement(**balance) -> dict:
    """Statement r1 as `GET /statements/{id}` reads it: April 2026, a draft of
    acc1, its soles balances a begin of 9,580.00, an end of 9,460.00 and a
    difference of -35.00, `balance` spread over them."""
    soles = {
        "currency_code": "PEN",
        "beginning_balance_cents": 958000,
        "ending_balance_cents": 946000,
        "difference_cents": -3500,
    }
    return statement_record({"id": "r1", "balances": [{**soles, **balance}]})


#: The statement as the engine holds it, and as the browse opens it.
STATEMENT = _statement()
DRAFT = STATEMENT
#: The statement's writes: the ending balance's save, complete, revert and delete.
STATEMENT_PATH = "/statements/r1"
COMPLETE_PATH = "/statements/r1/complete"
REVERT_PATH = "/statements/r1/revert"

#: The dollar balances of statement r1, on an account holding soles and dollars: none of
#: the soles figures.
DOLLARS = {
    "currency_code": "USD",
    "beginning_balance_cents": 5000,
    "ending_balance_cents": 7000,
    "difference_cents": 120,
}
#: Statement r1 covering both currencies: the dollars first, then the soles as `STATEMENT`'s.
CARD = statement_record({"id": "r1", "balances": [DOLLARS, *STATEMENT["balances"]]})


def _patch(monkeypatch):
    """Screen-specific patches; the client/config seams come from fake_client.
    Returns the log of `GET /statements/{id}` reads (the header's re-read), by id."""
    statement_reads: list = []

    def fake_fetch(cfg, **k):
        if k.get("reconciliation") == "r1":
            return cursor_page(ASSIGNED)
        if k.get("account") == "acc1" and k.get("unreconciled"):
            return cursor_page(AVAILABLE)
        return cursor_page([])

    def fake_statement(cfg, statement_id, **k):
        statement_reads.append(statement_id)
        return dict(STATEMENT)

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fake_fetch)
    monkeypatch.setattr("expense.reads.fetch_statement", fake_statement)
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc1": "BCP"}
    )
    return statement_reads


def _head_row(screen, code: str) -> list[str]:
    """The words of the head's line for `code`, a currency the statement covers."""
    head = shown(screen.query_one("#rhead", Static))
    return next(ln.split() for ln in head.splitlines() if ln.split()[:1] == [code])


def _end(screen, code: str = "PEN"):
    """The ending balance the screen holds for `code`."""
    return balance_of(screen._record, code)["ending_balance_cents"]


async def _wait_list(screen, pilot):
    await wait_for(pilot, lambda: screen._list is not None)


def test_available_read_takes_the_periods_days_byte_for_byte(fake_client, monkeypatch):
    """The tick-list's in-range read asks for the account's lines in no statement,
    with the period's own days in the engine's day filters, unconverted: a bare
    `date_to` is the whole last day (contract: GET /v1/bank-lines). The statement's
    own lines are read on the opened account, any day
    (contract: GET /v1/bank-lines, "Filters")."""
    _patch(monkeypatch)
    calls: list = []
    from expense import reads

    fake = reads.fetch_bank_lines  # _patch's fake

    def spy(cfg, **k):
        assert "offset" not in k
        calls.append(k)
        return fake(cfg, **k)

    monkeypatch.setattr("expense.reads.fetch_bank_lines", spy)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        in_range = [k for k in calls if k.get("unreconciled")]
        assert len(in_range) == 1
        assert in_range[0]["account"] == "acc1"
        assert in_range[0]["date_from"] == "2026-04-01"
        assert in_range[0]["date_to"] == "2026-04-30"
        batch = [k for k in calls if k.get("reconciliation") == "r1"]
        assert len(batch) == 1 and batch[0]["account"] == "acc1"
        assert "date_from" not in batch[0] and "date_to" not in batch[0]

    run_app(scenario)


def test_header_shows_difference_not_source(fake_client, monkeypatch):
    """The header's old "(chained)"/"(manual)" tag answered a question the
    engine no longer has two answers to; it carries the add-up check instead."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        head = shown(screen.query_one("#rhead", Static))
        assert "diff" in head and "-35.00" in head
        assert "chained" not in head and "manual" not in head

    run_app(scenario)


def test_draft_lists_assigned_checked_plus_available(fake_client, monkeypatch):
    """The batch's lines first, ticked, then the account's lines in no statement;
    the split purchase is one row with its total."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        cl = screen._list
        assert [r[0] for r in cl._rows] == ["l1", "l3", "l2"]
        assert cl.checked == {"l1"}
        assert not cl._read_only
        assert cl._rows[2][1:5] == ("2026-04-11", "FARMACIA", "48201764", -10000)

    run_app(scenario)


def test_tick_puts_statement_id_on_one_part_then_reads_again(fake_client, monkeypatch):
    """`space` on a split purchase: one `PUT` of `statement_id` on one of its parts,
    then the statement and its lines are read again, and the cursor stays on that row."""
    statement_reads = _patch(monkeypatch)
    ticked = {**FARMACIA, "parts": [{**p, "statement_id": "r1"} for p in FARMACIA["parts"]]}

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        # the engine after the PUT: FARMACIA is in the batch, listed among its lines
        monkeypatch.setattr(
            "expense.reads.fetch_bank_lines",
            lambda cfg, **k: cursor_page([NETFLIX, ticked] if k.get("reconciliation") else [UBER]),
        )
        first._cursor = 2
        await pilot.press("space")
        await wait_for(pilot, lambda: fake_client.puts)
        await wait_for(pilot, lambda: screen._list is not first)
        assert fake_client.puts == [("/transactions/t2a", {"statement_id": "r1"})]
        assert statement_reads == ["r1"]  # the header's figures, read again
        assert [r[0] for r in screen._list._rows] == ["l1", "l2", "l3"]  # ticked rows first
        assert screen._list.checked == {"l1", "l2"}
        assert screen._list.cursor_key == "l2"  # the cursor stays on the purchase

    run_app(scenario)


def test_untick_sends_null_on_one_part_then_reads_again(fake_client, monkeypatch):
    statement_reads = _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        await pilot.press("space")  # the cursor starts on NETFLIX, ticked
        await wait_for(pilot, lambda: screen._list is not first)
        assert fake_client.puts == [("/transactions/t1", {"statement_id": None})]
        assert statement_reads == ["r1"]
        assert screen._list.cursor_key == "l1"

    run_app(scenario)


def test_a_tick_carries_one_idempotency_key(configured, monkeypatch):
    """A tick is one logical write: one `PUT`, one `X-Idempotency-Key`, through
    the shared write path and the real HTTP client."""
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc1": "BCP"}
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        first._cursor = 2
        await pilot.press("space")
        await wait_for(pilot, lambda: screen._list is not first)

    with respx.mock() as mock:
        lines = mock.get(f"{ENGINE_URL}/v1/bank-lines").mock(
            side_effect=lambda request: httpx.Response(
                200,
                json=cursor_page(ASSIGNED if "statement_id" in request.url.params else AVAILABLE),
            )
        )
        read = mock.get(f"{ENGINE_URL}/v1/statements/r1").mock(httpx.Response(200, json=STATEMENT))
        ticked = [{**p, "statement_id": "r1", "version": 2} for p in FARMACIA["parts"]]
        answer = put_answer(ticked[0], ticked)
        route = mock.put(f"{ENGINE_URL}/v1/transactions/t2a").mock(httpx.Response(200, json=answer))
        run_app(scenario)
    assert route.call_count == 1
    assert read.call_count == 1  # the statement, read again by its id after the tick
    request = route.calls.last.request
    assert request.headers["X-Idempotency-Key"]
    assert request.read() == b'{"statement_id":"r1"}'
    sent = [dict(call.request.url.params) for call in lines.calls]
    assert {
        "statement_id": "r1",
        "account_id": "acc1",
        "sort": "statement",
        "limit": "200",
    } in sent
    assert {
        "account_id": "acc1",
        "unreconciled": "true",
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
        "sort": "date_asc",
        "limit": "200",
    } in sent


def test_rapid_toggles_serialize_puts_in_order(fake_client, monkeypatch):
    """Rapid `space` toggles queue their PUTs one at a time, in order."""
    import threading
    import time

    _patch(monkeypatch)
    active = 0
    max_active = 0
    lock = threading.Lock()
    real_put = fake_client.put

    def slow_put(path, json_body=None):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.08)  # wide enough that overlapping PUTs would be caught
        with lock:
            active -= 1
        return real_put(path, json_body=json_body)

    fake_client.put = slow_put

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        first._cursor = 0
        first.action_toggle()  # l1 → out of the batch
        first._cursor = 2
        first.action_toggle()  # l2 → into the batch
        await wait_for(pilot, lambda: len(fake_client.puts) == 2)
        await wait_for(pilot, lambda: screen._list is not first)  # the re-read is in

    run_app(scenario)
    assert max_active == 1  # serialized: never two PUTs in flight
    assert fake_client.puts == [
        ("/transactions/t1", {"statement_id": None}),
        ("/transactions/t2a", {"statement_id": "r1"}),
    ]


def test_toggle_error_drops_queued_intents_and_resyncs(fake_client, monkeypatch):
    """A failed toggle clears the queue and resyncs instead of applying stale intents (3.2)."""
    import threading

    from expense.errors import EngineError as _EngineError

    _patch(monkeypatch)
    fake_client.errors["PUT"] = _EngineError("CONFLICT", "Transaction is locked.", None, 409, {})
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notices.append(message)
    )
    # Each toggle reaches the screen as its own message, so the first PUT can
    # fail before the second toggle is even queued — and then there is nothing
    # queued to drop. Hold the first PUT until the second sits in the queue.
    release = threading.Event()
    failing_put = fake_client.put

    def held_put(path, json_body=None):
        release.wait(timeout=5)
        return failing_put(path, json_body=json_body)

    fake_client.put = held_put

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        first._cursor = 0
        first.action_toggle()
        first._cursor = 1
        first.action_toggle()  # queued behind the failing PUT
        await wait_for(pilot, lambda: len(screen._write_queue or ()) == 1)
        release.set()
        await wait_for(pilot, lambda: notices)
        await wait_for(pilot, lambda: screen._list is not first)  # the resync is in
        await pilot.pause()  # let the queue drain settle, then assert a non-event
        assert not screen._write_queue  # stale intent dropped, not sent
        assert len(fake_client.puts) == 1

    run_app(scenario)


@pytest.mark.parametrize(
    "error",
    [
        # The statement's refusals of an assignment, on `statement_id`
        # (contract: "Statements", "Assigning transactions").
        EngineError(
            "VALIDATION_ERROR",
            "Cannot assign transactions to a completed statement.",
            {"statement_id": "Cannot assign transactions to a completed statement."},
            422,
            {},
            reasons={"statement_id": "RECONCILIATION_COMPLETED"},
        ),
        EngineError(
            "VALIDATION_ERROR",
            "Transaction t2b, another part of the same bank line, refuses this change.",
            {
                "statement_id": "The statement holds no balance of the transaction's account: "
                "it is another account's."
            },
            422,
            {},
            reasons={"statement_id": "ACCOUNT_MISMATCH"},
        ),
    ],
)
def test_a_refused_tick_shows_the_engines_words_and_reads_again(fake_client, monkeypatch, error):
    """A refusal is shown in the engine's words under `Couldn't update`, and the
    list is read again from the engine, the cursor back on row 1."""
    _patch(monkeypatch)
    fake_client.errors["PUT"] = error
    notices: list = []

    def note(self, message, title="", **kw):
        notices.append((title, message))

    monkeypatch.setattr(ReconciliationDetailScreen, "notify", note)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        first._cursor = 2
        await pilot.press("space")
        await wait_for(pilot, lambda: notices)
        await wait_for(pilot, lambda: screen._list is not first)
        assert notices[0][0] == "Couldn't update"
        assert error.message in notices[0][1]
        assert screen._list.checked == {"l1"}  # the engine's state, not the tick
        assert screen._list.cursor_key == "l1"

    run_app(scenario)


def test_a_tick_at_the_same_moment_as_another_write_says_to_press_r(fake_client, monkeypatch):
    """`CONCURRENT_CHANGE` on a tick: the engine's words, then the list's own line,
    `press r, then try again.`, and the statement is read again."""
    statement_reads = _patch(monkeypatch)
    fake_client.errors["PUT"] = EngineError(
        "CONFLICT",
        "Engine words for CONCURRENT_CHANGE.",
        {"statement_id": "Engine field words."},
        409,
        {},
        {"statement_id": "CONCURRENT_CHANGE"},
    )
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen,
        "notify",
        lambda self, message, title="", **kw: notices.append((title, message)),
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("space")
        await wait_for(pilot, lambda: notices)
        await wait_for(pilot, lambda: statement_reads)

    run_app(scenario)
    assert statement_reads == ["r1"]
    assert notices == [
        (
            "Couldn't update",
            "CONFLICT — Engine words for CONCURRENT_CHANGE.\n"
            "  statement_id: Engine field words.\n\n"
            "It changed at the same moment: press r, then try again.",
        )
    ]


def test_a_tick_on_an_archived_account_shows_the_engine_words_alone(fake_client, monkeypatch):
    """The batch was opened
    before its account was archived, and `space` is refused. `Couldn't update`
    carries the engine's words and its `statement_id` words, no line of
    the app's; the list is read again as after any refused tick, the engine's
    ticks kept and the cursor on row 1."""
    _patch(monkeypatch)
    err = archived_refusal(422, ARCHIVED_PUT_WORDS, "statement_id")
    fake_client.errors["PUT"] = err
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen,
        "notify",
        lambda self, message, title="", **kw: notices.append((title, message)),
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        first._cursor = 2
        await pilot.press("space")
        await wait_for(pilot, lambda: notices)
        await wait_for(pilot, lambda: screen._list is not first)
        assert notices == [
            (
                "Couldn't update",
                f"VALIDATION_ERROR — {ARCHIVED_PUT_WORDS}\n  statement_id: {ARCHIVED_FIELD_WORDS}",
            )
        ]
        assert notices[0][1] == refusal_text(err, None)
        assert screen._list.checked == {"l1"}
        assert screen._list.cursor_key == "l1"
        assert screen._record["status"] == 1

    run_app(scenario)
    assert fake_client.puts == [("/transactions/t2a", {"statement_id": "r1"})]


def test_a_burst_ending_in_a_refusal_reads_the_month_and_the_list_again(fake_client, monkeypatch):
    """Tick A lands while tick B waits behind it, then B is refused: A moved the
    month's `diff`, so the screen reads the month again as well as its lines,
    and the cursor goes back to row 1."""
    import threading

    statement_reads = _patch(monkeypatch)
    from expense import reads as reads_module

    fake = reads_module.fetch_bank_lines
    line_reads: list = []

    def counting(cfg, **k):
        line_reads.append(k)
        return fake(cfg, **k)

    monkeypatch.setattr("expense.reads.fetch_bank_lines", counting)
    release = threading.Event()
    real_put = fake_client.put
    refusal = EngineError(
        "VALIDATION_ERROR",
        "Cannot assign transactions to a completed statement.",
        {"statement_id": "Cannot assign transactions to a completed statement."},
        422,
        {},
    )

    def put(path, json_body=None):
        if path == "/transactions/t1":
            release.wait(timeout=5)  # A lands only once B sits in the queue
            return real_put(path, json_body=json_body)
        fake_client.calls.append(("PUT", path, json_body))
        raise refusal

    fake_client.put = put
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        loaded = len(line_reads)
        first._cursor = 0
        first.action_toggle()  # l1 out: lands
        first._cursor = 2
        first.action_toggle()  # l2 in: refused
        await wait_for(pilot, lambda: len(screen._write_queue or ()) == 1)
        release.set()
        await wait_for(pilot, lambda: notices)
        await wait_for(pilot, lambda: screen._list is not first)
        await pilot.pause()  # let any further read settle, then count
        assert fake_client.puts == [
            ("/transactions/t1", {"statement_id": None}),
            ("/transactions/t2a", {"statement_id": "r1"}),
        ]
        assert statement_reads == ["r1"]  # the header's figures, read again once
        assert len(line_reads) - loaded == 2  # the batch's lines and the rest, once
        assert screen._list.cursor_key == "l1"

    run_app(scenario)


def test_a_tick_while_a_reload_runs_keeps_the_cursor_on_it(fake_client, monkeypatch):
    """Ticking down a statement: tick A lands and its re-read starts; `↓ ↓
    space` ticks B on the list still shown, and B's PUT is still out when A's
    re-read lands. That read is not drawn (it may predate B); the one after B
    is, with the cursor on B."""
    import threading

    _patch(monkeypatch)
    from expense import reads as reads_module

    fake = reads_module.fetch_bank_lines
    reads_open = threading.Event()
    reads_open.set()
    line_reads: list = []

    def gated(cfg, **k):
        reads_open.wait(timeout=5)
        line_reads.append(k)
        return fake(cfg, **k)

    monkeypatch.setattr("expense.reads.fetch_bank_lines", gated)
    put_open = threading.Event()
    put_open.set()
    real_put = fake_client.put

    def put(path, json_body=None):
        put_open.wait(timeout=5)
        return real_put(path, json_body=json_body)

    fake_client.put = put

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        loaded = len(line_reads)
        reads_open.clear()  # A's re-read waits
        await pilot.press("space")  # A: l1 out
        await wait_for(pilot, lambda: len(fake_client.puts) == 1 and not screen._ticks_unanswered())
        put_open.clear()  # B's PUT stays out
        await pilot.press("down", "down", "space")  # B: l2 in, on the list still shown
        await wait_for(pilot, screen._ticks_unanswered)
        reads_open.set()  # A's re-read lands while B is unanswered
        await wait_for(pilot, lambda: len(line_reads) - loaded == 2)
        await pilot.pause()
        await pilot.pause()
        assert screen._list is first  # not drawn
        assert first.cursor_key == "l2"
        put_open.set()
        await wait_for(pilot, lambda: screen._list is not first)
        assert fake_client.puts == [
            ("/transactions/t1", {"statement_id": None}),
            ("/transactions/t2a", {"statement_id": "r1"}),
        ]
        assert screen._list.cursor_key == "l2"

    run_app(scenario)


def test_a_refused_status_write_with_a_tick_behind_it_draws_the_list_again(
    fake_client, monkeypatch
):
    """`y` to revert, then `space` before the engine answers: the tick waits
    behind the revert. The revert is refused, which drops the tick unsent, so
    the month and its list are read again and drawn — the engine's ticks, the
    cursor on row 1 — and `r` keeps drawing after it."""
    import threading

    statement_reads = _patch(monkeypatch)
    release = threading.Event()
    refusal = EngineError("CONFLICT", ARCHIVED_FIELD_WORDS, None, 409, {})

    def held_post(path, json_body=None):
        release.wait(timeout=5)
        fake_client.calls.append(("POST", path, json_body))
        raise refusal

    fake_client.post = held_post
    notices: list = []

    def note(self, message, title="", **kw):
        notices.append((title, message))

    monkeypatch.setattr(ReconciliationDetailScreen, "notify", note)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        await pilot.press("u")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: app.screen is screen and screen.writes_unanswered())
        first._cursor = 2
        first.action_toggle()  # l2 in, queued behind the revert
        await wait_for(pilot, lambda: len(screen._write_queue or ()) == 1)
        assert first.checked == {"l1", "l2"}
        release.set()
        await wait_for(pilot, lambda: screen._list is not first)
        assert notices[0][0] == "Couldn't revert"
        assert fake_client.puts == []  # the tick was never sent
        assert statement_reads == ["r1"]
        assert screen._list.checked == {"l1"}  # the engine's ticks
        assert screen._list.cursor_key == "l1"
        assert not screen._ticks_unanswered()
        drawn = screen._list
        await pilot.press("r")
        await wait_for(pilot, lambda: screen._list is not drawn)

    run_app(scenario)


def test_toggle_burst_puts_every_toggle_in_order(fake_client, monkeypatch):
    """A burst of toggles sends one PUT per toggle, in the order pressed —
    including a re-toggle of the same row (l1 out, then back in) — and reads
    the list again once, after the last.

    The engine holds its first answer until all three ticks are at the screen,
    one sent and two queued behind it: each `Toggled` reaches the screen through
    the checklist's container, and an answer that comes back before the next
    tick arrives empties the queue, which reads again by design ("once every
    tick sent is answered")."""
    _patch(monkeypatch)
    reads: list = []
    from expense import reads as reads_module

    fake = reads_module.fetch_bank_lines

    def counting(cfg, **k):
        reads.append(k)
        return fake(cfg, **k)

    monkeypatch.setattr("expense.reads.fetch_bank_lines", counting)
    release = threading.Event()
    real_put = fake_client.put

    def held(path, json_body=None):
        release.wait(timeout=5)
        return real_put(path, json_body=json_body)

    fake_client.put = held

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        loaded = len(reads)
        first = screen._list
        try:
            screen._list._cursor = 0
            screen._list.action_toggle()  # l1 → out
            screen._list._cursor = 2
            screen._list.action_toggle()  # l2 → in
            screen._list._cursor = 0
            screen._list.action_toggle()  # l1 → back in
            # the burst is at the screen: one tick in flight, two queued
            await wait_for(pilot, lambda: len(screen.writes_unanswered()) == 3)
            assert fake_client.puts == []
        finally:
            release.set()
        await wait_for(pilot, lambda: len(fake_client.puts) == 3)
        await wait_for(pilot, lambda: screen._list is not first)
        await pilot.pause()
        assert fake_client.puts == [
            ("/transactions/t1", {"statement_id": None}),
            ("/transactions/t2a", {"statement_id": "r1"}),
            ("/transactions/t1", {"statement_id": "r1"}),
        ]
        assert len(reads) - loaded == 2  # one re-read: the batch's lines and the rest

    run_app(scenario)


def test_rapid_reloads_keep_one_fresh_checklist(fake_client, monkeypatch):
    """A superseded load must not paint: no stacked or stale checklist.

    Exclusive-group cancellation is cooperative — the first worker keeps
    running. Before the fix it painted its stale rows over (or under) the
    fresh ones; now it checks is_cancelled and the swap is lock-serialized.
    """
    import time

    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)
    calls = {"n": 0}
    fresh_line = bank_line_row(
        "l9",
        [_part("t9", -100, line="l9", day="2026-04-10", title="Fresh", recon="r1")],
        net_cents=-100,
        account_id="acc1",
    )

    def fake_fetch(cfg, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            time.sleep(0.15)  # the superseded first load finishes last
            return cursor_page(ASSIGNED)
        return cursor_page([*ASSIGNED, fresh_line])

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fake_fetch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: calls["n"] >= 1)
        screen._load_txns()  # supersedes the slow mount-time load
        await wait_for(pilot, lambda: screen._list is not None and len(screen._list._rows) == 2)
        await pilot.pause(0.25)  # window for the cancelled worker to (not) paint
        assert len(screen.query(CheckList)) == 1
        assert [r[0] for r in screen._list._rows] == ["l1", "l9"]

    run_app(scenario)


def test_a_read_a_newer_one_replaced_does_not_paint_or_use_up_the_landing(fake_client, monkeypatch):
    """A read that passed its cancel check before a newer load started still
    hands back after it; the UI thread drops it, so the newest read paints with the
    cursor on the line ticked last."""
    from expense.tui.screens import reconciliations as module

    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)
    fresh_line = bank_line_row(
        "l9",
        [_part("t9", -100, line="l9", day="2026-04-10", title="Fresh", recon="r1")],
        net_cents=-100,
        account_id="acc1",
    )
    entered, release = threading.Event(), threading.Event()
    first_thread: list[int] = []

    def fake_fetch(cfg, **k):
        if not first_thread:
            first_thread.append(threading.get_ident())
        if threading.get_ident() == first_thread[0]:
            entered.set()
            assert release.wait(5)
            return cursor_page(ASSIGNED)  # the older read's answer, held until released
        return cursor_page([*ASSIGNED, fresh_line])

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fake_fetch)

    class Live:  # a worker whose cancel flag the older read has already passed
        is_cancelled = False

    monkeypatch.setattr(module, "get_current_worker", lambda: Live())
    handed_back: list[str] = []
    real = module.call_while_attached

    def counting(screen, fn, *a, **k):
        real(screen, fn, *a, **k)
        handed_back.append(getattr(fn, "__name__", ""))

    monkeypatch.setattr(module, "call_while_attached", counting)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await wait_for(pilot, entered.is_set)
        screen._land_on = "l9"
        screen._load_txns()  # the newer load
        await wait_for(pilot, lambda: screen._list is not None and len(screen._list._rows) == 2)
        assert screen._list.cursor_key == "l9"
        release.set()
        await wait_for(pilot, lambda: handed_back.count("_populate") == 2)
        await pilot.pause()
        assert len(screen.query(CheckList)) == 1
        assert [r[0] for r in screen._list._rows] == ["l1", "l9"]
        assert screen._list.cursor_key == "l9"

    run_app(scenario)


def test_a_stale_read_handing_back_before_the_newer_paints_changes_nothing(
    fake_client, monkeypatch
):
    """The older read hands back after the newer one started and before it paints: its
    record, count and rows are dropped, `_land_on` stays for the newer read, and the
    status a complete just set is kept."""
    from expense.tui.screens import reconciliations as module

    _patch(monkeypatch)
    entered = {1: threading.Event(), 2: threading.Event()}
    release = {1: threading.Event(), 2: threading.Event()}
    threads: list[int] = []
    stale = {**DRAFT, "status": 0}

    def which() -> int:
        if threading.get_ident() not in threads:
            threads.append(threading.get_ident())
        return threads.index(threading.get_ident()) + 1

    def hold(n: int) -> None:
        entered[n].set()
        assert release[n].wait(5)

    def fake_statement(cfg, statement_id, **k):
        n = which()
        if n == 1:
            hold(1)  # read 1 is held before its record lands
            return stale
        return {**DRAFT, "status": 2}

    def fake_fetch(cfg, **k):
        if which() == 2:
            hold(2)  # read 2 is held before it paints
        return cursor_page(ASSIGNED)

    monkeypatch.setattr("expense.reads.fetch_statement", fake_statement)
    monkeypatch.setattr("expense.reads.fetch_bank_lines", fake_fetch)
    monkeypatch.setattr("expense.reads.count_bank_lines", lambda cfg, **k: 3)

    class Live:
        is_cancelled = False

    monkeypatch.setattr(module, "get_current_worker", lambda: Live())
    handed_back: list[str] = []
    real = module.call_while_attached
    real_load = ReconciliationDetailScreen._load_txns

    def counting(screen, fn, *a, **k):
        real(screen, fn, *a, **k)
        handed_back.append(getattr(fn, "__name__", ""))

    monkeypatch.setattr(module, "call_while_attached", counting)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        monkeypatch.setattr(ReconciliationDetailScreen, "_load_txns", lambda self, **k: None)
        await app.push_screen(screen)  # no mount-time read: the test starts both
        monkeypatch.setattr(ReconciliationDetailScreen, "_load_txns", real_load)
        screen._load_txns(refresh_record=True)  # read 1, held before its record lands
        await wait_for(pilot, entered[1].is_set)
        screen._record["status"] = 2  # a complete just landed
        screen._land_on = "l1"
        screen._open_when_counted = True
        screen._load_txns(refresh_record=True)  # read 2, held in its fetch
        await wait_for(pilot, entered[2].is_set)
        release[1].set()
        await wait_for(pilot, lambda: handed_back.count("_if_newest") >= 4)
        await pilot.pause()
        assert screen._list is None  # read 1 painted nothing
        assert screen._land_on == "l1"  # and used up nothing
        assert screen._open_when_counted is True
        assert screen._record["status"] == 2
        release[2].set()
        await wait_for(pilot, lambda: screen._list is not None)
        assert screen._list.cursor_key == "l1"

    run_app(scenario)


def test_fetch_all_lines_pages_at_engine_cap(monkeypatch):
    """The detail fetch never exceeds the engine's 200-row limit cap
    and follows `next_cursor` until it is null — never an offset."""
    from expense.tui.screens.reconciliations import _fetch_all_lines

    calls: list[tuple[int, str | None]] = []

    def fake_fetch(cfg, *, limit, after=None, **kw):
        assert "offset" not in kw
        calls.append((limit, after))
        if after is None:  # one full page with a cursor, then the last one
            return cursor_page([{"id": f"l{i}"} for i in range(200)], next_cursor="c1")
        return cursor_page([{"id": f"l{200 + i}"} for i in range(40)])

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fake_fetch)
    rows = _fetch_all_lines(object(), reconciliation="r1")
    assert calls == [(200, None), (200, "c1")]
    assert [r["id"] for r in rows] == [f"l{i}" for i in range(240)]


def test_complete_confirms_then_posts(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        screen.action_complete()  # opens confirm
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")  # confirm
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts == [(COMPLETE_PATH, None)]

    run_app(scenario)


#: NETFLIX once its statement is completed: every line field locked and its
#: one part's amount held as the total (tests/contract/test_bank_line_edit_limits.py).
LOCKED_NETFLIX = {
    **NETFLIX,
    "edit_limits": edit_limits(
        locked_fields=dict.fromkeys(
            ("title", "date", "account_id", "statement_id", "operation_code"), "LOCKED"
        ),
        total_fixed=True,
        locked_part_fields={"t1": {"amount_cents": "SPLIT_TOTAL_MISMATCH"}},
    ),
}


def test_completed_is_read_only(fake_client, monkeypatch):
    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_bank_lines",
        lambda cfg, **k: cursor_page([LOCKED_NETFLIX] if k.get("reconciliation") == "r1" else []),
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        assert screen._list._read_only
        assert [r[0] for r in screen._list._rows] == ["l1"]  # only the batch's lines

    run_app(scenario)


def test_a_completed_statement_with_no_lines_says_so_in_statement_words(fake_client, monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_bank_lines", lambda cfg, **k: cursor_page([]))

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen({**DRAFT, "status": 2})
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        assert screen._list._empty == "(no transactions in this statement)"

    run_app(scenario)


@pytest.mark.parametrize(
    ("ticked", "count"),
    [(1, "1 ticked row"), (2, "2 ticked rows"), (5, "5 ticked rows")],
)
def test_cs_question_counts_the_ticked_rows_in_written_english(
    fake_client, monkeypatch, ticked, count
):
    """`c` asks before completing, and its count reads as English: `1 ticked
    row` for one, `N ticked rows` otherwise. Nothing is sent by asking."""
    _patch(monkeypatch)
    batch = [
        bank_line_row(
            f"b{i}",
            [
                _part(
                    f"tb{i}", -100 * (i + 1), line=f"b{i}", day="2026-04-14", title="X", recon="r1"
                )
            ],
            net_cents=-100 * (i + 1),
            account_id="acc1",
        )
        for i in range(ticked)
    ]

    def fake_fetch(cfg, **k):
        return cursor_page(batch if k.get("reconciliation") == "r1" else [])

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fake_fetch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        assert len(screen._list.checked) == ticked
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        texts = [str(s.visual) for s in app.screen.query(Static)]
        assert texts[0] == "Complete statement?"
        assert texts[1] == (
            "Locks the amount, date, title, account, operation number and statement"
            f" of the {count}."
        )
        assert fake_client.posts == []

    run_app(scenario)


def test_delete_completed_surfaces_engine_409(fake_client, monkeypatch):
    """No draft-only pre-guard: the DELETE reaches the engine
    and its 409 message toasts."""
    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)
    fake_client.errors["DELETE"] = EngineError(
        "CONFLICT",
        "Cannot delete a completed statement. Revert it to draft first.",
        None,
        409,
        {},
    )
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notices)
        assert fake_client.deletes == [STATEMENT_PATH]  # request was attempted
        assert any("Revert it to draft first" in m for m in notices)

    run_app(scenario)


@pytest.mark.parametrize(
    ("reason", "line"),
    [
        ("RECONCILIATION_NOT_DRAFT", "Press u to revert it, then d again."),
        ("CONCURRENT_CHANGE", "It changed at the same moment: press r, then try again."),
    ],
    ids=["not-a-draft", "concurrent-change"],
)
def test_a_refused_delete_names_the_key_on_this_screen(fake_client, monkeypatch, reason, line):
    """The engine's words, on `statement_id` (contract: DELETE /v1/statements/{statement_id}),
    then the line naming this screen's own key: `u` reverts, `r` reads it again."""
    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)
    words = "Cannot delete a completed statement. Revert it to draft first."
    fake_client.errors["DELETE"] = EngineError(
        "CONFLICT",
        words,
        {"statement_id": "Must be a draft statement."},
        409,
        {},
        {"statement_id": reason},
    )
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen,
        "notify",
        lambda self, message, title="", **kw: notices.append((title, message)),
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notices)
        assert notices == [
            (
                "Couldn't delete",
                f"CONFLICT — {words}\n  statement_id: Must be a draft statement.\n\n{line}",
            )
        ]

    run_app(scenario)


@pytest.mark.parametrize(
    ("key", "verb", "method", "path"),
    [
        ("c", "complete", "POST", COMPLETE_PATH),
        ("u", "revert", "POST", REVERT_PATH),
        ("d", "delete", "DELETE", STATEMENT_PATH),
    ],
    ids=["complete", "revert", "delete"],
)
def test_a_status_write_on_an_archived_account_shows_the_engine_words_alone(
    fake_client, monkeypatch, key, verb, method, path
):
    """The statement was opened
    before its account was archived; `c`, `u` or `d`, then `y`, is refused on
    `statement_id` (contract: POST /v1/statements/{statement_id}/complete, "An archived
    account"). `Couldn't <verb>` carries the engine's words and its `statement_id`
    words, no line of the app's; the statement stays open as a draft."""
    _patch(monkeypatch)
    _fresh_read(monkeypatch, STATEMENT)  # a refused complete reads the statement fresh
    err = archived_refusal(409, ARCHIVED_FIELD_WORDS, "statement_id")
    fake_client.errors[method] = err
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press(key)
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        words = f"CONFLICT — {ARCHIVED_FIELD_WORDS}\n  statement_id: {ARCHIVED_FIELD_WORDS}"
        under_the_head = verb == "complete"  # a refused complete is lines, not a toast
        if under_the_head:
            await wait_for(pilot, lambda: complete_refusal(screen))
            assert complete_refusal(screen) == ["Couldn't complete", *words.splitlines()]
            assert notices == []
        else:
            await wait_for(pilot, lambda: notices)
            assert notices == [(f"Couldn't {verb}", words, "error")]
        await pilot.pause()
        assert words == refusal_text(err, None)
        assert app.screen is screen
        assert screen._record["status"] == 1 and not screen._busy
        assert screen._list.checked == {"l1"}

    run_app(scenario)
    assert [(m, p) for m, p, _b in fake_client.calls if m != "GET"] == [(method, path)]


#: The engine's message on a complete of a statement with no transaction on any of its
#: accounts
#: (contract: POST /v1/statements/{statement_id}/complete).
NO_TRANSACTIONS_WORDS = "Cannot complete a statement with no transaction on any of its accounts."


def _no_transactions(*currencies: str) -> EngineError:
    """The engine's refusal of a complete with no transaction on any account: keyed
    `balances.<currency_code>.transactions` once for every currency of the statement
    (contract: POST /v1/statements/{statement_id}/complete)."""
    keys = [f"balances.{code}.transactions" for code in currencies]
    fields = dict.fromkeys(keys, "At least one transaction must be assigned.")
    reasons = dict.fromkeys(keys, "NO_TRANSACTIONS_ASSIGNED")
    body = error_body("VALIDATION_ERROR", NO_TRANSACTIONS_WORDS, fields, reasons)
    return EngineError(
        "VALIDATION_ERROR", NO_TRANSACTIONS_WORDS, fields, 422, body, reasons=reasons
    )


def test_complete_with_no_transaction_shows_the_engines_words_whole(fake_client, monkeypatch):
    """No ≥1-assigned pre-guard: the confirm opens and the POST fires on a statement
    covering two currencies. The engine refuses it on every currency's
    `transactions`, and `Couldn't complete` shows its words whole, PEN's line
    among them, no line of the app's."""
    _patch(monkeypatch)
    _fresh_read(monkeypatch, CARD)

    def fake_fetch(cfg, **k):  # nothing assigned to r1
        if k.get("account") == "acc1" and k.get("unreconciled"):
            return cursor_page(AVAILABLE)
        return cursor_page([])

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fake_fetch)
    err = _no_transactions("USD", "PEN")
    fake_client.errors["POST"] = err
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(CARD)
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        assert not screen._list.checked
        await pilot.press("c")  # no pre-block: confirm opens
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: complete_refusal(screen))
        assert fake_client.posts == [(COMPLETE_PATH, None)]
        assert complete_refusal(screen) == [
            "Couldn't complete",
            *refusal_text(err, None).splitlines(),
        ]
        assert (
            "  balances.PEN.transactions: At least one transaction must be assigned."
            in refusal_text(err, None).splitlines()
        )
        assert complete_refusal(screen)[1] == f"VALIDATION_ERROR — {NO_TRANSACTIONS_WORDS}"
        assert notices == []  # nothing in the corner

    run_app(scenario)


#: The days of `GAP`: from the day after the previous completed statement on acc1 to
#: the day before this statement's first (contract: POST
#: /v1/statements/{statement_id}/complete, "Response").
GAP_DAYS = {
    "first_uncovered_day": "2026-02-25",
    "last_uncovered_day": "2026-03-31",
    "unfiled_count": 3,
}
#: The engine's sentence for `GAP_DAYS`, as the contract prints it (contract: POST
#: /v1/statements/{statement_id}/complete, "Response"), built from the same object.
GAP = (
    "The days 2026-02-25 to 2026-03-31 are not covered by any completed statement on this "
    "account — they fall between 'February 2026' and this period (3 unfiled transactions "
    "in them)."
)


def _complete_with_warnings(fake_client, warnings: list[str], *, statement=STATEMENT) -> None:
    """The complete's answer: acc1's balance carrying `warnings`, with `GAP_DAYS` as its
    `coverage_gap` when there are any and `None` when there are none, and every other
    balance of `statement` as it reads."""
    acc1 = {"warnings": warnings, "coverage_gap": GAP_DAYS if warnings else None}
    balances = [
        {**balance, **acc1} if balance["currency_code"] == "PEN" else balance
        for balance in statement["balances"]
    ]
    fake_client.write_responses[COMPLETE_PATH] = statement_complete_answer(
        {**statement, "status": 2, "balances": balances}
    )


def test_the_gap_falls_before_the_statement_and_its_sentence_names_its_days():
    """The fixture is one the engine could send: the uncovered days end before the
    statement's first, and the sentence names the days of its `coverage_gap`."""
    assert GAP_DAYS["first_uncovered_day"] <= GAP_DAYS["last_uncovered_day"]
    assert GAP_DAYS["last_uncovered_day"] < STATEMENT["date_start"]
    days = f"{GAP_DAYS['first_uncovered_day']} to {GAP_DAYS['last_uncovered_day']}"
    assert f"The days {days} are not covered" in GAP
    assert f"({GAP_DAYS['unfiled_count']} unfiled transactions in them)." in GAP


def test_complete_gap_warning_is_a_line_not_a_toast(fake_client, monkeypatch):
    """`complete`'s `warnings` reach the screen as a persistent line.

    Not a toast: the whole
    value of this message is not being missed, and a toast fades. The success
    feedback is NOT replaced — both are shown.
    """
    _patch(monkeypatch)
    _complete_with_warnings(fake_client, [GAP])
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        line = screen.query_one("#rwarn", Static)
        assert not line.display  # nothing before the write
        screen.action_complete()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: line.display)
        assert " ".join(shown(line).split()) == f"⚠ {GAP}"  # the engine's own sentence, verbatim
        # the gap never replaces the success feedback
        await wait_for(pilot, lambda: notices)
        assert any("completed" in m for m in notices)

    run_app(scenario)


def test_a_gap_on_any_currency_draws_its_line(fake_client, monkeypatch):
    """The close's notes are per balance: a gap on the dollar balance alone is the
    dollars', and the statement's screen draws it."""
    _patch(monkeypatch)
    balances = [{**DOLLARS, "warnings": [GAP], "coverage_gap": GAP_DAYS}, CARD["balances"][1]]
    _complete_with_warnings(fake_client, [], statement={**CARD, "balances": balances})

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(CARD)
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: screen._record["status"] == 2)
        await pilot.pause()
        assert fake_client.posts == [(COMPLETE_PATH, None)]
        assert " ".join(shown(screen.query_one("#rwarn", Static)).split()) == f"⚠ {GAP}"

    run_app(scenario)


def test_complete_without_warnings_draws_no_line(fake_client, monkeypatch):
    """The clean close is unchanged — an empty `warnings` leaves no line."""
    _patch(monkeypatch)
    _complete_with_warnings(fake_client, [])

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        screen.action_complete()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.posts)
        assert not screen.query_one("#rwarn", Static).display

    run_app(scenario)


def test_revert_clears_a_shown_gap(fake_client, monkeypatch):
    """A gap report is true of one moment: revert unseals the very window it
    named, so the line goes with the status change rather than lingering."""
    _patch(monkeypatch)
    _complete_with_warnings(fake_client, [GAP])

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        line = screen.query_one("#rwarn", Static)
        screen.action_complete()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: line.display)
        screen.action_revert()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: not line.display)

    run_app(scenario)


def test_revert_on_draft_posts_idempotently(fake_client, monkeypatch):
    """No completed-only pre-guard: revert on a draft POSTs and
    the engine's idempotent 200 no-op reads as success."""
    _patch(monkeypatch)
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("u")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts == [(REVERT_PATH, None)]
        await wait_for(pilot, lambda: notices)
        assert any("reverted to draft" in m for m in notices)

    run_app(scenario)


def test_revert_posts(fake_client, monkeypatch):
    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        screen.action_revert()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts == [(REVERT_PATH, None)]

    run_app(scenario)


def test_revert_key_is_u(fake_client, monkeypatch):
    """Real `u` keypress routes to revert (`r` must never write)."""
    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("u")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts == [(REVERT_PATH, None)]

    run_app(scenario)


#: Statement r1 completed, read fresh covering two currencies: the dollars first, then the
#: soles, their end moved to 9,999.99 and their difference to 0.
CARD_FRESH = statement_record(
    {
        "id": "r1",
        "status": 2,
        "balances": [
            DOLLARS,
            {
                "currency_code": "PEN",
                "beginning_balance_cents": 958000,
                "ending_balance_cents": 999999,
                "difference_cents": 0,
            },
        ],
    }
)


def _detail_lines(mock) -> None:
    """The checklist's reads on the mocked engine: the statement's line, and
    none in no statement."""
    mock.get(f"{ENGINE_URL}/v1/bank-lines").mock(
        side_effect=lambda request: httpx.Response(
            200, json=cursor_page(ASSIGNED if "statement_id" in request.url.params else [])
        )
    )


def test_r_reads_the_statement_by_its_id_and_shows_its_balances(configured, monkeypatch):
    """`r` reads the statement again by its id, `GET /statements/{id}`, through the
    real HTTP client (contract: GET /v1/statements/{statement_id}), and the
    checklist; the head shows every currency's entry in `balances`, and the status
    read. No write, no dismiss."""
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc1": "BCP"}
    )
    seen: dict = {}

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("r")
        await wait_for(
            pilot, lambda: balance_of(screen._record, "PEN").get("ending_balance_cents") == 999999
        )
        await wait_for(pilot, lambda: screen._list._read_only)
        seen["head"] = shown(screen.query_one("#rhead", Static))
        seen["record"] = dict(screen._record)
        seen["screen"] = app.screen is screen

    with respx.mock() as mock:
        _detail_lines(mock)
        read = mock.get(f"{ENGINE_URL}/v1/statements/r1").mock(httpx.Response(200, json=CARD_FRESH))
        run_app(scenario)
        writes = [call.request for call in mock.calls if call.request.method != "GET"]
    assert read.call_count == 1
    assert writes == []
    assert seen["screen"]  # not dismissed
    assert (seen["record"]["id"], seen["record"]["account_id"]) == ("r1", "acc1")
    rows = {ln.split()[0]: ln.split() for ln in seen["head"].splitlines()[2:]}
    assert rows == {
        "USD": ["USD", "50.00", "70.00", "1.20"],
        "PEN": ["PEN", "9,580.00", "9,999.99", "—"],
    }
    assert seen["head"].splitlines()[0].endswith("status completed")


def test_r_on_a_deleted_statement_says_so_and_goes_back(configured, monkeypatch):
    """The statement deleted elsewhere: its read by id is a `404`, which is how the
    screen learns it (contract: GET /v1/statements/{statement_id}); it says so and
    goes back."""
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc1": "BCP"}
    )
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen,
        "notify",
        lambda self, message, **kw: notices.append((message, kw.get("severity"))),
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("r")
        await wait_for(pilot, lambda: app.screen is not screen)

    with respx.mock() as mock:
        _detail_lines(mock)
        read = mock.get(f"{ENGINE_URL}/v1/statements/r1").mock(
            error_response(404, "NOT_FOUND", "statement not found.")
        )
        run_app(scenario)
    assert read.call_count == 1
    assert notices == [("This statement no longer exists.", "error")]


def test_r_refused_otherwise_shows_the_engines_words_and_stays(fake_client, monkeypatch):
    """Any other refusal of the read is no sign of a delete: its words show, as every
    read failure shows them, and the screen stays."""
    _patch(monkeypatch)
    refusal = EngineError("INTERNAL_ERROR", "Something went wrong on our side.", None, 500, {})

    def refused(cfg, statement_id, **k):
        raise refusal

    monkeypatch.setattr("expense.reads.fetch_statement", refused)
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("r")
        await wait_for(pilot, lambda: notices)
        await pilot.pause()
        assert notices == [format_error(refusal)]
        assert app.screen is screen

    run_app(scenario)


def test_confirm_modal_enter_cancels(fake_client, monkeypatch):
    """Enter is the safe default: dismisses the confirm without applying (4.1)."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("d")  # delete → confirm modal
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == "Delete statement?"
        assert app.screen._message == (
            "Detaches its transactions and removes the statement. Its transactions stay. "
            "No screen can bring it back."
        )
        await pilot.press("enter")
        await wait_for(pilot, lambda: app.screen is screen)  # modal gone
        await pilot.pause()  # let the cancel settle, then assert a non-event
        assert not fake_client.deletes

    run_app(scenario)


def test_q_inert_inside_confirm_modal(fake_client, monkeypatch):
    """q inside a ConfirmModal must not kill the app."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("d")  # delete → confirm modal
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("q")
        await pilot.pause()  # let the (inert) keypress settle, then assert a non-event
        assert app.is_running
        assert isinstance(app.screen, ConfirmModal)  # modal still up, undecided
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)  # modal dismissed
        assert not fake_client.deletes

    run_app(scenario)


def test_detail_fetch_error_notifies_not_crash(fake_client, monkeypatch):
    """An engine/config error in _load_txns must not exit the app."""
    _patch(monkeypatch)

    def boom(cfg, **k):
        raise RuntimeError("engine down")

    monkeypatch.setattr("expense.reads.fetch_bank_lines", boom)
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: notices)
        assert notices and "engine down" in notices[0]
        assert app.is_running
        assert app.screen is screen

    run_app(scenario)


# ---- the ending balance, asked for at complete --------------------------------
# The engine refuses to complete without every balance (contract: POST
# /v1/statements/{statement_id}/complete, "Every balance must be entered"). The other
# blank balances and the refusals that name one are in test_tui_statement_balances.py.

NO_END_STATEMENT = _statement(ending_balance_cents=None, difference_cents=None)
NO_END = NO_END_STATEMENT
SAVED_STATEMENT = _statement(ending_balance_cents=1385320, difference_cents=0)
#: The ending balance's save of 13,853.20 on the soles, in the statement's `balances`.
SAVED_BODY = {"balances": [{"currency_code": "PEN", "ending_balance_cents": 1385320}]}


def test_the_ending_balance_is_saved_in_balances_naming_only_the_currency_that_changes():
    """`PUT /statements/{id}` takes `balances` naming only the currencies that change,
    keyed by `currency_code`; the opened currency's entry carries the figure and no other
    currency is named, so the engine keeps its balances
    (contract: PUT /v1/statements/{statement_id}, "`balances`")."""
    assert balances_body({("PEN", "ending"): 1385320}) == SAVED_BODY
    assert balances_body({("USD", "ending"): -12050}) == {
        "balances": [{"currency_code": "USD", "ending_balance_cents": -12050}]
    }


def _notes(monkeypatch) -> list:
    notices: list = []

    def note(self, message, title="", severity="information", **kw):
        notices.append((title, message, severity))

    monkeypatch.setattr(ReconciliationDetailScreen, "notify", note)
    monkeypatch.setattr("expense.tui.screens.modals.AmountPromptModal.notify", note)
    return notices


def _fresh_read(monkeypatch, statement: dict) -> None:
    """What `GET /statements/{id}` answers when the screen reads the statement fresh."""
    monkeypatch.setattr("expense.reads.fetch_statement", lambda cfg, *a, **k: dict(statement))


async def _open_box(pilot, app, record=NO_END):
    from expense.tui.screens.modals import AmountPromptModal

    screen = ReconciliationDetailScreen(dict(record))
    await app.push_screen(screen)
    await _wait_list(screen, pilot)
    await pilot.press("c")
    await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))
    return screen


async def _type(pilot, text: str) -> None:
    for ch in text:
        await pilot.press(ch)


def test_c_without_an_ending_balance_opens_the_box_with_its_title_and_keys(
    fake_client, monkeypatch
):
    """The box's title, its two dim lines naming the account and its
    currency, and its keys."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await wait_for(pilot, lambda: screen._acct_name == "BCP")
        box = app.screen
        texts = [str(s.visual) for s in box.query(Static)]
        assert texts[0] == "Ending balance first"
        assert texts[1] == (
            "The statement's closing figure for BCP,\nin PEN · signed · e.g. 13,853.20"
        )
        assert texts[-1] == "[enter] save    [esc] cancel"
        assert fake_client.calls == []  # nothing sent by opening it

    run_app(scenario)


def test_enter_saves_the_balance_then_the_usual_question_and_y_completes(fake_client, monkeypatch):
    """`enter` PUTs the balance as typed, the header shows the
    engine's saved end and diff, then "Complete statement?" and only `y`
    completes."""
    _patch(monkeypatch)
    fake_client.write_responses[STATEMENT_PATH] = statement_put_answer(SAVED_STATEMENT)
    fake_client.write_responses[COMPLETE_PATH] = statement_complete_answer(
        {**SAVED_STATEMENT, "status": 2}
    )
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert fake_client.puts == [(STATEMENT_PATH, SAVED_BODY)]
        assert fake_client.posts == []  # the question comes first
        head = shown(screen.query_one("#rhead", Static))
        assert _head_row(screen, "PEN") == ["PEN", "9,580.00", "13,853.20", "—"]
        assert head.splitlines()[0].endswith("status draft")
        texts = [str(s.visual) for s in app.screen.query(Static)]
        assert texts[0] == "Complete statement?"
        assert texts[1] == (
            "Locks the amount, date, title, account, operation number and statement"
            " of the 1 ticked row."
        )
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts == [(COMPLETE_PATH, None)]
        await wait_for(pilot, lambda: any(m == "Statement completed." for _, m, _ in notices))

    run_app(scenario)


def test_the_sign_is_the_one_typed(fake_client, monkeypatch):
    """The amount is taken exactly as typed: a negative stays negative, a bare
    figure stays positive — never added or flipped."""
    _patch(monkeypatch)
    fake_client.write_responses[STATEMENT_PATH] = statement_put_answer(
        _statement(ending_balance_cents=-12050, difference_cents=0)
    )

    async def scenario(pilot, app):
        await _open_box(pilot, app)
        await _type(pilot, "-120.50")
        await pilot.press("enter")
        await wait_for(pilot, lambda: fake_client.puts)
        assert fake_client.puts == [
            (
                STATEMENT_PATH,
                {"balances": [{"currency_code": "PEN", "ending_balance_cents": -12050}]},
            )
        ]

    run_app(scenario)


def test_a_save_on_a_two_currency_statement_names_the_opened_currency_alone(
    fake_client, monkeypatch
):
    """On a statement covering soles and dollars opened on soles, `enter` sends one `PUT`
    naming the soles with the figure and not the dollars; the header then shows the
    soles' entry of the engine's answer, never the dollars' figures."""
    _patch(monkeypatch)
    no_end = statement_record({"id": "r1", "balances": [DOLLARS, *NO_END_STATEMENT["balances"]]})
    saved = statement_record({"id": "r1", "balances": [DOLLARS, *SAVED_STATEMENT["balances"]]})
    fake_client.write_responses[STATEMENT_PATH] = statement_put_answer(saved)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app, record=no_end)
        await _type(pilot, "13853.20")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert fake_client.puts == [(STATEMENT_PATH, SAVED_BODY)]
        assert _head_row(screen, "PEN") == ["PEN", "9,580.00", "13,853.20", "—"]
        assert _head_row(screen, "USD") == ["USD", "50.00", "70.00", "1.20"]  # as it was

    run_app(scenario)


def test_the_balances_are_saved_and_completed_each_write_under_its_own_key(configured, monkeypatch):
    """Through the shared write path and the real HTTP client, two boxes typed are one
    `PUT /statements/{id}` carrying one `X-Idempotency-Key`, its body the balances in
    `balances`; `y` sends the complete under another key. A complete the engine refuses
    naming a balance opens the boxes again: a second `PUT` and a second complete, each
    with a key of its own."""
    from expense.tui.screens.modals import AmountPromptModal

    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc1": "BCP"}
    )
    blank = _statement(beginning_balance_cents=None, ending_balance_cents=None)
    refused = error_response(
        422,
        "VALIDATION_ERROR",
        "Engine words.",
        fields={"balances.PEN.ending_balance_cents": "Must be entered before completing."},
        reasons={"balances.PEN.ending_balance_cents": "ENDING_BALANCE_REQUIRED"},
    )
    both = {
        "balances": [
            {"currency_code": "PEN", "beginning_balance_cents": 958000, "ending_balance_cents": -5}
        ]
    }
    end_only = {"balances": [{"currency_code": "PEN", "ending_balance_cents": -5}]}

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(blank))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))
        await _type(pilot, "9580.00")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))
        await _type(pilot, "-0.05")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")  # refused: the ending balance is named
        await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))
        await _type(pilot, "-0.05")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: not screen._busy and complete.call_count == 2)

    with respx.mock() as mock:
        _detail_lines(mock)
        mock.get(f"{ENGINE_URL}/v1{STATEMENT_PATH}").mock(httpx.Response(200, json=blank))
        put = mock.put(f"{ENGINE_URL}/v1{STATEMENT_PATH}").mock(
            httpx.Response(200, json=statement_put_answer(SAVED_STATEMENT))
        )
        complete = mock.post(f"{ENGINE_URL}/v1{COMPLETE_PATH}").mock(
            side_effect=[
                refused,
                httpx.Response(
                    200, json=statement_complete_answer({**SAVED_STATEMENT, "status": 2})
                ),
            ]
        )
        run_app(scenario)
        writes = [call.request for call in mock.calls if call.request.method != "GET"]
    assert [(w.method, w.url.path) for w in writes] == [
        ("PUT", f"/v1{STATEMENT_PATH}"),
        ("POST", f"/v1{COMPLETE_PATH}"),
        ("PUT", f"/v1{STATEMENT_PATH}"),
        ("POST", f"/v1{COMPLETE_PATH}"),
    ]
    assert put.call_count == 2
    assert json.loads(writes[0].read()) == both
    assert json.loads(writes[2].read()) == end_only
    keys = [w.headers["X-Idempotency-Key"] for w in writes]
    assert all(keys) and len(set(keys)) == 4


@pytest.mark.parametrize("answer", ["n", "escape", "enter"])
def test_no_on_the_question_leaves_a_saved_draft(fake_client, monkeypatch, answer):
    """Say no and the reconciliation stays a draft with its balance saved;
    the next `c` goes straight to the question, no box."""
    _patch(monkeypatch)
    fake_client.write_responses[STATEMENT_PATH] = statement_put_answer(SAVED_STATEMENT)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press(answer)
        await wait_for(pilot, lambda: app.screen is screen)
        assert fake_client.posts == []
        assert screen._record["status"] == 1
        assert _end(screen) == 1385320
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert len(fake_client.puts) == 1  # no second box, no second save

    run_app(scenario)


def test_esc_on_the_box_sends_nothing(fake_client, monkeypatch):
    """`esc` goes back with nothing saved."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert fake_client.calls == []
        assert _end(screen) is None

    run_app(scenario)


@pytest.mark.parametrize("typed", ["13.853.20", "13.853,20", "abc", ""])
def test_a_balance_typed_wrong_keeps_the_box_open(fake_client, monkeypatch, typed):
    """The New Reconciliation form's note for a badly typed balance;
    the box stays open with what was typed, and nothing is sent."""
    from textual.widgets import Input

    from expense.tui.screens.modals import AmountPromptModal

    _patch(monkeypatch)
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        await _open_box(pilot, app)
        await _type(pilot, typed)
        await pilot.press("enter")
        await wait_for(pilot, lambda: notices)
        assert notices == [("", "End balance PEN: a signed decimal, e.g. 9460.00", "error")]
        assert isinstance(app.screen, AmountPromptModal)
        assert app.screen.query_one(Input).value == typed
        assert fake_client.calls == []

    run_app(scenario)


def test_a_refused_save_shows_the_engines_words_and_completes_nothing(fake_client, monkeypatch):
    """The engine refuses the PUT of a statement completed meanwhile, `LOCKED` on the
    balance (contract: PUT /v1/statements/{statement_id}, "Field locking on COMPLETED"):
    its words whole, no line of the app's, and no complete is asked or sent."""
    _patch(monkeypatch)
    balance = "balances.PEN.ending_balance_cents"
    fake_client.errors["PUT"] = EngineError(
        "VALIDATION_ERROR",
        "Engine words for LOCKED.",
        {balance: "Locked while the statement is completed."},
        422,
        {},
        {balance: "LOCKED"},
    )
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("enter")
        await wait_for(pilot, lambda: notices)
        assert notices == [
            (
                "Couldn't save",
                "VALIDATION_ERROR — Engine words for LOCKED.\n"
                f"  {balance}: Locked while the statement is completed.",
                "error",
            )
        ]
        assert app.screen is screen
        assert fake_client.posts == []
        assert not screen._busy

    run_app(scenario)


def test_a_balance_save_on_an_archived_account_shows_the_engine_words_alone(
    fake_client, monkeypatch
):
    """`c` on a draft with
    no ending balance, opened before its account was archived; the figure's
    save is refused on the balance sent, `balances.<currency_code>.ending_balance_cents`
    (contract: PUT /v1/statements/{statement_id}, "An archived account").
    `Couldn't save` carries the engine's words and that field's words, no line of the
    app's; nothing is completed and the end stays empty."""
    _patch(monkeypatch)
    field = "balances.PEN.ending_balance_cents"
    err = archived_refusal(422, ARCHIVED_FIELD_WORDS, field)
    fake_client.errors["PUT"] = err
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("enter")
        await wait_for(pilot, lambda: notices)
        assert notices == [
            (
                "Couldn't save",
                f"VALIDATION_ERROR — {ARCHIVED_FIELD_WORDS}\n  {field}: {ARCHIVED_FIELD_WORDS}",
                "error",
            )
        ]
        assert notices[0][1] == refusal_text(err, None)
        assert app.screen is screen and not screen._busy
        assert _end(screen) is None

    run_app(scenario)
    assert fake_client.puts == [(STATEMENT_PATH, SAVED_BODY)]
    assert fake_client.posts == []


def test_saved_then_complete_refused_says_the_balance_is_saved_and_the_complete_is_not(
    fake_client, monkeypatch
):
    """The balance saves, the complete is refused. The note says the
    balance is saved, then the engine's words; the header keeps the saved end,
    and the next `c` goes straight to the question."""
    _patch(monkeypatch)
    fake_client.write_responses[STATEMENT_PATH] = statement_put_answer(SAVED_STATEMENT)
    fake_client.errors["POST"] = _no_transactions("PEN")
    _fresh_read(monkeypatch, SAVED_STATEMENT)
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: complete_refusal(screen))
        assert complete_refusal(screen) == [
            "Couldn't complete",
            "The balances are saved. The statement is not completed:",
            f"VALIDATION_ERROR — {NO_TRANSACTIONS_WORDS}",
            "  balances.PEN.transactions: At least one transaction must be assigned.",
        ]
        assert notices == []
        await pilot.pause()
        head = shown(screen.query_one("#rhead", Static))
        assert _head_row(screen, "PEN")[:3] == ["PEN", "9,580.00", "13,853.20"]
        assert head.splitlines()[0].endswith("status draft")
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert len(fake_client.puts) == 1

    run_app(scenario)


def test_complete_refused_for_a_missing_balance_shows_the_words_and_opens_the_box(
    fake_client, monkeypatch
):
    """The screen read a balance, the engine says it is missing, on
    `balances.<currency_code>.ending_balance_cents`
    (contract: POST /v1/statements/{statement_id}/complete, "Every balance must be entered").
    The engine's words whole, no line of the app's; the screen reads the statement fresh,
    so the header's end is empty again, and the box for that balance is open."""
    from expense.tui.screens.modals import AmountPromptModal

    _patch(monkeypatch)
    words = "Cannot complete the statement without every currency's balances."
    field = "balances.PEN.ending_balance_cents"
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR",
        words,
        {field: "Must be entered before completing."},
        422,
        {},
        {field: "ENDING_BALANCE_REQUIRED"},
    )
    _fresh_read(monkeypatch, NO_END_STATEMENT)
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))
        assert complete_refusal(screen) == [
            "Couldn't complete",
            f"VALIDATION_ERROR — {words}",
            f"  {field}: Must be entered before completing.",
        ]
        assert notices == []
        await wait_for(pilot, lambda: _end(screen) is None)
        # the head as it stands for a missing end: a dim `—`, the difference blank
        assert _head_row(screen, "PEN") == ["PEN", "9,580.00", "—"]
        assert shown(screen.query_one("#rhead", Static)).splitlines()[0].endswith("status draft")

    run_app(scenario)


def test_a_draft_with_its_balance_skips_the_box(fake_client, monkeypatch):
    """A reconciliation that already has its ending balance
    completes as before — `c` goes straight to the question."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.puts == []
        assert fake_client.posts == [(COMPLETE_PATH, None)]

    run_app(scenario)
