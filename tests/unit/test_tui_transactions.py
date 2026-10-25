"""Smoke tests for the Transactions TUI screen."""

from expense.reads import AccountIndex
from expense.tui.screens.edit_form import EditFormScreen
from expense.tui.screens.log_bar import LogBarScreen
from expense.tui.screens.transactions import TransactionsScreen, transaction_rows
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import fake_ledger, render_text, run_app, wait_for, wait_for_list, whole

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
        "line_code": "#000001",
        "statement_line": None,
        "statement_place": None,
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
        "line_code": "#000002",
        "statement_line": None,
        "statement_place": None,
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
    """With a palette the amount cell is a Text sign-colored (rule A)."""
    from expense.tui.theme import Palette

    palette = Palette("#0f0", "#f00", "#ff0")
    by_id = dict(transaction_rows(ITEMS, ACCOUNTS, CATEGORIES, HASHTAGS, palette=palette))
    assert by_id["t1"][2].style == palette.success and str(by_id["t1"][2]) == "6,519.00"
    assert by_id["t2"][2].style == palette.error and str(by_id["t2"][2]) == "-432.50"


def test_transactions_screen_lists_and_opens_detail(monkeypatch):
    import expense.tui.screens.transactions as tx_mod

    fake_ledger(monkeypatch, ITEMS)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(ACCOUNTS))
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: CATEGORIES)
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: HASHTAGS)
    # the edit screen loads entities on mount — stub those too
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(TransactionsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("enter")  # opens the edit screen, pre-filled
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        assert app.screen._resource == "transactions"
        assert app.screen._values["amount"] == 651900

    run_app(scenario)


def _ledger_rows(n: int) -> list:
    return [dict(ITEMS[1], id=f"t{i}", title=f"ROW {i}") for i in range(1, n + 1)]


def _patch_detail(monkeypatch, rows: list):
    import expense.tui.screens.transactions as tx_mod

    calls, _counts = fake_ledger(monkeypatch, rows)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(ACCOUNTS))
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: CATEGORIES)
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: HASHTAGS)
    monkeypatch.setattr(EditFormScreen, "_load_entities", lambda self: None)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    return calls


def test_esc_from_the_detail_keeps_the_rows_and_the_cursor(monkeypatch):
    """`⏎` then `esc` is not a write: the ledger comes back as it was — the
    rows `pgdn` loaded and the cursor on the row it was on."""
    calls = _patch_detail(monkeypatch, _ledger_rows(25))

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        listing = screen.query_one(CursorList)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._rows) == 20)
        await pilot.press("down", "down")
        key = listing.cursor_key
        assert key == "t13"
        reads = len(calls)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        assert len(calls) == reads  # nothing was read again
        assert screen.query_one(CursorList) is listing
        assert listing.cursor_key == key and len(screen._rows) == 20

    run_app(scenario)


def test_a_save_from_the_detail_still_reloads_fresh(monkeypatch):
    """A save is a write, and after any write the ledger is the newest 10 again
    with the cursor on row 1."""
    calls = _patch_detail(monkeypatch, _ledger_rows(25))

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: len(screen._rows) == 20)
        reads = len(calls)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        app.screen._done()  # the save's success callback
        await wait_for(pilot, lambda: len(calls) > reads and len(screen._rows) == 10)
        await wait_for(pilot, lambda: screen.query_one(CursorList).cursor_index == 0)

    run_app(scenario)


def test_plus_opens_the_log_bar(monkeypatch):
    """`+` on the ledger logs a new transaction through the LOG bar. The row
    under the cursor is irrelevant to it."""
    import expense.tui.screens.transactions as tx_mod

    fake_ledger(monkeypatch, ITEMS)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(ACCOUNTS))
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: CATEGORIES)
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: HASHTAGS)
    monkeypatch.setattr(EditFormScreen, "_load_entities", lambda self: None)
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
    """The arrow keys are never advertised as navigation on the footer.
    The keys still work — only the footer row is gone, and
    the `?` card still lists them."""
    import expense.tui.screens.transactions as tx_mod

    fake_ledger(monkeypatch, ITEMS)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(ACCOUNTS))
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
    """The row builder never caps title/description/hashtags: the table cuts each cell
    at the edge of the column it actually has."""
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
    """⏎ on a hashtag row on Home: the ledger asks the engine for
    that category and that hashtag, both, and says so in its crumb."""
    import expense.tui.screens.transactions as tx_mod
    from expense.tui.screens.transactions import LedgerFilter

    seen, counts = fake_ledger(monkeypatch, ITEMS)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(ACCOUNTS))
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
        # the count asks the same question as the rows
        assert counts == [{"category": "cat2", "hashtag": "h1", "verbose": False}]
        assert screen.crumb == ("Ledger", "Comida #trabajo")

    run_app(scenario)
