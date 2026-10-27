"""Every list shows a name or a title as the engine holds it, `[` and all.

A plain cell is words, never content markup: `BCP [like this]` keeps its
brackets, and a `[/]` or a lone `[` neither vanishes nor breaks the list. The
app's own styled cells (`Text`: a swatch, a coloured amount, a mark) keep their
styling. Pinned where the owner meets it: Manage ▸ Accounts, the ledger and the
bank import's preview (mockup expense-world-bracketed-names.html).
"""

import re

import pytest
from rich.text import Text

import expense.tui.screens.transactions as tx_mod
from expense.reads import AccountIndex
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.transactions import TransactionsScreen
from expense.tui.widgets.cells import swatch
from expense.tui.widgets.cursor_list import CursorList, list_table
from tests.unit.helpers import (
    fake_ledger,
    import_row,
    render_text,
    run_app,
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
from tests.unit.test_tui_transactions import ITEMS as LEDGER_ITEMS

NAME = "BCP [like this]"


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
