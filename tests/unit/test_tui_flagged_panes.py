"""The flagged lines and the lines in no statement at 80 columns.

A statement shows `⚑` and `f` whenever its review list counts a line, open or completed,
counted when the screen reads the statement (contract: GET /v1/bank-lines/count). The
flagged screen lists that review list whole, every currency of the account together in the
engine's order, and on an account with a statement code reads the engine's two ways as
words under it (contract: POST /v1/statements/{statement_id}/complete, "What a client
does with a flagged line"). `u` on the browse lists the account's lines in no statement,
every currency together, oldest first, in one read with their count (contract:
GET /v1/bank-lines, "Filters")."""

import pytest
from textual.widgets import Static

from expense.errors import EngineError, format_error
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.statements import (
    FlaggedLinesScreen,
    StatementScreen,
)
from tests.unit.helpers import (
    cursor_page,
    run_app,
    screen_lines,
    statement_record,
    stub_home_month,
    wait_for,
)
from tests.unit.test_tui_statement_list import ACCOUNTS, VISA, VISA_STATEMENTS, _open
from tests.unit.test_tui_statement_screen import _balance, _line, _pane, _screen_lines

NAMES = {"acc-visa": "Visa BCP", "acc-ibk": "IBK Visa"}

#: VIS-202610 on Visa BCP, completed: its places, then a place for each currency.
VIS_OCT = statement_record(
    {
        "id": "vis-oct",
        "account_id": "acc-visa",
        "name": "VIS-202610",
        "date_start": "2026-09-26",
        "date_end": "2026-10-25",
        "status": 2,
        "balances": [_balance("PEN", -45560, -23420, 0), _balance("USD", 0, -3098, 0)],
    }
)
#: The same days, a draft on IBK Visa, which has no statement code.
IBK_OCT = statement_record(
    {
        "id": "ibk-oct",
        "account_id": "acc-ibk",
        "name": "Octubre 2026",
        "date_start": "2026-09-26",
        "date_end": "2026-10-25",
        "status": 1,
        "balances": [_balance("PEN", -82000, -34860, 0)],
    }
)

IN_STATEMENT = [
    _line(1, "2026-09-27", "PLAZA VEA SURCO", -8430, "PEN", "004812"),
    _line(2, "2026-10-02", "UBER *TRIP", -4200, "PEN", None),
    _line(3, "2026-10-05", "STEAM PURCHASE", -1999, "USD", "004903"),
    _line(4, "2026-10-09", "SAGA FALABELLA", -9500, "PEN", "004931"),
    _line(5, "2026-10-14", "NETFLIX.COM", -4490, "PEN", "004977"),
    _line(6, "2026-10-20", "PAGO TARJETA", 50000, "PEN", "005102"),
    _line(7, "2026-10-24", "APPLE.COM/BILL", -1099, "USD", "004951"),
    _line(8, "2026-10-25", "INTERESES", -1240, "PEN", None),
]
#: The statement's review list in the engine's order: no place, oldest first, both
#: currencies mixed by date.
FLAGGED = [
    _line(11, "2026-10-03", "UBER *TRIP", -4200, "PEN", None),
    _line(12, "2026-10-18", "KFC JOCKEY PLAZA", -3190, "PEN", None),
    _line(13, "2026-10-21", "SPOTIFY P2F3", -599, "USD", None),
]

COMPLETED_WITH_FLAGGED = """
  ◈ EXPENSE WORLD  ▸  Statements  ▸  VIS-202610
────────────────────────────────────────────────────────────────────────────────
  VIS-202610  ·  Visa BCP  ·  2026-09-26 → 2026-10-25  ·  status completed
            begin          end      diff
  PEN     -455.60      -234.20         —
  USD        0.00       -30.98         —
  ⚑ 3 lines flagged for review: in no statement, dated up to this one's last day
  · f shows them

    #  Date        Title                     Operation  Cur     Amount
    1  2026-09-27  PLAZA VEA SURCO           004812     PEN     -84.30
    2  2026-10-02  UBER *TRIP                —          PEN     -42.00
    3  2026-10-05  STEAM PURCHASE            004903     USD     -19.99
    4  2026-10-09  SAGA FALABELLA            004931     PEN     -95.00
    5  2026-10-14  NETFLIX.COM               004977     PEN     -44.90
    6  2026-10-20  PAGO TARJETA              005102     PEN    +500.00
    7  2026-10-24  APPLE.COM/BILL            004951     USD     -10.99
    8  2026-10-25  INTERESES                 —          PEN     -12.40

 esc Back  r Refresh  u Revert  d Delete  f Flagged  ? Keys
"""

CODED_FLAGGED = """
  ◈ EXPENSE WORLD  ▸  Statements  ▸  VIS-202610  ▸  Flagged
────────────────────────────────────────────────────────────────────────────────

  VIS-202610 has 3 flagged lines. 3 lines dated up to its last day are in
  no statement.

  Date        Title                     Operation  Cur     Amount
  2026-10-03  UBER *TRIP                —          PEN     -42.00
  2026-10-18  KFC JOCKEY PLAZA          —          PEN     -31.90
  2026-10-21  SPOTIFY P2F3              —          USD      -5.99

  On an account with a statement code, when the paper prints the line, the
  upload made the paper's row a line of its own, its twin. Keep one:
    the bank's: delete your line. The statement stays completed.
    yours: revert, delete the twin, set your line's day to the row's day,
    upload the PDF again.
  When the paper does not print it: leave it for a later statement, or fix
  it, or delete it.

 esc Back to the statement  ⏎ Open  d Delete  ↑↓ Move
"""


def assert_pane(lines: list[str], pane: str) -> None:
    """The screen is the pane line for line, the room the terminal has left over blank
    between its last row and its footer."""
    wanted = _pane(pane)
    assert lines[:-1] == [*wanted[:-1], *[""] * (len(lines) - len(wanted))]
    assert lines[-1] == wanted[-1]


class Engine:
    """The fake engine's bank lines for one statement's screens. A read of the statement's
    lines (`statement_id`) answers `in_statement`; the draft's offer (`unreconciled`
    with dates) `offer`; the review list (`unassigned_in_period_of`) `flagged`; its
    count `count`, or the length of `flagged`. `GET /statements/{id}` answers `statement`.
    Every query is kept, in `reads` and `counts`."""

    def __init__(
        self,
        fake_client,
        monkeypatch,
        *,
        in_statement,
        flagged,
        offer=(),
        count=None,
        statement=None,
    ):
        self.reads: list[dict] = []
        self.counts: list[dict] = []
        self.count = count
        self.count_error: Exception | None = None
        self.flagged = flagged

        def get(path, *, auth=True, params=None):
            params = dict(params or {})
            fake_client.calls.append(("GET", path, params))
            if path.startswith("/statements/"):
                return dict(statement or VIS_OCT)
            if path == "/bank-lines/count":
                self.counts.append(params)
                if self.count_error is not None:
                    raise self.count_error
                return {"count": len(self.flagged) if self.count is None else self.count}
            assert path == "/bank-lines", path
            self.reads.append(params)
            if "unassigned_in_period_of" in params:
                return cursor_page(list(self.flagged))
            if "statement_id" in params:
                return cursor_page(list(in_statement))
            return cursor_page(list(offer))

        fake_client.get = get
        stub_home_month(monkeypatch)
        monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)
        monkeypatch.setattr(
            "expense.tui.screens.statements.load_account_name_map", lambda: dict(NAMES)
        )

    def review_reads(self) -> list[dict]:
        return [r for r in self.reads if "unassigned_in_period_of" in r]


def _statement(record: dict, code: str | None):
    async def scenario(pilot, app):
        screen = StatementScreen(dict(record), statement_code=code)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        # the statement's read, count included, has ended
        await wait_for(
            pilot,
            lambda: (
                not any(
                    w.group == "statement-detail-load" and not w.is_finished for w in app.workers
                )
            ),
        )
        await pilot.pause()
        return screen

    return scenario


# ---- the statement: ⚑ and f --------------------------------------------------------


def test_a_completed_statement_with_flagged_lines_reads_whole_at_80_columns(
    fake_client, monkeypatch
):
    engine = Engine(fake_client, monkeypatch, in_statement=IN_STATEMENT, flagged=FLAGGED)

    async def scenario(pilot, app):
        await _statement(VIS_OCT, "VIS")(pilot, app)
        await wait_for(pilot, lambda: _screen_lines(app)[-1].find("f Flagged") >= 0)
        return _screen_lines(app)

    lines = run_app(scenario, size=(80, 24))
    assert_pane(lines, COMPLETED_WITH_FLAGGED)
    # the count is read once, on the review list itself, when the screen opens
    assert engine.counts == [{"unassigned_in_period_of": "vis-oct"}]
    assert engine.review_reads() == []


@pytest.mark.parametrize(
    ("record", "code"),
    [(IBK_OCT, None), ({**VIS_OCT, "status": 1}, "VIS"), (VIS_OCT, "VIS")],
    ids=["draft", "draft waiting for its PDF", "completed"],
)
def test_the_flag_and_f_show_on_an_open_statement_too(fake_client, monkeypatch, record, code):
    """A draft's review list is exactly the lines a complete would flag, so a draft shows
    `⚑` and `f` as a completed statement does (contract: GET /v1/bank-lines,
    "Filters")."""
    engine = Engine(fake_client, monkeypatch, in_statement=[], flagged=FLAGGED)

    async def scenario(pilot, app):
        screen = await _statement(record, code)(pilot, app)
        line = screen.query_one("#rflag", Static)
        return line.display, bool(screen.check_action("flagged", ())), str(line.visual)

    shown, f_live, text = run_app(scenario, size=(80, 24))
    assert shown and f_live
    assert text.startswith("⚑ 3 lines flagged for review")
    assert engine.counts == [{"unassigned_in_period_of": record["id"]}]


def test_neither_shows_when_the_review_list_counts_none(fake_client, monkeypatch):
    engine = Engine(fake_client, monkeypatch, in_statement=[], flagged=[])

    async def scenario(pilot, app):
        screen = await _statement(VIS_OCT, "VIS")(pilot, app)
        await pilot.press("f")
        await pilot.pause()
        return (
            screen.query_one("#rflag", Static).display,
            bool(screen.check_action("flagged", ())),
            app.screen is screen,
        )

    assert run_app(scenario, size=(80, 24)) == (False, False, True)
    assert engine.counts == [{"unassigned_in_period_of": "vis-oct"}]


def test_the_screen_counts_again_each_time_it_reads_the_statement(fake_client, monkeypatch):
    """`r` reads the statement again, and the count with it: a line flagged since shows."""
    engine = Engine(fake_client, monkeypatch, in_statement=[], flagged=[])

    async def scenario(pilot, app):
        screen = await _statement(VIS_OCT, "VIS")(pilot, app)
        assert not screen.query_one("#rflag", Static).display
        engine.flagged = FLAGGED[:2]
        await pilot.press("r")
        await wait_for(pilot, lambda: screen.query_one("#rflag", Static).display)
        assert str(screen.query_one("#rflag", Static).visual).startswith("⚑ 2 lines flagged")

    run_app(scenario, size=(80, 24))
    assert engine.counts == [{"unassigned_in_period_of": "vis-oct"}] * 2


def test_a_refused_delete_or_revert_keeps_the_flag_and_f(fake_client, monkeypatch):
    """A change the engine refuses changes nothing, so the review list still counts the
    same lines and `⚑` and `f` stay."""
    Engine(fake_client, monkeypatch, in_statement=[], flagged=FLAGGED)
    refusal = EngineError(
        "CONFLICT", "Revert it first.", {"status": "RECONCILIATION_NOT_DRAFT"}, 409, {}
    )

    async def scenario(pilot, app):
        screen = await _statement(VIS_OCT, "VIS")(pilot, app)
        seen = []
        for method, key in (("DELETE", "d"), ("POST", "u")):
            fake_client.errors[method] = refusal
            await pilot.press(key)
            await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
            await pilot.press("y")
            await wait_for(pilot, lambda: app.screen is screen and not screen._busy)
            await pilot.pause()
            del fake_client.errors[method]
            seen.append(
                (
                    screen.query_one("#rflag", Static).display,
                    bool(screen.check_action("flagged", ())),
                )
            )
        return seen

    assert run_app(scenario, size=(80, 24)) == [(True, True), (True, True)]


def test_a_count_that_cannot_be_read_toasts_the_engines_words(fake_client, monkeypatch):
    engine = Engine(fake_client, monkeypatch, in_statement=[], flagged=FLAGGED)
    engine.count_error = EngineError("INTERNAL_ERROR", "Something broke.", None, 500, {})
    notes: list = []
    monkeypatch.setattr(
        StatementScreen,
        "notify",
        lambda self, message, **kw: notes.append((str(message), kw.get("severity"))),
    )

    async def scenario(pilot, app):
        screen = await _statement(VIS_OCT, "VIS")(pilot, app)
        await wait_for(pilot, lambda: notes)
        return screen.query_one("#rflag", Static).display

    assert run_app(scenario, size=(80, 24)) is False
    assert notes == [(format_error(engine.count_error), "error")]


# ---- the flagged screen ----------------------------------------------------------------


def test_the_flagged_screen_of_a_coded_account_reads_whole_at_80_columns(fake_client, monkeypatch):
    engine = Engine(fake_client, monkeypatch, in_statement=IN_STATEMENT, flagged=FLAGGED)

    async def scenario(pilot, app):
        screen = await _statement(VIS_OCT, "VIS")(pilot, app)
        await wait_for(pilot, lambda: screen._flagged)
        await pilot.press("f")
        await wait_for(pilot, lambda: isinstance(app.screen, FlaggedLinesScreen))
        flagged = app.screen
        await wait_for(pilot, lambda: flagged._list is not None)
        await pilot.pause()
        return _screen_lines(app)

    lines = run_app(scenario, size=(80, 24))
    assert_pane(lines, CODED_FLAGGED)
    # one read of the review list, every currency together in the statement's order, and
    # its count: nothing names a currency or a line
    assert engine.review_reads() == [
        {"unassigned_in_period_of": "vis-oct", "sort": "statement", "limit": 200}
    ]
    assert engine.counts == [{"unassigned_in_period_of": "vis-oct"}] * 2  # open, then here


def test_the_flagged_screen_of_an_account_with_no_code_shows_no_ways(fake_client, monkeypatch):
    """No statement code: the two ways show for an account with one and nothing
    for one without, so no words show under the list."""
    Engine(fake_client, monkeypatch, in_statement=[], flagged=FLAGGED)

    async def scenario(pilot, app):
        screen = await _statement(IBK_OCT, None)(pilot, app)
        await pilot.press("f")
        await wait_for(pilot, lambda: isinstance(app.screen, FlaggedLinesScreen))
        await wait_for(pilot, lambda: app.screen._list is not None)
        await pilot.pause()
        assert screen is not app.screen
        return _screen_lines(app), bool(app.screen.query("#fways"))

    lines, ways = run_app(scenario, size=(80, 24))
    wanted = _pane(CODED_FLAGGED)
    assert lines[:2] == [wanted[0].replace("VIS-202610", "Octubre 2026"), wanted[1]]
    assert lines[3:5] == [
        "  Octubre 2026 has 3 flagged lines. 3 lines dated up to its last day are in",
        "  no statement.",
    ]
    assert lines[5:11] == wanted[5:11]  # the list
    assert not ways
    assert lines[-1] == wanted[-1]  # and nothing between the list and the footer
    assert lines[11:-1] == [""] * (len(lines) - 12)


# ---- `u` on the browse: the account's lines in no statement ----------------------------

#: The caption and list of the lines in no statement, from the caption to the footer, at 80 columns.
NO_STATEMENT_LIST = """
  In no statement · Visa BCP   ·   6 of 6 loaded · oldest first   ·
  ! dated inside a statement

    Date        Title                     Operation  Cur     Amount
  ! 2026-10-03  UBER *TRIP                —          PEN     -42.00
  ! 2026-10-18  KFC JOCKEY PLAZA          —          PEN     -31.90
  ! 2026-10-21  SPOTIFY P2F3              —          USD      -5.99
    2026-11-03  UBER EATS                 —          PEN     -36.40
    2026-11-06  APPLE.COM/BILL            004951     USD      -2.99
    2026-11-11  TOTTUS LA MOLINA          005266     PEN    -118.70

 esc Back  ⏎ Edit  d Delete  r Refresh  ? Keys
"""
NO_STATEMENT_CAPTION = (
    "In no statement · Visa BCP   ·   6 of 6 loaded · oldest first   ·\n! dated inside a statement"
)
UNFILED = [
    _line(21, "2026-10-03", "UBER *TRIP", -4200, "PEN", None, account="acc-visa"),
    _line(22, "2026-10-18", "KFC JOCKEY PLAZA", -3190, "PEN", None, account="acc-visa"),
    _line(23, "2026-10-21", "SPOTIFY P2F3", -599, "USD", None, account="acc-visa"),
    _line(24, "2026-11-03", "UBER EATS", -3640, "PEN", None, account="acc-visa"),
    _line(25, "2026-11-06", "APPLE.COM/BILL", -299, "USD", "004951", account="acc-visa"),
    _line(26, "2026-11-11", "TOTTUS LA MOLINA", -11870, "PEN", "005266", account="acc-visa"),
]


def _browse(fake_client, monkeypatch, lines, count=None):
    """The browse's reads: accounts, the open account's statements, and the lines in no
    statement (`unreconciled`) with their count. Returns the queries of the last two."""
    reads: list[dict] = []
    counts: list[dict] = []

    def get(path, *, auth=True, params=None):
        params = dict(params or {})
        fake_client.calls.append(("GET", path, params))
        if path == "/accounts":
            from tests.unit.helpers import whole

            return whole([a for a in ACCOUNTS if not a["is_archived"]])
        if path == "/statements":
            from tests.unit.helpers import whole

            return whole([s for s in VISA_STATEMENTS if s["account_id"] == params["account_id"]])
        if path == "/bank-lines/count":
            counts.append(params)
            return {"count": len(lines) if count is None else count}
        assert path == "/bank-lines", path
        reads.append(params)
        return cursor_page(list(lines))

    fake_client.get = get
    stub_home_month(monkeypatch)
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)
    return reads, counts


def test_u_lists_the_accounts_lines_in_no_statement_in_one_read(fake_client, monkeypatch):
    reads, counts = _browse(fake_client, monkeypatch, UNFILED)

    async def scenario(pilot, app):
        screen = await _open(pilot, app, VISA)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        await pilot.pause()
        listed = screen._statement_list
        return _screen_lines(app), [r.key for r in listed._rows], listed._headers, listed._caption

    lines, keys, headers, screen_caption = run_app(scenario, size=(80, 24))
    # one read of the account's lines in no statement, oldest first, every currency
    # together (no currency named), and one count of the same question
    assert reads == [
        {"account_id": "acc-visa", "unreconciled": "true", "sort": "date_asc", "limit": 10}
    ]
    assert counts == [{"account_id": "acc-visa", "unreconciled": "true"}]
    assert keys == [f"l{n}" for n in range(21, 27)]
    assert headers == ["", "Date", "Title", "Operation", "Cur", "Amount"]
    # the caption, the list and the footer, line for line
    first = next(n for n, line in enumerate(lines) if "In no statement" in line)
    assert_pane(lines[first:], NO_STATEMENT_LIST)
    assert screen_caption == NO_STATEMENT_CAPTION


def test_the_caption_counts_against_the_engines_count(fake_client, monkeypatch):
    """The caption says `N of M loaded` with M the engine's count, not the length of the
    page in hand."""
    reads, counts = _browse(fake_client, monkeypatch, UNFILED, count=1716)

    async def scenario(pilot, app):
        screen = await _open(pilot, app, VISA)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        return screen._statement_list._caption

    caption = run_app(scenario, size=(80, 40))
    assert caption == NO_STATEMENT_CAPTION.replace("6 of 6", "6 of 1716")
    assert counts == [{"account_id": "acc-visa", "unreconciled": "true"}]
    assert all(r["sort"] == "date_asc" for r in reads)


LONG_TITLE = "PAGO SERVICIOS INTERNET HOGAR LIMA PERU"  # 39 letters, past the title's 24


def _listed_at(fake_client, monkeypatch, width, *, more=False, down=0):
    """The lines in no statement with the second one's title long, at `width` columns:
    the screen's lines, the cursor `down` rows from the first (the lines beyond the first
    six are made up)."""
    long = _line(22, "2026-10-18", LONG_TITLE, -3190, "PEN", None, account="acc-visa")
    extra = [
        _line(30 + n, f"2026-11-{12 + n}", f"MORE {n}", -100, "PEN", None, account="acc-visa")
        for n in range(down)
    ]
    lines = [UNFILED[0], long, *UNFILED[2:], *extra]
    _browse(fake_client, monkeypatch, lines)
    if more:
        get = fake_client.get
        fake_client.get = lambda path, **kw: {
            **get(path, **kw),
            **({"next_cursor": "c6"} if path == "/bank-lines" else {}),
        }

    async def scenario(pilot, app):
        screen = await _open(pilot, app, VISA)
        await pilot.press("u")
        await wait_for(pilot, lambda: screen._mode == "unfiled" and screen._unfiled)
        await pilot.press(*["down"] * down)
        await pilot.pause()
        key = "pgup Prev" if down else "10 more" if more else "? Keys"
        await wait_for(pilot, lambda: key in screen_lines(app)[-1])  # the footer repaints late
        return _screen_lines(app)

    return run_app(scenario, size=(width, 24))


def test_the_title_takes_the_room_it_needs_and_the_other_columns_stay_packed(
    fake_client, monkeypatch
):
    """A title past its 24 letters is cut with `…` when the row would not fit the
    terminal and whole on a wider one, the title column then as wide as it; Operation,
    Cur and Amount stay two cells apart behind it, the row never stretched to the room."""
    narrow = _listed_at(fake_client, monkeypatch, 70)
    wide = _listed_at(fake_client, monkeypatch, 120)
    cut = next(line for line in narrow if "PAGO SERV" in line)
    whole = next(line for line in wide if "PAGO SERV" in line)
    assert LONG_TITLE not in cut and "…" in cut
    assert LONG_TITLE in whole
    header = next(line for line in wide if "Operation" in line)
    title_at = header.index("Title")
    assert header.index("Operation") == title_at + len(LONG_TITLE) + 2
    assert len(header) == len(whole)  # the amount ends the row, nothing stretched past it
    assert len(whole) == title_at + len(LONG_TITLE) + 2 + 9 + 2 + 3 + 2 + 9


def test_the_footer_reads_the_drawn_keys_first_and_the_paging_keys_after_them(
    fake_client, monkeypatch
):
    """`pgdn 10 more` while the engine holds more lines and `pgup Prev` once a page lies
    before the one shown follow `? Keys`; the footer's drawn keys never move."""
    drawn = "esc Back  ⏎ Edit  d Delete  r Refresh  ? Keys"
    assert _listed_at(fake_client, monkeypatch, 80)[-1].strip() == drawn
    assert _listed_at(fake_client, monkeypatch, 80, more=True)[-1].strip() == (
        drawn + "  pgdn 10 more"
    )
    second_page = _listed_at(fake_client, monkeypatch, 80, down=7)
    assert second_page[-1].strip() == drawn + "  pgup Prev"


def test_the_flagged_words_speak_of_no_closed_day():
    """A flagged line sits on the last day, which stays open; nothing under the list
    speaks of a closed or sealed day."""
    from expense.tui.screens.statements import FLAGGED_WAYS

    words = " ".join(w for _, w in FLAGGED_WAYS).lower()
    assert "closed" not in words and "seal" not in words
