"""The Edit form with its parts: `⏎` and `s` on a ledger row, `⏎` in "no batch".

Screens: docs/mockups/expense-world-split-transaction-screen.html, with the
owner's picks 1 A to 6 A. On top, the line's shared fields; below, every part
of the line in a table, and with two parts or more the line adding them up. One
save is one `PUT /bank-lines/{id}`, the line fields the owner changed beside the
line's whole set of parts (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"),
and what is read-only is what the line's `edit_limits` names
(contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). Every engine
call goes to one fake engine (`LineClient`), so a test asserts exactly what was
read and sent. Each line's `edit_limits` is the one the live engine answers for
its state (tests/contract/test_bank_line_edit_limits.py). The refusals' words
are stand-ins, except the mismatch sentence and the opening balance's, which
are the contract's own (contract: PUT /v1/bank-lines/{bank_line_id}, "The total")
(contract: PUT /v1/bank-lines/{bank_line_id}, "The parts' rules").
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
from expense.tui.screens.edit_form import (
    EVERY_PART_NOTE,
    NOTE_GOES_ON,
    NOTE_SAVES,
    BankLineEditFormScreen,
    EditFormScreen,
)
from expense.tui.screens.reconciliations import ReconciliationsScreen
from expense.tui.screens.transactions import TransactionsScreen
from expense.tui.theme import ACCENT, PALETTE
from expense.tui.widgets.cursor_list import CursorList
from expense.tui.widgets.parts_table import (
    Part,
    count_line,
    key_words,
    part_empty,
    part_from_engine,
)
from expense.tui.widgets.refusal import hanging
from tests.unit.helpers import (
    ENGINE_URL,
    FakeClient,
    cursor_page,
    edit_limits,
    import_part,
    line_code_of,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

SIZE = (120, 50)

ACCOUNTS = [
    {
        "id": "acc1",
        "name": "Sueldo Soles",
        "currency_code": "PEN",
        "is_person": False,
        "is_archived": False,
        "opening_balance_transaction_id": "o1",
        "statement_code": None,
    },
    {
        "id": "acc2",
        "name": "BCP Dólares",
        "currency_code": "USD",
        "is_person": False,
        "is_archived": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
    {
        "id": "acc-old",
        "name": "Ahorro viejo",
        "currency_code": "PEN",
        "is_person": False,
        "is_archived": True,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
]
#: In the engine's order, as the mockup's lists draw it: @Pendiente first.
CATEGORIES = [
    {"id": "c-pend", "name": "@Pendiente", "is_system": True, "system_key": "pending"},
    {"id": "c-com", "name": "COMIDA", "is_system": False, "system_key": None},
    {"id": "c-hog", "name": "HOGAR", "is_system": False, "system_key": None},
    {"id": "c-oci", "name": "OCIO", "is_system": False, "system_key": None},
    {"id": "c-open", "name": "@Opening", "is_system": True, "system_key": "opening_balance"},
]
HASHTAGS = [
    {"id": "h-casa", "name": "casa", "system_key": None},
    {"id": "h-sal", "name": "salidas", "system_key": None},
    {"id": "h-pend", "name": "Pendiente", "system_key": "pending"},
]


def _tx(
    tx_id,
    amount,
    *,
    line,
    title="Tottus Jockey Plaza",
    day="2026-10-11",
    account="acc1",
    category="c-pend",
    tags=None,
    note=None,
):
    """A transaction as the signed list read returns it."""
    return {
        "id": tx_id,
        "title": title,
        "description": note,
        "amount_cents": amount,
        "date": f"{day}T12:00:00-05:00",
        "account_id": account,
        "category_id": category,
        "hashtag_ids": tags if tags is not None else ["h-pend"],
        "bank_line_id": line,
        "line_code": line_code_of(line),
        "statement_line": None,
        "statement_place": None,
        "version": 1,
    }


#: The mockup's Tottus Jockey Plaza, split -60.00 + -40.00, and Cine Plaza, never split.
P1 = _tx("p1", -6000, line="bl-9", category="c-com", tags=["h-casa"], note="verduras")
P2 = _tx("p2", -4000, line="bl-9", category="c-hog", note="lejía y papel")
CINE = _tx(
    "t1",
    -2800,
    line="bl-1",
    title="Cine Plaza",
    day="2026-08-30",
    category="c-oci",
    tags=["h-sal"],
    note="con Ana",
)
#: The same split on an archived account, its opening balance, and two lines in a
#: completed reconciliation: one split, one of one part.
A1 = _tx("a1", -6000, line="bl-a", account="acc-old", category="c-com", note="verduras")
A2 = _tx("a2", -4000, line="bl-a", account="acc-old", category="c-hog")
OPENING = _tx(
    "o1", 320000, line="bl-o", title="Saldo inicial", day="2026-01-01", category="c-open", tags=[]
)
C1 = _tx("c1", -6000, line="bl-c", category="c-com")
C2 = _tx("c2", -4000, line="bl-c", category="c-hog")
SOLO = _tx("s1", -2800, line="bl-s", title="Uber", category="c-oci")

LEDGER = [P1, P2, CINE, A1, A2, OPENING, C1, C2, SOLO]
LINES = {
    "bl-9": [P1, P2],
    "bl-1": [CINE],
    "bl-a": [A1, A2],
    "bl-o": [OPENING],
    "bl-c": [C1, C2],
    "bl-s": [SOLO],
}
OPERATION = {"bl-9": "47391026"}

_LOCKED = ("title", "date", "account_id", "reconciliation_id")
#: What the engine answers for each line's state (test_bank_line_edit_limits.py).
LIMITS = {
    "bl-9": edit_limits(),
    "bl-1": edit_limits(),
    "bl-a": edit_limits(
        locked_fields=dict.fromkeys(_LOCKED, "ACCOUNT_ARCHIVED"),
        total_fixed=True,
        parts_fixed=True,
        locked_part_fields={
            "a1": {"amount_cents": "ACCOUNT_ARCHIVED"},
            "a2": {"amount_cents": "ACCOUNT_ARCHIVED"},
        },
    ),
    "bl-o": edit_limits(
        locked_fields={"account_id": "OPENING_BALANCE_ACCOUNT_FIXED"},
        parts_fixed=True,
        locked_part_fields={
            "o1": {
                "category_id": "OPENING_BALANCE_CATEGORY_FIXED",
                "hashtag_ids": "OPENING_BALANCE_NOT_TAGGED",
            }
        },
    ),
    "bl-c": edit_limits(locked_fields=dict.fromkeys(_LOCKED, "LOCKED"), total_fixed=True),
    "bl-s": edit_limits(
        locked_fields=dict.fromkeys(_LOCKED, "LOCKED"),
        total_fixed=True,
        locked_part_fields={"s1": {"amount_cents": "SPLIT_TOTAL_MISMATCH"}},
    ),
}


def _as_part(tx: dict) -> dict:
    """A ledger transaction as `GET /bank-lines/{id}` lists it among `parts`."""
    return import_part(
        tx["id"],
        tx["amount_cents"],
        account_id=tx["account_id"],
        line=tx["bank_line_id"],
        day=tx["date"][:10],
        title=tx["title"],
        category_id=tx["category_id"],
        hashtag_ids=tuple(tx["hashtag_ids"]),
        description=tx["description"],
    )


def bank_line(line: str) -> dict:
    """`GET /bank-lines/{id}` for one of `LINES`: the line, every part, its
    `edit_limits`."""
    parts = LINES[line]
    return {
        "id": line,
        "line_code": line_code_of(line),
        "account_id": parts[0]["account_id"],
        "operation_code": OPERATION.get(line),
        "statement_line": None,
        "statement_place": None,
        "net_cents": sum(tx["amount_cents"] for tx in parts),
        "part_count": len(parts),
        "is_opening_balance": line == "bl-o",
        "parts": [_as_part(tx) for tx in parts],
        "edit_limits": LIMITS[line],
    }


MISMATCH = (
    "Must add up to the line's total: the line's total is -10000 cents "
    "and the parts add up to -12500."
)
PART_MISMATCH = (
    "The parts must add up to the line's total: the line's total is -10000 cents "
    "and the parts add up to -12500."
)


class LineClient(FakeClient):
    """The fake engine: reference lists whole, the ledger and its count, each
    bank line with its parts, and "no batch" for Sueldo Soles."""

    def __init__(self) -> None:
        super().__init__()
        self.get_responses.update(
            {
                "/accounts": whole(ACCOUNTS),
                "/categories": whole(CATEGORIES),
                "/hashtags": whole(HASHTAGS),
                "/reconciliations": whole([]),
            }
        )
        for line in LINES:
            self.get_responses[f"/bank-lines/{line}"] = bank_line(line)

    def get(self, path: str, *, auth: bool = True, params: dict | None = None) -> dict:
        params = params or {}
        if path == "/transactions":
            self._record("GET", path, params)
            limit = params.get("limit") or 50
            return cursor_page(LEDGER[:limit], limit=limit)
        if path == "/transactions/count":
            self._record("GET", path, params)
            return {"count": len(LEDGER)}
        if path == "/bank-lines":
            self._record("GET", path, params)
            return cursor_page([bank_line("bl-9"), bank_line("bl-1")])
        if path == "/bank-lines/count":
            self._record("GET", path, params)
            return {"count": 2}
        return super().get(path, auth=auth, params=params)

    def form_requests(self, since: int) -> list[tuple[str, str]]:
        """Every request from call `since` on but the reference lists'."""
        return [
            (method, path)
            for method, path, _ in self.calls[since:]
            if path not in ("/accounts", "/categories", "/hashtags")
        ]


@pytest.fixture
def engine(monkeypatch):
    client = LineClient()
    monkeypatch.setattr("expense.http.ExpenseClient", lambda *a, **k: client)
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: client)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    return client


@pytest.fixture
def notes(monkeypatch) -> list[tuple[str, str]]:
    """Every toast as (title, message)."""
    seen: list[tuple[str, str]] = []

    def notify(self, message, *, title="", severity="information", timeout=None, markup=True):
        seen.append((title, str(message)))

    monkeypatch.setattr("textual.app.App.notify", notify)
    return seen


# ---- driving the form --------------------------------------------------------


async def _open_ledger(pilot, app) -> TransactionsScreen:
    screen = TransactionsScreen()
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    screen.query_one(CursorList).focus()
    await pilot.pause()
    return screen


async def _open(pilot, app, key: str, press: str = "enter") -> tuple[TransactionsScreen, object]:
    """The ledger, the cursor on row `key`, then `press` (`⏎` or `s`); waits
    for the form to hold the line and the reference lists."""
    ledger = await _open_ledger(pilot, app)
    listing = ledger.query_one(CursorList)
    listing.set_cursor(listing.index_of(key))
    await pilot.pause()
    await pilot.press(press)
    await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
    screen = app.screen
    await wait_for(pilot, lambda: screen._ready, message="the form never loaded")
    await pilot.pause()
    return ledger, screen


async def _type(pilot, screen, text: str, key: str = "enter") -> None:
    """Type `text` over the bar, then press `key`."""
    bar = screen.query_one("#bar", Input)
    bar.value = text
    await pilot.pause()
    await pilot.press(key)
    await pilot.pause()


async def _go(pilot, screen, key: str) -> None:
    """`tab` until the bar is on `key`."""
    for _ in range(len(screen._sequence())):
        if screen._key == key:
            return
        await pilot.press("tab")
        await pilot.pause()
    assert screen._key == key


def _summary(screen, width: int = 110) -> list[str]:
    content = screen.query_one("#summary", Static).content
    return [line.rstrip() for line in render_text(content, width=width).splitlines()]


def _rows(screen) -> list[Text]:
    """The parts table's lines, as `Text`: its header, then each part."""
    group = screen.query_one("#summary", Static).content
    texts = [r for r in group.renderables if isinstance(r, Text)]
    start = next(i for i, t in enumerate(texts) if t.plain.strip().startswith("amount"))
    return [t for t in texts[start:] if t.plain.strip()][: 1 + len(screen._parts)]


def _styles_of(text: Text, needle: str) -> set[str]:
    start = text.plain.index(needle)
    return {str(s.style) for s in text.spans if s.start <= start < s.end} | (
        {str(text.style)} if text.style else set()
    )


def _footer(screen) -> list[tuple[str, str]]:
    return [(k.key_display, k.description) for k in screen.query_one(Footer).query(FooterKey)]


async def _settle_footer(pilot, screen) -> list[tuple[str, str]]:
    """The footer once it shows the keys `check_action` allows on this line."""
    for _ in range(5):
        await pilot.pause()
    return _footer(screen)


def _hint(screen) -> str:
    return screen.query_one("#hint", Static).content.plain


def _label(screen) -> str:
    return str(screen.query_one("#field").content)


def _writes(engine, since: int = 0) -> list[tuple[str, str, object]]:
    """Every request but a read, from call `since` on: what a save sent, all of it."""
    return [(method, path, body) for method, path, body in engine.calls[since:] if method != "GET"]


def _put(engine) -> tuple[str, dict]:
    ((path, body),) = engine.puts
    return path, body


def _fresh(part_id: str) -> bool:
    """A new part's id: a UUID the app minted, never one a line held."""
    held = {tx["id"] for tx in LEDGER}
    return part_id not in held and bool(uuid.UUID(part_id))


# ---- section 2: ⏎ on a part · the form with its parts --------------------------


@pytest.mark.parametrize("key", ["p1", "p2"])
def test_enter_on_either_part_opens_the_form_on_date_with_every_part(engine, key):
    """Screen 2a: the shared fields on top, both parts below whichever part `⏎`
    was on, the line adding them up; the bar on DATE, its hint DATE's own
    (`YYYY-MM-DD · enter to accept, or type a date`) and then
    `changes every part of the transaction` in the accent; the footer offers
    `^n Add part` and no `^x` off a part's line."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, key)
        return (
            screen._key,
            _label(screen),
            screen.query_one("#hint", Static).content,
            _summary(screen),
            await _settle_footer(pilot, screen),
            screen.crumb,
        )

    key_on, label, hint, summary, footer, crumb = run_app(scenario, size=SIZE)
    assert (key_on, label.strip()) == ("date", "DATE")
    assert hint.plain == f"YYYY-MM-DD · enter to accept, or type a date · {EVERY_PART_NOTE}"
    assert _styles_of(hint, EVERY_PART_NOTE) == {ACCENT}
    assert summary == [
        "date     2026-10-11",
        "title    Tottus Jockey Plaza",
        "account  Sueldo Soles",
        "",
        "      amount    category       hashtags        note",
        "  1   -60.00    COMIDA         #casa           verduras",
        "  2   -40.00    HOGAR          —               lejía y papel",
        "",
        "2 parts  ·  -100.00 of -100.00  ✓",
    ]
    assert footer == [("esc", "Cancel"), ("^s", "Save"), ("⇥", "Field"), ("^n", "Add part")]
    assert crumb == ("Capture & ledger", "Transactions", "Edit")


def test_s_opens_the_same_form_on_date(engine):
    """Question 6 A: `s` on the ledger opens the form exactly as `⏎` does."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "p2", press="s")
        return type(screen), screen._key, _summary(screen), await _settle_footer(pilot, screen)

    kind, key, summary, footer = run_app(scenario, size=SIZE)
    assert kind is EditFormScreen and key == "date"
    assert summary[5:7] == [
        "  1   -60.00    COMIDA         #casa           verduras",
        "  2   -40.00    HOGAR          —               lejía y papel",
    ]
    assert footer[-1] == ("^n", "Add part")


def test_the_bar_names_the_part_and_the_table_marks_it(engine):
    """Screen 2b: `⇥` three times puts the bar on PART 1 AMOUNT, its hint
    AMOUNT's own (`signed decimal · − expense / + income · in the account's
    currency`); part 1 reads `▌ 1` in the accent, bold; `^x Drop part` joins
    the footer."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "p1")
        for _ in range(3):
            await pilot.press("tab")
        await pilot.pause()
        return (
            screen._key,
            _label(screen),
            _hint(screen),
            _rows(screen),
            await _settle_footer(pilot, screen),
        )

    key, label, hint, rows, footer = run_app(scenario, size=SIZE)
    assert (key, label.strip()) == ("0.amount", "PART 1 AMOUNT")
    assert hint == "signed decimal · − expense / + income · in the account's currency"
    assert rows[1].plain == "▌ 1   -60.00    COMIDA         #casa           verduras"
    assert _styles_of(rows[1], "COMIDA") == {f"bold {ACCENT}"}
    assert rows[2].plain.startswith("  2   -40.00")
    assert footer[-2:] == [("^n", "Add part"), ("^x", "Drop part")]


def test_a_parts_note_says_enter_goes_on_and_the_last_one_saves(engine):
    """Question 3 A: part 1's NOTE, `⏎` going on to part 2, reads `optional ·
    enter to go on`; part 2's NOTE, the last line, keeps `optional · enter saves
    · (ctrl+s anytime)`. `⏎` on part 1's NOTE goes on to PART 2 AMOUNT."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "p1")
        await _go(pilot, screen, "0.note")
        first = _hint(screen)
        await pilot.press("enter")
        await pilot.pause()
        moved = screen._key
        await _go(pilot, screen, "1.note")
        return first, moved, _hint(screen)

    first, moved, last = run_app(scenario, size=SIZE)
    assert first == NOTE_GOES_ON == "optional · enter to go on"
    assert moved == "1.amount"
    assert last == NOTE_SAVES == "optional · enter saves · (ctrl+s anytime)"


def test_ctrl_n_adds_a_part_and_the_line_says_what_is_left(engine):
    """Screen 2c: `^n` adds part 3, empty, the bar on its AMOUNT; `-15` `⏎`
    moves to its CATEGORY, the list starting on @Pendiente, and the line reads
    `3 parts · -115.00 of -100.00 · 15.00 left`, what is left in the error
    colour. Screen 2d: `^x` drops it at once, the bar on PART 2 CATEGORY."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "p1")
        await pilot.press("ctrl+n")
        await pilot.pause()
        added = (screen._key, _label(screen).strip(), _rows(screen)[3].plain)
        await _type(pilot, screen, "-15")
        on = (screen._key, screen._suggestions[screen._suggest_idx][1])
        group = screen.query_one("#summary", Static).content
        count = next(r for r in group.renderables if isinstance(r, Text) and "parts" in r.plain)
        await pilot.press("ctrl+x")
        await pilot.pause()
        after = (screen._key, screen._suggestions[screen._suggest_idx][1], _summary(screen)[-1])
        return added, on, count, after, engine.puts

    added, on, count, after, puts = run_app(scenario, size=SIZE)
    assert added == ("2.amount", "PART 3 AMOUNT", "▌ 3        —    —              —")
    assert on == ("2.category", "@Pendiente")
    assert count.plain == "3 parts  ·  -115.00 of -100.00  ·  15.00 left"
    assert _styles_of(count, "15.00 left") == {PALETTE.error}
    assert after == ("1.category", "HOGAR", "2 parts  ·  -100.00 of -100.00  ✓")
    assert puts == []  # nothing is sent until the save


def test_a_line_never_split_shows_one_part_and_no_line_adding_up(engine):
    """Screens 2e and 2f: Cine Plaza has one part, no line under the table, no
    `changes every part` in the hints, no `^x`; `^n` makes it two parts, the
    line adding up against the -28.00 it holds."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "t1")
        one = (_summary(screen), _hint(screen), await _settle_footer(pilot, screen))
        await pilot.press("ctrl+n")
        await pilot.pause()
        return one, (_summary(screen), _label(screen).strip(), await _settle_footer(pilot, screen))

    (summary, hint, footer), (two, label, footer_two) = run_app(scenario, size=SIZE)
    assert summary[4:] == [
        "      amount    category       hashtags        note",
        "  1   -28.00    OCIO           #salidas        con Ana",
    ]
    assert hint == "YYYY-MM-DD · enter to accept, or type a date"
    assert footer[-1] == ("^n", "Add part")
    assert label == "PART 2 AMOUNT"
    assert two[-4:] == [
        "  1   -28.00    OCIO           #salidas        con Ana",
        "▌ 2        —    —              —",
        "",
        "2 parts  ·  -28.00 of -28.00  ✓",
    ]
    assert footer_two[-1] == ("^x", "Drop part")


def test_an_empty_new_part_is_left_out_and_nothing_else_changed_sends_nothing(engine, notes):
    """2f: a part added and left empty is dropped at the save; with nothing
    else changed the form says `No changes to save.` and sends nothing."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "t1")
        await pilot.press("ctrl+n")
        await pilot.press("ctrl+s")
        await pilot.pause()
        return app.screen is screen

    assert run_app(scenario, size=SIZE)
    assert engine.puts == []
    assert ("", "No changes to save.") in notes


# ---- the spec's checks 3 to 6 ----------------------------------------------------


def test_check_3_a_new_date_and_a_re_split_go_in_one_write_ids_kept(engine, notes):
    """Edit the date and re-split 60 + 40 into 70 + 30: one `PUT
    /bank-lines/bl-9` with the date and both parts under their own ids, their
    new amounts alone; no transaction write and no other route. Saved, the
    ledger reads fresh."""

    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "p1")
        since = len(engine.calls)
        await _type(pilot, screen, "2026-10-12")
        await _go(pilot, screen, "0.amount")
        await _type(pilot, screen, "-70")
        await _go(pilot, screen, "1.amount")
        await _type(pilot, screen, "-30")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)
        await wait_for_list(pilot, app)
        return engine.form_requests(since)

    requests = run_app(scenario, size=SIZE)
    path, body = _put(engine)
    assert path == "/bank-lines/bl-9"
    assert body == {
        "date": "2026-10-12T00:00:00-05:00",
        "parts": [{"id": "p1", "amount_cents": -7000}, {"id": "p2", "amount_cents": -3000}],
    }
    writes = [r for r in requests if r[0] != "GET"]
    assert writes == [("PUT", "/bank-lines/bl-9")]
    assert len(_writes(engine)) == 1
    assert ("", "Saved.") in notes


def test_check_4_a_two_part_line_goes_back_to_one_part_in_one_write(engine):
    """`^x` on part 2 and `^s`: one write naming part 1 alone, so the engine
    deletes part 2; with one part left, no line adds them up."""

    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "p1")
        await _go(pilot, screen, "1.amount")
        await pilot.press("ctrl+x")
        await pilot.pause()
        summary = _summary(screen)
        footer = await _settle_footer(pilot, screen)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)
        return summary, footer

    summary, footer = run_app(scenario, size=SIZE)
    assert summary[-1] == "▌ 1   -60.00    COMIDA         #casa           verduras"
    assert ("^x", "Drop part") not in footer  # one part left: nothing to drop
    assert _writes(engine) == [
        ("PUT", "/bank-lines/bl-9", {"parts": [{"id": "p1", "amount_cents": -6000}]})
    ]


def test_check_5_both_parts_of_an_archived_accounts_line_re_categorised_in_one_write(engine):
    """Question 5 A: the line on an archived account opens on PART 1 CATEGORY;
    date, title, account and both amounts are read-only, `amount  read-only`
    under the table; no `^n`, no `^x`. Both parts re-categorised: one write,
    each part its current amount and its new category, no line field."""

    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "a1")
        opened = (screen._key, _summary(screen), await _settle_footer(pilot, screen), _rows(screen))
        await _type(pilot, screen, "hog")
        await _go(pilot, screen, "1.category")
        await _type(pilot, screen, "com")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)
        return opened

    key, summary, footer, rows = run_app(scenario, size=SIZE)
    assert key == "0.category"
    assert summary == [
        "date     2026-10-11  read-only",
        "title    Tottus Jockey Plaza  read-only",
        "account  Ahorro viejo  read-only",
        "",
        "      amount    category       hashtags        note",
        "▌ 1   -60.00    COMIDA         —               verduras",
        "  2   -40.00    HOGAR          —",
        "amount  read-only",
        "",
        "2 parts  ·  -100.00 of -100.00  ✓",
    ]
    assert footer == [("esc", "Cancel"), ("^s", "Save"), ("⇥", "Field")]
    assert _styles_of(rows[1], "-60.00") == {"dim"}
    assert _styles_of(rows[2], "-40.00") == {"dim"}
    assert _writes(engine) == [
        (
            "PUT",
            "/bank-lines/bl-a",
            {
                "parts": [
                    {"id": "a1", "amount_cents": -6000, "category_id": "c-hog"},
                    {"id": "a2", "amount_cents": -4000, "category_id": "c-com"},
                ]
            },
        )
    ]


def test_check_5_an_opening_balances_amount_and_note_in_one_write(engine):
    """Question 5 A: an opening balance opens on DATE; its account, category and
    hashtags are read-only, `category  read-only` and `hashtags  read-only`
    under the table, the two cells dimmed; no `^n`. Its amount and note go in
    one write under its own id, nothing else."""

    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "o1")
        opened = (screen._key, _summary(screen), await _settle_footer(pilot, screen), _rows(screen))
        await _go(pilot, screen, "0.amount")
        await _type(pilot, screen, "3500")
        moved = screen._key  # category and hashtags are skipped
        await _type(pilot, screen, "apertura")
        await wait_for(pilot, lambda: app.screen is ledger)
        return opened, moved

    (key, summary, footer, rows), moved = run_app(scenario, size=SIZE)
    assert key == "date"
    assert summary == [
        "date     2026-01-01",
        "title    Saldo inicial",
        "account  Sueldo Soles  read-only",
        "",
        "       amount    category       hashtags        note",
        "  1  3,200.00    @Opening       —",
        "category  read-only",
        "hashtags  read-only",
    ]
    assert footer == [("esc", "Cancel"), ("^s", "Save"), ("⇥", "Field")]
    assert _styles_of(rows[1], "@Opening") == {"dim"}
    assert _styles_of(rows[1], "—") == {"dim"}
    assert moved == "0.note"
    assert _writes(engine) == [
        (
            "PUT",
            "/bank-lines/bl-o",
            {"parts": [{"id": "o1", "amount_cents": 350000, "description": "apertura"}]},
        )
    ]


#: Each line opened, and exactly the lines its `edit_limits` makes read-only.
READ_ONLY = {
    "c1": {"date", "title", "account"},
    "s1": {"date", "title", "account", "0.amount"},
    "a1": {"date", "title", "account", "0.amount", "1.amount"},
    "o1": {"account", "0.category", "0.hashtags"},
    "p1": set(),
    "t1": set(),
}


@pytest.mark.parametrize("key", sorted(READ_ONLY))
def test_check_6_a_line_shows_read_only_exactly_what_its_edit_limits_names(engine, key):
    """No reconciliation read on opening, one read of the line: every line its
    `edit_limits` names reads `read-only`, dimmed, and no other."""

    async def scenario(pilot, app):
        ledger = await _open_ledger(pilot, app)
        since = len(engine.calls)
        listing = ledger.query_one(CursorList)
        listing.set_cursor(listing.index_of(key))
        await pilot.pause()
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        screen = app.screen
        await wait_for(pilot, lambda: screen._ready)
        await pilot.pause()
        return set(screen._locked), _summary(screen), engine.form_requests(since)

    locked, summary, requests = run_app(scenario, size=SIZE)
    assert locked == READ_ONLY[key]
    line = next(tx for tx in LEDGER if tx["id"] == key)["bank_line_id"]
    assert requests == [("GET", f"/bank-lines/{line}")]
    shared = {row.split()[0] for row in summary[:3] if row.endswith("read-only")}
    assert shared == {k for k in READ_ONLY[key] if "." not in k}
    marked = {row.split()[0] for row in summary[3:] if row.endswith("  read-only")}
    assert marked == {k.split(".")[1] for k in READ_ONLY[key] if "." in k}


def test_check_6_a_completed_reconciliations_split_line_opens_on_part_1s_amount(engine):
    """Screen 3a: date, title and account read-only; the parts' amounts stay
    changeable and parts can still be added and dropped."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "c1")
        return screen._key, _summary(screen)[:3], await _settle_footer(pilot, screen)

    key, shared, footer = run_app(scenario, size=SIZE)
    assert key == "0.amount"
    assert shared == [
        "date     2026-10-11  read-only",
        "title    Tottus Jockey Plaza  read-only",
        "account  Sueldo Soles  read-only",
    ]
    assert footer[-2:] == [("^n", "Add part"), ("^x", "Drop part")]


def test_check_6_a_completed_line_of_one_part_holds_its_total_until_split(engine):
    """Screen 3b: one part, its amount the line's total, read-only and dimmed
    with `amount  read-only` under the table; the form opens on its category.
    With the total fixed and the parts not, `^n` makes two parts and the amounts
    move between them: part 1's amount is no longer read-only."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "s1")
        one = (screen._key, _summary(screen)[4:], _rows(screen)[1])
        await pilot.press("ctrl+n")
        await pilot.pause()
        return one, set(screen._locked), _summary(screen)

    (key, table, row), locked, two = run_app(scenario, size=SIZE)
    assert key == "0.category"
    assert table == [
        "      amount    category       hashtags        note",
        "▌ 1   -28.00    OCIO           —",
        "amount  read-only",
    ]
    assert _styles_of(row, "-28.00") == {"dim"}
    assert locked == {"date", "title", "account"}
    assert "amount  read-only" not in two


def test_check_6_a_completed_split_line_re_split_with_its_total_saves_its_parts_alone(
    engine, notes
):
    """Screen 3a saved: 60 + 40 re-split into 70 + 30, the total kept. The one
    write is `parts` alone, both under their own ids: no line field changed, so
    none is sent, and nothing else goes."""

    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "c1")
        assert screen._key == "0.amount"
        await _type(pilot, screen, "-70")
        await _go(pilot, screen, "1.amount")
        await _type(pilot, screen, "-30")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert _writes(engine) == [
        (
            "PUT",
            "/bank-lines/bl-c",
            {"parts": [{"id": "c1", "amount_cents": -7000}, {"id": "c2", "amount_cents": -3000}]},
        )
    ]
    assert ("", "Saved.") in notes


def test_check_6_a_completed_line_of_one_part_saves_a_new_category_alone(engine, notes):
    """Screen 3b saved: the form opens on the category; a new one, `^s`. The one
    write is its part at the line's total and the new category, no line field."""

    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "s1")
        assert screen._key == "0.category"
        await _type(pilot, screen, "com", key="ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert _writes(engine) == [
        (
            "PUT",
            "/bank-lines/bl-s",
            {"parts": [{"id": "s1", "amount_cents": -2800, "category_id": "c-com"}]},
        )
    ]
    assert ("", "Saved.") in notes


def test_an_amount_read_only_again_after_a_drop_goes_back_to_the_lines_own(engine, notes):
    """A completed line of one part: `^n` opens part 1's amount, it is edited,
    then the new part is dropped. The amount is read-only again, and it shows
    and sends the line's own -28.00, not the edited one: nothing changed, so
    nothing is sent."""

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "s1")
        await pilot.press("ctrl+n")
        await pilot.pause()
        while screen._key != "0.amount":  # back up from part 2's AMOUNT
            await pilot.press("shift+tab")
            await pilot.pause()
        await _type(pilot, screen, "-20")
        edited = screen._parts[0].amount_cents
        await _go(pilot, screen, "1.amount")
        await pilot.press("ctrl+x")
        await pilot.pause()
        held = (set(screen._locked), screen._parts[0].amount_cents, _rows(screen)[1])
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: ("", "No changes to save.") in notes)
        return edited, held

    edited, (locked, amount, row) = run_app(scenario, size=SIZE)
    assert edited == -2000
    assert "0.amount" in locked
    assert amount == -2800
    assert "-28.00" in row.plain and _styles_of(row, "-28.00") == {"dim"}
    assert _writes(engine) == []


# ---- what the save sends ---------------------------------------------------------


def test_a_kept_parts_hashtags_go_only_when_changed_and_a_new_part_gets_a_fresh_id(engine):
    """Part 1's category changed, its hashtags untouched: no `hashtag_ids`;
    part 2 tagged #casa: its `hashtag_ids` without the pending one; a part
    added with an amount and a note under a fresh id with only what it holds."""

    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "p1")
        await _go(pilot, screen, "0.category")
        await _type(pilot, screen, "oci")
        await _go(pilot, screen, "1.hashtags")
        await _type(pilot, screen, "casa")
        await pilot.press("ctrl+n")
        await _type(pilot, screen, "-5")
        await _go(pilot, screen, "2.note")
        await _type(pilot, screen, "bolsa")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    _path, body = _put(engine)
    first, second, third = body["parts"]
    assert first == {"id": "p1", "amount_cents": -6000, "category_id": "c-oci"}
    assert second == {"id": "p2", "amount_cents": -4000, "hashtag_ids": ["h-casa"]}
    assert _fresh(third.pop("id"))
    assert third == {"amount_cents": -500, "description": "bolsa"}
    assert set(body) == {"parts"}


def test_a_moved_account_sends_the_unassign_beside_the_parts(engine, notes):
    """A changed account goes with `reconciliation_id: null`, the parts as they
    are; the answer flags a part as leaving, so the note says so
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Response")."""
    part = bank_line("bl-1")["parts"][0]
    engine.write_responses["/bank-lines/bl-1"] = {
        **bank_line("bl-1"),
        "changed_parts": [{"transaction": part, "left_reconciliation": True}],
        "created_part_ids": [],
        "deleted_part_ids": [],
    }

    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "t1")
        await _go(pilot, screen, "account")
        await _type(pilot, screen, "dól")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert _writes(engine) == [
        (
            "PUT",
            "/bank-lines/bl-1",
            {
                "account_id": "acc2",
                "reconciliation_id": None,
                "parts": [{"id": "t1", "amount_cents": -2800}],
            },
        )
    ]
    assert ("", "Saved. It left its reconciliation.") in notes


def test_an_emptied_note_goes_as_an_empty_description(engine):
    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "t1")
        await _go(pilot, screen, "0.note")
        await _type(pilot, screen, "")  # the last line: `⏎` saves
        await wait_for(pilot, lambda: app.screen is ledger)

    run_app(scenario, size=SIZE)
    assert _writes(engine) == [
        (
            "PUT",
            "/bank-lines/bl-1",
            {"parts": [{"id": "t1", "amount_cents": -2800, "description": ""}]},
        )
    ]


def test_the_write_carries_one_idempotency_key_and_a_retry_reuses_it(configured, monkeypatch):
    """`^s` is one logical write through the shared write path and the real
    HTTP client: a `503` goes again by itself, the same body under the same
    `X-Idempotency-Key`, a new part under the id minted for the save."""
    client = LineClient()
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: client)

    async def scenario(pilot, app):
        ledger, screen = await _open(pilot, app, "p1")
        await pilot.press("ctrl+n")
        await _type(pilot, screen, "-10")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is ledger)

    with respx.mock() as mock:
        route = mock.put(f"{ENGINE_URL}/v1/bank-lines/bl-9").mock(
            side_effect=[
                httpx.Response(503, json={"error": {"code": "INTERNAL_ERROR", "message": "x"}}),
                httpx.Response(200, json={"id": "bl-9", "parts": [], "changed_parts": []}),
            ]
        )
        run_app(scenario, size=SIZE)
    assert route.call_count == 2
    first, second = (call.request for call in route.calls)
    assert first.headers["X-Idempotency-Key"]
    assert first.headers["X-Idempotency-Key"] == second.headers["X-Idempotency-Key"]
    assert first.content == second.content
    ids = [p["id"] for p in json.loads(first.content)["parts"]]
    assert ids[:2] == ["p1", "p2"] and _fresh(ids[2])


# ---- question 4 A: a refused save shows under the parts --------------------------


def _mismatch() -> EngineError:
    keys = ("parts", "parts.0.amount_cents", "parts.1.amount_cents")
    return EngineError(
        "VALIDATION_ERROR",
        "Validation failed.",
        {
            "parts": MISMATCH,
            "parts.0.amount_cents": PART_MISMATCH,
            "parts.1.amount_cents": PART_MISMATCH,
        },
        422,
        {},
        reasons=dict.fromkeys(keys, "SPLIT_TOTAL_MISMATCH"),
    )


def test_a_refused_save_shows_under_the_parts_each_part_named_by_its_number(engine):
    """Question 4 A on Tottus Jockey Plaza in a completed reconciliation: part 1
    at -85.00, `^s`, refused: under the line adding up, the engine's words,
    `! part 1 (amount): …` for each part, `Nothing was saved.`; the amounts it
    names red and bold; the form stays, and a change clears it."""
    engine.errors["PUT"] = _mismatch()

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "c1")
        await _type(pilot, screen, "-85", key="ctrl+s")
        await wait_for(pilot, lambda: screen._refusal is not None)
        shown = _summary(screen, width=100)
        rows = _rows(screen)
        hint = _hint(screen)
        await _type(pilot, screen, "-60")
        return app.screen is screen, shown, rows, hint, _summary(screen, width=100)

    stayed, shown, rows, hint, after = run_app(scenario, size=SIZE)
    assert stayed
    tail = shown[shown.index("2 parts  ·  -125.00 of -100.00  ·  25.00 left") :]
    assert tail[1] == ""
    assert tail[2] == "VALIDATION_ERROR — Validation failed."
    flat = " ".join(row.strip() for row in tail[3:])
    assert f"! parts: {MISMATCH}" in flat
    assert f"! part 1 (amount): {PART_MISMATCH}" in flat
    assert f"! part 2 (amount): {PART_MISMATCH}" in flat
    assert tail[-1] == "Nothing was saved."
    assert _styles_of(rows[1], "-85.00") == {f"bold {PALETTE.error}"}
    assert _styles_of(rows[2], "-40.00") == {f"bold {PALETTE.error}"}
    assert hint.startswith("signed decimal")  # not left on `Saving…`
    assert "Nothing was saved." not in after
    assert _writes(engine) == [
        (
            "PUT",
            "/bank-lines/bl-c",
            {"parts": [{"id": "c1", "amount_cents": -8500}, {"id": "c2", "amount_cents": -4000}]},
        )
    ]


#: Each refusal the form handles, on the key the engine names: the line under the
#: words chosen by the reason (`app_lines`), or None.
REFUSALS = [
    (
        "o1",
        "parts.0.category_id",
        "OPENING_BALANCE_CATEGORY_FIXED",
        "Must not move an opening balance out of the opening-balance category.",
        "part 1 (category_id)",
        "An opening balance always stays in @Opening.",
    ),
    (
        "o1",
        "parts.0.hashtag_ids",
        "OPENING_BALANCE_NOT_TAGGED",
        "Must be empty: an opening balance carries no hashtag.",
        "part 1 (hashtag_ids)",
        "Leave the opening balance out of the selection.",
    ),
    (
        "a1",
        "parts.1.amount_cents",
        "ACCOUNT_ARCHIVED",
        "Part a2 of this bank line is the cause: The account is archived. Unarchive it first.",
        "part 2 (amount)",
        None,
    ),
    ("c1", "title", "LOCKED", "stand-in words: the title is locked", "title", None),
    ("p1", "parts", "SPLIT_LINE_PARTS_DIVERGE", "stand-in words: diverge", "parts", None),
    ("p1", "date", "SEALED_PERIOD", "stand-in words: sealed", "date", None),
]


@pytest.mark.parametrize(
    ("key", "field", "reason", "words", "named", "line"),
    REFUSALS,
    ids=[f"{r[2]}-{r[1]}" for r in REFUSALS],
)
def test_each_refusal_lands_under_the_parts_on_the_key_it_names(
    engine, key, field, reason, words, named, line
):
    engine.errors["PUT"] = EngineError(
        "VALIDATION_ERROR",
        f"Engine words for {reason}.",
        {field: words},
        422,
        {},
        reasons={field: reason},
    )

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, key)
        await _go(pilot, screen, screen._sequence()[-1])
        await _type(pilot, screen, "otra nota", key="ctrl+s")
        await wait_for(pilot, lambda: screen._refusal is not None)
        return app.screen is screen, _summary(screen, width=200)

    stayed, shown = run_app(scenario, size=SIZE)
    assert stayed
    tail = shown[shown.index(f"VALIDATION_ERROR — Engine words for {reason}.") :]
    assert tail[1] == f"! {named}: {words}"
    assert tail[2] == "Nothing was saved."
    assert [row for row in tail[3:] if row] == ([line] if line else [])
    # the one write: every part at its amount, the last part's new note, no line field
    bank = next(tx for tx in LEDGER if tx["id"] == key)["bank_line_id"]
    parts = [{"id": tx["id"], "amount_cents": tx["amount_cents"]} for tx in LINES[bank]]
    parts[-1]["description"] = "otra nota"
    assert _writes(engine) == [("PUT", f"/bank-lines/{bank}", {"parts": parts})]


def test_an_engine_out_of_reach_says_so_under_the_parts(engine):
    engine.errors["PUT"] = EngineConnectionError(url="https://x.invalid", original=Exception("no"))

    async def scenario(pilot, app):
        _ledger, screen = await _open(pilot, app, "t1")
        await _go(pilot, screen, "0.note")
        await _type(pilot, screen, "x")
        await wait_for(pilot, lambda: screen._refusal is not None)
        return _summary(screen)

    shown = run_app(scenario, size=SIZE)
    assert "could not reach engine at https://x.invalid (is it running?)" in shown
    assert "Nothing was saved." not in shown


def test_a_failed_line_read_says_why_and_the_form_takes_nothing(engine, notes):
    """The line cannot be read: the toast says why, the parts never show, and
    `⏎` or `^s` sends nothing."""
    engine.errors["GET"] = EngineConnectionError(url="https://x.invalid", original=Exception("no"))

    async def scenario(pilot, app):
        screen = EditFormScreen(record=dict(CINE))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: notes)
        await pilot.press("enter", "ctrl+s")
        await pilot.pause()
        return app.screen is screen, _summary(screen)

    stayed, summary = run_app(scenario, size=SIZE)
    assert stayed
    assert summary[-1] == "loading accounts, categories and tags…"
    assert notes == [("", "could not reach engine at https://x.invalid (is it running?)")]
    assert engine.puts == []


# ---- question 1 A: ⏎ in "no batch" opens the same form ---------------------------


async def _open_no_batch(pilot, app) -> BankLineEditFormScreen:
    browse = ReconciliationsScreen()
    await app.push_screen(browse)
    await wait_for_list(pilot, app)
    await pilot.press("enter")  # Sueldo Soles' reconciliations
    await wait_for(pilot, lambda: browse._mode == "batches")
    await pilot.press("u")
    await wait_for(pilot, lambda: browse._mode == "unfiled" and browse._unfiled_record())
    await pilot.pause()
    await pilot.press("enter")
    await wait_for(pilot, lambda: isinstance(app.screen, BankLineEditFormScreen))
    screen = app.screen
    await wait_for(pilot, lambda: screen._ready)
    await pilot.pause()
    return screen


def test_enter_in_no_batch_opens_the_form_with_its_heading_operation_and_parts(engine):
    """Question 1 A: the heading (the line as saved), OPERATION among the
    shared fields, the parts below, the same keys; no read of the line."""

    async def scenario(pilot, app):
        since = len(engine.calls)
        screen = await _open_no_batch(pilot, app)
        head = render_text(screen.query_one("#form-head", Static).content, width=80).strip()
        reads = [p for m, p in engine.form_requests(since) if p.startswith("/bank-lines/bl-")]
        return head, _summary(screen), await _settle_footer(pilot, screen), screen.crumb, reads

    head, summary, footer, crumb, reads = run_app(scenario, size=SIZE)
    assert head == "Tottus Jockey Plaza  ·  -100.00 PEN"
    assert summary == [
        "date       2026-10-11",
        "title      Tottus Jockey Plaza",
        "operation  47391026",
        "account    Sueldo Soles",
        "",
        "      amount    category       hashtags        note",
        "  1   -60.00    COMIDA         #casa           verduras",
        "  2   -40.00    HOGAR          —               lejía y papel",
        "",
        "2 parts  ·  -100.00 of -100.00  ✓",
    ]
    assert footer[-1] == ("^n", "Add part")
    assert crumb == ("Capture & ledger", "Reconciliations", "Edit")
    assert reads == []


def test_the_no_batch_form_saves_its_operation_and_parts_in_one_write(engine):
    """An emptied operation clears it, and `^s` keeps the amount typed in the
    bar first: one write, `operation_code: null` beside both parts."""

    async def scenario(pilot, app):
        screen = await _open_no_batch(pilot, app)
        await _go(pilot, screen, "operation")
        await _type(pilot, screen, "")  # emptied: clears the operation code
        await _go(pilot, screen, "1.amount")
        await _type(pilot, screen, "-45", key="ctrl+s")
        await wait_for(pilot, lambda: not isinstance(app.screen, BankLineEditFormScreen))

    run_app(scenario, size=SIZE)
    assert engine.puts == [
        (
            "/bank-lines/bl-9",
            {
                "operation_code": None,
                "parts": [{"id": "p1", "amount_cents": -6000}, {"id": "p2", "amount_cents": -4500}],
            },
        )
    ]


# ---- the pure builders -----------------------------------------------------------


def test_a_part_read_from_the_line_is_signed_by_its_transaction_type():
    part = part_from_engine(import_part("p9", -1500, account_id="acc1", line="bl-x"))
    assert (part.amount_cents, part.id) == (-1500, "p9")
    inflow = part_from_engine(import_part("p8", 2500, account_id="acc1", line="bl-x"))
    assert inflow.amount_cents == 2500


@pytest.mark.parametrize(
    ("part", "empty"),
    [
        (Part(), True),
        (Part(hashtag_ids=("h-pend",)), True),
        (Part(amount_cents=-100), False),
        (Part(note="x"), False),
        (Part(id="p1"), False),
    ],
)
def test_a_new_part_is_empty_with_nothing_in_it_but_the_pending_hashtag(part, empty):
    assert part_empty(part, "h-pend") is empty


def test_the_line_adds_the_parts_up_against_the_engines_total():
    parts = [Part(amount_cents=-6000), Part(amount_cents=-3000), Part()]
    short = count_line(parts, -10000, palette=PALETTE)
    assert short.plain == "3 parts  ·  -90.00 of -100.00  ·  -10.00 left"
    assert _styles_of(short, "-10.00 left") == {PALETTE.error}
    full = count_line([Part(amount_cents=-10000)], -10000, palette=PALETTE)
    assert full.plain == "1 part  ·  -100.00 of -100.00  ✓"
    assert _styles_of(full, "✓") == {PALETTE.success}


def test_a_refused_key_reads_its_part_by_number():
    assert key_words("parts.0.amount_cents") == "part 1 (amount)"
    assert key_words("parts.11.category_id") == "part 12 (category_id)"
    assert key_words("parts.2") == "part 3"
    assert key_words("parts") == "parts"
    assert key_words("title") == "title"


def test_a_refused_line_hangs_under_its_own_words():
    """`hanging`: a `! …` line is the `!` beside its words, so a wrapped line
    starts under the words; any other line is itself."""
    plain = Text("Nothing was saved.")
    assert hanging(plain) is plain
    long = Text("! part 1 (amount): " + "word " * 30)
    rendered = render_text(hanging(long), width=40).splitlines()
    assert rendered[0].startswith("! part 1 (amount):")
    assert all(row.startswith("  ") for row in rendered[1:])


@pytest.mark.parametrize(("status", "said"), [(422, True), (409, True), (500, False), (503, False)])
def test_nothing_was_saved_is_said_only_below_a_5xx(status, said):
    """A refusal under `500` wrote nothing, so the form says so
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Refusals, in order"); on a `5xx`
    the engine failed and the form does not claim it."""
    from expense.tui.widgets.parts_table import NOTHING_SAVED, refusal_lines

    err = EngineError("INTERNAL_ERROR", "Something broke.", None, status, {})
    lines = [line.plain for line in refusal_lines(err) if isinstance(line, Text)]
    assert lines[0] == "INTERNAL_ERROR — Something broke."
    assert (NOTHING_SAVED in lines) is said
