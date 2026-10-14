"""The ledger's selection and bulk keys.

`space` selects, `a` selects the page, `c`/`b`/`h` open the picker over the
selection (or the cursor row) and write one PUT per row; `esc` clears the
selection, else goes back. A fake client stands in for the engine, so the
PUTs are asserted, never sent.
"""

from rich.text import Text

import expense.tui.screens.transactions as tx_mod
from expense.errors import EngineError
from expense.reads import QuickAddRefs
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
from tests.unit.helpers import fake_ledger, run_app, wait_for, wait_for_list, wait_for_loaded

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
    fake_ledger(monkeypatch, list(items))
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
    """One line: `N of M loaded` took the place of `M rows`."""
    assert legend_text(FILTER, 20, 57, 0) == "filter: category @Pendiente · 20 of 57 loaded"
    one = "filter: category @Pendiente · 1 of 1 loaded · 1 selected"
    assert legend_text(FILTER, 1, 1, 1) == one
    assert legend_text(None, 10, 133, 3) == "no filter · 10 of 133 loaded · 3 selected"
    assert legend_text(None, 0, None, 0) == "no filter"


def test_bulk_receipt_counts_rows():
    assert bulk_receipt(3, "KORAKUEN") == "3 rows → KORAKUEN"
    assert bulk_receipt(1, "#COMIDA #CAJAS") == "1 row → #COMIDA #CAJAS"


def test_bulk_receipt_counts_the_rows_that_left_their_reconciliation():
    assert bulk_receipt(3, "BCP USD", 0) == "3 rows → BCP USD"
    assert bulk_receipt(3, "BCP USD", 1) == "3 rows → BCP USD · 1 left its reconciliation"
    assert bulk_receipt(3, "BCP USD", 2) == "3 rows → BCP USD · 2 left their reconciliation"


# ---- selection ---------------------------------------------------------------


def test_space_selects_and_a_selects_every_loaded_row(monkeypatch):
    _stub_ledger(monkeypatch)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        await _open(app, pilot, screen)
        assert screen.crumb == ("Ledger", "@Pendiente")
        assert _legend(screen) == "filter: category @Pendiente · 3 of 3 loaded"
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
        assert _legend(screen) == "filter: category @Pendiente · 3 of 3 loaded"

    run_app(scenario, size=(120, 30))


def test_space_is_inert_and_unadvertised_where_no_screen_owns_a_selection(monkeypatch):
    """The Manage lists have no selection: the key does nothing there and the
    footer does not offer it — the same gate `⏎ Open` goes through."""
    _stub_ledger(monkeypatch)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda cfg, **k: {"items": [{"id": "a1", "name": "BCP", "is_archived": False}]},
    )

    async def scenario(pilot, app):
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

    run_app(scenario, size=(120, 30))


# ---- the bulk write ------------------------------------------------------------


def test_c_writes_one_put_per_selected_row_then_reloads(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)
    toasts: list[str] = []

    async def scenario(pilot, app):
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

    run_app(scenario, size=(120, 30))


def test_with_nothing_selected_the_keys_act_on_the_cursor_row(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        await _open(app, pilot, screen)
        await pilot.press("down", "b")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        assert app.screen._title == "ACCOUNT for 1 row"
        await pilot.press("o", "r", "o", "enter")
        await wait_for(pilot, lambda: fake_client.puts)
        assert fake_client.puts == [
            ("/transactions/t2", {"account_id": "acc2", "reconciliation_id": None})
        ]

    run_app(scenario, size=(120, 30))


def test_h_replaces_the_tag_set_with_several(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)

    async def scenario(pilot, app):
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

    run_app(scenario, size=(120, 30))


def test_a_refused_row_is_named_and_the_rest_go_through(fake_client, monkeypatch):
    """The account move a completed reconciliation refuses: row 2 is
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

    async def scenario(pilot, app):
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

    run_app(scenario, size=(120, 30))


def test_settings_missing_stops_the_bulk_edit_at_the_first_row(fake_client, monkeypatch):
    """A refusal about the account, not the row: every later PUT would draw it
    too, so none goes out and the hint is on screen once."""
    _stub_ledger(monkeypatch)
    toasts: list[tuple[str, str]] = []
    puts: list[str] = []

    def put(path, json_body=None):
        puts.append(path)
        raise EngineError(
            "SETTINGS_MISSING",
            "User settings have not been provisioned.",
            {"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
            422,
            {},
            reasons={"user_settings": "NOT_PROVISIONED"},
        )

    fake_client.put = put

    async def scenario(pilot, app):
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
        await wait_for(pilot, lambda: bool(toasts))
        await wait_for(pilot, lambda: not screen._bulk_busy)

        assert puts == ["/transactions/t1"]
        assert toasts == [
            (
                "Refused",
                "row 1: SETTINGS_MISSING — User settings have not been provisioned.\n"
                "  user_settings: Must be provisioned via POST /v1/auth/bootstrap.\n"
                "\n"
                "Hint: First-time setup is not done yet. "
                "Open System ▸ Auth & profile and press b.",
            )
        ]
        # the refused row and the two never sent stay selected for the retry
        assert screen._selected == {"t1", "t2", "t3"}

    run_app(scenario, size=(120, 30))


def test_settings_missing_mid_run_keeps_the_refused_and_unsent_rows_selected(
    fake_client, monkeypatch
):
    """The run stops at row 2: row 1 went through and leaves the selection, row 2
    was refused and row 3 was never sent, so those two stay selected."""
    _stub_ledger(monkeypatch)
    puts: list[str] = []
    real_put = fake_client.put

    def put(path, json_body=None):
        puts.append(path)
        if path.endswith("/t2"):
            raise EngineError(
                "SETTINGS_MISSING",
                "User settings have not been provisioned.",
                {"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."},
                422,
                {},
                reasons={"user_settings": "NOT_PROVISIONED"},
            )
        return real_put(path, json_body=json_body)

    fake_client.put = put

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        await _open(app, pilot, screen)
        await pilot.press("a", "b")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        await pilot.press("o", "r", "o", "enter")
        await wait_for(pilot, lambda: len(puts) == 2)
        await wait_for(pilot, lambda: not screen._bulk_busy)

        assert puts == ["/transactions/t1", "/transactions/t2"]
        assert screen._selected == {"t2", "t3"}

    run_app(scenario, size=(120, 30))


# ---- b: a move leaves the reconciliation ---------------------------------------
# (contract: "Assigning transactions") (contract: PUT /v1/transactions/{transaction_id})

#: t1 is assigned and moves, t2 is assigned but already on the picked account,
#: t3 is in no reconciliation and moves.
MIXED = [
    {**ITEMS[0], "reconciliation_id": "r1"},
    {**ITEMS[1], "account_id": "acc2", "reconciliation_id": "r2"},
    {**ITEMS[2], "reconciliation_id": None},
]


def test_b_unassigns_only_the_rows_whose_account_changes(fake_client, monkeypatch):
    _stub_ledger(monkeypatch, MIXED)
    toasts: list[str] = []

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        monkeypatch.setattr(screen, "notify", lambda message, **kw: toasts.append(str(message)))
        await _open(app, pilot, screen)
        await pilot.press("a", "b")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        await pilot.press("o", "r", "o", "enter")
        await wait_for(pilot, lambda: len(fake_client.puts) == 3)
        assert fake_client.puts == [
            ("/transactions/t1", {"account_id": "acc2", "reconciliation_id": None}),
            # already on acc2: not a move, so it keeps its reconciliation
            ("/transactions/t2", {"account_id": "acc2"}),
            ("/transactions/t3", {"account_id": "acc2", "reconciliation_id": None}),
        ]
        await wait_for(pilot, lambda: toasts)
        # t3 was in no reconciliation, t2 stayed in its own: one left
        assert toasts[0] == "3 rows → BCP Oro PEN · 1 left its reconciliation"

    run_app(scenario, size=(120, 30))


def test_b_onto_the_rows_own_account_never_unassigns(fake_client, monkeypatch):
    _stub_ledger(monkeypatch, MIXED)
    toasts: list[str] = []

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        monkeypatch.setattr(screen, "notify", lambda message, **kw: toasts.append(str(message)))
        await _open(app, pilot, screen)
        await pilot.press("space", "b")  # t1, on acc1, back onto acc1
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        await pilot.press("s", "i", "g", "enter")
        await wait_for(pilot, lambda: fake_client.puts)
        assert fake_client.puts == [("/transactions/t1", {"account_id": "acc1"})]
        await wait_for(pilot, lambda: toasts)
        assert toasts[0] == "1 row → BCP Signature PEN"

    run_app(scenario, size=(120, 30))


def test_b_on_a_completed_reconciliation_is_still_refused_with_the_lock(fake_client, monkeypatch):
    """The engine checks `LOCKED` first, `reconciliation_id` included: the
    locked row is named with the engine's reason and is not counted as left."""
    _stub_ledger(monkeypatch, MIXED)
    toasts: list[tuple[str, str]] = []
    real_put = fake_client.put

    def put(path, json_body=None):
        if path.endswith("/t1"):
            raise EngineError(
                "VALIDATION_ERROR",
                "Fields are locked by a completed reconciliation.",
                {"account_id": "Locked by completed reconciliation."},
                422,
                {},
                reasons={"account_id": "LOCKED", "reconciliation_id": "LOCKED"},
            )
        return real_put(path, json_body=json_body)

    fake_client.put = put

    async def scenario(pilot, app):
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
        refused = next(m for t, m in toasts if t == "Refused")
        assert refused.startswith("row 1: ") and "Locked by completed reconciliation." in refused
        assert ("", "2 rows → BCP Oro PEN") in toasts  # t1 never left: nothing to count
        await wait_for(pilot, lambda: not screen._bulk_busy)
        assert screen._selected == {"t1"}

    run_app(scenario, size=(120, 30))


def test_esc_cancels_the_picker_and_writes_nothing(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        await _open(app, pilot, screen)
        await pilot.press("space", "c")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert fake_client.puts == []
        assert screen._selected == {"t1"}  # the selection survives a cancel

    run_app(scenario, size=(120, 30))


# ---- esc -----------------------------------------------------------------------


def test_esc_clears_the_selection_then_goes_back_with_the_filter_kept(monkeypatch):
    """Esc on a filtered ledger is back to where you came
    from, never to the unfiltered ledger. A selection still clears first."""
    _stub_ledger(monkeypatch)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        before = app.screen
        screen = TransactionsScreen(filter=FILTER)
        await _open(app, pilot, screen)
        await pilot.press("space")
        await wait_for(pilot, lambda: screen._selected == {"t1"})
        await pilot.press("escape")
        await wait_for(pilot, lambda: screen._selected == set())
        assert screen._filter == FILTER and app.screen is screen
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is before)
        assert screen._filter == FILTER  # left as it was entered, never cleared

    run_app(scenario, size=(120, 30))


# ---- the picker on its own ------------------------------------------------------


def test_picker_single_mode_narrows_and_moves():
    async def scenario(pilot, app):
        results: list = []
        modal = PickerModal("CATEGORY for 1 row", [("a", "HOGAR"), ("b", "KORAKUEN")])
        app.push_screen(modal, results.append)
        await wait_for(pilot, lambda: app.screen is modal)
        assert [i for i, _ in modal._pool] == ["a", "b"]
        await pilot.press("down", "enter")  # the second candidate
        await wait_for(pilot, lambda: results == ["b"])

    run_app(scenario, size=(100, 30))


def test_picker_refuses_an_empty_multi_pick_and_an_unknown_tag():
    async def scenario(pilot, app):
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

    run_app(scenario, size=(100, 30))


# ---- refusals collapse by reason ---------------------------------------------
SEALED_AUG = (
    "VALIDATION_ERROR — Transaction falls inside a sealed reconciliation period.\n"
    "  account_id: Period 2026-07-24 to 2026-08-25 is sealed by completed "
    "reconciliation 'August 2026'. Revert it to draft to change anything inside it."
)
SEALED_JUL = SEALED_AUG.replace("2026-07-24 to 2026-08-25", "2026-06-26 to 2026-07-23").replace(
    "'August 2026'", "'July 2026'"
)


def test_refusals_collapse_to_one_line_per_reason():
    """Eight rows refused by two closed periods is two lines, not eight toasts.

    The grouping key is the engine's sentence exactly as it arrived — the period
    name is inside it and nothing here parses it out.
    """
    from expense.tui.screens.transactions import group_refusals

    failed = [(f"t{n}", n, SEALED_AUG) for n in (1, 2, 3, 4, 5)]
    failed += [(f"t{n}", n, SEALED_JUL) for n in (7, 8, 9)]
    lines = group_refusals(failed)
    assert len(lines) == 2
    assert lines[0].startswith("rows 1, 2, 3, 4, 5: ")
    assert "'August 2026'" in lines[0]
    assert lines[1].startswith("rows 7, 8, 9: ") and "'July 2026'" in lines[1]


def test_one_refusal_still_reads_as_one_row():
    from expense.tui.screens.transactions import group_refusals

    assert group_refusals([("t2", 2, "nope")]) == ["row 2: nope"]


def test_a_long_refused_run_stops_listing_numbers_and_counts_them():
    from expense.tui.screens.transactions import REFUSAL_ROWS_SHOWN, group_refusals

    failed = [(f"t{n}", n, SEALED_AUG) for n in range(1, 13)]
    (line,) = group_refusals(failed)
    assert f"+{12 - REFUSAL_ROWS_SHOWN} more" in line


def test_a_chunk_level_refusal_with_no_row_number_keeps_its_message():
    """A whole-run failure arrives as `(None, 0, message)` — it must not be
    dressed up as a row."""
    from expense.tui.screens.transactions import group_refusals

    assert group_refusals([(None, 0, "could not reach engine")]) == ["could not reach engine"]


def test_eight_sealed_rows_raise_two_toasts_not_eight(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)
    toasts: list[tuple[str, str]] = []

    def put(path, json_body=None):
        raise EngineError(
            "VALIDATION_ERROR",
            "Transaction falls inside a sealed reconciliation period.",
            {"account_id": "Period … is sealed by completed reconciliation 'August 2026'."},
            422,
            {},
            reasons={"account_id": "SEALED_PERIOD"},
        )

    fake_client.put = put

    async def scenario(pilot, app):
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
        await wait_for(pilot, lambda: toasts)
        await wait_for(pilot, lambda: not screen._bulk_busy)
        # every row shares one reason → exactly one refusal toast, counted
        refusals = [(t, m) for t, m in toasts if "refused" in t or t == "Refused"]
        assert len(refusals) == 1
        title, message = refusals[0]
        assert title == "3 of 3 refused"
        assert message.startswith("rows 1, 2, 3: ")
        assert "'August 2026'" in message
        assert screen._selected == {"t1", "t2", "t3"}  # all stay selected for the retry

    run_app(scenario, size=(120, 30))
