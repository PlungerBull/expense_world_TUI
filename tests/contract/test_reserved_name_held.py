"""Contract: a held reserved name — `RESERVED_NAME_HELD`, as the reserved-names practice user.

`@Pendiente`, `@Opening` and the built-in pending hashtag are created by the engine the first
time a write needs them. When one of the caller's own categories or hashtags already holds
that name, the write that needed it is refused `409` `CONFLICT` with reason
`RESERVED_NAME_HELD`, and nothing is written (contract: "Error reasons")
(contract: POST /v1/categories, "Reserved names")
(contract: "Hashtags", "The built-in pending hashtag"). The reserved-names practice user
(`reserved_client`, docs/runtime.md "Working against the live engine") holds a user category
`@Pendiente`, one `@Opening` and a user hashtag `Pendiente`, and none of the system rows, so
every such write of theirs is refused.

The routes whose check can answer it, each one the contract lists `RESERVED_NAME_HELD` for,
and the key it names:

  · POST /v1/transactions, a row with no hashtag on `hashtag_ids`, one with no category
    on `category_id` (contract: POST /v1/transactions);
  · POST /v1/transactions/batch, the same, keyed as on the single create, never
    `transactions.<i>.…` (contract: POST /v1/transactions/batch);
  · PUT /v1/transactions/{id}, its hashtags emptied, on `hashtag_ids`
    (contract: PUT /v1/transactions/{transaction_id});
  · PUT /v1/bank-lines/{id} with `parts`, a new part with no hashtag on `hashtag_ids`, one
    with no category on `category_id`, never `parts.<i>.…`
    (contract: PUT /v1/bank-lines/{bank_line_id});
  · DELETE /v1/hashtags/{id} of a transaction's only hashtag, on `hashtag_id`
    (contract: DELETE /v1/hashtags/{hashtag_id});
  · POST /v1/accounts/{id}/opening-balance, needing `@Opening`, on `category_id`
    (contract: POST /v1/accounts/{account_id}/opening-balance);
  · POST /v1/transactions/import, the apply of a made-up download whose row is new, which
    needs both, on `category_id` or `hashtag_ids`, whichever it needs first: the contract
    names both keys and no order between them (contract: POST /v1/transactions/import);
  · POST /v1/transactions/import-sheet, the apply of a made-up sheet whose row is an
    account's opening balance, on `rows.<row>.category_id`
    (contract: POST /v1/transactions/import-sheet);
  · POST /v1/reconciliations/import, the apply of a made-up savings statement PDF
    (`savings_paper` in conftest.py) whose row is new, which needs both, on `category_id`
    or `hashtag_ids`, whichever it needs first (contract: POST /v1/reconciliations/import).

After each refusal, nothing was written: the account's transaction count, the bank line or
transaction it would have changed, and the user's categories and hashtags read as before.

The user's seeded category and hashtag are never renamed or deleted: every run and every
other test relies on them. Everything a test makes on the user is named `contract-…` and
undone; the leak check covers this user too (`leaves_nothing` in conftest.py). Gating, target
and the real-ledger guard: conftest.py.
"""

from collections.abc import Callable
from datetime import date
from uuid import uuid4

import pytest

from expense.bank_line_write import line_body, new_part
from expense.http import ExpenseClient
from expense.import_.engine import request_body
from tests.contract.conftest import (
    PaperRow,
    Scratch,
    assert_refusal,
    free_statement_codes,
    refused,
    savings_paper,
    send_statement,
    sheet_file,
    sheet_row,
    workbook,
)

#: The names the reserved-names user's own rows hold: two categories and a hashtag.
HELD_CATEGORIES = {"@Pendiente", "@Opening"}
HELD_HASHTAG = "Pendiente"

DAY = "2026-05-04"
AMOUNT = -1250


@pytest.fixture
def held(reserved_client) -> None:
    """The reserved-names user holds the reserved names as their own rows, and the engine
    has made none of the system rows for them; otherwise no write can be refused here."""
    categories = reserved_client.get("/categories")["items"]
    hashtags = reserved_client.get("/hashtags")["items"]
    assert HELD_CATEGORIES <= {c["name"] for c in categories if c["system_key"] is None}
    assert HELD_HASHTAG in {h["name"] for h in hashtags if h["system_key"] is None}
    assert not [row for row in categories + hashtags if row["system_key"] is not None]


@pytest.fixture
def made(reserved_client, held):
    """A `Scratch` on the reserved-names user, cleaned up after the test."""
    scratch = Scratch(reserved_client)
    yield scratch
    scratch.cleanup()


def _snapshot(client: ExpenseClient, account_id: str) -> tuple:
    """What a refused write must leave as it was: the account's live transaction count and
    every category and hashtag of the user's, as read."""
    count = client.get("/transactions/count", params={"account_id": account_id})["count"]
    return count, client.get("/categories")["items"], client.get("/hashtags")["items"]


def _refused_writing_nothing(
    client: ExpenseClient, account_id: str, call: Callable[[], object], *keys: str
) -> None:
    """`call` is refused `409` `CONFLICT` with `RESERVED_NAME_HELD` on one key alone, one of
    `keys`, and the account and the user's categories and hashtags read as before. A write
    needing both `@Pendiente` and the pending hashtag is refused on the first it needs, and
    the contract fixes no order between them, so such a call passes both keys."""
    before = _snapshot(client, account_id)
    err = refused(call)
    assert isinstance(err.reasons, dict) and len(err.reasons) == 1, err.reasons
    key = next(iter(err.reasons))
    assert key in keys, err.reasons
    assert_refusal(err, 409, "CONFLICT", key, "RESERVED_NAME_HELD")
    assert _snapshot(client, account_id) == before


def _row(made: Scratch, account_id: str, **fields) -> dict:
    return {
        "id": str(uuid4()),
        "title": "contract reserved row",
        "amount_cents": AMOUNT,
        "account_id": account_id,
        "date": made.noon(DAY),
        **fields,
    }


def _tagged_row(made: Scratch, account_id: str, category: str, hashtag: str) -> dict:
    """A transaction with a category and a hashtag of the test's own, which needs no
    system row; its read."""
    row = _row(made, account_id, category_id=category, hashtag_ids=[hashtag])
    made.transactions.append(row["id"])
    return made.client.post("/transactions", json_body=row)


def test_a_create_needing_the_pending_hashtag_or_pendiente_is_refused(reserved_client, made):
    account, category, hashtag = made.account(), made.category(), made.hashtag()
    for body, key in (
        (_row(made, account, category_id=category), "hashtag_ids"),
        (_row(made, account, hashtag_ids=[hashtag]), "category_id"),
    ):
        made.transactions.append(body["id"])
        _refused_writing_nothing(
            reserved_client,
            account,
            lambda body=body: reserved_client.post("/transactions", json_body=body),
            key,
        )


def test_a_batch_needing_the_pending_hashtag_or_pendiente_is_refused(reserved_client, made):
    account, category, hashtag = made.account(), made.category(), made.hashtag()
    for body, key in (
        (_row(made, account, category_id=category), "hashtag_ids"),
        (_row(made, account, hashtag_ids=[hashtag]), "category_id"),
    ):
        made.transactions.append(body["id"])
        batch = {"transactions": [body]}
        _refused_writing_nothing(
            reserved_client,
            account,
            lambda batch=batch: reserved_client.post("/transactions/batch", json_body=batch),
            key,
        )


def test_an_edit_emptying_the_hashtags_is_refused(reserved_client, made):
    account, category, hashtag = made.account(), made.category(), made.hashtag()
    tx = _tagged_row(made, account, category, hashtag)
    _refused_writing_nothing(
        reserved_client,
        account,
        lambda: reserved_client.put(f"/transactions/{tx['id']}", json_body={"hashtag_ids": []}),
        "hashtag_ids",
    )
    reread = reserved_client.get(f"/transactions/{tx['id']}")
    assert (reread["hashtag_ids"], reread["version"]) == ([hashtag], tx["version"])


def test_a_whole_line_write_needing_the_pending_hashtag_or_pendiente_is_refused(
    reserved_client, made
):
    account, category, hashtag = made.account(), made.category(), made.hashtag()
    tx = _tagged_row(made, account, category, hashtag)
    line = tx["bank_line_id"]
    before = reserved_client.get(f"/bank-lines/{line}")
    for part, key in (
        (new_part(amount_cents=AMOUNT, category_id=category), "hashtag_ids"),
        (new_part(amount_cents=AMOUNT, hashtag_ids=[hashtag]), "category_id"),
    ):
        made.transactions.append(part["id"])
        body = line_body([part])
        _refused_writing_nothing(
            reserved_client,
            account,
            lambda body=body: reserved_client.put(f"/bank-lines/{line}", json_body=body),
            key,
        )
        assert reserved_client.get(f"/bank-lines/{line}") == before


def test_deleting_a_transactions_only_hashtag_is_refused(reserved_client, made):
    account, category, hashtag = made.account(), made.category(), made.hashtag()
    tx = _tagged_row(made, account, category, hashtag)
    _refused_writing_nothing(
        reserved_client,
        account,
        lambda: reserved_client.delete(f"/hashtags/{hashtag}"),
        "hashtag_id",
    )
    assert reserved_client.get(f"/hashtags/{hashtag}")["deleted_at"] is None
    assert reserved_client.get(f"/transactions/{tx['id']}")["hashtag_ids"] == [hashtag]


def test_an_opening_balance_needing_opening_is_refused(reserved_client, made):
    account = made.account()
    body = {"transaction_id": str(uuid4()), "amount_cents": 50000, "date": made.noon(DAY)}
    made.transactions.append(body["transaction_id"])
    _refused_writing_nothing(
        reserved_client,
        account,
        lambda: reserved_client.post(f"/accounts/{account}/opening-balance", json_body=body),
        "category_id",
    )


def test_a_bank_download_creating_a_row_is_refused(reserved_client, made):
    account = made.account()
    file = workbook(
        [
            ["Fecha", "Descripcion", "Moneda", "Monto", "Numero de Operacion"],
            ["04/05/2026", "contract reserved row", "S/", AMOUNT / 100, "000123"],
        ]
    )

    def upload(dry_run: bool) -> dict:
        body = {"dry_run": dry_run, "account_id": account, "file": file}
        return reserved_client.post("/transactions/import", json_body=body)

    assert [row["outcome"] for row in upload(True)["rows"]] == ["new"]
    _refused_writing_nothing(
        reserved_client, account, lambda: upload(False), "category_id", "hashtag_ids"
    )


def test_a_sheet_creating_an_opening_balance_is_refused(reserved_client, made):
    account = made.account()
    name = reserved_client.get(f"/accounts/{account}")["name"]
    opening = sheet_row(
        "contract reserved opening",
        "contract-unused",
        "SALDO INICIAL",
        date(2026, 1, 2),
        500,
        name,
        "PEN",
    )
    names = {
        "accounts": [{"name": name, "currency_code": "PEN", "account_id": account}],
        "categories": [],
        "hashtags": [],
    }
    body = request_body(sheet_file([opening]), dry_run=False, names=names)
    _refused_writing_nothing(
        reserved_client,
        account,
        lambda: reserved_client.post("/transactions/import-sheet", json_body=body),
        "rows.2.category_id",
    )


def test_a_statement_pdf_creating_a_row_is_refused(reserved_client, made):
    code = free_statement_codes(reserved_client, 1)[0]
    account = made.account("PEN", code)
    paper = savings_paper(
        [PaperRow(date(2026, 5, 4), "CONTRACT RESERVED", AMOUNT)],
        start=date(2026, 5, 1),
        end=date(2026, 5, 31),
        before_cents=10000,
    )
    dry = send_statement(reserved_client, account, paper, dry_run=True)
    assert [row["outcome"] for row in dry["rows"]] == ["new"]
    _refused_writing_nothing(
        reserved_client,
        account,
        lambda: send_statement(reserved_client, account, paper, dry_run=False),
        "category_id",
        "hashtag_ids",
    )
    assert reserved_client.get("/reconciliations", params={"account_id": account})["items"] == []
