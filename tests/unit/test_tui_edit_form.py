"""The bar-cycle transaction **edit** form (fake client).

Edit-only: creating is the LOG bar's — see
[test_tui_log_bar.py](test_tui_log_bar.py). The form owns pre-fill, the diffed
PUT, and the suggestion pickers.
"""

import pytest
from textual.widgets import Input

from expense.errors import EngineConnectionError
from expense.tui.screens.create_forms import (
    EditAccountScreen,
    EditCategoryScreen,
    EditHashtagScreen,
    NewAccountScreen,
    NewCategoryScreen,
    NewHashtagScreen,
)
from expense.tui.screens.edit_form import EditFormScreen
from tests.unit.helpers import render_text, run_app, wait_for, whole

ACCOUNTS = [
    {"id": "acc1", "name": "BCP PEN", "currency_code": "PEN", "is_person": False},
    {"id": "acc2", "name": "BCP USD", "currency_code": "USD", "is_person": False},
    {"id": "acc3", "name": "Ahorros", "currency_code": "PEN", "is_person": False},
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
    monkeypatch.setattr(
        "expense.commands.accounts_cmd.fetch_accounts", lambda *a, **k: whole(ACCOUNTS)
    )
    monkeypatch.setattr(
        "expense.commands.categories_cmd.fetch_categories", lambda *a, **k: CATEGORIES
    )
    monkeypatch.setattr("expense.commands.hashtags_cmd.fetch_hashtags", lambda *a, **k: HASHTAGS)


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
}


def test_load_entities_three_superset_queries(fake_client, monkeypatch):
    """The form loads each resource once and derives both the suggestion pools
    and the full name maps — three queries, not six. Only the
    accounts fetch is a superset (include_archived); categories/hashtags have
    no archive."""
    calls: list[tuple[str, bool]] = []
    archived = {"id": "accX", "name": "Old bank", "currency_code": "PEN", "is_archived": True}

    def rec(name, payload):
        def fetch(cfg, *a, **k):
            calls.append((name, bool(k.get("include_archived"))))
            return payload

        return fetch

    monkeypatch.setattr(
        "expense.commands.accounts_cmd.fetch_accounts",
        rec("accounts", whole([*ACCOUNTS, archived])),
    )
    monkeypatch.setattr(
        "expense.commands.categories_cmd.fetch_categories", rec("categories", CATEGORIES)
    )
    monkeypatch.setattr("expense.commands.hashtags_cmd.fetch_hashtags", rec("hashtags", HASHTAGS))

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN, resource="transactions")
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        assert sorted(calls) == [("accounts", True), ("categories", False), ("hashtags", False)]
        assert "accX" not in [a[0] for a in screen._accounts]  # archived out of the pool
        assert screen._acc_names.get("accX") == "Old bank"  # but resolvable in the map

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

    monkeypatch.setattr("expense.commands.accounts_cmd.fetch_accounts", boom)
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

    monkeypatch.setattr("expense.commands.accounts_cmd.fetch_accounts", boom)
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
