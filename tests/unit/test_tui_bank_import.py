"""The import door — a bank file dropped on the LOG bar → account → preview → result.

The screens are docs/mockups/expense-world-import-whole-file.html (the account
list, a skipped row 2 B, a card's `cur` column 3 B, a refused file 4, the
result 5), with the rest of the preview as expense-world-import-report.html
1 A. Pure builders first, then pilot tests through the LOG bar the way a drop
arrives. A dropped file is a few made-up bytes: the app sends them whole and
reads no cell, and the one engine call, `POST /transactions/import`, is
answered by a fake on the shared FakeClient that reads the file it was sent
and answers that file's rows (`import_answer`).
"""

import base64
import re
import threading

import pytest
from textual.widgets import Input, Static

from expense.bank_import.engine import AnswerCounts, Verdict, answer_rows, preview_line
from expense.bank_import.flow import ImportRefused, account_picks, read_file
from expense.errors import EngineError
from expense.tui.screens.bank_import import (
    FileProblem,
    ImportAccountScreen,
    ImportPreviewScreen,
    ImportResultScreen,
    account_lines,
    mark_cell,
    problem_hint,
    reason_cell,
    result_head,
)
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.log_bar import LogBarScreen
from expense.tui.theme import PALETTE
from tests.unit.helpers import (
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_BANK_NAMES,
    import_answer,
    import_day,
    import_part,
    import_row,
    render_text,
    run_app,
    stub_home_month,
    unclaimed_line,
    wait_for,
    whole,
)


def _account(ident, name, currency="PEN", *, partner=None, **extra) -> dict:
    return {
        "id": ident,
        "name": name,
        "currency_code": currency,
        "is_person": False,
        "is_archived": False,
        "opening_balance_transaction_id": None,
        "statement_code": "SIG" if partner else None,
        "statement_partner_id": partner,
        **extra,
    }


#: The card's dollar account first, so its line stands there and still sends the
#: soles one; then a current account, and an archived one the list leaves out.
ACCOUNTS = [
    _account("sig-usd", "BCP Signature USD", "USD", partner="sig-pen"),
    _account("sig-pen", "BCP Signature PEN", partner="sig-usd"),
    _account("bcp-pen", "BCP PEN"),
    _account("old", "Retired PEN", is_archived=True),
]
LEDGER_LINE = "tottus porongoche -38.60 $BCP Signature PEN"

#: A card's download as the engine reads it: rows 2–5, row 3 in dollars.
CARD_ROWS = [
    import_row(2, -4900, day="2026-09-11", title="EDO SUSHI BAR LI"),
    import_row(3, -2117, day="2026-09-09", title="APPLE.COM/BILL", account_id="sig-usd"),
    import_row(4, -420, day="2026-09-08", title="UBER TRIP"),
    import_row(5, -350, day="2026-09-07", title="APPARKA MALL AVENTURA AREQU"),
]
#: The card's rows with two in the ledger already, one of them taking the bank's title.
CARD_TWO_IN_LEDGER = [
    CARD_ROWS[0],
    {**CARD_ROWS[1], "outcome": "matched", "rule": "same_day", "bank_line_id": "bl-x"},
    {
        **CARD_ROWS[2],
        "outcome": "matched",
        "rule": "operation_code",
        "bank_line_id": "bl-y",
        "retitled": True,
        "redated": False,
    },
    CARD_ROWS[3],
]
#: A current account's one-row download.
CURRENT_ROWS = [
    import_row(2, 651900, day="2026-09-12", title="PAGO PLANILLA", account_id="bcp-pen")
]

PART_1 = import_part("t-1", -350)
DAY_0907 = import_day(
    "2026-09-07", -350, -700, unmatched_rows=(5,), lines=(unclaimed_line("bl-1", [PART_1]),)
)
#: A transaction of 100 split 60 + 40 that no file row claimed: one line, two parts.
SPLIT_PARTS = [
    import_part("t-2a", -6000, line="bl-2", day="2026-09-08"),
    import_part("t-2b", -4000, line="bl-2", day="2026-09-08"),
]
DAY_0908_SPLIT = import_day(
    "2026-09-08", -420, -10420, lines=(unclaimed_line("bl-2", SPLIT_PARTS),)
)
#: A day whose totals agree, reported for the ledger lines no file row claimed:
#: a +50 and a -50 the file does not have.
EQUAL_PARTS = [
    import_part("t-3", 5000, line="bl-3", day="2026-09-11"),
    import_part("t-4", -5000, line="bl-4", day="2026-09-11"),
]
DAY_0911_EQUAL = import_day(
    "2026-09-11",
    -4900,
    -4900,
    lines=(unclaimed_line("bl-3", EQUAL_PARTS[:1]), unclaimed_line("bl-4", EQUAL_PARTS[1:])),
)


# ---- the seams ---------------------------------------------------------------
def _patch(monkeypatch, accounts=None) -> None:
    """The LOG bar's reference reads, its peek, and the account list."""
    listed = whole(ACCOUNTS if accounts is None else accounts)
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: listed)
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_transactions", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.count_transactions", lambda *a, **k: 0)


def _engine(fake_client, files: dict, *, mismatches=None, counts=None) -> None:
    """Answer `POST /transactions/import` like the engine: it reads the file it
    was sent (`files`: a file's bytes → its rows as the engine reads them) and
    answers those rows, with `mismatches` and `counts` when given (by default
    no days, and the rows counted). Every call is still recorded on the fake
    client."""
    record = fake_client.post

    def post(path, json_body=None):
        record(path, json_body)
        rows = files[base64.b64decode(json_body["file"])]
        return import_answer(
            rows, dry_run=json_body["dry_run"], day_mismatches=mismatches, counts=counts
        )

    fake_client.post = post


def _imports(fake_client) -> list[bool]:
    """The `dry_run` of every import call, in order."""
    return [body["dry_run"] for path, body in fake_client.posts if path == "/transactions/import"]


def _bank_file(tmp_path, name: str = "Sueldo Soles (1).xlsx"):
    """A dropped file: made-up bytes, its own name in them so two differ."""
    path = tmp_path / name
    path.write_bytes(f"made-up download {name}".encode())
    return path


def _escaped(path) -> str:
    """What Terminal.app types for a drop."""
    return "".join("\\" + c if c in " ()" else c for c in str(path))


def _shown(screen) -> dict[str, str]:
    return {
        key: active.binding.description
        for key, active in screen.active_bindings.items()
        if active.binding.show
    }


def _footer(screen) -> list[str]:
    """The footer's entries, in order, as `key Description`."""
    return [
        f"{screen.app.get_key_display(a.binding)} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


def _body(screen) -> str:
    return render_text(screen.query_one("#import-body", Static).content, width=120)


def _crumb(screen) -> str:
    return render_text(screen.query_one("#crumb", Static).render(), width=120)


def _days_shown(preview) -> list[str]:
    """The preview's lines from the days' `!` head down, each stripped."""
    lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
    start = next(i for i, line in enumerate(lines) if line.startswith("! ") and "day" in line)
    return lines[start:]


def _lines_shown(screen) -> list[str]:
    """The screen's lines, each stripped, blanks left out."""
    return [line.strip() for line in _body(screen).split("\n") if line.strip()]


async def _open(app, pilot) -> LogBarScreen:
    screen = LogBarScreen()
    await app.push_screen(screen)
    await wait_for(pilot, lambda: screen._refs is not None, message="refs never loaded")
    return screen


def _type(screen, text) -> None:
    bar = screen.query_one("#bar", Input)
    bar.value = text
    bar.cursor_position = len(text)
    screen.on_input_changed(Input.Changed(bar, text))


async def _drop(pilot, screen, *paths) -> None:
    _type(screen, " ".join(_escaped(p) for p in paths))
    await pilot.pause()  # the bar's own Changed lands before the key, as when typed
    await pilot.press("enter")


async def _on(pilot, app, kind, message: str):
    await wait_for(pilot, lambda: isinstance(app.screen, kind), message=message)
    return app.screen


async def _preview(pilot, app):
    """The account list, once its accounts are read."""
    account = await _on(pilot, app, ImportAccountScreen, "no account list")
    await wait_for(pilot, lambda: account._run.picks is not None, message="accounts not read")
    return account


async def _previewed(pilot, app) -> ImportPreviewScreen:
    preview = await _on(pilot, app, ImportPreviewScreen, "no preview")
    await wait_for(pilot, lambda: preview._lines is not None, message="dry run never answered")
    return preview


async def _refused(pilot, app) -> ImportPreviewScreen:
    preview = await _on(pilot, app, ImportPreviewScreen, "no preview")
    await wait_for(pilot, lambda: bool(preview._failure), message="no failure shown")
    return preview


# ---- pure ----------------------------------------------------------------------
def test_a_cards_two_accounts_are_one_line():
    lines = [line.plain.rstrip() for line in account_lines(account_picks(ACCOUNTS), 0)]
    assert [re.split(r"\s{2,}", line.strip()) for line in lines] == [
        ["BCP Signature", "PEN + USD"],
        ["BCP PEN", "PEN"],
    ]
    assert "Retired" not in " ".join(lines)  # archived


def test_the_result_head_is_the_engines_new_count_and_where_the_rows_landed():
    """The result's title line: the engine's `new`, the account, and the
    pending category and hashtag, dim."""
    pick = account_picks(ACCOUNTS)[1]
    head = result_head(pick, AnswerCounts(14, 9, 5, 0, 0, 2, 1))
    assert head.plain == "✓ 9 rows imported · BCP PEN   new ones under @Pendiente and #Pendiente"
    assert result_head(pick, AnswerCounts(1, 1, 0, 0, 0, 0, 0)).plain.startswith(
        "✓ 1 row imported · BCP PEN"
    )


@pytest.mark.parametrize(
    ("keys", "mark", "mark_style", "style"),
    [
        ({}, "✓", PALETTE.success, PALETTE.success),
        ({"outcome": "matched"}, "✓", PALETTE.success, "dim"),
        ({"outcome": "matched", "retitled": True}, "✓", PALETTE.success, ""),
        (
            {"outcome": "matched", "redate_blocked_by": "r1"},
            "✗",
            f"bold {PALETTE.error}",
            PALETTE.warning,
        ),
        ({"outcome": "sealed"}, "✗", f"bold {PALETTE.error}", PALETTE.warning),
        ({"outcome": "skipped"}, "·", "dim", "dim"),
    ],
    ids=["new", "in-ledger", "modified", "not-moved", "closed", "skipped"],
)
def test_each_verdict_takes_its_mark_and_its_style(keys, mark, mark_style, style):
    """The mark and the reason's style follow the engine's outcome; every
    style is the theme's."""
    (row,) = answer_rows(import_answer([import_row(2, **keys)]))
    line = preview_line(row, {})
    assert (mark_cell(line).plain, str(mark_cell(line).style)) == (mark, mark_style)
    assert (reason_cell(line).plain, str(reason_cell(line).style)) == (line.reason, style)


def test_the_style_is_the_outcomes_whatever_the_reason_says():
    """Two rows whose reasons read alike are styled by their verdicts."""
    (row,) = answer_rows(import_answer([import_row(2)]))
    line = preview_line(row, {})
    odd = type(line)(row, Verdict.CLOSED, line.reason)  # "New", but closed
    assert str(reason_cell(odd).style) == PALETTE.warning
    assert mark_cell(odd).plain == "✗"


# ---- a file that cannot be read -------------------------------------------------
def test_a_file_gone_from_disk_stays_in_the_bar(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path, "Movimientos.xlsx")
    _patch(monkeypatch)
    _engine(fake_client, {})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, _escaped(path))
        await pilot.pause()
        path.unlink()  # gone between the drop and ⏎
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is screen
        hint = screen.query_one("#hint", Static).content.plain
        assert hint == f"can't read the file · File not found: {path}"
        assert _shown(screen) == {"escape": "Cancel"}
        await pilot.press("enter")  # ⏎ does nothing more
        await pilot.pause()
        assert app.screen is screen
        assert fake_client.calls == []  # nothing sent, not even the account list
        _type(screen, "")  # the next keystroke is a new attempt
        assert screen._file_problem is None

    run_app(scenario)


def test_an_unreadable_second_file_stops_the_drop_before_the_first_starts(
    fake_client, monkeypatch, tmp_path
):
    good, bad = _bank_file(tmp_path), _bank_file(tmp_path, "Otra.xlsx")
    _patch(monkeypatch)
    _engine(fake_client, {})

    def read_bytes(self):
        if self.name == bad.name:
            raise PermissionError(13, "Permission denied")
        return b"x"

    monkeypatch.setattr("pathlib.Path.read_bytes", read_bytes)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, good, bad)
        await pilot.pause()
        assert app.screen is screen
        assert screen.query_one("#hint", Static).content.plain == (
            f"Otra.xlsx · can't read the file · Could not open {bad}: Permission denied"
        )
        assert fake_client.calls == []

    run_app(scenario)


@pytest.mark.parametrize("several", [False, True], ids=["one file", "several files"])
def test_the_hint_says_the_file_cannot_be_read_in_both_forms(several, monkeypatch, tmp_path):
    """Gone or unreadable, one file or several: `can't read the file`, in the
    error colour, then the disk's own words; with several files, the name first."""
    gone = tmp_path / "Movimientos.xlsx"
    locked = tmp_path / "Otra.xlsx"

    def refused(path):
        try:
            read_file(path)
        except ImportRefused as exc:
            return FileProblem(path, exc)
        raise AssertionError("read")

    def read_bytes(self):
        raise PermissionError(13, "Permission denied")

    not_found = refused(gone)
    monkeypatch.setattr("pathlib.Path.read_bytes", read_bytes)
    no_open = refused(locked)
    head = "Otra.xlsx · " if several else ""
    found_head = "Movimientos.xlsx · " if several else ""
    for problem, text in (
        (not_found, f"{found_head}can't read the file · File not found: {gone}"),
        (no_open, f"{head}can't read the file · Could not open {locked}: Permission denied"),
    ):
        hint = problem_hint(problem, name_it=several)
        assert hint.plain == text
        (span,) = hint.spans
        assert hint.plain[span.start : span.end] == "can't read the file"
        assert str(span.style) == PALETTE.error


# ---- which account — pane 1 -------------------------------------------------------
def test_the_account_list_names_the_file_and_pairs_a_card_by_the_engine(
    fake_client, monkeypatch, tmp_path
):
    """The question and the file's name, dim, nothing read from the file; a
    card's two accounts one line, two accounts sharing a name but not a card
    two lines."""
    path = _bank_file(tmp_path)
    accounts = [
        *ACCOUNTS,
        _account("ia-pen", "Interbank Ahorros PEN"),
        _account("ia-usd", "Interbank Ahorros USD", "USD"),
    ]
    _patch(monkeypatch, accounts)
    _engine(fake_client, {})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        assert "Capture & ledger  ▸  Import  ▸  Sueldo Soles (1).xlsx" in _crumb(account)
        body = _body(account).split("\n")
        assert body[0].strip() == "Which account is this file?   Sueldo Soles (1).xlsx"
        listed = [re.split(r"\s{2,}", line.strip()) for line in body[2:] if line.strip()]
        assert listed == [
            ["BCP Signature", "PEN + USD"],
            ["BCP PEN", "PEN"],
            ["Interbank Ahorros PEN", "PEN"],
            ["Interbank Ahorros USD", "USD"],
        ]
        assert _shown(account) == {"escape": "Cancel", "enter": "Pick", "down": "Move"}
        assert _footer(account) == ["esc Cancel", "⏎ Pick", "↑↓ Move"]  # pane 1, in order
        assert _imports(fake_client) == []  # nothing asked of the import yet
        await pilot.press("down")
        assert account._cursor == 1
        await pilot.press("up")
        assert account._cursor == 0

    run_app(scenario, size=(120, 40))


def test_the_account_list_shows_the_engines_order(fake_client, monkeypatch, tmp_path):
    """The list shows the accounts exactly as `GET /accounts` returned them —
    not alphabetical, not by `sort_order`; the person is left out and nothing
    else moves."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch, ENGINE_ORDER_ACCOUNTS)
    _engine(fake_client, {})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        assert [pick.name for pick in account._picks] == ENGINE_ORDER_BANK_NAMES
        listed = [line.strip() for line in _body(account).split("\n")[2:] if line.strip()]
        assert [line.split("  ")[0] for line in listed] == ENGINE_ORDER_BANK_NAMES

    run_app(scenario, size=(120, 40))


def test_the_card_sends_the_file_whole_on_its_soles_account(fake_client, monkeypatch, tmp_path):
    """The body is exactly the three keys: the dry run, the card's soles
    account though its dollar one comes first, and the file's own bytes."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        ((sent_to, body),) = fake_client.posts
        assert sent_to == "/transactions/import"
        assert body == {
            "dry_run": True,
            "account_id": "sig-pen",
            "file": base64.b64encode(path.read_bytes()).decode("ascii"),
        }

    run_app(scenario, size=(120, 40))


# ---- the preview ------------------------------------------------------------------
def test_the_preview_shows_verdicts_and_writes_nothing_before_enter(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_TWO_IN_LEDGER})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = _lines_shown(preview)
        assert lines[0] == "Preview · BCP Signature · nothing written yet"
        assert lines[1].split() == ["#", "date", "title", "amount", "cur", "reason"]
        rows = [re.split(r"\s{2,}", line) for line in lines[2:6]]
        assert rows == [
            ["2", "2026-09-11", "EDO SUSHI BAR LI", "-49.00", "PEN", "✓", "New"],
            ["3", "2026-09-09", "APPLE.COM/BILL", "-21.17", "USD", "✓", "Already in the ledger"],
            ["4", "2026-09-08", "UBER TRIP", "-4.20", "PEN", "✓", "Modified existing transaction"],
            ["5", "2026-09-07", "APPARKA MALL AVENTURA AREQU", "-3.50", "PEN", "✓", "New"],
        ]
        assert lines[6] == "4 rows · 2 new · 2 in the ledger · 1 takes the bank's title"
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 2 rows"}
        assert _imports(fake_client) == [True]  # the dry run only

    run_app(scenario, size=(120, 40))


def test_a_current_accounts_preview_has_no_currency_column(fake_client, monkeypatch, tmp_path):
    """`cur` is a card's alone (3 B): a current account's download holds its
    one currency."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CURRENT_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        lines = _lines_shown(preview)
        assert lines[1].split() == ["#", "date", "title", "amount", "reason"]
        assert re.split(r"\s{2,}", lines[2]) == [
            "2",
            "2026-09-12",
            "PAGO PLANILLA",
            "6,519.00",
            "✓",
            "New",
        ]

    run_app(scenario, size=(120, 40))


#: A download with one row of each outcome, numbered by the spreadsheet; row 6 is a
#: row of 0 the engine skipped, and row 9 has no title.
EVERY_REASON_ROWS = [
    import_row(2, -1850, day="2026-10-14", title="CAFE ANDINO LIMA PE", account_id="bcp-pen"),
    import_row(
        3,
        -420,
        day="2026-10-13",
        title="AMAZON MKTPLACE",
        account_id="bcp-pen",
        outcome="matched",
        rule="same_day",
    ),
    import_row(
        4,
        -4290,
        day="2026-10-11",
        title="FARMACIA CENTRAL",
        account_id="bcp-pen",
        outcome="matched",
        rule="operation_code",
        retitled=True,
    ),
    import_row(
        5,
        -2800,
        day="2026-10-09",
        title="SPOTIFY P2F3",
        account_id="bcp-pen",
        outcome="matched",
        rule="operation_code",
        redated=True,
    ),
    import_row(
        6, 0, day="2026-10-05", title="PAGO TARJETA", account_id="bcp-pen", outcome="skipped"
    ),
    import_row(
        7,
        -750,
        day="2026-10-01",
        title="TAMBO MIRAFLORES",
        account_id="bcp-pen",
        outcome="matched",
        rule="operation_code",
        redate_blocked_by="r-sep",
    ),
    import_row(
        8,
        -12000,
        day="2026-08-29",
        title="SHELL SAN ISIDRO",
        account_id="bcp-pen",
        outcome="sealed",
        sealed_by="r-aug",
    ),
    import_row(9, -1540, day="2026-10-15", title=None, account_id="bcp-pen"),
]
EVERY_REASON_COUNTS = {
    "new": 2,
    "matched": 4,
    "sealed": 1,
    "skipped": 1,
    "backfilled": 0,
    "retitled": 1,
    "redated": 1,
}
RECONCILIATIONS = {
    "r-aug": {"id": "r-aug", "name": "Agosto 2026"},
    "r-sep": {"id": "r-sep", "name": "Septiembre 2026"},
}


def _reconciliations(monkeypatch, answer=None) -> list:
    """`GET /reconciliations/{id}`, recorded: each call's id, answered from
    RECONCILIATIONS, or `answer` raised when it is an exception. The account's
    list is never read: a read of it fails the test."""
    asked: list = []

    def fetch(cfg, reconciliation_id, *, verbose=False):
        asked.append(reconciliation_id)
        if isinstance(answer, Exception):
            raise answer
        return RECONCILIATIONS[reconciliation_id]

    def listed(*a, **k):
        raise AssertionError("the account's reconciliation list is read")

    monkeypatch.setattr("expense.reads.fetch_reconciliation", fetch)
    monkeypatch.setattr("expense.reads.fetch_reconciliations", listed)
    return asked


def test_every_row_shows_its_mark_and_its_reason(fake_client, monkeypatch, tmp_path):
    """One table of the rows the engine read, numbered by the spreadsheet,
    each with its mark and reason alone: a row of 0 a dim `·` and `Skipped:
    amount 0` (2 B). A move a completed reconciliation stops names that
    reconciliation, read once by its id in the worker; the counts add the
    engine's moved count, and the closed and skipped counts go on a line of
    their own."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    asked = _reconciliations(monkeypatch)
    _engine(fake_client, {path.read_bytes(): EVERY_REASON_ROWS}, counts=EVERY_REASON_COUNTS)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        lines = _lines_shown(preview)
        assert lines[1].split() == ["#", "date", "title", "amount", "reason"]
        rows = [re.split(r"\s{2,}", line) for line in lines[2:10]]
        assert rows == [
            ["2", "2026-10-14", "CAFE ANDINO LIMA PE", "-18.50", "✓", "New"],
            ["3", "2026-10-13", "AMAZON MKTPLACE", "-4.20", "✓", "Already in the ledger"],
            ["4", "2026-10-11", "FARMACIA CENTRAL", "-42.90", "✓", "Modified existing transaction"],
            ["5", "2026-10-09", "SPOTIFY P2F3", "-28.00", "✓", "Modified existing transaction"],
            ["6", "2026-10-05", "PAGO TARJETA", "0.00", "·", "Skipped: amount 0"],
            [
                "7",
                "2026-10-01",
                "TAMBO MIRAFLORES",
                "-7.50",
                "✗",
                "Not moved: Septiembre 2026 is reconciled",
            ],
            ["8", "2026-08-29", "SHELL SAN ISIDRO", "-120.00", "✗", "Closed period"],
            ["9", "2026-10-15", "—", "-15.40", "✓", "New"],
        ]
        assert lines[10:] == [
            "8 rows · 2 new · 4 in the ledger · 1 moves to the bank's day · "
            "1 takes the bank's title",
            "1 closed · 1 skipped",
        ]
        # the second line sits under the first count, not under `8 rows`
        raw = [line for line in _body(preview).split("\n") if line.strip()]
        assert raw[-1].index("1 closed") == raw[-2].index("2 new")
        body = _body(preview)
        assert "2026" not in lines[-1] and "unreadable" not in body and "Couldn't" not in body
        # the reconciliation is named by one read of it by its id, in the worker
        assert asked == ["r-sep"]
        preview._repaint()
        await pilot.resize_terminal(130, 40)
        await pilot.pause()
        assert asked == ["r-sep"]  # drawing the screen again reads nothing
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 2 rows"}

    run_app(scenario, size=(120, 40))


def test_no_reconciliation_is_read_when_no_move_is_stopped(fake_client, monkeypatch, tmp_path):
    """A closed period's row says `Closed period` alone, so nothing is read to
    name it; and with no move, the counts say nothing of the bank's day."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    asked = _reconciliations(monkeypatch)
    rows = [{**CARD_ROWS[0], "outcome": "sealed", "sealed_by": "r-aug"}, *CARD_ROWS[1:]]
    _engine(fake_client, {path.read_bytes(): rows})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = _lines_shown(preview)
        assert lines[2].endswith("✗  Closed period")
        assert lines[-2:] == ["4 rows · 3 new · 0 in the ledger", "1 closed"]
        assert "bank's day" not in _body(preview)
        assert asked == []

    run_app(scenario, size=(120, 40))


def test_a_reconciliation_that_cannot_be_read_leaves_the_move_unnamed(
    fake_client, monkeypatch, tmp_path
):
    """A failed read never hides the preview: the row stays ✗, its
    reconciliation unnamed, and why is one dim line under the counts."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    refusal = EngineError("INTERNAL_ERROR", "The engine failed.", None, 500, {})
    asked = _reconciliations(monkeypatch, refusal)
    stopped = {**CARD_ROWS[0], "outcome": "matched", "redate_blocked_by": "r-sep"}
    _engine(fake_client, {path.read_bytes(): [stopped, *CARD_ROWS[1:]]})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = _lines_shown(preview)
        assert lines[2].endswith("✗  Not moved: a reconciliation is reconciled")
        assert any(
            line.startswith("! could not read the reconciliations' names:") for line in lines
        )
        assert asked == ["r-sep"]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 3 rows"}

    run_app(scenario, size=(120, 40))


def test_the_summary_and_the_footer_read_the_engines_counts(fake_client, monkeypatch, tmp_path):
    """The verdict counts and `⏎ Import N rows` are the engine's `counts`, not
    the rows counted — here they disagree on purpose; the total is its rows."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    counts = {
        "new": 7,
        "matched": 5,
        "sealed": 0,
        "skipped": 3,
        "backfilled": 0,
        "retitled": 3,
        "redated": 0,
    }
    _engine(fake_client, {path.read_bytes(): CARD_TWO_IN_LEDGER}, counts=counts)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _lines_shown(preview)[-2:] == [
            "4 rows · 7 new · 5 in the ledger · 3 take the bank's title",
            "3 skipped",
        ]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 7 rows"}
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no result screen")
        assert _lines_shown(result) == [
            "✓ 7 rows imported · BCP Signature   new ones under @Pendiente and #Pendiente",
            "4 rows · 7 new · 5 in the ledger · 3 took the bank's title",
            "3 skipped",
        ]

    run_app(scenario, size=(120, 40))


def test_the_counts_say_how_many_move_in_the_plural(fake_client, monkeypatch, tmp_path):
    """`2 move to the bank's day` on the preview, the engine's number."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    counts = {
        "new": 2,
        "matched": 2,
        "sealed": 0,
        "skipped": 0,
        "backfilled": 0,
        "retitled": 0,
        "redated": 2,
    }
    _engine(fake_client, {path.read_bytes(): CARD_TWO_IN_LEDGER}, counts=counts)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _lines_shown(preview)[-1] == (
            "4 rows · 2 new · 2 in the ledger · 2 move to the bank's day"
        )

    run_app(scenario, size=(120, 40))


# ---- the days where the file and the ledger disagree ----------------------------
def _no_reads_per_part(monkeypatch) -> list:
    """Every transaction read the screens make, recorded: the unclaimed lines
    carry their parts whole, so the upload needs none."""
    reads_made: list = []
    monkeypatch.setattr(
        "expense.reads.fetch_transaction", lambda *a, **k: reads_made.append(("one", a, k))
    )
    monkeypatch.setattr(
        "expense.reads.fetch_transactions",
        lambda *a, **k: reads_made.append(("list", a, k)) or whole([]),
    )
    return reads_made


@pytest.mark.parametrize(
    ("day", "shown"),
    [
        (
            DAY_0908_SPLIT,
            [
                "! 1 day where the file and the ledger disagree",
                "2026-09-08 · BCP Signature PEN   file -4.20 · ledger after import -104.20",
                "TOTTUS PORONGOCHE  -60.00   in the ledger, not in the file",
                "TOTTUS PORONGOCHE  -40.00   in the ledger, not in the file",
            ],
        ),
        (
            DAY_0911_EQUAL,
            [
                "! 1 day where the file and the ledger disagree",
                "2026-09-11 · BCP Signature PEN   file -49.00 · ledger after import -49.00",
                "TOTTUS PORONGOCHE   50.00   in the ledger, not in the file",
                "TOTTUS PORONGOCHE  -50.00   in the ledger, not in the file",
            ],
        ),
    ],
    ids=["split-line-two-parts", "equal-totals-day"],
)
def test_reported_days_are_drawn_from_their_parts_on_the_preview_only(
    fake_client, monkeypatch, tmp_path, day, shown
):
    """A split line (one entry, two parts) and a day reported with equal totals:
    each part is its own row, its amount signed off the engine's magnitude and
    type, under the engine's two totals as sent; no transaction is read to fill
    them, and the screen after importing shows no days."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_TWO_IN_LEDGER}, mismatches=[day])

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        reads_made = _no_reads_per_part(monkeypatch)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _days_shown(preview) == shown
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no result screen")
        assert not any("disagree" in line or "TOTTUS" in line for line in _lines_shown(result))
        assert reads_made == []
        assert [m for m, _ in fake_client.requests if m == "GET"] == []

    run_app(scenario, size=(120, 40))


def test_a_reported_day_lists_the_file_rows_not_found_and_the_ledger_rows_not_claimed(
    fake_client, monkeypatch, tmp_path
):
    """The day's two totals, the file's row by its spreadsheet row and the
    ledger's by title and signed amount, the ledger row under the file row's
    title."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_TWO_IN_LEDGER}, mismatches=[DAY_0907])

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _days_shown(preview) == [
            "! 1 day where the file and the ledger disagree",
            "2026-09-07 · BCP Signature PEN   file -3.50 · ledger after import -7.00",
            "row 5   APPARKA MALL AVENTURA AREQU  -3.50   in the file, not found",
            "TOTTUS PORONGOCHE            -3.50   in the ledger, not in the file",
        ]
        rows = [
            line
            for line in _body(preview).split("\n")
            if "not found" in line or "not in the file" in line
        ]
        assert rows[0].index("APPARKA") == rows[1].index("TOTTUS")
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 2 rows"}  # a report only

    run_app(scenario, size=(120, 40))


#: The card's dollar account's reported day: a ledger row the file did not claim.
DAY_0909_USD = import_day(
    "2026-09-09",
    -2117,
    -4234,
    account_id="sig-usd",
    lines=(
        unclaimed_line(
            "bl-9",
            [
                import_part(
                    "t-9", -2117, account_id="sig-usd", line="bl-9", day="2026-09-09", title="Apple"
                )
            ],
        ),
    ),
)


def test_a_card_files_days_name_their_account(fake_client, monkeypatch, tmp_path):
    """A card's two currencies are two accounts: every day on the preview
    names its account."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(
        fake_client, {path.read_bytes(): CARD_TWO_IN_LEDGER}, mismatches=[DAY_0907, DAY_0909_USD]
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _days_shown(preview) == [
            "! 2 days where the file and the ledger disagree",
            "2026-09-07 · BCP Signature PEN   file  -3.50 · ledger after import  -7.00",
            "row 5   APPARKA MALL AVENTURA AREQU   -3.50   in the file, not found",
            "TOTTUS PORONGOCHE             -3.50   in the ledger, not in the file",
            "2026-09-09 · BCP Signature USD   file -21.17 · ledger after import -42.34",
            "Apple                        -21.17   in the ledger, not in the file",
        ]

    run_app(scenario, size=(120, 40))


def test_a_one_account_files_days_carry_the_date_alone(fake_client, monkeypatch, tmp_path):
    """On a file of one account the days are not named by account."""
    path = _bank_file(tmp_path)
    rows = [
        import_row(2, -4290, day="2026-09-12", title="FARMACIA CENTRAL", account_id="bcp-pen"),
        import_row(3, -2800, day="2026-09-11", title="CINE", account_id="bcp-pen"),
    ]
    farmacia = import_part(
        "t-f", -4200, account_id="bcp-pen", line="bl-f", day="2026-09-12", title="Farmacia"
    )
    day = import_day(
        "2026-09-12",
        -4290,
        -8490,
        account_id="bcp-pen",
        unmatched_rows=(2,),
        lines=(unclaimed_line("bl-f", [farmacia]),),
    )
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): rows}, mismatches=[day])

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        assert _days_shown(preview) == [
            "! 1 day where the file and the ledger disagree",
            "2026-09-12   file -42.90 · ledger after import -84.90",
            "row 2   FARMACIA CENTRAL  -42.90   in the file, not found",
            "Farmacia          -42.00   in the ledger, not in the file",
        ]

    run_app(scenario, size=(120, 40))


def test_the_preview_pages_with_pgdn(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    rows = [
        import_row(d + 1, -d, day=f"2026-09-{d:02d}", title=f"SHOP {d}", account_id="bcp-pen")
        for d in range(1, 29)
    ]
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): rows})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("down", "enter")
        preview = await _previewed(pilot, app)
        size = preview._page_size()
        assert size < 28
        assert f"… {28 - size} more · pgdn" in _body(preview)
        await pilot.press("pagedown")
        assert preview._start == size
        await pilot.press("pageup")
        assert preview._start == 0

    run_app(scenario, size=(120, 30))


# ---- pane 4: a file the engine refuses ---------------------------------------------
def test_rows_the_engine_refuses_show_in_its_words_and_nothing_is_written(
    fake_client, monkeypatch, tmp_path
):
    """4 a: `CODE — message`, then each refused row in the engine's words,
    alone, as they begin `Row <n>:` (a `FUTURE_DATE` included), then `Nothing
    was written.`; `esc Back`, and `⏎` sends nothing more. Words that do not
    begin `Row <n>:` keep the row's key
    (`test_a_refused_apply_shows_the_engines_words_and_what_to_do`)."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR",
        "Import validation failed.",
        {
            "rows.12.amount_cents": "Row 12: Monto holds 'abc', not a number.",
            "rows.15.operation_code": "Row 15: operation number 0001 is on row 3 too.",
            "rows.16.date": "Row 16: Must not be in the future.",
        },
        422,
        {},
        {
            "rows.12.amount_cents": "UNEXPECTED_LAYOUT",
            "rows.15.operation_code": "DUPLICATE_IN_REQUEST",
            "rows.16.date": "FUTURE_DATE",
        },
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _refused(pilot, app)
        assert _lines_shown(preview) == [
            "Preview · BCP PEN · nothing written yet",
            "VALIDATION_ERROR — Import validation failed.",
            "! Row 12: Monto holds 'abc', not a number.",
            "! Row 15: operation number 0001 is on row 3 too.",
            "! Row 16: Must not be in the future.",
            "Nothing was written.",
        ]
        assert _shown(preview) == {"escape": "Back"}
        await pilot.press("enter")
        await pilot.pause()
        assert len(fake_client.posts) == 1  # the refused dry run, nothing after
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc Back did not return to the bar")

    run_app(scenario, size=(120, 40))


@pytest.mark.parametrize(
    ("key", "reason", "words"),
    [
        (
            "file",
            "UNEXPECTED_LAYOUT",
            "Row 1 must be the header 'Fecha | Descripcion | Moneda | Monto'; it is 'a | b'.",
        ),
        (
            "file",
            "UNREADABLE_FILE",
            "It is not an Excel workbook (.xlsx): it is not a zip archive.",
        ),
        ("account_id", "INVALID_REFERENCE", "Must reference an active, non-archived account."),
    ],
    ids=["not-a-download", "unreadable", "account"],
)
def test_a_file_refused_whole_shows_its_key_and_the_engines_words(
    fake_client, monkeypatch, tmp_path, key, reason, words
):
    """4 b: a refusal on `file` or `account_id` names its key before the
    engine's words."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR", "The file is not a bank download.", {key: words}, 422, {}, {key: reason}
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _refused(pilot, app)
        assert _lines_shown(preview)[1:] == [
            "VALIDATION_ERROR — The file is not a bank download.",
            f"! {key}: {words}",
            "Nothing was written.",
        ]
        assert _shown(preview) == {"escape": "Back"}

    run_app(scenario, size=(160, 40))


def test_a_row_changed_while_the_import_ran_previews_again_before_any_write(
    fake_client, monkeypatch, tmp_path
):
    """The apply's `409 CONFLICT` with `CONCURRENT_CHANGE` on `rows.<row>`
    shows the engine's words, and `⏎ Preview again` asks for a fresh dry run;
    the next apply waits for its own `⏎`."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_TWO_IN_LEDGER})
    words = "Row 4: another request changed this row's ledger line. Send it again."

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        fake_client.errors["POST"] = EngineError(
            "CONFLICT",
            "The ledger changed while the import ran.",
            {"rows.4": words},
            409,
            {},
            {"rows.4": "CONCURRENT_CHANGE"},
        )
        await pilot.press("enter")
        await wait_for(
            pilot,
            lambda: bool(preview._failure) and bool(app._notifications),
            message="no failure shown, or no toast",
        )
        lines = [line.strip() for line in _body(preview).split("\n")]
        at = lines.index("CONFLICT — The ledger changed while the import ran.")
        assert lines[at : at + 5] == [
            "CONFLICT — The ledger changed while the import ran.",
            f"! {words}",
            "Nothing was written.",
            "",
            "It changed while the import ran: ⏎ checks the file against the ledger again.",
        ]
        assert str(list(app._notifications)[-1].message) == (
            "CONFLICT — The ledger changed while the import ran.\n"
            f"  rows.4: {words}\n\n"
            "It changed while the import ran: ⏎ checks the file against the ledger again."
        )
        assert _shown(preview) == {"escape": "Cancel", "enter": "Preview again"}
        assert _imports(fake_client) == [True, False]

        del fake_client.errors["POST"]
        await pilot.press("enter")  # a fresh dry run, never the apply
        await wait_for(
            pilot, lambda: preview._lines is not None, message="the preview did not run again"
        )
        assert _imports(fake_client) == [True, False, True]
        assert preview._failure == []
        assert "CONFLICT" not in _body(preview)
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 2 rows"}

        await pilot.press("enter")  # only now is the file written
        await _on(pilot, app, ImportResultScreen, "no result screen")
        assert _imports(fake_client) == [True, False, True, False]

    run_app(scenario, size=(120, 40))


def test_a_row_refusal_naming_no_row_is_not_a_reason_to_preview_again(
    fake_client, monkeypatch, tmp_path
):
    """`CONCURRENT_CHANGE` keyed by anything but a row keeps the other saves'
    line, and `⏎` sends nothing more."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        fake_client.errors["POST"] = EngineError(
            "CONFLICT", "stand-in", {"rows": "x"}, 409, {}, {"rows": "CONCURRENT_CHANGE"}
        )
        await pilot.press("enter")
        await wait_for(pilot, lambda: bool(preview._failure), message="no failure shown")
        assert "! rows: x" in _body(preview)
        assert "It changed at the same moment: save again." in _body(preview)
        assert _shown(preview) == {"escape": "Back"}
        await pilot.press("enter")
        await pilot.pause()
        assert _imports(fake_client) == [True, False]

    run_app(scenario, size=(120, 40))


#: The app's line under an operation number already on the account.
CODE_EXISTS_LINE = (
    "That account already has a row with this operation number: look there for a duplicate."
)


@pytest.mark.parametrize(
    ("code", "status", "key", "reason", "words", "shown", "line"),
    [
        (
            "CONFLICT",
            409,
            "rows.2.operation_code",
            "OPERATION_CODE_EXISTS",
            "Row 2: operation number 0001 is already on the account.",
            "! Row 2: operation number 0001 is already on the account.",
            CODE_EXISTS_LINE,
        ),
        (
            "CONFLICT",
            409,
            "rows.2.operation_code",
            "OPERATION_CODE_EXISTS",
            "Already on the account.",
            "! rows.2.operation_code: Already on the account.",
            CODE_EXISTS_LINE,
        ),
        (
            "CONFLICT",
            409,
            "category_id",
            "RESERVED_NAME_HELD",
            "stand-in field words.",
            "! category_id: stand-in field words.",
            "One of your categories has a built-in category's name: "
            "rename it on Manage ▸ Categories, then save again.",
        ),
        (
            "LIMIT_REACHED",
            422,
            "rows.2.transaction_id",
            "LINE_CODES_EXHAUSTED",
            "Row 2: stand-in field words.",
            "! Row 2: stand-in field words.",
            None,
        ),
    ],
    ids=[
        "operation-code-exists",
        "operation-code-exists-words-without-row",
        "reserved-name-held",
        "line-codes-exhausted",
    ],
)
def test_a_refused_apply_shows_the_engines_words_and_what_to_do(
    fake_client, monkeypatch, tmp_path, code, status, key, reason, words, shown, line
):
    """The apply refused: the engine's words as the preview lays a refusal
    out, then the app's line for it when it has one; the toast is the shared
    error text. A row's words that do not begin `Row <n>:` keep their key, so
    the row is never lost. Nothing more is sent."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        err = EngineError(code, "stand-in", {key: words}, status, {}, {key: reason})
        fake_client.errors["POST"] = err
        await pilot.press("enter")
        await wait_for(
            pilot,
            lambda: bool(preview._failure) and bool(app._notifications),
            message="no failure shown, or no toast",
        )
        expected = [f"{code} — stand-in", shown, "Nothing was written."]
        if line is not None:
            expected += ["", line]
        assert [t.plain for t in preview._failure] == expected
        toast_words = str(list(app._notifications)[-1].message)
        assert toast_words.startswith(f"{code} — stand-in\n  {key}: {words}")
        assert _shown(preview) == {"escape": "Back"}
        await pilot.press("enter")
        await pilot.pause()
        assert _imports(fake_client) == [True, False]

    run_app(scenario, size=(160, 40))


def test_an_engine_error_on_apply_is_shown_and_nothing_more_is_sent(
    fake_client, monkeypatch, tmp_path
):
    """A failure naming no key is the shared error text, whole."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        fake_client.errors["POST"] = EngineError(
            "INTERNAL_ERROR", "The engine failed.", None, 500, {}
        )
        await pilot.press("enter")
        await wait_for(
            pilot,
            lambda: bool(preview._failure) and bool(app._notifications),
            message="no failure shown, or no toast",
        )
        assert [t.plain for t in preview._failure] == ["INTERNAL_ERROR — The engine failed."]
        assert any("INTERNAL_ERROR" in str(n.message) for n in app._notifications)
        assert _shown(preview) == {"escape": "Back"}
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is preview
        assert len(fake_client.posts) == 2  # the dry run and the refused apply

    run_app(scenario, size=(120, 40))


# ---- nothing new -------------------------------------------------------------------
def test_nothing_new_shows_the_preview_and_enter_writes_nothing(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    matched = [{**r, "outcome": "matched", "rule": "operation_code"} for r in CARD_ROWS]
    _engine(fake_client, {path.read_bytes(): matched})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = _lines_shown(preview)
        assert lines[-2:] == ["4 rows · 0 new · 4 in the ledger", "nothing to import"]
        assert sum(line.endswith("✓  Already in the ledger") for line in lines) == 4
        assert _shown(preview) == {"escape": "Back"}
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is preview
        assert _imports(fake_client) == [True]
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc Back did not return to the bar")
        assert _imports(fake_client) == [True]

    run_app(scenario, size=(120, 40))


# ---- the apply and pane 5 ------------------------------------------------------------
def test_apply_writes_once_and_the_result_gives_the_counts(fake_client, monkeypatch, tmp_path):
    """Pane 5: the title line and the counts in the past tense, `1 skipped`
    among them; no table and no days, though the apply reported one. The apply
    sends the same file on the same account."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    rows = [*CARD_TWO_IN_LEDGER, import_row(6, 0, outcome="skipped", title="PAGO TARJETA")]
    _engine(fake_client, {path.read_bytes(): rows}, mismatches=[DAY_0907])

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no result screen")
        assert _imports(fake_client) == [True, False]
        assert _lines_shown(result) == [
            "✓ 2 rows imported · BCP Signature   new ones under @Pendiente and #Pendiente",
            "5 rows · 2 new · 2 in the ledger · 1 took the bank's title",
            "1 skipped",
        ]
        assert _shown(result) == {"escape": "Back", "enter": "Home"}
        (_, dry), (_, applied) = fake_client.posts
        assert applied == {**dry, "dry_run": False}

    run_app(scenario, size=(120, 40))


def test_a_repeated_enter_on_the_preview_sends_one_apply(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})
    answer = fake_client.post
    release = threading.Event()

    def held(path, json_body=None):
        if not json_body["dry_run"]:
            release.wait(timeout=5)  # the apply is still on its way
        return answer(path, json_body)

    fake_client.post = held

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        await pilot.press("enter", "enter", "enter")
        await pilot.pause()
        assert app.screen is preview and preview._writing
        assert "enter" not in _shown(preview)
        release.set()
        await _on(pilot, app, ImportResultScreen, "no result screen")
        assert _imports(fake_client) == [True, False]

    try:
        run_app(scenario, size=(120, 40))
    finally:
        release.set()


def test_esc_back_returns_to_a_cleared_bar_with_the_staged_rows(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        assert [e.line for e in screen._staged] == [LEDGER_LINE]
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no result screen")
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc Back did not return to the bar")
        assert app.screen is screen
        assert screen.query_one("#bar", Input).value == ""
        assert screen._files is None
        assert [e.line for e in screen._staged] == [LEDGER_LINE]
        assert not screen._staged[0].saved

    run_app(scenario, size=(120, 40))


def test_enter_home_goes_home_and_home_reads_fresh(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    stub_home_month(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})

    async def scenario(pilot, app):
        home = app.screen
        assert isinstance(home, HomeScreen)
        await wait_for(pilot, lambda: home._data is not None, message="home never loaded")
        home.action_older()  # a window and a cursor somewhere else
        await wait_for(pilot, lambda: home._data["end"] == home._end, message="window")
        home.query_one("#menu").highlighted = 3
        await pilot.press("plus")
        screen = await _on(pilot, app, LogBarScreen, "+ did not open the bar")
        await wait_for(pilot, lambda: screen._refs is not None, message="refs never loaded")
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no result screen")
        await pilot.press("enter")
        await _on(pilot, app, HomeScreen, "⏎ Home did not go home")
        assert app.screen is home
        assert home._end == home._today
        await wait_for(
            pilot, lambda: home._data and home._data["end"] == home._today, message="no re-read"
        )
        menu = home.query_one("#menu")
        enabled = [i for i in range(menu.option_count) if not menu.get_option_at_index(i).disabled]
        assert menu.highlighted == enabled[0]

    run_app(scenario, size=(120, 40))


def test_enter_home_with_unwritten_staged_rows_asks_first(fake_client, monkeypatch, tmp_path):
    from expense.tui.screens.modals import DiscardStagedModal

    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no result screen")
        await pilot.press("enter")
        await _on(pilot, app, DiscardStagedModal, "no discard question")
        await pilot.press("escape")  # keep the rows
        await _on(pilot, app, LogBarScreen, "the bar did not come back")
        assert [e.line for e in screen._staged] == [LEDGER_LINE]

    run_app(scenario, size=(120, 40))


# ---- several files -----------------------------------------------------------------
def test_two_files_go_one_after_the_other_then_home(fake_client, monkeypatch, tmp_path):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    _patch(monkeypatch)
    _engine(fake_client, {first.read_bytes(): CARD_ROWS, second.read_bytes(): CURRENT_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
        account = await _preview(pilot, app)
        assert "Import  ▸  file 1 of 2" in _crumb(account)
        assert _lines_shown(account)[0] == "Which account is this file?   Sueldo Soles (1).xlsx"
        assert _shown(account) == {"escape": "Cancel both", "enter": "Pick", "down": "Move"}
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _shown(preview) == {"escape": "Cancel both", "enter": "Import 4 rows"}
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no first result")
        assert _shown(result) == {"escape": "Back", "enter": "Next file"}

        await pilot.press("enter")
        account = await _preview(pilot, app)
        assert "Import  ▸  file 2 of 2" in _crumb(account)
        assert _lines_shown(account)[0] == "Which account is this file?   Cuenta Corriente.xlsx"
        await pilot.press("down", "enter")  # BCP PEN
        await _previewed(pilot, app)
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no second result")
        assert result is not None and "· BCP PEN" in _body(result)
        assert _shown(result) == {"escape": "Back", "enter": "Home"}
        sent = [(body["account_id"], body["file"]) for _, body in fake_client.posts]
        assert sent == [
            ("sig-pen", base64.b64encode(first.read_bytes()).decode()),
            ("sig-pen", base64.b64encode(first.read_bytes()).decode()),
            ("bcp-pen", base64.b64encode(second.read_bytes()).decode()),
            ("bcp-pen", base64.b64encode(second.read_bytes()).decode()),
        ]
        assert _imports(fake_client) == [True, False, True, False]
        await pilot.press("enter")
        await _on(pilot, app, HomeScreen, "⏎ Home did not go home")

    run_app(scenario, size=(120, 40))


def test_esc_on_the_first_file_cancels_both(fake_client, monkeypatch, tmp_path):
    files = [_bank_file(tmp_path, f"{name}.xlsx") for name in ("Uno", "Dos", "Tres")]
    _patch(monkeypatch)
    _engine(fake_client, {p.read_bytes(): CARD_ROWS for p in files})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, *files[:2])
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc did not return to the bar")
        await pilot.pause()
        assert app.screen is screen and preview is not app.screen
        assert _imports(fake_client) == [True]  # the first file's dry run; nothing written
        assert screen.query_one("#bar", Input).value == ""

        # three files: the word is `all`
        await _drop(pilot, screen, *files)
        account = await _preview(pilot, app)
        assert _shown(account) == {"escape": "Cancel all", "enter": "Pick", "down": "Move"}

    run_app(scenario, size=(120, 40))


def test_a_refused_file_with_a_file_to_come_still_cancels_both(fake_client, monkeypatch, tmp_path):
    """A refusal leaves `esc` stopping this file and the ones after it, so its
    word still counts them."""
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    _patch(monkeypatch)
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR", "stand-in", {"file": "words."}, 422, {}, {"file": "EMPTY"}
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _refused(pilot, app)
        assert _shown(preview) == {"escape": "Cancel both"}

    run_app(scenario, size=(120, 40))


def test_nothing_new_with_a_file_to_come_moves_on_without_writing(
    fake_client, monkeypatch, tmp_path
):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    _patch(monkeypatch)
    # the card's four rows are in the ledger already; the second file's one is new
    matched = [{**r, "outcome": "matched", "rule": "operation_code"} for r in CARD_ROWS]
    _engine(fake_client, {first.read_bytes(): matched, second.read_bytes(): CURRENT_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert "nothing to import" in _body(preview)
        assert _shown(preview) == {"escape": "Cancel both", "enter": "Next file"}
        await pilot.press("enter")
        account = await _preview(pilot, app)
        assert account is not preview
        assert "Import  ▸  file 2 of 2" in _crumb(account)
        assert _imports(fake_client) == [True]  # the dry run only; nothing written
        assert _shown(account) == {"escape": "Cancel", "enter": "Pick", "down": "Move"}
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 1 row"}

    run_app(scenario, size=(120, 40))


def test_nothing_new_on_the_last_of_several_files_goes_back_only(
    fake_client, monkeypatch, tmp_path
):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    _patch(monkeypatch)
    # the card's rows are new; the second file's one is in the ledger already
    matched = [{**CURRENT_ROWS[0], "outcome": "matched", "rule": "operation_code"}]
    _engine(fake_client, {first.read_bytes(): CARD_ROWS, second.read_bytes(): matched})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no first result")
        await pilot.press("enter")
        await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        assert _lines_shown(preview)[-1] == "nothing to import"
        assert _shown(preview) == {"escape": "Back"}
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is preview
        assert _imports(fake_client) == [True, False, True]
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc Back did not return to the bar")
        assert _imports(fake_client) == [True, False, True]

    run_app(scenario, size=(120, 40))


def test_the_esc_word_counts_the_files_still_to_come(fake_client, monkeypatch, tmp_path):
    files = [_bank_file(tmp_path, f"{name}.xlsx") for name in ("Uno", "Dos", "Tres")]
    _patch(monkeypatch)
    _engine(fake_client, {p.read_bytes(): CARD_ROWS for p in files})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, *files)
        account = await _preview(pilot, app)
        assert _shown(account) == {
            "escape": "Cancel all",
            "enter": "Pick",
            "down": "Move",
        }  # 1 of 3
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no first result")
        await pilot.press("enter")
        account = await _preview(pilot, app)
        assert "Import  ▸  file 2 of 3" in _crumb(account)
        assert _shown(account) == {"escape": "Cancel both", "enter": "Pick", "down": "Move"}
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _shown(preview) == {"escape": "Cancel both", "enter": "Import 4 rows"}
        # esc on file 2 of 3 cancels it and file 3; file 1 stays imported
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc did not return to the bar")
        assert app.screen is screen
        assert preview._run.imported == 1
        assert _imports(fake_client) == [True, False, True]

    run_app(scenario, size=(120, 40))


# ---- edit + drop -----------------------------------------------------------------
def test_a_drop_onto_a_lifted_row_drops_the_edit_and_keeps_the_row(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD_ROWS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, LEDGER_LINE)
        screen.on_input_submitted()
        screen.action_move(1)
        screen.on_input_submitted()  # lift the picked row into the bar
        assert screen._editing == 0
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        assert screen._editing is None
        assert [e.line for e in screen._staged] == [LEDGER_LINE]
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc did not return to the bar")
        assert [e.line for e in screen._staged] == [LEDGER_LINE]
        assert str(screen.query_one("#field").content) == "LOG"
        assert fake_client.posts == []

    run_app(scenario, size=(120, 40))
