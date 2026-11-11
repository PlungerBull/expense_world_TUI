"""The leftover lines — a statement PDF's upload refused for lines in no statement.

The engine refuses the dry run and the apply while a bank line in no statement sits on a day
the close seals, naming the lines by id in `error.details`
(contract: POST /v1/statements/import, "Response"). The preview opens a screen in its place;
it reads the lines by their ids, and `⏎`, `d` and `r` deal with them. The screens are pushed
on the app directly, the owner of the run a stub that records how the run ended."""

import threading
from pathlib import Path

import pytest
from textual.widgets import Static

from expense.bank_import.flow import AccountPick
from expense.bank_import.statement import loose_lines
from expense.errors import EngineError, format_error
from expense.tui.screens.bank_import import DroppedFile, ImportRun
from expense.tui.screens.edit_form import EditFormScreen
from expense.tui.screens.leftover_lines import LeftoverLinesScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.statement_upload import StatementPreviewScreen
from tests.unit.helpers import (
    bank_line_row,
    import_part,
    render_text,
    run_app,
    screen_lines,
    statement_upload_answer,
    toasts_shown,
    wait_for,
)

PICK = AccountPick("BCP-5678", "acc-1", ("PEN", "USD"))
#: The lines the engine holds in no statement, by id.
AMAZON = bank_line_row(
    "l-amazon",
    [import_part("t-amazon", -1999, line="l-amazon", day="2026-03-12", title="Amazon")],
    net_cents=-1999,
    currency_code="USD",
)
ALMUERZO = bank_line_row(
    "l-almuerzo",
    [import_part("t-almuerzo", -1111, line="l-almuerzo", day="2026-03-15", title="Almuerzo")],
    net_cents=-1111,
)
TAXI = bank_line_row(
    "l-taxi",
    [import_part("t-taxi", -2222, line="l-taxi", day="2026-03-18", title="Taxi")],
    net_cents=-2222,
)


def refusal(ids: list[str], count: int | None = None) -> EngineError:
    """The engine's `422` on `file` for lines in no statement, as the contract states it."""
    words = "Cannot close the statement: lines in no statement sit on days it seals."
    return EngineError(
        "VALIDATION_ERROR",
        "The statement cannot be closed.",
        {"file": words},
        422,
        {},
        {"file": "LOOSE_LINES_ON_SEALED_DAYS"},
        {"bank_line_ids": ids, "count": len(ids) if count is None else count},
    )


class Owner:
    """The LOG bar's side of the run: told how the run ended."""

    def __init__(self) -> None:
        self.closed: list[bool] = []

    def import_closed(self, run, *, home: bool) -> None:
        self.closed.append(home)


class Engine:
    """The ledger and the upload as the screens meet them: `held` the live lines by id (one
    taken out is deleted), `refusals` the dry runs' answers in turn (an error refuses, the
    last one repeats), `by_ids` every read of the lines by id."""

    def __init__(self, monkeypatch, fake_client, *lines: dict) -> None:
        self.held = {line["id"]: line for line in lines}
        self.refusals: list[Exception | None] = []
        self.by_ids: list[tuple[list[str], dict]] = []
        self.uploads: list[bool] = []
        self.read_refusal: Exception | None = None
        monkeypatch.setattr("expense.reads.fetch_bank_lines_by_ids", self._read)
        self._client = fake_client
        fake_client.post = self._post

    def _read(self, cfg, ids, **kwargs):
        self.by_ids.append((list(ids), kwargs))
        if self.read_refusal is not None:
            raise self.read_refusal
        found = [self.held[i] for i in ids if i in self.held]
        # the engine's own order, newest first: never the order of the ids
        return sorted(found, key=lambda line: line["parts"][0]["date"], reverse=True)

    def _post(self, path, json_body=None):
        self._client.calls.append(("POST", path, json_body))
        self.uploads.append(json_body["dry_run"])
        step = self.refusals.pop(0) if len(self.refusals) > 1 else self.refusals[0]
        if step is not None:
            raise step
        return statement_upload_answer([], dry_run=json_body["dry_run"], name="BCP-202603")


async def _preview(pilot, app, owner: Owner) -> StatementPreviewScreen:
    run = ImportRun([DroppedFile(Path("EECC_2026-03.pdf"), b"%PDF")])
    preview = StatementPreviewScreen(run, owner, PICK)
    await app.push_screen(preview)
    return preview


async def _leftover(pilot, app) -> LeftoverLinesScreen:
    await wait_for(pilot, lambda: isinstance(app.screen, LeftoverLinesScreen))
    screen = app.screen
    await wait_for(pilot, lambda: screen._lines is not None, message="lines never read")
    return screen


def _listed(screen) -> list:
    return [row.key for row in screen._list._rows]


def _head(screen) -> list[str]:
    return [
        line.strip()
        for line in render_text(screen.query_one("#import-body", Static).content, width=80).split(
            "\n"
        )
        if line.strip()
    ]


def _footer(screen) -> list[str]:
    return [
        f"{screen.app.get_key_display(a.binding)} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


@pytest.fixture
def owner():
    return Owner()


def test_a_refused_upload_reads_its_lines_and_mends_to_the_preview(fake_client, monkeypatch, owner):
    """The dry run refused for two lines: the screen draws its crumb, head, the lines in the
    refusal's order (the read answers newest first), the ways and the footer at 80 columns,
    reading them once by their ids. A line deleted leaves the list; `r` sends the same PDF
    again and, nothing left over, the usual preview opens."""
    engine = Engine(monkeypatch, fake_client, AMAZON, ALMUERZO)
    engine.refusals = [refusal(["l-amazon", "l-almuerzo"]), None]

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        screen = await _leftover(pilot, app)
        assert engine.by_ids == [(["l-amazon", "l-almuerzo"], {"verbose": False})]
        assert _listed(screen) == ["l-amazon", "l-almuerzo"]
        assert screen.crumb() == ("Upload", "EECC_2026-03.pdf", "Leftover")
        assert _head(screen) == [
            "Can't close the statement yet · BCP-5678",
            "2 lines in no statement sit on its days.",
            "Nothing was written.",
        ]
        assert _footer(screen) == ["esc Cancel", "⏎ Edit", "d Delete", "r Read again"]
        text = "\n".join(screen_lines(app))
        for shown in ("2026-03-12", "Amazon", "-19.99", "USD", "2026-03-15", "Almuerzo", "-11.11"):
            assert shown in text
        assert text.index("Amazon") < text.index("Almuerzo")
        assert "For each one:" in text and "Then r reads the paper again." in text
        assert engine.uploads == [True]

        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        assert "no screen can bring it back" in app.screen._message.lower()
        del engine.held["l-amazon"]
        await pilot.press("y")
        await wait_for(pilot, lambda: _listed(screen) == ["l-almuerzo"])
        assert fake_client.deletes == ["/transactions/t-amazon"]
        assert _head(screen)[1] == "1 line in no statement sits on its days."

        await pilot.press("r")
        await wait_for(pilot, lambda: isinstance(app.screen, StatementPreviewScreen))
        await wait_for(pilot, lambda: app.screen._answer is not None, message="no preview")
        assert engine.uploads == [True, True]  # two dry runs, nothing applied

    run_app(scenario)


def test_a_line_deleted_meanwhile_is_absent_and_the_cursor_returns_to_row_1(
    fake_client, monkeypatch, owner
):
    engine = Engine(monkeypatch, fake_client, AMAZON, ALMUERZO, TAXI)
    engine.refusals = [refusal(["l-amazon", "l-almuerzo", "l-taxi"])]
    del engine.held["l-almuerzo"]  # gone before the screen reads

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        screen = await _leftover(pilot, app)
        assert _listed(screen) == ["l-amazon", "l-taxi"]
        assert _head(screen)[1] == "2 lines in no statement sit on its days."
        await pilot.press("down")
        assert screen._list.cursor_key == "l-taxi"
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        del engine.held["l-taxi"]
        await pilot.press("y")
        await wait_for(pilot, lambda: _listed(screen) == ["l-amazon"])
        assert screen._list.cursor_key == "l-amazon"

    run_app(scenario)


def test_a_refusal_naming_more_lines_than_it_lists_says_so_in_the_head(
    fake_client, monkeypatch, owner
):
    """`count` above the ids named: the head gives the engine's count, says how many are
    listed and that `r` reads the paper again for the rest."""
    engine = Engine(monkeypatch, fake_client, AMAZON, ALMUERZO)
    engine.refusals = [refusal(["l-amazon", "l-almuerzo"], count=201)]

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        screen = await _leftover(pilot, app)
        assert _head(screen) == [
            "Can't close the statement yet · BCP-5678",
            "201 lines in no statement sit on its days.",
            "The first 2 are listed; r reads the paper again for the rest.",
            "Nothing was written.",
        ]
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        del engine.held["l-amazon"]
        await pilot.press("y")
        await wait_for(pilot, lambda: _listed(screen) == ["l-almuerzo"])
        assert _head(screen)[1] == "201 lines in no statement sit on its days."

    run_app(scenario)


def test_a_long_list_pages_above_the_ways_and_the_footer_at_80x24(fake_client, monkeypatch, owner):
    many = [
        bank_line_row(
            f"l-{n:02}",
            [import_part(f"t-{n:02}", -100 * n, line=f"l-{n:02}", day=f"2026-03-{n:02}")],
            net_cents=-100 * n,
        )
        for n in range(1, 31)
    ]
    engine = Engine(monkeypatch, fake_client, *many)
    engine.refusals = [refusal([line["id"] for line in many])]

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        screen = await _leftover(pilot, app)
        await pilot.pause()
        shown = screen_lines(app)
        assert "  Then r reads the paper again." in shown
        assert "esc Cancel" in shown[-1]
        assert any(line.strip().startswith("rows 1-") for line in shown)
        assert screen._list.row_count == 30
        await pilot.press("pagedown")
        assert screen._list.cursor_index > 1

    run_app(scenario)


def test_the_apply_refused_for_lines_opens_the_screen_too(fake_client, monkeypatch, owner):
    engine = Engine(monkeypatch, fake_client, AMAZON)
    engine.refusals = [None, refusal(["l-amazon"])]

    async def scenario(pilot, app):
        preview = await _preview(pilot, app, owner)
        await wait_for(pilot, lambda: preview._answer is not None, message="no preview")
        await pilot.press("enter")
        screen = await _leftover(pilot, app)
        assert engine.uploads == [True, False]
        assert _listed(screen) == ["l-amazon"]
        assert not screen._run.imported  # nothing was written

    run_app(scenario)


def test_enter_opens_the_ledgers_edit_form_and_a_save_sends_the_paper_again(
    fake_client, monkeypatch, owner
):
    """A save from the Edit form does what `r` does: the PDF goes again as a dry run, and
    a refusal for the lines still left opens the screen with them."""
    engine = Engine(monkeypatch, fake_client, AMAZON, ALMUERZO)
    engine.refusals = [refusal(["l-amazon", "l-almuerzo"]), refusal(["l-amazon"])]

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        screen = await _leftover(pilot, app)
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        form = app.screen
        assert form._record["bank_line_id"] == "l-almuerzo"
        assert form.crumb == (*screen.crumb(), "Edit")
        assert form._opener is screen
        assert engine.uploads == [True]
        form.dismiss(None)  # left unsaved: nothing is sent
        await wait_for(pilot, lambda: app.screen is screen)
        await pilot.pause()
        assert engine.uploads == [True]
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EditFormScreen))
        del engine.held["l-almuerzo"]  # the fix: the paper takes it
        app.screen.dismiss(True)
        await wait_for(pilot, lambda: len(engine.uploads) == 2)
        second = await _leftover(pilot, app)
        assert second is not screen
        assert _listed(second) == ["l-amazon"]

    run_app(scenario)


def test_every_line_dealt_with_says_what_to_do_next_and_drops_edit_and_delete(
    fake_client, monkeypatch, owner
):
    engine = Engine(monkeypatch, fake_client, AMAZON)
    engine.refusals = [refusal(["l-amazon"])]

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        screen = await _leftover(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        del engine.held["l-amazon"]
        await pilot.press("y")
        await wait_for(pilot, lambda: _listed(screen) == [])
        text = "\n".join(screen_lines(app))
        assert "Nothing is left over: r reads the paper again." in text
        assert "For each one:" not in text
        assert _head(screen) == ["Can't close the statement yet · BCP-5678", "Nothing was written."]
        assert _footer(screen) == ["esc Cancel", "r Read again"]

    run_app(scenario)


def test_r_waits_for_a_delete_still_being_sent(fake_client, monkeypatch, owner):
    engine = Engine(monkeypatch, fake_client, AMAZON, ALMUERZO)
    engine.refusals = [refusal(["l-amazon", "l-almuerzo"])]
    release = threading.Event()
    answer = fake_client.delete

    def slow_delete(path):
        release.wait(timeout=10)
        return answer(path)

    fake_client.delete = slow_delete

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        screen = await _leftover(pilot, app)
        await pilot.press("d")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmModal))
        await pilot.press("y")
        await wait_for(pilot, lambda: bool(screen.saves_pending()))
        await pilot.press("r")
        await pilot.pause()
        assert app.screen is screen
        assert engine.uploads == [True]  # no second dry run while the delete is on its way
        assert "Writing — one moment." in [n.message for n in app._notifications]
        release.set()

    run_app(scenario)


def test_esc_follows_the_runs_cancel_word_when_several_files_were_dropped(
    fake_client, monkeypatch, owner
):
    engine = Engine(monkeypatch, fake_client, AMAZON)
    engine.refusals = [refusal(["l-amazon"])]

    async def scenario(pilot, app):
        run = ImportRun([DroppedFile(Path("a.pdf"), b"%PDF"), DroppedFile(Path("b.pdf"), b"%PDF")])
        await app.push_screen(StatementPreviewScreen(run, owner, PICK))
        screen = await _leftover(pilot, app)
        assert _footer(screen)[0] == "esc Cancel both"

    run_app(scenario)


def test_r_refused_again_for_lines_shows_the_screen_with_the_new_lines(
    fake_client, monkeypatch, owner
):
    engine = Engine(monkeypatch, fake_client, AMAZON, TAXI)
    engine.refusals = [refusal(["l-amazon"]), refusal(["l-taxi"])]

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        first = await _leftover(pilot, app)
        await pilot.press("r")
        await wait_for(pilot, lambda: app.screen is not first)
        second = await _leftover(pilot, app)
        assert _listed(second) == ["l-taxi"]
        assert engine.uploads == [True, True]

    run_app(scenario)


def test_r_met_by_another_refusal_shows_it_on_the_preview_in_the_engines_words(
    fake_client, monkeypatch, owner
):
    engine = Engine(monkeypatch, fake_client, AMAZON)
    other = EngineError(
        "CONFLICT",
        "Octubre is completed.",
        {"file": "Octubre is completed."},
        409,
        {},
        {"file": "STATEMENT_NOT_DRAFT"},
    )
    engine.refusals = [refusal(["l-amazon"]), other]

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        await _leftover(pilot, app)
        await pilot.press("r")
        await wait_for(pilot, lambda: isinstance(app.screen, StatementPreviewScreen))
        await wait_for(pilot, lambda: bool(app.screen._failure), message="no refusal")
        assert "! file: Octubre is completed." in [t.plain for t in app.screen._failure]

    run_app(scenario)


def test_a_refused_read_shows_the_engines_words_and_keeps_the_head(fake_client, monkeypatch, owner):
    engine = Engine(monkeypatch, fake_client, AMAZON)
    engine.refusals = [refusal(["l-amazon"])]
    engine.read_refusal = EngineError("INTERNAL_ERROR", "The read failed.", None, 500, {})

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        await wait_for(pilot, lambda: isinstance(app.screen, LeftoverLinesScreen))
        screen = app.screen
        await wait_for(pilot, lambda: bool(toasts_shown(app)), message="no note")
        shown = toasts_shown(app)[0]
        assert shown.startswith("Failed") and format_error(engine.read_refusal) in shown
        assert screen._lines is None
        assert _head(screen)[1] == "1 line in no statement sits on its days."

    run_app(scenario, toasts=True)


def test_esc_leaves_to_the_log_bar_and_writes_nothing(fake_client, monkeypatch, owner):
    engine = Engine(monkeypatch, fake_client, AMAZON)
    engine.refusals = [refusal(["l-amazon"])]

    async def scenario(pilot, app):
        await _preview(pilot, app, owner)
        await _leftover(pilot, app)
        await pilot.press("escape")
        await wait_for(pilot, lambda: owner.closed == [False])
        assert fake_client.deletes == [] and engine.uploads == [True]

    run_app(scenario)


@pytest.mark.parametrize(
    "err",
    [
        EngineError("VALIDATION_ERROR", "x", {"file": "x"}, 422, {}, {"file": "SEALED_PERIOD"}),
        EngineError(
            "VALIDATION_ERROR", "x", {"file": "x"}, 422, {}, {"file": "LOOSE_LINES_ON_SEALED_DAYS"}
        ),
        ValueError("no engine"),
    ],
    ids=["another-reason", "no-details", "not-an-engine-error"],
)
def test_only_a_refusal_naming_lines_is_read_as_leftover_lines(err):
    assert loose_lines(err) is None
