"""Contract: a currency is added to an account and removed from it, and the account is edited
and deleted, against a real engine.

`POST /accounts/{id}/currencies` takes `{currency_code}` and `DELETE
/accounts/{id}/currencies/{code}` takes the code in the path; Manage ▸ Accounts sends both
(`c` and `x`), so only the engine can say what they answer and in which order they refuse
(contract: POST /v1/accounts/{account_id}/currencies, "Refusals").

What it pins:

1. An add is `201` with the account, the new currency at `0` with no opening balance, the
   account's `version` and `updated_at` unmoved, the read of the account the answer, and the
   currencies in code order whichever was added last; a person is judged like a bank account
   (contract: POST /v1/accounts/{account_id}/currencies, "Response").
2. The add's refusals in the engine's order, every refusal leaving every account the caller
   has as it was (`refused_writing_nothing`): the request's shape (`REQUIRED`, `INVALID_FORMAT`,
   `UNKNOWN_FIELD`) answered alone, even for an account that does not exist; then `404` for
   an unknown or deleted account; then `UNSUPPORTED_VALUE` (`EUR`, `usd`) on `currency_code`;
   then `409 DUPLICATE_CURRENCY` on `currency_code`; then, last, `INVALID_REFERENCE` on
   `account_id` for an archived account, which takes the add again once unarchived
   (contract: POST /v1/accounts/{account_id}/currencies, "Refusals"). Each step is proven
   against the next by one request breaking both, except the pair `UNSUPPORTED_VALUE` and
   `DUPLICATE_CURRENCY`, which no request breaks together (only a supported code can be
   held): the first is shown before the archived step, `pen` on a PEN account is the first
   and not the second, and the second is shown before the archived step.
3. A remove is `200` with the account without the currency, `version` and `updated_at`
   unmoved; the code is released, so the same code added back is `201` at `0` with no opening
   balance (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code},
   "Response").
4. The remove's refusals in the engine's order, each step proven against the next by one
   request breaking both, every refusal leaving every account as it was: `404` "account not
   found." (unknown or deleted account), `404` "currency <code> not found." (`EUR`, `usd`, one
   removed before, the code as sent), `409 ACCOUNT_ARCHIVED` on `account_id`, `409
   LAST_CURRENCY` on `currency_code`, `409 HAS_TRANSACTIONS` on `account_id` while the opening
   balance stands, then `409 IN_LIVE_STATEMENT` on `account_id` while a draft or a completed
   statement (reverted, still a draft) holds the currency's balances, and `200` once each is
   gone; the other currency's opening balance and draft stop nothing
   (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals").
5. An edit (`PUT /accounts/{id}`) is one write: `{statement_code}` (and a person's `name`) is
   `200`, a person's name trimmed, `version` up by one, every currency as it was, for a bank
   account and a person;
   `statement_code: null` clears the code; a body repeating the values still bumps `version`
   and an empty body does not; an archived account is edited and stays archived (contract:
   PUT /v1/accounts/{account_id}, "Response").
6. The edit's refusals, each leaving every account as it was: `currency_code` `IMMUTABLE`
   (`NOT_NULL` for a `null`), `currencies`, `is_person`, `is_archived` and `holder_id`
   `UNKNOWN_FIELD` whatever their value, `NOT_NULL` on a person's `name`, `color` and
   `sort_order`, `409 NAME_EXISTS` for a person's name (a held name of either kind, any case,
   trimmed) and `409 STATEMENT_CODE_EXISTS` (a
   person's and an archived account's included), an account's own name and code no conflict,
   a deleted account's free; and in the engine's order, each step against the next by one body
   breaking both: shape (unknown field, `null`, malformed code), malformed `color`,
   `currency_code`, `404`, empty `name`, then a held code beside an empty name and a held name
   beside a held code (contract: PUT /v1/accounts/{account_id}, "Refusals").
7. A delete is `200` with the account, `deleted_at` set and the currencies it held at `0`,
   an archived account and a person included; the account is then `404` to a read, an edit,
   a second delete and an add, off the list, and a new account takes its name and code at
   once (contract: DELETE /v1/accounts/{account_id}). Its refusals, each `409` on
   `account_id` with the engine's words and every account as it was: `HAS_TRANSACTIONS` for
   an opening balance in either currency or a row, also beside a draft holding balances
   (the earlier rule answers), then `IN_LIVE_STATEMENT` for an account whose only hold is a
   draft with dollar balances and no transaction, archived too, or for a completed statement
   with none (an all-zero card paper), reverted too, and `200` once the statement is
   deleted (contract: DELETE /v1/accounts/{account_id}, "Refusals").

What it leaves out:

  · A per-currency account's old id, and an account of another user, answered `404` like an
    unknown id: the former is task 5's, which sends an old name only to prove its refusal, and
    the second would need a second user holding an id, which the shared practice user's suite
    does not have (docs/decisions.md).
  · The activity entries the writes make (`CREATED` and `DELETED` under `currency`, `UPDATED`
    and `DELETED` under `account`): test_account_reads.py reads them, and the writes here are
    proven by the account read.
  · A `color` or `sort_order` written (only a malformed colour and a `null` are refused here),
    and an empty `name` against `NAME_EXISTS`: no held name is empty, so no body breaks both.
  · Two requests sent at the same moment (`CONCURRENT_CHANGE`, `NAME_EXISTS` raced and the
    other races the contract lists): a live test cannot land two requests together.

Every account is fresh per run (a person named by its UUID, a bank account numbered from the
suite's range) and removed by the `scratch` fixture.
Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from datetime import date
from functools import partial
from uuid import uuid4

import pytest

from tests.contract.conftest import (
    DRAWN_LAST4,
    all_accounts,
    assert_refusal,
    card_paper,
    free_statement_codes,
    refused,
    refused_writing_nothing,
    send_statement,
)

NO_ACCOUNT = "account not found."
#: The words the engine gives each refusal on its key, quoted by the contract's refusal lists.
WORDS = {
    "DUPLICATE_CURRENCY": "Must be a currency the account does not hold.",
    "INVALID_REFERENCE": "Must reference an active, non-archived account.",
    "ACCOUNT_ARCHIVED": "The account is archived. Unarchive it first.",
    "LAST_CURRENCY": "Must not be the account's last currency: delete the account instead.",
    "HAS_TRANSACTIONS": "Must not be used by any active transaction.",
    "IN_LIVE_STATEMENT": (
        "Must be an account no live statement holds, draft or completed: "
        "delete the statement first."
    ),
}


def _add(client, account_id: str, code, **fields) -> dict:
    body = {"currency_code": code, **fields}
    return client.post(f"/accounts/{account_id}/currencies", json_body=body)


def _remove(client, account_id: str, code: str) -> dict:
    return client.delete(f"/accounts/{account_id}/currencies/{code}")


def _add_refused(client, account_id: str, body: dict):
    """The refusal of `body` sent as an add, with every account read the same after."""
    return refused_writing_nothing(
        client, lambda: client.post(f"/accounts/{account_id}/currencies", json_body=body)
    )


def _remove_refused(client, account_id: str, code: str):
    """The refusal of removing `code`, with every account read the same after."""
    return refused_writing_nothing(client, lambda: _remove(client, account_id, code))


def _codes(account: dict) -> list[str]:
    return [c["currency_code"] for c in account["currencies"]]


def _currency(account: dict, code: str) -> dict:
    return next(c for c in account["currencies"] if c["currency_code"] == code)


def _unmoved(after: dict, before: dict) -> None:
    """The account itself was not written: `version` and `updated_at` as before."""
    assert after["version"] == before["version"]
    assert after["updated_at"] == before["updated_at"]


def _deleted(client, scratch) -> str:
    """The id of an account that was live and is deleted."""
    gone = scratch.account("PEN")
    client.delete(f"/accounts/{gone}")
    assert gone not in {a["id"] for a in all_accounts(client)}
    return gone


def _says(err, reason: str) -> None:
    """The refusal's one message is the contract's sentence for `reason`."""
    assert list(err.fields.values()) == [WORDS[reason]]


def _not_found(err, message: str) -> None:
    assert (err.status, err.code, err.message) == (404, "NOT_FOUND", message)


@pytest.mark.parametrize("person", [False, True])
def test_a_currency_is_added_at_zero_with_the_account_itself_unwritten(
    client, statuses, scratch, person
):
    """A bank account and a person, each holding dollars, take soles: `201` with the account,
    the new currency first in code order at `0` with no opening balance, the dollars kept,
    `version` and `updated_at` unmoved, and the read of the account is the answer
    (contract: POST /v1/accounts/{account_id}/currencies, "Response")."""
    account_id = scratch.account("USD", person=person)
    before = client.get(f"/accounts/{account_id}")

    made = _add(client, account_id, "PEN")

    assert statuses[-1] == 201
    assert _codes(made) == ["PEN", "USD"]
    pen = _currency(made, "PEN")
    assert (pen["current_balance_cents"], pen["opening_balance_transaction_id"]) == (0, None)
    assert _currency(made, "USD") == _currency(before, "USD")
    _unmoved(made, before)
    assert made["is_person"] is person
    assert client.get(f"/accounts/{account_id}") == made
    assert [a for a in all_accounts(client) if a["id"] == account_id] == [made]


def test_the_requests_shape_is_answered_alone_even_for_an_account_that_does_not_exist(
    client, scratch
):
    """`currency_code` missing is `REQUIRED`, not a string `INVALID_FORMAT`, any other field
    `UNKNOWN_FIELD`, each also with an id that names no account, where the `404` would follow
    (contract: POST /v1/accounts/{account_id}/currencies, "Refusals")."""
    held = scratch.account("PEN")
    for account_id in (held, str(uuid4()), _deleted(client, scratch)):
        err = _add_refused(client, account_id, {})
        assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "REQUIRED")

        for bad in (7, None, ["USD"]):
            err = _add_refused(client, account_id, {"currency_code": bad})
            assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "INVALID_FORMAT")

        err = _add_refused(client, account_id, {"currency_code": "USD", "bogus": 1})
        assert_refusal(err, 422, "VALIDATION_ERROR", "bogus", "UNKNOWN_FIELD")

        err = _add_refused(client, account_id, {"currency_code": "EUR", "holder_id": "x"})
        assert_refusal(err, 422, "VALIDATION_ERROR", "holder_id", "UNKNOWN_FIELD")


def test_an_add_to_an_account_that_does_not_exist_is_not_found_before_its_currency_is_judged(
    client, scratch
):
    """An unknown id and a deleted account's are `404`, whatever the currency: an
    unsupported one, a held one, a good one
    (contract: POST /v1/accounts/{account_id}/currencies, "Refusals")."""
    for account_id in (str(uuid4()), _deleted(client, scratch)):
        for code in ("EUR", "PEN", "USD"):
            err = _add_refused(client, account_id, {"currency_code": code})
            assert (err.status, err.code) == (404, "NOT_FOUND")


def test_an_unsupported_currency_is_refused_before_a_held_one_and_before_the_archive(
    client, scratch
):
    """`EUR` and a lower-case `usd` are `422` `UNSUPPORTED_VALUE` on `currency_code`, even on
    an archived account, which would answer `INVALID_REFERENCE` later
    (contract: POST /v1/accounts/{account_id}/currencies, "Refusals")."""
    account_id = scratch.account("PEN")
    for code in ("EUR", "usd", "pen", ""):
        err = _add_refused(client, account_id, {"currency_code": code})
        assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "UNSUPPORTED_VALUE")

    scratch.archive(account_id)
    for code in ("EUR", "usd"):
        err = _add_refused(client, account_id, {"currency_code": code})
        assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "UNSUPPORTED_VALUE")


def test_a_held_currency_is_a_duplicate_before_the_archive_and_a_removed_one_is_free(
    client, scratch
):
    """A currency the account holds is `409` `DUPLICATE_CURRENCY` on `currency_code`, also
    on an archived account, which would answer `INVALID_REFERENCE` later; a currency removed
    before does not hold its code (contract: POST /v1/accounts/{account_id}/currencies,
    "Refusals")."""
    account_id = scratch.account("PEN", "USD")
    for code in ("PEN", "USD"):
        err = _add_refused(client, account_id, {"currency_code": code})
        assert_refusal(err, 409, "CONFLICT", "currency_code", "DUPLICATE_CURRENCY")
        _says(err, "DUPLICATE_CURRENCY")

    scratch.archive(account_id)
    err = _add_refused(client, account_id, {"currency_code": "USD"})
    assert_refusal(err, 409, "CONFLICT", "currency_code", "DUPLICATE_CURRENCY")
    _says(err, "DUPLICATE_CURRENCY")

    client.post(f"/accounts/{account_id}/unarchive")
    _remove(client, account_id, "USD")
    assert _codes(_add(client, account_id, "USD")) == ["PEN", "USD"]


def test_an_archived_account_takes_no_new_currency_until_it_is_unarchived(client, scratch):
    """The add of a currency the archived account lacks is `422` `INVALID_REFERENCE` on
    `account_id`, for a bank account and a person, and `201` once unarchived, the account
    then holding every currency (contract: POST /v1/accounts/{account_id}/currencies,
    "Refusals")."""
    for person in (False, True):
        account_id = scratch.account("PEN", person=person)
        scratch.archive(account_id)

        err = _add_refused(client, account_id, {"currency_code": "USD"})
        assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "INVALID_REFERENCE")
        _says(err, "INVALID_REFERENCE")

        client.post(f"/accounts/{account_id}/unarchive")
        made = _add(client, account_id, "USD")
        assert _codes(made) == ["PEN", "USD"]
        assert made["is_archived"] is False


def test_a_currency_is_removed_with_the_account_unwritten_and_its_code_released(
    client, statuses, scratch
):
    """A bank account and a person holding soles and dollars lose the dollars: `200` with
    the account without them, the soles kept, `version` and `updated_at` unmoved, the read of
    the account the answer; the same code added back is `201` at `0` with no opening balance
    (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Response")."""
    for person in (False, True):
        account_id = scratch.account("PEN", "USD", person=person)
        before = client.get(f"/accounts/{account_id}")

        left = _remove(client, account_id, "USD")

        assert statuses[-1] == 200
        assert _codes(left) == ["PEN"]
        assert _currency(left, "PEN") == _currency(before, "PEN")
        _unmoved(left, before)
        assert client.get(f"/accounts/{account_id}") == left

        back = _add(client, account_id, "USD")
        assert statuses[-1] == 201
        assert _codes(back) == ["PEN", "USD"]
        usd = _currency(back, "USD")
        assert (usd["current_balance_cents"], usd["opening_balance_transaction_id"]) == (0, None)
        _unmoved(back, before)


def test_a_remove_for_an_account_or_currency_not_found_is_404_with_the_codes_as_sent(
    client, scratch
):
    """An unknown and a deleted account are `404` "account not found." whatever the code,
    one that is unsupported included; an account lacking the currency is `404` "currency
    <code> not found.": `EUR`, a lower-case `usd`, and `USD` once removed, each as sent; the
    account's own check comes first (contract: DELETE
    /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals")."""
    account_id = scratch.account("PEN", "USD")

    for gone in (str(uuid4()), _deleted(client, scratch)):
        for code in ("USD", "EUR", "usd"):
            _not_found(_remove_refused(client, gone, code), NO_ACCOUNT)

    for code in ("EUR", "usd", "Pen", "GBP"):
        _not_found(_remove_refused(client, account_id, code), f"currency {code} not found.")

    _remove(client, account_id, "USD")
    _not_found(_remove_refused(client, account_id, "USD"), "currency USD not found.")


def test_a_currency_not_found_is_answered_before_the_archive(client, scratch):
    """On an archived account a code it does not hold is still `404` "currency <code> not
    found.", while one it holds is `ACCOUNT_ARCHIVED` (contract: DELETE
    /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals")."""
    account_id = scratch.account("PEN", "USD")
    _remove(client, account_id, "USD")
    scratch.archive(account_id)

    for code in ("USD", "EUR", "usd"):
        _not_found(_remove_refused(client, account_id, code), f"currency {code} not found.")
    err = _remove_refused(client, account_id, "PEN")
    assert_refusal(err, 409, "CONFLICT", "account_id", "ACCOUNT_ARCHIVED")
    _says(err, "ACCOUNT_ARCHIVED")


def test_an_archived_account_keeps_its_currencies_before_the_last_one_is_judged(client, scratch):
    """An archived account loses no currency: `409` `ACCOUNT_ARCHIVED` on `account_id` for a
    removal of either of two and of an only one, where `LAST_CURRENCY` would follow, a person
    included; once unarchived the removal goes through again (contract: DELETE
    /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals")."""
    both = scratch.account("PEN", "USD")
    only = scratch.account("PEN", person=True)
    scratch.archive(both)
    scratch.archive(only)

    for account_id, code in ((both, "PEN"), (both, "USD"), (only, "PEN")):
        err = _remove_refused(client, account_id, code)
        assert_refusal(err, 409, "CONFLICT", "account_id", "ACCOUNT_ARCHIVED")
        _says(err, "ACCOUNT_ARCHIVED")

    client.post(f"/accounts/{both}/unarchive")
    assert _codes(_remove(client, both, "USD")) == ["PEN"]


def test_the_last_currency_is_refused_before_what_is_booked_in_it_and_its_account_goes_instead(
    client, scratch
):
    """The only currency of an account is `409` `LAST_CURRENCY` on `currency_code`, a person's
    too, even with an opening balance in it, which would answer `HAS_TRANSACTIONS` later; so
    is the one currency left after the other was removed; the account is deleted instead
    (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals")."""
    only = scratch.account("USD")
    person = scratch.account("PEN", person=True)
    for account_id, code in ((only, "USD"), (person, "PEN")):
        err = _remove_refused(client, account_id, code)
        assert_refusal(err, 409, "CONFLICT", "currency_code", "LAST_CURRENCY")
        _says(err, "LAST_CURRENCY")

    scratch.opening_balance(only, "2026-01-02", "USD")
    err = _remove_refused(client, only, "USD")
    assert_refusal(err, 409, "CONFLICT", "currency_code", "LAST_CURRENCY")
    _says(err, "LAST_CURRENCY")

    pair = scratch.account("PEN", "USD")
    _remove(client, pair, "PEN")
    err = _remove_refused(client, pair, "USD")
    assert_refusal(err, 409, "CONFLICT", "currency_code", "LAST_CURRENCY")
    _says(err, "LAST_CURRENCY")

    client.delete(f"/accounts/{person}")
    assert person not in {a["id"] for a in all_accounts(client)}


@pytest.mark.xfail(
    strict=True,
    reason="the removal's refusal is keyed on currency_code: task 4 of "
    "docs/specs/catch-up-to-1002f105c6bacdf1.md",
)
def test_an_opening_balance_stops_the_removal_before_a_draft_and_goes_with_its_deletion(
    client, scratch
):
    """A currency holding an opening balance is `409` `HAS_TRANSACTIONS` on `account_id`; a
    draft holding the currency's balances too still answers `HAS_TRANSACTIONS`, the earlier
    rule; with the opening balance deleted it is `IN_LIVE_STATEMENT`, also once the statement
    is completed and again once it is reverted, and the removal goes through once the
    statement is deleted (the completed one holds a soles line to complete on, and the dollars
    at 0, which are what stops the removal). On another account, an opening balance and a
    draft in USD stop nothing when PEN is removed: the rules judge the currency removed alone
    (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals")."""
    account_id = scratch.account("PEN", "USD")
    scratch.opening_balance(account_id, "2026-01-02", "USD")
    seed = _currency(client.get(f"/accounts/{account_id}"), "USD")["opening_balance_transaction_id"]
    assert seed is not None

    err = _remove_refused(client, account_id, "USD")
    assert_refusal(err, 409, "CONFLICT", "account_id", "HAS_TRANSACTIONS")
    _says(err, "HAS_TRANSACTIONS")

    draft = scratch.statement(account_id, "2026-02-01", "2026-02-28", "USD")["id"]
    err = _remove_refused(client, account_id, "USD")
    assert_refusal(err, 409, "CONFLICT", "account_id", "HAS_TRANSACTIONS")
    _says(err, "HAS_TRANSACTIONS")

    client.delete(f"/transactions/{seed}")
    assert (
        _currency(client.get(f"/accounts/{account_id}"), "USD")["opening_balance_transaction_id"]
        is None
    )
    err = _remove_refused(client, account_id, "USD")
    assert_refusal(err, 409, "CONFLICT", "account_id", "IN_LIVE_STATEMENT")
    _says(err, "IN_LIVE_STATEMENT")

    client.delete(f"/statements/{draft}")
    row = scratch.row(account_id, "2026-02-10", -1000, "PEN")["id"]
    balances = [
        {"currency_code": "PEN", "beginning_balance_cents": 0, "ending_balance_cents": -1000},
        {"currency_code": "USD", "beginning_balance_cents": 0, "ending_balance_cents": 0},
    ]
    draft = scratch.statement(account_id, "2026-02-01", "2026-02-28", balances=balances)["id"]
    scratch.assign(row, draft)
    client.post(f"/statements/{draft}/complete")
    err = _remove_refused(client, account_id, "USD")
    assert_refusal(err, 409, "CONFLICT", "account_id", "IN_LIVE_STATEMENT")
    _says(err, "IN_LIVE_STATEMENT")

    client.post(f"/statements/{draft}/revert")
    err = _remove_refused(client, account_id, "USD")
    assert_refusal(err, 409, "CONFLICT", "account_id", "IN_LIVE_STATEMENT")
    _says(err, "IN_LIVE_STATEMENT")

    client.delete(f"/statements/{draft}")
    assert _codes(_remove(client, account_id, "USD")) == ["PEN"]

    other = scratch.account("PEN", "USD")
    scratch.opening_balance(other, "2026-01-02", "USD")
    scratch.statement(other, "2026-02-01", "2026-02-28", "USD")
    assert _codes(_remove(client, other, "PEN")) == ["USD"]


def test_a_removal_judged_by_every_refusal_is_answered_by_the_first(client, scratch):
    """One account breaking every rule at once: archived, one currency, an opening balance in
    it and a draft holding it. A code it lacks is `404` first; the held one is
    `ACCOUNT_ARCHIVED`, then, unarchived, `LAST_CURRENCY`, never the two rules after it
    (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals")."""
    account_id = scratch.account("USD")
    scratch.opening_balance(account_id, "2026-01-02", "USD")
    scratch.statement(account_id, "2026-02-01", "2026-02-28", "USD")
    scratch.archive(account_id)

    _not_found(_remove_refused(client, account_id, "PEN"), "currency PEN not found.")
    err = _remove_refused(client, account_id, "USD")
    assert_refusal(err, 409, "CONFLICT", "account_id", "ACCOUNT_ARCHIVED")
    _says(err, "ACCOUNT_ARCHIVED")

    client.post(f"/accounts/{account_id}/unarchive")
    err = _remove_refused(client, account_id, "USD")
    assert_refusal(err, 409, "CONFLICT", "currency_code", "LAST_CURRENCY")
    _says(err, "LAST_CURRENCY")


def _put(client, account_id: str, body: dict) -> dict:
    return client.put(f"/accounts/{account_id}", json_body=body)


def _edit_refused(client, account_id: str, body: dict):
    """The refusal of `body` sent as an edit, with every account read the same after."""
    return refused_writing_nothing(client, lambda: _put(client, account_id, body))


def _delete_refused(client, account_id: str):
    """The refusal of deleting the account, with every account read the same after."""
    return refused_writing_nothing(client, lambda: client.delete(f"/accounts/{account_id}"))


def _fresh(client, account_id: str) -> dict:
    """The account as its read gives it, the answer of a write shown by the list too."""
    held = client.get(f"/accounts/{account_id}")
    assert [a for a in all_accounts(client) if a["id"] == account_id] == [held]
    return held


def _name() -> str:
    return f"contract-stmt-edit-{uuid4().hex[:8]}"


@pytest.mark.parametrize("person", [False, True])
def test_an_edit_writes_the_account_once_and_no_currency(client, statuses, scratch, person):
    """`{statement_code}` (and a person's `name`) is one write, `200` with the account: the
    person's name trimmed, a bank account's as it was, the code set, `version` up by one,
    `updated_at` not before it was, every currency as it was (balance and opening balance) and
    the kind, colour, order, archive state kept; the read of the account is the answer
    (contract: PUT /v1/accounts/{account_id}, "Response")."""
    old, new = free_statement_codes(client, 2)
    account_id = scratch.account("PEN", "USD", person=person, code=old)
    scratch.opening_balance(account_id, "2026-01-02", "USD")
    before = client.get(f"/accounts/{account_id}")
    name = _name()
    body = {"statement_code": new, **({"name": f"  {name}  "} if person else {})}

    made = _put(client, account_id, body)

    assert statuses[-1] == 200
    assert (made["name"], made["statement_code"]) == (name if person else before["name"], new)
    assert made["version"] == before["version"] + 1
    assert made["updated_at"] >= before["updated_at"]
    assert made["currencies"] == before["currencies"]
    kept = {"id", "user_id", "color", "is_person", "is_archived", "sort_order", "created_at"}
    assert {k: made[k] for k in kept} == {k: before[k] for k in kept}
    assert made["deleted_at"] is None
    assert _fresh(client, account_id) == made


def test_a_statement_code_is_cleared_by_null_and_the_colour_alone_leaves_it(client, scratch):
    """`statement_code: null` clears the code, `version` up by one; a body with the colour alone
    leaves a code as it was; clearing an account with none still writes (`version` up), as does
    a body repeating the values it holds, while an empty body returns the account unchanged
    with no bump; the cleared code is then taken back (contract: PUT
    /v1/accounts/{account_id})."""
    code = free_statement_codes(client, 1)[0]
    account_id = scratch.account("PEN", code=code)
    start = client.get(f"/accounts/{account_id}")

    recoloured = _put(client, account_id, {"color": "#00aa00"})
    assert recoloured["statement_code"] == code
    assert recoloured["version"] == start["version"] + 1

    cleared = _put(client, account_id, {"statement_code": None})
    assert cleared["statement_code"] is None
    assert cleared["version"] == recoloured["version"] + 1
    assert _fresh(client, account_id) == cleared

    again = _put(client, account_id, {"statement_code": None})
    assert again["version"] == cleared["version"] + 1
    assert again["statement_code"] is None

    same = _put(client, account_id, {"color": again["color"]})
    assert same["version"] == again["version"] + 1

    empty = _put(client, account_id, {})
    assert empty == same
    assert _fresh(client, account_id) == same

    free = _put(client, account_id, {"statement_code": code})
    assert free["statement_code"] == code


def test_an_archived_account_is_edited_and_stays_archived(client, scratch):
    """An archived account takes a new colour and code and a cleared one, and its `is_archived`
    stays true (contract: PUT /v1/accounts/{account_id})."""
    code = free_statement_codes(client, 1)[0]
    account_id = scratch.account("PEN", "USD")
    scratch.archive(account_id)
    before = client.get(f"/accounts/{account_id}")

    made = _put(client, account_id, {"color": "#00aa00", "statement_code": code})
    assert (made["color"], made["statement_code"], made["is_archived"]) == ("#00aa00", code, True)
    assert made["version"] == before["version"] + 1
    assert made["currencies"] == before["currencies"]
    assert _fresh(client, account_id) == made

    assert _put(client, account_id, {"statement_code": None})["is_archived"] is True


def test_a_currency_is_no_field_of_the_edit_and_nor_are_the_kind_and_archive_state(client, scratch):
    """`currency_code` is `422` `IMMUTABLE` on its key, a `null` there `NOT_NULL` like any
    other; `currencies`, `is_person`,
    `is_archived` and `holder_id` are `UNKNOWN_FIELD`, whatever their value (their own, the
    other, `null`); each leaves every account as it was, and a change of kind or archive state
    goes through its own route (contract: PUT /v1/accounts/{account_id})."""
    account_id = scratch.account("PEN", "USD")

    for code in ("PEN", "USD", "EUR"):
        err = _edit_refused(client, account_id, {"currency_code": code})
        assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "IMMUTABLE")
    err = _edit_refused(client, account_id, {"currency_code": None})
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "NOT_NULL")

    held = [{"currency_code": "PEN"}, {"currency_code": "USD"}]
    values = {
        "currencies": [held, [], None],
        "is_person": [False, True, None],
        "is_archived": [False, True, None],
        "holder_id": [str(uuid4()), None],
    }
    for key, sent in values.items():
        for value in sent:
            err = _edit_refused(client, account_id, {key: value})
            assert_refusal(err, 422, "VALIDATION_ERROR", key, "UNKNOWN_FIELD")


def test_a_null_is_refused_on_every_field_but_the_statement_code(client, scratch):
    """`null` on `name`, `color` or `sort_order` is `422` `NOT_NULL` on that key, even beside
    an edit that would be good; the statement code is the one field it clears
    (contract: PUT /v1/accounts/{account_id})."""
    account_id = scratch.account("PEN", person=True)

    for key in ("name", "color", "sort_order"):
        err = _edit_refused(client, account_id, {key: None})
        assert_refusal(err, 422, "VALIDATION_ERROR", key, "NOT_NULL")
        err = _edit_refused(client, account_id, {key: None, "statement_code": None})
        assert_refusal(err, 422, "VALIDATION_ERROR", key, "NOT_NULL")


def test_an_edit_is_refused_in_the_engines_order_each_step_before_the_next(client, scratch):
    """Each pair is one body breaking both rules: the request's shape (an unknown field, a
    `null`, a malformed `statement_code`) before a malformed `color`, a malformed `color`
    before `currency_code`, `currency_code` before the `404` of an account that does not
    exist, that `404` before an empty `name`, `NAME_EXISTS` before `STATEMENT_CODE_EXISTS`;
    `EMPTY` and `NAME_EXISTS` are not paired, as no empty name is held by an account
    (contract: PUT /v1/accounts/{account_id}, "Refusals")."""
    held_code = free_statement_codes(client, 1)[0]
    account_id = scratch.account("PEN", code=held_code, person=True)
    other = scratch.account("PEN", person=True)
    other_name = client.get(f"/accounts/{other}")["name"]
    third = scratch.account("PEN", person=True)
    gone = str(uuid4())
    bad_color = "red"

    cases = [
        ({"bogus": 1, "color": bad_color}, "bogus", "UNKNOWN_FIELD", account_id),
        ({"sort_order": None, "color": bad_color}, "sort_order", "NOT_NULL", account_id),
        ({"statement_code": "ab", "color": bad_color}, "statement_code", "INVALID_FORMAT", gone),
        (
            {"statement_code": "ab", "currency_code": "PEN"},
            "statement_code",
            "INVALID_FORMAT",
            gone,
        ),
        ({"color": bad_color, "currency_code": "PEN"}, "color", "INVALID_FORMAT", account_id),
        ({"color": bad_color}, "color", "INVALID_FORMAT", gone),
        ({"currency_code": "PEN", "name": ""}, "currency_code", "IMMUTABLE", account_id),
        ({"currency_code": "PEN"}, "currency_code", "IMMUTABLE", gone),
        ({"name": ""}, None, "NOT_FOUND", gone),
        ({"name": other_name}, None, "NOT_FOUND", gone),
        ({"statement_code": held_code, "name": ""}, "name", "EMPTY", third),
        ({"name": other_name, "statement_code": held_code}, "name", "NAME_EXISTS", third),
    ]
    for body, key, reason, target in cases:
        err = _edit_refused(client, target, body)
        if key is None:
            assert (err.status, err.code, err.message) == (404, reason, NO_ACCOUNT)
            continue
        status = 409 if reason == "NAME_EXISTS" else 422
        code = "CONFLICT" if status == 409 else "VALIDATION_ERROR"
        assert_refusal(err, status, code, key, reason)


def test_a_name_or_code_another_account_holds_is_a_conflict_and_its_own_is_not(client, scratch):
    """A name another live account holds, of either kind, upper case or trimmed, is `409`
    `NAME_EXISTS` on `name`; a code another holds, an archived account's and a person's
    included, is `409` `STATEMENT_CODE_EXISTS` on `statement_code`; an account's own name
    (also in other letters) and code are not a conflict; a deleted account's are free
    (contract: PUT /v1/accounts/{account_id}, "Refusals")."""
    bank_code, person_code, own_code, archived_code = free_statement_codes(client, 4)
    bank = scratch.account("PEN", code=bank_code)
    person = scratch.account("USD", person=True, code=person_code)
    scratch.archive(scratch.account("PEN", code=archived_code))
    mine = scratch.account("PEN", code=own_code, person=True)
    names = {k: client.get(f"/accounts/{k}")["name"] for k in (bank, person)}

    for held in names.values():
        for sent in (held, held.upper(), f"  {held}  "):
            err = _edit_refused(client, mine, {"name": sent})
            assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")

    for held in (bank_code, person_code):
        err = _edit_refused(client, mine, {"statement_code": held})
        assert_refusal(err, 409, "CONFLICT", "statement_code", "STATEMENT_CODE_EXISTS")

    err = _edit_refused(client, mine, {"statement_code": archived_code})
    assert_refusal(err, 409, "CONFLICT", "statement_code", "STATEMENT_CODE_EXISTS")

    own_name = client.get(f"/accounts/{mine}")["name"]
    made = _put(client, mine, {"name": own_name.upper(), "statement_code": own_code})
    assert (made["name"], made["statement_code"]) == (own_name.upper(), own_code)

    client.delete(f"/accounts/{bank}")
    taken = _put(client, mine, {"name": names[bank], "statement_code": bank_code})
    assert (taken["name"], taken["statement_code"]) == (names[bank], bank_code)


def test_an_account_edit_that_does_not_exist_is_not_found(client, scratch):
    """An unknown id and a deleted account's are `404` "account not found." for an edit that
    would be good (contract: PUT /v1/accounts/{account_id})."""
    for gone in (str(uuid4()), _deleted(client, scratch)):
        _not_found(_edit_refused(client, gone, {"name": _name()}), NO_ACCOUNT)
        _not_found(_edit_refused(client, gone, {}), NO_ACCOUNT)


@pytest.mark.parametrize("person", [False, True])
def test_a_deleted_account_is_gone_with_its_currencies_and_releases_its_name_and_code(
    client, statuses, scratch, person
):
    """The delete is `200` with the account, `deleted_at` set, the currencies it held each at
    `0`; `GET` is then `404`, the list lacks it, an edit, a second delete and an add are
    `404`, and a new account takes its name and code at once; an archived account is deleted
    like any other (contract: DELETE /v1/accounts/{account_id}, "Response")."""
    for archived in (False, True):
        code = free_statement_codes(client, 1)[0]
        account_id = scratch.account("PEN", "USD", person=person, code=code)
        if archived:
            scratch.archive(account_id)
        before = client.get(f"/accounts/{account_id}")

        gone = client.delete(f"/accounts/{account_id}")

        assert statuses[-1] == 200
        assert gone["deleted_at"] is not None
        assert gone["id"] == account_id
        assert _codes(gone) == ["PEN", "USD"]
        assert [c["current_balance_cents"] for c in gone["currencies"]] == [0, 0]
        assert (gone["name"], gone["is_person"]) == (before["name"], person)
        assert account_id not in {a["id"] for a in all_accounts(client)}
        _not_found(refused(partial(client.get, f"/accounts/{account_id}")), NO_ACCOUNT)
        _not_found(refused(partial(_put, client, account_id, {})), NO_ACCOUNT)
        _not_found(refused(partial(client.delete, f"/accounts/{account_id}")), NO_ACCOUNT)
        _not_found(_add_refused(client, account_id, {"currency_code": "EUR"}), NO_ACCOUNT)

        same = {"name": before["name"]} if person else {"last4": before["numbers"][0]["last4"]}
        remade = scratch.account("PEN", code=code, person=person, **same)
        again = client.get(f"/accounts/{remade}")
        assert (again["name"], again["statement_code"]) == (before["name"], code)


def test_a_delete_of_an_account_that_does_not_exist_is_not_found(client, scratch):
    """An unknown id and an id a delete already took are `404` "account not found."
    (contract: DELETE /v1/accounts/{account_id})."""
    for gone in (str(uuid4()), _deleted(client, scratch)):
        _not_found(_delete_refused(client, gone), NO_ACCOUNT)


def test_a_transaction_in_any_currency_stops_the_delete_before_a_statement(client, scratch):
    """An opening balance in either currency of the account is `409` `HAS_TRANSACTIONS` on
    `account_id`; so is a row, and so is one beside a draft holding balances for the account
    (the earlier rule is the one answered); the account is deleted once the row is gone
    (contract: DELETE /v1/accounts/{account_id}, "Refusals")."""
    for code in ("PEN", "USD"):
        account_id = scratch.account("PEN", "USD")
        scratch.opening_balance(account_id, "2026-01-02", code)
        err = _delete_refused(client, account_id)
        assert_refusal(err, 409, "CONFLICT", "account_id", "HAS_TRANSACTIONS")
        _says(err, "HAS_TRANSACTIONS")

        scratch.statement(account_id, "2026-02-01", "2026-02-28", "PEN", "USD")
        err = _delete_refused(client, account_id)
        assert_refusal(err, 409, "CONFLICT", "account_id", "HAS_TRANSACTIONS")
        _says(err, "HAS_TRANSACTIONS")

    account_id = scratch.account("PEN", "USD")
    row = scratch.row(account_id, "2026-01-05", -1000, "USD")["id"]
    err = _delete_refused(client, account_id)
    assert_refusal(err, 409, "CONFLICT", "account_id", "HAS_TRANSACTIONS")
    _says(err, "HAS_TRANSACTIONS")

    client.delete(f"/transactions/{row}")
    assert client.delete(f"/accounts/{account_id}")["deleted_at"] is not None


def test_a_statement_alone_stops_the_delete_until_it_is_deleted(client, scratch):
    """An account whose only hold is a draft with dollar balances and no transaction is `409`
    `IN_LIVE_STATEMENT` on `account_id`, archived too; a deleted statement does not count and
    the account is then deleted (contract: DELETE /v1/accounts/{account_id}, "Refusals")."""
    account_id = scratch.account("PEN", "USD")
    draft = scratch.statement(account_id, "2026-02-01", "2026-02-28", "USD")["id"]
    err = _delete_refused(client, account_id)
    assert_refusal(err, 409, "CONFLICT", "account_id", "IN_LIVE_STATEMENT")
    _says(err, "IN_LIVE_STATEMENT")

    scratch.archive(account_id)
    err = _delete_refused(client, account_id)
    assert_refusal(err, 409, "CONFLICT", "account_id", "IN_LIVE_STATEMENT")

    client.post(f"/accounts/{account_id}/unarchive")
    client.delete(f"/statements/{draft}")
    assert client.delete(f"/accounts/{account_id}")["deleted_at"] is not None


def test_a_completed_statement_with_no_transaction_stops_the_delete(client, scratch):
    """An all-zero card paper uploaded to a soles and dollars account with a statement code
    completes a statement holding no transaction; the delete is `409` `IN_LIVE_STATEMENT`
    on `account_id`, also once reverted, and `200` once the statement is deleted (contract:
    DELETE /v1/accounts/{account_id}, "Refusals")."""
    code = free_statement_codes(client, 1)[0]
    account_id = scratch.account("PEN", "USD", code=code, last4=DRAWN_LAST4)
    paper = card_paper([], start=date(2026, 3, 1), end=date(2026, 3, 31))
    done = send_statement(client, account_id, paper, dry_run=False)
    # no answer rows, so `[]` alone proves little: that no transaction stands is the refusal
    # below being IN_LIVE_STATEMENT, not HAS_TRANSACTIONS, which the engine judges first
    assert scratch.took(done) == []
    statement = done["statement_id"]
    assert client.get(f"/statements/{statement}")["status"] == 2

    err = _delete_refused(client, account_id)
    assert_refusal(err, 409, "CONFLICT", "account_id", "IN_LIVE_STATEMENT")
    _says(err, "IN_LIVE_STATEMENT")

    client.post(f"/statements/{statement}/revert")
    err = _delete_refused(client, account_id)
    assert_refusal(err, 409, "CONFLICT", "account_id", "IN_LIVE_STATEMENT")

    client.delete(f"/statements/{statement}")
    assert client.delete(f"/accounts/{account_id}")["deleted_at"] is not None
