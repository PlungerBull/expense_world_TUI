"""Every list shows a name or a title as the engine holds it, `[` and all.

A plain cell is words, never content markup: `BCP [like this]` keeps its
brackets, and a `[/]` or a lone `[` neither vanishes nor breaks the list. The
app's own styled cells (`Text`: a swatch, a coloured amount, a mark) keep their
styling. Pinned where the owner meets it: Home's balances, Manage ▸ Accounts,
the ledger, the bank import's preview, the reconciliation tick list and the LOG
bar's staged rows (mockup expense-world-bracketed-names.html).
"""

import re

import pytest
from rich.text import Text
from textual.widgets import OptionList

import expense.tui.screens.transactions as tx_mod
from expense.reads import AccountIndex
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.reconciliations import ReconciliationDetailScreen
from expense.tui.screens.transactions import TransactionsScreen
from expense.tui.widgets.cells import swatch
from expense.tui.widgets.cursor_list import CursorList, list_table
from tests.unit.helpers import (
    HOME_DASHBOARD,
    account_with_currencies,
    bank_line_row,
    cursor_page,
    fake_ledger,
    held_currency,
    import_part,
    import_row,
    render_text,
    run_app,
    stub_home_month,
    wait_for,
    wait_for_list,
    whole,
)
from tests.unit.test_tui_accounts import ITEMS as ACCOUNT_ITEMS
from tests.unit.test_tui_bank_import import (
    _bank_file,
    _drop,
    _engine,
    _lines_shown,
    _open,
    _patch,
    _preview,
    _previewed,
)
from tests.unit.test_tui_log_bar import _open as _open_log_bar
from tests.unit.test_tui_log_bar import _patch as _patch_log_bar
from tests.unit.test_tui_log_bar import _type
from tests.unit.test_tui_reconcile_detail import DRAFT
from tests.unit.test_tui_transactions import ITEMS as LEDGER_ITEMS

NAME = "BCP [like this]"
#: Words that lose something when read as markup: a whole tag pair, a closing
#: tag with nothing to close (Rich refuses it outright), a bold pair.
BRACKETED = [NAME, "[/]", "[bold]x[/bold]"]


@pytest.mark.parametrize("words", [NAME, "[/]", "a lone [ here", "[bold]x[/bold]", "[[x]]"])
def test_a_plain_cell_shows_as_typed(words):
    """A plain-string cell is drawn as its words: nothing read as markup."""
    table = list_table(["Name", "Cur"], [("k", [words, "PEN"])])
    shown = render_text(table, width=80)
    assert words in shown, shown


def test_a_plain_cell_is_never_styled_by_its_words():
    """`[bold]x[/bold]` typed as a name shows its tags and is not bold."""
    table = list_table(["Name"], [("k", ["[bold]x[/bold]"])])
    row = next(line for line in render_text(table, width=40, ansi=True).splitlines() if "x" in line)
    assert "[bold]x[/bold]" in row
    assert "\x1b[1m" not in row  # the header is bold; the name's row is not


def test_the_apps_own_styled_cells_keep_their_styling():
    """A `Text` the app built (a swatch, a coloured mark) is drawn as built,
    beside a bracketed plain name in the same row."""
    mark = Text("✓", style="green")
    table = list_table(["Name", "Color", ""], [("k", [NAME, swatch("#4a90d9"), mark])])
    cells = [cell for column in table.columns for cell in column.cells]
    assert cells[1].style == "#4a90d9" and cells[2] is mark
    shown = render_text(table, width=80, ansi=True)
    for built, glyph in ((swatch("#4a90d9"), "██"), (mark, "✓")):
        colour = render_text(built, ansi=True).split(glyph)[0]  # its escape, drawn alone
        assert colour and colour + glyph in shown, shown
    assert NAME in render_text(table, width=80)


@pytest.mark.parametrize("words", BRACKETED)
def test_home_shows_a_bracketed_balance_name_whole(monkeypatch, words):
    """Home's balances: a bank account and a person as the engine holds them,
    the balance after each where it was."""
    account = {**HOME_DASHBOARD["bank_accounts"][0], "name": words}
    person = {"id": "p1", "name": words, "currency_code": "PEN", "current_balance_cents": -150000}
    dashboard = {
        **HOME_DASHBOARD,
        "bank_accounts": [account, *HOME_DASHBOARD["bank_accounts"][1:]],
        "people": [person],
    }
    stub_home_month(monkeypatch, dashboard=dashboard)

    async def scenario(pilot, app):
        home = app.screen
        await wait_for(pilot, lambda: home._data is not None)
        await pilot.pause()
        option_list = app.query_one(OptionList)
        options = [option_list.get_option_at_index(i) for i in range(option_list.option_count)]
        shown = {o.id: render_text(o.prompt, width=120).strip() for o in options if o.id}
        for row_id, balance in (("account:a-pen", "5,145.82 PEN"), ("account:p1", "-1,500.00 PEN")):
            assert re.split(r"\s{2,}", shown[row_id]) == [words, balance], shown[row_id]

    run_app(scenario)


def test_manage_accounts_shows_a_bracketed_name_whole(monkeypatch):
    items = [{**ACCOUNT_ITEMS[0], "name": NAME}, *ACCOUNT_ITEMS[1:]]
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(items))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        cl = app.screen.query_one(CursorList)
        lines = render_text(cl._build(), width=AccountsScreen.CARD_WIDTH - 2).splitlines()
        row = next(line for line in lines if "BCP" in line)
        assert NAME in row, row
        assert row.split()[3:5] == ["bank", "PEN"]  # the columns after it are where they were

    run_app(scenario)


def test_the_ledger_shows_a_bracketed_title_and_account_whole(monkeypatch):
    items = [{**LEDGER_ITEMS[0], "title": "Sueldo [marzo]"}, *LEDGER_ITEMS[1:]]
    fake_ledger(monkeypatch, items)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex({"acc1": NAME}))
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: {"cat1": "Ingreso [/]"})
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: {"h1": "trabajo"})
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(TransactionsScreen())
        await wait_for_list(pilot, app)
        cl = app.screen.query_one(CursorList)
        lines = render_text(cl._build(), width=200).splitlines()
        row = next(line for line in lines if "6,519.00" in line)
        assert "Sueldo [marzo]" in row and NAME in row and "Ingreso [/]" in row, row

    run_app(scenario, size=(200, 35))


def test_the_bank_import_preview_shows_a_bracketed_title_whole(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    rows = [import_row(2, 651900, day="2026-09-12", title=NAME, account_id="bcp-pen")]
    _engine(fake_client, {path.read_bytes(): rows})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        lines = _lines_shown(preview)
        assert re.split(r"\s{2,}", lines[2]) == ["2", "2026-09-12", NAME, "6,519.00", "✓", "New"]

    run_app(scenario, size=(120, 40))


@pytest.mark.parametrize("title", BRACKETED)
def test_the_tick_list_shows_a_bracketed_bank_line_title_whole(fake_client, monkeypatch, title):
    """The reconciliation's tick list: the bank line's title as the engine
    holds it, the date before it and the operation and amount after it where
    they were."""
    part = {
        **import_part("t1", -10000, account_id="acc1", line="l1", day="2026-04-11", title=title),
        "statement_id": None,
    }
    line = bank_line_row(
        "l1", [part], net_cents=-10000, operation_code="48201764", account_id="acc1"
    )

    def fetch(cfg, **k):
        return cursor_page([line] if k.get("unreconciled") else [])

    monkeypatch.setattr("expense.reads.fetch_bank_lines", fetch)
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc1": "BCP PEN"}
    )

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(DRAFT))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        lines = render_text(screen._list._build(), width=100).splitlines()
        row = next(ln for ln in lines if "2026-04-11" in ln)
        assert re.split(r"\s{2,}", row.strip()) == [
            "[ ]",
            "2026-04-11",
            title,
            "48201764",
            "-100.00",
        ]

    run_app(scenario)


@pytest.mark.parametrize(("account", "category"), [(NAME, "Comida [/]"), ("[/]", "[bold]x[/bold]")])
def test_the_log_bar_shows_a_bracketed_account_and_category_whole(
    fake_client, monkeypatch, account, category
):
    """The LOG bar's staged row: the account and the category as the engine
    holds them, typed into the bar by those names; the columns around them are
    where they were."""
    _patch_log_bar(monkeypatch)
    accounts = [account_with_currencies(id="acc1", name=account, currencies=[held_currency("PEN")])]
    categories = {"items": [{"id": "cat1", "name": category, "is_system": False}]}
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(accounts))
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: categories)

    async def scenario(pilot, app):
        screen = await _open_log_bar(app, pilot)
        _type(screen, f"almuerzo -20 ${account} @{category} #TAXI")
        screen.on_input_submitted()
        assert len(screen._staged) == 1
        lines = render_text(screen._staged_renderable(), width=160).splitlines()
        row = next(ln for ln in lines if "almuerzo" in ln)
        assert re.split(r"\s{2,}", row.strip())[2:] == [
            "almuerzo",
            "-20.00",
            f"{account} · PEN",
            category,
            "#TAXI",
        ], row

    run_app(scenario)
