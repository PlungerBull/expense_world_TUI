"""Contract lifecycle for an account's opening balance, per currency, against a real engine.

The account Edit form reads each currency's opening balance through that currency's entry in
the account's `currencies` (`opening_balance_transaction_id`) and changes it through the
transaction routes. Only the engine can say that id stays current, and that an opening
balance never moves to another account or currency or out of `@Opening`
(contract: PUT /v1/transactions/{transaction_id}, "Opening balances stay put").

What it pins, in the order the form meets it:

1. A new account names no opening balance in any currency (`null`); `POST
   /accounts/{id}/opening-balance` seeds one currency and only that currency's entry then
   names its id.
2. Editing its amount and date keeps the same id on the entry.
3. A different `account_id` or `currency_code` is `422` `OPENING_BALANCE_ACCOUNT_FIXED` on
   each key sent; a different `category_id` (`@Pendiente`) is `422`
   `OPENING_BALANCE_CATEGORY_FIXED`; all in one body report all. Resending its own is accepted.
4. The request needs a `currency_code` (`REQUIRED`), a supported one (`UNSUPPORTED_VALUE`)
   that the account holds (`CURRENCY_NOT_HELD`), all `422` on `currency_code`.
5. A second opening balance in one currency is `409` `OPENING_BALANCE_EXISTS` on
   `account_id` while the account's other currency takes its own; each entry names its own.
6. Deleting one leaves its entry `null` and the other's untouched; the currency then takes a
   new one.
7. A person takes them the same way, per currency, as a bank account.
8. An archived account takes no opening balance: the seed route is `422` `ACCOUNT_ARCHIVED` on
   `currency_code`, and an edit sending any `opening_balances` (a set, a change or a clear)
   is `422` `ACCOUNT_ARCHIVED` on every `opening_balances.<code>` it names, whatever the
   entries say; nothing is written, and unarchived the same edit goes through.

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from tests.contract.conftest import (
    all_accounts,
    assert_refusal,
    assert_refusals,
    refused,
    refused_keeping,
    refused_writing_nothing,
    transaction_count,
)

DAY = "2026-01-01"


def _ids(client, account_id: str) -> dict[str, str | None]:
    """Each currency's `opening_balance_transaction_id` as the account's entries read it."""
    held = client.get(f"/accounts/{account_id}")["currencies"]
    return {entry["currency_code"]: entry["opening_balance_transaction_id"] for entry in held}


def _no_currency(scratch) -> dict:
    """A seed body that names no `currency_code`."""
    body = scratch.opening_balance_body(DAY, amount_cents=1000)
    del body["currency_code"]
    return body


def _post_new_seed(client, scratch, account_id: str, currency: str):
    """Posts an opening balance of `currency` under a fresh transaction id."""
    body = scratch.opening_balance_body(DAY, currency, 1000)
    return _post_seed(client, account_id, body)


def _post_seed(client, account_id: str, body: dict):
    return client.post(f"/accounts/{account_id}/opening-balance", json_body=body)


def test_opening_balance_lifecycle(client, scratch):
    account_id = scratch.account("PEN", "USD")
    other_account_id = scratch.account()

    # 1 — none yet in either currency, then only the seeded currency names the one just made.
    assert _ids(client, account_id) == {"PEN": None, "USD": None}
    scratch.opening_balance(account_id, DAY, "PEN", 150000)
    tx_id = _ids(client, account_id)["PEN"]
    assert tx_id == scratch.transactions[-1]  # the seed is the client-minted `transaction_id`
    assert _ids(client, account_id)["USD"] is None
    seeded = client.get(f"/transactions/{tx_id}")
    assert (seeded["account_id"], seeded["currency_code"]) == (account_id, "PEN")
    opening_category_id = seeded["category_id"]
    assert client.get(f"/categories/{opening_category_id}")["system_key"] == "opening_balance"
    listed = client.get("/accounts")
    row = next(a for a in listed["items"] if a["id"] == account_id)
    assert {e["currency_code"]: e["opening_balance_transaction_id"] for e in row["currencies"]} == {
        "PEN": tx_id,
        "USD": None,
    }

    # 2 — amount and date stay editable; the entry names the same row.
    edited = client.put(
        f"/transactions/{tx_id}",
        json_body={"amount_cents": -2500, "date": "2026-01-03T00:00:00Z"},
    )
    assert edited["id"] == tx_id
    assert edited["currency_code"] == "PEN"
    assert edited["amount_cents"] == 2500
    assert edited["transaction_type"] == 1
    assert edited["date"].startswith("2026-01-03")
    assert _ids(client, account_id)["PEN"] == tx_id

    # 3 — it never changes account or currency and never leaves @Opening.
    err = refused(
        lambda: client.put(f"/transactions/{tx_id}", json_body={"account_id": other_account_id})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "OPENING_BALANCE_ACCOUNT_FIXED")

    err = refused(lambda: client.put(f"/transactions/{tx_id}", json_body={"currency_code": "USD"}))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "OPENING_BALANCE_ACCOUNT_FIXED")

    pendiente_id = scratch.row(other_account_id, "2026-01-02")["category_id"]
    assert client.get(f"/categories/{pendiente_id}")["system_key"] == "pending"
    err = refused(
        lambda: client.put(f"/transactions/{tx_id}", json_body={"category_id": pendiente_id})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "category_id", "OPENING_BALANCE_CATEGORY_FIXED")

    err = refused(
        lambda: client.put(
            f"/transactions/{tx_id}",
            json_body={
                "account_id": other_account_id,
                "currency_code": "USD",
                "category_id": pendiente_id,
            },
        )
    )
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "account_id": "OPENING_BALANCE_ACCOUNT_FIXED",
            "currency_code": "OPENING_BALANCE_ACCOUNT_FIXED",
            "category_id": "OPENING_BALANCE_CATEGORY_FIXED",
        },
    )

    unchanged = client.get(f"/transactions/{tx_id}")
    assert (unchanged["account_id"], unchanged["currency_code"]) == (account_id, "PEN")
    assert unchanged["category_id"] == opening_category_id

    # Resending what it already has is not a move.
    resent = client.put(
        f"/transactions/{tx_id}",
        json_body={
            "account_id": account_id,
            "currency_code": "PEN",
            "category_id": opening_category_id,
        },
    )
    assert (resent["account_id"], resent["currency_code"]) == (account_id, "PEN")
    assert resent["category_id"] == opening_category_id


def test_a_seed_names_a_currency_the_account_holds(client, scratch):
    """The currency is required, supported and held, each refused on `currency_code`, and
    nothing is written (contract: POST /v1/accounts/{account_id}/opening-balance,
    "Validation")."""
    account_id = scratch.account("PEN")

    err = refused(lambda: _post_seed(client, account_id, _no_currency(scratch)))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "REQUIRED")

    for unsupported in ("usd", "EUR"):
        err = refused(lambda u=unsupported: _post_new_seed(client, scratch, account_id, u))
        assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "UNSUPPORTED_VALUE")

    err = refused(lambda: _post_new_seed(client, scratch, account_id, "USD"))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "CURRENCY_NOT_HELD")

    assert _ids(client, account_id) == {"PEN": None}
    assert client.get("/transactions/count", params={"account_id": account_id}) == {"count": 0}


def test_one_opening_balance_per_currency_and_each_named_by_its_own_entry(client, scratch):
    """A second seed in one currency is `409` `OPENING_BALANCE_EXISTS` on `account_id`
    while the account's other currency takes its own; each entry names its own seed, and a
    deleted one frees only its currency (contract: POST /v1/accounts/{account_id}/opening-balance,
    "Validation")."""
    account_id = scratch.account("PEN", "USD")
    scratch.opening_balance(account_id, DAY, "PEN")

    err = refused(lambda: _post_new_seed(client, scratch, account_id, "PEN"))
    assert_refusal(err, 409, "CONFLICT", "account_id", "OPENING_BALANCE_EXISTS")

    scratch.opening_balance(account_id, DAY, "USD", -7000)
    ids = _ids(client, account_id)
    assert ids["PEN"] is not None and ids["USD"] is not None and ids["PEN"] != ids["USD"]
    for code, tx_id in ids.items():
        assert client.get(f"/transactions/{tx_id}")["currency_code"] == code

    err = refused(lambda: _post_new_seed(client, scratch, account_id, "USD"))
    assert_refusal(err, 409, "CONFLICT", "account_id", "OPENING_BALANCE_EXISTS")
    assert _ids(client, account_id) == ids

    # Deleted, the currency's entry is null, the other's is untouched, and it takes a new one.
    client.delete(f"/transactions/{ids['PEN']}")
    assert _ids(client, account_id) == {"PEN": None, "USD": ids["USD"]}
    scratch.opening_balance(account_id, DAY, "PEN")
    renewed = _ids(client, account_id)
    assert renewed["PEN"] not in (None, ids["PEN"])
    assert renewed["USD"] == ids["USD"]


def test_a_person_takes_one_opening_balance_per_currency(client, scratch, statuses):
    person_id = scratch.account("PEN", "USD", person=True)
    created = client.get(f"/accounts/{person_id}")
    assert created["kind"] == "person"
    assert _ids(client, person_id) == {"PEN": None, "USD": None}

    scratch.opening_balance(person_id, DAY, "PEN", -42000)
    assert statuses[-1] == 201
    tx_id = _ids(client, person_id)["PEN"]
    assert tx_id == scratch.transactions[-1]
    seeded = client.get(f"/transactions/{tx_id}")
    assert (seeded["account_id"], seeded["currency_code"]) == (person_id, "PEN")
    assert client.get(f"/categories/{seeded['category_id']}")["system_key"] == "opening_balance"

    err = refused(lambda: _post_new_seed(client, scratch, person_id, "PEN"))
    assert_refusal(err, 409, "CONFLICT", "account_id", "OPENING_BALANCE_EXISTS")
    assert _ids(client, person_id) == {"PEN": tx_id, "USD": None}

    scratch.opening_balance(person_id, DAY, "USD")
    assert _ids(client, person_id)["USD"] not in (None, tx_id)


def test_an_archived_account_takes_no_opening_balance(client, scratch):
    """On an archived bank account and an archived person, each holding soles with an
    opening balance and dollars with none, a seed in either currency is `422`
    `ACCOUNT_ARCHIVED` on `currency_code` (the soles one would be `OPENING_BALANCE_EXISTS`
    later), and an edit with `opening_balances` for both, a change and a set, or a clear
    beside it, is `422` `ACCOUNT_ARCHIVED` on `opening_balances.PEN` and `opening_balances.USD`,
    the account's own colour unsaved. Every account and the account's transaction count read the
    same after each refusal; unarchived, the edit changes the soles and sets the dollars
    (contract: POST /v1/accounts/{account_id}/opening-balance, "Validation")
    (contract: PUT /v1/accounts/{account_id}, "Refusals")."""
    for person in (False, True):
        account_id = scratch.account("PEN", "USD", person=person)
        scratch.opening_balance(account_id, DAY, "PEN", 1000)
        scratch.archive(account_id)
        _archived_refusals_then_unarchived(client, scratch, account_id)


def _archived_refusals_then_unarchived(client, scratch, account_id: str) -> None:
    held = transaction_count(client, account_id)
    path = f"/accounts/{account_id}"

    for currency in ("PEN", "USD"):
        body = scratch.opening_balance_body(DAY, currency, 2000)
        scratch.transactions.append(body["transaction_id"])
        err = refused_writing_nothing(client, lambda b=body: _post_seed(client, account_id, b))
        assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "ACCOUNT_ARCHIVED")

    new_seed = scratch.opening_balance_body(DAY, "USD", 3000)
    del new_seed["currency_code"]
    scratch.transactions.append(new_seed["transaction_id"])
    sets_and_changes = {"PEN": {"amount_cents": 7000}, "USD": new_seed}
    reasons = dict.fromkeys(("opening_balances.PEN", "opening_balances.USD"), "ACCOUNT_ARCHIVED")
    for entries in (sets_and_changes, {"PEN": None, "USD": None}):
        sent = {"color": "#00aa00", "opening_balances": entries}
        err = refused_keeping(
            lambda: (all_accounts(client), transaction_count(client, account_id)),
            lambda sent=sent: client.put(path, json_body=sent),
        )
        assert_refusals(err, 422, "VALIDATION_ERROR", reasons)
    assert transaction_count(client, account_id) == held

    client.post(f"{path}/unarchive")
    edited = client.put(path, json_body={"opening_balances": sets_and_changes})
    assert _ids(client, account_id)["USD"] == new_seed["transaction_id"]
    assert edited["currencies"][0]["current_balance_cents"] == 7000
