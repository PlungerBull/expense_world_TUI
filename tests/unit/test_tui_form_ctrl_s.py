"""`^s` on a bar form keeps what is typed in the bar, as `⏎` would, then saves."""

from textual.widgets import Input

from expense.tui.screens.create_forms import (
    EditAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from expense.tui.screens.statements import NewStatementScreen
from tests.unit.helpers import ENGINE_CURRENCIES, account_with_currencies, run_app, wait_for, whole


def _type(screen, text):
    """Type into the bar without `⏎`."""
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)


def _enter(screen, text):
    _type(screen, text)
    screen.on_input_submitted(None)


async def _open(pilot, app, screen):
    await app.push_screen(screen)
    await wait_for(pilot, lambda: bool(screen.query("#bar")))


def _statement():
    return NewStatementScreen(account_id="acc1", account_name="BCP", currencies=("PEN",))


def _notes(monkeypatch, cls):
    notes: list[str] = []
    monkeypatch.setattr(cls, "notify", lambda self, message, **kw: notes.append(message))
    return notes


def test_ctrl_s_keeps_a_single_line_form_s_typed_name(fake_client):
    async def scenario(pilot, app):
        screen = NewHashtagScreen()
        await _open(pilot, app, screen)
        _type(screen, "#groceries")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(path, body)] = fake_client.posts
    assert path == "/hashtags" and body["name"] == "groceries"


def test_ctrl_s_keeps_a_create_form_s_typed_line(fake_client):
    async def scenario(pilot, app):
        screen = NewCategoryScreen()
        await _open(pilot, app, screen)
        _enter(screen, "Mascotas")
        assert screen._key == "color"
        _type(screen, "green")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(_path, body)] = fake_client.posts
    assert body["name"] == "Mascotas" and body["color"] == "#5ab87a"


def test_ctrl_s_keeps_an_edit_form_s_typed_name(fake_client):
    async def scenario(pilot, app):
        screen = EditAccountScreen(
            account_with_currencies(id="abc", name="Sueldo"), ENGINE_CURRENCIES
        )
        await _open(pilot, app, screen)
        assert screen._key == "name"
        _type(screen, "Salario")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    [(path, body)] = fake_client.puts
    assert path == "/accounts/abc" and body["name"] == "Salario"


def test_ctrl_s_on_an_untouched_line_changes_nothing(fake_client):
    """Nothing typed since landing on the line: its value stays as it was."""

    async def scenario(pilot, app):
        screen = NewCategoryScreen()
        await _open(pilot, app, screen)
        _enter(screen, "Mascotas")
        screen.action_field(-1)
        assert screen._key == "name"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(_path, body)] = fake_client.posts
    assert body["name"] == "Mascotas" and "color" not in body


def test_ctrl_s_on_the_new_statement_form_sends_the_balance_typed_in_the_bar(fake_client):
    async def scenario(pilot, app):
        screen = _statement()
        await _open(pilot, app, screen)
        _enter(screen, "April 2026")
        _enter(screen, "2026-04-01")
        _enter(screen, "2026-04-30")
        assert screen._key == "begin:PEN"
        _type(screen, "9580.00")  # never entered
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(path, body)] = fake_client.posts
    assert path == "/statements"
    assert body["balances"] == [{"currency_code": "PEN", "beginning_balance_cents": 958000}]


def test_ctrl_s_with_a_value_enter_would_refuse_sends_nothing_and_stays(fake_client, monkeypatch):
    notes = _notes(monkeypatch, NewStatementScreen)

    async def scenario(pilot, app):
        screen = _statement()
        await _open(pilot, app, screen)
        _enter(screen, "April 2026")
        _enter(screen, "2026-04-01")
        _enter(screen, "2026-04-30")
        _type(screen, "9.580,00")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert screen._key == "begin:PEN" and "begin:PEN" not in screen._values
        assert screen.query_one("#bar", Input).value == "9.580,00"
        screen.on_input_submitted(None)  # `⏎` on the same text gives the same note
        assert len(notes) == 2 and notes[0] == notes[1]

    run_app(scenario)
    assert not fake_client.posts


def test_ctrl_s_with_a_required_line_emptied_stops_as_enter_stops(fake_client, monkeypatch):
    notes = _notes(monkeypatch, NewStatementScreen)

    async def scenario(pilot, app):
        screen = _statement()
        await _open(pilot, app, screen)
        _enter(screen, "April 2026")
        screen.action_field(-1)
        assert screen._key == "name"
        _type(screen, "")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert screen._key == "name" and notes == ["Name is required."]

    run_app(scenario)
    assert not fake_client.posts


def test_ctrl_s_on_a_read_only_line_keeps_nothing_and_saves_as_before(fake_client):
    async def scenario(pilot, app):
        screen = EditAccountScreen(
            account_with_currencies(id="abc", name="Sueldo"), ENGINE_CURRENCIES
        )
        await _open(pilot, app, screen)
        screen._locked.add("name")
        screen.query_one("#bar", Input).value = "Salario"  # set past the bar's own lock
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    [(_path, body)] = fake_client.puts
    assert body["name"] == "Sueldo"


def test_ctrl_s_on_an_untouched_pick_line_picks_nothing(fake_client, monkeypatch):
    """`⏎` on an empty ACCOUNT bar would pick the first account listed; `^s`
    on a line nobody typed on changes nothing and the required line stops the save."""
    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        lambda *a, **k: whole([account_with_currencies(id="acc1", name="BCP")]),
    )
    notes = _notes(monkeypatch, NewStatementScreen)

    async def scenario(pilot, app):
        screen = NewStatementScreen()
        await _open(pilot, app, screen)
        await wait_for(pilot, lambda: screen._accounts)
        _enter(screen, "April 2026")
        assert screen._key == "account"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "account" not in screen._values and screen._key == "account"
        assert notes == ["Account is required."]

    run_app(scenario)
    assert not fake_client.posts
