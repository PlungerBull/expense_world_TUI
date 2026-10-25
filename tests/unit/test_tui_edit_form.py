"""The bar-cycle transaction **edit** form (fake client).

Edit-only: creating is the LOG bar's — see
[test_tui_log_bar.py](test_tui_log_bar.py). The form owns pre-fill, the diffed
PUT, and the suggestion pickers.
"""

import threading

import pytest
from rich.text import Text
from textual import events
from textual.widgets import Input, Static

from expense.errors import EngineConnectionError, EngineError
from expense.tui.screens._form import TITLE_REQUIRED
from expense.tui.screens.create_forms import (
    EditAccountScreen,
    EditCategoryScreen,
    EditHashtagScreen,
    NewAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from expense.tui.screens.edit_form import EditFormScreen
from expense.tui.theme import ACCENT
from tests.unit.helpers import (
    ARCHIVED_FIELD_WORDS,
    ARCHIVED_PUT_WORDS,
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_NAMES,
    HASHTAG_REFUSALS,
    archived_refusal,
    edit_limits,
    hashtag_refusal,
    import_part,
    in_order,
    line_code_of,
    put_answer,
    refusal_text,
    render_text,
    run_app,
    wait_for,
    whole,
)

ACCOUNTS = [
    {
        "id": "acc1",
        "name": "BCP PEN",
        "currency_code": "PEN",
        "is_person": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
    {
        "id": "acc2",
        "name": "BCP USD",
        "currency_code": "USD",
        "is_person": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
    {
        "id": "acc3",
        "name": "Ahorros",
        "currency_code": "PEN",
        "is_person": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
]
CATEGORIES = {
    "items": [
        {"id": "cat1", "name": "Mascotas", "is_system": False},
        {"id": "catO", "name": "@Opening", "is_system": True, "system_key": "opening_balance"},
    ]
}
HASHTAGS = {"items": [{"id": "h1", "name": "dog"}, {"id": "h2", "name": "traveling"}]}


def _patch(monkeypatch):
    """Screen-specific patches; the client/config seams come from fake_client.

    Name maps derive from the same fetches — no separate
    load_*_name_map seams to patch.
    """
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(ACCOUNTS))
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: CATEGORIES)
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: HASHTAGS)


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute_suggestions(text)
    screen.on_input_submitted(None)


async def _wait_loaded(screen, pilot):
    await wait_for(pilot, lambda: screen._accounts)


TXN = {
    "id": "tx1",
    "date": "2026-06-20T00:00:00Z",
    "title": "Farmacia",
    "amount_cents": -4250,
    "account_id": "acc1",
    "category_id": "cat1",
    "hashtag_ids": ["h1"],
    "description": "receta",
    "bank_line_id": "bl1",
    "line_code": line_code_of("bl1"),
    "statement_line": None,
    "statement_place": None,
}


def test_load_entities_three_superset_queries(fake_client, monkeypatch):
    """The form loads each resource once and derives both the suggestion pools
    and the full name maps — three queries, not six. Only the
    accounts fetch is a superset (include_archived); categories/hashtags have
    no archive."""
    calls: list[tuple[str, bool]] = []
    archived = {
        "id": "accX",
        "name": "Old bank",
        "currency_code": "PEN",
        "is_archived": True,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    }

    def rec(name, payload):
        def fetch(cfg, *a, **k):
            calls.append((name, bool(k.get("include_archived"))))
            return payload

        return fetch

    monkeypatch.setattr(
        "expense.reads.fetch_accounts",
        rec("accounts", whole([*ACCOUNTS, archived])),
    )
    monkeypatch.setattr("expense.reads.fetch_categories", rec("categories", CATEGORIES))
    monkeypatch.setattr("expense.reads.fetch_hashtags", rec("hashtags", HASHTAGS))

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        assert sorted(calls) == [("accounts", True), ("categories", False), ("hashtags", False)]
        assert "accX" not in [a[0] for a in screen._accounts]  # archived out of the pool
        assert screen._acc_names.get("accX") == "Old bank"  # but resolvable in the map

    run_app(scenario)


def test_the_account_field_suggests_in_the_engines_order(fake_client, monkeypatch):
    """The account picker lists accounts exactly as `GET /accounts` returned
    them — not alphabetical, not by `sort_order`, the person after every bank."""
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_ACCOUNTS)
    )

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("account")
        screen._recompute("")
        assert [ent[1] for ent in screen._suggestions] == ENGINE_ORDER_NAMES
        shown = render_text(screen._suggest_renderable(), width=120)
        assert in_order(shown, ENGINE_ORDER_NAMES)

    run_app(scenario)


def test_edit_with_null_hashtag_ref_renders_dash_not_crash(fake_client, monkeypatch):
    """A record carrying a null reference id must render the shared em-dash
    fallback instead of TypeError-ing on None[:8]."""
    _patch(monkeypatch)
    record = {**TXN, "hashtag_ids": ["h1", None]}

    async def scenario(pilot, app):
        screen = EditFormScreen(record=record, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        await wait_for(pilot, lambda: "—" in screen._display.get("hashtags", ""))
        assert app.is_running
        assert "—" in screen._display["hashtags"]  # null id → em-dash
        assert "—" in screen._tag_display_names()

    run_app(scenario)


def test_edit_form_guards_double_submit(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._values.update(title="x", amount=-500, account="acc1", category="cat1")
        screen.action_submit()
        screen.action_submit()  # in flight → ignored
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)
        await pilot.pause()  # let the ignored submits settle, then assert a non-event
        assert len(fake_client.puts) == 1

    run_app(scenario)


def test_suggest_window_keeps_highlight_visible():

    screen = EditFormScreen(record=TXN, resource="transactions")
    screen._current = 3  # account (an entity field)
    screen._suggestions = [(f"c{i}", f"Cat{i}", "PEN") for i in range(20)]
    screen._suggest_idx = 17
    out = render_text(screen._suggest_renderable(), width=60)
    assert "Cat17" in out and "more" in out


def test_edit_prefills_and_puts_only_changed_fields(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        assert screen._values["title"] == "Farmacia" and screen._values["amount"] == -4250
        # change just the title, then save
        screen._current = screen._sequence().index("title")
        _enter(screen, "Farmacia Inkafarma")
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)
        path, body = fake_client.puts[0]
        assert path == "/transactions/tx1"
        assert body == {"title": "Farmacia Inkafarma"}  # diff only
        assert not fake_client.posts  # never POSTs in edit mode

    run_app(scenario)


def test_edit_add_hashtag_puts_merged_hashtag_ids(fake_client, monkeypatch):
    """Hashtag appends must survive the edit diff — the snapshot must not alias."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("hashtags")
        _enter(screen, "trav")  # add #traveling next to the pre-existing #dog
        assert screen._values["hashtags"] == ["h1", "h2"]
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)
        path, body = fake_client.puts[0]
        assert path == "/transactions/tx1"
        assert body == {"hashtag_ids": ["h1", "h2"]}  # diff only, both tags
        assert not fake_client.posts

    run_app(scenario)


def test_edit_no_changes_does_not_submit(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen.action_submit()  # nothing changed
        await pilot.pause()  # let the no-op submit settle, then assert a non-event
        assert not fake_client.calls

    run_app(scenario)


# ---- an account move leaves the reconciliation --------------------------------
# (contract: "Assigning transactions") (contract: PUT /v1/transactions/{transaction_id})

ASSIGNED = {**TXN, "reconciliation_id": "rec1"}


def _record_notices(monkeypatch) -> list:
    notices: list = []
    monkeypatch.setattr(
        EditFormScreen,
        "notify",
        lambda self, message, title="", **kw: notices.append((title, str(message))),
    )
    return notices


def _move_and_save(record, account_text, fake_client, monkeypatch, *, settle):
    """Open the form on `record`, pick the account `account_text` names, save;
    returns (notices, the screen) once `settle(screen, notices)` holds."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)
    seen: dict = {}

    async def scenario(pilot, app):
        screen = EditFormScreen(record=record, resource="transactions")
        seen["screen"] = screen
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("account")
        _enter(screen, account_text)
        screen.action_submit()
        await wait_for(pilot, lambda: settle(screen, notices))
        seen["on_top"] = app.screen is screen

    run_app(scenario)
    return notices, seen


#: The other part of TXN's bank line, for the answers that list both parts.
OTHER_PART = {**TXN, "id": "tx1b", "amount_cents": -1000}


def _moved(part: dict) -> dict:
    return {**part, "account_id": "acc3", "reconciliation_id": None, "version": 2}


@pytest.mark.parametrize(
    ("record", "answer", "note"),
    [
        pytest.param(
            ASSIGNED,
            put_answer(_moved(TXN), [_moved(TXN), _moved(OTHER_PART)], left=("tx1", "tx1b")),
            "Saved. It left its reconciliation.",
            id="answer-flags-the-row",
        ),
        pytest.param(
            {**TXN, "reconciliation_id": None},
            put_answer(_moved(TXN), [_moved(TXN), _moved(OTHER_PART)], left=("tx1b",)),
            "Saved. It left its reconciliation.",
            id="answer-flags-another-part-the-read-showed-unassigned",
        ),
        pytest.param(
            ASSIGNED,
            put_answer(_moved(TXN), [_moved(TXN), _moved(OTHER_PART)]),
            "Saved.",
            id="answer-lists-parts-flags-none",
        ),
        pytest.param(ASSIGNED, put_answer(_moved(TXN), []), "Saved.", id="answer-lists-none"),
    ],
)
def test_the_saved_note_reads_the_engines_answer(fake_client, monkeypatch, record, answer, note):
    """Typed key by key: `⏎` past date, title and amount, `Ahorros` on ACCOUNT,
    `ctrl+s`. Every account change sends `reconciliation_id: null`, and the note
    says the row left its reconciliation only when the answer's `changed_parts`
    flags a part (contract: PUT /v1/transactions/{transaction_id}, "Response"):
    never from the row as read before the save, so a row read as assigned whose
    answer flags none says `Saved.`, and one read as unassigned whose answer flags
    a part says it left."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)
    fake_client.write_responses["/transactions/tx1"] = answer

    async def scenario(pilot, app):
        screen = EditFormScreen(record=record, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        await pilot.press("enter", "enter", "enter")  # date, title, amount: kept
        await wait_for(pilot, lambda: screen._key == "account")
        await pilot.press(*"Ahorros", "enter")
        await wait_for(pilot, lambda: screen._key != "account")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: notices)

    run_app(scenario)
    assert fake_client.puts == [
        ("/transactions/tx1", {"account_id": "acc3", "reconciliation_id": None})
    ]
    assert notices == [("", note)]


def test_an_edit_that_keeps_the_account_sends_no_reconciliation_id(fake_client, monkeypatch):
    """Re-picking the row's own account is no change, so an assigned row edited
    on another field keeps its reconciliation."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=ASSIGNED, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("account")
        _enter(screen, "BCP PEN")  # the account it is already on
        screen._current = screen._sequence().index("title")
        _enter(screen, "Farmacia Inkafarma")
        screen.action_submit()
        await wait_for(pilot, lambda: notices)

    run_app(scenario)
    assert fake_client.puts == [("/transactions/tx1", {"title": "Farmacia Inkafarma"})]
    assert ("", "Saved.") in notices


def test_a_move_on_a_completed_reconciliation_still_shows_the_lock(fake_client, monkeypatch):
    """The engine checks `LOCKED` first; the form shows its refusal and stays."""
    fake_client.errors["PUT"] = EngineError(
        "VALIDATION_ERROR",
        "Fields are locked by a completed reconciliation.",
        {"account_id": "Locked by completed reconciliation."},
        422,
        {},
        reasons={"account_id": "LOCKED", "reconciliation_id": "LOCKED"},
    )
    notices, seen = _move_and_save(
        ASSIGNED,
        "BCP USD",
        fake_client,
        monkeypatch,
        settle=lambda s, n: n and not s._submitting,
    )
    assert fake_client.puts == [
        ("/transactions/tx1", {"account_id": "acc2", "reconciliation_id": None})
    ]
    title, message = notices[0]
    assert title == "Failed"
    assert "Locked by completed reconciliation." in message
    assert seen["on_top"]  # not dismissed: nothing was saved


def test_a_move_onto_an_account_holding_its_operation_code_says_what_to_do(
    fake_client, monkeypatch
):
    """Screen 4: the engine refuses the move keyed on `operation_code`, though
    the body did not send it (contract: PUT /v1/transactions/{transaction_id});
    the note is its words, then the line, and the form stays."""
    fake_client.errors["PUT"] = EngineError(
        "CONFLICT",
        "Operation code already exists.",
        {"operation_code": "Must be unique per account."},
        409,
        {},
        reasons={"operation_code": "OPERATION_CODE_EXISTS"},
    )
    notices, seen = _move_and_save(
        {**TXN, "reconciliation_id": None},
        "BCP USD",
        fake_client,
        monkeypatch,
        settle=lambda s, n: n and not s._submitting,
    )
    assert notices[0] == (
        "Failed",
        "CONFLICT — Operation code already exists.\n"
        "  operation_code: Must be unique per account.\n\n"
        "That account already has a row with this operation number: "
        "look there for a duplicate.",
    )
    assert seen["on_top"]


# ---- an opening balance stays put (1A) -----------------------------------------
# (contract: PUT /v1/transactions/{transaction_id}, "Opening balances stay put")

OPENING = {
    **TXN,
    "id": "txO",
    "title": "Saldo inicial",
    "amount_cents": 320000,
    "category_id": "catO",
    "hashtag_ids": [],
    "description": None,
}


def test_an_opening_balance_shows_account_category_and_hashtags_read_only(fake_client, monkeypatch):
    """The three lines show dimmed and marked read-only, hashtags as `—`
    (pending-hashtag-manage 6 A); a field move skips them, from amount
    straight to note and back, with ⇥ and with the arrows."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=OPENING, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        assert screen._locked == {"account", "category", "hashtags"}
        summary = render_text(screen._summary_renderable(), width=60)
        assert "account   BCP PEN  read-only" in summary
        assert "category  @Opening  read-only" in summary
        assert "hashtags  —  read-only" in summary
        assert summary.count("read-only") == 3
        screen._current = screen._sequence().index("amount")
        screen._refresh_bar()
        await pilot.press("tab")
        assert screen._key == "note"
        await pilot.press("shift+tab")
        assert screen._key == "amount"
        await pilot.press("down")
        assert screen._key == "note"
        await pilot.press("up")
        assert screen._key == "amount"

    run_app(scenario)


def test_an_opening_balance_saves_its_other_fields_and_never_its_locked_ones(
    fake_client, monkeypatch
):
    """Amount, date, title and note save as on any row; the PUT carries no
    account, no category and no hashtags, even if a value was set under them."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=OPENING, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("amount")
        _enter(screen, "3500")
        assert screen._key == "note"  # account, category and hashtags skipped
        # whatever lands under the locked keys is never sent
        screen._values.update(account="acc2", category="cat1", hashtags=["h1"])
        _enter(screen, "apertura")  # enter on note saves
        await wait_for(pilot, lambda: fake_client.puts)
        assert fake_client.puts == [
            ("/transactions/txO", {"amount_cents": 350000, "description": "apertura"})
        ]

    run_app(scenario)


def test_an_ordinary_row_keeps_account_and_category_editable(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        assert screen._locked == set()
        assert "read-only" not in render_text(screen._summary_renderable(), width=60)
        screen._current = screen._sequence().index("amount")
        screen.action_field(1)
        assert screen._key == "account"

    run_app(scenario)


@pytest.mark.parametrize(
    ("field", "reason", "line"),
    [
        (
            "account_id",
            "OPENING_BALANCE_ACCOUNT_FIXED",
            "To move an opening balance, set it on the other account's Edit form.",
        ),
        (
            "category_id",
            "OPENING_BALANCE_CATEGORY_FIXED",
            "An opening balance always stays in @Opening.",
        ),
        # pending-hashtag-manage 7 B: the same note as on the ledger's `h`
        (
            "hashtag_ids",
            "OPENING_BALANCE_NOT_TAGGED",
            "Leave the opening balance out of the selection.",
        ),
    ],
)
def test_an_opening_balance_refusal_on_the_form_shows_the_same_line(
    fake_client, monkeypatch, field, reason, line
):
    """If the refusal reaches the form anyway (here, a row the form could not
    tell apart), its note is the engine's words, then the same line as on the
    ledger, and the form stays."""
    fake_client.errors["PUT"] = EngineError(
        "VALIDATION_ERROR",
        "Validation failed.",
        {field: "stand-in field words"},
        422,
        {},
        reasons={field: reason},
    )
    notices, seen = _move_and_save(
        {**TXN, "reconciliation_id": None},
        "BCP USD",
        fake_client,
        monkeypatch,
        settle=lambda s, n: n and not s._submitting,
    )
    assert notices[0] == (
        "Failed",
        f"VALIDATION_ERROR — Validation failed.\n  {field}: stand-in field words\n\n{line}",
    )
    assert seen["on_top"]


def test_no_form_offers_cleared():
    """`cleared` is gone from the ledger — no form may offer it.

    The engine has no `cleared`: create lists it as retired
    (contract: POST /v1/transactions). Sending it is a 422 on an unknown field,
    which rejects the whole body, so a lingering row here would lose an entire
    edit. Nothing replaces it: a row is confirmed by belonging to a completed
    reconciliation that adds up.
    """
    screen = EditFormScreen(record={"id": "t1", "title": "x"}, resource="transactions")
    assert "cleared" not in screen._sequence()


def test_edit_sequence_offers_hashtags():
    """Hashtags are an ordinary editable field."""
    tx = EditFormScreen(record={"id": "t1", "title": "x"}, resource="transactions")
    assert "hashtags" in tx._sequence()


def test_edit_form_rejects_zero_and_unknown_account(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        _enter(screen, "")  # date
        _enter(screen, "x")  # title
        _enter(screen, "0")  # amount zero → rejected, stays
        assert screen._key == "amount"
        _enter(screen, "-5.00")  # valid → account
        _enter(screen, "Nonexistent")  # no match → rejected, stays
        assert screen._key == "account"

    run_app(scenario)


def test_edit_form_refuses_an_amount_with_a_comma_after_its_dot(fake_client, monkeypatch):
    """Typed key by key on AMOUNT: `13.853,20` is not read as 13.85. The field
    gives its note and the cursor stays; `13853.20` then saves 13,853.20."""
    _patch(monkeypatch)
    notes: list[tuple[str, object]] = []

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen.notify = lambda message, **kw: notes.append((message, kw.get("severity")))
        bar = screen.query_one("#bar", Input)
        await pilot.press("enter", "enter")  # date, title: kept
        await pilot.pause()
        assert screen._key == "amount"
        await pilot.press("ctrl+a", "ctrl+k", *"13.853,20", "enter")
        await pilot.pause()
        assert screen._key == "amount" and bar.value == "13.853,20"
        assert screen._values["amount"] == -4250
        await pilot.press("ctrl+a", "ctrl+k", *"13853.20", "enter")
        await pilot.pause()
        assert screen._key != "amount"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    assert notes[0] == ("Amount: a signed decimal, e.g. -99.92", "error")
    assert [m for m, sev in notes if sev == "error"] == [notes[0][0]]  # once, then saved
    assert fake_client.puts == [("/transactions/tx1", {"amount_cents": 1385320})]


def test_edit_form_refuses_an_emptied_title_and_stays(fake_client, monkeypatch):
    """`⏎` on an emptied title says `Title is required.` as an error toast and
    the cursor stays on TITLE; the split screen's title field says the same
    (`_title_given` in _form.py)."""
    _patch(monkeypatch)
    notes: list[tuple[str, object]] = []

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen.notify = lambda message, **kw: notes.append((message, kw.get("severity")))
        screen._current = screen._sequence().index("title")
        _enter(screen, "   ")
        assert screen._key == "title" and screen._values["title"] == "Farmacia"

    run_app(scenario)
    assert notes == [(TITLE_REQUIRED, "error")]


def test_edit_form_fetch_error_notifies_not_crash(fake_client, monkeypatch):
    """An engine/config error in _load_entities must not exit the app."""
    _patch(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("engine down")

    monkeypatch.setattr("expense.reads.fetch_accounts", boom)
    notices: list = []
    monkeypatch.setattr(
        EditFormScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await wait_for(pilot, lambda: notices)
        assert notices and "engine down" in notices[0]
        assert app.is_running
        assert app.screen is screen

    run_app(scenario)


def test_edit_form_fetch_error_uses_canonical_renderer(fake_client, monkeypatch):
    """Engine errors surface with the canonical text, not bare str(exc)."""
    _patch(monkeypatch)

    def boom(*a, **k):
        raise EngineConnectionError(url="https://x.invalid", original=Exception("refused"))

    monkeypatch.setattr("expense.reads.fetch_accounts", boom)
    notices: list = []
    monkeypatch.setattr(
        EditFormScreen, "notify", lambda self, message, **kw: notices.append(message)
    )

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await wait_for(pilot, lambda: notices)
        assert notices and "could not reach engine at https://x.invalid" in notices[0]

    run_app(scenario)


def test_the_form_cannot_be_opened_without_a_record():
    """The create door is shut, and shut structurally.

    `+` opens the LOG bar. Making `record` required means no future caller
    can reopen that door by accident — it is a TypeError, not a second create
    form drifting quietly out of sync with the bar.
    """
    with pytest.raises(TypeError):
        EditFormScreen()


@pytest.mark.parametrize(
    ("make", "submit"),
    [
        (lambda: NewAccountScreen(), "Create"),
        (lambda: NewCategoryScreen(), "Create"),
        (lambda: NewHashtagScreen(), "Create"),
        (lambda: EditFormScreen(record=TXN, resource="transactions"), "Save"),
        (lambda: EditAccountScreen(ACCOUNTS[0]), "Save"),
        (lambda: EditCategoryScreen({"id": "cat1", "name": "Food"}), "Save"),
        (lambda: EditHashtagScreen({"id": "tag1", "name": "#trip"}), "Save"),
    ],
    ids=[
        "new-account",
        "new-category",
        "new-hashtag",
        "edit-form",
        "edit-account",
        "edit-category",
        "edit-hashtag",
    ],
)
def test_form_footer_reads_cancel_submit_field(fake_client, monkeypatch, make, submit):
    """`esc Cancel  ^s Save|Create  ⇥ Field`, in that order, and nothing else;
    `⇥` moves to the next field with the bar keeping focus."""
    from textual.widgets import Footer
    from textual.widgets._footer import FooterKey

    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = make()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query(FooterKey)))
        keys = screen.query_one(Footer).query(FooterKey)
        assert [(k.key_display, k.description) for k in keys] == [
            ("esc", "Cancel"),
            ("^s", submit),
            ("⇥", "Field"),
        ]
        first = screen._key
        await pilot.press("tab")
        await pilot.pause()
        # A one-field form (hashtag) has nowhere to move: moves stop at either end.
        if len(screen._sequence()) > 1:
            assert screen._key != first
        assert app.focused is screen.query_one("#bar", Input)

    run_app(scenario)


# ---- the pending hashtag never rides beside a real one -------------------------
# (contract: PUT /v1/transactions/{transaction_id})
# (contract: "Transactions (Ledger)", "The pending hashtag is never combined")

PENDING_TAG = {"id": "hp", "name": "Pendiente", "system_key": "pending"}
WITH_PENDING = {"items": [{**t, "system_key": None} for t in HASHTAGS["items"]] + [PENDING_TAG]}
ON_PENDING = {**TXN, "hashtag_ids": ["hp"]}


def _tag_and_save(record, typed, fake_client, monkeypatch, *, tags=WITH_PENDING, settle=None):
    """Open the form on `record`, add each hashtag `typed` names, save; returns
    the notices once `settle(notices)` holds (by default: a PUT went out)."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: tags)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=record, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("hashtags")
        for text in typed:
            _enter(screen, text)
        screen.action_submit()
        await wait_for(pilot, lambda: (settle or (lambda n: fake_client.puts))(notices))

    run_app(scenario)
    return notices


def test_tagging_a_pending_row_sends_only_the_real_hashtag(fake_client, monkeypatch):
    """The row carries the pending hashtag; adding #dog sends `["h1"]` alone,
    never the pending id beside it."""
    _tag_and_save(ON_PENDING, ["dog"], fake_client, monkeypatch)
    assert fake_client.puts == [("/transactions/tx1", {"hashtag_ids": ["h1"]})]


def test_naming_the_pending_hashtag_beside_a_real_one_drops_it(fake_client, monkeypatch):
    """A row on #dog given the pending hashtag too keeps #dog alone: the set
    is unchanged, so nothing is sent."""
    notices = _tag_and_save(TXN, ["pend"], fake_client, monkeypatch, settle=bool)
    assert not fake_client.puts
    assert notices == [("", "No changes to save.")]


def _hashtags_shown(record, typed, monkeypatch, *, tags=WITH_PENDING) -> list[str]:
    """Open the form on `record` and add each hashtag `typed` names; returns the
    summary's `hashtags` line after the load, then after each addition."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: tags)
    shown: list[str] = []

    def line(screen) -> str:
        summary = render_text(screen._summary_renderable(), width=80)
        return next(row.strip() for row in summary.splitlines() if "hashtags" in row)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=record, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("hashtags")
        shown.append(line(screen))
        for text in typed:
            _enter(screen, text)
            shown.append(line(screen))

    run_app(scenario)
    return shown


def test_the_pending_hashtag_leaves_the_list_once_a_real_one_is_in(fake_client, monkeypatch):
    """A row waiting under the pending hashtag lists it; adding #dog leaves
    #dog alone on the form, what the save sends; #traveling then joins it."""
    shown = _hashtags_shown(ON_PENDING, ["dog", "traveling"], monkeypatch)
    assert shown == ["hashtags  #Pendiente", "hashtags  #dog", "hashtags  #dog #traveling"]


def test_naming_the_pending_hashtag_beside_a_real_one_does_not_list_it(fake_client, monkeypatch):
    shown = _hashtags_shown(TXN, ["pend"], monkeypatch)
    assert shown == ["hashtags  #dog", "hashtags  #dog"]


def test_with_no_pending_hashtag_yet_the_list_shows_every_pick(fake_client, monkeypatch):
    """No hashtag carries `system_key` `pending`; a user hashtag only named like
    it is an ordinary hashtag and stays listed."""
    named_like_it = {"id": "hx", "name": "Pendiente", "system_key": None}
    tags = {"items": HASHTAGS["items"] + [named_like_it]}
    shown = _hashtags_shown({**TXN, "hashtag_ids": ["hx"]}, ["dog"], monkeypatch, tags=tags)
    assert shown == ["hashtags  #Pendiente", "hashtags  #Pendiente #dog"]


def test_an_emptied_set_sends_an_empty_list(fake_client, monkeypatch):
    """Every hashtag taken off sends `[]`: the engine files the row under the
    pending hashtag; the client never sends the pending id for it."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: WITH_PENDING)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._values["hashtags"] = []
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    assert fake_client.puts == [("/transactions/tx1", {"hashtag_ids": []})]


def test_with_no_pending_hashtag_yet_the_set_goes_as_picked(fake_client, monkeypatch):
    """The user has no pending hashtag yet (none carries `system_key`
    `pending`), so nothing is dropped; a user hashtag named like it is not it."""
    named_like_it = {"items": [{"id": "hx", "name": "Pendiente", "system_key": None}]}
    record = {**TXN, "hashtag_ids": ["hx"]}
    tags = {"items": HASHTAGS["items"] + named_like_it["items"]}
    _tag_and_save(record, ["dog"], fake_client, monkeypatch, tags=tags)
    assert fake_client.puts == [("/transactions/tx1", {"hashtag_ids": ["hx", "h1"]})]


@pytest.mark.parametrize(("code", "status", "reason", "line"), HASHTAG_REFUSALS)
def test_a_hashtag_refusal_on_the_form_shows_as_sent(
    fake_client, monkeypatch, code, status, reason, line
):
    """The engine's words whole, then its line if the reason has one; the form
    stays."""
    err = hashtag_refusal(code, status, reason)
    fake_client.errors["PUT"] = err
    notices = _tag_and_save(ON_PENDING, ["dog"], fake_client, monkeypatch, settle=bool)
    assert notices == [("Failed", refusal_text(err, line))]


def test_a_save_on_an_archived_account_shows_the_engine_words_alone(fake_client, monkeypatch):
    """Screen 3 A of expense-world-archived-account.html: the form was opened
    before the row's account was archived, and a new amount is saved. The
    "Failed" note is the engine's words, its field's words under them, and no
    line of the app's; the form stays open with what was typed."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)
    err = archived_refusal(422, ARCHIVED_PUT_WORDS, "amount_cents")
    fake_client.errors["PUT"] = err

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("amount")
        _enter(screen, "-50.00")
        typed = dict(screen._values)
        screen.action_submit()
        await wait_for(pilot, lambda: notices and not screen._submitting)
        assert notices == [
            (
                "Failed",
                f"VALIDATION_ERROR — {ARCHIVED_PUT_WORDS}\n  amount_cents: {ARCHIVED_FIELD_WORDS}",
            )
        ]
        assert notices[0][1] == refusal_text(err, None)
        assert app.screen is screen
        assert screen._values == typed

    run_app(scenario)
    assert fake_client.puts == [("/transactions/tx1", {"amount_cents": -5000})]


# ---- a part of a split purchase: the every-part note (screen 1 B) ----------
# expense-world-edit-part.html: on a part, the hint under the bar adds the note
# while the cursor is on date, title or account, and says nothing on the others.

LINE_PATH = "/bank-lines/bl1"
EVERY_PART = "changes every part of the transaction"
#: Every field of the form, in its order, with the hint it shows on any row.
FIELD_HINTS = [
    ("date", "YYYY-MM-DD · enter to accept, or type a date"),
    ("title", "free text · enter to go on"),
    ("amount", "signed decimal · − expense / + income · in the account's currency"),
    ("account", "pick an existing account · ↑↓ highlight · enter select"),
    ("category", "pick an existing category · ↑↓ highlight · enter select"),
    ("hashtags", "type a tag · ↑↓ highlight · enter adds & stays · empty enter = done (optional)"),
    ("note", "optional · enter saves · (ctrl+s anytime)"),
]


def _bank_line(part_count: int) -> dict:
    """A bank line as the engine reads it (contract: GET /v1/bank-lines/{bank_line_id})."""
    return {
        "id": "bl1",
        "line_code": line_code_of("bl1"),
        "account_id": "acc1",
        "operation_code": None,
        "statement_line": None,
        "statement_place": None,
        "net_cents": -10000 if part_count > 1 else -4250,
        "part_count": part_count,
        "parts": [
            import_part(tx_id, amount, account_id="acc1", line="bl1")
            for tx_id, amount in [("tx1", -6000), ("tx2", -4000)][:part_count]
        ]
        if part_count > 1
        else [import_part("tx1", -4250, account_id="acc1", line="bl1")],
        "edit_limits": edit_limits(),
    }


@pytest.fixture
def line_client(fake_client, monkeypatch):
    """`fake_client`, also answering the shared reads' `fetch_body`, so the bank-line
    read goes through `reads.fetch_bank_line` to the fake engine. Reference lists stay
    patched as `_patch` does."""
    monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)
    _patch(monkeypatch)
    return fake_client


def _line_reads(client) -> list[tuple[str, str]]:
    return [r for r in client.requests if r[1].startswith("/bank-lines/")]


async def _open_and_settle(app, pilot, client, record=TXN) -> EditFormScreen:
    """Open the form and wait for both of its opening reads to finish."""
    screen = EditFormScreen(record=record, resource="transactions")
    await app.push_screen(screen)
    await _wait_loaded(screen, pilot)
    await wait_for(pilot, lambda: _line_reads(client))
    await app.workers.wait_for_complete()
    await pilot.pause()
    return screen


async def _hints_by_field(screen, pilot) -> dict[str, Text]:
    """The `#hint` line on each field, reached by `tab` from the first."""
    seen: dict[str, Text] = {}
    for key, _ in FIELD_HINTS:
        assert screen._key == key
        seen[key] = screen.query_one("#hint", Static).content
        await pilot.press("tab")
    return seen


def test_a_part_of_a_split_purchase_notes_every_part_on_date_title_and_account(line_client):
    """`part_count` 2: date, title and account read their hint, then
    `· changes every part of the purchase` in the accent; amount, category,
    hashtags and note read their hint alone."""
    line_client.get_responses[LINE_PATH] = _bank_line(2)

    async def scenario(pilot, app):
        screen = await _open_and_settle(app, pilot, line_client)
        assert screen._split_part
        return await _hints_by_field(screen, pilot)

    hints = run_app(scenario)
    for key, hint in FIELD_HINTS:
        shown = hints[key]
        if key in ("date", "title", "account"):
            assert shown.plain == f"{hint} · {EVERY_PART}"
            note = shown.plain.index(EVERY_PART)
            styles = {str(s.style) for s in shown.spans if s.start <= note < s.end}
            assert styles == {ACCENT}
            assert all(str(s.style) == "dim" for s in shown.spans if s.end <= note)
        else:
            assert shown.plain == hint
            assert EVERY_PART not in shown.plain
    assert _line_reads(line_client) == [("GET", LINE_PATH)]  # one read per opening


def test_a_row_that_is_not_split_shows_the_hints_as_on_any_row(line_client):
    """`part_count` 1: every field's hint is the form's own, dimmed, no note."""
    line_client.get_responses[LINE_PATH] = _bank_line(1)

    async def scenario(pilot, app):
        screen = await _open_and_settle(app, pilot, line_client)
        assert not screen._split_part
        return await _hints_by_field(screen, pilot)

    hints = run_app(scenario)
    for key, hint in FIELD_HINTS:
        assert hints[key].plain == hint
        assert str(hints[key].style) == "dim" and not hints[key].spans
    assert _line_reads(line_client) == [("GET", LINE_PATH)]


@pytest.mark.parametrize("network", [False, True], ids=["not-found", "network"])
def test_a_failed_bank_line_read_leaves_the_form_working_with_no_note(line_client, network):
    """The read fails (the fake engine has no such line: 404; or the connection
    drops): the form opens, shows no note on any field, and still saves a changed
    title; the engine decides on save."""
    if network:
        line_client.errors["GET"] = EngineConnectionError(
            url="https://x.invalid", original=Exception("refused")
        )

    async def scenario(pilot, app):
        screen = await _open_and_settle(app, pilot, line_client)
        assert not screen._split_part
        hints = await _hints_by_field(screen, pilot)
        screen._current = screen._sequence().index("title")
        screen._refresh_bar()
        _enter(screen, "Farmacia Central")
        screen.action_submit()
        await wait_for(pilot, lambda: line_client.puts)
        return hints

    hints = run_app(scenario)
    assert all(EVERY_PART not in hints[key].plain for key, _ in FIELD_HINTS)
    assert line_client.puts == [("/transactions/tx1", {"title": "Farmacia Central"})]
    assert _line_reads(line_client) == [("GET", LINE_PATH)]


def test_a_row_with_no_bank_line_reads_none(line_client):
    """No `bank_line_id` on the row: no bank-line read, the hints as on any row."""
    record = {k: v for k, v in TXN.items() if k != "bank_line_id"}

    async def scenario(pilot, app):
        screen = EditFormScreen(record=record, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        await app.workers.wait_for_complete()
        return str(screen.query_one("#hint", Static).content)

    assert run_app(scenario) == FIELD_HINTS[0][1]
    assert _line_reads(line_client) == []


# ---- what the save sends for an emptied field --------------------------------
# An explicit `null` is `NOT_NULL` on every field of the transaction PUT except
# `reconciliation_id` (unassigns), `title` and `operation_code` (clear them);
# `""` empties `description` (contract: PUT /v1/transactions/{transaction_id}).
NULL_CLEARS = {"reconciliation_id", "title", "operation_code"}

BANK_LINE = {
    "id": "bl1",
    "line_code": line_code_of("bl1"),
    "account_id": "acc1",
    "operation_code": "47391026",
    "statement_line": None,
    "statement_place": None,
    "part_count": 1,
    "net_cents": -4250,
    "parts": [
        {
            "id": "p1",
            "date": "2026-06-20T00:00:00Z",
            "title": "FARMACIA",
            "amount_cents": 4250,
            "transaction_type": 1,
            "line_code": line_code_of("bl1"),
            "statement_line": None,
            "statement_place": None,
        }
    ],
    "edit_limits": edit_limits(),
}


TXN_FIELDS = ["date", "title", "amount", "account", "category", "hashtags", "note"]
LINE_FIELDS = ["date", "title", "operation", "amount", "account"]
# The exact save an emptied field sends, for the fields whose save the null check pins,
# keyed by (form, field).
EMPTIED_FIELD_PUTS = {
    ("transaction", "note"): [("/transactions/tx1", {"description": ""})],
    ("bank_line", "operation"): [("/transactions/p1", {"operation_code": None})],
}


def test_the_null_check_covers_every_field_of_both_forms():
    from expense.tui.screens.edit_form import BankLineEditFormScreen

    assert EditFormScreen(record=TXN)._sequence() == TXN_FIELDS
    assert BankLineEditFormScreen(line=BANK_LINE)._sequence() == LINE_FIELDS


def _nulls(body: dict) -> set[str]:
    return {key for key, value in body.items() if value is None}


def test_an_emptied_note_sends_an_empty_description_and_says_saved(fake_client, monkeypatch):
    """`⏎` on an emptied NOTE empties the note: the PUT carries
    `description: ""`, never `null`, and the form says `Saved.`."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("note")
        screen._refresh_bar()
        assert screen.query_one("#bar", Input).value == "receta"
        _enter(screen, "")
        await wait_for(pilot, lambda: ("", "Saved.") in notices)

    run_app(scenario)
    assert fake_client.puts == [("/transactions/tx1", {"description": ""})]


def test_an_empty_note_on_a_row_with_none_is_no_change(fake_client, monkeypatch):
    """A row with no note, `⏎` on the empty NOTE: nothing to empty, nothing sent."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)
    record = {k: v for k, v in TXN.items() if k != "description"}

    async def scenario(pilot, app):
        screen = EditFormScreen(record=record, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("note")
        screen._refresh_bar()
        _enter(screen, "")
        await wait_for(pilot, lambda: notices)

    run_app(scenario)
    assert notices == [("", "No changes to save.")]
    assert fake_client.puts == []


@pytest.mark.parametrize(
    ("form", "field"),
    [
        *[("transaction", f) for f in TXN_FIELDS],
        *[("bank_line", f) for f in LINE_FIELDS],
    ],
)
def test_an_emptied_field_never_sends_null_where_the_engine_refuses_it(
    fake_client, monkeypatch, form, field
):
    """Every field of both Edit forms, its bar emptied and `⏎`, then saved:
    whatever the form sends holds `null` only on a field `null` clears. An
    emptied date commits today, an emptied title or amount is refused, an empty
    account or category picks the first name, an emptied operation clears the
    operation code and an emptied note sends `""`."""
    from expense.tui.screens.edit_form import BankLineEditFormScreen

    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = (
            EditFormScreen(record=TXN, resource="transactions")
            if form == "transaction"
            else BankLineEditFormScreen(line=BANK_LINE)
        )
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index(field)
        screen._refresh_bar()
        _enter(screen, "")
        screen.action_submit()  # a no-op when `⏎` already saved
        await wait_for(pilot, lambda: notices)

    run_app(scenario)
    for _path, body in fake_client.puts:
        assert _nulls(body) <= NULL_CLEARS, body
    if (form, field) in EMPTIED_FIELD_PUTS:
        assert fake_client.puts == EMPTIED_FIELD_PUTS[form, field]


def test_every_field_changed_at_once_sends_null_only_where_it_clears(fake_client, monkeypatch):
    """Date, title, amount, account, hashtags changed and the note emptied, in
    one save: the one `null` is the `reconciliation_id` the move adds."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        _enter(screen, "2026-07-01")  # date
        _enter(screen, "Inkafarma")  # title
        _enter(screen, "-10.00")  # amount
        _enter(screen, "BCP USD")  # account
        _enter(screen, "Mascotas")  # category, as it is
        _enter(screen, "traveling")  # hashtags: adds one and stays
        _enter(screen, "")  # hashtags done
        _enter(screen, "")  # note emptied: saves
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    [(path, body)] = fake_client.puts
    assert path == "/transactions/tx1"
    assert _nulls(body) == {"reconciliation_id"}
    assert body["description"] == ""
    assert body["title"] == "Inkafarma"
    assert body["amount_cents"] == -1000
    assert body["account_id"] == "acc2"
    assert body["hashtag_ids"] == ["h1", "h2"]
    assert body["date"].startswith("2026-07-01T00:00:00")


# ---- an archived account's transaction: the read-only lines alone (screen 2 B) ----
# expense-world-archived-account.html, screen 2 B. Only the categorisation of an
# archived account's transaction changes, and the refusal is on keys, not
# changed values (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts");
# an empty title or operation code may be filled once
# (contract: PUT /v1/transactions/{transaction_id}, "An empty field may be filled").

ARCHIVED_ACCOUNT = {
    "id": "accX",
    "name": "Old bank",
    "currency_code": "PEN",
    "is_person": False,
    "is_archived": True,
    "opening_balance_transaction_id": None,
    "statement_code": None,
}
ON_ARCHIVED = {**TXN, "account_id": "accX", "reconciliation_id": None}
#: The keys no save on an archived account's transaction ever holds (an empty
#: title or operation code filled aside).
FROZEN_KEYS = {"amount_cents", "date", "title", "operation_code", "account_id", "reconciliation_id"}
#: Each frozen field of the transaction form, by its form key: a new value, and
#: its current one (pairs, not a dict: the drift check reads dict keys as fields).
FROZEN_VALUES = dict(
    [
        ("date", ("2026-06-21", "2026-06-20")),
        ("title", ("Farmacia Inkafarma", "Farmacia")),
        ("amount", (-5000, -4250)),
        ("account", ("acc2", "accX")),
    ]
)
WITH_SALUD = {"items": [*CATEGORIES["items"], {"id": "cat2", "name": "Salud", "is_system": False}]}


def _patch_archived(monkeypatch, *, categories=CATEGORIES):
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole([*ACCOUNTS, ARCHIVED_ACCOUNT])
    )
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: categories)


def _summary_rows(screen) -> list[tuple[Text, Text]]:
    table = screen._summary_renderable()
    labels, values = (list(column._cells) for column in table.columns)
    return list(zip(labels, values, strict=True))


def test_an_archived_accounts_row_shows_date_title_amount_and_account_read_only(
    fake_client, monkeypatch
):
    """Screen 2 B: date, title, amount and account read `… read-only`, dimmed,
    as an opening balance's locked lines are; the form opens on CATEGORY, a
    field move never lands on them, and no line says why."""
    _patch_archived(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=ON_ARCHIVED, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        assert screen._locked == {"date", "title", "amount", "account"}
        assert screen._key == "category"
        assert screen.query_one("#bar", Input).value == ""
        assert screen.query_one("#hint", Static).content.plain == (
            "pick an existing category · ↑↓ highlight · enter select"
        )
        summary = render_text(screen._summary_renderable(), width=60)
        assert [line.rstrip() for line in summary.splitlines()] == [
            "date      2026-06-20  read-only",
            "title     Farmacia  read-only",
            "amount    -42.50  read-only",
            "account   Old bank  read-only",
            "category  Mascotas",
            "hashtags  #dog",
            "note      receta",
        ]
        for label, value in _summary_rows(screen)[:4]:
            assert (label.style, value.style) == ("dim", "dim")
        assert not screen.query("#form-head")  # no heading, no line saying why
        await pilot.press("shift+tab")
        assert screen._key == "category"  # nothing editable above it
        await pilot.press("up")
        assert screen._key == "category"
        await pilot.press("tab", "tab")
        assert screen._key == "note"
        await pilot.press("shift+tab", "shift+tab", "shift+tab")
        assert screen._key == "category"

    run_app(scenario)


def test_an_opening_balance_and_an_archived_row_look_alike_where_locked(fake_client, monkeypatch):
    """The account line of an archived account's row is drawn as an opening
    balance's: `<name>  read-only`, the label and the value dimmed; an active
    account's row locks nothing."""
    _patch_archived(monkeypatch)

    async def scenario(pilot, app):
        drawn = []
        for record in (OPENING, ON_ARCHIVED, {**ON_ARCHIVED, "account_id": "acc1"}):
            screen = EditFormScreen(record=record, resource="transactions")
            await app.push_screen(screen)
            await _wait_loaded(screen, pilot)
            drawn.append(screen)
        return drawn

    opening, archived, active = run_app(scenario)
    assert active._locked == set()
    index = TXN_FIELDS.index("account")
    [(o_label, o_value), (a_label, a_value)] = [
        _summary_rows(screen)[index] for screen in (opening, archived)
    ]
    assert (o_value.plain, a_value.plain) == ("BCP PEN  read-only", "Old bank  read-only")
    assert o_label.plain == a_label.plain == "account"
    assert (a_label.style, a_value.style) == (o_label.style, o_value.style) == ("dim", "dim")


@pytest.mark.parametrize("field", list(FROZEN_VALUES))
@pytest.mark.parametrize("which", ["new", "current"])
def test_a_frozen_field_is_never_sent_at_a_new_or_its_current_value(
    fake_client, monkeypatch, field, which
):
    """Whatever lands under a frozen field, a new value or the one it has, the
    save sends only the category change, never the field's key."""
    _patch_archived(monkeypatch, categories=WITH_SALUD)
    notices = _record_notices(monkeypatch)
    value = FROZEN_VALUES[field][0 if which == "new" else 1]

    async def scenario(pilot, app):
        screen = EditFormScreen(record=ON_ARCHIVED, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._values[field] = value
        _enter(screen, "Salud")  # category
        screen.action_submit()
        await wait_for(pilot, lambda: ("", "Saved.") in notices)

    run_app(scenario)
    assert fake_client.puts == [("/transactions/tx1", {"category_id": "cat2"})]


def test_every_frozen_field_changed_still_sends_only_the_categorisation(fake_client, monkeypatch):
    """Date, title, amount and account all set under their locks, then the
    category, a hashtag and the note changed through the bar: the save holds
    exactly those three keys."""
    _patch_archived(monkeypatch, categories=WITH_SALUD)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=ON_ARCHIVED, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._values.update({key: new for key, (new, _) in FROZEN_VALUES.items()})
        _enter(screen, "Salud")  # category
        _enter(screen, "trav")  # hashtags: adds one and stays
        _enter(screen, "")  # hashtags done
        _enter(screen, "otra receta")  # note is last: enter saves
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    [(path, body)] = fake_client.puts
    assert path == "/transactions/tx1"
    assert not FROZEN_KEYS & set(body)
    assert body == {
        "category_id": "cat2",
        "hashtag_ids": ["h1", "h2"],
        "description": "otra receta",
    }


def test_an_account_set_under_the_lock_adds_no_unassign(fake_client, monkeypatch):
    """`unassign_on_move` on an assigned row whose account is archived: a new
    account set under the lock is no move, so no `reconciliation_id` goes with
    the save and the note is a plain `Saved.`."""
    _patch_archived(monkeypatch)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record={**ON_ARCHIVED, "reconciliation_id": "rec1"})
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._values["account"] = "acc2"
        screen._current = screen._sequence().index("note")
        _enter(screen, "otra receta")
        await wait_for(pilot, lambda: notices)

    run_app(scenario)
    assert fake_client.puts == [("/transactions/tx1", {"description": "otra receta"})]
    assert notices == [("", "Saved.")]


def test_an_archived_rows_empty_title_is_filled_once(fake_client, monkeypatch):
    """A title still empty stays editable, its look and hint as on any row: the
    form opens on it, `⏎` goes on to category past amount and account, and the
    save sends `title` once. Reopened with the title filled, it is read-only."""
    _patch_archived(monkeypatch)
    untitled = {**ON_ARCHIVED, "title": None}

    async def scenario(pilot, app):
        screen = EditFormScreen(record=untitled, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        assert screen._locked == {"date", "amount", "account"}
        assert screen._key == "title"
        assert screen.query_one("#hint", Static).content.plain == "free text · enter to go on"
        assert "title     —  (optional)" in render_text(screen._summary_renderable(), width=60)
        _enter(screen, "Retiro cajero")
        assert screen._key == "category"
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)
        await wait_for(pilot, lambda: app.screen is not screen)

        reopened = EditFormScreen(record={**untitled, "title": "Retiro cajero"})
        await app.push_screen(reopened)
        await _wait_loaded(reopened, pilot)
        assert reopened._locked == {"date", "title", "amount", "account"}
        assert reopened._key == "category"
        summary = render_text(reopened._summary_renderable(), width=60)
        assert "title     Retiro cajero  read-only" in summary

    run_app(scenario)
    assert fake_client.puts == [("/transactions/tx1", {"title": "Retiro cajero"})]


def test_an_archived_rows_empty_title_left_empty_sends_no_title(fake_client, monkeypatch):
    _patch_archived(monkeypatch, categories=WITH_SALUD)

    async def scenario(pilot, app):
        screen = EditFormScreen(record={**ON_ARCHIVED, "title": None})
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("category")
        _enter(screen, "Salud")
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    assert fake_client.puts == [("/transactions/tx1", {"category_id": "cat2"})]


def test_an_opening_balance_on_an_archived_account_keeps_only_its_note(fake_client, monkeypatch):
    """Both locks at once: an opening balance's three, an archived account's
    four; the form opens on NOTE, the one field left."""
    _patch_archived(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record={**OPENING, "account_id": "accX"})
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        assert screen._locked == {"date", "title", "amount", "account", "category", "hashtags"}
        assert screen._key == "note"

    run_app(scenario)


def test_a_failed_accounts_read_leaves_an_archived_row_as_any_row(fake_client, monkeypatch):
    """With no accounts read the form cannot know the account is archived: it
    is the form of any row, and the engine judges the save."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)

    def fail(*a, **k):
        raise EngineConnectionError("engine down")

    monkeypatch.setattr("expense.reads.fetch_accounts", fail)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=ON_ARCHIVED, resource="transactions")
        await app.push_screen(screen)
        await wait_for(pilot, lambda: notices)
        assert screen._locked == set()
        assert screen._key == "date"

    run_app(scenario)


# The bank-line Edit form on an archived account's line ("no batch" opened before
# the account was archived): the same rule for date, title, operation, amount
# and account.
ARCHIVED_LINE = {**BANK_LINE, "account_id": "accX"}
UNNAMED_LINE = {
    **ARCHIVED_LINE,
    "operation_code": None,
    "parts": [{**BANK_LINE["parts"][0], "title": None}],
}


def _open_line(line, monkeypatch, steps):
    from expense.tui.screens.edit_form import BankLineEditFormScreen

    _patch_archived(monkeypatch)

    async def scenario(pilot, app):
        screen = BankLineEditFormScreen(line=line)
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        return await steps(screen, pilot, app)

    return run_app(scenario)


def test_an_archived_line_with_title_and_code_has_nothing_to_save(fake_client, monkeypatch):
    """Every field of the line is frozen and drawn read-only; values set under
    them, new or current, are never sent."""
    notices = _record_notices(monkeypatch)

    async def steps(screen, pilot, app):
        assert screen._locked == set(LINE_FIELDS)
        summary = render_text(screen._summary_renderable(), width=60)
        assert summary.count("read-only") == len(LINE_FIELDS)
        assert "operation  47391026  read-only" in summary
        screen._values.update(
            date="2026-06-21", title="OTRA", operation="1", amount=-1, account="acc2"
        )
        screen.action_submit()
        screen._values.update(
            date="2026-06-20", title="FARMACIA", operation="47391026", amount=-4250, account="accX"
        )
        screen.action_submit()
        await wait_for(pilot, lambda: len(notices) == 2)

    _open_line(ARCHIVED_LINE, monkeypatch, steps)
    assert fake_client.puts == []
    assert notices == [("", "No changes to save.")] * 2


def test_an_archived_line_with_title_and_code_says_nothing_can_change(fake_client, monkeypatch):
    """Pick 3 B of expense-world-wording-picks.html: with every line read-only
    the bar sits on DATE and the hint under it says nothing here can change and
    `esc` leaves, in place of DATE's own; keys pressed there change neither the
    line nor the hint, and `esc` leaves."""
    from expense.tui.screens.edit_form import NOTHING_CAN_CHANGE

    assert NOTHING_CAN_CHANGE == (
        "read-only · its account is archived, so nothing here can change · esc to leave"
    )

    async def steps(screen, pilot, app):
        hint = screen.query_one("#hint", Static)
        assert screen._locked == set(LINE_FIELDS)
        assert screen._key == "date"
        assert hint.content.plain == NOTHING_CAN_CHANGE
        assert hint.content.style == "dim"
        await pilot.press("tab", "2", "shift+tab")
        await pilot.pause()
        assert screen._key == "date"
        assert hint.content.plain == NOTHING_CAN_CHANGE
        await pilot.press("escape")
        await wait_for(pilot, lambda: not screen.is_attached)

    _open_line(ARCHIVED_LINE, monkeypatch, steps)
    assert fake_client.puts == []


@pytest.mark.parametrize(
    ("line", "key", "hint"),
    [
        (
            {**ARCHIVED_LINE, "parts": [{**BANK_LINE["parts"][0], "title": None}]},
            "title",
            "free text · enter to save",  # the one line left: `⏎` saves
        ),
        ({**ARCHIVED_LINE, "operation_code": None}, "operation", None),
        (UNNAMED_LINE, "title", "free text · enter to go on"),
        (BANK_LINE, "date", None),
    ],
    ids=["archived-no-title", "archived-no-operation", "archived-neither", "not-archived"],
)
def test_a_line_still_open_keeps_its_own_hint(fake_client, monkeypatch, line, key, hint):
    """A line with a field left to change, an archived account's line with an
    empty title or operation, or a line whose account is not archived, shows
    the hint of the field the bar sits on, never the read-only one."""
    from expense.tui.screens.edit_form import _HINTS, NOTHING_CAN_CHANGE

    expected = hint or _HINTS[key]

    async def steps(screen, pilot, app):
        assert screen._key == key
        assert screen.query_one("#hint", Static).content.plain == expected
        assert expected != NOTHING_CAN_CHANGE

    _open_line(line, monkeypatch, steps)


def test_an_archived_lines_empty_operation_code_is_filled_once(fake_client, monkeypatch):
    """A line with no operation code and no title: both stay editable, the form
    opens on the title, and the save sends the two first values alone."""

    async def steps(screen, pilot, app):
        assert screen._locked == {"date", "amount", "account"}
        assert screen._key == "title"
        _enter(screen, "FARMACIA")
        assert screen._key == "operation"
        screen._values.update(date="2026-06-21", amount=-1, account="acc2")
        _enter(screen, "47391026")  # nothing editable after it: `⏎` saves
        await wait_for(pilot, lambda: fake_client.puts)

    _open_line(UNNAMED_LINE, monkeypatch, steps)
    assert fake_client.puts == [
        ("/transactions/p1", {"title": "FARMACIA", "operation_code": "47391026"})
    ]


def test_enter_on_an_archived_lines_only_open_line_saves(fake_client, monkeypatch):
    """Spec check 4: the empty operation code is the line's only open line, so
    with no line ahead that can change, a real `⏎` there sends the save."""

    async def steps(screen, pilot, app):
        assert screen._locked == {"date", "title", "amount", "account"}
        assert screen._key == "operation"
        await pilot.press(*"47391026")
        await pilot.press("enter")
        await wait_for(pilot, lambda: fake_client.puts)

    _open_line({**ARCHIVED_LINE, "operation_code": None}, monkeypatch, steps)
    assert fake_client.puts == [("/transactions/p1", {"operation_code": "47391026"})]


def test_enter_on_an_archived_lines_title_moves_one_line_to_its_code(fake_client, monkeypatch):
    """With an editable line ahead, `⏎` moves to it and sends nothing: one line
    per press, through Textual's dispatch; the code's `⏎` then saves both."""

    async def steps(screen, pilot, app):
        assert screen._key == "title"
        await pilot.press(*"farmacia")
        await pilot.press("enter")
        await pilot.pause()
        assert screen._key == "operation"
        assert fake_client.calls == []
        await pilot.press(*"47391026")
        await pilot.press("enter")
        await wait_for(pilot, lambda: fake_client.puts)

    _open_line(UNNAMED_LINE, monkeypatch, steps)
    assert fake_client.puts == [
        ("/transactions/p1", {"title": "farmacia", "operation_code": "47391026"})
    ]


@pytest.mark.parametrize("refused", [False, True], ids=["saved", "refused"])
def test_the_saves_busy_hint_stays_while_it_is_sent(fake_client, monkeypatch, refused):
    """The line's only open line is its empty title, so a real `⏎` there saves:
    while the engine's answer is held back, the hint under the bar reads
    `Saving…`, not the title's hint. Once the answer arrives the form goes on
    as before: a save closes it, a refusal brings the title's hint back."""
    notices = _record_notices(monkeypatch)
    asked, release = threading.Event(), threading.Event()
    answer = fake_client.put

    def held(path, json_body=None):
        asked.set()
        release.wait(timeout=5)
        return answer(path, json_body)

    fake_client.put = held
    if refused:
        fake_client.errors["PUT"] = EngineError("VALIDATION", "Refused.", None, 422, {})

    async def steps(screen, pilot, app):
        hint = screen.query_one("#hint", Static)
        assert screen._locked == {"date", "operation", "amount", "account"}
        assert screen._key == "title"
        await pilot.press(*"farmacia")
        try:
            await pilot.press("enter")
            await wait_for(pilot, asked.is_set)  # the PUT is in flight
            await pilot.pause()
            assert str(hint.content) == "Saving…"
        finally:
            release.set()
        await wait_for(pilot, lambda: notices)
        if refused:
            await wait_for(pilot, lambda: not screen._submitting)
            assert screen.is_attached and screen._key == "title"
            assert str(hint.content) == "free text · enter to save"
        else:
            await wait_for(pilot, lambda: not screen.is_attached)

    _open_line({**UNNAMED_LINE, "operation_code": "47391026"}, monkeypatch, steps)
    assert fake_client.puts == [("/transactions/p1", {"title": "farmacia"})]
    assert notices[0][0] == ("Failed" if refused else "")
    if not refused:
        assert notices == [("", "Saved.")]


def test_an_archived_lines_filled_code_reopens_read_only(fake_client, monkeypatch):
    async def steps(screen, pilot, app):
        assert screen._locked == {"date", "operation", "amount", "account"}
        assert screen._key == "title"

    _open_line({**UNNAMED_LINE, "operation_code": "47391026"}, monkeypatch, steps)


def test_an_archived_split_line_freezes_its_fields_too(fake_client, monkeypatch):
    """A split line shows no amount field; the other four follow the rule."""
    split = {
        **ARCHIVED_LINE,
        "part_count": 2,
        "net_cents": -10000,
        "parts": [
            {**BANK_LINE["parts"][0], "amount_cents": 6000},
            {**BANK_LINE["parts"][0], "id": "p2", "amount_cents": 4000},
        ],
    }

    async def steps(screen, pilot, app):
        assert screen._locked == {"date", "title", "operation", "account"}

    _open_line(split, monkeypatch, steps)


def _count_commits(monkeypatch, form) -> list:
    """Every run of `form`'s commit handler (`on_input_submitted`), recorded
    before it runs."""
    commits: list = []
    commit = form.__dict__["on_input_submitted"]

    def counted(self, event):
        commits.append(self._key)
        return commit(self, event)

    monkeypatch.setattr(form, "on_input_submitted", counted)
    return commits


async def _type_on_every_line_and_save(screen, pilot):
    """On a form whose every line is read-only: type, paste, delete and `⏎` on
    the line the bar opens on, then `ctrl+s`. With no line ahead that can change,
    each `⏎` saves as `ctrl+s` does. Returns the summary before and after, as
    drawn."""
    bar = screen.query_one("#bar", Input)
    before = render_text(screen._summary_renderable(), width=60)
    opened_on, shown = screen._key, bar.value
    await pilot.press(*"xyz")
    assert bar.value == shown  # the bar takes nothing typed
    await pilot.press("backspace", "ctrl+u")
    assert bar.value == shown  # nor deletes anything
    bar.post_message(events.Paste("pasted"))
    await pilot.pause()
    assert bar.value == shown  # nor anything pasted
    await pilot.press("enter")
    await pilot.pause()
    assert screen._key == opened_on  # nothing editable ahead: it stays and saves
    assert screen._values == screen._original
    await pilot.press(*"abc", "enter")
    after = render_text(screen._summary_renderable(), width=60)
    await pilot.press("ctrl+s")
    await pilot.pause()
    return before, after


@pytest.mark.parametrize("split", [False, True], ids=["whole", "split"])
def test_nothing_typed_lands_on_an_archived_line_with_title_and_code(
    fake_client, monkeypatch, split
):
    """The owner's pick A: the form opens, every line read-only, showing what the
    line holds. Typing and `⏎` on the line the bar opens on change no line, and
    neither `⏎` nor `ctrl+s` sends anything."""
    from expense.tui.screens.edit_form import BankLineEditFormScreen

    notices = _record_notices(monkeypatch)
    commits = _count_commits(monkeypatch, BankLineEditFormScreen)
    line = ARCHIVED_LINE
    if split:
        line = {
            **ARCHIVED_LINE,
            "part_count": 2,
            "net_cents": -10000,
            "parts": [
                {**BANK_LINE["parts"][0], "amount_cents": 6000},
                {**BANK_LINE["parts"][0], "id": "p2", "amount_cents": 4000},
            ],
        }

    async def steps(screen, pilot, app):
        assert screen._locked == set(screen._sequence())
        assert screen._key == "date"
        assert screen.query_one("#bar", Input).value == "2026-06-20"
        return await _type_on_every_line_and_save(screen, pilot)

    before, after = _open_line(line, monkeypatch, steps)
    assert after == before
    rows = [row.rstrip() for row in after.splitlines()[: 4 if split else 5]]
    assert rows == [
        "date       2026-06-20  read-only",
        "title      FARMACIA  read-only",
        "operation  47391026  read-only",
        *([] if split else ["amount     -42.50  read-only"]),
        "account    Old bank  read-only",
    ]
    assert "xyz" not in after and "abc" not in after
    assert commits == []  # `⏎` on a read-only line runs no field's commit
    assert fake_client.puts == [] and not fake_client.calls
    assert notices == [("", "No changes to save.")] * 3  # two `⏎`, then `ctrl+s`


def test_the_transaction_form_holds_no_reachable_read_only_line(fake_client, monkeypatch):
    """On a transaction of an archived account the bar never reaches a locked
    line (the note is never locked, so some line is always open); were every
    line read-only, the shared bar takes nothing typed there either."""
    _patch_archived(monkeypatch)
    notices = _record_notices(monkeypatch)
    commits = _count_commits(monkeypatch, EditFormScreen)

    async def scenario(pilot, app):
        for record in (ON_ARCHIVED, {**OPENING, "account_id": "accX"}):
            screen = EditFormScreen(record=record, resource="transactions")
            await app.push_screen(screen)
            await _wait_loaded(screen, pilot)
            for key in ("shift+tab", "up", "ctrl+up", "tab", "tab", "tab", "down", "ctrl+down"):
                await pilot.press(key)
                assert screen._key not in screen._locked
            app.pop_screen()
            await pilot.pause()
        screen = EditFormScreen(record=ON_ARCHIVED, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._locked |= set(screen._sequence())
        screen._current = screen._first_editable()
        screen._refresh_bar()
        before, after = await _type_on_every_line_and_save(screen, pilot)
        assert after == before

    run_app(scenario)
    assert commits == []
    assert fake_client.puts == [] and not fake_client.calls
    assert notices == [("", "No changes to save.")] * 3  # two `⏎`, then `ctrl+s`


# ---- stepping through the form never changes it --------------------------------
# ACCOUNT and CATEGORY open with the bar empty and the highlight on the line's own
# account or category, so `⏎` with nothing typed keeps it (Question 1 A of
# expense-world-enter-and-esc.html). The row sits on the third account and the
# second category, so a highlight left on the first entry would move it.
STEP_CATEGORIES = {
    "items": [
        {"id": "cat1", "name": "Mascotas", "is_system": False},
        {"id": "cat2", "name": "Salud", "is_system": False},
        {"id": "cat3", "name": "Hogar", "is_system": False},
        *CATEGORIES["items"][1:],
    ]
}
ON_THIRD = {**TXN, "account_id": "acc3", "category_id": "cat2"}
LINE_ON_THIRD = {**BANK_LINE, "account_id": "acc3"}


def _open_stepping(form, monkeypatch, steps, categories=STEP_CATEGORIES):
    """Open `form()` over the step lists and run `steps(screen, pilot)`; returns
    the notices it raised."""
    _patch(monkeypatch)
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: categories)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = form()
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        await app.workers.wait_for_complete()
        await pilot.pause()
        await steps(screen, pilot)

    run_app(scenario)
    return notices


async def _enter_to(screen, pilot, key):
    """Press `⏎` until the cursor is on `key`, nothing typed on the way."""
    while screen._key != key:
        await pilot.press("enter")


def _highlighted(screen) -> str:
    return screen._suggestions[screen._suggest_idx][1]


def test_enter_through_every_line_then_ctrl_s_sends_nothing(fake_client, monkeypatch):
    """`⏎` on every line, the note's `⏎` saving, then `ctrl+s`: nothing changed,
    so nothing is sent and both saves say so."""

    async def steps(screen, pilot):
        visited = []
        for _ in screen._sequence():
            visited.append(screen._key)
            await pilot.press("enter")
        assert visited == TXN_FIELDS
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert screen._values == screen._original

    notices = _open_stepping(
        lambda: EditFormScreen(record=ON_THIRD, resource="transactions"), monkeypatch, steps
    )
    assert fake_client.puts == [] and not fake_client.calls
    assert notices == [("", "No changes to save.")] * 2


SPLIT_LINE_ON_THIRD = {
    **LINE_ON_THIRD,
    "part_count": 2,
    "net_cents": -10000,
    "parts": [
        {**BANK_LINE["parts"][0], "amount_cents": 6000},
        {**BANK_LINE["parts"][0], "id": "p2", "amount_cents": 4000},
    ],
}


@pytest.mark.parametrize("line", [LINE_ON_THIRD, SPLIT_LINE_ON_THIRD], ids=["whole", "split"])
def test_enter_through_every_line_of_the_bank_line_form_sends_nothing(
    fake_client, monkeypatch, line
):
    """One line per `⏎`, none skipped; `⏎` on ACCOUNT, the last line, saves, and
    with nothing changed nothing is sent."""
    from expense.tui.screens.edit_form import BankLineEditFormScreen

    async def steps(screen, pilot):
        visited = []
        for _ in screen._sequence():
            visited.append(screen._key)
            if screen._key == "account":
                assert _highlighted(screen) == "Ahorros"
            await pilot.press("enter")
        assert visited == screen._sequence()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert screen._values == screen._original
        assert screen._values["account"] == "acc3"

    notices = _open_stepping(lambda: BankLineEditFormScreen(line=line), monkeypatch, steps)
    assert fake_client.puts == [] and not fake_client.calls
    assert notices == [("", "No changes to save.")] * 2


@pytest.mark.parametrize(
    ("key", "own_id", "own_name"), [("account", "acc3", "Ahorros"), ("category", "cat2", "Salud")]
)
def test_an_untouched_entity_line_starts_on_its_own_value_and_enter_keeps_it(
    fake_client, monkeypatch, key, own_id, own_name
):
    """The list stays in its order, every entry shown; the highlight is on the
    row's own one, and `⏎` keeps it and moves on."""

    async def steps(screen, pilot):
        await _enter_to(screen, pilot, key)
        assert screen.query_one("#bar", Input).value == ""
        pool = screen._accounts if key == "account" else screen._categories
        assert screen._suggestions == pool  # the usual order, nothing filtered
        assert _highlighted(screen) == own_name
        shown = render_text(screen._suggest_renderable(), width=60)
        assert own_name in shown
        await pilot.press("enter")
        assert screen._values[key] == own_id
        assert screen._display[key] == own_name
        assert screen._key != key  # moved on

    _open_stepping(
        lambda: EditFormScreen(record=ON_THIRD, resource="transactions"), monkeypatch, steps
    )


def test_typing_a_name_then_enter_still_picks_the_typed_one(fake_client, monkeypatch):
    """Typing filters the list and highlights its first match; `⏎` takes it."""

    async def steps(screen, pilot):
        await _enter_to(screen, pilot, "account")
        await pilot.press(*"usd")
        assert [e[1] for e in screen._suggestions] == ["BCP USD"]
        await pilot.press("enter")
        assert screen._values["account"] == "acc2"
        assert screen._key == "category"
        await pilot.press(*"hog")
        assert _highlighted(screen) == "Hogar"
        await pilot.press("enter")
        assert screen._values["category"] == "cat3"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    _open_stepping(
        lambda: EditFormScreen(record=ON_THIRD, resource="transactions"), monkeypatch, steps
    )
    path, body = fake_client.puts[0]
    assert path == "/transactions/tx1"
    assert body["account_id"] == "acc2" and body["category_id"] == "cat3"


def test_arrows_still_choose_another_and_an_erased_bar_returns_to_the_own_one(
    fake_client, monkeypatch
):
    async def steps(screen, pilot):
        await _enter_to(screen, pilot, "category")
        assert _highlighted(screen) == "Salud"
        await pilot.press(*"mas")
        assert _highlighted(screen) == "Mascotas"
        await pilot.press("backspace", "backspace", "backspace")
        assert screen.query_one("#bar", Input).value == ""
        assert _highlighted(screen) == "Salud"  # empty again: back on the row's own
        await pilot.press("down")
        assert _highlighted(screen) == "Hogar"
        await pilot.press("enter")
        assert screen._values["category"] == "cat3"

    _open_stepping(
        lambda: EditFormScreen(record=ON_THIRD, resource="transactions"), monkeypatch, steps
    )


# ---- @Pendiente is in the CATEGORY list, where the engine lists it --------------
# Question 3 A of expense-world-enter-and-esc.html: the Edit form's category list is
# the bulk `c` pick's (`reads.pickable_categories`), so a row in @Pendiente starts on
# it and a row can be sent back there; @Opening is never offered. The engine lists
# @Pendiente between two user categories here, so its place is the engine's.
PENDING_CAT = {"id": "catP", "name": "@Pendiente", "is_system": True, "system_key": "pending"}
WITH_PENDING_CATEGORIES = {
    "items": [
        STEP_CATEGORIES["items"][0],
        PENDING_CAT,
        *STEP_CATEGORIES["items"][1:],
    ]
}
IN_PENDING = {**ON_THIRD, "category_id": "catP"}


def _open_with_pending(record, monkeypatch, steps):
    return _open_stepping(
        lambda: EditFormScreen(record=record, resource="transactions"),
        monkeypatch,
        steps,
        categories=WITH_PENDING_CATEGORIES,
    )


def test_a_row_in_pendiente_starts_on_it_and_enter_through_every_line_sends_nothing(
    fake_client, monkeypatch
):
    """CATEGORY lists @Pendiente in the engine's place, highlighted; `⏎` on every
    line, the note's `⏎` saving, then `ctrl+s`: nothing changed, nothing sent."""

    async def steps(screen, pilot):
        for _ in screen._sequence():
            if screen._key == "category":
                names = [name for _id, name in screen._suggestions]
                assert names == ["Mascotas", "@Pendiente", "Salud", "Hogar"]
                assert _highlighted(screen) == "@Pendiente"
            await pilot.press("enter")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert screen._values == screen._original
        assert screen._values["category"] == "catP"

    notices = _open_with_pending(IN_PENDING, monkeypatch, steps)
    assert fake_client.puts == [] and not fake_client.calls
    assert notices == [("", "No changes to save.")] * 2


def test_picking_pendiente_on_a_categorised_row_sends_its_id(fake_client, monkeypatch):
    """Typing `pend` highlights @Pendiente; `⏎` takes it and the save sends its id,
    the row going back to waiting for a category."""

    async def steps(screen, pilot):
        await _enter_to(screen, pilot, "category")
        assert _highlighted(screen) == "Salud"
        await pilot.press(*"pend")
        assert [name for _id, name in screen._suggestions] == ["@Pendiente"]
        await pilot.press("enter")
        assert screen._display["category"] == "@Pendiente"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    _open_with_pending(ON_THIRD, monkeypatch, steps)
    assert fake_client.puts == [("/transactions/tx1", {"category_id": "catP"})]


def test_opening_is_never_offered_on_category(fake_client, monkeypatch):
    """@Opening is not in the list, empty or filtered, and typing its name
    matches nothing: `⏎` refuses and the line stays."""

    async def steps(screen, pilot):
        await _enter_to(screen, pilot, "category")
        assert "catO" not in [ent[0] for ent in screen._suggestions]
        assert "@Opening" not in render_text(screen._suggest_renderable(), width=60)
        await pilot.press(*"open")
        assert screen._suggestions == []
        await pilot.press("enter")
        assert screen._key == "category"
        assert screen._values["category"] == "cat2"

    notices = _open_with_pending(ON_THIRD, monkeypatch, steps)
    assert ("", "No category matches “open”.") in notices
    assert fake_client.puts == []


# ---- a date the save cannot read is refused at ⏎ ------------------------------


def _date_notes(monkeypatch) -> list[tuple[str, object]]:
    notes: list[tuple[str, object]] = []
    monkeypatch.setattr(
        EditFormScreen,
        "notify",
        lambda self, message, **kw: notes.append((str(message), kw.get("severity"))),
    )
    return notes


def _keys(text: str) -> list[str]:
    return ["space" if ch == " " else ch for ch in text]


def _date_form(form: str) -> EditFormScreen:
    from expense.tui.screens.edit_form import BankLineEditFormScreen

    if form == "transaction":
        return EditFormScreen(record=TXN, resource="transactions")
    return BankLineEditFormScreen(line=BANK_LINE)


FORMS_AND_PATHS = [("transaction", "/transactions/tx1"), ("bank_line", "/transactions/p1")]


@pytest.mark.parametrize(("form", "path"), FORMS_AND_PATHS)
def test_a_non_date_on_date_is_refused_at_enter_and_the_save_never_crashes(
    fake_client, monkeypatch, form, path
):
    """Typed key by key on DATE: `abc` + `⏎` notes `Date: use YYYY-MM-DD.`, the
    bar keeps `abc` and the cursor stays on DATE; `ctrl+s` then sends nothing and
    the app goes on running, on the Edit form and on the "no batch" Edit form."""
    from expense.tui.screens.edit_form import DATE_UNREADABLE

    _patch(monkeypatch)
    notes = _date_notes(monkeypatch)

    async def scenario(pilot, app):
        screen = _date_form(form)
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        bar = screen.query_one("#bar", Input)
        assert screen._key == "date"
        await pilot.press("ctrl+a", "ctrl+k", *"abc", "enter")
        await pilot.pause()
        assert screen._key == "date" and bar.value == "abc"
        assert screen._values["date"] == "2026-06-20"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: ("No changes to save.", None) in notes)
        assert app.is_running and app.screen is screen

    run_app(scenario)
    assert DATE_UNREADABLE == "Date: use YYYY-MM-DD."
    assert notes == [(DATE_UNREADABLE, "error"), ("No changes to save.", None)]
    assert fake_client.puts == []


@pytest.mark.parametrize(("form", "path"), FORMS_AND_PATHS)
@pytest.mark.parametrize("typed", ["2026-10-23", "2026-10-23 14:30"])
def test_a_day_with_or_without_a_time_still_saves(fake_client, monkeypatch, form, path, typed):
    """A day on DATE, with or without a time, is taken at `⏎` and saved as the
    save's reader writes it, after a refused `abc` as on a first try."""
    from expense.dates import to_canonical_aware

    _patch(monkeypatch)
    notes = _date_notes(monkeypatch)

    async def scenario(pilot, app):
        screen = _date_form(form)
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        await pilot.press("ctrl+a", "ctrl+k", *"abc", "enter")
        await pilot.pause()
        await pilot.press("ctrl+a", "ctrl+k", *_keys(typed), "enter")
        await pilot.pause()
        assert screen._key == "title"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    assert notes[0] == ("Date: use YYYY-MM-DD.", "error")
    assert fake_client.puts == [(path, {"date": to_canonical_aware(typed)})]


def test_an_empty_date_still_commits_today(fake_client, monkeypatch):
    """An emptied DATE and `⏎` is no refusal: it commits today, as before."""
    from datetime import date

    from expense.dates import to_canonical_aware

    _patch(monkeypatch)
    notes = _date_notes(monkeypatch)

    async def scenario(pilot, app):
        screen = _date_form("transaction")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        await pilot.press("ctrl+a", "ctrl+k", "enter")
        await pilot.pause()
        assert screen._key == "title"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    assert not [n for n in notes if n[1] == "error"]
    today = to_canonical_aware(date.today().isoformat())
    assert fake_client.puts == [("/transactions/tx1", {"date": today})]
