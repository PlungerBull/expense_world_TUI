"""Phase 2 reconciliations tests — list rows + new-batch form (fake client)."""

from textual.widgets import Input

from expense.tui.screens.reconciliations import (
    NewReconciliationScreen,
    ReconciliationsScreen,
)
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import page, run_app, wait_for, wait_for_list

ITEMS = [
    {
        "id": "r1",
        "account_id": "acc1",
        "name": "March 2026",
        "date_start": "2026-03-01T00:00:00Z",
        "date_end": "2026-03-31T00:00:00Z",
        "beginning_balance_cents": 1200000,
        "ending_balance_cents": 958000,
        "difference_cents": 0,
        "status": 2,
    },
    {
        "id": "r2",
        "account_id": "acc2",
        "name": "April 2026",
        "beginning_balance_cents": 958000,
        "ending_balance_cents": None,
        "difference_cents": -3500,
        "status": 1,
    },
]


def test_batch_rows_format():
    from expense.tui.screens.reconciliations import batch_rows

    rows = batch_rows(ITEMS)
    assert rows[0][0] == "r1"
    cells = rows[0][1]
    assert cells[0] == "March 2026"
    assert cells[1] == "2026-03-01 → 2026-03-31"
    assert cells[2] == "12,000.00" and cells[3] == "9,580.00"
    # a balanced batch shows a dim em dash, not 0.00 (Phase 3 sketch, option H)
    assert str(cells[4]) == "—" and cells[5] == "completed"
    assert rows[0][2] == "dim"  # completed dimmed
    # draft, open-ended period, null end balance — and a batch that is off by
    # -35.00 prints the signed figure
    off = batch_rows([ITEMS[1]])[0][1]
    assert off[5] == "draft"
    assert off[1] == "—"
    assert str(off[4]) == "-35.00"


def _patch(monkeypatch):
    """Screen-specific patches; the client/config seams come from fake_client."""
    monkeypatch.setattr(
        "expense.commands.accounts_cmd.fetch_accounts",
        lambda *a, **k: [
            {"id": "acc1", "name": "BCP PEN", "currency_code": "PEN"},
            {"id": "acc2", "name": "Interbank USD", "currency_code": "USD"},
        ],
    )


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


async def _wait_accounts(screen, pilot):
    await wait_for(pilot, lambda: screen._accounts)


def test_new_reconciliation_always_sends_begin_never_source(fake_client, monkeypatch):
    """One straight path since the 2026-08-06 de-chaining: begin is always typed,
    and `beginning_balance_source` must never be sent (request schemas are
    extra="forbid", so shipping it is a 422)."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewReconciliationScreen()
        await app.push_screen(screen)
        await _wait_accounts(screen, pilot)
        _enter(screen, "April 2026")  # name
        _enter(screen, "BCP")  # account → acc1
        _enter(screen, "2026-04-01")  # date_start (required)
        _enter(screen, "")  # date_end skip
        _enter(screen, "9580.00")  # begin
        _enter(screen, "9460.00")  # end → submits
        await wait_for(pilot, lambda: fake_client.posts)
        path, body = fake_client.posts[0]
        assert path == "/reconciliations"
        assert body["account_id"] == "acc1" and body["name"] == "April 2026"
        assert body["beginning_balance_cents"] == 958000
        assert body["ending_balance_cents"] == 946000
        assert "beginning_balance_source" not in body
        assert "sort_order" not in body

    run_app(scenario)


def test_new_reconciliation_date_start_is_required(fake_client, monkeypatch):
    """date_start orders the batch now, so an empty enter is refused in place
    rather than silently creating an unorderable batch."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewReconciliationScreen()
        await app.push_screen(screen)
        await _wait_accounts(screen, pilot)
        _enter(screen, "April 2026")  # name
        _enter(screen, "BCP")  # account → acc1
        _enter(screen, "")  # date_start → rejected, stays put
        assert screen._key == "date_start"
        assert "date_start" in screen._required()
        _enter(screen, "2026-04-01")
        assert screen._key == "date_end"
        await pilot.pause()
        assert not fake_client.posts

    run_app(scenario)


def _patch_browse(monkeypatch):
    """Two accounts, one batch each — the browse screen's standard fixture."""
    monkeypatch.setattr(
        "expense.commands.reconcile_cmd.fetch_reconciliations",
        lambda *a, **k: page(ITEMS, total=2),
    )
    monkeypatch.setattr(
        "expense.commands.accounts_cmd.fetch_accounts",
        lambda *a, **k: [
            {"id": "acc1", "name": "BCP PEN", "currency_code": "PEN", "current_balance_cents": 100},
            {"id": "acc2", "name": "Interbank USD", "currency_code": "USD"},
        ],
    )
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())


def test_reconciliations_browse_account_first(monkeypatch):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        # account focus: first account (acc1) selected → its batch (r1) shown below
        assert screen._mode == "accts"
        assert set(screen._by_id) == {"r1"}
        # arrow to the second account → batch list follows to acc2's batch (r2).
        # Wait on the state, not a fixed sleep: the Highlighted message
        # bubbles through several widget pumps and a 50ms nap lost that race
        # on CI (flaked 2026-07-13 after the adaptive-rows load deferral).
        screen._accts_list.action_move(1)
        await wait_for(pilot, lambda: screen._acct_idx == 1)
        assert set(screen._by_id) == {"r2"}

    run_app(scenario)


def test_highlight_from_batches_pane_does_not_switch_account(monkeypatch):
    """A Highlighted sourced from the batches pane (Tab/click focus, no select)
    must not overwrite the selected account while in accounts mode — `n` would
    then create the new batch under the wrong account (backlog 6.2c)."""
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen._mode == "accts" and screen._acct_idx == 0
        # from the *batches* list → ignored
        screen.on_cursor_list_highlighted(CursorList.Highlighted(screen._batch_list, "r1", 1))
        assert screen._acct_idx == 0
        assert set(screen._by_id) == {"r1"}
        # the same event from the *accounts* list still drives the panes
        screen.on_cursor_list_highlighted(CursorList.Highlighted(screen._accts_list, "acc2", 1))
        assert screen._acct_idx == 1
        assert set(screen._by_id) == {"r2"}

    run_app(scenario)


def test_reconciliations_list_pages_past_engine_cap(monkeypatch):
    """The browse fetch pages through the whole collection — a batch past the
    default page must not vanish from the account's pane (backlog 6.2b, list
    half)."""
    total = 201
    all_items = [
        {"id": f"r{i}", "account_id": "acc1", "name": f"B{i}", "status": 1} for i in range(total)
    ]

    def paged(cfg, *, limit=None, offset=None, **k):
        lo = offset or 0
        return page(all_items[lo : lo + (limit or 100)], total=total)

    monkeypatch.setattr("expense.commands.reconcile_cmd.fetch_reconciliations", paged)
    monkeypatch.setattr(
        "expense.commands.accounts_cmd.fetch_accounts",
        lambda *a, **k: [{"id": "acc1", "name": "BCP PEN", "currency_code": "PEN"}],
    )
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert len(screen._recons) == total  # both pages collected
        assert len(screen._batches) == total  # every batch for the account

    run_app(scenario)


def test_batches_ordered_by_statement_start_date_nulls_last():
    """The pane mirrors the engine's account-scoped key (date_start ASC NULLS
    LAST, created_at ASC). The bulk fetch is unscoped, and *that* list is
    created_at DESC — so without this the rows would sit in creation order."""
    from expense.tui.screens.reconciliations import _batch_sort_key

    rows = [
        {"id": "undated", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "may", "date_start": "2026-05-01T00:00:00Z", "created_at": "2026-01-02T00:00:00Z"},
        {"id": "march", "date_start": "2026-03-01T00:00:00Z", "created_at": "2026-07-09T00:00:00Z"},
        {"id": "april", "date_start": "2026-04-01T00:00:00Z", "created_at": "2026-01-03T00:00:00Z"},
    ]
    assert [r["id"] for r in sorted(rows, key=_batch_sort_key)] == [
        "march",
        "april",
        "may",
        "undated",
    ]


def test_new_reconciliation_from_account_drops_account_field():
    screen = NewReconciliationScreen(account_id="acc1", account_name="BCP PEN")
    assert "account" not in screen._sequence()  # account preset from browse
    assert screen._values["account"] == "acc1"
    assert screen.crumb == ("Reconciliations", "BCP PEN", "New")


def test_new_reconciliation_fetch_error_notifies_not_crash(fake_client, monkeypatch):
    """An engine/config error in _load_accounts must not exit the app (backlog 1.3)."""

    def boom(*a, **k):
        raise RuntimeError("engine down")

    monkeypatch.setattr("expense.commands.accounts_cmd.fetch_accounts", boom)
    notices: list = []
    monkeypatch.setattr(
        NewReconciliationScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = NewReconciliationScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: notices)
        assert notices and "engine down" in notices[0]
        assert app.is_running
        assert app.screen is screen

    run_app(scenario)


def test_the_account_picker_matches_through_accents_like_every_other_one():
    """This picker was the last one on a plain `.lower()`, so `bcp credito`
    found no `BCP Crédito` here while the same text matched in the LOG bar and
    every modal. One matcher — `quickadd.names.matches` — for all of them."""
    screen = NewReconciliationScreen()
    screen._accounts = [
        ("acc1", "BCP Crédito", "PEN"),
        ("acc2", "Interbank USD", "USD"),
    ]
    screen._current = screen._sequence().index("account")  # `_key` is derived

    for typed in ("credito", "Crédito", "CRÉDITO", "crédito"):
        screen._recompute(typed)
        assert [a[0] for a in screen._suggestions] == ["acc1"], typed

    screen._recompute("interbank")
    assert [a[0] for a in screen._suggestions] == ["acc2"]


# ---- the unfiled pane (`u`, 2026-09-22) -------------------------------------
# Shape: mockups/expense-world-rows-in-no-batch.html. Reconciliation work stays
# in the reconciliation view, so `u` swaps the LOWER PANE of this screen — it
# does not push a filtered ledger, and it does not touch the account cursor.
UNFILED = [
    # the engine answers date DESC; the pane reads oldest first
    {"id": "t3", "date": "2026-03-20T12:00:00-05:00", "title": "RAPPI", "amount_cents": -3890},
    {"id": "t2", "date": "2026-03-10T12:00:00-05:00", "title": "UBER", "amount_cents": -2450},
    {"id": "t1", "date": "2026-01-04T12:00:00-05:00", "title": "NETFLIX", "amount_cents": -4490},
]


def test_blocking_windows_takes_this_account_and_needs_both_dates():
    from expense.tui.screens.reconciliations import blocking_windows

    assert blocking_windows(ITEMS, "acc1") == [("2026-03-01", "2026-03-31", "March 2026")]
    # r2 is acc2's and carries no dates at all — a window needs both ends
    assert blocking_windows(ITEMS, "acc2") == []


def test_unfiled_rows_read_oldest_first_and_flag_the_blocking_ones():
    from expense.tui.screens.reconciliations import blocking_windows, unfiled_rows

    windows = blocking_windows(ITEMS, "acc1")
    rows = unfiled_rows(UNFILED, {}, windows)
    assert [r[0] for r in rows] == ["t1", "t2", "t3"]  # reversed into date order
    flags = [r[1][0] for r in rows]
    # January is in no window; both March rows sit inside 'March 2026'
    assert flags == ["", "!", "!"]
    assert [r[1][1] for r in rows] == ["2026-01-04", "2026-03-10", "2026-03-20"]


def test_unfiled_offset_asks_for_the_last_page():
    """`GET /transactions` is always date DESC and takes no sort parameter, so
    the oldest rows are the tail — the pane asks for them by offset."""
    from expense.tui.screens.reconciliations import unfiled_offset

    assert unfiled_offset(3553, 40) == 3513
    assert unfiled_offset(12, 40) == 0  # fewer than one page: no offset at all


def _patch_unfiled(monkeypatch, items=None, total=None):
    calls: list = []
    rows = UNFILED if items is None else items

    def fetch(_cfg, **kw):
        calls.append(kw)
        count = len(rows) if total is None else total
        if kw.get("limit") == 1:
            return page(rows[:1], total=count, limit=1)
        return page(rows, total=count, limit=kw.get("limit") or 40, offset=kw.get("offset") or 0)

    monkeypatch.setattr("expense.commands.transactions_cmd.fetch_transactions", fetch)
    monkeypatch.setattr("expense.tui.screens.reconciliations.load_category_name_map", lambda: {})
    return calls


def test_u_swaps_the_lower_pane_and_leaves_the_account_cursor_alone(monkeypatch):
    _patch_browse(monkeypatch)
    calls = _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen._mode == "accts" and screen._acct_idx == 0

        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        # the account cursor never moved, and no screen was pushed
        assert screen._acct_idx == 0 and app.screen is screen
        # oldest first, in the lower pane, under its own column labels
        assert [r.key for r in screen._batch_list._rows] == ["t1", "t2", "t3"]
        assert screen._batch_list._headers[1] == "Date"
        assert "In no batch · BCP PEN" in (screen._batch_list._caption or "")
        # the request was the engine's own filter, scoped to this account
        assert calls and calls[-1]["account"] == "acc1" and calls[-1]["unreconciled"] is True

    run_app(scenario)


def test_esc_swaps_the_pane_back_to_the_batches(monkeypatch):
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._unfiled)

        await pilot.press("escape")
        await wait_for(pilot, lambda: screen._mode != "unfiled")
        assert app.screen is screen  # esc swapped the pane, it did not pop the screen
        assert [r.key for r in screen._batch_list._rows] == ["r1"]  # acc1's batch is back
        assert screen._batch_list._headers[0] == "Name"

    run_app(scenario)


def test_the_pane_asks_for_the_oldest_page_when_there_are_many(monkeypatch):
    _patch_browse(monkeypatch)
    calls = _patch_unfiled(monkeypatch, total=3553)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._unfiled)
        # one probe for the count, then the tail — never the whole ledger
        assert [c.get("limit") for c in calls] == [1, 40]
        assert calls[-1]["offset"] == 3513
        assert "3553 rows · the 3 oldest" in (screen._batch_list._caption or "")

    run_app(scenario)


def test_d_deletes_the_cursor_row_after_a_confirm(monkeypatch, fake_client):
    from expense.tui.screens.modals import ConfirmModal

    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._unfiled)

        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.deletes)
        assert fake_client.deletes == ["/transactions/t1"]  # the cursor row, oldest first

    run_app(scenario)


def test_d_does_nothing_outside_the_unfiled_pane(monkeypatch, fake_client):
    """`d` is the pane's key, not the screen's: on the batches it must not fire
    — one key per job, and a batch's own delete lives on the batch screen."""
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("d")
        await pilot.pause()
        assert app.screen is screen  # no confirm opened
        assert not fake_client.deletes

    run_app(scenario)
