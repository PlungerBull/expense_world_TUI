"""A statement's screen: its head and its one list, panes 4, 5, 8 and 9 of
docs/mockups/expense-world-statements-screens.html at 80 columns.

The head shows each covered currency's begin, end and diff once; the list is the
paper's order, both currencies mixed and numbered 1, 2, 3 … with no gaps, a `Cur`
column, the opening balance apart; the lines are read by account, every currency
together, in the engine's order (contract: GET /v1/bank-lines, "Ordering")."""

from types import SimpleNamespace

import pytest
from rich.style import Style
from textual.widgets import Static

from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.reconciliations import ReconciliationDetailScreen
from expense.tui.widgets.checklist import CheckList
from tests.unit.helpers import (
    NOVIEMBRE_IBK,
    bank_line_row,
    cursor_page,
    import_part,
    money_at_start_refusal,
    render_text,
    run_app,
    screen_lines,
    shown,
    statement_complete_answer,
    statement_record,
    stub_home_month,
    wait_for,
)

NAMES = {"acc-visa": "Visa BCP", "acc-ibk": "IBK Visa"}


def _line(
    n: int,
    day: str,
    title: str,
    cents: int,
    currency: str,
    operation: str | None,
    *,
    account: str = "acc-visa",
    opening: bool = False,
) -> dict:
    """A bank line of an account, `n` its id's number."""
    part = import_part(
        f"t{n}",
        cents,
        account_id=account,
        currency_code=currency,
        line=f"l{n}",
        day=day,
        title=title,
    )
    return bank_line_row(
        f"l{n}",
        [part],
        net_cents=cents,
        operation_code=operation,
        account_id=account,
        currency_code=currency,
        is_opening_balance=opening,
    )


#: [VIS] Agosto's lines in the order the engine lists them: the paper's places, then the
#: lines holding none, oldest first (the opening balances are two of those).
AGOSTO = [
    _line(1, "2026-07-27", "TAMBO MIRAFLORES", -750, "PEN", None),
    _line(2, "2026-07-29", "PLAZA VEA SURCO", -8430, "PEN", "004812"),
    _line(3, "2026-08-02", "UBER *TRIP", -4200, "PEN", None),
    _line(4, "2026-08-05", "AMAZON MKTPLACE", -2499, "USD", "004890"),
    _line(5, "2026-08-14", "NETFLIX.COM", -4490, "PEN", "004977"),
    _line(6, "2026-08-20", "PAGO TARJETA", 80000, "PEN", "005102"),
    _line(7, "2026-08-20", "PAGO TARJETA", 6740, "USD", "005103"),
    _line(8, "2026-08-24", "SPOTIFY P2F3", -599, "USD", None),
    _line(9, "2026-08-25", "INTERESES", -1240, "PEN", None),
    _line(10, "2026-08-25", "SEGURO DE DESGRAVAMEN", -690, "PEN", None),
    _line(11, "2026-07-26", "Opening balance", -120410, "PEN", None, opening=True),
    _line(12, "2026-07-26", "Opening balance", -3642, "USD", None, opening=True),
]


def _balance(currency: str, begin, end, diff) -> dict:
    return {
        "currency_code": currency,
        "beginning_balance_cents": begin,
        "ending_balance_cents": end,
        "difference_cents": diff,
    }


VIS_AGOSTO = statement_record(
    {
        "id": "vis-ago",
        "account_id": "acc-visa",
        "name": "[VIS] Agosto",
        "date_start": "2026-07-26",
        "date_end": "2026-08-25",
        "status": 2,
        "balances": [_balance("PEN", 0, -60210, 0), _balance("USD", 0, 0, 0)],
    }
)

#: Octubre 2026 on IBK Visa: a draft covering soles, then a dollar line ticked in, so the
#: dollars' balances are both blank.
OCTUBRE = statement_record(
    {
        "id": "ibk-oct",
        "account_id": "acc-ibk",
        "name": "Octubre 2026",
        "date_start": "2026-09-26",
        "date_end": "2026-10-25",
        "status": 1,
        "balances": [_balance("PEN", -82000, -34860, 0), _balance("USD", None, None, None)],
    }
)
OCTUBRE_IN = [
    _line(21, "2026-10-04", "WONG BENAVIDES", -6310, "PEN", "003301", account="acc-ibk"),
    _line(22, "2026-10-12", "CINEPLANET", -3800, "PEN", None, account="acc-ibk"),
    _line(23, "2026-10-14", "AMAZON MKTPLACE", -2499, "USD", "003340", account="acc-ibk"),
    _line(24, "2026-10-18", "PAGO TARJETA", 60000, "PEN", "003355", account="acc-ibk"),
    _line(25, "2026-10-22", "RAPPI", -2750, "PEN", "003372", account="acc-ibk"),
]
OCTUBRE_OUT = [_line(26, "2026-10-24", "SPOTIFY P2F3", -599, "USD", None, account="acc-ibk")]

PANE_4 = """
  ◈ EXPENSE WORLD  ▸  Statements  ▸  [VIS] Agosto
────────────────────────────────────────────────────────────────────────────────
  [VIS] Agosto  ·  Visa BCP  ·  2026-07-26 → 2026-08-25  ·  status completed
            begin          end      diff
  PEN        0.00      -602.10         —
  USD        0.00         0.00         —

    #  Date        Title                     Operation  Cur     Amount
    1  2026-07-27  TAMBO MIRAFLORES          —          PEN      -7.50
    2  2026-07-29  PLAZA VEA SURCO           004812     PEN     -84.30
    3  2026-08-02  UBER *TRIP                —          PEN     -42.00
    4  2026-08-05  AMAZON MKTPLACE           004890     USD     -24.99
    5  2026-08-14  NETFLIX.COM               004977     PEN     -44.90
    6  2026-08-20  PAGO TARJETA              005102     PEN    +800.00
    7  2026-08-20  PAGO TARJETA              005103     USD     +67.40
    8  2026-08-24  SPOTIFY P2F3              —          USD      -5.99
    9  2026-08-25  INTERESES                 —          PEN     -12.40
   10  2026-08-25  SEGURO DE DESGRAVAMEN     —          PEN      -6.90

       Not on the paper
    —  2026-07-26  Opening balance           —          PEN  -1,204.10
    —  2026-07-26  Opening balance           —          USD     -36.42

 esc Back  r Refresh  u Revert  d Delete  ? Keys
"""

PANE_5 = """
  ◈ EXPENSE WORLD  ▸  Statements  ▸  Octubre 2026
────────────────────────────────────────────────────────────────────────────────
  Octubre 2026  ·  IBK Visa  ·  2026-09-26 → 2026-10-25  ·  status draft
            begin          end      diff
  PEN     -820.00      -348.60         —
  USD           —            —

       Date        Title                     Operation  Cur     Amount
  [x]  2026-10-04  WONG BENAVIDES            003301     PEN     -63.10
  [x]  2026-10-12  CINEPLANET                —          PEN     -38.00
  [x]  2026-10-14  AMAZON MKTPLACE           003340     USD     -24.99
  [x]  2026-10-18  PAGO TARJETA              003355     PEN    +600.00
  [x]  2026-10-22  RAPPI                     003372     PEN     -27.50
  [ ]  2026-10-24  SPOTIFY P2F3              —          USD      -5.99

 space Toggle  esc Back  r Refresh  c Complete  u Revert  d Delete  ? Keys
"""


def _engine(fake_client, monkeypatch, *, statement_lines, other_lines=(), statement=None):
    """The fake engine's bank lines: the statement's read (`statement_id`) answers
    `statement_lines`, the read of the account's lines in no statement `other_lines`
    (both lists are read at each call, so a test may change them); `GET /statements/{id}`
    answers `statement`. Returns the list of every `GET /bank-lines` query."""
    queries: list[dict] = []

    def get(path, *, auth=True, params=None):
        if path.startswith("/statements/"):
            return dict(statement)
        if path == "/bank-lines/count":  # the review list's count: nothing is flagged
            return {"count": 0}
        assert path == "/bank-lines", path
        queries.append(dict(params or {}))
        lines = statement_lines if "statement_id" in (params or {}) else other_lines
        return cursor_page(list(lines))

    fake_client.get = get
    stub_home_month(monkeypatch)
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: dict(NAMES)
    )
    return queries


def _screen_lines(app) -> list[str]:
    """The screen as drawn, a line each, trailing blanks off. An income is
    written with its plus, as the mockups draw it (`+800.00`)."""
    lines = screen_lines(app)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _pane(text: str) -> list[str]:
    """A pane's lines as the mockup draws them, trailing blanks off."""
    return [line.rstrip() for line in text.strip("\n").splitlines()]


def _open(statement: dict, code: str | None = None):
    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(statement), statement_code=code)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.pause()
        head = screen.query_one("#rhead", Static)
        return (
            screen,
            _screen_lines(app),
            SimpleNamespace(text=shown(head), parts=head.content.renderables),
        )

    return scenario


def test_a_completed_statement_reads_as_pane_4_at_80_columns(fake_client, monkeypatch):
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)
    _, lines, _ = run_app(_open(VIS_AGOSTO, "VIS"), size=(80, 24))
    # the footer has `d` and no `c`, and no `space Toggle` (Question 9 B)
    assert lines == _pane(PANE_4)


def test_a_draft_reads_as_pane_5_at_80_columns(fake_client, monkeypatch):
    _engine(fake_client, monkeypatch, statement_lines=OCTUBRE_IN, other_lines=OCTUBRE_OUT)
    _, lines, _ = run_app(_open(OCTUBRE), size=(80, 16))
    assert lines == _pane(PANE_5)


def test_lines_are_read_by_account_every_currency_together_in_the_engines_order(
    fake_client, monkeypatch
):
    """The statement's lines: its id and its account, in the statement's order, no
    currency; the draft's offer: the account's lines in no statement inside the
    days, oldest first. No sort is made here
    (contract: GET /v1/bank-lines, "Filters") (contract: GET /v1/bank-lines, "Ordering")."""
    queries = _engine(fake_client, monkeypatch, statement_lines=OCTUBRE_IN, other_lines=OCTUBRE_OUT)
    run_app(_open(OCTUBRE), size=(80, 18))
    assert sorted(queries, key=lambda q: "unreconciled" in q) == [
        {"account_id": "acc-ibk", "statement_id": "ibk-oct", "sort": "statement", "limit": 200},
        {
            "account_id": "acc-ibk",
            "unreconciled": "true",
            "date_from": "2026-09-26",
            "date_to": "2026-10-25",
            "sort": "date_asc",
            "limit": 200,
        },
    ]
    assert not any("currency_code" in q for q in queries)


def test_the_rows_keep_the_order_the_engine_gave_them(fake_client, monkeypatch):
    """Nothing sorts client-side: lines listed against their dates stay where the
    engine put them, and the numbers follow the rows."""
    odd = [AGOSTO[4], AGOSTO[0], AGOSTO[2]]
    _engine(fake_client, monkeypatch, statement_lines=odd)
    screen, _, _ = run_app(_open(VIS_AGOSTO, "VIS"), size=(80, 24))
    assert [row.key for row in screen._list._rows] == ["l5", "l1", "l3"]
    assert [row.number for row in screen._list._rows] == [1, 2, 3]


def test_a_currency_the_statement_does_not_cover_shows_nothing(fake_client, monkeypatch):
    """Septiembre covers soles alone: the head has a soles line and no dollar line, and
    a dollar line in its list does not bring one (contract: "Statements", "Which
    currencies a statement covers")."""
    soles = statement_record(
        {**VIS_AGOSTO, "balances": [_balance("PEN", 0, -60210, 0)], "name": "VIS-202609"}
    )
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO[:4])
    _, _, visual = run_app(_open(soles), size=(80, 24))
    head = visual.text
    assert [line.split()[0] for line in head.splitlines()[2:]] == ["PEN"]
    assert "USD" not in head


def test_a_statement_covering_nothing_has_no_balances_table(fake_client, monkeypatch):
    bare = statement_record({**VIS_AGOSTO, "balances": []})
    _engine(fake_client, monkeypatch, statement_lines=[])
    _, _, visual = run_app(_open(bare), size=(80, 24))
    head = visual.text
    assert head.splitlines() == [
        "  [VIS] Agosto  ·  Visa BCP  ·  2026-07-26 → 2026-08-25  ·  status completed"
    ]


def test_a_blank_balance_is_a_dim_dash_and_its_difference_stays_blank(fake_client, monkeypatch):
    """Question 3 B: a balance not entered is a dim `—`, never zero
    (contract: "Statements", "A balance not entered is `null`, never zero")."""
    _engine(fake_client, monkeypatch, statement_lines=OCTUBRE_IN, other_lines=OCTUBRE_OUT)
    _, _, head = run_app(_open(OCTUBRE), size=(80, 18))
    usd_part = next(p for p in head.parts[1:] if p.plain.split()[:1] == ["USD"])
    assert usd_part.plain.split() == ["USD", "—", "—"]  # no figure, and no difference
    dashes = [span.style for span in usd_part.spans if "—" in usd_part.plain[span.start : span.end]]
    assert len(dashes) == 2 and all(Style.parse(str(style)).dim for style in dashes)


@pytest.mark.parametrize("height", [30, 24, 22, 21, 17])
def test_every_row_and_the_page_status_show_at_any_height(fake_client, monkeypatch, height):
    """The opening balances' blank line and label cost two lines on a page that shares
    it with numbered rows, and the pages count them: no page is taller than the room
    for the list, and paging through shows all 12 rows once."""
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(VIS_AGOSTO))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.pause()
        rlist = screen.query_one("#rlist")
        seen, statuses = [], []
        for _ in range(12):
            lst = screen._list
            assert lst.outer_size.height <= rlist.content_size.height, height
            seen += [row.key for row in lst._window()[1]]
            statuses.append(lst.page_status)
            if lst.cursor_index + 1 == lst.row_count or lst._window()[1][-1].key == "l12":
                break
            lst.action_page(1)
            await pilot.pause()
        return seen, statuses

    seen, statuses = run_app(scenario, size=(80, height))
    assert seen == [f"l{n}" for n in range(1, 13)]
    assert (statuses == [None]) == (height >= 24)


def test_a_page_of_opening_balances_alone_draws_the_label_where_the_header_stands():
    rows = [("l1", "2026-07-26", "Opening balance", None, -100, "PEN", None, True)]
    shown = render_text(CheckList(rows, read_only=True, numbered=True)._build(), width=80)
    assert [line.strip() for line in shown.splitlines() if line.strip()][0] == "Not on the paper"
    assert shown.splitlines()[0] == ""
    assert "Date" not in shown


def test_pages_hold_rows_by_their_lines():
    """Ten rows and two opening balances at a budget of 12 lines: the numbered rows fill
    page 1 (adding an opening balance would cost 2 more lines), the opening balances page 2."""
    rows = [(f"l{n}", "2026-08-01", "x", None, -1, "PEN", n, False) for n in range(1, 11)]
    rows += [(f"o{n}", "2026-07-26", "o", None, -1, "PEN", None, True) for n in (1, 2)]
    chk = CheckList(rows, read_only=True, numbered=True, page_size=12)
    assert chk._page_starts() == [0, 10]
    chk = CheckList(rows, read_only=True, numbered=True, page_size=14)
    assert chk._page_starts() == [0]
    chk = CheckList(rows, read_only=True, numbered=True, page_size=8)
    assert chk._page_starts() == [0, 8]
    assert chk.page_status == "rows 1-8 of 12 · page 1 of 2"
    chk.action_page(1)
    assert chk.cursor_key == "l9" and chk.page_status == "rows 9-12 of 12 · page 2 of 2"


PANE_8_TOP = """
  ◈ EXPENSE WORLD  ▸  Statements  ▸  Septiembre 2026
────────────────────────────────────────────────────────────────────────────────
  Septiembre 2026  ·  IBK Visa  ·  2026-08-26 → 2026-09-25  ·  status completed
            begin          end      diff
  PEN     -912.30      -820.00         —
  ⚠ The statement's last line is 6 days before its last day.
  ⚠ USD: Dollars held 0.00 all through the statement's days.
"""

PANE_9 = """
  ◈ EXPENSE WORLD  ▸  Statements  ▸  Noviembre 2026
────────────────────────────────────────────────────────────────────────────────
  Noviembre 2026  ·  Visa BCP  ·  2026-10-26 → 2026-11-25  ·  status draft
            begin          end      diff
  PEN     -234.20            —
  USD      -30.98            —
  closes when its PDF is dropped on the LOG bar

  Date        Title                     Operation  Cur     Amount
  2026-10-29  CINEPLANET                —          PEN     -38.00
  2026-11-02  WONG BENAVIDES            005230     PEN     -63.10

 esc Back  r Refresh  d Delete  ? Keys
"""

NOVIEMBRE = statement_record(
    {
        "id": "vis-nov",
        "account_id": "acc-visa",
        "name": "Noviembre 2026",
        "date_start": "2026-10-26",
        "date_end": "2026-11-25",
        "status": 1,
        "balances": [_balance("PEN", -23420, None, None), _balance("USD", -3098, None, None)],
    }
)
NOVIEMBRE_LINES = [
    _line(31, "2026-10-29", "CINEPLANET", -3800, "PEN", None),
    _line(32, "2026-11-02", "WONG BENAVIDES", -6310, "PEN", "005230"),
]
SEPTIEMBRE = statement_record(
    {
        "id": "ibk-sep",
        "account_id": "acc-ibk",
        "name": "Septiembre 2026",
        "date_start": "2026-08-26",
        "date_end": "2026-09-25",
        "status": 1,
        "balances": [_balance("PEN", -91230, -82000, 0)],
    }
)
SEPTIEMBRE_LINES = [
    _line(41, "2026-08-29", "METRO SURCO", -9120, "PEN", "003210", account="acc-ibk"),
    _line(42, "2026-09-06", "TOTTUS LA MOLINA", -5680, "PEN", "003244", account="acc-ibk"),
]


def test_a_tick_into_a_soles_only_draft_reads_the_statement_again_as_pane_5(
    fake_client, monkeypatch
):
    """Ticking a dollar line in: the screen reads the statement and its lines again,
    and the dollars the statement now covers show blank, a dim `—`, their difference
    blank (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment")."""
    soles = statement_record({**OCTUBRE, "balances": [_balance("PEN", -82000, -34860, 0)]})
    inside = [line for line in OCTUBRE_IN if line["id"] != "l23"]
    amazon = OCTUBRE_IN[2]
    outside = [amazon, *OCTUBRE_OUT]
    reads: list[str] = []
    _engine(fake_client, monkeypatch, statement_lines=inside, other_lines=outside, statement=soles)
    plain_get = fake_client.get

    def get(path, *, auth=True, params=None):
        if path.startswith("/statements/"):
            reads.append(path)
            return dict(OCTUBRE)  # the engine after the tick: dollars covered, both blank
        return plain_get(path, auth=auth, params=params)

    fake_client.get = get

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(soles))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.pause()
        assert "USD" not in shown(screen.query_one("#rhead", Static))
        first = screen._list
        for _ in range(4):
            await pilot.press("down")
        # the engine after the PUT: the dollar line is in the statement, in its place
        inside[:] = OCTUBRE_IN
        outside[:] = OCTUBRE_OUT
        await pilot.press("space")
        await wait_for(pilot, lambda: screen._list is not first and reads)
        await pilot.pause()
        return _screen_lines(app)

    lines = run_app(scenario, size=(80, 16))
    assert fake_client.puts == [("/transactions/t23", {"statement_id": "ibk-oct"})]
    assert reads == ["/statements/ibk-oct"]
    assert lines == _pane(PANE_5)


def test_the_close_notes_of_a_currency_not_covered_follow_the_covered_ones_as_pane_8(
    fake_client, monkeypatch
):
    """The close reviews every currency: a covered one's note sits under its balances,
    a currency with no row has its note led by its code, under the head, beside them
    (contract: POST /v1/statements/{statement_id}/complete, "`not_covered`")."""
    _engine(fake_client, monkeypatch, statement_lines=SEPTIEMBRE_LINES)
    answer = statement_complete_answer(SEPTIEMBRE)
    answer["balances"][0]["warnings"] = ["The statement's last line is 6 days before its last day."]
    answer["not_covered"] = [
        {
            "currency_code": "USD",
            "warnings": ["Dollars held 0.00 all through the statement's days."],
            "coverage_gap": None,
            "review_lines": [],
        },
        {"currency_code": "EUR", "warnings": [], "coverage_gap": None, "review_lines": []},
    ]
    fake_client.write_responses["/statements/ibk-sep/complete"] = answer

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(SEPTIEMBRE))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: screen._record["status"] == 2)
        await wait_for(pilot, lambda: screen.query_one("#rwarn", Static).display)
        await pilot.pause()
        return _screen_lines(app)

    lines = run_app(scenario, size=(80, 24))
    top = _pane(PANE_8_TOP)
    assert lines[: len(top)] == top  # an empty `not_covered` entry draws nothing
    assert lines[len(top)] == ""  # then the list, which keeps its own blank line


#: Pane 8's list: a completed statement on an account with no statement code has no `#`.
SEPTIEMBRE_DONE = statement_record(SEPTIEMBRE | {"status": 2})
SEPTIEMBRE_PAPER = SEPTIEMBRE_LINES + [
    _line(43, "2026-09-12", "PAGO TARJETA", 30000, "PEN", "003260", account="acc-ibk"),
    _line(44, "2026-09-19", "RAPPI", -5970, "PEN", "003281", account="acc-ibk"),
]
PANE_8_LIST = """
  ◈ EXPENSE WORLD  ▸  Statements  ▸  Septiembre 2026
────────────────────────────────────────────────────────────────────────────────
  Septiembre 2026  ·  IBK Visa  ·  2026-08-26 → 2026-09-25  ·  status completed
            begin          end      diff
  PEN     -912.30      -820.00         —

  Date        Title                     Operation  Cur     Amount
  2026-08-29  METRO SURCO               003210     PEN     -91.20
  2026-09-06  TOTTUS LA MOLINA          003244     PEN     -56.80
  2026-09-12  PAGO TARJETA              003260     PEN    +300.00
  2026-09-19  RAPPI                     003281     PEN     -59.70

 esc Back  r Refresh  u Revert  d Delete  ? Keys
"""


def test_a_completed_statement_on_an_account_with_no_code_draws_no_number_as_pane_8(
    fake_client, monkeypatch
):
    # The pane's two `⚠` lines are left out: they show only just after `c`, and
    # test_the_close_notes_of_a_currency_not_covered_… pins them.
    _engine(fake_client, monkeypatch, statement_lines=SEPTIEMBRE_PAPER)
    _, lines, _ = run_app(_open(SEPTIEMBRE_DONE), size=(80, 13))
    assert lines == _pane(PANE_8_LIST)


def test_only_a_completed_statement_on_an_account_with_a_code_is_numbered(fake_client, monkeypatch):
    """`#` leads the list of a completed statement with a code (pane 4) and no other
    (panes 5, 8 and 9)."""
    _engine(fake_client, monkeypatch, statement_lines=SEPTIEMBRE_PAPER)
    headers = {}
    for key, statement, code in [
        ("completed, code", SEPTIEMBRE_DONE, "IBK"),
        ("completed, no code", SEPTIEMBRE_DONE, None),
        ("open, code", NOVIEMBRE, "VIS"),
        ("open, no code", SEPTIEMBRE, None),
    ]:
        _, lines, _ = run_app(_open(statement, code), size=(80, 24))
        headers[key] = next(line for line in lines if "Date " in line and "Title" in line)
    numbered = {key: line.lstrip().startswith("#") for key, line in headers.items()}
    assert numbered == {
        "completed, code": True,
        "completed, no code": False,
        "open, code": False,
        "open, no code": False,
    }


LONG_ACCOUNT = "Cuenta Sueldo Interbank Soles Principal Hogar"


def _long_account(monkeypatch):
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map",
        lambda: {**NAMES, "acc-visa": LONG_ACCOUNT},
    )


def test_a_long_account_name_wraps_the_head_under_the_statement_name(fake_client, monkeypatch):
    """At 80 columns the head's second line stands under the statement name's first
    letter, after the two-cell indent, never at column 1."""
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)
    _long_account(monkeypatch)
    _, lines, _ = run_app(_open(VIS_AGOSTO, "VIS"), size=(80, 24))
    first = next(n for n, line in enumerate(lines) if line.startswith("  [VIS] Agosto"))
    head = lines[first : first + 2]
    assert LONG_ACCOUNT in " ".join(" ".join(head).split())
    assert head[1].startswith("  ") and not head[1].startswith("   ")
    assert head[1].strip().split()[-1] == "completed"
    assert "status" in " ".join(head)
    assert lines[first + 2].strip().startswith("begin")  # the balances follow, as they were


def test_a_long_close_note_wraps_under_its_first_word_after_the_warning_sign(
    fake_client, monkeypatch
):
    """A long `⚠` note and a long `⚠ USD: …` note each wrap under their first word,
    never under the `⚠` or at column 1."""
    _engine(fake_client, monkeypatch, statement_lines=SEPTIEMBRE_LINES)
    long_note = (
        "The statement's last line is six days before its last day, and the days after it "
        "hold nothing at all on this account."
    )
    usd_note = (
        "Dollars held 0.00 all through the statement's days, so nothing in dollars was "
        "checked against the paper."
    )
    answer = statement_complete_answer(SEPTIEMBRE)
    answer["balances"][0]["warnings"] = [long_note]
    answer["not_covered"] = [
        {"currency_code": "USD", "warnings": [usd_note], "coverage_gap": None, "review_lines": []}
    ]
    fake_client.write_responses["/statements/ibk-sep/complete"] = answer

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(SEPTIEMBRE))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: screen.query_one("#rwarn", Static).display)
        await pilot.pause()
        return _screen_lines(app)

    lines = run_app(scenario, size=(80, 24))
    start = next(n for n, line in enumerate(lines) if line.startswith("  ⚠ The statement"))
    note = lines[start : start + 2]
    assert note[1].startswith("    ") and not note[1].startswith("     ")  # under `The`
    assert " ".join(" ".join(note).replace("⚠", "").split()) == long_note
    usd = next(n for n, line in enumerate(lines) if line.startswith("  ⚠ USD:"))
    pair = lines[usd : usd + 2]
    assert pair[1].startswith("    ") and not pair[1].startswith("     ")  # under `USD:`
    assert " ".join(" ".join(pair).replace("⚠", "").split()) == f"USD: {usd_note}"


@pytest.mark.parametrize("height", [24, 22, 20])
def test_a_wrapped_head_costs_the_checklist_a_row_and_nothing_overflows(
    fake_client, monkeypatch, height
):
    """The head's extra line comes out of the list's room, measured again once the head
    is drawn: on 30 lines (more than a page) no page is taller than #rlist, and the
    page status line is drawn."""
    many = [
        _line(n, f"2026-08-{1 + n % 25:02d}", f"SHOP {n}", -100 * n, "PEN", None)
        for n in range(1, 31)
    ]
    _engine(fake_client, monkeypatch, statement_lines=many)
    _long_account(monkeypatch)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(VIS_AGOSTO))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.pause()
        await pilot.pause()
        lst = screen._list
        fits = lst.outer_size.height <= screen.query_one("#rlist").content_size.height
        return (
            fits,
            lst.page_status,
            screen.query_one("#rhead").outer_size.height,
            _screen_lines(app),
        )

    fits, status, head_height, lines = run_app(scenario, size=(80, height))
    assert head_height == 5  # two lines of name, the balances' header and two currencies
    assert fits
    assert status and any(status in line for line in lines)


def test_the_flagged_line_keeps_the_page_line_and_gives_its_room_back(fake_client, monkeypatch):
    """The `⚑` line lands after the list is sized (its count is a separate read): the
    list is measured again, so on a statement with more rows than fit the page line, the
    list and the footer all show with the line; when none are flagged the list takes the
    room back."""
    many = [
        _line(n, f"2026-08-{1 + n % 25:02d}", f"SHOP {n}", -100 * n, "PEN", None)
        for n in range(1, 31)
    ]
    _engine(fake_client, monkeypatch, statement_lines=many)
    flagged = {"count": 3}
    plain_get = fake_client.get

    def get(path, *, auth=True, params=None):
        if path == "/bank-lines/count":
            return dict(flagged)
        return plain_get(path, auth=auth, params=params)

    fake_client.get = get

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(VIS_AGOSTO))
        await app.push_screen(screen)
        flag = screen.query_one("#rflag", Static)
        await wait_for(pilot, lambda: flag.display)
        rlist = screen.query_one("#rlist")
        await wait_for(
            pilot,
            lambda: (
                screen._list is not None
                and screen._list.page_status == "rows 1-12 of 30 · page 1 of 3"
                and screen._list.outer_size.height <= rlist.content_size.height
            ),
        )
        await pilot.pause()
        with_flag = (
            screen._list.outer_size.height,
            screen._list.outer_size.height <= rlist.content_size.height,
            screen._list.page_status,
            _screen_lines(app),
            screen.max_scroll_y,
        )
        flagged["count"] = 0
        screen._load_txns()
        await wait_for(pilot, lambda: not flag.display)
        await wait_for(pilot, lambda: (screen._list.page_status or "").startswith("rows 1-14"))
        return with_flag, screen._list.outer_size.height, screen._list.page_status

    (_, fits, status, lines, scroll), freed, freed_status = run_app(scenario, size=(80, 24))
    assert fits and scroll == 0
    assert status and any(status in line for line in lines)
    flag_at = next(i for i, line in enumerate(lines) if line.startswith("  ⚑ 3 lines flagged"))
    assert lines[flag_at + 1].strip() == "· f shows them"
    assert "f Flagged" in lines[-1]
    assert freed_status != status  # a page of 14 rows, not 12
    assert freed_status.startswith("rows 1-14 of 30")


def _many(account: str = "acc-visa") -> list[dict]:
    return [
        _line(n, f"2026-10-{1 + n % 25:02d}", f"SHOP {n}", -100 * n, "PEN", None, account=account)
        for n in range(1, 31)
    ]


def _count_answers(fake_client, flagged: dict) -> None:
    """The review list's count answers `flagged`, read at each call."""
    plain_get = fake_client.get

    def get(path, *, auth=True, params=None):
        if path == "/bank-lines/count":
            return dict(flagged)
        return plain_get(path, auth=auth, params=params)

    fake_client.get = get


def _page_is_whole(screen, app) -> tuple[bool, str | None]:
    """The list fits the room under the head, and its page line is on screen."""
    lst = screen._list
    fits = lst.outer_size.height <= screen.query_one("#rlist").content_size.height
    status = lst.page_status
    return fits and bool(status) and any(status in line for line in screen_lines(app)), status


def test_a_complete_that_flags_lines_keeps_the_page_line_back_from_them(fake_client, monkeypatch):
    """The count lands and opens the flagged lines' screen over the statement; back from
    it the list has the room the `⚑` line left."""
    from expense.tui.screens.reconciliations import FlaggedLinesScreen

    review = [_line(90 + n, "2026-08-01", f"REV {n}", -100, "PEN", None) for n in range(3)]
    _engine(
        fake_client, monkeypatch, statement_lines=_many(), other_lines=review, statement=VIS_AGOSTO
    )
    flagged = {"count": 0}
    _count_answers(fake_client, flagged)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(VIS_AGOSTO))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None and screen._list.page_status)
        await wait_for(pilot, lambda: _page_is_whole(screen, app)[0])
        assert _page_is_whole(screen, app)[0]  # drawn once, with no `⚑` line
        flagged["count"] = 3
        screen._open_when_counted = True
        screen._counted(3)
        await wait_for(pilot, lambda: isinstance(app.screen, FlaggedLinesScreen))
        await wait_for(pilot, lambda: any("flagged" in line for line in screen_lines(app)))
        assert any("flagged" in line for line in screen_lines(app))  # drawn
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await wait_for(pilot, lambda: _page_is_whole(screen, app)[0])
        return _page_is_whole(screen, app)

    whole, status = run_app(scenario, size=(80, 24))
    assert whole, status


def test_the_flagged_line_arriving_under_a_box_keeps_the_page_line_after_esc(
    fake_client, monkeypatch
):
    """The `⚑` line's count lands while the `c` box is open over the statement: after
    esc the list has measured itself against the line, and its page line shows."""
    from expense.tui.screens.modals import AmountPromptModal

    _engine(fake_client, monkeypatch, statement_lines=_many("acc-ibk"), statement=OCTUBRE)
    flagged = {"count": 0}
    _count_answers(fake_client, flagged)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(OCTUBRE))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None and screen._list.page_status)
        await pilot.pause()
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))
        await pilot.pause()
        flagged["count"] = 3
        screen._load_txns()
        flag = screen.query_one("#rflag", Static)
        await wait_for(pilot, lambda: flag.display)
        await pilot.pause()
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await wait_for(pilot, lambda: _page_is_whole(screen, app)[0])
        return _page_is_whole(screen, app)

    whole, status = run_app(scenario, size=(80, 24))
    assert whole, status


def last_row(status: str) -> int:
    return int(status.split("-")[1].split()[0])


def test_the_refusal_lines_cleared_under_a_box_give_the_room_back_after_esc(
    fake_client, monkeypatch
):
    """A refused complete's lines clear with the box that opens under them: after esc the
    list takes their room back, with the `⚑` line still above it."""
    from expense.tui.screens.modals import AmountPromptModal, ConfirmModal

    _engine(fake_client, monkeypatch, statement_lines=_many("acc-ibk"), statement=NOVIEMBRE_IBK)
    _count_answers(fake_client, {"count": 3})
    fake_client.errors["POST"] = money_at_start_refusal()

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(NOVIEMBRE_IBK))
        await app.push_screen(screen)
        flag = screen.query_one("#rflag", Static)
        await wait_for(pilot, lambda: flag.display and screen._list is not None)
        await wait_for(pilot, lambda: _page_is_whole(screen, app)[0])
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))
        await wait_for(pilot, lambda: screen.query_one("#rnote", Static).display)
        with_refusal = screen._list.page_status
        await pilot.press("escape")  # clears the refusal and closes the box
        await wait_for(pilot, lambda: app.screen is screen)
        await wait_for(
            pilot,
            lambda: last_row(screen._list.page_status) > last_row(with_refusal),
            message="the list never took the refusal's room back",
        )
        await wait_for(pilot, lambda: _page_is_whole(screen, app)[0])
        whole, status = _page_is_whole(screen, app)
        return whole, with_refusal, status

    whole, with_refusal, status = run_app(scenario, size=(80, 24))
    assert whole, status
    assert last_row(status) > last_row(with_refusal)


def test_a_refit_with_the_size_unchanged_sets_nothing(fake_client, monkeypatch):
    """The refit that follows every layout of the screen is a no-op when the room is the
    same, so it cannot start a layout of its own."""
    _engine(fake_client, monkeypatch, statement_lines=_many())

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(VIS_AGOSTO))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None and screen._list.page_status)
        await pilot.pause()
        calls = []
        screen._list._refresh = lambda *a, **k: calls.append(1)
        screen._refit_list()
        screen._refit_list()
        return calls

    assert run_app(scenario, size=(80, 24)) == []


def _bound(app) -> dict[str, bool]:
    """The footer's keys: each shown binding's description, whether the screen
    lets it act."""
    return {
        active.binding.description: active.enabled
        for active in app.screen.active_bindings.values()
        if active.binding.show
    }


def test_an_open_statement_on_an_account_with_a_code_waits_for_its_pdf_as_pane_9(
    fake_client, monkeypatch
):
    queries = _engine(fake_client, monkeypatch, statement_lines=NOVIEMBRE_LINES)

    async def scenario(pilot, app):
        screen, lines, visual = await _open(NOVIEMBRE, "VIS")(pilot, app)
        for key in ("space", "c", "u"):
            await pilot.press(key)
        await pilot.pause()
        return screen, lines, app.screen is screen, visual

    screen, lines, still_here, visual = run_app(scenario, size=(80, 18))
    pane = _pane(PANE_9)
    assert lines[:-1] == [*pane[:-1], *[""] * (len(lines) - len(pane))]  # then the room left
    assert lines[-1] == pane[-1]
    line = visual.parts[-1]  # the line under the balances
    assert "closes when" in line.plain and line.style == "dim"
    assert still_here  # `c` and `u` opened no question
    assert fake_client.puts == [] and fake_client.posts == []
    # no line from outside the statement is read, and none is offered
    assert not any("unreconciled" in q for q in queries)
    assert screen._list._read_only  # no tick box, no toggle


def test_the_keys_show_and_act_as_the_statements_state_allows(fake_client, monkeypatch):
    """Panes 4, 5 and 9: a completed statement has `d` and no `c` or toggle; a draft all
    three; an open statement waiting for its PDF has neither `c` nor a toggle, nor `u`."""
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)

    def keys(statement, code):
        async def scenario(pilot, app):
            screen = ReconciliationDetailScreen(dict(statement), statement_code=code)
            await app.push_screen(screen)
            await wait_for(pilot, lambda: screen._list is not None)
            await pilot.pause()
            return _bound(app)

        return scenario

    completed = run_app(keys(VIS_AGOSTO, "VIS"), size=(80, 24))
    draft = run_app(keys(OCTUBRE, None), size=(80, 24))
    waiting = run_app(keys(NOVIEMBRE, "VIS"), size=(80, 24))
    assert "Complete" not in completed and "Toggle" not in completed
    assert "Delete" in completed and "Revert" in completed
    assert {"Toggle", "Complete", "Revert", "Delete"} <= set(draft)
    assert not {"Complete", "Toggle", "Revert"} & set(waiting) and "Delete" in waiting


def test_the_page_keys_reach_every_page_of_a_completed_statement(fake_client, monkeypatch):
    """The list holds focus on a completed statement as on a draft, so `pgdn` and `pgup`
    page it: the opening balances at the end of Agosto sit on a later page at this height."""
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)

    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(VIS_AGOSTO))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.pause()
        lst = screen._list
        first = lst._window()[1][0].key
        assert lst.page_status.endswith("page 1 of 2")
        await pilot.press("pagedown")
        await pilot.pause()
        second = lst._window()[1][0].key
        assert lst.page_status.endswith("page 2 of 2") and second != first
        assert "Next" in _bound(app) or "Prev" in _bound(app)
        await pilot.press("pageup")
        await pilot.pause()
        return first, lst._window()[1][0].key

    first, back = run_app(scenario, size=(80, 19))
    assert back == first


def test_c_and_space_do_nothing_on_a_completed_statement(fake_client, monkeypatch):
    """`check_action` is the only stop: no question, no box, no write."""
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)

    async def scenario(pilot, app):
        screen, _, _ = await _open(VIS_AGOSTO, "VIS")(pilot, app)
        before = screen._list.checked
        await pilot.press("c")
        await pilot.press("space")
        await pilot.pause()
        return screen, app.screen is screen, before == screen._list.checked

    screen, still_here, same = run_app(scenario, size=(80, 24))
    assert still_here and same and not screen._busy
    assert fake_client.puts == [] and fake_client.posts == []
