"""A list screen's footer tightens its spacing, then leaves whole keys out from its end,
so no key is drawn cut; a key left out still works and the `?` card lists it."""

import pytest

from expense.reads import AccountIndex
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.screens.help import screen_inventory
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.transactions import TransactionsScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    bank_line_row,
    fake_ledger,
    import_part,
    run_app,
    screen_lines,
    wait_for,
    wait_for_list,
    whole,
)

ROWS = [
    {
        "id": f"t{i}",
        "title": f"Row {i}",
        "description": None,
        "amount_cents": -100 * (i + 1),
        "date": "2026-03-05T00:00:00Z",
        "account_id": "acc1",
        "currency_code": "PEN",
        "category_id": None,
        "hashtag_ids": [],
        "bank_line_id": f"bl{i}",
        "line_code": f"#{i:06}",
        "statement_line": None,
        "statement_place": None,
    }
    for i in range(200)
]


def _footer(app) -> str:
    return next(line for line in reversed(screen_lines(app)) if line.strip())


def _stub_ledger(monkeypatch) -> None:
    import expense.tui.screens.transactions as tx_mod

    fake_ledger(monkeypatch, ROWS)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex({"acc1": "BCP"}))
    for name in ("load_category_name_map", "load_hashtag_name_map"):
        monkeypatch.setattr(tx_mod, name, lambda: {})
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())


def _ledger_footers(monkeypatch, *, size=(140, 24), then=None):
    """The ledger's footer on page 1 and on page 2, and what `then(pilot, app, screen)`
    returns on page 2."""
    _stub_ledger(monkeypatch)

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        screen.query_one(CursorList).focus()
        await wait_for(pilot, lambda: "pgdn" in _footer(app))
        first = _footer(app)
        for _ in range(6):  # until the cursor leaves page 1
            await pilot.press("pagedown")
            await pilot.pause()
            if "pgup Prev" in _footer(app):
                break
        await wait_for(pilot, lambda: "pgup Prev" in _footer(app))
        second = _footer(app)
        return first, second, (await then(pilot, app, screen) if then else None)

    return run_app(scenario, size=size)


# Page 2's keys, tightened, are 144 wide with `d Delete` and 135 without it; spaced, 160.
# Page 1's, tightened, are 134 wide; spaced, 149 (the line drawn is one column less).
@pytest.mark.parametrize(
    ("width", "ends", "line"),
    [(144, "d Delete", 144), (143, "s Edit", 135), (160, "d Delete", 159), (159, "d Delete", 144)],
)
def test_the_ledger_on_page_2_fits_to_the_column(monkeypatch, width, ends, line):
    _first, second, _ = _ledger_footers(monkeypatch, size=(width, 24))
    assert second.endswith(ends)
    assert len(second) == line <= width
    assert second.startswith(" ⏎ Open  space") == (width >= 160)  # spaced only from 160


@pytest.mark.parametrize(("width", "line"), [(149, 148), (148, 134)])
def test_the_ledger_on_page_1_goes_from_spaced_to_tightened_at_the_edge(monkeypatch, width, line):
    first, _second, _ = _ledger_footers(monkeypatch, size=(width, 24))
    assert first.endswith("d Delete") and len(first) == line
    assert first.startswith(" ⏎ Open  space") == (width == 149)


def test_a_key_left_out_of_the_footer_is_still_on_the_help_card(monkeypatch):
    async def card(pilot, app, screen):
        return [(row.keys, row.description) for row in _own_rows(screen)]

    def _own_rows(screen):
        _, groups = screen_inventory(screen)
        return next(g for g in groups if g.title == "This screen").rows

    _first, second, rows = _ledger_footers(monkeypatch, then=card)
    assert "d Delete" not in second
    assert ("d", "Delete") in rows


def test_a_key_left_out_of_the_footer_still_works(monkeypatch):
    def one_part_line(_cfg, line, **_kw):
        row = next(r for r in ROWS if r["bank_line_id"] == line)
        part = import_part(
            row["id"], row["amount_cents"], account_id="acc1", line=line, title=row["title"]
        )
        return bank_line_row(line, [part], net_cents=row["amount_cents"], account_id="acc1")

    monkeypatch.setattr("expense.reads.fetch_bank_line", one_part_line)

    async def press_d(pilot, app, screen):
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        return app.screen._title

    _first, second, title = _ledger_footers(monkeypatch, then=press_d)
    assert "d Delete" not in second
    assert title == "Delete this transaction?"


def _tags(count: int) -> list[dict]:
    return [{"id": f"h{i}", "name": f"tag{i:02}", "system_key": None} for i in range(count)]


def test_manage_on_page_2_at_80_is_tightened_and_loses_no_key(monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole(_tags(40)))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(HashtagsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("pagedown")
        await wait_for(pilot, lambda: "pgup Prev" in _footer(app))
        await pilot.pause()
        return _footer(app)

    footer = run_app(scenario, size=(80, 24))
    assert footer.strip() == (
        "⏎ Open pgdn Next pgup Prev esc Back r Refresh ? Keys n New e Edit d Delete"
    )
