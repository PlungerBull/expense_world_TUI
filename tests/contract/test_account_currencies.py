"""Contract: a currency is added to an account and removed from it, against a real engine.

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

What it leaves out:

  · A per-currency account's old id, and an account of another user, answered `404` like an
    unknown id: the former is task 5's, which sends an old name only to prove its refusal, and
    the second would need a second user holding an id, which the shared practice user's suite
    does not have (docs/decisions.md).
  · The activity entries the two writes make (`CREATED` and `DELETED` under `currency`): the
    activity log is read by its own tests, and the writes here are proven by the account read.
  · Two requests sent at the same moment (`CONCURRENT_CHANGE` and the races the contract
    lists): a live test cannot land two requests together.

Every account is fresh per run (named by its UUID) and removed by the `scratch` fixture.
Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from uuid import uuid4

import pytest

from tests.contract.conftest import (
    all_accounts,
    assert_refusal,
    refused_writing_nothing,
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
