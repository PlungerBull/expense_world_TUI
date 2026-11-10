"""The Edit forms finish after they have been left (`left_behind`).

The ledger's form (`EditFormScreen`) and the "no statement" list's
(`BankLineEditFormScreen`), saved with one `PUT /bank-lines/{id}`. Left (esc) before the
engine answers, the answer ends as a toast on the app: `Saved.` or `Saved. It left its
statement.` by the answer's body, or the form's refusal words under `Not saved · TITLE ·
AMOUNT` ending `Nothing was saved: open it again to fix it.`; and the screen that opened the
form, when it is the one shown, reads again. The queue is in test_tui_writes.py.
"""

import pytest
from textual.screen import Screen

from expense.errors import EngineConnectionError, EngineError, app_lines, format_error
from expense.reads import AccountIndex
from expense.tui.screens.edit_form import BankLineEditFormScreen, EditFormScreen
from expense.tui.screens.transactions import TransactionsScreen
from expense.tui.widgets.cursor_list import CursorList
from expense.tui.widgets.parts_table import refusal_text
from tests.unit.helpers import (
    LateAnswer,
    app_notes,
    fake_ledger,
    run_app,
    wait_for,
    wait_for_list,
)
from tests.unit.test_tui_edit_form import (
    BANK_LINE,
    PATH,
    TXN,
    _enter,
    _line,
    _moved,
    _on,
    _patch,
    _wait_loaded,
)
from tests.unit.test_tui_left_behind_statements import Opener

LAST = "Nothing was saved: open it again to fix it."
INCOME = {**TXN, "amount_cents": 4250}
FORMS = {
    "ledger form": (
        lambda opener, reload: EditFormScreen(record=TXN, opener=opener, reload=reload)
    ),
    "income form": (
        lambda opener, reload: EditFormScreen(record=INCOME, opener=opener, reload=reload)
    ),
    "line form": (
        lambda opener, reload: BankLineEditFormScreen(line=BANK_LINE, opener=opener, reload=reload)
    ),
}
#: The two screens: one case each for what they share.
SCREENS = ["ledger form", "line form"]
FIRST_LINE = {
    "ledger form": "Not saved · Farmacia · -42.50",
    "income form": "Not saved · Farmacia · +42.50",
    "line form": "Not saved · FARMACIA · -42.50",
}

REFUSED_PART = EngineError(
    "VALIDATION_ERROR",
    "The parts do not add up [to the total]",
    {"parts.1.amount_cents": "must be [negative]"},
    422,
    {},
)
UNAUTHORIZED = EngineError(
    "UNAUTHORIZED",
    "The key [is] not valid.",
    {"parts.0.amount_cents": "must [not] be zero"},
    401,
    {},
)
SERVER_ERROR = EngineError("INTERNAL_ERROR", "Something went wrong [on our side].", None, 500, {})


def _left_form(
    fake_client, monkeypatch, form: str, *, refusal=None, answer=None, elsewhere=False
) -> tuple[list, int]:
    """Open `form` from an `Opener`, change its title, save, leave the form before the
    engine answers, let it answer, and return `(the app's toasts, the opener's reads)`.
    With `elsewhere`, another screen than the opener is the one shown when it answers."""
    _patch(
        monkeypatch,
        BANK_LINE if form == "line form" else _line(INCOME if form == "income form" else TXN),
    )
    if answer is not None:
        fake_client.write_responses[PATH] = answer
    late = LateAnswer(fake_client, "put", refusal)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        opener = Opener()
        await app.push_screen(opener)
        screen = FORMS[form](opener, opener.reload)
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        _on(screen, "title")
        _enter(screen, "Otro")
        screen.action_submit()
        await wait_for(pilot, late.started.is_set)
        await app.pop_screen()  # left: popped, so its dismiss callback never runs
        await wait_for(pilot, lambda: app.screen is opener)
        if elsewhere:
            await app.push_screen(Screen())
            await wait_for(pilot, lambda: app.screen is not opener)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.pause()
        result.extend([notes, opener.reads])

    run_app(scenario)
    return result[0], result[1]


@pytest.mark.parametrize(
    ("form", "changed", "words"),
    [
        pytest.param(
            "ledger form", [_moved(TXN, left=True)], "Saved. It left its statement.", id="left"
        ),
        pytest.param("ledger form", [_moved(TXN, left=False)], "Saved.", id="stayed"),
        pytest.param("ledger form", [], "Saved.", id="none-listed"),
        pytest.param(
            "line form", [_moved(TXN, left=True)], "Saved. It left its statement.", id="line-left"
        ),
    ],
)
def test_a_save_answered_after_leaving_says_what_the_answer_says(
    fake_client, monkeypatch, form, changed, words
):
    notes, reads = _left_form(
        fake_client, monkeypatch, form, answer={**_line(TXN), "changed_parts": changed}
    )
    assert [(title, message) for title, message, _ in notes] == [("", words)]
    assert reads == 1  # the opener is the screen shown: it reads again


@pytest.mark.parametrize("form", sorted(FORMS))
def test_a_refused_save_after_leaving_names_the_line_and_keeps_the_part_lines(
    fake_client, monkeypatch, form
):
    notes, reads = _left_form(fake_client, monkeypatch, form, refusal=REFUSED_PART)
    [(title, message, options)] = notes
    assert title == FIRST_LINE[form]
    words = (
        "VALIDATION_ERROR — The parts do not add up \\[to the total]\n"
        "! part 2 (amount): must be \\[negative]"
    )
    assert message == f"{words}\n[dim]{LAST}"  # the engine's brackets never read as markup
    assert options["severity"] == "error"
    assert options["timeout"] == 10
    assert options["markup"] is True
    assert reads == 0  # a refusal changed nothing


@pytest.mark.parametrize("form", SCREENS)
def test_a_save_refused_with_a_5xx_after_leaving_ends_with_no_last_line(
    fake_client, monkeypatch, form
):
    notes, reads = _left_form(fake_client, monkeypatch, form, refusal=SERVER_ERROR)
    [(title, message, options)] = notes
    assert title == FIRST_LINE[form]
    assert message == refusal_text(SERVER_ERROR)  # as sent, `[on our side]` and all
    assert "Nothing was saved" not in message
    assert options["markup"] is False
    assert options["timeout"] == 10
    assert reads == 0


def test_a_failure_that_is_no_answer_shows_the_forms_error_text_without_a_last_line(
    fake_client, monkeypatch
):
    down = EngineConnectionError(url="https://x.invalid", original=Exception("refused"))
    notes, reads = _left_form(fake_client, monkeypatch, "ledger form", refusal=down)
    assert [(title, message) for title, message, _ in notes] == [
        (FIRST_LINE["ledger form"], format_error(down))
    ]
    assert reads == 0


@pytest.mark.parametrize("form", SCREENS)
def test_a_save_answered_after_leaving_for_another_screen_reads_nothing_more(
    fake_client, monkeypatch, form
):
    notes, reads = _left_form(fake_client, monkeypatch, form, elsewhere=True)
    assert [message for _, message, _ in notes] == ["Saved."]
    assert reads == 0


@pytest.mark.parametrize("form", SCREENS)
def test_a_refusal_with_the_apps_line_after_leaving_keeps_the_blank_line_then_the_last_line(
    fake_client, monkeypatch, form
):
    notes, _ = _left_form(fake_client, monkeypatch, form, refusal=UNAUTHORIZED)
    [(title, message, options)] = notes
    assert title == FIRST_LINE[form]
    [hint] = app_lines(UNAUTHORIZED)
    assert message == (
        "UNAUTHORIZED — The key \\[is] not valid.\n"
        "! part 1 (amount): must \\[not] be zero\n"
        f"\n{hint}\n"
        f"[dim]{LAST}"
    )
    assert options["markup"] is True


def test_the_ledger_form_left_before_its_save_answers_starts_the_ledger_over(
    fake_client, monkeypatch
):
    """The real caller: `⏎` on a ledger row, esc, the answer: the newest 10 again, the
    cursor on row 1."""
    import expense.tui.screens.transactions as tx_mod
    from tests.unit.test_tui_transactions import ACCOUNTS, CATEGORIES, HASHTAGS, ITEMS

    rows = [ITEMS[0], {**ITEMS[0], "id": "t9", "title": "Otra fila"}]
    reads, _ = fake_ledger(monkeypatch, rows)
    monkeypatch.setattr(tx_mod, "load_account_index", lambda: AccountIndex(ACCOUNTS))
    monkeypatch.setattr(tx_mod, "load_category_name_map", lambda: CATEGORIES)
    monkeypatch.setattr(tx_mod, "load_hashtag_name_map", lambda: HASHTAGS)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    _patch(monkeypatch, _line({**TXN, "id": "t9"}))
    late = LateAnswer(fake_client, "put", None)

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        ledger = TransactionsScreen()
        await app.push_screen(ledger)
        await wait_for_list(pilot, app)
        listing = ledger.query_one(CursorList)
        listing.set_cursor(listing.index_of("t9"))
        await pilot.press("enter")
        form = app.screen
        assert isinstance(form, EditFormScreen)
        await _wait_loaded(form, pilot)
        _on(form, "title")
        _enter(form, "Otro")
        form.action_submit()
        await wait_for(pilot, late.started.is_set)
        await app.pop_screen()
        await wait_for(pilot, lambda: app.screen is ledger)
        await wait_for_list(pilot, app)
        before = len(reads)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await wait_for(pilot, lambda: len(reads) > before, timeout=3)
        await wait_for_list(pilot, app)
        assert [message for _, message, _ in notes] == ["Saved."]
        assert ledger.query_one(CursorList).cursor_key == "t1"  # row 1

    run_app(scenario, size=(160, 30))
