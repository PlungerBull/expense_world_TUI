"""Guard: a toast shows the engine's words as text, never as styling.

Textual reads a toast's message as content markup unless the call says
`markup=False`, so a `[like this]` in the engine's words would vanish, read as
a style, and a stray `[/]` would raise. Every `notify` in the app's code is
therefore one of two things:

* a **fixed sentence**: its message is a string literal, or a choice between
  two (`"Saved." if done else "Not saved."`), written in the app and read by
  whoever writes it; or
* a call that **says how its message reads**, passing `markup=` itself:
  `toast` in expense/tui/widgets/refusal.py passes `markup=False`, and the one
  toast whose colours are content markup on purpose (the ledger's bulk edit
  note, its words escaped inside it) passes `markup=True`.

Anything else — a variable, `format_error(...)`, an f-string, a constant
from elsewhere — fails here and goes through `toast`. So does `notify`
handed on uncalled (`call_while_attached(self, self.notify, ...)`), since the
call it makes cannot be read here.

What this cannot catch:

* a `markup=True` call whose words are not escaped: the guard trusts the
  caller who says it;
* `notify` reached under another name (`getattr(self, "notify")`), or a
  `Notification` built by hand;
* engine words drawn anywhere but a toast — a `Static("…")`, `.update("…")`,
  `Label`, an `Option` prompt, `Content.from_markup`, `Text.from_markup`. Those
  are held by the per-screen tests in test_tui_engine_words.py, and by the
  rule in docs/tui.md "When the engine says no" that they draw `Text`.

The guard reads the code; the tests at the end of this file drive the app. Each
toast that shows the owner's own words (an account, a category, a hashtag or a
pick that matches nothing, and System ▸ Config's save that failed) is met with
`[like this]` typed or supplied, and finds it whole in the toast as drawn
(`run_app(..., toasts=True)`, `toasts_shown`): content markup would read it as
a style and drop it.
"""

import ast
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import Input

from expense.tui.screens.bulk_pick import BulkPickScreen
from expense.tui.screens.edit_form import EditFormScreen
from expense.tui.screens.reconciliations import NewReconciliationScreen
from expense.tui.screens.system import ConfigScreen
from tests.unit.helpers import run_app, toasts_shown, wait_for, whole
from tests.unit.test_tui_edit_form import TXN
from tests.unit.test_tui_edit_form import _enter_to as _enter_to_edit
from tests.unit.test_tui_edit_form import _patch as _patch_edit
from tests.unit.test_tui_edit_form import _wait_loaded as _wait_edit_loaded
from tests.unit.test_tui_system import CFG

PACKAGE = Path(__file__).resolve().parents[2] / "expense"


def _fixed(node: ast.expr | None) -> bool:
    """A string literal, or a choice between fixed sentences."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.IfExp):
        return _fixed(node.body) and _fixed(node.orelse)
    return False


def _message(call: ast.Call) -> ast.expr | None:
    if call.args:
        return call.args[0]
    return next((k.value for k in call.keywords if k.arg == "message"), None)


def markup_toasts(source: str, name: str) -> list[str]:
    """Each `notify` in `source` that may read words as markup, as
    `name:line: code`."""
    tree = ast.parse(source)
    called: set[int] = set()
    found: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "notify"
        ):
            called.add(id(node.func))
            says = any(k.arg == "markup" for k in node.keywords)
            if not says and not _fixed(_message(node)):
                found.append(f"{name}:{node.lineno}: {ast.unparse(node)}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "notify" and id(node) not in called:
            found.append(f"{name}:{node.lineno}: {ast.unparse(node)} handed on uncalled")
    return sorted(found)


def test_the_reader_tells_a_fixed_sentence_from_words_it_did_not_write():
    """The guard is only as good as this reader: each spelling lands on the
    side it belongs to."""
    safe = """
self.notify("Saved.")
self.notify("Saved." if left else "Not saved.", severity="error")
self.app.notify(message="Connected.")
toast(self, format_error(exc), title="Failed", severity="error")
host.notify(message, markup=False, **options)
self.notify(note, title=head, markup=True)
call_while_attached(self, toast, self, format_error(exc))
"""
    assert markup_toasts(safe, "safe.py") == []
    unsafe = """
self.notify(format_error(exc), title="Failed", severity="error")
self.notify(message)
self.app.notify(f"Not saved:\\n{message}")
self.notify(DATE_UNREADABLE, severity="error")
self.notify("Saved." if left else message)
self._host.notify(message=words)
call_while_attached(self, self.notify, format_error(exc), severity="error")
"""
    found = markup_toasts(unsafe, "unsafe.py")
    assert [line.split(":")[1] for line in found] == ["2", "3", "4", "5", "6", "7", "8"]
    assert found[-1].endswith("handed on uncalled")


def test_no_toast_reads_words_it_did_not_write_as_markup():
    found = [
        problem
        for path in sorted(PACKAGE.rglob("*.py"))
        for problem in markup_toasts(
            path.read_text(encoding="utf-8"), str(path.relative_to(PACKAGE.parent))
        )
    ]
    assert found == [], (
        "These toasts read their message as content markup, so a `[` in words the "
        "app did not write would vanish or raise. Send them through `toast` "
        "(expense/tui/widgets/refusal.py):\n" + "\n".join(found)
    )


# ---- the owner's own words, as the toast draws them ----------------------------

#: What the owner types: brackets content markup reads as a style and drops.
TYPED = "[like this]"


async def _toast_holding(pilot, app, words: str) -> str:
    """The first toast that shows `words`, as drawn; fails when none does."""
    await wait_for(
        pilot,
        lambda: any(words in shown for shown in toasts_shown(app)),
        message=f"no toast shows {words!r} whole: {toasts_shown(app)!r}",
    )
    return next(shown for shown in toasts_shown(app) if words in shown)


def test_an_account_no_name_matches_on_a_new_reconciliation_shows_it_whole(
    fake_client, monkeypatch
):
    """The new reconciliation form's account line, `[like this]` typed and
    matching no account: `No account matches “[like this]”.`"""
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole(
            [{"id": "acc1", "name": "BCP PEN", "currency_code": "PEN", "is_person": False}]
        ),
    )

    async def scenario(pilot, app):
        screen = NewReconciliationScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._accounts, message="the accounts never loaded")
        await pilot.press(*"Octubre", "enter")
        await wait_for(pilot, lambda: screen._key == "account")
        await pilot.press(*TYPED, "enter")
        shown = await _toast_holding(pilot, app, TYPED)
        assert shown == f"No account matches “{TYPED}”."
        assert screen._key == "account"

    run_app(scenario, toasts=True)


def test_an_account_no_name_matches_on_the_edit_form_shows_it_whole(fake_client, monkeypatch):
    """The Edit form's account line, `[like this]` typed and matching no
    account: `No account matches “[like this]”.`"""
    _patch_edit(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN)
        await app.push_screen(screen)
        await _wait_edit_loaded(screen, pilot)
        await _enter_to_edit(screen, pilot, "account")
        await pilot.press(*TYPED, "enter")
        shown = await _toast_holding(pilot, app, TYPED)
        assert shown == f"No account matches “{TYPED}”."
        assert screen._key == "account"

    run_app(scenario, toasts=True)


def test_a_pick_nothing_matches_shows_it_whole():
    """The bulk edit's pick screen, one pick, `[like this]` typed and matching
    nothing: `Nothing matches “[like this]”.`, and the screen stays."""

    async def scenario(pilot, app):
        results: list = []
        modal = BulkPickScreen("category", 1, [("a", "HOGAR"), ("b", "KORAKUEN")], rows=Text(""))
        app.push_screen(modal, results.append)
        await wait_for(pilot, lambda: app.screen is modal)
        await pilot.press(*TYPED)
        await wait_for(pilot, lambda: modal._pool == [])
        await pilot.press("enter")
        shown = await _toast_holding(pilot, app, TYPED)
        assert shown == f"Nothing matches “{TYPED}”."
        assert app.screen is modal and results == []

    run_app(scenario, toasts=True)


@pytest.mark.parametrize("field", ["category", "hashtag"])
def test_a_part_s_name_no_name_matches_on_the_edit_form_shows_it_whole(
    fake_client, monkeypatch, field
):
    """The Edit form's part line, CATEGORY or HASHTAGS, `[like this]` typed and
    matching no name: `No category matches “[like this]”.`, or `No hashtag
    matches …`, and the line stays."""
    _patch_edit(monkeypatch)
    key = "0.category" if field == "category" else "0.hashtags"

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN)
        await app.push_screen(screen)
        await _wait_edit_loaded(screen, pilot)
        await _enter_to_edit(screen, pilot, key)
        await pilot.press(*TYPED, "enter")
        shown = await _toast_holding(pilot, app, TYPED)
        assert shown == f"No {field} matches “{TYPED}”."
        assert screen._key == key

    run_app(scenario, toasts=True)


def test_a_hashtag_no_name_matches_on_the_pick_screen_shows_it_whole():
    """The bulk edit's pick screen for hashtags, `[like this]` typed and
    matching none: `No hashtag matches “[like this]”.`, nothing picked, and
    the screen stays."""

    async def scenario(pilot, app):
        results: list = []
        modal = BulkPickScreen("hashtags", 2, [("h1", "COMIDA")], rows=Text(""))
        app.push_screen(modal, results.append)
        await wait_for(pilot, lambda: app.screen is modal)
        await pilot.press(*TYPED)
        await wait_for(pilot, lambda: modal._pool == [])
        await pilot.press("enter")
        shown = await _toast_holding(pilot, app, TYPED)
        assert shown == f"No hashtag matches “{TYPED}”."
        assert app.screen is modal and results == [] and modal._picked == []

    run_app(scenario, toasts=True)


async def _open_config(pilot, app) -> ConfigScreen:
    screen = ConfigScreen()
    await app.push_screen(screen)
    await wait_for(pilot, lambda: screen._cfg is not None, message="the config never loaded")
    return screen


async def _type_engine_url(pilot, app, typed: str) -> None:
    """`e`, the box's words cleared, `typed`, `⏎`."""
    await pilot.press("e")
    await wait_for(pilot, lambda: bool(app.screen.query(Input)))
    app.screen.query_one(Input).value = ""
    await pilot.press(*typed, "enter")


def test_a_config_that_cannot_be_saved_shows_its_words_whole(tmp_path, monkeypatch):
    """System ▸ Config, a new URL typed, the settings file's folder
    `[like this]` a file, so the save cannot write it: the toast titled
    `Couldn't save` shows the system's words whole, `[Errno 17]` and the path
    with `[like this]` in it."""
    blocker = tmp_path / TYPED
    blocker.write_text("")
    monkeypatch.setenv("EXPENSE_CONFIG", str(blocker / "expense-config"))
    monkeypatch.setattr("expense.config.load", lambda: CFG)

    async def scenario(pilot, app):
        await _open_config(pilot, app)
        await _type_engine_url(pilot, app, "https://new.example")
        shown = await _toast_holding(pilot, app, str(blocker))
        assert shown == f"Couldn't save\n[Errno 17] File exists: '{blocker}'"

    run_app(scenario, toasts=True)
