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
import itertools
import os
import random
from collections.abc import Callable, Iterable
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import cache, partial
from typing import Any
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

#: The colour a create gives when `color` is left out (contract: "Colour format").
DEFAULT_COLOR = "#3b82f6"

#: The practice account the seed holds, `BCP-0000`, by the id the seed printed
#: (`EXPENSE_PRACTICE_ACCOUNT_ID`, docs/runtime.md "Working against the live engine"). The only
#: account the engine's statement samples upload to, since they print numbers ending `0000`; a
#: test that uses it undoes every change it makes there (`practice_account`).
PRACTICE_ACCOUNT_ID = os.environ.get("EXPENSE_PRACTICE_ACCOUNT_ID")


def minute_before(now: datetime, zone: ZoneInfo) -> datetime:
    """The moment a minute before `now`, in `zone`: the moment a recent row is dated at. The
    minute comes off in real time, then the result is read in `zone`, so a wall clock that
    just jumped forward still gives a time that exists."""
    return (now - timedelta(minutes=1)).astimezone(zone)


def month_of(moment: datetime) -> dict[str, str]:
    """The `year` and `month` a report is asked for to hold a row dated at `moment`, read in
    `moment`'s own zone (the zone a month is cut in), so a row and its month share one reading."""
    return {"year": str(moment.year), "month": str(moment.month)}


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


# ---- statements: accounts with a statement code, their statements and lines ----

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def free_statement_codes(client: ExpenseClient, count: int) -> list[str]:
    """`count` different statement codes no account of the caller's holds, so a test's
    codes clash with nothing but what it builds itself, whatever an earlier run left.
    A deleted account holds no code; an archived account and a person are read too
    (contract: "What an account is", "One account per code")."""
    held = {item["statement_code"] for item in all_accounts(client)}
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


def balance_of(statement: dict, code: str) -> dict:
    """The statement's balance entry for the currency `code`."""
    return next(b for b in statement["balances"] if b["currency_code"] == code)


def statement_codes(statement: dict) -> list[str]:
    """The currency codes the statement holds balances for, in the engine's order."""
    return [entry["currency_code"] for entry in statement["balances"]]


def account_balance(client: ExpenseClient, account_id: str, code: str = "PEN") -> int:
    """The account's current balance in the currency `code`, in cents
    (contract: "Bank Accounts", "Account response")."""
    held = client.get(f"/accounts/{account_id}")
    return next(c for c in held["currencies"] if c["currency_code"] == code)[
        "current_balance_cents"
    ]


def all_accounts(client: ExpenseClient) -> list[dict]:
    """Every account the caller has, as `GET /accounts` lists them: bank accounts, the cash
    account and people, archived ones included, each whole with its currencies."""
    params = {"include_people": "true", "include_archived": "true"}
    return client.get("/accounts", params=params)["items"]


def refused_keeping(
    read: Callable[[], Any], call: Callable[[], Any], what: Any = ""
) -> EngineError:
    """The engine's refusal of `call`, with `read()` giving the same before and after it;
    `what` (the body sent, say) names the case in the failure message."""
    before = read()
    err = refused(call)
    assert read() == before, what
    return err


def refused_writing_nothing(client: ExpenseClient, call) -> EngineError:
    """The engine's refusal of `call`, with every account the caller has (`all_accounts`:
    version, `updated_at`, kind, archive state, every currency's balance and opening
    balance) read the same before and after it."""
    return refused_keeping(partial(all_accounts, client), call)


def refused_line_write(client: ExpenseClient, line_id: str, body: dict) -> EngineError:
    """The engine's refusal of `body` sent to the line (`PUT /bank-lines/{id}`), with one
    read of the line (`GET /bank-lines/{id}`, its parts included as that read shapes them)
    the same before and after, and no part `body` names under a new id existing
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Refusals, in order")
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")."""
    read = partial(client.get, f"/bank-lines/{line_id}")
    held = {p["id"] for p in read()["parts"]}
    err = refused_keeping(read, lambda: client.put(f"/bank-lines/{line_id}", json_body=body), body)
    for part in body.get("parts", []):
        if part["id"] not in held:
            gone = refused(lambda part=part: client.get(f"/transactions/{part['id']}"))
            assert gone.status == 404, part
    return err


def assert_refusals(err: EngineError, status: int, code: str, reasons: dict[str, str]) -> None:
    """The refusal is `status` `code`, keyed on exactly the keys of `reasons`, each
    carrying its reason
    (contract: "Base Conventions", "`fields`, `reasons` and `details` semantics")."""
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


#: The last 4 digits every bank account the suite makes is numbered by, drawn without repeating
#: from 9200 to 9999 (a name is unique among the live accounts, so two accounts never share
#: one). Every number starts with `CLEANER.TEST_LAST4_PREFIX`, which is how the cleaner tells
#: what the suite made; the seed's `0000` and `DRAWN_LAST4` are outside the draw.
_NUMBERS = itertools.cycle(random.sample(range(9200, 10000), 800))

#: A test the engine's later versions fail: a close or an upload refused while a bank line in no
#: statement sits on a day it would seal. The next catch-up rewrites it and drops the mark.
LOOSE_LINES_ON_SEALED_DAYS = pytest.mark.xfail(
    strict=True,
    reason="LOOSE_LINES_ON_SEALED_DAYS: engine versions cd6574eee1dd5ec0 and 5a465cd6cf5f21fe",
)

#: A test of the sheet import's create step, which makes a bank account from the sheet's typed
#: name, as the engine no longer lets a bank account be named (`NAME_BUILT`). The official
#: import's rewrite on built names (docs/specs/before-the-official-import.md) drops the mark.
SHEET_IMPORT_TYPES_A_NAME = pytest.mark.xfail(
    strict=True,
    reason="the sheet import creates a bank account from a typed name, NAME_BUILT: "
    "docs/specs/before-the-official-import.md",
)

#: The number a made-up statement paper prints unless a test gives another; a test that uploads
#: one makes its account with it (`last4=DRAWN_LAST4`).
DRAWN_LAST4 = "9100"


def next_last4() -> str:
    """The last 4 digits of a new bank account of the suite's: the next of the draw, so none
    repeats within a run. An account an earlier run left behind may still hold it (the
    cleaner removes such leftovers)."""
    return str(next(_NUMBERS))


# ---- made-up statement PDFs ----
#
# The contract states what a BCP paper holds and where (contract: POST /v1/statements/import,
# "The paper's layout"): lines read left to right within 1 point of a line's first character,
# a savings account's table a fixed-width record of columns 0 to 72 and a card's of columns 0 to
# 106, in one fixed-pitch font.

#: Every character of a made-up paper is Courier, whose characters are all one width, at
#: this size, so a line is a row of character cells, each cell a column of the stated table.
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


#: A savings account's table by its stated columns (contract: POST /v1/statements/import,
#: "The paper's layout"): the processing date from column 0, the value date from column 6,
#: the description from column 12 (18 characters at most, `_TEXT_WIDTH`), and the amount, out
#: ending in column 53 (`_OUT_END`) or in ending in column 72 (`_IN_END`). Column 0 is the
#: first cell, so `SALDO ANTERIOR` starts in column 12 as the layout asks. The column header
#: line is read word for word, and the totals' amounts print within 5 points of their labels,
#: the out total left and the in total and closing balance right of the point halfway between
#: where `DEBE` and `HABER` end.
_PROCESSED, _VALUED, _TEXT, _TEXT_WIDTH, _OUT_END, _IN_END = 0, 6, 12, 18, 53, 72
_SAVINGS_HEADER = _cells(
    (0, "FECHA PROC."),
    (12, "FECHA VALOR"),
    (24, "DESCRIPCION"),
    _ending(_OUT_END, "CARGOS / DEBE"),
    _ending(_IN_END, "ABONOS / HABER"),
)
#: How far above its label, in points, a totals line's amounts print: within 5 points of the
#: label's line and more than 1 point off it, since each label stands alone on its line.
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
    """One row of a made-up savings paper: its day (its value date, and its processing date
    too unless `processed` is given), its description, and its amount in cents, signed:
    negative out (`CARGOS`), positive in (`ABONOS`), `0` a row of `0.00`, printed in the out
    column."""

    day: date
    description: str
    amount_cents: int
    processed: date | None = None


def savings_paper(
    rows: list[PaperRow],
    *,
    start: date,
    end: date,
    before_cents: int,
    currency: str = "PEN",
    closing_cents: int | None = None,
    rows_per_page: int = 40,
    last4: str = DRAWN_LAST4,
) -> bytes:
    """A made-up BCP savings account statement (`Estado de Cuenta de Ahorros`) in
    `currency`, over `start` to `end`, holding what the contract says such a paper holds
    (contract: POST /v1/statements/import, "The paper"): its previous balance
    `before_cents` (`SALDO ANTERIOR`), its `rows` out (`CARGOS`) and in (`ABONOS`) in paper
    order, and its closing balance (`SALDO`). Its totals out and in and its closing balance
    are the rows' own, so it reads; `closing_cents` prints another closing balance, which
    the rows do not add up to. Laid out as the comments above say, `rows_per_page` to a
    page: every page carries the title, the account code ending in `last4`, the currency, the
    period, its `n DE m`, the header and the totals' labels (`TOTAL MOVIMIENTO`, `SALDO`), whose
    amounts print on the last page only. Never one of the owner's real statements: this repo is
    public; every name and number in it is made up by the test."""
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
            "CODIGO DE CUENTA",
            f"191-1234567{last4[0]}-{last4[1]}-{last4[2:]}",
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
                    (_PROCESSED, paper_day(row.processed or row.day)),
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


#: A card's table by its stated columns (contract: POST /v1/statements/import, "The paper's
#: layout"): the processing date from column 0, the purchase date from column 9, the
#: description (or an undated line's label) from column 18, the type from column 73, the soles
#: figure ending in column 93 and the dollars figure ending in column 105, each followed by `-`
#: in the next column for a credit. `SALDO ANTERIOR` starts in column 18 as the layout asks, so
#: the grid's cell 0 is column 0. The two header lines read word for word.
_CARD_PROCESSED, _CARD_PURCHASED, _CARD_TEXT, _CARD_TYPE = 0, 9, 18, 73
_CARD_END = {"PEN": 93, "USD": 105}
_CARD_HEADERS = (
    _cells(
        (0, "Fecha de"),
        (9, "Fecha de"),
        (18, "Descripción"),
        (73, "Tipo de"),
        (86, "Soles"),
        (98, "Dólares"),
    ),
    _cells((0, "proceso"), (9, "consumo"), (73, "Operación")),
)


@dataclass(frozen=True)
class CardRow:
    """One dated row of a made-up card paper: its purchase day, description, type
    (`CONSUMO`, `PAGO`, …) and amount in cents in `currency`, as the paper prints it: positive
    a purchase or charge, negative a credit (printed with `-`). The processing date is the
    purchase day unless `processed` is given."""

    day: date
    description: str
    type: str
    amount_cents: int
    currency: str = "PEN"
    processed: date | None = None


@dataclass(frozen=True)
class CardCharge:
    """One undated line of a made-up card paper (interest, a fee): its label and amount in
    cents in `currency`, positive a charge, negative a credit."""

    label: str
    amount_cents: int
    currency: str = "PEN"


def _card_figure(currency: str, cents: int) -> list[tuple[int, str]]:
    """A card's figure in `currency`'s column: the amount ending in the column, `-` after it
    when `cents` is negative."""
    end = _CARD_END[currency]
    return [_ending(end, paper_amount(cents)), *([(end + 1, "-")] if cents < 0 else [])]


def card_paper(
    rows: list[CardRow],
    *,
    start: date,
    end: date,
    owed_before: tuple[int, int] = (0, 0),
    charges: list[CardCharge] | None = None,
    fees: list[CardCharge] | None = None,
    last4: str = DRAWN_LAST4,
) -> bytes:
    """A made-up BCP Visa statement (`Estado de Cuenta Tarjeta Visa`) of one page over the
    cycle `start` to `end`, holding what the contract says such a paper holds (contract:
    POST /v1/statements/import, "The paper's layout"): `SALDO ANTERIOR` of the debts
    `owed_before` (soles, dollars; debt as the paper prints it, negative a balance in the
    owner's favour), the dated `rows` of both currencies in paper order, the undated
    `charges` before `SUB TOTAL` (interest) and the `fees` after it, and `MONTO TOTAL
    FACTURADO`. Its `SUB TOTAL` and total billed are the lines' own, so it reads. A currency
    nothing is owed in and no line is in prints `0.00` in every figure, so the paper shows it at
    zero with no row. Its header prints the card number ending in `last4`. Never one of the
    owner's real statements: this repo is public; every name and number in it is made up by the
    test."""
    charges, fees = charges or [], fees or []
    assert all(len(row.description) <= 55 for row in rows), "a description too long"
    assert all(len(row.type) <= 10 for row in rows), "a type too long"
    assert all(len(line.label) <= 66 for line in (*charges, *fees)), "a label too long"

    def totals(*lines: CardRow | CardCharge) -> list[int]:
        return [sum(line.amount_cents for line in lines if line.currency == c) for c in _CARD_END]

    subtotal = [
        before + by_rows + by_charges
        for before, by_rows, by_charges in zip(
            owed_before, totals(*rows), totals(*charges), strict=True
        )
    ]
    billed = [owed + by_fees for owed, by_fees in zip(subtotal, totals(*fees), strict=True)]

    def figures(owed: Iterable[int]) -> list[tuple[int, str]]:
        return [
            cell
            for c, cents in zip(_CARD_END, owed, strict=True)
            for cell in _card_figure(c, cents)
        ]

    def undated(line: CardCharge) -> str:
        return _cells((_CARD_TEXT, line.label), *_card_figure(line.currency, line.amount_cents))

    lines = [
        _cells((100, "Pag 1 de 1")),
        "Estado de Cuenta Tarjeta Visa",
        "Número de tarjeta",
        f"4280-76XX-XXXX-{last4}",
        _cells((60, "Del"), (70, "Al")),
        _cells((60, f"{start:%d/%m/%y} {end:%d/%m/%y}")),
        *_CARD_HEADERS,
        _cells((_CARD_TEXT, "SALDO ANTERIOR"), *figures(owed_before)),
    ]
    for row in rows:
        lines.append(
            _cells(
                (_CARD_PROCESSED, paper_day(row.processed or row.day).title()),
                (_CARD_PURCHASED, paper_day(row.day).title()),
                (_CARD_TEXT, row.description),
                (_CARD_TYPE, row.type),
                *_card_figure(row.currency, row.amount_cents),
            )
        )
    lines += [undated(charge) for charge in charges]
    lines.append(_cells((_CARD_TEXT, "SUB TOTAL"), *figures(subtotal)))
    lines += [undated(fee) for fee in fees]
    lines.append(_cells((_CARD_TEXT, "MONTO TOTAL FACTURADO"), *figures(billed)))
    return pdf_file([[[(line, 0)] for line in lines]])


def statement_body(account_id: str, paper: bytes, *, dry_run: bool) -> dict:
    """The `POST /statements/import` body for `paper`: exactly its three keys, the
    file in standard base64 (contract: POST /v1/statements/import), built by the
    statement upload's own `request_body`, the body of both uploads."""
    return request_body(account_id, paper, dry_run=dry_run)


def send_statement(client: ExpenseClient, account_id: str, paper: bytes, *, dry_run: bool) -> dict:
    """`paper` sent whole as `account_id`'s statement; the engine's answer."""
    return client.post(
        "/statements/import", json_body=statement_body(account_id, paper, dry_run=dry_run)
    )


@cache
def bank_code() -> str:
    """The bank a new bank account is made with: the first one `GET /banks` lists
    (contract: GET /v1/banks)."""
    with ExpenseClient(_target()) as c:
        return c.get("/banks")["items"][0]["code"]


def kind_change(client: ExpenseClient, account_id: str, route: str) -> dict:
    """`route` (`make-person` or `make-account`) sent for the account with the body it takes: a
    new `contract-…` name for a person, a bank and a new number for a bank account
    (contract: POST /v1/accounts/{account_id}/make-person)
    (contract: POST /v1/accounts/{account_id}/make-account)."""
    if route == "make-person":
        body = {"name": f"contract-kind-{uuid4().hex[:8]}"}
    else:
        body = {"bank_code": bank_code(), "last4": next_last4()}
    return client.post(f"/accounts/{account_id}/{route}", json_body=body)


def account_body(*codes: str, code: str | None = None, person: bool = False, **fields) -> dict:
    """A `POST /accounts` body under a fresh id holding one entry per currency code in
    `codes` (PEN when none), with `statement_code` when given. A bank account carries `bank_code`
    and a new `last4` (`next_last4`), its name the engine's; a person, when `person`, carries a
    `contract-…` name. `fields` replace or add keys (contract: POST /v1/accounts, "Required")."""
    new_id = str(uuid4())
    body: dict = {
        "id": new_id,
        "kind": "person" if person else "bank",
        "currencies": [{"currency_code": c} for c in (codes or ("PEN",))],
    }
    if person:
        body["name"] = f"contract-stmt-{new_id[:8]}"
    else:
        body |= {"bank_code": bank_code(), "last4": next_last4()}
    if code is not None:
        body["statement_code"] = code
    return {**body, **fields}


def statement_create_body(
    account_id: str,
    start: str,
    end: str,
    *currencies: str,
    balances: list[dict] | None = None,
    **fields,
) -> dict:
    """A `POST /statements` body under a fresh id over the calendar days `start` to `end`:
    `balances` as given, else one entry per currency in `currencies` (PEN when none), each
    beginning and ending at 0 so nothing but the rule under test stands in the way of
    completing it; `fields` replace or add keys (contract: POST /v1/statements,
    "Required")."""
    new_id = str(uuid4())
    return {
        "id": new_id,
        "account_id": account_id,
        "name": f"contract-stmt-s-{new_id[:8]}",
        "date_start": start,
        "date_end": end,
        "balances": balances
        if balances is not None
        else [
            {"currency_code": c, "beginning_balance_cents": 0, "ending_balance_cents": 0}
            for c in (currencies or ("PEN",))
        ],
        **fields,
    }


class Scratch:
    """What one test builds on the practice user, undone in reverse dependency order:
    archived accounts unarchived, statements reverted and deleted, transactions (opening
    balances included) deleted, then hashtags and categories, then each account in one
    delete. Every step is best-effort, so a failed test still frees its statement codes."""

    def __init__(self, client: ExpenseClient) -> None:
        self.client = client
        self.zone = ZoneInfo(client.get("/auth/me")["settings"]["display_timezone"])
        self.accounts: list[str] = []
        self.statements: list[str] = []
        self.transactions: list[str] = []
        self.categories: list[str] = []
        self.hashtags: list[str] = []

    def account(self, *codes: str, code: str | None = None, person: bool = False, **fields) -> str:
        """A bank account, or a person with `person`, holding one currency per code in
        `codes` (PEN when none), made in one write (`fields` replace or add keys of the
        body, `account_body`); its id."""
        body = account_body(*codes, code=code, person=person, **fields)
        self.accounts.append(body["id"])
        self.client.post("/accounts", json_body=body)
        return body["id"]

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

    def statement(
        self,
        account_id: str,
        start: str,
        end: str,
        *currencies: str,
        balances: list[dict] | None = None,
        **fields,
    ) -> dict:
        """A draft statement of the account over the calendar days `start` to `end`, posted
        (`statement_create_body`); the engine's answer. Its id joins the scratch before the
        call, so cleanup reaches it whatever the engine does."""
        body = statement_create_body(
            account_id, start, end, *currencies, balances=balances, **fields
        )
        self.statements.append(body["id"])
        return self.client.post("/statements", json_body=body)

    def assign(self, tx_id: str, statement_id: str | None) -> None:
        """Assigns the transaction to the statement, or unassigns it with `None`
        (contract: PUT /v1/transactions/{transaction_id})."""
        self.client.put(f"/transactions/{tx_id}", json_body={"statement_id": statement_id})

    def at(self, day: str, hour: int = 12, minute: int = 0) -> str:
        """`day` at `hour`:`minute` in the user's display timezone, as the engine reads a date."""
        y, m, d = (int(part) for part in day.split("-"))
        return datetime(y, m, d, hour, minute, tzinfo=self.zone).isoformat(timespec="seconds")

    def noon(self, day: str) -> str:
        return self.at(day)

    def _item(
        self,
        account_id: str,
        when: str,
        amount: int,
        currency: str,
        *,
        titled: bool = True,
        **fields: Any,
    ) -> dict:
        """One transaction body dated `when` (`at`), sent alone or in a batch; the one body shape
        every helper sends. `fields` go in the body as given, whatever their type; it has a
        title unless `titled` is false and `fields` give none."""
        title = {"title": "contract statement line"} if titled else {}
        return {
            "id": str(uuid4()),
            **title,
            "amount_cents": amount,
            "account_id": account_id,
            "currency_code": currency,
            "date": when,
            **fields,
        }

    def body(
        self,
        account_id: str,
        amount: int = -1000,
        currency: str = "PEN",
        *,
        when: str | None = None,
        **fields: Any,
    ) -> dict:
        """One transaction body for a test that sends it itself, to a route, in a batch, again
        or after changing it: dated `when` (`at`; default `recent_moment`) with no title unless
        `fields` give one (`_item`). Its id joins the scratch before any send, so cleanup
        reaches the row whatever the engine does."""
        moment = when if when is not None else self.recent_moment().isoformat(timespec="seconds")
        item = self._item(account_id, moment, amount, currency, titled=False, **fields)
        self.transactions.append(item["id"])
        return item

    def _create(self, items: list[dict]) -> list[dict]:
        """Creates `items` in one batch; the created items, in request order."""
        self.transactions.extend(item["id"] for item in items)
        return self._send_batch(items)

    def _send_batch(self, items: list[dict]) -> list[dict]:
        """Posts `items` as one batch, registering nothing; the created items, in order."""
        return self.client.post("/transactions/batch", json_body={"transactions": items})["created"]

    def line(self, account_id: str, day: str, *amounts: int, currency: str = "PEN") -> str:
        """A new bank line on `day` in `currency` holding one part per amount (a batch
        `line_group` for more than one); its id."""
        group = {"line_group": "g"} if len(amounts) > 1 else {}
        when = self.noon(day)
        items = [self._item(account_id, when, amount, currency, **group) for amount in amounts]
        return self._create(items)[0]["bank_line_id"]

    def row_at(
        self,
        account_id: str,
        when: str,
        amount: int = -1000,
        currency: str = "PEN",
        *,
        alone: bool = False,
        **fields,
    ) -> dict:
        """A new transaction dated `when` (`at`; it may not be ahead of now) in `currency`
        with no title, category or operation code unless `fields` give them, sent in a batch
        or, with `alone`, by itself to `POST /transactions`; its id joins the scratch before
        the call. The created item, which must name the id, the account and the currency sent."""
        item = self.body(account_id, amount, currency, when=when, **fields)
        if alone:
            made = self.client.post("/transactions", json_body=item)
        else:
            made = self._send_batch([item])[0]
        assert (made["id"], made["account_id"], made["currency_code"]) == (
            item["id"],
            account_id,
            currency,
        )
        return made

    def row(
        self, account_id: str, day: str, amount: int = -1000, currency: str = "PEN", **fields
    ) -> dict:
        """`row_at` noon on `day` (a past day: noon today is `FUTURE_DATE` before noon)."""
        return self.row_at(account_id, self.noon(day), amount, currency, **fields)

    def recent_moment(self) -> datetime:
        """The moment `recent_row` dates a row at: a minute ago in the display timezone, read
        from the clock once. A test that also needs the row's month takes it from this
        moment (`month_of`), never from a second clock reading."""
        return minute_before(datetime.now(UTC), self.zone)

    def recent_row(
        self,
        account_id: str,
        amount: int = -1000,
        currency: str = "PEN",
        *,
        moment: datetime | None = None,
        alone: bool = False,
        **fields,
    ) -> dict:
        """A new transaction dated at `moment` (default `recent_moment`: a minute ago in the
        user's display timezone, the zone a month is cut in; contract: GET /v1/dashboard,
        "Field rules"); a transaction may not be dated ahead. The created item, as `row_at`
        makes it, sent in a batch or, with `alone`, by itself."""
        at = moment if moment is not None else self.recent_moment()
        when = at.isoformat(timespec="seconds")
        return self.row_at(account_id, when, amount, currency, alone=alone, **fields)

    def refused_row(
        self,
        account_id: str,
        when: str,
        currency: str = "PEN",
        *,
        batch: bool = False,
        **fields,
    ) -> EngineError:
        """The engine's refusal of a new transaction dated `when` (`at`) with `fields` added,
        sent to `POST /transactions` or, with `batch`, as the one item of
        `POST /transactions/batch`. Its id joins the scratch before the call, so a row the
        engine takes after all is still removed."""
        item = self._item(account_id, when, -100, currency, **fields)
        self.transactions.append(item["id"])
        if batch:
            body = {"transactions": [item]}
            return refused(lambda: self.client.post("/transactions/batch", json_body=body))
        return refused(lambda: self.client.post("/transactions", json_body=item))

    def completed(
        self, account_id: str, start: str, end: str, *tx_ids: str, currency: str = "PEN"
    ) -> dict:
        """A statement of the account over the calendar days `start` to `end` holding the
        lines of the transactions `tx_ids`, every part of each, all in `currency`, then
        completed: it begins at 0 and ends at their signed sum, so it adds up. The engine's
        read of it after the close (contract: POST /v1/statements/{statement_id}/complete)."""
        total = sum(read_signed(self.client, tx)["amount_cents"] for tx in tx_ids)
        balances = [
            {"currency_code": currency, "beginning_balance_cents": 0, "ending_balance_cents": total}
        ]
        statement = self.statement(account_id, start, end, balances=balances)["id"]
        for tx in tx_ids:
            self.assign(tx, statement)
        self.client.post(f"/statements/{statement}/complete")
        return self.client.get(f"/statements/{statement}")

    def opening_balance_body(
        self, day: str, currency: str = "PEN", amount_cents: int = 50000
    ) -> dict:
        """The body of an opening balance of `amount_cents` in `currency` dated at noon on
        `day`, under a new transaction id that is not yet kept for cleanup."""
        return {
            "transaction_id": str(uuid4()),
            "currency_code": currency,
            "amount_cents": amount_cents,
            "date": self.noon(day),
        }

    def opening_balance(
        self, account_id: str, day: str, currency: str = "PEN", amount_cents: int = 50000
    ) -> str:
        """The account's opening balance of `amount_cents` in `currency`; its line's id."""
        body = self.opening_balance_body(day, currency, amount_cents)
        self.transactions.append(body["transaction_id"])
        made = self.client.post(f"/accounts/{account_id}/opening-balance", json_body=body)
        return made["bank_line_id"]

    def took(self, answer: dict) -> list[str]:
        """Takes on what an upload's answer says it wrote, a bank download's
        (`send_download`) or a statement's (`send_statement`): every transaction it created
        and, for a statement, the statement it created or filled, so cleanup reverts and
        deletes it. Sent on a dry run, it takes on no transaction (none is created) and the
        draft the upload would fill, whose `statement_id` the answer carries, but not a
        statement the upload would create, whose `statement_id` is null
        (contract: POST /v1/statements/import, "Response"). The created transactions'
        ids, in row order."""
        statement = answer.get("statement_id")
        if statement is not None and statement not in self.statements:
            self.statements.append(statement)
        created = [row["transaction_id"] for row in answer["rows"] if row["transaction_id"]]
        self.transactions.extend(created)
        return created

    def _quietly(self, call, path: str) -> dict | None:
        try:
            return call(path)
        except EngineError:
            return None

    def cleanup(self) -> None:
        """Undoes what the test built, in the order the engine's deletes need."""
        for account in self.accounts:
            self._quietly(self.client.post, f"/accounts/{account}/unarchive")
        for statement in self.statements:
            self._quietly(self.client.post, f"/statements/{statement}/revert")
        for statement in self.statements:
            self._quietly(self.client.delete, f"/statements/{statement}")
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


NO_PRACTICE_ACCOUNT = (
    "EXPENSE_PRACTICE_ACCOUNT_ID is not set: pass the practice account's id, the one the reseed "
    "prints, inline on the contract suite's command line beside EXPENSE_PAT "
    '(docs/runtime.md "Working against the live engine")'
)


def _held_on(client: ExpenseClient, account_id: str) -> tuple[set[str], int]:
    """The ids of the account's statements and the count of its live transactions."""
    statements = client.get("/statements", params={"account_id": account_id})["items"]
    return {s["id"] for s in statements}, transaction_count(client, account_id)


@pytest.fixture
def practice_account(client, scratch):
    """The seed's practice account `BCP-0000` (`PRACTICE_ACCOUNT_ID`) given a statement code of a
    test's own, as `(id, statement_code)`: the one account a statement sample uploads to, since
    the sample prints a number ending `0000` and a name is unique among the live accounts, so no
    other account can hold it. Without the id the test fails, never skips. At teardown the
    scratch is cleaned first (what the test took on there goes), the account's statement code
    goes back to what it was, and an account holding a statement or a transaction it did not
    hold at setup fails the test."""
    if not PRACTICE_ACCOUNT_ID:
        pytest.fail(NO_PRACTICE_ACCOUNT, pytrace=False)
    path = f"/accounts/{PRACTICE_ACCOUNT_ID}"
    original = client.get(path)["statement_code"]
    code = free_statement_codes(client, 1)[0]
    client.put(path, json_body={"statement_code": code})
    held = _held_on(client, PRACTICE_ACCOUNT_ID)
    yield PRACTICE_ACCOUNT_ID, code
    scratch.cleanup()
    client.put(path, json_body={"statement_code": original})
    if _held_on(client, PRACTICE_ACCOUNT_ID) != held:
        pytest.fail("the test left a statement or a transaction on the practice account")
