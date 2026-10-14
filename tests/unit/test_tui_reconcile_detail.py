"""Reconciliation working-screen tests — checklist + assign/complete."""

from textual.widgets import Static

from expense.errors import EngineError
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.reconciliations import ReconciliationDetailScreen, _txn_sub
from expense.tui.widgets.checklist import CheckList
from tests.unit.helpers import cursor_page, run_app, wait_for, whole

CATS = {"c1": "Vivienda"}
TAGS = {"h1": "oficina"}


def test_txn_sub_assembles_category_tags_note():
    it = {"category_id": "c1", "hashtag_ids": ["h1"], "description": "alquiler"}
    assert _txn_sub(it, CATS, TAGS) == 'Vivienda  ·  #oficina  ·  "alquiler"'
    assert _txn_sub({"category_id": "c1"}, CATS, TAGS) == "Vivienda"
    assert _txn_sub({}, CATS, TAGS) == ""


def test_checklist_toggle_emits_and_tracks():
    rows = [("t1", "Alquiler", -250000, "2026-04-03", "Vivienda")]
    cl = CheckList(rows, checked=[])
    assert cl.cursor_key == "t1" and cl.checked == set()
    # simulate a toggle (no event loop): action_toggle posts a message + flips state
    cl.action_toggle()
    assert cl.checked == {"t1"}
    cl.action_toggle()
    assert cl.checked == set()


def test_checklist_colors_come_from_palette():
    """Amounts + checked marks use the injected palette, never literal colors (4.2)."""
    from expense.tui.theme import PALETTE

    rows = [
        ("t1", "Alquiler", -250000, "2026-04-03", "Vivienda"),
        ("t2", "Refund", 5620, "2026-04-09", ""),
    ]
    table = CheckList(rows, checked=["t1"])._build()  # app-less, PALETTE palette
    marks, amounts = table.columns[0]._cells, table.columns[2]._cells
    assert marks[0].style == PALETTE.success and marks[2].style == "dim"  # [x] vs [ ]
    assert amounts[0].style == PALETTE.error  # -2,500.00
    assert amounts[2].style == PALETTE.success  # +56.20


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
ASSIGNED = [
    {
        "id": "t1",
        "title": "Alquiler",
        "amount_cents": -250000,
        "date": "2026-04-03",
        "reconciliation_id": "r1",
        "category_id": "c1",
        "hashtag_ids": ["h1"],
    },
]
AVAILABLE = [
    {
        "id": "t2",
        "title": "Gasolina",
        "amount_cents": -12000,
        "date": "2026-04-08",
        "reconciliation_id": None,
        "category_id": None,
        "hashtag_ids": [],
    },
    {
        "id": "t3",
        "title": "Other batch",
        "amount_cents": -5000,
        "date": "2026-04-09",
        "reconciliation_id": "rX",
    },  # belongs elsewhere → excluded
]


def _patch(monkeypatch):
    """Screen-specific patches; the client/config seams come from fake_client."""

    def fake_fetch(cfg, **k):
        if k.get("reconciliation") == "r1":
            return {"items": ASSIGNED}
        if k.get("account") == "acc1":
            return {"items": AVAILABLE}
        return {"items": []}

    monkeypatch.setattr("expense.reads.fetch_transactions", fake_fetch)
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc1": "BCP PEN"}
    )
    monkeypatch.setattr("expense.tui.screens.reconciliations.load_category_name_map", lambda: CATS)
    monkeypatch.setattr("expense.tui.screens.reconciliations.load_hashtag_name_map", lambda: TAGS)


async def _wait_list(screen, pilot):
    await wait_for(pilot, lambda: screen._list is not None)


def test_available_read_takes_the_periods_days_byte_for_byte(fake_client, monkeypatch):
    """The tick-list's in-range read passes the period's own days to the
    engine's day filters, unconverted: a bare `date_to` is the whole last day
    (contract: GET /v1/transactions), so rows dated on the 30th are offered too."""
    _patch(monkeypatch)
    calls: list = []
    from expense import reads

    fake = reads.fetch_transactions  # _patch's fake

    def spy(cfg, **k):
        assert "offset" not in k
        calls.append(k)
        return fake(cfg, **k)

    monkeypatch.setattr("expense.reads.fetch_transactions", spy)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        in_range = [k for k in calls if k.get("account") == "acc1"]
        assert len(in_range) == 1
        assert in_range[0]["date_from"] == "2026-04-01"
        assert in_range[0]["date_to"] == "2026-04-30"

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
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        cl = screen._list
        keys = [r[0] for r in cl._rows]
        assert keys == ["t1", "t2"]  # t3 (other batch) excluded
        assert cl.checked == {"t1"}  # assigned one is checked
        assert not cl._read_only

    run_app(scenario)


def test_toggle_puts_reconciliation_id(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        # toggle the available row (t2) into the batch
        screen._list._cursor = 1
        screen._list.action_toggle()
        await wait_for(pilot, lambda: fake_client.puts)
        assert fake_client.puts == [("/transactions/t2", {"reconciliation_id": "r1"})]

    run_app(scenario)


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
        screen._list._cursor = 0
        screen._list.action_toggle()  # t1 → out of the batch
        screen._list._cursor = 1
        screen._list.action_toggle()  # t2 → into the batch
        await wait_for(pilot, lambda: len(fake_client.puts) == 2)

    run_app(scenario)
    assert max_active == 1  # serialized: never two PUTs in flight
    assert fake_client.puts == [
        ("/transactions/t1", {"reconciliation_id": None}),
        ("/transactions/t2", {"reconciliation_id": "r1"}),
    ]


def test_toggle_error_drops_queued_intents_and_resyncs(fake_client, monkeypatch):
    """A failed toggle clears the queue and resyncs instead of applying stale intents (3.2)."""
    from expense.errors import EngineError as _EngineError

    _patch(monkeypatch)
    fake_client.errors["PUT"] = _EngineError("CONFLICT", "Transaction is locked.", None, 409, {})
    notices: list = []
    monkeypatch.setattr(
        ReconciliationDetailScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        screen._list._cursor = 0
        screen._list.action_toggle()
        screen._list._cursor = 1
        screen._list.action_toggle()  # queued behind the failing PUT
        await wait_for(pilot, lambda: notices)
        await pilot.pause()  # let the queue drain settle, then assert a non-event
        assert not screen._write_queue  # stale intent dropped, not sent
        assert len(fake_client.puts) == 1

    run_app(scenario)


def test_toggle_burst_puts_every_toggle_in_order(fake_client, monkeypatch):
    """A burst of toggles sends one PUT per toggle, in the order pressed —
    including a re-toggle of the same row (t1 out, then back in)."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        screen._list._cursor = 0
        screen._list.action_toggle()  # t1 → out
        screen._list._cursor = 1
        screen._list.action_toggle()  # t2 → in
        screen._list._cursor = 0
        screen._list.action_toggle()  # t1 → back in
        await wait_for(pilot, lambda: len(fake_client.puts) == 3)
        assert fake_client.puts == [
            ("/transactions/t1", {"reconciliation_id": None}),
            ("/transactions/t2", {"reconciliation_id": "r1"}),
            ("/transactions/t1", {"reconciliation_id": "r1"}),
        ]

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
    fresh_row = {
        "id": "t9",
        "title": "Fresh",
        "amount_cents": -100,
        "date": "2026-04-10",
        "reconciliation_id": "r1",
    }

    def fake_fetch(cfg, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            time.sleep(0.15)  # the superseded first load finishes last
            return {"items": ASSIGNED}
        return {"items": [*ASSIGNED, fresh_row]}

    monkeypatch.setattr("expense.reads.fetch_transactions", fake_fetch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(completed))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: calls["n"] >= 1)
        screen._load_txns()  # supersedes the slow mount-time load
        await wait_for(pilot, lambda: screen._list is not None and len(screen._list._rows) == 2)
        await pilot.pause(0.25)  # window for the cancelled worker to (not) paint
        assert len(screen.query(CheckList)) == 1
        assert [r[0] for r in screen._list._rows] == ["t1", "t9"]

    run_app(scenario)


def test_fetch_all_txns_pages_at_engine_cap(monkeypatch):
    """The detail fetch never exceeds the engine's 200-row limit cap
    and follows `next_cursor` until it is null — never an offset."""
    from expense.tui.screens.reconciliations import _fetch_all_txns

    calls: list[tuple[int, str | None]] = []

    def fake_fetch(cfg, *, limit, after=None, **kw):
        assert "offset" not in kw
        calls.append((limit, after))
        if after is None:  # one full page with a cursor, then the last one
            return cursor_page([{"id": f"t{i}"} for i in range(200)], next_cursor="c1")
        return cursor_page([{"id": f"t{200 + i}"} for i in range(40)])

    monkeypatch.setattr("expense.reads.fetch_transactions", fake_fetch)
    rows = _fetch_all_txns(object(), reconciliation="r1")
    assert calls == [(200, None), (200, "c1")]
    assert [r["id"] for r in rows] == [f"t{i}" for i in range(240)]


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
        assert [r[0] for r in screen._list._rows] == ["t1"]  # only batch txns

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


def test_complete_with_zero_assigned_surfaces_engine_422(fake_client, monkeypatch):
    """No ≥1-assigned pre-guard: the confirm opens, the POST
    fires, and the engine's 422 message toasts."""
    _patch(monkeypatch)

    def fake_fetch(cfg, **k):  # nothing assigned to r1
        if k.get("account") == "acc1":
            return {"items": AVAILABLE}
        return {"items": []}

    monkeypatch.setattr("expense.reads.fetch_transactions", fake_fetch)
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

    monkeypatch.setattr("expense.reads.fetch_transactions", boom)
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
