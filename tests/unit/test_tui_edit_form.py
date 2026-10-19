"""The bar-cycle transaction **edit** form (fake client).

Edit-only: creating is the LOG bar's — see
[test_tui_log_bar.py](test_tui_log_bar.py). The form owns pre-fill, the diffed
PUT, and the suggestion pickers.
"""

import pytest
from rich.text import Text
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
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_NAMES,
    HASHTAG_REFUSALS,
    hashtag_refusal,
    import_part,
    in_order,
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
    },
    {
        "id": "acc2",
        "name": "BCP USD",
        "currency_code": "USD",
        "is_person": False,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "acc3",
        "name": "Ahorros",
        "currency_code": "PEN",
        "is_person": False,
        "opening_balance_transaction_id": None,
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


def test_moving_an_assigned_row_unassigns_it_and_says_so(fake_client, monkeypatch):
    notices, _seen = _move_and_save(
        ASSIGNED, "BCP USD", fake_client, monkeypatch, settle=lambda s, n: n
    )
    assert fake_client.puts == [
        ("/transactions/tx1", {"account_id": "acc2", "reconciliation_id": None})
    ]
    assert ("", "Saved. It left its reconciliation.") in notices


def test_moving_an_unassigned_row_still_sends_the_unassign_and_says_saved(fake_client, monkeypatch):
    """No path sends an account change without `reconciliation_id`; the note
    speaks only when the row was in a reconciliation."""
    notices, _seen = _move_and_save(
        {**TXN, "reconciliation_id": None},
        "BCP USD",
        fake_client,
        monkeypatch,
        settle=lambda s, n: n,
    )
    assert fake_client.puts == [
        ("/transactions/tx1", {"account_id": "acc2", "reconciliation_id": None})
    ]
    assert ("", "Saved.") in notices


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


ARCHIVED_ACCOUNT = {
    "id": "accX",
    "name": "Old bank",
    "currency_code": "PEN",
    "is_person": False,
    "is_archived": True,
    "opening_balance_transaction_id": None,
}


def test_a_row_on_an_archived_account_saves_every_other_field_without_its_account(
    fake_client, monkeypatch
):
    """The engine refuses a `PUT` that sends an archived account's id as
    `account_id`, even unchanged, and takes every other field
    (contract: POST /v1/accounts/{account_id}/archive). So an edit that
    leaves the account alone never sends `account_id`, on a row whose account
    is archived too, and the account field offers no archived account."""
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole([*ACCOUNTS, ARCHIVED_ACCOUNT])
    )
    record = {**TXN, "account_id": "accX"}

    async def scenario(pilot, app):
        screen = EditFormScreen(record=record, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        for key, text in (
            ("date", "2026-06-21"),
            ("title", "Farmacia Inkafarma"),
            ("amount", "-50"),
            ("category", "Masc"),
            ("hashtags", "trav"),
        ):
            screen._current = screen._sequence().index(key)
            _enter(screen, text)
        # the cursor passes the account field without picking anything
        screen._current = screen._sequence().index("account")
        screen._recompute("")
        assert "accX" not in [ent[0] for ent in screen._suggestions]
        screen.action_field(1)
        screen._current = screen._sequence().index("note")
        _enter(screen, "otra receta")  # note is last: enter saves
        await wait_for(pilot, lambda: fake_client.puts)

    run_app(scenario)
    [(path, body)] = fake_client.puts
    assert path == "/transactions/tx1"
    assert "account_id" not in body and "reconciliation_id" not in body
    assert body.pop("date").startswith("2026-06-21")
    assert body == {
        "title": "Farmacia Inkafarma",
        "amount_cents": -5000,
        "hashtag_ids": ["h1", "h2"],
        "description": "otra receta",
    }


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


# ---- a part of a split purchase: the every-part note (screen 1 B) ----------
# expense-world-edit-part.html: on a part, the hint under the bar adds the note
# while the cursor is on date, title or account, and says nothing on the others.

LINE_PATH = "/bank-lines/bl1"
EVERY_PART = "changes every part of the transaction"
#: Every field of the form, in its order, with the hint it shows on any row.
FIELD_HINTS = [
    ("date", "YYYY-MM-DD · enter to accept, or type a date"),
    ("title", "free text · enter to save"),
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
        "account_id": "acc1",
        "operation_code": None,
        "net_cents": -10000 if part_count > 1 else -4250,
        "part_count": part_count,
        "parts": [
            import_part(tx_id, amount, account_id="acc1", line="bl1")
            for tx_id, amount in [("tx1", -6000), ("tx2", -4000)][:part_count]
        ]
        if part_count > 1
        else [import_part("tx1", -4250, account_id="acc1", line="bl1")],
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
    "account_id": "acc1",
    "operation_code": "47391026",
    "part_count": 1,
    "net_cents": -4250,
    "parts": [
        {
            "id": "p1",
            "date": "2026-06-20T00:00:00Z",
            "title": "FARMACIA",
            "amount_cents": 4250,
            "transaction_type": 1,
        }
    ],
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
    code and an emptied note sends `""`."""
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
