"""The lines a statement's close flagged for review (pick 1A of
docs/mockups/expense-world-statement-flagged-lines.html).

A complete goes through with lines left in no statement and names them by id, the
half's own `review_lines` and its twin's
(contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response"). The
app pushes a screen of its own on them, read by their ids in one list read, oldest
first, 200 ids at most each (contract: GET /v1/bank-lines, "At most 200 ids"), and
the statement keeps a `⚑` line and `f` until its next status change."""

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
)
from expense.tui.theme import PALETTE
from tests.unit.helpers import (
    NO_STATEMENT,
    ORDERED_ALONE,
    bank_line_row,
    complete_answer,
    cursor_page,
    import_part,
    render_text,
    run_app,
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

#: The soles half of Octubre 2026, a draft with its ending balance, and its twin.
SOLES = {
    "id": "r-pen",
    "account_id": "sig-pen",
    "name": "Octubre 2026",
    "date_start": "2026-09-26",
    "date_end": "2026-10-25",
    "beginning_balance_cents": 0,
    "ending_balance_cents": -4490,
    "difference_cents": 0,
    "status": 1,
    **ORDERED_ALONE,
    "twin_id": "r-usd",
}
#: A reconciliation on an account with no statement code: no twin.
PLAIN = {**SOLES, "id": "r1", "account_id": "acc1", "name": "Octubre BCP", **NO_STATEMENT}


class Lines(dict):
    """The engine's live bank lines by id, answering the fake client's GETs as the
    engine does (contract: GET /v1/bank-lines, "Filters"):

    - `GET /bank-lines?ids=…`: the live lines among the ids, in the `sort` asked
      for (`date_asc` oldest first, else newest first), never in the ids' order,
      at most `limit` of them (50 when none is sent); an id naming no live line
      is left out; more than 200 ids is a `422` on `ids`. Each read's query is
      kept in `reads`; `refusal`, when set, is raised instead.
    - `GET /bank-lines` with no `ids`: the statement's own reads, no line.
    - `GET /bank-lines/{id}`: the line, as the Edit form reads it, or a `404`.

    Every read in `expense.reads` goes to the fake client. A line deleted is one
    taken out. Any other GET goes to the fake client's own answers."""

    def __init__(self, monkeypatch, fake_client, *lines: dict) -> None:
        super().__init__((line["id"], line) for line in lines)
        self.reads: list[dict] = []
        self.refusal: Exception | None = None
        self._client = fake_client
        self._get = fake_client.get
        monkeypatch.setattr(fake_client, "get", self._serve)
        monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)

    def _serve(self, path: str, *, auth: bool = True, params: dict | None = None):
        if path == "/bank-lines" and params and "ids" in params:
            self._client.calls.append(("GET", path, params))
            self.reads.append(dict(params))
            if self.refusal is not None:
                raise self.refusal
            ids = params["ids"].split(",")
            if len(ids) > 200:
                raise EngineError(
                    "VALIDATION_ERROR", "Invalid request.", {"ids": "At most 200."}, 422, {}
                )
            live = [self[line_id] for line_id in dict.fromkeys(ids) if line_id in self]
            live.sort(
                key=lambda line: (bank_line_columns(line)[0], line["id"]),
                reverse=params.get("sort") != "date_asc",
            )
            limit = params.get("limit", 50)
            return cursor_page(live[:limit], limit=limit)
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

    def ids_read(self) -> list[str]:
        """The ids each read sent, comma-joined, in the order they were read."""
        return [read["ids"] for read in self.reads]


def _by_id(fake_client) -> list[str]:
    """Every `GET /bank-lines/{id}` the app sent."""
    return [path for verb, path, _ in fake_client.calls if verb == "GET" and path.count("/") > 1]


def _patch(monkeypatch) -> None:
    """The accounts' names the screens show."""
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map", lambda: dict(NAMES)
    )


def _flags(fake_client, record: dict, own: list[str], twin: list[str] | None = None) -> None:
    """The complete's answer: the named half's `review_lines`, and the twin's when
    the statement has one."""
    other = None if twin is None else {"id": "r-usd", "account_id": "sig-usd", "review_lines": twin}
    fake_client.write_responses[f"/reconciliations/{record['id']}/complete"] = complete_answer(
        {**record, "status": 2}, review_lines=own, twin=other
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
    """No twin: the lines come from the named half alone, in one list read by
    their ids, oldest first, with a `limit` covering them, and no line read by its
    id; the rows in the engine's order, not the close's; the screen's words, its
    columns and its footer as pane 1A draws them."""
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
        assert engine.reads == [{"ids": "l-uber,l-tambo", "sort": "date_asc", "limit": 2}]
        assert _by_id(fake_client) == []

    run_app(scenario)


def test_a_card_shows_both_halves_lines_oldest_first(fake_client, monkeypatch):
    """The named half's `review_lines`, then the twin's, in one read, listed oldest
    first as the engine orders them, each row naming its account."""
    _patch(monkeypatch)
    engine = Lines(monkeypatch, fake_client, TAMBO, UBER, SPOTIFY)
    _flags(fake_client, SOLES, ["l-tambo", "l-uber"], ["l-spotify"])

    async def scenario(pilot, app):
        await _complete(pilot, app, SOLES)
        screen = await _flagged_screen(pilot, app)
        assert _listed(screen) == ["l-tambo", "l-uber", "l-spotify"]
        assert engine.ids_read() == ["l-tambo,l-uber,l-spotify"]
        drawn = " ".join(render_text(screen._list._build(), width=100).split())
        assert "2026-10-24 Signature USD SPOTIFY P2F3 -5.99" in drawn
        assert "2026-09-25 Signature PEN TAMBO MIRAFLORES -7.50" in drawn
        assert "3 lines dated up to its last day are in no statement." in _text(screen, "#fhead")

    run_app(scenario)


def test_the_twins_lines_merge_by_day_whichever_half_is_named(fake_client, monkeypatch):
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
    save reads the flagged lines again, by their ids, `esc` reads nothing."""
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
        assert engine.ids_read() == ["l-tambo,l-uber"]
        form.dismiss(None)
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert engine.ids_read() == ["l-tambo,l-uber"]
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        app.screen.dismiss(True)
        await wait_for(pilot, lambda: engine.ids_read() == ["l-tambo,l-uber"] * 2)
        assert engine.reads[-1] == {"ids": "l-tambo,l-uber", "sort": "date_asc", "limit": 2}

    run_app(scenario)


def test_d_asks_and_y_deletes_and_the_list_drops_the_line(fake_client, monkeypatch):
    """Deleted, the line is gone from the engine: the same ids read again leave it
    out, so it drops from the list, and the next read sends only the line left."""
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
        assert engine.ids_read() == ["l-tambo,l-uber", "l-tambo,l-uber"]
        assert "1 line dated up to its last day is in no statement." in _text(screen, "#fhead")
        await pilot.press("r")
        await wait_for(pilot, lambda: len(engine.reads) == 3)
        assert engine.reads[-1] == {"ids": "l-uber", "sort": "date_asc", "limit": 1}
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


# ---- more than 200 lines --------------------------------------------------------------


def test_more_than_200_ids_are_read_200_at_a_time_in_the_closes_order(fake_client, monkeypatch):
    """A close names 250 lines: two reads, its first 200 ids then the last 50, each
    with a `limit` of its own ids; the rows are each read's answer in turn, oldest
    first within each read only (contract: GET /v1/bank-lines, "At most 200 ids")."""
    _patch(monkeypatch)
    days = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(250)]
    many = [
        _line(f"l-{i:03d}", -100, day, f"LINE {i}", account="acc1") for i, day in enumerate(days)
    ]
    # The close names the newest 200 first, newest first, then the oldest 50.
    close = [line["id"] for line in reversed(many)]
    engine = Lines(monkeypatch, fake_client, *many)
    _flags(fake_client, PLAIN, close)

    async def scenario(pilot, app):
        await _complete(pilot, app, PLAIN)
        screen = await _flagged_screen(pilot, app)
        assert engine.reads == [
            {"ids": ",".join(close[:200]), "sort": "date_asc", "limit": 200},
            {"ids": ",".join(close[200:]), "sort": "date_asc", "limit": 50},
        ]
        assert _listed(screen) == sorted(close[:200]) + sorted(close[200:])
        assert _by_id(fake_client) == []
        assert "250 lines dated up to its last day are in no statement." in _text(screen, "#fhead")

    run_app(scenario)
