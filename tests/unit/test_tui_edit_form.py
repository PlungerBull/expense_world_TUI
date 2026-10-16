"""The bar-cycle transaction **edit** form (fake client).

Edit-only: creating is the LOG bar's — see
[test_tui_log_bar.py](test_tui_log_bar.py). The form owns pre-fill, the diffed
PUT, and the suggestion pickers.
"""

import pytest
from textual.widgets import Input

from expense.errors import EngineConnectionError, EngineError
from expense.tui.screens.create_forms import (
    EditAccountScreen,
    EditCategoryScreen,
    EditHashtagScreen,
    NewAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from expense.tui.screens.edit_form import EditFormScreen
from tests.unit.helpers import (
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_NAMES,
    HASHTAG_REFUSALS,
    hashtag_refusal,
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


def test_an_opening_balance_shows_account_and_category_read_only(fake_client, monkeypatch):
    """The two lines show dimmed and marked read-only; a field move skips
    them, from amount straight to hashtags and back."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=OPENING, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        assert screen._locked == {"account", "category"}
        summary = render_text(screen._summary_renderable(), width=60)
        assert "account   BCP PEN  read-only" in summary
        assert "category  @Opening  read-only" in summary
        assert summary.count("read-only") == 2
        screen._current = screen._sequence().index("amount")
        screen.action_field(1)
        assert screen._key == "hashtags"
        screen.action_field(-1)
        assert screen._key == "amount"

    run_app(scenario)


def test_an_opening_balance_saves_its_other_fields_and_never_its_account(fake_client, monkeypatch):
    """Amount, date, title, note and hashtags save as on any row; the PUT
    carries no account and no category, even if a value was set under them."""
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=OPENING, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        screen._current = screen._sequence().index("amount")
        _enter(screen, "3500")
        assert screen._key == "hashtags"  # account and category skipped
        _enter(screen, "dog")
        _enter(screen, "")  # done with hashtags → note
        # whatever lands under the locked keys is never sent
        screen._values.update(account="acc2", category="cat1")
        screen._current = screen._sequence().index("note")
        _enter(screen, "apertura")  # enter on note saves
        await wait_for(pilot, lambda: fake_client.puts)
        assert fake_client.puts == [
            (
                "/transactions/txO",
                {"amount_cents": 350000, "hashtag_ids": ["h1"], "description": "apertura"},
            )
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
