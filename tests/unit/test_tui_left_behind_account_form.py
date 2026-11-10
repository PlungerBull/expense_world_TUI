"""The account Edit form finishes its save after it has been left.

A save is one `PUT /accounts/{id}`. Left (esc) while it is unanswered, it still goes and
its answer shows on the app: `Saved.`, or an error toast titled `Not saved · Account <name>`
with the engine's words and, for a refusal under 500, a dim last line saying nothing was
saved; Manage ▸ Accounts, when it is the screen shown, then reads again. The queue is in
test_tui_writes.py.
"""

import threading

from textual.widgets import Input

from expense.errors import EngineError, format_error
from expense.tui.screens._form import open_it_again
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.create_forms import EditAccountScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
    ENGINE_BANKS,
    ENGINE_CURRENCIES,
    account_with_currencies,
    app_notes,
    held_currency,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)
from tests.unit.test_tui_opening_balance import OPENING_ROW, USD_ROW, _on

VISA = account_with_currencies(
    id="acc-visa",
    name="Visa",
    color="#4a90d9",
    currencies=[
        held_currency("PEN", opening_balance_transaction_id="tx-open"),
        held_currency("USD", opening_balance_transaction_id="tx-usd"),
    ],
)
ELIANA = account_with_currencies(
    VISA,
    id="acc-eli",
    name="Eliana",
    kind="person",
    currencies=[held_currency("PEN", opening_balance_transaction_id="tx-open")],
)
ROWS = {"tx-open": OPENING_ROW, "tx-usd": USD_ROW}

NOT_FUTURE = EngineError(
    "VALIDATION_ERROR", "Validation failed [x].", {"date": "Must not be in the future."}, 422, {}
)
SERVER_ERROR = EngineError("INTERNAL", "Something broke.", None, 500, {})
PUT_ACCOUNT = ("PUT", "/accounts/acc-visa")
CLOSING = "[dim]Nothing was saved: open it again to fix it."


def _words(exc: Exception) -> str:
    return format_error(exc).replace("[", "\\[")


def _gate(client, refusals: dict):
    """Make the save's write wait on `release`, and the writes named in `refusals`
    (`(verb, path)` → error) fail. `started` is set when it reached the client."""
    release, started, returned = threading.Event(), threading.Event(), threading.Event()

    def wrap(verb: str):
        real = getattr(client, verb)

        def call(path, *args, **kwargs):
            started.set()
            release.wait(5)
            returned.set()
            exc = refusals.get((verb.upper(), path))
            if exc is not None:
                client._record(verb.upper(), path, kwargs.get("json_body"))
                raise exc
            return real(path, *args, **kwargs)

        return call

    for verb in ("post", "put", "delete"):
        setattr(client, verb, wrap(verb))
    return release, started, returned


def _left_save(
    fake_client,
    monkeypatch,
    record=VISA,
    edits=(("color", "green"), ("opening:PEN", "-3000.00"), ("opening:USD", "41.00")),
    *,
    refusals=None,
    quit_instead=False,
    real_esc=False,
    before_release=None,
):
    """Open `record`'s form over Manage ▸ Accounts, make `edits`, save, leave the form while
    the write is unanswered (`before_release(pilot, app)`, when given, runs while
    it is), let it answer, and return `(the app's toasts, the requests sent, the list's
    reads)`."""
    monkeypatch.setattr("expense.reads.fetch_transaction", lambda cfg, tid, **kw: ROWS[tid])
    list_reads: list[int] = []

    def fetch_accounts(*a, **k):
        list_reads.append(1)
        return whole([record])

    monkeypatch.setattr("expense.reads.fetch_accounts", fetch_accounts)
    release, started, returned = _gate(fake_client, refusals or {})
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        listing = AccountsScreen()
        await app.push_screen(listing)
        await wait_for_list(pilot, app)
        if real_esc:  # opened by the list's own `e`, so its `_edited` is the callback
            await pilot.press("e")
            form = app.screen
            assert isinstance(form, EditAccountScreen)
        else:
            form = EditAccountScreen(record, ENGINE_CURRENCIES, ENGINE_BANKS)
            await app.push_screen(form)
        await wait_for(pilot, lambda: bool(form.query("#bar")) and not form._openings_loading)
        for key, text in edits:
            _on(form, key)
            form.query_one("#bar", Input).value = text
            form._recompute(text)
            form.on_input_submitted(None)
        form.action_submit()
        if any(text == "" for _, text in edits):
            await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
            await pilot.press("y")
        await wait_for(pilot, started.is_set)
        if quit_instead:
            app.exit()
            release.set()
            await wait_for(pilot, returned.is_set)
            await pilot.pause()
            result.extend([notes, list(fake_client.requests), len(list_reads)])
            return
        reads_at_leaving = len(list_reads)
        if real_esc:  # the form's own `esc`: its dismiss callback runs, as for a user
            await pilot.press("escape")
        else:
            await app.pop_screen()  # left: popped, so its dismiss callback never runs
        await wait_for(pilot, lambda: app.screen is listing)
        await wait_for_list(pilot, app)
        await pilot.pause()
        reads_before = len(list_reads)
        if before_release is not None:
            await before_release(pilot, app)
        release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.pause()
        unrefused = {k for k, e in (refusals or {}).items() if open_it_again(e) is None}
        if set(fake_client.requests) - set(refusals or {}) | unrefused:
            await wait_for(pilot, lambda: len(list_reads) > reads_before, timeout=3)
            await wait_for_list(pilot, app)
            assert listing.query_one(CursorList).cursor_key == record["id"]  # row 1
        reads_base = reads_at_leaving if real_esc else reads_before
        result.extend([notes, list(fake_client.requests), len(list_reads) - reads_base])

    run_app(scenario, size=(120, 40))
    return tuple(result)


def test_the_save_still_goes_and_one_message_says_saved(fake_client, monkeypatch):
    notes, sent, reads = _left_save(fake_client, monkeypatch)
    assert sent == [PUT_ACCOUNT]
    assert [(t, m, o.get("severity", "information")) for t, m, o in notes] == [
        ("", "Saved.", "information")
    ]
    assert reads == 1  # Manage ▸ Accounts is the screen shown: it reads again


def test_a_refusal_names_the_account_and_says_nothing_was_saved(fake_client, monkeypatch):
    notes, sent, reads = _left_save(fake_client, monkeypatch, refusals={PUT_ACCOUNT: NOT_FUTURE})
    assert sent == [PUT_ACCOUNT]
    [(title, message, options)] = notes
    assert title == "Not saved · Account Visa"  # the name as the list showed it
    assert message == f"{_words(NOT_FUTURE)}\n{CLOSING}"
    assert "Validation failed \\[x]." in message  # the engine's brackets stay text
    assert (options["severity"], options["timeout"], options["markup"]) == ("error", 10, True)
    assert reads == 0  # nothing landed


def test_a_person_is_named_as_a_person(fake_client, monkeypatch):
    notes, _, _ = _left_save(
        fake_client,
        monkeypatch,
        ELIANA,
        edits=(("opening:PEN", "-100.00"),),
        refusals={("PUT", "/accounts/acc-eli"): NOT_FUTURE},
    )
    [(title, message, _)] = notes
    assert title == "Not saved · Person Eliana"
    assert message == f"{_words(NOT_FUTURE)}\n{CLOSING}"


def test_a_save_not_refused_clearly_leaves_no_closing_line_and_reads_the_list(
    fake_client, monkeypatch
):
    """It may have landed, so the message does not say nothing was saved, and the list
    reads again."""
    notes, _, reads = _left_save(fake_client, monkeypatch, refusals={PUT_ACCOUNT: SERVER_ERROR})
    [(title, message, _)] = notes
    assert title == "Not saved · Account Visa"
    assert message == _words(SERVER_ERROR)
    assert reads == 1


def test_an_emptied_balance_is_one_put_and_says_saved(fake_client, monkeypatch):
    notes, sent, _ = _left_save(fake_client, monkeypatch, edits=(("opening:USD", ""),))
    assert sent == [PUT_ACCOUNT]
    assert fake_client.puts == [("/accounts/acc-visa", {"opening_balances": {"USD": None}})]
    assert [(t, m) for t, m, _ in notes] == [("", "Saved.")]


def test_quitting_mid_save_sends_and_shows_nothing_more(fake_client, monkeypatch):
    notes, sent, _ = _left_save(fake_client, monkeypatch, quit_instead=True)
    assert sent == [PUT_ACCOUNT]
    assert notes == []


def test_the_real_esc_with_the_save_unanswered_reads_the_list_at_esc_and_again_at_the_end(
    fake_client, monkeypatch
):
    """`esc` with the PUT unanswered closes the form with nothing to say it was saved, so
    the list's own reload is one read, and the late answer's `start_over` a second."""
    notes, sent, reads = _left_save(fake_client, monkeypatch, real_esc=True)
    assert sent == [PUT_ACCOUNT]
    assert [(t, m) for t, m, _ in notes] == [("", "Saved.")]
    assert reads == 2
