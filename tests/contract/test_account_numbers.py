"""Contract: a bank account's bank and numbers over time, and the kind changes' bodies, against a
real engine.

The account forms send `bank_code`, `last4`, `current_number` and `new_number`, and the kind
changes send `make-person {name}` and `make-account {bank_code, last4?}`; only the engine can say
what name it builds, how a replacement ends the number before it and what it refuses.

What it pins:

1. `GET /banks` lists `{code, name}` items and includes `BCP` (contract: GET /v1/banks).
2. Every account read, the list and the one, carries `bank_code` and `numbers`; a bank account
   made with its `last4` is named `BCP-<last4>` with that one number; a person keeps its typed
   name, with no bank and no number
   (contract: POST /v1/accounts, "The name")
   (contract: "Bank Accounts", "Account response").
3. Numbers over time (contract: PUT /v1/accounts/{account_id}, "The numbers"): a `new_number`
   ends the number before it the day before its `start_date` and the name follows the new
   card; `current_number: null` makes the one before current again; each moves `version` once.
   `FIRST_NUMBER_HAS_NO_START` and `NUMBER_START_NOT_LATER` are refused on their keys, nothing
   written.
4. The kind changes' bodies (contract: POST /v1/accounts/{account_id}/make-person)
   (contract: POST /v1/accounts/{account_id}/make-account): `make-person {name}` drops the bank
   and the numbers; `make-account {bank_code, last4}` names the account `BCP-<last4>`; a `name`
   on `make-account` is `NAME_BUILT`, nothing written.

Every account is fresh per run (a bank account numbered from the suite's range) and removed by the
`scratch` fixture. Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from uuid import uuid4

from tests.contract.conftest import (
    account_body,
    assert_refusal,
    bank_code,
    next_last4,
    refused_writing_nothing,
)


def _bank_account(client, scratch, *, last4: str) -> str:
    """A soles bank account of the suite's bank, numbered `last4`; its id."""
    body = account_body(last4=last4)
    scratch.accounts.append(body["id"])
    client.post("/accounts", json_body=body)
    return body["id"]


def _numbers(account: dict) -> list[tuple[str, str | None, str | None]]:
    return [(n["last4"], n["start_date"], n["end_date"]) for n in account["numbers"]]


def _put(client, account_id: str, body: dict) -> dict:
    return client.put(f"/accounts/{account_id}", json_body=body)


def test_the_banks_read_lists_code_and_name_and_includes_bcp(client):
    """(contract: GET /v1/banks)"""
    items = client.get("/banks")["items"]
    assert items
    assert all(set(item) == {"code", "name"} for item in items)
    assert all(isinstance(item["code"], str) and isinstance(item["name"], str) for item in items)
    assert "BCP" in {item["code"] for item in items}


def test_every_account_read_carries_its_bank_and_numbers_and_the_name_is_built(client, scratch):
    """A bank account is `BCP-<last4>` with its one number, no start and no end; a person keeps
    its typed name, `bank_code` null and `numbers` empty; the list and the read agree
    (contract: POST /v1/accounts, "The name")
    (contract: "Bank Accounts", "Account response")."""
    last4 = next_last4()
    numbered = _bank_account(client, scratch, last4=last4)
    person = scratch.account(person=True)

    listed = {
        a["id"]: a for a in client.get("/accounts", params={"include_people": "true"})["items"]
    }
    for account_id in (numbered, person):
        read = client.get(f"/accounts/{account_id}")
        assert listed[account_id] == read
        assert "bank_code" in read and "numbers" in read

    read = client.get(f"/accounts/{numbered}")
    assert (read["name"], read["bank_code"]) == (f"{bank_code()}-{last4}", bank_code())
    assert _numbers(read) == [(last4, None, None)]

    read = client.get(f"/accounts/{person}")
    assert read["name"].startswith("contract-stmt-")
    assert (read["bank_code"], read["numbers"]) == (None, [])


def test_a_replacement_ends_the_old_number_the_day_before_and_a_removal_restores_it(
    client, scratch
):
    """`new_number` adds a current number from its `start_date`, the number it replaces ends the
    day before and the name follows the new card; `current_number: null` removes it, the one
    before is current again with no end; each write moves `version` once
    (contract: PUT /v1/accounts/{account_id}, "The numbers")."""
    first, second = next_last4(), next_last4()
    account_id = _bank_account(client, scratch, last4=first)
    version = client.get(f"/accounts/{account_id}")["version"]

    replaced = _put(
        client, account_id, {"new_number": {"last4": second, "start_date": "2026-04-10"}}
    )
    assert _numbers(replaced) == [(first, None, "2026-04-09"), (second, "2026-04-10", None)]
    assert replaced["name"] == f"{bank_code()}-{second}"
    assert replaced["version"] == version + 1
    assert client.get(f"/accounts/{account_id}") == replaced

    removed = _put(client, account_id, {"current_number": None})
    assert _numbers(removed) == [(first, None, None)]
    assert removed["name"] == f"{bank_code()}-{first}"
    assert removed["version"] == version + 2


def test_a_number_start_the_first_number_cannot_have_or_not_later_is_refused(client, scratch):
    """A start day for the first number is `FIRST_NUMBER_HAS_NO_START` on
    `current_number.start_date`; a replacement starting on the current number's start day is
    `NUMBER_START_NOT_LATER` on `new_number.start_date`, and a later number moved to the start of
    the one before it on `current_number.start_date`; each writes nothing
    (contract: PUT /v1/accounts/{account_id}, "The numbers")."""
    account_id = _bank_account(client, scratch, last4=next_last4())

    for body in (
        {"current_number": {"start_date": "2026-04-10"}},
        {"current_number": {"last4": next_last4(), "start_date": "2026-04-10"}},
    ):
        err = refused_writing_nothing(client, lambda b=body: _put(client, account_id, b))
        assert_refusal(
            err, 422, "VALIDATION_ERROR", "current_number.start_date", "FIRST_NUMBER_HAS_NO_START"
        )

    _put(client, account_id, {"new_number": {"last4": next_last4(), "start_date": "2026-04-10"}})
    again = {"new_number": {"last4": next_last4(), "start_date": "2026-04-10"}}
    err = refused_writing_nothing(client, lambda: _put(client, account_id, again))
    assert_refusal(err, 422, "VALIDATION_ERROR", "new_number.start_date", "NUMBER_START_NOT_LATER")

    _put(client, account_id, {"new_number": {"last4": next_last4(), "start_date": "2026-05-10"}})
    earlier = {"current_number": {"start_date": "2026-04-10"}}
    err = refused_writing_nothing(client, lambda: _put(client, account_id, earlier))
    assert_refusal(
        err, 422, "VALIDATION_ERROR", "current_number.start_date", "NUMBER_START_NOT_LATER"
    )


def test_the_kind_changes_take_the_bodies_the_contract_names(client, scratch):
    """`make-person {name}` makes the typed name the account's and drops the bank and the
    numbers; `make-account {bank_code, last4}` names it `BCP-<last4>` with that one
    number; a `name` on `make-account` is `NAME_BUILT` on `name`, writing nothing
    (contract: POST /v1/accounts/{account_id}/make-person)
    (contract: POST /v1/accounts/{account_id}/make-account)."""
    account_id = _bank_account(client, scratch, last4=next_last4())
    typed = f"contract-kind-{uuid4().hex[:8]}"

    person = client.post(f"/accounts/{account_id}/make-person", json_body={"name": typed})
    assert (person["kind"], person["name"]) == ("person", typed)
    assert (person["bank_code"], person["numbers"]) == (None, [])

    err = refused_writing_nothing(
        client,
        lambda: client.post(
            f"/accounts/{account_id}/make-account",
            json_body={"bank_code": bank_code(), "last4": next_last4(), "name": typed},
        ),
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "name", "NAME_BUILT")

    last4 = next_last4()
    numbered = client.post(
        f"/accounts/{account_id}/make-account",
        json_body={"bank_code": bank_code(), "last4": last4},
    )
    assert (numbered["kind"], numbered["bank_code"]) == ("bank", bank_code())
    assert numbered["name"] == f"{bank_code()}-{last4}"
    assert _numbers(numbered) == [(last4, None, None)]
    assert client.get(f"/accounts/{account_id}") == numbered
