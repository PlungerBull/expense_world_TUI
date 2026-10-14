"""Smoke tests for the Categories and Hashtags TUI screens."""

from rich.text import Text

from expense.tui.screens.categories import CategoriesScreen, category_rows
from expense.tui.screens.create_forms import EditCategoryScreen, EditHashtagScreen
from expense.tui.screens.hashtags import HashtagsScreen, hashtag_rows
from tests.unit.helpers import run_app, wait_for, wait_for_list

CATS = [
    {"id": "c1", "name": "Comida", "color": "#d9744a", "is_system": False},
    {"id": "c2", "name": "@Opening", "color": None, "is_system": True},
]
TAGS = [
    {"id": "h1", "name": "trabajo"},
    {"id": "h2", "name": "#casa"},
]


def test_category_rows_swatch_and_system():
    by_id = {r[0]: r for r in category_rows(CATS)}
    _k, cells, style = by_id["c1"]
    assert isinstance(cells[0], Text) and cells[0].style == "#d9744a"
    assert cells[1] == "Comida" and cells[2] == "—" and style == ""
    assert by_id["c2"][1][2] == "system 🔒"  # system marker


def test_categories_legend_is_the_shared_delete_hint():
    """One copy of the system-category rule: the legend is the shared hint."""
    from expense.formatting import SYSTEM_HINT

    assert CategoriesScreen.LEGEND is SYSTEM_HINT
    assert SYSTEM_HINT == "System categories can be renamed but not deleted."


def test_hashtag_rows_hash_prefix():
    by_id = {r[0]: r for r in hashtag_rows(TAGS)}
    assert by_id["h1"][1][0] == "#trabajo"  # prefix added
    assert by_id["h2"][1][0] == "#casa"  # no double-hash


def _run_list_screen(monkeypatch, screen_cls, fetch_mod, fetch_name, items, edit_cls):
    monkeypatch.setattr(fetch_mod, fetch_name, lambda *a, **k: {"items": items})
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(screen_cls())
        await wait_for_list(pilot, app)
        await pilot.press("e")  # edit the cursor row — no detail hop
        await wait_for(pilot, lambda: isinstance(app.screen, edit_cls))

    run_app(scenario)


def test_categories_screen_lists_and_edits(monkeypatch):
    import expense.reads as cc

    _run_list_screen(
        monkeypatch, CategoriesScreen, cc, "fetch_categories", CATS, EditCategoryScreen
    )


def test_hashtags_screen_lists_and_edits(monkeypatch):
    import expense.reads as hc

    _run_list_screen(monkeypatch, HashtagsScreen, hc, "fetch_hashtags", TAGS, EditHashtagScreen)
