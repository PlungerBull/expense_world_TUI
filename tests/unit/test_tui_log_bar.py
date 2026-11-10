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
from expense.reads import QuickAddRefs, currency_picks
from expense.tui.screens.log_bar import (
    EDIT_HINT,
    LEGEND,
    STAGED_HINT,
    AccountPeek,
    LogBarScreen,
    Staged,
    fit_label,
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
    AMOUNT_BELOW_RANGE_WORDS,
    ENGINE_ORDER_HOLDING_ACCOUNTS,
    HASHTAG_REFUSALS,
    account_with_currencies,
    amount_refusal,
    cursor_page,
    hashtag_refusal,
    held_currency,
    in_order,
    refusal_text,
    render_text,
    run_app,
    screen_lines,
    wait_for,
    whole,
)

ACCOUNTS = [
    account_with_currencies(id="acc1", name="BCP Signature", currencies=[held_currency("PEN")]),
    account_with_currencies(
        id="acc2", name="BCP Signature Platinum", currencies=[held_currency("USD")]
    ),
    account_with_currencies(id="acc3", name="BCP", currencies=[held_currency("PEN")]),
]
CATEGORIES = {
    "items": [
        {"id": "cat1", "name": "KORAKUEN", "is_system": False},
        {"id": "cat2", "name": "TRANSPORTE", "is_system": False},
    ]
}
HASHTAGS = {"items": [{"id": "h1", "name": "CAJA CHICA"}, {"id": "h2", "name": "TAXI"}]}

REFS = QuickAddRefs(
    picks=currency_picks(ACCOUNTS),
    categories=[("cat1", "KORAKUEN"), ("cat2", "TRANSPORTE")],
    hashtags=[("h1", "CAJA CHICA"), ("h2", "TAXI")],
    account_names={
        "acc1": "BCP Signature",
        "acc2": "BCP Signature Platinum",
        "acc3": "BCP",
    },
    category_names={"cat1": "KORAKUEN", "cat2": "TRANSPORTE"},
    hashtag_names={"h1": "CAJA CHICA", "h2": "TAXI"},
)

TODAY = date(2026, 8, 20)


PEEK_ITEMS = [
    {
        "id": "t1",
        "date": "2026-08-20T10:00:00-05:00",
        "day": "2026-08-20",
        "title": "WONG CAYMA",
        "amount_cents": -15240,
        "account_id": "acc1",
        "category_id": "cat1",
        "hashtag_ids": ["h1"],
        "line_code": "#000002",
        "statement_line": None,
        "statement_place": None,
    },
    {
        "id": "t2",
        "date": "2026-08-19T10:00:00-05:00",
        "day": "2026-08-19",
        "title": "NETFLIX",
        "amount_cents": -4490,
        "account_id": "acc1",
        "category_id": "cat2",
        "hashtag_ids": [],
        "line_code": "#000001",
        "statement_line": None,
        "statement_place": None,
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
        self.currencies: list[str] = []
        self.counted_currencies: list[str] = []

    def __call__(self, _cfg, **kw):
        assert "offset" not in kw, "the engine refuses offset"
        self.accounts.append(kw.get("account"))
        self.currencies.append(kw.get("currency_code"))
        if self.error is not None:
            raise self.error
        return self.body

    def count(self, _cfg, **kw):
        self.counted.append(kw.get("account"))
        self.counted_currencies.append(kw.get("currency_code"))
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
        accounts=REFS.quickadd_accounts,
        categories=REFS.categories,
        hashtags=REFS.hashtags,
        today=today,
    )
    return Staged(line=line, parsed=parsed, routing=route(parsed, today))


LEDGER_LINE = "tottus porongoche -38.60 $BCP Signature @KORAKUEN #CAJA CHICA"
NO_ACCOUNT_LINE = "apparka mall -3.50 @TRANSPORTE #TAXI 18/08/2026"  # refused on ↵
NO_CATEGORY_LINE = "apparka mall -3.50 $BCP #TAXI 18/08/2026"  # stages → @Pendiente
NO_TITLE_LINE = "-6.60 $BCP"  # stages as a titleless row
AHEAD_LINE = "alquiler -1800 $BCP @KORAKUEN 22/08/2026"  # refused on ↵
USD_LINE = "shimaya ramen -96.00 $BCP Signature Platinum @KORAKUEN"


# ---- pure: the staged table -------------------------------------------------
def test_ledger_row_is_marked():
    out = _text(staged_table([_stage(LEDGER_LINE)], REFS, today=TODAY.isoformat()))
    assert "•" in out
    assert "goes to" not in out
    assert "TOTTUS" not in out  # the title is shown verbatim, never upper-cased
    assert "tottus porongoche" in out
    assert "-38.60" in out and "BCP Signature" in out and "#CAJA CHICA" in out


def test_the_staged_list_has_a_cur_column_and_the_account_cell_names_the_account_alone():
    """Header `date title amount cur account category tags`; a PEN row and a USD
    row each hold their own code in `cur`, and no account cell reads "<name> · <code>"."""
    pen = _stage(LEDGER_LINE)
    usd = _stage("netflix -9.99 $BCP Signature Platinum @KORAKUEN")
    out = _text(staged_table([pen, usd], REFS, today=TODAY.isoformat()))
    header = out.splitlines()[0].split()
    assert header == ["date", "title", "amount", "cur", "account", "category", "tags"]
    rows = staged_rows([pen, usd], REFS, palette=PALETTE, today=TODAY.isoformat())
    assert [(r[4], r[5]) for r in rows] == [
        ("PEN", "BCP Signature"),
        ("USD", "BCP Signature Platinum"),
    ]
    assert " · PEN" not in out and " · USD" not in out


def test_a_sparse_row_reads_where_the_engine_will_file_it():
    """No category reads `pendiente`, no title `(untitled)`, no tags a dim dash."""
    today = TODAY.isoformat()
    no_category = _text(staged_table([_stage(NO_CATEGORY_LINE)], REFS, today=today))
    assert "•" in no_category and "pendiente" in no_category.lower()
    assert "apparka mall" in no_category
    assert "(untitled)" in _text(staged_table([_stage(NO_TITLE_LINE)], REFS, today=today))
    assert "—" in _text(staged_table([_stage(USD_LINE)], REFS, today=today))


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

    income = _stage("sueldo +2450 $BCP @KORAKUEN").parsed
    amount = next(s for s in income.spans if s.kind == "amount")
    assert span_style(amount, income, PALETTE) == PALETTE.success

    unresolved = _stage("apparka -3.50 $nope @KORAKUEN").parsed  # an unresolved token: error
    bad = next(s for s in unresolved.spans if not s.resolved)
    assert span_style(bad, unresolved, PALETTE) == PALETTE.error


def test_highlighter_paints_the_bar_from_the_parse():

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
        assert "stages the line" not in _legend(screen)
        assert "Nothing staged" in _text(screen._staged_renderable())

    run_app(scenario)


def test_state2_an_ambiguous_account_opens_the_picker(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "tottus porongoche -38.60 $sig")
        assert [name for _, name in screen._picker.candidates] == [
            "BCP Signature",
            "BCP Signature Platinum",
        ]
        assert '"$sig" matches 2 accounts' in screen._hint()
        assert screen._suggest_idx == 0
        screen.action_move(1)
        assert screen._suggest_idx == 1

    run_app(scenario)


def test_the_account_picker_shows_the_engines_order(fake_client, monkeypatch):
    """A bare `$` lists the accounts exactly as `GET /accounts` returned them — not
    alphabetical, not by `sort_order`, the person after every bank — one row each,
    by its name alone."""
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_HOLDING_ACCOUNTS)
    )
    labels = ["Zeta Visa", "Alfa Ahorros", "Ana"]

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "almuerzo -20 $")
        assert [n for _, n in screen._picker.candidates] == labels
        assert in_order(_text(screen._suggest_renderable()), labels)

    run_app(scenario)


def test_state3_enter_completes_the_token_inside_the_line(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "tottus porongoche -38.60 $sig")
        screen.action_move(1)  # the Platinum one
        screen.on_input_submitted()
        assert _bar(screen).value == "tottus porongoche -38.60 $BCP Signature Platinum"
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


def test_state4_a_positive_staged_total_is_unsigned(fake_client, monkeypatch):
    """A sum of amounts is not a transaction's amount: no `+` before it."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "sueldo +1500.00 $BCP Signature @TRANSPORTE")
        screen.on_input_submitted()
        out = _text(screen._staged_renderable())
        assert "  1 staged · 1,500.00 PEN" in out

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

        _type(screen, NO_ACCOUNT_LINE + " $BCP")  # any edit is a new attempt
        assert screen._refused is None
        screen.on_input_submitted()
        assert len(screen._staged) == 2

    run_app(scenario)


def test_an_amount_with_a_comma_after_its_dot_is_refused_in_place(fake_client, monkeypatch):
    """`-13.853,20` is not read as -13.85. The line stays in
    the bar, refused with a note naming `-13.853,20`, and nothing is staged or
    sent; the same figure written `-13,853.20` stages and saves as -13,853.20."""
    _patch(monkeypatch)
    refused = "tottus -13.853,20 $BCP"
    fixed = "tottus -13,853.20 $BCP"

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, refused)
        await pilot.press("enter")
        await pilot.pause()
        assert screen._staged == []
        assert _bar(screen).value == refused
        assert screen._refused is not None
        out = _text(screen._suggest_renderable(), width=160)
        assert "not staged" in out
        assert "can't read -13.853,20 as an amount: amounts are 1,234.56" in out
        assert "needs a sign" not in out
        assert fake_client.posts == []

        _type(screen, fixed)
        await pilot.press("enter")
        await wait_for(pilot, lambda: len(screen._staged) == 1)
        assert screen._staged[0].parsed.amount_cents == -1385320
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

    run_app(scenario)
    [(path, body)] = fake_client.posts
    assert path == "/transactions/batch"
    assert [row["amount_cents"] for row in body["transactions"]] == [-1385320]


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


def test_ctrl_x_beats_the_inputs_own_cut_binding(fake_client, monkeypatch):
    """Textual's Input binds ctrl+x to `cut`; ours must win, or the key would
    edit the line instead of dropping the row."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, NO_CATEGORY_LINE)
        screen.action_move(1)
        await pilot.press("ctrl+x")
        await wait_for(pilot, lambda: len(screen._staged) == 1, message="ctrl+x never dropped it")
        assert [e.line for e in screen._staged] == [NO_CATEGORY_LINE]

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
        _stage_lines(screen, LEDGER_LINE, NO_CATEGORY_LINE, NO_TITLE_LINE, USD_LINE)
        assert len(screen._staged) == 4

        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: len(fake_client.posts) == 1)

        batch_path, batch_body = fake_client.posts[0]
        assert batch_path == "/transactions/batch"
        rows = batch_body["transactions"]
        assert len(rows) == 4  # ONE call for every row, not one call each
        assert "category_id" not in rows[1] and rows[1]["title"] == "apparka mall"
        assert "title" not in rows[2] and "category_id" not in rows[2]
        # each item names its account; the lines typed no `%` and their accounts hold one
        # currency, so no `currency_code` (never a null) and no `holder_id` go
        assert [r["account_id"] for r in rows] == ["acc1", "acc3", "acc3", "acc2"]
        assert all("currency_code" not in r and "holder_id" not in r for r in rows)

        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))
        assert app.screen is screen  # it stays: the ticks are the receipt
        assert "4 logged · 2 pendiente" in _text(screen._staged_renderable())

    run_app(scenario)


VISA = account_with_currencies(
    id="acc-visa",
    name="VISA Infinite Sapphire",
    currencies=[held_currency("PEN"), held_currency("USD")],
)


def test_dollar_visa_is_one_account_and_the_currency_is_a_token_of_its_own(
    fake_client, monkeypatch
):
    """`$visa` names one account holding two currencies; `%usd` picks the dollars, and
    the save sends that account with that currency."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([VISA, *ACCOUNTS]))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "-12.50 $visa")
        assert screen._picker is None  # one account, however many currencies it holds
        assert screen._parsed.account_id == "acc-visa"
        _type(screen, "-12.50 $visa %")
        labels = ["PEN", "USD"]
        assert [c for c, _ in screen._picker.candidates] == labels
        assert in_order(_text(screen._suggest_renderable()), labels)
        assert '"%" names no currency yet' in screen._hint()

        screen.action_move(1)  # the USD one
        screen.on_input_submitted()
        assert _bar(screen).value == "-12.50 $visa %USD"
        assert screen._picker is None
        assert (screen._parsed.account_id, screen._parsed.currency_code) == ("acc-visa", "USD")

        screen.on_input_submitted()
        shown = _text(screen._staged_renderable())
        assert "VISA Infinite Sapphire" in shown and "VISA Infinite Sapphire · USD" not in shown
        assert staged_rows(screen._staged, screen._refs, palette=PALETTE)[0][4] == "USD"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: len(fake_client.posts) == 1)
        item = fake_client.posts[0][1]["transactions"][0]
        assert (item["account_id"], item["currency_code"]) == ("acc-visa", "USD")

    run_app(scenario)


def test_the_currency_token_is_listed_in_the_legend_and_painted_as_a_pick(fake_client, monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([VISA, *ACCOUNTS]))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        assert "$account · %currency · @category" in _legend(screen)
        _type(screen, "-12.50 $visa %usd")
        (span,) = [s for s in screen._parsed.spans if s.kind == "currency"]
        assert span_style(span, screen._parsed, PALETTE) == ACCENT

    run_app(scenario)


def test_a_two_currency_account_with_none_picked_is_not_staged_and_lists_its_currencies(
    fake_client, monkeypatch
):
    """The words of the LOG bar's currency pick; `↑↓`
    and `↵` write the pick into the line as `%USD`, and `↵` again stages it."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([VISA, *ACCOUNTS]))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "Streamly -12.99 $visa")
        screen.on_input_submitted()
        assert screen._staged == []
        assert screen._hint() == "not staged — pick a currency and press ↵ again"
        shown = _text(screen._suggest_renderable())
        assert [line.strip() for line in shown.splitlines()] == [
            "! not staged — VISA Infinite Sapphire holds PEN and USD: pick one",
            "PEN",
            "USD",
        ]
        screen.action_move(1)
        screen.on_input_submitted()
        assert _bar(screen).value == "Streamly -12.99 $visa %USD"
        assert screen._staged == []
        screen.on_input_submitted()
        assert [e.parsed.currency_code for e in screen._staged] == ["USD"]

    run_app(scenario)


def test_the_peek_follows_the_highlighted_currency_of_the_percent_picker(fake_client, monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([VISA, *ACCOUNTS]))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "-12.50 $visa %")
        assert screen._peek_target() == ("acc-visa", "PEN")
        screen.action_move(1)
        assert screen._peek_target() == ("acc-visa", "USD")

    run_app(scenario)


def test_a_line_refused_for_an_unknown_account_keeps_its_own_hint(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "taxi -5 $zzz")
        screen.on_input_submitted()
        assert screen._staged == []
        assert '"$zzz" matches no accounts' in " ".join(screen._refused.reasons)
        assert screen._hint() == "not staged — fix the line and press ↵ again"
        assert "pick something that exists" not in _text(screen._suggest_renderable())
        assert "pick a currency" not in _text(screen._suggest_renderable())

    run_app(scenario)


def test_a_line_refused_for_its_currency_and_something_else_gets_the_plain_hint(
    fake_client, monkeypatch
):
    """The pick of a currency is the hint only when it is the line's sole problem."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([VISA, *ACCOUNTS]))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "Streamly -12.99 $visa")
        screen.on_input_submitted()
        assert len(screen._refused.reasons) == 1
        assert screen._hint() == "not staged — pick a currency and press ↵ again"
        # a category that matches nothing, beside the currency
        screen._set_bar("Streamly -12.99 $visa @zzzz")
        screen.on_input_submitted()
        assert len(screen._refused.reasons) == 2
        assert screen._offered
        assert screen._hint() == "not staged — fix the line and press ↵ again"
        # no amount beside the currency: the same plain hint
        screen._set_bar("taxi $visa")
        screen.on_input_submitted()
        assert screen._hint() == "not staged — fix the line and press ↵ again"

    run_app(scenario)


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


#: The engine's words on a batch item dated on a sealed day, of the form the contract
#: prints (contract: "Transactions (Ledger)", "Sealed periods").
_SEALED = (
    "Period 2026-08-01 to 2026-08-25 is sealed by completed statement 'August 2026'. "
    "Revert it to draft to change anything inside it."
)


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


def test_a_run_stop_keeps_a_rows_own_earlier_refusal(fake_client, monkeypatch):
    """Row 2 is refused for its own date; row 1, sent again alone, meets the
    line codes running out. The stop is one toast and on no row; row 2 keeps the
    engine's words for its own refusal, never swallowed."""
    _patch(monkeypatch)
    date_key = "transactions.1.date"
    own = EngineError(
        "VALIDATION_ERROR",
        "Batch validation failed.",
        {date_key: _SEALED},
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
        assert _SEALED in second.error
        assert "LIMIT_REACHED" not in second.error
        assert sum("LIMIT_REACHED" in t for t in toasts) == 1

    run_app(scenario)


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


def test_any_other_409_is_a_refusal_with_no_tick(fake_client, monkeypatch):
    """Only a replay of the row's own id is a tick. A row refused for another
    reason keeps no ✓ and shows the engine's words, then the line saying what to
    do: `ctrl+s` is how this screen saves again."""
    _patch(monkeypatch)
    reason, line = "CONCURRENT_CHANGE", "It changed at the same moment: save again."

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


def test_ctrl_s_leaves_a_half_typed_line_in_the_bar_alone(fake_client, monkeypatch):
    """Decision 3: `↵` is the only thing that stages, so a save can never write
    something you were still in the middle of."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE)
        _type(screen, "pollo -25 $BCP @KORAKUEN")  # typed, never submitted
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: all(e.saved for e in screen._staged))

        assert len(screen._staged) == 1  # the bar's line was not staged
        batch = fake_client.posts[0][1]["transactions"]
        assert len(batch) == 1 and batch[0]["title"] == "tottus porongoche"
        assert _bar(screen).value == "pollo -25 $BCP @KORAKUEN"  # still yours

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
def test_the_summary_totals_only_the_rows_still_pending():
    """A written row stops being something you are about to do — otherwise the
    figure under a half-saved list describes a batch that no longer exists."""
    done, pending = _stage(LEDGER_LINE), _stage(USD_LINE)
    done.saved = True
    out = _text(staged_summary([done, pending], REFS, palette=PALETTE))
    assert "1 logged" in out
    assert "-96.00" in out and "USD" in out  # the pending row's own currency
    assert "-38.60" not in out  # the saved one has left the total


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


def test_refused_rows_read_one_line_per_kind(fake_client, monkeypatch):
    """The engine's words, then the rows they hit — `row 3` for one,
    `rows 2, 4` for several — and the line saying what to press, dim, last."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, LEDGER_LINE, USD_LINE, NO_CATEGORY_LINE, LEDGER_LINE)
        _script(fake_client, [_two_kinds(), {}])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)

        out = _text(save_errors(screen._staged), width=200)  # the sealed line whole
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


def test_peek_row_of_a_titleless_transaction_shows_untitled():
    row = {
        "date": "2026-08-20T10:00:00-05:00",
        "day": "2026-08-20",
        "amount_cents": -100,
        "line_code": "#000003",
        "statement_line": None,
        "statement_place": None,
    }
    rows = peek_rows([row], REFS)
    assert rows and str(rows[0][1]) == "(untitled)"


def test_peek_status_names_the_label_the_title_shows():
    label = "VISA Infinite Sapphire · USD"
    assert peek_status(3, 48, label) == f"3 of 48 in {label} · newest first"
    assert peek_status(3, 3, label) == f"3 in {label} · newest first"
    assert peek_status(0, 0, label) == f"nothing in {label} yet"
    # squeezed out by a long staged list: say so, do not read as an empty account
    assert peek_status(0, 48, label) == f"48 in {label} · no room to show them"


def test_peek_status_shortens_only_the_name_to_fit_the_width():
    name = "Interbank Cuenta Sueldo Mancomunada Familia Quispe"
    for args, ending in (
        ((7, 1716), " · PEN · newest first"),
        ((0, 0), " · PEN yet"),
        ((0, 1716), " · PEN · no room to show them"),
    ):
        line = peek_status(*args, name, "PEN", 60)
        assert len(line) == 60 and "…" in line and line.endswith(ending)
    assert peek_status(7, 1716, name, "PEN", 72) == (
        "7 of 1716 in Interbank Cuenta Sueldo Mancomunada F… · PEN · newest first"
    )
    # a name that fits, an unknown width and a hopeless one never break the line
    assert peek_status(7, 1716, "BCP", "PEN", 72) == "7 of 1716 in BCP · PEN · newest first"
    assert peek_status(7, 1716, name, "PEN", 0).count("…") == 0
    assert peek_status(7, 1716, name, "PEN", 5).startswith("7 of 1716 in I")
    assert peek_status(3, 3, name, None, 40).endswith("… · newest first")


LONG_ACCOUNT = "Cuenta Corriente Empresarial Korakuen Ingeniería y Construcción SAC Arequipa"


def test_a_long_account_name_gives_way_in_the_title_too(fake_client, monkeypatch):
    assert len(LONG_ACCOUNT) == 76
    accounts = [
        account_with_currencies(id="acc9", name=LONG_ACCOUNT, currencies=[held_currency("PEN")])
    ]
    _patch(monkeypatch, _PeekFetch(total=214))
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(accounts))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, f"tottus -38.60 ${LONG_ACCOUNT} @KORAKUEN")
        await _peeked(pilot, screen)
        panel = _peek(screen)
        title = panel.panel_title
        assert "…" in title and title.endswith("… · PEN")
        assert title.endswith(" · PEN") and len(title) <= panel.content_size.width
        lines = [ln.rstrip() for ln in screen_lines(app)]
        # one row: the title, then the rule; the count line is on screen below the rows
        at = next(i for i, ln in enumerate(lines) if ln.strip() == title)
        assert set(lines[at + 1].strip()) <= {"─", "━", "-"}
        assert any(" of 214 in " in ln and ln.endswith(" · PEN · newest first") for ln in lines)
        # the same cut as the count line, and wider again the name comes back whole
        await pilot.resize_terminal(140, 24)
        await wait_for(
            pilot, lambda: panel.panel_title == f"{LONG_ACCOUNT} · PEN", message="no refit"
        )
        await pilot.pause()
        assert f"{LONG_ACCOUNT} · PEN" in [ln.strip() for ln in screen_lines(app)]

    run_app(scenario, size=(80, 24))


def test_a_short_name_and_a_two_currency_pick_keep_their_title():
    assert fit_label("BCP", "PEN", 80) == "BCP · PEN"
    assert fit_label("visa", "USD", 80) == "visa · USD"
    assert fit_label("BCP", None, 80) == "BCP"
    cut = fit_label(LONG_ACCOUNT, "PEN", 80)
    assert len(cut) == 80 and cut.endswith("… · PEN")
    assert fit_label(LONG_ACCOUNT, "PEN", 0) == f"{LONG_ACCOUNT} · PEN"


async def _peeked(pilot, screen):
    """Until the panel's fetch has landed (it is debounced, then threaded) and
    the panel has measured its room and drawn rows, so its status line and
    content are the settled ones (before its first layout it reads "no room")."""
    await wait_for(pilot, lambda: bool(screen._peek_cache), message="the peek never loaded")
    panel = _peek(screen)
    await wait_for(
        pilot,
        lambda: (
            panel.capacity > 0 and bool(panel.panel_status) and "no room" not in panel.panel_status
        ),
        message="the peek never drew its rows",
    )


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
        # the pick's currency rides on the read and on the count
        assert (fetch.currencies, fetch.counted_currencies) == (["PEN"], ["PEN"])
        panel = _peek(screen)
        assert panel.display
        # content lines, not border decorations (docs/tui.md §2)
        assert panel.panel_title == "BCP Signature · PEN"
        assert f"of 214 in {panel.panel_title}" in panel.panel_status
        assert "WONG CAYMA" in _text(panel.content)

    run_app(scenario, size=(110, 30))


def test_the_peek_title_and_count_name_the_picked_currency_of_a_two_currency_account(
    fake_client, monkeypatch
):
    fetch = _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([VISA, *ACCOUNTS]))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "-12.50 $visa")
        assert screen._peek_target() is None  # no currency picked: no ledger to show
        _type(screen, "-12.50 $visa %usd")
        await _peeked(pilot, screen)
        panel = _peek(screen)
        assert (fetch.currencies, fetch.counted_currencies) == (["USD"], ["USD"])
        assert panel.panel_title == "VISA Infinite Sapphire · USD"
        assert panel.panel_status == "2 of 214 in VISA Infinite Sapphire · USD · newest first"
        drawn = [ln.strip() for ln in screen_lines(app)]
        assert "VISA Infinite Sapphire · USD" in drawn
        assert "2 of 214 in VISA Infinite Sapphire · USD · newest first" in drawn
        assert not any("· PEN" in ln for ln in drawn)

    run_app(scenario, size=(110, 30))


def test_a_nameless_account_reads_the_same_in_the_title_and_the_count_line(
    fake_client, monkeypatch
):
    accounts = [account_with_currencies(id="acc9", name="", currencies=[held_currency("PEN")])]
    fetch = _patch(monkeypatch, _PeekFetch(body=cursor_page([], next_cursor=None), total=0))
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(accounts))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "tottus -38.60 $(unnamed) @KORAKUEN")
        await wait_for(pilot, lambda: bool(fetch.accounts), message="never fetched")
        panel = _peek(screen)
        await wait_for(pilot, lambda: bool(panel.panel_status), message="no status")
        assert panel.panel_title == "(unnamed) · PEN"
        assert panel.panel_status == "nothing in (unnamed) · PEN yet"

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
        assert screen._peek_account == ("acc1", "PEN")  # the highlighted candidate
        screen.action_move(1)
        assert screen._peek_account == ("acc2", "USD")  # …and it swaps as you arrow

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
        assert screen._peek_account == ("acc1", "PEN")
        assert _peek(screen).display

    run_app(scenario, size=(110, 30))


def test_the_staged_rows_never_choose_the_peeks_account(fake_client, monkeypatch):
    """The account is the bar's. A staged row for another one does not vote."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)  # $BCP Signature → acc1
        screen.on_input_submitted()
        _type(screen, "tran.cel.bm. -6.60 $BCP @TRANSPORTE")
        assert screen._peek_account == ("acc3", "PEN")  # the line's, not the staged row's
        assert _peek(screen).panel_title == "BCP · PEN"

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
# The whole grammar in one row.
def test_the_legend_is_one_row_and_the_footer_carries_stage(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        await _open(app, pilot)
        await pilot.pause()
        lines = screen_lines(app)
        at = next(i for i, line in enumerate(lines) if "$account" in line)
        assert lines[at].strip() == LEGEND
        assert "stages" not in lines[at + 1]  # the next row is not a wrapped tail
        assert not any("stages the line" in line for line in lines)
        footer = next(line for line in lines if "Cancel" in line)
        assert " ".join(footer.split()) == "esc Cancel ⏎ Stage ^s Save"

    run_app(scenario)
    run_app(scenario, size=(140, 30))


def test_enter_still_stages_with_the_footer_entry(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        await pilot.press("enter")
        assert [e.line for e in screen._staged] == [LEDGER_LINE]

    run_app(scenario)


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
        assert screen._peek_account == ("acc1", "PEN")  # hidden, not forgotten
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
        assert _shown_bindings(screen) == {
            "escape": "Cancel",
            "enter": "Stage",
            "ctrl+s": "Save",
        }
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


# ---- the pending hashtag never rides beside a real one ---------------------------
# (contract: "Transactions (Ledger)", "Hashtags on a transaction")

WITH_PENDING = {
    "items": [
        {"id": "h1", "name": "CAJA CHICA", "system_key": None},
        {"id": "h2", "name": "TAXI", "system_key": None},
        {"id": "hp", "name": "Pendiente", "system_key": "pending"},
    ]
}
PENDING_AND_REAL_LINE = "tottus -38.60 $BCP Signature @KORAKUEN #Pendiente #TAXI"


def _save_line(fake_client, monkeypatch, *lines, script=None, tags=WITH_PENDING):
    """Stage `lines` with the pending hashtag in the lists, save them; returns the
    first staged row once the save has run."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: tags)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, *lines)
        if script is not None:
            _script(fake_client, script)
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)
        seen["entry"] = screen._staged[0]

    run_app(scenario)
    return seen["entry"]


def test_the_pending_hashtag_is_sent_alone_and_never_beside_a_real_one(fake_client, monkeypatch):
    """A real tag beside `#Pendiente` goes alone; `#Pendiente` alone goes; no tag sends
    no `hashtag_ids` at all, so the engine files the row under the pending hashtag."""
    _save_line(
        fake_client,
        monkeypatch,
        PENDING_AND_REAL_LINE,
        "tottus -38.60 $BCP Signature #Pendiente",
        "tottus -38.60 $BCP Signature",
    )
    sent = [item.get("hashtag_ids") for item in fake_client.posts[0][1]["transactions"]]
    assert sent == [["h2"], ["hp"], None]


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
REFS_PENDING_RENAMED = replace(
    REFS_PENDING,
    hashtag_names={**REFS.hashtag_names, "hp": "Pend-from-engine"},
    pending_hashtag=("hp", "Pend-from-engine"),
)
REFS_NAMED_LIKE_PENDING = replace(
    REFS,
    hashtags=[*REFS.hashtags, ("hx", "Pendiente")],
    hashtag_names={**REFS.hashtag_names, "hx": "Pendiente"},
)
PLAIN_LINE = "tottus -38.60 $BCP Signature"


@pytest.mark.parametrize(
    ("line", "refs", "plain", "style"),
    [
        (PENDING_AND_REAL_LINE, REFS_PENDING, "#TAXI", ACCENT),  # the real one alone
        (PLAIN_LINE + " #Pendiente", REFS_PENDING, "#Pendiente", ACCENT),
        (PLAIN_LINE, REFS_PENDING, "#Pendiente", ACCENT),  # no tag: where the engine files it
        (PLAIN_LINE, REFS_PENDING_RENAMED, "#Pend-from-engine", ACCENT),  # the engine's name
        (PLAIN_LINE, REFS, "—", "dim"),  # no pending hashtag yet
        (PENDING_AND_REAL_LINE, REFS_NAMED_LIKE_PENDING, "#Pendiente #TAXI", ACCENT),
        (PLAIN_LINE + " #nope", REFS_PENDING, "#nope?", PALETTE.error),
    ],
)
def test_the_tags_cell_echoes_what_the_save_sends(line, refs, plain, style):
    parsed = parse(
        line,
        accounts=refs.quickadd_accounts,
        categories=refs.categories,
        hashtags=refs.hashtags,
        today=TODAY,
    )
    entry = Staged(line=line, parsed=parsed, routing=route(parsed, TODAY))
    cell = staged_rows([entry], refs, palette=PALETTE, today=TODAY.isoformat())[0][-1]
    assert (cell.plain, cell.style) == (plain, style)


@pytest.mark.parametrize(("code", "status", "reason", "line"), HASHTAG_REFUSALS[::2])
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


@pytest.mark.parametrize(("width", "title_len"), [(74, 60), (114, 100)])
def test_the_staged_list_cuts_the_title_and_keeps_every_other_cell_whole(width, title_len):
    """Rows wider than the bar (74 columns is an 80-column terminal less
    `#staged`'s padding): the title and tags give way with `…`; the marker,
    date, amount, `cur`, account and category are never cut."""
    title = "x" * title_len
    rows = [
        _stage(f"{title} -38.60 $BCP Signature @KORAKUEN #CAJA CHICA"),
        _stage("shimaya ramen -96.00 $BCP Signature Platinum @KORAKUEN"),
        _stage("sueldo +1500.00 $BCP Signature @TRANSPORTE"),
    ]
    lines = render_text(staged_table(rows, REFS, today=TODAY.isoformat()), width=width).splitlines()
    head, body = lines[0], lines[1:4]
    assert "cur" in head and "category" in head
    assert "…" in body[0].split("-38.60")[0]  # the long title ends in …
    expected = [
        ("• 1", "-38.60", "PEN", "BCP Signature", "KORAKUEN"),
        ("• 2", "-96.00", "USD", "BCP Signature Platinum", "KORAKUEN"),
        ("• 3", "+1,500.00", "PEN", "BCP Signature", "TRANSPORTE"),
    ]
    for line, cells in zip(body, expected, strict=True):
        assert "20 Aug" in line
        whole = line[: line.index(cells[4]) + len(cells[4])]
        assert "…" not in whole[whole.index(cells[1]) :]  # amount through category
        for cell in cells:
            assert cell in line


def test_a_plain_amount_past_the_bound_is_sent_and_refused_in_the_engines_words(
    fake_client, monkeypatch
):
    """The app adds no bound: the amount goes as whole cents, and the engine's refusal reads in its
    words on its row (contract: "Money amounts")."""
    _patch(monkeypatch)
    amount, cents = "-1000000000.00", -100000000000
    err = amount_refusal("transactions.0.amount_cents", below=True)
    words = AMOUNT_BELOW_RANGE_WORDS

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _stage_lines(screen, f"tottus {amount} $BCP")
        assert screen._staged[0].parsed.amount_cents == cents
        _script(fake_client, [err])
        await pilot.press("ctrl+s")
        await _save_settled(pilot, screen, fake_client)
        out = _text(save_errors(screen._staged), width=200)
        assert f"amount_cents: {words} row 1" in out
        assert [e.saved for e in screen._staged] == [False]

    run_app(scenario)
    [(_path, body)] = fake_client.posts
    assert [row["amount_cents"] for row in body["transactions"]] == [cents]


BANKS = [
    account_with_currencies(
        id="n1",
        name="BCP-5678",
        numbers=[
            {"last4": "1234", "start_date": None, "end_date": "2025-12-31"},
            {"last4": "5678", "start_date": "2026-01-01", "end_date": None},
        ],
        currencies=[held_currency("PEN")],
    ),
    account_with_currencies(
        id="n2",
        name="BCP-4471",
        numbers=[{"last4": "4471", "start_date": None, "end_date": None}],
        currencies=[held_currency("PEN")],
    ),
    account_with_currencies(id="n3", name="BCP", numbers=[], currencies=[held_currency("PEN")]),
]


@pytest.mark.parametrize(
    ("pick", "typed", "account"),
    [(0, "$BCP-5678", "n1"), (2, "$BCP", "n3"), (1, "$BCP-4471", "n2")],
)
def test_dollar_bcp_lists_the_three_and_a_pick_resolves_to_that_account(
    fake_client, monkeypatch, pick, typed, account
):
    """The exact name `BCP` and every `BCP-…` stand in the list while `$bcp` is typed; the
    picked name is written into the line and resolves to its own account, and `↵` again
    stages it."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(BANKS))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "Almuerzo -24.00 $bcp")
        assert [c[1] for c in screen._picker.candidates] == ["BCP-5678", "BCP-4471", "BCP"]
        screen._suggest_idx = pick
        screen.on_input_submitted()
        assert _bar(screen).value == f"Almuerzo -24.00 {typed}"
        assert screen._picker is None
        assert screen._parsed.account_id == account
        screen.on_input_submitted()
        assert [e.parsed.account_id for e in screen._staged] == [account]

    run_app(scenario)


def test_dollar_and_a_cards_last_four_stage_the_account_that_holds_it(fake_client, monkeypatch):
    """The wiring from the engine's `numbers` to the parser: a current and an earlier
    number both find their account, and the line stages on it."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(BANKS))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "Almuerzo -24.00 $4471")
        assert screen._parsed.account_id == "n2"
        _type(screen, "Almuerzo -24.00 $5678")
        assert screen._parsed.account_id == "n1"
        screen.on_input_submitted()
        assert [e.parsed.account_id for e in screen._staged] == ["n1"]
        _type(screen, "Cena -9.00 $1234")
        screen.on_input_submitted()
        assert [e.parsed.account_id for e in screen._staged] == ["n1", "n1"]

    run_app(scenario)


def test_a_lifted_line_naming_bcp_is_finished_text_and_restages_on_the_same_account(
    fake_client, monkeypatch
):
    """Stage `$BCP` through the list, lift the row: no list opens over the resolved token,
    the hint is the edit's, and `↵` stages the same account with the text unchanged."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(BANKS))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "Almuerzo -24.00 $bcp")
        screen._suggest_idx = 2
        screen.on_input_submitted()
        screen.on_input_submitted()
        assert [e.parsed.account_id for e in screen._staged] == ["n3"]
        screen._lift(0)
        assert _bar(screen).value == "Almuerzo -24.00 $BCP"
        assert screen._picker is None
        assert screen._hint() == EDIT_HINT
        screen.on_input_submitted()
        assert [(e.line, e.parsed.account_id) for e in screen._staged] == [
            ("Almuerzo -24.00 $BCP", "n3")
        ]

    run_app(scenario)


def test_a_pick_that_writes_the_text_already_in_the_bar_leaves_no_echo_waiting(
    fake_client, monkeypatch
):
    """`$BCP` typed whole and picked as `BCP` changes nothing, so no `Changed` follows; the
    next keystroke must still read as typing and reopen the list."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(BANKS))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "Almuerzo -24.00 $BCP")
        screen._suggest_idx = 2
        screen.on_input_submitted()
        assert _bar(screen).value == "Almuerzo -24.00 $BCP"
        assert screen._echo is False
        _type(screen, "Almuerzo -24.00 $BCP")  # the next keystroke
        assert screen._picker is not None

    run_app(scenario)


@pytest.mark.parametrize("key", ["escape", "ctrl+x"])
def test_leaving_a_lifted_row_leaves_the_staged_hint_not_the_completed_one(
    fake_client, monkeypatch, key
):
    """A lifted line is finished text; esc or dropping the row empties the bar, and the hint
    is the staged list's again."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(BANKS))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, "Almuerzo -24.00 $5678")
        screen.on_input_submitted()
        _type(screen, "Cena -9.00 $4471")
        screen.on_input_submitted()
        screen._picked = 0
        screen._lift(0)
        assert screen._hint() == EDIT_HINT
        if key == "escape":
            screen.action_back()
        else:
            screen.action_drop_row()
        assert _bar(screen).value == ""
        assert screen._editing is None
        assert screen._hint() == STAGED_HINT

    run_app(scenario)
