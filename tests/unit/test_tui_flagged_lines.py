"""The lines a statement's close flagged for review (pick 1A of
docs/mockups/expense-world-statement-flagged-lines.html).

A complete goes through with lines left in no statement and names them by id, each
balance's `review_lines`, every account's of the statement
(contract: POST /v1/statements/{statement_id}/complete, "Response"). The
app pushes a screen of its own on the statement's review list, paged whole in the
statement's order with no id sent, its count the engine's
(contract: GET /v1/bank-lines, "It has no bound"), and the statement keeps a `⚑`
line and `f` until its next status change."""

import pytest
from textual.widgets import Static

from expense.errors import EngineError, format_error
from expense.formatting import bank_line_columns
from expense.tui.screens.edit_form import EditFormScreen
from expense.tui.screens.help import screen_inventory
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.reconciliations import (
    FlaggedLinesScreen,
    ReconciliationDetailScreen,
    account_view,
)
from expense.tui.theme import PALETTE
from tests.unit.helpers import (
    bank_line_row,
    cursor_page,
    import_part,
    render_text,
    run_app,
    statement_complete_answer,
    statement_record,
    wait_for,
)

NAMES = {"sig-pen": "Signature PEN", "sig-usd": "Signature USD", "acc1": "BCP PEN"}


def _line(line: str, cents: int, day: str, title: str, account: str = "sig-pen") -> dict:
    part = import_part(f"t-{line}", cents, account_id=account, line=line, day=day, title=title)
    return bank_line_row(line, [part], net_cents=cents, account_id=account)


TAMBO = _line("l-tambo", -750, "2026-09-25", "TAMBO MIRAFLORES")
UBER = _line("l-uber", -4200, "2026-10-20", "UBER *TRIP")
SPOTIFY = _line("l-spotify", -599, "2026-10-24", "SPOTIFY P2F3", account="sig-usd")
#: A purchase split 60 + 40: deleted whole, after the question naming its parts.
FARMACIA = bank_line_row(
    "l-farmacia",
    [
        import_part("t-f1", -6000, account_id="sig-pen", line="l-farmacia", day="2026-10-11"),
        import_part("t-f2", -4000, account_id="sig-pen", line="l-farmacia", day="2026-10-11"),
    ],
    net_cents=-10000,
    account_id="sig-pen",
)


def _balance(account: str) -> dict:
    """An account's balances in a draft whose ending balance is entered and adds up."""
    return {
        "account_id": account,
        "beginning_balance_cents": 0,
        "ending_balance_cents": -4490,
        "difference_cents": 0,
    }


#: Octubre 2026, a draft statement of the card holding Signature PEN and Signature USD,
#: every ending balance entered and its order whole.
CARD = statement_record(
    {
        "id": "s-sig",
        "holder_id": "h-sig",
        "name": "Octubre 2026",
        "date_start": "2026-09-26",
        "date_end": "2026-10-25",
        "unplaced_count": 0,
        "shared_place_count": 0,
        "balances": [_balance("sig-pen"), _balance("sig-usd")],
    }
)
#: The same days' statement of a holder of acc1 alone, with no statement code.
BCP = statement_record(
    {
        "id": "s1",
        "name": "Octubre BCP",
        "date_start": "2026-09-26",
        "date_end": "2026-10-25",
        "balances": [_balance("acc1")],
    }
)
#: The card's statement opened on Signature PEN, and the plain one opened on acc1.
SOLES = account_view(CARD, "sig-pen")
PLAIN = account_view(BCP, "acc1")


def _conflict(field: str) -> EngineError:
    return EngineError(
        "VALIDATION_ERROR", "Invalid request.", {field: "CONFLICTING_PARAMETERS"}, 422, {}
    )


class Lines(dict):
    """The engine's live bank lines by id, every one of them on the statement's
    review list, answering the fake client's GETs as the engine does
    (contract: GET /v1/bank-lines, "Filters"):

    - `GET /bank-lines?unassigned_in_period_of=…&sort=statement`: the review list,
      oldest first as lines holding no place are (contract: GET /v1/bank-lines,
      "Ordering"), `limit` lines a page (50 when none is sent), paged by
      `c<next index>` cursors. Any other `sort`, or another filter beside it, is a
      `422`, as the engine answers (contract: GET /v1/bank-lines, "Taken alone").
      Each read's query is kept in `reads`; `refusal`, when set, is raised instead.
    - `GET /bank-lines/count?unassigned_in_period_of=…`: how many lines the review
      list holds, or `count` when a test sets it. Each count's query is kept in
      `counts`.
    - `GET /bank-lines` with `ids`: fails the test — the flagged lines send none.
    - `GET /bank-lines` otherwise: the statement's own reads, no line.
    - `GET /bank-lines/{id}`: the line, as the Edit form reads it, or a `404`.

    Every read in `expense.reads` goes to the fake client. A line deleted is one
    taken out. Any other GET goes to the fake client's own answers."""

    def __init__(self, monkeypatch, fake_client, *lines: dict) -> None:
        super().__init__((line["id"], line) for line in lines)
        self.reads: list[dict] = []
        self.counts: list[dict] = []
        self.count: int | None = None
        self.refusal: Exception | None = None
        self._client = fake_client
        self._get = fake_client.get
        monkeypatch.setattr(fake_client, "get", self._serve)
        monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)

    def _review_list(self) -> list[dict]:
        return sorted(self.values(), key=lambda line: (bank_line_columns(line)[0], line["id"]))

    def _serve(self, path: str, *, auth: bool = True, params: dict | None = None):
        query = params or {}
        assert "ids" not in query, "the flagged lines are read with no ids"
        if path == "/bank-lines/count" and "unassigned_in_period_of" in query:
            self._client.calls.append(("GET", path, params))
            self.counts.append(dict(query))
            if set(query) != {"unassigned_in_period_of"}:
                raise _conflict("unassigned_in_period_of")
            return {"count": len(self) if self.count is None else self.count}
        if path == "/bank-lines" and "unassigned_in_period_of" in query:
            self._client.calls.append(("GET", path, params))
            self.reads.append(dict(query))
            if self.refusal is not None:
                raise self.refusal
            if query.get("sort") != "statement":
                raise _conflict("sort")
            if set(query) - {"unassigned_in_period_of", "sort", "after", "limit"}:
                raise _conflict("unassigned_in_period_of")
            start = int(query["after"][1:]) if query.get("after") else 0
            limit = query.get("limit", 50)
            listed = self._review_list()
            end = start + limit
            more = f"c{end}" if end < len(listed) else None
            return cursor_page(listed[start:end], next_cursor=more, limit=limit)
        if path == "/bank-lines":
            self._client.calls.append(("GET", path, params))
            return cursor_page([])
        if path.startswith("/bank-lines/"):
            self._client.calls.append(("GET", path, params))
            line_id = path.removeprefix("/bank-lines/")
            if line_id not in self:
                raise EngineError("NOT_FOUND", "Bank line not found.", None, 404, {})
            return self[line_id]
        return self._get(path, auth=auth, params=params)


def _review(statement_id: str, after: str | None = None) -> dict:
    """One page's read of a statement's review list, as the screen sends it."""
    read = {"unassigned_in_period_of": statement_id, "sort": "statement", "limit": 200}
    return read if after is None else {**read, "after": after}


def _by_id(fake_client) -> list[str]:
    """Every `GET /bank-lines/{id}` the app sent."""
    return [
        path
        for verb, path, _ in fake_client.calls
        if verb == "GET" and path.count("/") > 1 and path != "/bank-lines/count"
    ]


def _patch(monkeypatch) -> None:
    """The accounts' names the screens show."""
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: dict(NAMES)
    )


def _flags(fake_client, record: dict, own: list[str], other: list[str] | None = None) -> None:
    """The complete's answer on the statement `record` is opened on: the opened
    account's balance flags `own`, the card's other account's balance `other`."""
    statement = {CARD["id"]: CARD, BCP["id"]: BCP}[record["id"]]
    balances = [
        {**b, "review_lines": own if b["account_id"] == record["account_id"] else other or []}
        for b in statement["balances"]
    ]
    fake_client.write_responses[f"/statements/{record['id']}/complete"] = statement_complete_answer(
        {**statement, "status": 2, "balances": balances}
    )


async def _complete(pilot, app, record: dict) -> ReconciliationDetailScreen:
    screen = ReconciliationDetailScreen(dict(record))
    await app.push_screen(screen)
    await wait_for(pilot, lambda: screen._list is not None)
    await pilot.press("c")
    await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
    await pilot.press("y")
    return screen


async def _flagged_screen(pilot, app) -> FlaggedLinesScreen:
    await wait_for(pilot, lambda: isinstance(app.screen, FlaggedLinesScreen))
    screen = app.screen
    await wait_for(pilot, lambda: screen._list is not None)
    return screen


def _text(screen, selector: str) -> str:
    return str(screen.query_one(selector, Static).visual)


def _footer(screen) -> list[str]:
    """The footer's entries, in order, as `key Description`."""
    return [
        f"{screen.app.get_key_display(a.binding)} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


def _listed(screen: FlaggedLinesScreen) -> list:
    return [row.key for row in screen._list._rows]


# ---- no flagged line ------------------------------------------------------------


def test_a_close_that_flags_nothing_opens_no_screen_and_adds_nothing(fake_client, monkeypatch):
    _patch(monkeypatch)
    engine = Lines(monkeypatch, fake_client)
    _flags(fake_client, SOLES, [], [])

    async def scenario(pilot, app):
        screen = await _complete(pilot, app, SOLES)
        await wait_for(pilot, lambda: screen._record["status"] == 2)
        await pilot.pause()
        assert app.screen is screen
        assert not screen.query_one("#rflag", Static).display
        assert "f Flagged" not in _footer(screen)
        await pilot.press("f")
        await pilot.pause()
        assert app.screen is screen
        assert engine.reads == []

    run_app(scenario)


# ---- a soles account, and a card ----------------------------------------------


def test_a_close_on_one_account_shows_its_flagged_lines_as_drawn(fake_client, monkeypatch):
    """A holder of one account: the lines are its statement's review list, in one page
    read with no id sent, the count the engine's, and no line read by its id; the rows
    in the engine's order, not the close's; the screen's words, its columns and its
    footer as pane 1A draws them."""
    _patch(monkeypatch)
    lines = [{**line, "account_id": "acc1"} for line in (TAMBO, UBER)]
    engine = Lines(monkeypatch, fake_client, *lines)
    _flags(fake_client, PLAIN, ["l-uber", "l-tambo"])

    async def scenario(pilot, app):
        await _complete(pilot, app, PLAIN)
        screen = await _flagged_screen(pilot, app)
        assert screen.crumb == ("Reconciliations", "Octubre BCP", "Flagged")
        head = _text(screen, "#fhead")
        assert head == (
            "Octubre BCP is completed. 2 lines dated up to its last day are in no statement.\n"
            "For each: if it belongs to this statement, revert, tick it, complete again.\n"
            "If it belongs to a later statement, leave it: tick it there when it comes.\n"
            "If it is a mistake, open it to fix it, or delete it."
        )
        drawn = [line.split() for line in render_text(screen._list._build()).split("\n")]
        drawn = [line for line in drawn if line and set(line[0]) != {"─"}]
        assert drawn[:3] == [
            ["Date", "Account", "Title", "Amount"],
            ["2026-09-25", "BCP", "PEN", "TAMBO", "MIRAFLORES", "-7.50"],
            ["2026-10-20", "BCP", "PEN", "UBER", "*TRIP", "-42.00"],
        ]
        assert _listed(screen) == ["l-tambo", "l-uber"]
        assert _footer(screen) == [
            "esc Back to the statement",
            "⏎ Open",
            "d Delete",
            "↑↓ Move",
        ]
        assert engine.reads == [_review("s1")]
        assert engine.counts == [{"unassigned_in_period_of": "s1"}]
        assert _by_id(fake_client) == []

    run_app(scenario)


def test_a_card_shows_every_accounts_lines_oldest_first(fake_client, monkeypatch):
    """Every account's lines of the card's statement in one read of its review list,
    listed oldest first as the engine orders them, each row naming its account."""
    _patch(monkeypatch)
    engine = Lines(monkeypatch, fake_client, TAMBO, UBER, SPOTIFY)
    _flags(fake_client, SOLES, ["l-tambo", "l-uber"], ["l-spotify"])

    async def scenario(pilot, app):
        await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        assert _listed(screen) == ["l-tambo", "l-uber", "l-spotify"]
        assert engine.reads == [_review("s-sig")]
        drawn = " ".join(render_text(screen._list._build(), width=100).split())
        assert "2026-10-24 Signature USD SPOTIFY P2F3 -5.99" in drawn
        assert "2026-09-25 Signature PEN TAMBO MIRAFLORES -7.50" in drawn
        assert "3 lines dated up to its last day are in no statement." in _text(screen, "#fhead")

    run_app(scenario)


def test_both_accounts_lines_merge_by_day_whichever_holds_them(fake_client, monkeypatch):
    _patch(monkeypatch)
    Lines(monkeypatch, fake_client, TAMBO, UBER, SPOTIFY)
    _flags(fake_client, SOLES, ["l-spotify"], ["l-tambo", "l-uber"])

    async def scenario(pilot, app):
        await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        assert _listed(screen) == ["l-tambo", "l-uber", "l-spotify"]

    run_app(scenario)


def test_one_line_reads_in_the_singular(fake_client, monkeypatch):
    _patch(monkeypatch)
    Lines(monkeypatch, fake_client, UBER)
    _flags(fake_client, SOLES, ["l-uber"], [])

    async def scenario(pilot, app):
        statement = await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        assert _text(screen, "#fhead").startswith(
            "Octubre 2026 is completed. 1 line dated up to its last day is in no statement."
        )
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is statement)
        assert _text(statement, "#rflag") == (
            "⚑ 1 line flagged for review: in no statement, dated up to this one's last day"
            "  · f shows them"
        )

    run_app(scenario)


# ---- ⏎ and d -----------------------------------------------------------------------


def test_enter_opens_the_line_in_the_ledgers_edit_form(fake_client, monkeypatch):
    """`⏎` opens the ledger's Edit form on the line, which reads it by its id; a
    save reads the review list again, `esc` reads nothing."""
    _patch(monkeypatch)
    engine = Lines(monkeypatch, fake_client, TAMBO, UBER)
    _flags(fake_client, SOLES, ["l-tambo", "l-uber"], [])

    async def scenario(pilot, app):
        await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        form = app.screen
        assert type(form) is EditFormScreen
        assert form._record["bank_line_id"] == "l-uber"
        assert form.crumb == ("Reconciliations", "Octubre 2026", "Flagged", "Edit")
        assert engine.reads == [_review("s-sig")]
        form.dismiss(None)
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert engine.reads == [_review("s-sig")]
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        app.screen.dismiss(True)
        await wait_for(pilot, lambda: engine.reads == [_review("s-sig")] * 2)

    run_app(scenario)


def test_d_asks_and_y_deletes_and_the_list_drops_the_line(fake_client, monkeypatch):
    """Deleted, the line is gone from the engine: the review list read again leaves
    it out, so it drops from the list, under the engine's new count."""
    _patch(monkeypatch)
    engine = Lines(monkeypatch, fake_client, TAMBO, UBER)
    _flags(fake_client, SOLES, ["l-tambo", "l-uber"], [])

    async def scenario(pilot, app):
        await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        modal = app.screen
        assert modal._title == "Delete this transaction?"
        assert "no screen can bring it back" in modal._message
        assert "TAMBO MIRAFLORES · -7.50" in modal._message
        del engine["l-tambo"]  # the engine has it no more
        await pilot.press("y")
        await wait_for(pilot, lambda: _listed(screen) == ["l-uber"])
        assert fake_client.deletes == ["/transactions/t-l-tambo"]
        assert engine.reads == [_review("s-sig")] * 2
        assert "1 line dated up to its last day is in no statement." in _text(screen, "#fhead")
        await pilot.press("r")
        await wait_for(pilot, lambda: len(engine.reads) == 3)
        assert engine.reads[-1] == _review("s-sig")
        assert _by_id(fake_client) == []

    run_app(scenario)


def test_a_split_line_goes_whole_after_the_question_naming_its_parts(fake_client, monkeypatch):
    _patch(monkeypatch)
    engine = Lines(monkeypatch, fake_client, FARMACIA, UBER)
    _flags(fake_client, SOLES, ["l-farmacia", "l-uber"], [])

    async def scenario(pilot, app):
        await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == "Delete this transaction and its 2 parts?"
        assert "No screen can bring it back." in app.screen._message
        del engine["l-farmacia"]
        await pilot.press("y")
        await wait_for(pilot, lambda: _listed(screen) == ["l-uber"])
        assert fake_client.deletes == ["/bank-lines/l-farmacia"]

    run_app(scenario)


@pytest.mark.parametrize("answer", ["n", "escape", "enter"])
def test_anything_but_y_keeps_the_line(fake_client, monkeypatch, answer):
    _patch(monkeypatch)
    Lines(monkeypatch, fake_client, TAMBO, UBER)
    _flags(fake_client, SOLES, ["l-tambo", "l-uber"], [])

    async def scenario(pilot, app):
        await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press(answer)
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert fake_client.deletes == []
        assert _listed(screen) == ["l-tambo", "l-uber"]

    run_app(scenario)


def test_the_last_line_gone_goes_back_to_the_statement_and_clears_it(fake_client, monkeypatch):
    _patch(monkeypatch)
    engine = Lines(monkeypatch, fake_client, UBER)
    _flags(fake_client, SOLES, ["l-uber"], [])

    async def scenario(pilot, app):
        statement = await _complete(pilot, app, SOLES)
        await _flagged_screen(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        del engine["l-uber"]
        await pilot.press("y")
        await wait_for(pilot, lambda: app.screen is statement)
        await pilot.pause()
        assert not statement.query_one("#rflag", Static).display
        assert "f Flagged" not in _footer(statement)

    run_app(scenario)


# ---- back on the statement --------------------------------------------------------


def test_esc_back_shows_the_warning_line_and_f_opens_the_list_again(fake_client, monkeypatch):
    _patch(monkeypatch)
    Lines(monkeypatch, fake_client, TAMBO, UBER, SPOTIFY)
    _flags(fake_client, SOLES, ["l-tambo", "l-uber"], ["l-spotify"])

    async def scenario(pilot, app):
        statement = await _complete(pilot, app, SOLES)
        await _flagged_screen(pilot, app)
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is statement)
        line = statement.query_one("#rflag", Static)
        assert line.display
        assert _text(statement, "#rflag") == (
            "⚑ 3 lines flagged for review: in no statement, dated up to this one's last day"
            "  · f shows them"
        )
        drawn = line.content
        assert drawn.spans[0].style == PALETTE.warning  # the count, in the warning colour
        assert drawn.spans[-1].style == "dim"  # `· f shows them`
        assert "f Flagged" in _footer(statement)
        _title, groups = screen_inventory(statement)
        assert any(row.keys == "f" for row in groups[0].rows)
        await pilot.press("f")
        screen = await _flagged_screen(pilot, app)
        assert _listed(screen) == ["l-tambo", "l-uber", "l-spotify"]

    run_app(scenario)


def test_revert_clears_the_line_and_f(fake_client, monkeypatch):
    _patch(monkeypatch)
    Lines(monkeypatch, fake_client, UBER)
    _flags(fake_client, SOLES, ["l-uber"], [])

    async def scenario(pilot, app):
        statement = await _complete(pilot, app, SOLES)
        await _flagged_screen(pilot, app)
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is statement)
        assert statement.query_one("#rflag", Static).display
        await pilot.press("u")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: not statement.query_one("#rflag", Static).display)
        assert "f Flagged" not in _footer(statement)
        _title, groups = screen_inventory(statement)
        assert not any(row.keys == "f" for row in groups[0].rows)
        await pilot.press("f")
        await pilot.pause()
        assert app.screen is statement

    run_app(scenario)


# ---- a read the engine refuses ------------------------------------------------------


def test_a_refused_read_shows_the_engines_words(fake_client, monkeypatch):
    """A read the engine refuses: the toast holds the engine's words as every read
    failure shows them (`format_error`), nothing is listed, and `r` reads again."""
    _patch(monkeypatch)
    refusal = EngineError("INTERNAL_ERROR", "Something went wrong on our side.", None, 500, {})
    engine = Lines(monkeypatch, fake_client, UBER, TAMBO)
    engine.refusal = refusal
    _flags(fake_client, SOLES, ["l-uber", "l-tambo"], [])
    notes: list = []
    monkeypatch.setattr(
        FlaggedLinesScreen,
        "notify",
        lambda self, message, **kw: notes.append((str(message), kw.get("severity"))),
    )

    async def scenario(pilot, app):
        await _complete(pilot, app, SOLES)
        await wait_for(pilot, lambda: isinstance(app.screen, FlaggedLinesScreen))
        screen = app.screen
        await wait_for(pilot, lambda: notes)
        assert notes == [(format_error(refusal), "error")]
        assert "Something went wrong on our side." in notes[0][0]
        assert screen._list is None
        engine.refusal = None
        await pilot.press("r")
        await wait_for(pilot, lambda: screen._list is not None)
        assert _listed(screen) == ["l-tambo", "l-uber"]

    run_app(scenario)


def test_a_refused_read_again_keeps_what_is_listed(fake_client, monkeypatch):
    """Listed, then a read the engine refuses: its words as a toast, the rows as
    they were, the cursor where it was."""
    _patch(monkeypatch)
    refusal = EngineError("INTERNAL_ERROR", "Something went wrong on our side.", None, 500, {})
    engine = Lines(monkeypatch, fake_client, TAMBO, UBER)
    _flags(fake_client, SOLES, ["l-tambo", "l-uber"], [])
    notes: list = []
    monkeypatch.setattr(
        FlaggedLinesScreen,
        "notify",
        lambda self, message, **kw: notes.append((str(message), kw.get("severity"))),
    )

    async def scenario(pilot, app):
        await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        await pilot.press("down")
        engine.refusal = refusal
        await pilot.press("r")
        await wait_for(pilot, lambda: notes)
        assert notes == [(format_error(refusal), "error")]
        assert app.screen is screen
        assert _listed(screen) == ["l-tambo", "l-uber"]
        assert screen._list.cursor_key == "l-uber"

    run_app(scenario)


# ---- the engine's count, and more than one page --------------------------------------


def test_the_count_shown_is_the_engines_count(fake_client, monkeypatch):
    """The head and the statement's `⚑` line say what `GET /bank-lines/count` answers
    on the review list, not how many rows came back (contract: GET /v1/bank-lines/count)."""
    _patch(monkeypatch)
    engine = Lines(monkeypatch, fake_client, TAMBO, UBER)
    engine.count = 7
    _flags(fake_client, SOLES, ["l-tambo", "l-uber"], [])

    async def scenario(pilot, app):
        statement = await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        assert _listed(screen) == ["l-tambo", "l-uber"]
        assert "7 lines dated up to its last day are in no statement." in _text(screen, "#fhead")
        assert engine.counts == [{"unassigned_in_period_of": "s-sig"}]
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is statement)
        assert _text(statement, "#rflag").startswith("⚑ 7 lines flagged for review")

    run_app(scenario)


def test_more_than_one_page_is_read_whole_in_the_statements_order(fake_client, monkeypatch):
    """A close flags 250 lines: the review list is paged by its cursor, 200 lines then
    the 50 after them, no id sent, and the rows are every page in turn, in the
    statement's order (contract: GET /v1/bank-lines, "It has no bound")."""
    _patch(monkeypatch)
    days = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(250)]
    many = [
        _line(f"l-{i:03d}", -100, day, f"LINE {i}", account="acc1") for i, day in enumerate(days)
    ]
    # The close names them newest first; the engine lists them oldest first.
    close = [line["id"] for line in reversed(many)]
    engine = Lines(monkeypatch, fake_client, *many)
    _flags(fake_client, PLAIN, close)

    async def scenario(pilot, app):
        await _complete(pilot, app, PLAIN)
        screen = await _flagged_screen(pilot, app)
        assert engine.reads == [_review("s1"), _review("s1", after="c200")]
        assert all("ids" not in read for read in engine.reads)
        assert _listed(screen) == [line["id"] for line in many]
        assert _by_id(fake_client) == []
        assert "250 lines dated up to its last day are in no statement." in _text(screen, "#fhead")

    run_app(scenario)
