"""`s` on the ledger — the split screen: split, re-split, and the refusals.

Screens: docs/mockups/expense-world-split-action.html (1, 2 B, 3, 4 B). Every
engine call goes to one fake engine (`LineClient`), the ledger's reads, the
split screen's and the split itself, so a test can assert exactly what was
read and sent. One test sends the split through the real HTTP client against
a respx-mocked engine, for the idempotency key. The refusals' words are
stand-ins, except the mismatch sentence, which is the contract's own
(contract: POST /v1/transactions/{transaction_id}/split, "The total is kept").
"""

import json
import uuid

import httpx
import pytest
import respx
from rich.text import Text
from textual.widgets import Input, Static

from expense.errors import EngineConnectionError, EngineError
from expense.tui.screens.split import (
    SplitScreen,
    count_line,
    part_key,
)
from expense.tui.screens.transactions import LedgerFilter, TransactionsScreen
from expense.tui.theme import PALETTE
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_URL,
    FakeClient,
    cursor_page,
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
        "version": 1,
    }


#: One purchase never split, and one already split into two parts (screen 1).
TOTTUS = _tx("t1", -10000, line="bl-1")
CAFE = _tx("t2", -1850, line="bl-2", title="Cafe Andino", category="c-com", tags=["h-casa"])
PART_1 = _tx("p1", -6000, line="bl-9", category="c-com", tags=["h-casa"], note="verduras")
PART_2 = _tx("p2", -4000, line="bl-9", category="c-hog", note="lejía y papel")
LEDGER = [TOTTUS, CAFE, PART_1, PART_2]
LINES = {"bl-1": [TOTTUS], "bl-2": [CAFE], "bl-9": [PART_1, PART_2]}
#: What `GET /bank-lines/{id}` reads (contract: GET /v1/bank-lines/{bank_line_id}); the
#: screen reads `net_cents` alone.
NET = {"bl-1": -10000, "bl-2": -1850, "bl-9": -10000}

MISMATCH = (
    "Must add up to the line's total: the line's total is -10000 cents "
    "and the parts add up to -9000."
)


class LineClient(FakeClient):
    """The fake engine: reference lists whole, `GET /transactions` by its
    `bank_line_id` filter (the ledger without one), the count, and each bank
    line's figures."""

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
        for line, net in NET.items():
            self.get_responses[f"/bank-lines/{line}"] = {
                "id": line,
                "account_id": "acc1",
                "operation_code": None,
                "net_cents": net,
                "part_count": len(LINES[line]),
            }

    def get(self, path: str, *, auth: bool = True, params: dict | None = None) -> dict:
        params = params or {}
        if path == "/transactions":
            self._record("GET", path, params)
            line = params.get("bank_line_id")
            rows = LINES.get(line, []) if line else self.ledger
            limit = params.get("limit") or 50
            return cursor_page(rows[:limit], limit=limit)
        if path == "/transactions/count":
            self._record("GET", path, params)
            return {"count": len(self.ledger)}
        return super().get(path, auth=auth, params=params)

    def line_reads(self) -> list[tuple[str, object]]:
        """The split screen's own reads: the line's parts and its figures."""
        return [
            (path, body.get("bank_line_id") if path == "/transactions" else None)
            for method, path, body in self.calls
            if method == "GET"
            and (
                path.startswith("/bank-lines/")
                or (path == "/transactions" and body.get("bank_line_id"))
            )
        ]

    def ledger_reads(self) -> list[dict]:
        return [
            body
            for method, path, body in self.calls
            if method == "GET" and path == "/transactions" and not body.get("bank_line_id")
        ]


@pytest.fixture
def engine(monkeypatch):
    client = LineClient(list(LEDGER))
    monkeypatch.setattr("expense.http.ExpenseClient", lambda *a, **k: client)
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: client)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    return client


def _footer(screen) -> list[str]:
    return [
        f"{a.binding.key} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


async def _open_ledger(pilot, app, flt=None) -> TransactionsScreen:
    screen = TransactionsScreen(filter=flt)
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    screen.query_one(CursorList).focus()
    await pilot.pause()
    return screen


async def _cursor_to(pilot, ledger, key) -> None:
    listing = ledger.query_one(CursorList)
    listing.set_cursor(listing.index_of(key))
    await pilot.pause()


async def _open_split(pilot, app, ledger, key) -> SplitScreen:
    await _cursor_to(pilot, ledger, key)
    await pilot.press("s")
    await wait_for(pilot, lambda: isinstance(app.screen, SplitScreen))
    screen = app.screen
    await wait_for(pilot, lambda: screen._refs is not None, message="split screen never loaded")
    await pilot.pause()
    return screen


async def _type(pilot, screen, line: str) -> None:
    """Type `line` into the bar and press `↵`."""
    bar = screen.query_one("#bar", Input)
    bar.value = line
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


def _text(screen, widget_id: str) -> str:
    return render_text(screen.query_one(widget_id, Static).content, width=110)


def _styles_of(text: Text, needle: str) -> set[str]:
    start = text.plain.index(needle)
    return {str(s.style) for s in text.spans if s.start <= start < s.end}


# ---- screen 1 · `s Split` on the ledger --------------------------------------


@pytest.mark.parametrize(
    "flt",
    [None, LedgerFilter("category", "c-pend", "@Pendiente")],
    ids=["whole", "filtered"],
)
def test_s_sits_before_d_and_opens_a_purchase_never_split(engine, flt):
    """`s Split` is the footer's key before `d Delete`; on a row never split it
    opens screen 2 headed by the purchase as the ledger has it, with an empty
    list, after reading the row's line: its parts and its total."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app, flt)
        assert _footer(ledger)[-2:] == ["s Split", "d Delete"]
        screen = await _open_split(pilot, app, ledger, "t1")
        assert screen.crumb[-1] == "Split"
        assert screen.crumb[:-1] == ledger.crumb
        head = _text(screen, "#split-head")
        assert head.strip() == "Tottus Jockey Plaza  ·  2026-10-11  ·  Sueldo Soles  ·  -100.00 PEN"
        assert screen._parts == []
        assert _text(screen, "#parts").strip() == "0 parts · 0.00 of -100.00 · -100.00 left"
        assert _footer(screen) == ["escape Cancel", "ctrl+s Split"]
        assert str(screen.query_one("#legend", Static).content) == (
            "±amount · @category · #tag · //note            ↵ adds the part"
        )
        assert screen.query_one("#bar", Input).has_focus

    run_app(scenario, size=SIZE)
    assert engine.line_reads() == [("/transactions", "bl-1"), ("/bank-lines/bl-1", None)]


def test_s_is_off_while_rows_are_selected(engine):
    """Like `d`: with a selection `s` leaves the footer and does nothing; `esc`
    clears the selection and it is back."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        await pilot.press("space")
        await pilot.pause()
        assert ledger._selected
        assert "s Split" not in _footer(ledger)
        await pilot.press("s")
        await pilot.pause()
        assert app.screen is ledger
        await pilot.press("escape")
        await pilot.pause()
        assert _footer(ledger)[-2:] == ["s Split", "d Delete"]

    run_app(scenario, size=SIZE)
    assert engine.line_reads() == []


# ---- screen 2 B · typing the parts -------------------------------------------


def test_typed_parts_join_the_list_and_ctrl_s_splits_then_the_ledger_reads_fresh(engine):
    """Each `↵` adds the typed line as a part; `^s` sends the whole set in one
    split, each part under a fresh id, and the ledger reads its newest rows
    again, the cursor on row 1."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "t1")
        screen.query_one("#bar", Input).value = "-60 @comida #casa //verduras"
        await pilot.pause()
        assert str(screen.query_one("#hint", Static).content) == "-60.00 · COMIDA · #casa"
        await pilot.press("enter")
        await pilot.pause()
        assert screen.query_one("#bar", Input).value == ""
        screen.query_one("#bar", Input).value = "-40 @hogar //lejía y papel"
        await pilot.pause()
        # screen 2 B: what the line makes of the part, under the bar
        assert str(screen.query_one("#hint", Static).content) == "-40.00 · HOGAR · no hashtag"
        parts = _text(screen, "#parts")
        assert "1 part · -60.00 of -100.00 · -40.00 left" in parts
        await pilot.press("enter")
        await pilot.pause()
        parts = _text(screen, "#parts")
        assert "2 parts · -100.00 of -100.00" in parts and "left" not in parts
        reads = len(engine.ledger_reads())
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)
        await wait_for(pilot, lambda: len(engine.ledger_reads()) > reads)
        await wait_for_list(pilot, app)
        assert engine.ledger_reads()[-1].get("after") is None
        assert ledger.query_one(CursorList).cursor_index == 0

    run_app(scenario, size=SIZE)
    assert len(engine.posts) == 1
    path, body = engine.posts[0]
    assert path == "/transactions/t1/split"
    ids = [p.pop("id") for p in body["parts"]]
    assert len(set(ids)) == 2 and all(uuid.UUID(i) for i in ids)
    assert body == {
        "parts": [
            {
                "amount_cents": -6000,
                "category_id": "c-com",
                "hashtag_ids": ["h-casa"],
                "description": "verduras",
            },
            {"amount_cents": -4000, "category_id": "c-hog", "description": "lejía y papel"},
        ]
    }


def test_a_part_with_no_category_or_hashtag_reads_pending_dim_and_sends_only_real_tags(engine):
    """A part naming no category reads `@Pendiente` dim and sends none; one
    naming the pending hashtag beside a real one sends the real one only."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "t1")
        await _type(pilot, screen, "-70")
        await _type(pilot, screen, "-30 #Pendiente #casa")
        table = screen.query_one("#parts", Static).content.renderables[0]
        first = [str(col._cells[0]) for col in table.columns]
        assert first[2:4] == ["@Pendiente", "#Pendiente"]
        assert table.columns[2]._cells[0].style == "dim"
        assert table.columns[3]._cells[0].style == "dim"
        assert str(table.columns[3]._cells[1]) == "#casa"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: engine.posts)

    run_app(scenario, size=SIZE)
    parts = engine.posts[0][1]["parts"]
    assert [{k: v for k, v in p.items() if k != "id"} for p in parts] == [
        {"amount_cents": -7000},
        {"amount_cents": -3000, "hashtag_ids": ["h-casa"]},
    ]


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("-40 $sueldo", "a part keeps the purchase's account and date"),
        ("-40 ayer", "a part keeps the purchase's account and date"),
        ("-40 lejía", "a part keeps the purchase's title"),
        ("@hogar", "the line has no amount — a number needs a sign to be one"),
    ],
    ids=["account", "date", "title-words", "no-amount"],
)
def test_a_line_the_part_cannot_take_is_refused_in_place(engine, line, reason):
    """The line stays in the bar with the reason under it; the list is
    untouched, and the next keystroke clears the reason."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "t1")
        await _type(pilot, screen, line)
        assert screen._parts == []
        assert screen.query_one("#bar", Input).value == line
        assert screen.query_one("#part-refused", Static).display
        shown = screen.query_one("#part-refused", Static).content
        assert shown.plain == f"! {reason}"
        assert str(shown.style) == PALETTE.error
        await pilot.press("x")
        await pilot.pause()
        assert not screen.query_one("#part-refused", Static).display

    run_app(scenario, size=SIZE)
    assert engine.posts == []


def test_ctrl_s_always_sends_even_when_the_parts_do_not_add_up(engine):
    """The app never stops a send: one part of -60.00 against -100.00 goes as
    typed, and the engine is the one to answer."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "t1")
        await _type(pilot, screen, "-60")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: engine.posts)

    run_app(scenario, size=SIZE)
    assert [p["amount_cents"] for p in engine.posts[0][1]["parts"]] == [-6000]


def test_left_is_in_the_error_colour_while_it_is_not_zero():
    """`left` is the parts as typed against the engine's total, and shows only
    while it is not 0 — in the error colour whichever way it points."""
    from expense.tui.screens.split import Part

    def part(cents):
        return Part(str(cents), cents, None, (), None)

    short = count_line([part(-6000)], -10000, palette=PALETTE)
    assert short.plain == "1 part · -60.00 of -100.00 · -40.00 left"
    assert _styles_of(short, "-40.00") == {PALETTE.error}
    over = count_line([part(-12000)], -10000, palette=PALETTE)
    assert over.plain == "1 part · -120.00 of -100.00 · 20.00 left"
    assert _styles_of(over, "20.00 left") == {PALETTE.error}
    mixed = count_line([part(-12000), part(2000)], -10000, palette=PALETTE)
    assert mixed.plain == "2 parts · -100.00 of -100.00"


def test_the_write_carries_one_idempotency_key(configured, monkeypatch):
    """`^s` is one logical write: one `POST`, one `X-Idempotency-Key`, through
    the shared write path and the real HTTP client."""
    client = LineClient(list(LEDGER))
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: client)

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "t1")
        await _type(pilot, screen, "-60")
        await _type(pilot, screen, "-40")
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


# ---- screen 3 · splitting it again -------------------------------------------


@pytest.mark.parametrize("key", ["p1", "p2"])
def test_s_on_either_part_opens_with_all_its_parts_and_sends_the_whole_new_set(engine, key):
    """The list opens with the line's current parts and the total is the line's
    `net_cents`; `↑` picks a part, `↵` puts it in the bar to change, `ctrl+x`
    drops one, a typed line adds one, and `^s` sends the whole new set by the
    id of the row `s` was pressed on."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, key)
        head = _text(screen, "#split-head").strip()
        assert head.endswith("-100.00 PEN  ·  2 parts")
        parts = _text(screen, "#parts")
        assert "2 parts · -100.00 of -100.00" in parts
        assert "verduras" in parts and "lejía y papel" in parts
        assert str(screen.query_one("#hint", Static).content) == (
            "↑↓ picks a part · ↵ puts it in the bar to change · ^x drops it"
        )
        # part 2 waits for a hashtag: #Pendiente, dim
        table = screen.query_one("#parts", Static).content.renderables[0]
        assert str(table.columns[3]._cells[1]) == "#Pendiente"
        assert table.columns[3]._cells[1].style == "dim"
        await pilot.press("up", "up")
        assert screen._picked == 0
        await pilot.press("enter")
        await pilot.pause()
        assert screen.query_one("#bar", Input).value == "-60 @COMIDA #casa //verduras"
        await _type(pilot, screen, "-70 @COMIDA #casa //verduras")
        await pilot.press("down")
        assert screen._picked == 1
        await pilot.press("ctrl+x")
        await pilot.pause()
        assert len(screen._parts) == 1
        await _type(pilot, screen, "-30 @hogar //lejía y papel")
        assert "2 parts · -100.00 of -100.00" in _text(screen, "#parts")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert engine.line_reads() == [("/transactions", "bl-9"), ("/bank-lines/bl-9", None)]
    ((path, body),) = engine.posts
    assert path == f"/transactions/{key}/split"
    assert [{k: v for k, v in p.items() if k != "id"} for p in body["parts"]] == [
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
    none, and the pending category none."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        await _open_split(pilot, app, ledger, "p1")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: engine.posts)

    run_app(scenario, size=SIZE)
    parts = engine.posts[0][1]["parts"]
    assert [{k: v for k, v in p.items() if k != "id"} for p in parts] == [
        {
            "amount_cents": -6000,
            "category_id": "c-com",
            "hashtag_ids": ["h-casa"],
            "description": "verduras",
        },
        {"amount_cents": -4000, "category_id": "c-hog", "description": "lejía y papel"},
    ]
    assert not {p["id"] for p in parts} & {"p1", "p2"}


def test_a_row_with_no_bank_line_opens_at_its_own_amount_and_reads_no_line(engine):
    engine.ledger = [{k: v for k, v in TOTTUS.items() if k != "bank_line_id"}]

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "t1")
        return _text(screen, "#split-head").strip()

    head = run_app(scenario, size=SIZE)
    assert head.endswith("-100.00 PEN")
    assert engine.line_reads() == []


# ---- screen 4 B · the refusals --------------------------------------------------


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


def test_parts_that_do_not_add_up_keep_the_refusal_under_the_parts(engine):
    """Screen 4 B: the engine's words under the list, each `parts.<i>` key read
    as part i+1, the amounts it names in the error colour, `Nothing was
    split.`; the screen stays, and changing the list clears it."""
    engine.errors["POST"] = _mismatch()

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "t1")
        await _type(pilot, screen, "+20")
        await _type(pilot, screen, "-110")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: screen._refusal is not None)
        assert app.screen is screen
        shown = _text(screen, "#parts")
        table = screen.query_one("#parts", Static).content.renderables[0]
        amounts = table.columns[1]._cells
        await pilot.press("ctrl+x")  # nothing picked: the list stands
        still = screen._refusal is not None
        await _type(pilot, screen, "-10")
        return shown, amounts, still, _text(screen, "#parts")

    shown, amounts, still, after = run_app(scenario, size=SIZE)
    lines = [line.strip() for line in shown.splitlines()]
    tail = lines[lines.index("VALIDATION_ERROR — Validation failed.") :]
    assert tail[0] == "VALIDATION_ERROR — Validation failed."
    flat = " ".join(tail)
    assert f"! parts: {MISMATCH}" in flat
    assert f"! part 1 (amount): {MISMATCH}" in flat
    assert f"! part 2 (amount): {MISMATCH}" in flat
    assert tail[-1] == "Nothing was split."
    # the named amounts in the error colour, the positive one included
    assert [a.plain for a in amounts] == ["20.00", "-110.00"]
    assert {str(a.style) for a in amounts} == {PALETTE.error}
    assert still
    assert "VALIDATION_ERROR" not in after and "Nothing was split." not in after


#: Every other refusal of the split route: (code, status, key, reason, the app's
#: line under it or None). The line is chosen by the reason alone.
OTHER_REFUSALS = [
    ("VALIDATION_ERROR", 422, "transaction_id", "OPENING_BALANCE_NOT_SPLIT", None),
    ("VALIDATION_ERROR", 422, "transaction_id", "SPLIT_LINE_PARTS_DIVERGE", None),
    ("VALIDATION_ERROR", 422, "transaction_id", "SPLIT_RECONCILIATION_MIXED", None),
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
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "t1")
        await _type(pilot, screen, "-60")
        await _type(pilot, screen, "-40")
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
        assert tail[3:] == [] or all(not row for row in tail[3:])
    else:
        assert [row for row in tail[3:] if row] == [line]


def test_part_keys_read_by_number():
    assert part_key("parts.0.amount_cents") == "part 1 (amount)"
    assert part_key("parts.11.category_id") == "part 12 (category_id)"
    assert part_key("parts.2") == "part 3"
    assert part_key("parts") == "parts"
    assert part_key("transaction_id") == "transaction_id"


def test_an_engine_out_of_reach_says_so_under_the_parts(engine):
    engine.errors["POST"] = EngineConnectionError(url="https://x.invalid", original=Exception("no"))

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "t1")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: screen._refusal is not None)
        return _text(screen, "#parts")

    shown = run_app(scenario, size=SIZE)
    assert "could not reach engine at https://x.invalid (is it running?)" in shown
    assert "Nothing was split." not in shown


def test_esc_leaves_with_nothing_sent(engine):
    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        screen = await _open_split(pilot, app, ledger, "p1")
        await pilot.press("up")
        await pilot.press("escape")  # unpick
        assert app.screen is screen and screen._picked is None
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert engine.posts == []
