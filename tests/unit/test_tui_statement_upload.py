"""The statement upload — a statement PDF dropped on the LOG bar → account → preview → close.

A dropped PDF is a few made-up bytes: the app sends them whole and reads nothing in
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
from textual.widgets import Footer, Static

from expense.bank_import.flow import AccountPick, statement_call
from expense.bank_import.statement import statement_answer
from expense.errors import EngineError, format_error
from expense.tui.dropped import dropped_bank_files, is_statement
from expense.tui.screens.bank_import import (
    ImportAccountScreen,
    ImportPreviewScreen,
    ImportResultScreen,
)
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.log_bar import LogBarScreen
from expense.tui.screens.statement_upload import (
    Columns,
    StatementAccountScreen,
    StatementPreviewScreen,
    StatementResultScreen,
    row_line,
)
from expense.tui.screens.statements import FlaggedLinesScreen
from tests.unit.helpers import (
    ENGINE_URL,
    FakeClient,
    account_with_currencies,
    bank_line_row,
    held_currency,
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

#: The card, one account holding soles and dollars; then a savings account and cash.
ACCOUNTS = [
    account_with_currencies(
        id="sig",
        name="BCP Premier",
        currencies=[held_currency("PEN"), held_currency("USD")],
        statement_code="SIG",
    ),
    account_with_currencies(id="aho", name="Sueldo Soles"),
    account_with_currencies(id="cash", name="Efectivo"),
]

#: A card's paper: both currencies, matched, new and empty
#: rows, and two undated fees.
CARD_ROWS = [
    statement_row(1, -750, day="2026-09-24", description="TAMBO MIRAFLORES"),
    statement_row(2, -8430, day="2026-09-27", description="PLAZA VEA SURCO"),
    statement_row(3, -4200, outcome="new", day="2026-10-02", description="UBER *TRIP"),
    statement_row(4, -4490, day="2026-10-14", description="NETFLIX.COM"),
    statement_row(5, 80000, day="2026-10-20", description="PAGO TARJETA"),
    statement_row(6, -2499, currency_code="USD", day="2026-10-05", description="AMAZON"),
    statement_row(
        7,
        -599,
        outcome="new",
        currency_code="USD",
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
        currency_code="USD",
        day="2026-10-25",
        description="MANT. CUENTA",
    ),
]
#: The card's balances, one per currency the paper covers, as the engine sends them.
USD_BALANCE = upload_balance("USD", begin=-3642, end=-6140)
PEN_BALANCE = upload_balance()
CARD = {
    "rows": CARD_ROWS,
    "balances": [USD_BALANCE, PEN_BALANCE],
    "taken_out": ["bl-farm"],
}

#: A savings account's paper: one currency, its open draft
#: filled, nothing taken out.
SAVINGS = {
    "rows": [
        statement_row(1, 485000, day="2026-10-01", description="HABERES"),
        statement_row(2, -80000, day="2026-10-03", description="TRANSF"),
        statement_row(3, -12000, day="2026-10-09", description="YAPE"),
        statement_row(4, -40000, outcome="new", day="2026-10-15", description="CAJERO"),
        statement_row(5, -19240, day="2026-10-28", description="LUZ"),
        statement_row(6, 0, outcome="empty", day="2026-10-30", description="INTERES"),
    ],
    "name": "Octubre 2026",
    "date_start": "2026-10-01",
    "date_end": "2026-10-31",
    "creates": False,
    "statement_id": "s-oct",
    "balances": [upload_balance(begin=1091240, end=1245000)],
}

#: The ledger lines the tests read by id: the line the card's answer takes out,
#: and one the flagged lines' screen lists.
LINES = {
    "bl-uber": bank_line_row(
        "bl-uber",
        [import_part("t-uber", -4200, line="bl-uber", day="2026-10-03", title="UBER *TRIP")],
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
    monkeypatch.setattr("expense.reads.count_bank_lines", lambda *a, **k: 0)
    monkeypatch.setattr("expense.reads.fetch_bank_lines_by_ids", by_ids)
    monkeypatch.setattr(
        "expense.tui.screens.statements.load_account_name_map",
        lambda: {"sig-pen": "BCP Premier", "sig-usd": "BCP Premier Plus"},
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


def test_the_call_sends_exactly_three_keys_on_the_accounts_id():
    """The body is the download's: `dry_run`, the picked account's id and the
    file's bytes in standard base64 (contract: POST /v1/statements/import)."""
    client = FakeClient()
    data = bytes(range(256)) * 50
    account = AccountPick("BCP Premier", "acc-sig", ("PEN",))
    statement_call(client, account, data, dry_run=True)
    ((path, body),) = client.posts
    assert path == "/statements/import"
    assert body == {
        "dry_run": True,
        "account_id": "acc-sig",
        "file": base64.b64encode(data).decode("ascii"),
    }


# ---- the PDF dropped on the LOG bar ------------------------------------------
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


# ---- which account is this statement? -------------------------------------------
def test_the_account_list_is_the_downloads_with_the_statements_question(
    fake_client, monkeypatch, tmp_path
):
    """A bank account with no statement code is listed too (the engine refuses it in
    its words if picked), a dollar account reads `USD`, an account in the way of nothing
    is left out: archived accounts, people and the cash account."""
    path = _pdf(tmp_path)
    _patch(
        monkeypatch,
        accounts=[
            account_with_currencies(
                id="visa",
                name="Visa BCP",
                currencies=[held_currency("PEN"), held_currency("USD")],
                statement_code="VIS",
            ),
            account_with_currencies(id="nocode", name="Sueldo Soles"),
            account_with_currencies(
                id="usd", name="BBVA Dólares", currencies=[held_currency("USD")]
            ),
            account_with_currencies(id="old", name="Cerrada", is_archived=True),
            account_with_currencies(id="ana", name="Ana", kind="person"),
            account_with_currencies(id="efe", name="Efectivo", kind="cash"),
        ],
    )

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        account = await _accounts(pilot, app)
        assert "Upload a statement" in _crumb(account)
        lines = _lines(account)
        assert lines[0] == "Which account is this statement?  BCP Visa 1492 2026-10.pdf"
        assert [_cells(line) for line in lines[1:]] == [
            ["Visa BCP", "PEN + USD"],
            ["Sueldo Soles", "PEN"],
            ["BBVA Dólares", "USD"],
        ]
        assert _shown(account) == {"escape": "Cancel", "enter": "Pick", "down": "Move"}
        assert fake_client.posts == []  # nothing sent before ⏎ on an account

    run_app(scenario, size=(120, 40))


# ---- a card's paper ---------------------------------------------------------------
def test_a_cards_preview_shows_its_rows_and_writes_nothing(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path)
    reads_by_ids = _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        assert "Capture & ledger  ▸  Upload  ▸  BCP Visa 1492 2026-10.pdf" in _crumb(preview)
        lines = _lines(preview)
        assert lines[:2] == [
            "Preview · BCP Premier PEN + USD · nothing written yet",
            "SIG-202610 · 2026-09-26 → 2026-10-25 · a new statement",
        ]
        assert [line.split() for line in lines[2:5]] == [
            ["begin", "end"],
            ["USD", "-36.42", "-61.40"],
            ["PEN", "-1,204.10", "-512.30"],
        ]
        assert _cells(lines[5]) == ["#", "date", "title", "amount", "cur"]
        rows = [_cells(line) for line in lines[6:16]]
        assert rows == [
            ["1", "2026-09-24", "TAMBO MIRAFLORES", "-7.50", "PEN", "✓", "In the ledger"],
            ["2", "2026-09-27", "PLAZA VEA SURCO", "-84.30", "PEN", "✓", "In the ledger"],
            ["3", "2026-10-02", "UBER *TRIP", "-42.00", "PEN", "+", "New"],
            ["4", "2026-10-14", "NETFLIX.COM", "-44.90", "PEN", "✓", "In the ledger"],
            ["5", "2026-10-20", "PAGO TARJETA", "+800.00", "PEN", "✓", "In the ledger"],
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
        assert lines[16:] == [
            "Taken out · in the statement, not on the paper; they stay in the ledger",
            "2026-10-11  FARMACIA CENTRAL        -42.90  PEN",
            "10 rows · 5 in the ledger · 4 new · 1 empty · 1 taken out",
            "new ones go under @Pendiente and #Pendiente",
        ]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Close SIG-202610"}
        assert _uploads(fake_client) == [True]  # the dry run only
        assert reads_by_ids == [["bl-farm"]]  # one read, by their ids
        text = "\n".join(lines)  # nothing to flag: no block, no count
        assert "Will be flagged" not in text and "to flag" not in text and "⚠" not in text
        raw = _body(preview).split("\n")  # a taken-out line stands under the table's columns
        row = next(line for line in raw if "TAMBO" in line)
        taken = next(line for line in raw if "FARMACIA" in line)
        assert taken.index("2026-10-11") == row.index("2026-09-24")
        assert taken.index("FARMACIA") == row.index("TAMBO")
        assert taken.rindex("PEN") == row.rindex("PEN")

    run_app(scenario, size=(120, 50))


def test_a_taken_out_line_shows_its_own_currency_and_no_title_shows_untitled(
    fake_client, monkeypatch, tmp_path
):
    """A dollar line taken out of a two-currency answer reads `USD`, the line's own
    `currency_code`; a row and a taken-out line with no title show `(untitled)`."""
    path = _pdf(tmp_path)
    bare = bank_line_row(
        "bl-bare",
        [{**import_part("t-bare", -599, account_id="sig", line="bl-bare"), "title": None}],
        net_cents=-599,
        account_id="sig",
        currency_code="USD",
    )
    _patch(monkeypatch, lines={"bl-bare": bare})
    paper = {
        **CARD,
        "rows": [statement_row(1, -750, description=None), *CARD["rows"][1:]],
        "taken_out": ["bl-bare"],
    }
    _engine(fake_client, {path.read_bytes(): paper})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        lines = _lines(preview)
        assert "(untitled)" in next(ln for ln in lines if ln.startswith("1 "))
        assert sum("(untitled)" in ln for ln in lines) == 2  # the row and the taken-out line
        taken = next(ln for ln in lines if "(untitled)" in ln and not ln.startswith("1 "))
        assert _cells(taken)[-1] == "USD"

    run_app(scenario, size=(120, 50))


def test_lines_that_cannot_be_read_keep_the_heads_the_counts_and_say_why(
    fake_client, monkeypatch, tmp_path
):
    """The taken-out and flagged blocks keep their heads and the count, and one dim
    line says why the lines went unread."""
    path = _pdf(tmp_path)
    _patch(monkeypatch, lines=FLAG_LINES)
    paper = {**CARD, "review_lines": {"PEN": ["bl-uber"]}}
    _engine(fake_client, {path.read_bytes(): paper})

    def refused(cfg, ids, **kwargs):
        raise EngineError("INTERNAL_ERROR", "Something went wrong.", None, 500, {})

    monkeypatch.setattr("expense.reads.fetch_bank_lines_by_ids", refused)

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        lines = _lines(preview)
        assert "Taken out · in the statement, not on the paper; they stay in the ledger" in lines
        assert FLAGGED_CAPTION in lines  # the flagged block keeps its head and its count
        assert any(line.endswith(" · 1 taken out · 1 to flag") for line in lines)
        assert not any("FARMACIA" in line or "2026-10-03" in line for line in lines)
        assert "! could not read the ledger lines: INTERNAL_ERROR — Something went wrong." in lines
        assert _shown(preview)["enter"] == "Close SIG-202610"

    run_app(scenario, size=(120, 50))


# ---- the lines the close will flag, and the close's notes -------------------------
USD_LINE = bank_line_row(
    "bl-usd",
    [
        import_part(
            "t-usd", -1999, account_id="sig", line="bl-usd", day="2026-10-12", title="AMAZON"
        )
    ],
    net_cents=-1999,
    account_id="sig",
    currency_code="USD",
)
KFC_LINE = bank_line_row(
    "bl-kfc",
    [import_part("t-kfc", -3190, line="bl-kfc", day="2026-10-20", title="KFC JOCKEY PLAZA")],
    net_cents=-3190,
)
FLAG_LINES = {**LINES, "bl-usd": USD_LINE, "bl-kfc": KFC_LINE}


FLAGGED_CAPTION = (
    "⚑ Will be flagged · in no statement, on the last day,"
    " which stays open until the next month closes"
)


def _flag_block(lines: list[str]) -> list[str]:
    """The lines from the `⚑ Will be flagged` head to the counts line, left out."""
    start = next(i for i, line in enumerate(lines) if line.startswith("⚑ Will be flagged"))
    end = next(i for i in range(start, len(lines)) if " rows · " in lines[i])
    return lines[start:end]


def test_the_lines_the_close_will_flag_show_under_the_lines_taken_out(
    fake_client, monkeypatch, tmp_path
):
    """The engine's `review_lines`, balance by balance in its order, are read once by
    their ids with the lines taken out; a line in both shows in both blocks."""
    path = _pdf(tmp_path)
    reads_by_ids = _patch(monkeypatch, lines=FLAG_LINES)
    paper = {
        **CARD,
        "review_lines": {"USD": ["bl-usd"], "PEN": ["bl-farm", "bl-uber", "bl-kfc"]},
    }
    _engine(fake_client, {path.read_bytes(): paper})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        lines = _lines(preview)
        assert lines.index(
            "Taken out · in the statement, not on the paper; they stay in the ledger"
        ) < (lines.index(FLAGGED_CAPTION))
        block = _flag_block(lines)
        assert [_cells(line)[:2] for line in block[1:]] == [
            ["2026-10-12", "AMAZON"],
            ["2026-10-11", "FARMACIA CENTRAL"],
            ["2026-10-03", "UBER *TRIP"],
            ["2026-10-20", "KFC JOCKEY PLAZA"],
        ]  # the engine's order: neither the days' nor the titles'
        assert [line.split()[-1] for line in block[1:]] == ["USD", "PEN", "PEN", "PEN"]
        assert any("FARMACIA" in line for line in lines[: lines.index(block[0])])  # taken out too
        assert lines[lines.index(block[0]) + len(block)].endswith(" · 1 taken out · 4 to flag")
        raw = _body(preview).split("\n")
        row = next(line for line in raw if "TAMBO" in line)
        amazon = next(line for line in raw if "AMAZON" in line and "2026-10-12" in line)
        assert amazon.index("2026-10-12") == row.index("2026-09-24")
        assert amazon.index("AMAZON") == row.index("TAMBO")
        assert reads_by_ids == [["bl-farm", "bl-usd", "bl-uber", "bl-kfc"]]  # one read

    run_app(scenario, size=(120, 50))


def test_a_full_page_with_a_flagged_line_wraps_its_head_and_ends_above_the_footer_at_80x30(
    fake_client, monkeypatch, tmp_path
):
    """The head wraps under its own words, `Will`, not `⚑`, and counts in the page
    budget: the body ends above the footer."""
    path = _pdf(tmp_path)
    _patch(monkeypatch, lines=FLAG_LINES)
    rows = [statement_row(n, -100 * n, description=f"ROW {n}") for n in range(1, 41)]
    paper = {
        "rows": rows,
        "balances": CARD["balances"],
        "review_lines": {"PEN": ["bl-uber"]},
    }
    _engine(fake_client, {path.read_bytes(): paper})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        body = preview.query_one("#import-body", Static)
        footer = preview.query_one(Footer)
        assert "UBER *TRIP" in " ".join(_lines(preview, width=body.content_region.width))
        assert body.region.y + body.virtual_size.height <= footer.region.y
        raw_lines = _body(preview, width=body.content_region.width).split("\n")
        at = next(i for i, line in enumerate(raw_lines) if line.startswith("⚑ Will be flagged"))
        head = [raw_lines[at].rstrip()]
        for line in raw_lines[at + 1 :]:
            if not line.startswith("  ") or line.strip()[:4].isdigit():
                break
            head.append(line.rstrip())
        assert len(head) >= 2
        assert all(line.startswith("  ") for line in head[1:])  # under `Will`, not `⚑`
        assert " ".join(line.strip() for line in head) == FLAGGED_CAPTION

    run_app(scenario, size=(80, 30))


def test_each_currencys_notes_show_under_the_balances_and_the_uncovered_ones_too(
    fake_client, monkeypatch, tmp_path
):
    path = _pdf(tmp_path)
    reads_by_ids = _patch(monkeypatch, lines=FLAG_LINES)
    paper = {
        **CARD,
        "taken_out": [],
        "warnings": {
            "USD": ["Two days of the paper hold no dollar line."],
            "EUR": ["The paper holds no euro balance."],
        },
        "not_covered": {"EUR": ["bl-uber"]},
    }
    _engine(fake_client, {path.read_bytes(): paper})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        lines = _lines(preview)
        assert lines[5:7] == [
            "⚠ USD: Two days of the paper hold no dollar line.",
            "⚠ EUR: The paper holds no euro balance.",
        ]
        assert lines[4].split()[0] == "PEN"  # the notes follow the last balance line
        block = _flag_block(lines)
        assert block[1].split()[-1] == "PEN"  # the line's own currency
        assert reads_by_ids == [["bl-uber"]]

    run_app(scenario, size=(120, 50))


def test_an_uncovered_currencys_flagged_line_on_a_one_balance_paper_has_no_cur_column(
    fake_client, monkeypatch, tmp_path
):
    """The `cur` column is a card's (two balances); a flagged line of a currency the
    paper does not cover shows day, title and amount only."""
    path = _pdf(tmp_path, "BCP Ahorros 2026-10.pdf")
    _patch(monkeypatch, lines=FLAG_LINES)
    _engine(fake_client, {path.read_bytes(): {**SAVINGS, "not_covered": {"USD": ["bl-usd"]}}})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _accounts(pilot, app)
        await pilot.press("down", "enter")
        preview = await _previewed(pilot, app)
        block = _flag_block(_lines(preview))
        assert _cells(block[1]) == ["2026-10-12", "AMAZON", "-19.99"]

    run_app(scenario, size=(120, 50))


def test_a_long_note_wraps_under_its_own_first_word(fake_client, monkeypatch, tmp_path):
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    sentence = "Two days of the paper hold no dollar line and the days after it hold none either."
    paper = {**CARD, "warnings": {"USD": [sentence]}}
    _engine(fake_client, {path.read_bytes(): paper})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        raw = _body(preview, width=50).split("\n")
        first = next(i for i, line in enumerate(raw) if "⚠ USD:" in line)
        balance = next(line for line in raw if line.startswith("USD"))
        assert raw[first].index("⚠") == balance.index("USD")  # the balances' column
        assert raw[first].startswith("⚠ USD: Two days")
        assert raw[first + 1].startswith("  ") and raw[first + 1].strip()  # under the words
        assert raw[first + 1].index(raw[first + 1].strip()) == raw[first].index("USD")

    run_app(scenario, size=(60, 50))


# ---- a savings account's paper ---------------------------------------------------
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
        assert _cells(lines[5]) == ["1", "2026-10-01", "HABERES", "+4,850.00", "✓", "In the ledger"]
        assert _cells(lines[8]) == ["4", "2026-10-15", "CAJERO", "-400.00", "+", "New"]
        assert _cells(lines[10]) == ["6", "2026-10-30", "INTERES", "0.00", "·", "Empty"]
        assert lines[11:] == [
            "6 rows · 4 in the ledger · 1 new · 1 empty",
            "new ones go under @Pendiente and #Pendiente",
        ]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Close Octubre 2026"}
        ((_, body),) = fake_client.posts
        assert body["account_id"] == "aho"
        assert reads_by_ids == []  # no id to read: nothing taken out

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
    """Nothing flagged: no ⚑ line and no `f`; the apply sends the
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
            "✓ SIG-202610 closed · BCP Premier PEN + USD  new ones under @Pendiente and #Pendiente",
            "10 rows · 5 were in the ledger · 4 created · 1 empty · 1 taken out",
        ]
        assert _shown(result) == {"escape": "Back", "enter": "Home"}
        (_, dry), (_, applied) = fake_client.posts
        assert applied == {**dry, "dry_run": False}
        await pilot.press("enter")
        await _on(pilot, app, HomeScreen, "⏎ Home did not go home")

    run_app(scenario, size=(120, 50))


def test_flagged_lines_show_and_f_opens_them(fake_client, monkeypatch, tmp_path):
    """The ⚑ line shows the engine's count of the completed statement's
    review list, and `f` opens the flagged lines' screen on that statement, which reads its
    review list and its count, no id sent; back from it, the screen stays."""
    path = _pdf(tmp_path)
    usd_line = bank_line_row(
        "bl-hulu",
        [
            import_part(
                "t-hulu",
                -799,
                account_id="sig",
                line="bl-hulu",
                day="2026-10-12",
                title="HULU",
            )
        ],
        net_cents=-799,
        account_id="sig",
        currency_code="USD",
    )
    _patch(monkeypatch, lines={**LINES, "bl-hulu": usd_line})
    paper = {
        "rows": [r for r in CARD_ROWS if r["currency_code"] == "PEN"],
        "balances": [PEN_BALANCE],  # the paper covers soles; the dollars are `not_covered`
        "review_lines": {"PEN": ["bl-uber"]},
        "not_covered": {"USD": ["bl-hulu"]},
    }
    _engine(fake_client, {path.read_bytes(): paper})
    review_reads: list[tuple] = []  # (read, statement id, sort, ids sent)

    def review_list(cfg, *, review_of, sort, **kwargs):
        review_reads.append(("list", review_of, sort, kwargs.get("ids")))
        return {"items": [LINES["bl-uber"], usd_line], "limit": 200, "next_cursor": None}

    def review_count(cfg, *, review_of, **kwargs):
        review_reads.append(("count", review_of, None, kwargs.get("ids")))
        return 5  # the engine's count, not the close's sum of two ids

    monkeypatch.setattr("expense.reads.fetch_bank_lines", review_list)
    monkeypatch.setattr("expense.reads.count_bank_lines", review_count)

    async def scenario(pilot, app):
        await _card_preview(pilot, app, path)
        await pilot.press("enter")
        result = await _on(pilot, app, StatementResultScreen, "no result screen")
        assert _lines(result)[-1] == (
            "⚑ 5 lines flagged for review: in no statement, dated up to this one's last day"
            "  · f shows them"
        )
        assert _footer(result) == ["esc Back", "⏎ Home", "f Flagged"]
        await pilot.press("f")
        flagged = await _on(pilot, app, FlaggedLinesScreen, "f did not open the flagged lines")
        await wait_for(pilot, lambda: flagged._list is not None, message="flagged never read")
        assert [row.key for row in flagged._list._rows] == ["bl-uber", "bl-hulu"]
        assert review_reads == [
            ("count", "s-paper", None, None),  # the apply's, behind the ⚑ line
            ("count", "s-paper", None, None),  # the screen's own, painted before its lines
            ("list", "s-paper", "statement", None),
        ]
        assert flagged._statement == "SIG-202610"
        # the picked account's statement code: the engine's two ways show as words
        assert flagged._statement_code == "SIG"
        assert len(flagged.query("#fways")) == 1
        await pilot.press("escape")
        await _on(pilot, app, StatementResultScreen, "esc did not come back")
        assert app.screen is result
        assert "f" in _shown(result)

    run_app(scenario, size=(120, 50))


# ---- refused uploads -------------------------------------------------------------
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
        assert _lines(preview) == ["Preview · BCP Premier PEN + USD", *shown]
        assert _shown(preview) == {"escape": "Back"}
        assert not list(app._notifications)  # the words once, on the screen
        await pilot.press("enter")  # ⏎ sends nothing more
        await pilot.pause()
        assert _uploads(fake_client) == [True]

    run_app(scenario, size=(120, 40))


@pytest.mark.parametrize(
    ("reason", "words"),
    [
        (
            "STATEMENT_NUMBER_MISMATCH",
            "The paper prints the number ending 1492, and the account's number on 2026-10-25 "
            "ends 4471.",
        ),
        ("ACCOUNT_HAS_NO_NUMBER", "The account has no card or account number."),
    ],
)
def test_a_number_refusal_stays_on_the_account_question_and_another_pick_goes_on(
    fake_client, monkeypatch, tmp_path, reason, words
):
    """A dry run refused on the account's number (by its reason code): the account
    question again, the cursor on the picked account, the engine's words in the
    "Failed" note, nothing written. Picking another account sends that account's
    dry run."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): SAVINGS})
    answer = fake_client.post
    refusal = EngineError(
        "VALIDATION_ERROR",
        "The statement cannot be uploaded.",
        {"account_id": words},
        422,
        {},
        {"account_id": reason},
    )

    def post(path_, json_body=None):
        if json_body["account_id"] != "aho":
            return answer(path_, json_body)
        fake_client.calls.append(("POST", path_, json_body))
        raise refusal

    fake_client.post = post

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _accounts(pilot, app)
        await pilot.press("down", "enter")  # Sueldo Soles, the second
        account = await _accounts(pilot, app)
        await wait_for(pilot, lambda: bool(app._notifications), message="no note")
        assert _lines(account)[0].startswith("Which account is this statement?")
        assert account._cursor == 1
        note = list(app._notifications)
        assert [n.title for n in note] == ["Failed"]
        assert words in str(note[0].message)
        assert _shown(account)["escape"] == "Cancel"
        assert [b["account_id"] for _, b in fake_client.posts] == ["aho"]
        assert _uploads(fake_client) == [True]

        await pilot.press("up", "enter")  # BCP Premier
        await _previewed(pilot, app)
        assert [b["account_id"] for _, b in fake_client.posts] == ["aho", "sig"]
        assert _uploads(fake_client) == [True, True]  # nothing written

    run_app(scenario, size=(120, 40))


def test_a_number_refusal_on_the_apply_shows_on_the_preview(fake_client, monkeypatch, tmp_path):
    """Only the dry run goes back to the question: the apply's refusal (a number
    changed in between) shows where apply refusals show."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})
    answer = fake_client.post

    def post(path_, json_body=None):
        if not json_body["dry_run"]:
            raise _refusal(
                "VALIDATION_ERROR",
                "account_id",
                "The paper prints the number ending 1492.",
                "STATEMENT_NUMBER_MISMATCH",
            )
        return answer(path_, json_body)

    fake_client.post = post

    async def scenario(pilot, app):
        await _card_preview(pilot, app, path)
        await pilot.press("enter")
        preview = await _refused(pilot, app)
        assert app.screen is preview
        assert "! account_id: The paper prints the number ending 1492." in _lines(preview)

    run_app(scenario, size=(120, 40))


def test_a_change_met_by_the_apply_previews_again_before_any_write(
    fake_client, monkeypatch, tmp_path
):
    """The apply's `409 CONFLICT` with `CONCURRENT_CHANGE`, on any key (here a matched
    line's; `file` is read whole at 80 columns below): the engine's words, the app's
    line, `⏎ Preview again`, a fresh dry run, and only then a new apply on its own `⏎`."""
    path = _pdf(tmp_path)
    key, words = "rows.4", "Another request changed this row's ledger line. Send it again."
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        fake_client.errors["POST"] = _refusal(
            "CONFLICT",
            key,
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
            f"! {key}: {words}",
            "Nothing was written.",
            "It changed while the upload ran: ⏎ checks the paper against the ledger again.",
        ]
        assert _shown(preview) == {"escape": "Cancel", "enter": "Preview again"}
        assert not list(app._notifications)  # the words once, on the screen
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


def test_a_change_met_by_the_apply_reads_whole_at_80_columns(fake_client, monkeypatch, tmp_path):
    """The `CONCURRENT_CHANGE` refusal on a narrow terminal: the engine's words, the app's line
    and the hint each wrap whole, none cut, and `⏎ Preview again` stays offered."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): CARD})
    words = (
        "Another request changed this statement's draft while the upload was being read, "
        "so none of its rows can be trusted. Send it again."
    )
    hint = "It changed while the upload ran: ⏎ checks the paper against the ledger again."

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        fake_client.errors["POST"] = _refusal(
            "CONFLICT",
            "file",
            words,
            "CONCURRENT_CHANGE",
            status=409,
            message="The ledger changed while the upload ran.",
        )
        await pilot.press("enter")
        await wait_for(pilot, lambda: bool(preview._failure), message="no failure shown")
        width = preview.query_one("#import-body", Static).content_region.width
        lines = _lines(preview, width=width)
        at = next(i for i, line in enumerate(lines) if line.startswith("CONFLICT"))
        shown = " ".join(lines[at:])
        for text in (
            "CONFLICT — The ledger changed while the upload ran.",
            f"! file: {words}",
            "Nothing was written.",
            hint,
        ):
            assert text in shown
        assert _shown(preview) == {"escape": "Cancel", "enter": "Preview again"}

    run_app(scenario, size=(80, 50))


def _flagged_close(fake_client, monkeypatch, tmp_path, count):
    """A card paper whose close lists one `review_lines` id on soles and two
    `not_covered` ids on dollars (a sum of three); `count` is what the engine's
    count answers, recorded in the returned list with the statement id asked."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    paper = {
        "rows": [r for r in CARD_ROWS if r["currency_code"] == "PEN"],
        "balances": [PEN_BALANCE],
        "review_lines": {"PEN": ["bl-1"]},
        "not_covered": {"USD": ["bl-2", "bl-3"]},
    }
    _engine(fake_client, {path.read_bytes(): paper})
    asked: list = []

    def counted(cfg, *, review_of, **kwargs):
        asked.append(review_of)
        if isinstance(count, Exception):
            raise count
        return count

    monkeypatch.setattr("expense.reads.count_bank_lines", counted)
    return path, asked


def test_a_review_list_the_engine_counts_empty_shows_no_flag(fake_client, monkeypatch, tmp_path):
    """The close names ids but the engine's count is 0: no `⚑` line, no `f`."""
    path, asked = _flagged_close(fake_client, monkeypatch, tmp_path, 0)

    async def scenario(pilot, app):
        await _card_preview(pilot, app, path)
        await pilot.press("enter")
        result = await _on(pilot, app, StatementResultScreen, "no result screen")
        assert asked == ["s-paper"]
        assert not any("⚑" in line for line in _lines(result))
        assert "f" not in _shown(result)

    run_app(scenario, size=(120, 50))


def test_a_count_that_fails_after_the_close_toasts_and_keeps_the_result(
    fake_client, monkeypatch, tmp_path
):
    """The apply is done: its counts stay on the result, the engine's words are
    toasted, and no `⚑` line or `f` shows."""
    refusal = EngineError("INTERNAL_ERROR", "the count broke", None, 500, {})
    path, asked = _flagged_close(fake_client, monkeypatch, tmp_path, refusal)

    async def scenario(pilot, app):
        await _card_preview(pilot, app, path)
        await pilot.press("enter")
        result = await _on(pilot, app, StatementResultScreen, "no result screen")
        assert asked == ["s-paper"]
        lines = _lines(result)
        assert lines[0].startswith("✓ ") and "closed" in lines[0]
        assert any("in the ledger" in line and "created" in line for line in lines[1:])
        assert not any("⚑" in line for line in lines)
        assert "f" not in _shown(result)
        (note,) = list(app._notifications)
        assert note.message == format_error(refusal)
        assert "the count broke" in note.message

    run_app(scenario, size=(120, 50))


def test_the_flagged_lines_of_an_account_with_no_code_show_no_ways(
    fake_client, monkeypatch, tmp_path
):
    """The picked account has no statement code: the flagged lines' screen shows
    no words about a twin."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    paper = {**SAVINGS, "review_lines": {"PEN": ["bl-uber"]}}
    _engine(fake_client, {path.read_bytes(): paper})
    monkeypatch.setattr(
        "expense.reads.fetch_bank_lines",
        lambda cfg, **kw: {"items": [LINES["bl-uber"]], "limit": 200, "next_cursor": None},
    )
    monkeypatch.setattr("expense.reads.count_bank_lines", lambda cfg, **kw: 1)

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _accounts(pilot, app)
        await pilot.press("down", "enter")  # Sueldo Soles, no statement code
        await _previewed(pilot, app)
        await pilot.press("enter")
        await _on(pilot, app, StatementResultScreen, "no result screen")
        await pilot.press("f")
        flagged = await _on(pilot, app, FlaggedLinesScreen, "f did not open the flagged lines")
        await wait_for(pilot, lambda: flagged._list is not None, message="flagged never read")
        assert flagged._statement_code is None
        assert not flagged.query("#fways")

    run_app(scenario, size=(120, 50))


# ---- several files of both kinds ------------------------------------------------
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
    """An empty row's `0.00` is drawn in no colour: it is no money in or out."""
    answer = statement_answer(statement_upload_answer(**CARD, dry_run=True))
    columns = Columns(answer, [], width=116)
    empty = row_line(answer.rows[9], columns)
    at = empty.plain.index("0.00")
    assert not [s for s in empty.spans if s.start <= at < s.end]
    matched = row_line(answer.rows[4], columns)  # +800.00 keeps its colour
    at = matched.plain.index("800.00")
    assert [s for s in matched.spans if s.start <= at < s.end]


@pytest.mark.parametrize(
    ("marked", "tail"),
    [
        ({"outcome": "new", "fee": True}, "+  New  · a fee, dated the last day"),
        ({"redated": True}, "✓  In the ledger  · day moved"),
    ],
    ids=["fee-note", "day-moved"],
)
def test_a_marked_row_stays_on_one_line_on_a_narrow_screen(
    fake_client, monkeypatch, tmp_path, marked, tail
):
    """The title column gives way to the widest row's mark, reason and note
    (the fee note, or `· day moved`), so such a row with a long title is one
    line, its title cut with `…`."""
    path = _pdf(tmp_path)
    _patch(monkeypatch)
    long_row = statement_row(
        1,
        -1240,
        day="2026-10-25",
        description="GASTO MENSUAL POR SEGURO DE DESGRAVAMEN DE LA TARJETA",
        **marked,
    )
    _engine(fake_client, {path.read_bytes(): {"rows": [long_row], "balances": CARD["balances"]}})
    note = tail.split("  ")[-1]

    async def scenario(pilot, app):
        preview = await _card_preview(pilot, app, path)
        raw = _body(preview, width=preview.size.width - 4).split("\n")
        (row,) = [line for line in raw if line.strip().startswith("1  2026-10-25")]
        assert row.rstrip().endswith(tail)
        assert "…" in row
        assert not any(note in line for line in raw if line is not row)

    run_app(scenario, size=(80, 40))


# ---- a line moved to the bank's day ----------------------------------------------------
#: A savings paper whose second row's line sits one day off it: matched, and moved
#: to the paper's day on ⏎ (contract: POST /v1/statements/import, "The bank's day wins").
MOVED = {
    **SAVINGS,
    "rows": [
        statement_row(1, 485000, day="2026-10-01", description="HABERES"),
        statement_row(2, -80000, day="2026-10-03", description="TRANSF", redated=True),
    ],
}


def test_a_moved_line_reads_day_moved_and_nothing_else_changes(fake_client, monkeypatch, tmp_path):
    """A row whose line moves to the paper's day reads `✓ In the ledger · day
    moved`, the mark alone with no old day, and a row matched on its own day
    no mark; the count line counts no move, and after ⏎ the close reads as any
    close."""
    path = _pdf(tmp_path, "BCP Ahorros 2026-10.pdf")
    _patch(monkeypatch)
    _engine(fake_client, {path.read_bytes(): MOVED})

    async def scenario(pilot, app):
        screen = await _open(app, pilot)
        await _drop(pilot, screen, path)
        await _accounts(pilot, app)
        await pilot.press("down", "enter")  # Sueldo Soles
        preview = await _previewed(pilot, app)
        lines = _lines(preview)
        assert _cells(lines[4]) == ["#", "date", "title", "amount"]
        assert _cells(lines[5]) == ["1", "2026-10-01", "HABERES", "+4,850.00", "✓", "In the ledger"]
        assert _cells(lines[6]) == [
            "2",
            "2026-10-03",
            "TRANSF",
            "-800.00",
            "✓",
            "In the ledger",
            "· day moved",
        ]
        assert lines[7:] == ["2 rows · 2 in the ledger · 0 new"]
        await pilot.press("enter")
        result = await _on(pilot, app, StatementResultScreen, "no result screen")
        assert _lines(result) == [
            "✓ Octubre 2026 closed · Sueldo Soles",
            "2 rows · 2 were in the ledger · 0 created",
        ]

    run_app(scenario, size=(120, 40))


def test_the_day_moved_mark_is_dim_as_the_fee_note_is():
    """`· day moved` is drawn as the fee note is: dim, after the reason."""
    rows = [
        statement_row(1, redated=True),
        statement_row(2, outcome="new", fee=True, day="2026-10-25"),
        statement_row(3),
    ]
    answer = statement_answer(statement_upload_answer(rows, dry_run=True))
    assert [row.redated for row in answer.rows] == [True, False, False]
    columns = Columns(answer, [], width=116)
    moved, fee, plain = (row_line(row, columns) for row in answer.rows)

    def styles(text, words: str) -> list[str]:
        at = text.plain.index(words)
        return [str(span.style) for span in text.spans if span.start <= at < span.end]

    assert moved.plain.rstrip().endswith("✓  In the ledger  · day moved")
    assert styles(moved, "· day moved") == styles(fee, "· a fee") == ["dim"]
    assert plain.plain.rstrip().endswith("✓  In the ledger")
