"""Contract: a transaction names the currency of its account it is in, and the lists narrow by
it, against a real engine.

`POST /transactions` and each item of `POST /transactions/batch` carry `account_id` and
`currency_code`; the app's quick-add and Edit form send both, and its lists send `account_id`
and `currency_code`, so only the engine can say what it answers and in which order it refuses
(contract: POST /v1/transactions, "Fields").

What it pins:

1. A create is `201` and echoes `account_id` and `currency_code`, in the answer, the read of
   the row and the list, for each currency of one account.
2. `currency_code` missing is `422` `REQUIRED`, an item's on `transactions.<i>.currency_code`;
   a code the engine does not support (`EUR`, a lower-case `usd`) is `UNSUPPORTED_VALUE`, and
   a supported one the account does not hold (`USD` on a soles-only account, or on one whose
   dollars were removed) is `CURRENCY_NOT_HELD` with the engine's words
   (contract: POST /v1/transactions, "Validation").
3. The order of those refusals, each pair proven by one body breaking both: a taken `id` is
   `409 ID_EXISTS` before the account and currency, even once the account is archived; an
   unknown or archived account and a bad currency are judged together and report both
   fields; on a create the currency is judged before the category and the hashtags, which
   read the ledger, while a batch's one ledger step names all three
   (contract: POST /v1/transactions, "Validation").
4. A batch with one bad item is refused whole on `transactions.<i>.currency_code`, every bad
   item named in the same answer, the good items not written; a missing code (the request's
   shape) answers before a code the account does not hold, and a `line_group` whose items
   differ answers alone, before the ledger's rules
   (contract: POST /v1/transactions/batch, "Refusals come in four steps").
5. A `line_group` whose items differ in `currency_code` is `LINE_GROUP_FIELDS_DIFFER` on each
   item's `currency_code`, nothing written; a group in one currency is one line
   (contract: POST /v1/transactions/batch, "Line groups").
6. An operation code is unique per currency of an account among live bank lines: one code is
   taken once in each currency of one account, a second line in the same currency is `409
   OPERATION_CODE_EXISTS` on `operation_code` (a batch's duplicate within the request
   `DUPLICATE_IN_REQUEST`), and the code is free again once its line is deleted
   (contract: POST /v1/transactions, "Unique per currency of an account among live bank
   lines").
7. `GET /transactions` and `/count` by `?account_id=` cover every currency of the account,
   `?currency_code=` narrows it or, alone, covers that currency on every account, a code the
   engine does not support is `422` `UNSUPPORTED_VALUE` on `currency_code` and dollars on a
   soles-only account list nothing; the list's rows and the count agree
   (contract: GET /v1/transactions) (contract: GET /v1/transactions/count).
8. A cursor sent back with `currency_code` changed, added or dropped is `422` `INVALID_CURSOR`
   on `after`, naming the filter; with the filters unchanged it pages on
   (contract: "Base Conventions", "Cursors, on every cursor-paged list").
9. The old names, sent only to prove their refusal: a former per-currency account id (an unknown
   UUID, see below) is `404` on `GET`, `PUT` and `DELETE /accounts/{id}`, `422`
   `INVALID_REFERENCE` on `account_id` of a create, and an empty list and a count of `0` as
   `?account_id=` on `/transactions` and `/bank-lines`, where the same lists find a real
   account's row; `GET /holders`, `GET /holders/{id}`, `POST /accounts/{id}/move` and
   `POST /people` answer exactly as a route that was never made does (status, code, message,
   `fields`, `reasons` and the whole envelope); `?holder_id=` is `422` `UNKNOWN_PARAMETER` on
   `GET /statements`, `/transactions`, `/bank-lines` and `/bank-lines/count`
   (contract: "Base Conventions", "Unknown query parameters").

Every refused write is read before and after: the account's count and its list (every
currency), and every account the caller has (`all_accounts`), are the same. The refused reads
(the list, the count, the cursor) write nothing.

What it leaves out:

  · `ZERO_AMOUNT` and `FUTURE_DATE` beside a bad currency: neither rule reads the currency,
    so the order between them is not a currency rule; `SEALED_PERIOD` on a currency's days
    is test_sealed_periods.py's.
  · A move of a row to another currency by `PUT`: test_bank_line_write.py's.
  · A real former per-currency id: the contract says no response carries one and no route reads
    it, and the practice user's activity log holds no older entry naming one
    (contract: GET /v1/activity, "Older and restored entries"), so a test would have to guess
    one. The tests of the old names send a fresh random UUID, which the contract says is
    refused the same way (a per-currency account's `id` sent anywhere is refused as an unknown
    account is): they prove an unknown account id's answer, which the contract says a former id
    gets too, not that a former id was once read.
  · The sentence of `OPERATION_CODE_EXISTS`: the contract gives it as the field's text and the
    engine puts a different one there (the contract's sentence is in `error.message`), so the
    suite pins neither; reported to the engine.
  · Which item of a batch's repeated operation code carries the `DUPLICATE_IN_REQUEST` key:
    the contract does not say, so the test accepts either item's key and no other; reported
    to the engine.
  · An operation code raced by two requests at the same moment: a live test cannot land two
    requests together.

Every account is fresh per run (named by its UUID) and every row is removed by the `scratch`
fixture, which is told each id before it is sent. Gating, target resolution and the
real-ledger guard live in conftest.py.
"""

from functools import partial
from uuid import uuid4

import pytest

from tests.contract.conftest import (
    ENGINE_FILLS_ONLY_CURRENCY,
    all_accounts,
    assert_refusal,
    assert_refusals,
    refused,
    refused_keeping,
    transaction_count,
)

DAY = "2026-01-05"
WORDS = {
    "CURRENCY_NOT_HELD": "Must be a currency the account holds.",
    "INVALID_REFERENCE": "Must reference an active, non-archived account.",
}


def _post(client, body: dict) -> dict:
    return client.post("/transactions", json_body=body)


def _batch(client, items: list[dict]) -> dict:
    return client.post("/transactions/batch", json_body={"transactions": items})


def _state(client, *account_ids: str) -> tuple:
    """Everything a refusal must leave as it was: every account the caller has, and for each
    of `account_ids` its count and its list (every currency)."""
    return (
        all_accounts(client),
        {
            account_id: (
                transaction_count(client, account_id),
                client.get("/transactions", params={"account_id": account_id, "limit": 200}),
            )
            for account_id in account_ids
        },
    )


def _refused_writing_nothing(client, account_ids: list[str], call):
    """The engine's refusal of `call`, with `_state` the same before and after it."""
    return refused_keeping(lambda: _state(client, *account_ids), call)


def _ids(client, **params) -> list[str]:
    """The ids `GET /transactions` lists for `params`, every page walked, which must be as
    many as `GET /transactions/count` counts for the same filters."""
    ids: list[str] = []
    after = None
    while True:
        page = {**params, "limit": 200, **({"after": after} if after else {})}
        body = client.get("/transactions", params=page)
        ids += [row["id"] for row in body["items"]]
        after = body["next_cursor"]
        if after is None:
            break
    assert client.get("/transactions/count", params=params)["count"] == len(ids)
    return ids


def test_a_create_echoes_the_account_and_the_currency_for_each_currency_of_an_account(
    client, statuses, scratch
):
    """`201` with `account_id` and `currency_code` as sent, in the answer, the read of the row
    and the list, for soles and for dollars of one account (contract: POST /v1/transactions,
    "Fields")."""
    account_id = scratch.account("PEN", "USD")
    for currency in ("PEN", "USD"):
        body = scratch.body(account_id, currency=currency)
        made = _post(client, body)
        assert statuses[-1] == 201
        assert (made["account_id"], made["currency_code"]) == (account_id, currency)
        read = client.get(f"/transactions/{body['id']}")
        assert (read["account_id"], read["currency_code"]) == (account_id, currency)

    listed = client.get("/transactions", params={"account_id": account_id})["items"]
    assert sorted((row["currency_code"], row["account_id"]) for row in listed) == [
        ("PEN", account_id),
        ("USD", account_id),
    ]
    assert transaction_count(client, account_id) == 2


def test_a_currency_missing_is_required_on_a_create_and_on_a_batch_item(client, scratch):
    """No `currency_code` is `422` `REQUIRED` on it, an item's on
    `transactions.<i>.currency_code`, nothing written (contract: POST /v1/transactions,
    "Fields")."""
    account_id = scratch.account("PEN", "USD")
    body = scratch.body(account_id)
    del body["currency_code"]
    err = _refused_writing_nothing(client, [account_id], partial(_post, client, body))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "REQUIRED")

    good = scratch.body(account_id)
    bad = scratch.body(account_id)
    del bad["currency_code"]
    err = _refused_writing_nothing(client, [account_id], partial(_batch, client, [good, bad]))
    assert_refusal(err, 422, "VALIDATION_ERROR", "transactions.1.currency_code", "REQUIRED")


def test_a_currency_the_engine_does_not_support_is_unsupported_not_unheld(client, scratch):
    """`EUR` and a lower-case `usd` are `422` `UNSUPPORTED_VALUE` on `currency_code`, on a
    soles-only account too, where a supported dollar is `CURRENCY_NOT_HELD`, and an item's on
    `transactions.<i>.currency_code` (contract: POST /v1/transactions, "Validation")."""
    account_id = scratch.account("PEN")
    for code in ("EUR", "usd"):
        body = scratch.body(account_id, currency=code)
        err = _refused_writing_nothing(client, [account_id], partial(_post, client, body))
        assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "UNSUPPORTED_VALUE")

        item = scratch.body(account_id, currency=code)
        err = _refused_writing_nothing(client, [account_id], partial(_batch, client, [item]))
        assert_refusal(
            err, 422, "VALIDATION_ERROR", "transactions.0.currency_code", "UNSUPPORTED_VALUE"
        )


def test_a_currency_the_account_does_not_hold_is_refused_and_a_removed_one_is_not_held(
    client, scratch
):
    """Dollars on a soles-only account are `422` `CURRENCY_NOT_HELD` on `currency_code`, with
    the engine's words; so are dollars on an account whose dollars were removed, and the row
    lands once they are added back (contract: POST /v1/transactions, "Validation")."""
    soles = scratch.account("PEN")
    body = scratch.body(soles, currency="USD")
    err = _refused_writing_nothing(client, [soles], partial(_post, client, body))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "CURRENCY_NOT_HELD")
    assert list(err.fields.values()) == [WORDS["CURRENCY_NOT_HELD"]]

    both = scratch.account("PEN", "USD")
    client.delete(f"/accounts/{both}/currencies/USD")
    again = scratch.body(both, currency="USD")
    err = _refused_writing_nothing(client, [both], partial(_post, client, again))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "CURRENCY_NOT_HELD")

    client.post(f"/accounts/{both}/currencies", json_body={"currency_code": "USD"})
    assert _post(client, again)["currency_code"] == "USD"


def test_the_account_and_the_currency_are_judged_together_after_the_taken_id(client, scratch):
    """An unknown account beside `EUR` reports both fields; an archived account beside dollars
    it does not hold reports both; a taken `id` is `409 ID_EXISTS` on `id` alone before them,
    though the account has been archived since (contract: POST /v1/transactions,
    "Validation")."""
    soles = scratch.account("PEN")
    body = scratch.body(str(uuid4()), currency="EUR")
    err = _refused_writing_nothing(client, [soles], partial(_post, client, body))
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {"account_id": "INVALID_REFERENCE", "currency_code": "UNSUPPORTED_VALUE"},
    )

    scratch.archive(soles)
    body = scratch.body(soles, currency="USD")
    err = _refused_writing_nothing(client, [soles], partial(_post, client, body))
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {"account_id": "INVALID_REFERENCE", "currency_code": "CURRENCY_NOT_HELD"},
    )
    client.post(f"/accounts/{soles}/unarchive")

    taken = scratch.body(soles, currency="PEN")
    _post(client, taken)
    scratch.archive(soles)
    err = _refused_writing_nothing(
        client, [soles], partial(_post, client, {**taken, "currency_code": "USD"})
    )
    assert_refusal(err, 409, "CONFLICT", "id", "ID_EXISTS")


def test_the_currency_is_judged_before_the_category_and_the_hashtags(client, scratch):
    """Dollars a soles-only account does not hold beside a category and a hashtag that name
    nothing report `currency_code` alone on a create; once the currency passes the category
    is reported alone, the hashtag only after the category passes
    (contract: POST /v1/transactions, "Validation"); a batch judges the
    account, the currency, the category and the hashtags in one step and names all three
    (contract: POST /v1/transactions/batch, "Refusals come in four steps")."""
    account_id = scratch.account("PEN")
    nothing = {"category_id": str(uuid4()), "hashtag_ids": [str(uuid4())]}

    body = scratch.body(account_id, currency="USD", **nothing)
    err = _refused_writing_nothing(client, [account_id], partial(_post, client, body))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "CURRENCY_NOT_HELD")

    item = scratch.body(account_id, currency="USD", **nothing)
    err = _refused_writing_nothing(client, [account_id], partial(_batch, client, [item]))
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "transactions.0.currency_code": "CURRENCY_NOT_HELD",
            "transactions.0.category_id": "INVALID_REFERENCE",
            "transactions.0.hashtag_ids": "INVALID_REFERENCE",
        },
    )

    passing = scratch.body(account_id, currency="PEN", **nothing)
    err = _refused_writing_nothing(client, [account_id], partial(_post, client, passing))
    assert_refusal(err, 422, "VALIDATION_ERROR", "category_id", "INVALID_REFERENCE")


def test_a_batch_with_one_bad_item_is_refused_whole_and_names_every_bad_item(client, scratch):
    """A good item, a dollar item on a soles-only account and an `EUR` item: `422` keyed on the
    two bad items' `currency_code` and nothing else, the good one written nowhere
    (contract: POST /v1/transactions/batch, "Refusals come in four steps")."""
    account_id = scratch.account("PEN")
    items = [
        scratch.body(account_id, currency="PEN"),
        scratch.body(account_id, currency="USD"),
        scratch.body(account_id, currency="EUR"),
    ]
    err = _refused_writing_nothing(client, [account_id], partial(_batch, client, items))
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "transactions.1.currency_code": "CURRENCY_NOT_HELD",
            "transactions.2.currency_code": "UNSUPPORTED_VALUE",
        },
    )
    assert err.fields["transactions.1.currency_code"] == WORDS["CURRENCY_NOT_HELD"]

    only_bad = [items[1]]
    err = _refused_writing_nothing(client, [account_id], partial(_batch, client, only_bad))
    assert_refusal(
        err, 422, "VALIDATION_ERROR", "transactions.0.currency_code", "CURRENCY_NOT_HELD"
    )


@ENGINE_FILLS_ONLY_CURRENCY
def test_a_missing_currency_in_a_batch_answers_before_a_currency_the_account_lacks(client, scratch):
    """An item with no `currency_code` beside an item in dollars on a soles-only account:
    only the first is named, as the request's shape is the first step
    (contract: POST /v1/transactions/batch, "Refusals come in four steps")."""
    account_id = scratch.account("PEN")
    missing = scratch.body(account_id)
    del missing["currency_code"]
    unheld = scratch.body(account_id, currency="USD")
    err = _refused_writing_nothing(client, [account_id], partial(_batch, client, [missing, unheld]))
    assert_refusal(err, 422, "VALIDATION_ERROR", "transactions.0.currency_code", "REQUIRED")


def test_a_line_group_whose_items_differ_in_currency_is_refused_and_one_in_a_currency_is_a_line(
    client, scratch
):
    """Two items of one `line_group`, one in soles and one in dollars, are `422`
    `LINE_GROUP_FIELDS_DIFFER` on each item's `currency_code` with the engine's words and
    nothing written; that step answers alone, before an item of another account in dollars
    that account lacks; the same group in one currency is created as one line
    (contract: POST /v1/transactions/batch, "Line groups")."""
    both = scratch.account("PEN", "USD")
    soles = scratch.account("PEN")
    pen = scratch.body(both, currency="PEN", line_group="g")
    usd = scratch.body(both, currency="USD", line_group="g")
    words = "Must be the same on every item of line group 'g'."

    err = _refused_writing_nothing(client, [both], partial(_batch, client, [pen, usd]))
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "transactions.0.currency_code": "LINE_GROUP_FIELDS_DIFFER",
            "transactions.1.currency_code": "LINE_GROUP_FIELDS_DIFFER",
        },
    )
    assert set(err.fields.values()) == {words}

    unheld = scratch.body(soles, currency="USD")
    err = _refused_writing_nothing(
        client, [both, soles], partial(_batch, client, [pen, usd, unheld])
    )
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "transactions.0.currency_code": "LINE_GROUP_FIELDS_DIFFER",
            "transactions.1.currency_code": "LINE_GROUP_FIELDS_DIFFER",
        },
    )

    first = scratch.body(both, currency="USD", line_group="h")
    second = scratch.body(both, -500, "USD", line_group="h")
    made = _batch(client, [first, second])["created"]
    assert {row["currency_code"] for row in made} == {"USD"}
    assert len({row["bank_line_id"] for row in made}) == 1
    assert transaction_count(client, both) == 2


def test_an_operation_code_is_taken_once_in_each_currency_of_an_account(client, scratch):
    """One code on a soles line and on a dollar line of one account is `201` twice, and on
    another account too; a second line in either currency is `409 OPERATION_CODE_EXISTS` on
    `operation_code`, nothing written; the code is free again in a
    currency once its line is deleted, the other currency's line untouched
    (contract: POST /v1/transactions, "Unique per currency of an account among live bank
    lines")."""
    account_id = scratch.account("PEN", "USD")
    other = scratch.account("PEN")
    code = f"OP-{uuid4().hex[:8]}"
    pen = _post(client, scratch.body(account_id, currency="PEN", operation_code=code))
    usd = _post(client, scratch.body(account_id, currency="USD", operation_code=code))
    _post(client, scratch.body(other, currency="PEN", operation_code=code))
    assert pen["bank_line_id"] != usd["bank_line_id"]
    assert transaction_count(client, account_id) == 2

    for currency in ("PEN", "USD"):
        body = scratch.body(account_id, currency=currency, operation_code=code)
        err = _refused_writing_nothing(client, [account_id, other], partial(_post, client, body))
        assert_refusal(err, 409, "CONFLICT", "operation_code", "OPERATION_CODE_EXISTS")

    item = scratch.body(account_id, currency="PEN", operation_code=code)
    err = _refused_writing_nothing(client, [account_id], partial(_batch, client, [item]))
    assert_refusal(err, 409, "CONFLICT", "transactions.0.operation_code", "OPERATION_CODE_EXISTS")

    client.delete(f"/transactions/{pen['id']}")
    again = _post(client, scratch.body(account_id, currency="PEN", operation_code=code))
    assert again["currency_code"] == "PEN"
    usd_again = scratch.body(account_id, currency="USD", operation_code=code)
    err = _refused_writing_nothing(client, [account_id], partial(_post, client, usd_again))
    assert_refusal(err, 409, "CONFLICT", "operation_code", "OPERATION_CODE_EXISTS")


def test_a_batch_takes_one_code_in_both_currencies_and_refuses_it_twice_in_one(client, scratch):
    """One batch holding the same code on a soles item and a dollar item of one account is
    `201`; two soles items with it are `422` `DUPLICATE_IN_REQUEST` on
    `operation_code`, nothing written (contract: POST /v1/transactions/batch,
    "Refusals come in four steps")."""
    account_id = scratch.account("PEN", "USD")
    code = f"OP-{uuid4().hex[:8]}"
    twice = [
        scratch.body(account_id, currency="PEN", operation_code=code),
        scratch.body(account_id, currency="PEN", operation_code=code),
    ]
    err = _refused_writing_nothing(client, [account_id], partial(_batch, client, twice))
    assert (err.status, err.code) == (422, "VALIDATION_ERROR")
    assert err.reasons, err.reasons
    assert set(err.reasons) <= {"transactions.0.operation_code", "transactions.1.operation_code"}
    assert set(err.reasons.values()) == {"DUPLICATE_IN_REQUEST"}
    assert set(err.fields) == set(err.reasons)

    each = [
        scratch.body(account_id, currency="PEN", operation_code=code),
        scratch.body(account_id, currency="USD", operation_code=code),
    ]
    made = _batch(client, each)["created"]
    assert [row["currency_code"] for row in made] == ["PEN", "USD"]
    assert transaction_count(client, account_id) == 2


@pytest.fixture
def ledger(client, scratch):
    """Two accounts holding soles and dollars, each with rows on `DAY`: the first two soles
    rows and one dollar row, the second one of each, and a soles-only account holding one.
    The accounts and the ids by account and currency."""
    first = scratch.account("PEN", "USD")
    second = scratch.account("PEN", "USD")
    soles = scratch.account("PEN")
    rows = {
        (first, "PEN"): [scratch.row(first, DAY, -100)["id"], scratch.row(first, DAY, -200)["id"]],
        (first, "USD"): [scratch.row(first, DAY, -300, "USD")["id"]],
        (second, "PEN"): [scratch.row(second, DAY, -400)["id"]],
        (second, "USD"): [scratch.row(second, DAY, -500, "USD")["id"]],
        (soles, "PEN"): [scratch.row(soles, DAY, -600)["id"]],
    }
    return first, second, soles, rows


def _held(rows, *keys) -> set[str]:
    return {tx for key in keys for tx in rows[key]}


def test_the_lists_by_account_cover_every_currency_and_by_currency_narrow_it(client, ledger):
    """`?account_id=` lists both currencies of the account and counts them; `?currency_code=`
    with it lists that currency of it, and alone that currency on every account, as many as
    `/count` counts; every row read carries the currency asked for
    (contract: GET /v1/transactions)."""
    first, second, soles, rows = ledger
    day = {"date_from": DAY, "date_to": DAY}

    assert set(_ids(client, account_id=first)) == _held(rows, (first, "PEN"), (first, "USD"))
    assert set(_ids(client, account_id=first, currency_code="USD")) == _held(rows, (first, "USD"))
    assert set(_ids(client, account_id=first, currency_code="PEN")) == _held(rows, (first, "PEN"))
    assert set(_ids(client, account_id=soles, currency_code="PEN")) == _held(rows, (soles, "PEN"))

    assert set(_ids(client, currency_code="USD", **day)) == _held(
        rows, (first, "USD"), (second, "USD")
    )
    assert set(_ids(client, currency_code="PEN", **day)) == _held(
        rows, (first, "PEN"), (second, "PEN"), (soles, "PEN")
    )
    for row in client.get("/transactions", params={"currency_code": "USD", **day})["items"]:
        assert row["currency_code"] == "USD"


def test_a_supported_currency_an_account_does_not_hold_lists_nothing(client, ledger):
    """Dollars on the soles-only account list `[]` and count `0`, no refusal
    (contract: GET /v1/transactions)."""
    _, _, soles, _ = ledger
    body = client.get("/transactions", params={"account_id": soles, "currency_code": "USD"})
    assert body["items"] == [] and body["next_cursor"] is None
    count = client.get("/transactions/count", params={"account_id": soles, "currency_code": "USD"})
    assert count == {"count": 0}


@pytest.mark.parametrize("code", ["EUR", "usd", "US"])
def test_a_currency_the_engine_does_not_support_is_refused_by_the_list_and_the_count(
    client, scratch, code
):
    """`?currency_code=<code>` is `422` `UNSUPPORTED_VALUE` on `currency_code` on the list and
    the count, alone or beside `account_id`, never an empty list
    (contract: GET /v1/transactions)."""
    account_id = scratch.account("PEN")
    for path in ("/transactions", "/transactions/count"):
        for extra in ({}, {"account_id": account_id}):
            err = refused(partial(client.get, path, params={"currency_code": code, **extra}))
            assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "UNSUPPORTED_VALUE")


def test_a_cursor_is_bound_to_the_currency_it_was_issued_under(client, scratch):
    """A cursor from `account_id` alone, sent back with `currency_code` added; from
    `currency_code=PEN`, sent back as `USD`; and from `currency_code=PEN`, sent back without
    it: each `422` `INVALID_CURSOR` on `after`, naming the filter, the count of the account
    unchanged; sent back with the same filters it pages on
    (contract: "Base Conventions", "Cursors, on every cursor-paged list")."""
    account_id = scratch.account("PEN", "USD")
    for amount in (-100, -200, -300):
        scratch.row(account_id, DAY, amount)
        scratch.row(account_id, DAY, amount, "USD")
    count = transaction_count(client, account_id)
    assert count == 6

    def page(**params):
        return client.get("/transactions", params={"account_id": account_id, "limit": 1, **params})

    plain = page()["next_cursor"]
    pen = page(currency_code="PEN")["next_cursor"]
    assert plain and pen

    for cursor, params in (
        (plain, {"currency_code": "PEN"}),
        (pen, {"currency_code": "USD"}),
        (pen, {}),
    ):
        err = refused(partial(page, after=cursor, **params))
        assert_refusal(err, 422, "VALIDATION_ERROR", "after", "INVALID_CURSOR")
        assert "currency_code" in err.fields["after"]
    assert transaction_count(client, account_id) == count

    second = page(after=pen, currency_code="PEN")
    assert len(second["items"]) == 1
    assert {row["currency_code"] for row in second["items"]} == {"PEN"}


OLD_FOUND = "account not found."


def test_an_unknown_account_id_is_refused_as_not_found_on_the_account_routes(client, scratch):
    """An id that names no live account is `404` `NOT_FOUND` "account not found." on `GET`,
    `PUT` and `DELETE /accounts/{id}`, with no `fields`, and every account the caller has is as
    it was after each (contract: GET /v1/accounts/{account_id}) (contract: PUT
    /v1/accounts/{account_id}, "Refusals") (contract: DELETE /v1/accounts/{account_id},
    "Refusals"). The contract says a per-currency account's `id` is refused as an unknown
    account is; no real one can be read (the module docstring), so a fresh UUID stands for it."""
    live = scratch.account("PEN")
    former = str(uuid4())
    calls = {
        "GET": partial(client.get, f"/accounts/{former}"),
        "PUT": partial(client.put, f"/accounts/{former}", json_body={"name": f"n-{uuid4()}"}),
        "DELETE": partial(client.delete, f"/accounts/{former}"),
    }
    for method, call in calls.items():
        err = _refused_writing_nothing(client, [live], call)
        assert (err.status, err.code, err.message) == (404, "NOT_FOUND", OLD_FOUND), method
        assert err.fields is None and err.reasons is None, method


def test_an_unknown_account_id_is_refused_as_the_account_of_a_create(client, scratch):
    """A create naming it as `account_id` is `422` `INVALID_REFERENCE` on `account_id` alone,
    with the engine's words, nothing written (contract: POST /v1/transactions,
    "Validation")."""
    live = scratch.account("PEN")
    body = scratch.body(str(uuid4()))
    err = _refused_writing_nothing(client, [live], partial(_post, client, body))
    assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "INVALID_REFERENCE")
    assert err.fields["account_id"] == WORDS["INVALID_REFERENCE"]


def test_an_unknown_account_id_lists_nothing_where_a_real_account_lists_its_rows(client, scratch):
    """`?account_id=` naming no account is `200` with `items` `[]`, no further page and a count
    of `0` on `/transactions` and `/bank-lines`, no refusal; the same lists for a real account
    with one row list it and count it, so the empty answer is not an empty ledger
    (contract: GET /v1/transactions) (contract: GET /v1/bank-lines, "Filters")."""
    live = scratch.account("PEN")
    scratch.row(live, DAY, -100)
    former = str(uuid4())
    for path in ("/transactions", "/bank-lines"):
        found = client.get(path, params={"account_id": live})
        assert len(found["items"]) == 1, path
        assert client.get(f"{path}/count", params={"account_id": live}) == {"count": 1}
        gone = client.get(path, params={"account_id": former})
        assert gone["items"] == [] and gone["next_cursor"] is None, path
        assert client.get(f"{path}/count", params={"account_id": former}) == {"count": 0}


def test_the_holder_routes_the_move_and_the_people_route_answer_as_an_unknown_route(
    client, scratch
):
    """`GET /holders`, `GET /holders/{id}`, `POST /accounts/{id}/move` and `POST /people` are
    `404` `NOT_FOUND` with `fields` and `reasons` `null`, the whole envelope the same as the
    answer of a route that was never made, sent as the same method with the same body; no
    account changes. The contract states these routes gone: there is no `/people` route, and no
    write moves a currency onto another account. The 404 and the null `fields` and `reasons`
    are the envelope's (contract: "Base Conventions", "Every failure is the envelope")
    (contract: "Base Conventions", "`fields` and `reasons` semantics")."""
    live = scratch.account("PEN")
    some = str(uuid4())
    scratch.accounts.append(some)
    cases = [
        (partial(client.get, "/holders"), partial(client.get, "/never-made")),
        (partial(client.get, f"/holders/{some}"), partial(client.get, f"/never-made/{some}")),
        (
            partial(client.post, f"/accounts/{live}/move", json_body={"holder_id": some}),
            partial(client.post, f"/accounts/{live}/never-made", json_body={"holder_id": some}),
        ),
        (
            partial(client.post, "/people", json_body={"id": some, "name": "x"}),
            partial(client.post, "/never-made", json_body={"id": some, "name": "x"}),
        ),
    ]
    for old, never_made in cases:
        err = _refused_writing_nothing(client, [live], old)
        control = refused(never_made)
        assert (control.status, control.code) == (404, "NOT_FOUND")
        assert err.fields is None and err.reasons is None
        assert (err.status, err.code, err.message) == (404, "NOT_FOUND", control.message)
        assert (err.fields, err.reasons) == (control.fields, control.reasons)
        assert err.raw_body == control.raw_body


@pytest.mark.parametrize(
    "path", ["/statements", "/transactions", "/bank-lines", "/bank-lines/count"]
)
def test_holder_id_is_an_unknown_parameter_on_the_lists(client, scratch, path):
    """`?holder_id=` on `GET /statements`, `/transactions`, `/bank-lines` and
    `/bank-lines/count` is `422` `UNKNOWN_PARAMETER` on `holder_id` alone, with the contract's
    words, whether it names a real account or nothing, and also beside a filter the route does
    take; the refused read writes nothing (contract: "Base Conventions", "Unknown query
    parameters")."""
    live = scratch.account("PEN")
    for value in (live, str(uuid4())):
        for extra in ({}, {"account_id": live}):
            call = partial(client.get, path, params={"holder_id": value, **extra})
            err = _refused_writing_nothing(client, [live], call)
            assert_refusal(err, 422, "VALIDATION_ERROR", "holder_id", "UNKNOWN_PARAMETER")
            assert err.fields["holder_id"] == "Not a parameter of this endpoint."
