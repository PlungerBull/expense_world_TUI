"""Contract lifecycle for the three named resources.

Accounts: create → update → archive → unarchive → delete.
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
transaction or of a bank line, is `409` and a split `422`, both `ACCOUNT_ARCHIVED`;
after unarchiving, a frozen field, a split and both deletes go through. Moving
another account's row onto it stays `INVALID_REFERENCE`. Its reconciliations'
freeze is in test_reconciliations_lifecycle.py.

Not pinned here: a line field sent on an active account's transaction refused
because another part of its line sits on an archived account. Every part of a line
shares its account: a split gives each part the line's account, a batch
`line_group` must share it, and `PUT` of `account_id` writes it onto every part
(contract: "Transactions (Ledger)", "Bank lines"), so no route builds such a line.

An account or a category created with no `color` comes back with the engine's
default colour.

Hits a real engine. Gating, target resolution and the real-ledger guard live in
conftest.py; uses ExpenseClient directly so each test owns its idempotency keys.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from expense.errors import EngineError
from tests.contract.conftest import read_signed


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


def test_accounts_lifecycle(client):
    new_id = str(uuid4())
    name = f"contract-account-{new_id[:8]}"

    created = client.post(
        "/accounts",
        json_body={"id": new_id, "name": name, "currency_code": "USD"},
    )
    try:
        assert created["id"] == new_id
        assert created["name"] == name

        fetched = client.get(f"/accounts/{new_id}")
        assert fetched["id"] == new_id

        updated = client.put(f"/accounts/{new_id}", json_body={"name": f"{name}-renamed"})
        assert updated["name"] == f"{name}-renamed"

        active = _list_all(client, "accounts")
        assert any(a["id"] == new_id for a in active)

        client.post(f"/accounts/{new_id}/archive")
        active_after = _list_all(client, "accounts")
        assert not any(a["id"] == new_id for a in active_after)

        archived = _list_all(client, "accounts", include_archived=True)
        assert any(a["id"] == new_id for a in archived)

        client.post(f"/accounts/{new_id}/unarchive")
        client.delete(f"/accounts/{new_id}")
        _assert_gone(client, "accounts", new_id)
    finally:
        # Best-effort cleanup; ignore if already deleted.
        try:
            client.delete(f"/accounts/{new_id}")
        except Exception:
            pass


def test_categories_lifecycle(client):
    new_id = str(uuid4())
    name = f"contract-cat-{new_id[:8]}"

    created = client.post(
        "/categories",
        json_body={"id": new_id, "name": name, "color": "#123456"},
    )
    try:
        assert created["id"] == new_id

        fetched = client.get(f"/categories/{new_id}")
        assert fetched["id"] == new_id

        updated = client.put(f"/categories/{new_id}", json_body={"name": f"{name}-renamed"})
        assert updated["name"] == f"{name}-renamed"

        # No archive/unarchive arm: those routes 404. Pin the
        # deletion so a silent re-introduction would be caught.
        active = _list_all(client, "categories")
        assert any(c["id"] == new_id for c in active)

        client.delete(f"/categories/{new_id}")
        _assert_gone(client, "categories", new_id)
    finally:
        try:
            client.delete(f"/categories/{new_id}")
        except Exception:
            pass


def test_hashtags_lifecycle(client):
    new_id = str(uuid4())
    name = f"contract-tag-{new_id[:8]}"

    created = client.post("/hashtags", json_body={"id": new_id, "name": name})
    try:
        assert created["id"] == new_id

        fetched = client.get(f"/hashtags/{new_id}")
        assert fetched["id"] == new_id

        updated = client.put(f"/hashtags/{new_id}", json_body={"name": f"{name}-renamed"})
        assert updated["name"] == f"{name}-renamed"

        # Same as categories — no archive routes.
        active = _list_all(client, "hashtags")
        assert any(h["id"] == new_id for h in active)

        client.delete(f"/hashtags/{new_id}")
        _assert_gone(client, "hashtags", new_id)
    finally:
        try:
            client.delete(f"/hashtags/{new_id}")
        except Exception:
            pass


class ArchivedBook:
    """Creates accounts, categories, hashtags, rows and draft periods, and undoes them:
    every account it archived is unarchived first, since an archived account's rows and
    reconciliations can be neither deleted nor changed
    (contract: POST /v1/accounts/{account_id}/archive, "Its transactions are frozen except
    for their categorisation")."""

    def __init__(self, client):
        self.c = client
        self.accounts: list[str] = []
        self.archived: list[str] = []
        self.categories: list[str] = []
        self.hashtags: list[str] = []
        self.rows: list[str] = []
        self.periods: list[str] = []

    def account(self) -> str:
        new_id = str(uuid4())
        self.c.post(
            "/accounts",
            json_body={"id": new_id, "name": f"contract-arch-{new_id[:8]}", "currency_code": "PEN"},
        )
        self.accounts.append(new_id)
        return new_id

    def category(self) -> str:
        new_id = str(uuid4())
        self.c.post("/categories", json_body={"id": new_id, "name": f"contract-arch-{new_id[:8]}"})
        self.categories.append(new_id)
        return new_id

    def hashtag(self) -> str:
        new_id = str(uuid4())
        self.c.post("/hashtags", json_body={"id": new_id, "name": f"contract-arch-{new_id[:8]}"})
        self.hashtags.append(new_id)
        return new_id

    def row(self, account_id: str, **fields) -> str:
        new_id = str(uuid4())
        body = {"id": new_id, "amount_cents": -1000, "account_id": account_id, "date": _now()}
        self.c.post("/transactions", json_body={**body, **fields})
        self.rows.append(new_id)
        return new_id

    def split(self, tx_id: str, amounts: list[int]) -> list[dict]:
        """Split the line holding `tx_id`; every part id is kept before the call, so
        cleanup reaches whatever the engine created."""
        parts = [{"id": str(uuid4()), "amount_cents": a} for a in amounts]
        self.rows.extend(p["id"] for p in parts)
        return self.c.post(f"/transactions/{tx_id}/split", json_body={"parts": parts})["parts"]

    def draft(self, account_id: str) -> str:
        new_id = str(uuid4())
        self.c.post(
            "/reconciliations",
            json_body={
                "id": new_id,
                "account_id": account_id,
                "name": f"contract-arch-{new_id[:8]}",
                "date_start": "2026-04-01",
                "date_end": "2026-04-30",
                "beginning_balance_cents": 0,
            },
        )
        self.periods.append(new_id)
        return new_id

    def archive(self, account_id: str) -> None:
        self.archived.append(account_id)
        self.c.post(f"/accounts/{account_id}/archive")
        assert self.c.get(f"/accounts/{account_id}")["is_archived"] is True

    def unarchive(self, account_id: str) -> None:
        self.c.post(f"/accounts/{account_id}/unarchive")
        assert self.c.get(f"/accounts/{account_id}")["is_archived"] is False

    def cleanup(self) -> None:
        for aid in self.archived:
            _safe(self.c.post, f"/accounts/{aid}/unarchive")
        for pid in reversed(self.periods):
            _safe(self.c.delete, f"/reconciliations/{pid}")
        for rid in reversed(self.rows):
            _safe(self.c.delete, f"/transactions/{rid}")
        for path in (
            *(f"/hashtags/{h}" for h in self.hashtags),
            *(f"/categories/{c}" for c in self.categories),
            *(f"/accounts/{a}" for a in reversed(self.accounts)),
        ):
            _safe(self.c.delete, path)


@pytest.fixture
def book(client):
    ledger = ArchivedBook(client)
    try:
        yield ledger
    finally:
        ledger.cleanup()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe(call, *args) -> None:
    try:
        call(*args)
    except EngineError:
        pass


def _refused(call, *args, **kw) -> EngineError:
    with pytest.raises(EngineError) as excinfo:
        call(*args, **kw)
    return excinfo.value


#: The fields an archived account's transaction refuses, even at their current value
#: (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts").
FROZEN = ("amount_cents", "date", "title", "operation_code", "account_id", "reconciliation_id")


def test_an_archived_accounts_transaction_takes_only_its_categorisation(client, book):
    """On a transaction whose account is archived, a `PUT` of `category_id`, of
    `hashtag_ids` and of `description` each go through. A `PUT` of any field in
    `FROZEN` is `422` `ACCOUNT_ARCHIVED` on that key, at a new value and at its current
    one, and writes nothing (contract: PUT /v1/transactions/{transaction_id}, "The
    refusal is on keys, not changed values")."""
    account_id = book.account()
    elsewhere = book.account()
    category_id = book.category()
    hashtag_id = book.hashtag()
    tx_id = book.row(account_id, title="archived-row", operation_code=f"OP-{uuid4().hex[:8]}")
    draft_id = book.draft(account_id)
    book.archive(account_id)

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
        "reconciliation_id": draft_id,
    }
    for key in FROZEN:
        for value in (changed[key], current[key]):
            err = _refused(client.put, path, json_body={key: value})
            assert (err.status, err.code) == (422, "VALIDATION_ERROR"), (key, value)
            assert err.reasons == {key: "ACCOUNT_ARCHIVED"}, (key, value)
    assert read_signed(client, tx_id) == current  # nothing written, `version` included


def test_a_mixed_put_on_an_archived_accounts_transaction_writes_nothing(client, book):
    """A `PUT` sending categorisation beside frozen fields names only the frozen keys,
    and writes none of it: the categorisation stays as it was and `version` does not
    move (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts")."""
    account_id = book.account()
    category_id = book.category()
    tx_id = book.row(account_id, title="archived-row")
    book.archive(account_id)
    before = read_signed(client, tx_id)

    err = _refused(
        client.put,
        f"/transactions/{tx_id}",
        json_body={
            "category_id": category_id,
            "description": "never written",
            "amount_cents": before["amount_cents"],
            "title": "renamed",
        },
    )
    assert (err.status, err.code) == (422, "VALIDATION_ERROR")
    assert err.reasons == {"amount_cents": "ACCOUNT_ARCHIVED", "title": "ACCOUNT_ARCHIVED"}
    assert read_signed(client, tx_id) == before


def test_an_archived_accounts_empty_title_is_filled_once(client, book):
    """A title that is still `null` may be filled on an archived account's transaction;
    once set, changing or clearing it is `422` `ACCOUNT_ARCHIVED` on `title`
    (contract: PUT /v1/transactions/{transaction_id}, "An empty field may be filled")."""
    account_id = book.account()
    tx_id = book.row(account_id)
    book.archive(account_id)
    assert client.get(f"/transactions/{tx_id}")["title"] is None

    filled = client.put(f"/transactions/{tx_id}", json_body={"title": "filled once"})
    assert filled["title"] == "filled once"
    before = read_signed(client, tx_id)
    for value in ("changed", None):
        err = _refused(client.put, f"/transactions/{tx_id}", json_body={"title": value})
        assert (err.status, err.reasons) == (422, {"title": "ACCOUNT_ARCHIVED"}), value
    assert read_signed(client, tx_id) == before


def test_an_archived_accounts_empty_operation_code_is_filled_once(client, book):
    """An `operation_code` that is still `null` may be filled on an archived account's
    transaction; once set, changing or clearing it is `422` `ACCOUNT_ARCHIVED` on
    `operation_code`
    (contract: PUT /v1/transactions/{transaction_id}, "An empty field may be filled")."""
    account_id = book.account()
    tx_id = book.row(account_id, title="archived-row")
    book.archive(account_id)
    assert client.get(f"/transactions/{tx_id}")["operation_code"] is None

    code = f"OP-{uuid4().hex[:8]}"
    filled = client.put(f"/transactions/{tx_id}", json_body={"operation_code": code})
    assert filled["operation_code"] == code
    before = read_signed(client, tx_id)
    for value in (f"OP-{uuid4().hex[:8]}", None):
        err = _refused(client.put, f"/transactions/{tx_id}", json_body={"operation_code": value})
        assert (err.status, err.reasons) == (422, {"operation_code": "ACCOUNT_ARCHIVED"}), value
    assert read_signed(client, tx_id) == before


def test_an_archived_accounts_rows_are_neither_split_nor_deleted_until_unarchived(client, book):
    """On an archived account, `DELETE /transactions/{id}` is `409` on `transaction_id`
    and `DELETE /bank-lines/{id}` `409` on `bank_line_id`, a split line's part and the
    line included; a split is `422` on `transaction_id`; all `ACCOUNT_ARCHIVED`, and
    the balance and every row stay as they were
    (contract: POST /v1/accounts/{account_id}/archive, "Its transactions are frozen
    except for their categorisation"). After `POST /accounts/{id}/unarchive` a frozen
    field, a split and both deletes go through
    (contract: POST /v1/accounts/{account_id}/unarchive)."""
    account_id = book.account()
    single = book.row(account_id, title="single")
    parts = book.split(book.row(account_id, title="split"), [-600, -400])
    single_line = client.get(f"/transactions/{single}")["bank_line_id"]
    split_line = parts[0]["bank_line_id"]
    book.archive(account_id)

    def ledger() -> tuple[int, list[dict]]:
        balance = client.get(f"/accounts/{account_id}")["current_balance_cents"]
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
        err = _refused(client.delete, path)
        assert (err.status, err.code) == (409, "CONFLICT"), path
        assert err.reasons == {key: "ACCOUNT_ARCHIVED"}, path

    for tx_id in (single, parts[0]["id"]):
        new_parts = [{"id": str(uuid4()), "amount_cents": a} for a in (-700, -300)]
        book.rows.extend(p["id"] for p in new_parts)
        err = _refused(client.post, f"/transactions/{tx_id}/split", json_body={"parts": new_parts})
        assert (err.status, err.code) == (422, "VALIDATION_ERROR"), tx_id
        assert err.reasons == {"transaction_id": "ACCOUNT_ARCHIVED"}, tx_id

    assert ledger() == before

    book.unarchive(account_id)
    assert client.put(f"/transactions/{single}", json_body={"title": "renamed"})["title"] == (
        "renamed"
    )
    assert len(book.split(single, [-700, -300])) == 2
    assert client.delete(f"/transactions/{parts[0]['id']}")["deleted_at"] is not None
    remaining = client.delete(f"/bank-lines/{split_line}")["parts"]
    assert [p["id"] for p in remaining] == [parts[1]["id"]]


def test_moving_a_row_onto_an_archived_account_stays_invalid_reference(client, book):
    """Moving a transaction of an active account onto an archived one is `422` on
    `account_id` with `INVALID_REFERENCE`, not `ACCOUNT_ARCHIVED`, and moves nothing
    (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts")."""
    archived_id = book.account()
    active_id = book.account()
    tx_id = book.row(active_id, title="active-row")
    book.archive(archived_id)
    before = read_signed(client, tx_id)

    err = _refused(client.put, f"/transactions/{tx_id}", json_body={"account_id": archived_id})
    assert (err.status, err.reasons) == (422, {"account_id": "INVALID_REFERENCE"})
    assert read_signed(client, tx_id) == before


#: The colour a create gives when `color` is left out (contract: "Colour format").
DEFAULT_COLOR = "#3b82f6"


@pytest.mark.parametrize(
    ("resource", "extra"),
    [("accounts", {"currency_code": "PEN"}), ("categories", {})],
)
def test_a_create_without_a_colour_gets_the_engine_default(client, resource, extra):
    """A body with no `color` key comes back with the engine's default, on the
    create and on a read."""
    new_id = str(uuid4())
    try:
        created = client.post(
            f"/{resource}",
            json_body={"id": new_id, "name": f"contract-color-{new_id[:8]}", **extra},
        )
        assert created["color"] == DEFAULT_COLOR
        assert client.get(f"/{resource}/{new_id}")["color"] == DEFAULT_COLOR
    finally:
        try:
            client.delete(f"/{resource}/{new_id}")
        except EngineError:
            pass
