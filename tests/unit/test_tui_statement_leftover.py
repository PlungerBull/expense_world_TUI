"""The leftover lines of a close — `c` on a statement closed by hand, refused while bank lines
sit in no statement on days it seals.

The engine refuses the complete `422` on `statement_id`, naming the lines by id in
`error.details` (contract: POST /v1/statements/{statement_id}/complete, "Validation"). The
statement's screen opens a screen of the lines over itself: `space` puts a line in the
statement, `⏎` and `d` edit and delete it, `c` goes back and asks "Complete statement?"
again. The lines are read by their ids; only those the read gives no statement are listed."""

import copy
import threading

import pytest
from textual.widgets import Static

from expense.bank_import.statement import loose_lines
from expense.errors import EngineError
from expense.tui.screens.edit_form import EditFormScreen
from expense.tui.screens.leftover_lines import StatementLeftoverScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.statements import StatementScreen
from tests.unit.helpers import (
    app_notes,
    bank_line_row,
    cursor_page,
    import_part,
    render_text,
    run_app,
    screen_lines,
    statement_complete_answer,
    statement_record,
    stub_home_month,
    toasts_shown,
    wait_for,
)

MARCH = statement_record(
    {
        "id": "s-mar",
        "account_id": "acc-1",
        "name": "Marzo 2026",
        "date_start": "2026-03-01",
        "date_end": "2026-03-31",
        "status": 1,
        "balances": [
            {
                "currency_code": "PEN",
                "beginning_balance_cents": 0,
                "ending_balance_cents": -3333,
                "difference_cents": 0,
            }
        ],
    }
)


def _line(n: str, cents: int, day: str, title: str) -> dict:
    part = import_part(f"t-{n}", cents, account_id="acc-1", line=f"l-{n}", day=day, title=title)
    return bank_line_row(f"l-{n}", [part], net_cents=cents, account_id="acc-1")


TAXI = _line("taxi", -2222, "2026-02-28", "Taxi")
ALMUERZO = _line("almuerzo", -1111, "2026-03-15", "Almuerzo")
CINE = _line("cine", -3000, "2026-03-20", "Cine")


def refusal(ids: list[str], count: int | None = None) -> EngineError:
    """The engine's `422` on `statement_id` for lines in no statement."""
    return EngineError(
        "VALIDATION_ERROR",
        "Cannot complete the statement.",
        {"statement_id": "Lines in no statement sit on days it seals."},
        422,
        {},
        {"statement_id": "LOOSE_LINES_ON_SEALED_DAYS"},
        {"bank_line_ids": ids, "count": len(ids) if count is None else count},
    )


class Engine:
    """The statement and its lines as the screens read them: `held` the live lines by id
    (a line put in the statement carries its id, one deleted is gone), `refusals` the
    completes' answers in turn (an error refuses, the last one repeats; None goes
    through), `by_ids` every read of the lines by id."""

    def __init__(self, monkeypatch, fake_client, *lines: dict) -> None:
        self.held = {line["id"]: copy.deepcopy(line) for line in lines}
        self.refusals: list[Exception | None] = []
        self.by_ids: list[list[str]] = []
        self.client = fake_client
        self.hold: threading.Event | None = None
        monkeypatch.setattr("expense.reads.fetch_bank_lines_by_ids", self._read)
        monkeypatch.setattr("expense.reads.ExpenseClient", lambda *a, **k: fake_client)
        monkeypatch.setattr(
            "expense.tui.screens.statements.load_account_name_map",
            lambda: {"acc-1": "BCP-9012"},
        )
        stub_home_month(monkeypatch)
        fake_client.get = self._get
        fake_client.post = self._post
        fake_client.put = self._put
        fake_client.write_responses["/statements/s-mar/complete"] = statement_complete_answer(
            {**MARCH, "status": 2}
        )

    def _get(self, path, *, auth=True, params=None):
        if path.startswith("/statements/"):
            return dict(MARCH)
        if path == "/bank-lines/count":
            return {"count": 0}
        assert path == "/bank-lines", path
        return cursor_page([])

    def _read(self, cfg, ids, **kwargs):
        self.by_ids.append(list(ids))
        # the engine's own order, newest first: never the order of the ids
        found = [self.held[i] for i in ids if i in self.held]
        return sorted(found, key=lambda line: line["parts"][0]["date"], reverse=True)

    def _post(self, path, json_body=None):
        self.client.calls.append(("POST", path, json_body))
        if path.endswith("/complete"):
            step = self.refusals.pop(0) if len(self.refusals) > 1 else self.refusals[0]
            if step is not None:
                raise step
        return self.client.write_responses.get(path, {})

    def _put(self, path, json_body=None):
        self.client.calls.append(("PUT", path, json_body))
        if self.hold is not None:
            self.hold.wait(timeout=10)
        err = self.client.errors.get("PUT")
        if err is not None:
            raise err
        for line in self.held.values():
            for part in line["parts"]:
                if f"/transactions/{part['id']}" == path:
                    part["statement_id"] = json_body["statement_id"]
        return {}

    def completes(self) -> int:
        return len([1 for _, path, _ in self.client.calls if path.endswith("/complete")])


def _head(screen) -> list[str]:
    text = render_text(screen.query_one("#import-body", Static).content, width=80)
    return [line.strip() for line in text.split("\n") if line.strip()]


def _footer(screen) -> list[str]:
    return [
        f"{screen.app.get_key_display(a.binding)} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


def _listed(screen) -> list:
    return [row.key for row in screen._list._rows]


async def _refused_close(pilot, app) -> tuple[StatementScreen, StatementLeftoverScreen]:
    """The statement's screen, `c` and `y`, and the leftover lines' screen that answers."""
    checklist = StatementScreen(dict(MARCH))
    await app.push_screen(checklist)
    await wait_for(pilot, lambda: checklist._list is not None)
    await pilot.press("c")
    await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
    await pilot.press("y")
    return checklist, await _leftover(pilot, app)


async def _leftover(pilot, app, other=None) -> StatementLeftoverScreen:
    await wait_for(
        pilot,
        lambda: isinstance(app.screen, StatementLeftoverScreen) and app.screen is not other,
        message="no leftover screen",
    )
    screen = app.screen
    await wait_for(pilot, lambda: screen._lines is not None, message="lines never read")
    return screen


def test_a_refused_close_lists_its_lines_and_closes_once_they_are_dealt_with(
    fake_client, monkeypatch
):
    """`c` refused for two lines: the screen names the statement and the account, lists the
    lines in the refusal's order, `space` puts one in the statement and it leaves the list,
    `d` deletes the other; with none left `c` goes back and the question closes March."""
    engine = Engine(monkeypatch, fake_client, TAXI, ALMUERZO)
    engine.refusals = [refusal(["l-taxi", "l-almuerzo"]), None]

    async def scenario(pilot, app):
        checklist, screen = await _refused_close(pilot, app)
        assert engine.by_ids == [["l-taxi", "l-almuerzo"]]
        assert screen.crumb() == ("Statements", "Marzo 2026", "Leftover")
        assert _listed(screen) == ["l-taxi", "l-almuerzo"]  # the refusal's order, not the read's
        assert _head(screen) == [
            "Can't close Marzo 2026 yet · BCP-9012",
            "2 lines in no statement sit on its days.",
            "Nothing was written.",
        ]
        assert _footer(screen) == [
            "esc Back",
            "space Put in Marzo 2026",
            "⏎ Edit",
            "d Delete",
            "c Close",
        ]
        await wait_for(pilot, lambda: "Marzo 2026 again." in " ".join(screen_lines(app)))
        text = " ".join(screen_lines(app))
        assert "For each one: space puts it in Marzo 2026" in text

        await pilot.press("space")  # Taxi, the first
        await wait_for(pilot, lambda: _listed(screen) == ["l-almuerzo"])
        assert ("PUT", "/transactions/t-taxi", {"statement_id": "s-mar"}) in fake_client.calls
        assert _head(screen)[1] == "1 line in no statement sits on its days."
        assert _head(screen)[-1] == "Nothing was written."

        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        del engine.held["l-almuerzo"]
        await pilot.press("y")
        await wait_for(pilot, lambda: _listed(screen) == [])
        assert "Nothing is left over: c closes Marzo 2026." in " ".join(screen_lines(app))
        assert _footer(screen) == ["esc Back", "c Close"]
        assert _head(screen) == ["Can't close Marzo 2026 yet · BCP-9012", "Nothing was written."]

        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert app.screen._title == "Complete statement?"
        await pilot.press("y")
        await wait_for(pilot, lambda: checklist._record["status"] == 2)
        assert app.screen is checklist
        assert engine.completes() == 2

    run_app(scenario, size=(80, 24))


def test_only_lines_the_read_gives_no_statement_are_listed(fake_client, monkeypatch):
    """A line the engine already puts in a statement is not a leftover: it is not listed,
    whatever the refusal named."""
    engine = Engine(monkeypatch, fake_client, TAXI, ALMUERZO)
    engine.held["l-taxi"]["parts"][0]["statement_id"] = "s-mar"
    engine.refusals = [refusal(["l-taxi", "l-almuerzo"])]

    async def scenario(pilot, app):
        _checklist, screen = await _refused_close(pilot, app)
        assert _listed(screen) == ["l-almuerzo"]
        assert _head(screen)[1] == "1 line in no statement sits on its days."

    run_app(scenario)


def test_a_line_fixed_in_the_edit_form_stays_listed_and_nothing_is_sent(fake_client, monkeypatch):
    """No dry run exists for a close: a save reads the lines by id and the line, still in no
    statement, stays; only `c` asks the engine."""
    engine = Engine(monkeypatch, fake_client, TAXI, ALMUERZO)
    engine.refusals = [refusal(["l-taxi", "l-almuerzo"])]

    async def scenario(pilot, app):
        _checklist, screen = await _refused_close(pilot, app)
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        form = app.screen
        assert form._record["bank_line_id"] == "l-taxi"
        assert form.crumb == ("Statements", "Marzo 2026", "Leftover", "Edit")
        form.dismiss(True)
        await wait_for(pilot, lambda: len(engine.by_ids) == 2)
        await wait_for(pilot, lambda: app.screen is screen)
        assert _listed(screen) == ["l-taxi", "l-almuerzo"]
        assert engine.completes() == 1

    run_app(scenario)


def test_c_refused_again_shows_the_screen_with_the_new_lines(fake_client, monkeypatch):
    engine = Engine(monkeypatch, fake_client, TAXI, ALMUERZO, CINE)
    engine.refusals = [refusal(["l-taxi"]), refusal(["l-cine"])]

    async def scenario(pilot, app):
        checklist, first = await _refused_close(pilot, app)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        second = await _leftover(pilot, app, other=first)
        assert second is not first
        assert _listed(second) == ["l-cine"]
        assert engine.completes() == 2
        assert checklist._record["status"] == 1  # still a draft

    run_app(scenario)


def test_esc_goes_back_to_the_checklist_and_asks_nothing(fake_client, monkeypatch):
    engine = Engine(monkeypatch, fake_client, TAXI)
    engine.refusals = [refusal(["l-taxi"])]

    async def scenario(pilot, app):
        checklist, _screen = await _refused_close(pilot, app)
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is checklist)
        await pilot.pause()
        assert app.screen is checklist and engine.completes() == 1

    run_app(scenario)


def test_a_refusal_naming_more_lines_than_it_lists_keeps_the_engines_count(
    fake_client, monkeypatch
):
    engine = Engine(monkeypatch, fake_client, TAXI, ALMUERZO)
    engine.refusals = [refusal(["l-taxi", "l-almuerzo"], count=201)]

    async def scenario(pilot, app):
        _checklist, screen = await _refused_close(pilot, app)
        assert _head(screen) == [
            "Can't close Marzo 2026 yet · BCP-9012",
            "201 lines in no statement sit on its days.",
            "The first 2 are listed; c closes Marzo 2026 again for the rest.",
            "Nothing was written.",
        ]

    run_app(scenario)


def _conflict() -> EngineError:
    return EngineError(
        "CONFLICT",
        "Another request changed it.",
        None,
        409,
        {},
        {"statement_id": "CONCURRENT_CHANGE"},
    )


@pytest.mark.parametrize("verb", ["PUT", "DELETE"])
def test_a_write_met_by_a_change_says_try_again_without_an_r_and_reads_again(
    fake_client, monkeypatch, verb
):
    """The screen reads itself again after a write and has no `r`: the line for a change
    at the same moment says only to try again. `space` and `d` go different ways."""
    engine = Engine(monkeypatch, fake_client, TAXI, ALMUERZO)
    engine.refusals = [refusal(["l-taxi", "l-almuerzo"])]
    fake_client.errors[verb] = _conflict()

    async def scenario(pilot, app):
        _checklist, screen = await _refused_close(pilot, app)
        assert "r" not in screen.active_bindings
        if verb == "PUT":
            await pilot.press("space")
        else:
            await pilot.press("d")
            await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
            await pilot.press("y")
        await wait_for(pilot, lambda: len(engine.by_ids) == 2)
        await wait_for(pilot, lambda: bool(toasts_shown(app)))
        shown = toasts_shown(app)[0]
        assert "It changed at the same moment: try again." in shown
        assert "press r" not in shown
        assert _listed(screen) == ["l-taxi", "l-almuerzo"]

    run_app(scenario, toasts=True)


def test_c_waits_for_a_space_still_being_sent_and_that_space_names_the_statement_if_refused_later(
    fake_client, monkeypatch
):
    engine = Engine(monkeypatch, fake_client, TAXI, ALMUERZO)
    engine.refusals = [refusal(["l-taxi", "l-almuerzo"])]
    engine.hold = threading.Event()

    async def scenario(pilot, app):
        notes = app_notes(monkeypatch, app)
        _checklist, screen = await _refused_close(pilot, app)
        await pilot.press("space")
        await wait_for(pilot, lambda: bool(screen.saves_pending()))
        assert screen.saves_pending()[0].left_behind.first_line.startswith("Not put in Marzo 2026")
        await pilot.press("c")
        await pilot.pause()
        assert app.screen is screen
        assert "Writing — one moment." in [message for _, message, _ in notes]
        engine.hold.set()

    run_app(scenario)


def test_a_close_is_read_by_the_reason_on_statement_id_and_never_by_the_words():
    err = refusal(["l-taxi"], count=3)
    assert loose_lines(err, on="statement_id") is not None
    assert loose_lines(err, on="statement_id").count == 3
    assert loose_lines(err) is None  # an upload's reason is on `file`


def test_a_close_refused_for_anything_else_is_shown_on_the_checklist_the_shared_way(
    fake_client, monkeypatch
):
    engine = Engine(monkeypatch, fake_client, TAXI)
    engine.refusals = [
        EngineError(
            "VALIDATION_ERROR",
            "The statement cannot be completed.",
            {"statement_id": "Order every line first."},
            422,
            {},
            {"statement_id": "STATEMENT_NOT_ORDERED"},
        )
    ]

    async def scenario(pilot, app):
        checklist = StatementScreen(dict(MARCH))
        await app.push_screen(checklist)
        await wait_for(pilot, lambda: checklist._list is not None)
        await pilot.press("c")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        note = checklist.query_one("#rnote", Static)
        await wait_for(pilot, lambda: note.display, message="no refusal shown")
        assert app.screen is checklist
        assert "Order every line first." in render_text(note.content, width=80)

    run_app(scenario)
