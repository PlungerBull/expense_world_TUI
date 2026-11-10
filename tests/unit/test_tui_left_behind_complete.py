"""A statement's complete (`c`) and its balances' save, finished after their screen has left.

Left with the engine still answering, a complete that went through says `Statement
completed · <name>` on the app: the engine's notes (`⚠ …`) and, when the engine's count of the
statement's review list is above zero, where its flagged lines are; nothing opens by itself.
A balances save says it is saved and the statement is not completed, and the question to
complete never comes. A refusal is a titled error toast of 10 seconds. The Statements screen
that opened the one left, when it is the one shown, reads again after a write that landed.
"""

import threading

import pytest

from expense.errors import EngineError, format_error
from expense.tui.screens._base import list_refusal_text
from expense.tui.screens.modals import AmountPromptModal
from expense.tui.screens.statements import StatementScreen
from tests.unit.helpers import (
    LateAnswer,
    app_notes,
    run_app,
    statement_complete_answer,
    statement_put_answer,
    wait_for,
)
from tests.unit.test_tui_bulk_edit import _plain
from tests.unit.test_tui_left_behind_statements import Opener, _leave
from tests.unit.test_tui_statement_balances import OCTUBRE, PATH, _balance, _engine, _ibk
from tests.unit.test_tui_statement_detail import COMPLETE_PATH, DRAFT, _patch, _wait_list

REFUSAL = EngineError("CONFLICT", "stand-in [not markup]", None, 409, {})
NAME = DRAFT["name"]
NOTE = "PEN: 3 days (2026-04-27 - 2026-04-29) are in no statement. [see them]"
ANSWER = statement_complete_answer(
    {
        "balances": [
            {
                "currency_code": "PEN",
                "warnings": [NOTE],
                "coverage_gap": None,
                "review_lines": [],
            }
        ],
        "not_covered": [{"currency_code": "USD", "warnings": ["no balances were given."]}],
    }
)
STILL_OPEN = "The statement is not completed: open it and press c."


def _left_complete(
    fake_client,
    monkeypatch,
    *,
    count=3,
    refusal=None,
    elsewhere=False,
    quit_app=False,
    answer=ANSWER,
):
    """Press `c`, `y`, leave while the complete waits, let it answer and the count read
    follow; return `((the app's toasts, the opener's reads, what the left screen was asked
    to touch), the screen shown at the end)`. `count` is the engine's count, or the error
    its read raises. With `quit_app` the app quits while the count read is held."""
    _patch(monkeypatch)
    count_started, count_release, count_done = (threading.Event() for _ in range(3))

    def fake_count(cfg, **k):
        if quit_app and late.release.is_set():
            count_started.set()
            count_release.wait(5)
            count_done.set()
        if isinstance(count, Exception):
            if late.release.is_set():  # the count read after the answer; the screen's own is fine
                raise count
            return 0
        return count

    monkeypatch.setattr("expense.reads.count_bank_lines", fake_count)
    fake_client.write_responses[COMPLETE_PATH] = answer
    late = LateAnswer(fake_client, "post", refusal)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        opener = Opener()
        await app.push_screen(opener)
        screen = StatementScreen(dict(DRAFT), opener=opener, reload=opener.reload)
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("c")
        await pilot.press("y")
        await wait_for(pilot, late.started.is_set)
        touched: list[str] = []
        monkeypatch.setattr(screen, "_load_txns", lambda *a, **k: touched.append("read"))
        monkeypatch.setattr(screen, "notify", lambda *a, **k: touched.append("toast"))
        await _leave(pilot, app, screen, opener, elsewhere)
        late.release.set()
        if quit_app:
            await wait_for(pilot, count_started.is_set, timeout=3)
            app.exit()
            count_release.set()
            await wait_for(pilot, count_done.is_set, timeout=3)
        else:
            await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.pause()
        result.extend([notes, opener.reads, touched, app.screen])

    run_app(scenario)
    return result[:3], result[3]


def _only(notes):
    [(title, message, options)] = notes
    return title, _plain(message), options


def test_a_complete_answered_after_leaving_gives_the_notes_and_the_flagged_count(
    fake_client, monkeypatch
):
    (notes, reads, touched), shown = _left_complete(fake_client, monkeypatch)
    title, message, options = _only(notes)
    assert title == f"Statement completed · {NAME}"
    assert message == (
        f"⚠ {NOTE}\n⚠ USD: no balances were given.\n"
        "⚑ 3 lines flagged for review: open the statement and press f."
    )
    assert "[see them]" in message  # the engine's words never read as markup
    assert (options["markup"], options.get("severity", "information")) == (True, "information")
    assert reads == 1  # the opener is the screen shown: it reads again
    assert touched == []
    assert type(shown) is Opener  # no flagged-lines screen opened by itself


@pytest.mark.parametrize(
    ("count", "flagged"),
    [
        (1, "⚑ 1 line flagged for review: open the statement and press f."),
        (0, None),
        (REFUSAL, None),  # the count read failed: the flagged line is left out
    ],
    ids=["singular", "none", "count failed"],
)
def test_the_flagged_line_is_worded_by_the_count_and_left_out_without_one(
    fake_client, monkeypatch, count, flagged
):
    (notes, *_), _ = _left_complete(fake_client, monkeypatch, count=count)
    title, message, _ = _only(notes)
    assert title == f"Statement completed · {NAME}"
    notes_only = f"⚠ {NOTE}\n⚠ USD: no balances were given."
    assert message == notes_only + (f"\n{flagged}" if flagged else "")


def test_a_complete_with_nothing_to_add_says_the_plain_words(fake_client, monkeypatch):
    (notes, reads, touched), _ = _left_complete(
        fake_client, monkeypatch, count=0, answer=statement_complete_answer()
    )
    assert [(t, m, o["markup"]) for t, m, o in notes] == [("", "Statement completed.", False)]
    assert (reads, touched) == (1, [])


def test_a_complete_answered_elsewhere_reads_nothing(fake_client, monkeypatch):
    (notes, reads, touched), _ = _left_complete(fake_client, monkeypatch, elsewhere=True)
    assert [t for t, _, _ in notes] == [f"Statement completed · {NAME}"]
    assert reads == 0
    assert touched == []


def test_a_refused_complete_names_the_statement_and_gives_the_engines_words(
    fake_client, monkeypatch
):
    (notes, reads, touched), _ = _left_complete(fake_client, monkeypatch, refusal=REFUSAL)
    [(title, message, options)] = notes
    assert title == f"Not completed · Statement {NAME}"
    assert message == format_error(REFUSAL)
    assert "[not markup]" in message
    assert (options["severity"], options["timeout"], options["markup"]) == ("error", 10, False)
    assert reads == 0  # a refusal changed nothing
    assert touched == []


def test_quitting_while_the_count_is_read_shows_nothing_more(fake_client, monkeypatch):
    (notes, _reads, touched), _ = _left_complete(fake_client, monkeypatch, quit_app=True)
    assert notes == []
    assert touched == []


# ---- the balances ------------------------------------------------------------------------


def _left_balances(fake_client, monkeypatch, *, refusal=None):
    _engine(fake_client, monkeypatch)
    monkeypatch.setattr("expense.reads.count_bank_lines", lambda *a, **k: 0)
    saved = _ibk(_balance("PEN", -82000, -34860), _balance("USD", 0, -2499, 0))
    fake_client.write_responses[PATH] = statement_put_answer(saved)
    late = LateAnswer(fake_client, "put", refusal)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        opener = Opener()
        await app.push_screen(opener)
        screen = StatementScreen(dict(OCTUBRE), opener=opener, reload=opener.reload)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: screen._list is not None)
        await pilot.pause()
        await pilot.press("c")
        for typed in ("0.00", "-24.99"):
            await wait_for(pilot, lambda: isinstance(app.screen, AmountPromptModal))
            await pilot.pause()
            for ch in typed:
                await pilot.press(ch)
            await pilot.press("enter")
        await wait_for(pilot, late.started.is_set)
        touched: list[str] = []
        monkeypatch.setattr(screen, "_confirm_complete", lambda **k: touched.append("question"))
        monkeypatch.setattr(screen, "_load_txns", lambda *a, **k: touched.append("read"))
        await _leave(pilot, app, screen, opener, False)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.pause()
        result.extend([notes, opener.reads, touched, app.screen])

    run_app(scenario)
    return result


def test_balances_saved_after_leaving_say_the_statement_is_not_completed(fake_client, monkeypatch):
    notes, reads, touched, shown = _left_balances(fake_client, monkeypatch)
    [(title, message, options)] = notes
    assert title == f"Balances saved · {OCTUBRE['name']}"
    assert _plain(message) == STILL_OPEN
    assert options["markup"] is True
    assert touched == []  # the question to complete never shows
    assert reads == 1
    assert type(shown) is Opener  # and nothing opened


def test_balances_refused_after_leaving_give_the_words_couldnt_save_shows(fake_client, monkeypatch):
    notes, reads, touched, _ = _left_balances(fake_client, monkeypatch, refusal=REFUSAL)
    [(title, message, options)] = notes
    assert title == f"Not saved · Statement {OCTUBRE['name']}"
    assert message == list_refusal_text(REFUSAL)
    assert "[not markup]" in message
    assert (options["severity"], options["timeout"], options["markup"]) == ("error", 10, False)
    assert (reads, touched) == (0, [])


# ---- the screen open ---------------------------------------------------------------------


def test_with_the_screen_open_a_complete_still_shows_its_notes_under_the_head(
    fake_client, monkeypatch
):
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.count_bank_lines", lambda *a, **k: 0)
    fake_client.write_responses[COMPLETE_PATH] = ANSWER

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = StatementScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("c")
        await pilot.press("y")
        await wait_for(pilot, lambda: notes, timeout=3)
        assert [(t, m) for t, m, _ in notes] == [("", "Statement completed.")]
        assert screen.query_one("#rwarn").display

    run_app(scenario)
