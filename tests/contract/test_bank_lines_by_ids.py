"""Contract: the bank-line list read by its lines' ids, and listed oldest first.

The flagged lines' screen reads the lines a statement's close flagged for review in one
`GET /bank-lines?ids=…&sort=date_asc` (expense/reads.py `fetch_bank_lines_by_ids`), and
drops a line the engine no longer has by reading the ids again
(contract: GET /v1/bank-lines, "Filters"). Pinned here:

  · `?ids=`: the live lines among the ids sent, each exactly the line read by id, in the
    list's own order whatever order the ids go in, a repeated id the same filter; a
    deleted id and an unknown one left out, never refused; `/bank-lines/count` with the
    same ids agreeing; beside `account_id` only the named lines on that account; read
    through the app's own `fetch_bank_lines_by_ids` and `count_bank_lines` too;
  · its refusals, on the list and the count: beside `unassigned_in_period_of`
    `CONFLICTING_PARAMETERS` on `unassigned_in_period_of`; 200 entries taken and 201
    `OUT_OF_RANGE` on `ids`, a repeated id counted twice; an empty `ids`, an empty entry
    and a non-UUID entry `INVALID_FORMAT` on `ids`;
  · `?sort=date_asc`: the newest-first list read backwards, line for line, beside `ids`
    too; paged by cursors of its own, which no other order takes and which take no
    other order's (contract: GET /v1/bank-lines, "Ordering").

The same order beside a statement (`reconciliation_id`, `unassigned_in_period_of`) is in
test_statement_order.py. Each test builds its own accounts and undoes everything
(conftest.py `scratch`). Gating, target and the real-ledger guard: conftest.py.
"""

from uuid import uuid4

from expense.reads import count_bank_lines, fetch_bank_lines, fetch_bank_lines_by_ids
from tests.contract.conftest import assert_refusal, refused


def _listed(client, **params) -> list[str]:
    return [line["id"] for line in client.get("/bank-lines", params=params)["items"]]


def _counted(client, **params) -> int:
    return client.get("/bank-lines/count", params=params)["count"]


def _joined(ids: list[str]) -> str:
    return ",".join(ids)


def test_ids_list_the_live_lines_among_them_and_the_count_agrees(client, target, scratch):
    """`?ids=` lists the live lines among the ids sent, each in the list's shape (exactly
    `GET /bank-lines/{id}`), newest first whatever order the ids go in; a deleted line's
    id and an unknown id match nothing and are never refused; the count agrees; beside
    `account_id` only the named lines on that account are listed
    (contract: GET /v1/bank-lines, "Left out, never refused")
    (contract: GET /v1/bank-lines/count). The app's own reads see the same lines, oldest
    first on request (contract: GET /v1/bank-lines, "Ordering")."""
    account = scratch.account()
    other = scratch.account()
    a1 = scratch.line(account, "2026-03-05", -1000)
    b1 = scratch.line(other, "2026-03-06", -2000)
    a2 = scratch.line(account, "2026-03-07", -600, -400)
    a3 = scratch.line(account, "2026-03-09", 3000)
    gone = scratch.line(account, "2026-03-08", -500)
    client.delete(f"/bank-lines/{gone}")
    unknown = str(uuid4())
    sent = [a3, unknown, a1, b1, gone, a2]
    newest_first = [a3, a2, b1, a1]

    body = client.get("/bank-lines", params={"ids": _joined(sent)})
    assert [line["id"] for line in body["items"]] == newest_first
    assert body["next_cursor"] is None
    for line in body["items"]:
        assert line == client.get(f"/bank-lines/{line['id']}")
    (split,) = [line for line in body["items"] if line["id"] == a2]
    assert (split["part_count"], split["net_cents"]) == (2, -1000)
    assert _counted(client, ids=_joined(sent)) == len(newest_first)

    # Another order of the ids, or one repeated, is the same filter.
    for again in (list(reversed(sent)), [*sent, a1, a1]):
        assert _listed(client, ids=_joined(again)) == newest_first
        assert _counted(client, ids=_joined(again)) == len(newest_first)

    # Only the ids naming no live line: nothing listed, nothing refused.
    assert _listed(client, ids=_joined([gone, unknown])) == []
    assert _counted(client, ids=_joined([gone, unknown])) == 0

    # The filters combine: the named lines on that account.
    on_account = {"ids": _joined(sent), "account_id": account}
    assert _listed(client, **on_account) == [a3, a2, a1]
    assert _counted(client, **on_account) == 3

    # Through the app's own reads, as the flagged lines' screen reads them.
    assert [line["id"] for line in fetch_bank_lines_by_ids(target, sent)] == newest_first
    oldest_first = fetch_bank_lines_by_ids(target, sent, sort="date_asc")
    assert [line["id"] for line in oldest_first] == newest_first[::-1]
    assert count_bank_lines(target, ids=sent) == len(newest_first)
    assert count_bank_lines(target, ids=sent, account=account) == 3


def test_ids_refusals(client, scratch):
    """`ids` beside `unassigned_in_period_of` is `422` `CONFLICTING_PARAMETERS` on
    `unassigned_in_period_of` (contract: GET /v1/bank-lines, "Taken alone"); at most 200
    entries, a repeated id counting twice, so 201 is `OUT_OF_RANGE` on `ids`
    (contract: GET /v1/bank-lines, "At most 200 ids"); an empty `ids`, an empty entry and
    an entry that is not a UUID are `INVALID_FORMAT` on `ids`
    (contract: GET /v1/bank-lines, "Filters"). The count refuses each the same way
    (contract: GET /v1/bank-lines/count)."""
    account = scratch.account()
    line = scratch.line(account, "2026-03-05", -1000)
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    two_hundred = [line, *(str(uuid4()) for _ in range(199))]

    assert _listed(client, ids=_joined(two_hundred), limit=200) == [line]
    assert _counted(client, ids=_joined(two_hundred)) == 1
    beside = "unassigned_in_period_of"
    for params, key, reason in (
        ({"ids": line, beside: recon}, beside, "CONFLICTING_PARAMETERS"),
        ({"ids": _joined([*two_hundred, str(uuid4())])}, "ids", "OUT_OF_RANGE"),
        ({"ids": _joined([*two_hundred, line])}, "ids", "OUT_OF_RANGE"),
        ({"ids": ""}, "ids", "INVALID_FORMAT"),
        ({"ids": f"{line},"}, "ids", "INVALID_FORMAT"),
        ({"ids": f"{line},not-a-uuid"}, "ids", "INVALID_FORMAT"),
    ):
        for path in ("/bank-lines", "/bank-lines/count"):
            err = refused(lambda path=path, params=params: client.get(path, params=params))
            assert_refusal(err, 422, "VALIDATION_ERROR", key, reason)


def _pages(client, **params) -> list[list[str]]:
    """Every page of the list under `params`, each by its line ids, following the cursors."""
    pages, after = [], None
    while True:
        page = client.get("/bank-lines", params={**params, **({"after": after} if after else {})})
        pages.append([line["id"] for line in page["items"]])
        after = page["next_cursor"]
        if after is None:
            return pages


def test_date_asc_is_the_newest_first_list_reversed_with_its_own_cursors(client, target, scratch):
    """`?sort=date_asc` lists the lines oldest first, the newest-first list read
    backwards, line for line, a split line whole; a small `limit` pages it through its
    own cursors to the whole list; a `date_asc` cursor is `422` `INVALID_CURSOR` on
    `after` without `sort` or with `sort=date_desc`, and a newest-first cursor with
    `sort=date_asc` (contract: GET /v1/bank-lines, "Ordering")
    (contract: GET /v1/bank-lines, "Paging is by cursor")."""
    account = scratch.account()
    d10 = scratch.line(account, "2026-03-10", -100)
    d02 = scratch.line(account, "2026-03-02", -200)
    d07 = scratch.line(account, "2026-03-07", -300, -400)
    d15 = scratch.line(account, "2026-03-15", 500)
    d04 = scratch.line(account, "2026-03-04", -600)
    oldest_first = [d02, d04, d07, d10, d15]

    assert _listed(client, account_id=account, sort="date_asc") == oldest_first
    assert _listed(client, account_id=account) == oldest_first[::-1]
    assert _listed(client, account_id=account, sort="date_desc") == oldest_first[::-1]
    read = fetch_bank_lines(target, account=account, sort="date_asc")
    assert [line["id"] for line in read["items"]] == oldest_first
    (split,) = [line for line in read["items"] if line["id"] == d07]
    assert split["part_count"] == 2

    # Beside ids: the same order among the lines named.
    named = _joined([d15, d02, d10])
    assert _listed(client, ids=named, sort="date_asc") == [d02, d10, d15]

    pages = _pages(client, account_id=account, sort="date_asc", limit=2)
    assert [len(page) for page in pages] == [2, 2, 1]
    assert [line for page in pages for line in page] == oldest_first

    asc_cursor = client.get(
        "/bank-lines", params={"account_id": account, "sort": "date_asc", "limit": 1}
    )["next_cursor"]
    desc_cursor = client.get("/bank-lines", params={"account_id": account, "limit": 1})[
        "next_cursor"
    ]
    rest = client.get(
        "/bank-lines", params={"account_id": account, "sort": "date_asc", "after": asc_cursor}
    )
    assert [line["id"] for line in rest["items"]] == oldest_first[1:]
    for params in (
        {"account_id": account, "after": asc_cursor},
        {"account_id": account, "sort": "date_desc", "after": asc_cursor},
        {"account_id": account, "sort": "date_asc", "after": desc_cursor},
    ):
        err = refused(lambda params=params: client.get("/bank-lines", params=params))
        assert_refusal(err, 422, "VALIDATION_ERROR", "after", "INVALID_CURSOR")
