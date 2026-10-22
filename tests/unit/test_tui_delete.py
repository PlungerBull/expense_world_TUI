"""`d` deletes the row under the cursor — Accounts, Categories, Hashtags, the ledger.

Screens: docs/mockups/expense-world-delete.html (1, 2, 3A, 4B, 5). The DELETE
goes through the real HTTP client against a respx-mocked engine, so the
idempotency key and the error envelope are the client's own; the lists' reads
are stubbed. Every refusal's words here are stand-ins: the line under them is
chosen by the engine's code and reason, never by its words.
"""

import re
import threading

import httpx
import pytest
import respx

import expense.tui.screens.transactions as tx_mod
from expense.errors import EngineError
from expense.reads import AccountIndex
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.categories import CategoriesScreen
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.screens.help import screen_inventory
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.transactions import LedgerFilter, TransactionsScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ARCHIVED_FIELD_WORDS,
    ENGINE_URL,
    archived_refusal,
    archived_words,
    bank_line_row,
    error_response,
    fake_ledger,
    import_part,
    line_code_of,
    refusal_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

SIZE = (120, 40)  # the manage window holds its 20-row cap, so row 22 is page 2


def _account(i: int) -> dict:
    return {
        "id": f"a{i}",
        "name": f"Cuenta {i:02d}",
        "is_person": i == 22,
        "is_archived": False,
        "currency_code": "PEN",
        "color": None,
        "current_balance_cents": -15000 if i == 22 else 0,
        "opening_balance_transaction_id": None,
    }


def _category(i: int) -> dict:
    return {"id": f"c{i}", "name": f"CAT {i:02d}", "is_system": False, "color": None}


def _hashtag(i: int) -> dict:
    """Row 24 is the built-in pending hashtag (its `system_key`), where the
    delete question says a transaction left with no hashtag goes."""
    if i == 24:
        return {"id": "h24", "name": "Pendiente", "system_key": "pending"}
    return {"id": f"h{i}", "name": f"tag-{i:02d}", "system_key": None}


# screen, the reads function it calls, row builder, engine collection,
# the question for row 22, the note after the delete
MANAGE = {
    "accounts": (
        AccountsScreen,
        "fetch_accounts",
        _account,
        "Delete this account?",
        "Cuenta 22 · person · PEN · -150.00\n"
        "It is for an account made by mistake: no screen can bring it back.",
        "Account deleted.",
    ),
    "categories": (
        CategoriesScreen,
        "fetch_categories",
        _category,
        "Delete this category?",
        "CAT 22\nIt is for a category made by mistake: no screen can bring it back.",
        "Category deleted.",
    ),
    "hashtags": (
        HashtagsScreen,
        "fetch_hashtags",
        _hashtag,
        "Delete this hashtag?",
        "#tag-22\nIt is also taken off every transaction that carries it; "
        "one with no other hashtag goes to #Pendiente. No screen can bring it back.",
        "Hashtag deleted.",
    ),
}


def _stub_manage(monkeypatch, resource: str, rows: list) -> None:
    """The list reads `rows` afresh on every load, so dropping a row from it
    plays the delete the engine applied."""
    _screen, fetch, *_ = MANAGE[resource]
    monkeypatch.setattr(f"expense.reads.{fetch}", lambda *a, **k: whole(list(rows)))


def _record_notes(monkeypatch, screen) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        screen, "notify", lambda message, title="", **kw: notes.append((title, str(message)))
    )
    return notes


def _footer(screen) -> list[str]:
    """The footer's entries, in order, as `key Description`."""
    return [
        f"{a.binding.key} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


# ---- 1 · the key, on four screens -------------------------------------------


@pytest.mark.parametrize("resource", sorted(MANAGE))
def test_d_asks_then_deletes_and_the_list_starts_over(configured, monkeypatch, resource):
    """`d` on row 22 (page 2) asks the drawn question; `y` sends one DELETE with
    an idempotency key; the list reads again from page 1, cursor on row 1, and
    the note says what went."""
    make, _fetch, build, title, message, done = MANAGE[resource]
    rows = [build(i) for i in range(25)]
    _stub_manage(monkeypatch, resource, rows)

    def engine_deletes(request):
        rows[:] = [r for r in rows if r["id"] != f"{resource[0]}22"]
        return httpx.Response(200, json={})

    async def scenario(pilot, app):
        screen = make()
        notes = _record_notes(monkeypatch, screen)
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        listing = screen.query_one(CursorList)
        listing.set_cursor(listing.index_of(f"{resource[0]}22"))
        # a re-selection left by an earlier toggle is dropped by a delete that went through
        screen._restore_key = f"{resource[0]}3"
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert (app.screen._title, app.screen._message) == (title, message)
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", done) in notes)
        await wait_for(pilot, lambda: len(screen._by_id) == 24)
        listing = screen.query_one(CursorList)
        assert listing.cursor_index == 0
        assert listing.page_status == "rows 1-20 of 24 · page 1 of 2"
        return notes

    with respx.mock() as engine:
        route = engine.delete(f"{ENGINE_URL}/v1/{resource}/{resource[0]}22").mock(
            side_effect=engine_deletes
        )
        run_app(scenario, size=SIZE)
    assert route.call_count == 1
    assert route.calls.last.request.headers["X-Idempotency-Key"]


@pytest.mark.parametrize("key", ["n", "escape", "enter"])
@pytest.mark.parametrize("resource", sorted(MANAGE))
def test_any_other_answer_cancels_and_sends_nothing(configured, monkeypatch, resource, key):
    make, _fetch, build, *_ = MANAGE[resource]
    _stub_manage(monkeypatch, resource, [build(i) for i in range(3)])

    async def scenario(pilot, app):
        screen = make()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press(key)
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert len(screen._by_id) == 3

    with respx.mock(assert_all_called=False) as engine:
        route = engine.delete(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not route.called


@pytest.mark.parametrize("resource", sorted(MANAGE))
def test_d_is_off_on_an_empty_list(configured, monkeypatch, resource):
    make, *_ = MANAGE[resource]
    _stub_manage(monkeypatch, resource, [])

    async def scenario(pilot, app):
        screen = make()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen.check_action("delete", ()) is None
        await pilot.press("d")
        await pilot.pause()
        assert app.screen is screen

    run_app(scenario, size=SIZE)


@pytest.mark.parametrize(
    ("resource", "tail"),
    [
        ("accounts", ["n New", "e Edit", "a Archive", "t Make person", "d Delete"]),
        ("categories", ["n New", "e Edit", "d Delete"]),
        ("hashtags", ["n New", "e Edit", "d Delete"]),
    ],
)
def test_footer_and_card_end_with_d_delete(configured, monkeypatch, resource, tail):
    """Screen 1: `d Delete` is the last of the screen's own keys in the footer,
    and the `?` card lists it."""
    make, _fetch, build, *_ = MANAGE[resource]
    _stub_manage(monkeypatch, resource, [build(1)])

    async def scenario(pilot, app):
        screen = make()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.pause()
        assert _footer(screen)[-len(tail) :] == tail
        _, groups = screen_inventory(screen)
        own = next(g for g in groups if g.title == "This screen")
        assert ("d", "Delete") in [(row.keys, row.description) for row in own.rows]

    run_app(scenario, size=SIZE)


# ---- the ledger: 3A ----------------------------------------------------------

LEDGER = [
    {
        "id": f"t{i}",
        "title": f"Compra {i:02d}",
        "description": None,
        "amount_cents": -2800,
        "date": "2026-10-10T00:00:00Z",
        "account_id": "acc1",
        "category_id": "pend",
        "hashtag_ids": [],
        "bank_line_id": f"bl{i}",
        "line_code": line_code_of(f"bl{i}"),
        "statement_line": None,
    }
    for i in range(1, 26)
]


def _one_part_lines(engine) -> respx.Route:
    """`GET /bank-lines/{id}` for every `LEDGER` row's line, each never split:
    one part, `part_count` 1 (contract: GET /v1/bank-lines/{bank_line_id})."""

    def read(request):
        line = request.url.path.rsplit("/", 1)[-1]
        row = next(r for r in LEDGER if r["bank_line_id"] == line)
        part = import_part(
            row["id"],
            row["amount_cents"],
            account_id="acc1",
            line=line,
            day=row["date"][:10],
            title=row["title"],
        )
        body = bank_line_row(line, [part], net_cents=row["amount_cents"], account_id="acc1")
        return httpx.Response(200, json=body)

    pattern = rf"{re.escape(ENGINE_URL)}/v1/bank-lines/bl\d+$"
    return engine.get(url__regex=pattern).mock(side_effect=read)


NAMES = {"acc1": "Sueldo Soles", "pend": "@Pendiente"}
FILTER = LedgerFilter("category", "pend", "@Pendiente")


def _stub_ledger(monkeypatch, rows: list) -> list:
    calls, _counts = fake_ledger(monkeypatch, rows)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(NAMES))
    for name in ("load_category_name_map", "load_hashtag_name_map"):
        monkeypatch.setattr(tx_mod, name, lambda: NAMES)
    return calls


async def _open_ledger(pilot, app, screen) -> None:
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    screen.query_one(CursorList).focus()
    await pilot.pause()


@pytest.mark.parametrize("flt", [None, FILTER], ids=["whole", "filtered"])
def test_d_on_the_ledger_deletes_the_cursor_row_and_reads_the_newest_ten(
    configured, monkeypatch, flt
):
    rows = list(LEDGER)
    calls = _stub_ledger(monkeypatch, rows)

    def engine_deletes(request):
        rows[:] = [r for r in rows if r["id"] != "t11"]
        return httpx.Response(200, json={})

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=flt)
        notes = _record_notes(monkeypatch, screen)
        await _open_ledger(pilot, app, screen)
        await pilot.press("pagedown")  # 20 loaded, the cursor on row 11
        await wait_for(pilot, lambda: len(screen._rows) == 20)
        assert screen.query_one(CursorList).cursor_key == "t11"
        assert "d Delete" in _footer(screen)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == "Delete this transaction?"
        assert app.screen._message == (
            "Compra 11 · -28.00 · 2026-10-10 · Sueldo Soles\n"
            "It leaves every balance and report, and no screen can bring it back."
        )
        reads = len(calls)
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", "Transaction deleted.") in notes)
        await wait_for(pilot, lambda: len(calls) > reads and len(screen._rows) == 10)
        assert calls[-1]["after"] is None and calls[-1]["limit"] == 10
        assert screen.query_one(CursorList).cursor_index == 0
        assert "t11" not in screen._by_id

    with respx.mock() as engine:
        lines = _one_part_lines(engine)
        route = engine.delete(f"{ENGINE_URL}/v1/transactions/t11").mock(side_effect=engine_deletes)
        run_app(scenario, size=SIZE)
    assert [c.request.url.path for c in lines.calls] == ["/v1/bank-lines/bl11"]
    assert route.call_count == 1
    assert route.calls.last.request.headers["X-Idempotency-Key"]


def test_d_is_off_while_ledger_rows_are_selected(configured, monkeypatch):
    """3A: with a selection `d` leaves the footer and does nothing; `esc` clears
    the selection and it is back. The `?` card always lists it."""
    _stub_ledger(monkeypatch, list(LEDGER[:3]))

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await _open_ledger(pilot, app, screen)
        await pilot.press("space")
        await pilot.pause()
        assert screen._selected
        assert "d Delete" not in _footer(screen)
        await pilot.press("d")
        await pilot.pause()
        assert app.screen is screen  # no question
        await pilot.press("a")  # every loaded row: still off
        await pilot.press("d")
        await pilot.pause()
        assert app.screen is screen
        await pilot.press("escape")  # selection cleared
        await pilot.pause()
        assert not screen._selected
        assert _footer(screen)[-1] == "d Delete"
        _, groups = screen_inventory(screen)
        own = next(g for g in groups if g.title == "This screen")
        assert ("d", "Delete") in [(row.keys, row.description) for row in own.rows]

    with respx.mock(assert_all_called=False) as engine:
        route = engine.delete(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not route.called


@pytest.mark.parametrize("key", ["n", "escape", "enter"])
def test_any_other_answer_on_the_ledger_sends_nothing(configured, monkeypatch, key):
    _stub_ledger(monkeypatch, list(LEDGER[:3]))

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await _open_ledger(pilot, app, screen)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press(key)
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert len(screen._rows) == 3 and not screen._selected

    with respx.mock(assert_all_called=False) as engine:
        _one_part_lines(engine)
        route = engine.delete(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not route.called


# ---- 4B · the engine says no -------------------------------------------------
# Each refusal carries `fields` and `reasons` keyed by the thing refused
# (contract: "Base Conventions", "`fields` and `reasons` semantics"); the line
# under the engine's words is chosen by the code and the reason alone.


@pytest.mark.parametrize(
    ("make", "fetch", "row", "path", "status", "code", "words", "key", "reason", "note"),
    [
        (
            AccountsScreen,
            "fetch_accounts",
            _account(1),
            "accounts/a1",
            409,
            "CONFLICT",
            "Account has active transactions. Archive instead.",
            "account_id",
            "HAS_TRANSACTIONS",
            "CONFLICT — Account has active transactions. Archive instead.\n"
            "  account_id: stand-in field words\n\n"
            "To retire it instead, archive it: press a.",
        ),
        (
            CategoriesScreen,
            "fetch_categories",
            _category(1),
            "categories/c1",
            409,
            "CONFLICT",
            "Category has transactions.",
            "category_id",
            "HAS_TRANSACTIONS",
            "CONFLICT — Category has transactions.\n"
            "  category_id: stand-in field words\n\n"
            "Move its transactions to another category first.",
        ),
        # `d` is not offered on a system category (pending-hashtag-manage 2 A);
        # the refusal still shows its line on a row the list read as ordinary
        (
            CategoriesScreen,
            "fetch_categories",
            _category(1),
            "categories/c1",
            403,
            "FORBIDDEN",
            "Operation not allowed.",
            "category_id",
            "SYSTEM_CATEGORY",
            "FORBIDDEN — Operation not allowed.\n"
            "  category_id: stand-in field words\n\n"
            "System categories cannot be renamed or deleted.",
        ),
        # the same for the pending hashtag (pending-hashtag-manage 4 B)
        (
            HashtagsScreen,
            "fetch_hashtags",
            _hashtag(1),
            "hashtags/h1",
            403,
            "FORBIDDEN",
            "Operation not allowed.",
            "hashtag_id",
            "SYSTEM_HASHTAG",
            "FORBIDDEN — Operation not allowed.\n"
            "  hashtag_id: stand-in field words\n\n"
            "The pending hashtag cannot be renamed or deleted.",
        ),
        (
            HashtagsScreen,
            "fetch_hashtags",
            _hashtag(1),
            "hashtags/h1",
            409,
            "CONFLICT",
            "Changed by another request.",
            "hashtag_id",
            "CONCURRENT_CHANGE",
            "CONFLICT — Changed by another request.\n"
            "  hashtag_id: stand-in field words\n\n"
            "It changed at the same moment: press r, then try again.",
        ),
        # a user hashtag holds the pending hashtag's name: the engine's words
        # name the remedy, and the category line stays off
        # (contract: "Hashtags", "When the engine creates it")
        (
            HashtagsScreen,
            "fetch_hashtags",
            _hashtag(1),
            "hashtags/h1",
            409,
            "CONFLICT",
            "Rename the hashtag named Pendiente, then retry.",
            "hashtag_id",
            "RESERVED_NAME_HELD",
            "CONFLICT — Rename the hashtag named Pendiente, then retry.\n"
            "  hashtag_id: stand-in field words",
        ),
    ],
    ids=[
        "account-has-transactions",
        "category-has-transactions",
        "system-category",
        "system-hashtag",
        "race",
        "pending-name-held",
    ],
)
def test_a_refusal_shows_the_engine_words_and_what_to_do(
    configured, monkeypatch, make, fetch, row, path, status, code, words, key, reason, note
):
    """The engine refuses the delete. Nothing is deleted, the list is not read
    again, and the row stays. A race names the list's own key, `r` (screen 5A)."""
    monkeypatch.setattr(f"expense.reads.{fetch}", lambda *a, **k: whole([row]))

    async def scenario(pilot, app):
        screen = make()
        notes = _record_notes(monkeypatch, screen)
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen.check_action("delete", ()) is True
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        assert notes == [("Failed", note)]
        assert screen.query_one(CursorList).cursor_key == row["id"]

    with respx.mock() as engine:
        engine.delete(f"{ENGINE_URL}/v1/{path}").mock(
            error_response(status, code, words, {key: "stand-in field words"}, {key: reason})
        )
        run_app(scenario, size=SIZE)


def test_a_sealed_transaction_shows_only_the_engine_words(configured, monkeypatch):
    """The engine's message already says what to do, so nothing is added."""
    _stub_ledger(monkeypatch, list(LEDGER[:3]))
    words = (
        "Cannot delete a transaction assigned to a completed reconciliation. "
        "Revert the reconciliation to draft first."
    )

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        notes = _record_notes(monkeypatch, screen)
        await _open_ledger(pilot, app, screen)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        assert notes == [
            (
                "Failed",
                f"CONFLICT — {words}\n  transaction_id: Must not be in a completed reconciliation.",
            )
        ]
        assert "t1" in screen._by_id and len(screen._rows) == 3

    with respx.mock() as engine:
        _one_part_lines(engine)
        engine.delete(f"{ENGINE_URL}/v1/transactions/t1").mock(
            error_response(
                409,
                "CONFLICT",
                words,
                {"transaction_id": "Must not be in a completed reconciliation."},
                {"transaction_id": "IN_COMPLETED_RECONCILIATION"},
            )
        )
        run_app(scenario, size=SIZE)


def test_a_transaction_on_an_archived_account_shows_only_the_engine_words(configured, monkeypatch):
    """Screen 3 A of expense-world-archived-account.html: the ledger was read
    before the row's account was archived, and `d` then `y` is refused. The
    "Failed" note is the engine's words alone, no line of the app's under them,
    and the list is as it was: not read again, its rows and cursor kept."""
    calls = _stub_ledger(monkeypatch, list(LEDGER[:3]))
    err = archived_refusal(409, archived_words("delete", "transaction"), "transaction_id")

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        notes = _record_notes(monkeypatch, screen)
        await _open_ledger(pilot, app, screen)
        await _cursor_on(pilot, screen, "t2")
        reads = len(calls)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert notes == [
            (
                "Failed",
                f"CONFLICT — {archived_words('delete', 'transaction')}\n"
                f"  transaction_id: {ARCHIVED_FIELD_WORDS}",
            )
        ]
        assert notes[0][1] == refusal_text(err, None)
        assert len(calls) == reads and len(screen._rows) == 3
        assert screen.query_one(CursorList).cursor_key == "t2"

    with respx.mock() as engine:
        _one_part_lines(engine)
        route = engine.delete(f"{ENGINE_URL}/v1/transactions/t2").mock(
            error_response(err.status, err.code, err.message, err.fields, err.reasons)
        )
        run_app(scenario, size=SIZE)
    assert route.call_count == 1


def test_a_delete_refusal_with_no_reason_gets_no_line(configured, monkeypatch):
    """A `409` on the very route whose refusal has a line, but with no reason,
    gets none: the line follows the reason, never the status and the route."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([_account(1)]))

    async def scenario(pilot, app):
        screen = AccountsScreen()
        notes = _record_notes(monkeypatch, screen)
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        assert notes == [("Failed", "CONFLICT — stand-in")]

    with respx.mock() as engine:
        engine.delete(f"{ENGINE_URL}/v1/accounts/a1").mock(
            error_response(409, "CONFLICT", "stand-in")
        )
        run_app(scenario, size=SIZE)


def test_no_question_says_or_command():
    """Every delete question says "no screen can bring it back": there is no
    command to bring anything back either."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    offenders = [
        str(path.relative_to(root))
        for path in [*(root / "expense").rglob("*.py"), root / "docs" / "tui.md"]
        if "or command can bring" in " ".join(path.read_text(encoding="utf-8").split())
    ]
    assert not offenders


def test_d_is_off_while_a_bulk_write_runs(configured, monkeypatch):
    """A delete never overlaps a running bulk PUT: `d` is off and out of the
    footer until the bulk write's reload lands."""
    _stub_ledger(monkeypatch, list(LEDGER[:3]))

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await _open_ledger(pilot, app, screen)
        assert "d Delete" in _footer(screen)
        screen._bulk_busy = True  # as `_apply_pick` sets it while the PUTs run
        screen.refresh_bindings()
        await pilot.pause()
        assert screen.check_action("delete", ()) is False
        assert "d Delete" not in _footer(screen)
        await pilot.press("d")
        await pilot.pause()
        assert app.screen is screen  # no question
        screen._bulk_finished(1, [], "KORAKUEN")  # the write lands; the list reloads
        await wait_for(pilot, lambda: "d Delete" in _footer(screen))

    with respx.mock(assert_all_called=False) as engine:
        route = engine.delete(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not route.called


def test_a_cancelled_delete_keeps_the_archive_re_selection(configured, monkeypatch):
    """`a` then `d` then cancel: the row the toggle will re-select after its
    reload is still the toggled one, so "press a again to undo" lands on it.
    Only a delete that went through starts the list over."""
    _stub_manage(monkeypatch, "accounts", [_account(i) for i in range(3)])

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        screen._restore_key = "a2"  # what `a` on row a2 leaves for its reload
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("n")
        await wait_for(pilot, lambda: app.screen is screen)
        assert screen._restore_key == "a2"
        screen._load()  # the toggle's reload lands
        await wait_for(pilot, lambda: screen._restore_key is None)
        await pilot.pause()
        assert screen.query_one(CursorList).cursor_key == "a2"

    run_app(scenario, size=SIZE)


# ---- a part of a split purchase: d deletes the purchase whole ---------------
# docs/mockups/expense-world-bank-lines-whole.html 3a, 3c, 3d, 3e. Each ledger row
# names its bank line; `d` reads that line once (contract: GET
# /v1/bank-lines/{bank_line_id}) and a line of more than one part goes whole, in
# one `DELETE /bank-lines/{id}` (contract: DELETE /v1/bank-lines/{bank_line_id}).

#: The engine's own words for a line in a completed reconciliation, as the practice
#: engine sends them (contract: DELETE /v1/bank-lines/{bank_line_id}).
SEALED_LINE_WORDS = (
    "Cannot delete a bank line assigned to a completed reconciliation. "
    "Revert the reconciliation to draft first."
)
SEALED_LINE_FIELD = "Must not be assigned to a completed reconciliation."


def _ledger_row(tx_id: str, title: str, amount: int, line: str, day: str = "2026-10-11") -> dict:
    """One ledger row as `GET /transactions` lists it, signed, naming its bank line."""
    return {
        "id": tx_id,
        "title": title,
        "description": None,
        "amount_cents": amount,
        "date": f"{day}T05:00:00Z",
        "account_id": "acc1",
        "category_id": "pend",
        "hashtag_ids": [],
        "bank_line_id": line,
        "line_code": line_code_of(line),
        "statement_line": None,
    }


#: Part amounts of FARMACIA, the split purchase, by how many parts it has.
PARTS = {2: [-6000, -4000], 3: [-6000, -2500, -1500]}


def _split_ledger(parts: int) -> tuple[list[dict], dict]:
    """A ledger whose rows 2.. are FARMACIA's parts, every other row a line of
    its own; and FARMACIA's line as `GET /bank-lines/bl-farm` reads it."""
    amounts = PARTS[parts]
    farm = [_ledger_row(f"p{i}", "FARMACIA", a, "bl-farm") for i, a in enumerate(amounts, 1)]
    rows = [
        _ledger_row("t-net", "NETFLIX.COM", -4490, "bl-net", "2026-10-14"),
        *farm,
        _ledger_row("t-cine", "CINE PLAZA", -2800, "bl-cine", "2026-10-10"),
    ]
    line = bank_line_row(
        "bl-farm",
        [
            import_part(f"p{i}", a, account_id="acc1", line="bl-farm", day="2026-10-11")
            for i, a in enumerate(amounts, 1)
        ],
        net_cents=sum(amounts),
        account_id="acc1",
    )
    for part in line["parts"]:
        part["title"] = "FARMACIA"
    return rows, line


def _cine_line() -> dict:
    """CINE PLAZA's line: one part, never split."""
    return bank_line_row(
        "bl-cine",
        [import_part("t-cine", -2800, account_id="acc1", line="bl-cine", day="2026-10-10")],
        net_cents=-2800,
        account_id="acc1",
    )


@pytest.fixture
def line_engine(fake_client, monkeypatch):
    """`fake_client`, also answering the shared reads, so the bank-line read goes
    through `reads.fetch_bank_line` to the fake engine; the ledger's own list
    reads stay `fake_ledger`'s."""
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)
    return fake_client


def _line_reads(client) -> list[str]:
    return [
        path
        for method, path in client.requests
        if method == "GET" and path.startswith("/bank-lines/")
    ]


async def _cursor_on(pilot, screen, key: str) -> None:
    listing = screen.query_one(CursorList)
    listing.set_cursor(listing.index_of(key))
    await pilot.pause()


@pytest.mark.parametrize("parts", [2, 3])
@pytest.mark.parametrize("flt", [None, FILTER], ids=["whole", "filtered"])
def test_d_on_a_part_asks_about_the_whole_purchase_then_deletes_it(
    configured, monkeypatch, line_engine, parts, flt
):
    """3a, 3c: `d` on the second part reads the line once and asks about the
    purchase, naming its real part count and its signed total; `y` sends one
    `DELETE /bank-lines/{id}`, the note reads `Transaction deleted.` and the
    ledger reads fresh from the newest ten, cursor on row 1, every part gone."""
    rows, line = _split_ledger(parts)
    calls = _stub_ledger(monkeypatch, rows)
    line_engine.get_responses["/bank-lines/bl-farm"] = line
    total = "-100.00"

    def engine_deletes(path: str) -> dict:
        line_engine._record("DELETE", path)
        rows[:] = [r for r in rows if r["bank_line_id"] != "bl-farm"]
        return {"parts": []}

    line_engine.delete = engine_deletes

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=flt)
        notes = _record_notes(monkeypatch, screen)
        await _open_ledger(pilot, app, screen)
        await _cursor_on(pilot, screen, "p2")
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == f"Delete this transaction and its {parts} parts?"
        assert app.screen._message == (
            f"FARMACIA · {total} · 2026-10-11 · Sueldo Soles\nNo screen can bring it back."
        )
        assert _line_reads(line_engine) == ["/bank-lines/bl-farm"]
        reads = len(calls)
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", "Transaction deleted.") in notes)
        await wait_for(pilot, lambda: len(calls) > reads and len(screen._rows) == 2)
        assert calls[-1]["after"] is None and calls[-1]["limit"] == 10
        assert screen.query_one(CursorList).cursor_index == 0
        assert not any(key.startswith("p") for key in screen._by_id)

    run_app(scenario, size=SIZE)
    assert line_engine.deletes == ["/bank-lines/bl-farm"]
    assert _line_reads(line_engine) == ["/bank-lines/bl-farm"]


def test_y_on_a_purchase_sends_one_delete_with_one_idempotency_key(configured, monkeypatch):
    """Through the real HTTP client: one `GET /bank-lines/{id}`, then one
    `DELETE /bank-lines/{id}` carrying the client's idempotency key, and no
    `DELETE /transactions/{id}` at all."""
    rows, line = _split_ledger(2)
    _stub_ledger(monkeypatch, rows)

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        notes = _record_notes(monkeypatch, screen)
        await _open_ledger(pilot, app, screen)
        await _cursor_on(pilot, screen, "p1")
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", "Transaction deleted.") in notes)

    with respx.mock(assert_all_called=False) as engine:
        read = engine.get(f"{ENGINE_URL}/v1/bank-lines/bl-farm").mock(
            httpx.Response(200, json=line)
        )
        route = engine.delete(f"{ENGINE_URL}/v1/bank-lines/bl-farm").mock(
            httpx.Response(200, json={"parts": []})
        )
        single = engine.delete(url__startswith=f"{ENGINE_URL}/v1/transactions/").mock(
            httpx.Response(200, json={})
        )
        run_app(scenario, size=SIZE)
    assert read.call_count == 1
    assert route.call_count == 1
    assert route.calls.last.request.headers["X-Idempotency-Key"]
    assert not single.called


@pytest.mark.parametrize("key", ["n", "escape", "enter"])
def test_any_other_answer_on_a_purchase_sends_nothing(configured, monkeypatch, line_engine, key):
    rows, line = _split_ledger(2)
    calls = _stub_ledger(monkeypatch, rows)
    line_engine.get_responses["/bank-lines/bl-farm"] = line

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await _open_ledger(pilot, app, screen)
        await _cursor_on(pilot, screen, "p1")
        reads = len(calls)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press(key)
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert len(calls) == reads and len(screen._rows) == 4
        assert screen.query_one(CursorList).cursor_key == "p1"

    run_app(scenario, size=SIZE)
    assert line_engine.deletes == []


@pytest.mark.parametrize(
    ("status", "code", "words", "fields", "reasons"),
    [
        (
            409,
            "CONFLICT",
            SEALED_LINE_WORDS,
            {"bank_line_id": SEALED_LINE_FIELD},
            {"bank_line_id": "IN_COMPLETED_RECONCILIATION"},
        ),
        (404, "NOT_FOUND", "Bank line not found.", None, None),
        # archived-account 3 A: the engine's words alone
        (
            409,
            "CONFLICT",
            archived_words("delete", "bank line"),
            {"bank_line_id": ARCHIVED_FIELD_WORDS},
            {"bank_line_id": "ACCOUNT_ARCHIVED"},
        ),
    ],
    ids=["completed-reconciliation", "gone", "archived-account"],
)
def test_a_refused_purchase_delete_shows_the_engine_words_and_keeps_the_list(
    configured, monkeypatch, line_engine, status, code, words, fields, reasons
):
    """3d: the engine refuses; nothing is deleted, the list is not read again and
    the cursor stays on the part. The note is the engine's words whole: its
    message already says to revert the reconciliation to draft, or to unarchive
    the account, so the app adds no line, and any other refusal reads as every
    delete's does."""
    rows, line = _split_ledger(2)
    calls = _stub_ledger(monkeypatch, rows)
    line_engine.get_responses["/bank-lines/bl-farm"] = line
    err = EngineError(code, words, fields, status, {}, reasons)
    line_engine.errors["DELETE"] = err

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        notes = _record_notes(monkeypatch, screen)
        await _open_ledger(pilot, app, screen)
        await _cursor_on(pilot, screen, "p2")
        reads = len(calls)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert notes == [("Failed", refusal_text(err, None))]
        assert len(calls) == reads and len(screen._rows) == 4
        assert screen.query_one(CursorList).cursor_key == "p2"

    run_app(scenario, size=SIZE)
    assert line_engine.deletes == ["/bank-lines/bl-farm"]
    if code == "CONFLICT":
        assert refusal_text(err, None) == (
            f"CONFLICT — {words}\n  bank_line_id: {fields['bank_line_id']}"
        )


def test_a_row_never_split_deletes_as_today(configured, monkeypatch, line_engine):
    """3e: CINE PLAZA's line holds one part, so `d` asks today's question word for
    word and `y` sends `DELETE /transactions/{id}` for that row alone."""
    rows, _line = _split_ledger(2)
    calls = _stub_ledger(monkeypatch, rows)
    line_engine.get_responses["/bank-lines/bl-cine"] = _cine_line()

    def engine_deletes(path: str) -> dict:
        line_engine._record("DELETE", path)
        rows[:] = [r for r in rows if r["id"] != "t-cine"]
        return {}

    line_engine.delete = engine_deletes

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        notes = _record_notes(monkeypatch, screen)
        await _open_ledger(pilot, app, screen)
        await _cursor_on(pilot, screen, "t-cine")
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == "Delete this transaction?"
        assert app.screen._message == (
            "CINE PLAZA · -28.00 · 2026-10-10 · Sueldo Soles\n"
            "It leaves every balance and report, and no screen can bring it back."
        )
        reads = len(calls)
        await pilot.press("y")
        await wait_for(pilot, lambda: ("", "Transaction deleted.") in notes)
        await wait_for(pilot, lambda: len(calls) > reads and len(screen._rows) == 3)
        assert screen.query_one(CursorList).cursor_index == 0

    run_app(scenario, size=SIZE)
    assert line_engine.deletes == ["/transactions/t-cine"]
    assert _line_reads(line_engine) == ["/bank-lines/bl-cine"]


def test_a_failed_line_read_asks_nothing_and_sends_nothing(configured, monkeypatch, line_engine):
    """The line cannot be read: no question, no delete, the list as it was, and
    the engine's words in the "Failed" note; `d` again reads again."""
    rows, _line = _split_ledger(2)
    calls = _stub_ledger(monkeypatch, rows)  # no answer for the line: the fake engine's 404

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        notes = _record_notes(monkeypatch, screen)
        await _open_ledger(pilot, app, screen)
        await _cursor_on(pilot, screen, "p1")
        reads = len(calls)
        await pilot.press("d")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        assert app.screen is screen
        assert notes == [("Failed", "NOT_FOUND — no fake response for GET /bank-lines/bl-farm")]
        assert len(calls) == reads and len(screen._rows) == 4
        assert screen.query_one(CursorList).cursor_key == "p1"
        await pilot.press("d")
        await wait_for(pilot, lambda: len(notes) == 2)

    run_app(scenario, size=SIZE)
    assert line_engine.deletes == []
    assert _line_reads(line_engine) == ["/bank-lines/bl-farm", "/bank-lines/bl-farm"]


def _held_line_read(monkeypatch, line: dict) -> tuple[threading.Event, list[str]]:
    """`reads.fetch_bank_line` that waits until the returned event is set, so a
    test acts while the read is in flight; every read is logged by line id."""
    release = threading.Event()
    asked: list[str] = []

    def read(_cfg, bank_line_id, **_kw):
        asked.append(bank_line_id)
        release.wait(timeout=5)
        return line

    monkeypatch.setattr("expense.reads.fetch_bank_line", read)
    return release, asked


def test_a_second_d_while_the_line_is_read_is_ignored(configured, monkeypatch, line_engine):
    """`d` pressed again before the line read lands reads nothing more and asks
    one question."""
    rows, line = _split_ledger(2)
    _stub_ledger(monkeypatch, rows)
    release, asked = _held_line_read(monkeypatch, line)

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await _open_ledger(pilot, app, screen)
        await _cursor_on(pilot, screen, "p1")
        try:
            await pilot.press("d")
            await wait_for(pilot, lambda: asked)
            await pilot.press("d")
            await pilot.pause()
        finally:
            release.set()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.pause()
        pushed = [s for s in app.screen_stack if isinstance(s, ConfirmModal)]
        assert len(pushed) == 1
        await pilot.press("n")
        await wait_for(pilot, lambda: app.screen is screen)

    run_app(scenario, size=SIZE)
    assert asked == ["bl-farm"]
    assert line_engine.deletes == []


@pytest.mark.parametrize("how", ["left", "covered"])
def test_a_line_read_that_lands_off_the_ledger_asks_nothing(
    configured, monkeypatch, line_engine, how
):
    """The user leaves the ledger (`esc`) or opens another screen over it while
    the line is read: when the read lands, nothing is asked and nothing is sent."""
    from textual.screen import Screen

    rows, line = _split_ledger(2)
    _stub_ledger(monkeypatch, rows)
    release, asked = _held_line_read(monkeypatch, line)

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await _open_ledger(pilot, app, screen)
        await _cursor_on(pilot, screen, "p1")
        try:
            await pilot.press("d")
            await wait_for(pilot, lambda: asked)
            if how == "left":
                await pilot.press("escape")
                await wait_for(pilot, lambda: screen not in app.screen_stack)
            else:
                await app.push_screen(Screen())
                await pilot.pause()
        finally:
            release.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.pause()
        assert not any(isinstance(s, ConfirmModal) for s in app.screen_stack)
        if how == "covered":
            assert not screen._delete_reading  # `d` works again once the ledger is in front

    run_app(scenario, size=SIZE)
    assert asked == ["bl-farm"]
    assert line_engine.deletes == []
