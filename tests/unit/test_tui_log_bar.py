"""The LOG bar — one typed line, a staged batch, one save.

Pure builders first (the staged table, its summary and the error block render
through a Rich console with no app), then one pilot test per screen state.

The save follows the four calls in docs/decisions.md "What a half-written
batch means": the screen stays
and the ticks are the receipt, a partial failure re-sends only what did not
land, `ctrl+s` leaves an unstaged line in the bar alone, and the discard card's
third answer saves before it leaves.
"""

from dataclasses import replace
from datetime import date

import pytest
from rich.text import Text
from textual.widgets import Input, Label, Static

from expense.errors import EngineConnectionError, EngineError
from expense.quickadd.parse import parse
from expense.quickadd.route import route
from expense.reads import QuickAddRefs
from expense.tui.screens.log_bar import (
    LEGEND_LINE,
    AccountPeek,
    LogBarScreen,
    Staged,
    format_date_cell,
    peek_rows,
    peek_status,
    save_errors,
    save_receipt,
    span_style,
    staged_rows,
    staged_summary,
    staged_table,
)
from expense.tui.screens.modals import DiscardStagedModal
from expense.tui.theme import ACCENT, PALETTE
from tests.unit.helpers import (
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_NAMES,
    HASHTAG_REFUSALS,
    cursor_page,
    hashtag_refusal,
    in_order,
    refusal_text,
    render_text,
    run_app,
    wait_for,
    whole,
)

ACCOUNTS = [
    {
        "id": "acc1",
        "name": "BCP Signature PEN",
        "currency_code": "PEN",
        "is_person": False,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "acc2",
        "name": "BCP Signature USD",
        "currency_code": "USD",
        "is_person": False,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "acc3",
        "name": "BCP PEN",
        "currency_code": "PEN",
        "is_person": False,
        "opening_balance_transaction_id": None,
    },
]
CATEGORIES = {
    "items": [
        {"id": "cat1", "name": "KORAKUEN", "is_system": False},
        {"id": "cat2", "name": "TRANSPORTE", "is_system": False},
    ]
}
HASHTAGS = {"items": [{"id": "h1", "name": "CAJA CHICA"}, {"id": "h2", "name": "TAXI"}]}

REFS = QuickAddRefs(
    accounts=[
        ("acc1", "BCP Signature PEN", "PEN"),
        ("acc2", "BCP Signature USD", "USD"),
        ("acc3", "BCP PEN", "PEN"),
    ],
    categories=[("cat1", "KORAKUEN"), ("cat2", "TRANSPORTE")],
    hashtags=[("h1", "CAJA CHICA"), ("h2", "TAXI")],
    account_names={
        "acc1": "BCP Signature PEN",
        "acc2": "BCP Signature USD",
        "acc3": "BCP PEN",
    },
    category_names={"cat1": "KORAKUEN", "cat2": "TRANSPORTE"},
    hashtag_names={"h1": "CAJA CHICA", "h2": "TAXI"},
)

TODAY = date(2026, 8, 20)


PEEK_ITEMS = [
    {
        "id": "t1",
        "date": "2026-08-20T10:00:00-05:00",
        "title": "WONG CAYMA",
        "amount_cents": -15240,
        "account_id": "acc1",
        "category_id": "cat1",
        "hashtag_ids": ["h1"],
        "line_code": "#000002",
        "statement_line": None,
    },
    {
        "id": "t2",
        "date": "2026-08-19T10:00:00-05:00",
        "title": "NETFLIX",
        "amount_cents": -4490,
        "account_id": "acc1",
        "category_id": "cat2",
        "hashtag_ids": [],
        "line_code": "#000001",
        "statement_line": None,
    },
]
PEEK_BODY = cursor_page(PEEK_ITEMS, next_cursor="c40", limit=40)


class _PeekFetch:
    """Stands in for `fetch_transactions` (called) and `count_transactions`
    (`.count`), recording the account of each read. Refuses `offset`, as the
    engine does."""

    def __init__(
        self,
        body=None,
        error: Exception | None = None,
        total: int = 214,
        count_error: Exception | None = None,
    ) -> None:
        self.body = PEEK_BODY if body is None else body
        self.error = error
        self.total = total
        self.count_error = count_error
        self.accounts: list[str] = []
        self.counted: list[str] = []

    def __call__(self, _cfg, **kw):
        assert "offset" not in kw, "the engine refuses offset"
        self.accounts.append(kw.get("account"))
        if self.error is not None:
            raise self.error
        return self.body

    def count(self, _cfg, **kw):
        self.counted.append(kw.get("account"))
        if self.count_error is not None:
            raise self.count_error
        return self.total


def _patch(monkeypatch, peek: "_PeekFetch | None" = None) -> "_PeekFetch":
    """Screen-specific patches; the client/config seams come from fake_client.

    The peek's own fetch is patched for **every** pilot test, not only the ones
    that assert on it: the panel fires on any line that names an account, and
    an unpatched fetch would be a real request out of a unit test.
    """
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(ACCOUNTS))
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: CATEGORIES)
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: HASHTAGS)
    peek = peek or _PeekFetch()
    monkeypatch.setattr("expense.reads.fetch_transactions", peek)
    monkeypatch.setattr("expense.reads.count_transactions", peek.count)
    return peek


def _text(renderable, width: int = 120) -> str:
    return render_text(renderable, width=width)


def _styled(renderable, width: int = 120) -> str:
    """Rendered *with* its ANSI codes — the only way to see reverse video."""
    return render_text(renderable, width=width, ansi=True)


def _stage(line: str, today: date = TODAY) -> Staged:
    parsed = parse(
        line,
        accounts=REFS.accounts,
        categories=REFS.categories,
        hashtags=REFS.hashtags,
        today=today,
    )
    return Staged(line=line, parsed=parsed, routing=route(parsed, today))


LEDGER_LINE = "tottus porongoche -38.60 $BCP Signature PEN @KORAKUEN #CAJA CHICA"
NO_ACCOUNT_LINE = "apparka mall -3.50 @TRANSPORTE #TAXI 18/08/2026"  # refused on ↵
NO_CATEGORY_LINE = "apparka mall -3.50 $BCP PEN #TAXI 18/08/2026"  # stages → @Pendiente
NO_TITLE_LINE = "-6.60 $BCP PEN"  # stages as a titleless row
AHEAD_LINE = "alquiler -1800 $BCP PEN @KORAKUEN 22/08/2026"  # refused on ↵
USD_LINE = "shimaya ramen -96.00 $BCP Signature USD @KORAKUEN"


# ---- pure: the staged table -------------------------------------------------
def test_ledger_row_is_marked():
    out = _text(staged_table([_stage(LEDGER_LINE)], REFS, today=TODAY.isoformat()))
    assert "•" in out
    assert "goes to" not in out
    assert "TOTTUS" not in out  # the title is shown verbatim, never upper-cased
    assert "tottus porongoche" in out
    assert "-38.60" in out and "BCP Signature PEN" in out and "#CAJA CHICA" in out


def test_a_line_with_no_account_is_refused_not_staged():
    """Routing's answer for the line `↵` refuses — the screen never builds a
    row from it."""
    entry = _stage(NO_ACCOUNT_LINE)
    assert entry.routing.refused
    assert "the line names no account" in entry.routing.reasons


def test_row_with_no_category_reads_as_pendiente():
    """The category cell already says where the engine will file it."""
    out = _text(staged_table([_stage(NO_CATEGORY_LINE)], REFS, today=TODAY.isoformat()))
    assert "•" in out
    assert "pendiente" in out.lower()
    assert "apparka mall" in out


def test_row_with_no_title_shows_a_dash():
    out = _text(staged_table([_stage(NO_TITLE_LINE)], REFS, today=TODAY.isoformat()))
    assert "—" in out
    assert "(no title)" not in out


def test_row_dated_ahead_is_refused_though_it_is_complete():
    entry = _stage(AHEAD_LINE)
    assert entry.parsed.is_complete  # nothing is missing — only the date is
    assert entry.routing.refused
    assert "it is dated ahead" in entry.routing.reasons


def test_row_without_tags_shows_a_dim_dash():
    out = _text(staged_table([_stage(USD_LINE)], REFS, today=TODAY.isoformat()))
    assert "—" in out


def test_empty_list_is_the_invitation_not_a_table():
    out = _text(staged_table([], REFS))
    assert "Nothing staged" in out
    assert "tottus -38.60 $signature @korakuen #caja hoy" in out
    assert "date" not in out  # no header row when there is nothing to head


def test_picked_row_renders_differently_from_its_neighbours():
    entries = [_stage(LEDGER_LINE), _stage(USD_LINE)]
    plain = _styled(staged_table(entries, REFS, palette=PALETTE, today=TODAY.isoformat()))
    picked = _styled(
        staged_table(entries, REFS, palette=PALETTE, picked=1, today=TODAY.isoformat())
    )
    assert plain != picked
    # reverse video, the app-wide cursor — applied as a Rich style, never CSS
    assert "\x1b[7m" in picked and "\x1b[7m" not in plain


# ---- pure: the date cell ----------------------------------------------------
def test_date_cell_hides_the_current_year_and_shows_any_other():
    assert format_date_cell("2026-08-18", "2026-08-20") == "18 Aug"
    # a two-digit year is only safe to accept because a misread stays visible
    assert format_date_cell("2024-08-18", "2026-08-20") == "18 Aug 2024"


# ---- pure: the summary ------------------------------------------------------
def test_summary_with_one_currency_reads_as_the_mockup_drew_it():
    entries = [_stage(LEDGER_LINE), _stage("shimaya ramen -96.00 $BCP PEN @KORAKUEN")]
    out = _text(staged_summary(entries, REFS))
    assert "2 staged" in out  # everything is going to the ledger
    assert "-134.60 PEN" in out


def test_summary_totals_per_currency_never_adds_soles_to_dollars():
    out = _text(staged_summary([_stage(LEDGER_LINE), _stage(USD_LINE)], REFS))
    assert "-38.60 PEN" in out
    assert "-96.00 USD" in out
    assert "-134.60" not in out


def test_summary_counts_the_rows_that_will_land_as_pendiente():
    entries = [_stage(LEDGER_LINE), _stage(NO_CATEGORY_LINE), _stage(NO_TITLE_LINE)]
    out = _text(staged_summary(entries, REFS), width=160)
    assert "3 staged" in out
    assert "-48.70 PEN" in out
    assert "2 pendiente" in out
    assert "Inbox" not in out


def test_summary_of_an_empty_list_is_silent():
    assert _text(staged_summary([], REFS)).strip() == ""


# ---- pure: colouring --------------------------------------------------------
def test_span_styles_come_from_the_theme_not_from_literals():
    parsed = _stage(LEDGER_LINE).parsed
    by_kind = {s.kind: span_style(s, parsed, PALETTE) for s in parsed.spans}
    assert by_kind["amount"] == PALETTE.error  # negative
    assert by_kind["account"] == ACCENT
    assert by_kind["category"] == ACCENT
    assert by_kind["title"] == "bold"

    income = _stage("sueldo +2450 $BCP PEN @KORAKUEN").parsed
    amount = next(s for s in income.spans if s.kind == "amount")
    assert span_style(amount, income, PALETTE) == PALETTE.success


def test_an_unresolved_token_takes_the_error_colour():
    parsed = _stage("apparka -3.50 $nope @KORAKUEN").parsed
    bad = next(s for s in parsed.spans if not s.resolved)
    assert span_style(bad, parsed, PALETTE) == PALETTE.error


def test_highlighter_paints_the_bar_from_the_parse():
    from rich.text import Text

    from expense.tui.screens.log_bar import LineHighlighter

    hl = LineHighlighter()
    assert hl(Text(LEDGER_LINE)).spans == []  # nothing parsed yet — no colour
    hl.parsed = _stage(LEDGER_LINE).parsed
    assert hl(Text(LEDGER_LINE)).spans  # every token carries a style


# ---- pilot ------------------------------------------------------------------
async def _open(app, pilot):
    screen = LogBarScreen()
    await app.push_screen(screen)
    await wait_for(pilot, lambda: screen._refs is not None, message="refs never loaded")
    return screen


async def _save_settled(pilot, screen, client) -> None:
    """Until the save `ctrl+s` asked for has been sent and has finished.

    `not screen._saving` alone is already true *before* the save starts: the
    key, or the discard question's answer, reaches the screen a moment after
    the press returns. The POST is the proof the save began — `_saving` is
    set before its worker starts — so both together mean it ran and ended.
    """
    await wait_for(
        pilot,
        lambda: bool(client.posts) and not screen._saving,
        message="the save never ran to its end",
    )


def _bar(screen) -> Input:
    return screen.query_one("#bar", Input)


def _label(screen) -> str:
    return str(screen.query_one("#field", Label).content)


def _legend(screen) -> str:
    return str(screen.query_one("#legend", Static).content)


def _type(screen, text, *, caret=None):
    """Drive the bar directly — a focused Input swallows key presses."""
    bar = _bar(screen)
    bar.value = text
    bar.cursor_position = len(text) if caret is None else caret
    screen.on_input_changed(Input.Changed(bar, text))


def test_state1_opens_on_an_empty_bar_with_the_invitation(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        assert _bar(screen).has_focus
        assert _label(screen) == "LOG"
        # the grammar moved to the legend row; the hint row is for what the
        # parser reads in the line, and an empty bar says nothing
        assert screen._hint() == ""
        assert "↵ stages the line" in _legend(screen)
        assert "Nothing staged" in _text(screen._staged_renderable())

    run_app(scenario)


def test_state2_an_ambiguous_account_opens_the_picker(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "tottus porongoche -38.60 $sig")
        assert [name for _, name in screen._picker.candidates] == [
            "BCP Signature PEN",
            "BCP Signature USD",
        ]
        assert '"$sig" matches 2 accounts' in screen._hint()
        assert screen._suggest_idx == 0
        screen.action_move(1)
        assert screen._suggest_idx == 1

    run_app(scenario)


def test_the_account_picker_shows_the_engines_order(fake_client, monkeypatch):
    """A bare `$` lists the accounts exactly as `GET /accounts` returned them —
    not alphabetical, not by `sort_order`, the person after every bank."""
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_ACCOUNTS)
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "almuerzo -20 $")
        assert [name for _, name in screen._picker.candidates] == ENGINE_ORDER_NAMES
        assert in_order(_text(screen._suggest_renderable()), ENGINE_ORDER_NAMES)

    run_app(scenario)


def test_state3_enter_completes_the_token_inside_the_line(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "tottus porongoche -38.60 $sig")
        screen.action_move(1)  # the USD one
        screen.on_input_submitted()
        assert _bar(screen).value == "tottus porongoche -38.60 $BCP Signature USD"
        assert screen._picker is None  # it resolves now, so the picker closes
        assert screen._staged == []  # completing is not staging
        assert "completed the token in place" in screen._hint()

    run_app(scenario)


def test_state4_enter_stages_the_line_and_clears_the_bar(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        assert _bar(screen).value == ""
        assert [e.line for e in screen._staged] == [LEDGER_LINE]
        out = _text(screen._staged_renderable())
        assert "1 staged" in out and "-38.60 PEN" in out

    run_app(scenario)


def test_state5_a_line_with_no_account_is_refused_in_place(fake_client, monkeypatch):
    """The line stays in the bar with the reason under
    it, and the staged list is untouched. The next keystroke clears the reason."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        _type(screen, NO_ACCOUNT_LINE)
        screen.on_input_submitted()
        assert len(screen._staged) == 1  # not staged
        assert _bar(screen).value == NO_ACCOUNT_LINE  # still in the bar
        assert screen._refused is not None
        out = _text(screen._suggest_renderable(), width=160)
        assert "not staged" in out
        assert "the line names no account" in out
        assert "not staged" in screen._hint()

        _type(screen, NO_ACCOUNT_LINE + " $BCP PEN")  # any edit is a new attempt
        assert screen._refused is None
        screen.on_input_submitted()
        assert len(screen._staged) == 2

    run_app(scenario)


def test_a_line_with_no_category_stages_and_reads_as_pendiente(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, NO_CATEGORY_LINE)
        screen.on_input_submitted()
        assert _bar(screen).value == ""
        assert screen._staged[0].parsed.category_id is None
        out = _text(screen._staged_renderable(), width=160)
        assert "1 staged" in out and "1 pendiente" in out

    run_app(scenario)


def test_state6_arrows_pick_a_staged_row_and_enter_lifts_the_typed_line(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        for line in (LEDGER_LINE, NO_CATEGORY_LINE):
            _type(screen, line)
            screen.on_input_submitted()

        screen.action_move(1)  # bar is empty, so the arrows drive the list
        assert screen._picked == 0
        screen.action_move(1)
        assert screen._picked == 1

        screen.on_input_submitted()  # lift it
        assert _bar(screen).value == NO_CATEGORY_LINE  # the raw line, verbatim
        assert screen._editing == 1
        assert _label(screen) == "EDIT 2"
        assert "the line that made it" in screen._hint()

    run_app(scenario)


def test_a_lifted_row_is_replaced_in_place_not_appended(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        for line in (LEDGER_LINE, NO_CATEGORY_LINE):
            _type(screen, line)
            screen.on_input_submitted()
        screen.action_move(1)
        screen.action_move(1)
        screen.on_input_submitted()  # lift row 2

        fixed = NO_CATEGORY_LINE + " @TRANSPORTE"
        _type(screen, fixed)
        screen.on_input_submitted()

        assert len(screen._staged) == 2
        assert screen._staged[1].line == fixed
        assert screen._staged[1].parsed.category_id == "cat2"  # classified now
        assert screen._editing is None
        assert _label(screen) == "LOG"

    run_app(scenario)


def test_ctrl_x_drops_the_picked_row(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        for line in (LEDGER_LINE, NO_CATEGORY_LINE):
            _type(screen, line)
            screen.on_input_submitted()
        screen.action_move(1)
        screen.action_drop_row()
        assert [e.line for e in screen._staged] == [NO_CATEGORY_LINE]

    run_app(scenario)


def test_ctrl_x_beats_the_inputs_own_cut_binding(fake_client, monkeypatch):
    """Textual's Input binds ctrl+x to `cut`; ours must win, or the key would
    edit the line instead of dropping the row."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        screen.action_move(1)
        await pilot.press("ctrl+x")
        await wait_for(pilot, lambda: not screen._staged, message="ctrl+x never dropped it")

    run_app(scenario)


def test_state9_escape_with_rows_staged_asks_before_leaving(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()

        screen.action_back()
        await wait_for(pilot, lambda: isinstance(app.screen, DiscardStagedModal))
        await pilot.press("enter")  # keep editing
        await wait_for(pilot, lambda: app.screen is screen)
        assert screen._staged  # nothing was thrown away

        screen.action_back()
        await wait_for(pilot, lambda: isinstance(app.screen, DiscardStagedModal))
        await pilot.press("d")  # discard
        await wait_for(pilot, lambda: app.screen is not screen)

    run_app(scenario)


def test_escape_unpicks_before_it_offers_to_leave(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        screen.action_move(1)
        assert screen._picked == 0

        screen.action_back()
        assert screen._picked is None
        assert app.screen is screen  # no modal yet

    run_app(scenario)


def test_escape_on_an_empty_screen_just_leaves(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        screen.action_back()
        await wait_for(pilot, lambda: app.screen is not screen)

    run_app(scenario)


def test_ctrl_s_writes_every_row_in_one_batch(fake_client, monkeypatch):
    """The shape of the save: one atomic call, and nothing after it.

    A sparse row rides the same batch, its absent
    fields omitted (never null) so the engine applies its own defaults.
    """
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        for line in (LEDGER_LINE, NO_CATEGORY_LINE, NO_TITLE_LINE):
            _type(screen, line)
            screen.on_input_submitted()
        assert len(screen._staged) == 3

        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: len(fake_client.posts) == 1)

        batch_path, batch_body = fake_client.posts[0]
        assert batch_path == "/transactions/batch"
        rows = batch_body["transactions"]
        assert len(rows) == 3  # ONE call for every row, not one call each
        assert "category_id" not in rows[1] and rows[1]["title"] == "apparka mall"
        assert "title" not in rows[2] and "category_id" not in rows[2]

        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))
        assert app.screen is screen  # it stays: the ticks are the receipt
        assert "3 logged · 2 pendiente" in _text(screen._staged_renderable())

    run_app(scenario)


def test_the_plus_key_opens_the_log_bar(fake_client, monkeypatch):
    """The switch: `+` opens the bar, never the edit form. Asserted on the source so a
    future edit cannot quietly point `+` back at the form.
    """
    import inspect

    from expense.tui.screens._base import LogTransactionMixin
    from expense.tui.screens.edit_form import EditFormScreen

    source = inspect.getsource(LogTransactionMixin.action_log_transaction)
    assert LogBarScreen.__name__ in source
    assert EditFormScreen.__name__ not in source


# ---- the save --------------------------------------------------------------
def _script(client, responses):
    """Give the fake client a per-call answer for POST.

    `FakeClient.errors["POST"]` fails *every* POST, which cannot express the
    interesting case — the batch is refused naming one row, and the rest then
    goes again and lands (batch_write). Each entry
    is either an exception to raise or a dict to return, consumed in order; the
    list running dry falls back to the ordinary empty-dict success.
    """
    queue = list(responses)

    def post(path, json_body=None):
        client.calls.append(("POST", path, json_body))
        if queue:
            answer = queue.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return {}

    client.post = post


def _refused(index: int, field: str, message: str, reason: str) -> EngineError:
    """The batch 422: each refused item field keyed `transactions.<index>.<field>`,
    its reason under the same key (contract: POST /v1/transactions/batch)."""
    key = f"transactions.{index}.{field}"
    return EngineError(
        "VALIDATION_ERROR", "Invalid input.", {key: message}, 422, {}, reasons={key: reason}
    )


def _stage_lines(screen, *lines):
    for line in lines:
        _type(screen, line)
        screen.on_input_submitted()


def test_state7_every_row_ticks_and_the_screen_stays(fake_client, monkeypatch):
    """The save is not an exit: the ticked list is the receipt."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))
        assert app.screen is screen
        out = _text(screen._staged_renderable())
        assert out.count("✓") == 2
        assert "2 logged" in out
        assert "ctrl+s again does nothing" in out

    run_app(scenario)


def test_ctrl_s_again_writes_nothing_once_every_row_is_saved(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))
        before = len(fake_client.calls)
        await pilot.press("ctrl+s")
        await pilot.pause()  # let the second chord settle, then assert a non-event
        assert len(fake_client.calls) == before

    run_app(scenario)


def test_saved_rows_clear_when_the_next_line_is_staged(fake_client, monkeypatch):
    """Decision 1: the list only ever shows rows you are about to write.

    What the finished batch leaves behind is one sentence, not a table.
    """
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))
        # between the save and the next line: the receipt, no table
        assert "1 logged a moment ago" in _text(staged_table([], REFS, last_save=screen._last_save))

        _stage_lines(screen, USD_LINE)
        assert len(screen._staged) == 1  # the ticked row went, this one stays
        assert not screen._staged[0].saved

    run_app(scenario)


def test_state8_a_partial_failure_ticks_what_landed(fake_client, monkeypatch):
    """The engine refuses the whole batch naming one row; the other goes again
    and lands — and the screen says which is which, because "nothing was
    written" would be a lie."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE)
        _script(
            fake_client,
            [_refused(1, "amount_cents", "Must not be zero.", "ZERO_AMOUNT"), {}],
        )
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        ledger, draft = screen._staged
        assert ledger.saved and ledger.error is None
        assert not draft.saved and "Must not be zero." in (draft.error or "")
        out = _text(screen._staged_renderable())
        assert "✓" in out and "1 logged" in out
        assert (
            "  amount_cents: Must not be zero. row 2\n" in out
        )  # the engine's words, then the row
        assert "ctrl+s retries just the rows without a ✓." in out

    run_app(scenario)


def test_a_sealed_row_keeps_its_period_and_the_rest_of_the_batch_saves(fake_client, monkeypatch):
    """The wall, at the LOG bar's door (sealed-periods plan S4).

    The bar has no pre-filter — you can type any date, including one inside a
    month you closed — so the engine's refusal is the only thing standing
    between a backdated line and silence. The period's NAME lives in the 422's
    field text and nowhere else, so what this pins is that it survives the
    batch writer's per-row reading, `format_error`, and the per-row error block,
    while the row that was fine still ticks.
    """
    _patch(monkeypatch)
    sealed_text = (
        "Period 2026-08-01 to 2026-08-25 is sealed by completed reconciliation "
        "'August 2026'. Revert it to draft to change anything inside it."
    )

    def sealed(index: int) -> EngineError:
        key = f"transactions.{index}.date"
        return EngineError(
            "VALIDATION_ERROR",
            "Transaction falls inside a sealed reconciliation period.",
            {key: sealed_text},
            422,
            {},
            reasons={key: "SEALED_PERIOD"},
        )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE)
        # the chunk is refused on its second item, sealed; row 1 goes again and lands
        _script(fake_client, [sealed(1), {}])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        ledger, backdated = screen._staged
        assert ledger.saved and ledger.error is None  # one refused row cancels nothing
        assert not backdated.saved
        # flattened: the engine's sentence is long enough to wrap in the block,
        # and where it wraps is a width detail, not the assertion
        out = " ".join(_text(screen._staged_renderable()).split())
        assert "1 logged" in out
        assert f"date: {sealed_text} row 2" in out  # the way out survives, then the row

    run_app(scenario)


def test_settings_missing_is_said_once_not_per_row(fake_client, monkeypatch):
    """Before first-time setup the engine refuses the batch for a reason that is
    about the account, not about any row: one POST, one toast carrying the error
    and its hint, and no row wearing a copy of it."""
    _patch(monkeypatch)
    refusal = EngineError(
        "SETTINGS_MISSING",
        "User settings have not been provisioned.",
        {"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
        422,
        {},
        reasons={"user_settings": "NOT_PROVISIONED"},
    )
    toasts: list[tuple[str, str]] = []

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        monkeypatch.setattr(
            screen, "notify", lambda message, title="", **kw: toasts.append((title, str(message)))
        )
        _stage_lines(screen, LEDGER_LINE, USD_LINE, NO_CATEGORY_LINE)
        _script(fake_client, [refusal])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        assert len(fake_client.posts) == 1  # nothing sent again
        assert all(not e.saved and e.error is None for e in screen._staged)
        assert app.screen is screen
        assert toasts == [
            (
                "Failed",
                "SETTINGS_MISSING — User settings have not been provisioned.\n"
                "  user_settings: Must be provisioned via POST /v1/auth/bootstrap.\n"
                "\n"
                "Hint: First-time setup is not done yet. "
                "Open System ▸ Auth & profile and press b.",
            ),
            ("Failed", "Some rows were not written."),
        ]
        out = _text(screen._staged_renderable())
        assert "SETTINGS_MISSING" not in out and "Hint" not in out

    run_app(scenario)


def test_line_codes_exhausted_stops_the_save_and_is_said_once(fake_client, monkeypatch):
    """The LOG bar shares the batch writer, so it shares its stop: every line code
    given, the save ends at the one POST, the refusal is one toast in the engine's
    words, and no row wears a copy of it (contract: "Transactions (Ledger)", "Bank lines")."""
    _patch(monkeypatch)
    key = "transactions.0.id"
    refusal = EngineError(
        "LIMIT_REACHED",
        "No bank line codes are left.",
        {key: "No line code is left for a new line."},
        422,
        {},
        reasons={key: "LINE_CODES_EXHAUSTED"},
    )
    toasts: list[tuple[str, str]] = []

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        monkeypatch.setattr(
            screen, "notify", lambda message, title="", **kw: toasts.append((title, str(message)))
        )
        _stage_lines(screen, LEDGER_LINE, USD_LINE)
        _script(fake_client, [refusal])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        assert len(fake_client.posts) == 1  # nothing sent again
        assert all(not e.saved and e.error is None for e in screen._staged)
        assert toasts == [
            (
                "Failed",
                "LIMIT_REACHED — No bank line codes are left.\n"
                "  transactions.0.id: No line code is left for a new line.",
            ),
            ("Failed", "Some rows were not written."),
        ]

    run_app(scenario)


def test_a_run_stop_keeps_a_rows_own_earlier_refusal(fake_client, monkeypatch):
    """Row 2 is refused for its own date; row 1, sent again alone, meets the
    line codes running out. The stop is one toast and on no row; row 2 keeps the
    engine's words for its own refusal, never swallowed."""
    _patch(monkeypatch)
    date_key = "transactions.1.date"
    own = EngineError(
        "VALIDATION_ERROR",
        "Transaction falls inside a sealed reconciliation period.",
        {date_key: "Period 2026-08-01 to 2026-08-25 is sealed."},
        422,
        {},
        reasons={date_key: "SEALED_PERIOD"},
    )
    id_key = "transactions.0.id"
    stop = EngineError(
        "LIMIT_REACHED",
        "No bank line codes are left.",
        {id_key: "No line code is left for a new line."},
        422,
        {},
        reasons={id_key: "LINE_CODES_EXHAUSTED"},
    )
    toasts: list[str] = []

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        monkeypatch.setattr(
            screen, "notify", lambda message, title="", **kw: toasts.append(str(message))
        )
        _stage_lines(screen, LEDGER_LINE, USD_LINE)
        _script(fake_client, [own, stop])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        first, second = screen._staged
        assert len(fake_client.posts) == 2
        assert not first.saved and first.error is None  # never settled: no marker
        assert not second.saved and second.error is not None
        assert "Period 2026-08-01 to 2026-08-25 is sealed." in second.error
        assert "LIMIT_REACHED" not in second.error
        assert sum("LIMIT_REACHED" in t for t in toasts) == 1

    run_app(scenario)


def test_an_unknown_hashtag_names_its_own_row(fake_client, monkeypatch):
    """A hashtag archived or deleted between staging and saving: the engine keys
    it on its item, `transactions.<index>.hashtag_ids`, with the other item
    failures. The row it belongs to carries the refusal; the other one ticks."""
    _patch(monkeypatch)
    unknown = "Some hashtag IDs are invalid."

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, USD_LINE, LEDGER_LINE)  # the second row carries #CAJA CHICA
        _script(
            fake_client,
            [_refused(1, "hashtag_ids", unknown, "INVALID_REFERENCE"), {}],
        )
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        plain, tagged = screen._staged
        assert plain.saved and plain.error is None
        assert not tagged.saved and unknown in (tagged.error or "")
        out = " ".join(_text(screen._staged_renderable()).split())
        assert "1 logged" in out
        assert f"hashtag_ids: {unknown} row 2" in out

    run_app(scenario)


def test_a_retry_re_sends_only_the_rows_without_a_tick(fake_client, monkeypatch):
    """Decision 2, the half that matters: nothing is ever written twice."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE)
        _script(
            fake_client,
            [_refused(1, "amount_cents", "Must not be zero.", "ZERO_AMOUNT"), {}],
        )
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)
        fake_client.calls.clear()

        await pilot.press("ctrl+s")  # the engine is healthy again
        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))
        # the first row is already in — the retry carries the other alone
        assert [p for _, p, _ in fake_client.calls] == ["/transactions/batch"]
        assert len(fake_client.calls[0][2]["transactions"]) == 1

    run_app(scenario)


def _conflict(key: str, reason: str, message: str = "stand-in") -> EngineError:
    """The batch 409, keyed by the thing refused: `transactions.<i>.id` for a
    taken id, `category_id` for the system-category refusals (contract: "Error reasons")."""
    return EngineError(
        "CONFLICT", message, {key: "stand-in field words"}, 409, {}, reasons={key: reason}
    )


def test_a_replayed_row_comes_back_409_and_counts_as_written(fake_client, monkeypatch):
    """The response was lost, not the write. `ID_EXISTS` on the row's own
    client-minted id means it is already there — a tick, never a second copy."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        first_id = screen._staged[0].row_id
        _script(fake_client, [_conflict("transactions.0.id", "ID_EXISTS")])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        assert screen._staged[0].saved  # ✓, not an error
        assert screen._staged[0].error is None
        assert screen._staged[0].row_id == first_id  # the id never changed

    run_app(scenario)


def test_one_save_ticks_a_replayed_row_names_a_refused_one_and_lands_the_rest(
    fake_client, monkeypatch
):
    """The engine answers what the request shows first (a zero amount on row 3),
    then, sent again without it, the taken id of row 1; row 2 goes a third time
    and lands. Rows 1 and 2 tick, row 3 carries its refusal: one request per send,
    never one per row (contract: POST /v1/transactions/batch)."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE, NO_CATEGORY_LINE)
        ids = [e.row_id for e in screen._staged]
        _script(
            fake_client,
            [
                _refused(2, "amount_cents", "Must not be zero.", "ZERO_AMOUNT"),
                _conflict("transactions.0.id", "ID_EXISTS"),
                {},
            ],
        )
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        sent = [[item["id"] for item in body["transactions"]] for _, _, body in fake_client.calls]
        assert sent == [ids, ids[:2], ids[1:2]]
        replayed, landed, refused = screen._staged
        assert replayed.saved and replayed.error is None
        assert landed.saved and landed.error is None
        assert not refused.saved
        assert refused.error == "amount_cents: Must not be zero."
        out = _text(screen._staged_renderable())
        assert "✓ 1" in out and "✓ 2" in out and "✓ 3" not in out
        assert "  amount_cents: Must not be zero. row 3\n" in out

    run_app(scenario)


@pytest.mark.parametrize(
    ("reason", "line"),
    [
        ("CONCURRENT_CHANGE", "It changed at the same moment: save again."),
        (
            "RESERVED_NAME_HELD",
            "One of your categories has a built-in category's name: "
            "rename it on Manage ▸ Categories, then save again.",
        ),
    ],
)
def test_any_other_409_is_a_refusal_with_no_tick(fake_client, monkeypatch, reason, line):
    """Only a replay of the row's own id is a tick. A row refused for another
    reason keeps no ✓ and shows the engine's words, then the line saying what to
    do: `ctrl+s` is how this screen saves again (screens 5A and 6B)."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        refusal = _conflict("category_id", reason)
        _script(fake_client, [refusal])  # names no row: the whole batch, sent once
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        entry = screen._staged[0]
        assert not entry.saved  # no ✓
        assert entry.error == (
            f"CONFLICT — stand-in\n  category_id: stand-in field words\n\n{line}"
        )
        assert app.screen is screen

    run_app(scenario)


def test_a_connection_error_writes_nothing_and_every_row_survives(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE)
        fake_client.errors["POST"] = EngineConnectionError(
            url="http://127.0.0.1:8000", original=ConnectionRefusedError("refused")
        )
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        assert len(screen._staged) == 2
        assert not any(e.saved for e in screen._staged)
        assert all("127.0.0.1:8000" in (e.error or "") for e in screen._staged)
        assert app.screen is screen  # every row is still here; ctrl+s tries again

    run_app(scenario)


def test_ctrl_s_leaves_a_half_typed_line_in_the_bar_alone(fake_client, monkeypatch):
    """Decision 3: `↵` is the only thing that stages, so a save can never write
    something you were still in the middle of."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        _type(screen, "pollo -25 $BCP PEN @KORAKUEN")  # typed, never submitted
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))

        assert len(screen._staged) == 1  # the bar's line was not staged
        batch = fake_client.posts[0][1]["transactions"]
        assert len(batch) == 1 and batch[0]["title"] == "tottus porongoche"
        assert _bar(screen).value == "pollo -25 $BCP PEN @KORAKUEN"  # still yours

    run_app(scenario)


def test_a_saved_row_cannot_be_lifted_back_into_the_bar(fake_client, monkeypatch):
    """Editing a written row here would promise something this screen cannot do:
    it only ever creates. Corrections are the edit form's job."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))

        screen._picked = 0
        screen.on_input_submitted()  # ↵ on a picked row would normally lift it
        assert screen._editing is None
        assert _bar(screen).value == ""

    run_app(scenario)


def test_escape_with_only_saved_rows_leaves_without_asking(fake_client, monkeypatch):
    """ "5 rows are staged and not written" must never count ticks."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))

        screen.action_back()
        await wait_for(pilot, lambda: app.screen is not screen)

    run_app(scenario)


def test_state9_the_discard_card_saves_first_and_then_leaves(fake_client, monkeypatch):
    """The discard card's third answer: save first, then leave."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE)
        screen.action_back()
        await wait_for(pilot, lambda: isinstance(app.screen, DiscardStagedModal))
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is not screen)
        assert fake_client.posts  # it saved on the way out

    run_app(scenario)


def test_a_failed_save_first_keeps_the_screen_so_the_error_is_readable(fake_client, monkeypatch):
    """You asked to leave, but an error you cannot read is the same as none."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        fake_client.errors["POST"] = EngineConnectionError(
            url="http://127.0.0.1:8000", original=ConnectionRefusedError("refused")
        )
        screen.action_back()
        await wait_for(pilot, lambda: isinstance(app.screen, DiscardStagedModal))
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        assert app.screen is screen  # still here
        assert "127.0.0.1:8000" in _text(screen._staged_renderable())

    run_app(scenario)


# ---- pure: the save's render layer ------------------------------------------
def test_a_saved_row_renders_a_tick_instead_of_its_routing_marker():
    entry = _stage(LEDGER_LINE)
    entry.saved = True
    out = _text(staged_table([entry], REFS, today=TODAY.isoformat()))
    assert "✓" in out and "•" not in out


def test_the_summary_totals_only_the_rows_still_pending():
    """A written row stops being something you are about to do — otherwise the
    figure under a half-saved list describes a batch that no longer exists."""
    done, pending = _stage(LEDGER_LINE), _stage(USD_LINE)
    done.saved = True
    out = _text(staged_summary([done, pending], REFS, palette=PALETTE))
    assert "1 logged" in out
    assert "-96.00" in out and "USD" in out  # the pending row's own currency
    assert "-38.60" not in out  # the saved one has left the total


def test_the_error_block_names_the_row_and_says_what_to_press():
    entry = _stage(LEDGER_LINE)
    entry.error = "SERVER_ERROR — engine exploded"
    out = _text(save_errors([_stage(USD_LINE), entry]))
    assert "  SERVER_ERROR — engine exploded row 2\n" in out
    assert "ctrl+s retries just the rows without a ✓." in out


_SEALED = "The date falls inside a completed reconciliation's period."


def _two_kinds() -> EngineError:
    """One batch 422 naming rows 1 and 3 for a zero amount and row 2 for a
    sealed date (contract: POST /v1/transactions/batch)."""
    entries = {
        "transactions.1.amount_cents": ("Must not be zero.", "ZERO_AMOUNT"),
        "transactions.2.date": (_SEALED, "SEALED_PERIOD"),
        "transactions.3.amount_cents": ("Must not be zero.", "ZERO_AMOUNT"),
    }
    return EngineError(
        "VALIDATION_ERROR",
        "Batch validation failed.",
        {key: words for key, (words, _) in entries.items()},
        422,
        {},
        reasons={key: reason for key, (_, reason) in entries.items()},
    )


def test_refused_rows_read_one_line_per_kind_screen_2a(fake_client, monkeypatch):
    """Screen 2 A: the engine's words, then the rows they hit — `row 3` for one,
    `rows 2, 4` for several — and the line saying what to press, dim, last."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE, NO_CATEGORY_LINE, LEDGER_LINE)
        _script(fake_client, [_two_kinds(), {}])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        out = _text(save_errors(screen._staged))
        assert out == (
            "  amount_cents: Must not be zero. rows 2, 4\n"
            f"  date: {_SEALED} row 3\n"
            "  ctrl+s retries just the rows without a ✓.\n"
        )

    run_app(scenario)


def test_one_kind_across_two_sends_is_one_line(fake_client, monkeypatch):
    """Row 2 is refused on the first send, row 4 on the send after it, whose
    message counts its items: the rows' words are alike, so they share a line."""
    _patch(monkeypatch)
    key = "transactions.2.amount_cents"
    counted = EngineError(
        "VALIDATION_ERROR",
        "1 of these items is not valid.",
        {key: "Must not be zero."},
        422,
        {},
        reasons={key: "ZERO_AMOUNT"},
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE, NO_CATEGORY_LINE, LEDGER_LINE)
        first = _refused(1, "amount_cents", "Must not be zero.", "ZERO_AMOUNT")
        _script(fake_client, [first, counted, {}])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        assert [e.saved for e in screen._staged] == [True, False, True, False]
        out = _text(save_errors(screen._staged))
        assert out == (
            "  amount_cents: Must not be zero. rows 2, 4\n"
            "  ctrl+s retries just the rows without a ✓.\n"
        )

    run_app(scenario)


def test_a_refusal_naming_no_row_keeps_a_line_of_its_own(fake_client, monkeypatch):
    """Row 2 is refused for its amount; row 1, sent again alone, meets a refusal
    naming no row. That one reads whole, the row after its first line, and the
    app's line under it; it never joins row 2's line."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE)
        zero = _refused(1, "amount_cents", "Must not be zero.", "ZERO_AMOUNT")
        _script(fake_client, [zero, _conflict("category_id", "CONCURRENT_CHANGE")])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        out = _text(save_errors(screen._staged))
        assert out == (
            "  CONFLICT — stand-in row 1\n"
            "    category_id: stand-in field words\n"
            "  It changed at the same moment: save again.\n"
            "  amount_cents: Must not be zero. row 2\n"
            "  ctrl+s retries just the rows without a ✓.\n"
        )

    run_app(scenario)


def test_a_kind_line_colours_the_words_and_not_the_rows():
    first, second = _stage(LEDGER_LINE), _stage(USD_LINE)
    for entry in (first, second):
        entry.error, entry.error_kind = "Must not be zero.", "zero"
    line, hint = save_errors([first, second], palette=PALETTE).renderables
    assert line.plain == "  Must not be zero. rows 1, 2"
    assert [(line.plain[s.start : s.end], s.style) for s in line.spans] == [
        ("Must not be zero.", PALETTE.error)
    ]
    assert hint.style == "dim"


def test_the_error_block_is_empty_when_nothing_failed():
    assert _text(save_errors([_stage(LEDGER_LINE)])).strip() == ""


def test_the_receipt_counts_what_landed_not_what_was_hoped_for():
    ledger, sparse, failed = _stage(LEDGER_LINE), _stage(NO_CATEGORY_LINE), _stage(USD_LINE)
    ledger.saved = sparse.saved = True
    assert save_receipt([ledger, sparse, failed]) == "2 logged · 1 pendiente"
    assert save_receipt([failed]) == ""


# ---- the account peek -------------------------------------------------------
# Elastic, and the panel stays on the last account the bar named.
def test_peek_rows_carry_the_five_columns_and_never_the_account():
    rows = peek_rows(PEEK_ITEMS, REFS, palette=PALETTE, today=TODAY.isoformat())
    (date, title, amount, category, tags) = rows[0]
    assert "20 Aug" in str(date)
    assert str(title) == "WONG CAYMA"
    assert "152.40" in str(amount)
    assert str(category) == "KORAKUEN"
    assert str(tags) == "#CAJA CHICA"
    # every row in the panel names the same account — the column would be noise
    assert all("Signature" not in str(cell) for cell in (date, title, amount, category, tags))


def test_peek_row_of_an_unnamed_category_still_renders():
    row = {
        "date": "2026-08-20T10:00:00-05:00",
        "amount_cents": -100,
        "line_code": "#000003",
        "statement_line": None,
    }
    rows = peek_rows([row], REFS)
    assert rows and str(rows[0][1]) == "—"


def test_peek_status_says_how_much_of_the_account_you_are_seeing():
    assert peek_status(6, 214) == "6 of 214 in this account · newest first"
    assert peek_status(3, 3) == "3 in this account · newest first"
    assert peek_status(0, 0) == "nothing in this account yet"
    # squeezed out by a long staged list: say so, do not read as an empty account
    assert peek_status(0, 214) == "214 in this account · no room to show them"


async def _peeked(pilot, screen):
    """Until the panel's fetch has landed (it is debounced, then threaded)."""
    await wait_for(pilot, lambda: bool(screen._peek_cache), message="the peek never loaded")


def _peek(screen) -> AccountPeek:
    return screen.query_one("#peek", AccountPeek)


def test_the_peek_opens_on_the_account_the_line_names(fake_client, monkeypatch):
    fetch = _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        assert not _peek(screen).display  # nothing named yet, no panel
        _type(screen, LEDGER_LINE)
        await _peeked(pilot, screen)
        assert fetch.accounts == ["acc1"]
        panel = _peek(screen)
        assert panel.display
        # content lines, not border decorations (docs/tui.md §2)
        assert panel.panel_title == "BCP Signature PEN"
        assert "of 214 in this account" in panel.panel_status
        assert "WONG CAYMA" in _text(panel.content)

    run_app(scenario, size=(110, 30))


def test_the_peek_draws_as_many_rows_as_it_was_given(fake_client, monkeypatch):
    """The panel is `1fr`, so it renders exactly what fits — no more."""
    _patch(monkeypatch, _PeekFetch(cursor_page(PEEK_ITEMS * 20, next_cursor="c40")))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        await _peeked(pilot, screen)
        await wait_for(pilot, lambda: _peek(screen).capacity > 0, message="no room")
        panel = _peek(screen)
        drawn = _text(panel.content).count("WONG CAYMA")
        assert 0 < drawn <= panel.capacity < len(PEEK_ITEMS) * 20

    run_app(scenario, size=(110, 24))


def test_the_peek_follows_the_picker_while_the_account_is_ambiguous(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "tottus porongoche -38.60 $sig")
        assert screen._peek_account == "acc1"  # the highlighted candidate
        screen.action_move(1)
        assert screen._peek_account == "acc2"  # …and it swaps as you arrow

    run_app(scenario, size=(110, 30))


def test_the_peek_stays_on_the_last_account_the_bar_named(fake_client, monkeypatch):
    """`↵` clears the bar, and the panel does not blink off with it."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        await _peeked(pilot, screen)
        screen.on_input_submitted()  # stages it; the bar is empty again
        assert _bar(screen).value == ""
        assert screen._peek_account == "acc1"
        assert _peek(screen).display

    run_app(scenario, size=(110, 30))


def test_the_staged_rows_never_choose_the_peeks_account(fake_client, monkeypatch):
    """The account is the bar's. A staged row for another one does not vote."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)  # $BCP Signature PEN → acc1
        screen.on_input_submitted()
        _type(screen, "tran.cel.bm. -6.60 $BCP PEN @TRANSPORTE")
        assert screen._peek_account == "acc3"  # the line's, not the staged row's
        assert _peek(screen).panel_title == "BCP PEN"

    run_app(scenario, size=(110, 30))


def test_an_account_token_that_resolves_to_nothing_closes_the_peek(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        await _peeked(pilot, screen)
        _type(screen, "apparka mall -3.50 $xyz")
        assert screen._peek_account is None
        assert not _peek(screen).display

    run_app(scenario, size=(110, 30))


def test_each_account_is_fetched_once_however_often_it_is_named(fake_client, monkeypatch):
    fetch = _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        await _peeked(pilot, screen)
        _type(screen, "")
        _type(screen, LEDGER_LINE)
        _type(screen, LEDGER_LINE + " ")
        await pilot.pause()
        assert fetch.accounts == ["acc1"]

    run_app(scenario, size=(110, 30))


def test_a_peek_that_cannot_load_says_so_and_does_not_retry(fake_client, monkeypatch):
    """A peek is a courtesy: it reports in its own panel and never interrupts."""
    fetch = _patch(
        monkeypatch, _PeekFetch(error=EngineError("BOOM", "engine is down", None, 500, {}))
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        await wait_for(pilot, lambda: bool(screen._peek_note), message="no note")
        assert "engine is down" in _text(_peek(screen).content)
        _type(screen, LEDGER_LINE + " ")
        await pilot.pause()
        assert fetch.accounts == ["acc1"]

    run_app(scenario, size=(110, 30))


def test_a_peek_that_lands_as_the_app_closes_touches_nothing(fake_client, monkeypatch):
    """The read was in flight when the app began to close: its answer has no
    screen to paint.

    A thread worker cannot be stopped, so the page still arrives — and drawing
    it while the bar's widgets are being taken down queries widgets that are
    already gone (`NoMatches '#field'`), which fails the app as it exits. The
    order is pinned: the app is told to exit, and only then does the read hand
    its answer back, while the bar is still linked to the app.
    """
    import threading

    release = threading.Event()
    submitted = threading.Event()
    returned = threading.Event()

    class _HeldPeek(_PeekFetch):
        def count(self, _cfg, **kw):
            self.counted.append(kw.get("account"))
            release.wait(timeout=5)
            return self.total

    fetch = _patch(monkeypatch, _HeldPeek())

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        real_call = app.call_from_thread

        def spy(callback, *args, **kwargs):
            submitted.set()
            try:
                return real_call(callback, *args, **kwargs)
            finally:
                returned.set()

        monkeypatch.setattr(app, "call_from_thread", spy)
        _type(screen, LEDGER_LINE)
        await wait_for(pilot, lambda: fetch.counted == ["acc1"], message="the peek never asked")
        app.exit()
        release.set()
        # Block the UI thread until the answer is on its way, so nothing of the
        # bar is taken down before the worker reaches for the app.
        assert submitted.wait(timeout=5), "the peek never handed back"
        await wait_for(pilot, returned.is_set, message="the hand-back never returned")
        assert screen._peek_cache == {}  # the answer was dropped, not drawn

    run_app(scenario, size=(110, 30))


def test_the_peek_total_is_the_engine_count_read_with_the_rows(fake_client, monkeypatch):
    fetch = _patch(monkeypatch, _PeekFetch(total=1716))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        await _peeked(pilot, screen)
        assert fetch.accounts == ["acc1"] and fetch.counted == ["acc1"]
        # the figure is the count, not the length of the page in hand
        assert "of 1716 in this account" in _peek(screen).panel_status

    run_app(scenario, size=(110, 30))


def test_a_count_that_cannot_be_read_fails_the_peek(fake_client, monkeypatch):
    """No rows beside a guessed number: the rows arrived,
    the count did not, so the panel says why and shows no rows."""
    _patch(
        monkeypatch,
        _PeekFetch(count_error=EngineError("BOOM", "count is down", None, 500, {})),
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        await wait_for(pilot, lambda: bool(screen._peek_note), message="no note")
        text = _text(_peek(screen).content)
        assert "count is down" in text and "NETFLIX" not in text

    run_app(scenario, size=(110, 30))


def test_a_save_refetches_the_account_it_just_wrote_to(fake_client, monkeypatch):
    fetch = _patch(monkeypatch)
    fake_client.get_responses["/transactions/batch"] = {}

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        await _peeked(pilot, screen)
        screen.on_input_submitted()
        screen.action_save()
        await wait_for(pilot, lambda: not screen._saving, message="save never finished")
        await wait_for(
            pilot, lambda: fetch.accounts == ["acc1", "acc1"], message="the peek went stale"
        )

    run_app(scenario, size=(110, 30))


# ---- the legend row ---------------------------------------------------------
# The whole grammar in one row, with the ↵ hint on the same line.
def test_the_legend_names_every_token_of_the_grammar():
    for token in ("$account", "@category", "#tag", "±amount", "//note", "when"):
        assert token in LEGEND_LINE
    assert "↵ stages the line" in LEGEND_LINE  # the ↵ hint rides the same row


def test_the_legend_never_changes_whatever_the_line_says(fake_client, monkeypatch):
    """It describes the grammar, not the moment — so nothing below it moves."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        before = _legend(screen)
        for line in ("", "tottus", LEDGER_LINE, "x -5 $sig", NO_ACCOUNT_LINE):
            _type(screen, line)
            assert _legend(screen) == before

    run_app(scenario, size=(110, 30))


def test_the_hint_row_carries_what_changes_not_the_grammar(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "tottus -38.60", caret=3)
        assert screen._hint() == ""  # nothing to echo: the caret is in the title
        _type(screen, "tottus -38.60")  # caret in the amount
        assert "-38.60" in screen._hint() and "sign" in screen._hint()
        _type(screen, "tottus -38.60 18/8/26")  # a fixed date: `hoy` moved with the calendar
        assert "Aug" in screen._hint()  # the resolved date, in words
        assert "$account" not in screen._hint()  # never the legend's job

    run_app(scenario, size=(110, 30))


def test_a_bare_sigil_opens_the_full_list(fake_client, monkeypatch):
    """Typing `#` alone means *show me what there is*."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "tottus -38.60 #")
        assert [n for _, n in screen._picker.candidates] == ["CAJA CHICA", "TAXI"]
        screen.on_input_submitted()  # ↵ completes it in place, as always
        assert _bar(screen).value == "tottus -38.60 #CAJA CHICA"

    run_app(scenario, size=(110, 30))


def test_a_bare_dollar_offers_every_account(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "tottus -38.60 $")
        assert len(screen._picker.candidates) == 3
        # and the peek follows it like any other account token
        assert screen._peek_account == "acc1"

    run_app(scenario, size=(110, 30))


# ---- dropped bank files ------------------------------------------------------
def _bank_file(tmp_path, name: str = "Sueldo Soles (1).xlsx"):
    path = tmp_path / name
    path.write_bytes(b"")
    return path


def _escaped(path) -> str:
    """What Terminal.app types for a drop."""
    return "".join("\\" + c if c in " ()" else c for c in str(path))


def _shown_bindings(screen) -> dict[str, str]:
    return {
        key: active.binding.description
        for key, active in screen.active_bindings.items()
        if active.binding.show
    }


def _spy_import(screen) -> list:
    handed: list = []
    screen.import_bank_files = handed.append
    return handed


def test_a_dropped_file_stands_quick_add_down(fake_client, monkeypatch, tmp_path):
    """No colouring, no picker, no refusal, no peek — and the bar says what it holds."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)  # a line naming an account opens the peek
        assert screen.query_one("#peek", AccountPeek).display
        _type(screen, _escaped(path))
        await pilot.pause()

        assert screen._files == [path]
        assert screen._parsed is None and screen._hl.parsed is None  # no colouring
        assert screen._picker is None and screen._refused is None
        assert not screen.query_one("#peek", AccountPeek).display
        assert screen._peek_account == "acc1"  # hidden, not forgotten
        assert not screen.query_one("#legend", Static).display
        assert screen._staged_renderable() is None  # the invitation stands down
        hint = screen.query_one("#hint", Static).content
        assert hint.plain == "bank file · Sueldo Soles (1).xlsx · ⏎ import it"
        assert any(span.style == ACCENT for span in hint.spans)  # colour from the theme
        assert _shown_bindings(screen) == {"escape": "Cancel", "enter": "Import"}

    run_app(scenario)


def test_several_dropped_files_list_one_name_per_line(fake_client, monkeypatch, tmp_path):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Digital Dólares.xlsx")
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, f"'{first}' '{second}'")  # VS Code's quoting
        assert screen._files == [first, second]
        assert screen._hint().split("\n") == [
            "bank files · 2 · ⏎ import them, one by one",
            "  Sueldo Soles (1).xlsx",
            "  Cuenta Digital Dólares.xlsx",
        ]

    run_app(scenario)


def test_editing_back_to_a_line_returns_to_quick_add_at_once(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, str(path))
        assert screen._files is not None
        _type(screen, str(path)[:-1])  # one character off: no such file
        assert screen._files is None
        assert screen.query_one("#legend", Static).display
        assert _shown_bindings(screen) == {"escape": "Cancel", "ctrl+s": "Save"}
        _type(screen, "")
        assert screen._files is None and screen._hint() == ""
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        assert [e.line for e in screen._staged] == [LEDGER_LINE]  # ↵ stages again

    run_app(scenario)


def test_enter_on_dropped_files_hands_them_over_and_stages_nothing(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    peek = _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        handed = _spy_import(screen)
        _type(screen, _escaped(path))
        await pilot.press("enter")
        await pilot.pause()

        assert handed == [[path]]
        assert screen._staged == []
        assert fake_client.calls == []  # no engine call at all
        assert peek.accounts == [] and peek.counted == []
        assert _bar(screen).value == _escaped(path)
        assert app.screen is screen

    run_app(scenario)


def test_a_pasted_path_goes_through_the_same_recognition(fake_client, monkeypatch, tmp_path):
    from textual import events

    path = _bank_file(tmp_path)
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        handed = _spy_import(screen)
        _bar(screen).post_message(events.Paste(_escaped(path) + " \n"))
        await wait_for(pilot, lambda: screen._files is not None, message="paste not seen")
        assert screen._files == [path]
        assert screen.query_one("#hint", Static).content.plain.startswith("bank file ·")
        await pilot.press("enter")
        await pilot.pause()
        assert handed == [[path]] and screen._staged == []

    run_app(scenario)


def test_a_typed_path_goes_through_the_same_recognition(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path, "movimientos.xlsx")
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        handed = _spy_import(screen)
        await pilot.press(*str(path))
        await wait_for(pilot, lambda: screen._files is not None, message="typing not seen")
        assert _bar(screen).value == str(path)
        assert screen._files == [path]
        await pilot.press("enter")
        await pilot.pause()
        assert handed == [[path]] and screen._staged == []

    run_app(scenario)


# ---- the pending hashtag never rides beside a real one ---------------------------
# (contract: "Transactions (Ledger)", "Hashtags on a transaction")

WITH_PENDING = {
    "items": [
        {"id": "h1", "name": "CAJA CHICA", "system_key": None},
        {"id": "h2", "name": "TAXI", "system_key": None},
        {"id": "hp", "name": "Pendiente", "system_key": "pending"},
    ]
}
PENDING_AND_REAL_LINE = "tottus -38.60 $BCP Signature PEN @KORAKUEN #Pendiente #TAXI"


def _save_line(fake_client, monkeypatch, line, *, script=None, tags=WITH_PENDING):
    """Stage `line` with the pending hashtag in the lists, save it; returns the
    staged row once the save has run."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: tags)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, line)
        if script is not None:
            _script(fake_client, script)
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)
        seen["entry"] = screen._staged[0]

    run_app(scenario)
    return seen["entry"]


def _sent_tags(fake_client) -> list:
    return [item.get("hashtag_ids") for item in fake_client.posts[0][1]["transactions"]]


def test_a_line_naming_the_pending_hashtag_and_a_real_one_sends_the_real_one(
    fake_client, monkeypatch
):
    _save_line(fake_client, monkeypatch, PENDING_AND_REAL_LINE)
    assert _sent_tags(fake_client) == [["h2"]]


def test_a_line_naming_only_the_pending_hashtag_sends_it_alone(fake_client, monkeypatch):
    _save_line(fake_client, monkeypatch, "tottus -38.60 $BCP Signature PEN #Pendiente")
    assert _sent_tags(fake_client) == [["hp"]]


def test_a_line_with_no_hashtag_sends_none(fake_client, monkeypatch):
    """No `hashtag_ids` at all: the engine files the row under the pending hashtag."""
    _save_line(fake_client, monkeypatch, "tottus -38.60 $BCP Signature PEN")
    assert _sent_tags(fake_client) == [None]


# ---- what the staged row's tags cell shows -----------------------------------------
# The staged list echoes what the save sends, so the pending hashtag named beside
# a real one is not listed, and a line with no `#tag` reads as the pending
# hashtag, where the engine files it, as its category cell reads @Pendiente
# (contract: "Transactions (Ledger)", "Hashtags on a transaction").

REFS_PENDING = replace(
    REFS,
    hashtags=[*REFS.hashtags, ("hp", "Pendiente")],
    hashtag_names={**REFS.hashtag_names, "hp": "Pendiente"},
    pending_hashtag=("hp", "Pendiente"),
)


def _tags_cell_of(line: str, refs: QuickAddRefs = REFS_PENDING) -> Text:
    parsed = parse(
        line,
        accounts=refs.accounts,
        categories=refs.categories,
        hashtags=refs.hashtags,
        today=TODAY,
    )
    entry = Staged(line=line, parsed=parsed, routing=route(parsed, TODAY))
    return staged_rows([entry], refs, palette=PALETTE, today=TODAY.isoformat())[0][-1]


def test_a_staged_line_naming_the_pending_hashtag_and_a_real_one_lists_the_real_one():
    cell = _tags_cell_of(PENDING_AND_REAL_LINE)
    assert (cell.plain, cell.style) == ("#TAXI", ACCENT)


def test_a_staged_line_naming_only_the_pending_hashtag_lists_it():
    cell = _tags_cell_of("tottus -38.60 $BCP Signature PEN #Pendiente")
    assert (cell.plain, cell.style) == ("#Pendiente", ACCENT)


def test_a_staged_line_with_no_hashtag_reads_as_the_pending_hashtag():
    """In the accent, like the category cell's @Pendiente beside it."""
    line = "tottus -38.60 $BCP Signature PEN"
    cell = _tags_cell_of(line)
    assert (cell.plain, cell.style) == ("#Pendiente", ACCENT)
    out = _text(staged_table([_stage(line)], REFS_PENDING, today=TODAY.isoformat()))
    assert "pendiente" in out and "#Pendiente" in out


def test_the_tags_cell_takes_the_pending_hashtags_name_from_the_engine():
    refs = replace(
        REFS_PENDING,
        hashtag_names={**REFS.hashtag_names, "hp": "Pend-from-engine"},
        pending_hashtag=("hp", "Pend-from-engine"),
    )
    assert _tags_cell_of("tottus -38.60 $BCP Signature PEN", refs).plain == "#Pend-from-engine"


def test_with_no_pending_hashtag_yet_a_line_with_no_hashtag_shows_a_dash():
    cell = _tags_cell_of("tottus -38.60 $BCP Signature PEN", REFS)
    assert (cell.plain, cell.style) == ("—", "dim")


def test_with_no_pending_hashtag_yet_a_hashtag_only_named_like_it_is_listed():
    refs = replace(
        REFS,
        hashtags=[*REFS.hashtags, ("hx", "Pendiente")],
        hashtag_names={**REFS.hashtag_names, "hx": "Pendiente"},
    )
    assert _tags_cell_of(PENDING_AND_REAL_LINE, refs).plain == "#Pendiente #TAXI"


def test_an_unknown_tag_still_reads_in_red_with_a_pending_hashtag():
    cell = _tags_cell_of("tottus -38.60 $BCP Signature PEN #nope")
    assert (cell.plain, cell.style) == ("#nope?", PALETTE.error)


def test_the_staged_row_lists_the_real_hashtag_and_up_brings_back_the_typed_line(
    fake_client, monkeypatch
):
    """Staged with the engine's lists: the row lists #TAXI alone, and picking
    it back up with the arrows lifts the line exactly as typed, #Pendiente in it."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: WITH_PENDING)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, PENDING_AND_REAL_LINE, "tottus -38.60 $BCP Signature PEN")
        rows = staged_rows(screen._staged, screen._refs, palette=PALETTE)
        assert [row[-1].plain for row in rows] == ["#TAXI", "#Pendiente"]
        screen.action_move(1)
        screen.on_input_submitted()  # lift the first row
        assert _bar(screen).value == PENDING_AND_REAL_LINE

    run_app(scenario)


@pytest.mark.parametrize(("code", "status", "reason", "line"), HASHTAG_REFUSALS)
def test_a_hashtag_refusal_on_the_log_bar_shows_as_sent(
    fake_client, monkeypatch, code, status, reason, line
):
    """The row keeps no tick and carries the engine's words whole, then its
    line if the reason has one. A `422` names the row by its place in the batch,
    and the row shows the words on its field; a `409` names no row and reads as sent."""
    err = hashtag_refusal(code, status, reason, item=0)
    entry = _save_line(fake_client, monkeypatch, PENDING_AND_REAL_LINE, script=[err])
    assert not entry.saved
    if status == 409:
        assert entry.error == refusal_text(hashtag_refusal(code, status, reason), line)
    else:
        assert entry.error == "hashtag_ids: stand-in field words"
