"""Write-worker isolation / content-swap serialization on a SectionScreen.

Uses a fake HTTP client so nothing real is mutated. They call `run_write` on
the Accounts list directly — the mixin is what is under test, not any one screen's keys. Manage-list
archive itself is covered in test_tui_manage_actions.py.
"""

import asyncio
import threading

from expense.errors import EngineError
from expense.tui.screens.accounts import AccountsScreen
from tests.unit.helpers import run_app, wait_for, wait_for_list, whole

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


def _stub_accounts(monkeypatch):
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(ACCOUNTS))


def test_refresh_mid_write_does_not_cancel_the_write(fake_client, monkeypatch):
    """`r` mid-write must not cancel the engine-write worker.

    run_write and _load must not share an exclusive group, or a refresh or
    theme change cancels an in-flight write worker. Exercised on
    a SectionScreen list write + the inherited `r` refresh.
    """
    _stub_accounts(monkeypatch)
    real_post = fake_client.post
    release = threading.Event()

    def gated_post(path, json_body=None):
        # Hold the write in flight until the test releases it. A fixed sleep is
        # racy: pilot.press awaits Textual's CPU-idleness heuristic, which on a
        # busy runner doesn't return until the whole write (sleep + reload)
        # has finished, so the engine-write worker is already gone by
        # the time we snapshot app.workers. The gate makes the window definite.
        release.wait(2.0)
        return real_post(path, json_body=json_body)

    fake_client.post = gated_post

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)

        await wait_for_list(pilot, app)
        screen.run_write("POST", "/accounts/a1/archive", on_success=lambda: None)
        # Poll (don't snapshot) until the write worker registers — it's
        # blocked in gated_post, so this state is stable, not fleeting.
        await wait_for(
            pilot,
            lambda: [w for w in app.workers if w.group == "engine-write"],
            message="write worker not running in its own group",
        )
        write_worker = next(w for w in app.workers if w.group == "engine-write")
        await pilot.press("r")  # refresh while the write is in flight
        await pilot.pause()  # let the refresh keypress settle, then assert a non-event
        assert not write_worker.is_cancelled, "refresh cancelled the in-flight write"
        release.set()  # let the gated write complete
        await wait_for(pilot, lambda: fake_client.calls)
        assert not write_worker.is_cancelled

    try:
        run_app(scenario)
    finally:
        release.set()  # never leave the worker thread blocked on the gate
    assert ("POST", "/accounts/a1/archive") in fake_client.requests


def test_rapid_writes_serialize_in_order(fake_client, monkeypatch):
    """Two immediate run_writes on any screen send both, one at a time, in
    order — the mixin-level generalization of the checklist-toggle queue."""
    import time

    _stub_accounts(monkeypatch)

    active = 0
    max_active = 0
    lock = threading.Lock()
    real_post = fake_client.post

    def slow_post(path, json_body=None):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.08)  # wide enough that overlapping POSTs would be caught
        with lock:
            active -= 1
        return real_post(path, json_body=json_body)

    fake_client.post = slow_post

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)

        await wait_for_list(pilot, app)
        screen.run_write("POST", "/accounts/a1/archive", on_success=lambda: None)
        screen.run_write("POST", "/accounts/a1/unarchive", on_success=lambda: None)
        await wait_for(pilot, lambda: len(fake_client.posts) == 2)

    run_app(scenario)
    assert max_active == 1  # serialized: never two writes in flight
    assert [p for p, _ in fake_client.posts] == ["/accounts/a1/archive", "/accounts/a1/unarchive"]


def test_concurrent_content_swaps_mount_one_card(fake_client, monkeypatch):
    """Two loads landing together must swap #content atomically.

    _show suspends between remove_children and mount; unserialized, the
    interleave mounts a second '#card' (DuplicateIds) and kills the load
    worker — seen on slow CI runners as a refresh raced a post-write reload.
    """
    _stub_accounts(monkeypatch)

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)

        await wait_for_list(pilot, app)
        await asyncio.gather(screen._show(ACCOUNTS), screen._show(ACCOUNTS))
        assert len(screen.query("#card")) == 1

    run_app(scenario)


def test_on_response_hands_over_the_body_before_on_success(fake_client, monkeypatch):
    """`run_write(on_response=…)` sees the engine's own body.

    Order is the assertion: a screen that reads the body repaints from it in
    `on_success`, so the body must already be in hand by then. The hook is
    opt-in — every callsite that passes only `on_success` is unaffected, which
    the rest of this file exercises.
    """
    _stub_accounts(monkeypatch)
    fake_client.write_responses["/accounts/a1/archive"] = {"id": "a1", "warnings": ["mind the gap"]}
    seen: list = []

    async def scenario(pilot, app):
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        screen.run_write(
            "POST",
            "/accounts/a1/archive",
            on_response=lambda body: seen.append(body.get("warnings")),
            on_success=lambda: seen.append("success"),
        )
        await wait_for(pilot, lambda: len(seen) == 2)
        assert seen == [["mind the gap"], "success"]

    run_app(scenario)


def _left_screen_scenario(fake_client, monkeypatch, writes, *, leave=True, toasts=None):
    """Open Accounts, queue `writes` (each `(path, kwargs)`) with the first held
    in flight, leave the screen (when `leave`), release it, and return
    `(sent paths, the app's toasts, the screen)`. `toasts` is how many
    toasts the app shows once every answer is in (default: one per write)."""
    _stub_accounts(monkeypatch)
    release = threading.Event()
    real_post = fake_client.post
    sent: list[str] = []
    answered = threading.Event()  # the first write's engine call has returned

    def post(path, json_body=None):
        sent.append(path)
        if len(sent) == 1:
            release.wait(5)
            answered.set()
        if "bad" in path:
            raise EngineError("CONFLICT", "no", None, 409, {})
        return real_post(path, json_body=json_body)

    fake_client.post = post
    notes: list[tuple[str, str, dict]] = []
    out: dict = {}
    expected = len(writes) if toasts is None else toasts

    async def scenario(pilot, app):
        monkeypatch.setattr(
            app, "notify", lambda m, title="", **o: notes.append((title, str(m), o))
        )
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        for path, kwargs in writes:
            screen.run_write("POST", path, **kwargs)
        await wait_for(pilot, lambda: sent)
        if leave:
            await pilot.press("escape")
            await wait_for(pilot, lambda: app.screen is not screen)
        release.set()
        await wait_for(pilot, lambda: len(notes) == expected, timeout=3)
        await wait_for(pilot, lambda: answered.is_set(), timeout=3)
        await pilot.pause()
        out["screen"] = screen

    run_app(scenario)
    return sent, notes, out["screen"]


def test_writes_queued_behind_a_left_screens_write_are_sent_and_shown(fake_client, monkeypatch):
    sent, notes, _ = _left_screen_scenario(
        fake_client,
        monkeypatch,
        [
            ("/a/one", dict(success="One done.", left_behind="Not one")),
            ("/a/bad", dict(success="x", left_behind="Not bad")),
            ("/a/three", dict(success="Three done.", left_behind="Not three")),
        ],
    )
    assert sent == ["/a/one", "/a/bad", "/a/three"]  # a refusal stopped none after it
    assert [(t, m) for t, m, _ in notes[:1]] == [("", "One done.")]
    assert notes[1][0] == "Not bad" and notes[1][1].startswith("CONFLICT")
    assert notes[1][2]["timeout"] == 10 and notes[1][2]["markup"] is False
    assert (notes[2][0], notes[2][1]) == ("", "Three done.")


def test_a_write_without_left_behind_words_is_dropped_after_leaving(fake_client, monkeypatch):
    sent, notes, _ = _left_screen_scenario(
        fake_client,
        monkeypatch,
        [("/a/one", dict(success="One done.")), ("/a/two", dict(left_behind="Not two"))],
        toasts=0,
    )
    assert sent == ["/a/one"]  # answered nobody, and the one behind it never went
    assert notes == []


def test_with_the_screen_open_a_refusal_still_drops_the_queue(fake_client, monkeypatch):
    sent, notes, screen = _left_screen_scenario(
        fake_client,
        monkeypatch,
        [
            ("/a/bad", dict(left_behind="Not bad")),
            ("/a/two", dict(left_behind="Not two")),
        ],
        leave=False,
        toasts=1,
    )
    assert sent == ["/a/bad"]
    assert [(t, m[:8]) for t, m, _ in notes] == [("Failed", "CONFLICT")]


def test_quitting_mid_run_sends_and_shows_nothing_more(fake_client, monkeypatch):
    _stub_accounts(monkeypatch)
    release = threading.Event()
    sent: list[str] = []
    done = threading.Event()
    real_post = fake_client.post

    def post(path, json_body=None):
        sent.append(path)
        if len(sent) == 1:
            release.wait(5)
            done.set()
        return real_post(path, json_body=json_body)

    fake_client.post = post
    notes: list = []

    async def scenario(pilot, app):
        monkeypatch.setattr(app, "notify", lambda m, title="", **o: notes.append(m))
        screen = AccountsScreen()
        await app.push_screen(screen)
        await wait_for_list(pilot, app)
        screen.run_write("POST", "/a/one", left_behind="Not one")
        screen.run_write("POST", "/a/two", left_behind="Not two")
        await wait_for(pilot, lambda: sent)
        app.exit()
        release.set()
        await wait_for(pilot, lambda: done.is_set())
        await pilot.pause()

    run_app(scenario)
    assert sent == ["/a/one"]
    assert notes == []
