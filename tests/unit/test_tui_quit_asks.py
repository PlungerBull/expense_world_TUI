"""Quitting (`ctrl+q` anywhere, `q` on Home) asks first while saves are still being sent.

The count is every write sent and not answered, or waiting to be sent and then sent, on any
screen: one still open, or one that has left and carries a `LeftBehind`. A write that is
dropped with its screen is not counted. Only `y` quits.
"""

import threading

import httpx
import pytest
import respx

from expense.tui.screens._base import LeftBehind, pending_writes
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.bank_import import ImportResultScreen
from expense.tui.screens.bulk_pick import BulkPickScreen
from expense.tui.screens.hashtags import HashtagsScreen
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.statement_upload import StatementResultScreen
from expense.tui.screens.transactions import TransactionsScreen
from tests.unit.helpers import (
    ENGINE_URL,
    LateAnswer,
    app_notes,
    run_app,
    stub_home_month,
    wait_for,
    wait_for_list,
    whole,
)
from tests.unit.test_tui_bank_import import (
    CARD_ROWS,
    _bank_file,
    _drop,
    _engine,
    _preview,
    _previewed,
)
from tests.unit.test_tui_bank_import import _open as _open_import
from tests.unit.test_tui_bank_import import _patch as _patch_import
from tests.unit.test_tui_bulk_edit import FILTER, ITEMS, _answer_moves, _open, _stub_ledger
from tests.unit.test_tui_left_behind_account_form import _left_save
from tests.unit.test_tui_log_bar import _open as _open_log
from tests.unit.test_tui_log_bar import _patch as _patch_log
from tests.unit.test_tui_statement_upload import _card_preview, _pdf
from tests.unit.test_tui_statement_upload import _engine as _upload_engine
from tests.unit.test_tui_statement_upload import _patch as _patch_upload

ACCOUNTS = [
    {
        "id": "a1",
        "name": "BCP",
        "is_person": False,
        "is_archived": False,
        "color": None,
        "opening_balance_transaction_id": None,
    }
]
ONE = (
    "1 save is still being sent. Quit anyway?",
    "If you quit now, no screen will tell you whether it was saved.",
)
TWO = (
    "2 saves are still being sent. Quit anyway?",
    "If you quit now, no screen will tell you whether they were saved.",
)


def _scenario(fake_client, monkeypatch, *, writes, leave, then, expect_toasts=True):
    """Open Accounts, send `writes` (each a `run_write` kwargs dict) with the first held
    in flight, leave the screen when `leave`, run `then(pilot, app, screen)`, release the
    held write and return the app's toasts (waited for when `expect_toasts`)."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(ACCOUNTS))
    release = threading.Event()
    sent: list[str] = []
    real_post = fake_client.post

    def post(path, json_body=None):
        sent.append(path)
        if len(sent) == 1:
            release.wait(5)
        return real_post(path, json_body=json_body)

    fake_client.post = post
    out: dict = {}

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        for i, kwargs in enumerate(writes):
            screen.run_write("POST", f"/a/{i}", **kwargs)
        await wait_for(pilot, lambda: sent)
        if leave:
            await pilot.press("escape")
            await wait_for(pilot, lambda: app.screen is not screen)
        try:
            await then(pilot, app, screen)
        finally:
            release.set()
        if expect_toasts:
            await wait_for(pilot, lambda: len(notes) == len(writes), timeout=3)
        out["notes"] = notes

    try:
        run_app(scenario)
    finally:
        release.set()
    return out.get("notes")


def _ending(i: int) -> dict:
    return dict(success=f"Done {i}.", left_behind=LeftBehind(f"Not {i}"))


def _asked(app) -> tuple[str, str]:
    assert isinstance(app.screen, ConfirmModal)
    return app.screen._title, app.screen._message


@pytest.mark.parametrize(("count", "words"), [(1, ONE), (2, TWO)])
def test_ctrl_q_asks_while_a_left_screens_saves_are_unanswered(
    fake_client, monkeypatch, count, words
):
    async def then(pilot, app, screen):
        assert pending_writes(app) == count
        await pilot.press("ctrl+q")
        assert _asked(app) == words
        await pilot.press("ctrl+q")  # a second quit opens no second question
        assert isinstance(app.screen, ConfirmModal)
        await pilot.press("escape")
        assert not isinstance(app.screen, ConfirmModal)
        assert not app._exit

    notes = _scenario(
        fake_client, monkeypatch, writes=[_ending(i) for i in range(count)], leave=True, then=then
    )
    # each write still reports its ending
    assert [m for _, m, _ in notes] == [f"Done {i}." for i in range(count)]


def test_y_quits(fake_client, monkeypatch):
    seen = []

    async def then(pilot, app, screen):
        await pilot.press("ctrl+q")
        await pilot.press("y")
        seen.append(app._exit)

    _scenario(
        fake_client, monkeypatch, writes=[_ending(0)], leave=True, then=then, expect_toasts=False
    )
    assert seen == [True]


@pytest.mark.parametrize("key", ["n", "enter"])
def test_n_and_enter_keep_the_app_and_a_later_quit_asks_again(fake_client, monkeypatch, key):
    async def then(pilot, app, screen):
        await pilot.press("ctrl+q")
        await pilot.press(key)
        assert not app._exit and not isinstance(app.screen, ConfirmModal)
        await pilot.press("ctrl+q")
        assert _asked(app) == ONE
        await pilot.press("n")

    _scenario(fake_client, monkeypatch, writes=[_ending(0)], leave=True, then=then)


def test_nothing_pending_quits_at_once():
    seen = []

    async def scenario(pilot, app):
        assert pending_writes(app) == 0
        await pilot.press("ctrl+q")
        seen.append(app._exit)

    run_app(scenario)
    assert seen == [True]


def test_q_on_home_asks_too(fake_client, monkeypatch):
    seen = []

    async def then(pilot, app, screen):
        await pilot.press("q")
        seen.append(_asked(app))
        await pilot.press("n")

    _scenario(fake_client, monkeypatch, writes=[_ending(0)], leave=True, then=then)
    assert seen == [ONE]


def test_a_write_on_an_open_screen_counts(fake_client, monkeypatch):
    async def then(pilot, app, screen):
        assert pending_writes(app) == 2
        await pilot.press("ctrl+q")
        assert _asked(app) == TWO
        await pilot.press("n")

    _scenario(
        fake_client,
        monkeypatch,
        writes=[dict(), dict(left_behind=LeftBehind("Not one"))],
        leave=False,
        then=then,
        expect_toasts=False,
    )


def test_writes_dropped_with_a_left_screen_are_not_counted(fake_client, monkeypatch):
    seen = []

    async def then(pilot, app, screen):
        seen.append(pending_writes(app))
        await pilot.press("ctrl+q")
        seen.append(app._exit)

    _scenario(
        fake_client,
        monkeypatch,
        # the first has no LeftBehind: dropped on leaving, and the one behind it never sent
        writes=[dict(), dict(left_behind=LeftBehind("Not one"))],
        leave=True,
        then=then,
        expect_toasts=False,
    )
    assert seen == [0, True]


def test_a_save_of_several_writes_counts_once(fake_client, monkeypatch):
    """The account Edit form's account write and two opening balances are one save."""
    seen = []

    async def ask(pilot, app):
        seen.append(pending_writes(app))
        await pilot.press("ctrl+q")
        seen.append(_asked(app))
        await pilot.press("n")

    _left_save(fake_client, monkeypatch, before_release=ask)
    assert seen == [1, ONE]


def test_a_left_queue_counts_up_to_the_first_write_that_is_dropped(fake_client, monkeypatch):
    seen = []

    async def then(pilot, app, screen):
        seen.append(pending_writes(app))

    _scenario(
        fake_client,
        monkeypatch,
        writes=[_ending(0), dict(), _ending(2)],
        leave=True,
        then=then,
        expect_toasts=False,
    )
    assert seen == [1]


def test_a_form_saved_under_the_question_leaves_it_up_and_closes_after_the_answer(
    fake_client, monkeypatch
):
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))
    late = LateAnswer(fake_client, "post")
    seen = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        listing = HashtagsScreen()
        await app.push_screen(listing)
        await wait_for_list(pilot, app)
        edited = []
        monkeypatch.setattr(
            listing, "_load", lambda: edited.append("reloaded")
        )  # the form's callback
        await pilot.press("n")
        form = app.screen
        await wait_for(pilot, lambda: bool(form.query("#bar")))
        form.query_one("#bar").value = "#nuevo"
        form._recompute("#nuevo")
        form.on_input_submitted(None)
        await wait_for(pilot, late.started.is_set)
        await pilot.press("ctrl+q")
        question = app.screen
        assert isinstance(question, ConfirmModal)
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)  # the save is answered
        await pilot.pause()
        seen.append(app.screen is question)  # the question was not popped by the form
        await pilot.press("n")
        await wait_for(pilot, lambda: app.screen is listing)  # the form closed after it
        await wait_for(pilot, lambda: edited)
        await pilot.pause()
        assert len(edited) == 1  # and handed its result back once
        await pilot.press("ctrl+q")  # nothing pending now
        seen.append(app._exit)

    run_app(scenario)
    assert seen == [True, True]


def test_after_a_form_closes_under_the_question_y_still_quits(fake_client, monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))
    late = LateAnswer(fake_client, "post")
    seen = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        await app.push_screen(HashtagsScreen())
        await wait_for_list(pilot, app)
        await pilot.press("n")
        form = app.screen
        await wait_for(pilot, lambda: bool(form.query("#bar")))
        form.query_one("#bar").value = "#nuevo"
        form._recompute("#nuevo")
        form.on_input_submitted(None)
        await wait_for(pilot, late.started.is_set)
        await pilot.press("ctrl+q")
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.press("y")
        seen.append(app._exit)

    run_app(scenario)
    assert seen == [True]


# ---- writes that do not go through run_write -----------------------------------------
def test_the_log_bars_batch_counts_as_one_save(fake_client, monkeypatch):
    """Two staged rows sent by one `ctrl+s` are one save while the batch is unanswered."""
    _patch_log(monkeypatch)
    late = LateAnswer(fake_client, "post")
    seen = []

    async def scenario(pilot, app):
        screen = await _open_log(app, pilot)
        for line in ("tottus -13.50 $BCP", "wong -9.00 $BCP"):
            await pilot.press(*line, "enter")
            await wait_for(pilot, lambda: bar_empty(screen))
        assert len(screen._staged) == 2
        await pilot.press("ctrl+s")
        await wait_for(pilot, late.started.is_set)
        seen.append(pending_writes(app))
        await pilot.press("ctrl+q")
        seen.append(_asked(app))
        await pilot.press("n")
        late.release.set()
        await wait_for(pilot, lambda: not screen._saving)
        seen.append(pending_writes(app))

    run_app(scenario)
    assert seen == [1, ONE, 0]


def bar_empty(screen) -> bool:
    return screen.query_one("#bar").value == ""


def test_a_ledger_bulk_run_counts_as_one_save_after_the_ledger_is_left(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)
    _answer_moves(fake_client, ITEMS)
    late = LateAnswer(fake_client, "put")
    seen = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        screen = TransactionsScreen(filter=FILTER)
        shown = app.screen
        await _open(app, pilot, screen)
        await pilot.press("a", "b")
        await wait_for(pilot, lambda: isinstance(app.screen, BulkPickScreen))
        await pilot.press("o", "r", "o", "enter")
        await wait_for(pilot, late.started.is_set)
        seen.append(pending_writes(app))  # three rows, one save
        await pilot.press("escape", "escape")
        await wait_for(pilot, lambda: app.screen is shown)
        seen.append(pending_writes(app))
        await pilot.press("ctrl+q")
        seen.append(_asked(app))
        await pilot.press("n")
        late.release.set()
        await wait_for(pilot, lambda: notes, timeout=3)  # the receipt still shows
        await wait_for(pilot, lambda: pending_writes(app) == 0)

    run_app(scenario, size=(120, 30))
    assert seen == [1, 1, ONE]


def _import_apply(fake_client, monkeypatch, tmp_path, check):
    """Drop a bank file, preview it, press `⏎` to apply with the apply held unanswered, and
    run `check(pilot, app, release)`."""
    path = _bank_file(tmp_path)
    _patch_import(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})
    real = fake_client.post
    release, applying = threading.Event(), threading.Event()

    def post(path_, json_body=None):
        if json_body and json_body.get("dry_run") is False:
            applying.set()
            release.wait(5)
        return real(path_, json_body=json_body)

    fake_client.post = post

    async def scenario(pilot, app):
        screen = await _open_import(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await wait_for(pilot, applying.is_set)
        try:
            await check(pilot, app, release)
        finally:
            release.set()

    run_app(scenario, size=(120, 40))


def test_an_import_apply_counts_and_its_answer_leaves_the_question_up(
    fake_client, monkeypatch, tmp_path
):
    seen = []

    async def check(pilot, app, release):
        seen.append(pending_writes(app))
        await pilot.press("ctrl+q")
        question = app.screen
        seen.append(_asked(app))
        release.set()
        await wait_for(pilot, lambda: pending_writes(app) == 0)
        await pilot.pause()
        seen.append(app.screen is question)  # the result did not replace the question
        await pilot.press("y")
        seen.append(app._exit)

    _import_apply(fake_client, monkeypatch, tmp_path, check)
    assert seen == [1, ONE, True, True]


def test_an_import_apply_answered_under_the_question_shows_its_result_after_n(
    fake_client, monkeypatch, tmp_path
):
    seen = []

    async def check(pilot, app, release):
        await pilot.press("ctrl+q")
        release.set()
        await wait_for(pilot, lambda: pending_writes(app) == 0)
        await pilot.pause()
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, ImportResultScreen))
        seen.append(app._exit)

    _import_apply(fake_client, monkeypatch, tmp_path, check)
    assert seen == [False]


def test_a_statement_upload_apply_counts_as_one_save(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path)
    _patch_upload(monkeypatch)
    _upload_engine(fake_client, {path.read_bytes(): {"rows": [], "balances": []}})
    real = fake_client.post
    release, applying = threading.Event(), threading.Event()

    def post(path_, json_body=None):
        if json_body and json_body.get("dry_run") is False:
            applying.set()
            release.wait(5)
        return real(path_, json_body=json_body)

    fake_client.post = post
    seen = []

    async def scenario(pilot, app):
        await _card_preview(pilot, app, path)
        await pilot.press("enter")
        await wait_for(pilot, applying.is_set)
        try:
            seen.append(pending_writes(app))
            await pilot.press("ctrl+q")
            question = app.screen
            seen.append(_asked(app))
            release.set()
            await wait_for(pilot, lambda: pending_writes(app) == 0)
            await pilot.pause()
            seen.append(app.screen is question)
            await pilot.press("n")
            await wait_for(pilot, lambda: isinstance(app.screen, StatementResultScreen))
        finally:
            release.set()

    run_app(scenario, size=(120, 50))
    assert seen == [1, ONE, True]


# ---- the save is counted until its ending has been handed back -------------------------
def _recording(monkeypatch, target, name, app_of, into):
    """Wrap `target.name` so the count at the moment it runs (the UI thread) is noted."""
    real = getattr(target, name)

    def wrapper(*args, **kwargs):
        into.append(pending_writes(app_of()))
        return real(*args, **kwargs)

    monkeypatch.setattr(target, name, wrapper)


def test_the_log_bars_batch_is_counted_when_its_ending_is_handed_back(fake_client, monkeypatch):
    _patch_log(monkeypatch)
    seen: list[int] = []

    async def scenario(pilot, app):
        screen = await _open_log(app, pilot)
        _recording(monkeypatch, screen, "_apply_outcome", lambda: app, seen)
        _recording(monkeypatch, screen, "_save_finished", lambda: app, seen)
        await pilot.press(*"tottus -13.50 $BCP", "enter")
        await wait_for(pilot, lambda: bar_empty(screen))
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not screen._saving and len(seen) == 2)
        await wait_for(pilot, lambda: pending_writes(app) == 0)

    run_app(scenario)
    assert seen == [1, 1]


def test_a_bulk_run_is_counted_when_its_ending_is_handed_back(fake_client, monkeypatch):
    _stub_ledger(monkeypatch)
    _answer_moves(fake_client, ITEMS)
    seen: list[int] = []

    async def scenario(pilot, app):
        screen = TransactionsScreen(filter=FILTER)
        await _open(app, pilot, screen)
        _recording(monkeypatch, screen, "_bulk_finished", lambda: app, seen)
        await pilot.press("a", "b")
        await wait_for(pilot, lambda: isinstance(app.screen, BulkPickScreen))
        await pilot.press("o", "r", "o", "enter")
        await wait_for(pilot, lambda: seen)

    run_app(scenario, size=(120, 30))
    assert seen == [1]


def test_an_import_apply_is_counted_when_its_result_is_handed_back(
    fake_client, monkeypatch, tmp_path
):
    from expense.tui.screens.bank_import import ImportPreviewScreen

    seen: list[int] = []
    _recording(monkeypatch, ImportPreviewScreen, "_applied", lambda: seen_app[0], seen)
    seen_app: list = []

    async def check(pilot, app, release):
        seen_app.append(app)
        release.set()
        await wait_for(pilot, lambda: seen)

    _import_apply(fake_client, monkeypatch, tmp_path, check)
    assert seen == [1]


def test_a_statement_apply_is_counted_through_its_count_read_and_hand_back(
    fake_client, monkeypatch, tmp_path
):
    from expense.tui.screens.statement_upload import StatementPreviewScreen

    path = _pdf(tmp_path)
    _patch_upload(monkeypatch)
    _upload_engine(fake_client, {path.read_bytes(): {"rows": [], "balances": []}})
    seen: list[int] = []
    app_box: list = []

    def counted(cfg, *, review_of, **kwargs):
        seen.append(pending_writes(app_box[0]))  # in the worker thread, after the apply
        return 0

    monkeypatch.setattr("expense.reads.count_bank_lines", counted)
    _recording(monkeypatch, StatementPreviewScreen, "_applied", lambda: app_box[0], seen)

    async def scenario(pilot, app):
        app_box.append(app)
        await _card_preview(pilot, app, path)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, StatementResultScreen))

    run_app(scenario, size=(120, 50))
    assert seen == [1, 1]


# ---- screens that close themselves under the question ------------------------------------
def _log_bar_save_first(fake_client, monkeypatch, after):
    """Stage a row, `esc`, `ctrl+s save first` with the batch held, `ctrl+q`, let the batch
    land (the bar then wants to leave), and run `after(pilot, app, bar, question)`."""
    _patch_log(monkeypatch)
    late = LateAnswer(fake_client, "post")

    async def scenario(pilot, app):
        shown = app.screen
        bar = await _open_log(app, pilot)
        await pilot.press(*"tottus -13.50 $BCP", "enter")
        await wait_for(pilot, lambda: bar_empty(bar))
        await pilot.press("escape")
        await pilot.press("ctrl+s")
        await wait_for(pilot, late.started.is_set)
        await pilot.press("ctrl+q")
        question = app.screen
        assert isinstance(question, ConfirmModal)
        late.release.set()
        await wait_for(pilot, lambda: pending_writes(app) == 0)
        await pilot.pause()
        assert app.screen is question and bar in app.screen_stack  # the bar did not close yet
        await after(pilot, app, bar, shown)

    run_app(scenario)


def test_the_log_bar_closes_after_n_when_it_finished_under_the_question(fake_client, monkeypatch):
    seen = []

    async def after(pilot, app, bar, shown):
        await pilot.press("n")
        await wait_for(pilot, lambda: bar not in app.screen_stack)
        seen.append((app.screen is shown, app._exit))

    _log_bar_save_first(fake_client, monkeypatch, after)
    assert seen == [(True, False)]


def test_y_quits_when_the_log_bar_finished_under_the_question(fake_client, monkeypatch):
    seen = []

    async def after(pilot, app, bar, shown):
        await pilot.press("y")
        seen.append((app._exit, bar in app.screen_stack))

    _log_bar_save_first(fake_client, monkeypatch, after)
    assert seen[0][0] is True


def _setup_created_under_the_question(monkeypatch, answer):
    """First-time setup creating its profile, the answer held; `ctrl+q`; the answer lands;
    then `answer` is pressed. Returns `(toasts, the screen after, exited)`."""
    from tests.unit.test_tui_setup import (
        ME,
        _no_profile_yet,
        _type,
        _until_name,
    )

    monkeypatch.setattr("expense.dates.detect_timezone", lambda *a, **k: "America/Lima")
    stub_home_month(monkeypatch)
    release, asked = threading.Event(), threading.Event()
    out: dict = {}

    def bootstrap(request):
        asked.set()
        release.wait(5)
        return httpx.Response(200, json=ME)

    async def scenario(pilot, app):
        notes: list = []
        app.notify = lambda message, **kw: notes.append(message)
        screen = app.screen
        await _until_name(pilot, screen)
        await _type(pilot, screen, "Alex")
        await pilot.press("enter")
        await wait_for(pilot, asked.is_set)
        await pilot.press("ctrl+q")
        question = app.screen
        assert isinstance(question, ConfirmModal)
        release.set()
        await wait_for(pilot, lambda: pending_writes(app) == 0)
        await pilot.pause()
        assert app.screen is question and notes == []  # nothing closed, nothing said yet
        await pilot.press(answer)
        await pilot.pause()
        if answer == "n":
            await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        out.update({"toasts said": list(notes), "app exited": app._exit})

    with respx.mock:
        _no_profile_yet()
        respx.post(f"{ENGINE_URL}/v1/auth/bootstrap").mock(side_effect=bootstrap)
        run_app(scenario, setup=True)
    return out


def test_setup_closes_and_says_connected_after_n(monkeypatch):
    out = _setup_created_under_the_question(monkeypatch, "n")
    assert out == {"toasts said": ["Connected."], "app exited": False}


def test_y_quits_when_setup_finished_under_the_question(monkeypatch):
    out = _setup_created_under_the_question(monkeypatch, "y")
    assert out == {"toasts said": [], "app exited": True}
