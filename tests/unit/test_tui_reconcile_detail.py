"""Reconciliation working-screen tests — the bank-line checklist + assign/complete.

Every list reads `GET /bank-lines`: a purchase split into parts is one row with
its total, and a tick is one `PUT` of `reconciliation_id` on one of its parts
(contract: GET /v1/bank-lines)
(contract: PUT /v1/transactions/{transaction_id}, "Reconciliation assignment")."""

import httpx
import pytest
import respx
from textual.widgets import Static

from expense.errors import EngineError
from expense.formatting import bank_line_columns
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.reconciliations import ReconciliationDetailScreen, line_rows
from expense.tui.widgets.checklist import CheckList
from tests.unit.helpers import (
    ENGINE_URL,
    bank_line_row,
    cursor_page,
    import_part,
    render_text,
    run_app,
    wait_for,
    whole,
)


def _part(tx_id: str, cents: int, *, line: str, day: str, title: str, recon=None) -> dict:
    return {
        **import_part(tx_id, cents, account_id="acc1", line=line, day=day, title=title),
        "reconciliation_id": recon,
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
    assert rows[2] == ("l2", "2026-04-11", "FARMACIA", "48201764", -10000)


def _rendered(checklist: CheckList, width: int = 100) -> str:
    return render_text(checklist._build(), width=width)


def test_a_row_is_one_line_of_bank_columns():
    """Date · title · operation · amount, in that order, one line per row; a row
    without an operation code shows `—`; no category, hashtag, note or part
    count, and nothing marks a row as split."""
    rows, checked, _ = line_rows(ASSIGNED, AVAILABLE)
    text = _rendered(CheckList(rows, checked))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = lines[0]
    assert header.split() == ["Date", "Title", "Operation", "Amount"]
    assert [header.index(w) for w in ("Date", "Title", "Operation", "Amount")] == sorted(
        header.index(w) for w in ("Date", "Title", "Operation", "Amount")
    )
    body = [ln for ln in lines if "[" in ln]
    assert len(body) == 3  # one physical line per row
    farmacia = next(ln for ln in body if "FARMACIA" in ln)
    assert farmacia.split() == ["[", "]", "2026-04-11", "FARMACIA", "48201764", "-100.00"]
    uber = next(ln for ln in body if "UBER" in ln)
    assert uber.split()[-2:] == ["—", "-42.00"]
    assert "[x]" in next(ln for ln in body if "NETFLIX.COM" in ln)
    for hidden in ("Vivienda", "#", "note", "-60.00", "-40.00", "part"):
        assert hidden not in "\n".join(body), hidden


def test_a_completed_list_has_no_tick_box():
    rows, checked, _ = line_rows(ASSIGNED, [])
    text = _rendered(CheckList(rows, checked, read_only=True))
    assert "[" not in text
    header = next(ln for ln in text.splitlines() if ln.strip())
    assert header.split() == ["Date", "Title", "Operation", "Amount"]
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
    table = CheckList(rows, checked=["l1"])._build()  # app-less, PALETTE palette
    marks, ops, amounts = table.columns[0]._cells, table.columns[3]._cells, table.columns[4]._cells
    assert marks[0].style == PALETTE.success and marks[1].style == "dim"  # [x] vs [ ]
    assert ops[0].style == "dim"  # the — of a line with no code
    assert amounts[0].style == PALETTE.error  # -2,500.00
    assert amounts[1].style == PALETTE.success  # +56.20


def test_status_span_maps_completed_and_draft():
    from expense.tui.screens.reconciliations import _status_span
    from expense.tui.theme import Palette

    palette = Palette("#0f0", "#f00", "#ff0")
    assert _status_span("completed", palette) == ("completed", palette.success)
    assert _status_span("draft", palette) == ("draft", palette.warning)


DRAFT = {
    "id": "r1",
    "account_id": "acc1",
    "name": "April 2026",
    "date_start": "2026-04-01",
    "date_end": "2026-04-30",
    "beginning_balance_cents": 958000,
    "ending_balance_cents": 946000,
    "difference_cents": -3500,
    "status": 1,
}


def _patch(monkeypatch, record: dict = DRAFT):
    """Screen-specific patches; the client/config seams come from fake_client.
    Returns the log of `GET /reconciliations` reads (the header's re-read)."""
    month_reads: list = []

    def fake_fetch(cfg, **k):
        if k.get("reconciliation") == "r1":
            return cursor_page(ASSIGNED)
        if k.get("account") == "acc1" and k.get("unreconciled"):
            return cursor_page(AVAILABLE)
        return cursor_page([])

    def fake_month(cfg, *, account_id, **k):
        month_reads.append(account_id)
        return whole([dict(record)])

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fake_fetch)
    monkeypatch.setattr("expense.reads.fetch_reconciliations", fake_month)
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc1": "BCP PEN"}
    )
    return month_reads


async def _wait_list(screen, pilot):
    await wait_for(pilot, lambda: screen._list is not None)


def test_available_read_takes_the_periods_days_byte_for_byte(fake_client, monkeypatch):
    """The tick-list's in-range read asks for the account's lines in no batch,
    with the period's own days in the engine's day filters, unconverted: a bare
    `date_to` is the whole last day (contract: GET /v1/bank-lines)."""
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
        in_range = [k for k in calls if k.get("account") == "acc1"]
        assert len(in_range) == 1
        assert in_range[0]["unreconciled"] is True
        assert in_range[0]["date_from"] == "2026-04-01"
        assert in_range[0]["date_to"] == "2026-04-30"
        batch = [k for k in calls if k.get("reconciliation") == "r1"]
        assert len(batch) == 1 and "account" not in batch[0]

    run_app(scenario)


def test_header_shows_difference_not_source(fake_client, monkeypatch):
    """The header's old "(chained)"/"(manual)" tag answered a question the
    engine no longer has two answers to; it carries the add-up check instead."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        head = str(screen.query_one("#rhead", Static).visual)
        assert "diff" in head and "-35.00" in head
        assert "chained" not in head and "manual" not in head

    run_app(scenario)


def test_draft_lists_assigned_checked_plus_available(fake_client, monkeypatch):
    """The batch's lines first, ticked, then the account's lines in no batch;
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
        assert cl._rows[2][1:] == ("2026-04-11", "FARMACIA", "48201764", -10000)

    run_app(scenario)


def test_tick_puts_reconciliation_id_on_one_part_then_reads_again(fake_client, monkeypatch):
    """`space` on a split purchase: one `PUT` on one of its parts, then the
    month and its lines are read again, and the cursor stays on that row."""
    month_reads = _patch(monkeypatch)
    ticked = {**FARMACIA, "parts": [{**p, "reconciliation_id": "r1"} for p in FARMACIA["parts"]]}

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
        assert fake_client.puts == [("/transactions/t2a", {"reconciliation_id": "r1"})]
        assert month_reads == ["acc1"]  # the header's figures, read again
        assert [r[0] for r in screen._list._rows] == ["l1", "l2", "l3"]  # ticked rows first
        assert screen._list.checked == {"l1", "l2"}
        assert screen._list.cursor_key == "l2"  # the cursor stays on the purchase

    run_app(scenario)


def test_untick_sends_null_on_one_part_then_reads_again(fake_client, monkeypatch):
    month_reads = _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        await pilot.press("space")  # the cursor starts on NETFLIX, ticked
        await wait_for(pilot, lambda: screen._list is not first)
        assert fake_client.puts == [("/transactions/t1", {"reconciliation_id": None})]
        assert month_reads == ["acc1"]
        assert screen._list.cursor_key == "l1"

    run_app(scenario)


def test_a_tick_carries_one_idempotency_key(configured, monkeypatch):
    """A tick is one logical write: one `PUT`, one `X-Idempotency-Key`, through
    the shared write path and the real HTTP client."""
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc1": "BCP PEN"}
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
                json=cursor_page(
                    ASSIGNED if "reconciliation_id" in request.url.params else AVAILABLE
                ),
            )
        )
        mock.get(f"{ENGINE_URL}/v1/reconciliations").mock(httpx.Response(200, json=whole([DRAFT])))
        route = mock.put(f"{ENGINE_URL}/v1/transactions/t2a").mock(httpx.Response(200, json={}))
        run_app(scenario)
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["X-Idempotency-Key"]
    assert request.read() == b'{"reconciliation_id":"r1"}'
    sent = [dict(call.request.url.params) for call in lines.calls]
    assert {"reconciliation_id": "r1", "limit": "200"} in sent
    assert {
        "account_id": "acc1",
        "unreconciled": "true",
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
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
        ("/transactions/t1", {"reconciliation_id": None}),
        ("/transactions/t2a", {"reconciliation_id": "r1"}),
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
        EngineError(
            "VALIDATION_ERROR",
            "Period 2026-04-01 to 2026-04-30 is sealed by completed reconciliation 'April'.",
            {"reconciliation_id": "Period is sealed."},
            422,
            {},
            reasons={"reconciliation_id": "PERIOD_SEALED"},
        ),
        EngineError(
            "VALIDATION_ERROR",
            "Another part of this bank line (t2b) is the cause: the account does not match.",
            {"reconciliation_id": "Must be on the reconciliation's account."},
            422,
            {},
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


def test_a_burst_ending_in_a_refusal_reads_the_month_and_the_list_again(fake_client, monkeypatch):
    """Tick A lands while tick B waits behind it, then B is refused: A moved the
    month's `diff`, so the screen reads the month again as well as its lines,
    and the cursor goes back to row 1."""
    import threading

    month_reads = _patch(monkeypatch)
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
        "Period 2026-04-01 to 2026-04-30 is sealed by completed reconciliation 'April'.",
        {"reconciliation_id": "Period is sealed."},
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
            ("/transactions/t1", {"reconciliation_id": None}),
            ("/transactions/t2a", {"reconciliation_id": "r1"}),
        ]
        assert month_reads == ["acc1"]  # the header's figures, read again once
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
            ("/transactions/t1", {"reconciliation_id": None}),
            ("/transactions/t2a", {"reconciliation_id": "r1"}),
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

    month_reads = _patch(monkeypatch)
    release = threading.Event()
    refusal = EngineError("CONFLICT", "Reconciliation changed elsewhere.", None, 409, {})

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
        assert month_reads == ["acc1"]
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
    the list again once, after the last."""
    _patch(monkeypatch)
    reads: list = []
    from expense import reads as reads_module

    fake = reads_module.fetch_bank_lines

    def counting(cfg, **k):
        reads.append(k)
        return fake(cfg, **k)

    monkeypatch.setattr("expense.reads.fetch_bank_lines", counting)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        loaded = len(reads)
        first = screen._list
        screen._list._cursor = 0
        screen._list.action_toggle()  # l1 → out
        screen._list._cursor = 2
        screen._list.action_toggle()  # l2 → in
        screen._list._cursor = 0
        screen._list.action_toggle()  # l1 → back in
        await wait_for(pilot, lambda: len(fake_client.puts) == 3)
        await wait_for(pilot, lambda: screen._list is not first)
        await pilot.pause()
        assert fake_client.puts == [
            ("/transactions/t1", {"reconciliation_id": None}),
            ("/transactions/t2a", {"reconciliation_id": "r1"}),
            ("/transactions/t1", {"reconciliation_id": "r1"}),
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
        assert fake_client.posts == [("/reconciliations/r1/complete", None)]

    run_app(scenario)


def test_completed_is_read_only(fake_client, monkeypatch):
    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        assert screen._list._read_only
        assert [r[0] for r in screen._list._rows] == ["l1"]  # only the batch's lines

    run_app(scenario)


def test_delete_completed_surfaces_engine_409(fake_client, monkeypatch):
    """No draft-only pre-guard: the DELETE reaches the engine
    and its 409 message toasts."""
    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)
    fake_client.errors["DELETE"] = EngineError(
        "CONFLICT",
        "Cannot delete a completed reconciliation. Revert to draft first.",
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
        assert fake_client.deletes == ["/reconciliations/r1"]  # request was attempted
        assert any("Revert to draft first" in m for m in notices)

    run_app(scenario)


@pytest.mark.parametrize(
    ("reason", "line"),
    [
        ("RECONCILIATION_NOT_DRAFT", "Press u to revert it, then d again."),
        ("CONCURRENT_CHANGE", "It changed at the same moment: press r, then try again."),
    ],
    ids=["screen-8B", "screen-5A"],
)
def test_a_refused_delete_names_the_key_on_this_screen(fake_client, monkeypatch, reason, line):
    """The engine's words, then the line naming this screen's own key: `u`
    reverts, `r` reads it again."""
    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)
    words = "Cannot delete a completed reconciliation. Revert to draft first."
    fake_client.errors["DELETE"] = EngineError(
        "CONFLICT",
        words,
        {"reconciliation_id": "Must be a draft."},
        409,
        {},
        {"reconciliation_id": reason},
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
                f"CONFLICT — {words}\n  reconciliation_id: Must be a draft.\n\n{line}",
            )
        ]

    run_app(scenario)


def test_complete_with_zero_assigned_surfaces_engine_422(fake_client, monkeypatch):
    """No ≥1-assigned pre-guard: the confirm opens, the POST
    fires, and the engine's 422 message toasts."""
    _patch(monkeypatch)

    def fake_fetch(cfg, **k):  # nothing assigned to r1
        if k.get("account") == "acc1":
            return cursor_page(AVAILABLE)
        return cursor_page([])

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fake_fetch)
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR",
        "Cannot complete reconciliation with no assigned transactions.",
        {"transactions": "At least one transaction must be assigned."},
        422,
        {},
        reasons={"transactions": "NO_TRANSACTIONS_ASSIGNED"},
    )
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        assert not screen._list.checked
        screen.action_complete()  # no pre-block: confirm opens
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notices)
        assert fake_client.posts == [("/reconciliations/r1/complete", None)]
        assert any("At least one transaction must be assigned" in m for m in notices)

    run_app(scenario)


GAP = (
    "2026-02-25 to 2026-04-01 is not covered by any completed reconciliation on this "
    "account — the days after 'February 2026' and before this period are sealed by nothing."
)


def _complete_with_warnings(fake_client, warnings: list[str]) -> None:
    fake_client.write_responses["/reconciliations/r1/complete"] = {
        **DRAFT,
        "status": 2,
        "warnings": warnings,
    }


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
        text = str(line.visual)
        assert "not covered by any completed reconciliation" in text
        assert "2026-02-25 to 2026-04-01" in text  # the engine's own sentence, verbatim
        # the gap never replaces the success feedback
        await wait_for(pilot, lambda: notices)
        assert any("completed" in m for m in notices)

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
        assert fake_client.posts == [("/reconciliations/r1/revert", None)]
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
        assert fake_client.posts == [("/reconciliations/r1/revert", None)]

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
        assert fake_client.posts == [("/reconciliations/r1/revert", None)]

    run_app(scenario)


def test_r_refreshes_record_from_its_account_list_and_never_writes(fake_client, monkeypatch):
    """`r` re-reads the batch (header + status gate) and the checklist; no
    write, no dismiss. There is no read by id, so it reads
    the account's list — whole, so the row is in it — and picks the row out."""
    completed = {**DRAFT, "status": 2}
    _patch(monkeypatch)
    fresh = {**completed, "ending_balance_cents": 999999}
    other = {**completed, "id": "r0", "name": "February 2026"}
    reads: list = []

    def listed(cfg, *, account_id, **k):
        assert "limit" not in k and "offset" not in k, "the list is whole"
        reads.append(account_id)
        return whole([dict(other), dict(fresh)])

    monkeypatch.setattr("expense.reads.fetch_reconciliations", listed)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("r")
        await wait_for(pilot, lambda: screen._record.get("ending_balance_cents") == 999999)
        await pilot.pause()  # let the refresh settle, then assert a non-event
        assert reads == [DRAFT["account_id"]]  # this batch's account, once
        assert screen._record["id"] == "r1"  # the right row, not its neighbour
        assert app.screen is screen  # not dismissed
        assert not fake_client.posts and not fake_client.deletes

    run_app(scenario)


def test_r_refresh_dismisses_when_record_gone(fake_client, monkeypatch):
    """Batch deleted elsewhere → absent from its account's whole list → notify
    and pop. Absent is reliable now: the list is never a page of it."""
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_reconciliations",
        lambda cfg, *, account_id, **k: whole([{**DRAFT, "id": "someone-else"}]),
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("r")
        await wait_for(pilot, lambda: app.screen is not screen)

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
        assert app.screen._title == "Delete reconciliation?"
        assert app.screen._message == (
            "Detaches its transactions and removes the batch. Its transactions stay. "
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
# The engine refuses to complete without it (contract: POST
# /v1/reconciliations/{reconciliation_id}/complete, "The ending balance must be entered").

NO_END = {**DRAFT, "ending_balance_cents": None, "difference_cents": None}
SAVED = {**NO_END, "ending_balance_cents": 1385320, "difference_cents": 0}
PUT_PATH = "/reconciliations/r1"
COMPLETE_PATH = "/reconciliations/r1/complete"


def _notes(monkeypatch) -> list:
    notices: list = []

    def note(self, message, title="", severity="information", **kw):
        notices.append((title, message, severity))

    monkeypatch.setattr(ReconciliationDetailScreen, "notify", note)
    monkeypatch.setattr("expense.tui.screens.modals.AmountPromptModal.notify", note)
    return notices


def _fresh_read(monkeypatch, record: dict) -> None:
    """What `GET /reconciliations?account_id=` answers when the screen reads it fresh."""
    monkeypatch.setattr(
        "expense.reads.fetch_reconciliations", lambda cfg, **k: {"items": [dict(record)]}
    )


async def _open_box(pilot, app, record=NO_END, currency="PEN"):
    from expense.tui.screens.modals import AmountPromptModal

    screen = ReconciliationDetailScreen(dict(record), currency=currency)
    await app.push_screen(screen)
    await _wait_list(screen, pilot)
    await pilot.press("c")
    await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))
    return screen


async def _type(pilot, text: str) -> None:
    for ch in text:
        await pilot.press(ch)


def test_c_without_an_ending_balance_opens_the_box_as_drawn(fake_client, monkeypatch):
    """Screen A1: the box's title, its two dim lines naming the account and its
    currency, and its keys."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await wait_for(pilot, lambda: screen._acct_name == "BCP PEN")
        box = app.screen
        texts = [str(s.visual) for s in box.query(Static)]
        assert texts[0] == "Ending balance first"
        assert texts[1] == (
            "The statement's closing figure for BCP PEN,\nin PEN · signed · e.g. 13,853.20"
        )
        assert texts[-1] == "[enter] save    [esc] cancel"
        assert fake_client.calls == []  # nothing sent by opening it

    run_app(scenario)


def test_enter_saves_the_balance_then_the_usual_question_and_y_completes(fake_client, monkeypatch):
    """Screens A1 → A2 → 5: `enter` PUTs the balance as typed, the header shows the
    engine's saved end and diff, then "Complete reconciliation?" and only `y`
    completes."""
    _patch(monkeypatch)
    fake_client.write_responses[PUT_PATH] = dict(SAVED)
    fake_client.write_responses[COMPLETE_PATH] = {**SAVED, "status": 2, "warnings": []}
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert fake_client.puts == [(PUT_PATH, {"ending_balance_cents": 1385320})]
        assert fake_client.posts == []  # the question comes first
        head = str(screen.query_one("#rhead", Static).visual)
        assert "end 13,853.20" in head and "diff —" in head and "status draft" in head
        texts = [str(s.visual) for s in app.screen.query(Static)]
        assert texts[0] == "Complete reconciliation?"
        assert texts[1] == "Locks amount/account/title/date on the 1 assigned transaction(s)."
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts == [(COMPLETE_PATH, None)]
        await wait_for(pilot, lambda: any(m == "Reconciliation completed." for _, m, _ in notices))

    run_app(scenario)


def test_the_sign_is_the_one_typed(fake_client, monkeypatch):
    """The amount is taken exactly as typed: a negative stays negative, a bare
    figure stays positive — never added or flipped."""
    _patch(monkeypatch)
    fake_client.write_responses[PUT_PATH] = {**SAVED, "ending_balance_cents": -12050}

    async def scenario(pilot, app):
        await _open_box(pilot, app)
        await _type(pilot, "-120.50")
        await pilot.press("enter")
        await wait_for(pilot, lambda: fake_client.puts)
        assert fake_client.puts == [(PUT_PATH, {"ending_balance_cents": -12050})]

    run_app(scenario)


@pytest.mark.parametrize("answer", ["n", "escape", "enter"])
def test_no_on_the_question_leaves_a_saved_draft(fake_client, monkeypatch, answer):
    """A2: say no and the reconciliation stays a draft with its balance saved;
    the next `c` goes straight to the question, no box."""
    _patch(monkeypatch)
    fake_client.write_responses[PUT_PATH] = dict(SAVED)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press(answer)
        await wait_for(pilot, lambda: app.screen is screen)
        assert fake_client.posts == []
        assert screen._record["status"] == 1
        assert screen._record["ending_balance_cents"] == 1385320
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert len(fake_client.puts) == 1  # no second box, no second save

    run_app(scenario)


def test_esc_on_the_box_sends_nothing(fake_client, monkeypatch):
    """A1: `esc` goes back with nothing saved."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert fake_client.calls == []
        assert screen._record["ending_balance_cents"] is None

    run_app(scenario)


@pytest.mark.parametrize("typed", ["13.853.20", "abc", ""])
def test_a_balance_typed_wrong_keeps_the_box_open(fake_client, monkeypatch, typed):
    """Screen 2: the New Reconciliation form's note for a badly typed balance;
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
        assert notices == [("", "End balance: a signed decimal, e.g. 9460.00", "error")]
        assert isinstance(app.screen, AmountPromptModal)
        assert app.screen.query_one(Input).value == typed
        assert fake_client.calls == []

    run_app(scenario)


def test_a_refused_save_shows_the_engines_words_and_completes_nothing(fake_client, monkeypatch):
    """The engine refuses the PUT: its words whole, with the line this screen's
    `r` makes true, and no complete is asked or sent."""
    _patch(monkeypatch)
    fake_client.errors["PUT"] = EngineError(
        "CONFLICT",
        "The reconciliation changed.",
        {"reconciliation_id": "Changed meanwhile."},
        409,
        {},
        {"reconciliation_id": "CONCURRENT_CHANGE"},
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
                "CONFLICT — The reconciliation changed.\n"
                "  reconciliation_id: Changed meanwhile.\n\n"
                "It changed at the same moment: press r, then try again.",
                "error",
            )
        ]
        assert app.screen is screen
        assert fake_client.posts == []
        assert not screen._busy

    run_app(scenario)


def test_saved_then_complete_refused_says_which_half_went_through(fake_client, monkeypatch):
    """Screen 3: the balance saves, the complete is refused. The note says the
    balance is saved, then the engine's words; the header keeps the saved end,
    and the next `c` goes straight to the question."""
    _patch(monkeypatch)
    fake_client.write_responses[PUT_PATH] = dict(SAVED)
    words = "1 transaction in the period is in no batch."
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR",
        words,
        {"date_start": "Unassigned rows."},
        422,
        {},
        {"date_start": "UNASSIGNED_IN_PERIOD"},
    )
    _fresh_read(monkeypatch, SAVED)
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_box(pilot, app)
        await _type(pilot, "13853.20")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notices)
        assert notices[0] == (
            "Couldn't complete",
            "The ending balance is saved. The reconciliation is not completed:\n"
            f"VALIDATION_ERROR — {words}\n  date_start: Unassigned rows.",
            "error",
        )
        await pilot.pause()
        head = str(screen.query_one("#rhead", Static).visual)
        assert "end 13,853.20" in head and "status draft" in head
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert len(fake_client.puts) == 1

    run_app(scenario)


def test_complete_refused_for_a_missing_balance_shows_the_line_and_reads_fresh(
    fake_client, monkeypatch
):
    """Screen 4: the screen read a balance, the engine says it is missing. The
    engine's words plus the line saying what to do; the screen reads the
    reconciliation fresh, so the header's end is empty again and `c` starts
    over from the box."""
    from expense.tui.screens.modals import AmountPromptModal

    _patch(monkeypatch)
    words = "A reconciliation needs its ending balance to be completed."
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR",
        words,
        {"ending_balance_cents": "Required to complete."},
        422,
        {},
        {"ending_balance_cents": "ENDING_BALANCE_REQUIRED"},
    )
    _fresh_read(monkeypatch, NO_END)
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT), currency="PEN")
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notices)
        assert notices[0] == (
            "Couldn't complete",
            f"VALIDATION_ERROR — {words}\n  ending_balance_cents: Required to complete.\n\n"
            "Press c again: the app asks for it first.",
            "error",
        )
        await wait_for(pilot, lambda: screen._record.get("ending_balance_cents") is None)
        head = str(screen.query_one("#rhead", Static).visual)
        # the header as it stands for a missing end (screen 1: "Nothing here changes")
        assert "end —    diff     status draft" in head
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))

    run_app(scenario)


def test_a_draft_with_its_balance_skips_the_box(fake_client, monkeypatch):
    """Screen 5's caption: a reconciliation that already has its ending balance
    completes as before — `c` goes straight to the question."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT), currency="PEN")
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.puts == []
        assert fake_client.posts == [(COMPLETE_PATH, None)]

    run_app(scenario)
