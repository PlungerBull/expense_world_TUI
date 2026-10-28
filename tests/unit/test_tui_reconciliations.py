"""Reconciliations tests — list rows + new-statement form (fake client)."""

import json

import pytest
from textual.widgets import Input

from expense.tui.screens._base import list_refusal_text
from expense.tui.screens.reconciliations import (
    NewReconciliationScreen,
    ReconciliationsScreen,
)
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ARCHIVED_FIELD_WORDS,
    ARCHIVED_PUT_WORDS,
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_BANK_NAMES,
    account_record,
    archived_refusal,
    archived_words,
    bank_line_row,
    cursor_page,
    holder_list,
    import_part,
    in_order,
    refusal_text,
    render_text,
    run_app,
    statement_list,
    statement_record,
    wait_for,
    wait_for_list,
    whole,
)


def _statement(sid: str, holder: str, name: str, days: tuple[str, str], **fields) -> dict:
    """A statement of a holder with no statement code, as `GET /statements` reads it:
    its one account's balances are `fields`'s `balances`, or nothing entered past a
    begin of 0 on `acc1` (`statement_record`)."""
    return statement_record(
        {"id": sid, "holder_id": holder, "name": name, "date_start": days[0], "date_end": days[1]}
        | fields
    )


#: One statement on each holder: March on acc1's, completed and adding up; April on
#: acc2's, a draft with no ending balance yet, off by -35.00.
ITEMS = [
    _statement(
        "r1",
        "h1",
        "March 2026",
        ("2026-03-01", "2026-03-31"),
        status=2,
        balances=[
            {
                "account_id": "acc1",
                "beginning_balance_cents": 1200000,
                "ending_balance_cents": 958000,
                "difference_cents": 0,
            }
        ],
    ),
    _statement(
        "r2",
        "h2",
        "April 2026",
        ("2026-04-01", "2026-04-30"),
        balances=[
            {
                "account_id": "acc2",
                "beginning_balance_cents": 958000,
                "ending_balance_cents": None,
                "difference_cents": -3500,
            }
        ],
    ),
]


def test_batch_rows_format():
    from expense.tui.screens.reconciliations import batch_rows

    rows = batch_rows(ITEMS[:1], "acc1")
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
    off = batch_rows([ITEMS[1]], "acc2")[0][1]
    assert off[5] == "draft"
    assert off[1] == "2026-04-01 → 2026-04-30"
    assert str(off[4]) == "-35.00"


def test_batch_rows_read_the_open_accounts_entry_in_balances():
    """Each row's Begin, End and Diff are the open account's, from its entry in the
    statement's `balances`, whatever other entry the statement holds
    (contract: "Statements", "Statement response")."""
    from expense.tui.screens.reconciliations import batch_rows

    two = _statement(
        "s1",
        "h1",
        "May 2026",
        ("2026-05-01", "2026-05-31"),
        balances=[
            {"account_id": "acc-other", "beginning_balance_cents": 500},
            {"account_id": "acc1", "beginning_balance_cents": 100, "ending_balance_cents": 200},
        ],
    )
    [(_key, cells, _style)] = batch_rows([two], "acc1")
    assert [str(cell) for cell in cells[2:4]] == ["1.00", "2.00"]


def _patch(monkeypatch):
    """Screen-specific patches; the client/config seams come from fake_client."""
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole(
            [
                account_record(id="acc1", name="BCP PEN"),
                account_record(
                    id="acc2",
                    name="Interbank USD",
                    currency_code="USD",
                    holder_id="h2",
                ),
            ]
        ),
    )


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


async def _wait_accounts(screen, pilot):
    await wait_for(pilot, lambda: screen._accounts)


def test_new_statement_sends_its_holder_and_the_picked_accounts_balances(fake_client, monkeypatch):
    """The form alone: the account picked, its holder is the one the accounts read
    names on it, and one `POST /statements` sends exactly the fields the engine takes,
    the account's typed balances its one entry in `balances`; the engine refuses any
    other field (contract: POST /v1/statements)."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewReconciliationScreen()
        await app.push_screen(screen)
        await _wait_accounts(screen, pilot)
        _enter(screen, "April 2026")  # name
        _enter(screen, "Interbank")  # account → acc2, on holder h2
        _enter(screen, "2026-04-01")  # date_start (required)
        _enter(screen, "2026-04-30")  # date_end (required)
        _enter(screen, "9580.00")  # begin
        _enter(screen, "9460.00")  # end → submits
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(path, body)] = fake_client.posts
    assert path == "/statements"
    assert set(body) == {"id", "holder_id", "name", "date_start", "date_end", "balances"}
    assert body["holder_id"] == "h2" and body["name"] == "April 2026"
    assert body["balances"] == [
        {"account_id": "acc2", "beginning_balance_cents": 958000, "ending_balance_cents": 946000}
    ]


def test_new_reconciliation_refuses_a_balance_with_a_comma_after_its_dot(fake_client, monkeypatch):
    """`9.580,00` is not read as 9.58: begin and end each give their note and
    the cursor stays; the same figures written `9,580.00` and `9460` send."""
    _patch(monkeypatch)
    notes: list[str] = []

    async def scenario(pilot, app):
        screen = NewReconciliationScreen(account_id="acc1", account_name="BCP PEN")
        await app.push_screen(screen)
        screen.notify = lambda message, **kw: notes.append(message)
        _enter(screen, "April 2026")  # name
        _enter(screen, "2026-04-01")
        _enter(screen, "2026-04-30")
        _enter(screen, "9.580,00")  # begin
        assert screen._key == "begin" and "begin" not in screen._values
        _enter(screen, "9,580.00")
        _enter(screen, "9.460,00")  # end
        assert screen._key == "end" and not fake_client.posts
        _enter(screen, "9460")  # end → submits
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    assert notes[:2] == [
        "Begin balance: a signed decimal, e.g. 9580.00",
        "End balance: a signed decimal, e.g. 9460.00",
    ]
    [(_path, body)] = fake_client.posts
    [balance] = body["balances"]
    assert balance["beginning_balance_cents"] == 958000
    assert balance["ending_balance_cents"] == 946000


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


def test_the_new_form_account_picker_shows_the_engines_order(fake_client, monkeypatch):
    """The account field lists the accounts exactly as `GET /accounts` returned
    them — not alphabetical, not by `sort_order`; people have no statements, so
    the person is left out and nothing else moves."""
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_ACCOUNTS)
    )

    async def scenario(pilot, app):
        screen = NewReconciliationScreen()
        await app.push_screen(screen)
        await _wait_accounts(screen, pilot)
        _enter(screen, "April 2026")  # name → the account field
        assert screen._key == "account"
        assert [ent[1] for ent in screen._suggestions] == ENGINE_ORDER_BANK_NAMES
        shown = render_text(screen._suggest_renderable(), width=120)
        assert in_order(shown, ENGINE_ORDER_BANK_NAMES)

    run_app(scenario)


def test_the_browse_lists_accounts_in_the_engines_order(monkeypatch):
    """The browse's account list stands as `GET /accounts` returned it, the
    person left out and nothing else moved."""
    _patch_browse(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_ACCOUNTS)
    )

    async def scenario(pilot, app):
        screen = ReconciliationsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert [a[1] for a in screen._accounts] == ENGINE_ORDER_BANK_NAMES
        shown = render_text(screen._accts_list._build(), width=120)
        assert in_order(shown, ENGINE_ORDER_BANK_NAMES)

    run_app(scenario)


#: acc1's and acc2's holders as `GET /holders` reads them, one account each, no
#: statement code.
HOLDERS = [
    {"id": "h1", "account_ids": ["acc1"]},
    {"id": "h2", "name": "Interbank USD", "account_ids": ["acc2"]},
]


def _patch_browse(monkeypatch, items=None, fail=False):
    """Two accounts, each alone on its holder with no statement code, one
    statement each — the browse screen's standard fixture. The fake reads like
    the engine: one holder at a time (the holder is required), the list whole,
    never paged (contract: GET /v1/statements). Returns the holders it was asked
    for, in order."""
    reads: list = []
    rows = ITEMS if items is None else items

    def fetch(_cfg, holder_id, **kw):
        assert "limit" not in kw and "offset" not in kw, "the engine refuses paging here"
        reads.append(holder_id)
        if fail:
            raise RuntimeError("statements unavailable")
        return statement_list([r for r in rows if r.get("holder_id") == holder_id])

    monkeypatch.setattr("expense.reads.fetch_statements", fetch)
    monkeypatch.setattr("expense.reads.fetch_holders", lambda *a, **k: holder_list(HOLDERS))
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole(
            [
                account_record(
                    id="acc1",
                    name="BCP PEN",
                    current_balance_cents=100,
                ),
                account_record(
                    id="acc2",
                    name="Interbank USD",
                    currency_code="USD",
                    holder_id="h2",
                ),
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


def test_the_browse_opens_on_the_accounts_alone_and_reads_no_statements(monkeypatch):
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
        assert reads == ["h2"]  # that account's holder, and only that one
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
    """The holder's list arrives `date_start` ascending, then creation time,
    oldest first (contract: "Statements", "Ordering"); the screen does not
    re-sort it. Served out of date order on purpose, so a re-sort would show."""
    served = [
        _statement("b-march", "h1", "March", ("2026-03-01", "2026-03-31")),
        _statement("b-april", "h1", "April", ("2026-04-01", "2026-04-30")),
        _statement("b-feb", "h1", "February", ("2026-02-01", "2026-02-28")),
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
        _statement("b1", "h1", "March", ("2026-03-01", "2026-03-31"), status=2),
        _statement("b2", "h1", "April", ("2026-04-01", "2026-04-30"), status=2),
    ]
    reads = _patch_browse(monkeypatch, items=two)
    # the working screen's own reads are not what this test is about
    monkeypatch.setattr(ReconciliationDetailScreen, "_load_txns", lambda self, **k: None)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        screen._batch_list.action_move(1)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ReconciliationDetailScreen))
        assert app.screen._currency == "PEN"  # the ending-balance box names it
        app.screen.dismiss()
        await wait_for(pilot, lambda: len(reads) == 2 and screen._mode == "batches")
        await wait_for(pilot, lambda: screen._batch_list is not None)
        assert reads == ["h1", "h1"]  # the open account's holder, re-read
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
        assert form._holder_id == "h2"  # and its holder
        rows.append(_statement("new-1", "h2", "May 2026", ("2026-05-01", "2026-05-31")))
        form.dismiss("new-1")  # what `_done` hands back after the POST
        await wait_for(pilot, lambda: screen._batch_list is not None)
        assert reads == ["h2"]
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

    monkeypatch.setattr("expense.reads.fetch_accounts", boom)
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


def test_a_new_statement_whose_holder_is_gone_shows_the_engine_words_alone(
    fake_client, monkeypatch
):
    """The browse was read before its account became a person, which deleted the
    holder it was alone on (contract: "Holders", "A holder is deleted with its last
    account"), so `n` still offers it: the engine refuses the create's `holder_id`
    (contract: POST /v1/statements). The "Failed" note is the engine's words and its
    field's words under them, with no line of the app's; the form stays open with what
    was typed, and nothing is handed back."""
    from expense.errors import EngineError

    words = "Stand-in field words."  # the contract does not print this refusal's sentence
    err = EngineError(
        "VALIDATION_ERROR",
        "Statement validation failed.",
        {"holder_id": words},
        422,
        {},
        reasons={"holder_id": "INVALID_REFERENCE"},
    )
    fake_client.errors["POST"] = err
    notices: list = []
    monkeypatch.setattr(
        NewReconciliationScreen,
        "notify",
        lambda self, message, title="", **kw: notices.append((title, str(message))),
    )
    handed: list = []

    async def scenario(pilot, app):
        screen = NewReconciliationScreen(
            account_id="acc1", account_name="ALEJO PEN", holder_id="h1"
        )
        await app.push_screen(screen, handed.append)
        _enter(screen, "October 2026")  # name
        _enter(screen, "2026-10-01")  # date_start
        _enter(screen, "2026-10-31")  # date_end
        _enter(screen, "1250.00")  # begin
        typed = dict(screen._values)
        _enter(screen, "")  # end → submits
        await wait_for(pilot, lambda: notices and not screen._submitting)
        assert notices == [
            ("Failed", f"VALIDATION_ERROR — Statement validation failed.\n  holder_id: {words}")
        ]
        assert notices[0][1] == refusal_text(err, None)
        assert app.screen is screen and screen._values == typed

    run_app(scenario)
    assert [path for path, _body in fake_client.posts] == ["/statements"]
    assert handed == []


# ---- the "no batch" list (`u`) ----------------------------------------------
# Reconciliation work stays
# in the reconciliation view, so `u` swaps the LOWER PANE of this screen — it
# does not push a filtered ledger, and it does not touch the account cursor.
# It lists bank lines (`GET /bank-lines`), newest first, a split purchase once.
def _line(
    key: str,
    amounts: list[int],
    *,
    day: str,
    title: str,
    code: str | None = None,
) -> dict:
    """One bank line on acc1 as `GET /bank-lines` lists it: a part per amount,
    each a magnitude and its type, and the engine's signed total."""
    parts = [
        import_part(f"{key}-p{i}", a, account_id="acc1", line=key, day=day, title=title)
        for i, a in enumerate(amounts, 1)
    ]
    return bank_line_row(key, parts, net_cents=sum(amounts), operation_code=code, account_id="acc1")


UNFILED = [
    # the engine's one order: newest first
    _line("bl-uber", [-2450], day="2026-03-20", title="UBER *TRIP"),
    _line("bl-farm", [-6000, -4000], day="2026-03-10", title="FARMACIA", code="48201764"),
    _line("bl-net", [-4490], day="2026-01-04", title="NETFLIX", code="47391026"),
]


def test_statement_windows_take_the_statements_holding_this_accounts_balances():
    """A statement holds a balance per account of its holder; the `!` days are those
    of the statements holding one of this account's."""
    from expense.tui.screens.reconciliations import statement_windows

    assert statement_windows(ITEMS, "acc1") == [("2026-03-01", "2026-03-31", "March 2026")]
    assert statement_windows(ITEMS, "acc2") == [("2026-04-01", "2026-04-30", "April 2026")]


def test_unfiled_rows_are_the_bank_columns_one_line_each_in_the_engine_order():
    """2d: date · title · operation · amount, the signed `net_cents`, a dim `—`
    for no operation code; a split purchase is one row with its title alone and its
    total; `!` on the rows dated inside a statement's days."""
    from expense.tui.screens.reconciliations import statement_windows, unfiled_rows

    windows = statement_windows(ITEMS, "acc1")
    rows = unfiled_rows(UNFILED, windows)
    assert [r[0] for r in rows] == ["bl-uber", "bl-farm", "bl-net"]  # as the engine sent them
    cells = [[str(c) for c in r[1]] for r in rows]
    # January is in no window; both March rows sit inside 'March 2026'
    assert cells == [
        ["!", "2026-03-20", "UBER *TRIP", "—", "-24.50"],
        ["!", "2026-03-10", "FARMACIA", "48201764", "-100.00"],
        ["", "2026-01-04", "NETFLIX", "47391026", "-44.90"],
    ]
    assert rows[0][1][3].style == "dim"  # no operation code: a dim em dash


def test_a_split_purchase_reads_as_one_row_and_nothing_marks_it_split():
    from expense.tui.screens.reconciliations import unfiled_rows

    rows = unfiled_rows([UNFILED[1]], [])
    assert len(rows) == 1
    assert [str(c) for c in rows[0][1]] == ["", "2026-03-10", "FARMACIA", "48201764", "-100.00"]


def _numbered(n: int) -> dict:
    return _line(f"bl{n}", [-100 * n], day=f"2025-01-{n:02d}", title=f"ROW {n}")


def _patch_unfiled(monkeypatch, items=None, total=None, count_fails=False):
    """A cursor-paged fake of `GET /bank-lines`: it refuses `offset` and `sort`,
    serves `items` in slices of the requested `limit`, and hands back
    `c<next index>` as the cursor; `count_bank_lines` answers `total`."""
    calls: list = []
    counts: list = []
    rows = UNFILED if items is None else items

    def fetch(_cfg, *, limit=None, after=None, **kw):
        assert "offset" not in kw, "the engine refuses offset"
        assert "sort" not in kw, "the engine's line list has one order"
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

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fetch)
    monkeypatch.setattr("expense.reads.count_bank_lines", count)

    def no_ledger_read(*_a, **_k):
        raise AssertionError("the no batch list reads no transactions")

    monkeypatch.setattr("expense.reads.fetch_transactions", no_ledger_read)
    monkeypatch.setattr("expense.reads.count_transactions", no_ledger_read)
    return calls, counts


async def _open_unfiled(pilot, app):
    screen = await _open_panel(pilot, app)
    await pilot.press("u")
    await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
    return screen


def test_u_reads_the_accounts_lines_in_no_batch_newest_first(monkeypatch):
    _patch_browse(monkeypatch)
    calls, counts = _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        # the account cursor never moved, and no screen was pushed
        assert screen._acct_idx == 0 and app.screen is screen
        # one row per line, in the engine's order, under the bank's columns
        assert [r.key for r in screen._batch_list._rows] == ["bl-uber", "bl-farm", "bl-net"]
        assert screen._batch_list._headers == ["", "Date", "Title", "Operation", "Amount"]
        assert screen._batch_list._caption == (
            "In no batch · BCP PEN   ·   3 of 3 loaded · newest first"
            "   ·   ! dated inside a statement"
        )
        # one read of the account's lines in no batch, no dates, no sort; the
        # count asks the same question
        assert calls == [
            {"limit": 10, "after": None, "account": "acc1", "unreconciled": True, "verbose": False}
        ]
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
    _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)], total=1716)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        assert len(screen._batch_list._rows) == 10
        # the figure is the engine's line count, not the length of the page in hand
        assert "10 of 1716 loaded · newest first" in (screen._batch_list._caption or "")

    run_app(scenario)


def test_pgdn_appends_the_next_ten_and_lands_on_the_first_new_row(monkeypatch):
    _patch_browse(monkeypatch)
    calls, counts = _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._batch_list._rows) == 20)
        # appended, not swapped: the first ten are still there, in order
        assert [r.key for r in screen._batch_list._rows] == [f"bl{n}" for n in range(1, 21)]
        assert screen._batch_list.cursor_index == 10  # row 11, the first new one
        assert calls[-1]["after"] == "c10" and calls[-1]["unreconciled"] is True
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


def test_appended_rows_carry_the_flag_too(monkeypatch):
    """The `!` rule holds on rows `pgdn` brings in, not only the first ten."""
    _patch_browse(monkeypatch)
    rows = [_numbered(n) for n in range(1, 12)]
    rows[10] = _line("bl11", [-500], day="2026-03-15", title="IN MARCH")
    _patch_unfiled(monkeypatch, items=rows)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._batch_list._rows) == 11)
        flags = [str(r.cells[0]) for r in screen._batch_list._rows]
        assert flags == [""] * 10 + ["!"]

    run_app(scenario)


def test_esc_from_the_edit_form_keeps_the_no_batch_rows_and_cursor(monkeypatch):
    """`⏎` on a line never split opens the Edit form on the line, its one part
    signed; `esc` is not a write, so nothing is read again and the cursor stays
    on its row."""
    from expense.tui.screens.edit_form import EditFormScreen

    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)])
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
        form = app.screen
        assert form._record["id"] == "bl12-p1"  # the line's one transaction
        assert [p.amount_cents for p in form._parts] == [-1200]  # signed
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        assert len(calls) == reads
        assert screen._batch_list.cursor_key == key == "bl12"
        assert len(screen._batch_list._rows) == 20

    run_app(scenario)


def _enter_label(app):
    active = app.screen.active_bindings.get("enter")
    return active.binding.description if active and active.enabled else None


def _card_enter_rows(screen) -> list[str]:
    from expense.tui.screens.help import screen_inventory

    _, groups = screen_inventory(screen)
    keyed = [g for g in groups if g.title in ("This screen", "Moving around")]
    return [row.description for g in keyed for row in g.rows if row.keys == "⏎"]


def _card_group(screen, title: str) -> list[tuple[str, str]]:
    """One group of the `?` card, row by row, in order."""
    from expense.tui.screens.help import screen_inventory

    _, groups = screen_inventory(screen)
    return [(row.keys, row.description) for g in groups if g.title == title for row in g.rows]


async def _cursor_on(pilot, screen, key: str) -> None:
    screen._batch_list.set_cursor(screen._batch_list.index_of(key))
    await pilot.pause()


def test_enter_edits_every_row_in_no_batch_in_the_footer_the_card_and_the_key(monkeypatch):
    """`⏎ Edit` is on for every row in no batch, a split transaction included:
    in the footer, on the `?` card, and the key opens the bank-line Edit form."""
    from expense.tui.screens.edit_form import BankLineEditFormScreen

    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)
    monkeypatch.setattr(BankLineEditFormScreen, "_load_entities", lambda self: None)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        for key in ("bl-uber", "bl-farm", "bl-net"):
            await _cursor_on(pilot, screen, key)
            assert _enter_label(app) == "Edit", key
            assert "enter" in _footer_keys(app), key
            # screen 2 A of expense-world-edit-form-words.html: the ledger's `s` words
            assert _card_enter_rows(screen) == ["Edit the transaction and its parts"], key
            assert _card_group(screen, "Moving around") == [
                ("⏎", "Edit the transaction and its parts"),
                ("↓", "Down"),
                ("pgdn", "Load the next 10 rows under these"),
                ("pgdn", "Next page"),
                ("pgup", "Previous page"),
            ], key
        await _cursor_on(pilot, screen, "bl-farm")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, BankLineEditFormScreen))
        assert app.screen._line is UNFILED[1]

    run_app(scenario)


# ---- `⏎` in no batch: the Edit form on the line and its parts ----------------
# Question 1 A of expense-world-split-transaction-screen.html: the same Edit form,
# OPERATION among the shared fields; one save is one `PUT /bank-lines/{id}`
# (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts").
EDIT_CATEGORIES = whole(
    [{"id": "pend", "name": "@Pendiente", "is_system": True, "system_key": "pending"}]
)
EDIT_HASHTAGS = whole([{"id": "h-pend", "name": "Pendiente", "system_key": "pending"}])


def _summary_lines(form, width: int = 120) -> list[str]:
    text = render_text(form._summary_renderable(), width=width)
    return [line.rstrip() for line in text.splitlines()]


def _heading_text(form) -> str:
    return render_text(form._heading(), width=120).rstrip()


async def _open_form(pilot, app, key: str):
    """The no batch list, the cursor on `key`, `⏎`; the form once loaded."""
    from expense.tui.screens.edit_form import BankLineEditFormScreen

    screen = await _open_unfiled(pilot, app)
    await _cursor_on(pilot, screen, key)
    await pilot.press("enter")
    await wait_for(pilot, lambda: isinstance(app.screen, BankLineEditFormScreen))
    form = app.screen
    await wait_for(pilot, lambda: form._ready)
    await pilot.pause()
    return screen, form


def _patch_form(monkeypatch, items=None):
    _patch_browse(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: EDIT_CATEGORIES)
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: EDIT_HASHTAGS)
    return _patch_unfiled(monkeypatch, items=items)


def _go_to(form, key: str) -> None:
    """Move the bar to `key`, a line of the form's own sequence."""
    assert key in form._sequence(), key
    while form._key != key:
        form.action_field(1)


#: Each line of a part, after the shared fields.
PART_FIELDS = ["amount", "category", "hashtags", "note"]


def test_a_row_never_split_opens_the_line_and_its_one_part(monkeypatch, fake_client):
    """A row never split: date, title, operation and account, then part 1's
    amount, category, hashtags and note, all editable; the heading is the row
    as listed; the crumb is `… ▸ Reconciliations ▸ Edit`."""
    from expense.tui.widgets.header import Breadcrumb

    _patch_form(monkeypatch)

    async def scenario(pilot, app):
        _screen, form = await _open_form(pilot, app, "bl-uber")
        assert form._sequence() == [
            "date",
            "title",
            "operation",
            "account",
            *(f"0.{f}" for f in PART_FIELDS),
        ]
        assert not form._locked
        assert form._key == "date"
        assert form.query_one("#crumb", Breadcrumb)._trail == (
            "Capture & ledger",
            "Reconciliations",
            "Edit",
        )
        assert _heading_text(form) == "UBER *TRIP  ·  -24.50 PEN"
        assert _summary_lines(form) == [
            "date       2026-03-20",
            "title      UBER *TRIP",
            "operation  —  (optional)",
            "account    BCP PEN",
            "",
            "      amount    category       hashtags        note",
            "  1   -24.50    —              —",
        ]
        for key in ("title", "operation", "account", "0.amount"):
            form.action_field(1)
            assert form._key == key
        assert form.query_one("#bar", Input).value == "-24.5"  # as `amount_to_text` writes it

    run_app(scenario)
    assert fake_client.calls == []  # the line was in hand: nothing read, nothing sent


def test_a_split_transaction_opens_the_line_and_every_part(monkeypatch, fake_client):
    """A split transaction: the shared fields, then each part's lines, every
    one editable, and the line adding the parts up against its total."""
    _patch_form(monkeypatch)

    async def scenario(pilot, app):
        _screen, form = await _open_form(pilot, app, "bl-farm")
        assert form._sequence()[4:] == [f"{i}.{f}" for i in (0, 1) for f in PART_FIELDS]
        assert _heading_text(form) == "FARMACIA  ·  -100.00 PEN"
        assert _summary_lines(form) == [
            "date       2026-03-10",
            "title      FARMACIA",
            "operation  48201764",
            "account    BCP PEN",
            "",
            "      amount    category       hashtags        note",
            "  1   -60.00    —              —",
            "  2   -40.00    —              —",
            "",
            "2 parts  ·  -100.00 of -100.00  ✓",
        ]
        _go_to(form, "operation")
        assert form.query_one("#bar", Input).value == "48201764"

    run_app(scenario)
    assert fake_client.calls == []


def _type_and_enter(form, text: str) -> None:
    form.query_one("#bar", Input).value = text
    form._recompute_suggestions(text)
    form.on_input_submitted(None)


FARM_PARTS = [
    {"id": "bl-farm-p1", "amount_cents": -6000},
    {"id": "bl-farm-p2", "amount_cents": -4000},
]


@pytest.mark.parametrize(
    ("row", "field", "typed", "sent"),
    [
        ("bl-farm", "date", "2026-03-12", {"date": "2026-03-12"}),
        ("bl-farm", "title", "FARMACIA CENTRAL", {"title": "FARMACIA CENTRAL"}),
        ("bl-farm", "operation", "55500011", {"operation_code": "55500011"}),
        ("bl-farm", "operation", "", {"operation_code": None}),
        ("bl-farm", "account", "Interbank", {"account_id": "acc2", "statement_id": None}),
        ("bl-uber", "operation", "11122233", {"operation_code": "11122233"}),
        ("bl-uber", "0.amount", "-30.00", {}),
    ],
    ids=[
        "split-date",
        "split-title",
        "split-operation",
        "split-operation-cleared",
        "split-account",
        "lone-operation",
        "lone-amount",
    ],
)
def test_saving_sends_one_put_on_the_line_with_the_field_changed_and_its_parts(
    monkeypatch, fake_client, row, field, typed, sent
):
    """One `PUT /bank-lines/{id}`: the line field changed, if any, beside every
    part under its own id with its current amount, a typed amount in its place.
    An emptied operation sends `null`, which clears it, and an account move
    also settles the assignment (contract: PUT /v1/bank-lines/{bank_line_id}, "Body")
    (`unassign_on_move`). Saved, "no batch" reads its newest ten again, the
    cursor on row 1."""
    from expense.dates import to_canonical_aware

    calls, counts = _patch_form(monkeypatch)
    if "date" in sent:
        sent = {"date": to_canonical_aware(sent["date"])}
    parts = FARM_PARTS if row == "bl-farm" else [{"id": "bl-uber-p1", "amount_cents": -2450}]
    if field == "0.amount":
        parts = [{"id": "bl-uber-p1", "amount_cents": -3000}]

    async def scenario(pilot, app):
        screen, form = await _open_form(pilot, app, row)
        await _cursor_on(pilot, screen, row)
        _go_to(form, field)
        reads = len(calls)
        _type_and_enter(form, typed)
        if form.is_attached and app.screen is form:
            await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is screen)
        await wait_for(pilot, lambda: len(calls) > reads and not screen._unfiled_busy)
        assert calls[-1]["after"] is None and calls[-1]["limit"] == 10
        assert len(counts) == 2  # the count is read again with the rows
        assert screen._batch_list.cursor_index == 0

    run_app(scenario)
    assert fake_client.puts == [(f"/bank-lines/{row}", {**sent, "parts": parts})]
    assert [m for m, _p in fake_client.requests] == ["PUT"]


def test_saving_carries_one_idempotency_key(configured, monkeypatch):
    """Through the real HTTP client: one `PUT /bank-lines/{id}` with the
    client's idempotency key, and no read of the line."""
    import httpx
    import respx

    from expense import config as config_module
    from expense.tui.screens.edit_form import BankLineEditFormScreen
    from tests.unit.helpers import ENGINE_URL

    real_config = config_module.ensure_loaded
    _patch_form(monkeypatch)
    monkeypatch.setattr("expense.config.ensure_loaded", real_config)

    async def scenario(pilot, app):
        screen, form = await _open_form(pilot, app, "bl-farm")
        form.action_field(1)  # past the date, unchanged
        _type_and_enter(form, "FARMACIA CENTRAL")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not isinstance(app.screen, BankLineEditFormScreen))

    farm = next(line for line in UNFILED if line["id"] == "bl-farm")
    with respx.mock(assert_all_called=False) as engine:
        read = engine.get(url__startswith=f"{ENGINE_URL}/v1/bank-lines").mock(
            httpx.Response(200, json={})
        )
        route = engine.put(f"{ENGINE_URL}/v1/bank-lines/bl-farm").mock(
            httpx.Response(
                200,
                json={**farm, "changed_parts": [], "created_part_ids": [], "deleted_part_ids": []},
            )
        )
        run_app(scenario)
    assert route.call_count == 1
    assert route.calls.last.request.headers["X-Idempotency-Key"]
    assert json.loads(route.calls.last.request.content) == {
        "title": "FARMACIA CENTRAL",
        "parts": FARM_PARTS,
    }
    assert not read.called


def _refused(monkeypatch, fake_client, err) -> tuple[list[str], tuple[bool, bool, int]]:
    """Type a new operation number on bl-farm and save into `err`; returns the
    summary once refused, then whether the form is still on top, whether it
    holds what was typed, and how many times "no batch" was read since."""
    calls, _counts = _patch_form(monkeypatch)
    fake_client.errors["PUT"] = err
    seen: list = []

    async def scenario(pilot, app):
        _screen, form = await _open_form(pilot, app, "bl-farm")
        reads = len(calls)
        _go_to(form, "operation")
        _type_and_enter(form, "47391026")
        typed = dict(form._values)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: form._refusal is not None and not form._submitting)
        seen.extend([app.screen is form, form._values == typed, len(calls) - reads])
        return _summary_lines(form, width=200)

    summary = run_app(scenario)
    assert fake_client.puts == [
        ("/bank-lines/bl-farm", {"operation_code": "47391026", "parts": FARM_PARTS})
    ]
    return summary, tuple(seen)


def test_a_refused_save_shows_the_engine_words_under_the_parts_and_the_form_stays(
    monkeypatch, fake_client
):
    """The engine refuses: its words whole under the parts, then the app's
    line for the reason, the form still open and "no batch" not read again."""
    from expense.errors import EngineError

    err = EngineError(
        "CONFLICT",
        "Another bank line on this account already has operation code '47391026'.",
        {"operation_code": "Another bank line on this account already has operation code."},
        409,
        {},
        reasons={"operation_code": "OPERATION_CODE_EXISTS"},
    )
    summary, seen = _refused(monkeypatch, fake_client, err)
    assert [line.strip() for line in summary[-5:]] == [
        "CONFLICT — Another bank line on this account already has operation code '47391026'.",
        "! operation_code: Another bank line on this account already has operation code.",
        "Nothing was saved.",
        "",
        "That account already has a row with this operation number: look there for a duplicate.",
    ]
    assert seen == (True, True, 0)  # on top, holding what was typed, nothing read again


def test_a_save_on_an_archived_account_shows_the_engine_words_alone(monkeypatch, fake_client):
    """Screen 3 A of expense-world-archived-account.html: the form was opened
    before the line's account was archived, and a new operation number is
    saved. Under the parts, the engine's words, its field's words under them,
    and no line of the app's; the form stays open with what was typed, and
    "no batch" is not read again."""
    err = archived_refusal(422, ARCHIVED_PUT_WORDS, "operation_code")
    summary, seen = _refused(monkeypatch, fake_client, err)
    assert [line.strip() for line in summary[-3:]] == [
        f"VALIDATION_ERROR — {ARCHIVED_PUT_WORDS}",
        f"! operation_code: {ARCHIVED_FIELD_WORDS}",
        "Nothing was saved.",
    ]
    assert seen == (True, True, 0)  # on top, holding what was typed, nothing read again


def test_esc_on_a_split_transaction_sends_nothing_and_keeps_the_cursor(monkeypatch, fake_client):
    calls, _counts = _patch_form(monkeypatch)

    async def scenario(pilot, app):
        screen, form = await _open_form(pilot, app, "bl-farm")
        reads = len(calls)
        _type_and_enter(form, "2026-03-12")  # typed, never saved
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert len(calls) == reads
        assert screen._batch_list.cursor_key == "bl-farm"

    run_app(scenario)
    assert fake_client.puts == []


def test_no_changes_sends_nothing(monkeypatch, fake_client):
    _patch_form(monkeypatch)

    async def scenario(pilot, app):
        _screen, form = await _open_form(pilot, app, "bl-farm")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.screen is form

    run_app(scenario)
    assert fake_client.puts == []


def test_the_card_on_the_reconciliations_offers_open_alone(monkeypatch):
    """The panel's two `⏎` rows follow what `⏎` does: `Open` on a reconciliation."""
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        assert _card_enter_rows(screen) == ["Open"]

    run_app(scenario)


def test_r_starts_again_from_the_newest_ten(monkeypatch):
    _patch_browse(monkeypatch)
    calls, counts = _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)])

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


def _notes(monkeypatch, screen) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        screen, "notify", lambda message, title="", **kw: notes.append((title, str(message)))
    )
    return notes


def test_d_on_a_line_never_split_deletes_its_transaction_and_starts_over(monkeypatch, fake_client):
    """A line never split deletes as today: the ledger's question word for word,
    `DELETE /transactions/{id}` of its one transaction, then the newest ten
    again, the cursor on row 1."""
    from expense.tui.screens.modals import ConfirmModal

    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        notes = _notes(monkeypatch, screen)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._batch_list._rows) == 20)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == "Delete this transaction?"
        assert app.screen._message == (
            "ROW 11 · -11.00 · 2025-01-11 · BCP PEN\n"
            "It leaves every balance and report, and no screen can bring it back."
        )
        reads = len(calls)
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.deletes)
        assert fake_client.deletes == ["/transactions/bl11-p1"]
        # any write starts the list over: the newest 10, the cursor on row 1
        await wait_for(pilot, lambda: len(calls) > reads and not screen._unfiled_busy)
        assert ("", "Transaction deleted.") in notes
        assert calls[-1]["limit"] == 10 and calls[-1]["after"] is None
        assert screen._batch_list.cursor_index == 0
        assert len(screen._batch_list._rows) == 10

    run_app(scenario)
    assert not [r for m, r in fake_client.requests if m == "GET"]  # nothing read before asking


@pytest.mark.parametrize("parts", [2, 3])
def test_d_on_a_split_purchase_asks_about_it_whole_then_deletes_it(monkeypatch, fake_client, parts):
    """3b: the purchase is one row, so `d` asks the ledger's purchase question
    with its real part count and total, reads nothing first, and `y` sends one
    `DELETE /bank-lines/{id}`; `Transaction deleted.`, then the newest ten again,
    the cursor on row 1."""
    from expense.tui.screens.modals import ConfirmModal

    amounts = {2: [-6000, -4000], 3: [-6000, -2500, -1500]}[parts]
    farm = _line("bl-farm", amounts, day="2026-03-10", title="FARMACIA", code="48201764")
    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch, items=[UNFILED[0], farm, UNFILED[2]])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        notes = _notes(monkeypatch, screen)
        await _cursor_on(pilot, screen, "bl-farm")
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == f"Delete this transaction and its {parts} parts?"
        assert app.screen._message == (
            "FARMACIA · -100.00 · 2026-03-10 · BCP PEN\nNo screen can bring it back."
        )
        reads = len(calls)
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", "Transaction deleted.") in notes)
        await wait_for(pilot, lambda: len(calls) > reads and not screen._unfiled_busy)
        assert calls[-1]["after"] is None and calls[-1]["limit"] == 10
        assert screen._batch_list.cursor_index == 0

    run_app(scenario)
    assert fake_client.deletes == ["/bank-lines/bl-farm"]
    assert not [r for m, r in fake_client.requests if m == "GET"]  # the line was in hand


@pytest.mark.parametrize("key", ["n", "escape", "enter"])
def test_any_other_answer_on_a_purchase_sends_nothing(monkeypatch, fake_client, key):
    from expense.tui.screens.modals import ConfirmModal

    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await _cursor_on(pilot, screen, "bl-farm")
        reads = len(calls)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press(key)
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert len(calls) == reads
        assert screen._batch_list.cursor_key == "bl-farm"

    run_app(scenario)
    assert fake_client.deletes == []


SEALED_LINE_WORDS = (
    "This bank line is in a completed reconciliation and cannot be deleted. "
    "Revert the reconciliation to draft first."
)


@pytest.mark.parametrize(
    ("row", "path", "status", "code", "fields", "reasons"),
    [
        (
            "bl-farm",
            "/bank-lines/bl-farm",
            409,
            "CONFLICT",
            {"bank_line_id": "Must not be assigned to a completed reconciliation."},
            {"bank_line_id": "IN_COMPLETED_RECONCILIATION"},
        ),
        ("bl-farm", "/bank-lines/bl-farm", 404, "NOT_FOUND", None, None),
        (
            "bl-net",
            "/transactions/bl-net-p1",
            409,
            "CONFLICT",
            {"transaction_id": "Must not be assigned to a completed reconciliation."},
            {"transaction_id": "IN_COMPLETED_RECONCILIATION"},
        ),
    ],
    ids=["purchase-sealed", "purchase-gone", "transaction-sealed"],
)
def test_a_refused_delete_shows_the_engine_words_and_keeps_the_list(
    monkeypatch, fake_client, row, path, status, code, fields, reasons
):
    """The engine refuses: its words in the "Failed" note, nothing deleted, the
    list not read again and the cursor where it was."""
    from expense.errors import EngineError
    from expense.tui.screens.modals import ConfirmModal

    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch)
    err = EngineError(code, SEALED_LINE_WORDS, fields, status, {}, reasons)
    fake_client.errors["DELETE"] = err

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        notes = _notes(monkeypatch, screen)
        await _cursor_on(pilot, screen, row)
        reads = len(calls)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert notes == [("Failed", list_refusal_text(err))]
        assert notes[0][1].startswith(f"{code} — {SEALED_LINE_WORDS}")
        assert len(calls) == reads and len(screen._batch_list._rows) == 3
        assert screen._batch_list.cursor_key == row

    run_app(scenario)
    assert fake_client.deletes == [path]


@pytest.mark.parametrize(
    ("row", "path", "thing", "key"),
    [
        ("bl-farm", "/bank-lines/bl-farm", "bank line", "bank_line_id"),
        ("bl-net", "/transactions/bl-net-p1", "transaction", "transaction_id"),
    ],
    ids=["purchase", "transaction"],
)
def test_a_delete_on_an_archived_account_shows_the_engine_words_alone(
    monkeypatch, fake_client, row, path, thing, key
):
    """Screen 3 A of expense-world-archived-account.html: the pane was read
    before the account was archived, and `d` then `y` is refused. The "Failed"
    note is the engine's words alone, no line of the app's under them, and the
    list is as it was: not read again, its rows and cursor kept."""
    from expense.tui.screens.modals import ConfirmModal

    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch)
    err = archived_refusal(409, archived_words("delete", thing), key)
    fake_client.errors["DELETE"] = err

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        notes = _notes(monkeypatch, screen)
        await _cursor_on(pilot, screen, row)
        reads = len(calls)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert notes == [
            (
                "Failed",
                f"CONFLICT — {archived_words('delete', thing)}\n  {key}: {ARCHIVED_FIELD_WORDS}",
            )
        ]
        assert notes[0][1] == refusal_text(err, None)
        assert len(calls) == reads and len(screen._batch_list._rows) == 3
        assert screen._batch_list.cursor_key == row

    run_app(scenario)
    assert fake_client.deletes == [path]


def test_y_on_a_purchase_sends_one_delete_with_an_idempotency_key(configured, monkeypatch):
    """Through the real HTTP client: one `DELETE /bank-lines/{id}` carrying the
    client's idempotency key, no `DELETE /transactions/{id}`, no line read."""
    import httpx
    import respx

    from expense import config as config_module
    from expense.tui.screens.modals import ConfirmModal
    from tests.unit.helpers import ENGINE_URL

    real_config = config_module.ensure_loaded
    _patch_browse(monkeypatch)
    monkeypatch.setattr("expense.config.ensure_loaded", real_config)
    _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        notes = _notes(monkeypatch, screen)
        await _cursor_on(pilot, screen, "bl-farm")
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", "Transaction deleted.") in notes)

    with respx.mock(assert_all_called=False) as engine:
        read = engine.get(url__startswith=f"{ENGINE_URL}/v1/bank-lines").mock(
            httpx.Response(200, json={})
        )
        route = engine.delete(f"{ENGINE_URL}/v1/bank-lines/bl-farm").mock(
            httpx.Response(200, json={"parts": []})
        )
        single = engine.delete(url__startswith=f"{ENGINE_URL}/v1/transactions/").mock(
            httpx.Response(200, json={})
        )
        run_app(scenario)
    assert route.call_count == 1
    assert route.calls.last.request.headers["X-Idempotency-Key"]
    assert not single.called and not read.called


def test_y_on_a_line_never_split_sends_its_transaction_delete_with_an_idempotency_key(
    configured, monkeypatch
):
    import httpx
    import respx

    from expense import config as config_module
    from expense.tui.screens.modals import ConfirmModal
    from tests.unit.helpers import ENGINE_URL

    real_config = config_module.ensure_loaded
    _patch_browse(monkeypatch)
    monkeypatch.setattr("expense.config.ensure_loaded", real_config)
    _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        notes = _notes(monkeypatch, screen)
        await _cursor_on(pilot, screen, "bl-net")
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", "Transaction deleted.") in notes)

    with respx.mock(assert_all_called=False) as engine:
        route = engine.delete(f"{ENGINE_URL}/v1/transactions/bl-net-p1").mock(
            httpx.Response(200, json={})
        )
        whole_line = engine.delete(url__startswith=f"{ENGINE_URL}/v1/bank-lines/").mock(
            httpx.Response(200, json={"parts": []})
        )
        run_app(scenario)
    assert route.call_count == 1
    assert route.calls.last.request.headers["X-Idempotency-Key"]
    assert not whole_line.called


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
