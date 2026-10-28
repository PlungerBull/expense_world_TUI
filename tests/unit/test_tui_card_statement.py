"""A card statement's create form: both accounts' balances in one form and one write.

Pane 2 A of docs/mockups/expense-world-card-statement.html: `n` on an account whose
holder holds another account opens one form, the name and days typed once, then each
account's balances; `^s Create both` sends one `POST /statements` with the holder and
an entry in `balances` for each account (contract: POST /v1/statements). An account
alone on its holder keeps today's form.
"""

import pytest
from textual.widgets import Input, Static

from expense.errors import EngineError
from expense.formatting import half_name
from expense.tui.screens.reconciliations import (
    NewCardStatementScreen,
    NewReconciliationScreen,
    ReconciliationsScreen,
)
from tests.unit.helpers import (
    ARCHIVED_FIELD_WORDS,
    account_record,
    holder_list,
    refusal_text,
    render_text,
    run_app,
    statement_create_answer,
    statement_list,
    wait_for,
    wait_for_list,
    whole,
)

#: The accounts as the engine reads them, each naming the holder it is on
#: (contract: "Holders"): a card's two on one holder, and two accounts alone on theirs.
SIG_PEN = account_record(id="acc-sig-pen", name="Signature PEN", holder_id="h-sig")
SIG_USD = account_record(
    id="acc-sig-usd", name="Signature USD", currency_code="USD", holder_id="h-sig"
)
SUELDO = account_record(id="acc-sueldo", name="Sueldo Soles", holder_id="h-sueldo")
AHORRO = account_record(id="acc-ahorro", name="Ahorro PEN", holder_id="h-ahorro")
JOINT_PEN = account_record(id="acc-joint-pen", name="Joint PEN", holder_id="h-joint")
JOINT_USD = account_record(
    id="acc-joint-usd", name="Joint USD", currency_code="USD", holder_id="h-joint"
)
ACCOUNTS = [SIG_PEN, SIG_USD, SUELDO, AHORRO, JOINT_PEN, JOINT_USD]
#: The holders as `GET /holders` reads them: the card's with code SIG, Sueldo's with
#: none, Ahorro's with a code and one account, and Joint's two accounts with no code.
HOLDERS = [
    {
        "id": "h-sig",
        "name": "BCP Signature",
        "statement_code": "SIG",
        "account_ids": ["acc-sig-pen", "acc-sig-usd"],
    },
    {"id": "h-sueldo", "name": "Sueldo Soles", "account_ids": ["acc-sueldo"]},
    {
        "id": "h-ahorro",
        "name": "Ahorro PEN",
        "statement_code": "AHO",
        "account_ids": ["acc-ahorro"],
    },
    {"id": "h-joint", "name": "Joint", "account_ids": ["acc-joint-pen", "acc-joint-usd"]},
]

PEN_ACCOUNT = (SIG_PEN["id"], "Signature PEN", "PEN")
USD_ACCOUNT = (SIG_USD["id"], "Signature USD", "USD")


def test_a_half_is_named_after_its_currency():
    assert half_name("PEN") == "soles half"
    assert half_name("USD") == "dollar half"
    assert half_name("EUR") == "EUR half"


# ---- `n` on the browse --------------------------------------------------------


def _patch_browse(monkeypatch, fake_client) -> list:
    """The accounts and holders as the engine lists them; the statements are what
    the fake engine has created, each listed under the holder it names, as
    `POST /statements` answers it (contract: GET /v1/statements). Returns the holder
    each statement read asked for."""
    reads: list = []

    def fetch(_cfg, holder_id, **kw):
        reads.append(holder_id)
        made = [body for _path, body in fake_client.posts if body["holder_id"] == holder_id]
        return statement_list([statement_create_answer(body) for body in made])

    monkeypatch.setattr("expense.reads.fetch_statements", fetch)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(ACCOUNTS))
    monkeypatch.setattr("expense.reads.fetch_holders", lambda *a, **k: holder_list(HOLDERS))
    return reads


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
        assert form._holder_id == "h-sig"
        assert form._display["accounts"] == f"{account[1]} + {other} · SIG"

    run_app(scenario)


@pytest.mark.parametrize(
    "row, holder",
    [(2, "h-sueldo"), (3, "h-ahorro")],
    ids=["no statement code", "a code and one account"],
)
def test_n_on_an_account_alone_on_its_holder_keeps_todays_form(
    monkeypatch, fake_client, row, holder
):
    _patch_browse(monkeypatch, fake_client)

    async def scenario(pilot, app):
        await _press_n_on(pilot, app, row)
        assert type(app.screen) is NewReconciliationScreen
        assert app.screen._sequence() == ["name", "date_start", "date_end", "begin", "end"]
        assert app.screen._holder_id == holder

    run_app(scenario)


# ---- the form -----------------------------------------------------------------


def _form(code: str = "SIG") -> NewCardStatementScreen:
    return NewCardStatementScreen(
        account=PEN_ACCOUNT, partner=USD_ACCOUNT, code=code, holder_id="h-sig"
    )


def _enter(screen, text):
    screen.query_one("#bar", Input).value = text
    screen._recompute(text)
    screen.on_input_submitted(None)


TYPED = ["Octubre 2026", "2026-09-26", "2026-10-25", "-1,240.50", "-380.70", "-60.12"]


def test_the_form_is_drawn_as_picked(fake_client):
    """The name and days once, the accounts stated on their own line, then each
    account's balances in its own currency; the footer says `Create both`."""

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
        assert hint.splitlines()[0] == "signed decimal · the dollar half's opening balance"
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


def test_a_holder_with_no_code_states_its_accounts_alone():
    """A holder's code is optional (contract: "Holders", "Statement code"): with none,
    the accounts' line names the two accounts and nothing after them."""
    assert _form(code="")._display["accounts"] == "Signature PEN + Signature USD"


def test_n_on_a_holder_of_two_accounts_with_no_code_opens_the_card_form(monkeypatch, fake_client):
    """Two accounts on one holder with no statement code: `n` opens the card form,
    its accounts' line the two accounts alone, and `^s` sends one create naming the
    holder with both accounts' balances."""
    _patch_browse(monkeypatch, fake_client)

    async def scenario(pilot, app):
        await _press_n_on(pilot, app, 4)
        form = app.screen
        assert type(form) is NewCardStatementScreen
        assert form._holder_id == "h-joint"
        for text in TYPED[:2]:
            _enter(form, text)
        summary = render_text(form._summary_renderable(), width=100)
        assert summary.splitlines()[1].split() == ["accounts", "Joint", "PEN", "+", "Joint", "USD"]
        for text in TYPED[2:]:
            _enter(form, text)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(path, body)] = fake_client.posts
    assert path == "/statements" and body["holder_id"] == "h-joint"
    assert body["balances"] == [
        {
            "account_id": "acc-joint-pen",
            "beginning_balance_cents": -124050,
            "ending_balance_cents": -38070,
        },
        {"account_id": "acc-joint-usd", "beginning_balance_cents": -6012},
    ]


def test_the_hints_say_save_only_on_the_last_line():
    screen = _form()
    for key, half in (("begin", "soles"), ("twin_begin", "dollar")):
        assert screen._hint_for(key).splitlines() == [
            f"signed decimal · the {half} half's opening balance",
            "0.00 if it holds the account's opening balance, which already counts it",
        ]
    assert screen._hint_for("end") == "signed decimal · the soles half's closing balance · optional"
    assert screen._hint_for("twin_end") == (
        "signed decimal · the dollar half's closing balance · optional · enter saves"
    )


def test_ctrl_s_sends_one_create_with_both_accounts_balances(fake_client):
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
    assert path == "/statements"
    assert set(body) == {"id", "holder_id", "name", "date_start", "date_end", "balances"}
    assert body["holder_id"] == "h-sig" and body["name"] == "Octubre 2026"
    assert (body["date_start"], body["date_end"]) == ("2026-09-26", "2026-10-25")
    # one entry per account of the holder, the open account's first; no end typed for
    # the dollar account, so its entry leaves the key out
    assert body["balances"] == [
        {
            "account_id": "acc-sig-pen",
            "beginning_balance_cents": -124050,
            "ending_balance_cents": -38070,
        },
        {"account_id": "acc-sig-usd", "beginning_balance_cents": -6012},
    ]


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
    pen, usd = body["balances"]
    assert "ending_balance_cents" not in pen
    assert usd["ending_balance_cents"] == -5388


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
    """As the one-account form does: back to the browse, the open account's holder's
    statements read again, the cursor on the new one, and the note `Statement
    created.`; no screen is pushed."""
    reads = _patch_browse(monkeypatch, fake_client)
    notes: list = []
    monkeypatch.setattr(
        NewCardStatementScreen, "notify", lambda self, message, **kw: notes.append(message)
    )

    async def scenario(pilot, app):
        browse = await _press_n_on(pilot, app, 0)
        form = app.screen
        for text in TYPED:
            _enter(form, text)
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: app.screen is browse and browse._batch_list is not None)
        [(_path, body)] = fake_client.posts
        assert reads == ["h-sig"]
        assert browse._mode == "batches" and browse._batch_list.has_focus
        # the new statement is one row, keyed by its id
        assert browse._batch_list.cursor_key == body["id"]
        assert [r.key for r in browse._batch_list._rows] == [body["id"]]

    run_app(scenario)
    assert notes == ["Statement created."]


# ---- every refusal the create can meet ----------------------------------------

_ON_HOLDER = "Must be a live account of the statement's holder."
_OVERLAP = "Overlaps 'Septiembre 2026' (2026-08-26 to 2026-09-25). A day belongs to one statement."
_MONTH = "Statement month taken by 'Octubre 2026' (2026-09-26 to 2026-10-25)."
#: The field words of a refusal whose sentence the contract does not print.
_STAND_IN = "Stand-in field words."


def _refusal(code: str, status: int, refused: dict[str, tuple[str, str]]) -> EngineError:
    """`refused` is `key → (reason, words)`."""
    return EngineError(
        code,
        "Statement validation failed.",
        {key: words for key, (_reason, words) in refused.items()},
        status,
        {},
        reasons={key: reason for key, (reason, _words) in refused.items()},
    )


def _invalid(refused: dict[str, tuple[str, str]]) -> EngineError:
    return _refusal("VALIDATION_ERROR", 422, refused)


#: In the order the engine checks them, the first that refuses answering
#: (contract: POST /v1/statements); a refusal of the request's own list names an
#: entry by its place (contract: "Statements", "Which account a refusal names").
REFUSALS = {
    "an empty name": _invalid({"name": ("EMPTY", "Must not be empty.")}),
    "an inverted period": _invalid(
        {"date_end": ("RANGE_INVERTED", "Must be on or after date_start.")}
    ),
    "an account listed twice": _invalid(
        {"balances.1.account_id": ("DUPLICATE_IN_REQUEST", _STAND_IN)}
    ),
    "the id taken": _refusal("CONFLICT", 409, {"id": ("ID_EXISTS", "Already exists.")}),
    "the holder gone": _invalid({"holder_id": ("INVALID_REFERENCE", _STAND_IN)}),
    "an account no longer on the holder": _invalid(
        {"balances.1.account_id": ("ACCOUNT_NOT_ON_HOLDER", _ON_HOLDER)}
    ),
    "an account of the holder left out": _invalid(
        {"balances": ("HOLDER_ACCOUNTS_MISSING", _STAND_IN)}
    ),
    "the holder archived": _invalid({"holder_id": ("ACCOUNT_ARCHIVED", ARCHIVED_FIELD_WORDS)}),
    "the days overlapping": _invalid({"date_start": ("PERIOD_OVERLAPS", _OVERLAP)}),
    "the statement month taken": _invalid({"date_end": ("STATEMENT_MONTH_TAKEN", _MONTH)}),
}

#: The one refusal with a line of the app's under the engine's words: a taken id is
#: the app's fault. Every other case has none.
LINES = {
    "the id taken": (
        "Not your mistake: the app sent it wrong and nothing was saved. "
        "Try again; if it happens again, report it."
    ),
}


@pytest.mark.parametrize("case", list(REFUSALS))
def test_a_refusal_shows_the_engine_words_and_creates_nothing(fake_client, monkeypatch, case):
    """The form's `Failed` note is the engine's words whole, each refused key as the
    engine names it, then the app's line where it has one (`LINES`); the form stays
    with what was typed, and nothing is handed back."""
    _refused_on_the_form(fake_client, monkeypatch, REFUSALS[case], LINES.get(case))


def test_a_refusal_keyed_by_an_accounts_balances_lands_under_its_field(fake_client, monkeypatch):
    """A refusal about one account's balances is keyed `balances.<account_id>.<field>`,
    by the account's id (contract: "Statements", "Which account a refusal names"): the
    note shows it under the engine's message as that key and its words, with no line
    of the app's."""
    key = "balances.acc-sig-usd.beginning_balance_cents"
    err = _invalid({key: ("OUT_OF_RANGE", _STAND_IN)})
    note = _refused_on_the_form(fake_client, monkeypatch, err, None)
    assert note.splitlines() == [
        "VALIDATION_ERROR — Statement validation failed.",
        f"  {key}: {_STAND_IN}",
    ]


def _refused_on_the_form(fake_client, monkeypatch, err: EngineError, line: str | None) -> str:
    """The card form, filled and sent with `^s`, `err` the engine's answer: the
    `Failed` note is `err`'s words and `line`, the form stays with what was typed, one
    create was sent and nothing is handed back. Returns the note."""
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
        assert app.screen is screen and screen._values == typed

    run_app(scenario)
    assert notices == [("Failed", refusal_text(err, line))]
    assert [path for path, _body in fake_client.posts] == ["/statements"]
    assert handed == []
    return notices[0][1]


def test_the_todays_form_still_saves_on_enter_on_end(fake_client):
    """The balances' commit is shared with today's form, whose END BALANCE is still
    its last line: `⏎` there saves one statement, one account's balances in it."""

    async def scenario(pilot, app):
        screen = NewReconciliationScreen(
            account_id="acc-sueldo", account_name="Sueldo Soles", holder_id="h-sueldo"
        )
        await app.push_screen(screen)
        await wait_for(pilot, lambda: bool(screen.query("#bar")))
        for text in ["Octubre 2026", "2026-10-01", "2026-10-31", "100", "90"]:
            _enter(screen, text)
        await wait_for(pilot, lambda: fake_client.posts)

    run_app(scenario)
    [(_path, body)] = fake_client.posts
    assert body["holder_id"] == "h-sueldo"
    assert body["balances"] == [
        {"account_id": "acc-sueldo", "beginning_balance_cents": 10000, "ending_balance_cents": 9000}
    ]
