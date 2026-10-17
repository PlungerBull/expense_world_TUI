"""The Categories and Hashtags TUI screens.

Screens: docs/mockups/expense-world-pending-hashtag-manage.html — 1 (Hashtags as
a table), 2 A (no `e`, no `d` on a system category), 3 B (the hashtag delete
question). A built-in row is the one with a `system_key`, never a name.
"""

import pytest
from rich.text import Text
from textual.widgets import Static

from expense.tui.screens.categories import CategoriesScreen, category_rows
from expense.tui.screens.create_forms import EditCategoryScreen, EditHashtagScreen
from expense.tui.screens.hashtags import HashtagsScreen, hashtag_rows
from expense.tui.screens.modals import ConfirmModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import render_text, run_app, wait_for, wait_for_list, whole

CATS = [
    {"id": "c1", "name": "Comida", "color": "#d9744a", "is_system": False, "system_key": None},
    {
        "id": "c2",
        "name": "@Opening",
        "color": None,
        "is_system": True,
        "system_key": "opening_balance",
    },
    {"id": "c3", "name": "@Pendiente", "color": None, "is_system": True, "system_key": "pending"},
    {"id": "c4", "name": "SUELDO", "color": None, "is_system": False, "system_key": None},
]
TAGS = [
    {"id": "h1", "name": "trabajo"},
    {"id": "h2", "name": "#casa"},
]
#: Manage ▸ Hashtags in the engine's order, which is not alphabetical: the
#: pending hashtag under a name of its own, and a user hashtag that only shares
#: the reserved name, so the marker can only follow `system_key`.
ENGINE_ORDER_TAGS = [
    {"id": "h-z", "name": "zapatos", "system_key": None},
    {"id": "h-pend", "name": "Por etiquetar", "system_key": "pending"},
    {"id": "h-a", "name": "almuerzo", "system_key": None},
    {"id": "h-like", "name": "Pendiente", "system_key": None},
]


def _footer(screen) -> list[str]:
    """The footer's entries, in order, as `key Description`."""
    return [
        f"{a.binding.key} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


def _card_text(screen) -> str:
    """What the card shows: the list's table (or its empty text), then the
    legend's words."""
    table = render_text(screen.query_one(CursorList)._build(), width=60)
    return table + "\n" + str(screen.query_one(".legend", Static).content)


# ---- pure row builders --------------------------------------------------------


def test_category_rows_swatch_and_system():
    by_id = {r[0]: r for r in category_rows(CATS)}
    _k, cells, style = by_id["c1"]
    assert isinstance(cells[0], Text) and cells[0].style == "#d9744a"
    assert cells[1] == "Comida" and cells[2] == "—" and style == ""
    assert by_id["c2"][1][2] == "system 🔒"  # system marker
    assert by_id["c3"][1][2] == "system 🔒"


def test_categories_legend_is_the_shared_hint():
    """One copy of the system-category rule: the legend is the line under the
    engine's `SYSTEM_CATEGORY` refusal (2 A)."""
    from expense.errors import SYSTEM_HINT

    assert CategoriesScreen.LEGEND is SYSTEM_HINT
    assert SYSTEM_HINT == "System categories cannot be renamed or deleted."


def test_hashtag_rows_name_and_system():
    by_id = {r[0]: r for r in hashtag_rows(TAGS)}
    assert by_id["h1"][1] == ["#trabajo", "—"]  # prefix added
    assert by_id["h2"][1] == ["#casa", "—"]  # no double-hash


def test_hashtag_rows_mark_the_pending_hashtag_by_its_system_key():
    """Screen 1: `system 🔒` on the row with a `system_key`, under whatever name
    it has; `—` on the rest, a user hashtag named `Pendiente` included. The
    engine's order is kept."""
    rows = hashtag_rows(ENGINE_ORDER_TAGS)
    assert [r[0] for r in rows] == ["h-z", "h-pend", "h-a", "h-like"]
    assert [r[1] for r in rows] == [
        ["#zapatos", "—"],
        ["#Por etiquetar", "system 🔒"],
        ["#almuerzo", "—"],
        ["#Pendiente", "—"],
    ]


# ---- the screens --------------------------------------------------------------


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


def _walk_footers(monkeypatch, make, fetch, items, size=(120, 30)) -> dict:
    """Open the list, put the cursor on each row in turn and record the
    footer, under the row's id, and the card, under `card`. On a row whose
    footer lacks `e Edit`, `e` and `d` are pressed too, and must open nothing."""
    monkeypatch.setattr(f"expense.reads.{fetch}", lambda *a, **k: whole(items))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    seen: dict = {}

    async def scenario(pilot, app):
        screen = make()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        seen["card"] = _card_text(screen)
        for item in items:
            listing = screen.query_one(CursorList)
            listing.set_cursor(listing.index_of(item["id"]))
            await pilot.pause()
            seen[item["id"]] = _footer(screen)
            if "e Edit" not in seen[item["id"]]:
                await pilot.press("e", "d")
                await pilot.pause()
                assert app.screen is screen, f"a key opened {app.screen!r} on {item['id']}"

    run_app(scenario, size=size)
    return seen


def test_hashtags_footer_offers_neither_e_nor_d_on_the_pending_hashtag(monkeypatch):
    """Screen 1: on the pending hashtag the footer ends at `n New`, and `e` and
    `d` do nothing; on every other row `e Edit` and `d Delete` close the footer,
    a user hashtag named `Pendiente` included. The table has Name and System
    and the legend, in the engine's order."""
    seen = _walk_footers(monkeypatch, HashtagsScreen, "fetch_hashtags", ENGINE_ORDER_TAGS)
    assert seen["h-pend"][-1] == "n New"
    assert not {"e Edit", "d Delete"} & set(seen["h-pend"])
    for key in ("h-z", "h-a", "h-like"):
        assert seen[key][-3:] == ["n New", "e Edit", "d Delete"], key
    card = seen["card"]
    lines = [line.strip() for line in card.splitlines() if line.strip()]
    assert lines[0].split() == ["Name", "System"]
    rows = [line for line in lines if line.startswith("#")]
    assert [r.split()[0] for r in rows] == ["#zapatos", "#Por", "#almuerzo", "#Pendiente"]
    assert rows[1].endswith("system 🔒") and all(r.endswith("—") for r in rows[::2] + rows[3:])
    assert lines[-1] == "System hashtags cannot be renamed or deleted."


def test_categories_footer_offers_neither_e_nor_d_on_a_system_category(monkeypatch):
    """2 A: on `@Opening` and `@Pendiente` (a `system_key`) neither `e` nor `d`
    is offered and both do nothing; other rows keep `e Edit` and `d Delete`.
    The legend reads as drawn."""
    seen = _walk_footers(monkeypatch, CategoriesScreen, "fetch_categories", CATS)
    for key in ("c2", "c3"):
        assert seen[key][-1] == "n New"
        assert not {"e Edit", "d Delete"} & set(seen[key])
    for key in ("c1", "c4"):
        assert seen[key][-3:] == ["n New", "e Edit", "d Delete"], key
    assert seen["card"].rstrip().endswith("System categories cannot be renamed or deleted.")


def test_a_category_is_system_by_its_key_never_its_name(monkeypatch):
    """A category only named like a built-in one is an ordinary row."""
    named_like = [{"id": "c9", "name": "@Pendiente", "is_system": False, "system_key": None}]
    seen = _walk_footers(monkeypatch, CategoriesScreen, "fetch_categories", named_like)
    assert seen["c9"][-2:] == ["e Edit", "d Delete"]


def test_hashtags_empty_list_still_says_so(monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        screen = HashtagsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert "(no hashtags)" in _card_text(screen)
        assert screen.check_action("edit", ()) is None
        assert screen.check_action("delete", ()) is None

    run_app(scenario)


@pytest.mark.parametrize(
    ("items", "goes_to"),
    [
        (ENGINE_ORDER_TAGS, "#Por etiquetar"),
        ([{"id": "h-a", "name": "almuerzo", "system_key": None}], "the pending hashtag"),
    ],
    ids=["named-as-listed", "none-yet"],
)
def test_the_hashtag_delete_question_says_where_its_rows_go(monkeypatch, items, goes_to):
    """3 B: the question adds that a transaction left with no other hashtag
    goes to the pending hashtag, named as the list gives it, or called the
    pending hashtag while the user has none yet."""
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole(items))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        screen = HashtagsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        listing = screen.query_one(CursorList)
        listing.set_cursor(listing.index_of("h-a"))
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == "Delete this hashtag?"
        assert app.screen._message == (
            "#almuerzo\nIt is also taken off every transaction that carries it; "
            f"one with no other hashtag goes to {goes_to}. No screen can bring it back."
        )
        await pilot.press("n")

    run_app(scenario)
