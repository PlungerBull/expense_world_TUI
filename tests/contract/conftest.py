"""Shared gating, target resolution and the real-ledger guard for tests/contract.

These tests hit a real engine and make real writes, so a contract run that would write to
the real ledger **refuses to start**. Point it at the disposable practice database
instead, or set EXPENSE_ALLOW_REAL_LEDGER=1 to say you meant it.

How to start the test engine on :8002, reseed its two practice users (the shared one, whose
key goes in EXPENSE_PAT, and the reserved-names one, whose key goes in EXPENSE_RESERVED_PAT)
and run this suite: docs/runtime.md "Working against the live engine".
"""

import base64
import io
import os
import random
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from openpyxl import Workbook

from expense import config as config_module
from expense.bank_import.engine import request_body
from expense.bank_line_write import line_body, new_part
from expense.config import Config
from expense.errors import EngineError
from expense.http import ExpenseClient
from tests.scripts_loader import load_script

# The default is the one real engine, the local deployment. A practice run sets
# EXPENSE_ENGINE_URL to the disposable test engine on :8002.
DEFAULT_ENGINE_URL = "http://127.0.0.1:8000"

ENGINE_URL = os.environ.get("EXPENSE_ENGINE_URL", DEFAULT_ENGINE_URL)
PAT = os.environ.get("EXPENSE_PAT")
#: The reserved-names practice user's key: the second one the reseed prints.
RESERVED_PAT = os.environ.get("EXPENSE_RESERVED_PAT")
ALLOW_REAL_LEDGER = os.environ.get("EXPENSE_ALLOW_REAL_LEDGER") == "1"

LIVE = os.environ.get("PYTEST_LIVE") == "1"

#: scripts/clean_practice_user.py: what a test may leave behind, and how it is removed.
CLEANER = load_script("clean_practice_user.py")


def reason_on(err: EngineError, field: str) -> str | None:
    """The engine's reason code for `field`, or None when it names no reason there
    (contract: "Error reasons")."""
    if not isinstance(err.reasons, dict):
        return None
    return err.reasons.get(field)


def read_signed(client: ExpenseClient, tx_id: str) -> dict:
    """The transaction read signed, negative for money out, so its `amount_cents` can
    be compared or sent back as is: write responses carry the magnitude and
    `transaction_type` (contract: "Base Conventions", "Sign convention — responses")."""
    return client.get(f"/transactions/{tx_id}", params={"debit_as_negative": "true"})


def transaction_count(client: ExpenseClient, account_id: str) -> int:
    """The account's live transactions, as `GET /transactions/count` counts them."""
    return client.get("/transactions/count", params={"account_id": account_id})["count"]


def live_ids(client: ExpenseClient, account_id: str) -> set[str]:
    """The ids of the account's live transactions on the first page of `GET /transactions`."""
    listed = client.get("/transactions", params={"account_id": account_id})
    return {item["id"] for item in listed["items"]}


def replace_parts(
    client: ExpenseClient, line_id: str, amounts: list[int], written: list[str]
) -> list[dict]:
    """Rewrite the bank line `line_id` into new parts of `amounts`, in one whole-line
    write sending only new ids, which replaces every part and keeps the line
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"). The body is the app's own
    (expense/bank_line_write.py). Each part id joins `written` before the call, so
    cleanup reaches whatever the engine created. Returns the parts as the answer reads
    them, in request order."""
    parts = [new_part(amount_cents=amount) for amount in amounts]
    written.extend(part["id"] for part in parts)
    answer = client.put(f"/bank-lines/{line_id}", json_body=line_body(parts))
    by_id = {part["id"]: part for part in answer["parts"]}
    return [by_id[part["id"]] for part in parts]


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config):
    """Run this suite in one process when `-n auto` comes from pyproject's addopts.

    Its tests share one practice user and make real writes (one seals periods the
    others write into), so they run one after another. xdist reads 0 workers as no
    distribution at all; an explicit `-n 4` still asks for workers. Holds when the
    run starts in tests/contract, where this conftest is loaded before xdist asks;
    tests/conftest.py covers a live run started above it.
    """
    return 0


def pytest_collection_modifyitems(config, items):
    """Gate the whole directory on PYTEST_LIVE=1.

    This is a hook, not a module-level `pytestmark`: a `pytestmark` assigned in a
    conftest does NOT apply to tests in other modules, so relying on it lets
    `pytest tests/contract` run against the live engine and create rows. The gate
    belongs somewhere that provably covers every item.
    """
    if LIVE:
        return
    skip = pytest.mark.skip(reason="Contract tests require PYTEST_LIVE=1")
    for item in items:
        item.add_marker(skip)


_REFUSAL = """
┌────────────────────────────────────────────────────────────┐
│  REFUSING TO RUN                                           │
│  this would write to your real ledger                      │
│    engine       {url:<42}│
│    signed in as you, from ~/.expense-config                │
│    rows created here are soft-deleted, never removed       │
│                                                            │
│  practice database instead:                                │
│    scripts/practice-engine up prints both practice keys    │
│    then EXPENSE_PAT=… EXPENSE_RESERVED_PAT=…               │
│    EXPENSE_ENGINE_URL=http://127.0.0.1:8002                │
│                                                            │
│  or, to mean it:                                           │
│    EXPENSE_ALLOW_REAL_LEDGER=1                             │
└────────────────────────────────────────────────────────────┘
"""


def _is_real_ledger() -> bool:
    """True when the run would write as the developer, to their own ledger.

    A PAT in the environment is the isolation signal: it is how the practice user
    is addressed. Without one, the only credential available is the developer's
    saved config — which is the real ledger by definition, whatever the URL says.
    """
    return not PAT


def pytest_sessionstart(session):
    """Refuse rather than warn — before collection, before any fixture.

    Deliberately a session hook rather than an autouse fixture: a fixture only runs
    when something requests it, and the guard must hold even if a future test
    forgets the `client` fixture entirely.
    """
    if not LIVE:
        return
    if _is_real_ledger() and not ALLOW_REAL_LEDGER:
        pytest.exit(_REFUSAL.format(url=ENGINE_URL), returncode=2)
    source = "EXPENSE_PAT" if PAT else "~/.expense-config (ALLOWED EXPLICITLY)"
    print(f"\ncontract target: {ENGINE_URL} · credential: {source}")


def _target() -> Config:
    """The resolved target: EXPENSE_PAT + EXPENSE_ENGINE_URL, or the developer's config
    only when the guard above has explicitly allowed it."""
    return Config(engine_url=ENGINE_URL, token=PAT) if PAT else config_module.ensure_loaded()


@pytest.fixture
def client():
    """An ExpenseClient aimed at the resolved target.

    Prefers EXPENSE_PAT + EXPENSE_ENGINE_URL so every module obeys the same target
    as the freshman walk; falls back to the developer's config only when the guard
    above has explicitly allowed it.
    """
    with ExpenseClient(_target()) as c:
        yield c


@pytest.fixture
def target() -> Config:
    """The resolved target as a `Config`, for a test driving one of the app's own modules
    that opens its clients from one (expense/import_/engine.py)."""
    return _target()


NO_RESERVED_PAT = (
    "EXPENSE_RESERVED_PAT is not set: pass the reserved-names practice user's key, the second "
    "one the reseed prints, inline on the contract suite's command line beside EXPENSE_PAT "
    '(docs/runtime.md "Working against the live engine")'
)


def reserved_target() -> Config:
    """The resolved target's engine as the reserved-names practice user, whose key comes
    only from EXPENSE_RESERVED_PAT. Without it, the test asking for it fails: it never
    skips, so a run that forgets the key cannot pass by leaving the test out."""
    if not RESERVED_PAT:
        pytest.fail(NO_RESERVED_PAT, pytrace=False)
    return Config(engine_url=ENGINE_URL, token=RESERVED_PAT)


@pytest.fixture
def reserved_client():
    """An ExpenseClient aimed at the resolved target as the reserved-names practice user,
    the one whose own category and hashtag hold the reserved names. Built like `client`,
    and covered by the same real-ledger refusal, which runs before any fixture."""
    with ExpenseClient(reserved_target()) as c:
        yield c


#: The words a leftover on the reserved-names practice user is listed under.
RESERVED_WHOSE = "the reserved-names user's "


def leak_targets(fixturenames: Iterable[str]) -> list[tuple[str, Config]]:
    """Whose records the leak check counts, each with the words its leftovers are listed
    under: the shared practice user's always, and the reserved-names practice user's too
    when the test asks for `reserved_client`, the one way a test writes as that user. So a
    test that does not ask for it never needs EXPENSE_RESERVED_PAT."""
    targets = [("", _target())]
    if "reserved_client" in fixturenames:
        targets.append((RESERVED_WHOSE, reserved_target()))
    return targets


def left_behind(before: dict[str, str], after: dict[str, str], whose: str = "") -> list[str]:
    """The labels of the records in `after` that `before` lacks, each under `whose`, sorted:
    `holdings` taken before and after a test (scripts/clean_practice_user.py)."""
    return sorted(f"{whose}{label}" for record, label in after.items() if record not in before)


@pytest.fixture(autouse=True)
def leaves_nothing(request):
    """Fails the test whose teardown leaves an account, category or hashtag it made, on
    the shared practice user or, for a test asking for `reserved_client`, on the
    reserved-names one (`leak_targets`).

    Autouse, so it is set up before every fixture a test asks for and torn down after
    them, the `scratch` cleanup included. It reads through clients of its own, so the
    `statuses` a test reads never see its calls. What it counts is the cleanup script's
    `holdings`, which leaves out the system rows the engine creates on first need. A
    leftover is listed by whose it is, kind and name; scripts/clean_practice_user.py
    removes it (docs/runtime.md "Working against the live engine")."""
    with ExitStack() as stack:
        owners = [
            (whose, stack.enter_context(ExpenseClient(target)))
            for whose, target in leak_targets(request.fixturenames)
        ]
        before = [CLEANER.holdings(own) for _, own in owners]
        yield
        left = [
            label
            for (whose, own), held in zip(owners, before, strict=True)
            for label in left_behind(held, CLEANER.holdings(own), whose)
        ]
    if left:
        pytest.fail(f"the test left {len(left)} record(s) behind: {', '.join(left)}")


@pytest.fixture
def statuses(client):
    """The HTTP status of every response `client` receives, in order. The client
    returns only the body on success, so a status such as `201` is read off httpx's
    own hook on the repo client's transport."""
    seen: list[int] = []
    hooks = client._client.event_hooks
    hooks["response"] = [*hooks.get("response", []), lambda r: seen.append(r.status_code)]
    return seen


# ---- statements: accounts with a statement code, their reconciliations and lines ----

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def free_statement_codes(client: ExpenseClient, count: int) -> list[str]:
    """`count` different statement codes no account of the caller's holds, so a test's
    codes clash with nothing but what it builds itself, whatever an earlier run left.
    A deleted account holds no code; an archived account and a person are read too
    (contract: "Bank Accounts", "Shared only across currencies")."""
    listed = client.get("/accounts", params={"include_people": "true", "include_archived": "true"})
    held = {item["statement_code"] for item in listed["items"]}
    rng = random.SystemRandom()
    codes: list[str] = []
    while len(codes) < count:
        code = "".join(rng.choice(_LETTERS) for _ in range(3))
        if code not in held and code not in codes:
            codes.append(code)
    return codes


def refused(call) -> EngineError:
    """The engine's refusal of `call`, which must be refused."""
    with pytest.raises(EngineError) as excinfo:
        call()
    return excinfo.value


def assert_refusals(err: EngineError, status: int, code: str, reasons: dict[str, str]) -> None:
    """The refusal is `status` `code`, keyed on exactly the keys of `reasons`, each
    carrying its reason (contract: "Base Conventions", "`fields` and `reasons` semantics")."""
    assert (err.status, err.code) == (status, code), (err.status, err.code, err.reasons)
    assert err.reasons == reasons, err.reasons
    assert isinstance(err.fields, dict) and set(err.fields) == set(reasons), err.fields


def assert_refusal(err: EngineError, status: int, code: str, key: str, reason: str) -> None:
    """The refusal is `status` `code`, keyed on `key` alone, carrying `reason` there."""
    assert_refusals(err, status, code, {key: reason})


def workbook(rows: list[list]) -> str:
    """A made-up `.xlsx`, in standard base64 as the engine's file uploads take it: one
    sheet named `data` holding `rows` from row 1 down, each cell as given (`None` an empty
    cell) (contract: POST /v1/transactions/import, "The download"). Never one of the
    owner's real files: this repo is public."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "data"
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return base64.b64encode(out.getvalue()).decode("ascii")


#: The two headers of the bank's download (contract: POST /v1/transactions/import,
#: "The download"): a current account's, with an operation number and `DD/MM/YYYY`
#: days, and a card's, without one and with `YYYY-MM-DD` days.
CURRENT_HEADER = ["Fecha", "Descripcion", "Moneda", "Monto", "Numero de Operacion"]
CARD_HEADER = ["Fecha", "Descripcion", "Moneda", "Monto"]


def download_body(account_id: str, rows: list[list], *, dry_run: bool) -> dict:
    """The `POST /transactions/import` body for a made-up download holding `rows`
    (`workbook`), built by the import door's own `request_body`."""
    return request_body(account_id, base64.b64decode(workbook(rows)), dry_run=dry_run)


def send_download(
    client: ExpenseClient, account_id: str, rows: list[list], *, dry_run: bool
) -> dict:
    """The made-up download holding `rows` sent whole, as the import door sends it;
    the engine's answer."""
    return client.post(
        "/transactions/import", json_body=download_body(account_id, rows, dry_run=dry_run)
    )


#: The sheet import's header, columns A to L in order
#: (contract: POST /v1/transactions/import-sheet, "The sheet").
SHEET_HEADER = [
    "description",
    "HASHTAG",
    "CATEGORY",
    "FECHA",
    "MONTO",
    "CUENTA",
    "T.C.",
    "MONEDA",
    "Solarizado",
    "ESTADO_CUENTA",
    "NOTAS",
    "COD_EECC",
]


def sheet_row(
    title: str,
    hashtag: str,
    category: str,
    day: date,
    amount: float,
    account: str,
    currency: str,
    *,
    note: str | None = None,
    code: str | None = None,
) -> list:
    """One row of a made-up sheet, its cells in `SHEET_HEADER`'s order: `day` saved as a
    date, `amount` signed (negative an outflow), the columns the engine never reads empty."""
    return [title, hashtag, category, day, amount, account, None, currency, None, None, note, code]


def sheet_file(rows: list[list]) -> bytes:
    """A made-up sheet of the books as `expense import sheet` reads it from disk: the
    workbook's bytes, `SHEET_HEADER` on row 1 and `rows` (`sheet_row`) below it
    (`workbook`). Never the owner's real sheet: this repo is public."""
    return base64.b64decode(workbook([SHEET_HEADER, *rows]))


# ---- made-up statement PDFs ----
#
# The contract names what a BCP paper holds, in words (contract: POST /v1/reconciliations/import,
# "The paper"). Where each thing sits on the page it does not state: the layout below is what
# the engine's dry-run answers show it reads, learnt from the page, line and cell its
# `UNEXPECTED_LAYOUT` messages name. The engine ask "Publish one made-up sample statement PDF
# per paper, so every client can test the statement upload" asks for it to be stated.

#: Every character of a made-up paper is Courier, whose characters are all one width, at
#: this size, so a line is a row of character cells: the engine's answers show it reads a
#: savings account's paper as such a grid, each of its columns a range of cells.
_PDF_FONT_SIZE = 7
#: Where the cells start, how far apart two lines print (closer lines read as one), and the
#: page's top and bottom margins, all in points.
_PDF_LEFT = 20
_PDF_LINE = 15
_PDF_MARGIN = 40


def _pdf_text(text: str) -> bytes:
    """`text` as a PDF string literal's bytes, its delimiters escaped."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return escaped.encode("latin-1")


def pdf_file(pages: list[list[list[tuple[str, float]]]]) -> bytes:
    """A made-up PDF of `pages`, each a list of lines from the top down, each line its
    layers: `(text, rise)`, `text` printed from the first cell of the grid, `rise` points
    above the line's baseline. Every page is as tall as its lines need. Never one of the
    owner's real statements: this repo is public."""
    objects: list[bytes] = [
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
        b"",  # the page tree, written once its pages are numbered
    ]
    kids: list[int] = []
    for lines in pages:
        height = 2 * _PDF_MARGIN + _PDF_LINE * len(lines)
        ops = []
        for index, layers in enumerate(lines):
            baseline = height - _PDF_MARGIN - _PDF_LINE * index
            for text, rise in layers:
                if text.strip():
                    at = str(baseline + rise).encode()
                    ops.append(
                        b"BT /F1 %d Tf %d %s Td (%s) Tj ET"
                        % (_PDF_FONT_SIZE, _PDF_LEFT, at, _pdf_text(text))
                    )
        stream = b"\n".join(ops)
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 %d] "
            b"/Resources << /Font << /F1 1 0 R >> >> /Contents %d 0 R >>" % (height, len(objects))
        )
        kids.append(len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % kid for kid in kids),
        len(kids),
    )
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        len(objects),
        xref,
    )
    return bytes(out)


def _cells(*placed: tuple[int, str]) -> str:
    """One line of the grid: each `(cell, text)` written from that cell on."""
    line = ""
    for cell, text in placed:
        line = line.ljust(cell)
        line = line[:cell] + text + line[cell + len(text) :]
    return line


def _ending(cell: int, text: str) -> tuple[int, str]:
    """`text` placed so that its last character falls in `cell`: an amount, right-aligned."""
    return cell - len(text) + 1, text


#: A savings account's paper, as its cells, as the engine's answers show it reads them (the
#: contract does not state them): the processing date, the value date, the description (up to
#: `_TEXT_WIDTH` characters), and the amount, out ending in `_OUT_END` or in ending in
#: `_IN_END`. The engine reads the header word for word, and the totals line's amounts only
#: under its `CARGOS` and `ABONOS`, so they end in the same cells.
_PROCESSED, _VALUED, _TEXT, _TEXT_WIDTH, _OUT_END, _IN_END = 14, 20, 26, 18, 67, 86
_SAVINGS_HEADER = _cells(
    (0, "FECHA PROC."),
    (12, "FECHA VALOR"),
    (_TEXT, "DESCRIPCION"),
    _ending(_OUT_END, "CARGOS / DEBE"),
    _ending(_IN_END, "ABONOS / HABER"),
)
#: How far above its label, in points, a totals line's amounts print. The engine's answers
#: show it reads the label standing alone on its line and the amounts beside it a little off
#: its baseline; on the label's own baseline they join its line, and the label does not read.
#: The contract does not state it.
_BESIDE = 3
_MONTHS = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SET", "OCT", "NOV", "DIC")
_SAVINGS_CURRENCIES = {"PEN": ("Soles", "SOLES"), "USD": ("Dolares", "US DOLARES")}


def paper_amount(cents: int) -> str:
    """`cents` as the paper prints an amount, unsigned: `1,234.50`."""
    whole, part = divmod(abs(cents), 100)
    return f"{whole:,}.{part:02d}"


def paper_day(day: date) -> str:
    """`day` as a row of the paper prints it: `05MAR`."""
    return f"{day.day:02d}{_MONTHS[day.month - 1]}"


@dataclass(frozen=True)
class PaperRow:
    """One row of a made-up savings paper: its day (its processing and value date both), its
    description, and its amount in cents, signed: negative out (`CARGOS`), positive in
    (`ABONOS`), `0` a row of `0.00`, printed in the out column."""

    day: date
    description: str
    amount_cents: int


def savings_paper(
    rows: list[PaperRow],
    *,
    start: date,
    end: date,
    before_cents: int,
    currency: str = "PEN",
    closing_cents: int | None = None,
    rows_per_page: int = 40,
) -> bytes:
    """A made-up BCP savings account statement (`Estado de Cuenta de Ahorros`) in
    `currency`, over `start` to `end`, holding what the contract says such a paper holds
    (contract: POST /v1/reconciliations/import, "The paper"): its previous balance
    `before_cents` (`SALDO ANTERIOR`), its `rows` out (`CARGOS`) and in (`ABONOS`) in paper
    order, and its closing balance (`SALDO`). Its totals out and in and its closing balance
    are the rows' own, so it reads; `closing_cents` prints another closing balance, which
    the rows do not add up to. Laid out as the comments above say, `rows_per_page` to a
    page: every page carries the title, the currency, the period, its `n DE m`, the header
    and the totals' labels (`TOTAL MOVIMIENTO`, `SALDO`), whose amounts print on the last
    page only. Never one of the owner's real statements: this repo is public; every name and
    number in it is made up by the test."""
    assert all(len(row.description) <= _TEXT_WIDTH for row in rows), "a description too long"
    out = sum(-row.amount_cents for row in rows if row.amount_cents < 0)
    into = sum(row.amount_cents for row in rows if row.amount_cents > 0)
    closing = before_cents + into - out if closing_cents is None else closing_cents
    word, printed = _SAVINGS_CURRENCIES[currency]
    period = f"DEL {start:%d/%m/%y} AL {end:%d/%m/%y}"
    chunks = [rows[i : i + rows_per_page] for i in range(0, len(rows), rows_per_page)] or [[]]
    pages = []
    for number, chunk in enumerate(chunks, start=1):
        last = number == len(chunks)
        lines = [
            _cells((80, f"{number} DE {len(chunks)}")),
            f"Estado de Cuenta de Ahorros {word}",
            "MONEDA",
            printed,
            period,
            _SAVINGS_HEADER,
        ]
        if number == 1:
            lines.append(
                _cells((_TEXT, "SALDO ANTERIOR"), _ending(_IN_END, paper_amount(before_cents)))
            )
        for row in chunk:
            end_cell = _IN_END if row.amount_cents > 0 else _OUT_END
            lines.append(
                _cells(
                    (_PROCESSED, paper_day(row.day)),
                    (_VALUED, paper_day(row.day)),
                    (_TEXT, row.description),
                    _ending(end_cell, paper_amount(row.amount_cents)),
                )
            )
        totals = _cells(_ending(_OUT_END, paper_amount(out)), _ending(_IN_END, paper_amount(into)))
        balance = _cells(_ending(_IN_END, paper_amount(closing)))
        lines += [
            "",
            [(_cells((_TEXT, "TOTAL MOVIMIENTO")), 0), (totals if last else "", _BESIDE)],
            [(_cells((_TEXT, "SALDO")), 0), (balance if last else "", _BESIDE)],
        ]
        pages.append([[(line, 0)] if isinstance(line, str) else line for line in lines])
    return pdf_file(pages)


def statement_body(account_id: str, paper: bytes, *, dry_run: bool) -> dict:
    """The `POST /reconciliations/import` body for `paper`: exactly its three keys, the
    file in standard base64 (contract: POST /v1/reconciliations/import)."""
    return {
        "dry_run": dry_run,
        "account_id": account_id,
        "file": base64.b64encode(paper).decode("ascii"),
    }


def send_statement(client: ExpenseClient, account_id: str, paper: bytes, *, dry_run: bool) -> dict:
    """`paper` sent whole as `account_id`'s statement; the engine's answer."""
    return client.post(
        "/reconciliations/import", json_body=statement_body(account_id, paper, dry_run=dry_run)
    )


def account_body(currency: str = "PEN", code: str | None = None) -> dict:
    """A `POST /accounts` body under a fresh id, with `statement_code` when given."""
    new_id = str(uuid4())
    body = {"id": new_id, "name": f"contract-stmt-{new_id[:8]}", "currency_code": currency}
    if code is not None:
        body["statement_code"] = code
    return body


def reconciliation_body(account_id: str, start: str, end: str, twin: str | None = None) -> dict:
    """A `POST /reconciliations` body under a fresh id over the calendar days `start`
    to `end`, with an ending balance so nothing but the rule under test stands in the
    way of completing it; with `twin`, the other half of a card statement on that
    account, under its own fresh id (contract: POST /v1/reconciliations)."""
    new_id = str(uuid4())
    body = {
        "id": new_id,
        "account_id": account_id,
        "name": f"contract-stmt-recon-{new_id[:8]}",
        "date_start": start,
        "date_end": end,
        "beginning_balance_cents": 0,
        "ending_balance_cents": 0,
    }
    if twin is not None:
        body["twin"] = {
            "id": str(uuid4()),
            "account_id": twin,
            "beginning_balance_cents": 0,
            "ending_balance_cents": 0,
        }
    return body


def send_order(client: ExpenseClient, recon: str, places: list[str | None]) -> dict:
    """Sends `places`, the statement's lines top to bottom with `None` for an empty slot,
    as `recon`'s statement order; the engine's answer
    (contract: PUT /v1/reconciliations/{reconciliation_id}/statement-order)."""
    return client.put(f"/reconciliations/{recon}/statement-order", json_body={"places": places})


class Scratch:
    """What one test builds on the practice user, undone in reverse dependency order:
    archived accounts unarchived, reconciliations reverted and deleted (each statement
    once), transactions deleted, hashtags, categories and accounts deleted. Every step
    is best-effort, so a failed test still frees its statement codes."""

    def __init__(self, client: ExpenseClient) -> None:
        self.client = client
        self.zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
        self.accounts: list[str] = []
        self.reconciliations: list[str] = []
        self.transactions: list[str] = []
        self.categories: list[str] = []
        self.hashtags: list[str] = []
        self._first_part: dict[str, str] = {}

    def account(self, currency: str = "PEN", code: str | None = None) -> str:
        body = account_body(currency, code)
        self.accounts.append(body["id"])
        self.client.post("/accounts", json_body=body)
        return body["id"]

    def person(self, currency: str = "PEN") -> str:
        new_id = str(uuid4())
        self.accounts.append(new_id)
        self.client.post(
            "/people",
            json_body={
                "id": new_id,
                "name": f"contract-stmt-p-{new_id[:8]}",
                "currency_code": currency,
            },
        )
        return new_id

    def archive(self, account_id: str) -> None:
        """Archives the account; cleanup unarchives every account it made."""
        self.client.post(f"/accounts/{account_id}/archive")

    def category(self) -> str:
        """A new category of the caller's; its id."""
        new_id = str(uuid4())
        self.categories.append(new_id)
        self.client.post(
            "/categories",
            json_body={"id": new_id, "name": f"contract-stmt-c-{new_id[:8]}", "color": "#123456"},
        )
        return new_id

    def hashtag(self) -> str:
        """A new hashtag of the caller's; its id."""
        new_id = str(uuid4())
        self.hashtags.append(new_id)
        self.client.post("/hashtags", json_body={"id": new_id, "name": f"contract-h-{new_id[:8]}"})
        return new_id

    def reconciliation(self, account_id: str, start: str, end: str) -> str:
        """A draft over the calendar days `start` to `end`, made alone (`reconciliation_body`)."""
        body = reconciliation_body(account_id, start, end)
        self.reconciliations.append(body["id"])
        self.client.post("/reconciliations", json_body=body)
        return body["id"]

    def card(self, account_id: str, twin_account_id: str, start: str, end: str) -> tuple[str, str]:
        """Both halves of a card statement over `start` to `end`, in one create: the
        half on `account_id` and its twin on `twin_account_id`; their ids, in that order."""
        body = reconciliation_body(account_id, start, end, twin=twin_account_id)
        self.reconciliations.extend((body["id"], body["twin"]["id"]))
        self.client.post("/reconciliations", json_body=body)
        return body["id"], body["twin"]["id"]

    def noon(self, day: str) -> str:
        y, m, d = (int(part) for part in day.split("-"))
        return datetime(y, m, d, 12, tzinfo=self.zone).isoformat(timespec="seconds")

    def _item(self, account_id: str, day: str, amount: int, **fields: str) -> dict:
        return {
            "id": str(uuid4()),
            "title": "contract statement line",
            "amount_cents": amount,
            "account_id": account_id,
            "date": self.noon(day),
            **fields,
        }

    def _create(self, items: list[dict]) -> list[dict]:
        """Creates `items` in one batch; the created items, in request order."""
        self.transactions.extend(item["id"] for item in items)
        created = self.client.post("/transactions/batch", json_body={"transactions": items})
        for item in created["created"]:
            self._first_part.setdefault(item["bank_line_id"], item["id"])
        return created["created"]

    def line(self, account_id: str, day: str, *amounts: int, recon: str | None = None) -> str:
        """A new bank line on `day` holding one part per amount (a batch `line_group`
        for more than one), assigned whole to `recon` when given (`assign`); its id."""
        group = {"line_group": "g"} if len(amounts) > 1 else {}
        items = [self._item(account_id, day, amount, **group) for amount in amounts]
        first = self._create(items)[0]
        if recon is not None:
            self.assign(first["bank_line_id"], recon)
        return first["bank_line_id"]

    def lines_into(self, recon: str, account_id: str, day: str, *amounts: int) -> list[str]:
        """One batch of one single-part line per amount, all on one instant, each created
        straight into `recon` by the create itself; the lines' ids, in request order."""
        items = [self._item(account_id, day, amount, reconciliation_id=recon) for amount in amounts]
        return [item["bank_line_id"] for item in self._create(items)]

    def assign(self, line_id: str, recon: str) -> None:
        """Assigns the whole bank line `line_id`, one this Scratch made, to `recon` by
        sending `reconciliation_id` on its first part, which writes it on every live part
        of the line
        (contract: PUT /v1/transactions/{transaction_id}, "Reconciliation assignment")."""
        self.client.put(
            f"/transactions/{self._first_part[line_id]}", json_body={"reconciliation_id": recon}
        )

    def opening_balance(self, account_id: str, day: str, recon: str | None = None) -> str:
        """The account's opening balance, assigned to `recon` when given; its line's id."""
        tx_id = str(uuid4())
        self.transactions.append(tx_id)
        made = self.client.post(
            f"/accounts/{account_id}/opening-balance",
            json_body={"transaction_id": tx_id, "amount_cents": 50000, "date": self.noon(day)},
        )
        self._first_part[made["bank_line_id"]] = tx_id
        if recon is not None:
            self.assign(made["bank_line_id"], recon)
        return made["bank_line_id"]

    def took(self, answer: dict) -> list[str]:
        """Takes on what an upload's answer says it wrote, a bank download's
        (`send_download`) or a statement's (`send_statement`): every transaction it created
        and, for a statement, every half it created or filled, so cleanup reverts and
        deletes them. Sent on a dry run too, it takes on nothing. The created transactions'
        ids, in row order."""
        for half in answer.get("halves", []):
            if half["reconciliation_id"] not in (None, *self.reconciliations):
                self.reconciliations.append(half["reconciliation_id"])
        created = [row["transaction_id"] for row in answer["rows"] if row["transaction_id"]]
        self.transactions.extend(created)
        return created

    def _quietly(self, call, path: str) -> dict | None:
        try:
            return call(path)
        except EngineError:
            return None

    def cleanup(self) -> None:
        """A revert and a delete each act on a whole statement, both halves of a card
        from either one (contract: DELETE /v1/reconciliations/{reconciliation_id}), so
        a half the delete of its twin took is not sent again."""
        for account in self.accounts:
            self._quietly(self.client.post, f"/accounts/{account}/unarchive")
        for recon in self.reconciliations:
            self._quietly(self.client.post, f"/reconciliations/{recon}/revert")
        gone: set[str] = set()
        for recon in self.reconciliations:
            if recon in gone:
                continue
            answer = self._quietly(self.client.delete, f"/reconciliations/{recon}")
            if answer is not None and answer.get("twin") is not None:
                gone.add(answer["twin"]["id"])
        for tx in self.transactions:
            self._quietly(self.client.delete, f"/transactions/{tx}")
        for hashtag in self.hashtags:
            self._quietly(self.client.delete, f"/hashtags/{hashtag}")
        for category in self.categories:
            self._quietly(self.client.delete, f"/categories/{category}")
        for account in self.accounts:
            self._quietly(self.client.delete, f"/accounts/{account}")


@pytest.fixture
def scratch(client):
    """A `Scratch` on the practice user, cleaned up after the test whatever its outcome."""
    made = Scratch(client)
    yield made
    made.cleanup()
