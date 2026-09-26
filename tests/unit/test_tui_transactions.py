"""Smoke tests for the Transactions TUI screen."""

from expense.tui.screens.log_bar import LogBarScreen
from expense.tui.screens.quick_log import QuickAddLogScreen
from expense.tui.screens.transactions import TransactionsScreen, transaction_rows
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import page, render_text, run_app, wait_for, wait_for_list, whole

ITEMS = [
    {
        "id": "t1",
        "title": "Sueldo marzo",
        "description": "Planilla",
        "amount_cents": 651900,
        "date": "2026-03-05T00:00:00Z",
        "account_id": "acc1",
        "category_id": "cat1",
        "hashtag_ids": ["h1"],
    },
    {
        "id": "t2",
        "title": "Supermercado",
        "description": None,
        "amount_cents": -43250,
        "date": "2026-03-12T00:00:00Z",
        "account_id": "acc1",
        "category_id": "cat2",
        "hashtag_ids": [],
    },
]
ACCOUNTS = {"acc1": "BCP Soles"}
CATEGORIES = {"cat1": "Ingreso", "cat2": "Comida"}
HASHTAGS = {"h1": "trabajo"}


def test_transaction_rows_format_and_resolve():
    by_id = dict(transaction_rows(ITEMS, ACCOUNTS, CATEGORIES, HASHTAGS))
    # amount grouped, account/category resolved, tags resolved
    assert by_id["t1"][2] == "6,519.00" and by_id["t1"][4] == "BCP Soles"
    assert by_id["t1"][5] == "Ingreso" and by_id["t1"][6] == "trabajo"
    # no tags → em dash; negative amount formatted
    assert by_id["t2"][2] == "-432.50" and by_id["t2"][6] == "—"


def test_transaction_rows_palette_sign_colors_amounts():
    """With a palette the amount cell is a Text sign-colored per backlog 4.2 (rule A)."""
    from expense.tui.theme import Palette

    palette = Palette("#0f0", "#f00", "#ff0")
    by_id = dict(transaction_rows(ITEMS, ACCOUNTS, CATEGORIES, HASHTAGS, palette=palette))
    assert by_id["t1"][2].style == palette.success and str(by_id["t1"][2]) == "6,519.00"
    assert by_id["t2"][2].style == palette.error and str(by_id["t2"][2]) == "-432.50"


def test_transactions_screen_lists_and_opens_detail(monkeypatch):
    import expense.commands.transactions_cmd as tc
    import expense.tui.screens.transactions as tx_mod

    monkeypatch.setattr(tc, "fetch_transactions", lambda *a, **k: page(ITEMS, total=2))
    monkeypatch.setattr(tx_mod, "load_account_name_map", lambda: ACCOUNTS)
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: CATEGORIES)
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: HASHTAGS)
    # the edit screen loads entities on mount — stub those too
    monkeypatch.setattr("expense.commands.accounts_cmd.fetch_accounts", lambda *a, **k: whole([]))
    monkeypatch.setattr(
        "expense.commands.categories_cmd.fetch_categories", lambda *a, **k: whole([])
    )
    monkeypatch.setattr("expense.commands.hashtags_cmd.fetch_hashtags", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(TransactionsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("enter")  # opens the edit screen, pre-filled
        await wait_for(pilot, lambda: isinstance(app.screen, QuickAddLogScreen))
        assert app.screen._resource == "transactions"
        assert app.screen._values["amount"] == 651900

    run_app(scenario)


def test_plus_opens_the_log_bar(monkeypatch):
    """`+` on the ledger logs a new transaction (2026-08-20) — through the LOG
    bar since quick-add phase 4 (2026-08-25). The row under the cursor is
    irrelevant to it."""
    import expense.commands.transactions_cmd as tc
    import expense.tui.screens.transactions as tx_mod

    monkeypatch.setattr(tc, "fetch_transactions", lambda *a, **k: page(ITEMS, total=2))
    monkeypatch.setattr(tx_mod, "load_account_name_map", lambda: ACCOUNTS)
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: CATEGORIES)
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: HASHTAGS)
    monkeypatch.setattr(QuickAddLogScreen, "_load_entities", lambda self: None)
    monkeypatch.setattr(LogBarScreen, "_load_entities", lambda self: None)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(TransactionsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("+")
        await wait_for(pilot, lambda: isinstance(app.screen, LogBarScreen))
        assert app.screen._staged == []

    run_app(scenario)


def test_navigate_is_not_advertised_in_the_footer(monkeypatch):
    """ "Never ever mention that the arrow keys are navigation on the lower bar"
    (user, 2026-08-20). The keys still work — only the footer row is gone, and
    the `?` card still lists them."""
    import expense.commands.transactions_cmd as tc
    import expense.tui.screens.transactions as tx_mod

    monkeypatch.setattr(tc, "fetch_transactions", lambda *a, **k: page(ITEMS, total=2))
    monkeypatch.setattr(tx_mod, "load_account_name_map", lambda: ACCOUNTS)
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: CATEGORIES)
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: HASHTAGS)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(TransactionsScreen())
        await wait_for_list(pilot, app)
        app.screen.query_one(CursorList).focus()
        await pilot.pause()
        shown = [b.description for _n, b, _e, _t in app.active_bindings.values() if b.show]
        assert "Navigate" not in shown
        assert "Open" in shown and "Add" in shown  # the non-obvious keys stay
        # the key itself still moves the cursor
        listing = app.screen.query_one(CursorList)
        before = listing._cursor
        await pilot.press("down")
        await pilot.pause()
        assert listing._cursor == before + 1

    run_app(scenario)


def test_transaction_rows_hand_the_table_whole_cells():
    """The row builder no longer caps title/description/hashtags (2026-09-12,
    option A of docs/mockups/expense-world-ledger-column-fit.html): the table
    cuts each cell at the edge of the column it actually has, so a wide
    terminal shows wide cells instead of wide columns of text cut at 20."""
    long_title = "ANTHROPIC* CLAUDE SUB  ANTHROPIC.COM CA"  # 39 chars, a real bank title
    long_desc = "APPARKA AAP AREQUIPA   AREQUIPA      PE"
    items = [
        {**ITEMS[0], "title": long_title, "description": long_desc, "hashtag_ids": ["h1", "h2"]}
    ]
    tags = {**HASHTAGS, "h2": "x" * 30}
    (_, cells), *_ = transaction_rows(items, ACCOUNTS, CATEGORIES, tags)
    assert cells[0] == long_title and cells[1] == long_desc
    assert cells[6] == "trabajo, " + "x" * 30
    assert "…" not in "".join(str(c) for c in cells)


def test_flex_columns_fill_the_width_and_cut_at_the_column_edge():
    """Free-text columns share the slack by ratio; the fixed ones keep their
    natural width. Rendered narrow, the text cells are elided by the table and
    the amount/date/account cells stay whole — the ledger's degradation order."""

    from expense.tui.screens.transactions import _FLEX, _HEADERS

    long_title = "ANTHROPIC* CLAUDE SUB  ANTHROPIC.COM CA"
    items = [{**ITEMS[0], "title": long_title, "description": "x" * 40}, ITEMS[1]]
    rows = transaction_rows(items, ACCOUNTS, CATEGORIES, HASHTAGS)
    lst = CursorList(_HEADERS, rows, align_right={2}, flex=_FLEX)
    lst._refresh = lambda: None

    def render(width: int) -> list[str]:
        return render_text(lst._build(), width=width).splitlines()

    wide = render(200)
    assert any(long_title in line and "6,519.00" in line for line in wide), wide
    narrow = render(80)
    first = next(line for line in narrow if "6,519.00" in line)
    assert "…" in first and "2026-03-05" in first and "BCP Soles" in first and "Ingreso" in first
    assert long_title not in first
    # the ratio columns are exactly the ones the screen names, nothing else
    table = lst._build()
    assert [c.ratio for c in table.columns] == [3, 3, None, None, None, None, 2]


def test_a_hashtag_filter_narrows_the_category_on_the_wire(monkeypatch):
    """⏎ on a hashtag row on Home (2026-09-13): the ledger asks the engine for
    that category and that hashtag, both, and says so in its crumb."""
    import expense.commands.transactions_cmd as tc
    import expense.tui.screens.transactions as tx_mod
    from expense.tui.screens.transactions import LedgerFilter

    seen: list = []

    def fake(cfg, **kw):
        seen.append(kw)
        return page(ITEMS, total=2)

    monkeypatch.setattr(tc, "fetch_transactions", fake)
    monkeypatch.setattr(tx_mod, "load_account_name_map", lambda: ACCOUNTS)
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: CATEGORIES)
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: HASHTAGS)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        flt = LedgerFilter("category", "cat2", "Comida #trabajo", hashtag_id="h1")
        screen = TransactionsScreen(filter=flt)
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert seen[0]["category"] == "cat2" and seen[0]["hashtag"] == "h1"
        assert "account" not in seen[0]
        assert screen.crumb == ("Ledger", "Comida #trabajo")

    run_app(scenario)
