"""The `?` key card, and no command palette.

The card is *derived* from BINDINGS rather than hand-listed, so the
tests that matter here are the ones that fail when the derivation drifts:

  · every binding we declare has text for the card to show (the guard)
  · Textual's own widget keys stay out, without a suppression list
  · a key the screen cannot actually service is not advertised
  · the palette is off, and the footer does not offer it
"""

import importlib
import pkgutil
import re

import pytest
from rich.text import Text
from textual.actions import parse as parse_action
from textual.binding import Binding

import expense.tui as tui_pkg
from expense.reads import AccountIndex
from expense.tui.screens._form import form_bindings
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.categories import CategoriesScreen
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.screens.help import (
    FOLD_INTO,
    NEEDS_SCREEN_HANDLER,
    HelpModal,
    declared_bindings,
    key_rows,
    listed_bindings,
    render_card,
    screen_inventory,
    scroll_window,
)
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.statements import _AccountList, _PanelList
from expense.tui.screens.transactions import LedgerFilter, TransactionsScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_ORDER_HOLDING_ACCOUNTS,
    assert_card_gutters_blank,
    fake_ledger,
    render_text,
    run_app,
    screen_lines,
    wait_for,
    wait_for_list,
    wait_for_loaded,
    whole,
)

LEDGER_ROW = {
    "id": "t-1",
    "title": "Pago tarjeta",
    "description": None,
    "amount_cents": -20000,
    "date": "2024-03-28T05:00:00Z",
    "day": "2024-03-28",
    "account_id": "sig-pen",
    "currency_code": "PEN",
    "category_id": None,
    "hashtag_ids": [],
    "bank_line_id": "bl-1",
    "line_code": "L1",
    "statement_line": None,
    "statement_place": None,
    "statement_id": None,
}


def _stub_engine(monkeypatch, items=ENGINE_ORDER_HOLDING_ACCOUNTS, rows=(LEDGER_ROW,)):
    """A ledger and an account list with a row each, unless the test passes none: the
    ledger's and Manage's list keys leave the card while the list is empty (the account
    list is stubbed by `items`, the ledger by `rows`)."""
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda cfg, **k: {"items": list(items)})
    fake_ledger(monkeypatch, list(rows))
    monkeypatch.setattr(
        "expense.tui.screens.transactions.load_account_index", lambda: AccountIndex({})
    )
    for name in ("load_category_name_map", "load_hashtag_name_map"):
        monkeypatch.setattr(f"expense.tui.screens.transactions.{name}", lambda: {})


def _card_text(groups) -> str:
    return render_text(render_card(groups, "#000000"), width=66)


def _titles(groups) -> list[str]:
    return [group.title for group in groups]


def _rows(groups, title):
    return next(group.rows for group in groups if group.title == title)


# ---------------------------------------------------------------------------
# the guard: nothing we declare may be undocumented
# ---------------------------------------------------------------------------


def _declaring_classes():
    """Every class under expense.tui that declares BINDINGS in its own body."""
    for info in pkgutil.walk_packages(tui_pkg.__path__, f"{tui_pkg.__name__}."):
        module = importlib.import_module(info.name)
        for obj in vars(module).values():
            if not isinstance(obj, type) or obj.__module__ != module.__name__:
                continue
            if "BINDINGS" in obj.__dict__:
                yield obj


def test_every_declared_binding_has_help_text():
    """The card can only show what the binding carries.

    A binding added with no description and no tooltip renders as a row with a
    blank right-hand side — exactly the defect that makes Textual's own panel
    hard to read (a bare `↑ k` row). Folded inverses are
    the one exception: they are absorbed into their partner's row.
    """
    undocumented = []
    for klass in _declaring_classes():
        for item in klass.__dict__["BINDINGS"]:
            for binding in Binding.make_bindings([item]):
                if binding.action in FOLD_INTO:
                    # a folded inverse renders as `(k / ↑ up)`: it needs its word too
                    if not binding.description:
                        undocumented.append(f"{klass.__name__}: {binding.key} has no word")
                    continue
                if not (binding.tooltip or binding.description):
                    undocumented.append(f"{klass.__name__}: {binding.key} → {binding.action}")
    assert not undocumented, f"bindings with nothing for the ? card to show: {undocumented}"


def _all_declared_bindings():
    for klass in _declaring_classes():
        for item in klass.__dict__["BINDINGS"]:
            for binding in Binding.make_bindings([item]):
                yield klass, binding


def test_no_duplicate_movement_key_aliases():
    """`j k h l , .` are gone, and may not come back.

    Every one was a second name for a key already bound and already in the
    footer — `j/k` for `↓/↑`, `h/l` for `←/→`, `,/.` for `pgup/pgdn` — so
    deleting them cost no capability at all.

    Guarding it is about the letters, not the tidiness: `j k h l` are usable as
    *command* letters on a list screen only while no widget claims them first.
    A stray alias would silently eat a future binding — which is exactly how the
    pile accumulated the first time.

    So the guard bans the letters on **widgets** (the layer that would eat them)
    and bans them as *movement* actions anywhere. A screen command is what the
    deletion freed the letters for: `h` is `hashtags` on the ledger, and that is
    allowed.
    """
    from textual.screen import Screen

    banned = {"j", "k", "h", "l", "comma", "full_stop"}
    movement = ("move", "page", "cursor", "scroll", "expand", "collapse", "suggest")
    offenders = [
        f"{klass.__name__}: {b.key} → {b.action}"
        for klass, b in _all_declared_bindings()
        if b.key in banned and (not issubclass(klass, Screen) or b.action.startswith(movement))
    ]
    assert not offenders, f"duplicate movement aliases are deleted, not re-added: {offenders}"


def test_square_brackets_are_not_bound_anywhere():
    """The month window rides `pgdn`/`pgup`.

    `[`/`]` were the app's only one-screen, one-job keys, and they existed only
    because the Monthly grid had already spent `←`/`→` on expand/collapse. The
    page keys already meant "the next window of data"; a month slide is that same
    idea with months instead of rows.
    """
    offenders = [
        f"{klass.__name__}: {b.key}"
        for klass, b in _all_declared_bindings()
        if b.key in {"left_square_bracket", "right_square_bracket"}
    ]
    assert not offenders, f"square brackets were retired: {offenders}"


# ---------------------------------------------------------------------------
# derivation
# ---------------------------------------------------------------------------


def test_declared_bindings_keeps_only_our_own_and_folds_the_inverse():
    """Textual's OptionList contributes home/end/tab/left/right/ctrl+c to a
    CursorList at runtime. None are ours to document, and none may appear —
    achieved by walking the MRO for *declaring* classes, not by a suppression
    list that would rot as Textual changes. `up` is `show=False` and rides along
    on the down row instead of becoming a blank-description row."""
    keys = {binding.key for binding in declared_bindings(CursorList)}
    assert keys == {"down", "up", "enter", "space", "pagedown", "pageup"}
    for intruder in ("home", "end", "tab", "shift+tab", "left", "right", "ctrl+c"):
        assert intruder not in keys
    rows = key_rows(declared_bindings(CursorList))
    assert not any(row.description == "Up" for row in rows)
    down = next(row for row in rows if row.description == "Down")
    assert down.note == "(↑ up)"


def test_rows_join_keys_typed_character_first():
    """`n / esc / ⏎`, not the reverse: the letter is what you actually press.

    ConfirmModal is the binding set that mixes printable and unprintable keys."""
    rows = {row.description: row.keys for row in key_rows(declared_bindings(ConfirmModal))}
    assert rows["No"] == "n / esc / ⏎"
    assert rows["Yes"] == "y"


# ---------------------------------------------------------------------------
# the assembled card
# ---------------------------------------------------------------------------


def test_accounts_card_matches_the_approved_layout(monkeypatch):
    """Variant C: four blocks, screen keys and conventions left, list keys and
    app-wide keys right."""
    _stub_engine(monkeypatch)

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_loaded(pilot, app)
        await pilot.pause()
        title, groups = screen_inventory(app.screen)

        assert title == "Keys — Accounts"
        assert _titles(groups) == [
            "This screen",
            "Moving around",
            "Always true",
            "Everywhere",
        ]
        assert [row.description for row in _rows(groups, "This screen")] == [
            "New",
            "Edit",
            "Add a currency",
            "Remove a currency",
            "Archive / unarchive",
            "Make person",
            "Make bank",
            "Delete",
            "Refresh",
            "Back",
        ]
        text = _card_text(groups)
        # the two columns' second blocks start on the same line
        lines = text.split("\n")
        conventions = next(i for i, line in enumerate(lines) if "Always true" in line)
        assert "Everywhere" in lines[conventions]
        # nothing overflows the 66-column card
        assert max(len(line) for line in lines) <= 66
        # `⏎` is a no-op on the Manage lists (no screen there handles the selection), so the
        # card does not list it as "Open", and says what it does everywhere
        assert not any(r.description == "Open" for r in _rows(groups, "Moving around"))
        assert ("⏎", "never changes data, except on a currency pick") in [
            (row.keys, row.description) for row in _rows(groups, "Always true")
        ]

    run_app(scenario, size=(100, 32))


def test_home_card_names_itself_without_a_crumb():
    """Home paints its own header and has no crumb, so the title falls back to
    the class name rather than rendering a bare `Keys`."""

    async def scenario(pilot, app):
        await pilot.pause()
        title, groups = screen_inventory(app.screen)
        assert title == "Keys — Home"
        # `+` sits with `q`: `Log a transaction` is not a menu row, so the card
        # is the only place the key is written down in full, and this assertion
        # is what keeps it discoverable. `r` re-reads the month.
        assert [row.keys for row in _rows(groups, "This screen")] == [
            "+",
            "pgdn",
            "pgup",
            "→",
            "←",
            "q",
            "r",
        ]

    run_app(scenario)


def test_question_mark_opens_and_closes_the_card(monkeypatch):
    """`?` is a peek: the key that opens it closes it, and so does esc."""
    _stub_engine(monkeypatch)

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_loaded(pilot, app)
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: isinstance(app.screen, HelpModal))
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: not isinstance(app.screen, HelpModal))
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: isinstance(app.screen, HelpModal))
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, HelpModal))

    run_app(scenario, size=(100, 32))


def test_question_mark_types_a_character_inside_a_form(monkeypatch):
    """Forms keep `?` as a typed character. A focused Input
    swallows printable keys, so no overlay opens and the note field gets its
    question mark — the behaviour we want, pinned so a later app-level binding
    cannot quietly take the key away."""
    _stub_engine(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda cfg, **k: {"items": []})
    monkeypatch.setattr("expense.reads.fetch_categories", lambda cfg, **k: {"items": []})
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda cfg, **k: {"items": []})

    async def scenario(pilot, app):
        from textual.widgets import Input

        from expense.tui.screens.create_forms import NewHashtagScreen

        await app.push_screen(NewHashtagScreen())
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)
        assert "?" in app.screen.query_one("#bar", Input).value

    run_app(scenario, size=(100, 32))


# ---------------------------------------------------------------------------
# the palette is gone
# ---------------------------------------------------------------------------


def test_footer_no_longer_offers_the_palette(monkeypatch):
    _stub_engine(monkeypatch)

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_loaded(pilot, app)
        await pilot.pause()
        from textual.widgets import Footer

        footer = app.screen.query_one(Footer)
        assert not footer.query(".-command-palette")

    run_app(scenario, size=(100, 32))


# ---------------------------------------------------------------------------
# the bar-form footer
# ---------------------------------------------------------------------------


def test_form_navigation_keys_are_not_advertised():
    """The form footer offers `esc Cancel`, `^s Save` and `⇥ Field` — nothing else.

    `⇥ Field` is the form's one navigation slot: tab moves fields on every
    field, and forms have no `?` card that could list the rest. `shift+tab`
    is its mirror. Plain `↑` / `↓` walk the suggestion list (or move fields
    without one) — plain-arrow navigation the list, tree and checklist widgets
    do not advertise either. `^↑` / `^↓` are bound but never advertised: macOS
    takes `⌃↑` for Mission Control and `⌃↓` for Application Windows before the
    terminal sees them. This guard is what fails if someone re-adds one as a
    plain tuple, which defaults to shown.
    """
    bindings = [
        binding for item in form_bindings("Save") for binding in Binding.make_bindings([item])
    ]
    by_key = {binding.key: binding for binding in bindings}

    assert {key for key, b in by_key.items() if b.show} == {"escape", "ctrl+s", "tab"}
    assert (by_key["tab"].description, by_key["tab"].key_display) == ("Field", "⇥")
    for key in ("shift+tab", "up", "down", "ctrl+up", "ctrl+down"):
        assert by_key[key].show is False, f"{key} is advertised in the form footer"
        # the card guard above still applies: hidden or not, a binding we
        # declare carries text.
        assert by_key[key].description


def test_every_bar_form_takes_the_form_keymap_not_textuals_focus_cycling():
    """FormScreen drops Textual's Screen bindings (`inherit_bindings=False`);
    every subclass still merges FormScreen's keymap, so `tab` moves fields
    everywhere and Screen's hidden copy key survives. Walks every FormScreen
    subclass, so a new form is covered without being listed here."""
    import expense.tui.screens.create_forms  # noqa: F401 — registers subclasses
    import expense.tui.screens.edit_form  # noqa: F401
    import expense.tui.screens.statements  # noqa: F401
    from expense.tui.screens._form import FormScreen

    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    forms = set(walk(FormScreen))
    assert len(forms) >= 8, sorted(c.__name__ for c in forms)
    for cls in forms:
        merged = cls._merged_bindings.key_to_bindings
        for key in ("escape", "ctrl+s", "tab", "shift+tab", "up", "down", "ctrl+c"):
            assert key in merged, f"{cls.__name__} lost {key}"
        assert merged["tab"][0].action == "field(1)", cls.__name__
        assert merged["shift+tab"][0].action == "field(-1)", cls.__name__
        assert merged["ctrl+c"][0].action == "screen.copy_text", cls.__name__


# ---------------------------------------------------------------------------
# the title: a screen's own words, never a class name that says "reconciliation"
# ---------------------------------------------------------------------------


def test_the_help_title_on_a_statements_own_screen_says_statements():
    from expense.tui.screens.statements import StatementScreen

    screen = StatementScreen({"id": "r1", "name": "Octubre BCP"})
    title, _ = screen_inventory(screen)
    assert title == "Keys — Octubre BCP"
    assert "reconcil" not in title.lower()


def test_the_card_lists_space_on_a_draft_statement_and_not_on_a_read_only_one(
    fake_client, monkeypatch
):
    """`space` is the statement list's own toggle (its screen handles `CheckList.Toggled`):
    a draft's card lists it, a completed statement's and one waiting for its PDF do not,
    nor `c`."""
    from expense.tui.screens.statements import StatementScreen
    from tests.unit.test_tui_statement_screen import (
        AGOSTO,
        NOVIEMBRE,
        OCTUBRE,
        VIS_AGOSTO,
        _engine,
    )

    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)

    def card(statement, code):
        async def scenario(pilot, app):
            screen = StatementScreen(dict(statement), statement_code=code)
            await app.push_screen(screen)
            await wait_for(pilot, lambda: screen._list is not None)
            await pilot.pause()
            _, groups = screen_inventory(screen)
            return {row.keys for group in groups for row in group.rows}

        return run_app(scenario, size=(80, 26))

    assert {"space", "c"} <= card(OCTUBRE, None)
    for statement, code in ((VIS_AGOSTO, "VIS"), (NOVIEMBRE, "VIS")):
        keys = card(statement, code)
        assert "space" not in keys and "c" not in keys


# ---------------------------------------------------------------------------
# a card taller than the screen scrolls
# ---------------------------------------------------------------------------


def _marks(lines):
    """`(lines above, lines below)` the scroll markers on the screen state, None for a
    marker that is not drawn."""
    text = "\n".join(lines)
    up = re.search(r"▲ (\d+) lines? above · ↑ scrolls", text)
    down = re.search(r"▼ (\d+) more lines? · ↓ scrolls", text)
    return (int(up[1]) if up else None, int(down[1]) if down else None)


def _ledger_card(monkeypatch, size, body):
    """Open the ledger's `?` card at `size` and run `body(pilot, app)` on it."""
    _stub_engine(monkeypatch)

    async def scenario(pilot, app):
        await app.push_screen(TransactionsScreen())
        await wait_for_loaded(pilot, app)
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: isinstance(app.screen, HelpModal))
        await pilot.pause()
        await body(pilot, app)

    run_app(scenario, size=size)


def test_scroll_window_counts_what_is_hidden_exactly():
    lines = [Text(f"l{i}") for i in range(30)]
    rows, offset = scroll_window(lines, 0, 10)
    assert [r.plain for r in rows][-1] == " ▼ 21 more lines · ↓ scrolls"
    assert len(rows) == 10 and offset == 0
    rows, _ = scroll_window(lines, 5, 10)
    assert rows[0].plain == " ▲ 5 lines above · ↑ scrolls"
    assert rows[-1].plain == " ▼ 17 more lines · ↓ scrolls"
    assert len(rows) == 10
    rows, offset = scroll_window(lines, 99, 10)
    assert offset == 21 and rows[0].plain == " ▲ 21 lines above · ↑ scrolls"
    assert rows[-1].plain == "l29" and len(rows) == 10
    rows, _ = scroll_window(lines, 1, 10)
    assert rows[0].plain == " ▲ 1 line above · ↑ scrolls"
    fits, _ = scroll_window(lines[:10], 0, 10)
    assert [r.plain for r in fits] == [f"l{i}" for i in range(10)]


def _walk_the_card(card, lines_of):
    """The arithmetic of a scrolled card: the lines hidden above, the window and the lines
    below add up to the whole card, the offset is the count above, and the head, the rules
    and the close line stay in place."""
    lines = lines_of()
    above, below = _marks(lines)
    window = card._room - 2 - (above is not None) - (below is not None)
    assert (above or 0) + window + (below or 0) == len(card._lines)
    assert (above or 0) == card._offset
    assert lines[0].startswith("  ◈ EXPENSE WORLD")
    return lines, above, below


def test_a_card_that_fits_has_no_scroll_markers_and_opens_at_the_top_after_a_shrink(monkeypatch):
    async def body(pilot, app):
        lines = screen_lines(app)
        assert _marks(lines) == (None, None)
        assert any("[?] or [esc] close" in line for line in lines)
        assert app.screen._shape == "narrow"
        await pilot.press(*["down"] * 10)
        assert _marks(screen_lines(app)) == (None, None)
        assert app.screen._offset == 0
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert _marks(screen_lines(app))[0] is None
        assert any("Keys — Transactions" in line for line in screen_lines(app))

    _ledger_card(monkeypatch, (140, 60), body)


@pytest.mark.parametrize("size", [(100, 24), (80, 24)])
def test_the_ledger_card_scrolls_to_edit_and_delete(monkeypatch, size):
    async def body(pilot, app):
        card = app.screen
        lines = screen_lines(app)
        above, below = _marks(lines)
        assert above is None and below
        assert not any("Always true" in line for line in lines)
        assert any("Keys — Transactions" in line for line in lines)
        await pilot.press("down")
        assert _marks(screen_lines(app)) == (1, below)
        steps = 0
        while below is not None and steps < 80:
            lines, above, below = _walk_the_card(card, lambda: screen_lines(app))
            # the head's rule and the card's two
            assert sum("─" * 60 in line for line in lines) == 3
            assert lines[-1].strip().startswith("esc")
            await pilot.press("down")
            steps += 1
        lines = screen_lines(app)
        above, below = _marks(lines)
        assert above and below is None
        assert any(re.search(r"\bs +Edit", line) for line in lines)
        assert any(re.search(r"\bd +Delete", line) for line in lines)
        await pilot.press("up")
        above, below = _marks(screen_lines(app))
        assert above and below == 2
        # the keys went to the card, not to the screen under it
        assert app.screen is card
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, HelpModal))

    _ledger_card(monkeypatch, size, body)


def test_a_card_that_does_not_fit_spreads_out_on_a_wide_terminal(monkeypatch):
    async def body(pilot, app):
        lines = screen_lines(app)
        assert _marks(lines) == (None, None)
        assert lines[0].startswith("  ◈ EXPENSE WORLD")
        text = "\n".join(lines)
        assert "Keys — Transactions" in text and "[?] or [esc] close" in text
        for title in ("This screen", "Moving around", "Everywhere", "Always true"):
            assert title in text
        for key in ("+", "a", "c", "b", "h", "m", "s", "d", "r", "esc"):
            assert any(re.search(rf"(^|\s){re.escape(key)} +[A-Z]", line) for line in lines), key
        # every key row's words whole on one drawn line, even at the tightest width
        for group in app.screen._groups:
            if group.inline:
                continue
            for row in group.rows:
                words = row.description + (f"   {row.note}" if row.note else "")
                assert any(words in line for line in lines), words
        # three groups across
        head = next(line for line in lines if "This screen" in line)
        assert "Moving around" in head and "Everywhere" in head
        # inset like the picked drawing: the head's rule edge to edge on row 1, the
        # card's own rules apart from it, 4 cells in from each side
        assert set(lines[1]) == {"─"} and len(lines[1]) == 140
        assert lines[2] == "" or set(lines[2].strip()) == {"─"}
        rules = [i for i, line in enumerate(lines) if set(line.strip()) == {"─"} and i > 1]
        assert len(rules) == 2 and rules[0] == 2
        for i in rules:
            assert lines[i] == " " * 4 + "─" * 132
        # the conventions wrap under their own words, key rows never
        at = next(i for i, line in enumerate(lines) if "never changes data" in line)
        assert "currency pick" not in lines[at] and "currency pick" in lines[at + 1]

    _ledger_card(monkeypatch, (140, 24), body)


def test_a_spread_card_too_tall_for_its_room_scrolls_with_exact_counts(monkeypatch):
    async def body(pilot, app):
        card = app.screen
        assert card._shape == "wide"
        for _ in range(len(card._lines)):
            _, above, below = _walk_the_card(card, lambda: screen_lines(app))
            await pilot.press("down")
        assert below is None and above

    _ledger_card(monkeypatch, (140, 14), body)


def test_resizing_moves_between_fit_spread_and_scroll(monkeypatch):
    async def body(pilot, app):
        card = app.screen
        assert card._shape == "wide" and _marks(screen_lines(app)) == (None, None)
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert card._shape == "narrow" and _marks(screen_lines(app))[1]
        for _ in range(5):
            await pilot.press("down")
        assert card._offset == 5
        await pilot.resize_terminal(140, 24)
        await pilot.pause()
        assert card._shape == "wide" and card._offset == 0
        assert _marks(screen_lines(app)) == (None, None)
        await pilot.resize_terminal(140, 60)
        await pilot.pause()
        assert card._shape == "narrow" and card.query_one("#modal").size.width == 68
        assert _marks(screen_lines(app)) == (None, None)

    _ledger_card(monkeypatch, (140, 24), body)


def test_a_narrow_card_nearly_as_tall_as_its_room_keeps_clear_of_the_head(monkeypatch):
    async def body(pilot, app):
        lines = screen_lines(app)
        rules = [i for i, line in enumerate(lines) if "─" * 60 in line]
        assert app.screen._shape == "narrow" and _marks(lines) == (None, None)
        assert rules[:2] == [1, 2]

    for height in (36, 37):
        _ledger_card(monkeypatch, (100, height), body)


def test_the_card_spreads_at_the_width_it_needs_and_scrolls_narrow_below_it(monkeypatch):
    shapes = {}

    async def body(pilot, app):
        card = app.screen
        shapes[card._needs] = card._shape
        await pilot.resize_terminal(card._needs - 1, 24)
        await pilot.pause()
        shapes["below"] = card._shape
        assert _marks(screen_lines(app))[1]
        await pilot.resize_terminal(card._needs, 24)
        await pilot.pause()
        shapes["at"] = card._shape
        assert _marks(screen_lines(app)) == (None, None)

    _ledger_card(monkeypatch, (140, 24), body)
    assert shapes["below"] == "narrow" and shapes["at"] == "wide"


def test_the_ledger_card_leaves_the_gutters_beside_it_blank_at_80_and_140(monkeypatch):
    async def narrow(pilot, app):
        assert_card_gutters_blank(screen_lines(app), 80)

    async def wide(pilot, app):
        assert_card_gutters_blank(screen_lines(app), 140)

    _ledger_card(monkeypatch, (80, 24), narrow)
    _ledger_card(monkeypatch, (140, 24), wide)


def _keys_of(groups, title) -> list[str]:
    return [row.keys for row in _rows(groups, title)] if title in _titles(groups) else []


def _ledger_inventory(monkeypatch, size, check, flt=None, select=False, **engine):
    """The ledger's card groups, read off the screen as `?` reads them, and drawn at `size`."""
    _stub_engine(monkeypatch, **engine)

    async def scenario(pilot, app):
        await app.push_screen(TransactionsScreen(flt))
        await wait_for_loaded(pilot, app)
        if select:
            await pilot.press("space")
        _, groups = screen_inventory(app.screen)
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: isinstance(app.screen, HelpModal))
        await pilot.pause()
        check(groups, " ".join(screen_lines(app)))

    run_app(scenario, size=size)


def test_an_empty_ledger_lists_only_plus_r_and_esc_at_80_and_140(monkeypatch):
    def check(groups, drawn):
        assert _titles(groups) == ["This screen", "Always true", "Everywhere"]
        assert _keys_of(groups, "This screen") == ["+", "r", "esc"]
        assert [(r.keys, r.description) for r in _rows(groups, "This screen")] == [
            ("+", "Add"),
            ("r", "Refresh"),
            ("esc", "Back"),
        ]
        assert "Clear the selection" not in drawn
        assert "pgdn" not in drawn and "Moving around" not in drawn

    for size in ((80, 24), (140, 24)):
        _ledger_inventory(monkeypatch, size, check, rows=())


def test_an_empty_ledger_footer_leaves_the_keys_that_need_a_row(monkeypatch):
    _stub_engine(monkeypatch, rows=())

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await app.push_screen(screen)
        await wait_for_loaded(pilot, app)
        shown = {b.binding.key: b.enabled for b in screen.active_bindings.values()}
        assert "enter" not in shown and "space" not in shown
        listing = screen.query_one(CursorList)
        assert listing.check_action("select", ()) is False
        assert listing.check_action("toggle", ()) is False
        assert screen.check_action("select_all", ()) is False

    run_app(scenario, size=(100, 32))


def test_a_ledger_with_a_row_lists_its_keys_again(monkeypatch):
    def check(groups, drawn):
        assert _keys_of(groups, "This screen") == [
            "+",
            "a",
            "c",
            "b",
            "h",
            "m",
            "s",
            "d",
            "r",
            "esc",
        ]
        assert [(r.keys, r.description) for r in _rows(groups, "Moving around")] == [
            ("↓", "Down"),
            ("⏎", "Open"),
            ("space", "Select / unselect the cursor row"),
            ("pgdn", "Load the next 10 rows under these"),
            ("pgdn", "Next page"),
            ("pgup", "Previous page"),
        ]

    _ledger_inventory(monkeypatch, (140, 24), check)


def _esc_row(groups):
    return next((r.keys, r.description) for r in _rows(groups, "This screen") if r.keys == "esc")


def test_the_ledger_card_says_clear_the_selection_while_it_has_a_row(monkeypatch):
    def check(groups, drawn):
        assert _esc_row(groups) == ("esc", "Clear the selection, else go back")

    _ledger_inventory(monkeypatch, (80, 24), check)
    _ledger_inventory(monkeypatch, (80, 24), check, select=True)


def test_the_filtered_ledger_card_follows_the_same_esc_rule(monkeypatch):
    flt = LedgerFilter("category", "cat-efe", "EFECTIVO")

    def with_rows(groups, drawn):
        assert _esc_row(groups) == ("esc", "Clear the selection, else go back")

    _ledger_inventory(monkeypatch, (80, 24), with_rows, flt=flt)

    def empty(groups, drawn):
        assert _esc_row(groups) == ("esc", "Back")

    _ledger_inventory(monkeypatch, (80, 24), empty, flt=flt, rows=())


def _manage_card(monkeypatch, screen_class, size, items, check):
    """`screen_class`'s `?` card over a list of `items`, read as groups and drawn at `size`."""
    _stub_engine(monkeypatch, items=items)
    for name in ("fetch_categories", "fetch_hashtags"):
        monkeypatch.setattr(f"expense.reads.{name}", lambda cfg, **k: {"items": list(items)})

    async def scenario(pilot, app):
        await app.push_screen(screen_class())
        await wait_for_loaded(pilot, app)
        _, groups = screen_inventory(app.screen)
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: isinstance(app.screen, HelpModal))
        await pilot.pause()
        check(groups, screen_lines(app))

    run_app(scenario, size=size)


EMPTY_MANAGE_CARD = [
    "This screen                       Everywhere",
    "  n    New                          ^q  Quit",
    "  r    Refresh                      ?   This help",
    "  esc  Back",
    "Always true",
    "  r refreshes, everywhere",
    "  y alone confirms",
    "  ⏎ never changes data, except on",
    "    a currency pick",
]


def test_an_empty_manage_list_card_lists_no_key_that_needs_a_row_at_80_and_40_lines(monkeypatch):
    """`n`, `r`, `esc`; `Everywhere` takes the column "Moving around" had."""

    def check(groups, lines):
        assert _titles(groups) == ["This screen", "Always true", "Everywhere"]
        assert _keys_of(groups, "This screen") == ["n", "r", "esc"]
        drawn = [re.sub(r"\s+", " ", line.replace("│", "")).strip() for line in lines]
        start = next(i for i, line in enumerate(drawn) if line.startswith("This screen"))
        shown = [line for line in drawn[start:] if line]
        wanted = [re.sub(r"\s+", " ", row).strip() for row in EMPTY_MANAGE_CARD]
        assert shown[: len(wanted)] == wanted
        text = " ".join(lines)
        for gone in ("Moving around", "pgdn", "pgup", "Edit", "Delete", "Archive"):
            assert gone not in text

    for screen_class in (AccountsScreen, CategoriesScreen, HashtagsScreen):
        for size in ((80, 24), (80, 40)):
            if screen_class is not AccountsScreen and size == (80, 40):
                continue
            _manage_card(monkeypatch, screen_class, size, (), check)


def test_a_manage_list_with_a_row_keeps_its_card(monkeypatch):
    keys = {
        AccountsScreen: ["n", "e", "c", "x", "a", "t", "t", "d", "r", "esc"],
        CategoriesScreen: ["d", "n", "e", "r", "esc"],
        HashtagsScreen: ["d", "n", "e", "r", "esc"],
    }
    row = {"id": "x-1", "name": "Food", "currency_code": "PEN", "is_system": False}

    for screen_class, expected in keys.items():

        def check(groups, lines, expected=expected):
            assert _keys_of(groups, "This screen") == expected
            assert _keys_of(groups, "Moving around") == ["↓", "pgdn", "pgup"]

        items = ENGINE_ORDER_HOLDING_ACCOUNTS if screen_class is AccountsScreen else [row]
        _manage_card(monkeypatch, screen_class, (100, 32), items, check)


def _agree_while_empty(owner):
    """On an empty list the footer drops a key exactly when the card does not list it,
    judged both ways: every key the owner's `CARD_NEEDS_A_ROW` names is dropped by both,
    and every key the card still lists is one `check_action` allows. Left out of the second
    pass: a key the card judges by `check_action` itself (`CARD_FOLLOWS_CHECK`) and one that
    waits on the screen around the list, not on a row (`NEEDS_SCREEN_HANDLER`: an unmounted
    widget has no such host)."""
    listed_all = listed_bindings(owner)
    listed = {parse_action(b.action)[1] for b in listed_all}
    named = type(owner).CARD_NEEDS_A_ROW
    declared = {parse_action(b.action)[1] for b in declared_bindings(type(owner))}
    for action in named & declared:
        in_footer = owner.check_action(action, ()) is not False
        assert not in_footer, f"{action}: the footer keeps a key the empty list cannot act on"
        assert action not in listed, f"{action}: the card lists a key the footer drops"
    follows = getattr(owner, "CARD_FOLLOWS_CHECK", ())
    for binding in listed_all:
        _, action, parameters = parse_action(binding.action)
        if action in follows or action in NEEDS_SCREEN_HANDLER:
            continue
        assert owner.check_action(action, parameters) is not False, (
            f"{action}: the card lists a key the footer drops"
        )


@pytest.mark.parametrize(
    "screen_class", [AccountsScreen, CategoriesScreen, HashtagsScreen, TransactionsScreen]
)
def test_the_footer_and_the_card_agree_on_an_empty_screen(screen_class):
    screen = screen_class()
    assert not screen.has_rows and screen_class.CARD_NEEDS_A_ROW
    _agree_while_empty(screen)


def test_the_footer_and_the_card_agree_on_an_empty_list_widget():
    for widget_class in (_AccountList, _PanelList):
        widget = widget_class(["A"], [])
        assert not widget.has_rows
        _agree_while_empty(widget)
    assert _AccountList.CARD_NEEDS_A_ROW and {"select", "edit_row"} <= _PanelList.CARD_NEEDS_A_ROW


@pytest.mark.parametrize(
    ("screen_class", "row", "dropped"),
    [
        (CategoriesScreen, {"id": "c1", "name": "Comida", "is_system": False}, {"edit", "delete"}),
        (HashtagsScreen, {"id": "h1", "name": "viaje"}, {"edit", "delete"}),
        (
            AccountsScreen,
            {"id": "a1", "name": "BCP", "currencies": [], "kind": "bank"},
            {"edit", "delete", "archive", "make_person", "add_currency", "remove_currency"},
        ),
    ],
)
def test_a_manage_list_after_a_failed_refresh_drops_its_row_keys_in_footer_and_card(
    monkeypatch, screen_class, row, dropped
):
    """The records read before stay in memory, but no list is on screen: the footer and the
    `?` card both leave the keys that need a row."""
    engine_down = []

    def read(*args, **kwargs):
        if engine_down:
            raise RuntimeError("engine down")
        return whole([row])

    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    for name in ("fetch_categories", "fetch_hashtags", "fetch_accounts"):
        monkeypatch.setattr(f"expense.reads.{name}", read)
    monkeypatch.setattr("expense.reads.fetch_currency_codes", lambda cfg, **k: ["PEN"])

    def names(screen):
        return {parse_action(b.action)[1] for b in listed_bindings(screen)}

    async def scenario(pilot, app):
        screen = screen_class()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.pause()
        assert screen.has_rows
        assert {"edit", "delete"} <= names(screen)
        engine_down.append(True)
        await pilot.press("r")
        await wait_for(pilot, lambda: "Could not load." in "".join(screen_lines(app)))
        await pilot.pause()
        assert not screen.has_rows
        assert screen._by_id  # the stale records are still held
        for action in dropped:
            assert screen.check_action(action, ()) is False, action
        assert not dropped & names(screen)

    run_app(scenario, size=(100, 32))
