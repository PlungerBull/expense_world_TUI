"""A card statement's create form: both halves in one form and one write.

Pane 2 A of docs/mockups/expense-world-card-statement.html: `n` on a card
account opens one form, the name and days typed once, then each half's
balances; `^s Create both` sends one `POST /reconciliations` with its `twin`
(contract: POST /v1/reconciliations). Any other account keeps today's form.
"""

import pytest
from textual.widgets import Input, Static

from expense import errors
from expense.errors import EngineError
from expense.formatting import half_name
from expense.reads import code_holders, statement_partners
from expense.tui.screens.reconciliations import (
    NewCardStatementScreen,
    NewReconciliationScreen,
    ReconciliationsScreen,
)
from tests.unit.helpers import (
    reconciliation_answer,
    refusal_text,
    render_text,
    run_app,
    wait_for,
    wait_for_list,
    whole,
)


def _account(aid: str, name: str, currency: str, code: str | None, **extra) -> dict:
    return {
        "id": aid,
        "name": name,
        "currency_code": currency,
        "current_balance_cents": 0,
        "statement_code": code,
        "is_person": False,
        **extra,
    }


SIG_PEN = _account("acc-sig-pen", "Signature PEN", "PEN", "SIG")
SIG_USD = _account("acc-sig-usd", "Signature USD", "USD", "SIG")
SUELDO = _account("acc-sueldo", "Sueldo Soles", "PEN", None)
AHORRO = _account("acc-ahorro", "Ahorro PEN", "PEN", "AHO")  # a code, no other half
ACCOUNTS = [SIG_PEN, SIG_USD, SUELDO, AHORRO]

PEN_ACCOUNT = (SIG_PEN["id"], "Signature PEN", "PEN")
USD_ACCOUNT = (SIG_USD["id"], "Signature USD", "USD")


# ---- the partner lookup and the half's name ----------------------------------


def test_each_card_account_names_the_other_and_no_other_account_has_one():
    partners = statement_partners(ACCOUNTS)
    assert partners == {
        "acc-sig-pen": ("acc-sig-usd", "Signature USD", "USD", "SIG"),
        "acc-sig-usd": ("acc-sig-pen", "Signature PEN", "PEN", "SIG"),
    }


def test_a_person_or_a_code_held_three_times_makes_no_card():
    eur = _account("acc-sig-eur", "Signature EUR", "EUR", "SIG")
    assert statement_partners([SIG_PEN, SIG_USD, eur]) == {}
    person = _account("acc-ana", "Ana", "USD", "SIG", is_person=True)
    assert statement_partners([SIG_PEN, person]) == {}


def test_an_archived_account_is_no_ones_other_half():
    """The engine refuses an archived account as `twin.account_id`
    (contract: POST /v1/reconciliations), so it makes no card."""
    archived = {**SIG_USD, "is_archived": True}
    assert statement_partners([SIG_PEN, archived]) == {}


def test_both_lookups_group_accounts_by_code_one_way():
    """`code_holders` is the one grouping: a code's accounts in the read's
    order, a person, a codeless or id-less account left out, and an archived
    one kept only when asked for."""
    archived = {**SIG_USD, "is_archived": True}
    person = _account("acc-ana", "Ana", "USD", "SIG", is_person=True)
    nameless = {"id": "acc-x", "statement_code": "AHO"}
    no_id = {**AHORRO, "id": None}
    items = [archived, SIG_PEN, SUELDO, person, AHORRO, nameless, no_id]
    assert code_holders(items, archived=True) == {
        "SIG": [USD_ACCOUNT, PEN_ACCOUNT],
        "AHO": [("acc-ahorro", "Ahorro PEN", "PEN"), ("acc-x", "(unnamed)", "?")],
    }
    assert code_holders(items, archived=False) == {
        "SIG": [PEN_ACCOUNT],
        "AHO": [("acc-ahorro", "Ahorro PEN", "PEN"), ("acc-x", "(unnamed)", "?")],
    }


def test_a_half_is_named_after_its_currency():
    assert half_name("PEN") == "soles half"
    assert half_name("USD") == "dollar half"
    assert half_name("EUR") == "EUR half"


# ---- `n` on the browse --------------------------------------------------------


def _patch_browse(monkeypatch, fake_client, accounts=ACCOUNTS) -> list:
    """`accounts`, an archived one only when asked for, as the engine lists
    them; the reconciliations are what the fake engine has created, each half
    naming its twin: `account_id` lists one account's, `statement_of` every
    account's holding the named account's code (contract: GET /v1/reconciliations).
    Returns each read's `(parameter, account)`."""
    reads: list = []

    def fetch(_cfg, *, account_id=None, statement_of=None, **kw):
        named = account_id or statement_of
        reads.append(("account_id" if account_id else "statement_of", named))
        code = next((a["statement_code"] for a in accounts if a["id"] == named), None)
        on = {named}
        if statement_of and code:
            on = {a["id"] for a in accounts if a["statement_code"] == code}
        made = [
            half
            for _path, body in fake_client.posts
            for half in _records(body)
            if half["account_id"] in on
        ]
        return whole(made)

    monkeypatch.setattr("expense.reads.fetch_reconciliations", fetch)

    def fetch_accounts(_cfg, *, include_archived=False, **kw):
        return whole([a for a in accounts if include_archived or not a.get("is_archived")])

    monkeypatch.setattr("expense.reads.fetch_accounts", fetch_accounts)
    return reads


def _halves(body: dict) -> list[dict]:
    """The halves a create sends: its top level, and its `twin` taking the
    request's name and days."""
    twin = body.get("twin")
    if not twin:
        return [body]
    shared = {key: body[key] for key in ("name", "date_start", "date_end")}
    return [body, {**shared, **twin}]


def _records(body: dict) -> list[dict]:
    """The halves one create makes, as the engine reads them back, each
    naming the other as its `twin_id`."""
    records = [_record(half) for half in _halves(body)]
    if len(records) == 2:
        records[0]["twin_id"], records[1]["twin_id"] = records[1]["id"], records[0]["id"]
    return records


def _record(sent: dict) -> dict:
    """A half as the engine reads it back from what was sent."""
    return {
        "id": sent["id"],
        "account_id": sent["account_id"],
        "name": sent["name"],
        "date_start": sent["date_start"],
        "date_end": sent["date_end"],
        "status": 1,
        "beginning_balance_cents": sent["beginning_balance_cents"],
        "ending_balance_cents": sent.get("ending_balance_cents"),
        "difference_cents": None,
        "twin_id": None,
        "unplaced_count": 0,
        "shared_place_count": 0,
    }


async def _press_n_on(pilot, app, row: int):
    screen = ReconciliationsScreen()
    await app.push_screen(screen)
    await wait_for_list(pilot, app)
    for _ in range(row):
        screen._accts_list.action_move(1)
    await wait_for(pilot, lambda: screen._acct_idx == row)
    await pilot.press("n")
    await wait_for(pilot, lambda: isinstance(app.screen, NewReconciliationScreen))
    return screen


@pytest.mark.parametrize(
    "row, account, other",
    [(0, PEN_ACCOUNT, "Signature USD"), (1, USD_ACCOUNT, "Signature PEN")],
    ids=["from the soles account", "from the dollar account"],
)
def test_n_on_either_card_account_opens_the_one_form(monkeypatch, fake_client, row, account, other):
    _patch_browse(monkeypatch, fake_client)

    async def scenario(pilot, app):
        await _press_n_on(pilot, app, row)
        form = app.screen
        assert type(form) is NewCardStatementScreen
        assert form._values["account"] == account[0]
        assert form._partner_id != account[0]
        assert form._display["accounts"] == f"{account[1]} + {other} · SIG"

    run_app(scenario)


@pytest.mark.parametrize("row", [2, 3], ids=["no statement code", "a code and no other half"])
def test_n_on_any_other_account_keeps_todays_form(monkeypatch, fake_client, row):
    _patch_browse(monkeypatch, fake_client)

    async def scenario(pilot, app):
        await _press_n_on(pilot, app, row)
        assert type(app.screen) is NewReconciliationScreen
        assert app.screen._sequence() == ["name", "date_start", "date_end", "begin", "end"]

    run_app(scenario)


def test_a_card_whose_other_account_is_archived_keeps_todays_form(monkeypatch, fake_client):
    """The browse lists no archived account, so Signature PEN has no other
    half to name: `n` opens the one-account form, and its save sends no `twin`."""
    _patch_browse(monkeypatch, fake_client, [SIG_PEN, {**SIG_USD, "is_archived": True}])

    async def scenario(pilot, app):
        await _press_n_on(pilot, app, 0)
        form = app.screen
        assert type(form) is NewReconciliationScreen
        for text in ["Octubre 2026", "2026-09-26", "2026-10-25", "-1,240.50", ""]:
            _enter(form, text)
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(_path, body)] = fake_client.posts
    assert body["account_id"] == "acc-sig-pen" and "twin" not in body


# ---- the form -----------------------------------------------------------------


def _form() -> NewCardStatementScreen:
    return NewCardStatementScreen(account=PEN_ACCOUNT, partner=USD_ACCOUNT, code="SIG")


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


TYPED = ["Octubre 2026", "2026-09-26", "2026-10-25", "-1,240.50", "-380.70", "-60.12"]


def test_the_form_is_drawn_as_picked(fake_client):
    """The name and days once, the accounts stated on their own line, then each
    half's balances in its own currency; the footer says `Create both`."""

    async def scenario(pilot, app):
        screen = _form()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        assert screen.crumb == ("Reconciliations", "Signature PEN", "New")
        assert screen.active_bindings["ctrl+s"].binding.description == "Create both"
        for text in TYPED[:5]:
            _enter(screen, text)
        assert screen._key == "twin_begin"
        assert screen._label("twin_begin") == "BEGIN BALANCE USD"
        await pilot.pause()
        label = screen.query_one("#field", Static)
        assert label.size.width == len("BEGIN BALANCE USD") and "USD" in str(label.content)
        hint = str(screen.query_one("#hint", Static).content)
        assert hint == "signed decimal · the dollar half's opening balance"
        summary = render_text(screen._summary_renderable(), width=100)
        lines = [line.split() for line in summary.splitlines()]
        assert lines[0] == ["name", "Octubre", "2026"]
        assert lines[1] == ["accounts", "Signature", "PEN", "+", "Signature", "USD", "·", "SIG"]
        assert lines[4] == ["begin", "balance", "PEN", "-1,240.50"]
        assert lines[5] == ["end", "balance", "PEN", "-380.70"]
        assert lines[6] == ["begin", "balance", "USD", "—", "*"]
        assert lines[7] == ["end", "balance", "USD", "—", "(optional)"]
        assert "read-only" not in summary

    run_app(scenario)


def test_the_hints_say_save_only_on_the_last_line():
    screen = _form()
    assert screen._hint_for("begin") == "signed decimal · the soles half's opening balance"
    assert screen._hint_for("end") == "signed decimal · the soles half's closing balance · optional"
    assert screen._hint_for("twin_end") == (
        "signed decimal · the dollar half's closing balance · optional · enter saves"
    )


def test_ctrl_s_sends_one_create_with_its_twin(fake_client):
    async def scenario(pilot, app):
        screen = _form()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in TYPED:
            _enter(screen, text)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(path, body)] = fake_client.posts
    assert path == "/reconciliations"
    twin = body.pop("twin")
    assert set(body) == {
        "id",
        "account_id",
        "name",
        "date_start",
        "date_end",
        "beginning_balance_cents",
        "ending_balance_cents",
    }
    assert body["account_id"] == "acc-sig-pen" and body["name"] == "Octubre 2026"
    assert (body["date_start"], body["date_end"]) == ("2026-09-26", "2026-10-25")
    assert (body["beginning_balance_cents"], body["ending_balance_cents"]) == (-124050, -38070)
    # the twin takes the request's name and days: only its id, account and balances
    assert set(twin) == {"id", "account_id", "beginning_balance_cents"}
    assert twin["account_id"] == "acc-sig-usd" and twin["beginning_balance_cents"] == -6012
    assert twin["id"] != body["id"]


def test_enter_on_the_last_line_saves_and_an_empty_end_is_left_out(fake_client):
    async def scenario(pilot, app):
        screen = _form()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in [*TYPED[:4], "", "-60.12", "-53.88"]:  # no soles end; ⏎ on the last saves
            _enter(screen, text)
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(_path, body)] = fake_client.posts
    assert "ending_balance_cents" not in body
    assert body["twin"]["ending_balance_cents"] == -5388


def test_a_missing_begin_balance_is_named_and_nothing_is_sent(fake_client, monkeypatch):
    notes: list = []
    monkeypatch.setattr(
        NewCardStatementScreen, "notify", lambda self, message, **kw: notes.append(message)
    )

    async def scenario(pilot, app):
        screen = _form()
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in TYPED[:5]:
            _enter(screen, text)
        await pilot.press("ctrl+s")
        await pilot.pause()

    run_app(scenario)
    assert notes == ["Begin balance USD is required."]
    assert fake_client.posts == []


def test_saved_it_says_so_and_the_panel_lands_on_the_new_statement(monkeypatch, fake_client):
    """As the one-account form does: back to the browse, the open account's
    panel read again, the cursor on its new half, and the note `Statement
    created.`; no screen is pushed."""
    reads = _patch_browse(monkeypatch, fake_client)
    notes: list = []
    monkeypatch.setattr(
        NewCardStatementScreen, "notify", lambda self, message, **kw: notes.append(message)
    )

    def post(path, json_body=None):
        fake_client.calls.append(("POST", path, json_body))
        return reconciliation_answer(*(_record(half) for half in _halves(json_body)))

    fake_client.post = post

    async def scenario(pilot, app):
        browse = await _press_n_on(pilot, app, 0)
        form = app.screen
        for text in TYPED:
            _enter(form, text)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is browse and browse._batch_list is not None)
        [(_path, body)] = fake_client.posts
        assert reads == [("statement_of", "acc-sig-pen")]
        assert browse._mode == "batches" and browse._batch_list.has_focus
        # the new statement is one row, standing for this account's half
        assert browse._batch_list.cursor_key == body["id"]
        assert [r.key for r in browse._batch_list._rows] == [body["id"]]

    run_app(scenario)
    assert notes == ["Statement created."]


# ---- every refusal the create can meet ----------------------------------------

_INVALID = "Must reference an active, non-archived account."
_PERSON = "Person accounts cannot have reconciliations."
_OVERLAP = "Overlaps 'Septiembre 2026' (2026-08-26 to 2026-09-25). A day belongs to one statement."
_MONTH = "Statement month taken by 'Octubre 2026' (2026-09-26 to 2026-10-25)."


def _refusal(code: str, status: int, refused: dict[str, tuple[str, str]]) -> EngineError:
    """`refused` is `key → (reason, words)`."""
    return EngineError(
        code,
        "Reconciliation validation failed.",
        {key: words for key, (_reason, words) in refused.items()},
        status,
        {},
        reasons={key: reason for key, (reason, _words) in refused.items()},
    )


#: In the order the engine checks them, one check at a time
#: (contract: POST /v1/reconciliations, "One check at a time"); `twin.` names
#: the other half (contract: POST /v1/reconciliations, "Which half a refusal names").
REFUSALS = {
    "an empty name": _refusal("VALIDATION_ERROR", 422, {"name": ("EMPTY", "Must not be empty.")}),
    "an inverted period": _refusal(
        "VALIDATION_ERROR",
        422,
        {"date_end": ("RANGE_INVERTED", "Must be on or after date_start.")},
    ),
    "the same id twice": _refusal(
        "VALIDATION_ERROR",
        422,
        {"twin.id": ("DUPLICATE_IN_REQUEST", "Must differ from id.")},
    ),
    "this half's id taken": _refusal("CONFLICT", 409, {"id": ("ID_EXISTS", "Already exists.")}),
    "the other half's id taken": _refusal(
        "CONFLICT", 409, {"twin.id": ("ID_EXISTS", "Already exists.")}
    ),
    "both ids taken": _refusal(
        "CONFLICT",
        409,
        {"id": ("ID_EXISTS", "Already exists."), "twin.id": ("ID_EXISTS", "Already exists.")},
    ),
    "this account gone": _refusal(
        "VALIDATION_ERROR", 422, {"account_id": ("INVALID_REFERENCE", _INVALID)}
    ),
    "this account a person": _refusal(
        "VALIDATION_ERROR", 422, {"account_id": ("PERSON_ACCOUNT", _PERSON)}
    ),
    "the other account gone": _refusal(
        "VALIDATION_ERROR", 422, {"twin.account_id": ("INVALID_REFERENCE", _INVALID)}
    ),
    "the other account a person": _refusal(
        "VALIDATION_ERROR", 422, {"twin.account_id": ("PERSON_ACCOUNT", _PERSON)}
    ),
    "the other account no longer the card's": _refusal(
        "VALIDATION_ERROR",
        422,
        {
            "twin.account_id": (
                "NOT_STATEMENT_PARTNER",
                "Must be the other account holding this account's statement code.",
            )
        },
    ),
    "this half's days overlapping": _refusal(
        "VALIDATION_ERROR", 422, {"date_start": ("PERIOD_OVERLAPS", _OVERLAP)}
    ),
    "the other half's days overlapping": _refusal(
        "VALIDATION_ERROR", 422, {"twin.date_start": ("PERIOD_OVERLAPS", _OVERLAP)}
    ),
    "both halves' days overlapping": _refusal(
        "VALIDATION_ERROR",
        422,
        {
            "date_start": ("PERIOD_OVERLAPS", _OVERLAP),
            "twin.date_start": ("PERIOD_OVERLAPS", _OVERLAP),
        },
    ),
    "the statement month taken": _refusal(
        "VALIDATION_ERROR",
        422,
        {
            "date_end": ("STATEMENT_MONTH_TAKEN", _MONTH),
            "twin.date_end": ("STATEMENT_MONTH_TAKEN", _MONTH),
        },
    ),
}

#: The one refusal with a line of the app's under the engine's words: a taken
#: id, on either half, is the app's fault (`errors.NEXT_STEPS`).
LINES = {
    case: errors.next_step(err)
    for case, err in REFUSALS.items()
    if "ID_EXISTS" in (err.reasons or {}).values()
}


@pytest.mark.parametrize("case", list(REFUSALS))
def test_a_refusal_shows_the_engine_words_and_creates_nothing(fake_client, monkeypatch, case):
    """The form's `Failed` note is the engine's words whole, the refused keys
    naming each half; the form stays with what was typed, and nothing is
    handed back."""
    err = REFUSALS[case]
    fake_client.errors["POST"] = err
    notices: list = []
    monkeypatch.setattr(
        NewCardStatementScreen,
        "notify",
        lambda self, message, title="", **kw: notices.append((title, str(message))),
    )
    handed: list = []

    async def scenario(pilot, app):
        screen = _form()
        await app.push_screen(screen, handed.append)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in TYPED:
            _enter(screen, text)
        typed = dict(screen._values)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: notices and not screen._submitting)
        assert notices == [("Failed", refusal_text(err, LINES.get(case)))]
        assert app.screen is screen and screen._values == typed

    run_app(scenario)
    assert [path for path, _body in fake_client.posts] == ["/reconciliations"]
    assert handed == []


def test_the_todays_form_still_saves_on_enter_on_end(fake_client):
    """The balances' commit is shared with today's form, whose END BALANCE is
    still its last line: `⏎` there saves one reconciliation, no `twin`."""

    async def scenario(pilot, app):
        screen = NewReconciliationScreen(account_id="acc-sueldo", account_name="Sueldo Soles")
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in ["Octubre 2026", "2026-10-01", "2026-10-31", "100", "90"]:
            _enter(screen, text)
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(_path, body)] = fake_client.posts
    assert "twin" not in body and body["ending_balance_cents"] == 9000
