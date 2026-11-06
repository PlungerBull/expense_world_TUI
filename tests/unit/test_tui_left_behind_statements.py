"""A statement's own writes finish after their screen has left (`left_behind`).

The New statement form's `POST /statements`, the ticks of the statement screen (`space`:
one `PUT /transactions/{part}` each), its revert (`u`) and its delete (`d`). Left with the
engine still answering, a write ends as a toast on the app: the screen's own success words
(a tick that lands shows none), or its own refusal words under what did not happen, for 10
seconds. Ticks still waiting are all sent, a refusal stopping none. The screen that opened
the one left, when it is the one shown, reads again. The queue itself is in test_tui_writes.py.
"""

import threading

import pytest
from textual.screen import Screen

from expense.errors import EngineError, format_error
from expense.tui.screens._base import list_refusal_text
from expense.tui.screens.statements import NewStatementScreen, StatementScreen
from tests.unit.helpers import LateAnswer, app_notes, cursor_page, run_app, wait_for
from tests.unit.test_tui_bulk_edit import _plain
from tests.unit.test_tui_statement_detail import DRAFT, UBER, _patch, _wait_list

pytestmark = pytest.mark.usefixtures("no_flagged_lines")

REFUSAL = EngineError("CONFLICT", "stand-in [not markup]", None, 409, {})
NAME = DRAFT["name"]
LAST = "Nothing was saved: open it again to fix it."


class Opener(Screen):
    """Stands for the screen that opened the one left; `reload` is how it reads again."""

    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    def reload(self) -> None:
        self.reads += 1


async def _leave(pilot, app, screen, opener, elsewhere: bool) -> None:
    await app.pop_screen()  # left: popped, so its dismiss callback never runs
    await wait_for(pilot, lambda: app.screen is opener)
    if elsewhere:
        await app.push_screen(Screen())
        await wait_for(pilot, lambda: app.screen is not opener)


# ---- the new statement -----------------------------------------------------------


def _enter(screen, text):
    screen.query_one("#bar").value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


def _left_new(fake_client, monkeypatch, refusal=None, elsewhere=False, name="Abril 2026"):
    late = LateAnswer(fake_client, "post", refusal)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        opener, created = Opener(), []
        await app.push_screen(opener)
        screen = NewStatementScreen(
            account_id="acc1",
            account_name="BCP",
            currencies=(),
            opener=opener,
            created=created.append,
        )
        await app.push_screen(screen)
        _enter(screen, name)
        _enter(screen, "2026-04-01")
        _enter(screen, "2026-04-30")  # the last line: submits
        await wait_for(pilot, late.started.is_set)
        await _leave(pilot, app, screen, opener, elsewhere)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.pause()
        result.extend([notes, created, screen._new_id])

    run_app(scenario)
    return result


def test_a_new_statement_answered_after_leaving_says_it_was_created(fake_client, monkeypatch):
    notes, created, new_id = _left_new(fake_client, monkeypatch)
    assert [(title, message) for title, message, _ in notes] == [("", "Statement created.")]
    assert created == [new_id]  # the opener is the screen shown: its panel opens on it


def test_a_new_statement_answered_elsewhere_opens_nothing(fake_client, monkeypatch):
    notes, created, _ = _left_new(fake_client, monkeypatch, elsewhere=True)
    assert [message for _, message, _ in notes] == ["Statement created."]
    assert created == []


def test_a_refused_new_statement_names_what_was_not_created(fake_client, monkeypatch):
    notes, created, _ = _left_new(fake_client, monkeypatch, REFUSAL)
    [(title, message, options)] = notes
    assert title == "Not created · Statement Abril 2026"
    assert _plain(message) == f"{format_error(REFUSAL)}\n{LAST}"
    assert "[not markup]" in _plain(message)
    assert (options["severity"], options["timeout"], options["markup"]) == ("error", 10, True)
    assert created == []


# ---- the ticks ----------------------------------------------------------------------

#: The statement's lines in the order the list shows them: NETFLIX (ticked), UBER, FARMACIA.
TICKS = [  # (row, the part it sends on)
    (0, "/transactions/t1"),
    (1, "/transactions/t3"),
    (2, "/transactions/t2a"),
]


def _left_ticks(fake_client, monkeypatch, refusals=None, *, elsewhere=False, quit_app=False):
    """Untick NETFLIX, tick UBER and FARMACIA, leave while the first waits, let all three
    answer, and return `(the app's toasts, the paths sent, the opener's reads, what the
    left screen was asked to touch)`."""
    _patch(monkeypatch)
    refusals = refusals or {}
    release, started, last = threading.Event(), threading.Event(), threading.Event()
    first_answered = threading.Event()
    sent: list[str] = []

    def put(path, json_body=None):
        sent.append(path)
        if len(sent) == 1:
            started.set()
            release.wait(5)
        if len(sent) == len(TICKS):
            last.set()
        if len(sent) == 1:
            first_answered.set()
        if path in refusals:
            raise refusals[path]
        return {}

    fake_client.put = put
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        opener = Opener()
        await app.push_screen(opener)
        screen = StatementScreen(dict(DRAFT), opener=opener, reload=opener.reload)
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        for row, _path in TICKS:
            screen._list._cursor = row
            await pilot.press("space")
        await wait_for(pilot, started.is_set)
        touched: list[str] = []
        monkeypatch.setattr(screen, "_load_txns", lambda *a, **k: touched.append("read"))
        monkeypatch.setattr(screen, "notify", lambda *a, **k: touched.append("toast"))
        await _leave(pilot, app, screen, opener, elsewhere)
        if quit_app:
            app.exit()
        release.set()
        if quit_app:
            await wait_for(pilot, first_answered.is_set, timeout=3)
        else:
            await wait_for(pilot, last.is_set, timeout=3)
            await wait_for(pilot, lambda: not screen.writes_unanswered(), timeout=3)
        await pilot.pause()
        result.extend([notes, sent, opener.reads, touched])

    run_app(scenario)
    return result


def test_ticks_answered_after_leaving_show_nothing_and_the_opener_reads_once(
    fake_client, monkeypatch
):
    notes, sent, reads, touched = _left_ticks(fake_client, monkeypatch)
    assert sent == [path for _, path in TICKS]
    assert notes == []  # a tick that lands shows nothing, as on the screen
    assert reads == 1  # after the last one, not after each
    assert touched == []


def test_every_tick_still_waiting_is_sent_and_a_refusal_stops_none(fake_client, monkeypatch):
    notes, sent, reads, touched = _left_ticks(
        fake_client, monkeypatch, {"/transactions/t3": REFUSAL}
    )
    assert sent == [path for _, path in TICKS]  # the one after the refused one still goes
    [(title, message, options)] = notes
    assert title == "Not ticked · UBER *TRIP · -42.00"
    assert message == list_refusal_text(REFUSAL)
    assert "[not markup]" in message
    assert (options["severity"], options["timeout"], options["markup"]) == ("error", 10, False)
    assert reads == 1
    assert touched == []


def test_each_refused_tick_has_its_own_message(fake_client, monkeypatch):
    refusals = {"/transactions/t1": REFUSAL, "/transactions/t2a": REFUSAL}
    notes, _, reads, _ = _left_ticks(fake_client, monkeypatch, refusals)
    assert [title for title, _, _ in notes] == [
        "Not unticked · NETFLIX.COM · -44.90",  # a line taken out is an untick
        "Not ticked · FARMACIA · -100.00",
    ]
    assert reads == 1  # the last answer, refused, still reads the panel again


def test_an_income_line_is_named_with_its_plus(fake_client, monkeypatch):
    income = {**UBER, "net_cents": 5000, "parts": [{**UBER["parts"][0], "amount_cents": 5000}]}
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_bank_lines",
        lambda cfg, **k: cursor_page([] if k.get("statement") else [income]),
    )
    late = LateAnswer(fake_client, "put", REFUSAL)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        opener = Opener()
        await app.push_screen(opener)
        screen = StatementScreen(dict(DRAFT), opener=opener, reload=opener.reload)
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press("space")
        await _leave(pilot, app, screen, opener, False)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        result.extend(notes)

    run_app(scenario)
    assert result[0][0] == "Not ticked · UBER *TRIP · +50.00"


def test_ticks_answered_elsewhere_read_nothing(fake_client, monkeypatch):
    notes, sent, reads, touched = _left_ticks(
        fake_client, monkeypatch, {"/transactions/t3": REFUSAL}, elsewhere=True
    )
    assert sent == [path for _, path in TICKS]
    assert [title for title, _, _ in notes] == ["Not ticked · UBER *TRIP · -42.00"]
    assert reads == 0
    assert touched == []


def test_quitting_mid_run_shows_nothing_more(fake_client, monkeypatch):
    notes, sent, reads, touched = _left_ticks(
        fake_client, monkeypatch, {"/transactions/t3": REFUSAL}, quit_app=True
    )
    assert notes == []
    assert sent == [TICKS[0][1]]  # what was already running goes; nothing behind it is sent
    assert touched == []


def test_with_the_screen_open_a_refused_tick_still_resyncs_and_says_couldnt_update(
    fake_client, monkeypatch
):
    _patch(monkeypatch)
    fake_client.errors["PUT"] = REFUSAL

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = StatementScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        first = screen._list
        await pilot.press("space")
        await wait_for(pilot, lambda: notes)
        await wait_for(pilot, lambda: screen._list is not first)
        assert [(title, message) for title, message, _ in notes] == [
            ("Couldn't update", list_refusal_text(REFUSAL))
        ]

    run_app(scenario)


# ---- revert and delete --------------------------------------------------------------

#: (the keys, the verb of the write, its success words, what did not happen, its words)
STATUS = {
    "revert it": ("u", "post", "Statement reverted to draft.", "Not reverted", format_error),
    "delete it": ("d", "delete", "Statement deleted.", "Not deleted", list_refusal_text),
}


def _left_status(fake_client, monkeypatch, action, refusal=None, elsewhere=False):
    key, verb, *_ = STATUS[action]
    _patch(monkeypatch)
    late = LateAnswer(fake_client, verb, refusal)
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        opener = Opener()
        await app.push_screen(opener)
        screen = StatementScreen(dict(DRAFT), opener=opener, reload=opener.reload)
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press(key)
        await pilot.press("y")
        await wait_for(pilot, late.started.is_set)
        touched: list[str] = []
        monkeypatch.setattr(screen, "_load_txns", lambda *a, **k: touched.append("read"))
        monkeypatch.setattr(screen, "notify", lambda *a, **k: touched.append("toast"))
        await _leave(pilot, app, screen, opener, elsewhere)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.pause()
        assert touched == []  # nothing of the left screen was touched
        result.extend([notes, opener.reads])

    run_app(scenario)
    return result


@pytest.mark.parametrize("action", sorted(STATUS))
def test_a_status_write_answered_after_leaving_shows_its_success_words(
    fake_client, monkeypatch, action
):
    notes, reads = _left_status(fake_client, monkeypatch, action)
    assert [(title, message) for title, message, _ in notes] == [("", STATUS[action][2])]
    assert reads == 1  # the opener is the screen shown: it reads again


@pytest.mark.parametrize("action", sorted(STATUS))
def test_a_status_write_refused_after_leaving_names_the_statement(fake_client, monkeypatch, action):
    *_, not_done, words = STATUS[action]
    notes, reads = _left_status(fake_client, monkeypatch, action, REFUSAL)
    [(title, message, options)] = notes
    assert title == f"{not_done} · Statement {NAME}"
    assert message == words(REFUSAL)
    assert "[not markup]" in message
    assert (options["severity"], options["timeout"], options["markup"]) == ("error", 10, False)
    assert reads == 0  # a refusal changed nothing: no read


@pytest.mark.parametrize("action", sorted(STATUS))
def test_a_status_write_answered_elsewhere_reads_nothing(fake_client, monkeypatch, action):
    notes, reads = _left_status(fake_client, monkeypatch, action, elsewhere=True)
    assert [message for _, message, _ in notes] == [STATUS[action][2]]
    assert reads == 0


@pytest.mark.parametrize(
    ("action", "title"), [("revert it", "Couldn't revert"), ("delete it", "Couldn't delete")]
)
def test_with_the_screen_open_a_refused_status_write_keeps_its_title(
    fake_client, monkeypatch, action, title
):
    key, verb, *_ = STATUS[action]
    _patch(monkeypatch)
    LateAnswer(fake_client, verb, REFUSAL).release.set()

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = StatementScreen(dict(DRAFT))
        await app.push_screen(screen)
        await _wait_list(screen, pilot)
        await pilot.press(key)
        await pilot.press("y")
        await wait_for(pilot, lambda: notes, timeout=3)
        assert [t for t, _, _ in notes] == [title]
        assert app.screen is screen  # a refused delete does not close it

    run_app(scenario)
