"""The ledger on an archived account's rows (tui.md "On an archived account's
row the ledger offers no `d`").

With the cursor on a transaction whose account is archived, `d` Delete leaves
the footer and does nothing, since the engine deletes none of its transactions
(contract: POST /v1/accounts/{account_id}/archive); the row is drawn as any
other, and `s`, `c`, `b`, `h` and `⏎` stay, `s` opening the same Edit form `⏎`
does. The archived ids come from the one accounts read the ledger makes for the
names (`reads.load_account_index`), served here by the fake engine.
"""

import pytest
from textual.widgets import Footer
from textual.widgets._footer import FooterKey

from expense.tui.screens.bulk_pick import BulkPickScreen
from expense.tui.screens.edit_form import EditFormScreen
from expense.tui.screens.help import screen_inventory
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.transactions import LedgerFilter, TransactionsScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_ORDER_ACCOUNTS,
    bank_line_row,
    edit_limits,
    fake_ledger,
    import_part,
    line_code_of,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

ARCHIVED = {
    "id": "acc-viejo",
    "name": "Ahorro viejo",
    "currency_code": "PEN",
    "is_person": False,
    "is_archived": True,
    "sort_order": 4,
    "color": "#3b82f6",
    "current_balance_cents": 0,
    "opening_balance_transaction_id": None,
}
ACCOUNTS = [*ENGINE_ORDER_ACCOUNTS, ARCHIVED]


def _row(tx_id: str, account_id: str, title: str) -> dict:
    return {
        "id": tx_id,
        "title": title,
        "description": None,
        "amount_cents": -20000,
        "date": "2024-03-28T00:00:00Z",
        "account_id": account_id,
        "category_id": "cat-efe",
        "hashtag_ids": [],
        "bank_line_id": f"bl-{tx_id}",
        "line_code": line_code_of(f"bl-{tx_id}"),
        "statement_line": None,
        "statement_place": None,
        "reconciliation_id": None,
    }


#: An active account's row, the archived account's row, a person's row.
LEDGER = [
    _row("t-live", "acc-zeta", "Pago tarjeta"),
    _row("t-old", "acc-viejo", "Retiro cajero"),
    _row("t-ana", "per-ana", "Préstamo Ana"),
]
CATEGORIES = [{"id": "cat-efe", "name": "EFECTIVO", "is_system": False}]


def _archived_limits(part_id: str) -> dict:
    """A line on an archived account: every line field refused, its parts and
    their amounts kept (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")."""
    return edit_limits(
        locked_fields=dict.fromkeys(
            ("title", "date", "account_id", "reconciliation_id"), "ACCOUNT_ARCHIVED"
        ),
        total_fixed=True,
        parts_fixed=True,
        locked_part_fields={part_id: {"amount_cents": "ACCOUNT_ARCHIVED"}},
    )


@pytest.fixture
def engine(fake_client, monkeypatch):
    """The fake engine behind the shared reads: every account, the archived one
    included, and each row's never-split bank line, the archived account's with
    the `edit_limits` the engine answers for it
    (tests/contract/test_bank_line_edit_limits.py); the ledger's own list reads
    are `fake_ledger`'s."""
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)
    fake_client.get_responses.update(
        {
            "/accounts": whole([dict(a) for a in ACCOUNTS]),
            "/categories": whole(CATEGORIES),
            "/hashtags": whole([]),
        }
    )
    for row in LEDGER:
        line = row["bank_line_id"]
        part = import_part(row["id"], row["amount_cents"], account_id=row["account_id"], line=line)
        read = bank_line_row(
            line, [part], net_cents=row["amount_cents"], account_id=row["account_id"]
        )
        if row["account_id"] == ARCHIVED["id"]:
            read["edit_limits"] = _archived_limits(row["id"])
        fake_client.get_responses[f"/bank-lines/{line}"] = read
    fake_ledger(monkeypatch, list(LEDGER))
    return fake_client


#: The ledger's footer with the cursor on an active account's row, slot by slot.
FOOTER_ON_AN_ACTIVE_ROW = [
    ("⏎", "Open"),
    ("space", "Select"),
    ("esc", "Back"),
    ("r", "Refresh"),
    ("?", "Keys"),
    ("+", "Add"),
    ("a", "All/none"),
    ("c", "Category"),
    ("b", "Account"),
    ("h", "Hashtags"),
    ("s", "Edit"),
    ("d", "Delete"),
]
#: The `?` card's "This screen" rows of the ledger, in order.
CARD_THIS_SCREEN = [
    ("+", "Add"),
    ("a", "Select every loaded row, or none"),
    ("c", "Set the category of the selection"),
    ("b", "Move the selection to an account"),
    ("h", "Replace the selection's hashtags"),
    ("s", "Edit the transaction and its parts"),
    ("d", "Delete"),
    ("r", "Refresh"),
    ("esc", "Clear the selection, else go back"),
    ("esc", "Back"),
]


def _footer(screen) -> list[str]:
    return [k.description for k in screen.query_one(Footer).query(FooterKey)]


def _keys_shown(screen) -> set[str]:
    shown = set(_footer(screen))
    return {d for d in ("Edit", "Delete") if d in shown}


#: The ledger as Home opens it filtered: every row here is on this category.
FILTER = LedgerFilter("category", "cat-efe", "EFECTIVO")


async def _open(pilot, app, flt: LedgerFilter | None = None) -> TransactionsScreen:
    screen = TransactionsScreen(filter=flt)
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    screen.query_one(CursorList).focus()
    await pilot.pause()
    return screen


async def _cursor_on(pilot, screen, key: str) -> None:
    """Move the cursor to `key` with the arrow keys, as the user does."""
    listing = screen.query_one(CursorList)
    steps = listing.index_of(key) - listing.cursor_index
    await pilot.press(*(["down"] * steps if steps > 0 else ["up"] * -steps))
    await wait_for(pilot, lambda: listing.cursor_key == key)


def _sent(client) -> list:
    """Every request but the ledger's own reads of accounts, categories and
    hashtags: a bank-line read, a write."""
    return [
        (method, path)
        for method, path, _ in client.calls
        if path not in ("/accounts", "/categories", "/hashtags")
    ]


def test_the_ledger_reads_the_archived_ids_with_the_names_in_one_read(engine):
    """One `GET /accounts` per ledger load gives both the names and the
    archived ids (contract: GET /v1/accounts)."""

    async def scenario(pilot, app):
        screen = await _open(pilot, app)
        assert screen._archived == {"acc-viejo"}
        assert [p for m, p, _ in engine.calls if p == "/accounts"] == ["/accounts"]

    run_app(scenario, size=(120, 30))


@pytest.mark.parametrize("flt", [None, FILTER], ids=["whole", "filtered"])
def test_d_leaves_the_footer_on_an_archived_accounts_row_only_and_s_stays(engine, flt):
    """Moving the cursor updates the footer: `d` shows on an active account's
    row and on a person's, and is gone on the archived account's; `s`, `c`,
    `b`, `h` and `⏎` stay on every row, whole ledger or filtered from Home."""

    async def scenario(pilot, app):
        screen = await _open(pilot, app, flt)
        seen = {}
        for key in ("t-live", "t-old", "t-ana", "t-old", "t-live"):
            await _cursor_on(pilot, screen, key)
            expect = {"Edit"} if key == "t-old" else {"Edit", "Delete"}
            await wait_for(
                pilot,
                lambda e=expect: _keys_shown(screen) == e,
                message=f"{key}: {_footer(screen)}",
            )
            seen[key] = _footer(screen)
            for always in ("Open", "Edit", "Category", "Account", "Hashtags"):
                assert always in seen[key], (key, always)
        assert "Delete" in seen["t-ana"] and "Delete" not in seen["t-old"]

    run_app(scenario, size=(160, 30))


def _footer_pairs(screen) -> list[tuple[str, str]]:
    return [(k.key_display, k.description) for k in screen.query_one(Footer).query(FooterKey)]


@pytest.mark.parametrize("flt", [None, FILTER], ids=["whole", "filtered"])
def test_the_footer_says_s_edit_and_the_card_says_what_the_form_does(engine, flt):
    """Screen 1 A of expense-world-edit-form-words.html: the footer reads
    `s Edit` before `d Delete`, and the `?` card's line for `s` reads "Edit the
    transaction and its parts"; every other footer slot and card row keeps its
    words and its place."""

    async def scenario(pilot, app):
        screen = await _open(pilot, app, flt)
        await _cursor_on(pilot, screen, "t-live")
        await wait_for(pilot, lambda: _keys_shown(screen) == {"Edit", "Delete"})
        assert _footer_pairs(screen) == FOOTER_ON_AN_ACTIVE_ROW
        _, groups = screen_inventory(screen)
        own = next(g for g in groups if g.title == "This screen")
        assert [(row.keys, row.description) for row in own.rows] == CARD_THIS_SCREEN
        assert [row.description for row in own.rows if row.keys == "s"] == [
            "Edit the transaction and its parts"
        ]

    run_app(scenario, size=(160, 30))


@pytest.mark.parametrize("flt", [None, FILTER], ids=["whole", "filtered"])
def test_s_on_an_archived_accounts_row_opens_the_edit_form_as_enter_does(engine, flt):
    """`s` pushes the Edit form for the cursor row, the same screen on the same
    record `⏎` opens; the form reads what is read-only from the line's
    `edit_limits` (test_tui_edit_form.py)."""

    async def scenario(pilot, app):
        screen = await _open(pilot, app, flt)
        await _cursor_on(pilot, screen, "t-old")
        assert screen.check_action("split", ()) is True
        await pilot.press("s")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        by_s = app.screen._record
        await wait_for(pilot, lambda: ("GET", "/bank-lines/bl-t-old") in _sent(engine))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        screen.query_one(CursorList).focus()
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        assert by_s is app.screen._record is screen._by_id["t-old"]
        assert engine.puts == [] and engine.deletes == []

    run_app(scenario, size=(160, 30))


@pytest.mark.parametrize("flt", [None, FILTER], ids=["whole", "filtered"])
def test_d_on_an_archived_accounts_row_does_nothing_and_sends_nothing(engine, flt):
    async def scenario(pilot, app):
        screen = await _open(pilot, app, flt)
        await _cursor_on(pilot, screen, "t-old")
        assert screen.check_action("delete", ()) is False
        before = list(engine.calls)
        await pilot.press("d")
        await pilot.pause()
        await pilot.pause()
        assert app.screen is screen
        assert engine.calls == before
        # the `?` card lists the screen's keys as declared, `s` and `d` included
        _, groups = screen_inventory(screen)
        own = next(g for g in groups if g.title == "This screen")
        assert {"s", "d"} <= {row.keys for row in own.rows}
        # called directly too, the action keeps to the cursor row's rule
        screen.action_delete()
        await pilot.pause()
        assert app.screen is screen and engine.calls == before
        assert not screen._delete_reading

    run_app(scenario, size=(160, 30))


@pytest.mark.parametrize("key", ["t-live", "t-ana"])
def test_s_and_d_work_as_today_on_an_active_or_a_persons_row(engine, key):
    async def scenario(pilot, app):
        screen = await _open(pilot, app)
        await _cursor_on(pilot, screen, key)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert ("GET", f"/bank-lines/bl-{key}") in _sent(engine)
        await pilot.press("n")
        await wait_for(pilot, lambda: app.screen is screen)
        assert engine.deletes == []
        await pilot.press("s")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))

    run_app(scenario, size=(160, 30))


def test_the_archived_accounts_row_is_drawn_as_any_other(engine):
    """Screen 1 A: no dimming, no mark. The list drawn over the archived
    account reads character for character, colour for colour, as the same
    list drawn with the account active, the cursor elsewhere."""

    def draw(archived: bool) -> str:
        engine.get_responses["/accounts"] = whole(
            [dict(a, is_archived=archived) if a is ARCHIVED else dict(a) for a in ACCOUNTS]
        )

        async def scenario(pilot, app):
            screen = await _open(pilot, app)
            assert screen._archived == ({"acc-viejo"} if archived else set())
            return render_text(screen.query_one(CursorList)._build(), width=120, ansi=True)

        return run_app(scenario, size=(160, 30))

    frozen = draw(True)
    active = draw(False)
    assert "Retiro cajero" in frozen and "Ahorro viejo" in frozen
    assert frozen == active


def test_after_an_unarchive_and_r_d_is_back_on_the_row(engine):
    async def scenario(pilot, app):
        screen = await _open(pilot, app)
        await _cursor_on(pilot, screen, "t-old")
        await wait_for(pilot, lambda: _keys_shown(screen) == {"Edit"})
        # the account is unarchived on Manage ▸ Accounts; the next read says so
        engine.get_responses["/accounts"] = whole([dict(a, is_archived=False) for a in ACCOUNTS])
        await pilot.press("r")
        await wait_for(pilot, lambda: screen._archived == set())
        await wait_for_list(pilot, app)
        screen.query_one(CursorList).focus()
        await _cursor_on(pilot, screen, "t-old")
        await wait_for(pilot, lambda: _keys_shown(screen) == {"Edit", "Delete"})
        await pilot.press("s")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))

    run_app(scenario, size=(160, 30))


def test_the_existing_gates_still_hold_beside_the_archived_rule(engine):
    """A selection takes `s` and `d` off every row, an active one and an
    archived one alike, and `esc` brings back what the row allows; a bulk write
    running takes both off too, and `s` then opens nothing."""

    async def scenario(pilot, app):
        screen = await _open(pilot, app)
        await _cursor_on(pilot, screen, "t-live")
        await pilot.press("space")
        await wait_for(pilot, lambda: _keys_shown(screen) == set())
        assert screen.check_action("split", ()) is False
        await pilot.press("escape")
        await wait_for(pilot, lambda: _keys_shown(screen) == {"Edit", "Delete"})
        await _cursor_on(pilot, screen, "t-old")
        await pilot.press("space")
        await wait_for(pilot, lambda: _keys_shown(screen) == set())
        await pilot.press("s")
        await pilot.pause()
        assert app.screen is screen
        await pilot.press("escape")
        await wait_for(pilot, lambda: _keys_shown(screen) == {"Edit"})
        screen._bulk_busy = True
        assert screen.check_action("split", ()) is False
        assert screen.check_action("delete", ()) is False
        assert screen.check_action("pick", ("category",)) is None
        screen.action_split()
        await pilot.pause()
        assert app.screen is screen
        screen._bulk_busy = False

    run_app(scenario, size=(160, 30))


def test_s_and_d_are_off_on_an_empty_ledger(fake_client, monkeypatch):
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)
    fake_client.get_responses.update(
        {"/accounts": whole([dict(a) for a in ACCOUNTS]), "/categories": whole(CATEGORIES)}
    )
    fake_client.get_responses["/hashtags"] = whole([])
    fake_ledger(monkeypatch, [])

    async def scenario(pilot, app):
        screen = TransactionsScreen()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._archived == {"acc-viejo"})
        await pilot.pause()
        assert screen.check_action("split", ()) is False
        assert screen.check_action("delete", ()) is False
        assert _keys_shown(screen) == set()
        await pilot.press("s")
        await pilot.pause()
        assert app.screen is screen

    run_app(scenario, size=(160, 30))


@pytest.mark.parametrize(
    ("key", "typed", "body"),
    [
        ("c", "efe", {"category_id": "cat-efe"}),
        ("h", "caj", {"hashtag_ids": ["h-caja"]}),
        ("b", "zeta", {"account_id": "acc-zeta", "reconciliation_id": None}),
    ],
    ids=["category", "hashtags", "account"],
)
def test_the_bulk_keys_and_enter_still_work_on_an_archived_accounts_row(engine, key, typed, body):
    """`c`, `h` and `b` still open their picker and send the one `PUT` on the
    cursor row (the engine judges it: a move off the account is refused in its
    own words, task 2's tests), and `⏎` opens the Edit form."""
    engine.get_responses["/hashtags"] = whole([{"id": "h-caja", "name": "CAJA CHICA"}])

    async def scenario(pilot, app):
        screen = await _open(pilot, app)
        await _cursor_on(pilot, screen, "t-old")
        await pilot.press(key)
        await wait_for(pilot, lambda: isinstance(app.screen, BulkPickScreen))
        await pilot.press(*typed, "enter")
        if key == "h":
            await pilot.press("enter")  # `enter` on the emptied input applies the marks
        await wait_for(pilot, lambda: engine.puts)
        assert engine.puts == [("/transactions/t-old", body)]
        await wait_for(pilot, lambda: not screen._bulk_busy and app.screen is screen)
        await wait_for_list(pilot, app)
        await _cursor_on(pilot, screen, "t-old")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))

    run_app(scenario, size=(160, 30))
