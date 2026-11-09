"""Contract: a statement PDF is checked against the account's numbers, against a real engine.

`POST /statements/import` reads the number the paper prints and the account's `numbers`; only the
engine can say which it takes and what it refuses (contract: POST /v1/statements/import, "The
numbers the paper prints must fit the account's"). Every paper is made up by the test
(`savings_paper`, `card_paper` in conftest.py), numbered by its `last4`.

What it pins:

1. A paper whose number is not the account's, a savings paper and a card paper alike, is `422`
   `STATEMENT_NUMBER_MISMATCH` on `account_id`, naming both numbers, on the dry run and the
   apply alike, writing nothing, and before a currency the account lacks.
2. An account with no number is `ACCOUNT_HAS_NO_NUMBER` on `account_id`, on both, writing
   nothing, after the statement code (`NO_STATEMENT_CODE` comes first) and before the currencies.
3. A card replaced after the month closes the earlier month: the March paper printing the old
   number is taken on the dry run and the apply, the new number's March paper is taken too (a
   replacement the account starts after the last day), the April paper printing the old number is
   refused, and the replacement may not then start inside the closed month
   (`NUMBER_IN_COMPLETED_STATEMENT`).

Every account is fresh per run and removed by the `scratch` fixture.
Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from datetime import date

from tests.contract.conftest import (
    CardRow,
    PaperRow,
    assert_refusal,
    card_paper,
    free_statement_codes,
    next_last4,
    refused_keeping,
    savings_paper,
    send_statement,
)

MARCH = {"start": date(2026, 3, 1), "end": date(2026, 3, 31)}
APRIL = {"start": date(2026, 4, 1), "end": date(2026, 4, 30)}
SAVINGS_ROWS = [PaperRow(date(2026, 3, 4), "COMPRA", -100)]
CARD_ROWS = [CardRow(date(2026, 3, 4), "LIBRERIA INVENTADA LIMA PE", "CONSUMO", 50000)]


def _held(client, account_id: str) -> tuple:
    """What a refused upload must leave as it was: the account's transactions, bank lines and
    statements."""
    return (
        client.get("/transactions", params={"account_id": account_id})["items"],
        client.get("/bank-lines", params={"account_id": account_id})["items"],
        client.get("/statements", params={"account_id": account_id})["items"],
    )


def _refused_on_both(client, account_id: str, paper: bytes, reason: str):
    """The paper is refused `reason` on `account_id` by the dry run and the apply, nothing
    written; the last refusal."""
    for dry_run in (True, False):
        err = refused_keeping(
            lambda: _held(client, account_id),
            lambda dry_run=dry_run: send_statement(client, account_id, paper, dry_run=dry_run),
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", reason)
    return err


def test_a_paper_printing_another_number_is_refused_naming_both(client, scratch):
    """A savings paper and a card paper numbered other than the account's, and a dollar paper
    sent to a soles account numbered otherwise (the number comes before the currencies)
    (contract: POST /v1/statements/import,
    "The numbers the paper prints must fit the account's")."""
    code = free_statement_codes(client, 1)[0]
    mine, theirs = next_last4(), next_last4()
    account_id = scratch.account("PEN", code=code, last4=mine)
    papers = [
        savings_paper(SAVINGS_ROWS, before_cents=10000, last4=theirs, **MARCH),
        card_paper(CARD_ROWS, last4=theirs, **MARCH),
        savings_paper(SAVINGS_ROWS, before_cents=10000, currency="USD", last4=theirs, **MARCH),
    ]
    for paper in papers:
        err = _refused_on_both(client, account_id, paper, "STATEMENT_NUMBER_MISMATCH")
        assert mine in err.fields["account_id"] and theirs in err.fields["account_id"]


def test_an_account_with_no_number_is_refused_after_its_statement_code(client, scratch):
    """An unnumbered account without a code is `NO_STATEMENT_CODE`; given a code it is
    `ACCOUNT_HAS_NO_NUMBER`, before the currencies (a dollar paper to a soles account)
    (contract: POST /v1/statements/import,
    "The numbers the paper prints must fit the account's")."""
    code = free_statement_codes(client, 1)[0]
    account_id = scratch.account("PEN", last4=None)
    soles = savings_paper(SAVINGS_ROWS, before_cents=10000, **MARCH)
    dollars = savings_paper(SAVINGS_ROWS, before_cents=10000, currency="USD", **MARCH)
    _refused_on_both(client, account_id, soles, "NO_STATEMENT_CODE")
    client.put(f"/accounts/{account_id}", json_body={"statement_code": code})
    for paper in (soles, dollars):
        _refused_on_both(client, account_id, paper, "ACCOUNT_HAS_NO_NUMBER")


def test_a_replaced_cards_earlier_month_still_closes(client, scratch):
    """The account's card is replaced from 10 April. The March paper printing the old number
    closes March; the one printing the new number is taken on the dry run too; the April paper
    printing the old number is `STATEMENT_NUMBER_MISMATCH`; and a replacement moved back into
    the closed March is `NUMBER_IN_COMPLETED_STATEMENT`
    (contract: POST /v1/statements/import,
    "The numbers the paper prints must fit the account's")
    (contract: PUT /v1/accounts/{account_id}, "The numbers")."""
    code = free_statement_codes(client, 1)[0]
    old, new = next_last4(), next_last4()
    account_id = scratch.account("PEN", code=code, last4=old)
    replacement = {"new_number": {"last4": new, "start_date": "2026-04-10"}}
    client.put(f"/accounts/{account_id}", json_body=replacement)

    march_old = card_paper(CARD_ROWS, last4=old, **MARCH)
    march_new = card_paper(CARD_ROWS, last4=new, **MARCH)
    dry = send_statement(client, account_id, march_new, dry_run=True)
    assert dry["statement_id"] is None

    april_old = card_paper(
        [CardRow(date(2026, 4, 4), "LIBRERIA INVENTADA LIMA PE", "CONSUMO", 50000)],
        last4=old,
        **APRIL,
    )
    _refused_on_both(client, account_id, april_old, "STATEMENT_NUMBER_MISMATCH")

    done = send_statement(client, account_id, march_old, dry_run=False)
    scratch.took(done)
    assert client.get(f"/statements/{done['statement_id']}")["status"] == 2

    moved = {"current_number": {"start_date": "2026-03-15"}}
    err = refused_keeping(
        lambda: client.get(f"/accounts/{account_id}"),
        lambda: client.put(f"/accounts/{account_id}", json_body=moved),
    )
    assert (err.status, err.reasons) == (409, {"current_number": "NUMBER_IN_COMPLETED_STATEMENT"})
