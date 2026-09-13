"""The ledger's selection and bulk keys (2026-09-12, mockup
docs/mockups/expense-world-home-as-ledger.html panes 2–6).

`space` selects, `a` selects the page, `c`/`b`/`h` open the picker over the
selection (or the cursor row) and write one PUT per row; `esc` retreats
selection → filter → screen. A fake client stands in for the engine, so the
PUTs are asserted, never sent.
"""

import asyncio

from rich.text import Text

import expense.tui.screens.transactions as tx_mod
from expense.commands._resource import QuickAddRefs
from expense.errors import EngineError
from expense.tui.app import ExpenseApp
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.modals import PickerModal
from expense.tui.screens.transactions import (
    SELECTED_MARK,
    LedgerFilter,
    TransactionsScreen,
    bulk_receipt,
    legend_text,
    mark_selected,
)
from expense.tui.theme import ACCENT
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import wait_for, wait_for_list, wait_for_loaded

ITEMS = [
    {
        "id": f"t{i}",
        "title": title,
        "description": None,
        "amount_cents": -1000 * i,
        "date": "2026-09-11T00:00:00Z",
        "account_id": "acc1",
        "category_id": "pend",
        "hashtag_ids": [],
    }
    for i, title in enumerate(["EDO SUSHI BAR", "DLC*RIDES", "MAR DE COLAS"], start=1)
]
# (id, name) pairs, built into maps with dict(): scripts/check_fixture_drift.py
# reads every quoted dict-literal key in a test file as an engine field, and
# these are ids.
ACCOUNTS = [("acc1", "BCP Signature PEN", "PEN"), ("acc2", "BCP Oro PEN", "PEN")]
CATEGORIES = [("kor", "KORAKUEN"), ("hog", "HOGAR")]
HASHTAGS = [("h1", "COMIDA"), ("h2", "CAJA CHICA"), ("h3", "CAJAS")]
PENDING = ("pend", "@Pendiente")
NAMES = dict([(i, n) for i, n, _c in ACCOUNTS] + CATEGORIES + [PENDING])
REFS = QuickAddRefs(
    accounts=ACCOUNTS,
    categories=CATEGORIES,
    hashtags=HASHTAGS,
    account_names={i: n for i, n, _c in ACCOUNTS},
    category_names=dict(CATEGORIES + [PENDING]),
    hashtag_names=dict(HASHTAGS),
    pending=PENDING,
)
FILTER = LedgerFilter("category", "pend", "@Pendiente")


def _stub_ledger(monkeypatch, items=ITEMS):
    monkeypatch.setattr(
        "expense.commands.transactions_cmd.fetch_transactions",
        lambda *a, **k: {"items": list(items), "total": len(items)},
    )
    for name in ("load_account_name_map", "load_category_name_map", "load_hashtag_name_map"):
        monkeypatch.setattr(tx_mod, name, lambda: NAMES)
    monkeypatch.setattr(tx_mod, "load_quickadd_refs", lambda cfg, **kw: REFS)


def _legend(screen) -> str:
    """What the legend widget was last painted with (a mounted Static keeps no
    readable renderable in Textual 8; the screen's builder is the one source)."""
    assert screen.query("#legend"), "the legend is not mounted"
    return screen._legend()


async def _open(app, pilot, screen):
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    screen.query_one(CursorList).focus()
    await pilot.pause()


# ---- pure helpers ----------------------------------------------------------


def test_mark_selected_draws_the_marker_and_keeps_titles_aligned():
    rows = [("t1", ["EDO", "", "-1.00"]), ("t2", ["DLC", "", "-2.00"])]
    marked = mark_selected(rows, {"t2"})
    assert marked[0][1][0] == "  EDO"  # a blank gutter, same width as the marker
    assert isinstance(marked[1][1][0], Text) and marked[1][1][0].plain == SELECTED_MARK + "DLC"
    assert marked[1][2] == ACCENT  # the tint is the theme's accent, no literal colour
    assert len(marked[0]) == 2  # unselected rows keep their shape


def test_legend_says_filter_count_and_selection():
    assert legend_text(FILTER, 57, 0) == "filter: category @Pendiente · 57 rows"
    assert legend_text(FILTER, 1, 1) == "filter: category @Pendiente · 1 row · 1 selected"
    assert legend_text(None, 133, 3) == "no filter · 133 rows · 3 selected"
    assert legend_text(None, None, 0) == "no filter"


def test_bulk_receipt_counts_rows():
    assert bulk_receipt(3, "KORAKUEN") == "3 rows → KORAKUEN"
    assert bulk_receipt(1, "#COMIDA #CAJAS") == "1 row → #COMIDA #CAJAS"


# ---- selection ---------------------------------------------------------------


def test_space_selects_and_a_selects_the_page(monkeypatch):
    _stub_ledger(monkeypatch)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(120, 30)) as pilot:
            screen = TransactionsScreen(filter=FILTER)
            await _open(app, pilot, screen)
            assert screen.crumb == ("Ledger", "@Pendiente")
            assert _legend(screen) == "filter: category @Pendiente · 3 rows"
            await pilot.press("space")  # select row 1; the cursor stays
            await wait_for(pilot, lambda: screen._selected == {"t1"})
            assert screen.query_one(CursorList)._cursor == 0
            assert _legend(screen).endswith("· 1 selected")
            await pilot.press("down", "space")
            await wait_for(pilot, lambda: screen._selected == {"t1", "t2"})
            await pilot.press("space")  # unselect the cursor row
            await wait_for(pilot, lambda: screen._selected == {"t1"})
            await pilot.press("a")  # all
            await wait_for(pilot, lambda: screen._selected == {"t1", "t2", "t3"})
            await pilot.press("a")  # none
            await wait_for(pilot, lambda: screen._selected == set())
            assert _legend(screen) == "filter: category @Pendiente · 3 rows"

    asyncio.run(scenario())


def test_space_is_inert_and_unadvertised_where_no_screen_owns_a_selection(monkeypatch):
    """The Manage lists have no selection: the key does nothing there and the
    footer does not offer it — the same gate `⏎ Open` goes through."""
    _stub_ledger(monkeypatch)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    monkeypatch.setattr(
        "expense.commands.accounts_cmd.fetch_accounts",
        lambda cfg, **k: {"items": [{"id": "a1", "name": "BCP", "is_archived": False}]},
    )

    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await app.push_screen(AccountsScreen())
            await wait_for_loaded(pilot, app)
            app.screen.query_one(CursorList).focus()
            await pilot.pause()
            shown = [b.description for _n, b, _e, _t in app.active_bindings.values() if b.show]
            assert "Select" not in shown
            app.pop_screen()

            screen = TransactionsScreen(filter=FILTER)
            await _open(app, pilot, screen)
            shown = [b.description for _n, b, _e, _t in app.active_bindings.values() if b.show]
            assert "Select" in shown and "All/none" in shown
            assert {"Category", "Account", "Hashtags"} <= set(shown)

    asyncio.run(scenario())


# ---- the bulk write ------------------------------------------------------------


def test_c_writes_one_put_per_selected_row_then_reloads(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)
    toasts: list[str] = []

    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(120, 30)) as pilot:
            screen = TransactionsScreen(filter=FILTER)
            monkeypatch.setattr(screen, "notify", lambda message, **kw: toasts.append(str(message)))
            await _open(app, pilot, screen)
            await pilot.press("space", "down", "down", "space")
            await wait_for(pilot, lambda: screen._selected == {"t1", "t3"})
            await pilot.press("c")
            await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
            assert app.screen._title == "CATEGORY for 2 rows"
            await pilot.press("k", "o", "r", "enter")
            await wait_for(pilot, lambda: len(fake_client.puts) == 2)
            assert fake_client.puts == [
                ("/transactions/t1", {"category_id": "kor"}),
                ("/transactions/t3", {"category_id": "kor"}),
            ]
            await wait_for(pilot, lambda: "2 rows → KORAKUEN" in toasts)
            await wait_for(pilot, lambda: not screen._bulk_busy and screen._selected == set())

    asyncio.run(scenario())


def test_with_nothing_selected_the_keys_act_on_the_cursor_row(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(120, 30)) as pilot:
            screen = TransactionsScreen(filter=FILTER)
            await _open(app, pilot, screen)
            await pilot.press("down", "b")
            await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
            assert app.screen._title == "ACCOUNT for 1 row"
            await pilot.press("o", "r", "o", "enter")
            await wait_for(pilot, lambda: fake_client.puts)
            assert fake_client.puts == [("/transactions/t2", {"account_id": "acc2"})]

    asyncio.run(scenario())


def test_h_replaces_the_tag_set_with_several(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(120, 30)) as pilot:
            screen = TransactionsScreen(filter=FILTER)
            await _open(app, pilot, screen)
            await pilot.press("space", "h")
            await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
            modal = app.screen
            assert modal._multi and "replaces every tag" in modal._note
            # `com` + ↵ picks COMIDA and clears the input; `caj` narrows to two,
            # ↓ takes CAJAS; ↵ on the empty input applies both
            await pilot.press("c", "o", "m", "enter")
            await wait_for(pilot, lambda: modal._picked == ["h1"])
            await pilot.press("c", "a", "j", "down", "enter")
            await wait_for(pilot, lambda: modal._picked == ["h1", "h3"])
            await pilot.press("enter")
            await wait_for(pilot, lambda: fake_client.puts)
            assert fake_client.puts == [("/transactions/t1", {"hashtag_ids": ["h1", "h3"]})]

    asyncio.run(scenario())


def test_a_refused_row_is_named_and_the_rest_go_through(fake_client, monkeypatch):
    """The account move a completed reconciliation refuses (pane 5): row 2 is
    reported by number, rows 1 and 3 are written, and row 2 stays selected so
    the same key retries exactly it."""
    _stub_ledger(monkeypatch)
    toasts: list[tuple[str, str]] = []
    real_put = fake_client.put

    def put(path, json_body=None):
        if path.endswith("/t2"):
            raise EngineError(
                "CONFLICT", "account is locked by a completed reconciliation", None, 409, {}
            )
        return real_put(path, json_body=json_body)

    fake_client.put = put

    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(120, 30)) as pilot:
            screen = TransactionsScreen(filter=FILTER)
            monkeypatch.setattr(
                screen,
                "notify",
                lambda message, title="", **kw: toasts.append((title, str(message))),
            )
            await _open(app, pilot, screen)
            await pilot.press("a", "b")
            await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
            await pilot.press("o", "r", "o", "enter")
            await wait_for(pilot, lambda: any(t == "Refused" for t, _m in toasts))
            assert [p for p, _b in fake_client.puts] == ["/transactions/t1", "/transactions/t3"]
            refused = next(m for t, m in toasts if t == "Refused")
            assert refused.startswith("row 2: ") and "locked" in refused
            assert ("", "2 rows → BCP Oro PEN") in toasts
            await wait_for(pilot, lambda: not screen._bulk_busy)
            assert screen._selected == {"t2"}

    asyncio.run(scenario())


def test_esc_cancels_the_picker_and_writes_nothing(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)

    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(120, 30)) as pilot:
            screen = TransactionsScreen(filter=FILTER)
            await _open(app, pilot, screen)
            await pilot.press("space", "c")
            await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
            await pilot.press("escape")
            await wait_for(pilot, lambda: app.screen is screen)
            await pilot.pause()
            assert fake_client.puts == []
            assert screen._selected == {"t1"}  # the selection survives a cancel

    asyncio.run(scenario())


# ---- esc retreats ---------------------------------------------------------------


def test_esc_retreats_selection_then_filter_then_screen(monkeypatch):
    _stub_ledger(monkeypatch)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(120, 30)) as pilot:
            screen = TransactionsScreen(filter=FILTER)
            await _open(app, pilot, screen)
            await pilot.press("space")
            await wait_for(pilot, lambda: screen._selected == {"t1"})
            await pilot.press("escape")
            await wait_for(pilot, lambda: screen._selected == set())
            assert screen._filter == FILTER and app.screen is screen
            await pilot.press("escape")
            await wait_for(pilot, lambda: screen._filter is None)
            await wait_for_list(pilot, app)
            assert app.screen is screen
            assert _legend(screen) == "no filter · 3 rows"
            await pilot.press("escape")
            await wait_for(pilot, lambda: app.screen is not screen)

    asyncio.run(scenario())


# ---- the picker on its own ------------------------------------------------------


def test_picker_single_mode_narrows_and_moves():
    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(100, 30)) as pilot:
            results: list = []
            modal = PickerModal("CATEGORY for 1 row", [("a", "HOGAR"), ("b", "KORAKUEN")])
            app.push_screen(modal, results.append)
            await wait_for(pilot, lambda: app.screen is modal)
            assert [i for i, _ in modal._pool] == ["a", "b"]
            await pilot.press("down", "enter")  # the second candidate
            await wait_for(pilot, lambda: results == ["b"])

    asyncio.run(scenario())


def test_picker_refuses_an_empty_multi_pick_and_an_unknown_tag():
    async def scenario():
        app = ExpenseApp()
        async with app.run_test(size=(100, 30)) as pilot:
            results: list = []
            modal = PickerModal("HASHTAGS for 2 rows", [("h1", "COMIDA")], multi=True)
            app.push_screen(modal, results.append)
            await wait_for(pilot, lambda: app.screen is modal)
            await pilot.press("enter")  # empty: not "clear every tag"
            await pilot.pause()
            assert app.screen is modal and results == []
            for ch in list("zzz"):  # no `"…":` — the drift scanner reads that as a field
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause()
            assert app.screen is modal and results == [] and modal._picked == []
            # a pick, then backspace on the empty input takes it back
            await pilot.press("backspace", "backspace", "backspace", "backspace")
            await pilot.press("c", "o", "enter")
            await wait_for(pilot, lambda: modal._picked == ["h1"])
            await pilot.press("backspace")
            await wait_for(pilot, lambda: modal._picked == [])
            await pilot.press("escape")
            await wait_for(pilot, lambda: results == [None])

    asyncio.run(scenario())
