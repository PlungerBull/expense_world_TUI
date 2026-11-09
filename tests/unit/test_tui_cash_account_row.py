"""The cash account on Manage ▸ Accounts: its row and its Edit form.

An account of `kind: "cash"` reads `cash` in the Type column, has no `t` and no `d`, and
keeps `a`, `e`, `c` and `x`; its Edit form holds `type`, `name` and `currencies` read-only,
then `color` and the openings, and saves only what changed
(contract: PUT /v1/accounts/{account_id}). The engine's refusals of the fields it takes
none of, and of its delete, read in its own words.
"""

import httpx
import respx

from expense.errors import EngineError
from expense.tui.screens._base import ResourceListScreen
from expense.tui.screens.accounts import AccountsScreen, account_line, account_rows
from expense.tui.screens.create_forms import EditAccountScreen
from expense.tui.screens.help import listed_bindings
from expense.tui.screens.modals import ConfirmModal, QuestionLine, QuestionModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_CURRENCIES,
    ENGINE_URL,
    account_with_currencies,
    error_response,
    held_currency,
    refusal_block,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)

SIZE = (120, 40)
CASH = account_with_currencies(
    id="a-cash",
    name="Efectivo Casa",
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


def test_the_type_column_reads_cash_and_bank_and_person_are_unchanged():
    kinds = [cells[1] for _, cells, *_ in account_rows(ROWS, ["PEN", "USD"])]
    assert kinds == ["bank", "cash", "person"]
    assert " · cash · " in account_line(CASH)


def test_t_and_d_leave_the_footer_on_the_cash_row_the_other_keys_stay(configured, monkeypatch):
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, monkeypatch, "a-cash")
        seen["cash"] = _footer(screen)
        seen["actions"] = {
            a: screen.check_action(a, ())
            for a in ("make_person", "make_bank", "delete", "archive", "edit")
        }
        listing = screen.query_one(CursorList)
        listing.set_cursor(listing.index_of("a-bank"))
        screen.refresh_bindings()
        seen["bank"] = _footer(screen)
        seen["bank_card"] = [b.key for b in listed_bindings(screen)]
        listing.set_cursor(listing.index_of("a-cash"))
        screen.refresh_bindings()
        seen["cash_card"] = [b.key for b in listed_bindings(screen)]

    run_app(scenario, size=SIZE)
    assert "t" not in seen["cash"] and "d" not in seen["cash"]
    assert {"a", "e", "n"} <= set(seen["cash"])
    assert seen["actions"] == dict(
        make_person=False, make_bank=False, delete=False, archive=True, edit=True
    )
    assert "t" in seen["bank"] and "d" in seen["bank"]
    assert "d" not in seen["cash_card"] and "d" in seen["bank_card"]
    assert "t" in seen["cash_card"]  # the card lists `t` on every row


def test_pressing_t_or_d_on_the_cash_row_sends_nothing(configured, monkeypatch):
    async def scenario(pilot, app):
        screen = await _open(pilot, app, monkeypatch, "a-cash")
        await pilot.press("t")
        await pilot.press("d")
        await pilot.pause()
        assert app.screen is screen  # no question opened

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.route().mock(return_value=httpx.Response(500))
        run_app(scenario, size=SIZE)
    assert [c.request.method for c in sent.calls if c.request.method != "GET"] == []


def test_a_delete_sent_anyway_shows_the_engines_words(configured, monkeypatch):
    """The shared delete path, reached past the cash row's guard: CASH_NOT_DELETABLE reads
    in the engine's words."""
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, monkeypatch, "a-cash")
        notes: list = []
        monkeypatch.setattr(
            screen, "notify", lambda message, title="", **kw: notes.append((title, str(message)))
        )
        ResourceListScreen.action_delete(screen)
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notes)
        seen["notes"] = notes

    with respx.mock() as engine:
        engine.delete(f"{ENGINE_URL}/v1/accounts/a-cash").mock(
            error_response(
                409,
                "CONFLICT",
                "The cash account is never deleted.",
                {"account_id": "words"},
                {"account_id": "CASH_NOT_DELETABLE"},
            )
        )
        run_app(scenario, size=SIZE)
    assert seen["notes"][0][0] == "Failed"
    assert "The cash account is never deleted." in seen["notes"][0][1]


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
            "name Efectivo Casa read-only",
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


def test_nothing_changed_sends_an_empty_body_and_a_change_only_the_color(fake_client):
    async def body(pilot, app, screen):
        assert screen._payload() == {}
        screen._values["color"] = "#e5484d"
        assert screen._payload() == {"color": "#e5484d"}

    _form(CASH, body)


def test_a_saved_color_is_one_put_with_that_body_alone(fake_client):
    async def body(pilot, app, screen):
        screen._values["color"] = "#e5484d"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen.is_attached)

    _form(CASH, body)
    assert fake_client.requests == [("PUT", "/accounts/a-cash")]
    assert fake_client.puts[0][1] == {"color": "#e5484d"}


def _refusal(key: str, code: str, status: int) -> EngineError:
    name = "CONFLICT" if status == 409 else "VALIDATION_ERROR"
    words = {key: "The engine's words."}
    return EngineError(name, "Validation failed.", words, status, {}, {key: code})


def test_a_cash_takes_no_field_refusal_on_save_shows_the_engines_words(fake_client):
    fake_client.errors["PUT"] = _refusal("name", "CASH_TAKES_NO_FIELD", 422)

    async def body(pilot, app, screen):
        before = dict(screen._values)
        screen._values["color"] = "#e5484d"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: refusal_block(screen) is not None)
        assert "The engine's words." in refusal_block(screen)
        assert screen._values == {**before, "color": "#e5484d"}
        assert screen.is_attached

    _form(CASH, body)


def test_a_turn_sent_anyway_shows_the_engines_words(configured, monkeypatch):
    """`t` is refused before it is sent; reached past that guard, CASH_KIND_FIXED (keyed
    `account_id`) reads in the engine's words in the list's Failed note."""
    seen: dict = {}

    async def scenario(pilot, app):
        screen = await _open(pilot, app, monkeypatch, "a-cash")
        notes: list = []
        monkeypatch.setattr(
            screen, "notify", lambda message, title="", **kw: notes.append((title, str(message)))
        )
        screen._ask_to_turn(
            "make-person",
            "a person",
            (QuestionLine("name", "name"),),
            lambda values: {"name": values["name"]},
            "Now a person.",
            "Not made a person",
        )
        await wait_for(pilot, lambda: isinstance(app.screen, QuestionModal))
        app.screen.query_one("#line-name").value = "Mamá"
        await pilot.press("enter")
        await wait_for(pilot, lambda: notes)
        seen["notes"] = notes

    with respx.mock() as engine:
        engine.post(f"{ENGINE_URL}/v1/accounts/a-cash/make-person").mock(
            error_response(
                409,
                "CONFLICT",
                "The cash account keeps its kind.",
                {"account_id": "words"},
                {"account_id": "CASH_KIND_FIXED"},
            )
        )
        run_app(scenario, size=SIZE)
    assert seen["notes"][0][0] == "Failed"
    assert "The cash account keeps its kind." in seen["notes"][0][1]
