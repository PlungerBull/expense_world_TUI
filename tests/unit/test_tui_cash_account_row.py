"""A cash account on Manage ▸ Accounts: its row and its Edit form.

An account of `kind: "cash"` reads `cash` in the Type column, has no `t`, and
keeps `a`, `d`, `e`, `c` and `x`; its Edit form holds `type`, `name` and `currencies` read-only,
then `color` and the openings, and saves only what changed
(contract: PUT /v1/accounts/{account_id}). The engine's refusals of the fields it takes
none of read in its own words.
"""

import httpx
import respx

from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.create_forms import EditAccountScreen
from expense.tui.screens.help import listed_bindings
from expense.tui.screens.modals import ConfirmModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_CURRENCIES,
    ENGINE_URL,
    account_with_currencies,
    held_currency,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

SIZE = (120, 40)
CASH = account_with_currencies(
    id="a-cash",
    name="CASH-0001",
    kind="cash",
    bank_code=None,
    numbers=[],
    color="#4a90d9",
    currencies=[held_currency("PEN", 23750), held_currency("USD", 3000)],
)
BANK = account_with_currencies(id="a-bank", name="BCP-5678", currencies=[held_currency("PEN", 0)])
PERSON = account_with_currencies(
    id="a-eli", name="Eliana", kind="person", currencies=[held_currency("PEN", 0)]
)
ROWS = [BANK, CASH, PERSON]


def _footer(screen) -> list[str]:
    return [a.binding.key for a in screen.active_bindings.values() if a.binding.show and a.enabled]


async def _open(pilot, app, monkeypatch, cursor: str) -> AccountsScreen:
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(list(ROWS)))
    screen = AccountsScreen()
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    listing = screen.query_one(CursorList)
    listing.set_cursor(listing.index_of(cursor))
    screen.refresh_bindings()
    await pilot.pause()
    return screen


def test_t_leaves_the_footer_on_the_cash_row_and_d_stays(configured, monkeypatch):
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, monkeypatch, "a-cash")
        seen["cash"] = _footer(screen)
        seen["actions"] = {
            a: screen.check_action(a, ())
            for a in ("make_person", "make_bank", "delete", "archive", "edit")
        }
        seen["cash_card"] = [b.key for b in listed_bindings(screen)]

    run_app(scenario, size=SIZE)
    assert "t" not in seen["cash"] and {"a", "e", "n", "d"} <= set(seen["cash"])
    assert seen["actions"] == dict(
        make_person=False, make_bank=False, delete=True, archive=True, edit=True
    )
    assert "d" in seen["cash_card"] and "t" in seen["cash_card"]


def test_pressing_t_on_the_cash_row_sends_nothing(configured, monkeypatch):
    async def scenario(pilot, app):
        screen = await _open(pilot, app, monkeypatch, "a-cash")
        await pilot.press("t")
        await pilot.pause()
        assert app.screen is screen

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.route().mock(return_value=httpx.Response(500))
        run_app(scenario, size=SIZE)
    assert [c.request.method for c in sent.calls if c.request.method != "GET"] == []


def test_d_on_a_cash_row_asks_then_sends_one_delete_and_the_list_starts_over(
    configured, monkeypatch
):
    rows = list(ROWS)

    def engine_deletes(request):
        rows[:] = [r for r in rows if r["id"] != "a-cash"]
        return httpx.Response(200, json={})

    async def scenario(pilot, app):
        screen = await _open(pilot, app, monkeypatch, "a-cash")
        monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(list(rows)))
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == "Delete this account?"
        assert app.screen._message.startswith("CASH-0001 · cash")
        await pilot.press("y")
        await wait_for(pilot, lambda: "a-cash" not in screen._by_id)
        assert screen.query_one(CursorList).cursor_index == 0

    with respx.mock() as engine:
        route = engine.delete(f"{ENGINE_URL}/v1/accounts/a-cash").mock(side_effect=engine_deletes)
        run_app(scenario, size=SIZE)
    assert route.call_count == 1


# ---- the Edit form -------------------------------------------------------------------


def _summary(screen) -> list[str]:
    text = render_text(screen._summary_renderable(), width=100)
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _form(record, body):
    async def scenario(pilot, app):
        screen = EditAccountScreen(record, ENGINE_CURRENCIES, ["BCP"])
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        await wait_for(pilot, lambda: not screen._openings_loading)
        return await body(pilot, app, screen)

    return run_app(scenario)


def test_the_cash_edit_form_holds_type_name_and_currencies_read_only():
    async def body(pilot, app, screen):
        summary = _summary(screen)
        assert summary[:3] == [
            "type cash read-only",
            "name CASH-0001 read-only",
            "currencies PEN · USD read-only",
        ]
        assert summary[3].startswith("color")
        for gone in ("bank", "last 4", "statement", "since", "new card", "cards before"):
            assert not any(line.startswith(gone) for line in summary)
        assert [k for k in screen._sequence() if k not in ("type", "name", "currencies")][0] == (
            "color"
        )
        assert len(screen._sequence()) == 3 + 1 + 4  # + color + two lines for each currency

    _form(CASH, body)


def test_a_saved_color_is_one_put_with_that_body_alone(fake_client):
    async def body(pilot, app, screen):
        screen._values["color"] = "#e5484d"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(CASH, body)
    assert fake_client.requests == [("PUT", "/accounts/a-cash")]
    assert fake_client.puts[0][1] == {"color": "#e5484d"}
