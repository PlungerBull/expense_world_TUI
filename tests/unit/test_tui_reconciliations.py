"""Reconciliations tests — list rows + new-batch form (fake client)."""

from textual.widgets import Input

from expense.tui.screens.reconciliations import (
    NewReconciliationScreen,
    ReconciliationsScreen,
)
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import cursor_page, run_app, wait_for, wait_for_list, whole

ITEMS = [
    {
        "id": "r1",
        "account_id": "acc1",
        "name": "March 2026",
        "date_start": "2026-03-01",
        "date_end": "2026-03-31",
        "beginning_balance_cents": 1200000,
        "ending_balance_cents": 958000,
        "difference_cents": 0,
        "status": 2,
    },
    {
        "id": "r2",
        "account_id": "acc2",
        "name": "April 2026",
        "date_start": "2026-04-01",
        "date_end": "2026-04-30",
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
    # a balanced batch shows a dim em dash, not 0.00
    assert str(cells[4]) == "—" and cells[5] == "completed"
    assert rows[0][2] == "dim"  # completed dimmed
    # draft, null end balance — and a batch that is off by -35.00 prints the
    # signed figure
    off = batch_rows([ITEMS[1]])[0][1]
    assert off[5] == "draft"
    assert off[1] == "2026-04-01 → 2026-04-30"
    assert str(off[4]) == "-35.00"


def _patch(monkeypatch):
    """Screen-specific patches; the client/config seams come from fake_client."""
    monkeypatch.setattr(
        "expense.commands.accounts_cmd.fetch_accounts",
        lambda *a, **k: whole(
            [
                {"id": "acc1", "name": "BCP PEN", "currency_code": "PEN"},
                {"id": "acc2", "name": "Interbank USD", "currency_code": "USD"},
            ]
        ),
    )


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


async def _wait_accounts(screen, pilot):
    await wait_for(pilot, lambda: screen._accounts)


def test_new_reconciliation_always_sends_begin_never_source(fake_client, monkeypatch):
    """One straight path: begin is always typed,
    and `beginning_balance_source` must never be sent: the engine forbids it,
    so shipping it is a 422 (contract: POST /v1/reconciliations)."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewReconciliationScreen()
        await app.push_screen(screen)
        await _wait_accounts(screen, pilot)
        _enter(screen, "April 2026")  # name
        _enter(screen, "BCP")  # account → acc1
        _enter(screen, "2026-04-01")  # date_start (required)
        _enter(screen, "2026-04-30")  # date_end (required)
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


def test_new_reconciliation_sends_the_typed_days_and_refuses_other_shapes(fake_client, monkeypatch):
    """A period's ends are calendar days on the wire (contract: "Date inputs"): the
    typed text goes out unconverted, and any shape the engine would 422 is
    refused at the field instead — unpadded, compact, day-first, not a day."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewReconciliationScreen(account_id="acc1", account_name="BCP PEN")
        await app.push_screen(screen)
        _enter(screen, "August 2026")  # name
        for bad in ("2026-8-01", "20260801", "01/08/2026", "2026-02-30", "2026-08-01T00:00"):
            _enter(screen, bad)
            assert screen._key == "date_start", bad
        _enter(screen, "2026-08-01")
        for bad in ("2026-8-31", "20260831", "31/08/2026"):
            _enter(screen, bad)
            assert screen._key == "date_end", bad
        _enter(screen, "2026-08-31")
        _enter(screen, "0")  # begin
        _enter(screen, "")  # end → submits
        await wait_for(pilot, lambda: fake_client.posts)
        _path, body = fake_client.posts[0]
        assert body["date_start"] == "2026-08-01"
        assert body["date_end"] == "2026-08-31"

    run_app(scenario)


def test_new_reconciliation_date_end_is_required(fake_client, monkeypatch):
    """A period with no last day can never be completed,
    so an empty enter on DATE END is refused in place, as on DATE START."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewReconciliationScreen(account_id="acc1", account_name="BCP PEN")
        await app.push_screen(screen)
        _enter(screen, "August 2026")
        _enter(screen, "2026-08-01")
        _enter(screen, "")  # date_end → rejected, stays put
        assert screen._key == "date_end"
        assert "date_end" in screen._required()
        await pilot.pause()
        assert not fake_client.posts

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


def _patch_browse(monkeypatch, items=None, fail=False):
    """Two accounts, one reconciliation each — the browse screen's standard
    fixture. The fake reads like the engine: one account at a time (the account
    is required), the list whole, never paged. Returns the accounts it was
    asked for, in order."""
    reads: list = []
    rows = ITEMS if items is None else items

    def fetch(_cfg, *, account_id, **kw):
        assert "limit" not in kw and "offset" not in kw, "the engine refuses paging here"
        reads.append(account_id)
        if fail:
            raise RuntimeError("reconciliations unavailable")
        return whole([r for r in rows if r.get("account_id") == account_id])

    monkeypatch.setattr("expense.commands.reconcile_cmd.fetch_reconciliations", fetch)
    monkeypatch.setattr(
        "expense.commands.accounts_cmd.fetch_accounts",
        lambda *a, **k: whole(
            [
                {
                    "id": "acc1",
                    "name": "BCP PEN",
                    "currency_code": "PEN",
                    "current_balance_cents": 100,
                },
                {"id": "acc2", "name": "Interbank USD", "currency_code": "USD"},
            ]
        ),
    )
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    return reads


def _footer_keys(app) -> set:
    """The keys the footer shows right now."""
    return {key for key, active in app.screen.active_bindings.items() if active.enabled}


def _crumb(screen) -> tuple:
    from expense.tui.widgets.header import Breadcrumb

    return screen.query_one("#crumb", Breadcrumb)._trail


async def _open_panel(pilot, app, *, down: int = 0):
    """Open the browse, move the account cursor `down` rows, press `⏎`."""
    screen = ReconciliationsScreen()
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    for _ in range(down):
        screen._accts_list.action_move(1)
    await wait_for(pilot, lambda: screen._acct_idx == down)
    await pilot.press("enter")
    await wait_for(pilot, lambda: screen._mode == "batches")
    return screen


def test_the_browse_opens_on_the_accounts_alone_and_reads_no_reconciliations(monkeypatch):
    reads = _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen._mode == "accts"
        assert screen._batch_list is None  # no lower panel at all
        assert reads == []  # nothing is read until ⏎
        # alone, the account list takes the whole height; the panel halves it
        alone = screen.pane_rows()
        screen._open_aid = "acc1"
        assert screen.pane_rows() < alone
        screen._open_aid = None
        assert _crumb(screen) == ("Capture & ledger", "Reconciliations")
        # moving the account cursor costs no read either
        screen._accts_list.action_move(1)
        await wait_for(pilot, lambda: screen._acct_idx == 1)
        await pilot.pause()
        assert reads == []

    run_app(scenario)


def test_enter_reads_that_account_and_opens_the_panel_with_the_cursor_in_it(monkeypatch):
    reads = _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app, down=1)
        assert reads == ["acc2"]  # that account, and only that one
        assert [r.key for r in screen._batch_list._rows] == ["r2"]
        assert screen._batch_list.has_focus
        assert "Reconciliations · Interbank USD" in (screen._batch_list._caption or "")
        assert "oldest → newest" in (screen._batch_list._caption or "")
        assert _crumb(screen) == ("Capture & ledger", "Reconciliations", "Interbank USD")
        # the open account keeps a ▸ so you can see whose panel this is
        names = [str(r.cells[0]) for r in screen._accts_list._rows]
        assert names == ["BCP PEN", "▸ Interbank USD"]

    run_app(scenario)


def test_an_account_with_no_reconciliations_says_so_in_the_panel(monkeypatch):
    _patch_browse(monkeypatch, items=[])

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        assert screen._batch_list._rows == []
        assert screen._batch_list._empty == "none yet · n to create one"

    run_app(scenario)


def test_the_panel_keeps_the_order_the_engine_sends(monkeypatch):
    """The account's list arrives in period order (`date_start ASC,
    created_at ASC`); the screen does not re-sort it. Served out of date order
    on purpose, so a re-sort would show."""
    served = [
        {
            "id": "b-march",
            "account_id": "acc1",
            "name": "March",
            "status": 1,
            "date_start": "2026-03-01",
            "date_end": "2026-03-31",
        },
        {
            "id": "b-april",
            "account_id": "acc1",
            "name": "April",
            "status": 1,
            "date_start": "2026-04-01",
            "date_end": "2026-04-30",
        },
        {
            "id": "b-feb",
            "account_id": "acc1",
            "name": "February",
            "status": 1,
            "date_start": "2026-02-01",
            "date_end": "2026-02-28",
        },
    ]
    _patch_browse(monkeypatch, items=served)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        assert [r.key for r in screen._batch_list._rows] == ["b-march", "b-april", "b-feb"]

    run_app(scenario)


def test_a_failed_read_leaves_the_panel_closed(monkeypatch):
    reads = _patch_browse(monkeypatch, fail=True)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("enter")
        await wait_for(pilot, lambda: reads)
        await pilot.pause()
        assert screen._mode == "accts" and screen._batch_list is None
        assert _crumb(screen) == ("Capture & ledger", "Reconciliations")

    run_app(scenario)


def test_u_works_only_with_a_panel_open(monkeypatch):
    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert "u" not in _footer_keys(app)  # not offered on the plain list
        await pilot.press("u")
        await pilot.pause()
        assert screen._mode == "accts" and not calls
        await pilot.press("enter")
        await wait_for(pilot, lambda: screen._mode == "batches")
        assert "u" in _footer_keys(app)

    run_app(scenario)


def test_enter_reads_open_on_reconciliations_and_edit_on_rows_in_no_batch(monkeypatch):
    """One panel, two things listed, two labels for `⏎`."""
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)

    def enter_label(app):
        active = app.screen.active_bindings.get("enter")
        return active.binding.description if active and active.enabled else None

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        assert enter_label(app) == "Open"
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        assert enter_label(app) == "Edit"
        await pilot.press("escape")
        await wait_for(pilot, lambda: screen._mode == "batches")
        assert enter_label(app) == "Open"

    run_app(scenario)


def test_esc_closes_the_panel_then_leaves_the_screen(monkeypatch):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.press("escape")
        await wait_for(pilot, lambda: screen._mode == "accts")
        assert app.screen is screen  # the panel closed; the screen stayed
        assert screen._batch_list is None and screen._accts_list.has_focus
        assert _crumb(screen) == ("Capture & ledger", "Reconciliations")
        assert [str(r.cells[0]) for r in screen._accts_list._rows][0] == "BCP PEN"
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is not screen)

    run_app(scenario)


def test_highlight_from_the_panel_does_not_switch_account(monkeypatch):
    """A Highlighted sourced from the panel (Tab/click focus, no select) must
    not move the account cursor — `n` would then create under the wrong one."""
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        screen.on_cursor_list_highlighted(CursorList.Highlighted(screen._batch_list, "r1", 1))
        assert screen._acct_idx == 0

    run_app(scenario)


def test_coming_back_from_a_reconciliation_keeps_the_panel_on_the_same_row(monkeypatch):
    from expense.tui.screens.reconciliations import ReconciliationDetailScreen

    two = [
        {
            "id": "b1",
            "account_id": "acc1",
            "name": "March",
            "date_start": "2026-03-01",
            "date_end": "2026-03-31",
            "status": 2,
        },
        {
            "id": "b2",
            "account_id": "acc1",
            "name": "April",
            "date_start": "2026-04-01",
            "date_end": "2026-04-30",
            "status": 2,
        },
    ]
    reads = _patch_browse(monkeypatch, items=two)
    # the working screen's own reads are not what this test is about
    monkeypatch.setattr(ReconciliationDetailScreen, "_load_txns", lambda self, **k: None)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        screen._batch_list.action_move(1)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ReconciliationDetailScreen))
        app.screen.dismiss()
        await wait_for(pilot, lambda: len(reads) == 2 and screen._mode == "batches")
        await wait_for(pilot, lambda: screen._batch_list is not None)
        assert reads == ["acc1", "acc1"]  # the open account, re-read
        assert screen._batch_list.cursor_key == "b2"
        assert screen._batch_list.has_focus

    run_app(scenario)


def test_n_on_the_plain_list_saves_into_that_accounts_open_panel(monkeypatch):
    """`n` with no panel open uses the account under the cursor; saved, that
    account's panel opens with the cursor on the new one."""
    rows = [dict(r) for r in ITEMS]
    reads = _patch_browse(monkeypatch, items=rows)

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        screen._accts_list.action_move(1)
        await wait_for(pilot, lambda: screen._acct_idx == 1)
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, NewReconciliationScreen))
        form = app.screen
        assert form._values["account"] == "acc2"  # the account under the cursor
        rows.append(
            {
                "id": "new-1",
                "account_id": "acc2",
                "name": "May 2026",
                "date_start": "2026-05-01",
                "date_end": "2026-05-31",
                "status": 1,
            }
        )
        form.dismiss("new-1")  # what `_done` hands back after the POST
        await wait_for(pilot, lambda: screen._batch_list is not None)
        assert reads == ["acc2"]
        assert screen._mode == "batches"
        assert screen._batch_list.cursor_key == "new-1"
        assert _crumb(screen)[-1] == "Interbank USD"

    run_app(scenario)


def test_the_form_hands_back_the_id_it_created(fake_client, monkeypatch):
    """The id is minted client-side in `_payload`; `_done` returns it."""
    screen = NewReconciliationScreen(account_id="acc1", account_name="BCP PEN")
    screen._values.update(
        {"name": "May", "date_start": "2026-05-01", "date_end": "2026-05-31", "begin": 0}
    )
    payload = screen._payload()
    handed: list = []
    monkeypatch.setattr(screen, "dismiss", lambda result=None: handed.append(result))
    monkeypatch.setattr(screen, "notify", lambda *a, **k: None)
    screen._done()
    assert handed == [payload["id"]]


def test_new_reconciliation_from_account_drops_account_field():
    screen = NewReconciliationScreen(account_id="acc1", account_name="BCP PEN")
    assert "account" not in screen._sequence()  # account preset from browse
    assert screen._values["account"] == "acc1"
    assert screen.crumb == ("Reconciliations", "BCP PEN", "New")


def test_new_reconciliation_fetch_error_notifies_not_crash(fake_client, monkeypatch):
    """An engine/config error in _load_accounts must not exit the app."""

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


# ---- the unfiled pane (`u`) -------------------------------------------------
# Reconciliation work stays
# in the reconciliation view, so `u` swaps the LOWER PANE of this screen — it
# does not push a filtered ledger, and it does not touch the account cursor.
UNFILED = [
    # the engine answers in the order asked for: `sort=date_asc`, oldest first
    {"id": "t1", "date": "2026-01-04T12:00:00-05:00", "title": "NETFLIX", "amount_cents": -4490},
    {"id": "t2", "date": "2026-03-10T12:00:00-05:00", "title": "UBER", "amount_cents": -2450},
    {"id": "t3", "date": "2026-03-20T12:00:00-05:00", "title": "RAPPI", "amount_cents": -3890},
]


def test_blocking_windows_takes_only_this_accounts_periods():
    from expense.tui.screens.reconciliations import blocking_windows

    assert blocking_windows(ITEMS, "acc1") == [("2026-03-01", "2026-03-31", "March 2026")]
    assert blocking_windows(ITEMS, "acc2") == [("2026-04-01", "2026-04-30", "April 2026")]


def test_unfiled_rows_keep_the_engine_order_and_flag_the_blocking_ones():
    from expense.tui.screens.reconciliations import blocking_windows, unfiled_rows

    windows = blocking_windows(ITEMS, "acc1")
    rows = unfiled_rows(UNFILED, {}, windows)
    assert [r[0] for r in rows] == ["t1", "t2", "t3"]  # as the engine sent them
    flags = [r[1][0] for r in rows]
    # January is in no window; both March rows sit inside 'March 2026'
    assert flags == ["", "!", "!"]
    assert [r[1][1] for r in rows] == ["2026-01-04", "2026-03-10", "2026-03-20"]


def _txn(n: int) -> dict:
    return {"id": f"t{n}", "date": f"2025-01-{n:02d}T12:00:00-05:00", "title": f"ROW {n}"}


def _patch_unfiled(monkeypatch, items=None, total=None, count_fails=False):
    """A cursor-paged fake: it refuses `offset`, serves `items` in slices of the
    requested `limit`, and hands back `c<next index>` as the cursor."""
    calls: list = []
    counts: list = []
    rows = UNFILED if items is None else items

    def fetch(_cfg, *, limit=None, after=None, **kw):
        assert "offset" not in kw, "the engine refuses offset"
        calls.append({"limit": limit, "after": after, **kw})
        start = int(after[1:]) if after else 0
        end = start + (limit or 50)
        nxt = f"c{end}" if end < len(rows) else None
        return cursor_page(rows[start:end], next_cursor=nxt, limit=limit or 50)

    def count(_cfg, **kw):
        counts.append(kw)
        if count_fails:
            raise RuntimeError("count unavailable")
        return len(rows) if total is None else total

    monkeypatch.setattr("expense.commands.transactions_cmd.fetch_transactions", fetch)
    monkeypatch.setattr("expense.commands.transactions_cmd.count_transactions", count)
    monkeypatch.setattr("expense.tui.screens.reconciliations.load_category_name_map", lambda: {})
    return calls, counts


async def _open_unfiled(pilot, app):
    screen = await _open_panel(pilot, app)
    await pilot.press("u")
    await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
    return screen


def test_u_swaps_the_lower_pane_and_leaves_the_account_cursor_alone(monkeypatch):
    _patch_browse(monkeypatch)
    calls, counts = _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        # the account cursor never moved, and no screen was pushed
        assert screen._acct_idx == 0 and app.screen is screen
        # oldest first, in the lower pane, under its own column labels
        assert [r.key for r in screen._batch_list._rows] == ["t1", "t2", "t3"]
        assert screen._batch_list._headers[1] == "Date"
        assert "In no batch · BCP PEN" in (screen._batch_list._caption or "")
        # one read, oldest first, scoped to this account; the count asks the same question
        assert len(calls) == 1
        assert calls[0]["sort"] == "date_asc" and calls[0]["limit"] == 10
        assert calls[0]["account"] == "acc1" and calls[0]["unreconciled"] is True
        assert counts == [{"account": "acc1", "unreconciled": True, "verbose": False}]

    run_app(scenario)


def test_esc_in_no_batch_returns_to_the_panel(monkeypatch):
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("escape")
        await wait_for(pilot, lambda: screen._mode != "unfiled")
        assert screen._mode == "batches"  # the panel, not the plain account list
        assert screen._batch_list.has_focus
        assert app.screen is screen  # esc swapped the pane, it did not pop the screen
        assert [r.key for r in screen._batch_list._rows] == ["r1"]  # acc1's batch is back
        assert screen._batch_list._headers[0] == "Name"
        assert screen._batch_list._more is None  # the batches are not a growing list

    run_app(scenario)


def test_the_caption_counts_what_is_loaded_against_the_engine_count(monkeypatch):
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch, items=[_txn(n) for n in range(1, 26)], total=1716)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        assert len(screen._batch_list._rows) == 10
        # the figure is the engine's count, not the length of the page in hand
        assert "10 of 1716 loaded · oldest first" in (screen._batch_list._caption or "")

    run_app(scenario)


def test_pgdn_appends_the_next_ten_and_lands_on_the_first_new_row(monkeypatch):
    _patch_browse(monkeypatch)
    calls, counts = _patch_unfiled(monkeypatch, items=[_txn(n) for n in range(1, 26)])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._batch_list._rows) == 20)
        # appended, not swapped: the first ten are still there, in order
        assert [r.key for r in screen._batch_list._rows] == [f"t{n}" for n in range(1, 21)]
        assert screen._batch_list.cursor_index == 10  # row 11, the first new one
        assert calls[-1]["after"] == "c10" and calls[-1]["sort"] == "date_asc"
        assert len(counts) == 1  # no recount on pgdn
        assert "20 of 25 loaded" in (screen._batch_list._caption or "")

        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._batch_list._rows) == 25)
        # the engine said that was the last: pgdn now asks for nothing
        assert screen._unfiled_grow.next_cursor is None
        sent = len(calls)
        await pilot.press("pagedown")
        await pilot.pause()
        assert len(calls) == sent

    run_app(scenario)


def test_esc_from_the_edit_form_keeps_the_no_batch_rows_and_cursor(monkeypatch):
    """`⏎` on a row in no batch, then `esc`: not a write, so nothing is read
    again and the cursor stays on its row."""
    from expense.tui.screens.edit_form import EditFormScreen

    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch, items=[_txn(n) for n in range(1, 26)])
    monkeypatch.setattr(EditFormScreen, "_load_entities", lambda self: None)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._batch_list._rows) == 20)
        await pilot.press("down")
        key = screen._batch_list.cursor_key
        reads = len(calls)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        assert len(calls) == reads
        assert screen._batch_list.cursor_key == key == "t12"
        assert len(screen._batch_list._rows) == 20

    run_app(scenario)


def test_r_starts_again_from_the_oldest_ten(monkeypatch):
    _patch_browse(monkeypatch)
    calls, counts = _patch_unfiled(monkeypatch, items=[_txn(n) for n in range(1, 26)])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._batch_list._rows) == 20)
        await pilot.press("r")
        await wait_for(pilot, lambda: len(screen._batch_list._rows) == 10)
        assert screen._mode == "unfiled"  # still the pane, not a screen reload
        assert calls[-1]["after"] is None and calls[-1]["limit"] == 10
        assert len(counts) == 2

    run_app(scenario)


def test_a_count_that_cannot_be_read_fails_the_pane(monkeypatch):
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch, count_fails=True)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.press("u")
        await wait_for(pilot, lambda: not screen._unfiled_busy and screen._mode != "unfiled")
        # no rows beside a guessed number: the batches are back
        assert [r.key for r in screen._batch_list._rows] == ["r1"]
        assert not screen._unfiled

    run_app(scenario)


def test_a_delete_starts_the_list_over(monkeypatch, fake_client):
    from expense.tui.screens.modals import ConfirmModal

    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch, items=[_txn(n) for n in range(1, 26)])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._batch_list._rows) == 20)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.deletes)
        assert fake_client.deletes == ["/transactions/t11"]
        # any write starts the list over: the oldest 10,
        # the cursor on row 1
        await wait_for(pilot, lambda: len(calls) == 3 and not screen._unfiled_busy)
        assert calls[-1]["limit"] == 10 and calls[-1]["after"] is None
        assert screen._batch_list.cursor_index == 0
        assert len(screen._batch_list._rows) == 10

    run_app(scenario)


def test_d_deletes_the_cursor_row_after_a_confirm(monkeypatch, fake_client):
    from expense.tui.screens.modals import ConfirmModal

    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        await _open_unfiled(pilot, app)
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
