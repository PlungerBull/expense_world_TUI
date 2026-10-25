"""The import door — a bank file dropped on the LOG bar → account → preview → result.

The preview and the result are docs/mockups/expense-world-import-report.html
(1 A, 2 A and 3). Pure builders first, then pilot tests through the LOG bar the
way a drop arrives. The sheet reaches flow.py's reader through its `read_workbook` seam;
the one engine call,
`POST /transactions/import`, is answered by a fake on the shared FakeClient
that echoes each row's id and decides its outcome.
"""

import re
import threading

import pytest
from textual.widgets import Input, Static

from expense.bank_import import flow
from expense.bank_import.engine import AnswerCounts, DayMismatch, UnclaimedLine
from expense.bank_import.flow import FileLine, account_groups
from expense.errors import EngineError
from expense.import_.reader import RawRow, SheetData
from expense.tui.screens.bank_import import (
    ImportAccountScreen,
    ImportPreviewScreen,
    ImportResultScreen,
    account_lines,
    mark_cell,
    reason_cell,
    result_head,
)
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.log_bar import LogBarScreen
from expense.tui.theme import PALETTE
from tests.unit.helpers import (
    ENGINE_ORDER_ACCOUNTS,
    ENGINE_ORDER_BANK_NAMES,
    NO_STATEMENT,
    import_part,
    line_code_of,
    render_text,
    run_app,
    stub_home_month,
    wait_for,
    whole,
)

ACCOUNTS = [
    {
        "id": "sig-pen",
        "name": "BCP Signature PEN",
        "currency_code": "PEN",
        "is_person": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
    {
        "id": "sig-usd",
        "name": "BCP Signature USD",
        "currency_code": "USD",
        "is_person": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
    {
        "id": "bcp-pen",
        "name": "BCP PEN",
        "currency_code": "PEN",
        "is_person": False,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
    {
        "id": "old",
        "name": "Retired PEN",
        "currency_code": "PEN",
        "is_person": False,
        "is_archived": True,
        "opening_balance_transaction_id": None,
        "statement_code": None,
    },
]
HEADERS = ["Fecha", "Descripcion", "Moneda", "Monto"]
CARD_ROWS = [
    ("2026-09-11", "EDO SUSHI BAR             LI", "S/", -49),
    ("2026-09-09", "APPLE.COM/BILL", "$", -21.17),
    ("2026-09-08", "UBER TRIP", "S/", -4.2),
    ("2026-09-07", "APPARKA MALL AVENTURA  AREQU", "S/", -3.5),
]
LEDGER_LINE = "tottus porongoche -38.60 $BCP Signature PEN"
PART_1 = import_part("t-1", -350)
DAY_0907 = {
    "account_id": "sig-pen",
    "date": "2026-09-07",
    "file_net_cents": -350,
    "ledger_net_cents": -700,
    "unmatched_rows": [3],
    "unclaimed_lines": [
        {
            "bank_line_id": "bl-1",
            "line_code": line_code_of("bl-1"),
            "net_cents": -350,
            "parts": [PART_1],
        }
    ],
}
#: DAY_0907 as the screens hold it.
PARSED_0907 = DayMismatch(
    account_id="sig-pen",
    account_name="BCP Signature PEN",
    date_iso="2026-09-07",
    file_net_cents=-350,
    ledger_net_cents=-700,
    unmatched_rows=(3,),
    unclaimed_lines=(UnclaimedLine("bl-1", -350, (PART_1,)),),
)
#: A purchase of 100 split 60 + 40 that no file row claimed: one line, two parts.
SPLIT_PARTS = [
    import_part("t-2a", -6000, line="bl-2", day="2026-09-08"),
    import_part("t-2b", -4000, line="bl-2", day="2026-09-08"),
]
DAY_0908_SPLIT = {
    "account_id": "sig-pen",
    "date": "2026-09-08",
    "file_net_cents": -420,
    "ledger_net_cents": -10420,
    "unmatched_rows": [],
    "unclaimed_lines": [
        {
            "bank_line_id": "bl-2",
            "line_code": line_code_of("bl-2"),
            "net_cents": -10000,
            "parts": SPLIT_PARTS,
        }
    ],
}
#: A day whose totals agree, reported for the ledger line no file row claimed:
#: a +50 and a -50 the file does not have.
EQUAL_PARTS = [
    import_part("t-3", 5000, line="bl-3", day="2026-09-11"),
    import_part("t-4", -5000, line="bl-4", day="2026-09-11"),
]
DAY_0911_EQUAL = {
    "account_id": "sig-pen",
    "date": "2026-09-11",
    "file_net_cents": -4900,
    "ledger_net_cents": -4900,
    "unmatched_rows": [],
    "unclaimed_lines": [
        {
            "bank_line_id": "bl-3",
            "line_code": line_code_of("bl-3"),
            "net_cents": 5000,
            "parts": EQUAL_PARTS[:1],
        },
        {
            "bank_line_id": "bl-4",
            "line_code": line_code_of("bl-4"),
            "net_cents": -5000,
            "parts": EQUAL_PARTS[1:],
        },
    ],
}


# ---- the seams ---------------------------------------------------------------
def _sheet(headers, rows) -> SheetData:
    return SheetData(headers=headers, rows=[RawRow(i + 2, list(r)) for i, r in enumerate(rows)])


def _feed(monkeypatch, sheets: dict) -> None:
    """Each dropped file's name → (headers, rows), read through the typed
    command's own reader seam."""
    from pathlib import Path

    def read(path, **_kw):
        headers, rows = sheets[Path(path).name]
        return _sheet(headers, rows)

    monkeypatch.setattr(flow, "read_workbook", read)


def _patch(monkeypatch) -> None:
    """The LOG bar's reference reads, its peek, and the account list."""
    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: whole(ACCOUNTS))
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_transactions", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.count_transactions", lambda *a, **k: 0)


def _engine(fake_client, decide=None, *, mismatches=None, counts=None):
    """Answer `POST /transactions/import` like the engine: every sent id back,
    with the outcome `decide(index, row)` gives (default new), and `counts`
    as the engine's (default: the outcomes counted). Every call is still
    recorded on the fake client."""
    record = fake_client.post

    def post(path, json_body=None):
        record(path, json_body)
        rows = []
        for i, row in enumerate(json_body["rows"]):
            result = {
                "id": row["id"],
                "outcome": "new",
                "rule": None,
                "bank_line_id": None,
                "backfill_code": None,
                "retitled": None,
                "redated": None,
                "redate_blocked_by": None,
                "sealed_by": None,
            }
            result.update((decide or (lambda i, r: {}))(i, row))
            rows.append(result)
        outcomes = [r["outcome"] for r in rows]
        counted = {
            "new": outcomes.count("new"),
            "matched": outcomes.count("matched"),
            "sealed": outcomes.count("sealed"),
            "backfilled": sum(1 for r in rows if r["backfill_code"]),
            "retitled": sum(1 for r in rows if r["retitled"]),
            "redated": sum(1 for r in rows if r["redated"]),
        }
        return {
            "dry_run": json_body["dry_run"],
            "rows": rows,
            "day_mismatches": mismatches or [],
            "counts": counts or counted,
        }

    fake_client.post = post


def _imports(fake_client) -> list[bool]:
    """The `dry_run` of every import call, in order."""
    return [body["dry_run"] for path, body in fake_client.posts if path == "/transactions/import"]


def _matched(rule):
    return {
        "outcome": "matched",
        "rule": rule,
        "bank_line_id": "bl-x",
        "retitled": False,
        "redated": False,
    }


def _two_new_two_in_ledger(i, _row):
    return {1: _matched("same_day"), 2: {**_matched("operation_code"), "retitled": True}}.get(i, {})


def _bank_file(tmp_path, name: str = "Sueldo Soles (1).xlsx"):
    path = tmp_path / name
    path.write_bytes(b"")
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


def _body(screen) -> str:
    return render_text(screen.query_one("#import-body", Static).content, width=120)


def _crumb(screen) -> str:
    return render_text(screen.query_one("#crumb", Static).render(), width=120)


def _days_shown(preview) -> list[str]:
    """The preview's lines from the days' `!` head down, each stripped."""
    lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
    start = next(i for i, line in enumerate(lines) if line.startswith("! ") and "day" in line)
    return lines[start:]


def _result_shown(result) -> list[str]:
    """The result's lines, each stripped, blanks left out."""
    return [line.strip() for line in _body(result).split("\n") if line.strip()]


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
    """From the account list: pick the cursor row, wait for the dry run."""
    account = await _on(pilot, app, ImportAccountScreen, "no account list")
    await wait_for(pilot, lambda: account._run.groups is not None, message="accounts not read")
    return account


async def _previewed(pilot, app) -> ImportPreviewScreen:
    preview = await _on(pilot, app, ImportPreviewScreen, "no preview")
    await wait_for(pilot, lambda: preview._placed is not None, message="dry run never answered")
    return preview


# ---- pure ----------------------------------------------------------------------
def test_a_cards_two_legs_fold_into_one_line():
    groups = account_groups(ACCOUNTS)
    lines = [line.plain.rstrip() for line in account_lines(groups, 0)]
    assert [line.split()[0:2] for line in lines] == [["BCP", "Signature"], ["BCP", "PEN"]]
    assert lines[0].endswith("PEN + USD")
    assert "Retired" not in " ".join(lines)  # archived: the typed import's list too
    assert lines[1].endswith("PEN")


def test_the_result_head_is_the_engines_new_count_and_where_the_rows_landed():
    """Screen 3's title line: the engine's `new`, the account, and the
    pending category and hashtag, dim."""
    group = account_groups(ACCOUNTS)[1]
    head = result_head(group, AnswerCounts(9, 5, 0, 0, 2, 1))
    assert head.plain == "✓ 9 rows imported · BCP PEN   new ones under @Pendiente and #Pendiente"
    assert result_head(group, AnswerCounts(1, 0, 0, 0, 0, 0)).plain.startswith(
        "✓ 1 row imported · BCP PEN"
    )


def _line(reason: str, kept: bool) -> FileLine:
    return FileLine(2, "2026-09-11", "X", -100, kept, reason)


@pytest.mark.parametrize(
    ("reason", "kept", "style"),
    [
        ("New", True, PALETTE.success),
        ("Already in the ledger", True, "dim"),
        ("Modified existing transaction", True, ""),
        ("Not moved: Septiembre 2026 is reconciled", False, PALETTE.warning),
        ("Closed period", False, PALETTE.warning),
        ("Before 2026", False, PALETTE.warning),
        ("Couldn't read the row", False, PALETTE.warning),
    ],
)
def test_each_reason_takes_its_style_and_its_mark(reason, kept, style):
    """A row in the ledger after the import is ✓; one left out is ✗ and its
    reason takes the warning style. Every style is the theme's."""
    line = _line(reason, kept)
    cell = reason_cell(line)
    assert (cell.plain, str(cell.style)) == (reason, style)
    mark = mark_cell(line)
    if kept:
        assert (mark.plain, str(mark.style)) == ("✓", PALETTE.success)
    else:
        assert (mark.plain, str(mark.style)) == ("✗", f"bold {PALETTE.error}")


# ---- screen 5 A: not a bank file -----------------------------------------------
def test_a_file_that_is_not_a_bank_export_stays_in_the_bar(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path, "presupuesto.xlsx")
    _patch(monkeypatch)
    _feed(monkeypatch, {"presupuesto.xlsx": (["Fecha", "Descripcion", "Moneda", "Total"], [])})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await pilot.pause()
        assert app.screen is screen
        hint = screen.query_one("#hint", Static).content
        assert hint.plain.split("\n") == [
            "not a BCP bank file · missing the column Monto",
            "it has: Fecha, Descripcion, Moneda, Total",
        ]
        assert _shown(screen) == {"escape": "Cancel"}
        await pilot.press("enter")  # ⏎ does nothing more
        await pilot.pause()
        assert app.screen is screen
        assert fake_client.calls == []  # nothing sent, not even the account list
        # the next keystroke is a new attempt
        _type(screen, "")
        assert screen._file_problem is None

    run_app(scenario)


def test_a_bad_second_file_stops_the_drop_before_the_first_starts(
    fake_client, monkeypatch, tmp_path
):
    good, bad = _bank_file(tmp_path), _bank_file(tmp_path, "presupuesto.xlsx")
    _patch(monkeypatch)
    _feed(
        monkeypatch,
        {
            good.name: (HEADERS, CARD_ROWS),
            bad.name: (["Mes", "Categoria", "Total"], []),
        },
    )
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, good, bad)
        await pilot.pause()
        assert app.screen is screen
        hint = screen.query_one("#hint", Static).content.plain.split("\n")
        assert hint == [
            "presupuesto.xlsx · not a BCP bank file · missing the columns "
            "Fecha, Descripcion, Moneda, Monto",
            "it has: Mes, Categoria, Total",
        ]
        assert fake_client.calls == []

    run_app(scenario)


# ---- screen 2: the account list -------------------------------------------------
def test_the_account_list_folds_a_card_and_names_the_file(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        assert "Capture & ledger  ▸  Import  ▸  Sueldo Soles (1).xlsx" in _crumb(account)
        body = _body(account).split("\n")
        assert body[0].strip() == (
            "Which account is this file?   4 movements · 2026-09-07 → 2026-09-11 · PEN + USD"
        )
        listed = [line.strip() for line in body[2:] if line.strip()]
        assert [line.split("  ")[0] for line in listed] == ["BCP Signature", "BCP PEN"]
        assert listed[0].endswith("PEN + USD")
        assert _shown(account) == {"escape": "Cancel", "enter": "Pick"}
        assert _imports(fake_client) == []  # nothing asked of the import yet
        await pilot.press("down")
        assert account._cursor == 1
        await pilot.press("up")
        assert account._cursor == 0

    run_app(scenario, size=(120, 40))


def test_the_account_list_shows_the_engines_order(fake_client, monkeypatch, tmp_path):
    """The "Which account is this file?" list shows the accounts exactly as
    `GET /accounts` returned them — not alphabetical, not by `sort_order`; the
    person is left out and nothing else moves."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    monkeypatch.setattr(
        "expense.reads.fetch_accounts", lambda *a, **k: whole(ENGINE_ORDER_ACCOUNTS)
    )
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        assert [group.base for group in account._groups] == ENGINE_ORDER_BANK_NAMES
        listed = [line.strip() for line in _body(account).split("\n")[2:] if line.strip()]
        assert [line.split("  ")[0] for line in listed] == ENGINE_ORDER_BANK_NAMES

    run_app(scenario, size=(120, 40))


def test_the_card_sends_each_row_to_the_leg_of_its_currency(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        (_, body), *_ = fake_client.posts
        assert body["dry_run"] is True
        legs = [(r["account_id"], r["amount_cents"]) for r in body["rows"]]
        assert legs == [
            ("sig-pen", -4900),
            ("sig-usd", -2117),
            ("sig-pen", -420),
            ("sig-pen", -350),
        ]

    run_app(scenario, size=(120, 40))


def test_a_currency_the_picked_account_has_no_leg_for_is_refused_on_the_list(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN: no USD leg
        await pilot.pause()
        assert app.screen is account
        assert account._refused[-1].plain == (
            "BCP holds PEN only, and this file has 1 row in USD. Pick the card that has "
            "both, or an account in that currency."
        )
        assert account._refused[-1].plain in " ".join(_body(account).split())
        assert fake_client.posts == []  # not even a dry run

    run_app(scenario, size=(160, 40))


def test_a_file_with_nothing_on_or_after_the_floor_is_refused_with_its_lines(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    rows = [
        ("2025-12-30", "UBER TRIP", "S/", -4.2),
        ("2026-09-08", "MYSTERY", "S/", "abc"),
    ]
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, rows)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        await pilot.pause()
        assert app.screen is account
        assert [line.plain for line in account._refused] == [
            '! row 3: "abc" is not an amount',
            "nothing to import — no row of this file is dated 2026-01-01 or later.",
        ]
        body = _body(account)
        assert '! row 3: "abc" is not an amount' in body
        assert "nothing to import — no row of this file is dated 2026-01-01 or later." in body
        assert fake_client.posts == []

    run_app(scenario, size=(160, 40))


# ---- screen 3: the preview --------------------------------------------------------
def test_the_preview_shows_verdicts_and_writes_nothing_before_enter(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, _two_new_two_in_ledger, mismatches=[DAY_0907])

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        body = _body(preview)
        lines = [line.rstrip() for line in body.split("\n")]
        assert lines[0].strip() == "Preview · BCP Signature · nothing written yet"
        # the mark's column has no heading, and the old `match` column is gone
        assert lines[2].split() == ["#", "date", "title", "amount", "reason"]
        rows = [line.split() for line in lines[3:7]]
        assert [r[0] for r in rows] == ["2", "3", "4", "5"]  # the file's own lines
        assert lines[3].endswith("✓  New")
        assert lines[4].endswith("✓  Already in the ledger")
        # the engine's `retitled`: the row takes the bank's title
        assert lines[5].endswith("✓  Modified existing transaction")
        assert lines[6].endswith("✓  New")
        assert lines[8] == "4 rows · 2 new · 2 in the ledger · 1 takes the bank's title"
        assert "match" not in body and "in ledger ·" not in body
        assert preview._mismatches == [PARSED_0907]
        assert preview._counts == AnswerCounts(
            new=2, matched=2, sealed=0, backfilled=0, retitled=1, redated=0
        )
        assert [p.retitled for p in preview._placed] == [None, False, True, None]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 2 rows"}
        assert _imports(fake_client) == [True]  # the dry run only

    run_app(scenario, size=(120, 40))


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
    ("day", "lines", "shown"),
    [
        (
            DAY_0908_SPLIT,
            [("bl-2", -10000, ("t-2a", "t-2b"))],
            [
                "! 1 day where the file and the ledger disagree",
                "2026-09-08 · BCP Signature PEN   file -4.20 · ledger after import -104.20",
                "TOTTUS PORONGOCHE  -60.00   in the ledger, not in the file",
                "TOTTUS PORONGOCHE  -40.00   in the ledger, not in the file",
            ],
        ),
        (
            DAY_0911_EQUAL,
            [("bl-3", 5000, ("t-3",)), ("bl-4", -5000, ("t-4",))],
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
    fake_client, monkeypatch, tmp_path, day, lines, shown
):
    """A split line (one entry, two parts) and a day reported with equal totals:
    each part is its own row, its amount signed off the engine's magnitude and
    type, under the engine's two totals as sent. The preview holds each line's
    signed `net_cents` and its parts, and no transaction is read to fill them;
    the screen after importing shows no days (expense-world-import-report.html
    2 A and 3)."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, _two_new_two_in_ledger, mismatches=[day])

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        reads_made = _no_reads_per_part(monkeypatch)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _days_shown(preview) == shown
        (held,) = preview._mismatches
        assert (held.file_net_cents, held.ledger_net_cents) == (
            day["file_net_cents"],
            day["ledger_net_cents"],
        )
        assert [
            (u.bank_line_id, u.net_cents, tuple(p["id"] for p in u.parts))
            for u in held.unclaimed_lines
        ] == lines
        assert [list(u.parts) for u in held.unclaimed_lines] == [
            entry["parts"] for entry in day["unclaimed_lines"]
        ]
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no result screen")
        assert not any("disagree" in line or "TOTTUS" in line for line in _result_shown(result))
        assert reads_made == []
        assert [m for m, _ in fake_client.requests if m == "GET"] == []

    run_app(scenario, size=(120, 40))


def test_the_summary_and_the_footer_read_the_engines_counts(fake_client, monkeypatch, tmp_path):
    """Screen 1 A: the summary's verdict counts and `⏎ Import N rows` are the
    engine's `counts`, not the rows counted — here they disagree on purpose."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    counts = {"new": 7, "matched": 5, "sealed": 0, "backfilled": 0, "retitled": 3, "redated": 0}
    _engine(fake_client, _two_new_two_in_ledger, counts=counts)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
        assert lines[-1] == "4 rows · 7 new · 5 in the ledger · 3 take the bank's title"
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 7 rows"}
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no result screen")
        assert _result_shown(result) == [
            "✓ 7 rows imported · BCP Signature   new ones under @Pendiente and #Pendiente",
            "4 rows · 7 new · 5 in the ledger · 3 took the bank's title",
        ]

    run_app(scenario, size=(120, 40))


def test_a_reported_day_lists_the_file_rows_not_found_and_the_ledger_rows_not_claimed(
    fake_client, monkeypatch, tmp_path
):
    """Screen 2 B: the old "no file row matched" warning is gone; the day shows
    its two totals, the file's row by its line and the ledger's by title and
    signed amount."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, _two_new_two_in_ledger, mismatches=[DAY_0907])

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
        body = _body(preview)
        assert "no file row matched" not in body and "unmatched" not in body
        # the ledger row sits under the file row's title, not under its tag
        rows = [
            line for line in body.split("\n") if "not found" in line or "not in the file" in line
        ]
        assert rows[0].index("APPARKA") == rows[1].index("TOTTUS")
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 2 rows"}  # a report only

    run_app(scenario, size=(120, 40))


#: A card file's two accounts, one reported day each: the PEN leg's row 5 not
#: found, and on the USD leg a ledger row the file did not claim.
DAY_0909_USD = {
    "account_id": "sig-usd",
    "date": "2026-09-09",
    "file_net_cents": -2117,
    "ledger_net_cents": -4234,
    "unmatched_rows": [],
    "unclaimed_lines": [
        {
            "bank_line_id": "bl-9",
            "line_code": line_code_of("bl-9"),
            "net_cents": -2117,
            "parts": [
                import_part(
                    "t-9", -2117, account_id="sig-usd", line="bl-9", day="2026-09-09", title="Apple"
                )
            ],
        }
    ],
}


def test_a_card_files_days_name_their_account(fake_client, monkeypatch, tmp_path):
    """A card's two currencies are two accounts: every day on the preview
    names its account."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, _two_new_two_in_ledger, mismatches=[DAY_0907, DAY_0909_USD])

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
    rows = [("2026-09-12", "FARMACIA CENTRAL", "S/", -42.9), ("2026-09-11", "CINE", "S/", -28)]
    day = {
        "account_id": "bcp-pen",
        "date": "2026-09-12",
        "file_net_cents": -4290,
        "ledger_net_cents": -8490,
        "unmatched_rows": [0],
        "unclaimed_lines": [
            {
                "bank_line_id": "bl-f",
                "line_code": line_code_of("bl-f"),
                "net_cents": -4200,
                "parts": [
                    import_part(
                        "t-f",
                        -4200,
                        account_id="bcp-pen",
                        line="bl-f",
                        day="2026-09-12",
                        title="Farmacia",
                    )
                ],
            }
        ],
    }
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, rows)})
    _engine(fake_client, mismatches=[day])

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


#: A file with one row of each reason: lines 2–7 go to the engine; line 8 is
#: under the floor and line 9 the parser cannot read (its date).
EVERY_REASON_ROWS = [
    ("2026-10-14", "CAFE ANDINO LIMA PE", "S/", -18.5),
    ("2026-10-13", "UBER TRIP", "S/", -4.2),
    ("2026-10-07", "MERCADO NORTE", "S/", -61.3),
    ("2026-10-04", "WONG SAN ISIDRO", "S/", -100),
    ("2026-10-01", "TAMBO MIRAFLORES", "S/", -7.5),
    ("2026-08-29", "SHELL SAN ISIDRO", "S/", -120),
    ("2025-12-30", "RAPPI LIMA PE", "S/", -36.9),
    ("31/13/2026", "PLIN JUAN P.", "S/", -15.4),
]


def _every_reason(i, _row):
    """The engine's answer for EVERY_REASON_ROWS, by the index each was sent under."""
    return {
        1: _matched("same_day"),
        2: {**_matched("operation_code"), "retitled": True},
        3: {**_matched("operation_code"), "redated": True},
        4: {**_matched("operation_code"), "redate_blocked_by": "r-sep"},
        5: {"outcome": "sealed", "sealed_by": "r-aug"},
    }.get(i, {})


EVERY_REASON_COUNTS = {
    "new": 1,
    "matched": 4,
    "sealed": 1,
    "backfilled": 0,
    "retitled": 1,
    "redated": 1,
}


RECONCILIATIONS = {
    "r-aug": {"id": "r-aug", "name": "Agosto 2026", **NO_STATEMENT},
    "r-sep": {"id": "r-sep", "name": "Septiembre 2026", **NO_STATEMENT},
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


def test_every_row_of_the_file_shows_its_mark_and_its_reason(fake_client, monkeypatch, tmp_path):
    """expense-world-import-report.html 1 A: one table of the file's lines,
    numbered by the file's own line, the line under the floor and the
    unreadable one included, each with ✓ or ✗ and its reason alone. A move a
    completed reconciliation stops names that reconciliation, read once by its
    id in the worker; the counts add the engine's moved count,
    and the closed, pre-2026 and unreadable counts go on a line of their own."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    asked = _reconciliations(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, EVERY_REASON_ROWS)})
    _engine(fake_client, _every_reason, counts=EVERY_REASON_COUNTS)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
        assert lines[1].split() == ["#", "date", "title", "amount", "reason"]
        rows = [re.split(r"\s{2,}", line) for line in lines[2:10]]
        assert rows == [
            ["2", "2026-10-14", "CAFE ANDINO LIMA PE", "-18.50", "✓", "New"],
            ["3", "2026-10-13", "UBER TRIP", "-4.20", "✓", "Already in the ledger"],
            ["4", "2026-10-07", "MERCADO NORTE", "-61.30", "✓", "Modified existing transaction"],
            ["5", "2026-10-04", "WONG SAN ISIDRO", "-100.00", "✓", "Modified existing transaction"],
            [
                "6",
                "2026-10-01",
                "TAMBO MIRAFLORES",
                "-7.50",
                "✗",
                "Not moved: Septiembre 2026 is reconciled",
            ],
            ["7", "2026-08-29", "SHELL SAN ISIDRO", "-120.00", "✗", "Closed period"],
            ["8", "2025-12-30", "RAPPI LIMA PE", "-36.90", "✗", "Before 2026"],
            ["9", "—", "PLIN JUAN P.", "-15.40", "✗", "Couldn't read the row"],
        ]
        assert lines[10:] == [
            "8 rows · 1 new · 4 in the ledger · 1 moves to the bank's day · "
            "1 takes the bank's title",
            "1 closed · 1 before 2026 · 1 unreadable",
        ]
        # the second line sits under the first count, not under `8 rows`
        raw = [line for line in _body(preview).split("\n") if line.strip()]
        assert raw[-1].index("1 closed") == raw[-2].index("1 new")
        # the old notes are gone: no closed-period block, no floor or refused-line note
        body = _body(preview)
        assert "never go" not in body and "not sent" not in body and "! row" not in body
        # the reconciliation is named by one read of it by its id, in the worker
        assert asked == ["r-sep"]
        preview._repaint()
        await pilot.resize_terminal(130, 40)
        await pilot.pause()
        assert asked == ["r-sep"]  # drawing the screen again reads nothing
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 1 row"}

    run_app(scenario, size=(120, 40))


def test_no_reconciliation_is_read_when_no_move_is_stopped(fake_client, monkeypatch, tmp_path):
    """A closed period's row says `Closed period` alone, so nothing is read to
    name it; and with no move, the counts say nothing of the bank's day."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    asked = _reconciliations(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    counts = {"new": 3, "matched": 0, "sealed": 1, "backfilled": 0, "retitled": 0, "redated": 0}
    _engine(
        fake_client,
        lambda i, r: {"outcome": "sealed", "sealed_by": "r-aug"} if i == 0 else {},
        counts=counts,
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
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
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(
        fake_client,
        lambda i, r: {**_matched("operation_code"), "redate_blocked_by": "r-sep"} if i == 0 else {},
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
        assert lines[2].endswith("✗  Not moved: a reconciliation is reconciled")
        assert any(
            line.startswith("! could not read the reconciliations' names:") for line in lines
        )
        assert asked == ["r-sep"]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Import 3 rows"}

    run_app(scenario, size=(120, 40))


def test_the_screen_after_importing_gives_the_counts_alone_in_the_past_tense(
    fake_client, monkeypatch, tmp_path
):
    """expense-world-import-report.html 3: the title line and the engine's
    counts, the moved count among them, in the past tense; no table and no
    days, though the apply reported one."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _reconciliations(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, EVERY_REASON_ROWS)})
    day = {**DAY_0907, "account_id": "bcp-pen", "unmatched_rows": []}
    _engine(fake_client, _every_reason, mismatches=[day], counts=EVERY_REASON_COUNTS)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("down", "enter")  # BCP PEN
        preview = await _previewed(pilot, app)
        assert "! 1 day where the file and the ledger disagree" in _body(preview)
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no result screen")
        assert _result_shown(result) == [
            "✓ 1 row imported · BCP PEN   new ones under @Pendiente and #Pendiente",
            "8 rows · 1 new · 4 in the ledger · 1 moved to the bank's day · "
            "1 took the bank's title",
            "1 closed · 1 before 2026 · 1 unreadable",
        ]
        assert _shown(result) == {"escape": "Back", "enter": "Home"}

    run_app(scenario, size=(120, 40))


def test_the_counts_say_how_many_move_in_the_plural(fake_client, monkeypatch, tmp_path):
    """`2 move to the bank's day` on the preview, the engine's number."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    counts = {"new": 2, "matched": 2, "sealed": 0, "backfilled": 0, "retitled": 0, "redated": 2}
    _engine(fake_client, _two_new_two_in_ledger, counts=counts)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
        assert lines[-1] == "4 rows · 2 new · 2 in the ledger · 2 move to the bank's day"

    run_app(scenario, size=(120, 40))


def test_a_row_changed_while_the_import_ran_previews_again_before_any_write(
    fake_client, monkeypatch, tmp_path
):
    """Screen 4 A: the apply's `409 CONFLICT` with `CONCURRENT_CHANGE` on
    `rows.<index>` shows the engine's words with the file's line, and `⏎ Preview
    again` asks for a fresh dry run; the next apply waits for its own `⏎`."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, _two_new_two_in_ledger)
    words = "Another request changed this row's ledger line. Send it again."

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        fake_client.errors["POST"] = EngineError(
            "CONFLICT",
            "The ledger changed while the import ran.",
            {"rows.2": words},
            409,
            {},
            {"rows.2": "CONCURRENT_CHANGE"},
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
            f"! row 4: {words}",  # the file's line for the engine's index 2
            "Nothing was written.",
            "",
            "It changed while the import ran: ⏎ checks the file against the ledger again.",
        ]
        assert str(list(app._notifications)[-1].message) == (
            "CONFLICT — The ledger changed while the import ran.\n"
            f"  rows.2: {words}\n\n"
            "It changed while the import ran: ⏎ checks the file against the ledger again."
        )
        assert _shown(preview) == {"escape": "Cancel", "enter": "Preview again"}
        assert _imports(fake_client) == [True, False]

        del fake_client.errors["POST"]
        await pilot.press("enter")  # a fresh dry run, never the apply
        await wait_for(
            pilot, lambda: preview._placed is not None, message="the preview did not run again"
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
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

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
        assert "It changed at the same moment: save again." in _body(preview)
        assert _shown(preview) == {"escape": "Cancel"}
        await pilot.press("enter")
        await pilot.pause()
        assert _imports(fake_client) == [True, False]

    run_app(scenario, size=(120, 40))


def test_the_preview_pages_with_pgdn(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    rows = [(f"2026-09-{d:02d}", f"SHOP {d}", "S/", -d) for d in range(1, 29)]
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, rows)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        size = preview._page_size()
        assert size < 28
        assert f"… {28 - size} more · pgdn" in _body(preview)
        await pilot.press("pagedown")
        assert preview._start == size
        await pilot.press("pageup")
        assert preview._start == 0

    run_app(scenario, size=(120, 30))


def test_an_engine_refusal_on_the_preview_is_shown_and_nothing_follows(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    fake_client.errors["POST"] = EngineError(
        "VALIDATION_ERROR", "Invalid rows", {"rows.1.amount_cents": "must not be 0"}, 422, {}
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _on(pilot, app, ImportPreviewScreen, "no preview")
        await wait_for(pilot, lambda: bool(preview._failure), message="no failure shown")
        body = _body(preview)
        assert "VALIDATION_ERROR — Invalid rows" in body
        assert "! row 3 (amount_cents): must not be 0" in body  # the file's line
        assert "Nothing was written." in body
        assert _shown(preview) == {"escape": "Cancel"}
        await pilot.press("enter")
        await pilot.pause()
        assert len(fake_client.posts) == 1  # the refused dry run, nothing after

    run_app(scenario, size=(120, 40))


# ---- screen 6 A: nothing new -----------------------------------------------------
def test_nothing_new_shows_the_preview_and_enter_writes_nothing(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, lambda i, r: _matched("operation_code"))

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
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


# ---- apply and screen 4 B ----------------------------------------------------------
def test_apply_writes_once_and_the_result_says_what_to_check(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client, _two_new_two_in_ledger, mismatches=[DAY_0907])

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no result screen")
        assert _imports(fake_client) == [True, False]
        # its title line and the counts, in the past tense: no table, no days
        assert _result_shown(result) == [
            "✓ 2 rows imported · BCP Signature   new ones under @Pendiente and #Pendiente",
            "4 rows · 2 new · 2 in the ledger · 1 took the bank's title",
        ]
        assert _shown(result) == {"escape": "Back", "enter": "Home"}
        # the two calls are one logical write each: the same rows, the same ids
        (_, dry), (_, applied) = fake_client.posts
        assert [r["id"] for r in dry["rows"]] == [r["id"] for r in applied["rows"]]

    run_app(scenario, size=(120, 40))


def test_a_repeated_enter_on_the_preview_sends_one_apply(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)
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


def test_an_engine_error_on_apply_is_shown_and_nothing_more_is_sent(
    fake_client, monkeypatch, tmp_path
):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        fake_client.errors["POST"] = EngineError(
            "PERIOD_LOCKED", "The period is completed.", None, 409, {}
        )
        await pilot.press("enter")
        # the toast is a message to the app: it lands a moment after the screen shows the failure
        await wait_for(
            pilot,
            lambda: bool(preview._failure) and bool(app._notifications),
            message="no failure shown, or no toast",
        )
        assert "PERIOD_LOCKED" in _body(preview)
        assert any("PERIOD_LOCKED" in str(n.message) for n in app._notifications)
        assert _shown(preview) == {"escape": "Cancel"}
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is preview
        assert len(fake_client.posts) == 2  # the dry run and the refused apply

    run_app(scenario, size=(120, 40))


@pytest.mark.parametrize(
    ("key", "reason", "line"),
    [
        (
            "rows.0.operation_code",
            "OPERATION_CODE_EXISTS",
            "That account already has a row with this operation number: "
            "look there for a duplicate.",
        ),
        ("category_id", "CONCURRENT_CHANGE", "It changed at the same moment: save again."),
        (
            "category_id",
            "RESERVED_NAME_HELD",
            "One of your categories has a built-in category's name: "
            "rename it on Manage ▸ Categories, then save again.",
        ),
        (
            "rows.0.id",
            "ID_EXISTS",
            "Not your mistake: the app sent it wrong and nothing was saved. "
            "Try again; if it happens again, report it.",
        ),
    ],
    ids=["screen-4", "screen-5A", "screen-6B", "screen-9A"],
)
def test_a_refused_import_shows_the_engine_words_and_what_to_do(
    fake_client, monkeypatch, tmp_path, key, reason, line
):
    """`POST /transactions/import` refuses keyed by the row (`rows.<i>.…`) or by
    the system category (contract: "Error reasons"): the note and the screen show
    the engine's words, then the line, where `⏎` is how this screen saves again."""
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)
    expected = f"CONFLICT — stand-in\n  {key}: stand-in field words\n\n{line}"

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _preview(pilot, app)
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        fake_client.errors["POST"] = EngineError(
            "CONFLICT", "stand-in", {key: "stand-in field words"}, 409, {}, {key: reason}
        )
        await pilot.press("enter")
        # the toast is a message to the app: it lands a moment after the screen shows the failure
        await wait_for(
            pilot,
            lambda: bool(preview._failure) and bool(app._notifications),
            message="no failure shown, or no toast",
        )
        assert [str(t) for t in preview._failure] == [expected]
        assert [str(n.message) for n in app._notifications][-1] == expected

    run_app(scenario, size=(120, 40))


def test_esc_back_returns_to_a_cleared_bar_with_the_staged_rows(fake_client, monkeypatch, tmp_path):
    path = _bank_file(tmp_path)
    _patch(monkeypatch)
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

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
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    stub_home_month(monkeypatch)
    _engine(fake_client)

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
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

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


# ---- screen 7 B: several files -----------------------------------------------------
def test_two_files_go_one_after_the_other_then_home(fake_client, monkeypatch, tmp_path):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    _patch(monkeypatch)
    _feed(
        monkeypatch,
        {
            first.name: (HEADERS, CARD_ROWS),
            second.name: (HEADERS, [("2026-09-12", "PAGO PLANILLA", "S/", 6519)]),
        },
    )
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
        account = await _preview(pilot, app)
        assert "Import  ▸  file 1 of 2" in _crumb(account)
        body = [line.strip() for line in _body(account).split("\n")]
        assert body[:2] == ["Which account is this file?", "Sueldo Soles (1).xlsx · 4 movements"]
        assert _shown(account) == {"escape": "Cancel both", "enter": "Pick"}
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert _shown(preview) == {"escape": "Cancel both", "enter": "Import 4 rows"}
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no first result")
        assert _shown(result) == {"escape": "Back", "enter": "Next file"}

        await pilot.press("enter")
        account = await _preview(pilot, app)
        assert "Import  ▸  file 2 of 2" in _crumb(account)
        assert "Cuenta Corriente.xlsx · 1 movement" in _body(account)
        await pilot.press("down", "enter")  # BCP PEN
        await _previewed(pilot, app)
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no second result")
        assert result is not None and "· BCP PEN" in _body(result)
        assert _shown(result) == {"escape": "Back", "enter": "Home"}
        assert _imports(fake_client) == [True, False, True, False]
        await pilot.press("enter")
        await _on(pilot, app, HomeScreen, "⏎ Home did not go home")

    run_app(scenario, size=(120, 40))


def test_esc_on_the_first_file_cancels_both(fake_client, monkeypatch, tmp_path):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    third = _bank_file(tmp_path, "Otra.xlsx")
    _patch(monkeypatch)
    _feed(monkeypatch, {p.name: (HEADERS, CARD_ROWS) for p in (first, second, third)})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, first, second)
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
        await _drop(pilot, screen, first, second, third)
        account = await _preview(pilot, app)
        assert _shown(account) == {"escape": "Cancel all", "enter": "Pick"}

    run_app(scenario, size=(120, 40))


def test_nothing_new_with_a_file_to_come_moves_on_without_writing(
    fake_client, monkeypatch, tmp_path
):
    first = _bank_file(tmp_path)
    second = _bank_file(tmp_path, "Cuenta Corriente.xlsx")
    _patch(monkeypatch)
    _feed(
        monkeypatch,
        {
            first.name: (HEADERS, CARD_ROWS),
            second.name: (HEADERS, [("2026-09-12", "PAGO PLANILLA", "S/", 6519)]),
        },
    )
    # the card's four rows are in the ledger already; the second file's one is new
    _engine(
        fake_client, lambda i, r: _matched("operation_code") if r["account_id"] != "bcp-pen" else {}
    )

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
        assert _shown(account) == {"escape": "Cancel", "enter": "Pick"}
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
    _feed(
        monkeypatch,
        {
            first.name: (HEADERS, CARD_ROWS),
            second.name: (HEADERS, [("2026-09-12", "PAGO PLANILLA", "S/", 6519)]),
        },
    )
    # the card's rows are new; the second file's one is in the ledger already
    _engine(
        fake_client, lambda i, r: _matched("operation_code") if r["account_id"] == "bcp-pen" else {}
    )

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
        lines = [line.strip() for line in _body(preview).split("\n") if line.strip()]
        assert lines[-1] == "nothing to import"
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
    _feed(monkeypatch, {p.name: (HEADERS, CARD_ROWS) for p in files})
    _engine(fake_client)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, *files)
        account = await _preview(pilot, app)
        assert _shown(account) == {"escape": "Cancel all", "enter": "Pick"}  # 1 of 3
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, ImportResultScreen, "no first result")
        await pilot.press("enter")
        account = await _preview(pilot, app)
        assert "Import  ▸  file 2 of 3" in _crumb(account)
        assert _shown(account) == {"escape": "Cancel both", "enter": "Pick"}
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
    _feed(monkeypatch, {path.name: (HEADERS, CARD_ROWS)})
    _engine(fake_client)

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
