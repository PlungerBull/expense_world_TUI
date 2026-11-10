"""`t`'s question on Manage ▸ Accounts: what it draws, what it sends, where a refusal lands.

`t` on a bank account asks `Make <name> a person?` with a `name` line; on a person it asks
`Make <name> a bank account?` with a `bank` line (the engine's `GET /banks`, fixed while it
lists one) and an optional `last 4`. `⏎` sends `POST /accounts/{id}/make-person` or
`make-account` with what the lines hold; `esc` sends nothing. A refusal keyed on one of the
question's lines keeps it open on that line, in the engine's words, what was typed kept; any
other closes it and reads as `t`'s refusals always have (contract: POST
/v1/accounts/{account_id}/make-person, "Refusals") (contract: POST
/v1/accounts/{account_id}/make-account, "Refusals"). The write goes through the real HTTP
client against a respx-mocked engine.
"""

import json

import httpx
import pytest
import respx

from expense.tui.screens.modals import QuestionModal
from tests.unit.helpers import (
    ENGINE_URL,
    error_response,
    run_app,
    screen_lines,
    wait_for,
)
from tests.unit.test_tui_account_kind import _open, _rows, _stub_list, _turns

SIZE = (120, 40)


async def _ask(pilot, app, monkeypatch, ident: str):
    """Open the list on `ident`'s row, press `t`, and wait for the question."""
    screen, notes = await _open(pilot, app, monkeypatch, ident)
    await pilot.press("t")
    await wait_for(pilot, lambda: isinstance(app.screen, QuestionModal))
    return screen, notes


def _drawn(app) -> str:
    return "\n".join(screen_lines(app))


def _words(app, key: str) -> str | None:
    """The engine's words shown under the line `key`, None while none is shown."""
    note = app.screen.query_one(f"#refusal-{key}")
    return str(note.content) if note.display else None


# ---- what it draws -------------------------------------------------------


def test_the_person_question_is_drawn_as_the_mockup_has_it(configured, monkeypatch):
    _stub_list(monkeypatch, _rows())
    seen: dict = {}

    async def scenario(pilot, app):
        await _ask(pilot, app, monkeypatch, "a-alejo")
        seen["text"] = _drawn(app)
        seen["name"] = app.screen.query_one("#line-name").value
        seen["focused"] = app.screen.focused.id

    run_app(scenario, size=SIZE)
    text = seen["text"]
    assert "Make ALEJO a person?" in text and "name" in text
    assert "⏎ makes it · esc keeps it" in text
    assert seen["name"] == "" and seen["focused"] == "line-name"


def test_the_bank_question_fixes_the_one_bank_and_marks_last_4_optional(configured, monkeypatch):
    _stub_list(monkeypatch, _rows())
    seen: dict = {}

    async def scenario(pilot, app):
        await _ask(pilot, app, monkeypatch, "a-eliana")
        seen["text"] = _drawn(app)
        seen["focused"] = app.screen.focused.id

    run_app(scenario, size=SIZE)
    text = seen["text"]
    assert "Make Eliana a bank account?" in text
    assert "bank    BCP" in text
    assert any("last 4" in ln and ln.endswith("optional") for ln in text.splitlines())
    assert "⏎ makes it · esc keeps it" in text
    assert seen["focused"] == "line-last4"  # the fixed bank takes no cursor


def test_with_two_banks_the_bank_line_picks_one_in_the_engines_order(configured, monkeypatch):
    _stub_list(monkeypatch, _rows())
    monkeypatch.setattr("expense.reads.fetch_bank_codes", lambda cfg, **kw: ["BCP", "IBK"])
    seen: dict = {}

    async def scenario(pilot, app):
        await _ask(pilot, app, monkeypatch, "a-eliana")
        text = _drawn(app)
        seen["order"] = text.index("BCP") < text.index("IBK")
        seen["focused"] = app.screen.focused  # the bank line, not an input
        await pilot.press("down")
        await pilot.press("tab")  # on to last 4
        seen["then"] = app.screen.focused.id
        await pilot.press("enter")
        await wait_for(pilot, lambda: not isinstance(app.screen, QuestionModal))

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-eliana/make-account").mock(
            httpx.Response(200, json=_rows()[3])
        )
        run_app(scenario, size=SIZE)
    assert seen["order"] and seen["focused"] is None and seen["then"] == "line-last4"
    assert json.loads(sent.calls.last.request.content) == {"bank_code": "IBK"}


# ---- what it sends ---------------------------------------------------------

SENDS = [
    ("a-alejo", "make-person", None, {"name": "Mamá"}),
    ("a-eliana", "make-account", "", {"bank_code": "BCP"}),
    ("a-eliana", "make-account", "4321", {"bank_code": "BCP", "last4": "4321"}),
]


@pytest.mark.parametrize(("ident", "route", "last4", "body"), SENDS)
def test_enter_sends_the_whole_body_the_lines_hold(
    configured, monkeypatch, ident, route, last4, body
):
    rows = _rows()
    _stub_list(monkeypatch, rows)

    async def scenario(pilot, app):
        screen, notes = await _ask(pilot, app, monkeypatch, ident)
        if route == "make-person":
            app.screen.query_one("#line-name").value = "Mamá"
        else:
            app.screen.query_one("#line-last4").value = last4
        await pilot.press("enter")
        note = "Now a person." if route == "make-person" else "Now a bank account."
        await wait_for(pilot, lambda: ("", note) in notes)
        await wait_for(pilot, lambda: not screen._toggle_busy)
        assert app.screen is screen

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/{ident}/{route}").mock(
            side_effect=_turns(rows, ident, route == "make-person")
        )
        run_app(scenario, size=SIZE)
    assert sent.call_count == 1
    assert json.loads(sent.calls.last.request.content) == body
    assert sent.calls.last.request.headers["X-Idempotency-Key"]


def test_esc_keeps_the_account_and_sends_nothing(configured, monkeypatch):
    _stub_list(monkeypatch, _rows())
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _ask(pilot, app, monkeypatch, "a-alejo")
        app.screen.query_one("#line-name").value = "Mamá"
        await pilot.press("escape")
        await pilot.pause()
        seen["on_list"] = app.screen is screen
        seen["notes"] = list(notes)
        seen["busy"] = screen._toggle_busy

    with respx.mock(assert_all_called=False) as engine:
        sent = engine.post(url__startswith=ENGINE_URL).mock(httpx.Response(200, json={}))
        run_app(scenario, size=SIZE)
    assert not sent.called
    assert seen == {"on_list": True, "notes": [], "busy": False}


# ---- refusals on the question's own lines ----------------------------------

_TAKEN = "That name is taken."

KEYED = [
    # cursor row, route, typed (line → text), engine key, code, status, reason, banks
    ("a-alejo", "make-person", {"name": "Eliana"}, "name", "CONFLICT", 409, "NAME_EXISTS", ["BCP"]),
    (
        "a-eliana",
        "make-account",
        {"last4": "5678"},
        "last4",
        "CONFLICT",
        409,
        "NAME_EXISTS",
        ["BCP"],
    ),
    ("a-eliana", "make-account", {}, "bank_code", "CONFLICT", 409, "NAME_EXISTS", ["BCP", "IBK"]),
]


@pytest.mark.parametrize(
    ("ident", "route", "typed", "key", "code", "status", "reason", "banks"),
    KEYED,
    ids=["name-exists", "last4-name-exists", "bank-code-name-exists"],
)
def test_a_refusal_on_a_line_keeps_the_question_open_on_it_with_what_was_typed(
    configured, monkeypatch, ident, route, typed, key, code, status, reason, banks
):
    _stub_list(monkeypatch, _rows())
    monkeypatch.setattr("expense.reads.fetch_bank_codes", lambda cfg, **kw: list(banks))
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _ask(pilot, app, monkeypatch, ident)
        for line, text in typed.items():
            app.screen.query_one(f"#line-{line}").value = text
        await pilot.press("enter")
        await wait_for(pilot, lambda: _words(app, key) is not None)
        seen["open"] = isinstance(app.screen, QuestionModal)
        seen["words"] = _words(app, key)
        seen["others"] = [
            _words(app, k)
            for k in app.screen.keys()
            if k != key  # no other line shows any
        ]
        seen["focused"] = getattr(app.screen.focused, "id", None)
        seen["held"] = app.screen.values()
        seen["notes"] = list(notes)
        seen["busy"] = screen._toggle_busy
        if key != "bank_code":  # typing on the refused line hides its words at once
            await pilot.press("x")
            seen["hidden_by_typing"] = _words(app, key) is None
        await pilot.press("enter")  # the question sends again
        await wait_for(pilot, lambda: sent.call_count == 2)

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/{ident}/{route}").mock(
            error_response(status, code, _TAKEN, {key: _TAKEN}, {key: reason})
        )
        run_app(scenario, size=SIZE)
    assert seen["open"] and _TAKEN in seen["words"]
    assert set(seen["others"]) <= {None}
    # the cursor is on the refused line: its input, or none for a choice line
    assert seen["focused"] == (None if key == "bank_code" else f"line-{key}")
    assert {k: v for k, v in seen["held"].items() if k in typed} == typed
    assert seen["notes"] == [] and seen["busy"] is False
    assert seen.get("hidden_by_typing", True)
    assert sent.call_count == 2
    keys = [c.request.headers["X-Idempotency-Key"] for c in sent.calls]
    assert keys[0] != keys[1]  # a resend after a refusal is a new write


@pytest.mark.parametrize(
    ("ident", "route", "reason", "message"),
    [
        (
            "a-alejo",
            "make-person",
            "HAS_RECONCILIATION",
            "The account has a reconciliation, which a person account cannot have.",
        ),
    ],
)
def test_a_refusal_on_the_account_closes_the_question_and_reads_as_before(
    configured, monkeypatch, ident, route, reason, message
):
    _stub_list(monkeypatch, _rows())
    seen: dict = {}

    async def scenario(pilot, app):
        screen, notes = await _ask(pilot, app, monkeypatch, ident)
        app.screen.query_one("#line-name" if route == "make-person" else "#line-last4").value = "x"
        await pilot.press("enter")
        await wait_for(pilot, lambda: notes)
        await pilot.pause()
        seen["closed"] = app.screen is screen
        seen["notes"] = list(notes)
        seen["busy"] = screen._toggle_busy

    with respx.mock() as engine:
        engine.post(f"{ENGINE_URL}/v1/accounts/{ident}/{route}").mock(
            error_response(
                409, "CONFLICT", message, {"account_id": message}, {"account_id": reason}
            )
        )
        run_app(scenario, size=SIZE)
    assert seen["closed"] and seen["busy"] is False
    assert seen["notes"] == [("Failed", f"CONFLICT — {message}\n  account_id: {message}")]


def test_tab_stops_at_either_end_and_a_new_refusal_hides_the_old(configured, monkeypatch):
    _stub_list(monkeypatch, _rows())
    monkeypatch.setattr("expense.reads.fetch_bank_codes", lambda cfg, **kw: ["BCP", "IBK"])
    seen: dict = {}

    async def scenario(pilot, app):
        await _ask(pilot, app, monkeypatch, "a-eliana")
        await pilot.press("shift+tab")  # already on the first line: stays
        seen["first"] = app.screen.focused
        await pilot.press("tab", "tab")  # last 4, then the end: stays
        seen["last"] = app.screen.focused.id
        await pilot.press("enter")
        await wait_for(pilot, lambda: _words(app, "last4") is not None)
        await pilot.press("shift+tab", "down", "enter")  # pick IBK: its refusal hides at once
        await wait_for(pilot, lambda: _words(app, "bank_code") is not None)
        seen["after"] = (_words(app, "last4"), _words(app, "bank_code") is not None)

    with respx.mock() as engine:
        answers = iter(["last4", "bank_code"])
        engine.post(f"{ENGINE_URL}/v1/accounts/a-eliana/make-account").mock(
            side_effect=lambda r: (
                lambda key: error_response(
                    409, "CONFLICT", _TAKEN, {key: _TAKEN}, {key: "NAME_EXISTS"}
                )
            )(next(answers))
        )
        run_app(scenario, size=SIZE)
    assert seen["first"] is None and seen["last"] == "line-last4"
    assert seen["after"] == (None, True)


def test_with_no_bank_listed_the_line_shows_nothing_and_enter_sends_none(configured, monkeypatch):
    _stub_list(monkeypatch, _rows())
    monkeypatch.setattr("expense.reads.fetch_bank_codes", lambda cfg, **kw: [])

    async def scenario(pilot, app):
        await _ask(pilot, app, monkeypatch, "a-eliana")
        await pilot.press("enter")
        await wait_for(pilot, lambda: _words(app, "bank_code") is not None)

    with respx.mock() as engine:
        sent = engine.post(f"{ENGINE_URL}/v1/accounts/a-eliana/make-account").mock(
            error_response(
                422,
                "VALIDATION_ERROR",
                "bank_code is required.",
                {"bank_code": "Required."},
                {"bank_code": "REQUIRED"},
            )
        )
        run_app(scenario, size=SIZE)
    assert json.loads(sent.calls.last.request.content) == {}
