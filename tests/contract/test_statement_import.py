"""Contract: `POST /reconciliations/import`, a month's statement closed from its PDF.

The app sends the bank's PDF whole and shows what comes back, so what the dry run and the
apply say is the engine's word (contract: POST /v1/reconciliations/import). Every paper here
is a made-up BCP savings account statement built by the test (`savings_paper` in
conftest.py), never a real one: this repo is public. Pinned here:

  · a dry run reads the paper and writes nothing: the statement's name, days and balances,
    each row by its place, `matched` to the ledger line of its day and total, `new`, or
    `empty` for a row of `0.00`, and a line one day off a `new` row named in its
    `near_misses`, never paired;
  · the apply closes the month as the dry run showed it: the statement created and
    completed, each new row created under `@Pendiente` and the pending hashtag, the paper's
    text as its title, at 00:00 of its day, every line in its row's place with an empty
    slot kept for the `0.00` row, and a line of the month in no statement flagged in
    `review_lines`, unchanged;
  · a completed month is refused, on the dry run and the apply alike
    (`RECONCILIATION_NOT_DRAFT` on `file`), writing nothing;
    once reverted, the same paper matches every row the first apply created and creates
    nothing;
  · an open month is filled: its days become the paper's, it keeps its name, and a line in
    it the paper does not print is taken out, never deleted;
  · a replay under the same idempotency key answers the stored answer and writes once;
  · each refusal a made-up file or account provokes, on the dry run and the apply alike,
    each writing nothing: the body's
    (`UNKNOWN_FIELD`, `INVALID_FORMAT`, `EMPTY`, a file over 5 MB `OUT_OF_RANGE`), the
    file's (`UNREADABLE_FILE`, more than 20 pages or 999 rows `OUT_OF_RANGE`,
    `UNEXPECTED_LAYOUT`, `TOTALS_MISMATCH`), the account's (`NO_STATEMENT_CODE`,
    `INVALID_REFERENCE` for an archived one, `NO_ACCOUNT_FOR_CURRENCY`), a row dated after
    today (`FUTURE_DATE` on `rows.<place>.date`, "Row <place>: Must not be in the
    future."), and the statement's (`PERIOD_OVERLAPS`, `STATEMENT_MONTH_TAKEN`, and
    `NO_TRANSACTIONS_ASSIGNED` for a paper of `0.00` rows only).

`RESERVED_NAME_HELD` is drawn in test_reserved_name_held.py, as the user holding the names.
Not drawn: a card's paper (`Estado de Cuenta Tarjeta Visa`), whose column header the engine
reads word for word and the contract does not print, so no made-up card paper reads; the
races (`CONCURRENT_CHANGE`), the line codes used up (`LINE_CODES_EXHAUSTED`) and the
engine's own fault (`INTERNAL_ERROR`), which no made-up file provokes.

Gating, target and the real-ledger guard: conftest.py.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from expense import http as http_module
from expense.reads import pending_hashtag_of
from tests.contract.conftest import (
    PaperRow,
    assert_refusal,
    free_statement_codes,
    pdf_file,
    refused,
    savings_paper,
    send_statement,
    statement_body,
    transaction_count,
)

MARCH = {"start": date(2026, 3, 1), "end": date(2026, 3, 31)}
APRIL = {"start": date(2026, 4, 1), "end": date(2026, 4, 30)}


def _statements(client, account_id: str) -> list[dict]:
    return client.get("/reconciliations", params={"account_id": account_id})["items"]


def _ledger(client, account_id: str) -> tuple[int, list[dict]]:
    """What a refused or dry-run upload must leave as it was: the account's live
    transaction count and its reconciliations, as read."""
    return transaction_count(client, account_id), _statements(client, account_id)


def _coded(scratch, currency: str = "PEN") -> tuple[str, str]:
    """A new account holding a statement code no other account of the caller's holds; its
    id and the code."""
    code = free_statement_codes(scratch.client, 1)[0]
    return scratch.account(currency, code), code


def _upload(client, account_id: str, paper: bytes, *, dry_run: bool):
    return lambda: send_statement(client, account_id, paper, dry_run=dry_run)


def _refused_writing_nothing(client, account_id: str, paper: bytes, status, code, key, reason):
    """The paper is refused alike on the dry run and the apply, writing nothing."""
    before = _ledger(client, account_id)
    for dry_run in (True, False):
        err = refused(_upload(client, account_id, paper, dry_run=dry_run))
        assert_refusal(err, status, code, key, reason)
        assert _ledger(client, account_id) == before
    return err


def _placed(client, recon: str) -> list[tuple[str, int, str]]:
    """The statement's lines in the paper's order, each `(id, place, statement_line)`
    (contract: GET /v1/bank-lines, "Ordering")."""
    listed = client.get("/bank-lines", params={"reconciliation_id": recon, "sort": "statement"})
    return [
        (line["id"], line["statement_place"], line["statement_line"]) for line in listed["items"]
    ]


def test_the_dry_run_shows_the_close_and_the_apply_does_it(client, scratch):
    account, code = _coded(scratch)
    matched = scratch.line(account, "2026-03-02", -2590)
    near = scratch.line(account, "2026-03-06", -1000)  # one day off row 3, never paired
    paper = savings_paper(
        [
            PaperRow(date(2026, 3, 2), "COMPRA BODEGA", -2590),
            PaperRow(date(2026, 3, 3), "MANT. CUENTA", 0),
            PaperRow(date(2026, 3, 5), "PAGO SERVICIO", -1000),
            PaperRow(date(2026, 3, 9), "ABONO PLANILLA", 651900),
        ],
        before_cents=100000,
        **MARCH,
    )
    ending = 100000 - 2590 - 1000 + 651900
    before = _ledger(client, account)

    dry = send_statement(client, account, paper, dry_run=True)
    assert _ledger(client, account) == before
    assert dry["dry_run"] is True and dry["reconciliation"] is None
    assert (dry["name"], dry["date_start"], dry["date_end"]) == (
        f"{code}-202603",
        "2026-03-01",
        "2026-03-31",
    )
    assert dry["halves"] == [
        {
            "account_id": account,
            "currency": "PEN",
            "reconciliation_id": None,
            "creates": True,
            "beginning_balance_cents": 100000,
            "ending_balance_cents": ending,
        }
    ]
    rows = dry["rows"]
    assert [(r["place"], r["outcome"]) for r in rows] == [
        (1, "matched"),
        (2, "empty"),
        (3, "new"),
        (4, "new"),
    ]
    assert [(r["date"], r["processed_on"], r["description"]) for r in rows] == [
        ("2026-03-02", "2026-03-02", "COMPRA BODEGA"),
        ("2026-03-03", "2026-03-03", "MANT. CUENTA"),
        ("2026-03-05", "2026-03-05", "PAGO SERVICIO"),
        ("2026-03-09", "2026-03-09", "ABONO PLANILLA"),
    ]
    assert [(r["amount_cents"], r["transaction_type"]) for r in rows if r["amount_cents"]] == [
        (2590, 1),
        (1000, 1),
        (651900, 2),
    ]
    assert [r["bank_line_id"] for r in rows] == [matched, None, None, None]
    assert [r["near_misses"] for r in rows] == [
        [],
        [],
        [{"bank_line_id": near, "date": "2026-03-06"}],
        [],
    ]
    assert all(r["transaction_id"] is None and r["fee"] is False for r in rows)
    assert all(r["account_id"] == account and r["currency"] == "PEN" for r in rows)
    assert (dry["taken_out"], dry["counts"]) == (
        [],
        {"matched": 1, "new": 2, "empty": 1, "taken_out": 0},
    )

    done = send_statement(client, account, paper, dry_run=False)
    scratch.took(done)
    recon = done["halves"][0]["reconciliation_id"]
    assert recon is not None and done["halves"][0]["creates"] is True
    assert [(r["place"], r["outcome"]) for r in done["rows"]] == [
        (r["place"], r["outcome"]) for r in rows
    ]
    assert (done["taken_out"], done["counts"]) == (dry["taken_out"], dry["counts"])
    statement = done["reconciliation"]
    assert (statement["id"], statement["status"], statement["name"]) == (recon, 2, dry["name"])
    assert (statement["beginning_balance_cents"], statement["ending_balance_cents"]) == (
        100000,
        ending,
    )
    assert statement["review_lines"] == [near]
    assert client.get(f"/bank-lines/{near}")["parts"][0]["reconciliation_id"] is None

    created = [r for r in done["rows"] if r["outcome"] == "new"]
    assert all(r["transaction_id"] and r["bank_line_id"] for r in created)
    pending_tag = pending_hashtag_of(client.get("/hashtags")["items"])
    assert pending_tag is not None
    for row in created:
        tx = client.get(f"/transactions/{row['transaction_id']}")
        assert tx["bank_line_id"] == row["bank_line_id"]
        assert (tx["title"], tx["hashtag_ids"]) == (row["description"], [pending_tag[0]])
        assert client.get(f"/categories/{tx['category_id']}")["system_key"] == "pending"
        midnight = datetime.combine(date.fromisoformat(row["date"]), datetime.min.time())
        assert datetime.fromisoformat(tx["date"]).astimezone(scratch.zone) == midnight.replace(
            tzinfo=scratch.zone
        )
        assert tx["reconciliation_id"] == recon
    assert transaction_count(client, account) == before[0] + 2
    lines = [matched, None, *(r["bank_line_id"] for r in created)]
    assert _placed(client, recon) == [
        (line, place, f"{code}-202603-{place:03d}")
        for place, line in enumerate(lines, start=1)
        if line is not None
    ]

    after = _ledger(client, account)
    for dry_run in (True, False):
        err = refused(_upload(client, account, paper, dry_run=dry_run))
        assert_refusal(err, 409, "CONFLICT", "file", "RECONCILIATION_NOT_DRAFT")
        assert _ledger(client, account) == after

    client.post(f"/reconciliations/{recon}/revert")
    again = send_statement(client, account, paper, dry_run=False)
    scratch.took(again)  # cleaned up whatever the checks below find
    assert again["halves"][0]["reconciliation_id"] == recon
    assert again["halves"][0]["creates"] is False
    assert again["counts"] == {"matched": 3, "new": 0, "empty": 1, "taken_out": 0}
    assert [r["bank_line_id"] for r in again["rows"]] == [lines[0], None, *lines[2:]]
    assert all(r["transaction_id"] is None for r in again["rows"])
    assert again["reconciliation"]["status"] == 2
    assert transaction_count(client, account) == after[0]


def test_an_open_month_is_filled_and_a_line_the_paper_lacks_taken_out(client, scratch):
    account, _ = _coded(scratch)
    draft = scratch.reconciliation(account, "2026-04-03", "2026-04-28")
    name = client.get(f"/reconciliations/{draft}")["name"]
    kept = scratch.line(account, "2026-04-10", -5000, recon=draft)
    stray = scratch.line(account, "2026-04-12", -777, recon=draft)
    paper = savings_paper(
        [PaperRow(date(2026, 4, 10), "COMPRA FERRETERIA", -5000)], before_cents=20000, **APRIL
    )

    dry = send_statement(client, account, paper, dry_run=True)
    assert [(h["reconciliation_id"], h["creates"]) for h in dry["halves"]] == [(draft, False)]
    assert [(r["outcome"], r["bank_line_id"]) for r in dry["rows"]] == [("matched", kept)]
    assert (dry["taken_out"], dry["counts"]["taken_out"]) == ([stray], 1)
    assert client.get(f"/bank-lines/{stray}")["parts"][0]["reconciliation_id"] == draft

    done = send_statement(client, account, paper, dry_run=False)
    scratch.took(done)
    assert done["taken_out"] == [stray]
    statement = client.get(f"/reconciliations/{draft}")
    assert (statement["status"], statement["name"]) == (2, name)
    assert (statement["date_start"], statement["date_end"]) == ("2026-04-01", "2026-04-30")
    assert (statement["beginning_balance_cents"], statement["ending_balance_cents"]) == (
        20000,
        15000,
    )
    left = client.get(f"/bank-lines/{stray}")
    assert (left["parts"][0]["reconciliation_id"], left["statement_place"]) == (None, None)
    assert [line for line, *_ in _placed(client, draft)] == [kept]


def test_a_replay_answers_the_same_and_writes_once(client, scratch, monkeypatch):
    """The same idempotency key answers the stored response, the minted ids included, and
    writes once (contract: POST /v1/reconciliations/import, "Idempotency")
    (contract: "Base Conventions", "Idempotency")."""
    account, _ = _coded(scratch)
    paper = savings_paper(
        [PaperRow(date(2026, 3, 4), "COMPRA LIBRERIA", -4250)], before_cents=10000, **MARCH
    )
    before = transaction_count(client, account)

    key = uuid4()
    monkeypatch.setattr(http_module, "uuid", SimpleNamespace(uuid4=lambda: key))
    try:
        first = send_statement(client, account, paper, dry_run=False)
        scratch.took(first)
        replayed = send_statement(client, account, paper, dry_run=False)
        scratch.took(replayed)  # cleaned up whatever the checks below find
    finally:
        monkeypatch.undo()

    assert replayed == first
    assert first["rows"][0]["outcome"] == "new" and first["rows"][0]["transaction_id"]
    assert transaction_count(client, account) == before + 1
    assert [s["id"] for s in _statements(client, account)] == [
        first["halves"][0]["reconciliation_id"]
    ]


def test_the_body_is_refused_before_the_paper_is_read(client, scratch):
    account, _ = _coded(scratch)
    paper = savings_paper([PaperRow(date(2026, 3, 4), "COMPRA", -100)], before_cents=0, **MARCH)
    # Over 5 MB once decoded, its base64 still within the body's limit.
    oversized = paper + b"%" * (5_242_881 - len(paper))
    before = _ledger(client, account)
    for dry_run in (True, False):
        good = statement_body(account, paper, dry_run=dry_run)
        for body, key, reason in (
            ({**good, "name": "x"}, "name", "UNKNOWN_FIELD"),
            ({**good, "file": "not base64!"}, "file", "INVALID_FORMAT"),
            ({**good, "file": ""}, "file", "EMPTY"),
            (statement_body(account, oversized, dry_run=dry_run), "file", "OUT_OF_RANGE"),
        ):
            err = refused(lambda body=body: client.post("/reconciliations/import", json_body=body))
            assert_refusal(err, 422, "VALIDATION_ERROR", key, reason)
            assert _ledger(client, account) == before


def test_a_file_the_engine_cannot_take_is_refused_whole(client, scratch):
    account, _ = _coded(scratch)
    one = [PaperRow(date(2026, 3, 4), "COMPRA", -100)]
    papers = {
        "not a PDF": (b"Fecha;Monto\n04/03/2026;-1.00\n", "UNREADABLE_FILE"),
        "a damaged PDF": (b"%PDF-1.4\nnot a document", "UNREADABLE_FILE"),
        "21 pages": (
            savings_paper(one * 21, before_cents=100000, rows_per_page=1, **MARCH),
            "OUT_OF_RANGE",
        ),
        "1,000 rows": (
            savings_paper(one * 1000, before_cents=1000000, rows_per_page=60, **MARCH),
            "OUT_OF_RANGE",
        ),
        "no BCP statement": (pdf_file([[[("contract made-up letter", 0)]]]), "UNEXPECTED_LAYOUT"),
        "rows that do not add up": (
            savings_paper(one, before_cents=10000, closing_cents=10000, **MARCH),
            "TOTALS_MISMATCH",
        ),
    }
    for what, (paper, reason) in papers.items():
        err = _refused_writing_nothing(
            client, account, paper, 422, "VALIDATION_ERROR", "file", reason
        )
        assert err.fields["file"], what


def test_the_account_is_refused(client, scratch):
    paper = savings_paper([PaperRow(date(2026, 3, 4), "COMPRA", -100)], before_cents=10000, **MARCH)
    uncoded = scratch.account()
    archived, _ = _coded(scratch)
    scratch.archive(archived)
    dollars, _ = _coded(scratch, "USD")
    for account, reason in (
        (uncoded, "NO_STATEMENT_CODE"),
        (archived, "INVALID_REFERENCE"),
        (dollars, "NO_ACCOUNT_FOR_CURRENCY"),  # a soles paper on a dollar account
    ):
        _refused_writing_nothing(
            client, account, paper, 422, "VALIDATION_ERROR", "account_id", reason
        )


def test_a_row_dated_after_today_refuses_the_whole_paper(client, scratch):
    """Every row dated after today in `display_timezone` is named on `rows.<place>.date`,
    all in one answer (contract: POST /v1/reconciliations/import)."""
    account, _ = _coded(scratch)
    today = datetime.now(scratch.zone).date()
    start = (today.replace(day=1) + timedelta(days=32)).replace(day=1)  # next month
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    paper = savings_paper(
        [
            PaperRow(start + timedelta(days=1), "COMPRA", -100),
            PaperRow(start + timedelta(days=2), "COMPRA", -200),
        ],
        start=start,
        end=end,
        before_cents=10000,
    )
    before = _ledger(client, account)
    for dry_run in (True, False):
        err = refused(_upload(client, account, paper, dry_run=dry_run))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert err.reasons == {"rows.1.date": "FUTURE_DATE", "rows.2.date": "FUTURE_DATE"}
        assert err.fields == {
            "rows.1.date": "Row 1: Must not be in the future.",
            "rows.2.date": "Row 2: Must not be in the future.",
        }
        assert _ledger(client, account) == before


def test_the_statement_days_are_judged(client, scratch):
    account, code = _coded(scratch)
    paper = savings_paper([PaperRow(date(2026, 3, 4), "COMPRA", -100)], before_cents=10000, **MARCH)

    # A period of April sharing March 31 with the paper's.
    april = scratch.reconciliation(account, "2026-03-31", "2026-04-15")
    _refused_writing_nothing(
        client, account, paper, 422, "VALIDATION_ERROR", "file", "PERIOD_OVERLAPS"
    )
    client.delete(f"/reconciliations/{april}")

    # The dollar account under the same code holds March over other days.
    dollars = scratch.account("USD", code)
    scratch.reconciliation(dollars, "2026-03-05", "2026-03-25")
    _refused_writing_nothing(
        client, account, paper, 422, "VALIDATION_ERROR", "file", "STATEMENT_MONTH_TAKEN"
    )


def test_a_savings_paper_of_empty_rows_only_is_refused(client, scratch):
    account, _ = _coded(scratch)
    paper = savings_paper(
        [PaperRow(date(2026, 3, 31), "MANT. CUENTA", 0)], before_cents=10000, **MARCH
    )
    _refused_writing_nothing(
        client, account, paper, 422, "VALIDATION_ERROR", "file", "NO_TRANSACTIONS_ASSIGNED"
    )
