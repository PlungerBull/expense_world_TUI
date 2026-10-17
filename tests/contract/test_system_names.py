"""Contract: the built-in rows keep their names — `SYSTEM_NAME_FIXED`.

`@Pendiente`, `@Opening` and the built-in pending hashtag are system rows, each
found by `system_key`, never by name. A rename of one is refused
(contract: PUT /v1/categories/{category_id}, "A system category keeps its name")
(contract: PUT /v1/hashtags/{hashtag_id}, "The pending hashtag keeps its name"), and
the app's forms show that refusal in the engine's words. Pinned here:

  · `PUT` of another name on each is `422` `VALIDATION_ERROR` with reason
    `SYSTEM_NAME_FIXED` on `name`, a change of letter case alone included, and
    the name stays;
  · `PUT` of the current name, or one that trims to it, is accepted;
  · their colour (categories) and order stay editable: `PUT` of `color` and
    `sort_order` on each system category, and of `sort_order` on the pending
    hashtag, is `200` with the new values.

The three rows are engine-created and can never be deleted, so they stay behind
on the practice user; nothing here changes their names, and a changed colour or
order is put back. Each test builds its own account and undoes what it wrote.
Gating, target and the real-ledger guard: conftest.py.
"""

from uuid import uuid4

import pytest

from expense.errors import EngineError
from expense.reads import OPENING_SYSTEM_KEY, PENDING_HASHTAG_KEY, PENDING_SYSTEM_KEY
from tests.contract.conftest import reason_on


def _safe(call, *args):
    try:
        call(*args)
    except EngineError:
        pass


def _refused(call) -> EngineError:
    with pytest.raises(EngineError) as excinfo:
        call()
    return excinfo.value


def _system_row(client, path: str, key: str) -> dict:
    found = [row for row in client.get(path)["items"] if row.get("system_key") == key]
    assert len(found) == 1, f"{path}: no single row with system_key {key!r}"
    return found[0]


def _swap_case(name: str) -> str:
    swapped = name.swapcase()
    assert swapped != name
    return swapped


def _assert_name_kept(client, path: str, row: dict, tried: list[str]) -> None:
    for name in tried:
        err = _refused(
            lambda name=name: client.put(f"{path}/{row['id']}", json_body={"name": name})
        )
        assert (err.status, err.code) == (422, "VALIDATION_ERROR"), name
        assert reason_on(err, "name") == "SYSTEM_NAME_FIXED", name
        assert client.get(f"{path}/{row['id']}")["name"] == row["name"]
    for same in (row["name"], f"  {row['name']} "):
        kept = client.put(f"{path}/{row['id']}", json_body={"name": same})
        assert kept["name"] == row["name"]


@pytest.fixture
def system_rows(client):
    """An account with an opening balance and an untagged, uncategorised row, so
    `@Opening`, `@Pendiente` and the pending hashtag all exist."""
    account = str(uuid4())
    opening = str(uuid4())
    sparse = str(uuid4())
    client.post(
        "/accounts",
        json_body={"id": account, "name": f"contract-names-{account[:8]}", "currency_code": "PEN"},
    )
    try:
        client.post(
            f"/accounts/{account}/opening-balance",
            json_body={
                "transaction_id": opening,
                "amount_cents": 10000,
                "date": "2026-01-01T00:00:00Z",
            },
        )
        client.post(
            "/transactions",
            json_body={
                "id": sparse,
                "amount_cents": -100,
                "account_id": account,
                "date": "2026-05-06T12:00:00Z",
            },
        )
        yield
    finally:
        _safe(client.delete, f"/transactions/{sparse}")
        _safe(client.delete, f"/transactions/{opening}")
        _safe(client.delete, f"/accounts/{account}")


def test_the_system_categories_keep_their_names(client, system_rows):
    for key in (PENDING_SYSTEM_KEY, OPENING_SYSTEM_KEY):
        row = _system_row(client, "/categories", key)
        _assert_name_kept(
            client, "/categories", row, [_swap_case(row["name"]), f"{row['name']} renamed"]
        )


def test_the_pending_hashtag_keeps_its_name(client, system_rows):
    row = _system_row(client, "/hashtags", PENDING_HASHTAG_KEY)
    _assert_name_kept(client, "/hashtags", row, [_swap_case(row["name"]), "Por revisar"])


def _assert_fields_editable(
    client, statuses: list[int], path: str, row: dict, changes: dict
) -> None:
    """`PUT` of `changes` on a system row is 200 with them, then the row's own
    values go back."""
    original = {field: row[field] for field in changes}
    try:
        edited = client.put(f"{path}/{row['id']}", json_body=changes)
        assert statuses[-1] == 200
        assert {field: edited[field] for field in changes} == changes
        reread = client.get(f"{path}/{row['id']}")
        assert {field: reread[field] for field in changes} == changes
        assert reread["name"] == row["name"]
    finally:
        client.put(f"{path}/{row['id']}", json_body=original)


def test_the_system_rows_keep_colour_and_order_editable(client, system_rows, statuses):
    # Only the name is fixed; colour and order stay editable
    # (contract: PUT /v1/categories/{category_id}, "A system category keeps its name")
    # (contract: PUT /v1/hashtags/{hashtag_id}, "The pending hashtag keeps its name")
    for key in (PENDING_SYSTEM_KEY, OPENING_SYSTEM_KEY):
        row = _system_row(client, "/categories", key)
        color = "#2a9d8f" if row["color"].lower() != "#2a9d8f" else "#e76f51"
        _assert_fields_editable(
            client,
            statuses,
            "/categories",
            row,
            {"color": color, "sort_order": row["sort_order"] + 7},
        )
        restored = client.get(f"/categories/{row['id']}")
        assert (restored["color"], restored["sort_order"]) == (row["color"], row["sort_order"])
    row = _system_row(client, "/hashtags", PENDING_HASHTAG_KEY)
    _assert_fields_editable(
        client, statuses, "/hashtags", row, {"sort_order": row["sort_order"] + 7}
    )
    assert client.get(f"/hashtags/{row['id']}")["sort_order"] == row["sort_order"]
