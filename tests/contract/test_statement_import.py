"""Contract: `POST /statements/import`, an account's month closed from the bank's PDF.

The app sends the bank's PDF whole and shows what comes back, so what the dry run and the
apply say is the engine's word (contract: POST /v1/statements/import). Every paper here
is a made-up BCP savings account statement built by the test (`savings_paper` in
conftest.py) to the stated layout (contract: POST /v1/statements/import, "The paper's
layout"), never a real one: this repo is public. Pinned here:

  · a dry run reads the paper and writes nothing: `statement_id` null and `creates` true for
    a statement it would make, the statement's name, days and the balances of the currencies
    it covers, each row by its place reading its `account_id` and `currency_code`, `matched`
    to the ledger line of its day and total, `new`, or `empty` for a row of `0.00`;
  · the apply closes the month as the dry run showed it: the statement created and
    completed, each new row created under `@Pendiente` and the pending hashtag, the paper's
    text as its title, at 00:00 of its day, every line in its row's place with an empty
    slot kept for the `0.00` row, and a line of the month in no statement flagged in the
    balance's `review_lines`, unchanged;
  · the bank's day wins: a line one day off a row is matched and moved to the row's day
    (`redated`, `counts.redated`; a dry run says so and moves nothing), a line two days off
    is not matched, the row is created and the line flagged
    (contract: POST /v1/statements/import, "The bank's day wins");
  · a completed month is refused, on the dry run and the apply alike
    (`RECONCILIATION_NOT_DRAFT` on `file`), writing nothing;
    once reverted, the same paper matches every row the first apply created and creates
    nothing;
  · an open month is filled: its days become the paper's, it keeps its name, and a line in
    it the paper does not print is taken out, never deleted;
  · a replay under the same idempotency key answers the stored answer and writes once;
  · each refusal a made-up file or account provokes, on the dry run and the apply alike,
    each writing nothing, shown by a full read of the account's transactions, bank lines and
    statements before and after: the body's
    (`UNKNOWN_FIELD`, `INVALID_FORMAT`, `EMPTY`, a file over 5 MB `OUT_OF_RANGE`), the
    file's (`UNREADABLE_FILE`, more than 20 pages or 999 rows `OUT_OF_RANGE`,
    `UNEXPECTED_LAYOUT`, `TOTALS_MISMATCH`), the account's (`NO_STATEMENT_CODE`,
    `INVALID_REFERENCE` for an archived one, `PERSON_TAKES_NO_STATEMENT` for a person, on
    the bank download too, `CURRENCY_NOT_HELD` for a paper in a currency the account lacks,
    `ACCOUNT_CURRENCY_NOT_ON_PAPER` for a currency of the account holding something the
    paper does not print), a row dated after today (`FUTURE_DATE` on `rows.<place>.date`,
    "Row <place>: Must not be in the future."), and the statement's (`PERIOD_OVERLAPS`, and
    `NO_TRANSACTIONS_ASSIGNED` for a paper of `0.00` rows only).

`RESERVED_NAME_HELD` is drawn in test_reserved_name_held.py, as the user holding the names.
The published samples, fetched live, are tested here too: `card` then `card-no-dollars`
closing one account of soles and dollars, the second closing its dollars with no line, and the
drawn savings paper answering as the `savings` sample does. Not drawn here: a card's paper,
whose cases are another test's; the races (`CONCURRENT_CHANGE`), the line codes used up
(`LINE_CODES_EXHAUSTED`) and the engine's own fault (`INTERNAL_ERROR`), which no made-up
file provokes.

Gating, target and the real-ledger guard: conftest.py.
"""

import base64
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from expense import http as http_module
from expense.reads import pending_hashtag_of
from tests.contract.conftest import (
    CURRENT_HEADER,
    PaperRow,
    assert_refusal,
    balance_of,
    free_statement_codes,
    pdf_file,
    refused,
    savings_paper,
    send_download,
    send_statement,
    statement_body,
    transaction_count,
)

MARCH = {"start": date(2026, 3, 1), "end": date(2026, 3, 31)}
APRIL = {"start": date(2026, 4, 1), "end": date(2026, 4, 30)}

NOT_A_PERSON = "Must not be a person: a person sends no bank statement."


def _statements(client, account_id: str) -> list[dict]:
    return client.get("/statements", params={"account_id": account_id})["items"]


def _ledger(client, account_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    """What a refused or dry-run upload must leave as it was, read in full: the account's
    live transactions, its bank lines and its statements."""
    return (
        client.get("/transactions", params={"account_id": account_id})["items"],
        client.get("/bank-lines", params={"account_id": account_id})["items"],
        _statements(client, account_id),
    )


def _coded(scratch, *currencies: str, person: bool = False) -> tuple[str, str]:
    """A new account holding the `currencies` (PEN when none) and a statement code no other
    account of the caller's holds; its id and the code."""
    code = free_statement_codes(scratch.client, 1)[0]
    return scratch.account(*currencies, code=code, person=person), code


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


def _placed(client, statement: str) -> list[tuple[str, int, str]]:
    """The statement's lines in the paper's order, each `(id, place, statement_line)`
    (contract: GET /v1/bank-lines, "Ordering")."""
    listed = client.get("/bank-lines", params={"statement_id": statement, "sort": "statement"})
    return [
        (line["id"], line["statement_place"], line["statement_line"]) for line in listed["items"]
    ]


def test_the_dry_run_shows_the_close_and_the_apply_does_it(client, scratch):
    account, code = _coded(scratch)
    matched = scratch.line(account, "2026-03-02", -2590)
    far = scratch.row(account, "2026-03-07", -1000)  # two days off row 3: not its line
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
    assert (dry["dry_run"], dry["statement_id"], dry["creates"], dry["statement"]) == (
        True,
        None,
        True,
        None,
    )
    assert (dry["name"], dry["date_start"], dry["date_end"]) == (
        f"{code}-202603",
        "2026-03-01",
        "2026-03-31",
    )
    assert dry["balances"] == [
        {"currency_code": "PEN", "beginning_balance_cents": 100000, "ending_balance_cents": ending}
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
    assert all(r["transaction_id"] is None and r["fee"] is False for r in rows)
    assert all(r["account_id"] == account and r["currency_code"] == "PEN" for r in rows)
    assert not any(r["redated"] for r in rows)
    assert (dry["taken_out"], dry["counts"]) == (
        [],
        {"matched": 1, "new": 2, "empty": 1, "taken_out": 0, "redated": 0},
    )

    done = send_statement(client, account, paper, dry_run=False)
    scratch.took(done)
    statement_id = done["statement_id"]
    assert statement_id is not None and done["creates"] is True and done["dry_run"] is False
    assert done["balances"] == dry["balances"]
    assert [(r["place"], r["outcome"]) for r in done["rows"]] == [
        (r["place"], r["outcome"]) for r in rows
    ]
    assert (done["taken_out"], done["counts"]) == (dry["taken_out"], dry["counts"])
    statement = done["statement"]
    assert (statement["id"], statement["status"], statement["name"]) == (
        statement_id,
        2,
        dry["name"],
    )
    assert statement["account_id"] == account
    balance = balance_of(statement, "PEN")
    assert (balance["beginning_balance_cents"], balance["ending_balance_cents"]) == (
        100000,
        ending,
    )
    assert balance["review_lines"] == [far["bank_line_id"]]
    assert client.get(f"/transactions/{far['id']}")["statement_id"] is None

    created = [r for r in done["rows"] if r["outcome"] == "new"]
    assert all(r["transaction_id"] and r["bank_line_id"] for r in created)
    pending_tag = pending_hashtag_of(client.get("/hashtags")["items"])
    assert pending_tag is not None
    for row in created:
        tx = client.get(f"/transactions/{row['transaction_id']}")
        assert tx["bank_line_id"] == row["bank_line_id"]
        assert (tx["account_id"], tx["currency_code"]) == (account, "PEN")
        assert (tx["title"], tx["hashtag_ids"]) == (row["description"], [pending_tag[0]])
        assert client.get(f"/categories/{tx['category_id']}")["system_key"] == "pending"
        midnight = datetime.combine(date.fromisoformat(row["date"]), datetime.min.time())
        assert datetime.fromisoformat(tx["date"]).astimezone(scratch.zone) == midnight.replace(
            tzinfo=scratch.zone
        )
        assert tx["statement_id"] == statement_id
    assert transaction_count(client, account) == len(before[0]) + 2
    lines = [matched, None, *(r["bank_line_id"] for r in created)]
    assert _placed(client, statement_id) == [
        (line, place, f"{code}-202603-{place:03d}")
        for place, line in enumerate(lines, start=1)
        if line is not None
    ]

    after = _ledger(client, account)
    for dry_run in (True, False):
        err = refused(_upload(client, account, paper, dry_run=dry_run))
        assert_refusal(err, 409, "CONFLICT", "file", "RECONCILIATION_NOT_DRAFT")
        assert _ledger(client, account) == after

    client.post(f"/statements/{statement_id}/revert")
    again = send_statement(client, account, paper, dry_run=False)
    scratch.took(again)  # cleaned up whatever the checks below find
    assert (again["statement_id"], again["creates"]) == (statement_id, False)
    assert again["counts"] == {"matched": 3, "new": 0, "empty": 1, "taken_out": 0, "redated": 0}
    assert [r["bank_line_id"] for r in again["rows"]] == [lines[0], None, *lines[2:]]
    assert all(r["transaction_id"] is None for r in again["rows"])
    assert again["statement"]["status"] == 2
    assert transaction_count(client, account) == len(after[0])


def test_a_line_one_day_off_is_moved_and_one_two_days_off_is_not(client, scratch):
    """The bank's day wins (contract: POST /v1/statements/import, "The bank's day wins"):
    the row dated 5 March takes the line of the 4th, moved to 00:00 of the 5th, and the
    row of the 9th takes none of the line of the 7th, which stays where it is, flagged."""
    account, _ = _coded(scratch)
    near = scratch.row(account, "2026-03-04", -3000)
    exact = scratch.row(account, "2026-03-20", -700)
    far = scratch.row(account, "2026-03-07", -4000)
    paper = savings_paper(
        [
            PaperRow(date(2026, 3, 5), "COMPRA UNO", -3000),
            PaperRow(date(2026, 3, 9), "COMPRA DOS", -4000),
            PaperRow(date(2026, 3, 20), "COMPRA TRES", -700),
        ],
        before_cents=50000,
        **MARCH,
    )
    before = _ledger(client, account)

    dry = send_statement(client, account, paper, dry_run=True)
    assert _ledger(client, account) == before  # a dry run moves nothing
    assert [(r["outcome"], r["bank_line_id"], r["redated"]) for r in dry["rows"]] == [
        ("matched", near["bank_line_id"], True),
        ("new", None, False),
        ("matched", exact["bank_line_id"], False),
    ]
    assert [r["date"] for r in dry["rows"]] == ["2026-03-05", "2026-03-09", "2026-03-20"]
    assert dry["counts"] == {"matched": 2, "new": 1, "empty": 0, "taken_out": 0, "redated": 1}

    done = send_statement(client, account, paper, dry_run=False)
    scratch.took(done)
    assert [(r["outcome"], r["redated"]) for r in done["rows"]] == [
        (r["outcome"], r["redated"]) for r in dry["rows"]
    ]
    assert done["rows"][0]["bank_line_id"] == near["bank_line_id"]
    assert done["counts"] == dry["counts"]
    moved = client.get(f"/transactions/{near['id']}")
    midnight = datetime(2026, 3, 5, tzinfo=scratch.zone)
    assert datetime.fromisoformat(moved["date"]).astimezone(scratch.zone) == midnight
    assert moved["statement_id"] == done["statement_id"]
    untouched = client.get(f"/transactions/{far['id']}")
    assert untouched["date"] == far["date"] and untouched["statement_id"] is None
    assert (
        done["rows"][1]["transaction_id"]
        and done["rows"][1]["bank_line_id"] != (far["bank_line_id"])
    )
    assert balance_of(done["statement"], "PEN")["review_lines"] == [far["bank_line_id"]]


def test_an_open_month_is_filled_and_a_line_the_paper_lacks_taken_out(client, scratch):
    account, _ = _coded(scratch)
    draft = scratch.statement(account, "2026-04-03", "2026-04-28", "PEN")["id"]
    name = client.get(f"/statements/{draft}")["name"]
    kept = scratch.row(account, "2026-04-10", -5000)
    stray = scratch.row(account, "2026-04-12", -777)
    scratch.assign(kept["id"], draft)
    scratch.assign(stray["id"], draft)
    paper = savings_paper(
        [PaperRow(date(2026, 4, 10), "COMPRA FERRETERIA", -5000)], before_cents=20000, **APRIL
    )

    dry = send_statement(client, account, paper, dry_run=True)
    assert (dry["statement_id"], dry["creates"]) == (draft, False)
    assert [(r["outcome"], r["bank_line_id"]) for r in dry["rows"]] == [
        ("matched", kept["bank_line_id"])
    ]
    assert (dry["taken_out"], dry["counts"]["taken_out"]) == ([stray["bank_line_id"]], 1)
    assert client.get(f"/transactions/{stray['id']}")["statement_id"] == draft

    done = send_statement(client, account, paper, dry_run=False)
    scratch.took(done)
    assert done["taken_out"] == [stray["bank_line_id"]]
    statement = client.get(f"/statements/{draft}")
    assert (statement["status"], statement["name"]) == (2, name)
    assert (statement["date_start"], statement["date_end"]) == ("2026-04-01", "2026-04-30")
    balance = balance_of(statement, "PEN")
    assert (balance["beginning_balance_cents"], balance["ending_balance_cents"]) == (20000, 15000)
    left = client.get(f"/bank-lines/{stray['bank_line_id']}")
    assert left["statement_place"] is None
    assert client.get(f"/transactions/{stray['id']}")["statement_id"] is None
    assert [line for line, *_ in _placed(client, draft)] == [kept["bank_line_id"]]


def test_a_replay_answers_the_same_and_writes_once(client, scratch, monkeypatch):
    """The same idempotency key answers the stored response, the minted ids included, and
    writes once (contract: POST /v1/statements/import, "Idempotency")
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
    assert [s["id"] for s in _statements(client, account)] == [first["statement_id"]]


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
            err = refused(lambda body=body: client.post("/statements/import", json_body=body))
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
    for account, reason in (
        (uncoded, "NO_STATEMENT_CODE"),
        (archived, "INVALID_REFERENCE"),
    ):
        _refused_writing_nothing(
            client, account, paper, 422, "VALIDATION_ERROR", "account_id", reason
        )


def test_a_person_takes_no_statement_on_either_upload(client, scratch):
    """A person sends no bank statement, even holding a statement code, on a dry run as on
    an apply, the statement upload and the bank download alike
    (contract: POST /v1/statements/import, "Accounts")
    (contract: POST /v1/transactions/import, "Accounts")."""
    person, _ = _coded(scratch, "PEN", "USD", person=True)
    paper = savings_paper([PaperRow(date(2026, 3, 4), "COMPRA", -100)], before_cents=10000, **MARCH)
    rows = [CURRENT_HEADER, ["04/03/2026", "contract person row", "S/", -1.0, "000123"]]
    before = _ledger(client, person)
    for dry_run in (True, False):
        err = refused(_upload(client, person, paper, dry_run=dry_run))
        assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "PERSON_TAKES_NO_STATEMENT")
        assert err.fields["account_id"] == NOT_A_PERSON
        assert _ledger(client, person) == before

        err = refused(lambda dry_run=dry_run: send_download(client, person, rows, dry_run=dry_run))
        assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "PERSON_TAKES_NO_STATEMENT")
        assert err.fields["account_id"] == NOT_A_PERSON
        assert _ledger(client, person) == before


def test_a_paper_in_a_currency_the_account_lacks_is_refused(client, scratch):
    """The account must hold at least one currency the paper prints, so a dollar paper sent
    to a soles-only account is `CURRENCY_NOT_HELD` naming it, and so is a soles paper sent
    to a dollar-only one (contract: POST /v1/statements/import, "Accounts")."""
    soles, _ = _coded(scratch, "PEN")
    dollars, _ = _coded(scratch, "USD")
    rows = [PaperRow(date(2026, 3, 4), "COMPRA", -100)]
    for account, currency in ((soles, "USD"), (dollars, "PEN")):
        paper = savings_paper(rows, before_cents=10000, currency=currency, **MARCH)
        err = _refused_writing_nothing(
            client, account, paper, 422, "VALIDATION_ERROR", "account_id", "CURRENCY_NOT_HELD"
        )
        assert err.fields["account_id"] == f"The account holds no {currency}."


def test_an_account_currency_the_paper_does_not_print_is_left_out_or_refused(client, scratch):
    """A soles paper for an account that also holds dollars leaves the dollars out when they
    hold nothing; with a line in the draft or money at the start it is
    `ACCOUNT_CURRENCY_NOT_ON_PAPER` naming the currency, on the dry run too
    (contract: POST /v1/statements/import, "Which currencies the statement covers")."""
    paper = savings_paper([PaperRow(date(2026, 3, 4), "COMPRA", -100)], before_cents=10000, **MARCH)

    empty, _ = _coded(scratch, "PEN", "USD")
    dry = send_statement(client, empty, paper, dry_run=True)
    assert [b["currency_code"] for b in dry["balances"]] == ["PEN"]

    started, _ = _coded(scratch, "PEN", "USD")
    scratch.opening_balance(started, "2026-02-10", "USD", 30000)
    held, _ = _coded(scratch, "PEN", "USD")
    draft = scratch.statement(held, "2026-03-01", "2026-03-31", "PEN", "USD")["id"]
    scratch.assign(scratch.row(held, "2026-03-10", -500, "USD")["id"], draft)
    for account in (started, held):
        err = _refused_writing_nothing(
            client,
            account,
            paper,
            422,
            "VALIDATION_ERROR",
            "account_id",
            "ACCOUNT_CURRENCY_NOT_ON_PAPER",
        )
        assert "USD" in err.fields["account_id"]


def test_a_row_dated_after_today_refuses_the_whole_paper(client, scratch):
    """Every row dated after today in `display_timezone` is named on `rows.<place>.date`,
    all in one answer (contract: POST /v1/statements/import, "The rows and their places")."""
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
    """A period sharing a day with the account's statement of the next month is
    `PERIOD_OVERLAPS` (contract: "Statements", "The days"). `STATEMENT_MONTH_TAKEN` is not
    drawn: the account's statement ending in the paper's month is the paper's, so a paper
    meets another statement of its month only as the draft it fills or the completed one
    `RECONCILIATION_NOT_DRAFT` refuses."""
    account, _ = _coded(scratch)
    paper = savings_paper([PaperRow(date(2026, 3, 4), "COMPRA", -100)], before_cents=10000, **MARCH)
    scratch.statement(account, "2026-03-31", "2026-04-15", "PEN")
    _refused_writing_nothing(
        client, account, paper, 422, "VALIDATION_ERROR", "file", "PERIOD_OVERLAPS"
    )


def test_a_savings_paper_of_empty_rows_only_is_refused(client, scratch):
    account, _ = _coded(scratch)
    paper = savings_paper(
        [PaperRow(date(2026, 3, 31), "MANT. CUENTA", 0)], before_cents=10000, **MARCH
    )
    _refused_writing_nothing(
        client, account, paper, 422, "VALIDATION_ERROR", "file", "NO_TRANSACTIONS_ASSIGNED"
    )


def _sample(client, name: str) -> dict:
    """The engine's published made-up sample `name` (contract: GET /v1/statements/samples/{sample}),
    the one paper the card tests use: no real statement is in this repo."""
    return client.get(f"/statements/samples/{name}")


def _paper_of(sample: dict) -> bytes:
    return base64.b64decode(sample["file"])


def _answer_rows(answer: dict, sample: dict) -> list[dict]:
    """The upload's rows under the keys the sample's rows hold
    (contract: GET /v1/statements/samples/{sample}, "Response")."""
    return [
        {k: row[k] for k in sample_row}
        for row, sample_row in zip(answer["rows"], sample["rows"], strict=True)
    ]


def test_the_card_samples_close_one_account_month_after_month(client, scratch):
    """`card` then `card-no-dollars`, both currencies of one account closing in turn: the
    second, with no dollar row, closes its dollars with no line, their balances equal
    (contract: POST /v1/statements/import, "A card's currency with no row still closes"),
    and the undated interest and fees are dated the statement's last day
    (contract: POST /v1/statements/import, "The rows and their places")."""
    account, code = _coded(scratch, "PEN", "USD")
    first, second = _sample(client, "card"), _sample(client, "card-no-dollars")
    assert first["balances"] == [
        {
            "currency_code": "PEN",
            "beginning_balance_cents": -125000,
            "ending_balance_cents": -37959,
        },
        {"currency_code": "USD", "beginning_balance_cents": -8000, "ending_balance_cents": -10498},
    ]
    assert second["balances"][1] == {
        "currency_code": "USD",
        "beginning_balance_cents": -10498,
        "ending_balance_cents": -10498,
    }

    for sample, month in ((first, "202503"), (second, "202504")):
        before = _ledger(client, account)
        dry = send_statement(client, account, _paper_of(sample), dry_run=True)
        assert dry["statement_id"] is None and dry["creates"] is True
        assert _ledger(client, account) == before
        assert (dry["name"], dry["date_start"], dry["date_end"]) == (
            f"{code}-{month}",
            sample["date_start"],
            sample["date_end"],
        )
        assert dry["balances"] == sample["balances"]
        assert _answer_rows(dry, sample) == sample["rows"]
        assert all(r["account_id"] == account and r["outcome"] == "new" for r in dry["rows"])
        fees = [r for r in dry["rows"] if r["fee"]]
        assert fees and all(r["date"] == sample["date_end"] for r in fees)

        done = send_statement(client, account, _paper_of(sample), dry_run=False)
        scratch.took(done)
        assert done["balances"] == sample["balances"]
        assert _answer_rows(done, sample) == sample["rows"]
        statement = done["statement"]
        assert (statement["account_id"], statement["status"]) == (account, 2)
        assert statement["name"] == f"{code}-{month}"
        for balance in sample["balances"]:
            held = balance_of(statement, balance["currency_code"])
            assert held["beginning_balance_cents"] == balance["beginning_balance_cents"]
            assert held["ending_balance_cents"] == balance["ending_balance_cents"]
            assert held["difference_cents"] == 0
        lines = client.get("/bank-lines", params={"statement_id": done["statement_id"]})["items"]
        assert len(lines) == len(sample["rows"])
        assert {line["currency_code"] for line in lines} == {
            r["currency_code"] for r in sample["rows"]
        }

    assert {r["currency_code"] for r in second["rows"]} == {"PEN"}
    assert sorted(s["name"] for s in _statements(client, account)) == [
        f"{code}-202503",
        f"{code}-202504",
    ]


def test_a_card_sample_sent_to_a_soles_only_account_is_refused(client, scratch):
    """The card prints dollar rows, so an account holding no dollars is `CURRENCY_NOT_HELD`
    on a dry run as on an apply (contract: POST /v1/statements/import, "Accounts")."""
    account, _ = _coded(scratch, "PEN")
    sample = _sample(client, "card")
    err = _refused_writing_nothing(
        client,
        account,
        _paper_of(sample),
        422,
        "VALIDATION_ERROR",
        "account_id",
        "CURRENCY_NOT_HELD",
    )
    assert err.fields["account_id"] == "The account holds no USD."


def test_the_drawn_savings_paper_answers_as_the_savings_sample_does(client, scratch):
    """The suite's own drawing of the `savings` sample's rows, days and balances is read as
    the published paper is: the same rows, days and balances (contract: POST /v1/statements/import,
    "The paper's layout")."""
    sample = _sample(client, "savings")
    drawn = savings_paper(
        [
            PaperRow(
                date.fromisoformat(row["date"]),
                row["description"],
                -row["amount_cents"] if row["transaction_type"] == 1 else row["amount_cents"],
                date.fromisoformat(row["processed_on"]),
            )
            for row in sample["rows"]
        ],
        start=date.fromisoformat(sample["date_start"]),
        end=date.fromisoformat(sample["date_end"]),
        before_cents=sample["balances"][0]["beginning_balance_cents"],
    )
    account, _ = _coded(scratch)
    published = send_statement(client, account, _paper_of(sample), dry_run=True)
    mine = send_statement(client, account, drawn, dry_run=True)

    assert published["balances"] == mine["balances"] == sample["balances"]
    assert (mine["date_start"], mine["date_end"]) == (sample["date_start"], sample["date_end"])
    assert _answer_rows(mine, sample) == _answer_rows(published, sample) == sample["rows"]
    assert [r["outcome"] for r in mine["rows"]] == [r["outcome"] for r in published["rows"]]
    assert mine["counts"] == published["counts"]
    assert mine["name"] == published["name"]
