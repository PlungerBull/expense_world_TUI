"""Contract lifecycle for the three named resources.

Accounts: create → update → archive → unarchive → delete, an account being one record
holding its currencies.
Categories and hashtags: create → update → delete — they have no
archive routes, and accounts (people included) are the only archivable
resource.

Every lifecycle ends on "deleted is deleted": the row leaves
every list, its get is a 404, and there is no `restore`.

An archived account's transactions are frozen except for their categorisation
(contract: POST /v1/accounts/{account_id}/archive): a `PUT` of `category_id`,
`hashtag_ids` or `description` goes through; any other field is `422`
`ACCOUNT_ARCHIVED` on its key, at its current value too, and a mixed `PUT` writes
nothing; an empty `title` or `operation_code` is filled once; a delete, of a
transaction or of a bank line, is `409`, and a whole-line write that adds or drops a
part is `422` on `parts` and one that changes a kept part's amount on its
`parts.<i>.amount_cents`, beside every line field sent, all `ACCOUNT_ARCHIVED`; after
unarchiving, a frozen field, a rewrite of a line's parts and both deletes go through.
What the whole-line write takes on such a line is in test_bank_line_edit_limits.py. Moving
another account's row onto it stays `INVALID_REFERENCE`. Its statements'
freeze is in test_statements_lifecycle.py.

Not pinned here: a line field sent on an active account's transaction refused
because another part of its line sits on an archived account. Every part of a line
shares its account: a part the whole-line write creates takes the line's account, a batch
`line_group` must share it, and `PUT` of `account_id` writes it onto every part
(contract: "Transactions (Ledger)", "Bank lines"), so no route builds such a line.
It comes only from a manual database repair outside the engine, so no client test
can build one; the refusal is a safety check for that case.

An account or a category created with no `color` comes back with the engine's
default colour.

Hits a real engine. Gating, target resolution and the real-ledger guard live in
conftest.py; uses ExpenseClient directly so each test owns its idempotency keys.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from expense.errors import EngineError
from tests.contract.conftest import (
    account_body,
    assert_refusal,
    assert_refusals,
    read_signed,
    refused,
    replace_parts,
)


def _list_all(client, resource: str, **flags) -> list[dict]:
    """The whole collection, in one read.

    The engine returns accounts, categories and hashtags whole
    as `{items}` and refuses `limit`/`offset` with a 422 — so this also pins
    that a plain read is the entire list, not a default page.
    """
    params = {flag: "true" for flag, on in flags.items() if on}
    body = client.get(f"/{resource}", params=params or None)
    assert set(body) == {"items"}, f"/{resource} is no longer the whole-list shape: {sorted(body)}"
    return body["items"]


def _assert_gone(client, resource: str, row_id: str) -> None:
    """A deleted row is invisible: absent from the list, 404 on get and restore."""
    assert not any(r["id"] == row_id for r in _list_all(client, resource))
    with pytest.raises(EngineError) as got:
        client.get(f"/{resource}/{row_id}")
    assert got.value.status == 404
    with pytest.raises(EngineError) as restored:
        client.post(f"/{resource}/{row_id}/restore")
    assert restored.value.status == 404


def test_accounts_lifecycle(client, scratch):
    body = account_body("USD")
    new_id, name = body["id"], body["name"]
    scratch.accounts.append(new_id)
    created = client.post("/accounts", json_body=body)
    assert created["id"] == new_id
    assert created["name"] == name
    assert client.get(f"/accounts/{new_id}")["id"] == new_id
    assert [entry["currency_code"] for entry in created["currencies"]] == ["USD"]

    updated = client.put(f"/accounts/{new_id}", json_body={"name": f"{name}-renamed"})
    assert updated["name"] == f"{name}-renamed"
    assert [entry["currency_code"] for entry in updated["currencies"]] == ["USD"]

    assert any(a["id"] == new_id for a in _list_all(client, "accounts"))

    scratch.archive(new_id)
    assert not any(a["id"] == new_id for a in _list_all(client, "accounts"))
    archived = _list_all(client, "accounts", include_archived=True)
    assert any(a["id"] == new_id for a in archived)

    client.post(f"/accounts/{new_id}/unarchive")
    client.delete(f"/accounts/{new_id}")
    _assert_gone(client, "accounts", new_id)


def test_categories_lifecycle(client, scratch):
    new_id = scratch.category()
    name = client.get(f"/categories/{new_id}")["name"]

    updated = client.put(f"/categories/{new_id}", json_body={"name": f"{name}-renamed"})
    assert updated["name"] == f"{name}-renamed"

    # No archive/unarchive arm: those routes 404. Pin the
    # deletion so a silent re-introduction would be caught.
    assert any(c["id"] == new_id for c in _list_all(client, "categories"))

    client.delete(f"/categories/{new_id}")
    _assert_gone(client, "categories", new_id)


def test_hashtags_lifecycle(client, scratch):
    new_id = scratch.hashtag()
    name = client.get(f"/hashtags/{new_id}")["name"]

    updated = client.put(f"/hashtags/{new_id}", json_body={"name": f"{name}-renamed"})
    assert updated["name"] == f"{name}-renamed"

    # Same as categories — no archive routes.
    assert any(h["id"] == new_id for h in _list_all(client, "hashtags"))

    client.delete(f"/hashtags/{new_id}")
    _assert_gone(client, "hashtags", new_id)


#: A day the archived tests' rows sit on, in the past.
DAY = "2026-03-10"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _archive(client, scratch, account_id: str) -> None:
    """Archives the account (`scratch` unarchives it at cleanup, so its rows and statements can
    be deleted; contract: "Bank Accounts", "An archived account")."""
    scratch.archive(account_id)
    assert client.get(f"/accounts/{account_id}")["is_archived"] is True


def _split(client, scratch, tx_id: str, amounts: list[int]) -> list[dict]:
    """Rewrite the line holding `tx_id` into new parts of `amounts` (conftest.py
    `replace_parts`); every part id is kept before the write, so cleanup reaches whatever
    the engine created."""
    line_id = client.get(f"/transactions/{tx_id}")["bank_line_id"]
    return replace_parts(client, line_id, amounts, scratch.transactions)


#: The fields an archived account's transaction refuses, even at their current value
#: (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts").
FROZEN = (
    "amount_cents",
    "date",
    "title",
    "operation_code",
    "account_id",
    "currency_code",
    "statement_id",
)


def test_an_archived_accounts_transaction_takes_only_its_categorisation(client, scratch):
    """On a transaction whose account is archived, a `PUT` of `category_id`, of
    `hashtag_ids` and of `description` each go through. A `PUT` of any field in
    `FROZEN` is `422` `ACCOUNT_ARCHIVED` on that key, at a new value and at its current
    one, and writes nothing (contract: PUT /v1/transactions/{transaction_id}, "The
    refusal is on keys, not changed values")."""
    account_id = scratch.account()
    elsewhere = scratch.account()
    category_id = scratch.category()
    hashtag_id = scratch.hashtag()
    tx_id = scratch.row(
        account_id, DAY, title="archived-row", operation_code=f"OP-{uuid4().hex[:8]}"
    )["id"]
    draft_id = scratch.statement(account_id, "2026-04-01", "2026-04-30")["id"]
    _archive(client, scratch, account_id)

    path = f"/transactions/{tx_id}"
    assert client.put(path, json_body={"category_id": category_id})["category_id"] == category_id
    assert client.put(path, json_body={"hashtag_ids": [hashtag_id]})["hashtag_ids"] == [hashtag_id]
    assert client.put(path, json_body={"description": "a note"})["description"] == "a note"

    current = read_signed(client, tx_id)
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    changed = {
        "amount_cents": -2000,
        "date": yesterday,
        "title": "renamed",
        "operation_code": f"OP-{uuid4().hex[:8]}",
        "account_id": elsewhere,
        "currency_code": "USD",
        "statement_id": draft_id,
    }
    for key in FROZEN:
        for value in (changed[key], current[key]):
            err = refused(lambda key=key, value=value: client.put(path, json_body={key: value}))
            assert_refusal(err, 422, "VALIDATION_ERROR", key, "ACCOUNT_ARCHIVED")
    assert read_signed(client, tx_id) == current  # nothing written, `version` included


def test_a_mixed_put_on_an_archived_accounts_transaction_writes_nothing(client, scratch):
    """A `PUT` sending categorisation beside frozen fields names only the frozen keys,
    and writes none of it: the categorisation stays as it was and `version` does not
    move (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts")."""
    account_id = scratch.account()
    category_id = scratch.category()
    tx_id = scratch.row(account_id, DAY, title="archived-row")["id"]
    _archive(client, scratch, account_id)
    before = read_signed(client, tx_id)

    err = refused(
        lambda: client.put(
            f"/transactions/{tx_id}",
            json_body={
                "category_id": category_id,
                "description": "never written",
                "amount_cents": before["amount_cents"],
                "title": "renamed",
            },
        )
    )
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {"amount_cents": "ACCOUNT_ARCHIVED", "title": "ACCOUNT_ARCHIVED"},
    )
    assert read_signed(client, tx_id) == before


def test_an_archived_accounts_empty_title_is_filled_once(client, scratch):
    """A title that is still `null` may be filled on an archived account's transaction;
    once set, changing or clearing it is `422` `ACCOUNT_ARCHIVED` on `title`
    (contract: PUT /v1/transactions/{transaction_id}, "An empty field may be filled")."""
    account_id = scratch.account()
    tx_id = scratch.row(account_id, DAY)["id"]
    _archive(client, scratch, account_id)
    assert client.get(f"/transactions/{tx_id}")["title"] is None

    filled = client.put(f"/transactions/{tx_id}", json_body={"title": "filled once"})
    assert filled["title"] == "filled once"
    before = read_signed(client, tx_id)
    for value in ("changed", None):
        err = refused(
            lambda value=value: client.put(f"/transactions/{tx_id}", json_body={"title": value})
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "title", "ACCOUNT_ARCHIVED")
    assert read_signed(client, tx_id) == before


def test_an_archived_accounts_empty_operation_code_is_filled_once(client, scratch):
    """An `operation_code` that is still `null` may be filled on an archived account's
    transaction; once set, changing or clearing it is `422` `ACCOUNT_ARCHIVED` on
    `operation_code`
    (contract: PUT /v1/transactions/{transaction_id}, "An empty field may be filled")."""
    account_id = scratch.account()
    tx_id = scratch.row(account_id, DAY, title="archived-row")["id"]
    _archive(client, scratch, account_id)
    assert client.get(f"/transactions/{tx_id}")["operation_code"] is None

    code = f"OP-{uuid4().hex[:8]}"
    filled = client.put(f"/transactions/{tx_id}", json_body={"operation_code": code})
    assert filled["operation_code"] == code
    before = read_signed(client, tx_id)
    for value in (f"OP-{uuid4().hex[:8]}", None):
        err = refused(
            lambda value=value: client.put(
                f"/transactions/{tx_id}", json_body={"operation_code": value}
            )
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "operation_code", "ACCOUNT_ARCHIVED")
    assert read_signed(client, tx_id) == before


def test_an_archived_accounts_rows_are_neither_split_nor_deleted_until_unarchived(client, scratch):
    """On an archived account, `DELETE /transactions/{id}` is `409` on `transaction_id`
    and `DELETE /bank-lines/{id}` `409` on `bank_line_id`, a split line's part and the
    line included; a whole-line write that replaces a line's part is `422` on `parts`,
    and one that changes kept parts' amounts on each `parts.<i>.amount_cents`, beside
    every line field sent; all `ACCOUNT_ARCHIVED`, and the balance and every row stay as
    they were
    (contract: "Bank Accounts", "An archived account")
    (contract: PUT /v1/bank-lines/{bank_line_id},
    "A line with a part on an archived account keeps its parts and their amounts").
    After `POST /accounts/{id}/unarchive` a frozen field, a rewrite of a line's parts
    and both deletes go through (contract: POST /v1/accounts/{account_id}/unarchive)."""
    account_id = scratch.account()
    single = scratch.row(account_id, DAY, title="single")["id"]
    parts = _split(client, scratch, scratch.row(account_id, DAY, title="split")["id"], [-600, -400])
    single_line = client.get(f"/transactions/{single}")["bank_line_id"]
    split_line = parts[0]["bank_line_id"]
    _archive(client, scratch, account_id)

    def ledger() -> tuple[list[dict], list[dict]]:
        balance = client.get(f"/accounts/{account_id}")["currencies"]
        listed = client.get(
            "/transactions", params={"account_id": account_id, "debit_as_negative": "true"}
        )
        return balance, sorted(listed["items"], key=lambda t: t["id"])

    before = ledger()
    assert len(before[1]) == 3

    for path, key in (
        (f"/transactions/{single}", "transaction_id"),
        (f"/transactions/{parts[0]['id']}", "transaction_id"),
        (f"/bank-lines/{single_line}", "bank_line_id"),
        (f"/bank-lines/{split_line}", "bank_line_id"),
    ):
        err = refused(lambda path=path: client.delete(path))
        assert_refusal(err, 409, "CONFLICT", key, "ACCOUNT_ARCHIVED")

    kept = [{"id": p["id"], "amount_cents": -500} for p in parts]
    amounts = {"parts.0.amount_cents", "parts.1.amount_cents"}
    for line_id, body, keys in (
        (single_line, {"parts": [{"id": str(uuid4()), "amount_cents": -1000}]}, {"parts"}),
        (split_line, {"parts": kept}, amounts),
        (split_line, {"parts": kept, "date": _now()}, {*amounts, "date"}),
    ):
        scratch.transactions.extend(p["id"] for p in body["parts"])
        err = refused(
            lambda line_id=line_id, body=body: client.put(f"/bank-lines/{line_id}", json_body=body)
        )
        assert_refusals(err, 422, "VALIDATION_ERROR", dict.fromkeys(keys, "ACCOUNT_ARCHIVED"))

    assert ledger() == before

    client.post(f"/accounts/{account_id}/unarchive")
    assert client.get(f"/accounts/{account_id}")["is_archived"] is False
    assert client.put(f"/transactions/{single}", json_body={"title": "renamed"})["title"] == (
        "renamed"
    )
    assert len(_split(client, scratch, single, [-700, -300])) == 2
    assert client.delete(f"/transactions/{parts[0]['id']}")["deleted_at"] is not None
    remaining = client.delete(f"/bank-lines/{split_line}")["parts"]
    assert [p["id"] for p in remaining] == [parts[1]["id"]]


def test_moving_a_row_onto_an_archived_account_stays_invalid_reference(client, scratch):
    """Moving a transaction of an active account onto an archived one is `422` on
    `account_id` with `INVALID_REFERENCE`, not `ACCOUNT_ARCHIVED`, and moves nothing
    (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts")."""
    archived_id = scratch.account()
    active_id = scratch.account()
    tx_id = scratch.row(active_id, DAY, title="active-row")["id"]
    _archive(client, scratch, archived_id)
    before = read_signed(client, tx_id)

    err = refused(
        lambda: client.put(f"/transactions/{tx_id}", json_body={"account_id": archived_id})
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "account_id", "INVALID_REFERENCE")
    assert read_signed(client, tx_id) == before


#: The colour a create gives when `color` is left out (contract: "Colour format").
DEFAULT_COLOR = "#3b82f6"


@pytest.mark.parametrize("resource", ["accounts", "categories"])
def test_a_create_without_a_colour_gets_the_engine_default(client, scratch, resource):
    """A body with no `color` key comes back with the engine's default, on the
    create and on a read."""
    if resource == "accounts":
        body = account_body()
        scratch.accounts.append(body["id"])
    else:
        new_id = str(uuid4())
        body = {"id": new_id, "name": f"contract-color-{new_id[:8]}"}
        scratch.categories.append(new_id)
    assert "color" not in body
    created = client.post(f"/{resource}", json_body=body)
    assert created["color"] == DEFAULT_COLOR
    assert client.get(f"/{resource}/{body['id']}")["color"] == DEFAULT_COLOR
