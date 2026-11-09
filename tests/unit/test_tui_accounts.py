"""Smoke tests for the Accounts TUI screen + CursorList enhancements."""

from rich.text import Text

from expense.errors import EngineError
from expense.tui.screens.accounts import AccountsScreen, account_headers, account_rows
from expense.tui.screens.create_forms import EditAccountScreen
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_CURRENCIES,
    ENGINE_ORDER_HOLDING_ACCOUNTS,
    account_with_currencies,
    held_currency,
    in_order,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

ITEMS = [
    account_with_currencies(
        id="a1",
        name="BCP Soles",
        color="#4a90d9",
        currencies=[held_currency("PEN", 1245000)],
    ),
    account_with_currencies(
        id="a2",
        name="Socio Juan",
        kind="person",
        color=None,
        currencies=[held_currency("PEN", -150000)],
    ),
    account_with_currencies(
        id="a3",
        name="Old BCP",
        is_archived=True,
        color="#888888",
        currencies=[held_currency("PEN", 0)],
    ),
]
#: The Visa and ALEJO, each in soles and dollars.
VISA = account_with_currencies(
    id="visa",
    name="Visa",
    statement_code="VIN",
    color="#4a90d9",
    currencies=[held_currency("PEN", -234050), held_currency("USD", -18520)],
)
ALEJO = account_with_currencies(
    id="alejo",
    name="ALEJO",
    kind="person",
    color=None,
    currencies=[held_currency("PEN", -15000), held_currency("USD", 4000)],
)

COLUMNS = ["Name", "Type", "Code", "Color", "PEN", "USD", "Status"]


def _dash(cell) -> bool:
    return isinstance(cell, Text) and cell.plain == "—" and cell.style == "dim"


def test_the_columns_are_name_type_code_color_a_column_per_currency_and_status():
    """A balance column per currency the engine lists, in its order; no Cur column,
    no single Balance column."""
    assert account_headers(ENGINE_CURRENCIES) == COLUMNS


def test_the_screen_takes_its_columns_from_the_engines_currencies(monkeypatch):
    """A third currency in the engine's list is a third balance column, right-aligned,
    in the engine's order, a dim `—` under it for an account not holding it."""
    monkeypatch.setattr(
        "expense.reads.fetch_currency_codes", lambda cfg, **kw: ["EUR", "PEN", "USD"]
    )
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([VISA]))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        assert screen.HEADERS == ["Name", "Type", "Code", "Color", "EUR", "PEN", "USD", "Status"]
        assert screen.ALIGN_RIGHT == {4, 5, 6}
        [(_key, cells, _style)] = screen.rows([VISA])
        assert _dash(cells[4])
        assert [c.plain if isinstance(c, Text) else c for c in cells[5:]] == [
            "-2,340.50",
            "-185.20",
            "active",
        ]

    run_app(scenario)


def test_a_refused_currencies_read_shows_the_engines_words_in_the_banner(monkeypatch):
    """The currencies are read in the list's worker: a refusal is the "Could not load."
    banner in the engine's words, as a refused accounts read is."""
    from textual.widgets import Static

    def refused(cfg, **kw):
        raise EngineError("UNAUTHORIZED", "Invalid or revoked token.", None, 401, {})

    monkeypatch.setattr("expense.reads.fetch_currency_codes", refused)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole([VISA]))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for(pilot, lambda: app.screen.query(".error"))
        banner = render_text(app.screen.query_one(".error", Static).content, width=100)
        assert "Could not load." in banner and "Invalid or revoked token." in banner

    run_app(scenario)


def test_account_rows_type_balance_status_and_swatch():
    by_id = {r[0]: r for r in account_rows(ITEMS, ENGINE_CURRENCIES)}
    # bank, formatted balance, active status, colored swatch Text
    _key, cells, style = by_id["a1"]
    assert cells[0] == "BCP Soles"
    assert cells[1] == "bank" and cells[4] == "12,450.00" and cells[6] == "active"
    assert isinstance(cells[3], Text) and cells[3].style == "#4a90d9"
    assert style == ""
    # person row
    assert by_id["a2"][1][1] == "person"
    # archived → dim base style + status archived
    _k, cells3, style3 = by_id["a3"]
    assert cells3[6] == "archived" and style3 == "dim"


def test_a_two_currency_account_is_one_row_each_balance_in_its_column():
    """The Visa and ALEJO in soles and dollars: one row each, keyed by the account's
    id, each balance under its currency and none summed."""
    rows = account_rows([VISA, ALEJO], ENGINE_CURRENCIES)
    assert [r[0] for r in rows] == ["visa", "alejo"]
    visa, alejo = rows[0][1], rows[1][1]
    assert visa[:3] == ["Visa", "bank", "VIN"]
    assert visa[4:] == ["-2,340.50", "-185.20", "active"]
    assert alejo[:2] == ["ALEJO", "person"] and _dash(alejo[2])
    assert alejo[4:] == ["-150.00", "40.00", "active"]


def test_a_currency_the_account_does_not_hold_is_a_dim_dash():
    """A soles-only account: its balance under PEN, a dim `—` under USD."""
    soles_only = ITEMS[1]
    rows = {r[0]: r[1] for r in account_rows([ITEMS[0], soles_only], ENGINE_CURRENCIES)}
    assert rows["a1"][4] == "12,450.00" and _dash(rows["a1"][5])


def test_an_archived_account_is_one_row_dimmed_whole():
    old = account_with_currencies(VISA, id="old", name="Ahorro Viejo", is_archived=True)
    rows = account_rows([VISA, old], ENGINE_CURRENCIES)
    assert [(r[0], r[2]) for r in rows] == [("visa", ""), ("old", "dim")]
    assert rows[1][1][6] == "archived"


def test_the_code_column_shows_the_statement_code_or_a_dim_dash():
    """The account's statement code, or a dim `—` when it
    has none (a person always)."""
    items = [account_with_currencies(ITEMS[0], statement_code="SIG"), ITEMS[1]]
    by_id = {r[0]: r[1] for r in account_rows(items, ENGINE_CURRENCIES)}
    assert by_id["a1"][2] == "SIG"
    assert _dash(by_id["a2"][2])


def test_the_list_reads_at_its_card_width(monkeypatch):
    """The list at its card width: one line per account, no `<account> · <code>`
    line, each balance under its currency's header and a dim `—` under USD for a
    soles-only account."""
    import expense.reads as ac

    items = [VISA, ALEJO, account_with_currencies(ITEMS[0], statement_code="SIG")]
    monkeypatch.setattr(ac, "fetch_accounts", lambda *a, **k: whole(items))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        cl = app.screen.query(CursorList).first()
        lines = render_text(cl._build(), width=AccountsScreen.CARD_WIDTH - 2).splitlines()
        header = next(line for line in lines if "Name" in line)
        assert header.split() == COLUMNS
        assert not any(" · " in line for line in lines)
        pen_end = header.index("PEN") + 3
        usd_end = header.index("USD") + 3
        rows = {
            line.split()[0]: line
            for line in lines
            if line.split()[:1] in (["Visa"], ["ALEJO"], ["BCP"])
        }
        assert rows["Visa"][:pen_end].endswith("-2,340.50")
        assert rows["Visa"][:usd_end].endswith("-185.20")
        assert rows["ALEJO"][:pen_end].endswith("-150.00")
        assert rows["ALEJO"][:usd_end].endswith("40.00")
        assert rows["BCP"][:pen_end].endswith("12,450.00")
        assert rows["BCP"][:usd_end].endswith("—")
        assert rows["BCP"].split()[3] == "SIG"  # BCP Soles, bank, then Code

    run_app(scenario)


def test_accounts_screen_lists_and_edits(monkeypatch):
    import expense.reads as ac

    monkeypatch.setattr(ac, "fetch_accounts", lambda *a, **k: whole(ITEMS))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        cl = app.screen.query(CursorList).first()
        assert cl is not None
        await pilot.press("e")  # edit the cursor row — no detail hop
        await wait_for(pilot, lambda: isinstance(app.screen, EditAccountScreen))

    run_app(scenario)


def test_accounts_screen_shows_the_engines_order(monkeypatch):
    """Rows stand exactly as `GET /accounts?include_people=true` lists them —
    not alphabetical, not by `sort_order`, the person after every bank."""
    import expense.reads as ac

    monkeypatch.setattr(ac, "fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_HOLDING_ACCOUNTS))
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())

    async def scenario(pilot, app):
        await app.push_screen(AccountsScreen())
        await wait_for_list(pilot, app)
        cl = app.screen.query(CursorList).first()
        assert [row.key for row in cl._rows] == [a["id"] for a in ENGINE_ORDER_HOLDING_ACCOUNTS]
        shown = render_text(cl._build(), width=120)
        assert in_order(shown, [a["name"] for a in ENGINE_ORDER_HOLDING_ACCOUNTS])

    run_app(scenario)
