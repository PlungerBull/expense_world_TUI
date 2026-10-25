"""The hint under a bar form's bar says what `⏎` does on that line.

`⏎` on a line goes on to the next line that can change; only on a line with
none after it does `⏎` save (`FormScreen._advance`). So a hint says "save" only
there (expense-world-wording-picks.html, questions 4a and 4b, both A).

The pins drive the screens with real key presses; the guard walks every bar
form in `expense/tui/screens/`, in each of its shapes, so a new form or a new
hint is covered as soon as it exists.
"""

import importlib
import pkgutil
import re

import pytest
from textual.widgets import Static

import expense.tui.screens as screens_pkg
from expense.tui.screens._form import FormScreen
from expense.tui.screens.create_forms import (
    BarFormScreen,
    EditAccountScreen,
    EditCategoryScreen,
    EditHashtagScreen,
    NewAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from expense.tui.screens.edit_form import BankLineEditFormScreen, EditFormScreen
from expense.tui.screens.reconciliations import NewReconciliationScreen
from expense.tui.screens.setup import SetupScreen
from expense.tui.screens.split import SplitScreen
from tests.unit.helpers import run_app, wait_for

NAME_GOES_ON = "free text · enter to go on"
COLOR_KEEPS = "optional · enter keeps it · ↑↓ another swatch"
CATEGORY_COLOR_SAVES = "optional · enter to save · ↑↓ another swatch"

ACCOUNT = {
    "id": "acc-sue",
    "name": "Sueldo Soles",
    "is_person": False,
    "is_archived": False,
    "currency_code": "PEN",
    "color": "#4a90d9",
    "statement_code": None,
    "current_balance_cents": 0,
    "opening_balance_transaction_id": None,
}
PERSON = {**ACCOUNT, "id": "acc-ana", "name": "Ana", "is_person": True}
CATEGORY = {"id": "cat1", "name": "Mascotas", "color": "#5ab87a", "is_system": False}
TXN = {
    "id": "tx1",
    "date": "2026-06-20T00:00:00Z",
    "title": "Farmacia",
    "amount_cents": -4250,
    "account_id": "acc1",
    "category_id": "cat1",
    "hashtag_ids": ["h1"],
    "description": "receta",
    "statement_line": None,
    "statement_place": None,
}
LINE = {
    "id": "bl1",
    "account_id": "acc1",
    "operation_code": "47391026",
    "part_count": 1,
    "net_cents": -4250,
    "parts": [
        {
            "id": "p1",
            "date": "2026-06-20T00:00:00Z",
            "title": "FARMACIA",
            "amount_cents": 4250,
            "transaction_type": 1,
            "statement_line": None,
            "statement_place": None,
        }
    ],
    "statement_line": None,
    "statement_place": None,
}
SPLIT_LINE = {**LINE, "part_count": 2, "parts": [*LINE["parts"], {**LINE["parts"][0], "id": "p2"}]}


def _hint(screen) -> str:
    return str(screen.query_one("#hint", Static).content)


def _open(screen, body):
    """Push `screen`, wait for its bar, then run `body(pilot, screen)`."""

    async def scenario(pilot, app):
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await pilot.pause()
        return await body(pilot, screen)

    return run_app(scenario)


# ---- the pins: each line the owner's picks name, reached by keys ---------------


def test_new_account_name_goes_on_and_color_keeps_it(fake_client):
    """New: `⏎` keeps bank on TYPE; NAME reads "enter to go on"; past CURRENCY,
    COLOR reads "enter keeps it"."""

    async def body(pilot, screen):
        await pilot.press("enter")  # TYPE keeps bank
        assert screen._key == "name"
        assert _hint(screen) == NAME_GOES_ON
        await pilot.press(*"BCP Oro", "enter")
        assert screen._key == "currency"
        await pilot.press(*"PEN", "enter")
        assert screen._key == "color"
        assert _hint(screen) == COLOR_KEEPS

    _open(NewAccountScreen(), body)


def test_edit_account_name_goes_on_and_color_keeps_it(fake_client):
    """Edit opens on NAME (TYPE is read-only); `⏎` keeps the name and goes on
    past the read-only CURRENCY to COLOR."""

    async def body(pilot, screen):
        assert screen._key == "name"
        assert _hint(screen) == NAME_GOES_ON
        await pilot.press("enter")
        assert screen._key == "color"
        assert _hint(screen) == COLOR_KEEPS

    _open(EditAccountScreen(dict(ACCOUNT)), body)


@pytest.mark.parametrize(
    "make",
    [NewCategoryScreen, lambda: EditCategoryScreen(dict(CATEGORY))],
    ids=["new", "edit"],
)
def test_category_name_goes_on(fake_client, make):
    async def body(pilot, screen):
        assert screen._key == "name"
        assert _hint(screen) == NAME_GOES_ON
        await pilot.press(*"Salud", "enter")
        assert screen._key == "color"  # `⏎` went on, nothing was sent
        assert fake_client.posts == [] and fake_client.puts == []

    _open(make(), body)


def test_new_category_color_saves_and_arrows_move_the_swatch(fake_client):
    """New category: COLOR is the last line, so its hint says `⏎` saves; `↓`
    and `↑` move the highlight between swatches, and `⏎` creates the category
    with the swatch highlighted."""

    async def body(pilot, screen):
        await pilot.press(*"Salud", "enter")
        assert screen._key == "color"
        assert _hint(screen) == CATEGORY_COLOR_SAVES
        assert screen._suggest_idx == -1  # nothing highlighted yet
        await pilot.press("down")
        assert screen._suggest_idx == 0
        await pilot.press("down", "down", "up")
        assert screen._suggest_idx == 1
        assert screen._key == "color"  # the arrows moved the swatch, not the line
        await pilot.press("enter")
        await wait_for(pilot, lambda: fake_client.posts)
        path, payload = fake_client.posts[0]
        assert path == "/categories" and payload["color"] == "#5ab87a"  # green

    _open(NewCategoryScreen(), body)


def test_new_reconciliation_name_goes_on(fake_client):
    async def body(pilot, screen):
        assert screen._key == "name"
        assert _hint(screen) == "e.g. “April 2026” · enter to go on"
        await pilot.press(*"Abril 2026", "enter")
        assert screen._key == "date_start"
        assert fake_client.posts == []

    _open(NewReconciliationScreen(account_id="acc1", account_name="BCP PEN"), body)


# ---- the guard: every bar form, in each of its shapes ------------------------


def _archived(screen: EditFormScreen) -> EditFormScreen:
    """The form as on an archived account's row (`_set_entities` locks these)."""
    screen._locked |= screen._frozen_on_archived()
    return screen


def _opening(screen: EditFormScreen) -> EditFormScreen:
    """The form as on an opening balance (`_set_entities` locks these)."""
    screen._locked |= {"account", "category", "hashtags"}
    return screen


def _with_profile(screen: SetupScreen) -> SetupScreen:
    screen._profile = True  # the engine has no profile for the key: name + zone
    return screen


def _title_open(screen: SplitScreen) -> SplitScreen:
    screen._title_open = True
    return screen


#: Every bar form, each in the shapes that change which line `⏎` saves on.
SHAPES = {
    NewHashtagScreen: lambda: [NewHashtagScreen()],
    EditHashtagScreen: lambda: [EditHashtagScreen({"id": "h1", "name": "dog"})],
    NewCategoryScreen: lambda: [NewCategoryScreen()],
    EditCategoryScreen: lambda: [EditCategoryScreen(dict(CATEGORY))],
    NewAccountScreen: lambda: [NewAccountScreen()],
    EditAccountScreen: lambda: [EditAccountScreen(dict(ACCOUNT)), EditAccountScreen(dict(PERSON))],
    EditFormScreen: lambda: [
        EditFormScreen(record=dict(TXN)),
        _opening(EditFormScreen(record=dict(TXN))),
        _archived(EditFormScreen(record=dict(TXN))),
        _archived(EditFormScreen(record={**TXN, "title": None})),
    ],
    BankLineEditFormScreen: lambda: [
        BankLineEditFormScreen(line=dict(LINE)),
        BankLineEditFormScreen(line=dict(SPLIT_LINE)),
        _archived(BankLineEditFormScreen(line={**LINE, "operation_code": None})),
        _archived(
            BankLineEditFormScreen(
                line={**LINE, "parts": [{**LINE["parts"][0], "title": None}]},
            )
        ),
    ],
    NewReconciliationScreen: lambda: [
        NewReconciliationScreen(),
        NewReconciliationScreen(account_id="acc1", account_name="BCP PEN"),
    ],
    SetupScreen: lambda: [SetupScreen(), _with_profile(SetupScreen())],
    SplitScreen: lambda: [SplitScreen(dict(TXN)), _title_open(SplitScreen(dict(TXN)))],
}

_SAYS_SAVE = re.compile(r"\bsav", re.IGNORECASE)


def _bar_forms() -> set[type]:
    """Every FormScreen subclass the app defines, each module under
    `expense/tui/screens/` imported first so none is missed."""
    for module in pkgutil.iter_modules(screens_pkg.__path__):
        importlib.import_module(f"{screens_pkg.__name__}.{module.name}")
    found: set[type] = set()
    todo = [FormScreen]
    while todo:
        for sub in todo.pop().__subclasses__():
            if sub.__module__.startswith("expense.") and sub not in found:
                found.add(sub)
                todo.append(sub)
    return found


def test_every_bar_form_has_its_shapes_here():
    """A new bar form fails here until it is added to SHAPES, so the guard
    below reads its hints too. BarFormScreen is the base the Manage forms
    share, never pushed itself."""
    assert _bar_forms() - {BarFormScreen} == set(SHAPES)


def _wrong_hints(screens) -> list[str]:
    """Each line of `screens` whose hint says "save" where `⏎` goes on, or
    "go on" where `⏎` saves. A read-only line is skipped: `⏎` only passes it."""
    wrong = []
    for screen in screens:
        name = type(screen).__name__
        for key in screen._sequence():
            if key in screen._locked:
                continue
            goes_on = screen._goes_on(key)
            for hint in {screen._hint_for(key), screen._hint_line(key).plain}:
                if goes_on and _SAYS_SAVE.search(hint):
                    wrong.append(f"{name}.{key}: {hint!r} (⏎ goes on)")
                if not goes_on and "go on" in hint:
                    wrong.append(f"{name}.{key}: {hint!r} (⏎ saves)")
    return wrong


@pytest.mark.parametrize("form", sorted(SHAPES, key=lambda c: c.__name__), ids=lambda c: c.__name__)
def test_no_hint_says_save_where_enter_goes_on(form):
    assert not _wrong_hints(SHAPES[form]())


def test_the_guard_trips_on_a_save_hint_before_the_last_line(monkeypatch):
    """NAME saying "enter to save" again, and COLOR (New's last line) saying
    "enter to go on", are both caught."""
    screen = NewCategoryScreen()
    worded = {"name": "enter to save", "color": "enter to go on"}
    monkeypatch.setattr(screen, "_hint_for", worded.get)
    assert _wrong_hints([screen]) == [
        "NewCategoryScreen.name: 'enter to save' (⏎ goes on)",
        "NewCategoryScreen.color: 'enter to go on' (⏎ saves)",
    ]


def test_title_says_save_only_when_it_is_the_one_line_left():
    """TITLE on an archived account's bank line with its operation set and no
    title: no line after it can change, so `⏎` there saves and the hint says so."""
    line = {**LINE, "parts": [{**LINE["parts"][0], "title": None}]}
    screen = _archived(BankLineEditFormScreen(line=line))
    assert [k for k in screen._sequence() if k not in screen._locked] == ["title"]
    assert screen._hint_for("title") == "free text · enter to save"
    assert EditFormScreen(record=dict(TXN))._hint_for("title") == NAME_GOES_ON
