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

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from uuid import uuid4

from tests.contract.conftest import assert_refusal, assert_refusals, refused

DAY = "2026-01-01"


def _ids(client, account_id: str) -> dict[str, str | None]:
    """Each currency's `opening_balance_transaction_id` as the account's entries read it."""
    held = client.get(f"/accounts/{account_id}")["currencies"]
    return {entry["currency_code"]: entry["opening_balance_transaction_id"] for entry in held}


def _seed_body(scratch, currency: str | None, **fields) -> dict:
    """An opening-balance body under a fresh transaction id, with `currency` named when given."""
    body = {"transaction_id": str(uuid4()), "amount_cents": 1000, "date": scratch.noon(DAY)}
    if currency is not None:
        body["currency_code"] = currency
    return {**body, **fields}


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

    err = refused(lambda: _post_seed(client, account_id, _seed_body(scratch, None)))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "REQUIRED")

    for unsupported in ("usd", "EUR"):
        body = _seed_body(scratch, unsupported)
        err = refused(lambda body=body: _post_seed(client, account_id, body))
        assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "UNSUPPORTED_VALUE")

    err = refused(lambda: _post_seed(client, account_id, _seed_body(scratch, "USD")))
    assert_refusal(err, 422, "VALIDATION_ERROR", "currency_code", "CURRENCY_NOT_HELD")
    assert err.fields["currency_code"] == "Must be a currency the account holds."

    assert _ids(client, account_id) == {"PEN": None}
    assert client.get("/transactions/count", params={"account_id": account_id}) == {"count": 0}


def test_one_opening_balance_per_currency_and_each_named_by_its_own_entry(client, scratch):
    """A second seed in one currency is `409` `OPENING_BALANCE_EXISTS` on `account_id`
    while the account's other currency takes its own; each entry names its own seed, and a
    deleted one frees only its currency (contract: POST /v1/accounts/{account_id}/opening-balance,
    "Validation")."""
    account_id = scratch.account("PEN", "USD")
    scratch.opening_balance(account_id, DAY, "PEN")

    err = refused(lambda: _post_seed(client, account_id, _seed_body(scratch, "PEN")))
    assert_refusal(err, 409, "CONFLICT", "account_id", "OPENING_BALANCE_EXISTS")

    scratch.opening_balance(account_id, DAY, "USD", -7000)
    ids = _ids(client, account_id)
    assert ids["PEN"] is not None and ids["USD"] is not None and ids["PEN"] != ids["USD"]
    for code, tx_id in ids.items():
        assert client.get(f"/transactions/{tx_id}")["currency_code"] == code

    err = refused(lambda: _post_seed(client, account_id, _seed_body(scratch, "USD")))
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
    assert created["is_person"] is True
    assert _ids(client, person_id) == {"PEN": None, "USD": None}

    scratch.opening_balance(person_id, DAY, "PEN", -42000)
    assert statuses[-1] == 201
    tx_id = _ids(client, person_id)["PEN"]
    assert tx_id == scratch.transactions[-1]
    seeded = client.get(f"/transactions/{tx_id}")
    assert (seeded["account_id"], seeded["currency_code"]) == (person_id, "PEN")
    assert client.get(f"/categories/{seeded['category_id']}")["system_key"] == "opening_balance"

    err = refused(lambda: _post_seed(client, person_id, _seed_body(scratch, "PEN")))
    assert_refusal(err, 409, "CONFLICT", "account_id", "OPENING_BALANCE_EXISTS")
    assert _ids(client, person_id) == {"PEN": tx_id, "USD": None}

    scratch.opening_balance(person_id, DAY, "USD")
    assert _ids(client, person_id)["USD"] not in (None, tx_id)
