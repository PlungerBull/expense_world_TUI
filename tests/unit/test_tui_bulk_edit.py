"""The ledger's selection and bulk keys.

`space` selects, `a` selects the page, `c`/`b`/`h` open the picker over the
selection (or the cursor row) and write one PUT per row; `esc` clears the
selection, else goes back. A fake client stands in for the engine, so the
PUTs are asserted, never sent.
"""

import pytest
from rich.text import Text

import expense.tui.screens.transactions as tx_mod
from expense.errors import EngineError
from expense.reads import AccountIndex, QuickAddRefs, load_quickadd_refs
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.modals import PickerModal
from expense.tui.screens.transactions import (
    SELECTED_MARK,
    LedgerFilter,
    TransactionsScreen,
    bulk_receipt,
    legend_text,
    mark_selected,
    moved_parts,
)
from expense.tui.theme import ACCENT
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ARCHIVED_FIELD_WORDS,
    ARCHIVED_PUT_WORDS,
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_NAMES,
    HASHTAG_REFUSALS,
    archived_refusal,
    fake_ledger,
    hashtag_refusal,
    in_order,
    line_code_of,
    list_ready,
    put_answer,
    refusal_text,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    wait_for_loaded,
    whole,
)

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
        "line_code": f"#{i:06d}",
        "statement_line": None,
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
# the pick list as `pickable_categories` gives it: @Pendiente where the engine lists it
PICKABLE = [CATEGORIES[0], PENDING, CATEGORIES[1]]
NAMES = dict([(i, n) for i, n, _c in ACCOUNTS] + CATEGORIES + [PENDING])
REFS = QuickAddRefs(
    accounts=ACCOUNTS,
    categories=CATEGORIES,
    hashtags=HASHTAGS,
    account_names={i: n for i, n, _c in ACCOUNTS},
    category_names=dict(CATEGORIES + [PENDING]),
    hashtag_names=dict(HASHTAGS),
    pending=PENDING,
    pickable_categories=PICKABLE,
)
FILTER = LedgerFilter("category", "pend", "@Pendiente")


def _stub_ledger(monkeypatch, items=ITEMS):
    fake_ledger(monkeypatch, list(items))
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(NAMES))
    for name in ("load_category_name_map", "load_hashtag_name_map"):
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


def _moved(row: dict, account: str = "acc2") -> dict:
    """`row` after a move onto `account`: on it, and in no reconciliation."""
    return {**row, "account_id": account, "reconciliation_id": None}


def _answer_moves(fake_client, rows: list[dict], *, left: tuple[str, ...] = ()) -> None:
    """Each row of `rows` answers its `PUT` as the engine answers a move of a
    one-part line: the row after the write, listed alone in `changed_parts`,
    flagged as leaving its reconciliation when its id is in `left`."""
    for row in rows:
        moved = _moved(row)
        fake_client.write_responses[f"/transactions/{row['id']}"] = put_answer(
            moved, [moved], left=left
        )


def _answer_unchanged(fake_client, row: dict) -> None:
    """`row` answers its `PUT` with no part changed: the move sent the account
    it is already on (contract: PUT /v1/transactions/{transaction_id}, "Response")."""
    fake_client.write_responses[f"/transactions/{row['id']}"] = put_answer(row, [])


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


def test_moved_parts_counts_each_part_once_across_the_answers():
    """A part listed by two answers counts once, and so does its flag; an answer
    that lists nothing adds nothing."""
    p1 = {"id": "p1"}
    p2 = {"id": "p2"}
    first = put_answer(p1, [p1, p2], left=("p1", "p2"))
    again = put_answer(p2, [p1, p2], left=("p2",))
    assert moved_parts([first, again]) == (2, 2)
    assert moved_parts([first, put_answer(p2, [])]) == (2, 2)
    assert moved_parts([put_answer(p1, [p1, p2], left=("p2",))]) == (2, 1)
    assert moved_parts([put_answer(p1, []), put_answer(p2, [])]) == (0, 0)
    assert moved_parts([]) == (0, 0)


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
        lambda cfg, **k: {
            "items": [
                {
                    "id": "a1",
                    "name": "BCP",
                    "is_archived": False,
                    "opening_balance_transaction_id": None,
                }
            ]
        },
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


def test_the_account_picker_shows_the_engines_order(fake_client, monkeypatch):
    """`b` lists the accounts exactly as `GET /accounts` returned them, through
    the shared reference read — not alphabetical, not by `sort_order`, the
    person after every bank."""
    _stub_ledger(monkeypatch)
    monkeypatch.setattr(tx_mod, "load_quickadd_refs", load_quickadd_refs)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_ACCOUNTS)
    )
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        await _open(app, pilot, screen)
        await pilot.press("b")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        modal = app.screen
        assert [name for _, name in modal._pool] == ENGINE_ORDER_NAMES
        shown = render_text(modal.query_one("#candidates").render(), width=160)
        assert in_order(shown, ENGINE_ORDER_NAMES)

    run_app(scenario, size=(160, 30))


def test_the_category_picker_shows_the_engines_order_pendiente_in_it(fake_client, monkeypatch):
    """`c` lists the categories as `GET /categories` returned them, through the
    shared reference read: @Pendiente in the engine's place (the Edit form's
    CATEGORY offers the same list) and @Opening never."""
    _stub_ledger(monkeypatch)
    monkeypatch.setattr(tx_mod, "load_quickadd_refs", load_quickadd_refs)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_ACCOUNTS)
    )
    rows = [
        {"id": "kor", "name": "KORAKUEN", "is_system": False},
        {"id": "pend", "name": "@Pendiente", "is_system": True, "system_key": "pending"},
        {"id": "open", "name": "@Opening", "is_system": True, "system_key": "opening_balance"},
        {"id": "hog", "name": "HOGAR", "is_system": False},
    ]
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole(rows))
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))
    names = ["KORAKUEN", "@Pendiente", "HOGAR"]

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        await _open(app, pilot, screen)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        modal = app.screen
        assert [name for _, name in modal._pool] == names
        shown = render_text(modal.query_one("#candidates").render(), width=160)
        assert in_order(shown, names) and "@Opening" not in shown

    run_app(scenario, size=(160, 30))


def test_b_offers_no_archived_account_so_no_body_names_one(fake_client, monkeypatch):
    """The engine refuses a `PUT` that sends an archived account's id as
    `account_id` (contract: POST /v1/accounts/{account_id}/archive), so `b`
    lists no archived account, bank or person, through the shared reference
    read, even on a row that sits on one, and every PUT names the picked active
    account."""
    archived = [
        {**ENGINE_ORDER_ACCOUNTS[0], "id": "accX", "name": "Retired Bank", "is_archived": True},
        {**ENGINE_ORDER_ACCOUNTS[-1], "id": "perX", "name": "Retired Friend", "is_archived": True},
    ]
    _stub_ledger(monkeypatch, [{**ITEMS[0], "account_id": "accX"}])
    monkeypatch.setattr(tx_mod, "load_quickadd_refs", load_quickadd_refs)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole([*ENGINE_ORDER_ACCOUNTS, *archived]),
    )
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        await _open(app, pilot, screen)
        await pilot.press("b")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        assert [name for _, name in app.screen._pool] == ENGINE_ORDER_NAMES
        await pilot.press("a", "l", "f", "a", "enter")
        await wait_for(pilot, lambda: fake_client.puts)
        assert fake_client.puts == [
            ("/transactions/t1", {"account_id": "acc-alfa", "reconciliation_id": None})
        ]

    run_app(scenario, size=(160, 30))


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
    _answer_moves(fake_client, [ITEMS[0], ITEMS[2]])

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


def test_a_refused_row_note_closes_with_the_next_step(fake_client, monkeypatch):
    """`b` onto an account that already holds row 2's operation number: the
    "Refused" note names the row, gives the engine's words, and closes with the
    line saying what to do (screen 4); the other rows still move."""
    _stub_ledger(monkeypatch)
    toasts: list[tuple[str, str]] = []
    real_put = fake_client.put

    def put(path, json_body=None):
        if path.endswith("/t2"):
            raise EngineError(
                "CONFLICT",
                "Operation code already exists.",
                {"operation_code": "Must be unique per account."},
                409,
                {},
                {"operation_code": "OPERATION_CODE_EXISTS"},
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
        assert refused == (
            "row 2: CONFLICT — Operation code already exists.\n"
            "  operation_code: Must be unique per account.\n\n"
            "That account already has a row with this operation number: "
            "look there for a duplicate."
        )

    run_app(scenario, size=(120, 30))


def test_a_row_on_an_archived_account_is_refused_in_the_engine_words_alone(
    fake_client, monkeypatch
):
    """Screen 3 A of expense-world-archived-account.html: `b` over a selection
    that holds a row of an account archived since the ledger was read. The
    "Refused" note names the row and gives the engine's words, each key it
    refused with its words, and no line of the app's; the other rows still
    move, and the refused row stays selected, as every refused row does."""
    _stub_ledger(monkeypatch)
    toasts: list[tuple[str, str]] = []
    real_put = fake_client.put

    def put(path, json_body=None):
        if path.endswith("/t2"):
            raise archived_refusal(422, ARCHIVED_PUT_WORDS, *json_body)
        return real_put(path, json_body=json_body)

    fake_client.put = put
    _answer_moves(fake_client, [ITEMS[0], ITEMS[2]])

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
        assert [m for t, m in toasts if t == "Refused"] == [
            f"row 2: VALIDATION_ERROR — {ARCHIVED_PUT_WORDS}\n"
            f"  account_id: {ARCHIVED_FIELD_WORDS}\n"
            f"  reconciliation_id: {ARCHIVED_FIELD_WORDS}"
        ]
        assert ("", "2 rows → BCP Oro PEN") in toasts
        await wait_for(pilot, lambda: not screen._bulk_busy)
        assert screen._selected == {"t2"}

    run_app(scenario, size=(120, 30))


@pytest.mark.parametrize(
    ("key", "typed", "field", "reason", "words", "line"),
    [
        (
            "b",
            "oro",
            "account_id",
            "OPENING_BALANCE_ACCOUNT_FIXED",
            "An opening balance cannot move to another account.",
            "To move an opening balance, set it on the other account's Edit form.",
        ),
        (
            "c",
            "kor",
            "category_id",
            "OPENING_BALANCE_CATEGORY_FIXED",
            "An opening balance must stay in @Opening.",
            "An opening balance always stays in @Opening.",
        ),
        # pending-hashtag-manage 7 B: `com` + ↵ picks #COMIDA, the second ↵ applies
        (
            "h",
            ["c", "o", "m", "enter"],
            "hashtag_ids",
            "OPENING_BALANCE_NOT_TAGGED",
            "Must be empty: an opening balance carries no hashtag.",
            "Leave the opening balance out of the selection.",
        ),
    ],
    ids=["b", "c", "h"],
)
def test_an_opening_balance_in_the_selection_is_refused_with_where_to_change_it(
    fake_client, monkeypatch, key, typed, field, reason, words, line
):
    """Opening-balance rows 2B, and pending-hashtag-manage 7 B: `b`, `c` or `h`
    over a selection holding an opening balance sends every row as usual; the
    engine refuses that one
    (contract: PUT /v1/transactions/{transaction_id}, "Opening balances stay put"),
    its note is the engine's words and then the line saying where the opening
    balance is changed, the other rows go, and the refused row stays selected."""
    items = [*ITEMS[:2], {**ITEMS[2], "title": "Saldo inicial", "category_id": "opn"}]
    _stub_ledger(monkeypatch, items)
    toasts: list[tuple[str, str]] = []
    real_put = fake_client.put

    def put(path, json_body=None):
        if path.endswith("/t3"):
            raise EngineError(
                "VALIDATION_ERROR",
                "Validation failed.",
                {field: words},
                422,
                {},
                {field: reason},
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
        await pilot.press("a", key)
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        await pilot.press(*typed, "enter")
        await wait_for(pilot, lambda: any(t == "Refused" for t, _m in toasts))
        assert [p for p, _b in fake_client.puts] == ["/transactions/t1", "/transactions/t2"]
        refused = next(m for t, m in toasts if t == "Refused")
        assert refused == (
            f"row 3: VALIDATION_ERROR — Validation failed.\n  {field}: {words}\n\n{line}"
        )
        await wait_for(pilot, lambda: not screen._bulk_busy)
        assert screen._selected == {"t3"}

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
    """The receipt counts what the engine's answers list: t1 and t3 moved, t1
    left its reconciliation; t2 was already on acc2, so its answer lists nothing."""
    _stub_ledger(monkeypatch, MIXED)
    _answer_moves(fake_client, [MIXED[0], MIXED[2]], left=("t1",))
    _answer_unchanged(fake_client, MIXED[1])
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
        # t3 was in no reconciliation, t2 never moved: two rows, one left
        assert toasts[0] == "2 rows → BCP Oro PEN · 1 left its reconciliation"

    run_app(scenario, size=(120, 30))


def test_b_onto_the_rows_own_account_never_unassigns(fake_client, monkeypatch):
    """Nothing moves, and the engine's answer lists no part: no receipt is shown."""
    _stub_ledger(monkeypatch, MIXED)
    _answer_unchanged(fake_client, MIXED[0])
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
        await wait_for(pilot, lambda: not screen._bulk_busy)
        await pilot.pause()
        assert toasts == []

    run_app(scenario, size=(120, 30))


def test_b_that_moves_nothing_still_names_its_refusal(fake_client, monkeypatch):
    """t1 and t2 onto acc2: t1 is refused by a completed reconciliation, t2 is
    already there and its answer lists no part. Nothing moved, so no receipt;
    the refusal still names row 1."""
    _stub_ledger(monkeypatch, MIXED)
    _answer_unchanged(fake_client, MIXED[1])
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
    toasts: list[tuple[str, str]] = []

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        monkeypatch.setattr(
            screen,
            "notify",
            lambda message, title="", **kw: toasts.append((title, str(message))),
        )
        await _open(app, pilot, screen)
        await pilot.press("space", "down", "space", "b")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        await pilot.press("o", "r", "o", "enter")
        await wait_for(pilot, lambda: not screen._bulk_busy)
        await pilot.pause()
        assert [p for p, _b in fake_client.puts] == ["/transactions/t2"]
        assert len(toasts) == 1
        title, message = toasts[0]
        assert title == "Refused"
        assert message.startswith("row 1: ") and "Locked by completed reconciliation." in message
        assert screen._selected == {"t1"}

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
    _answer_unchanged(fake_client, MIXED[1])
    _answer_moves(fake_client, [MIXED[2]])

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
        # t1 refused, t2 already on acc2: only t3 moved, and it was in none
        assert ("", "1 row → BCP Oro PEN") in toasts
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


# ---- `h` and the pending hashtag ----------------------------------------------
# (contract: PUT /v1/transactions/{transaction_id})
# (contract: "Transactions (Ledger)", "The pending hashtag is never combined")

PENDING_TAG = ("hp", "Pendiente")
TAGGED_REFS = QuickAddRefs(
    accounts=ACCOUNTS,
    categories=CATEGORIES,
    hashtags=[*HASHTAGS, PENDING_TAG],
    account_names={i: n for i, n, _c in ACCOUNTS},
    category_names=dict(CATEGORIES + [PENDING]),
    hashtag_names=dict([*HASHTAGS, PENDING_TAG]),
    pending=PENDING,
    pending_hashtag=PENDING_TAG,
    pickable_categories=PICKABLE,
)
ON_PENDING = [{**it, "hashtag_ids": ["hp"]} for it in ITEMS]


def _pick_tags(fake_client, monkeypatch, typed, *, settle):
    """`h` on the cursor row (row 1, on the pending hashtag), each of `typed`
    picked, then applied; returns the toasts once `settle(toasts)` holds."""
    _stub_ledger(monkeypatch, ON_PENDING)
    monkeypatch.setattr(tx_mod, "load_quickadd_refs", lambda cfg, **kw: TAGGED_REFS)
    toasts: list[tuple[str, str]] = []

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        monkeypatch.setattr(
            screen,
            "notify",
            lambda message, title="", **kw: toasts.append((title, str(message))),
        )
        await _open(app, pilot, screen)
        await pilot.press("h")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        modal = app.screen
        for text in typed:
            before = len(modal._picked)
            await pilot.press(*text, "enter")
            await wait_for(pilot, lambda n=before + 1: len(modal._picked) == n)
        await pilot.press("enter")
        await wait_for(pilot, lambda: settle(toasts))
        await wait_for(pilot, lambda: not screen._bulk_busy)

    run_app(scenario, size=(120, 30))
    return toasts


def test_h_on_a_pending_row_sends_only_the_real_hashtag(fake_client, monkeypatch):
    """The pending hashtag picked beside COMIDA is dropped: the PUT names COMIDA
    alone, and the receipt says what was written."""
    toasts = _pick_tags(fake_client, monkeypatch, ["pend", "com"], settle=bool)
    assert fake_client.puts == [("/transactions/t1", {"hashtag_ids": ["h1"]})]
    assert ("", "1 row → #COMIDA") in toasts


def test_h_with_the_pending_hashtag_alone_sends_it_alone(fake_client, monkeypatch):
    """Alone it is a whole set the engine accepts, so it goes as picked."""
    _pick_tags(fake_client, monkeypatch, ["pend"], settle=bool)
    assert fake_client.puts == [("/transactions/t1", {"hashtag_ids": ["hp"]})]


@pytest.mark.parametrize(("code", "status", "reason", "line"), HASHTAG_REFUSALS)
def test_a_hashtag_refusal_on_h_shows_as_sent(fake_client, monkeypatch, code, status, reason, line):
    """The "Refused" note names the row, then the engine's words whole and
    its line if the reason has one."""
    err = hashtag_refusal(code, status, reason)
    fake_client.errors["PUT"] = err
    toasts = _pick_tags(
        fake_client, monkeypatch, ["com"], settle=lambda t: any(x == "Refused" for x, _ in t)
    )
    assert ("Refused", f"row 1: {refusal_text(err, line)}") in toasts


# ---- the bulk keys on parts of a split purchase -----------------------------
# A part's category and hashtags are its own, while its account belongs to its
# bank line: a `PUT` of `account_id` on one part moves every part in the engine's
# one write (contract: PUT /v1/transactions/{transaction_id}, "Line fields"). So
# `c`, `h` and `b` send one `PUT` per selected row and nothing for the other
# part: the engine moves the line, the app fans nothing out. No body carries a
# `version`: the `PUT` takes none (contract: PUT /v1/transactions/{transaction_id}).


def _part(tx_id: str, title: str, amount: int, line: str, recon: str | None) -> dict:
    return {
        "id": tx_id,
        "title": title,
        "description": None,
        "amount_cents": amount,
        "date": "2026-10-11T05:00:00Z",
        "account_id": "acc1",
        "category_id": "pend",
        "hashtag_ids": ["hp"],
        "bank_line_id": line,
        "line_code": line_code_of(line),
        "statement_line": None,
        "reconciliation_id": recon,
    }


#: Row 1 an ordinary row, rows 2 and 3 the two parts of FARMACIA, a purchase in a
#: draft reconciliation.
PURCHASE = [
    _part("t-net", "NETFLIX.COM", -4490, "bl-net", None),
    _part("p1", "FARMACIA", -6000, "bl-farm", "rec-draft"),
    _part("p2", "FARMACIA", -4000, "bl-farm", "rec-draft"),
]

#: What each key picks in its picker, and the body it sends for one row: `h`
#: picks the pending hashtag beside COMIDA, and only COMIDA goes.
ON_PARTS = {
    "c": (["kor"], {"category_id": "kor"}),
    "h": (["pend", "com", ""], {"hashtag_ids": ["h1"]}),
    "b": (["oro"], {"account_id": "acc2", "reconciliation_id": None}),
}


def _answer_line_moves(fake_client, rows: list[dict]) -> None:
    """Each `PUT` answers as the engine answers a move onto acc2: the first on a
    bank line lists every part of that line after the move, a part that was in a
    reconciliation flagged as leaving it; a later `PUT` on the same line finds it
    moved and lists none (contract: PUT /v1/transactions/{transaction_id}, "Response")."""
    real_put = fake_client.put
    by_id = {row["id"]: row for row in rows}
    moved_lines: set[str] = set()

    def put(path, json_body=None):
        real_put(path, json_body=json_body)
        named = by_id[path.rsplit("/", 1)[-1]]
        line = named["bank_line_id"]
        if line in moved_lines:
            return put_answer(_moved(named), [])
        moved_lines.add(line)
        parts = [row for row in rows if row["bank_line_id"] == line]
        left = tuple(part["id"] for part in parts if part["reconciliation_id"])
        return put_answer(_moved(named), [_moved(part) for part in parts], left=left)

    fake_client.put = put


def _bulk_on_parts(fake_client, monkeypatch, key: str, select: list[str], cursor: str):
    """The ledger over PURCHASE, the cursor on `cursor`, `select` selected, then
    `key` and its pick; a `b` move is answered as the engine answers it
    (`_answer_line_moves`). Returns (the toasts, the ledger reads before the write,
    the reads after the fresh reload, the cursor's index and key once it is in,
    and what was asked of the engine between the pick and the receipt: the ledger
    reads and the client's calls)."""
    calls, counts = fake_ledger(monkeypatch, list(PURCHASE))
    if key == "b":
        _answer_line_moves(fake_client, PURCHASE)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(NAMES))
    for name in ("load_category_name_map", "load_hashtag_name_map"):
        monkeypatch.setattr(tx_mod, name, lambda: NAMES)
    monkeypatch.setattr(tx_mod, "load_quickadd_refs", lambda cfg, **kw: TAGGED_REFS)
    typed, _body = ON_PARTS[key]
    seen: dict = {}

    async def scenario(pilot, app):
        screen = TransactionsScreen()

        def notify(message, **kw):
            if "toasts" not in seen:  # the receipt: what was asked before it
                seen["asked"] = (calls[seen["reads"] :], fake_client.calls[seen["sent"] :])
            seen.setdefault("toasts", []).append(str(message))

        monkeypatch.setattr(screen, "notify", notify)
        await _open(app, pilot, screen)
        listing = screen.query_one(CursorList)
        for row in select:
            listing.set_cursor(listing.index_of(row))
            await pilot.press("space")
        await wait_for(pilot, lambda: screen._selected == set(select))
        listing.set_cursor(listing.index_of(cursor))
        await pilot.pause()
        await pilot.press(key)
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        title = "row" if len(select) <= 1 else "rows"
        assert app.screen._title.endswith(f"for {max(len(select), 1)} {title}")
        reads = len(calls)
        seen.update(reads=reads, sent=len(fake_client.calls))
        for text in typed:
            await pilot.press(*text, "enter")
        await wait_for(pilot, lambda: not isinstance(app.screen, PickerModal))
        # the fresh read recounts: the second count, and its list settled
        await wait_for(pilot, lambda: len(counts) == 2 and not screen._bulk_busy)
        await wait_for(pilot, lambda: list_ready(app) and len(screen._rows) == len(PURCHASE))
        listing = screen.query_one(CursorList)
        seen.update(
            reads=reads,
            fresh=calls[reads:],
            cursor=(listing.cursor_index, listing.cursor_key),
            selected=set(screen._selected),
        )

    run_app(scenario, size=(120, 30))
    return seen


@pytest.mark.parametrize("key", ["c", "h", "b"])
@pytest.mark.parametrize("select", [[], ["p2"]], ids=["cursor", "selected"])
def test_c_h_b_on_one_part_send_only_that_part_then_read_fresh(
    fake_client, monkeypatch, key, select
):
    """The cursor on FARMACIA's second part, with it selected or not: the key's
    one `PUT` names that part alone, never the first part or the ordinary row,
    and `b` sends it `account_id` once — the engine moves the purchase whole.
    Then the ledger reads fresh: the newest ten, the cursor on row 1."""
    _typed, body = ON_PARTS[key]
    seen = _bulk_on_parts(fake_client, monkeypatch, key, select, cursor="p2")
    assert fake_client.puts == [("/transactions/p2", body)]
    assert seen["fresh"][0]["after"] is None and seen["fresh"][0]["limit"] == 10
    assert seen["cursor"] == (0, "t-net")
    assert seen["selected"] == set()


@pytest.mark.parametrize("key", ["c", "h", "b"])
def test_c_h_b_with_both_parts_selected_send_each_part_its_own_put(fake_client, monkeypatch, key):
    """Both parts of FARMACIA selected: one `PUT` per part, in list order, each
    the body one row gets. For `b` the second `PUT` names the part the first one
    already moved, with the same body built from the read before the move, and
    no `version`, so no stale-version refusal can come of it; the engine accepts
    it (tests/contract/test_bank_lines.py
    `test_an_account_move_on_one_part_moves_the_whole_line`)."""
    _typed, body = ON_PARTS[key]
    seen = _bulk_on_parts(fake_client, monkeypatch, key, ["p1", "p2"], cursor="p1")
    assert fake_client.puts == [("/transactions/p1", body), ("/transactions/p2", body)]
    assert not any("version" in sent for _path, sent in fake_client.puts)
    assert seen["fresh"][0]["after"] is None and seen["fresh"][0]["limit"] == 10
    assert seen["cursor"] == (0, "t-net")
    if key == "b":
        assert seen["toasts"][0] == "2 rows → BCP Oro PEN · 2 left their reconciliation"


# ---- b: the receipt counts what the engine says moved ------------------------
# Each `PUT` answers with `changed_parts`: every part of the line whose line field
# the write changed, each flagged `left_reconciliation` when it left one
# (contract: PUT /v1/transactions/{transaction_id}, "Response"). The receipt
# counts the distinct parts across the answers, and nothing is read to count them.


def _asked_nothing_but_the_puts(seen: dict) -> None:
    """Between the pick and the receipt: no ledger read, no bank-line read, no
    `GET` of any kind — only the move's `PUT`s."""
    ledger_reads, client_calls = seen["asked"]
    assert ledger_reads == []
    assert [method for method, _path, _body in client_calls] == ["PUT"] * len(client_calls)


@pytest.mark.parametrize("select", [[], ["p2"]], ids=["cursor", "selected"])
def test_b_on_one_part_of_a_reconciled_line_counts_both_parts_and_both_leavings(
    fake_client, monkeypatch, select
):
    """FARMACIA is 60 + 40 in a draft reconciliation. `b` on its second part sends
    one `PUT`; the engine moves the whole line and lists both parts as leaving
    their reconciliation, so the receipt says 2 rows and 2 left."""
    seen = _bulk_on_parts(fake_client, monkeypatch, "b", select, cursor="p2")
    assert fake_client.puts == [("/transactions/p2", ON_PARTS["b"][1])]
    assert seen["toasts"][0] == "2 rows → BCP Oro PEN · 2 left their reconciliation"
    _asked_nothing_but_the_puts(seen)


def test_b_on_both_parts_counts_each_part_once(fake_client, monkeypatch):
    """Both parts selected: two `PUT`s, the first moving the line and listing both
    parts, the second listing none. The receipt says 2 rows, not 3 or 4."""
    seen = _bulk_on_parts(fake_client, monkeypatch, "b", ["p1", "p2"], cursor="p1")
    assert [path for path, _body in fake_client.puts] == ["/transactions/p1", "/transactions/p2"]
    assert seen["toasts"][0] == "2 rows → BCP Oro PEN · 2 left their reconciliation"
    _asked_nothing_but_the_puts(seen)


def test_b_on_a_one_part_line_in_no_reconciliation_says_nothing_of_leaving(
    fake_client, monkeypatch
):
    """NETFLIX.COM is one part in no reconciliation: its answer lists it, not
    flagged, so the receipt says 1 row and nothing about leaving one."""
    seen = _bulk_on_parts(fake_client, monkeypatch, "b", [], cursor="t-net")
    assert fake_client.puts == [("/transactions/t-net", ON_PARTS["b"][1])]
    assert seen["toasts"][0] == "1 row → BCP Oro PEN"
    _asked_nothing_but_the_puts(seen)


def test_b_counts_only_the_answers_that_landed(fake_client, monkeypatch):
    """Both parts selected, the first `PUT` refused: the second moves the line and
    its answer lists both parts, so the receipt counts them; the refused part is
    named and stays selected."""
    _answer_line_moves(fake_client, PURCHASE)
    answering = fake_client.put

    def put(path, json_body=None):
        if path.endswith("/p1"):
            raise EngineError("CONFLICT", "Operation code already exists.", None, 409, {})
        return answering(path, json_body=json_body)

    fake_client.put = put
    calls, _counts = fake_ledger(monkeypatch, list(PURCHASE))
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(NAMES))
    for name in ("load_category_name_map", "load_hashtag_name_map"):
        monkeypatch.setattr(tx_mod, name, lambda: NAMES)
    monkeypatch.setattr(tx_mod, "load_quickadd_refs", lambda cfg, **kw: TAGGED_REFS)
    toasts: list[tuple[str, str]] = []

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        monkeypatch.setattr(
            screen,
            "notify",
            lambda message, title="", **kw: toasts.append((title, str(message))),
        )
        await _open(app, pilot, screen)
        listing = screen.query_one(CursorList)
        for row in ("p1", "p2"):
            listing.set_cursor(listing.index_of(row))
            await pilot.press("space")
        await pilot.press("b")
        await wait_for(pilot, lambda: isinstance(app.screen, PickerModal))
        await pilot.press("o", "r", "o", "enter")
        await wait_for(pilot, lambda: any(t == "Refused" for t, _m in toasts))
        await wait_for(pilot, lambda: not screen._bulk_busy)
        assert ("", "2 rows → BCP Oro PEN · 2 left their reconciliation") in toasts
        assert next(m for t, m in toasts if t == "Refused").startswith("row 2: CONFLICT")
        assert screen._selected == {"p1"}

    run_app(scenario, size=(120, 30))
