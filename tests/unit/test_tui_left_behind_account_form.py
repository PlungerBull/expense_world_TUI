"""The account Edit form finishes its whole save after it has been left.

A save is up to one `PUT /accounts/{id}` and one write per changed opening balance, sent in
order. Left (esc) while any is unanswered, every write still goes, a refusal stopping none,
and the last answer shows ONE message for the whole save on the app: `Saved.`, or an error
toast titled `Not all saved · Account <name>` (`Not saved · …` when every write was refused)
with one line per write and a dim last line naming what is left to set again; Manage ▸
Accounts, when it is the screen shown, then reads again. The queue is in test_tui_writes.py.
"""

import threading

import pytest
from textual.screen import Screen
from textual.widgets import Input

from expense.errors import EngineConnectionError, EngineError, format_error
from expense.tui.screens._form import open_it_again
from expense.tui.screens.accounts import AccountsScreen
from expense.tui.screens.create_forms import EditAccountScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.widgets.cursor_list import CursorList
from tests.unit.helpers import (
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
    is_person=True,
    currencies=[held_currency("PEN", opening_balance_transaction_id="tx-open")],
)
ROWS = {"tx-open": OPENING_ROW, "tx-usd": USD_ROW}

NOT_FUTURE = EngineError(
    "VALIDATION_ERROR", "Validation failed [x].", {"date": "Must not be in the future."}, 422, {}
)
SERVER_ERROR = EngineError("INTERNAL", "Something broke.", None, 500, {})
NO_ANSWER = EngineConnectionError(url="http://x", original=OSError("down"))
PUT_PEN = ("PUT", "/transactions/tx-open")
PUT_USD = ("PUT", "/transactions/tx-usd")
PUT_ACCOUNT = ("PUT", "/accounts/acc-visa")
ALL_THREE = [PUT_ACCOUNT, PUT_PEN, PUT_USD]
ACCOUNT_SAVED = "The account's changes are saved."
PEN_SAVED = "The PEN opening balance is saved."
USD_SAVED = "The USD opening balance is saved."


def _words(exc: Exception) -> str:
    return format_error(exc).replace("[", "\\[")


def _gate(client, hold: int, refusals: dict, quit_app=None):
    """Make the `hold`th write wait on `release`, and the writes named in `refusals`
    (`(verb, path)` → error) fail. `started` is set when the held write reached the client."""
    release, started, returned = threading.Event(), threading.Event(), threading.Event()
    count = [0]

    def wrap(verb: str):
        real = getattr(client, verb)

        def call(path, *args, **kwargs):
            count[0] += 1
            if count[0] == hold:
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
    edits=(("name", "Visa 2"), ("opening:PEN", "-3000.00"), ("opening:USD", "41.00")),
    *,
    hold=1,
    refusals=None,
    elsewhere=False,
    quit_instead=False,
    before_release=None,
):
    """Open `record`'s form over Manage ▸ Accounts, make `edits`, save, leave the form while
    the `hold`th write is unanswered (`before_release(pilot, app)`, when given, runs while
    it is), let it answer, and return `(the app's toasts, the
    requests sent, the list's reads)`; `elsewhere`: another screen is the one shown."""
    monkeypatch.setattr("expense.reads.fetch_transaction", lambda cfg, tid, **kw: ROWS[tid])
    list_reads: list[int] = []

    def fetch_accounts(*a, **k):
        list_reads.append(1)
        return whole([record])

    monkeypatch.setattr("expense.reads.fetch_accounts", fetch_accounts)
    release, started, returned = _gate(fake_client, hold, refusals or {})
    result: list = []

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        listing = AccountsScreen()
        await app.push_screen(listing)
        await wait_for_list(pilot, app)
        form = EditAccountScreen(record)
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
        await app.pop_screen()  # left: popped, so its dismiss callback never runs
        await wait_for(pilot, lambda: app.screen is listing)
        await wait_for_list(pilot, app)
        if elsewhere:
            await app.push_screen(Screen())
            await wait_for(pilot, lambda: app.screen is not listing)
        reads_before = len(list_reads)
        if before_release is not None:
            await before_release(pilot, app)
        release.set()
        await wait_for(pilot, lambda: notes, timeout=3)
        await pilot.pause()
        unrefused = {k for k, e in (refusals or {}).items() if open_it_again(e) is None}
        if not elsewhere and set(fake_client.requests) - set(refusals or {}) | unrefused:
            await wait_for(pilot, lambda: len(list_reads) > reads_before, timeout=3)
            await wait_for_list(pilot, app)
            assert listing.query_one(CursorList).cursor_key == record["id"]  # row 1
        result.extend([notes, list(fake_client.requests), len(list_reads) - reads_before])

    run_app(scenario, size=(120, 40))
    return tuple(result)


def test_every_write_still_goes_in_order_and_one_message_says_all_saved(fake_client, monkeypatch):
    notes, sent, reads = _left_save(fake_client, monkeypatch)
    assert sent == ALL_THREE
    assert [(t, m, o.get("severity", "information")) for t, m, o in notes] == [
        ("", "Saved.", "information")
    ]
    assert reads == 1  # Manage ▸ Accounts is the screen shown: it reads again


def test_a_refused_soles_balance_names_what_each_write_did_and_what_is_left(
    fake_client, monkeypatch
):
    """The mockup's pane: the account saved, the soles refused, the dollars saved."""
    notes, sent, reads = _left_save(fake_client, monkeypatch, refusals={PUT_PEN: NOT_FUTURE})
    assert sent == ALL_THREE  # a refusal stopped none
    [(title, message, options)] = notes
    assert title == "Not all saved · Account Visa"  # the name as the list showed it
    assert message == (
        f"{ACCOUNT_SAVED}\nThe PEN opening balance is not:\n{_words(NOT_FUTURE)}\n{USD_SAVED}\n"
        "[dim]Open the account's Edit form to set PEN again."
    )
    assert "Validation failed \\[x]." in message  # the engine's brackets stay text
    assert (options["severity"], options["timeout"], options["markup"]) == ("error", 10, True)
    assert reads == 1  # part of it landed


def test_the_account_changes_refused_and_the_balances_saved(fake_client, monkeypatch):
    notes, sent, reads = _left_save(fake_client, monkeypatch, refusals={PUT_ACCOUNT: NOT_FUTURE})
    assert sent == ALL_THREE
    [(title, message, _)] = notes
    assert title == "Not all saved · Account Visa"
    assert message == (
        f"The account's changes are not saved:\n{_words(NOT_FUTURE)}\n{PEN_SAVED}\n{USD_SAVED}\n"
        "[dim]Open the account's Edit form to set its changes again."
    )
    assert reads == 1


def test_two_refused_are_named_in_the_order_sent(fake_client, monkeypatch):
    notes, _, _ = _left_save(
        fake_client, monkeypatch, refusals={PUT_ACCOUNT: NOT_FUTURE, PUT_USD: NOT_FUTURE}
    )
    [(title, message, _)] = notes
    assert title == "Not all saved · Account Visa"
    assert message.endswith("[dim]Open the account's Edit form to set its changes and USD again.")
    assert f"{PEN_SAVED}\nThe USD opening balance is not:" in message


def test_two_balances_refused_are_named_by_their_codes(fake_client, monkeypatch):
    notes, _, _ = _left_save(
        fake_client, monkeypatch, refusals={PUT_PEN: NOT_FUTURE, PUT_USD: NOT_FUTURE}
    )
    [(_, message, _)] = notes
    assert message.endswith("[dim]Open the account's Edit form to set PEN and USD again.")


def test_every_write_refused_is_titled_not_saved_and_reads_nothing_again(fake_client, monkeypatch):
    notes, sent, reads = _left_save(
        fake_client,
        monkeypatch,
        refusals={PUT_ACCOUNT: NOT_FUTURE, PUT_PEN: NOT_FUTURE, PUT_USD: NOT_FUTURE},
    )
    assert sent == ALL_THREE
    [(title, message, _)] = notes
    assert title == "Not saved · Account Visa"
    assert message.endswith(
        "[dim]Open the account's Edit form to set its changes, PEN and USD again."
    )
    assert reads == 0  # nothing landed


@pytest.mark.parametrize("failure", [SERVER_ERROR, NO_ANSWER], ids=["5xx", "no answer"])
def test_a_part_not_refused_clearly_leaves_no_closing_line(fake_client, monkeypatch, failure):
    """It may have landed, so the message does not send the owner to set it again."""
    notes, _, _ = _left_save(fake_client, monkeypatch, refusals={PUT_PEN: failure})
    [(title, message, _)] = notes
    assert title == "Not all saved · Account Visa"
    assert message == (
        f"{ACCOUNT_SAVED}\nThe PEN opening balance is not:\n{_words(failure)}\n{USD_SAVED}"
    )


def test_only_the_clearly_refused_part_is_named(fake_client, monkeypatch):
    notes, _, _ = _left_save(
        fake_client, monkeypatch, refusals={PUT_PEN: SERVER_ERROR, PUT_USD: NOT_FUTURE}
    )
    [(_, message, _)] = notes
    assert message.endswith("[dim]Open the account's Edit form to set USD again.")
    assert "PEN again" not in message


def test_a_person_is_named_as_a_person(fake_client, monkeypatch):
    notes, _, _ = _left_save(
        fake_client,
        monkeypatch,
        ELIANA,
        edits=(("opening:PEN", "-100.00"),),
        refusals={("PUT", "/transactions/tx-open"): NOT_FUTURE},
    )
    [(title, message, _)] = notes
    assert title == "Not saved · Person Eliana"
    assert message == (
        f"The PEN opening balance is not:\n{_words(NOT_FUTURE)}\n"
        "[dim]Open the account's Edit form to set PEN again."
    )


def test_a_write_that_landed_before_leaving_is_in_the_message(fake_client, monkeypatch):
    """The account's write answered with the form open; the soles' is the one unanswered."""
    notes, sent, _ = _left_save(fake_client, monkeypatch, hold=2, refusals={PUT_PEN: NOT_FUTURE})
    assert sent == ALL_THREE
    [(title, message, _)] = notes
    assert title == "Not all saved · Account Visa"
    assert message.startswith(f"{ACCOUNT_SAVED}\nThe PEN opening balance is not:")


def test_an_emptied_balance_is_reported_deleted(fake_client, monkeypatch):
    notes, sent, _ = _left_save(fake_client, monkeypatch, edits=(("opening:USD", ""),))
    assert sent == [("DELETE", "/transactions/tx-usd")]
    assert [(t, m) for t, m, _ in notes] == [("", "Saved.")]


def test_an_emptied_balance_refused_says_it_is_not_deleted(fake_client, monkeypatch):
    notes, _, reads = _left_save(
        fake_client,
        monkeypatch,
        edits=(("name", "Visa 2"), ("opening:USD", "")),
        refusals={("DELETE", "/transactions/tx-usd"): NOT_FUTURE},
    )
    [(title, message, _)] = notes
    assert title == "Not all saved · Account Visa"
    assert message == (
        f"{ACCOUNT_SAVED}\nThe USD opening balance is not deleted:\n{_words(NOT_FUTURE)}\n"
        "[dim]Open the account's Edit form to set USD again."
    )
    assert reads == 1


def test_an_emptied_balance_deleted_is_said_with_the_others(fake_client, monkeypatch):
    notes, _, _ = _left_save(
        fake_client,
        monkeypatch,
        edits=(("opening:PEN", "-3000.00"), ("opening:USD", "")),
        refusals={PUT_PEN: NOT_FUTURE},
    )
    [(title, message, _)] = notes
    assert title == "Not all saved · Account Visa"
    assert message == (
        f"The PEN opening balance is not:\n{_words(NOT_FUTURE)}\n"
        "The USD opening balance is deleted.\n"
        "[dim]Open the account's Edit form to set PEN again."
    )


def test_elsewhere_the_message_shows_and_nothing_is_read_again(fake_client, monkeypatch):
    notes, sent, reads = _left_save(fake_client, monkeypatch, elsewhere=True)
    assert sent == ALL_THREE
    assert [(t, m) for t, m, _ in notes] == [("", "Saved.")]
    assert reads == 0


def test_quitting_mid_save_sends_and_shows_nothing_more(fake_client, monkeypatch):
    notes, sent, _ = _left_save(fake_client, monkeypatch, quit_instead=True)
    assert sent == [PUT_ACCOUNT]
    assert notes == []


@pytest.mark.parametrize("hold", [1, 2, 3])
def test_one_message_however_far_the_save_had_got(fake_client, monkeypatch, hold):
    notes, sent, _ = _left_save(fake_client, monkeypatch, hold=hold)
    assert sent == ALL_THREE
    assert len(notes) == 1


@pytest.mark.parametrize("failure", [SERVER_ERROR, NO_ANSWER], ids=["5xx", "no answer"])
def test_every_part_ended_unknown_still_reads_the_list_again(fake_client, monkeypatch, failure):
    """Nothing is known to have landed, but any part may have: the list reads again."""
    _, sent, reads = _left_save(
        fake_client,
        monkeypatch,
        refusals={PUT_ACCOUNT: failure, PUT_PEN: failure, PUT_USD: failure},
    )
    assert sent == ALL_THREE
    assert reads == 1


def test_one_part_unknown_and_the_rest_refused_clearly_reads_the_list_again(
    fake_client, monkeypatch
):
    _, _, reads = _left_save(
        fake_client,
        monkeypatch,
        refusals={PUT_ACCOUNT: NOT_FUTURE, PUT_PEN: SERVER_ERROR, PUT_USD: NOT_FUTURE},
    )
    assert reads == 1
