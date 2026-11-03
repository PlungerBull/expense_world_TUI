"""`c` on a draft asks for every balance it needs: pane 6 of
docs/mockups/expense-world-statements-screens.html at 80 columns.

A box for each blank balance, currency by currency, the starting balance first; one
`PUT /statements/{id}` naming only the currencies that change (contract: PUT
/v1/statements/{statement_id}, "`balances`"); then the usual question. A refused
complete that names a missing balance, or money at the start of a currency the
statement does not cover, leads to the same boxes for the currency the engine names
(contract: POST /v1/statements/{statement_id}/complete, "Every balance must be entered")
(contract: POST /v1/statements/{statement_id}/complete,
"Every currency with money at the start has balances in it")."""

import pytest
from textual.widgets import Input, Static

from expense.errors import EngineError
from expense.tui.screens.modals import AmountPromptModal, ConfirmModal
from expense.tui.screens.reconciliations import (
    ReconciliationDetailScreen,
    balances_body,
    balances_named,
    blank_balances,
)
from tests.unit.helpers import (
    cursor_page,
    run_app,
    screen_lines,
    shown,
    statement_complete_answer,
    statement_put_answer,
    statement_record,
    stub_home_month,
    wait_for,
)

pytestmark = pytest.mark.usefixtures("no_flagged_lines")

PATH = "/statements/ibk"
COMPLETE = "/statements/ibk/complete"
SAVED_WORDS = "The balances are saved. The statement is not completed:"


def _balance(currency: str, begin, end, diff=None) -> dict:
    return {
        "currency_code": currency,
        "beginning_balance_cents": begin,
        "ending_balance_cents": end,
        "difference_cents": diff,
    }


def _ibk(*balances: dict, name: str = "Octubre 2026") -> dict:
    return statement_record(
        {
            "id": "ibk",
            "account_id": "acc-ibk",
            "name": name,
            "date_start": "2026-09-26",
            "date_end": "2026-10-25",
            "status": 1,
            "balances": list(balances),
        }
    )


#: Octubre: soles entered, dollars added blank by a dollar line ticked in.
OCTUBRE = _ibk(_balance("PEN", -82000, -34860), _balance("USD", None, None))
#: Noviembre: soles alone; the dollars hold money at its start.
NOVIEMBRE = _ibk(_balance("PEN", -34860, -51290), name="Noviembre 2026")


def _engine(fake_client, monkeypatch, fresh: dict | None = None) -> None:
    """A fake engine with no bank lines, the account named IBK Visa; a read of the
    statement answers `fresh` when given."""
    fake_client.get = lambda path, *, auth=True, params=None: cursor_page([])
    stub_home_month(monkeypatch)
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map",
        lambda: {"acc-ibk": "IBK Visa"},
    )
    if fresh is not None:
        monkeypatch.setattr("expense.reads.fetch_statement", lambda cfg, *a, **k: dict(fresh))


def _notes(monkeypatch) -> list:
    notices: list = []

    def note(self, message, title="", severity="information", **kw):
        notices.append((title, message, severity))

    monkeypatch.setattr(ReconciliationDetailScreen, "notify", note)
    monkeypatch.setattr("expense.tui.screens.modals.AmountPromptModal.notify", note)
    return notices


def _lines(app) -> list[str]:
    """The box on screen as drawn at 80 columns, a line each from its title to its
    keys, cropped at the title's column and its blank rows left out (the line the
    figure is typed on is blank until something is typed). Empty when no box is up."""
    rows = screen_lines(app)
    for top, row in enumerate(rows):
        column = max(row.find("Starting balance first"), row.find("Ending balance first"))
        if column < 0:
            continue
        lines = []
        for below in rows[top:]:
            lines.append(below[column:].strip())
            if lines[-1].startswith("[enter]"):
                return [line for line in lines if line]
    return []


def _box(title: str, what: str, currency: str, typed: str) -> list[str]:
    return [
        title,
        f"The statement's {what} figure for IBK Visa,",
        f"in {currency} · signed · e.g. 13,853.20",
        *([typed] if typed else []),
        "[enter] save    [esc] cancel",
    ]


def _starting(currency: str, typed: str = "") -> list[str]:
    return _box("Starting balance first", "opening", currency, typed)


def _ending(currency: str, typed: str = "") -> list[str]:
    return _box("Ending balance first", "closing", currency, typed)


async def _open(pilot, app, record) -> ReconciliationDetailScreen:
    screen = ReconciliationDetailScreen(dict(record))
    await app.push_screen(screen)
    await wait_for(pilot, lambda: screen._list is not None)
    await pilot.pause()
    return screen


async def _press_c(pilot, app) -> None:
    await pilot.press("c")
    await wait_for(pilot, lambda: _is_box(app))
    await pilot.pause()


async def _type_in(pilot, typed: str) -> None:
    for ch in typed:
        await pilot.press(ch)
    await pilot.press("enter")


def _is_box(app) -> bool:
    return isinstance(app.screen, AmountPromptModal)


# ---- which balances are asked for ------------------------------------------------


def test_the_blank_balances_come_currency_by_currency_starting_before_ending():
    both = _ibk(_balance("PEN", None, None), _balance("USD", 500, None))
    assert blank_balances(both) == [("PEN", "beginning"), ("PEN", "ending"), ("USD", "ending")]
    assert blank_balances(OCTUBRE) == [("USD", "beginning"), ("USD", "ending")]
    assert blank_balances(_ibk(_balance("PEN", 1, 2))) == []
    assert blank_balances({"balances": None}) == []


def test_the_body_names_only_the_currencies_typed_with_only_the_balances_typed():
    one = balances_body({("USD", "beginning"): 0, ("USD", "ending"): -2499})
    assert one == {
        "balances": [
            {"currency_code": "USD", "beginning_balance_cents": 0, "ending_balance_cents": -2499}
        ]
    }
    two = balances_body({("PEN", "beginning"): -100, ("USD", "ending"): 5, ("PEN", "ending"): 7})
    assert two == {
        "balances": [
            {"currency_code": "PEN", "beginning_balance_cents": -100, "ending_balance_cents": 7},
            {"currency_code": "USD", "ending_balance_cents": 5},
        ]
    }


def _refused(**reasons: str) -> EngineError:
    return EngineError(
        "VALIDATION_ERROR",
        "Engine words.",
        {key: "Engine field words." for key in reasons},
        422,
        {},
        dict(reasons),
    )


def test_the_balances_a_refusal_names_are_read_off_its_reasons_by_key():
    err = _refused(
        **{
            "balances.USD.ending_balance_cents": "ENDING_BALANCE_REQUIRED",
            "balances.PEN.beginning_balance_cents": "BEGINNING_BALANCE_REQUIRED",
            "balances.USD.beginning_balance_cents": "BEGINNING_BALANCE_REQUIRED",
            "balances.EUR": "MONEY_AT_START_NOT_COVERED",
            "balances.PEN.difference_cents": "DIFFERENCE_NOT_ZERO",
            "statement_order": "STATEMENT_NOT_ORDERED",
        }
    )
    assert balances_named(err) == [
        ("USD", "beginning"),
        ("USD", "ending"),
        ("PEN", "beginning"),
        ("EUR", "beginning"),
        ("EUR", "ending"),
    ]
    assert balances_named(RuntimeError("down")) == []
    assert (
        balances_named(_refused(**{"balances.PEN.difference_cents": "DIFFERENCE_NOT_ZERO"})) == []
    )


# ---- c on a draft with blank balances (pane 6, steps 1 to 3) -----------------------


def test_c_asks_the_starting_then_the_ending_balance_saves_once_then_asks_to_complete(
    fake_client, monkeypatch
):
    """Pane 6, steps 1-3: the starting box, then the ending box, both for the
    dollars; one `PUT` naming the dollars alone with both figures; the header shows
    the engine's answer; then the usual question, and only `y` completes."""
    _engine(fake_client, monkeypatch)
    saved = _ibk(_balance("PEN", -82000, -34860), _balance("USD", 0, -2499, 0))
    fake_client.write_responses[PATH] = statement_put_answer(saved)
    fake_client.write_responses[COMPLETE] = statement_complete_answer({**saved, "status": 2})

    async def scenario(pilot, app):
        screen = await _open(pilot, app, OCTUBRE)
        await _press_c(pilot, app)
        assert _lines(app) == _starting("USD")
        assert fake_client.calls == []
        for ch in "0.00":
            await pilot.press(ch)
        assert _lines(app) == _starting("USD", "0.00")
        await pilot.press("enter")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        assert fake_client.puts == []  # nothing is sent between the boxes
        await _type_in(pilot, "-24.99")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert fake_client.puts == [
            (
                PATH,
                {
                    "balances": [
                        {
                            "currency_code": "USD",
                            "beginning_balance_cents": 0,
                            "ending_balance_cents": -2499,
                        }
                    ]
                },
            )
        ]
        assert fake_client.posts == []
        head = shown(screen.query_one("#rhead", Static)).splitlines()
        assert head[-1].split() == ["USD", "0.00", "-24.99", "—"]
        assert [str(s.visual) for s in app.screen.query(Static)][0] == "Complete statement?"
        await pilot.press("y")
        await wait_for(pilot, lambda: fake_client.posts)
        assert fake_client.posts == [(COMPLETE, None)]

    run_app(scenario, size=(80, 26))


def test_two_currencies_are_asked_in_turn_and_saved_in_one_put_naming_both(
    fake_client, monkeypatch
):
    """The soles' blank starting balance, then the dollars' blank ending balance: the
    body names each currency once, with only the balance typed for it."""
    record = _ibk(_balance("PEN", None, -34860), _balance("USD", 500, None))
    _engine(fake_client, monkeypatch)
    fake_client.write_responses[PATH] = statement_put_answer(
        _ibk(_balance("PEN", -82000, -34860, 0), _balance("USD", 500, -2499, 0))
    )

    async def scenario(pilot, app):
        await _open(pilot, app, record)
        await _press_c(pilot, app)
        assert _lines(app) == _starting("PEN")
        await _type_in(pilot, "-820.00")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        await _type_in(pilot, "-24.99")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))

    run_app(scenario, size=(80, 26))
    assert fake_client.puts == [
        (
            PATH,
            {
                "balances": [
                    {"currency_code": "PEN", "beginning_balance_cents": -82000},
                    {"currency_code": "USD", "ending_balance_cents": -2499},
                ]
            },
        )
    ]


def test_esc_in_a_box_sends_nothing_even_after_an_earlier_box(fake_client, monkeypatch):
    _engine(fake_client, monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(pilot, app, OCTUBRE)
        await _press_c(pilot, app)
        await _type_in(pilot, "0.00")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert fake_client.calls == []
        assert not screen._busy

    run_app(scenario, size=(80, 26))


def test_text_the_box_cannot_read_keeps_it_open_and_sends_nothing(fake_client, monkeypatch):
    _engine(fake_client, monkeypatch)
    notices = _notes(monkeypatch)

    async def scenario(pilot, app):
        await _open(pilot, app, OCTUBRE)
        await _press_c(pilot, app)
        await _type_in(pilot, "abc")
        await wait_for(pilot, lambda: notices)
        assert notices == [("", "Begin balance: a signed decimal, e.g. 9580.00", "error")]
        assert app.screen.query_one(Input).value == "abc"
        assert fake_client.calls == []

    run_app(scenario, size=(80, 26))


# ---- a refused complete that names a balance (pane 6, last two screens) ----------------


def _money_at_start() -> EngineError:
    """Dollars hold money at Noviembre's start and it holds no balances for them
    (contract: POST /v1/statements/{statement_id}/complete,
    "Every currency with money at the start has balances in it"). The words are the test's."""
    return EngineError(
        "VALIDATION_ERROR",
        "Engine words for MONEY_AT_START_NOT_COVERED.",
        {"balances.USD": "Engine field words."},
        422,
        {},
        {"balances.USD": "MONEY_AT_START_NOT_COVERED"},
    )


def test_money_at_start_not_covered_opens_the_boxes_for_the_currency_the_engine_names(
    fake_client, monkeypatch
):
    """Pane 6's last two screens: the question, `y`, the refusal naming the dollars the
    statement does not cover; the starting box and the ending box (empty) open for
    them, one `PUT` adds both, and the question asks again."""
    _engine(fake_client, monkeypatch, fresh=NOVIEMBRE)
    notices = _notes(monkeypatch)
    fake_client.errors["POST"] = _money_at_start()
    saved = _ibk(
        _balance("PEN", -34860, -51290, 0), _balance("USD", -2499, -2499, 0), name="Noviembre 2026"
    )
    fake_client.write_responses[PATH] = statement_put_answer(saved)

    async def scenario(pilot, app):
        screen = await _open(pilot, app, NOVIEMBRE)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: _is_box(app))
        await pilot.pause()
        assert notices[0] == (
            "Couldn't complete",
            "VALIDATION_ERROR — Engine words for MONEY_AT_START_NOT_COVERED.\n"
            "  balances.USD: Engine field words.",
            "error",
        )
        assert _lines(app) == _starting("USD")
        await _type_in(pilot, "-24.99")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        await _type_in(pilot, "-24.99")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert [str(s.visual) for s in app.screen.query(Static)][0] == "Complete statement?"
        assert len(fake_client.posts) == 1
        fake_client.errors.pop("POST")
        fake_client.write_responses[COMPLETE] = statement_complete_answer({**saved, "status": 2})
        await pilot.press("y")
        await wait_for(pilot, lambda: len(fake_client.posts) == 2)
        assert screen.is_attached

    run_app(scenario, size=(80, 26))
    assert fake_client.puts == [
        (
            PATH,
            {
                "balances": [
                    {
                        "currency_code": "USD",
                        "beginning_balance_cents": -2499,
                        "ending_balance_cents": -2499,
                    }
                ]
            },
        )
    ]


@pytest.mark.parametrize(
    ("reason", "field", "box"),
    [
        ("BEGINNING_BALANCE_REQUIRED", "balances.PEN.beginning_balance_cents", "beginning"),
        ("ENDING_BALANCE_REQUIRED", "balances.PEN.ending_balance_cents", "ending"),
    ],
)
def test_a_missing_balance_refusal_opens_the_box_for_it_then_asks_again(
    fake_client, monkeypatch, reason, field, box
):
    """The screen read the balance as entered, the engine says it is blank: the same box
    opens for the currency and balance named, one `PUT` sends it alone, and the
    question asks again."""
    _engine(fake_client, monkeypatch, fresh=NOVIEMBRE)
    fake_client.errors["POST"] = _refused(**{field: reason})
    fake_client.write_responses[PATH] = statement_put_answer(NOVIEMBRE)
    key = "beginning_balance_cents" if box == "beginning" else "ending_balance_cents"

    async def scenario(pilot, app):
        await _open(pilot, app, NOVIEMBRE)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: _is_box(app))
        await pilot.pause()
        assert _lines(app) == (_starting("PEN") if box == "beginning" else _ending("PEN"))
        await _type_in(pilot, "-12.50")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))

    run_app(scenario, size=(80, 26))
    assert fake_client.puts == [(PATH, {"balances": [{"currency_code": "PEN", key: -1250}]})]


def test_a_refusal_naming_no_balance_opens_no_box(fake_client, monkeypatch):
    _engine(fake_client, monkeypatch, fresh=NOVIEMBRE)
    notices = _notes(monkeypatch)
    fake_client.errors["POST"] = _refused(
        **{"balances.PEN.difference_cents": "DIFFERENCE_NOT_ZERO"}
    )

    async def scenario(pilot, app):
        screen = await _open(pilot, app, NOVIEMBRE)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notices)
        await pilot.pause()
        assert app.screen is screen
        assert fake_client.puts == []

    run_app(scenario, size=(80, 26))


# ---- a refused save -------------------------------------------------------------------


def test_a_balance_save_at_the_same_moment_as_another_write_says_to_press_r(
    fake_client, monkeypatch
):
    """`CONCURRENT_CHANGE` on the save: the engine's words, then the screen's own line
    for a list, `press r, then try again.`, and nothing is asked or completed
    (contract: PUT /v1/statements/{statement_id}, "Sent at the same moment as another write")."""
    _engine(fake_client, monkeypatch)
    notices = _notes(monkeypatch)
    field = "balances.USD"
    fake_client.errors["PUT"] = EngineError(
        "CONFLICT",
        "Engine words for CONCURRENT_CHANGE.",
        {field: "Engine field words."},
        409,
        {},
        {field: "CONCURRENT_CHANGE"},
    )

    async def scenario(pilot, app):
        screen = await _open(pilot, app, OCTUBRE)
        await _press_c(pilot, app)
        await _type_in(pilot, "0.00")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        await _type_in(pilot, "-24.99")
        await wait_for(pilot, lambda: notices)
        assert notices == [
            (
                "Couldn't save",
                "CONFLICT — Engine words for CONCURRENT_CHANGE.\n"
                "  balances.USD: Engine field words.\n\n"
                "It changed at the same moment: press r, then try again.",
                "error",
            )
        ]
        assert app.screen is screen and not screen._busy
        assert fake_client.posts == []

    run_app(scenario, size=(80, 26))


def test_a_complete_refused_after_the_save_says_the_balances_are_saved(fake_client, monkeypatch):
    _engine(fake_client, monkeypatch, fresh=OCTUBRE)
    notices = _notes(monkeypatch)
    fake_client.write_responses[PATH] = statement_put_answer(OCTUBRE)
    fake_client.errors["POST"] = _refused(
        **{"balances.PEN.difference_cents": "DIFFERENCE_NOT_ZERO"}
    )

    async def scenario(pilot, app):
        await _open(pilot, app, OCTUBRE)
        await _press_c(pilot, app)
        await _type_in(pilot, "0.00")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        await _type_in(pilot, "0.00")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: notices)
        assert notices[0][0] == "Couldn't complete"
        assert notices[0][1].startswith(f"{SAVED_WORDS}\nVALIDATION_ERROR — Engine words.")

    run_app(scenario, size=(80, 26))
