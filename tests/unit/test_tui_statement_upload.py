"""The statement upload — a statement PDF dropped on the LOG bar → account → preview → close.

The screens are A1 and A2 of docs/mockups/expense-world-statement-pdf-upload.html
and 1 to 3 and 6A of docs/mockups/expense-world-statement-pdf-screens.html. A
dropped PDF is a few made-up bytes: the app sends them whole and reads nothing in
them, and the one engine call, `POST /statements/import`, is answered by a fake
on the shared FakeClient that reads the file it was sent and answers that paper
(`statement_upload_answer`); one test goes through the real HTTP client
against respx, for the idempotency key.
"""

import base64
import json
import re
import threading

import httpx
import pytest
import respx
from textual.widgets import Static

from expense.bank_import.flow import account_picks, statement_call
from expense.bank_import.statement import statement_answer
from expense.errors import EngineError
from expense.tui.dropped import dropped_bank_files, is_statement
from expense.tui.screens.bank_import import (
    ImportAccountScreen,
    ImportPreviewScreen,
    ImportResultScreen,
)
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.log_bar import LogBarScreen, bank_files_hint
from expense.tui.screens.reconciliations import FlaggedLinesScreen
from expense.tui.screens.statement_upload import (
    Columns,
    StatementAccountScreen,
    StatementPreviewScreen,
    StatementResultScreen,
    row_lines,
)
from tests.unit.helpers import (
    ENGINE_URL,
    FakeClient,
    account_record,
    bank_line_row,
    import_answer,
    import_part,
    import_row,
    render_text,
    run_app,
    statement_row,
    statement_upload_answer,
    upload_balance,
    wait_for,
    whole,
)

#: The card's dollar account first, so its line stands there and still sends the
#: soles one; then a savings account and cash, each alone on its holder.
ACCOUNTS = [
    account_record(id="sig-usd", name="BCP Signature USD", currency_code="USD", holder_id="h-sig"),
    account_record(id="sig-pen", name="BCP Signature PEN", holder_id="h-sig"),
    account_record(id="aho-pen", name="Sueldo Soles", holder_id="h2"),
    account_record(id="cash", name="Efectivo", holder_id="h3"),
]

#: A card's paper as screen 1A draws it: both currencies, matched, new and empty
#: rows, a near miss under a new row, and two undated fees.
CARD_ROWS = [
    statement_row(1, -750, day="2026-09-24", description="TAMBO MIRAFLORES"),
    statement_row(2, -8430, day="2026-09-27", description="PLAZA VEA SURCO"),
    statement_row(
        3,
        -4200,
        outcome="new",
        day="2026-10-02",
        description="UBER *TRIP",
        near_misses=(("bl-near", "2026-10-03"),),
    ),
    statement_row(4, -4490, day="2026-10-14", description="NETFLIX.COM"),
    statement_row(5, 80000, day="2026-10-20", description="PAGO TARJETA"),
    statement_row(
        6, -2499, account_id="sig-usd", currency="USD", day="2026-10-05", description="AMAZON"
    ),
    statement_row(
        7,
        -599,
        outcome="new",
        account_id="sig-usd",
        currency="USD",
        day="2026-10-24",
        description="SPOTIFY P2F3",
    ),
    statement_row(8, -1240, outcome="new", fee=True, day="2026-10-25", description="INTERESES"),
    statement_row(
        9, -690, outcome="new", fee=True, day="2026-10-25", description="SEGURO DE DESGRAVAMEN"
    ),
    statement_row(
        10,
        0,
        outcome="empty",
        account_id="sig-usd",
        currency="USD",
        day="2026-10-25",
        description="MANT. CUENTA",
    ),
]
#: The card's balances, one per account of its holder in the accounts' order, as
#: the engine sends them: the dollar account first, as ACCOUNTS lists it.
USD_BALANCE = upload_balance("sig-usd", "USD", begin=-3642, end=-6140)
PEN_BALANCE = upload_balance()
CARD = {
    "rows": CARD_ROWS,
    "balances": [USD_BALANCE, PEN_BALANCE],
    "taken_out": ["bl-farm"],
}

#: A savings account's paper as screen 1B draws it: one currency, its open draft
#: filled, nothing taken out.
SAVINGS = {
    "rows": [
        statement_row(1, 485000, account_id="aho-pen", day="2026-10-01", description="HABERES"),
        statement_row(2, -80000, account_id="aho-pen", day="2026-10-03", description="TRANSF"),
        statement_row(3, -12000, account_id="aho-pen", day="2026-10-09", description="YAPE"),
        statement_row(
            4, -40000, outcome="new", account_id="aho-pen", day="2026-10-15", description="CAJERO"
        ),
        statement_row(5, -19240, account_id="aho-pen", day="2026-10-28", description="LUZ"),
        statement_row(
            6, 0, outcome="empty", account_id="aho-pen", day="2026-10-30", description="INTERES"
        ),
    ],
    "name": "Octubre 2026",
    "date_start": "2026-10-01",
    "date_end": "2026-10-31",
    "creates": False,
    "statement_id": "s-oct",
    "balances": [upload_balance("aho-pen", begin=1091240, end=1245000)],
}

#: The ledger lines the card's answer names by id alone: the near miss and the
#: line taken out.
LINES = {
    "bl-near": bank_line_row(
        "bl-near",
        [import_part("t-near", -4200, line="bl-near", day="2026-10-03", title="UBER *TRIP")],
        net_cents=-4200,
    ),
    "bl-farm": bank_line_row(
        "bl-farm",
        [import_part("t-farm", -4290, line="bl-farm", day="2026-10-11", title="FARMACIA CENTRAL")],
        net_cents=-4290,
    ),
}


# ---- the seams ---------------------------------------------------------------
def _patch(
    monkeypatch, lines: dict | None = None, accounts: list[dict] | None = None
) -> list[list[str]]:
    """The LOG bar's reference reads, its peek, the account list (ACCOUNTS
    unless `accounts` is given) and the lines read by their ids; returns the ids
    of each read by ids."""
    listed = whole(ACCOUNTS if accounts is None else accounts)
    served = LINES if lines is None else lines
    reads_by_ids: list[list[str]] = []

    def by_ids(cfg, ids, **kwargs):
        reads_by_ids.append(list(ids))
        return [served[i] for i in ids if i in served]

    monkeypatch.setattr("expense.reads.fetch_accounts", lambda *a, **k: listed)
    monkeypatch.setattr("expense.reads.fetch_categories", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_hashtags", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.fetch_transactions", lambda *a, **k: whole([]))
    monkeypatch.setattr("expense.reads.count_transactions", lambda *a, **k: 0)
    monkeypatch.setattr("expense.reads.fetch_bank_lines_by_ids", by_ids)
    monkeypatch.setattr(
        "expense.tui.screens.reconciliations.load_account_name_map",
        lambda: {"sig-pen": "BCP Signature PEN", "sig-usd": "BCP Signature USD"},
    )
    return reads_by_ids


def _engine(fake_client: FakeClient, papers: dict, downloads: dict | None = None) -> None:
    """Answer like the engine: a statement upload reads the PDF it was sent
    (`papers`: a file's bytes → the answer's parts) and answers that paper; a
    download's import answers its rows (`downloads`). Every call is still
    recorded on the fake client."""
    record = fake_client.post

    def post(path, json_body=None):
        record(path, json_body)
        sent = base64.b64decode(json_body["file"])
        if path == "/statements/import":
            return statement_upload_answer(**papers[sent], dry_run=json_body["dry_run"])
        return import_answer((downloads or {})[sent], dry_run=json_body["dry_run"])

    fake_client.post = post


def _uploads(fake_client) -> list[bool]:
    """The `dry_run` of every statement upload, in order."""
    return [b["dry_run"] for path, b in fake_client.posts if path == "/statements/import"]


def _pdf(tmp_path, name: str = "BCP Visa 1492 2026-10.pdf"):
    """A dropped statement: made-up bytes, its own name in them so two differ."""
    path = tmp_path / name
    path.write_bytes(f"%PDF-1.4 made-up statement {name}".encode())
    return path


def _xlsx(tmp_path, name: str = "Movimientos.xlsx"):
    path = tmp_path / name
    path.write_bytes(f"made-up download {name}".encode())
    return path


def _escaped(path) -> str:
    """What Terminal.app types for a drop."""
    return "".join("\\" + c if c in " ()" else c for c in str(path))


def _footer(screen) -> list[str]:
    """The footer's entries, in order, as `key Description`."""
    return [
        f"{screen.app.get_key_display(a.binding)} {a.binding.description}"
        for a in screen.active_bindings.values()
        if a.binding.show and a.enabled
    ]


def _shown(screen) -> dict[str, str]:
    return {
        key: active.binding.description
        for key, active in screen.active_bindings.items()
        if active.binding.show and active.enabled
    }


def _body(screen, width: int = 120) -> str:
    return render_text(screen.query_one("#import-body", Static).content, width=width)


def _crumb(screen) -> str:
    return render_text(screen.query_one("#crumb", Static).render(), width=160)


def _lines(screen, width: int = 120) -> list[str]:
    """The screen's lines, each stripped, blanks left out."""
    return [line.strip() for line in _body(screen, width).split("\n") if line.strip()]


def _cells(line: str) -> list[str]:
    return re.split(r"\s{2,}", line.strip())


async def _open(app, pilot) -> LogBarScreen:
    screen = LogBarScreen()
    await app.push_screen(screen)
    await wait_for(pilot, lambda: screen._refs is not None, message="refs never loaded")
    return screen


def _type(screen, text) -> None:
    from textual.widgets import Input

    bar = screen.query_one("#bar", Input)
    bar.value = text
    bar.cursor_position = len(text)
    screen.on_input_changed(Input.Changed(bar, text))


async def _drop(pilot, screen, *paths) -> None:
    _type(screen, " ".join(_escaped(p) for p in paths))
    await pilot.pause()
    await pilot.press("enter")


async def _on(pilot, app, kind, message: str):
    await wait_for(pilot, lambda: isinstance(app.screen, kind), message=message)
    return app.screen


async def _accounts(pilot, app, kind=StatementAccountScreen):
    account = await _on(pilot, app, kind, "no account list")
    await wait_for(pilot, lambda: account._run.picks is not None, message="accounts not read")
    return account


async def _previewed(pilot, app) -> StatementPreviewScreen:
    preview = await _on(pilot, app, StatementPreviewScreen, "no preview")
    await wait_for(pilot, lambda: preview._answer is not None, message="dry run never answered")
    return preview


async def _refused(pilot, app) -> StatementPreviewScreen:
    preview = await _on(pilot, app, StatementPreviewScreen, "no preview")
    await wait_for(pilot, lambda: bool(preview._failure), message="no failure shown")
    return preview


async def _card_preview(pilot, app, path) -> StatementPreviewScreen:
    """Drop the card's PDF, pick the card's line (the first), wait for the dry run."""
    screen = await _open(app, pilot)
    await _drop(pilot, screen, path)
    await _accounts(pilot, app)
    await pilot.press("enter")
    return await _previewed(pilot, app)


def _refusal(code, key, words, reason, status=422, message="The statement cannot be uploaded."):
    return EngineError(code, message, {key: words}, status, {}, {key: reason})


# ---- pure ------------------------------------------------------------------------
def test_a_pdf_is_a_dropped_file_and_a_statement_by_its_name(tmp_path):
    pdf = _pdf(tmp_path, "Estado.PDF")
    xlsx = _xlsx(tmp_path)
    assert dropped_bank_files(f"{_escaped(xlsx)} {_escaped(pdf)}") == [xlsx, pdf]
    assert is_statement(pdf) and not is_statement(xlsx)
    other = tmp_path / "notes.txt"
    other.write_bytes(b"")
    assert dropped_bank_files(f"{_escaped(pdf)} {_escaped(other)}") is None


def test_the_call_sends_exactly_three_keys_on_the_cards_soles_account():
    """The body is the download's: `dry_run`, the picked account (a card's soles
    one) and the file's bytes in standard base64
    (contract: POST /v1/statements/import)."""
    client = FakeClient()
    data = bytes(range(256)) * 50
    card = account_picks(ACCOUNTS)[0]
    statement_call(client, card, data, dry_run=True)
    ((path, body),) = client.posts
    assert path == "/statements/import"
    assert body == {
        "dry_run": True,
        "account_id": "sig-pen",
        "file": base64.b64encode(data).decode("ascii"),
    }


def test_the_answer_reads_as_the_engine_sent_it():
    answer = statement_answer(statement_upload_answer(**CARD, dry_run=True))
    assert (answer.name, answer.date_start, answer.date_end) == (
        "SIG-202610",
        "2026-09-26",
        "2026-10-25",
    )
    assert [r.amount_cents for r in answer.rows[:5]] == [-750, -8430, -4200, -4490, 80000]
    assert answer.rows[9].amount_cents == 0 and answer.rows[9].outcome == "empty"
    assert answer.rows[7].fee and not answer.rows[0].fee
    assert answer.several_currencies and not answer.fills_a_draft
    assert answer.lines_to_read() == ["bl-farm", "bl-near"]
    assert (answer.counts.matched, answer.counts.new, answer.counts.empty) == (5, 4, 1)
    assert answer.counts.taken_out == 1 and answer.counts.rows == 10


# ---- A1 · the PDF dropped on the LOG bar ------------------------------------------
def test_a_dropped_pdf_says_upload_it(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path)
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, _escaped(path))
        await pilot.pause()
        hint = screen.query_one("#hint", Static).content.plain
        assert hint == "statement PDF · BCP Visa 1492 2026-10.pdf · ⏎ upload it"
        assert _shown(screen) == {"escape": "Cancel", "enter": "Upload"}
        _type(screen, _escaped(_xlsx(tmp_path)))  # a download says import again
        await pilot.pause()
        assert _shown(screen) == {"escape": "Cancel", "enter": "Import"}
        assert fake_client.calls == []

    run_app(scenario)


def test_files_of_both_kinds_list_each_with_its_kind():
    """6A: every file with its kind, taken one by one."""
    from pathlib import Path

    files = [Path("/d/Movimientos.xlsx"), Path("/d/BCP Visa 1492 2026-10.pdf")]
    assert bank_files_hint(files).plain.split("\n") == [
        "files · 2 · ⏎ take them, one by one",
        "  Movimientos.xlsx · bank download",
        "  BCP Visa 1492 2026-10.pdf · statement PDF",
    ]
    two_downloads = [Path("/d/a.xlsx"), Path("/d/b.xlsx")]
    assert bank_files_hint(two_downloads).plain.startswith("bank files · 2 · ⏎ import them")


def test_a_pdf_gone_from_disk_stays_in_the_bar(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path)
    _patch(monkeypatch)

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
        assert fake_client.calls == []

    run_app(scenario)


# ---- A2 · which account is this statement? -------------------------------------------
def test_the_account_list_is_the_downloads_with_the_statements_question(
    fake_client, monkeypatch, tmp_path
):
    path = _pdf(tmp_path)
    _patch(monkeypatch)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _accounts(pilot, app)
        assert "Upload a statement" in _crumb(account)
        lines = _lines(account)
        assert lines[0] == "Which account is this statement?  BCP Visa 1492 2026-10.pdf"
        assert [_cells(line) for line in lines[1:]] == [
            ["BCP Signature", "PEN + USD"],
            ["Sueldo Soles", "PEN"],
            ["Efectivo", "PEN"],
        ]
        assert _shown(account) == {"escape": "Cancel", "enter": "Pick", "down": "Move"}
        assert fake_client.posts == []  # nothing sent before ⏎ on an account

    run_app(scenario, size=(120, 40))


# ---- 1A · a card's paper ---------------------------------------------------------------
def test_a_cards_preview_is_screen_1a_and_writes_nothing(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path)
    reads_by_ids = _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        assert "Capture & ledger  ▸  Upload  ▸  BCP Visa 1492 2026-10.pdf" in _crumb(preview)
        lines = _lines(preview)
        assert lines[:2] == [
            "Preview · BCP Signature PEN + USD · nothing written yet",
            "SIG-202610 · 2026-09-26 → 2026-10-25 · a new statement",
        ]
        assert [line.split() for line in lines[2:5]] == [
            ["begin", "end"],
            ["USD", "-36.42", "-61.40"],
            ["PEN", "-1,204.10", "-512.30"],
        ]
        assert _cells(lines[5]) == ["#", "date", "title", "amount", "cur"]
        rows = [_cells(line) for line in lines[6:17]]
        assert rows == [
            ["1", "2026-09-24", "TAMBO MIRAFLORES", "-7.50", "PEN", "✓", "In the ledger"],
            ["2", "2026-09-27", "PLAZA VEA SURCO", "-84.30", "PEN", "✓", "In the ledger"],
            ["3", "2026-10-02", "UBER *TRIP", "-42.00", "PEN", "+", "New"],
            ["! 2026-10-03 UBER *TRIP -42.00 in the ledger is one day off: not paired"],
            ["4", "2026-10-14", "NETFLIX.COM", "-44.90", "PEN", "✓", "In the ledger"],
            ["5", "2026-10-20", "PAGO TARJETA", "800.00", "PEN", "✓", "In the ledger"],
            ["6", "2026-10-05", "AMAZON", "-24.99", "USD", "✓", "In the ledger"],
            ["7", "2026-10-24", "SPOTIFY P2F3", "-5.99", "USD", "+", "New"],
            [
                "8",
                "2026-10-25",
                "INTERESES",
                "-12.40",
                "PEN",
                "+",
                "New",
                "· a fee, dated the last day",
            ],
            [
                "9",
                "2026-10-25",
                "SEGURO DE DESGRAVAMEN",
                "-6.90",
                "PEN",
                "+",
                "New",
                "· a fee, dated the last day",
            ],
            ["10", "2026-10-25", "MANT. CUENTA", "0.00", "USD", "·", "Empty"],
        ]
        assert lines[17:] == [
            "Taken out · in the statement, not on the paper; they stay in the ledger",
            "2026-10-11  FARMACIA CENTRAL       -42.90  PEN",
            "10 rows · 5 in the ledger · 4 new · 1 empty · 1 taken out",
            "new ones go under @Pendiente and #Pendiente",
        ]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Close SIG-202610"}
        assert _uploads(fake_client) == [True]  # the dry run only
        assert reads_by_ids == [["bl-farm", "bl-near"]]  # one read, by their ids

    run_app(scenario, size=(120, 50))


@pytest.mark.parametrize(
    ("first", "second", "shown"),
    [
        ("sig-usd", "sig-pen", ["USD", "PEN"]),
        ("sig-pen", "sig-usd", ["PEN", "USD"]),
    ],
    ids=["dollar-account-first", "soles-account-first"],
)
def test_a_cards_balance_lines_follow_its_holders_accounts_order(
    fake_client, monkeypatch, tmp_path, first, second, shown
):
    """One balance line per account of the holder, in the engine's order, the
    holder's accounts' order (contract: POST /v1/statements/import, "Response"):
    the app sorts nothing, and still sends the soles account."""
    by_id = {a["id"]: a for a in ACCOUNTS}
    balance = {"sig-usd": USD_BALANCE, "sig-pen": PEN_BALANCE}
    path = _pdf(tmp_path)
    _patch(monkeypatch, accounts=[by_id[first], by_id[second], *ACCOUNTS[2:]])
    paper = {**CARD, "balances": [balance[first], balance[second]]}
    _engine(fake_client, {path.read_bytes(): paper})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        lines = _lines(preview)
        assert lines[2].split() == ["begin", "end"]
        assert [line.split()[0] for line in lines[3:5]] == shown
        ((_, body),) = fake_client.posts
        assert body["account_id"] == "sig-pen"

    run_app(scenario, size=(120, 50))


def test_a_taken_out_line_lines_up_under_the_tables_columns(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        raw = _body(preview).split("\n")
        row = next(line for line in raw if "TAMBO" in line)
        taken = next(line for line in raw if "FARMACIA" in line)
        assert taken.index("2026-10-11") == row.index("2026-09-24")
        assert taken.index("FARMACIA") == row.index("TAMBO")
        assert taken.rindex("PEN") == row.rindex("PEN")

    run_app(scenario, size=(120, 50))


def test_lines_that_cannot_be_read_leave_the_rows_and_say_why(fake_client, monkeypatch, tmp_path):
    """The near miss keeps its day and the row's amount, the taken-out block its
    head, and one dim line says why the lines went unread."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})

    def refused(cfg, ids, **kwargs):
        raise EngineError("INTERNAL_ERROR", "Something went wrong.", None, 500, {})

    monkeypatch.setattr("expense.reads.fetch_bank_lines_by_ids", refused)

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        lines = _lines(preview)
        assert "! 2026-10-03 — -42.00 in the ledger is one day off: not paired" in lines
        assert "Taken out · in the statement, not on the paper; they stay in the ledger" in lines
        assert not any("FARMACIA" in line for line in lines)
        assert "! could not read the ledger lines: INTERNAL_ERROR — Something went wrong." in lines
        assert _shown(preview)["enter"] == "Close SIG-202610"

    run_app(scenario, size=(120, 50))


# ---- 1B · a savings account's paper ---------------------------------------------------
def test_a_savings_preview_has_one_balance_line_and_no_currency(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path, "BCP Ahorros 2026-10.pdf")
    reads_by_ids = _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): SAVINGS})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _accounts(pilot, app)
        await pilot.press("down", "enter")  # Sueldo Soles
        preview = await _previewed(pilot, app)
        lines = _lines(preview)
        assert lines[:2] == [
            "Preview · Sueldo Soles · nothing written yet",
            "Octubre 2026 · 2026-10-01 → 2026-10-31 · a draft, filled from the paper",
        ]
        assert [line.split() for line in lines[2:4]] == [
            ["begin", "end"],
            ["PEN", "10,912.40", "12,450.00"],
        ]
        assert _cells(lines[4]) == ["#", "date", "title", "amount"]
        assert _cells(lines[5]) == ["1", "2026-10-01", "HABERES", "4,850.00", "✓", "In the ledger"]
        assert _cells(lines[8]) == ["4", "2026-10-15", "CAJERO", "-400.00", "+", "New"]
        assert _cells(lines[10]) == ["6", "2026-10-30", "INTERES", "0.00", "·", "Empty"]
        assert lines[11:] == [
            "6 rows · 4 in the ledger · 1 new · 1 empty",
            "new ones go under @Pendiente and #Pendiente",
        ]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Close Octubre 2026"}
        ((_, body),) = fake_client.posts
        assert body["account_id"] == "aho-pen"
        assert reads_by_ids == []  # no id to read: nothing taken out, no near miss

    run_app(scenario, size=(120, 40))


# ---- esc and the apply ---------------------------------------------------------------
def test_esc_on_the_preview_sends_nothing(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        bar = preview._owner
        await pilot.press("escape")
        await _on(pilot, app, LogBarScreen, "esc did not return to the bar")
        assert app.screen is bar and bar._files is None
        await pilot.pause()
        assert _uploads(fake_client) == [True]

    run_app(scenario, size=(120, 50))


def test_enter_closes_the_month_and_says_so_in_the_past_tense(fake_client, monkeypatch, tmp_path):
    """Screen 3, nothing flagged: no ⚑ line and no `f`; the apply sends the
    same file on the same account."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})

    async def scenario(pilot, app):
        await _card_preview(pilot, app, path)
        await pilot.press("enter")
        result = await _on(pilot, app, StatementResultScreen, "no result screen")
        assert _uploads(fake_client) == [True, False]
        assert _lines(result) == [
            "✓ SIG-202610 closed · BCP Signature PEN + USD  new ones under @Pendiente and "
            "#Pendiente",
            "10 rows · 5 were in the ledger · 4 created · 1 empty · 1 taken out",
        ]
        assert _shown(result) == {"escape": "Back", "enter": "Home"}
        (_, dry), (_, applied) = fake_client.posts
        assert applied == {**dry, "dry_run": False}
        await pilot.press("enter")
        await _on(pilot, app, HomeScreen, "⏎ Home did not go home")

    run_app(scenario, size=(120, 50))


def test_flagged_lines_show_and_f_opens_them(fake_client, monkeypatch, tmp_path):
    """Screen 3: the ⚑ line counts every account's `review_lines` in the
    completed statement, and `f` opens the flagged lines' screen on them; back
    from it, the screen stays."""
    path = _pdf(tmp_path)
    usd_line = bank_line_row(
        "bl-hulu",
        [
            import_part(
                "t-hulu",
                -799,
                account_id="sig-usd",
                line="bl-hulu",
                day="2026-10-12",
                title="HULU",
            )
        ],
        net_cents=-799,
        account_id="sig-usd",
    )
    _patch(monkeypatch, lines={**LINES, "bl-hulu": usd_line})
    flagged = {"sig-pen": ["bl-near"], "sig-usd": ["bl-hulu"]}  # each on its own account
    _engine(fake_client, {path.read_bytes(): {**CARD, "review_lines": flagged}})

    async def scenario(pilot, app):
        await _card_preview(pilot, app, path)
        await pilot.press("enter")
        result = await _on(pilot, app, StatementResultScreen, "no result screen")
        assert _lines(result)[-1] == (
            "⚑ 2 lines flagged for review: in no statement, dated up to this one's last day"
            "  · f shows them"
        )
        assert _footer(result) == ["esc Back", "⏎ Home", "f Flagged"]
        await pilot.press("f")
        flagged = await _on(pilot, app, FlaggedLinesScreen, "f did not open the flagged lines")
        await wait_for(pilot, lambda: flagged._list is not None, message="flagged never read")
        assert flagged._ids == ["bl-hulu", "bl-near"]  # the balances' order, USD first
        assert flagged._statement == "SIG-202610"
        await pilot.press("escape")
        await _on(pilot, app, StatementResultScreen, "esc did not come back")
        assert app.screen is result
        assert "f" in _shown(result)

    run_app(scenario, size=(120, 50))


# ---- 2 · refused uploads -------------------------------------------------------------
@pytest.mark.parametrize(
    ("err", "shown"),
    [
        (
            _refusal(
                "VALIDATION_ERROR",
                "file",
                "PEN total billed: the paper prints 512.30, the rows add up to 498.10.",
                "TOTALS_MISMATCH",
            ),
            [
                "VALIDATION_ERROR — The statement cannot be uploaded.",
                "! file: PEN total billed: the paper prints 512.30, the rows add up to 498.10.",
                "Nothing was written.",
            ],
        ),
        (
            _refusal(
                "VALIDATION_ERROR",
                "account_id",
                "The account has no statement code.",
                "NO_STATEMENT_CODE",
            ),
            [
                "VALIDATION_ERROR — The statement cannot be uploaded.",
                "! account_id: The account has no statement code.",
                "Nothing was written.",
            ],
        ),
        (
            _refusal(
                "VALIDATION_ERROR",
                "rows.7.date",
                "Row 7: Must not be in the future.",
                "FUTURE_DATE",
            ),
            [
                "VALIDATION_ERROR — The statement cannot be uploaded.",
                "! Row 7: Must not be in the future.",
                "Nothing was written.",
            ],
        ),
        (
            _refusal(
                "CONFLICT",
                "file",
                "Octubre 2026 is completed.",
                "RECONCILIATION_NOT_DRAFT",
                status=409,
                message="Octubre 2026 is completed.",
            ),
            [
                "CONFLICT — Octubre 2026 is completed.",
                "! file: Octubre 2026 is completed.",
                "Nothing was written.",
                "Revert it first, then drop the PDF again.",
            ],
        ),
    ],
    ids=["refused-file", "account", "future-date", "not-draft"],
)
def test_a_refused_upload_shows_the_engines_words_and_writes_nothing(
    fake_client, monkeypatch, tmp_path, err, shown
):
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    fake_client.errors["POST"] = err

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _accounts(pilot, app)
        await pilot.press("enter")
        preview = await _refused(pilot, app)
        assert _lines(preview) == ["Preview · BCP Signature PEN + USD", *shown]
        assert _shown(preview) == {"escape": "Back"}
        await pilot.press("enter")  # ⏎ sends nothing more
        await pilot.pause()
        assert _uploads(fake_client) == [True]

    run_app(scenario, size=(120, 40))


def test_a_savings_paper_for_a_holder_of_two_currencies_is_refused_in_the_engines_words(
    fake_client, monkeypatch, tmp_path
):
    """A savings paper, in soles, sent for a savings account whose holder also
    holds a dollar account: `HOLDER_ACCOUNT_NOT_ON_PAPER` on `account_id`, shown
    in the engine's words with no line of the app's, nothing written
    (contract: POST /v1/statements/import, "Every account of the holder is on the paper")."""
    path = _pdf(tmp_path, "BCP Ahorros 2026-10.pdf")
    _patch(
        monkeypatch,
        accounts=[
            *ACCOUNTS[:2],
            account_record(id="aho-pen", name="Sueldo PEN", holder_id="h2"),
            account_record(id="aho-usd", name="Sueldo USD", currency_code="USD", holder_id="h2"),
        ],
    )
    words = "Sueldo USD is an account of this holder the paper does not print."
    fake_client.errors["POST"] = _refusal(
        "VALIDATION_ERROR", "account_id", words, "HOLDER_ACCOUNT_NOT_ON_PAPER"
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _accounts(pilot, app)
        await pilot.press("down", "enter")  # the savings holder's line
        preview = await _refused(pilot, app)
        assert _lines(preview) == [
            "Preview · Sueldo PEN + USD",
            "VALIDATION_ERROR — The statement cannot be uploaded.",
            f"! account_id: {words}",
            "Nothing was written.",
        ]
        assert _shown(preview) == {"escape": "Back"}
        ((_, body),) = fake_client.posts
        assert body["account_id"] == "aho-pen"
        assert _uploads(fake_client) == [True]

    run_app(scenario, size=(120, 40))


def test_a_change_met_by_the_apply_previews_again_before_any_write(
    fake_client, monkeypatch, tmp_path
):
    """The apply's `409 CONFLICT` with `CONCURRENT_CHANGE`: the engine's words,
    the app's line, `⏎ Preview again`, a fresh dry run, and only then a new
    apply on its own `⏎`."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})
    words = "Another request changed this row's ledger line. Send it again."

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        fake_client.errors["POST"] = _refusal(
            "CONFLICT",
            "rows.4",
            words,
            "CONCURRENT_CHANGE",
            status=409,
            message="The ledger changed while the upload ran.",
        )
        await pilot.press("enter")
        await wait_for(pilot, lambda: bool(preview._failure), message="no failure shown")
        lines = _lines(preview)
        at = lines.index("CONFLICT — The ledger changed while the upload ran.")
        assert lines[at:] == [
            "CONFLICT — The ledger changed while the upload ran.",
            f"! rows.4: {words}",
            "Nothing was written.",
            "It changed while the upload ran: ⏎ checks the paper against the ledger again.",
        ]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Preview again"}
        assert _uploads(fake_client) == [True, False]

        del fake_client.errors["POST"]
        await pilot.press("enter")  # a fresh dry run, never the apply
        await wait_for(pilot, lambda: preview._answer is not None, message="no fresh preview")
        assert _uploads(fake_client) == [True, False, True]
        assert preview._failure == []
        assert _shown(preview) == {"escape": "Cancel", "enter": "Close SIG-202610"}
        await pilot.press("enter")
        await _on(pilot, app, StatementResultScreen, "no result screen")
        assert _uploads(fake_client) == [True, False, True, False]

    run_app(scenario, size=(120, 50))


# ---- 6A · several files of both kinds ------------------------------------------------
def test_a_download_and_a_pdf_go_one_by_one_each_its_own_way(fake_client, monkeypatch, tmp_path):
    download = _xlsx(tmp_path)
    paper = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(
        fake_client,
        {paper.read_bytes(): CARD},
        {download.read_bytes(): [import_row(2, -4900, title="EDO SUSHI")]},
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        _type(screen, f"{_escaped(download)} {_escaped(paper)}")
        await pilot.pause()
        assert screen._hint().split("\n") == [
            "files · 2 · ⏎ take them, one by one",
            "  Movimientos.xlsx · bank download",
            "  BCP Visa 1492 2026-10.pdf · statement PDF",
        ]
        assert _shown(screen) == {"escape": "Cancel", "enter": "Import"}
        await pilot.press("enter")

        account = await _accounts(pilot, app, ImportAccountScreen)
        assert "Import  ▸  file 1 of 2" in _crumb(account)
        assert _shown(account)["escape"] == "Cancel both"
        await pilot.press("enter")
        await _on(pilot, app, ImportPreviewScreen, "no download preview")
        await wait_for(pilot, lambda: app.screen._lines is not None, message="no dry run")
        await pilot.press("enter")
        result = await _on(pilot, app, ImportResultScreen, "no download result")
        assert _shown(result)["enter"] == "Next file"

        await pilot.press("enter")
        account = await _accounts(pilot, app)
        assert _lines(account)[0] == "Which account is this statement?  BCP Visa 1492 2026-10.pdf"
        assert _crumb(account).rstrip().endswith("Upload a statement  ▸  file 2 of 2")
        assert _shown(account)["escape"] == "Cancel"
        await pilot.press("enter")
        preview = await _previewed(pilot, app)
        assert "Upload  ▸  file 2 of 2" in _crumb(preview)
        await pilot.press("enter")
        result = await _on(pilot, app, StatementResultScreen, "no statement result")
        assert _shown(result)["enter"] == "Home"
        assert [path for path, _ in fake_client.posts] == [
            "/transactions/import",
            "/transactions/import",
            "/statements/import",
            "/statements/import",
        ]
        await pilot.press("enter")
        await _on(pilot, app, HomeScreen, "⏎ Home did not go home")

    run_app(scenario, size=(120, 50))


def test_a_pdf_before_a_download_reads_next_file_after_its_close(
    fake_client, monkeypatch, tmp_path
):
    paper = _pdf(tmp_path)
    download = _xlsx(tmp_path)
    _patch(monkeypatch)
    _engine(
        fake_client,
        {paper.read_bytes(): CARD},
        {download.read_bytes(): [import_row(2, -4900, title="EDO SUSHI")]},
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, paper, download)
        account = await _accounts(pilot, app)
        assert _crumb(account).rstrip().endswith("Upload a statement  ▸  file 1 of 2")
        assert _shown(account)["escape"] == "Cancel both"
        await pilot.press("enter")
        await _previewed(pilot, app)
        await pilot.press("enter")
        result = await _on(pilot, app, StatementResultScreen, "no statement result")
        assert _shown(result) == {"escape": "Back", "enter": "Next file"}
        await pilot.press("enter")
        await _accounts(pilot, app, ImportAccountScreen)

    run_app(scenario, size=(120, 50))


# ---- the real HTTP client: one key per apply --------------------------------------
def test_the_apply_is_one_write_its_key_reused_on_a_retry(configured, monkeypatch, tmp_path):
    """Through the shared HTTP client: the dry run and the apply each carry a
    key of their own; the apply's 503 is sent again under the same key, and
    `esc` before it sent nothing more."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    applies = iter(
        [
            httpx.Response(503, json={"error": {"code": "UNAVAILABLE", "message": "busy"}}),
            httpx.Response(200, json=statement_upload_answer(**CARD, dry_run=False)),
        ]
    )

    def engine(request):
        if json.loads(request.content)["dry_run"]:
            return httpx.Response(200, json=statement_upload_answer(**CARD, dry_run=True))
        return next(applies)

    async def scenario(pilot, app):
        await _card_preview(pilot, app, path)
        await pilot.press("enter")
        await _on(pilot, app, StatementResultScreen, "no result screen")

    with respx.mock(assert_all_called=False) as mocked:
        route = mocked.post(f"{ENGINE_URL}/v1/statements/import").mock(side_effect=engine)
        run_app(scenario, size=(120, 50))
    sent = [json.loads(call.request.content) for call in route.calls]
    keys = [call.request.headers["X-Idempotency-Key"] for call in route.calls]
    assert [body["dry_run"] for body in sent] == [True, False, False]
    assert keys[1] == keys[2] and keys[0] != keys[1]


def test_a_repeated_enter_on_the_preview_sends_one_apply(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})
    answer = fake_client.post
    release = threading.Event()

    def held(path, json_body=None):
        if not json_body["dry_run"]:
            release.wait(timeout=5)  # the apply is still on its way
        return answer(path, json_body)

    fake_client.post = held

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        await pilot.press("enter", "enter", "enter")
        await pilot.pause()
        assert app.screen is preview and preview._writing
        assert "enter" not in _shown(preview)
        assert "writing…" in _lines(preview)
        release.set()
        await _on(pilot, app, StatementResultScreen, "no result screen")
        assert _uploads(fake_client) == [True, False]

    try:
        run_app(scenario, size=(120, 50))
    finally:
        release.set()


def test_a_long_paper_pages_with_pgdn_and_pgup(fake_client, monkeypatch, tmp_path):
    """The rows a page holds, `… N more · pgdn` under them; pgdn shows the
    rest, pgup the page before; the counts stay under every page."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    rows = [statement_row(n, -100 * n, description=f"ROW {n}") for n in range(1, 41)]
    _engine(fake_client, {path.read_bytes(): {"rows": rows, "balances": CARD["balances"]}})

    def places(preview) -> list[str]:
        return [_cells(line)[0] for line in _lines(preview) if re.match(r"\d+\s+2026-", line)]

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        first = places(preview)
        assert first[0] == "1" and len(first) < 40
        assert f"… {40 - len(first)} more · pgdn" in _lines(preview)
        assert "40 rows · 40 in the ledger · 0 new" in _lines(preview)
        await pilot.press("pagedown")
        second = places(preview)
        assert second[0] == str(len(first) + 1)
        await pilot.press("pageup")
        assert places(preview) == first

    run_app(scenario, size=(120, 30))


def test_an_empty_rows_amount_is_plain():
    """Screen 1A draws an empty row's `0.00` in no colour: it is no money in or out."""
    answer = statement_answer(statement_upload_answer(**CARD, dry_run=True))
    columns = Columns(answer, [], width=116)
    (empty,) = row_lines(answer.rows[9], columns, {})
    at = empty.plain.index("0.00")
    assert not [s for s in empty.spans if s.start <= at < s.end]
    (matched,) = row_lines(answer.rows[4], columns, {})  # +800.00 keeps its colour
    at = matched.plain.index("800.00")
    assert [s for s in matched.spans if s.start <= at < s.end]


def test_a_fee_row_stays_on_one_line_on_a_narrow_screen(fake_client, monkeypatch, tmp_path):
    """The title column gives way to the widest row's mark, reason and fee
    note, so a fee row with a long title is one line, its title cut with `…`."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    long_fee = statement_row(
        1,
        -1240,
        outcome="new",
        fee=True,
        day="2026-10-25",
        description="GASTO MENSUAL POR SEGURO DE DESGRAVAMEN DE LA TARJETA",
    )
    _engine(fake_client, {path.read_bytes(): {"rows": [long_fee], "balances": CARD["balances"]}})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        raw = _body(preview, width=preview.size.width - 4).split("\n")
        (row,) = [line for line in raw if line.strip().startswith("1  2026-10-25")]
        assert row.rstrip().endswith("+  New  · a fee, dated the last day")
        assert "…" in row
        assert not any("fee, dated" in line for line in raw if line is not row)

    run_app(scenario, size=(80, 40))
