"""Contract: how an account is read and what its writes leave in the activity log, against a
real engine.

The app reads accounts through `GET /accounts` and `GET /accounts/{id}` and shows what they
answer; only the engine can say which keys an account and each of its currencies carry, in
which order they list, and which entries a write logs for them
(contract: "Bank Accounts", "Account response").

What it pins:

1. An account is read with exactly the fifteen keys of the contract, on the list and on its
   own, for a bank account, a person and an archived account; each entry of `currencies` is
   exactly `{currency_code, current_balance_cents, opening_balance_transaction_id}`, so it
   carries no home-currency value and no total across currencies exists (the exact key sets
   are the proof); the list holds the very account the read answers (contract: "Bank
   Accounts", "Account response").
2. An account's currencies list `PEN` before `USD` whichever was created first, whatever their
   balances, on the list and on the read, a person's too (contract: "Bank Accounts",
   "Per-currency order").
3. The list puts every bank account before every person, each group by `sort_order`, then
   creation time, oldest first (contract: GET /v1/accounts, "Ordering"). The test holds
   persons whose names, creation order and `sort_order` would put them first if the engine
   ordered by any of those across both groups, and two banks with one `sort_order` told apart
   by creation time.
4. An archived account is listed, with its currencies and their balances, only with
   `?include_archived=true`; a person only with `?include_people=true`; the read answers
   either (contract: GET /v1/accounts) (contract: GET /v1/accounts/{account_id}).
5. `GET /activity?resource_id=<account id>` reads an account's entries together with its
   currencies' (contract: GET /v1/activity, "Accounts and their currencies"), counted
   exactly: a create is one `account` and two `currency` entries, an edit, an archive, an
   unarchive and a kind change either way (`make-person`, `make-account`) the `account` entry
   alone, an added and a removed currency one `currency` entry each, a delete one `DELETED`
   `account` entry and one `DELETED` `currency` entry per currency; every snapshot carries
   the keys of the contract (contract: "What an account is", "Account snapshot")
   (contract: "Bank Accounts", "Per-currency account").
6. `kind` is on every answer that is an account (`POST /accounts`, the list, the read, `PUT`,
   archive, unarchive, a currency's add and removal) and on each `account` entry's snapshots
   written now, for a bank account and a person alike (contract: "Bank Accounts", "Account
   response").
7. A boolean query flag is exactly `true` or `false`: `1` for `include_archived` or
   `include_people` is `422` `INVALID_FORMAT` on that parameter (contract: "Base Conventions",
   "Booleans and whole numbers in a request").

What it leaves out:

  · The older nouns of the log (`card`, a currency under `account`, `RESTORED`): no
    write logs under them any more and the practice user's log holds none of them to read
    (contract: GET /v1/activity, "Older and restored entries").
  · The activity log's paging and window: test_transactions_cursor.py reads them.
  · A refused write's entries: every refusal there writes nothing, which the refusal tests of
    test_account_currencies.py and test_account_create.py prove by reading the accounts.

Every account is fresh per run (a person named by its UUID, a bank account numbered from the
suite's range) and removed by the `scratch` fixture.
Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from uuid import uuid4

import pytest

from tests.contract.conftest import (
    DEFAULT_COLOR,
    account_body,
    all_accounts,
    assert_refusal,
    bank_code,
    next_last4,
    refused,
)

ACCOUNT_KEYS = {
    "id",
    "user_id",
    "name",
    "color",
    "kind",
    "bank_code",
    "numbers",
    "statement_code",
    "is_archived",
    "sort_order",
    "currencies",
    "created_at",
    "updated_at",
    "version",
    "deleted_at",
}
CURRENCY_KEYS = {"currency_code", "current_balance_cents", "opening_balance_transaction_id"}
#: The keys of an `account` entry's snapshot: the account's, without its currencies.
ACCOUNT_SNAPSHOT_KEYS = ACCOUNT_KEYS - {"currencies"}
CURRENCY_SNAPSHOT_KEYS = {
    "user_id",
    "account_id",
    "currency_code",
    "current_balance_cents",
    "created_at",
    "updated_at",
    "version",
    "deleted_at",
}
ENTRY_KEYS = {
    "id",
    "user_id",
    "resource_type",
    "resource_id",
    "action",
    "before_snapshot",
    "after_snapshot",
    "changed_by",
    "created_at",
}
CREATED, UPDATED, DELETED = 1, 2, 3


def _named(tag: str) -> str:
    """A name no other account holds, ending in `tag` so that the names of one test sort as
    the test needs."""
    return f"contract-reads-{tag}-{uuid4().hex[:8]}"


def _mine(listed: list[dict], ids: list[str]) -> list[str]:
    """Which of `ids` the list holds, in the list's order."""
    return [a["id"] for a in listed if a["id"] in ids]


def _listed(client, **params) -> list[dict]:
    return client.get("/accounts", params=params)["items"]


def _codes(account: dict) -> list[str]:
    return [c["currency_code"] for c in account["currencies"]]


def _assert_whole(account: dict) -> None:
    """The account carries exactly the contract's keys, each currency exactly its three."""
    assert set(account) == ACCOUNT_KEYS, set(account) ^ ACCOUNT_KEYS
    assert account["deleted_at"] is None
    for currency in account["currencies"]:
        assert set(currency) == CURRENCY_KEYS, set(currency) ^ CURRENCY_KEYS


def test_an_account_is_read_with_exactly_the_contracts_keys_on_the_list_and_alone(client, scratch):
    """A bank account, a person and an archived account, each holding soles and dollars with
    an opening balance in the soles: the list and the read answer the same account with
    exactly the fifteen keys, and each currency exactly its three (contract: "Bank
    Accounts", "Account response")."""
    bank = scratch.account("PEN", "USD")
    person = scratch.account("PEN", "USD", person=True)
    archived = scratch.account("PEN", "USD")
    for account_id in (bank, person, archived):
        scratch.opening_balance(account_id, "2026-01-02", "PEN", 12345)
    scratch.archive(archived)

    listed = {a["id"]: a for a in all_accounts(client)}
    for account_id, kind, is_archived in (
        (bank, "bank", False),
        (person, "person", False),
        (archived, "bank", True),
    ):
        read = client.get(f"/accounts/{account_id}")
        _assert_whole(read)
        assert listed[account_id] == read
        assert (read["kind"], read["is_archived"]) == (kind, is_archived)
        assert read["id"] == account_id
        assert read["version"] >= 1

        soles, dollars = read["currencies"]
        assert soles["current_balance_cents"] == 12345
        assert isinstance(soles["opening_balance_transaction_id"], str)
        assert (dollars["current_balance_cents"], dollars["opening_balance_transaction_id"]) == (
            0,
            None,
        )


def test_currencies_list_soles_before_dollars_whichever_was_created_first(client, scratch):
    """Dollars created before soles, the soles holding money above the dollars in a bank
    account and below them in a person, still list `PEN` then `USD`: not in creation order,
    not by balance either way; a currency added later takes its place by code, on the read
    and the list (contract: "Bank Accounts", "Per-currency order")."""
    for person, soles in ((False, 50000), (True, -50000)):
        account_id = scratch.account("USD", "PEN", person=person)
        scratch.opening_balance(account_id, "2026-01-02", "PEN", soles)
        read = client.get(f"/accounts/{account_id}")
        assert _codes(read) == ["PEN", "USD"]
        assert [c["current_balance_cents"] for c in read["currencies"]] == [soles, 0]
        listed = next(a for a in all_accounts(client) if a["id"] == account_id)
        assert _codes(listed) == ["PEN", "USD"]

    later = scratch.account("USD")
    client.post(f"/accounts/{later}/currencies", json_body={"currency_code": "PEN"})
    assert _codes(client.get(f"/accounts/{later}")) == ["PEN", "USD"]


def test_every_bank_account_comes_before_every_person(client, scratch):
    """Two people made first, with the lowest names and `sort_order`s, then three bank
    accounts: the list still puts the banks first, ordered by `sort_order` ascending and, for
    the two sharing one, by creation time, oldest first, then the people by `sort_order` (the
    first made having the higher one), so neither names, creation time nor one `sort_order`
    across both kinds gives the order; of the two banks sharing a `sort_order`, the one made
    first has the later name (built from its number) and the higher id, so neither name nor id
    breaks the tie
    (contract: GET /v1/accounts, "Ordering")."""
    first_person = scratch.account(name=_named("a1"), person=True, sort_order=1)
    second_person = scratch.account(name=_named("a2"), person=True, sort_order=0)
    late = scratch.account(last4="9170", sort_order=9)
    low_id, high_id = sorted([str(uuid4()), str(uuid4())])
    early = scratch.account(last4="9190", sort_order=3, id=high_id)
    tied = scratch.account(last4="9180", sort_order=3, id=low_id)
    banks = [early, tied, late]
    people = [second_person, first_person]
    made = banks + people

    both = {"include_people": "true", "include_archived": "true"}
    assert _mine(_listed(client, **both), made) == banks + people
    assert _mine(_listed(client, include_people="true"), made) == banks + people

    plain = _listed(client)
    assert _mine(plain, made) == banks
    assert not [a for a in plain if a["kind"] == "person"]


def test_an_archived_account_lists_only_when_asked_and_a_person_likewise(client, scratch):
    """An archived account and a person each hold soles and dollars with money in the
    soles: the plain list lacks both; `?include_archived=true` adds the archived account whole
    with its currencies and balances, `?include_people=true` the person; the read answers the
    archived account as the list does (contract: GET /v1/accounts)
    (contract: GET /v1/accounts/{account_id})."""
    archived = scratch.account("PEN", "USD")
    person = scratch.account("PEN", "USD", person=True)
    scratch.opening_balance(archived, "2026-01-02", "PEN", 777)
    before = client.get(f"/accounts/{archived}")
    scratch.archive(archived)
    kept = client.get(f"/accounts/{archived}")

    assert _mine(_listed(client), [archived, person]) == []
    assert _mine(_listed(client, include_people="true"), [archived, person]) == [person]
    assert _mine(_listed(client, include_archived="true"), [archived, person]) == [archived]

    listed = next(a for a in _listed(client, include_archived="true") if a["id"] == archived)
    assert listed == kept
    assert _codes(listed) == ["PEN", "USD"]
    assert listed["currencies"] == before["currencies"]
    assert listed["is_archived"] is True


class Entries:
    """The activity log of one account, read by its `resource_id` alone: `new()` is the
    entries written since the last call."""

    def __init__(self, client, account_id: str) -> None:
        self.client = client
        self.account_id = account_id
        self.seen: set[str] = set()

    def new(self) -> list[dict]:
        body = self.client.get("/activity", params={"resource_id": self.account_id, "limit": 200})
        assert body["next_cursor"] is None
        fresh = [e for e in body["items"] if e["id"] not in self.seen]
        self.seen.update(e["id"] for e in fresh)
        for entry in fresh:
            assert set(entry) == ENTRY_KEYS, set(entry) ^ ENTRY_KEYS
            assert entry["resource_id"] == self.account_id
        return fresh


def _kinds(entries: list[dict]) -> list[tuple[str, int]]:
    """The `(resource_type, action)` of each entry, sorted."""
    return sorted((e["resource_type"], e["action"]) for e in entries)


def _snapshot(entry: dict, which: str, keys: set[str]) -> dict:
    snapshot = entry[which]
    assert set(snapshot) == keys, set(snapshot) ^ keys
    return snapshot


def test_a_create_logs_one_account_entry_and_one_entry_per_currency(client, scratch):
    """A bank account made with dollars then soles reads exactly three entries by its id: one
    `account` `CREATED` with the account's snapshot, and one `currency` `CREATED` for each
    currency, each snapshot the currency's at balance `0` naming the account (contract: GET
    /v1/activity, "Accounts and their currencies") (contract: POST /v1/accounts, "Response")."""
    account_id = scratch.account("USD", "PEN")
    made = client.get(f"/accounts/{account_id}")

    entries = Entries(client, account_id).new()

    assert _kinds(entries) == [("account", CREATED), ("currency", CREATED), ("currency", CREATED)]
    (account_entry,) = [e for e in entries if e["resource_type"] == "account"]
    snap = _snapshot(account_entry, "after_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    assert snap == {k: v for k, v in made.items() if k != "currencies"}
    assert account_entry["before_snapshot"] is None

    currency_entries = [e for e in entries if e["resource_type"] == "currency"]
    snaps = [_snapshot(e, "after_snapshot", CURRENCY_SNAPSHOT_KEYS) for e in currency_entries]
    assert sorted(s["currency_code"] for s in snaps) == ["PEN", "USD"]
    for snap in snaps:
        assert snap["account_id"] == account_id
        assert (snap["current_balance_cents"], snap["deleted_at"]) == (0, None)
    assert all(e["before_snapshot"] is None for e in currency_entries)


def test_an_edit_an_archive_and_a_kind_change_each_log_the_account_alone(client, scratch):
    """On an account holding soles and dollars, an edit, a `make-person` and an archive each
    write exactly one `account` `UPDATED` entry and no `currency` entry; the snapshots show
    the colour, then `kind` (and `sort_order`), then `is_archived` before and after
    (contract: PUT /v1/accounts/{account_id}) (contract: POST
    /v1/accounts/{account_id}/make-person) (contract: POST /v1/accounts/{account_id}/archive)."""
    account_id = scratch.account("PEN", "USD")
    log = Entries(client, account_id)
    assert len(log.new()) == 3

    client.put(f"/accounts/{account_id}", json_body={"color": "#00aa00"})
    (edit,) = log.new()
    assert (edit["resource_type"], edit["action"]) == ("account", UPDATED)
    before = _snapshot(edit, "before_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    after = _snapshot(edit, "after_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    assert (before["color"], after["color"]) == (DEFAULT_COLOR, "#00aa00")
    assert after["version"] == before["version"] + 1

    made = client.post(f"/accounts/{account_id}/make-person", json_body={"name": _named("person")})
    (kind,) = log.new()
    assert (kind["resource_type"], kind["action"]) == ("account", UPDATED)
    before = _snapshot(kind, "before_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    after = _snapshot(kind, "after_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    assert (before["kind"], after["kind"]) == ("bank", "person")
    assert after["sort_order"] == made["sort_order"]

    client.post(f"/accounts/{account_id}/archive")
    (archive,) = log.new()
    assert (archive["resource_type"], archive["action"]) == ("account", UPDATED)
    before = _snapshot(archive, "before_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    after = _snapshot(archive, "after_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    assert (before["is_archived"], after["is_archived"]) == (False, True)
    assert after["version"] == before["version"] + 1

    assert log.new() == []


def test_an_unarchive_and_a_turn_back_into_a_bank_account_each_log_the_account_alone(
    client, scratch
):
    """On an archived account holding soles and dollars, an unarchive writes exactly one
    `account` `UPDATED` entry and no `currency` entry, `is_archived` going from true to false;
    on a person, `make-account` writes exactly one `account` `UPDATED` entry and no `currency`
    entry, `kind` going from `person` to `bank` and `sort_order` ending at the one the write
    answers (contract: POST /v1/accounts/{account_id}/unarchive) (contract: POST
    /v1/accounts/{account_id}/make-account)."""
    archived = scratch.account("PEN", "USD")
    log = Entries(client, archived)
    assert len(log.new()) == 3
    scratch.archive(archived)
    assert len(log.new()) == 1

    client.post(f"/accounts/{archived}/unarchive")
    (unarchive,) = log.new()
    assert (unarchive["resource_type"], unarchive["action"]) == ("account", UPDATED)
    before = _snapshot(unarchive, "before_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    after = _snapshot(unarchive, "after_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    assert (before["is_archived"], after["is_archived"]) == (True, False)
    assert after["version"] == before["version"] + 1
    assert log.new() == []

    person = scratch.account("PEN", "USD", person=True, name=_named("back"))
    log = Entries(client, person)
    assert len(log.new()) == 3

    made = client.post(
        f"/accounts/{person}/make-account",
        json_body={"bank_code": bank_code(), "last4": next_last4()},
    )
    (kind,) = log.new()
    assert (kind["resource_type"], kind["action"]) == ("account", UPDATED)
    before = _snapshot(kind, "before_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    after = _snapshot(kind, "after_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    assert (before["kind"], after["kind"]) == ("person", "bank")
    assert after["sort_order"] == made["sort_order"]
    assert after["version"] == before["version"] + 1
    assert log.new() == []


def test_a_delete_logs_one_deleted_account_entry_and_one_per_currency(client, scratch):
    """An account holding soles and dollars, deleted, writes exactly three new entries by its
    id: one `account` `DELETED` with the account's snapshots and one `currency` `DELETED` for
    each currency with that currency's, each `deleted_at` unset before and set after (contract:
    DELETE /v1/accounts/{account_id}, "Activity log") (contract: GET /v1/activity, "Accounts
    and their currencies")."""
    account_id = scratch.account("PEN", "USD")
    log = Entries(client, account_id)
    assert len(log.new()) == 3

    client.delete(f"/accounts/{account_id}")
    entries = log.new()

    assert _kinds(entries) == [("account", DELETED), ("currency", DELETED), ("currency", DELETED)]
    (account_entry,) = [e for e in entries if e["resource_type"] == "account"]
    held = _snapshot(account_entry, "before_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    gone = _snapshot(account_entry, "after_snapshot", ACCOUNT_SNAPSHOT_KEYS)
    assert (held["id"], gone["id"]) == (account_id, account_id)
    assert held["deleted_at"] is None
    assert gone["deleted_at"] is not None

    codes = []
    for entry in [e for e in entries if e["resource_type"] == "currency"]:
        held = _snapshot(entry, "before_snapshot", CURRENCY_SNAPSHOT_KEYS)
        gone = _snapshot(entry, "after_snapshot", CURRENCY_SNAPSHOT_KEYS)
        for snap in (held, gone):
            assert snap["account_id"] == account_id
            assert snap["current_balance_cents"] == 0
        assert held["currency_code"] == gone["currency_code"]
        codes.append(held["currency_code"])
        assert held["deleted_at"] is None
        assert gone["deleted_at"] is not None
    assert sorted(codes) == ["PEN", "USD"]
    assert log.new() == []


def test_an_added_and_a_removed_currency_each_log_one_currency_entry(client, scratch):
    """Dollars added to a soles account write exactly one `currency` `CREATED` entry, the
    removal of them exactly one `currency` `DELETED` entry, each naming the account and the
    code at balance `0`, and no `account` entry (contract: POST
    /v1/accounts/{account_id}/currencies, "Response") (contract: DELETE
    /v1/accounts/{account_id}/currencies/{currency_code}, "Response")."""
    account_id = scratch.account("PEN")
    log = Entries(client, account_id)
    assert len(log.new()) == 2

    client.post(f"/accounts/{account_id}/currencies", json_body={"currency_code": "USD"})
    (added,) = log.new()
    assert (added["resource_type"], added["action"]) == ("currency", CREATED)
    snap = _snapshot(added, "after_snapshot", CURRENCY_SNAPSHOT_KEYS)
    assert (snap["account_id"], snap["currency_code"]) == (account_id, "USD")
    assert (snap["current_balance_cents"], snap["deleted_at"]) == (0, None)

    client.delete(f"/accounts/{account_id}/currencies/USD")
    (removed,) = log.new()
    assert (removed["resource_type"], removed["action"]) == ("currency", DELETED)
    held = _snapshot(removed, "before_snapshot", CURRENCY_SNAPSHOT_KEYS)
    gone = _snapshot(removed, "after_snapshot", CURRENCY_SNAPSHOT_KEYS)
    for snap in (held, gone):
        assert (snap["account_id"], snap["currency_code"]) == (account_id, "USD")
        assert snap["current_balance_cents"] == 0
    assert held["deleted_at"] is None
    assert gone["deleted_at"] is not None
    assert log.new() == []


def test_every_account_answer_and_snapshot_carries_its_kind(client, scratch):
    """A bank account and a person, each made, listed, read, edited, archived, unarchived, given
    dollars and relieved of them, answer `kind` as made every time, and every snapshot of the
    `account` entries these writes left names it too, before and after
    (contract: "Bank Accounts", "Account response")
    (contract: "What an account is", "Account snapshot")."""
    for person in (False, True):
        kind = "person" if person else "bank"
        body = account_body("PEN", person=person)
        account_id = body["id"]
        scratch.accounts.append(account_id)
        path = f"/accounts/{account_id}"
        answers = [client.post("/accounts", json_body=body), client.get(path)]
        answers.append(next(a for a in all_accounts(client) if a["id"] == account_id))
        answers.append(client.put(path, json_body={"color": "#00aa00"}))
        answers.append(client.post(f"{path}/archive"))
        answers.append(client.post(f"{path}/unarchive"))
        answers.append(client.post(f"{path}/currencies", json_body={"currency_code": "USD"}))
        answers.append(client.delete(f"{path}/currencies/USD"))
        assert [a["kind"] for a in answers] == [kind] * len(answers)

        entries = Entries(client, account_id).new()
        written = [e for e in entries if e["resource_type"] == "account"]
        assert len(written) == 4  # create, edit, archive, unarchive
        for entry in written:
            for which in ("before_snapshot", "after_snapshot"):
                if entry[which] is not None:
                    assert entry[which]["kind"] == kind


@pytest.mark.parametrize("path", ["/accounts", "/dashboard"])
def test_a_query_flag_of_one_is_invalid_format_on_its_parameter(client, path):
    """`1` is no boolean in a query: `include_archived=1` (and `include_people=1` on the
    list) is `422` `INVALID_FORMAT` keyed on the parameter, while `true` is taken
    (contract: "Base Conventions", "Booleans and whole numbers in a request")."""
    flags = ["include_archived"] + (["include_people"] if path == "/accounts" else [])
    for flag in flags:
        err = refused(lambda flag=flag: client.get(path, params={flag: "1"}))
        assert_refusal(err, 422, "VALIDATION_ERROR", flag, "INVALID_FORMAT")
        client.get(path, params={flag: "true"})
