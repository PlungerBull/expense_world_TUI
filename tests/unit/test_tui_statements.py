"""Statements tests — list rows + new-statement form (fake client)."""

import json

import pytest
from textual.widgets import Input, Static

from expense.errors import EngineError
from expense.tui.screens._base import list_refusal_text
from expense.tui.screens.help import screen_inventory
from expense.tui.screens.statements import (
    NewStatementScreen,
    StatementsScreen,
)
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ARCHIVED_FIELD_WORDS,
    ARCHIVED_PUT_WORDS,
    ENGINE_ORDER_BANK_NAMES,
    ENGINE_ORDER_HOLDING_ACCOUNTS,
    SEALED_FIELD_WORDS,
    SEALED_LINE_WORDS,
    SEALED_TRANSACTION_WORDS,
    LateAnswer,
    account_with_currencies,
    app_notes,
    archived_refusal,
    archived_words,
    assert_card_gutters_blank,
    bank_line_row,
    cursor_page,
    held_currency,
    import_part,
    in_order,
    leave_then_answer,
    no_failed_toast,
    refusal_block,
    refusal_text,
    render_text,
    run_app,
    screen_lines,
    statement_list,
    statement_record,
    wait_for,
    wait_for_list,
    whole,
)


def _statement(sid: str, account: str, name: str, days: tuple[str, str], **fields) -> dict:
    """A statement of an account with no statement code, as `GET /statements` reads it:
    its balances are `fields`'s `balances`, or nothing entered past a begin of 0 in soles
    (`statement_record`)."""
    return statement_record(
        {
            "id": sid,
            "account_id": account,
            "name": name,
            "date_start": days[0],
            "date_end": days[1],
        }
        | fields
    )


#: One statement on each account: March on acc1's, completed and adding up; April on
#: acc2's, a draft with no ending balance yet, off by -35.00.
ITEMS = [
    _statement(
        "r1",
        "acc1",
        "March 2026",
        ("2026-03-01", "2026-03-31"),
        status=2,
        balances=[
            {
                "currency_code": "PEN",
                "beginning_balance_cents": 1200000,
                "ending_balance_cents": 958000,
                "difference_cents": 0,
            }
        ],
    ),
    _statement(
        "r2",
        "acc2",
        "April 2026",
        ("2026-04-01", "2026-04-30"),
        balances=[
            {
                "currency_code": "USD",
                "beginning_balance_cents": 958000,
                "ending_balance_cents": None,
                "difference_cents": -3500,
            }
        ],
    ),
]


def _patch(monkeypatch):
    """Screen-specific patches; the client/config seams come from fake_client."""
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole(
            [
                account_with_currencies(id="acc1", name="BCP"),
                account_with_currencies(
                    id="acc2", name="Interbank Plus", currencies=[held_currency("USD")]
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


def test_new_statement_sends_its_account_and_the_picked_accounts_balances(fake_client, monkeypatch):
    """The form alone: the account picked, and one `POST /statements` sends exactly the
    fields the engine takes, the account's typed balances its one entry in `balances`,
    keyed by the currency the accounts read gives it; the engine refuses any other
    field (contract: POST /v1/statements)."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewStatementScreen()
        await app.push_screen(screen)
        await _wait_accounts(screen, pilot)
        _enter(screen, "April 2026")  # name
        _enter(screen, "Interbank")  # account → acc2, holding dollars
        _enter(screen, "2026-04-01")  # date_start (required)
        _enter(screen, "2026-04-30")  # date_end (required)
        _enter(screen, "9580.00")  # begin
        _enter(screen, "9460.00")  # end → submits
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(path, body)] = fake_client.posts
    assert path == "/statements"
    assert set(body) == {"id", "account_id", "name", "date_start", "date_end", "balances"}
    assert body["account_id"] == "acc2" and body["name"] == "April 2026"
    assert body["balances"] == [
        {"currency_code": "USD", "beginning_balance_cents": 958000, "ending_balance_cents": 946000}
    ]


def test_new_statement_refuses_a_balance_with_a_comma_after_its_dot(fake_client, monkeypatch):
    """`9.580,00` is not read as 9.58: begin and end each give their note and
    the cursor stays; the same figures written `9,580.00` and `9460` send."""
    _patch(monkeypatch)
    notes: list[str] = []

    async def scenario(pilot, app):
        screen = NewStatementScreen(account_id="acc1", account_name="BCP", currencies=("PEN",))
        await app.push_screen(screen)
        screen.notify = lambda message, **kw: notes.append(message)
        _enter(screen, "April 2026")  # name
        _enter(screen, "2026-04-01")
        _enter(screen, "2026-04-30")
        _enter(screen, "9.580,00")  # begin
        assert screen._key == "begin:PEN" and "begin:PEN" not in screen._values
        _enter(screen, "9,580.00")
        _enter(screen, "9.460,00")  # end
        assert screen._key == "end:PEN" and not fake_client.posts
        _enter(screen, "9460")  # end → submits
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    assert notes[:2] == [
        "Begin balance PEN: a signed decimal, e.g. 9580.00. Amounts are 1,234.56.",
        "End balance PEN: a signed decimal, e.g. 9460.00. Amounts are 1,234.56.",
    ]
    [(_path, body)] = fake_client.posts
    [balance] = body["balances"]
    assert balance["beginning_balance_cents"] == 958000
    assert balance["ending_balance_cents"] == 946000


def test_new_statement_sends_the_typed_days_and_refuses_other_shapes(fake_client, monkeypatch):
    """A period's ends are calendar days on the wire (contract: "Date inputs"): the
    typed text goes out unconverted, and any shape the engine would 422 is
    refused at the field instead — unpadded, compact, day-first, not a day."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewStatementScreen(account_id="acc1", account_name="BCP", currencies=("PEN",))
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


def test_new_statement_date_end_is_required(fake_client, monkeypatch):
    """A period with no last day can never be completed,
    so an empty enter on DATE END is refused in place, as on DATE START."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewStatementScreen(account_id="acc1", account_name="BCP", currencies=("PEN",))
        await app.push_screen(screen)
        _enter(screen, "August 2026")
        _enter(screen, "2026-08-01")
        _enter(screen, "")  # date_end → rejected, stays put
        assert screen._key == "date_end"
        assert "date_end" in screen._required()
        await pilot.pause()
        assert not fake_client.posts

    run_app(scenario)


def test_the_date_start_line_says_it_orders_the_statement(fake_client, monkeypatch):
    """The hint under the bar says the first day is what orders the statement, on the
    first-day line and not on the last-day line."""
    _patch(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = NewStatementScreen()
        await app.push_screen(screen)
        await _wait_accounts(screen, pilot)
        _enter(screen, "April 2026")
        _enter(screen, "BCP")
        await wait_for(pilot, lambda: screen._key == "date_start")
        seen["start"] = screen.query_one("#hint", Static).content.plain
        _enter(screen, "2026-04-01")
        await wait_for(pilot, lambda: screen._key == "date_end")
        seen["end"] = screen.query_one("#hint", Static).content.plain

    run_app(scenario)
    assert seen["start"] == "YYYY-MM-DD · the statement's first day · it orders the statement"
    assert seen["end"] == "YYYY-MM-DD · the statement's last day"


def test_new_statement_date_start_is_required(fake_client, monkeypatch):
    """date_start orders the statement now, so an empty enter is refused in place
    rather than silently creating an unorderable statement."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = NewStatementScreen()
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
    them — not alphabetical; people have no statements, so
    the person is left out and nothing else moves."""
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_HOLDING_ACCOUNTS)
    )

    async def scenario(pilot, app):
        screen = NewStatementScreen()
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
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_HOLDING_ACCOUNTS)
    )

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert [a[1] for a in screen._accounts] == ENGINE_ORDER_BANK_NAMES
        shown = render_text(screen._accts_list._build(), width=120)
        assert in_order(shown, ENGINE_ORDER_BANK_NAMES)

    run_app(scenario)


def _patch_browse(monkeypatch, items=None, fail=False):
    """Two accounts, one holding soles and one dollars, neither with a statement
    code, one statement each — the browse screen's standard fixture. The fake reads
    like the engine: one account at a time (the account is required), the list whole,
    never paged (contract: GET /v1/statements). Returns the accounts it was asked
    for, in order."""
    reads: list = []
    rows = ITEMS if items is None else items

    def fetch(_cfg, account_id, **kw):
        assert "limit" not in kw and "offset" not in kw, "the engine refuses paging here"
        reads.append(account_id)
        if fail:
            raise RuntimeError("statements unavailable")
        return statement_list([r for r in rows if r.get("account_id") == account_id])

    monkeypatch.setattr("expense.reads.fetch_statements", fetch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole(
            [
                account_with_currencies(
                    id="acc1", name="BCP", currencies=[held_currency("PEN", 100)]
                ),
                account_with_currencies(
                    id="acc2", name="Interbank Plus", currencies=[held_currency("USD")]
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
    screen = StatementsScreen()
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    for _ in range(down):
        screen._accts_list.action_move(1)
    await wait_for(pilot, lambda: screen._acct_idx == down)
    await pilot.press("enter")
    await wait_for(pilot, lambda: screen._mode == "statements")
    return screen


def test_the_browse_opens_on_the_accounts_alone_and_reads_no_statements(monkeypatch):
    reads = _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen._mode == "accts"
        assert screen._statement_list is None  # no lower panel at all
        assert reads == []  # nothing is read until ⏎
        # alone, the account list takes the whole height; the panel halves it
        alone = screen.pane_rows()
        screen._open_aid = "acc1"
        assert screen.pane_rows() < alone
        screen._open_aid = None
        assert _crumb(screen) == ("Capture & ledger", "Statements")
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
        assert [r.key for r in screen._statement_list._rows] == ["r2"]
        assert screen._statement_list.has_focus
        assert "Statements · Interbank Plus" in (screen._statement_list._caption or "")
        assert "oldest → newest" in (screen._statement_list._caption or "")
        assert _crumb(screen) == ("Capture & ledger", "Statements", "Interbank Plus")
        # the open account keeps a ▸ so you can see whose panel this is
        names = [str(r.cells[0]) for r in screen._accts_list._rows]
        assert names == ["  BCP", "▸ Interbank Plus"]

    run_app(scenario)


def test_an_account_with_no_statements_says_so_in_the_panel(monkeypatch):
    _patch_browse(monkeypatch, items=[])

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        assert screen._statement_list._rows == []
        assert screen._statement_list._empty == "none yet · n to create one"

    run_app(scenario)


def test_the_panel_keeps_the_order_the_engine_sends(monkeypatch):
    """The account's list arrives `date_start` ascending, then creation time,
    oldest first (contract: "Statements", "Ordering"); the screen does not
    re-sort it. Served out of date order on purpose, so a re-sort would show."""
    served = [
        _statement("b-march", "acc1", "March", ("2026-03-01", "2026-03-31")),
        _statement("b-april", "acc1", "April", ("2026-04-01", "2026-04-30")),
        _statement("b-feb", "acc1", "February", ("2026-02-01", "2026-02-28")),
    ]
    _patch_browse(monkeypatch, items=served)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        assert [r.key for r in screen._statement_list._rows] == ["b-march", "b-april", "b-feb"]

    run_app(scenario)


def test_a_failed_read_leaves_the_panel_closed(monkeypatch):
    reads = _patch_browse(monkeypatch, fail=True)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("enter")
        await wait_for(pilot, lambda: reads)
        await pilot.pause()
        assert screen._mode == "accts" and screen._statement_list is None
        assert _crumb(screen) == ("Capture & ledger", "Statements")

    run_app(scenario)


def test_u_works_only_with_a_panel_open(monkeypatch):
    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert "u" not in _footer_keys(app)  # not offered on the plain list
        await pilot.press("u")
        await pilot.pause()
        assert screen._mode == "accts" and not calls
        await pilot.press("enter")
        await wait_for(pilot, lambda: screen._mode == "statements")
        assert "u" in _footer_keys(app)

    run_app(scenario)


def test_enter_reads_open_on_statements_and_edit_on_rows_in_no_statement(monkeypatch):
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
        await wait_for(pilot, lambda: screen._mode == "statements")
        assert enter_label(app) == "Open"

    run_app(scenario)


def test_esc_closes_the_panel_then_leaves_the_screen(monkeypatch):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.press("escape")
        await wait_for(pilot, lambda: screen._mode == "accts")
        assert app.screen is screen  # the panel closed; the screen stayed
        assert screen._statement_list is None and screen._accts_list.has_focus
        assert _crumb(screen) == ("Capture & ledger", "Statements")
        assert [str(r.cells[0]) for r in screen._accts_list._rows][0] == "  BCP"
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is not screen)

    run_app(scenario)


def test_highlight_from_the_panel_does_not_switch_account(monkeypatch):
    """A Highlighted sourced from the panel (Tab/click focus, no select) must
    not move the account cursor — `n` would then create under the wrong one."""
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        screen.on_cursor_list_highlighted(CursorList.Highlighted(screen._statement_list, "r1", 1))
        assert screen._acct_idx == 0

    run_app(scenario)


def test_a_statement_opens_with_the_screen_that_reads_again_after_it(monkeypatch):
    from expense.tui.screens.statements import StatementScreen

    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, StatementScreen))
        assert (app.screen._opener, app.screen._reload) == (screen, screen._load)

    run_app(scenario)


def test_coming_back_from_a_statement_keeps_the_panel_on_the_same_row(monkeypatch):
    from expense.tui.screens.statements import StatementScreen

    two = [
        _statement("b1", "acc1", "March", ("2026-03-01", "2026-03-31"), status=2),
        _statement("b2", "acc1", "April", ("2026-04-01", "2026-04-30"), status=2),
    ]
    reads = _patch_browse(monkeypatch, items=two)
    # the working screen's own reads are not what this test is about
    monkeypatch.setattr(StatementScreen, "_load_txns", lambda self, **k: None)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        screen._statement_list.action_move(1)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, StatementScreen))
        assert app.screen._id == "b2"  # the statement under the cursor opened
        old = screen._statement_list
        app.screen.dismiss()
        # the read's own list (not the old one) has the cursor back on the statement that was open
        await wait_for(
            pilot,
            lambda: (
                len(reads) == 2
                and screen._mode == "statements"
                and screen._statement_list is not old
                and screen._statement_list is not None
                and screen._statement_list.cursor_key == "b2"
            ),
            message="the panel never came back with its cursor on b2",
        )
        assert reads == ["acc1", "acc1"]  # the open account's statements, re-read
        assert screen._statement_list.cursor_key == "b2"
        assert screen._statement_list.has_focus

    run_app(scenario)


def test_n_on_the_plain_list_saves_into_that_accounts_open_panel(monkeypatch):
    """`n` with no panel open uses the account under the cursor; saved, that
    account's panel opens with the cursor on the new one."""
    rows = [dict(r) for r in ITEMS]
    reads = _patch_browse(monkeypatch, items=rows)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        screen._accts_list.action_move(1)
        await wait_for(pilot, lambda: screen._acct_idx == 1)
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, NewStatementScreen))
        form = app.screen
        assert form._values["account"] == "acc2"  # the account under the cursor
        assert form._codes == ("USD",)  # and the currencies its balance lines are named by
        # a save answered after the form was left opens this account's panel on the new one
        assert form._opener is screen and form._created is not None
        rows.append(_statement("new-1", "acc2", "May 2026", ("2026-05-01", "2026-05-31")))
        form.dismiss("new-1")  # what `_done` hands back after the POST
        await wait_for(
            pilot,
            lambda: (
                screen._statement_list is not None and screen._statement_list.cursor_key == "new-1"
            ),
        )
        assert reads == ["acc2"]
        assert screen._mode == "statements"
        assert screen._statement_list.cursor_key == "new-1"
        assert _crumb(screen)[-1] == "Interbank Plus"

    run_app(scenario)


def test_a_statement_created_after_leaving_opens_its_accounts_panel(fake_client, monkeypatch):
    """The account cursor goes with the panel it opens, though it moved while the form was
    open; the answer is the real write's, late."""
    rows = [dict(r) for r in ITEMS]
    reads = _patch_browse(monkeypatch, items=rows)
    late = LateAnswer(fake_client, "post")

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        screen._accts_list.action_move(1)
        await wait_for(pilot, lambda: screen._acct_idx == 1)
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, NewStatementScreen))
        form = app.screen
        for typed in ("May 2026", "2026-05-01", "2026-05-31", "", ""):  # name, dates, USD lines
            form.query_one("#bar", Input).value = typed
            form._recompute(typed)
            form.on_input_submitted(None)
        await wait_for(pilot, late.started.is_set)
        await app.pop_screen()  # left before the engine answered
        await wait_for(pilot, lambda: app.screen is screen)
        screen._accts_list.action_move(-1)
        await wait_for(pilot, lambda: screen._acct_idx == 0)
        new_id = form._new_id
        rows.append(_statement(new_id, "acc2", "May 2026", ("2026-05-01", "2026-05-31")))
        late.release.set()
        # `_show` ends (crumb and all) in `_mode`: a test that ends before it
        # tears the screen down under its last lines
        await wait_for(
            pilot,
            lambda: (
                screen._mode == "statements"
                and screen._statement_list is not None
                and screen._statement_list.cursor_key == new_id
            ),
            message="the new statement's panel never finished opening",
        )
        assert (screen._acct_idx, reads[-1]) == (1, "acc2")
        assert screen._statement_list.cursor_key == new_id

    run_app(scenario)


def test_the_form_hands_back_the_id_it_created(fake_client, monkeypatch):
    """The id is minted client-side in `_payload`; `_done` returns it."""
    screen = NewStatementScreen(account_id="acc1", account_name="BCP", currencies=("PEN",))
    screen._values.update(
        {"name": "May", "date_start": "2026-05-01", "date_end": "2026-05-31", "begin:PEN": 0}
    )
    payload = screen._payload()
    handed: list = []
    monkeypatch.setattr(screen, "dismiss", lambda result=None: handed.append(result))
    monkeypatch.setattr(screen, "notify", lambda *a, **k: None)
    screen._done()
    assert handed == [payload["id"]]


def test_new_statement_from_account_drops_account_field():
    screen = NewStatementScreen(account_id="acc1", account_name="BCP", currencies=("PEN",))
    assert "account" not in screen._sequence()  # account preset from browse
    assert screen._values["account"] == "acc1"
    assert screen.crumb == ("Statements", "BCP", "New")


def test_new_statement_fetch_error_notifies_not_crash(fake_client, monkeypatch):
    """An engine/config error in _load_accounts must not exit the app."""

    def boom(*a, **k):
        raise RuntimeError("engine down")

    monkeypatch.setattr("expense.reads.fetch_accounts", boom)
    notices: list = []
    monkeypatch.setattr(
        NewStatementScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = NewStatementScreen()
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
    screen = NewStatementScreen()
    screen._accounts = [
        ("acc1", "BCP Crédito"),
        ("acc2", "Interbank Plus"),
    ]
    screen._current = screen._sequence().index("account")  # `_key` is derived

    for typed in ("credito", "Crédito", "CRÉDITO", "crédito"):
        screen._recompute(typed)
        assert [a[0] for a in screen._suggestions] == ["acc1"], typed

    screen._recompute("interbank")
    assert [a[0] for a in screen._suggestions] == ["acc2"]


def test_a_new_statement_whose_account_is_gone_shows_the_engine_words_alone(
    fake_client, monkeypatch
):
    """The browse was read before its account was deleted, so `n` still offers it:
    the engine refuses the create's `account_id` (contract: POST /v1/statements).
    The refusal block is the engine's words and its
    field's words under them, with no line of the app's; the form stays open with what
    was typed, and nothing is handed back."""
    from expense.errors import EngineError

    words = "Stand-in field words."  # the contract does not print this refusal's sentence
    err = EngineError(
        "VALIDATION_ERROR",
        "Statement validation failed.",
        {"account_id": words},
        422,
        {},
        reasons={"account_id": "INVALID_REFERENCE"},
    )
    fake_client.errors["POST"] = err
    handed: list = []

    async def scenario(pilot, app):
        screen = NewStatementScreen(account_id="acc1", account_name="ALEJO", currencies=("PEN",))
        await app.push_screen(screen, handed.append)
        _enter(screen, "October 2026")  # name
        _enter(screen, "2026-10-01")  # date_start
        _enter(screen, "2026-10-31")  # date_end
        _enter(screen, "1250.00")  # begin
        typed = dict(screen._values)
        _enter(screen, "")  # end → submits
        await wait_for(pilot, lambda: refusal_block(screen) and not screen._submitting)
        assert no_failed_toast(app)
        assert refusal_block(screen) == (
            f"Failed\nVALIDATION_ERROR — Statement validation failed.\n  account_id: {words}"
        )
        assert refusal_block(screen) == f"Failed\n{refusal_text(err, None)}"
        assert app.screen is screen and screen._values == typed

    run_app(scenario, toasts=True)
    assert [path for path, _body in fake_client.posts] == ["/statements"]
    assert handed == []


# ---- the "no statement" list (`u`) ----------------------------------------------
# Statement work stays
# in the Statements view, so `u` swaps the LOWER PANE of this screen — it
# does not push a filtered ledger, and it does not touch the account cursor.
# It lists bank lines (`GET /bank-lines`), oldest first, every currency together, a split
# purchase once.
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
    # the order asked for: oldest first
    _line("bl-net", [-4490], day="2026-01-04", title="NETFLIX", code="47391026"),
    _line("bl-farm", [-6000, -4000], day="2026-03-10", title="FARMACIA", code="48201764"),
    _line("bl-uber", [-2450], day="2026-03-20", title="UBER *TRIP"),
]


def test_statement_windows_are_the_days_of_every_statement_of_the_account():
    """The `!` days are those of the account's statements, as the one read gave them."""
    from expense.tui.screens.statements import statement_windows

    assert statement_windows(ITEMS[:1]) == [("2026-03-01", "2026-03-31", "March 2026")]
    assert statement_windows(ITEMS) == [
        ("2026-03-01", "2026-03-31", "March 2026"),
        ("2026-04-01", "2026-04-30", "April 2026"),
    ]


def test_unfiled_rows_are_the_bank_columns_one_line_each_in_the_engine_order():
    """Date · title · operation · currency · amount, the signed `net_cents`, a
    dim `—` for no operation code; a split purchase is one row with its title alone and
    its total; `!` on the rows dated inside a statement's days."""
    from expense.tui.screens.statements import statement_windows, unfiled_rows

    windows = statement_windows(ITEMS[:1])
    rows = unfiled_rows(UNFILED, windows)
    assert [r[0] for r in rows] == ["bl-net", "bl-farm", "bl-uber"]  # as the engine sent them
    cells = [[str(c) for c in r[1]] for r in rows]
    # January is in no window; both March rows sit inside 'March 2026'
    assert cells == [
        ["", "2026-01-04", "NETFLIX", "47391026", "PEN", "-44.90"],
        ["!", "2026-03-10", "FARMACIA", "48201764", "PEN", "-100.00"],
        ["!", "2026-03-20", "UBER *TRIP", "—", "PEN", "-24.50"],
    ]
    assert rows[2][1][3].style == "dim"  # no operation code: a dim em dash


def test_a_split_purchase_reads_as_one_row_and_nothing_marks_it_split():
    from expense.tui.screens.statements import unfiled_rows

    rows = unfiled_rows([UNFILED[1]], [])
    assert len(rows) == 1
    assert [str(c) for c in rows[0][1]] == [
        "",
        "2026-03-10",
        "FARMACIA",
        "48201764",
        "PEN",
        "-100.00",
    ]


def _numbered(n: int) -> dict:
    return _line(f"bl{n}", [-100 * n], day=f"2025-01-{n:02d}", title=f"ROW {n}")


def _patch_unfiled(monkeypatch, items=None, total=None, count_fails=False):
    """A cursor-paged fake of `GET /bank-lines`: it refuses `offset` and any `sort`
    but `date_asc`, serves `items` in slices of the requested `limit`, and hands back
    `c<next index>` as the cursor; `count_bank_lines` answers `total`."""
    calls: list = []
    counts: list = []
    rows = UNFILED if items is None else items

    def fetch(_cfg, *, limit=None, after=None, **kw):
        assert "offset" not in kw, "the engine refuses offset"
        assert kw.get("sort") == "date_asc", "the lines in no statement are read oldest first"
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
        raise AssertionError("the no statement list reads no transactions")

    monkeypatch.setattr("expense.reads.fetch_transactions", no_ledger_read)
    monkeypatch.setattr("expense.reads.count_transactions", no_ledger_read)
    return calls, counts


async def _open_unfiled(pilot, app):
    screen = await _open_panel(pilot, app)
    await pilot.press("u")
    await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
    return screen


def test_u_reads_the_accounts_lines_in_no_statement_oldest_first(monkeypatch):
    _patch_browse(monkeypatch)
    calls, counts = _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        # the account cursor never moved, and no screen was pushed
        assert screen._acct_idx == 0 and app.screen is screen
        # one row per line, in the engine's order, under the bank's columns
        assert [r.key for r in screen._statement_list._rows] == ["bl-net", "bl-farm", "bl-uber"]
        assert screen._statement_list._headers == [
            "",
            "Date",
            "Title",
            "Operation",
            "Cur",
            "Amount",
        ]
        assert screen._statement_list._caption == (
            "In no statement · BCP   ·   3 of 3 loaded · oldest first"
            "   ·\n! dated inside a statement"
        )
        # one read of the account's lines in no statement, every currency together, no
        # dates, oldest first; the count asks the same question, with no order
        assert calls == [
            {
                "limit": 10,
                "after": None,
                "account": "acc1",
                "sort": "date_asc",
                "unreconciled": True,
                "verbose": False,
            }
        ]
        assert counts == [{"account": "acc1", "unreconciled": True, "verbose": False}]

    run_app(scenario)


def test_esc_in_no_statement_returns_to_the_panel(monkeypatch):
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("escape")
        await wait_for(pilot, lambda: screen._mode != "unfiled")
        assert screen._mode == "statements"  # the panel, not the plain account list
        assert screen._statement_list.has_focus
        assert app.screen is screen  # esc swapped the pane, it did not pop the screen
        assert [r.key for r in screen._statement_list._rows] == ["r1"]  # acc1's statements is back
        assert screen._statement_list._headers[0] == "Name"
        assert screen._statement_list._more is None  # the statements are not a growing list

    run_app(scenario)


def test_the_caption_counts_what_is_loaded_against_the_engine_count(monkeypatch):
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)], total=1716)

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        assert len(screen._statement_list._rows) == 10
        # the figure is the engine's line count, not the length of the page in hand
        assert "10 of 1716 loaded · oldest first" in (screen._statement_list._caption or "")

    run_app(scenario)


def test_pgdn_appends_the_next_ten_and_lands_on_the_first_new_row(monkeypatch):
    _patch_browse(monkeypatch)
    calls, counts = _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._statement_list._rows) == 20)
        # appended, not swapped: the first ten are still there, in order
        assert [r.key for r in screen._statement_list._rows] == [f"bl{n}" for n in range(1, 21)]
        assert screen._statement_list.cursor_index == 10  # row 11, the first new one
        assert calls[-1]["after"] == "c10" and calls[-1]["unreconciled"] is True
        assert len(counts) == 1  # no recount on pgdn
        assert "20 of 25 loaded" in (screen._statement_list._caption or "")

        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._statement_list._rows) == 25)
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
        await wait_for(pilot, lambda: len(screen._statement_list._rows) == 11)
        flags = [str(r.cells[0]) for r in screen._statement_list._rows]
        assert flags == [""] * 10 + ["!"]

    run_app(scenario)


def test_esc_from_the_edit_form_keeps_the_no_statement_rows_and_cursor(monkeypatch):
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
        await wait_for(pilot, lambda: len(screen._statement_list._rows) == 20)
        await pilot.press("down")
        key = screen._statement_list.cursor_key
        reads = len(calls)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        form = app.screen
        assert form._record["id"] == "bl12-p1"  # the line's one transaction
        assert [p.amount_cents for p in form._parts] == [-1200]  # signed
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        assert len(calls) == reads
        assert screen._statement_list.cursor_key == key == "bl12"
        assert len(screen._statement_list._rows) == 20

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
    screen._statement_list.set_cursor(screen._statement_list.index_of(key))
    await pilot.pause()


def test_enter_edits_every_row_in_no_statement_in_the_footer_the_card_and_the_key(monkeypatch):
    """`⏎ Edit` is on for every row in no statement, a split transaction included:
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
            # the ledger's `s` words
            assert _card_enter_rows(screen) == ["Edit the transaction and its parts"], key
            assert _card_group(screen, "Moving around") == [
                ("⏎", "Edit the transaction and its parts"),
                ("↓", "Down"),
            ], key
        await _cursor_on(pilot, screen, "bl-farm")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, BankLineEditFormScreen))
        assert app.screen._line is UNFILED[1]
        # a save answered after the form was left reads this list again
        assert (app.screen._opener, app.screen._reload) == (screen, screen._reload_unfiled)

    run_app(scenario)


# ---- `⏎` in no statement: the Edit form on the line and its parts ----------------
# The same Edit form, OPERATION among the shared fields; one save is one
# `PUT /bank-lines/{id}` (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts").
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
    """The no statement list, the cursor on `key`, `⏎`; the form once loaded."""
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
    """A row never split: date, title, operation, account and currency, then part 1's
    amount, category, hashtags and note, all editable; the heading is the row
    as listed; the crumb is `… ▸ Statements ▸ Edit`."""
    from expense.tui.widgets.header import Breadcrumb

    _patch_form(monkeypatch)

    async def scenario(pilot, app):
        _screen, form = await _open_form(pilot, app, "bl-uber")
        assert form._sequence() == [
            "date",
            "title",
            "operation",
            "account",
            "currency",
            *(f"0.{f}" for f in PART_FIELDS),
        ]
        assert form._locked == {"currency"}  # BCP holds one currency: shown dim, skipped
        assert form._key == "date"
        assert form.query_one("#crumb", Breadcrumb)._trail == (
            "Capture & ledger",
            "Statements",
            "Edit",
        )
        assert _heading_text(form) == "UBER *TRIP  ·  -24.50 PEN"
        assert _summary_lines(form) == [
            "date       2026-03-20",
            "title      UBER *TRIP",
            "operation  —  (optional)",
            "account    BCP",
            "currency   PEN  · BCP holds only PEN",
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
        assert form._sequence()[5:] == [f"{i}.{f}" for i in (0, 1) for f in PART_FIELDS]
        assert _heading_text(form) == "FARMACIA  ·  -100.00 PEN"
        assert _summary_lines(form) == [
            "date       2026-03-10",
            "title      FARMACIA",
            "operation  48201764",
            "account    BCP",
            "currency   PEN  · BCP holds only PEN",
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
        (
            "bl-farm",
            "account",
            "Interbank",
            {"account_id": "acc2", "statement_id": None},
        ),
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
    (`unassign_on_move`). Saved, "no statement" reads its oldest ten again, the
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
        assert screen._statement_list.cursor_index == 0

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
    holds what was typed, and how many times "no statement" was read since."""
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
    line for the reason, the form still open and "no statement" not read again."""
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
    """The form was opened
    before the line's account was archived, and a new operation number is
    saved. Under the parts, the engine's words, its field's words under them,
    and no line of the app's; the form stays open with what was typed, and
    "no statement" is not read again."""
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
        assert screen._statement_list.cursor_key == "bl-farm"

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


def test_the_card_on_the_statements_offers_open_alone(monkeypatch):
    """The panel's two `⏎` rows follow what `⏎` does: `Open` on a statement."""
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        assert _card_enter_rows(screen) == ["Open"]

    run_app(scenario)


def test_r_starts_again_from_the_oldest_ten(monkeypatch):
    _patch_browse(monkeypatch)
    calls, counts = _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._statement_list._rows) == 20)
        await pilot.press("r")
        await wait_for(pilot, lambda: len(screen._statement_list._rows) == 10)
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
        # no rows beside a guessed number: the statements are back
        assert [r.key for r in screen._statement_list._rows] == ["r1"]
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
    `DELETE /transactions/{id}` of its one transaction, then the oldest ten
    again, the cursor on row 1."""
    from expense.tui.screens.modals import ConfirmModal

    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        notes = _notes(monkeypatch, screen)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._statement_list._rows) == 20)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == "Delete this transaction?"
        assert app.screen._message == (
            "ROW 11 · -11.00 · 2025-01-11 · BCP\n"
            "It leaves every balance and report, and no screen can bring it back."
        )
        reads = len(calls)
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.deletes)
        assert fake_client.deletes == ["/transactions/bl11-p1"]
        # any write starts the list over: the oldest 10, the cursor on row 1
        await wait_for(pilot, lambda: len(calls) > reads and not screen._unfiled_busy)
        assert ("", "Transaction deleted.") in notes
        assert calls[-1]["limit"] == 10 and calls[-1]["after"] is None
        assert screen._statement_list.cursor_index == 0
        assert len(screen._statement_list._rows) == 10

    run_app(scenario)
    assert not [r for m, r in fake_client.requests if m == "GET"]  # nothing read before asking


@pytest.mark.parametrize("parts", [2, 3])
def test_d_on_a_split_purchase_asks_about_it_whole_then_deletes_it(monkeypatch, fake_client, parts):
    """3b: the purchase is one row, so `d` asks the ledger's purchase question
    with its real part count and total, reads nothing first, and `y` sends one
    `DELETE /bank-lines/{id}`; `Transaction deleted.`, then the oldest ten again,
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
            "FARMACIA · -100.00 · 2026-03-10 · BCP\nNo screen can bring it back."
        )
        reads = len(calls)
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", "Transaction deleted.") in notes)
        await wait_for(pilot, lambda: len(calls) > reads and not screen._unfiled_busy)
        assert calls[-1]["after"] is None and calls[-1]["limit"] == 10
        assert screen._statement_list.cursor_index == 0

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
        assert screen._statement_list.cursor_key == "bl-farm"

    run_app(scenario)
    assert fake_client.deletes == []


@pytest.mark.parametrize(
    ("row", "path", "status", "code", "words", "fields", "reasons"),
    [
        (
            "bl-farm",
            "/bank-lines/bl-farm",
            409,
            "CONFLICT",
            SEALED_LINE_WORDS,
            {"bank_line_id": SEALED_FIELD_WORDS},
            {"bank_line_id": "IN_COMPLETED_RECONCILIATION"},
        ),
        ("bl-farm", "/bank-lines/bl-farm", 404, "NOT_FOUND", "bank_line not found.", None, None),
        (
            "bl-net",
            "/transactions/bl-net-p1",
            409,
            "CONFLICT",
            SEALED_TRANSACTION_WORDS,
            {"transaction_id": SEALED_FIELD_WORDS},
            {"transaction_id": "IN_COMPLETED_RECONCILIATION"},
        ),
    ],
    ids=["purchase-sealed", "purchase-gone", "transaction-sealed"],
)
def test_a_refused_delete_shows_the_engine_words_and_keeps_the_list(
    monkeypatch, fake_client, row, path, status, code, words, fields, reasons
):
    """The engine refuses: its words in the "Failed" note, nothing deleted, the
    list not read again and the cursor where it was."""
    from expense.errors import EngineError
    from expense.tui.screens.modals import ConfirmModal

    _patch_browse(monkeypatch)
    calls, _counts = _patch_unfiled(monkeypatch)
    err = EngineError(code, words, fields, status, {}, reasons)
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
        assert notes[0][1].startswith(f"{code} — {words}")
        assert len(calls) == reads and len(screen._statement_list._rows) == 3
        assert screen._statement_list.cursor_key == row

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
    """The pane was read
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
        assert len(calls) == reads and len(screen._statement_list._rows) == 3
        assert screen._statement_list.cursor_key == row

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


@pytest.mark.parametrize(
    ("row", "path", "first_line"),
    [
        ("bl-net", "/transactions/bl-net-p1", "Not deleted · NETFLIX · -44.90"),
        ("bl-farm", "/bank-lines/bl-farm", "Not deleted · FARMACIA · -100.00"),
    ],
    ids=["never split", "split"],
)
@pytest.mark.parametrize("refused", [False, True], ids=["deleted", "refused"])
def test_a_delete_answered_after_leaving_says_how_it_ended(
    monkeypatch, fake_client, row, path, first_line, refused
):
    """`d` in no statement, the screen left before the engine answers: the deleted note,
    or the refusal's words under what was not deleted, 10 seconds."""
    from expense.tui.screens.modals import ConfirmModal

    err = EngineError("CONFLICT", "stand-in [not markup]", None, 409, {})
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)
    late = LateAnswer(fake_client, "delete", err if refused else None)
    shown: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = await _open_unfiled(pilot, app)
        await _cursor_on(pilot, screen, row)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await leave_then_answer(pilot, app, screen, late, notes)
        shown.extend(notes)

    run_app(scenario)
    if not refused:
        assert [(t, m) for t, m, _ in shown] == [("", "Transaction deleted.")]
        return
    [(title, message, options)] = shown
    assert title == first_line
    assert message == list_refusal_text(err)
    assert (options["severity"], options["timeout"], options["markup"]) == ("error", 10, False)


def test_d_does_nothing_outside_the_unfiled_pane(monkeypatch, fake_client):
    """`d` is the pane's key, not the screen's: on the statements it must not fire
    — one key per job, and a statement's own delete lives on the statement screen."""
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("d")
        await pilot.pause()
        assert app.screen is screen  # no confirm opened
        assert not fake_client.deletes

    run_app(scenario)


# ---- everything fits at 80x24 (the size every test runs at) ------------------------

FIVE_ACCOUNTS = [
    account_with_currencies(
        id=f"a{i}", name=name, statement_code="VIS", currencies=[held_currency("PEN", 100)]
    )
    for i, name in enumerate(["Visa BCP", "IBK Visa", "Sueldo Soles", "BBVA Dolares", "Extra"])
]


def _five_accounts(monkeypatch, statements: list[dict]) -> None:
    _patch_browse(monkeypatch, items=statements)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(FIVE_ACCOUNTS))


def _footer_whole(app) -> None:
    """Every key the screen offers is drawn whole in the last line, words and all."""
    drawn = " ".join(screen_lines(app)[-1].split())
    offered = [
        f"{app.get_key_display(a.binding)} {a.binding.description}"
        for a in app.screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]
    assert offered
    for key in offered:
        assert key in drawn, (key, drawn)


def _numbered_statements(count: int) -> list[dict]:
    return [
        _statement(
            f"s{n}",
            "a0",
            f"VIS-2026{n:02d}",
            (f"2026-{n:02d}-01", f"2026-{n:02d}-28"),
            unplaced_count=0,
            shared_place_count=0,
        )
        for n in range(1, count + 1)
    ]


def test_the_statements_browse_fits_80x24_with_no_paging_and_its_whole_footer(monkeypatch):
    """Four accounts and three statements, every statement on one
    page, no `pgdn`, and the footer's last key `u No statement` whole."""
    _five_accounts(monkeypatch, _numbered_statements(3))
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(FIVE_ACCOUNTS[:4]))

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.pause()
        assert screen._statement_list.page_status is None
        assert "pgdn" not in screen_lines(app)[-1]
        assert len([line for line in screen_lines(app) if "VIS-2026" in line]) == 3
        assert screen_lines(app)[-1].endswith("u No statement")
        _footer_whole(app)

    run_app(scenario)


def _unfiled_lines(count: int) -> list[dict]:
    return [
        _line(f"b{n}", [-100 - n], day=f"2026-03-{n + 1:02d}", title=f"T{n}") for n in range(count)
    ]


def _drawn_unfiled(app) -> list[str]:
    return [line for line in screen_lines(app) if " PEN " in line and "2026-03-" in line]


def test_u_under_four_accounts_shows_all_four_lines(monkeypatch):
    """Four accounts, six lines in no statement (the room the frame leaves at 80x24), all six
    drawn, one blank line under them and the footer, `#content` not scrolling and every key
    whole."""
    _five_accounts(monkeypatch, [])
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(FIVE_ACCOUNTS[:4]))
    _patch_unfiled(monkeypatch, items=_unfiled_lines(6))

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        await pilot.pause()
        assert screen.query_one("#content").max_scroll_y == 0
        shown = screen_lines(app)
        assert len(_drawn_unfiled(app)) == 6
        assert any("6 of 6 loaded" in line for line in shown)
        assert shown[-2].strip() == ""  # the one blank line above the footer
        assert shown[-3].lstrip().startswith("2026-03-06")
        _footer_whole(app)

    run_app(scenario)


def test_u_with_five_accounts_fills_the_room_and_pages_the_rest(monkeypatch):
    """Under five accounts the room holds five lines, exactly five are drawn with no
    blank line left, the rest come by moving the cursor, `#content` never scrolls."""
    _five_accounts(monkeypatch, [])
    _patch_unfiled(monkeypatch, items=_unfiled_lines(8))

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        await pilot.pause()
        assert screen.query_one("#content").max_scroll_y == 0
        rows = _drawn_unfiled(app)
        assert len(rows) == 5
        assert screen_lines(app)[-3].lstrip().startswith("2026-03-05")  # no gap under the rows
        assert any("8 of 8 loaded" in line for line in screen_lines(app))
        await pilot.press("down", "down", "down", "down", "down", "down")
        later = _drawn_unfiled(app)
        assert len(later) == 3 and later != rows  # the rest, a page not a scroll
        assert screen.query_one("#content").max_scroll_y == 0
        _footer_whole(app)

    run_app(scenario)


def test_a_statements_list_that_needs_a_page_keeps_in_order_and_every_key_whole(monkeypatch):
    """Nine statements under five accounts do not fit one page: the panel pages them, so
    `#content` has no scrollbar to cut the Order column to `in or…`, and the footer, with
    `pgdn`/`pgup` in it, keeps `u No statement` whole."""
    _five_accounts(monkeypatch, _numbered_statements(9))

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.pause()
        assert screen._statement_list.row_count == 9
        assert screen._statement_list.page_status is not None  # more than one page
        assert screen.query_one("#content").max_scroll_y == 0
        shown = [line for line in screen_lines(app) if "VIS-2026" in line]
        assert shown
        assert all(line.endswith("in order") for line in shown)
        assert "pgdn Next" in screen_lines(app)[-1]
        _footer_whole(app)

    run_app(scenario)


LONG_NAME = "Cuenta Sueldo Interbank Soles Principal Hogar"


def _long_name_accounts(monkeypatch, statements: list[dict]) -> None:
    accounts = [
        account_with_currencies(
            id=f"a{i}",
            name=LONG_NAME if i == 0 else name,
            statement_code="VIS",
            currencies=[held_currency("PEN", 100), held_currency("USD", 100)],
        )
        for i, name in enumerate(["", "IBK Visa", "Sueldo Soles", "BBVA Dolares", "Extra"])
    ]
    _patch_browse(monkeypatch, items=statements)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(accounts))


def test_a_caption_that_wraps_is_counted_before_the_panel_exists(monkeypatch):
    """The page size is measured with the caption the panel is about to draw, at the width
    the list will have: a long account name wraps it to two lines, and `#content` still does
    not scroll, every row drawn whole."""
    _long_name_accounts(monkeypatch, _numbered_statements(9))

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.pause()
        assert screen._caption_lines() == 2
        assert screen.query_one("#content").max_scroll_y == 0
        shown = [line for line in screen_lines(app) if "VIS-2026" in line]
        assert shown and len(shown) == screen._statement_list._page_size
        assert all(line.endswith("in order") for line in shown)
        await pilot.press("r")  # a refresh measures again, to the same effect
        await pilot.pause()
        assert screen.query_one("#content").max_scroll_y == 0
        _footer_whole(app)

    run_app(scenario)


def test_u_keeps_its_rows_whole_under_a_caption_that_wraps(monkeypatch):
    _long_name_accounts(monkeypatch, [])
    _patch_unfiled(monkeypatch, items=_unfiled_lines(12))

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        await pilot.pause()
        assert screen.query_one("#content").max_scroll_y == 0
        rows = [line for line in screen_lines(app) if "PEN" in line and "20" in line]
        assert rows and len(rows) == screen._statement_list._page_size
        _footer_whole(app)

    run_app(scenario)


def test_the_browse_frame_costs_exactly_browse_frame_lines(monkeypatch):
    """`BROWSE_FRAME_LINES` is derived from what the three lists draw, so an overcount
    shows as well as an undercount: each list's frame, without its rows and its caption."""
    _five_accounts(monkeypatch, _numbered_statements(2))

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.pause()
        frame = screen.BROWSE_FRAME_LINES

        def drawn(lst, rows: int, caption: int) -> int:
            return render_text(lst.framed(), width=78).count("\n") - rows - caption

        assert drawn(screen._accts_list, 5, 0) == frame
        assert drawn(screen._statement_list, 2, screen._caption_lines()) == frame
        screen._statement_list.set_divider("blank")  # the lines in no statement: no status line
        screen._statement_list.set_status_line(False)
        assert (
            drawn(screen._statement_list, 2, screen._caption_lines()) == screen.UNFILED_FRAME_LINES
        )

    run_app(scenario)


def test_a_wide_terminal_measures_the_caption_at_the_card_width(monkeypatch):
    """Above 102 columns the lists sit in a card capped at `CARD_WIDTH`, narrower than
    `#content`: a caption between the two widths still wraps, and is counted."""
    _long_name_accounts(monkeypatch, _numbered_statements(9))
    _patch_unfiled(monkeypatch, items=_unfiled_lines(12))

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.pause()
        assert screen.query_one("#content").max_scroll_y == 0
        shown = [line for line in screen_lines(app) if "VIS-2026" in line]
        assert shown and len(shown) == screen._statement_list._page_size
        assert all(line.rstrip().endswith("in order") for line in shown)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        await pilot.pause()
        assert screen.query_one("#content").max_scroll_y == 0
        rows = [line for line in screen_lines(app) if "PEN" in line and "20" in line]
        assert rows and len(rows) == screen._statement_list._page_size

    run_app(scenario, size=(140, 24))


# ---- a long account name in the crumb ------------------------------------

CRUMB_NAME = "Cuenta de ahorros en soles del Banco de Credito del Peru"[:50]


def _crumb_name_accounts(monkeypatch):
    reads = _patch_browse(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole(
            [account_with_currencies(id="acc1", name=CRUMB_NAME, currencies=[held_currency("PEN")])]
        ),
    )
    return reads


def _drawn_crumb(app) -> tuple[str, str]:
    """The crumb line as drawn, and the line under it (the rule)."""
    lines = screen_lines(app)
    return lines[0].strip(), lines[1].strip()


@pytest.mark.parametrize(("stale", "ending"), [(True, "…  !"), (False, "…"), (None, "…")])
def test_a_long_account_name_cuts_the_crumb_to_one_line_and_keeps_the_alert(
    monkeypatch, stale, ending
):
    reads = _crumb_name_accounts(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        assert _crumb(screen)[-1] == CRUMB_NAME
        app._set_rate_stale(stale)
        await pilot.pause()
        crumb, rule = _drawn_crumb(app)
        assert crumb.startswith("◈ EXPENSE WORLD") and crumb.endswith(ending), crumb
        assert ("!" in crumb) is bool(stale)
        assert rule and set(rule) <= set("▁─━ "), rule  # the line under it is the rule
        assert reads == ["acc1"]

    run_app(scenario, size=(80, 24))


def test_a_short_crumb_is_not_cut(monkeypatch):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        await _open_panel(pilot, app)
        app._set_rate_stale(True)
        await pilot.pause()
        crumb, rule = _drawn_crumb(app)
        assert "…" not in crumb
        assert crumb.endswith("BCP  !")
        assert rule and set(rule) <= set("▁─━ "), rule

    run_app(scenario, size=(80, 24))


def test_the_crumb_is_cut_again_whenever_the_terminal_is_resized(monkeypatch):
    _crumb_name_accounts(monkeypatch)

    async def scenario(pilot, app):
        await _open_panel(pilot, app)
        app._set_rate_stale(True)
        for width in (80, 60, 140, 80):
            await pilot.resize_terminal(width, 24)
            await pilot.pause()
            crumb, _rule = _drawn_crumb(app)
            assert len(crumb) <= width, (width, crumb)
            if width < 100:
                assert crumb.endswith("…  !"), (width, crumb)
            else:
                assert crumb.endswith(CRUMB_NAME + "  !"), (width, crumb)

    run_app(scenario, size=(80, 24))


# ---- the browse at 80 columns ----------

LONG_NAME_50 = "Cuenta corriente en soles y dolares del Banco de Credito"[:50]


def _two_currency_accounts(monkeypatch, names):
    """The browse's accounts: each of `names` holding soles and dollars, in a debt."""
    reads = _patch_browse(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole(
            [
                account_with_currencies(
                    id=f"acc{i}",
                    name=name,
                    currencies=[held_currency("PEN", -26050), held_currency("USD", -3098)],
                )
                for i, name in enumerate(names)
            ]
        ),
    )
    return reads


def _has_header_and_rule(app) -> bool:
    lines = screen_lines(app)
    return any(
        "Account" in line and "Balances" in line and "─" in lines[i + 1]
        for i, line in enumerate(lines[:-1])
    )


def _header_and_rule(app) -> tuple[str, str]:
    lines = screen_lines(app)
    at = next(i for i, line in enumerate(lines) if "Account" in line and "Balances" in line)
    return lines[at], lines[at + 1]


def test_the_rule_under_the_accounts_header_is_60_wide_under_its_first_letter(monkeypatch):
    _two_currency_accounts(monkeypatch, ["Visa BCP", "IBK Visa"])

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await wait_for(pilot, lambda: _has_header_and_rule(app), message="header never drawn")
        header, rule = _header_and_rule(app)
        assert rule == " " * header.index("Account") + "─" * 60
        await pilot.press("enter")
        await wait_for(pilot, lambda: screen._mode == "statements")
        await wait_for(pilot, lambda: _has_header_and_rule(app), message="header never drawn")
        header, rule = _header_and_rule(app)
        assert rule == " " * header.index("Account") + "─" * 60

    run_app(scenario, size=(80, 24))


def test_a_long_account_name_is_cut_with_an_ellipsis_and_every_balance_shows_whole(monkeypatch):
    _two_currency_accounts(monkeypatch, [LONG_NAME_50, "Visa BCP", "IBK Visa"])

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await wait_for(
            pilot,
            lambda: len([line for line in screen_lines(app) if "PEN + USD" in line]) == 3,
            message="the three account rows were never drawn",
        )
        rows = [line for line in screen_lines(app) if "PEN + USD" in line]
        assert all(row.rstrip().endswith("-260.50 PEN   -30.98 USD") for row in rows), rows
        assert "…" in rows[0] and LONG_NAME_50 not in rows[0]
        assert rows[0].lstrip().startswith(LONG_NAME_50[:20])
        assert all("…" not in row for row in rows[1:])

    run_app(scenario, size=(80, 24))


def test_a_blank_line_stands_between_the_accounts_page_line_and_the_statements_caption(
    monkeypatch,
):
    _two_currency_accounts(monkeypatch, [f"Account {n}" for n in range(1, 7)])

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        await pilot.pause()
        lines = screen_lines(app)
        at = next(i for i, line in enumerate(lines) if "rows 1-5 of 6 · page 1 of 2" in line)
        assert lines[at + 1] == ""
        assert lines[at + 2].strip().startswith("Statements · Account 1")
        assert screen.query_one("#content").max_scroll_y == 0

    run_app(scenario, size=(80, 24))


def test_the_card_of_the_no_statement_list_lists_only_the_keys_that_work_there(monkeypatch):
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 6)])

    async def scenario(pilot, app):
        await _open_unfiled(pilot, app)
        screen = app.screen
        from expense.tui.screens.help import screen_inventory

        _, groups = screen_inventory(screen)
        assert [g.title for g in groups] == [
            "This screen",
            "Moving around",
            "Always true",
            "Everywhere",
        ]
        down = next(r for r in groups[1].rows if r.keys == "↓")
        assert down.note == "(↑ up)"
        assert _card_group(screen, "This screen") == [
            ("d", "Delete"),
            ("r", "Refresh"),
            ("esc", "Back"),
        ]
        assert _card_group(screen, "Moving around") == [
            ("⏎", "Edit the transaction and its parts"),
            ("↓", "Down"),
        ]
        await pilot.press("question_mark")
        await pilot.pause()
        lines = screen_lines(app)
        assert not any("▼" in line or "▲" in line for line in lines)
        assert any("[?] or [esc] close" in line for line in lines)

    run_app(scenario, size=(80, 24))


def test_the_card_lists_pgdn_only_while_more_rows_are_left_to_load(monkeypatch):
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 26)])

    async def scenario(pilot, app):
        screen = await _open_unfiled(pilot, app)
        assert _card_group(screen, "Moving around") == [
            ("⏎", "Edit the transaction and its parts"),
            ("↓", "Down"),
            ("pgdn", "Load the next 10 rows under these"),
        ]
        await pilot.press("question_mark")
        await pilot.pause()
        assert not any("▼" in line for line in screen_lines(app))
        await pilot.press("escape")
        for _ in range(2):
            await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._statement_list._rows) == 25)
        assert ("pgdn", "Load the next 10 rows under these") not in _card_group(
            screen, "Moving around"
        )

    run_app(scenario, size=(80, 24))


def test_the_card_of_the_account_list_has_no_d_and_u_only_once_a_panel_has_been_opened(
    monkeypatch,
):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert _card_group(screen, "This screen") == [
            ("n", "New"),
            ("r", "Refresh"),
            ("esc", "Back"),
        ]
        await pilot.press("enter")
        await wait_for(pilot, lambda: screen._mode == "statements")
        assert ("u", "This account's rows that are in no statement") in _card_group(
            screen, "This screen"
        )

    run_app(scenario, size=(80, 24))


def test_the_card_of_the_statements_panel_closes_the_panel_and_pages_only_with_several_pages(
    monkeypatch,
):
    _five_accounts(monkeypatch, _numbered_statements(3))
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(FIVE_ACCOUNTS[:4]))

    async def one_page(pilot, app):
        screen = await _open_panel(pilot, app)
        assert _card_group(screen, "This screen") == [
            ("esc", "Close the panel"),
            ("n", "New"),
            ("u", "This account's rows that are in no statement"),
            ("r", "Refresh"),
        ]
        assert _card_group(screen, "Moving around") == [("⏎", "Open"), ("↓", "Down")]

    run_app(one_page, size=(80, 24))

    _five_accounts(monkeypatch, _numbered_statements(9))

    async def several_pages(pilot, app):
        screen = await _open_panel(pilot, app)
        assert ("esc", "Back") not in _card_group(screen, "This screen")
        assert ("d", "Delete") not in _card_group(screen, "This screen")
        assert _card_group(screen, "Moving around") == [
            ("⏎", "Open"),
            ("↓", "Down"),
            ("pgdn", "Next page"),
        ]
        await pilot.press("pagedown")
        await pilot.pause()
        assert ("pgup", "Previous page") in _card_group(screen, "Moving around")

    run_app(several_pages, size=(80, 24))


def test_the_card_of_the_account_list_lists_no_page_key_while_one_page_holds_the_accounts(
    monkeypatch,
):
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen._mode == "accts"
        assert _card_group(screen, "Moving around") == [("⏎", "Its statements"), ("↓", "Down")]

    run_app(scenario, size=(80, 24))


def test_the_card_of_the_account_list_lists_the_page_keys_once_they_work(monkeypatch):
    _two_currency_accounts(monkeypatch, [f"Account {n}" for n in range(1, 25)])

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen._mode == "accts"
        keys = _card_group(screen, "Moving around")
        assert ("pgdn", "Next page") in keys and ("pgup", "Previous page") not in keys
        assert not any(desc.startswith("Load the next") for _, desc in keys)
        await pilot.press("pagedown")
        await pilot.pause()
        assert ("pgup", "Previous page") in _card_group(screen, "Moving around")

    run_app(scenario, size=(80, 24))


def test_the_no_statement_list_card_leaves_the_gutters_beside_it_blank(monkeypatch):
    _patch_browse(monkeypatch)
    _patch_unfiled(monkeypatch, items=[_numbered(n) for n in range(1, 6)])

    async def scenario(pilot, app):
        await _open_unfiled(pilot, app)
        await pilot.press("question_mark")
        await pilot.pause()
        assert_card_gutters_blank(screen_lines(app), 80)

    run_app(scenario, size=(80, 24))


def test_the_card_of_the_account_list_lists_no_list_key_with_no_bank_account_and_all_with_one(
    monkeypatch,
):
    _patch_browse(monkeypatch)
    bank_accounts: list = []
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(bank_accounts))

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        _, groups = screen_inventory(screen)
        assert [g.title for g in groups] == ["This screen", "Always true", "Everywhere"]
        assert _card_group(screen, "This screen") == [
            ("n", "New"),
            ("r", "Refresh"),
            ("esc", "Back"),
        ]
        bank_accounts.append(
            account_with_currencies(id="acc1", name="BCP", currencies=[held_currency("PEN", 100)])
        )
        await pilot.press("r")
        await wait_for(pilot, lambda: bool(screen.query_one(CursorList)._rows))
        assert _card_group(screen, "Moving around") == [
            ("⏎", "Its statements"),
            ("↓", "Down"),
        ]

    run_app(scenario, size=(80, 24))


def _panel_footer_and_card(app):
    """The footer the panel shows now, and the `?` card's keys for its list."""
    from expense.tui.screens.help import listed_bindings
    from tests.unit.test_tui_fitting_footer import _footer

    panel = app.screen._statement_list
    card = {b.key for b in listed_bindings(panel)}
    card |= {f"screen:{b.key}" for b in listed_bindings(app.screen)}
    return _footer(app).strip(), card


#: unfiled -> (the footer with no row, the footer with rows) at 80 columns
PANEL_FOOTERS = {
    False: (
        "esc Close the panel  r Refresh  ? Keys  n New  u No statement",
        "⏎ Open  esc Close the panel  r Refresh  ? Keys  n New  u No statement",
    ),
    True: (
        "esc Back  r Refresh  ? Keys",
        "esc Back  ⏎ Edit  d Delete  r Refresh  ? Keys",
    ),
}


#: unfiled -> (the card's keys with no row, with rows): the panel's list, then the screen's
PANEL_CARDS = {
    False: (
        {"screen:escape", "screen:n", "screen:question_mark", "screen:r", "screen:u"},
        {"down", "enter", "space", "up"}
        | {"screen:escape", "screen:n", "screen:question_mark", "screen:r", "screen:u"},
    ),
    True: (
        {"screen:escape", "screen:question_mark", "screen:r"},
        {"down", "enter", "space", "up"}
        | {"screen:d", "screen:escape", "screen:question_mark", "screen:r"},
    ),
}


@pytest.mark.parametrize("unfiled", [False, True])
def test_the_panel_without_a_row_keeps_no_key_that_needs_one_and_gets_them_back(
    monkeypatch, unfiled
):
    """Each panel kind (an account's statements, its rows in no statement): empty, the
    footer and the `?` card drop `⏎` and the list keys; with a row they are listed."""
    _patch_browse(monkeypatch, items=[])
    _patch_unfiled(monkeypatch, items=[])

    async def scenario(pilot, app):
        screen = await _open_panel(pilot, app)
        if unfiled:
            await pilot.press("u")
            await wait_for(pilot, lambda: screen._mode == "unfiled")
        await wait_for(pilot, lambda: not screen._statement_list.has_rows)
        await pilot.pause()
        return _panel_footer_and_card(app)

    empty_footer, empty_card = run_app(scenario, size=(80, 24))
    assert "⏎" not in empty_footer
    assert empty_card == PANEL_CARDS[unfiled][0]
    assert "screen:d" not in empty_card
    assert empty_footer == PANEL_FOOTERS[unfiled][0]

    if unfiled:
        _patch_unfiled(monkeypatch)
    else:
        _patch_browse(monkeypatch)

    async def with_rows(pilot, app):
        screen = await _open_panel(pilot, app)
        if unfiled:
            await pilot.press("u")
            await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        await pilot.pause()
        return _panel_footer_and_card(app)

    footer, card = run_app(with_rows, size=(80, 24))
    assert footer == PANEL_FOOTERS[unfiled][1]
    assert card == PANEL_CARDS[unfiled][1]


def test_the_screen_has_no_row_while_its_list_is_off_screen_after_a_failed_read(monkeypatch):
    """A failed refresh swaps the list out; the held reference must not count as a row."""
    _patch_browse(monkeypatch)

    async def scenario(pilot, app):
        screen = StatementsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen.has_rows
        monkeypatch.setattr(
            "expense.reads.fetch_accounts",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("engine down")),
        )
        await pilot.press("r")
        await wait_for(pilot, lambda: not screen._accts_list.is_attached)
        await pilot.pause()
        assert not screen.has_rows

    run_app(scenario, size=(80, 24))
