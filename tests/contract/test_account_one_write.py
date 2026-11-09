"""Contract: an account and its opening balances save in one write, whole or not at all, against
a real engine.

The account form sends the account with every opening balance in one `POST /accounts`, and an
edit with the changed fields and the opening balances in one `PUT /accounts/{id}`; only the engine
can say that a refused entry leaves nothing behind and which key it lands on.

What it pins:

1. A create of two currencies with an opening balance each is `201` in one request, each
   currency's balance the opening's signed amount and its `opening_balance_transaction_id` the
   one sent (contract: POST /v1/accounts).
2. A refused opening leaves no account: a future date on `currencies.1.opening_balance.date`, a
   zero amount and a future date together, a transaction id sent twice on the later entry, and a
   taken one `409`; a list read shows no such account (contract: POST /v1/accounts, "Validation").
3. An edit setting one currency's opening balance, changing another's and clearing a third's is
   one `200` that writes all three and the account's colour
   (contract: PUT /v1/accounts/{account_id}).
4. An edit with an entry refused after another was valid writes nothing: the account's `version`,
   its colour and every opening balance read the same; a clear of a currency with no opening
   balance is `NO_OPENING_BALANCE` on `opening_balances.<code>` and a future date on
   `opening_balances.<code>.date` (contract: PUT /v1/accounts/{account_id}, "Refusals").

Every account is fresh per run and removed by the `scratch` fixture.
Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from datetime import datetime, timedelta

from tests.contract.conftest import (
    account_body,
    all_accounts,
    assert_refusal,
    assert_refusals,
    read_signed,
    refused_writing_nothing,
)

DAY = "2026-01-01"


def _opening(scratch, amount_cents: int, day: str = DAY) -> dict:
    """An opening balance of `amount_cents` as the engine's create and edit take it, without a
    currency; its transaction id joins the scratch for cleanup."""
    body = scratch.opening_balance_body(day, amount_cents=amount_cents)
    del body["currency_code"]
    scratch.transactions.append(body["transaction_id"])
    return body


def _future(scratch) -> str:
    return scratch.noon((datetime.now(scratch.zone).date() + timedelta(days=3)).isoformat())


def _post(client, scratch, body: dict):
    scratch.accounts.append(body["id"])
    return client.post("/accounts", json_body=body)


def _absent(client, account_id: str) -> bool:
    return account_id not in {a["id"] for a in all_accounts(client)}


def test_an_account_with_two_currencies_and_two_openings_is_created_in_one_write(client, scratch):
    """(contract: POST /v1/accounts)"""
    soles, dollars = _opening(scratch, 50000), _opening(scratch, -4550)
    body = account_body()
    body["currencies"] = [
        {"currency_code": "PEN", "opening_balance": soles},
        {"currency_code": "USD", "opening_balance": dollars},
    ]
    made = _post(client, scratch, body)
    assert [
        (c["currency_code"], c["current_balance_cents"], c["opening_balance_transaction_id"])
        for c in made["currencies"]
    ] == [
        ("PEN", 50000, soles["transaction_id"]),
        ("USD", -4550, dollars["transaction_id"]),
    ]
    assert client.get(f"/accounts/{body['id']}") == made
    assert made["version"] == 1


def test_a_refused_opening_leaves_no_account(client, scratch):
    """Each refusal is keyed on its entry's field and a list read shows no such account
    (contract: POST /v1/accounts, "Validation")."""
    fine = _opening(scratch, 50000)

    def body_with(second: dict, first: dict = fine) -> dict:
        body = account_body()
        body["currencies"] = [
            {"currency_code": "PEN", "opening_balance": first},
            {"currency_code": "USD", "opening_balance": second},
        ]
        return body

    cases = {
        "currencies.1.opening_balance.date": (
            {**_opening(scratch, 100), "date": _future(scratch)},
            {"currencies.1.opening_balance.date": "FUTURE_DATE"},
        ),
        "zero and future": (
            {**_opening(scratch, 0), "date": _future(scratch)},
            {
                "currencies.1.opening_balance.amount_cents": "ZERO_AMOUNT",
                "currencies.1.opening_balance.date": "FUTURE_DATE",
            },
        ),
        "twice": (
            {**_opening(scratch, 100), "transaction_id": fine["transaction_id"]},
            {"currencies.1.opening_balance.transaction_id": "DUPLICATE_IN_REQUEST"},
        ),
    }
    for what, (second, reasons) in cases.items():
        body = body_with(second)
        scratch.accounts.append(body["id"])
        err = refused_writing_nothing(client, lambda b=body: client.post("/accounts", json_body=b))
        assert_refusals(err, 422, "VALIDATION_ERROR", reasons)
        assert _absent(client, body["id"]), what

    held = _post(client, scratch, body_with(_opening(scratch, 100)))
    held_id = held["currencies"][0]["opening_balance_transaction_id"]
    taken = body_with(
        {**_opening(scratch, 100), "transaction_id": held_id}, first=_opening(scratch, 100)
    )
    scratch.accounts.append(taken["id"])
    err = refused_writing_nothing(client, lambda: client.post("/accounts", json_body=taken))
    assert (err.status, err.code) == (409, "CONFLICT")
    assert err.reasons == {"currencies.1.opening_balance.transaction_id": "ID_EXISTS"}
    assert _absent(client, taken["id"])


def _edit_fixture(client, scratch) -> tuple[str, str]:
    """A soles and dollars account with an opening balance in soles (1000) and none in dollars;
    its id and the soles opening balance's transaction id."""
    account_id = scratch.account("PEN", "USD")
    scratch.opening_balance(account_id, DAY, "PEN", 1000)
    held = client.get(f"/accounts/{account_id}")["currencies"]
    ids = {c["currency_code"]: c["opening_balance_transaction_id"] for c in held}
    assert ids["USD"] is None
    return account_id, ids["PEN"]


def test_an_edit_sets_changes_and_clears_openings_in_one_write(client, scratch):
    """The practice engine supports two currencies, so the three kinds of entry go in two
    edits: a change of soles with a set of dollars, then a clear of soles with a change of
    dollars, each landing together with the colour, `version` moving once
    (contract: PUT /v1/accounts/{account_id})."""
    account_id, soles_id = _edit_fixture(client, scratch)
    path = f"/accounts/{account_id}"
    before = client.get(path)
    dollars = _opening(scratch, 3000)
    edited = client.put(
        path,
        json_body={
            "color": "#00aa00",
            "opening_balances": {"PEN": {"amount_cents": 7000}, "USD": dollars},
        },
    )
    by_code = {c["currency_code"]: c for c in edited["currencies"]}
    assert by_code["PEN"]["opening_balance_transaction_id"] == soles_id
    assert by_code["PEN"]["current_balance_cents"] == 7000
    assert by_code["USD"]["opening_balance_transaction_id"] == dollars["transaction_id"]
    assert by_code["USD"]["current_balance_cents"] == 3000
    assert (edited["color"], edited["version"]) == ("#00aa00", before["version"] + 1)
    assert client.get(path) == edited

    again = client.put(
        path,
        json_body={
            "color": "#aa0000",
            "opening_balances": {"PEN": None, "USD": {"amount_cents": 4000}},
        },
    )
    by_code = {c["currency_code"]: c for c in again["currencies"]}
    assert by_code["PEN"]["opening_balance_transaction_id"] is None
    assert by_code["PEN"]["current_balance_cents"] == 0
    assert by_code["USD"]["opening_balance_transaction_id"] == dollars["transaction_id"]
    assert by_code["USD"]["current_balance_cents"] == 4000
    assert (again["color"], again["version"]) == ("#aa0000", edited["version"] + 1)


def test_a_refused_entry_of_the_edit_writes_nothing(client, scratch):
    """The soles change is valid and first in code order, the dollars set is refused after it:
    the soles opening, the colour and the version read as before. A clear of dollars, which have
    no opening balance, is `NO_OPENING_BALANCE` on `opening_balances.USD`
    (contract: PUT /v1/accounts/{account_id}, "Refusals")."""
    account_id, soles_id = _edit_fixture(client, scratch)
    path = f"/accounts/{account_id}"
    before = client.get(path)
    opening = read_signed(client, soles_id)

    late = {**_opening(scratch, 9999), "date": _future(scratch)}
    refusals = (
        ({"PEN": {"amount_cents": 9000}, "USD": late}, "opening_balances.USD.date", "FUTURE_DATE"),
        (
            {"PEN": {"amount_cents": 9000}, "USD": None},
            "opening_balances.USD",
            "NO_OPENING_BALANCE",
        ),
    )
    for entries, key, reason in refusals:
        sent = {"color": "#00aa00", "opening_balances": entries}
        err = refused_writing_nothing(client, lambda s=sent: client.put(path, json_body=s))
        assert_refusal(err, 422, "VALIDATION_ERROR", key, reason)
        assert client.get(path) == before
        assert read_signed(client, soles_id) == opening
