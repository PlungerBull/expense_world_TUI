"""Contract: the largest amount the engine takes, sent whole to the engine, and `GET /currencies`,
against a real engine.

The app reads an amount only as a plain number and sends it as whole cents, so it never sends
`1e5000` or a whole number of any size; these tests send what the app cannot, to prove what the
engine answers every client (contract: "Base Conventions", "Money amounts"):

1. `GET /currencies` answers `{items: [{currency_code}]}` alone per entry, in `currency_code`
   order, ascending, the same for every user, and lists the currencies an account may hold
   (PEN and USD among them); each of those is accepted on a new account, and the list takes no
   parameter (contract: GET /v1/currencies).
2. A transaction's `amount_cents` one cent past 99,999,999,999 in either direction, or a whole
   number of any size, is `422` `OUT_OF_RANGE` on `amount_cents` (an item's on
   `transactions.<i>.amount_cents`), the message naming the bound; a decimal or exponent form
   up to what a 64-bit whole number holds (`1e18`) is the same; past that (`1e19`, `1e30`,
   `1e5000`, sent as raw JSON) it is `INVALID_FORMAT`. The bound itself is taken in either
   direction. A refusal writes nothing.
3. A cell past the bound in the statement PDF's rows and printed balance, in the sheet import
   (`rows.<row>.amount_cents`) and in the bank import is refused up front, every such row in
   one answer, each message beginning `Row <row>:`, on the dry run (with and without the
   sheet's table) and the apply, nothing written. A cell of a
   workbook is a number a spreadsheet can hold, so `1e5000` cannot be put in one: the files
   carry a cell one cent past the bound and a far larger one
   (contract: POST /v1/transactions/import-sheet, "Rejected up front with `422`")
   (contract: POST /v1/transactions/import, "Rejected up front with `422`").

Gating, target and the real-ledger guard: conftest.py.
"""

import json
from datetime import date
from uuid import uuid4

import httpx
import pytest

from expense.import_.engine import request_body as sheet_request_body
from tests.contract.conftest import (
    CLEANER,
    CURRENT_HEADER,
    DRAWN_LAST4,
    PaperRow,
    assert_refusal,
    free_statement_codes,
    refused,
    refused_keeping,
    savings_paper,
    send_download,
    send_statement,
    sheet_file,
    sheet_row,
    transaction_count,
)

#: The largest amount, in cents (contract: "Base Conventions", "Money amounts").
BOUND = 99_999_999_999
#: How a request field's message names the bound, and how a file row's does.
BOUND_TEXT = "99999999999"
FILE_BOUND_TEXT = "99,999,999,999"


def test_the_currencies_listed_are_the_ones_an_account_may_hold(client, reserved_client, scratch):
    """`GET /currencies` answers the whole list, each entry `currency_code` alone, in code order,
    ascending; it lists PEN and USD, the currencies an account is made with, and every listed
    code is accepted on a new account (contract: GET /v1/currencies)."""
    answer = client.get("/currencies")
    assert list(answer) == ["items"]
    codes = [entry["currency_code"] for entry in answer["items"]]
    assert all(list(entry) == ["currency_code"] for entry in answer["items"])
    assert codes == sorted(set(codes))
    assert {"PEN", "USD"} <= set(codes)
    assert reserved_client.get("/currencies") == answer
    err = refused(lambda: client.get("/currencies", params={"page": "1"}))
    assert_refusal(err, 422, "VALIDATION_ERROR", "page", "UNKNOWN_PARAMETER")
    for code in codes:
        account = scratch.account(code)
        assert [c["currency_code"] for c in client.get(f"/accounts/{account}")["currencies"]] == [
            code
        ]


def _error_of(response: httpx.Response) -> dict:
    return response.json()["error"]


def _raw_post(target, path: str, raw: str) -> httpx.Response:
    """`raw`, JSON text exactly as given, posted to `path` as the caller: the app's client
    encodes a body from Python values, which cannot spell `1e5000`."""
    return httpx.post(
        f"{target.engine_url}/v1{path}",
        content=raw.encode(),
        headers={
            "Authorization": f"Bearer {target.token}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": str(uuid4()),
        },
        timeout=60,
    )


def _assert_out_of_range(err, key: str = "amount_cents") -> None:
    assert_refusal(err, 422, "VALIDATION_ERROR", key, "OUT_OF_RANGE")
    assert BOUND_TEXT in err.fields[key]


@pytest.mark.parametrize(
    "amount",
    [BOUND + 1, -BOUND - 1, 10**30, -(10**30), 10**400],
)
def test_a_whole_number_past_the_bound_is_out_of_range_on_a_create_and_a_batch_item(
    client, scratch, amount
):
    """One cent past the bound, a much larger whole number and the negative side are each `422`
    `OUT_OF_RANGE` on `amount_cents`, an item's on `transactions.<i>.amount_cents`, the message
    naming the bound, nothing written (contract: "Base Conventions", "Money amounts")."""
    account = scratch.account()
    body = scratch.body(account, amount)
    err = refused_keeping(
        lambda: transaction_count(client, account),
        lambda: client.post("/transactions", json_body=body),
    )
    _assert_out_of_range(err)

    good, bad = scratch.body(account), scratch.body(account, amount)
    err = refused_keeping(
        lambda: transaction_count(client, account),
        lambda: client.post("/transactions/batch", json_body={"transactions": [good, bad]}),
    )
    _assert_out_of_range(err, "transactions.1.amount_cents")


def test_the_bound_itself_is_taken_in_either_direction(client, scratch):
    """99,999,999,999 and its negative are accepted (contract: "Base Conventions", "Money
    amounts")."""
    account = scratch.account()
    for amount in (BOUND, -BOUND):
        made = client.post("/transactions", json_body=scratch.body(account, amount))
        assert made["amount_cents"] == BOUND  # a write answers the magnitude
    assert transaction_count(client, account) == 2


@pytest.mark.parametrize(
    ("number", "reason"),
    [
        ("100000000000.0", "OUT_OF_RANGE"),
        ("-100000000000.0", "OUT_OF_RANGE"),
        ("1e18", "OUT_OF_RANGE"),
        ("-1e18", "OUT_OF_RANGE"),
        ("1e19", "INVALID_FORMAT"),
        ("-1e19", "INVALID_FORMAT"),
        ("1e30", "INVALID_FORMAT"),
        ("1e5000", "INVALID_FORMAT"),
        ("-1e5000", "INVALID_FORMAT"),
    ],
)
def test_an_exponent_form_is_out_of_range_up_to_a_64_bit_whole_number_and_invalid_past_it(
    client, target, scratch, number, reason
):
    """A decimal form past the bound (`100000000000.0`) and an exponent form up to about 9.2e18
    are `OUT_OF_RANGE`, past it (`1e19`, `1e30`, `1e5000`) `INVALID_FORMAT`, on
    `amount_cents`, nothing written; sent as raw JSON, since the app's client cannot
    spell it (contract: "Base Conventions", "Money amounts")."""
    account = scratch.account()
    body = scratch.body(account, 7)
    raw = json.dumps(body)
    assert '"amount_cents": 7' in raw
    sent = raw.replace('"amount_cents": 7', f'"amount_cents": {number}')
    before = transaction_count(client, account)
    response = _raw_post(target, "/transactions", sent)
    error = _error_of(response)
    assert (response.status_code, error["code"]) == (422, "VALIDATION_ERROR")
    assert error["reasons"] == {"amount_cents": reason}
    if reason == "OUT_OF_RANGE":
        assert BOUND_TEXT in error["fields"]["amount_cents"]
    assert transaction_count(client, account) == before == 0


# ---- a cell past the bound in a file ----

#: One cent past the bound, a far larger amount and the negative side, as a spreadsheet cell.
PAST = [(1_000_000_000.0, "positive"), (-1_000_000_000.0, "negative"), (1e30, "huge")]


def test_a_sheet_cell_past_the_bound_refuses_the_whole_sheet_up_front(client, scratch):
    """Rows holding `MONTO` one cent past the bound, its negative and `1e30` are each `422`
    `OUT_OF_RANGE` on `rows.<row>.amount_cents` beside a good row that is not named, every row
    in one answer, its message beginning `Row <row>:`, on the dry run with or without the table
    and on the apply, nothing written (contract: POST /v1/transactions/import-sheet,
    "Rejected up front with `422`")."""
    run = uuid4().hex[:10]
    person = scratch.account("PEN", person=True)
    category, hashtag = scratch.category(), scratch.hashtag()
    names = {
        "accounts": [{"name": f"contract-sheet-{run}", "account_id": person}],
        "categories": [{"name": f"contract-sheet-c-{run}", "category_id": category}],
        "hashtags": [{"name": f"contract-sheet-h-{run}", "hashtag_id": hashtag}],
    }
    rows = [
        sheet_row(
            "BIEN",
            names["hashtags"][0]["name"],
            names["categories"][0]["name"],
            date(2026, 3, 14),
            -9.5,
            f"contract-sheet-{run}",
            "PEN",
        )  # fmt: skip
    ] + [
        sheet_row(
            f"PASADO {kind}",
            names["hashtags"][0]["name"],
            names["categories"][0]["name"],
            date(2026, 3, 15),
            amount,
            f"contract-sheet-{run}",
            "PEN",
        )  # fmt: skip
        for amount, kind in PAST
    ]
    data = sheet_file(rows)
    held = CLEANER.holdings(client), transaction_count(client, person)
    for dry_run, table in ((True, None), (True, names), (False, names)):
        body = sheet_request_body(data, dry_run=dry_run, names=table)
        err = refused(lambda body=body: client.post("/transactions/import-sheet", json_body=body))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert err.reasons == {f"rows.{row}.amount_cents": "OUT_OF_RANGE" for row in (3, 4, 5)}
        for row in (3, 4, 5):
            message = err.fields[f"rows.{row}.amount_cents"]
            assert message.startswith(f"Row {row}:") and FILE_BOUND_TEXT in message
        assert (CLEANER.holdings(client), transaction_count(client, person)) == held


def test_a_bank_download_cell_past_the_bound_refuses_the_whole_file_up_front(client, scratch):
    """The same cells in a current account's download are `OUT_OF_RANGE` on
    `rows.<row>.amount_cents` beside a good row, each message beginning `Row <row>:`, on the dry
    run and the apply, nothing written (contract: POST /v1/transactions/import, "Rejected up
    front with `422`")."""
    account = scratch.account()
    held = CLEANER.holdings(client)
    rows = [CURRENT_HEADER, ["05/03/2026", "BIEN", "S/", -9.5, f"OP{uuid4().hex[:10]}"]] + [
        ["06/03/2026", f"PASADO {kind}", "S/", amount, f"OP{uuid4().hex[:10]}"]
        for amount, kind in PAST
    ]
    for dry_run in (True, False):
        err = refused(lambda dry_run=dry_run: send_download(client, account, rows, dry_run=dry_run))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR")
        assert err.reasons == {f"rows.{row}.amount_cents": "OUT_OF_RANGE" for row in (3, 4, 5)}
        for row in (3, 4, 5):
            message = err.fields[f"rows.{row}.amount_cents"]
            assert message.startswith(f"Row {row}:") and FILE_BOUND_TEXT in message
        assert transaction_count(client, account) == 0
        assert client.get("/bank-lines", params={"account_id": account})["items"] == []
        assert CLEANER.holdings(client) == held


def test_a_statement_paper_past_the_bound_refuses_the_whole_paper_up_front(client, scratch):
    """A row of a savings paper one cent past the bound, its negative and a far larger one are
    each `OUT_OF_RANGE` on `rows.<place>.amount_cents` beside a good row, every such row in one
    answer, each message `Row <place>: The amount is past the largest amount,
    99,999,999,999 cents.`; a previous balance printed past it is `OUT_OF_RANGE` on `file`
    alone, naming the balance; dry run and apply alike, nothing written
    (contract: POST /v1/statements/import, "Rejected up front with `422`")."""
    code = free_statement_codes(client, 1)[0]
    account = scratch.account(code=code, last4=DRAWN_LAST4)
    march = {"start": date(2026, 3, 1), "end": date(2026, 3, 31)}
    day = date(2026, 3, 10)
    amounts = [BOUND + 1, -BOUND - 1, 10**12, -(10**12)]
    rows = [PaperRow(day, "BIEN", 950)] + [
        PaperRow(day, f"PASADO {i}", a) for i, a in enumerate(amounts)
    ]
    papers = [
        (savings_paper(rows, before_cents=0, **march), "rows"),
        (savings_paper([PaperRow(day, "BIEN", 950)], before_cents=BOUND + 1, **march), "file"),
    ]
    held = (CLEANER.holdings(client), _held_on(client, account))
    for paper, where in papers:
        for dry_run in (True, False):
            err = refused(lambda p=paper, d=dry_run: send_statement(client, account, p, dry_run=d))
            assert (err.status, err.code) == (422, "VALIDATION_ERROR")
            if where == "file":
                assert_refusal(err, 422, "VALIDATION_ERROR", "file", "OUT_OF_RANGE")
                assert FILE_BOUND_TEXT in err.fields["file"] or BOUND_TEXT in err.fields["file"]
            else:
                assert err.reasons == {
                    f"rows.{p}.amount_cents": "OUT_OF_RANGE" for p in (2, 3, 4, 5)
                }
                for place in (2, 3, 4, 5):
                    assert err.fields[f"rows.{place}.amount_cents"] == (
                        f"Row {place}: The amount is past the largest amount, "
                        f"{FILE_BOUND_TEXT} cents."
                    )
            assert (CLEANER.holdings(client), _held_on(client, account)) == held


def _held_on(client, account: str) -> tuple:
    """What a refused upload leaves as it was: the account's transactions, bank lines and
    statements."""
    return (
        transaction_count(client, account),
        client.get("/bank-lines", params={"account_id": account})["items"],
        client.get("/statements", params={"account_id": account})["items"],
    )
