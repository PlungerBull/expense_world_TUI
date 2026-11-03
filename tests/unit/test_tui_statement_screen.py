"""A statement's screen: its head and its one list, panes 4 and 5 of
docs/mockups/expense-world-statements-screens.html at 80 columns.

The head shows each covered currency's begin, end and diff once; the list is the
paper's order, both currencies mixed and numbered 1, 2, 3 … with no gaps, a `Cur`
column, the opening balance apart; the lines are read by account, every currency
together, in the engine's order (contract: GET /v1/bank-lines, "Ordering")."""

import re

import pytest
from textual.widgets import Static

from expense.tui.screens.reconciliations import ReconciliationDetailScreen
from expense.tui.widgets.checklist import CheckList
from tests.unit.helpers import (
    bank_line_row,
    cursor_page,
    import_part,
    render_text,
    run_app,
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


def _engine(fake_client, monkeypatch, *, statement_lines, other_lines=()):
    """The fake engine's bank lines: the statement's read (`statement_id`) answers
    `statement_lines`, the read of the account's lines in no statement `other_lines`.
    Returns the list of every `GET /bank-lines` query."""
    queries: list[dict] = []

    def get(path, *, auth=True, params=None):
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
    """The screen as drawn, a line each, trailing blanks off. The app's own chrome is
    left out: the blank row above the crumb and the one under it, which the mockups
    do not draw. An income is written without the plus the mockups draw, as every
    list of the app writes it (`+800.00` reads ` 800.00`)."""
    lines = [strip.text.rstrip() for strip in app.screen._compositor.render_strips()]
    while lines and not lines[-1]:
        lines.pop()
    assert lines[0] == "" and lines[2] == "", lines[:3]
    return [line for n, line in enumerate(lines) if n not in (0, 2)]


def _pane(text: str) -> list[str]:
    """A pane's lines as the mockup draws them, trailing blanks off, the incomes'
    plus written as a blank."""
    return [re.sub(r"\+(\d)", r" \1", line.rstrip()) for line in text.strip("\n").splitlines()]


def _open(statement: dict):
    async def scenario(pilot, app):
        screen = ReconciliationDetailScreen(dict(statement))
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.pause()
        return screen, _screen_lines(app), screen.query_one("#rhead", Static).visual

    return scenario


def test_a_completed_statement_reads_as_pane_4_at_80_columns(fake_client, monkeypatch):
    _engine(fake_client, monkeypatch, statement_lines=AGOSTO)
    _, lines, _ = run_app(_open(VIS_AGOSTO), size=(80, 26))
    # the footer is the footer rules' task: a completed statement offers no `c`
    assert lines[:-1] == _pane(PANE_4)[:-1]


def test_a_draft_reads_as_pane_5_at_80_columns(fake_client, monkeypatch):
    _engine(fake_client, monkeypatch, statement_lines=OCTUBRE_IN, other_lines=OCTUBRE_OUT)
    _, lines, _ = run_app(_open(OCTUBRE), size=(80, 18))
    assert lines == _pane(PANE_5)


def test_lines_are_read_by_account_every_currency_together_in_the_engines_order(
    fake_client, monkeypatch
):
    """The statement's lines: its id and its account, in the statement's order, no
    currency; the draft's offer: the account's lines in no statement inside the
    days, oldest first. No sort is made here, and no request names a holder
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
    assert not any("currency_code" in q or "holder_id" in q for q in queries)


def test_the_rows_keep_the_order_the_engine_gave_them(fake_client, monkeypatch):
    """Nothing sorts client-side: lines listed against their dates stay where the
    engine put them, and the numbers follow the rows."""
    odd = [AGOSTO[4], AGOSTO[0], AGOSTO[2]]
    _engine(fake_client, monkeypatch, statement_lines=odd)
    screen, _, _ = run_app(_open(VIS_AGOSTO), size=(80, 26))
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
    _, _, visual = run_app(_open(soles), size=(80, 26))
    head = str(visual)
    assert [line.split()[0] for line in head.splitlines()[2:]] == ["PEN"]
    assert "USD" not in head


def test_a_statement_covering_nothing_has_no_balances_table(fake_client, monkeypatch):
    bare = statement_record({**VIS_AGOSTO, "balances": []})
    _engine(fake_client, monkeypatch, statement_lines=[])
    _, _, visual = run_app(_open(bare), size=(80, 26))
    head = str(visual)
    assert head.splitlines() == [
        "  [VIS] Agosto  ·  Visa BCP  ·  2026-07-26 → 2026-08-25  ·  status completed"
    ]


def test_a_blank_balance_is_a_dim_dash_and_its_difference_stays_blank(fake_client, monkeypatch):
    """Question 3 B: a balance not entered is a dim `—`, never zero
    (contract: "Statements", "A balance not entered is `null`, never zero")."""
    _engine(fake_client, monkeypatch, statement_lines=OCTUBRE_IN, other_lines=OCTUBRE_OUT)
    _, _, head = run_app(_open(OCTUBRE), size=(80, 18))
    text = str(head)
    usd = next(line for line in text.splitlines() if line.split()[:1] == ["USD"])
    assert usd.split() == ["USD", "—", "—"]  # no figure, and no difference
    start = text.index(usd)
    dashes = [
        span.style
        for span in head.spans
        if start <= span.start < start + len(usd) and "—" in text[span.start : span.end]
    ]
    assert len(dashes) == 2 and all(style.dim for style in dashes)


@pytest.mark.parametrize("height", [30, 24, 23, 19])
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
    assert (statuses == [None]) == (height >= 26)


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
