"""Contract lifecycle for a person against a real engine.

**This is the only check that can see this feature at all.** The fast suite mocks the engine
with recorded fixtures, and a recorded fixture cannot grow a rule that did not exist when it
was written; `scripts/check_fixture_drift.py` is blind here too, since it only reports fields
the engine has *stopped* serving. Unit-green therefore says nothing about whether a person
works — this file does.

A person is an account with `kind: "person"`, held in one or more currencies and made in one
`POST /accounts` (contract: POST /v1/accounts, "Optional"). What it pins, in the order the
client meets it:

1. A person made with two currencies in one write reads `kind` `person`, a balance of `0`
   and no opening balance in each.
2. `kind` is required (`422` `REQUIRED`), and `is_person`, the field it replaced, is
   `422` `UNKNOWN_FIELD` whatever its value.
3. The name is **shared** with bank accounts, case-insensitively, in both directions (`409`
   `NAME_EXISTS` on `name`), not scoped per kind.
4. A person takes an opening balance in each of its currencies like any account; a second one
   in the same currency is `OPENING_BALANCE_EXISTS`
   (contract: POST /v1/accounts/{account_id}/opening-balance).
5. Everything after creation is an *account* route: `GET`, `PUT`, `/archive`, `/unarchive`,
   `DELETE` all accept the person. No route is named for people.
6. She is listed by `GET /accounts?include_people=true`, appears in the dashboard's `people`
   panel with a row holding every currency, and moves to `archived_people` — a panel distinct
   from `archived_accounts` — when archived.
7. That list has every bank account before every person.

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

import pytest

from tests.contract.conftest import (
    account_body,
    assert_refusal,
    refused_writing_nothing,
)


def _names(rows) -> set[str]:
    return {row.get("name") for row in rows or []}


def _currencies(account: dict) -> dict[str, tuple[int, str | None]]:
    return {
        c["currency_code"]: (c["current_balance_cents"], c["opening_balance_transaction_id"])
        for c in account["currencies"]
    }


def test_a_person_is_made_in_one_write_with_two_currencies(client, scratch, statuses):
    body = account_body("PEN", "USD", person=True)
    person_id = body["id"]
    scratch.accounts.append(person_id)
    created = client.post("/accounts", json_body=body)

    assert statuses[-1] == 201
    assert created["id"] == person_id
    assert created["kind"] == "person"
    assert created["is_archived"] is False
    assert _currencies(created) == {"PEN": (0, None), "USD": (0, None)}
    assert client.get(f"/accounts/{person_id}") == created


def test_kind_is_required_on_create(client, scratch):
    body = account_body("PEN")
    del body["kind"]
    scratch.accounts.append(body["id"])
    err = refused_writing_nothing(client, lambda: client.post("/accounts", json_body=body))
    assert_refusal(err, 422, "VALIDATION_ERROR", "kind", "REQUIRED")


@pytest.mark.parametrize("value", [True, False, None])
def test_is_person_is_no_field_of_create(client, scratch, value):
    body = account_body("PEN", person=True, is_person=value)
    scratch.accounts.append(body["id"])
    err = refused_writing_nothing(client, lambda: client.post("/accounts", json_body=body))
    assert_refusal(err, 422, "VALIDATION_ERROR", "is_person", "UNKNOWN_FIELD")


def test_a_persons_name_is_shared_with_people_and_bank_accounts(client, scratch):
    """One name list for both kinds, compared without regard to case: a person's name, new or
    by rename, is refused when a person or a bank account holds it. The other direction, a bank
    account whose built name a person holds, is test_account_create.py's."""
    person_id = scratch.account("PEN", person=True)
    account_id = scratch.account("PEN")
    person_name = client.get(f"/accounts/{person_id}")["name"]
    account_name = client.get(f"/accounts/{account_id}")["name"]

    for name in (person_name.swapcase(), account_name.swapcase()):
        body = account_body("PEN", person=True, name=name)
        scratch.accounts.append(body["id"])
        err = refused_writing_nothing(client, lambda b=body: client.post("/accounts", json_body=b))
        assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")

    err = refused_writing_nothing(
        client, lambda: client.put(f"/accounts/{person_id}", json_body={"name": account_name})
    )
    assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")


def test_a_person_takes_an_opening_balance_in_each_currency(client, scratch):
    """A person is judged by every rule a bank account is: each currency takes one opening
    balance, a second in the same currency is refused and the other currency still takes its
    own (contract: POST /v1/accounts/{account_id}/opening-balance, "Validation")."""
    person_id = scratch.account("PEN", "USD", person=True)
    scratch.opening_balance(person_id, "2026-01-01", "PEN", -10000)
    held = client.get(f"/accounts/{person_id}")
    pen = next(c for c in held["currencies"] if c["currency_code"] == "PEN")
    assert pen["current_balance_cents"] == -10000
    assert pen["opening_balance_transaction_id"] is not None

    err = refused_writing_nothing(
        client, lambda: scratch.opening_balance(person_id, "2026-01-02", "PEN", 500)
    )
    assert_refusal(err, 409, "CONFLICT", "account_id", "OPENING_BALANCE_EXISTS")

    scratch.opening_balance(person_id, "2026-01-01", "USD", 2500)
    both = _currencies(client.get(f"/accounts/{person_id}"))
    assert both["PEN"] == (-10000, pen["opening_balance_transaction_id"])
    assert both["USD"][0] == 2500 and both["USD"][1] is not None


def test_people_lifecycle(client, scratch):
    person_id = scratch.account("PEN", "USD", person=True)
    name = client.get(f"/accounts/{person_id}")["name"]

    # Everything after creation is an ordinary account route.
    renamed = client.put(f"/accounts/{person_id}", json_body={"name": f"{name}-renamed"})
    assert renamed["name"] == f"{name}-renamed"
    assert renamed["kind"] == "person"  # a rename never changes the kind
    assert client.get(f"/accounts/{person_id}") == renamed
    new_name = renamed["name"]

    # Where she shows up.
    listed = client.get("/accounts", params={"include_people": "true"})["items"]
    assert person_id in {row["id"] for row in listed}
    plain = client.get("/accounts")["items"]
    assert person_id not in {row["id"] for row in plain}

    dashboard = client.get("/dashboard", params={"include_archived": "true"})
    row = next(p for p in dashboard["people"] if p["id"] == person_id)
    assert [c["currency_code"] for c in row["currencies"]] == ["PEN", "USD"]
    assert new_name not in _names(dashboard["bank_accounts"])
    assert new_name not in _names(dashboard["archived_accounts"])

    # Archived, she moves to her own panel and the two archived panels never mix.
    scratch.archive(person_id)
    archived = client.get("/dashboard", params={"include_archived": "true"})
    assert new_name not in _names(archived["people"])
    shown = next(p for p in archived["archived_people"] if p["id"] == person_id)
    assert [c["currency_code"] for c in shown["currencies"]] == ["PEN", "USD"]
    assert new_name not in _names(archived["archived_accounts"])

    # Both archived panels are null, not omitted, without the flag.
    default_view = client.get("/dashboard")
    assert default_view["archived_people"] is None
    assert default_view["archived_accounts"] is None

    client.post(f"/accounts/{person_id}/unarchive")
    back = client.get("/dashboard", params={"include_archived": "true"})
    assert new_name in _names(back["people"])
    assert new_name not in _names(back["archived_people"])


def test_settled_person_is_returned_not_hidden(client, scratch):
    """A person whose debt clears stays in the `people` panel with balance 0 in each currency.

    The engine refuses to filter on a computed balance — folding settled people is a *client*
    display choice, and this test is what guarantees the client still receives the rows it
    folds. If the engine ever started hiding them, `▸ 3 settled` would quietly become
    `▸ 0 settled` and nobody would notice.
    """
    person_id = scratch.account("PEN", "USD", person=True)

    # Lend 200 in soles: an ordinary transaction against her. Her balance IS the debt.
    scratch.row(person_id, "2026-08-01", 20000, "PEN")
    owed = client.get(f"/accounts/{person_id}")
    assert _currencies(owed)["PEN"][0] == 20000

    # She pays it back. Zero is a balance, not a missing value.
    scratch.row(person_id, "2026-08-02", -20000, "PEN")
    settled = client.get(f"/accounts/{person_id}")
    assert _currencies(settled) == {"PEN": (0, None), "USD": (0, None)}

    panel = client.get("/dashboard")["people"]
    row = next((p for p in panel if p["id"] == person_id), None)
    assert row is not None, "a settled person must still be returned, not filtered out"
    assert row["currencies"] == [
        {"currency_code": "PEN", "current_balance_cents": 0},
        {"currency_code": "USD", "current_balance_cents": 0},
    ]


def test_the_list_with_people_has_every_account_before_every_person(client, scratch):
    """`GET /accounts?include_people=true` lists every bank account first, then every
    person, each group by `sort_order` ascending, then oldest first
    (contract: GET /v1/accounts, "Ordering"); the app shows that order as it comes.

    The person is created first and with `sort_order` 0, the account after it with a high
    `sort_order`, so a list ordered by either alone would put the person ahead of the
    account.
    """
    person_id = scratch.account("PEN", "USD", person=True, sort_order=0)
    account_id = scratch.account("PEN", "USD", sort_order=9999)
    rows = client.get("/accounts", params={"include_people": "true"})["items"]
    flags = [row["kind"] == "person" for row in rows]
    assert {row["id"] for row in rows} >= {person_id, account_id}
    assert True in flags and False in flags
    assert next(r for r in rows if r["id"] == person_id)["sort_order"] == 0
    assert next(r for r in rows if r["id"] == account_id)["sort_order"] == 9999
    last_account = max(i for i, is_person in enumerate(flags) if not is_person)
    first_person = min(i for i, is_person in enumerate(flags) if is_person)
    assert last_account < first_person
