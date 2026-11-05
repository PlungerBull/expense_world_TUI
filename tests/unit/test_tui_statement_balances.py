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
    NOVIEMBRE_IBK,
    bank_line_row,
    complete_refusal,
    cursor_page,
    import_part,
    money_at_start_refusal,
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
NOVIEMBRE = NOVIEMBRE_IBK


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
        assert notices == [("", "Begin balance USD: a signed decimal, e.g. 9580.00", "error")]
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
        assert complete_refusal(screen) == [
            "Couldn't complete",
            "VALIDATION_ERROR — Engine words for MONEY_AT_START_NOT_COVERED.",
            "  balances.USD: Engine field words.",
        ]
        assert notices == []
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
        await wait_for(pilot, lambda: complete_refusal(screen))
        assert complete_refusal(screen)[0] == "Couldn't complete"
        assert notices == []
        assert app.screen is screen
        assert fake_client.puts == []
        await pilot.press("down")  # the next key takes the lines away
        assert complete_refusal(screen) is None

    run_app(scenario, size=(80, 26))


# ---- the refusal under the head, as pane 6 draws it ---------------------------------

_NOVIEMBRE_HEAD = [
    "  Noviembre 2026  ·  IBK Visa  ·  2026-09-26 → 2026-10-25  ·  status draft",
    "            begin          end      diff",
    "  PEN     -348.60      -512.90",
]


async def _refused_with_the_box_up(pilot, app) -> ReconciliationDetailScreen:
    screen = await _open(pilot, app, NOVIEMBRE)
    await pilot.press("c")
    await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
    await pilot.press("y")
    await wait_for(pilot, lambda: _is_box(app))
    await pilot.pause()
    return screen


def test_pane_6_the_refusal_stands_between_the_head_and_the_box_at_80x24(fake_client, monkeypatch):
    """The engine names a currency the draft does not cover: `Couldn't complete` and the
    engine's code, message and field line, each wrapping under its own first word, stand
    between the head's last currency row and the box's top rule, the box below them,
    and nothing in the corner."""
    _engine(fake_client, monkeypatch, fresh=NOVIEMBRE)
    notices = _notes(monkeypatch)
    fake_client.errors["POST"] = money_at_start_refusal()

    async def scenario(pilot, app):
        await _refused_with_the_box_up(pilot, app)
        assert _under_head(app) == [
            *_NOVIEMBRE_HEAD,
            "",
            "  Couldn't complete",
            "  MONEY_AT_START_NOT_COVERED — Every currency with money at the start needs",
            "  balances in the statement.",
            "    balances.USD: USD has -24.99 at the statement's start, and the statement",
            "    holds no balances for it.",
            "",
            RULE,
            "",
            *[("    " + line).rstrip() for line in _starting("USD", "")[:3]],
            "",
            "    [enter] save    [esc] cancel",
            "",
            RULE,
            " esc Cancel",
        ]
        assert notices == []

    run_app(scenario, size=(80, 24))


@pytest.mark.parametrize("key", ["5", "enter", "escape"])
def test_the_next_key_takes_the_refusal_away_and_the_box_keeps_its_place(
    fake_client, monkeypatch, key
):
    """The first character typed, `enter` and `esc` each remove the lines; the box moves
    up to where it stands without them and still works."""
    _engine(fake_client, monkeypatch, fresh=NOVIEMBRE)
    _notes(monkeypatch)
    fake_client.errors["POST"] = money_at_start_refusal()

    async def scenario(pilot, app):
        screen = await _refused_with_the_box_up(pilot, app)
        assert complete_refusal(screen)[0] == "Couldn't complete"
        await pilot.press(key)
        await pilot.pause()
        assert complete_refusal(screen) is None
        if key == "escape":
            assert app.screen is screen
            return
        typed = "5" if key == "5" else ""
        assert _is_box(app)
        assert _under_head(app) == _pane6(
            _NOVIEMBRE_HEAD,
            [*_starting("USD")[:3], typed, "[enter] save    [esc] cancel"],
            " esc Cancel",
        )
        if key == "5":
            await pilot.press("enter")
            await wait_for(pilot, lambda: _lines(app) == _ending("USD"))

    run_app(scenario, size=(80, 24))


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
        screen = await _open(pilot, app, OCTUBRE)
        await _press_c(pilot, app)
        await _type_in(pilot, "0.00")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        await _type_in(pilot, "0.00")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: complete_refusal(screen))
        assert complete_refusal(screen)[:3] == [
            "Couldn't complete",
            SAVED_WORDS,
            "VALIDATION_ERROR — Engine words.",
        ]
        assert notices == []

    run_app(scenario, size=(80, 26))


# ---- where the boxes sit: under the head, as pane 6 draws them ------------------------

RULE = "  " + "─" * 60
#: Where the box's text ends at most: column 4 and 60 wide.
TEXT_END = 64


def _under_head(app) -> list[str]:
    """The screen as drawn at 80x24 from the head's first line to the closing rule of
    the box or the question, the footer's line last."""
    rows = screen_lines(app)
    first = next(i for i, row in enumerate(rows) if "·  IBK Visa" in row)
    last = max(i for i, row in enumerate(rows) if row == RULE)
    return [*rows[first : last + 1], rows[-1]]


def _pane6(head: list[str], box: list[str], footer: str) -> list[str]:
    """Pane 6's lines: the head, a blank line, the rule, a blank line, the text at
    column 4, a blank line, the rule, the footer."""
    return [*head, "", RULE, "", *[("    " + line).rstrip() for line in box], "", RULE, footer]


def _cells(rows: list[str]) -> list[list[str]]:
    return [row.split() for row in rows]


def test_pane_6_octubre_the_boxes_and_the_question_under_the_head_at_80x24(
    fake_client, monkeypatch
):
    """Pane 6, steps 1-3, as drawn at 80x24: the head's lines (both currencies) stay on
    screen above each box and above the question, the blank line, the rule, the text at
    column 4, the blank line, the closing rule, and the footer naming only that box's or
    that question's keys."""
    _engine(fake_client, monkeypatch)
    saved = _ibk(_balance("PEN", -82000, -34860), _balance("USD", 0, -2499, 0))
    fake_client.write_responses[PATH] = statement_put_answer(saved)
    title = "  Octubre 2026  ·  IBK Visa  ·  2026-09-26 → 2026-10-25  ·  status draft"
    columns = "            begin          end      diff"
    pen = "  PEN     -820.00      -348.60"

    async def scenario(pilot, app):
        await _open(pilot, app, OCTUBRE)
        await _press_c(pilot, app)
        for ch in "0.00":
            await pilot.press(ch)
        await pilot.pause()
        step1 = _pane6(
            [title, columns, pen, "  USD           —            —"],
            [
                "Starting balance first",
                "The statement's opening figure for IBK Visa,",
                "in USD · signed · e.g. 13,853.20",
                "0.00",
                "[enter] save    [esc] cancel",
            ],
            " esc Cancel",
        )
        assert _under_head(app) == step1
        await pilot.press("enter")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        for ch in "-24.99":
            await pilot.press(ch)
        await pilot.pause()
        step2 = _pane6(
            step1[:4],
            [
                "Ending balance first",
                "The statement's closing figure for IBK Visa,",
                "in USD · signed · e.g. 13,853.20",
                "-24.99",
                "[enter] save    [esc] cancel",
            ],
            " esc Cancel",
        )
        assert _under_head(app) == step2
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.pause()
        step3 = _under_head(app)
        head = [title, columns, pen, "  USD        0.00       -24.99         —"]
        want = _pane6(
            head,
            [
                "Complete statement?",
                "",
                "Locks the amount, date, title, account, operation number and",
                "statement of the 0 ticked rows.",
                "[y] confirm    [enter / n / esc] cancel",
            ],
            " y Yes  n No",
        )
        assert step3[:2] == want[:2]
        assert _cells(step3[2:4]) == _cells(want[2:4])  # the saved figures, in sight
        assert step3[4:] == want[4:]

    run_app(scenario, size=(80, 24))


def test_pane_6_noviembre_the_saved_dollar_line_shows_above_the_question_asked_again(
    fake_client, monkeypatch
):
    """The head grows by a `USD` line when the dollars are saved; the question that
    asks again is drawn below that line, never over it."""
    _engine(fake_client, monkeypatch, fresh=NOVIEMBRE)
    _notes(monkeypatch)
    fake_client.errors["POST"] = _money_at_start()
    saved = _ibk(
        _balance("PEN", -34860, -51290, 0), _balance("USD", -2499, -2499, 0), name="Noviembre 2026"
    )
    fake_client.write_responses[PATH] = statement_put_answer(saved)

    async def scenario(pilot, app):
        await _open(pilot, app, NOVIEMBRE)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.pause()
        before = _under_head(app)
        assert [r.split() for r in before[2:3]] == [["PEN", "-348.60", "-512.90"]]
        assert before[3:5] == ["", RULE]  # one currency: the rule right under it
        await pilot.press("y")
        await wait_for(pilot, lambda: _is_box(app))
        await pilot.pause()
        await _type_in(pilot, "-24.99")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        await _type_in(pilot, "-24.99")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.pause()
        after = _under_head(app)
        assert _cells(after[2:4]) == [
            ["PEN", "-348.60", "-512.90", "—"],
            ["USD", "-24.99", "-24.99", "—"],
        ]
        assert after[4:7] == ["", RULE, ""]
        assert after[7].strip() == "Complete statement?"

    run_app(scenario, size=(80, 24))


def _nothing_beside_or_below(rows: list[str]) -> None:
    """From the box's first rule down: no row reaches past the text's right end (the
    list's columns, the head's words), and every row under the closing rule down to the
    footer is blank."""
    first = rows.index(RULE)
    last = max(i for i, row in enumerate(rows) if row == RULE)
    for row in rows[first:-1]:
        assert len(row.rstrip()) <= TEXT_END, row
    assert [r for r in rows[last + 1 : -1] if r.strip()] == []


def _crowded(fake_client, monkeypatch, name: str, size: tuple[int, int]):
    _engine(fake_client, monkeypatch)
    monkeypatch.setattr("expense.reads.count_bank_lines", lambda *a, **k: 3)
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc-ibk": name}
    )
    record = _ibk(
        _balance("PEN", -82000, -34860),
        _balance("USD", None, None),
        _balance("EUR", 100, 200),
        name="Octubre 2026 tarjeta principal",
    )

    async def scenario(pilot, app):
        screen = await _open(pilot, app, record)
        await wait_for(pilot, lambda: screen.query_one("#rflag").display)
        await pilot.pause()
        await _press_c(pilot, app)
        rows = screen_lines(app)
        keys = next(i for i, row in enumerate(rows) if "[enter] save    [esc] cancel" in row)
        title = next(i for i, row in enumerate(rows) if "Starting balance first" in row)
        assert title < keys
        assert rows[-1].strip() == "esc Cancel"
        assert any(row == RULE for row in rows[keys:])  # the closing rule, whole
        _nothing_beside_or_below(rows)
        return rows

    return run_app(scenario, size=size)


def test_a_tall_head_never_cuts_the_boxes_keys_at_80x24(fake_client, monkeypatch):
    """Three currencies, a head of two lines and the `⚑` line: the box's message, input
    and keys are all drawn, and the head's balances are above it."""
    rows = _crowded(
        fake_client, monkeypatch, "Interbank Visa Signature Platinum Viajes Familia", (80, 24)
    )
    assert any(r.split()[:1] == ["EUR"] for r in rows)
    assert any("⚑ 3 lines flagged" in r for r in rows)


def test_a_box_too_short_for_the_head_rises_over_its_last_lines_rather_than_lose_its_keys(
    fake_client, monkeypatch
):
    """Where the space under the head is shorter than the box, the box moves up over the
    head's last lines; its own lines stay whole."""
    rows = _crowded(
        fake_client, monkeypatch, "Interbank Visa Signature Platinum Viajes Familia", (80, 20)
    )
    assert any("begin" in r and "end" in r for r in rows)


def _long_list(monkeypatch, count: int = 14) -> None:
    """The account's lines in no statement: more rows than the box is tall."""
    rows = [
        bank_line_row(
            f"l{n}",
            [import_part(f"t{n}", -1000 - n, account_id="acc-ibk", line=f"l{n}", day="2026-10-01")],
            net_cents=-1000 - n,
            account_id="acc-ibk",
        )
        for n in range(count)
    ]
    monkeypatch.setattr("expense.reads.fetch_bank_lines", lambda cfg, **k: cursor_page(rows))


def test_nothing_of_the_list_shows_beside_or_below_a_box_or_the_question(fake_client, monkeypatch):
    """A statement whose list has more rows than the box is tall: the list's columns do
    not draw beside the box, nor its rows below it, for a box and for the question."""
    _engine(fake_client, monkeypatch)
    _long_list(monkeypatch)
    saved = _ibk(_balance("PEN", -82000, -34860), _balance("USD", 0, -2499, 0))
    fake_client.write_responses[PATH] = statement_put_answer(saved)

    async def scenario(pilot, app):
        await _open(pilot, app, OCTUBRE)
        assert any("Amount" in row for row in screen_lines(app))  # the list is on screen
        await _press_c(pilot, app)
        _nothing_beside_or_below(screen_lines(app))
        assert not any("Amount" in row for row in screen_lines(app))
        await _type_in(pilot, "0.00")
        await wait_for(pilot, lambda: _lines(app) == _ending("USD"))
        _nothing_beside_or_below(screen_lines(app))
        await _type_in(pilot, "-24.99")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.pause()
        rows = screen_lines(app)
        _nothing_beside_or_below(rows)
        assert any("Complete statement?" in row for row in rows)
        assert ["USD", "0.00", "-24.99", "—"] in [row.split() for row in rows[:9]]

    run_app(scenario, size=(80, 24))


def test_a_long_statement_name_wraps_the_crumb_and_the_box_still_clears_the_dollar_line(
    fake_client, monkeypatch
):
    """A name of 42-45 characters wraps the crumb: the head is a line longer, and the
    box opens under its last line, the `USD` line in sight."""
    _engine(fake_client, monkeypatch)
    name = "Octubre 2026 cuenta principal de la familia"
    record = _ibk(_balance("PEN", -82000, -34860), _balance("USD", None, None), name=name)

    async def scenario(pilot, app):
        await _open(pilot, app, record)
        await _press_c(pilot, app)
        rows = screen_lines(app)
        usd = next(i for i, row in enumerate(rows) if row.split()[:1] == ["USD"])
        assert rows[usd].split() == ["USD", "—", "—"]
        assert rows[usd + 1] == ""
        assert rows[usd + 2] == RULE
        assert app.screen.query_one("#modal").region.y == usd + 1

    run_app(scenario, size=(80, 24))


def test_a_resize_while_a_box_is_open_places_it_again_under_the_head(fake_client, monkeypatch):
    """At 60 columns the head wraps to more lines than at 100; the open box moves down
    with it, and back up when the terminal is wide again."""
    _engine(fake_client, monkeypatch)
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map",
        lambda: {"acc-ibk": "BCP Cuenta Sueldo Soles"},
    )

    async def scenario(pilot, app):
        await _open(pilot, app, OCTUBRE)
        await _press_c(pilot, app)
        wide = app.screen.query_one("#modal").region.y
        await pilot.resize_terminal(60, 24)
        await wait_for(pilot, lambda: app.screen.query_one("#modal").region.y > wide)
        rows = screen_lines(app)
        assert rows[app.screen.query_one("#modal").region.y - 1].split()[:1] == ["USD"]
        await pilot.resize_terminal(100, 24)
        await wait_for(pilot, lambda: app.screen.query_one("#modal").region.y == wide)

    run_app(scenario, size=(100, 24))


# ---- a narrow terminal: the boxes wrap their words, none is cut ---------------------

STARTING_WORDS = (
    "Starting balance first The statement's opening figure for IBK Visa, "
    "in USD · signed · e.g. 13,853.20 [enter] save [esc] cancel"
)
QUESTION_WORDS = (
    "Complete statement? Locks the amount, date, title, account, operation number and "
    "statement of the 0 ticked rows. [y] confirm [enter / n / esc] cancel"
)


def _box_rows(app, first_word: str, last_word: str) -> list[str]:
    """The rows on screen from the one holding `first_word` to the one holding
    `last_word`, blank rows left out."""
    rows = screen_lines(app)
    top = next(i for i, row in enumerate(rows) if first_word in row)
    bottom = next(i for i, row in enumerate(rows) if last_word in row and i >= top)
    return [row.strip() for row in rows[top : bottom + 1] if row.strip()]


def _box_at(record, width, first, last, keys=()):
    """Open the statement at `width` columns, press `c` (and `keys` after it) and
    return the rows of the box standing."""

    async def scenario(pilot, app):
        await _open(pilot, app, record)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal | AmountPromptModal))
        for key in keys:
            await pilot.press(key)
            await pilot.pause()
        await pilot.pause()
        return _box_rows(app, first, last)

    return run_app(scenario, size=(width, 24))


def _wrapped_whole(rows: list[str], words: str) -> None:
    got = " ".join(rows).split()
    assert got == words.split()
    assert not any("…" in row for row in rows)


@pytest.mark.parametrize(
    ("record", "words", "first", "last", "keys"),
    [
        (OCTUBRE, STARTING_WORDS, "Starting", "[esc]", ()),
        (
            OCTUBRE,
            STARTING_WORDS.replace("Starting", "Ending").replace("opening", "closing"),
            "Ending",
            "[esc]",
            ("0", "enter"),
        ),
        (NOVIEMBRE, QUESTION_WORDS, "Complete", "cancel", ()),
    ],
    ids=["starting", "ending", "question"],
)
def test_at_60_columns_each_box_wraps_its_words_and_cuts_none(
    fake_client, monkeypatch, record, words, first, last, keys
):
    _engine(fake_client, monkeypatch)
    _wrapped_whole(_box_at(record, 60, first, last, keys), words)


def test_a_long_account_name_wraps_in_the_box_under_its_line(fake_client, monkeypatch):
    _engine(fake_client, monkeypatch)
    name = "Interbank Visa Signature Cuenta Sueldo Personal Soles y Dolares de Alejandro Ternero"
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: {"acc-ibk": name}
    )
    wide = _box_at(OCTUBRE, 80, "Starting", "[esc]")
    narrow = _box_at(OCTUBRE, 60, "Starting", "[esc]")
    assert len(narrow) > len(wide)
    words = STARTING_WORDS.replace("IBK Visa", name)
    _wrapped_whole(narrow, words)
