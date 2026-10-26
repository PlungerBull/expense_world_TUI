"""The Edit form's fields on a line of one part, and the "no batch" Edit form (fake client).

Edit-only: creating is the LOG bar's — see
[test_tui_log_bar.py](test_tui_log_bar.py). The form owns pre-fill, the one
`PUT /bank-lines/{id}` a save sends (the line fields changed beside the line's
whole set of parts, contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"), and the
suggestion pickers. The form with two parts or more, `^n` and `^x`, each line's
`edit_limits` by its state and a refusal under the parts are
[test_tui_edit_form_parts.py](test_tui_edit_form_parts.py).

The reference lists and the line read are patched on `expense.reads`, so
`fake_client.calls` holds the writes alone.
"""

import threading
from pathlib import Path

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
from expense.tui.screens.edit_form import (
    DATE_UNREADABLE,
    EVERY_PART_NOTE,
    NOTE_SAVES,
    BankLineEditFormScreen,
    EditFormScreen,
)
from expense.tui.theme import ACCENT
from expense.tui.widgets.parts_table import readonly_lines
from tests.unit.helpers import (
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_NAMES,
    HASHTAG_REFUSALS,
    LOCK_MESSAGES,
    edit_limits,
    hashtag_refusal,
    import_part,
    in_order,
    line_code_of,
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
        "is_archived": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
    {
        "id": "acc2",
        "name": "BCP USD",
        "currency_code": "USD",
        "is_person": False,
        "is_archived": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
    {
        "id": "acc3",
        "name": "Ahorros",
        "currency_code": "PEN",
        "is_person": False,
        "is_archived": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
    {
        "id": "accX",
        "name": "Old bank",
        "currency_code": "PEN",
        "is_person": False,
        "is_archived": True,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
]
CATEGORIES = [
    {"id": "cat1", "name": "Mascotas", "is_system": False},
    {"id": "cat2", "name": "Salud", "is_system": False},
    {"id": "cat3", "name": "Hogar", "is_system": False},
    {"id": "catO", "name": "@Opening", "is_system": True, "system_key": "opening_balance"},
]
HASHTAGS = [
    {"id": "h1", "name": "dog", "system_key": None},
    {"id": "h2", "name": "traveling", "system_key": None},
]

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
PATH = "/bank-lines/bl1"
#: A one-part line's form: the shared fields, then part 1's.
TXN_FIELDS = ["date", "title", "account", "0.amount", "0.category", "0.hashtags", "0.note"]


def _as_part(tx: dict) -> dict:
    """A ledger row as `GET /bank-lines/{id}` lists it among `parts`."""
    return import_part(
        tx["id"],
        tx["amount_cents"],
        account_id=tx["account_id"],
        line=tx["bank_line_id"],
        day=tx["date"][:10],
        title=tx.get("title"),
        category_id=tx.get("category_id"),
        hashtag_ids=tuple(tx.get("hashtag_ids") or ()),
        description=tx.get("description"),
    )


def _line(*parts: dict, limits: dict | None = None, operation: str | None = None) -> dict:
    """`GET /bank-lines/bl1` holding `parts` (ledger rows), with `limits`, its
    `edit_limits` (a line nothing closes by default)."""
    return {
        "id": "bl1",
        "line_code": line_code_of("bl1"),
        "account_id": parts[0]["account_id"],
        "operation_code": operation,
        "statement_line": None,
        "statement_place": None,
        "net_cents": sum(p["amount_cents"] for p in parts),
        "part_count": len(parts),
        "is_opening_balance": False,
        "parts": [_as_part(p) for p in parts],
        "edit_limits": limits or edit_limits(),
    }


def _patch(
    monkeypatch,
    line: dict | None = None,
    *,
    accounts=ACCOUNTS,
    categories=CATEGORIES,
    hashtags=HASHTAGS,
) -> list[str]:
    """The reference lists and the line read, on `expense.reads`; returns the
    ids of the lines read, one per read."""
    read: list[str] = []
    served = line or _line(TXN)

    def fetch_line(cfg, bank_line_id, **kw):
        read.append(bank_line_id)
        return served

    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(accounts))
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole(categories))
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole(hashtags))
    monkeypatch.setattr("expense.reads.fetch_bank_line", fetch_line)
    return read


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute_suggestions(text)
    screen.on_input_submitted(None)


def _on(screen, key):
    screen._current = screen._sequence().index(key)
    screen._refresh_bar()


async def _wait_loaded(screen, pilot):
    await wait_for(pilot, lambda: screen._ready, message="the form never loaded")
    await pilot.pause()


def _record_notices(monkeypatch) -> list:
    notices: list = []
    monkeypatch.setattr(
        EditFormScreen,
        "notify",
        lambda self, message, title="", **kw: notices.append((title, str(message))),
    )
    return notices


def _open(record=TXN, scenario_steps=None):
    """Open the Edit form on `record`, wait for it to load, run `steps`."""

    async def scenario(pilot, app):
        screen = EditFormScreen(record=record)
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        return await scenario_steps(screen, pilot, app)

    return run_app(scenario)


def _summary(screen, width: int = 80) -> str:
    return render_text(screen._summary_renderable(), width=width)


def _kept(**fields) -> dict:
    """TXN's part as a save sends it: its id, its current amount, then `fields`."""
    return {"id": "tx1", "amount_cents": -4250, **fields}


# ---- opening the form --------------------------------------------------------


def test_the_form_reads_three_reference_lists_and_the_line_once(fake_client, monkeypatch):
    """The form loads each reference list once, the accounts as a superset
    (include_archived) feeding both the pool and the name map, then the row's
    line in one read: the form's line fields and parts come from it."""
    calls: list[tuple[str, bool]] = []
    read = _patch(monkeypatch)

    def rec(name, payload):
        def fetch(cfg, *a, **k):
            calls.append((name, bool(k.get("include_archived"))))
            return payload

        return fetch

    monkeypatch.setattr("expense.reads.fetch_accounts", rec("accounts", whole(ACCOUNTS)))
    monkeypatch.setattr("expense.reads.fetch_categories", rec("categories", whole(CATEGORIES)))
    monkeypatch.setattr("expense.reads.fetch_hashtags", rec("hashtags", whole(HASHTAGS)))

    async def steps(screen, pilot, app):
        assert sorted(calls) == [("accounts", True), ("categories", False), ("hashtags", False)]
        assert "accX" not in [a[0] for a in screen._accounts]  # archived out of the pool
        assert screen._acc_names.get("accX") == "Old bank"  # but resolvable in the map
        assert screen._sequence() == TXN_FIELDS
        return [p.id for p in screen._parts]

    assert _open(scenario_steps=steps) == ["tx1"]
    assert read == ["bl1"]
    assert fake_client.calls == []


def test_the_account_field_suggests_in_the_engines_order(fake_client, monkeypatch):
    """The account picker lists accounts exactly as `GET /accounts` returned
    them — not alphabetical, not by `sort_order`, the person after every bank."""
    record = {**TXN, "account_id": ENGINE_ORDER_ACCOUNTS[0]["id"]}
    _patch(monkeypatch, _line(record), accounts=ENGINE_ORDER_ACCOUNTS)

    async def steps(screen, pilot, app):
        _on(screen, "account")
        screen._recompute("")
        assert [ent[1] for ent in screen._suggestions] == ENGINE_ORDER_NAMES
        shown = render_text(screen._suggest_renderable(), width=120)
        assert in_order(shown, ENGINE_ORDER_NAMES)

    _open(record, steps)


def test_a_failed_reference_read_notifies_and_the_app_goes_on(fake_client, monkeypatch):
    """An engine or config error while loading is a note, not an exit; the
    form stays on top and takes no input."""
    _patch(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("engine down")

    monkeypatch.setattr("expense.reads.fetch_accounts", boom)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: notices)
        assert app.is_running and app.screen is screen
        assert not screen._ready

    run_app(scenario)
    assert notices and "engine down" in notices[0][1]
    assert fake_client.calls == []


def test_a_failed_read_uses_the_canonical_renderer(fake_client, monkeypatch):
    """Engine errors surface with the canonical text, not bare str(exc)."""
    _patch(monkeypatch)

    def boom(*a, **k):
        raise EngineConnectionError(url="https://x.invalid", original=Exception("refused"))

    monkeypatch.setattr("expense.reads.fetch_bank_line", boom)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = EditFormScreen(record=TXN)
        await app.push_screen(screen)
        await wait_for(pilot, lambda: notices)

    run_app(scenario)
    assert "could not reach engine at https://x.invalid" in notices[0][1]


def test_the_form_cannot_be_opened_without_a_record():
    """The create door is shut, and shut structurally.

    `+` opens the LOG bar. Making `record` required means no future caller
    can reopen that door by accident — it is a TypeError, not a second create
    form drifting quietly out of sync with the bar.
    """
    with pytest.raises(TypeError):
        EditFormScreen()


def test_no_form_offers_cleared_and_every_part_offers_hashtags():
    """`cleared` is gone from the ledger — no form may offer it.

    The engine has no `cleared`: create lists it as retired
    (contract: POST /v1/transactions). Sending it is a 422 on an unknown field,
    which rejects the whole body. Hashtags are an ordinary field of each part.
    """
    screen = EditFormScreen(record=TXN)
    screen._take_line(_line(TXN))
    assert not any(key.endswith("cleared") for key in screen._sequence())
    assert "0.hashtags" in screen._sequence()


FORM_FOOTER = [("esc", "Cancel"), ("^s", "Save"), ("⇥", "Field"), ("^n", "Add part")]


@pytest.mark.parametrize(
    ("make", "footer"),
    [
        (lambda: NewAccountScreen(), "Create"),
        (lambda: NewCategoryScreen(), "Create"),
        (lambda: NewHashtagScreen(), "Create"),
        (lambda: EditFormScreen(record=TXN), FORM_FOOTER),
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
def test_form_footer_reads_cancel_submit_field(fake_client, monkeypatch, make, footer):
    """`esc Cancel  ^s Save|Create  ⇥ Field`, in that order; the Edit form adds
    `^n Add part` after them on a line whose parts may change. `⇥` moves to the
    next field with the bar keeping focus."""
    from textual.widgets import Footer
    from textual.widgets._footer import FooterKey

    _patch(monkeypatch)
    expected = (
        footer if isinstance(footer, list) else [("esc", "Cancel"), ("^s", footer), ("⇥", "Field")]
    )

    async def scenario(pilot, app):
        screen = make()
        await app.push_screen(screen)
        if isinstance(screen, EditFormScreen):
            await _wait_loaded(screen, pilot)
        await wait_for(pilot, lambda: bool(screen.query(FooterKey)))
        for _ in range(5):
            await pilot.pause()
        keys = screen.query_one(Footer).query(FooterKey)
        assert [(k.key_display, k.description) for k in keys] == expected
        first = screen._key
        await pilot.press("tab")
        await pilot.pause()
        # A one-field form (hashtag) has nowhere to move: moves stop at either end.
        if len(screen._sequence()) > 1:
            assert screen._key != first
        assert app.focused is screen.query_one("#bar", Input)

    run_app(scenario)


def test_suggest_window_keeps_highlight_visible():
    screen = EditFormScreen(record=TXN)
    screen._current = 2  # account (an entity field)
    screen._suggestions = [(f"c{i}", f"Cat{i}", "PEN") for i in range(20)]
    screen._suggest_idx = 17
    out = render_text(screen._suggest_renderable(), width=60)
    assert "Cat17" in out and "more" in out


# ---- what a save sends -------------------------------------------------------


def test_the_form_prefills_and_sends_the_changed_line_field_beside_the_part(
    fake_client, monkeypatch
):
    """A changed title goes alone among the line fields, beside the line's
    one part under its own id with its current amount, nothing else of it."""
    _patch(monkeypatch)

    async def steps(screen, pilot, app):
        assert screen._values["title"] == "Farmacia" and screen._parts[0].amount_cents == -4250
        _on(screen, "title")
        _enter(screen, "Farmacia Inkafarma")
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)

    _open(scenario_steps=steps)
    assert fake_client.calls == [("PUT", PATH, {"title": "Farmacia Inkafarma", "parts": [_kept()]})]
    assert not fake_client.posts  # never POSTs in edit mode


def test_an_added_hashtag_sends_the_parts_whole_set(fake_client, monkeypatch):
    """Adding #traveling next to #dog sends both, on the part."""
    _patch(monkeypatch)

    async def steps(screen, pilot, app):
        _on(screen, "0.hashtags")
        _enter(screen, "trav")  # adds and stays
        assert screen._parts[0].hashtag_ids == ("h1", "h2")
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)

    _open(scenario_steps=steps)
    assert fake_client.calls == [("PUT", PATH, {"parts": [_kept(hashtag_ids=["h1", "h2"])]})]


def test_no_changes_sends_nothing(fake_client, monkeypatch):
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)

    async def steps(screen, pilot, app):
        screen.action_submit()
        await wait_for(pilot, lambda: notices)

    _open(scenario_steps=steps)
    assert fake_client.calls == []
    assert notices == [("", "No changes to save.")]


def test_a_double_submit_sends_one_write(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def steps(screen, pilot, app):
        screen._values["title"] = "x"
        screen.action_submit()
        screen.action_submit()  # in flight → ignored
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)
        await pilot.pause()  # let the ignored submits settle, then assert a non-event
        assert len(fake_client.calls) == 1  # one write, nothing else

    _open(scenario_steps=steps)


def test_a_zero_amount_and_an_unknown_account_are_refused_and_stay(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def steps(screen, pilot, app):
        _enter(screen, "")  # date
        _enter(screen, "x")  # title
        _enter(screen, "Nonexistent")  # no match → refused, stays
        assert screen._key == "account"
        _enter(screen, "BCP")  # → part 1's amount
        _enter(screen, "0")  # zero → refused, stays
        assert screen._key == "0.amount"
        _enter(screen, "-5.00")
        assert screen._key == "0.category"

    _open(scenario_steps=steps)
    assert fake_client.calls == []


def test_an_amount_with_a_comma_after_its_dot_is_refused(fake_client, monkeypatch):
    """Typed key by key on part 1's AMOUNT: `13.853,20` is not read as 13.85.
    The field gives its note and the cursor stays; `13853.20` then saves
    13,853.20."""
    _patch(monkeypatch)
    notes: list[tuple[str, object]] = []

    async def steps(screen, pilot, app):
        screen.notify = lambda message, **kw: notes.append((message, kw.get("severity")))
        bar = screen.query_one("#bar", Input)
        await pilot.press("enter", "enter", "enter")  # date, title, account: kept
        await pilot.pause()
        assert screen._key == "0.amount"
        await pilot.press("ctrl+a", "ctrl+k", *"13.853,20", "enter")
        await pilot.pause()
        assert screen._key == "0.amount" and bar.value == "13.853,20"
        assert screen._parts[0].amount_cents == -4250
        await pilot.press("ctrl+a", "ctrl+k", *"13853.20", "enter")
        await pilot.pause()
        assert screen._key != "0.amount"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    _open(scenario_steps=steps)
    assert notes[0] == ("Amount: a signed decimal, e.g. -99.92", "error")
    assert [m for m, sev in notes if sev == "error"] == [notes[0][0]]  # once, then saved
    assert fake_client.calls == [("PUT", PATH, {"parts": [{"id": "tx1", "amount_cents": 1385320}]})]


def test_an_emptied_title_is_refused_and_stays(fake_client, monkeypatch):
    """`⏎` on an emptied title says `Title is required.` as an error toast and
    the cursor stays on TITLE (`_title_given` in _form.py)."""
    _patch(monkeypatch)
    notes: list[tuple[str, object]] = []

    async def steps(screen, pilot, app):
        screen.notify = lambda message, **kw: notes.append((message, kw.get("severity")))
        _on(screen, "title")
        _enter(screen, "   ")
        assert screen._key == "title" and screen._values["title"] == "Farmacia"

    _open(scenario_steps=steps)
    assert notes == [(TITLE_REQUIRED, "error")]


def test_a_null_hashtag_id_renders_and_a_title_edit_leaves_the_set_alone(fake_client, monkeypatch):
    """A part carrying a null hashtag id renders without crashing, and a save
    that changes only the title does not send the part's hashtags."""
    record = {**TXN, "hashtag_ids": ["h1", None]}
    _patch(monkeypatch, _line(record))

    async def steps(screen, pilot, app):
        assert "dog" in _summary(screen)
        _on(screen, "title")
        _enter(screen, "Farmacia Central")
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)
        assert app.is_running

    _open(record, steps)
    assert fake_client.calls == [("PUT", PATH, {"title": "Farmacia Central", "parts": [_kept()]})]


# ---- an account move leaves the reconciliation --------------------------------
# (contract: "Assigning transactions") (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")


def _moved(part: dict, *, left: bool) -> dict:
    return {
        "transaction": {**part, "account_id": "acc3", "reconciliation_id": None},
        "left_reconciliation": left,
    }


@pytest.mark.parametrize(
    ("changed", "note"),
    [
        pytest.param([_moved(TXN, left=True)], "Saved. It left its reconciliation.", id="flagged"),
        pytest.param([_moved(TXN, left=False)], "Saved.", id="listed-not-flagged"),
        pytest.param([], "Saved.", id="lists-none"),
    ],
)
def test_the_saved_note_reads_the_engines_answer(fake_client, monkeypatch, changed, note):
    """Typed key by key: `⏎` past date and title, `Ahorros` on ACCOUNT, `ctrl+s`.
    Every account change sends `reconciliation_id: null` beside the parts, and
    the note says the line left its reconciliation only when the answer's
    `changed_parts` flags a part (contract: PUT /v1/bank-lines/{bank_line_id}, "Response")."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)
    fake_client.write_responses[PATH] = {**_line(TXN), "changed_parts": changed}

    async def steps(screen, pilot, app):
        await pilot.press("enter", "enter")  # date, title: kept
        await wait_for(pilot, lambda: screen._key == "account")
        await pilot.press(*"Ahorros", "enter")
        await wait_for(pilot, lambda: screen._key != "account")
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: notices)

    _open(scenario_steps=steps)
    assert fake_client.calls == [
        ("PUT", PATH, {"account_id": "acc3", "reconciliation_id": None, "parts": [_kept()]})
    ]
    assert notices == [("", note)]


def test_an_edit_that_keeps_the_account_sends_no_reconciliation_id(fake_client, monkeypatch):
    """Re-picking the line's own account is no change, so a line edited on
    another field keeps its reconciliation."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)

    async def steps(screen, pilot, app):
        _on(screen, "account")
        _enter(screen, "BCP PEN")  # the account it is already on
        _on(screen, "title")
        _enter(screen, "Farmacia Inkafarma")
        screen.action_submit()
        await wait_for(pilot, lambda: notices)

    _open(scenario_steps=steps)
    assert fake_client.calls == [("PUT", PATH, {"title": "Farmacia Inkafarma", "parts": [_kept()]})]
    assert ("", "Saved.") in notices


def _move_refused(err, fake_client, monkeypatch) -> tuple[str, bool]:
    """Pick BCP USD on ACCOUNT and save into the refusal `err`; returns the
    summary as drawn and whether the form is still on top."""
    _patch(monkeypatch)
    fake_client.errors["PUT"] = err

    async def steps(screen, pilot, app):
        _on(screen, "account")
        _enter(screen, "BCP USD")
        screen.action_submit()
        await wait_for(pilot, lambda: screen._refusal is not None and not screen._submitting)
        return _summary(screen, width=120), app.screen is screen

    return _open(scenario_steps=steps)


def test_a_move_on_a_completed_reconciliation_shows_the_lock_under_the_parts(
    fake_client, monkeypatch
):
    """The engine checks `LOCKED` first; the form shows its refusal and stays."""
    err = EngineError(
        "VALIDATION_ERROR",
        "Fields are locked by a completed reconciliation.",
        {"account_id": "Locked by completed reconciliation."},
        422,
        {},
        reasons={"account_id": "LOCKED", "reconciliation_id": "LOCKED"},
    )
    summary, on_top = _move_refused(err, fake_client, monkeypatch)
    assert fake_client.calls == [
        ("PUT", PATH, {"account_id": "acc2", "reconciliation_id": None, "parts": [_kept()]})
    ]
    assert "VALIDATION_ERROR — Fields are locked by a completed reconciliation." in summary
    assert "! account_id: Locked by completed reconciliation." in summary
    assert "Nothing was saved." in summary
    assert on_top  # not dismissed: nothing was saved


def test_a_move_onto_an_account_holding_its_operation_code_says_what_to_do(
    fake_client, monkeypatch
):
    """Screen 4: the engine refuses the move keyed on `operation_code`, though
    the body did not send it (contract: PUT /v1/bank-lines/{bank_line_id}, "Body");
    under the parts its words, then the app's line, and the form stays."""
    err = EngineError(
        "CONFLICT",
        "Operation code already exists.",
        {"operation_code": "Must be unique per account."},
        409,
        {},
        reasons={"operation_code": "OPERATION_CODE_EXISTS"},
    )
    summary, on_top = _move_refused(err, fake_client, monkeypatch)
    lines = [row.strip() for row in summary.splitlines() if row.strip()]
    assert lines[-4:] == [
        "CONFLICT — Operation code already exists.",
        "! operation_code: Must be unique per account.",
        "Nothing was saved.",
        "That account already has a row with this operation number: look there for a duplicate.",
    ]
    assert on_top


# ---- an opening balance stays put -----------------------------------------------
# What is read-only is the line's `edit_limits`
# (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields").

OPENING = {
    **TXN,
    "id": "txO",
    "title": "Saldo inicial",
    "amount_cents": 320000,
    "category_id": "catO",
    "hashtag_ids": [],
    "description": None,
}
OPENING_LIMITS = edit_limits(
    locked_fields={"account_id": "OPENING_BALANCE_ACCOUNT_FIXED"},
    parts_fixed=True,
    locked_part_fields={
        "txO": {
            "category_id": "OPENING_BALANCE_CATEGORY_FIXED",
            "hashtag_ids": "OPENING_BALANCE_NOT_TAGGED",
        }
    },
)


def _opening_line(record=OPENING, limits=OPENING_LIMITS) -> dict:
    return {**_line(record, limits=limits), "is_opening_balance": True}


def test_an_opening_balances_field_moves_skip_its_read_only_lines(fake_client, monkeypatch):
    """Account, category and hashtags are read-only; a field move skips them,
    from amount straight to note and back, with ⇥ and with the arrows."""
    _patch(monkeypatch, _opening_line())

    async def steps(screen, pilot, app):
        assert screen._locked == {"account", "0.category", "0.hashtags"}
        assert "account  BCP PEN  read-only" in _summary(screen)
        _on(screen, "0.amount")
        await pilot.press("tab")
        assert screen._key == "0.note"
        await pilot.press("shift+tab")
        assert screen._key == "0.amount"
        await pilot.press("down")
        assert screen._key == "0.note"
        await pilot.press("up")
        assert screen._key == "0.amount"

    _open(OPENING, steps)


def test_an_opening_balance_saves_its_other_fields_and_never_its_locked_ones(
    fake_client, monkeypatch
):
    """Amount and note save as on any line; the write carries no account, and
    the part no category and no hashtags, even with a value set under the
    account."""
    _patch(monkeypatch, _opening_line())

    async def steps(screen, pilot, app):
        _on(screen, "0.amount")
        _enter(screen, "3500")
        assert screen._key == "0.note"  # category and hashtags skipped
        screen._values["account"] = "acc2"  # never sent: it is read-only
        _enter(screen, "apertura")  # `⏎` on the last line saves
        await wait_for(pilot, lambda: fake_client.puts)

    _open(OPENING, steps)
    assert fake_client.calls == [
        ("PUT", PATH, {"parts": [{"id": "txO", "amount_cents": 350000, "description": "apertura"}]})
    ]


def test_an_ordinary_line_keeps_account_and_category_editable(fake_client, monkeypatch):
    _patch(monkeypatch)

    async def steps(screen, pilot, app):
        assert screen._locked == set()
        assert "read-only" not in _summary(screen)
        _on(screen, "title")
        screen.action_field(1)
        assert screen._key == "account"
        _on(screen, "0.amount")
        screen.action_field(1)
        assert screen._key == "0.category"

    _open(scenario_steps=steps)


def test_an_opening_balances_account_refusal_shows_its_line_under_the_parts(
    fake_client, monkeypatch
):
    """If the refusal reaches the form anyway (here, a line the engine closed
    after the form read it), its words, then the app's line, and the form stays."""
    err = EngineError(
        "VALIDATION_ERROR",
        "Validation failed.",
        {"account_id": "stand-in field words"},
        422,
        {},
        reasons={"account_id": "OPENING_BALANCE_ACCOUNT_FIXED"},
    )
    summary, on_top = _move_refused(err, fake_client, monkeypatch)
    lines = [row.strip() for row in summary.splitlines() if row.strip()]
    assert lines[-4:] == [
        "VALIDATION_ERROR — Validation failed.",
        "! account_id: stand-in field words",
        "Nothing was saved.",
        "To move an opening balance, set it on the other account's Edit form.",
    ]
    assert on_top


# ---- an archived account's line: what edit_limits names, nothing more ----------
# On a line with a part on an archived account every line field is refused but a
# title or operation code filled while empty, and each kept part keeps its amount
# (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")
# (contract: PUT /v1/bank-lines/{bank_line_id}, "The parts' rules").

ON_ARCHIVED = {**TXN, "account_id": "accX"}
_ARCHIVED_FIELDS = ("title", "date", "account_id", "reconciliation_id")


def _archived_limits(*fields: str, part="tx1") -> dict:
    return edit_limits(
        locked_fields=dict.fromkeys(fields, "ACCOUNT_ARCHIVED"),
        total_fixed=True,
        parts_fixed=True,
        locked_part_fields={part: {"amount_cents": "ACCOUNT_ARCHIVED"}},
    )


def test_a_value_set_under_an_archived_lines_read_only_field_is_never_sent(
    fake_client, monkeypatch
):
    """Every line field and the part's amount read-only: new values set under
    them change nothing, so nothing is sent."""
    _patch(monkeypatch, _line(ON_ARCHIVED, limits=_archived_limits(*_ARCHIVED_FIELDS)))
    notices = _record_notices(monkeypatch)

    async def steps(screen, pilot, app):
        assert screen._locked == {"date", "title", "account", "0.amount"}
        assert screen._key == "0.category"
        screen._values.update(date="2026-06-21", title="OTRA", account="acc2")
        screen.action_submit()
        await wait_for(pilot, lambda: notices)

    _open(ON_ARCHIVED, steps)
    assert fake_client.calls == []
    assert notices == [("", "No changes to save.")]


def test_an_archived_lines_empty_title_left_open_by_edit_limits_saves(fake_client, monkeypatch):
    """`edit_limits` leaves out the title a line has none of, so it may be
    filled: the form opens on TITLE, and the save sends it beside the part at
    its current amount."""
    record = {**ON_ARCHIVED, "title": None}
    limits = _archived_limits("date", "account_id", "reconciliation_id")
    _patch(monkeypatch, _line(record, limits=limits))

    async def steps(screen, pilot, app):
        assert screen._locked == {"date", "account", "0.amount"}
        assert screen._key == "title"
        _enter(screen, "FARMACIA")
        assert screen._key == "0.category"
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)

    _open(record, steps)
    assert fake_client.calls == [("PUT", PATH, {"title": "FARMACIA", "parts": [_kept()]})]


@pytest.mark.parametrize(
    "line",
    [
        _line(ON_ARCHIVED, limits=_archived_limits(*_ARCHIVED_FIELDS)),
        _opening_line(
            {**OPENING, "account_id": "accX"},
            edit_limits(
                locked_fields=dict.fromkeys(_ARCHIVED_FIELDS, "ACCOUNT_ARCHIVED"),
                total_fixed=True,
                parts_fixed=True,
                locked_part_fields={
                    "txO": {
                        "amount_cents": "ACCOUNT_ARCHIVED",
                        "category_id": "OPENING_BALANCE_CATEGORY_FIXED",
                        "hashtag_ids": "OPENING_BALANCE_NOT_TAGGED",
                    }
                },
            ),
        ),
    ],
    ids=["archived", "archived-opening-balance"],
)
def test_no_field_move_lands_on_a_read_only_line(fake_client, monkeypatch, line):
    """On an archived account's line, and on its opening balance, which changes
    only its note, the bar never reaches a line `edit_limits` names."""
    _patch(monkeypatch, line)
    record = {**TXN, "id": line["parts"][0]["id"], "account_id": "accX"}

    async def steps(screen, pilot, app):
        assert screen._key not in screen._locked
        for key in ("shift+tab", "up", "ctrl+up", "tab", "tab", "tab", "down", "ctrl+down"):
            await pilot.press(key)
            assert screen._key not in screen._locked
        return set(screen._sequence()) - screen._locked

    open_lines = _open(record, steps)
    assert "0.note" in open_lines


# ---- why a line is read-only: the engine's sentences, screen 1 B ----------------
# of mockups/expense-world-read-only-reasons.html. Each locked field comes as
# `{reason, message}` (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields");
# the form shows the message as sent.

COMPLETED_LIMITS = edit_limits(
    locked_fields=dict.fromkeys(_ARCHIVED_FIELDS, "LOCKED"),
    total_fixed=True,
    locked_part_fields={"tx1": {"amount_cents": "SPLIT_TOTAL_MISMATCH"}},
)


def _drawn(record: dict, line: dict, form=None, *, ansi: bool = False) -> list[str]:
    """The Edit form's summary on `record`'s `line` as an 80-column terminal
    draws it: rendered at the summary's own width there, its padding taken off;
    with `ansi`, its escape codes kept."""

    async def scenario(pilot, app):
        screen = form() if form else EditFormScreen(record=record)
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        summary = screen.query_one("#summary", Static)
        width = summary.content_region.width
        text = render_text(summary.content, width=width, ansi=ansi)
        return [row.rstrip() for row in text.splitlines()], width

    rows, width = run_app(scenario, size=(80, 50))
    assert width == 74  # 80 columns, less the summary's padding of 3 on each side
    return rows


def test_a_completed_reconciliations_line_says_why_once_under_its_fields(fake_client, monkeypatch):
    """Date, title and account each still read `read-only`; one line under them
    names the three in the form's order with the engine's sentence, and the
    amount's line under the parts carries its own."""
    line = _line(TXN, limits=COMPLETED_LIMITS)
    _patch(monkeypatch, line)
    assert _drawn(TXN, line) == [
        "date     2026-06-20  read-only",
        "title    Farmacia  read-only",
        "account  BCP PEN  read-only",
        "date, title, account: Locked by completed reconciliation.",
        "",
        "      amount    category       hashtags        note",
        "▌ 1   -42.50    Mascotas       #dog            receta",
        "amount  read-only · The parts must add up to the line's total.",
    ]


def test_an_archived_accounts_line_says_why_with_the_engines_sentence(fake_client, monkeypatch):
    line = _line(ON_ARCHIVED, limits=_archived_limits(*_ARCHIVED_FIELDS))
    _patch(monkeypatch, line)
    assert _drawn(ON_ARCHIVED, line) == [
        "date     2026-06-20  read-only",
        "title    Farmacia  read-only",
        "account  Old bank  read-only",
        "date, title, account: The account is archived. Unarchive it first.",
        "",
        "      amount    category       hashtags        note",
        "▌ 1   -42.50    Mascotas       #dog            receta",
        "amount  read-only · The account is archived. Unarchive it first.",
    ]


def test_an_opening_balances_sentences_wrap_under_themselves(fake_client, monkeypatch):
    """Three locked lines, three sentences: the account's under the shared
    fields, each part column's beside its `read-only`, a long one wrapping
    under the `·` that opens it at 80 columns, as the mockup draws it."""
    line = _opening_line()
    _patch(monkeypatch, line)
    assert _drawn(OPENING, line) == [
        "date     2026-06-20",
        "title    Saldo inicial",
        "account  BCP PEN  read-only",
        "account: Must not move an opening balance to another account.",
        "",
        "       amount    category       hashtags        note",
        "  1  3,200.00    @Opening       —",
        "category  read-only · Must not move an opening balance out of the",
        "                    opening-balance category.",
        "hashtags  read-only · Must be empty: an opening balance carries no",
        "                    hashtag.",
    ]


def test_the_no_batch_form_names_its_operation_line_among_the_locked(fake_client, monkeypatch):
    """The "no batch" form shares the lines: OPERATION, read-only on an
    archived account's line, is named in the form's order, and a sentence too
    long for the line wraps under itself."""
    limits = _archived_limits(*_ARCHIVED_FIELDS, "operation_code")
    line = _line(ON_ARCHIVED, limits=limits, operation="47391026")
    _patch(monkeypatch, line)
    rows = _drawn(ON_ARCHIVED, line, form=lambda: BankLineEditFormScreen(line=line))
    assert rows[:6] == [
        "date       2026-06-20  read-only",
        "title      Farmacia  read-only",
        "operation  47391026  read-only",
        "account    Old bank  read-only",
        "date, title, operation, account: The account is archived. Unarchive it",
        "                                 first.",
    ]
    assert rows[-1] == "amount  read-only · The account is archived. Unarchive it first."


def test_line_fields_locked_for_different_reasons_get_a_sentence_each(fake_client, monkeypatch):
    """Each distinct sentence once, in the form's order of the lines it covers;
    a field the form has no line for (`reconciliation_id`) is named nowhere."""
    limits = edit_limits(
        locked_fields={
            "reconciliation_id": "LOCKED",
            "account_id": "ACCOUNT_ARCHIVED",
            "title": "LOCKED",
            "date": "ACCOUNT_ARCHIVED",
        }
    )
    line = _line(TXN, limits=limits)
    _patch(monkeypatch, line)
    assert _drawn(TXN, line)[3:5] == [
        "date, account: The account is archived. Unarchive it first.",
        "title: Locked by completed reconciliation.",
    ]


def test_the_sentences_are_dim_like_the_rest_of_their_lines(fake_client, monkeypatch):
    """The line naming the read-only fields and a column's `read-only` line
    with its sentence are dim from end to end."""
    line = _line(TXN, limits=COMPLETED_LIMITS)
    _patch(monkeypatch, line)
    wanted = {
        "date, title, account: Locked by completed reconciliation.",
        "amount  read-only · The parts must add up to the line's total.",
    }
    seen = set()
    for row in _drawn(TXN, line, ansi=True):
        text = Text.from_ansi(row)
        if text.plain.rstrip() not in wanted:
            continue
        seen.add(text.plain.rstrip())
        dim = {i for span in text.spans if span.style.dim for i in range(span.start, span.end)}
        shown = {i for i, char in enumerate(text.plain) if not char.isspace()}
        assert shown <= dim, text.plain
    assert seen == wanted


def test_the_engines_sentence_shows_as_sent_never_as_styling(fake_client, monkeypatch):
    """`[like this]`, `[/]` and `[bold]` in the engine's words show whole, under
    the shared fields and beside a part column's `read-only`."""
    words = "Locked [like this] by [bold]a[/] reconciliation."
    limits = {
        **COMPLETED_LIMITS,
        "locked_fields": {
            field: {"reason": "LOCKED", "message": words} for field in _ARCHIVED_FIELDS
        },
        "locked_part_fields": {"tx1": {"amount_cents": {"reason": "X", "message": words}}},
    }
    line = _line(TXN, limits=limits)
    _patch(monkeypatch, line)
    rows = _drawn(TXN, line)
    assert f"date, title, account: {words}" in rows
    assert f"amount  read-only · {words}" in rows


def test_two_parts_locked_in_one_column_for_different_reasons_join_their_sentences():
    """One line per column: each distinct sentence once, in the parts' order,
    joined by ` · `; a lock the engine sends no sentence for reads `read-only`."""
    first, second = LOCK_MESSAGES["ACCOUNT_ARCHIVED"], LOCK_MESSAGES["SPLIT_TOTAL_MISMATCH"]
    lines = readonly_lines(
        {
            0: {"amount": first, "note": None},
            1: {"amount": second},
            2: {"amount": first},
        }
    )
    drawn = [render_text(line, width=200).rstrip() for line in lines]
    assert drawn == [f"amount  read-only · {first} · {second}", "note  read-only"]


def test_the_app_keeps_no_table_from_reason_to_sentence():
    """The sentences come from the engine alone: no file under expense/ holds
    one of them (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")."""
    package = Path(__file__).resolve().parents[2] / "expense"
    held = {
        f"{path.relative_to(package)}: {sentence}"
        for path in package.rglob("*.py")
        for sentence in LOCK_MESSAGES.values()
        if sentence in path.read_text(encoding="utf-8")
    }
    assert held == set()


# ---- the pending hashtag never rides beside a real one -------------------------
# (contract: PUT /v1/bank-lines/{bank_line_id}, "The parts' rules")
# (contract: "Transactions (Ledger)", "The pending hashtag is never combined")

PENDING_TAG = {"id": "hp", "name": "Pendiente", "system_key": "pending"}
WITH_PENDING = [*HASHTAGS, PENDING_TAG]
ON_PENDING = {**TXN, "hashtag_ids": ["hp"]}


def _tag(record, typed, fake_client, monkeypatch, *, tags=WITH_PENDING, save=True):
    """Open the form on `record`, add each hashtag `typed` names, then save;
    returns the notices and the part's hashtags after each addition."""
    _patch(monkeypatch, _line(record), hashtags=tags)
    notices = _record_notices(monkeypatch)

    async def steps(screen, pilot, app):
        _on(screen, "0.hashtags")
        shown = [screen._parts[0].hashtag_ids]
        for text in typed:
            _enter(screen, text)
            shown.append(screen._parts[0].hashtag_ids)
        if save:
            screen.action_submit()
            await wait_for(pilot, lambda: notices)
        return shown

    shown = _open(record, steps)
    return notices, shown


def test_tagging_a_pending_part_sends_only_the_real_hashtag(fake_client, monkeypatch):
    """The part carries the pending hashtag; adding #dog sends `["h1"]` alone,
    never the pending id beside it."""
    _notices, shown = _tag(ON_PENDING, ["dog", "traveling"], fake_client, monkeypatch)
    assert shown == [("hp",), ("h1",), ("h1", "h2")]
    assert fake_client.calls == [("PUT", PATH, {"parts": [_kept(hashtag_ids=["h1", "h2"])]})]


def test_naming_the_pending_hashtag_beside_a_real_one_drops_it(fake_client, monkeypatch):
    """A part on #dog given the pending hashtag too keeps #dog alone: the set
    is unchanged, so nothing is sent."""
    notices, shown = _tag(TXN, ["pend"], fake_client, monkeypatch)
    assert shown == [("h1",), ("h1",)]
    assert not fake_client.puts
    assert notices == [("", "No changes to save.")]


def test_with_no_pending_hashtag_yet_the_set_goes_as_picked(fake_client, monkeypatch):
    """No hashtag carries `system_key` `pending`; a user hashtag only named like
    it is an ordinary hashtag, kept and sent."""
    named_like_it = {"id": "hx", "name": "Pendiente", "system_key": None}
    record = {**TXN, "hashtag_ids": ["hx"]}
    tags = [*HASHTAGS, named_like_it]
    _notices, shown = _tag(record, ["dog"], fake_client, monkeypatch, tags=tags)
    assert shown == [("hx",), ("hx", "h1")]
    assert fake_client.calls == [("PUT", PATH, {"parts": [_kept(hashtag_ids=["hx", "h1"])]})]


def test_an_emptied_set_sends_an_empty_list(fake_client, monkeypatch):
    """Every hashtag taken off sends `[]`: the engine files the part under the
    pending hashtag; the client never sends the pending id for it."""
    from dataclasses import replace

    _patch(monkeypatch, hashtags=WITH_PENDING)

    async def steps(screen, pilot, app):
        screen._parts[0] = replace(screen._parts[0], hashtag_ids=())
        screen.action_submit()
        await wait_for(pilot, lambda: fake_client.puts)

    _open(scenario_steps=steps)
    assert fake_client.calls == [("PUT", PATH, {"parts": [_kept(hashtag_ids=[])]})]


@pytest.mark.parametrize(("code", "status", "reason", "line"), HASHTAG_REFUSALS)
def test_a_hashtag_refusal_shows_under_the_parts_as_sent(
    fake_client, monkeypatch, code, status, reason, line
):
    """The engine's words whole, then its line if the reason has one; the form
    stays."""
    err = hashtag_refusal(code, status, reason)
    fake_client.errors["PUT"] = err
    _patch(monkeypatch, _line(ON_PENDING), hashtags=WITH_PENDING)

    async def steps(screen, pilot, app):
        _on(screen, "0.hashtags")
        _enter(screen, "dog")
        screen.action_submit()
        await wait_for(pilot, lambda: screen._refusal is not None and not screen._submitting)
        return _summary(screen, width=120), app.screen is screen

    summary, on_top = _open(ON_PENDING, steps)
    assert f"{code} — Engine words for {reason}." in summary
    assert "! hashtag_ids: stand-in field words" in summary
    assert (line in summary) if line else True
    assert on_top


# ---- the hints, on a line of one part and of two -----------------------------

FIELD_HINTS = [
    ("date", "YYYY-MM-DD · enter to accept, or type a date"),
    ("title", "free text · enter to go on"),
    ("account", "pick an existing account · ↑↓ highlight · enter select"),
    ("0.amount", "signed decimal · − expense / + income · in the account's currency"),
    ("0.category", "pick an existing category · ↑↓ highlight · enter select"),
    (
        "0.hashtags",
        "type a tag · ↑↓ highlight · enter adds & stays · empty enter = done (optional)",
    ),
]


async def _hints_by_field(screen, pilot, keys) -> dict[str, Text]:
    """The `#hint` line on each of `keys`, reached by `tab` from the first."""
    seen: dict[str, Text] = {}
    for key in keys:
        assert screen._key == key
        seen[key] = screen.query_one("#hint", Static).content
        await pilot.press("tab")
    return seen


def test_a_line_of_one_part_shows_each_fields_hint_alone(fake_client, monkeypatch):
    """Every field's hint is the form's own, dimmed, no every-part note; part
    1's NOTE, the last line, says `⏎` saves."""
    _patch(monkeypatch)

    async def steps(screen, pilot, app):
        return await _hints_by_field(screen, pilot, [*(k for k, _ in FIELD_HINTS), "0.note"])

    hints = _open(scenario_steps=steps)
    for key, hint in [*FIELD_HINTS, ("0.note", NOTE_SAVES)]:
        assert hints[key].plain == hint
        assert str(hints[key].style) == "dim" and not hints[key].spans


def test_a_line_of_two_parts_notes_every_part_on_date_title_and_account(fake_client, monkeypatch):
    """Two parts: date, title and account read their hint, then
    `· changes every part of the transaction` in the accent; a part's fields
    read their hint alone."""
    other = {**TXN, "id": "tx2", "amount_cents": -1000}
    _patch(monkeypatch, _line(TXN, other))

    async def steps(screen, pilot, app):
        return await _hints_by_field(screen, pilot, [k for k, _ in FIELD_HINTS])

    hints = _open(scenario_steps=steps)
    for key, hint in FIELD_HINTS:
        shown = hints[key]
        if key in ("date", "title", "account"):
            assert shown.plain == f"{hint} · {EVERY_PART_NOTE}"
            note = shown.plain.index(EVERY_PART_NOTE)
            styles = {str(s.style) for s in shown.spans if s.start <= note < s.end}
            assert styles == {ACCENT}
            assert all(str(s.style) == "dim" for s in shown.spans if s.end <= note)
        else:
            assert shown.plain == hint


@pytest.mark.parametrize("refused", [False, True], ids=["saved", "refused"])
def test_the_saves_busy_hint_stays_while_it_is_sent(fake_client, monkeypatch, refused):
    """`⏎` on part 1's NOTE, the last line, saves: while the engine's answer is
    held back, the hint under the bar reads `Saving…`. Once the answer arrives
    the form goes on: a save closes it, a refusal brings NOTE's hint back and
    stays under the parts."""
    _patch(monkeypatch)
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
        _on(screen, "0.note")
        await pilot.press("ctrl+a", "ctrl+k", *"nueva")
        try:
            await pilot.press("enter")
            await wait_for(pilot, asked.is_set)  # the PUT is in flight
            await pilot.pause()
            assert str(hint.content) == "Saving…"
        finally:
            release.set()
        if refused:
            await wait_for(pilot, lambda: screen._refusal is not None and not screen._submitting)
            await pilot.pause()
            assert screen.is_attached and screen._key == "0.note"
            assert str(hint.content) == NOTE_SAVES
            assert "VALIDATION — Refused." in _summary(screen)
        else:
            await wait_for(pilot, lambda: not screen.is_attached)

    _open(scenario_steps=steps)
    assert fake_client.calls == [("PUT", PATH, {"parts": [_kept(description="nueva")]})]
    assert notices == ([] if refused else [("", "Saved.")])


# ---- what the save sends for an emptied field --------------------------------
# An explicit `null` is `NOT_NULL` on every line field but `title` and
# `operation_code` (clear them) and `reconciliation_id` (unassigns), and on a kept
# part's `category_id`, `description` and `hashtag_ids`; `""` empties a description
# (contract: PUT /v1/bank-lines/{bank_line_id}, "Body")
# (contract: PUT /v1/bank-lines/{bank_line_id}, "A live part of this line is updated in place").
NULL_CLEARS = {"reconciliation_id", "title", "operation_code"}

LINE_PART = {**TXN, "id": "p1", "title": "FARMACIA"}
BANK_LINE = _line(LINE_PART, operation="47391026")
LINE_FIELDS = ["date", "title", "operation", "account", *TXN_FIELDS[3:]]
# The exact save an emptied field sends, for the fields whose save the null check
# pins, keyed by (form, field).
EMPTIED_FIELD_PUTS = {
    ("transaction", "0.note"): [("PUT", PATH, {"parts": [_kept(description="")]})],
    ("bank_line", "operation"): [
        (
            "PUT",
            PATH,
            {
                "operation_code": None,
                "parts": [{"id": "p1", "amount_cents": -4250}],
            },
        )
    ],
}


def _form(form: str) -> EditFormScreen:
    if form == "transaction":
        return EditFormScreen(record=TXN)
    return BankLineEditFormScreen(line=BANK_LINE)


def test_the_null_check_covers_every_field_of_both_forms():
    edit = EditFormScreen(record=TXN)
    edit._take_line(_line(TXN))
    assert edit._sequence() == TXN_FIELDS
    assert BankLineEditFormScreen(line=BANK_LINE)._sequence() == LINE_FIELDS


def _nulls(body: dict) -> set[str]:
    """The keys sent as `null`: a line field's name, or `parts.<field>`."""
    nulls = {key for key, value in body.items() if value is None}
    for part in body.get("parts", []):
        nulls |= {f"parts.{key}" for key, value in part.items() if value is None}
    return nulls


def test_an_emptied_note_sends_an_empty_description_and_says_saved(fake_client, monkeypatch):
    """`⏎` on an emptied NOTE empties the note: the part carries
    `description: ""`, never `null`, and the form says `Saved.`."""
    _patch(monkeypatch)
    notices = _record_notices(monkeypatch)

    async def steps(screen, pilot, app):
        _on(screen, "0.note")
        assert screen.query_one("#bar", Input).value == "receta"
        _enter(screen, "")
        await wait_for(pilot, lambda: ("", "Saved.") in notices)

    _open(scenario_steps=steps)
    assert fake_client.calls == EMPTIED_FIELD_PUTS["transaction", "0.note"]


def test_an_empty_note_on_a_part_with_none_is_no_change(fake_client, monkeypatch):
    """A part with no note, `⏎` on the empty NOTE: nothing to empty, nothing sent."""
    record = {**TXN, "description": None}
    _patch(monkeypatch, _line(record))
    notices = _record_notices(monkeypatch)

    async def steps(screen, pilot, app):
        _on(screen, "0.note")
        _enter(screen, "")
        await wait_for(pilot, lambda: notices)

    _open(record, steps)
    assert notices == [("", "No changes to save.")]
    assert fake_client.calls == []


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
    whatever the form sends holds `null` only on a line field `null` clears. An
    emptied date commits today, an emptied title or amount is refused, an empty
    account, category or hashtags line keeps what the line holds, an emptied
    operation clears the operation code and an emptied note sends `""`."""
    _patch(monkeypatch, _line(TXN) if form == "transaction" else BANK_LINE)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = _form(form)
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        _on(screen, field)
        _enter(screen, "")
        screen.action_submit()  # a no-op when `⏎` already saved
        await wait_for(pilot, lambda: notices)

    run_app(scenario)
    for method, _path, body in fake_client.calls:
        assert method == "PUT"
        assert _nulls(body) <= NULL_CLEARS, body
    if (form, field) in EMPTIED_FIELD_PUTS:
        assert fake_client.calls == EMPTIED_FIELD_PUTS[form, field]


def test_every_field_changed_at_once_sends_null_only_where_it_clears(fake_client, monkeypatch):
    """Date, title, account, amount, category and hashtags changed and the note
    emptied, in one save: the one `null` is the `reconciliation_id` the move adds."""
    _patch(monkeypatch)

    async def steps(screen, pilot, app):
        _enter(screen, "2026-07-01")  # date
        _enter(screen, "Inkafarma")  # title
        _enter(screen, "BCP USD")  # account
        _enter(screen, "-10.00")  # amount
        _enter(screen, "Salud")  # category
        _enter(screen, "traveling")  # hashtags: adds one and stays
        _enter(screen, "")  # hashtags done
        _enter(screen, "")  # note emptied: saves
        await wait_for(pilot, lambda: fake_client.puts)

    _open(scenario_steps=steps)
    [(path, body)] = fake_client.puts
    assert path == PATH
    assert _nulls(body) == {"reconciliation_id"}
    assert body["title"] == "Inkafarma"
    assert body["account_id"] == "acc2"
    assert body["date"].startswith("2026-07-01T00:00:00")
    assert body["parts"] == [
        {
            "id": "tx1",
            "amount_cents": -1000,
            "category_id": "cat2",
            "description": "",
            "hashtag_ids": ["h1", "h2"],
        }
    ]


# ---- stepping through the form never changes it --------------------------------
# ACCOUNT and CATEGORY open with the bar empty and the highlight on the line's own
# account or the part's own category, so `⏎` with nothing typed keeps it (Question
# 1 A of expense-world-enter-and-esc.html). The line sits on the third account and
# the part on the second category, so a highlight left on the first entry would
# move it.
ON_THIRD = {**TXN, "account_id": "acc3", "category_id": "cat2"}
SPLIT_ON_THIRD = [ON_THIRD, {**ON_THIRD, "id": "tx2", "amount_cents": -1000}]


def _open_stepping(monkeypatch, steps, *, line=None, form=None, categories=CATEGORIES):
    """Open the form (`form()`, by default the Edit form on ON_THIRD) and run
    `steps(screen, pilot)`; returns the notices it raised."""
    _patch(monkeypatch, line or _line(ON_THIRD), categories=categories)
    notices = _record_notices(monkeypatch)

    async def scenario(pilot, app):
        screen = (form or (lambda: EditFormScreen(record=ON_THIRD)))()
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        await steps(screen, pilot)

    run_app(scenario)
    return notices


async def _enter_to(screen, pilot, key):
    """Press `⏎` until the cursor is on `key`, nothing typed on the way."""
    while screen._key != key:
        await pilot.press("enter")


def _highlighted(screen) -> str:
    return screen._suggestions[screen._suggest_idx][1]


@pytest.mark.parametrize("split", [False, True], ids=["one-part", "two-parts"])
def test_enter_through_every_line_then_ctrl_s_sends_nothing(fake_client, monkeypatch, split):
    """`⏎` on every line, one line per press, the last NOTE's `⏎` saving, then
    `ctrl+s`: nothing changed, so nothing is sent and both saves say so."""
    line = _line(*SPLIT_ON_THIRD) if split else _line(ON_THIRD)

    async def steps(screen, pilot):
        visited = []
        before = list(screen._parts)
        for _ in screen._sequence():
            visited.append(screen._key)
            await pilot.press("enter")
        assert visited == screen._sequence()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert screen._values == screen._original and screen._parts == before

    notices = _open_stepping(monkeypatch, steps, line=line)
    assert fake_client.calls == [] and not fake_client.calls
    assert notices == [("", "No changes to save.")] * 2


@pytest.mark.parametrize("split", [False, True], ids=["one-part", "two-parts"])
def test_enter_through_every_line_of_the_no_batch_form_sends_nothing(
    fake_client, monkeypatch, split
):
    """The "no batch" Edit form: one line per `⏎`, none skipped, ACCOUNT kept on
    the line's own; the last NOTE's `⏎` saves, and with nothing changed nothing
    is sent."""
    line = {**(_line(*SPLIT_ON_THIRD) if split else _line(ON_THIRD)), "operation_code": "1"}

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

    notices = _open_stepping(
        monkeypatch, steps, line=line, form=lambda: BankLineEditFormScreen(line=line)
    )
    assert fake_client.calls == [] and not fake_client.calls
    assert notices == [("", "No changes to save.")] * 2


@pytest.mark.parametrize(("key", "own_name"), [("account", "Ahorros"), ("0.category", "Salud")])
def test_an_untouched_entity_line_starts_on_its_own_value_and_enter_keeps_it(
    fake_client, monkeypatch, key, own_name
):
    """The list stays in its order, every entry shown; the highlight is on the
    line's or part's own one, and `⏎` keeps it and moves on."""

    async def steps(screen, pilot):
        await _enter_to(screen, pilot, key)
        assert screen.query_one("#bar", Input).value == ""
        pool = screen._accounts if key == "account" else screen._categories
        assert screen._suggestions == pool  # the usual order, nothing filtered
        assert _highlighted(screen) == own_name
        assert own_name in render_text(screen._suggest_renderable(), width=60)
        await pilot.press("enter")
        assert screen._key != key  # moved on
        assert screen._values["account"] == "acc3"
        assert screen._parts[0].category_id == "cat2"

    _open_stepping(monkeypatch, steps)


def test_typing_a_name_then_enter_still_picks_the_typed_one(fake_client, monkeypatch):
    """Typing filters the list and highlights its first match; `⏎` takes it."""

    async def steps(screen, pilot):
        await _enter_to(screen, pilot, "account")
        await pilot.press(*"usd")
        assert [e[1] for e in screen._suggestions] == ["BCP USD"]
        await pilot.press("enter")
        assert screen._values["account"] == "acc2"
        await _enter_to(screen, pilot, "0.category")
        await pilot.press(*"hog")
        assert _highlighted(screen) == "Hogar"
        await pilot.press("enter")
        assert screen._parts[0].category_id == "cat3"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    _open_stepping(monkeypatch, steps)
    path, body = fake_client.puts[0]
    assert path == PATH
    assert body["account_id"] == "acc2" and body["parts"][0]["category_id"] == "cat3"


def test_arrows_still_choose_another_and_an_erased_bar_returns_to_the_own_one(
    fake_client, monkeypatch
):
    async def steps(screen, pilot):
        await _enter_to(screen, pilot, "0.category")
        assert _highlighted(screen) == "Salud"
        await pilot.press(*"mas")
        assert _highlighted(screen) == "Mascotas"
        await pilot.press("backspace", "backspace", "backspace")
        assert screen.query_one("#bar", Input).value == ""
        assert _highlighted(screen) == "Salud"  # empty again: back on the part's own
        await pilot.press("down")
        assert _highlighted(screen) == "Hogar"
        await pilot.press("enter")
        assert screen._parts[0].category_id == "cat3"

    _open_stepping(monkeypatch, steps)


# ---- @Pendiente is in the CATEGORY list, where the engine lists it --------------
# Question 3 A of expense-world-enter-and-esc.html: a part's category list is the
# bulk `c` pick's (`reads.pickable_categories`), so a part in @Pendiente starts on
# it and a part can be sent back there; @Opening is never offered. The engine lists
# @Pendiente between two user categories here, so its place is the engine's.
PENDING_CAT = {"id": "catP", "name": "@Pendiente", "is_system": True, "system_key": "pending"}
WITH_PENDING_CATEGORIES = [CATEGORIES[0], PENDING_CAT, *CATEGORIES[1:]]
IN_PENDING = {**ON_THIRD, "category_id": "catP"}


def test_a_part_in_pendiente_starts_on_it_and_enter_through_every_line_sends_nothing(
    fake_client, monkeypatch
):
    """CATEGORY lists @Pendiente in the engine's place, highlighted; `⏎` on every
    line, the note's `⏎` saving, then `ctrl+s`: nothing changed, nothing sent."""

    async def steps(screen, pilot):
        for _ in screen._sequence():
            if screen._key == "0.category":
                names = [name for _id, name in screen._suggestions]
                assert names == ["Mascotas", "@Pendiente", "Salud", "Hogar"]
                assert _highlighted(screen) == "@Pendiente"
            await pilot.press("enter")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert screen._parts[0].category_id == "catP"

    notices = _open_stepping(
        monkeypatch,
        steps,
        line=_line(IN_PENDING),
        form=lambda: EditFormScreen(record=IN_PENDING),
        categories=WITH_PENDING_CATEGORIES,
    )
    assert fake_client.calls == [] and not fake_client.calls
    assert notices == [("", "No changes to save.")] * 2


def test_picking_pendiente_on_a_categorised_part_sends_its_id(fake_client, monkeypatch):
    """Typing `pend` highlights @Pendiente; `⏎` takes it and the save sends its
    id, the part going back to waiting for a category."""

    async def steps(screen, pilot):
        await _enter_to(screen, pilot, "0.category")
        assert _highlighted(screen) == "Salud"
        await pilot.press(*"pend")
        assert [name for _id, name in screen._suggestions] == ["@Pendiente"]
        await pilot.press("enter")
        assert screen._parts[0].category_id == "catP"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    _open_stepping(monkeypatch, steps, categories=WITH_PENDING_CATEGORIES)
    assert fake_client.calls == [("PUT", PATH, {"parts": [_kept(category_id="catP")]})]


def test_opening_is_never_offered_on_category(fake_client, monkeypatch):
    """@Opening is not in the list, empty or filtered, and typing its name
    matches nothing: `⏎` refuses and the line stays."""

    async def steps(screen, pilot):
        await _enter_to(screen, pilot, "0.category")
        assert "catO" not in [ent[0] for ent in screen._suggestions]
        assert "@Opening" not in render_text(screen._suggest_renderable(), width=60)
        await pilot.press(*"open")
        assert screen._suggestions == []
        await pilot.press("enter")
        assert screen._key == "0.category"
        assert screen._parts[0].category_id == "cat2"

    notices = _open_stepping(monkeypatch, steps, categories=WITH_PENDING_CATEGORIES)
    assert ("", "No category matches “open”.") in notices
    assert fake_client.calls == []


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


#: Each form, and the part its save sends under its own id at its current amount.
FORMS = [("transaction", "tx1"), ("bank_line", "p1")]


@pytest.mark.parametrize(("form", "part"), FORMS)
def test_a_non_date_on_date_is_refused_at_enter_and_the_save_never_crashes(
    fake_client, monkeypatch, form, part
):
    """Typed key by key on DATE: `abc` + `⏎` notes `Date: use YYYY-MM-DD.`, the
    bar keeps `abc` and the cursor stays on DATE; `ctrl+s` then tries `abc` again,
    sends nothing and the app goes on running, on the Edit form and on the
    "no batch" Edit form."""
    _patch(monkeypatch, _line(TXN) if form == "transaction" else BANK_LINE)
    notes = _date_notes(monkeypatch)

    async def scenario(pilot, app):
        screen = _form(form)
        await app.push_screen(screen)
        await _wait_loaded(screen, pilot)
        bar = screen.query_one("#bar", Input)
        assert screen._key == "date"
        await pilot.press("ctrl+a", "ctrl+k", *"abc", "enter")
        await pilot.pause()
        assert screen._key == "date" and bar.value == "abc"
        assert screen._values["date"] == "2026-06-20"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: len(notes) == 2)
        assert app.is_running and app.screen is screen

    run_app(scenario)
    assert DATE_UNREADABLE == "Date: use YYYY-MM-DD."
    assert notes == [(DATE_UNREADABLE, "error")] * 2
    assert fake_client.calls == []


@pytest.mark.parametrize(("form", "part"), FORMS)
@pytest.mark.parametrize("typed", ["2026-10-23", "2026-10-23 14:30"])
def test_a_day_with_or_without_a_time_still_saves(fake_client, monkeypatch, form, part, typed):
    """A day on DATE, with or without a time, is taken at `⏎` and saved as the
    save's reader writes it, after a refused `abc` as on a first try."""
    from expense.dates import to_canonical_aware

    _patch(monkeypatch, _line(TXN) if form == "transaction" else BANK_LINE)
    notes = _date_notes(monkeypatch)

    async def scenario(pilot, app):
        screen = _form(form)
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
    assert fake_client.puts == [
        (
            PATH,
            {
                "date": to_canonical_aware(typed),
                "parts": [{"id": part, "amount_cents": -4250}],
            },
        )
    ]


def test_an_empty_date_still_commits_today(fake_client, monkeypatch):
    """An emptied DATE and `⏎` is no refusal: it commits today."""
    from datetime import date

    from expense.dates import to_canonical_aware

    _patch(monkeypatch)
    notes = _date_notes(monkeypatch)

    async def steps(screen, pilot, app):
        await pilot.press("ctrl+a", "ctrl+k", "enter")
        await pilot.pause()
        assert screen._key == "title"
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.puts)

    _open(scenario_steps=steps)
    assert not [n for n in notes if n[1] == "error"]
    today = to_canonical_aware(date.today().isoformat())
    assert fake_client.calls == [("PUT", PATH, {"date": today, "parts": [_kept()]})]
