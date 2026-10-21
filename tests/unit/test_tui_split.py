"""`s` on the ledger — the split screen: the table of parts, each part's fields
below, the title's field, the split, the re-split and the refusals.

Screens: docs/mockups/expense-world-split-screen.html (1 to 6). Every engine
call goes to one fake engine (`LineClient`), the ledger's reads, the split
screen's and the split itself, so a test can assert exactly what was read and
sent. One test sends the split through the real HTTP client against a
respx-mocked engine, for the idempotency key. The refusals' words are
stand-ins, except the mismatch sentence, which is the contract's own
(contract: POST /v1/transactions/{transaction_id}/split, "The total is kept").
"""

import json
import uuid

import httpx
import pytest
import respx
from rich.text import Text
from textual.widgets import Footer, Input, Static
from textual.widgets._footer import FooterKey

from expense.errors import EngineConnectionError, EngineError
from expense.reads import QuickAddRefs
from expense.tui.screens._form import TITLE_REQUIRED
from expense.tui.screens.split import (
    TITLE_ROW,
    Part,
    SplitScreen,
    count_line,
    part_from_engine,
    part_key,
)
from expense.tui.screens.transactions import LedgerFilter, TransactionsScreen
from expense.tui.theme import ACCENT, PALETTE
from expense.tui.widgets.cursor_list import CursorList
from expense.tui.widgets.refusal import hanging
from tests.unit.helpers import (
    ARCHIVED_FIELD_WORDS,
    ENGINE_URL,
    FakeClient,
    archived_refusal,
    archived_words,
    cursor_page,
    import_part,
    line_code_of,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

SIZE = (120, 40)

ACCOUNTS = [
    {
        "id": "acc1",
        "name": "Sueldo Soles",
        "currency_code": "PEN",
        "is_person": False,
        "is_archived": False,
        "opening_balance_transaction_id": None,
    }
]
CATEGORIES = [
    {"id": "c-com", "name": "COMIDA", "is_system": False, "system_key": None},
    {"id": "c-hog", "name": "HOGAR", "is_system": False, "system_key": None},
    {"id": "c-hos", "name": "HOSPEDAJE", "is_system": False, "system_key": None},
    {"id": "c-pend", "name": "@Pendiente", "is_system": True, "system_key": "pending"},
    {"id": "c-open", "name": "@Opening", "is_system": True, "system_key": "opening_balance"},
]
HASHTAGS = [
    {"id": "h-casa", "name": "casa", "system_key": None},
    {"id": "h-pend", "name": "Pendiente", "system_key": "pending"},
]


def _tx(
    tx_id, amount, *, line, title="Tottus Jockey Plaza", category="c-pend", tags=None, note=None
):
    """A transaction as the signed list read returns it."""
    return {
        "id": tx_id,
        "title": title,
        "description": note,
        "amount_cents": amount,
        "date": "2026-10-11T12:00:00-05:00",
        "account_id": "acc1",
        "category_id": category,
        "hashtag_ids": tags if tags is not None else ["h-pend"],
        "bank_line_id": line,
        "line_code": line_code_of(line),
        "statement_line": None,
        "version": 1,
    }


#: One transaction never split, and one already split into two parts.
TOTTUS = _tx("t1", -10000, line="bl-1")
CAFE = _tx("t2", -1850, line="bl-2", title="Cafe Andino", category="c-com", tags=["h-casa"])
PART_1 = _tx("p1", -6000, line="bl-9", category="c-com", tags=["h-casa"], note="verduras")
PART_2 = _tx("p2", -4000, line="bl-9", category="c-hog", note="lejía y papel")
LEDGER = [TOTTUS, CAFE, PART_1, PART_2]
LINES = {"bl-1": [TOTTUS], "bl-2": [CAFE], "bl-9": [PART_1, PART_2]}
#: Each line's signed total, its `net_cents` (contract: GET /v1/bank-lines/{bank_line_id}).
NET = {"bl-1": -10000, "bl-2": -1850, "bl-9": -10000}


def _as_part(tx: dict) -> dict:
    """A ledger transaction as `GET /bank-lines/{id}` lists it among `parts`."""
    return import_part(
        tx["id"],
        tx["amount_cents"],
        account_id=tx["account_id"],
        line=tx["bank_line_id"],
        day="2026-10-11",
        title=tx["title"],
        category_id=tx["category_id"],
        hashtag_ids=tuple(tx["hashtag_ids"]),
        description=tx["description"],
    )


def bank_line(line: str) -> dict:
    """`GET /bank-lines/{id}` for one of `LINES`: the line with every part."""
    return {
        "id": line,
        "line_code": line_code_of(line),
        "account_id": "acc1",
        "operation_code": None,
        "statement_line": None,
        "net_cents": NET[line],
        "part_count": len(LINES[line]),
        "parts": [_as_part(tx) for tx in LINES[line]],
    }


MISMATCH = (
    "Must add up to the line's total: the line's total is -10000 cents "
    "and the parts add up to -9000."
)


class LineClient(FakeClient):
    """The fake engine: reference lists whole, the ledger and its count, and
    each bank line with its parts."""

    def __init__(self, ledger: list[dict]) -> None:
        super().__init__()
        self.ledger = ledger
        self.get_responses.update(
            {
                "/accounts": whole(ACCOUNTS),
                "/categories": whole(CATEGORIES),
                "/hashtags": whole(HASHTAGS),
            }
        )
        for line in LINES:
            self.get_responses[f"/bank-lines/{line}"] = bank_line(line)

    def get(self, path: str, *, auth: bool = True, params: dict | None = None) -> dict:
        params = params or {}
        if path == "/transactions":
            self._record("GET", path, params)
            limit = params.get("limit") or 50
            return cursor_page(self.ledger[:limit], limit=limit)
        if path == "/transactions/count":
            self._record("GET", path, params)
            return {"count": len(self.ledger)}
        return super().get(path, auth=auth, params=params)

    def line_reads(self) -> list[str]:
        """The split screen's own reads of a line, `GET /bank-lines/{id}`."""
        return [path for method, path, _ in self.calls if path.startswith("/bank-lines/")]

    def ledger_reads(self) -> list[dict]:
        return [
            body for method, path, body in self.calls if method == "GET" and path == "/transactions"
        ]


@pytest.fixture
def engine(monkeypatch):
    client = LineClient(list(LEDGER))
    monkeypatch.setattr("expense.http.ExpenseClient", lambda *a, **k: client)
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: client)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    return client


def _footer(screen) -> list[tuple[str, str]]:
    return [(k.key_display, k.description) for k in screen.query_one(Footer).query(FooterKey)]


async def _open_ledger(pilot, app, flt=None) -> TransactionsScreen:
    screen = TransactionsScreen(filter=flt)
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    screen.query_one(CursorList).focus()
    await pilot.pause()
    return screen


async def _open_split(pilot, app, key, flt=None) -> tuple[TransactionsScreen, SplitScreen]:
    ledger = await _open_ledger(pilot, app, flt)
    listing = ledger.query_one(CursorList)
    listing.set_cursor(listing.index_of(key))
    await pilot.pause()
    await pilot.press("s")
    await wait_for(pilot, lambda: isinstance(app.screen, SplitScreen))
    screen = app.screen
    await wait_for(pilot, lambda: screen._refs is not None, message="split screen never loaded")
    await pilot.pause()
    return ledger, screen


async def _field(pilot, screen, text: str, key: str = "enter") -> None:
    """Type `text` in the field the cursor is on, then press `key`."""
    bar = screen.query_one("#bar", Input)
    bar.value = text
    await pilot.pause()
    await pilot.press(key)
    await pilot.pause()


async def _add_part(pilot, screen, amount, category="", tag="", note="") -> None:
    """`⏎` on `+ add a part`, then each field in turn: `⏎` on NOTE closes it."""
    while screen._cursor < len(screen._parts):
        await pilot.press("down")
    await pilot.press("enter")
    await pilot.pause()
    await _field(pilot, screen, amount)
    await _field(pilot, screen, category)
    if tag:
        await _field(pilot, screen, tag)  # adds the hashtag, stays for another
    await _field(pilot, screen, "")
    await _field(pilot, screen, note)


def _text(screen, widget_id: str) -> str:
    return render_text(screen.query_one(widget_id, Static).content, width=110)


def _lines(screen, widget_id: str) -> list[str]:
    return [line.rstrip() for line in _text(screen, widget_id).splitlines()]


def _part_rows(screen) -> list[Text]:
    """The table's lines: its header, each part, `+  add a part`."""
    return [r for r in screen.query_one("#parts", Static).content.renderables if r.plain][:-1]


def _styles_of(text: Text, needle: str) -> set[str]:
    start = text.plain.index(needle)
    return {str(s.style) for s in text.spans if s.start <= start < s.end}


def _sent(engine) -> list[dict]:
    """The one split's parts, without their fresh ids."""
    ((_path, body),) = engine.posts
    return [{k: v for k, v in p.items() if k != "id"} for p in body["parts"]]


# ---- `s Split` on the ledger -----------------------------------------------------


def _ledger_footer(screen) -> list[str]:
    return [
        f"{a.binding.key} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


def test_s_sits_before_d_on_the_ledger(engine):
    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        assert _ledger_footer(ledger)[-2:] == ["s Split", "d Delete"]

    run_app(scenario, size=SIZE)


def test_s_is_off_while_rows_are_selected(engine):
    """Like `d`: with a selection `s` leaves the footer and does nothing; `esc`
    clears the selection and it is back."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        await pilot.press("space")
        await pilot.pause()
        assert ledger._selected
        assert "s Split" not in _ledger_footer(ledger)
        await pilot.press("s")
        await pilot.pause()
        assert app.screen is ledger
        await pilot.press("escape")
        await pilot.pause()
        assert _ledger_footer(ledger)[-2:] == ["s Split", "d Delete"]

    run_app(scenario, size=SIZE)
    assert engine.line_reads() == []


# ---- screen 1 · on the table ---------------------------------------------------


@pytest.mark.parametrize(
    "flt",
    [None, LedgerFilter("category", "c-pend", "@Pendiente")],
    ids=["whole", "filtered"],
)
def test_s_opens_the_table_under_the_date_account_total_and_the_title(engine, flt):
    """Screen 1: the line every part keeps, the TITLE line, the table's header,
    `+  add a part` and the count line; on a transaction never split the table
    opens empty, the cursor on `+ add a part`, after one read of the row's
    line. Nothing is focused, and the footer is the table's."""

    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, "t1", flt)
        assert screen.crumb == (*ledger.crumb, "Split")
        assert _text(screen, "#split-head").strip() == (
            "2026-10-11  ·  Sueldo Soles  ·  -100.00 PEN  ·  every part keeps this date and account"
        )
        title = _text(screen, "#split-title").strip()
        assert title.startswith("TITLE      Tottus Jockey Plaza")
        assert title.endswith("same on every part")
        assert _lines(screen, "#parts") == [
            "      amount    category       hashtags        note",
            "  +  add a part",
            "",
            "0 parts  ·  0.00 of -100.00  ·  -100.00 left",
        ]
        assert screen._cursor == 0 and screen._parts == []
        assert app.focused is None
        assert not screen.query_one("#part-fields").display
        assert _footer(screen) == [
            ("esc", "Cancel"),
            ("^s", "Split"),
            ("⏎", "Edit"),
            ("^x", "Drop part"),
        ]

    run_app(scenario, size=SIZE)
    assert engine.line_reads() == ["/bank-lines/bl-1"]


def test_the_cursor_moves_from_the_title_through_the_parts_to_add_a_part(engine):
    """`↑↓` move from the TITLE line through the parts to `+ add a part` and
    stop at either end; the screen opens on the first part. The cursor's line
    is in the cursor style, the TITLE line's too."""

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        lines = _lines(screen, "#parts")
        assert lines[1].split() == ["1", "-60.00", "COMIDA", "#casa", "verduras"]
        assert lines[2].split() == ["2", "-40.00", "HOGAR", "—", "lejía", "y", "papel"]
        assert lines[3].strip() == "+  add a part"
        seen = [screen._cursor]
        for key in ("up", "up"):
            await pilot.press(key)
            seen.append(screen._cursor)
        title = screen.query_one("#split-title", Static).content
        part_lines = screen.query_one("#parts", Static).content.renderables
        on_title = [line for line in part_lines[1:4] if "reverse" in str(line.spans)]
        for key in ("down", "down", "down", "down", "up"):
            await pilot.press(key)
            seen.append(screen._cursor)
        assert seen == [0, TITLE_ROW, TITLE_ROW, 0, 1, 2, 2, 1]
        cursor_line = screen.query_one("#parts", Static).content.renderables[2]
        assert cursor_line.plain.startswith("  2")
        assert "reverse" in {str(s.style) for s in cursor_line.spans}
        return title, on_title, screen.query_one("#split-title", Static).content

    title, on_title, left = run_app(scenario, size=SIZE)
    assert title.plain.startswith("TITLE      Tottus Jockey Plaza")
    assert "reverse" in {str(s.style) for s in title.spans}
    assert on_title == []  # no part is under the cursor while the title is
    assert "reverse" not in {str(s.style) for s in left.spans}


def test_parts_that_reach_the_total_tick_and_ones_short_of_it_say_what_is_left():
    """`2 parts  ·  -100.00 of -100.00  ✓`, the tick in the success colour, or
    `-10.00 left` in the error colour; a part with no amount adds nothing."""
    whole_line = count_line([Part(-6000), Part(-4000)], -10000, palette=PALETTE)
    assert whole_line.plain == "2 parts  ·  -100.00 of -100.00  ✓"
    assert _styles_of(whole_line, "✓") == {PALETTE.success}
    short = count_line([Part(-6000), Part(-3000), Part()], -10000, palette=PALETTE)
    assert short.plain == "3 parts  ·  -90.00 of -100.00  ·  -10.00 left"
    assert _styles_of(short, "-10.00 left") == {PALETTE.error}
    over = count_line([Part(-12000)], -10000, palette=PALETTE)
    assert over.plain == "1 part  ·  -120.00 of -100.00  ·  20.00 left"


# ---- screen 2 · a part's fields below -------------------------------------------


def test_enter_on_a_part_opens_its_fields_below_with_the_part_marked(engine):
    """Screen 2: `⏎` on part 2 opens PART 2's fields one per line, the cursor
    on AMOUNT holding the part's amount; the part reads `▌ 2` in the table, and
    the footer is the fields'."""

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await pilot.press("down", "enter")
        await pilot.pause()
        assert screen._editing == 1
        assert screen.query_one("#part-fields").display
        assert app.focused is screen.query_one("#bar", Input)
        assert screen.query_one("#bar", Input).value == "-40"
        head = _lines(screen, "#part-head")
        assert head[0].startswith("────") and head[1] == "PART 2"
        assert str(screen.query_one("#part-field").content).strip() == "▌ AMOUNT"
        assert _lines(screen, "#fields-below") == [
            "  CATEGORY  HOGAR",
            "  HASHTAGS",
            "  NOTE      lejía y papel",
        ]
        assert not screen.query_one("#fields-above").display
        marked = screen.query_one("#parts", Static).content.renderables[2]
        assert marked.plain.startswith("▌ 2")
        assert _footer(screen) == [
            ("esc", "Back to the parts"),
            ("^s", "Split"),
            ("⇥", "Field"),
        ]

    run_app(scenario, size=SIZE)


def test_typing_ho_in_category_lists_hogar_and_hospedaje_and_arrows_move_in_it(engine):
    """Spec check 2: the shared suggestion list shows as you type, under the
    field; `↑↓` move in it while it is open, and `⏎` picks the highlighted one,
    which the table shows at once."""

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "t1")
        await pilot.press("enter")  # + add a part
        await _field(pilot, screen, "-40")
        assert screen._key == "category"
        assert not screen.query_one("#part-suggest").display  # nothing typed yet
        await pilot.press("h", "o")
        await pilot.pause()
        assert screen.query_one("#part-suggest").display
        assert [line.strip() for line in _lines(screen, "#part-suggest")] == [
            "HOGAR",
            "HOSPEDAJE",
        ]
        await pilot.press("down")
        assert screen._key == "category" and screen._suggest_idx == 1
        await pilot.press("up")
        assert screen._suggest_idx == 0
        await pilot.press("down", "enter")
        await pilot.pause()
        assert screen._key == "hashtags"
        assert screen._parts[0].category_id == "c-hos"
        assert _lines(screen, "#parts")[1].split()[:3] == ["▌", "1", "-40.00"]
        assert "HOSPEDAJE" in _lines(screen, "#parts")[1]

    run_app(scenario, size=SIZE)


def test_arrows_and_tab_move_between_fields_keeping_each_field_left(engine):
    """`↓`, `↑`, `⇥` and `⏎` move between the fields; each field left is kept
    and shows in the table row at once; moves stop at either end."""

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await pilot.press("enter")  # part 1, AMOUNT
        await _field(pilot, screen, "-70", key="down")
        assert screen._key == "category"
        assert "-70.00" in _lines(screen, "#parts")[1]
        assert _lines(screen, "#fields-above") == ["  AMOUNT    -70.00"]
        await pilot.press("tab")
        assert screen._key == "hashtags"
        await pilot.press("down")
        assert screen._key == "note"
        await _field(pilot, screen, "fruta", key="down")  # the last field: stays
        assert screen._key == "note" and screen._parts[0].note == "fruta"
        assert _lines(screen, "#parts")[1].endswith("fruta")
        await pilot.press("shift+tab", "up", "up", "up")
        assert screen._key == "amount"
        assert screen._editing == 0

    run_app(scenario, size=SIZE)


def test_enter_on_the_last_field_goes_back_to_the_table_on_that_part(engine):
    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await pilot.press("down", "enter")
        for _ in range(3):
            await _field(pilot, screen, screen.query_one("#bar", Input).value)
        assert screen._key == "note"
        await _field(pilot, screen, "lejía")
        assert screen._editing is None and screen._cursor == 1
        assert not screen.query_one("#part-fields").display
        assert app.focused is None
        assert _lines(screen, "#parts")[2].endswith("lejía")
        assert _footer(screen)[0] == ("esc", "Cancel")

    run_app(scenario, size=SIZE)


def test_esc_in_the_fields_keeps_the_fields_left_and_drops_only_the_one_typed(engine):
    """`esc` goes back to the table: AMOUNT, left, keeps -55.00; the note being
    typed goes back to what it was. The screen stays."""

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await pilot.press("enter")
        await _field(pilot, screen, "-55")
        await pilot.press("tab", "tab")
        assert screen._key == "note"
        screen.query_one("#bar", Input).value = "never kept"
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is screen
        assert screen._editing is None and screen._cursor == 0
        assert screen._parts[0] == Part(-5500, "c-com", ("h-casa",), "verduras")

    run_app(scenario, size=SIZE)
    assert engine.posts == []


def test_a_category_or_hashtag_that_matches_nothing_is_not_kept(engine):
    """As on the Edit form: the field says so and the cursor stays; an amount
    that is not a number likewise."""
    notes: list[str] = []

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "t1")
        screen.notify = lambda message, **kw: notes.append(message)
        await pilot.press("enter")
        await _field(pilot, screen, "sesenta")
        assert screen._key == "amount"
        await _field(pilot, screen, "-60")
        await _field(pilot, screen, "zzz")
        assert screen._key == "category" and screen._parts[0].category_id is None
        await _field(pilot, screen, "")  # empty keeps what the part holds: none
        await _field(pilot, screen, "zzz")
        assert screen._key == "hashtags" and screen._parts[0].hashtag_ids == ()

    run_app(scenario, size=SIZE)
    assert notes == [
        "Amount: a signed decimal, e.g. -99.92",
        "No category matches “zzz”.",
        "No hashtag matches “zzz”.",
    ]


# ---- screen 3 · + add a part --------------------------------------------------------


def test_enter_on_add_a_part_adds_an_empty_part_open_on_its_amount(engine):
    """Screen 3: part 3 appears in the table, marked, with `—` cells, its
    fields open below and empty, the cursor on AMOUNT; the count counts it."""

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await pilot.press("down", "down", "enter")
        await pilot.pause()
        assert screen._editing == 2 and screen._key == "amount"
        assert screen.query_one("#bar", Input).value == ""
        lines = _lines(screen, "#parts")
        assert lines[3].split() == ["▌", "3", "—", "—", "—"]
        assert lines[4].strip() == "+  add a part"
        assert lines[-1] == "3 parts  ·  -100.00 of -100.00  ✓"
        assert _lines(screen, "#fields-below") == ["  CATEGORY", "  HASHTAGS", "  NOTE"]

    run_app(scenario, size=SIZE)


@pytest.mark.parametrize("leave", ["escape", "fields"], ids=["esc", "enter-through"])
def test_a_part_left_with_nothing_typed_drops_again(engine, leave):
    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await pilot.press("down", "down", "enter")
        await pilot.pause()
        assert len(screen._parts) == 3
        if leave == "escape":
            await pilot.press("escape")
        else:
            for _ in range(4):
                await _field(pilot, screen, "")
        await pilot.pause()
        assert screen._editing is None
        assert len(screen._parts) == 2
        assert screen._cursor == 2  # back on `+ add a part`
        assert app.screen is screen

    run_app(scenario, size=SIZE)


# ---- the table's keys and the split ---------------------------------------------


def test_two_parts_typed_in_the_fields_and_ctrl_s_split_then_the_ledger_reads_fresh(engine):
    """Spec check 1: -60.00 COMIDA #casa and -40.00 HOGAR, `^s`, and one split
    goes with both, each under a fresh id; the ledger reads its newest rows
    again, the cursor on row 1."""

    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, "t1")
        await _add_part(pilot, screen, "-60", "comida", "casa", "verduras")
        await _add_part(pilot, screen, "-40", "hogar")
        lines = _lines(screen, "#parts")
        assert lines[1].split() == ["1", "-60.00", "COMIDA", "#casa", "verduras"]
        assert lines[2].split() == ["2", "-40.00", "HOGAR", "—"]
        assert lines[-1] == "2 parts  ·  -100.00 of -100.00  ✓"
        reads = len(engine.ledger_reads())
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)
        await wait_for(pilot, lambda: len(engine.ledger_reads()) > reads)
        await wait_for_list(pilot, app)
        assert engine.ledger_reads()[-1].get("after") is None
        assert ledger.query_one(CursorList).cursor_index == 0

    run_app(scenario, size=SIZE)
    path, body = engine.posts[0]
    assert path == "/transactions/t1/split"
    ids = [p["id"] for p in body["parts"]]
    assert len(set(ids)) == 2 and all(uuid.UUID(i) for i in ids)
    assert _sent(engine) == [
        {
            "amount_cents": -6000,
            "category_id": "c-com",
            "hashtag_ids": ["h-casa"],
            "description": "verduras",
        },
        {"amount_cents": -4000, "category_id": "c-hog"},
    ]


def test_ctrl_s_in_the_fields_keeps_the_field_being_typed_and_sends(engine):
    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, "t1")
        await pilot.press("enter")
        screen.query_one("#bar", Input).value = "-100"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert _sent(engine) == [{"amount_cents": -10000}]


def test_a_part_with_only_the_pending_hashtag_sends_none_and_no_category_none(engine):
    """A part naming the pending hashtag alone sends no hashtag, as one with
    none; beside a real one, only the real one goes. The table reads `—`."""

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "t1")
        await _add_part(pilot, screen, "-70", "", "pendiente")
        await _add_part(pilot, screen, "-30", "", "pendiente")
        await pilot.press("enter", "tab", "tab")  # part 2, under the cursor: HASHTAGS
        await _field(pilot, screen, "casa")
        await pilot.press("escape")
        assert _lines(screen, "#parts")[1].split() == ["1", "-70.00", "—", "—"]
        assert _lines(screen, "#parts")[2].split() == ["2", "-30.00", "—", "#casa"]
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: engine.posts)

    run_app(scenario, size=SIZE)
    assert _sent(engine) == [
        {"amount_cents": -7000},
        {"amount_cents": -3000, "hashtag_ids": ["h-casa"]},
    ]


def test_ctrl_x_drops_the_part_under_the_cursor(engine):
    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, "p1")
        await pilot.press("ctrl+x")
        assert [p.note for p in screen._parts] == ["lejía y papel"]
        assert screen._cursor == 0
        await pilot.press("down", "ctrl+x")  # on `+ add a part`: nothing to drop
        assert len(screen._parts) == 1
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert _sent(engine) == [
        {"amount_cents": -4000, "category_id": "c-hog", "description": "lejía y papel"}
    ]


def test_esc_on_the_table_leaves_at_once_with_nothing_sent(engine):
    """Spec check 3: back to the ledger, Tottus still one row."""

    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, "t1")
        await _add_part(pilot, screen, "-60")
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert engine.posts == []


def test_ctrl_s_always_sends_even_when_the_parts_do_not_add_up(engine):
    """The app never stops a send: one part of -60.00 against -100.00 goes as
    typed, and the engine is the one to answer."""

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "t1")
        await _add_part(pilot, screen, "-60")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: engine.posts)

    run_app(scenario, size=SIZE)
    assert _sent(engine) == [{"amount_cents": -6000}]


def test_the_write_carries_one_idempotency_key(configured, monkeypatch):
    """`^s` is one logical write: one `POST`, one `X-Idempotency-Key`, through
    the shared write path and the real HTTP client."""
    client = LineClient(list(LEDGER))
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: client)

    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, "t1")
        await _add_part(pilot, screen, "-60")
        await _add_part(pilot, screen, "-40")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    with respx.mock() as mock:
        route = mock.post(f"{ENGINE_URL}/v1/transactions/t1/split").mock(
            httpx.Response(201, json={"parts": []})
        )
        run_app(scenario, size=SIZE)
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["X-Idempotency-Key"]
    assert [p["amount_cents"] for p in json.loads(request.content)["parts"]] == [-6000, -4000]


# ---- a transaction already split -------------------------------------------------


@pytest.mark.parametrize("key", ["p1", "p2"])
def test_s_on_either_part_opens_the_table_with_both_parts(engine, key):
    """Spec check 5: the table opens with the line's current parts and the
    total is the line's `net_cents`, from one `GET /bank-lines/{id}`; `^s`
    sends the whole new set by the id of the row `s` was pressed on."""

    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, key)
        lines = _lines(screen, "#parts")
        assert lines[1].split()[:4] == ["1", "-60.00", "COMIDA", "#casa"]
        assert lines[2].split()[:3] == ["2", "-40.00", "HOGAR"]
        assert lines[-1] == "2 parts  ·  -100.00 of -100.00  ✓"
        await pilot.press("enter")
        await _field(pilot, screen, "-70")
        await pilot.press("escape", "down", "enter")
        await _field(pilot, screen, "-30")
        await pilot.press("escape")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert engine.line_reads() == ["/bank-lines/bl-9"]
    assert engine.posts[0][0] == f"/transactions/{key}/split"
    assert _sent(engine) == [
        {
            "amount_cents": -7000,
            "category_id": "c-com",
            "hashtag_ids": ["h-casa"],
            "description": "verduras",
        },
        {"amount_cents": -3000, "category_id": "c-hog", "description": "lejía y papel"},
    ]


def test_an_unchanged_re_split_sends_the_parts_as_the_engine_holds_them(engine):
    """Loaded parts go back as they are: a part waiting for a hashtag sends
    none, and the pending category none; every part under a fresh id."""

    async def scenario(pilot, app):
        _ledger, _screen = await _open_split(pilot, app, "p1")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: engine.posts)

    run_app(scenario, size=SIZE)
    assert _sent(engine) == [
        {
            "amount_cents": -6000,
            "category_id": "c-com",
            "hashtag_ids": ["h-casa"],
            "description": "verduras",
        },
        {"amount_cents": -4000, "category_id": "c-hog", "description": "lejía y papel"},
    ]
    assert not {p["id"] for p in engine.posts[0][1]["parts"]} & {"p1", "p2"}


def test_a_row_with_no_bank_line_opens_at_its_own_amount_and_reads_no_line(engine):
    engine.ledger = [{k: v for k, v in TOTTUS.items() if k != "bank_line_id"}]

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "t1")
        return _lines(screen, "#parts")[-1]

    assert run_app(scenario, size=SIZE) == "0 parts  ·  0.00 of -100.00  ·  -100.00 left"
    assert engine.line_reads() == []


def test_a_part_read_from_the_line_is_signed_by_its_transaction_type():
    """`parts` carry a magnitude and `transaction_type`; a part money out reads
    negative and a part money in positive, and the pending category as none."""
    refs = QuickAddRefs([], [], [], {}, {}, {}, pending=("c-pend", "@Pendiente"))
    out = part_from_engine(import_part("o", -6000, category_id="c-pend"), refs)
    into = part_from_engine(import_part("i", 5000, category_id="c-com"), refs)
    assert (out.amount_cents, out.category_id) == (-6000, None)
    assert (into.amount_cents, into.category_id) == (5000, "c-com")


# ---- screens 4 to 6 · the title ---------------------------------------------------

NEW_TITLE = "Tottus — semana"


async def _open_title(pilot, screen) -> None:
    """`↑` to the TITLE line, then `⏎`."""
    while screen._cursor != TITLE_ROW:
        await pilot.press("up")
    await pilot.press("enter")
    await pilot.pause()


async def _retitle(pilot, screen, title: str) -> None:
    """`⏎` on the TITLE line, `title` typed, `⏎`."""
    await _open_title(pilot, screen)
    await _field(pilot, screen, title)


def test_enter_on_the_title_opens_one_field_below_and_enter_keeps_it(engine):
    """Screen 4: `⏎` on the TITLE line opens `TITLE · changes it on every
    part` below, one field holding the title; the TITLE line reads
    `▌TITLE …` in the accent while it is open, and the footer is `esc Back to
    the parts  ^s Split`. `⏎` puts the new title on the TITLE line and goes
    back to the table, the cursor on the TITLE line."""

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await _open_title(pilot, screen)
        assert screen._title_open and screen._editing is None
        assert screen.query_one("#part-fields").display
        assert app.focused is screen.query_one("#bar", Input)
        assert screen.query_one("#bar", Input).value == "Tottus Jockey Plaza"
        head = _lines(screen, "#part-head")
        assert head[0].startswith("────") and head[1] == "TITLE · changes it on every part"
        assert str(screen.query_one("#part-field").content).strip() == "▌ TITLE"
        for hidden in ("#fields-above", "#part-suggest", "#fields-below"):
            assert not screen.query_one(hidden).display
        assert _footer(screen) == [("esc", "Back to the parts"), ("^s", "Split")]
        open_line = screen.query_one("#split-title", Static).content
        assert not any("reverse" in str(row.spans) for row in _part_rows(screen))
        screen.query_one("#bar", Input).value = NEW_TITLE
        await pilot.pause()
        typing = _text(screen, "#split-title").strip()
        await pilot.press("enter")
        await pilot.pause()
        assert not screen._title_open and screen._cursor == TITLE_ROW
        assert not screen.query_one("#part-fields").display
        assert app.focused is None
        assert _footer(screen)[0] == ("esc", "Cancel")
        return open_line, typing, _text(screen, "#split-title").strip()

    open_line, typing, kept = run_app(scenario, size=SIZE)
    assert open_line.plain == "▌TITLE      Tottus Jockey Plaza"
    assert str(open_line.style) == f"bold {ACCENT}" and not open_line.spans
    assert typing == "▌TITLE      Tottus Jockey Plaza"  # the field holds the new one
    assert kept.startswith(f"TITLE      {NEW_TITLE}") and kept.endswith("same on every part")
    assert engine.posts == []


def test_esc_in_the_title_field_leaves_the_title_as_it_was(engine):
    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await _open_title(pilot, screen)
        screen.query_one("#bar", Input).value = "never kept"
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is screen
        assert not screen._title_open and screen._cursor == TITLE_ROW
        assert screen._title == "Tottus Jockey Plaza"
        assert _text(screen, "#split-title").strip().startswith("TITLE      Tottus Jockey Plaza")
        await pilot.press("enter")
        await pilot.pause()
        assert screen.query_one("#bar", Input).value == "Tottus Jockey Plaza"

    run_app(scenario, size=SIZE)
    assert engine.posts == []


@pytest.mark.parametrize("typed", ["", "   "], ids=["empty", "spaces"])
@pytest.mark.parametrize("key", ["enter", "ctrl+s"])
def test_an_emptied_title_is_refused_as_on_the_edit_form_and_nothing_is_sent(engine, typed, key):
    """Screen 5: `⏎` (or `^s`) on an emptied title says `Title is required.`
    as an error toast, the Edit form's note; the field stays open and the
    TITLE line keeps the title it had. Nothing is sent."""
    notes: list[tuple[str, object]] = []

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        screen.notify = lambda message, **kw: notes.append((message, kw.get("severity")))
        await _open_title(pilot, screen)
        await _field(pilot, screen, typed, key=key)
        assert screen._title_open
        assert screen.query_one("#part-fields").display
        assert app.focused is screen.query_one("#bar", Input)
        assert screen._title == "Tottus Jockey Plaza"
        assert _text(screen, "#split-title").strip() == "▌TITLE      Tottus Jockey Plaza"
        assert not screen._sending

    run_app(scenario, size=SIZE)
    assert notes == [(TITLE_REQUIRED, "error")]
    assert TITLE_REQUIRED == "Title is required."
    assert engine.posts == []


def test_a_changed_title_is_sent_once_beside_the_parts(engine):
    """Spec check 1: the title changed to `Tottus — semana`, two parts and
    `^s` send `title` beside `parts`, once for the line; the engine writes it
    onto every part (contract: POST /v1/transactions/{transaction_id}/split),
    which the live contract test pins. The screen closes and the ledger reads
    fresh."""

    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, "t1")
        await _retitle(pilot, screen, f"  {NEW_TITLE}  ")
        await _add_part(pilot, screen, "-60", "comida")
        await _add_part(pilot, screen, "-40", "hogar")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    ((path, body),) = engine.posts
    assert path == "/transactions/t1/split"
    assert set(body) == {"parts", "title"}
    assert body["title"] == NEW_TITLE  # trimmed, as the Edit form keeps it
    assert all("title" not in part for part in body["parts"])
    assert _sent(engine) == [
        {"amount_cents": -6000, "category_id": "c-com"},
        {"amount_cents": -4000, "category_id": "c-hog"},
    ]


@pytest.mark.parametrize(
    "retitles",
    [[], ["Tottus Jockey Plaza"], [NEW_TITLE, "Tottus Jockey Plaza"]],
    ids=["untouched", "same-typed-again", "changed-back"],
)
def test_a_title_that_matches_the_transactions_is_not_sent(engine, retitles):
    """Spec check 2: a title left alone — or typed back to what it is — is
    not sent, so every part keeps the transaction's title."""

    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, "t1")
        for title in retitles:
            await _retitle(pilot, screen, title)
        await _add_part(pilot, screen, "-60")
        await _add_part(pilot, screen, "-40")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    ((_path, body),) = engine.posts
    assert set(body) == {"parts"}


def test_ctrl_s_in_the_title_field_keeps_the_title_typed_and_sends_it(engine):
    async def scenario(pilot, app):
        ledger, screen = await _open_split(pilot, app, "p1")
        await _open_title(pilot, screen)
        screen.query_one("#bar", Input).value = NEW_TITLE
        await pilot.pause()
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    ((_path, body),) = engine.posts
    assert body["title"] == NEW_TITLE and len(body["parts"]) == 2


def test_ctrl_x_on_the_title_line_drops_nothing(engine):
    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await pilot.press("up", "ctrl+x")
        await pilot.pause()
        assert screen._cursor == TITLE_ROW and len(screen._parts) == 2

    run_app(scenario, size=SIZE)


def _locked_with_a_part() -> EngineError:
    """A `422` naming the locked title and a part's amount together, as the
    route reports every failure in one answer
    (contract: POST /v1/transactions/{transaction_id}/split, "Validation")."""
    fields = {
        "title": "stand-in words: the title is locked by a completed reconciliation",
        "parts.1.amount_cents": "stand-in words: must not be zero",
    }
    return EngineError(
        "VALIDATION_ERROR",
        "Validation failed.",
        fields,
        422,
        {},
        reasons={"title": "LOCKED", "parts.1.amount_cents": "ZERO_AMOUNT"},
    )


def test_a_locked_title_shows_under_the_parts_with_a_parts_refusal_and_nothing_splits(engine):
    """Screen 6: `^s` with a new title on a transaction in a completed
    reconciliation: the engine's `title` refusal reads `! title: …` under the
    parts with the part's own line, then `Nothing was split.`; the screen
    stays and the title is still the one typed. The title kept again as it is
    leaves the refusal; changed, the refusal goes."""
    engine.errors["POST"] = _locked_with_a_part()

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "p1")
        await _retitle(pilot, screen, NEW_TITLE)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: screen._refusal is not None)
        assert app.screen is screen
        shown = _text(screen, "#parts")
        title = _text(screen, "#split-title").strip()
        await _retitle(pilot, screen, NEW_TITLE)
        kept_same = screen._refusal is not None
        await _retitle(pilot, screen, "Tottus Jockey Plaza")
        return shown, title, kept_same, _text(screen, "#parts")

    shown, title, kept_same, after = run_app(scenario, size=SIZE)
    lines = [line.strip() for line in shown.splitlines()]
    tail = lines[lines.index("VALIDATION_ERROR — Validation failed.") :]
    assert tail[1:] == [
        "! title: stand-in words: the title is locked by a completed reconciliation",
        "! part 2 (amount): stand-in words: must not be zero",
        "Nothing was split.",
    ]
    assert title.startswith(f"TITLE      {NEW_TITLE}")
    assert kept_same
    assert "VALIDATION_ERROR" not in after and "Nothing was split." not in after
    ((_path, body),) = engine.posts
    assert body["title"] == NEW_TITLE


# ---- the refusals -------------------------------------------------------------------


def _mismatch() -> EngineError:
    keys = ("parts", "parts.0.amount_cents", "parts.1.amount_cents")
    return EngineError(
        "VALIDATION_ERROR",
        "Validation failed.",
        {k: MISMATCH for k in keys},
        422,
        {},
        reasons={k: "SPLIT_TOTAL_MISMATCH" for k in keys},
    )


def test_parts_short_of_the_total_say_what_is_left_and_keep_the_refusal_under_them(engine):
    """Spec check 6: -60.00 and -30.00 of -100.00 show `-10.00 left` in red;
    `^s` shows the engine's words under the parts, each `parts.<i>` key read as
    part i+1, the amounts it names in the error colour, `Nothing was split.`;
    the screen stays, and changing a part clears it."""
    engine.errors["POST"] = _mismatch()

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "t1")
        await _add_part(pilot, screen, "+20")
        await _add_part(pilot, screen, "-110")
        await _add_part(pilot, screen, "-10")
        await pilot.press("ctrl+x")  # drop the -10.00 again: -90.00 of -100.00
        count = screen.query_one("#parts", Static).content.renderables[5]
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: screen._refusal is not None)
        assert app.screen is screen
        shown = _text(screen, "#parts")
        table = screen.query_one("#parts", Static).content.renderables
        amounts = [table[1], table[2]]
        await pilot.press("enter")
        await _field(pilot, screen, "-20")
        return count, shown, amounts, _text(screen, "#parts")

    count, shown, amounts, after = run_app(scenario, size=SIZE)
    assert count.plain == "2 parts  ·  -90.00 of -100.00  ·  -10.00 left"
    assert _styles_of(count, "-10.00 left") == {PALETTE.error}
    lines = [line.strip() for line in shown.splitlines()]
    tail = lines[lines.index("VALIDATION_ERROR — Validation failed.") :]
    flat = " ".join(tail)
    assert f"! parts: {MISMATCH}" in flat
    assert f"! part 1 (amount): {MISMATCH}" in flat
    assert f"! part 2 (amount): {MISMATCH}" in flat
    assert tail[-1] == "Nothing was split."
    # the named amounts in the error colour, the positive one included
    assert _styles_of(amounts[0], "20.00") == {PALETTE.error}
    assert PALETTE.error in _styles_of(amounts[1], "-110.00")  # under the cursor too
    assert "VALIDATION_ERROR" not in after and "Nothing was split." not in after
    assert len(engine.posts) == 1


#: Every other refusal of the split route: (code, status, key, reason, the app's
#: line under it or None). The line is chosen by the reason alone.
OTHER_REFUSALS = [
    ("VALIDATION_ERROR", 422, "transaction_id", "OPENING_BALANCE_NOT_SPLIT", None),
    ("VALIDATION_ERROR", 422, "transaction_id", "SPLIT_LINE_PARTS_DIVERGE", None),
    ("VALIDATION_ERROR", 422, "parts.1.hashtag_ids", "PENDING_HASHTAG_NOT_ALONE", None),
    ("VALIDATION_ERROR", 422, "parts.0.amount_cents", "ZERO_AMOUNT", None),
    ("VALIDATION_ERROR", 422, "parts.0.category_id", "INVALID_REFERENCE", None),
    ("VALIDATION_ERROR", 422, "parts.0.category_id", "RESERVED_CATEGORY", None),
    ("VALIDATION_ERROR", 422, "parts.1.id", "DUPLICATE_IN_REQUEST", None),
    ("VALIDATION_ERROR", 422, "parts", "OUT_OF_RANGE", None),
    (
        "CONFLICT",
        409,
        "parts.0.id",
        "ID_EXISTS",
        "Not your mistake: the app sent it wrong and nothing was saved. "
        "Try again; if it happens again, report it.",
    ),
    (
        "CONFLICT",
        409,
        "category_id",
        "RESERVED_NAME_HELD",
        "One of your categories has a built-in category's name: "
        "rename it on Manage ▸ Categories, then save again.",
    ),
    ("CONFLICT", 409, "hashtag_ids", "RESERVED_NAME_HELD", None),
    (
        "CONFLICT",
        409,
        "transaction_id",
        "CONCURRENT_CHANGE",
        "It changed at the same moment: save again.",
    ),
]


@pytest.mark.parametrize(
    ("code", "status", "key", "reason", "line"),
    OTHER_REFUSALS,
    ids=[f"{r[3]}-{r[2]}" for r in OTHER_REFUSALS],
)
def test_every_other_refusal_shows_the_engine_words_in_the_same_place(
    engine, code, status, key, reason, line
):
    words = f"Engine words for {reason}."
    fields = {key: "stand-in field words"}
    engine.errors["POST"] = EngineError(code, words, fields, status, {}, reasons={key: reason})

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "t1")
        await _add_part(pilot, screen, "-60")
        await _add_part(pilot, screen, "-40")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: screen._refusal is not None)
        assert app.screen is screen
        return _text(screen, "#parts")

    shown = run_app(scenario, size=SIZE)
    lines = [row.strip() for row in shown.splitlines()]
    tail = lines[lines.index(f"{code} — Engine words for {reason}.") :]
    assert tail[1] == f"! {part_key(key)}: stand-in field words"
    assert tail[2] == "Nothing was split."
    if line is None:
        assert [row for row in tail[3:] if row] == []
    else:
        assert [row for row in tail[3:] if row] == [line]


def test_a_split_on_an_archived_account_shows_the_engine_words_alone(engine):
    """Screen 3 A of expense-world-archived-account.html: the split screen was
    opened before the account was archived, and `^s` is refused. Under the
    parts: the engine's words, its `transaction_id` words, `Nothing was split.`
    and no line of the app's; the screen stays with the parts as typed."""
    words = archived_words("split", "transaction")
    engine.errors["POST"] = archived_refusal(422, words, "transaction_id")

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "t1")
        await _add_part(pilot, screen, "-60")
        await _add_part(pilot, screen, "-40")
        typed = list(screen._parts)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: screen._refusal is not None)
        assert app.screen is screen
        assert screen._parts == typed
        return _text(screen, "#parts")

    shown = run_app(scenario, size=SIZE)
    lines = [row.strip() for row in shown.splitlines()]
    tail = lines[lines.index(f"VALIDATION_ERROR — {words}") :]
    assert [row for row in tail[1:] if row] == [
        f"! transaction_id: {ARCHIVED_FIELD_WORDS}",
        "Nothing was split.",
    ]
    assert len(engine.posts) == 1


def test_part_keys_read_by_number():
    assert part_key("parts.0.amount_cents") == "part 1 (amount)"
    assert part_key("parts.11.category_id") == "part 12 (category_id)"
    assert part_key("parts.2") == "part 3"
    assert part_key("parts") == "parts"
    assert part_key("transaction_id") == "transaction_id"


def test_a_refused_line_hangs_under_its_own_words():
    """`hanging`: a `! …` line is the `!` beside its words, so a wrapped line
    starts under the words; any other line is itself."""
    plain = Text("Nothing was split.")
    assert hanging(plain) is plain
    long = Text("! part 1 (amount): " + "word " * 30)
    rendered = render_text(hanging(long), width=40).splitlines()
    assert rendered[0].startswith("! part 1 (amount):")
    assert all(row.startswith("  ") for row in rendered[1:])


def test_an_engine_out_of_reach_says_so_under_the_parts(engine):
    engine.errors["POST"] = EngineConnectionError(url="https://x.invalid", original=Exception("no"))

    async def scenario(pilot, app):
        _ledger, screen = await _open_split(pilot, app, "t1")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: screen._refusal is not None)
        return _text(screen, "#parts")

    shown = run_app(scenario, size=SIZE)
    assert "could not reach engine at https://x.invalid (is it running?)" in shown
    assert "Nothing was split." not in shown
