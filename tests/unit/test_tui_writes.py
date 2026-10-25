"""Write-worker isolation / content-swap serialization on a SectionScreen.

Uses a fake HTTP client so nothing real is mutated. They call `run_write` on
the Accounts list directly — the mixin is what is under test, not any one screen's keys. Manage-list
archive itself is covered in test_tui_manage_actions.py.
"""

import asyncio
import threading

from expense.tui.screens.accounts import AccountsScreen
from tests.unit.helpers import run_app, wait_for, wait_for_list, whole

ACCOUNTS = [
    {
        "id": "a1",
        "name": "BCP",
        "is_person": False,
        "is_archived": False,
        "color": None,
        "statement_code": None,
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
