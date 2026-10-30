"""Contract coverage for the two aggregate reads: /dashboard and /reports/monthly.

These are the only endpoints the app does not merely relay — Home and the range
grid do arithmetic *on top of* their shape (four months side by side, a hashtag
breakdown folded under each category, balances in each account's own currency).
Every fixture behind that arithmetic is one we wrote, so the unit suite proves
the grid renders `HOME_MONTHS` correctly and nothing more. If the engine renames
`spent_home_cents` or stops nesting `hashtag_breakdown`, 1232 unit tests stay
green and Home draws zeros.

So these tests assert *shape*, not values: the keys the renderers index by, the
nesting they walk, and the one number that has to agree with the rows it came
from. The practice user holds whatever earlier runs left, so a test that
depended on its contents would depend on run order.

Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from expense.reads import pending_hashtag_of

from .conftest import Scratch


def _a_minute_ago(scratch: Scratch) -> str:
    """A moment just past, in the caller's display timezone, the zone the month is cut in
    (contract: GET /v1/dashboard, "Field rules"); a transaction may not be dated ahead."""
    past = datetime.now(scratch.zone) - timedelta(minutes=1)
    return past.isoformat(timespec="seconds")


def _month(scratch: Scratch) -> dict[str, str]:
    now = datetime.now(scratch.zone)
    return {"year": str(now.year), "month": str(now.month)}


def _spend(scratch: Scratch, account_id: str, amount: int, **fields: str) -> str:
    """A signed transaction of today in the account's PEN, written whole; its id."""
    tx_id = str(uuid4())
    scratch.transactions.append(tx_id)
    scratch.client.post(
        "/transactions",
        json_body={
            "id": tx_id,
            "title": "report row",
            "amount_cents": amount,
            "account_id": account_id,
            "currency_code": "PEN",
            "date": _a_minute_ago(scratch),
            **fields,
        },
    )
    return tx_id


def _row(rows: list[dict] | None, account_id: str) -> dict:
    assert rows is not None, "the section is null"
    found = [r for r in rows if r["id"] == account_id]
    assert len(found) == 1, "an account is not exactly one row"
    return found[0]


def _balances(row: dict) -> dict[str, int]:
    return {c["currency_code"]: c["current_balance_cents"] for c in row["currencies"]}


def _assert_row_shape(row: dict) -> None:
    """`{id, name, currencies}`, each currency `{currency_code, current_balance_cents}`,
    and no home-currency value anywhere on it
    (contract: GET /v1/dashboard, "Balances are native only")."""
    assert row.keys() == {"id", "name", "currencies"}
    codes = [c["currency_code"] for c in row["currencies"]]
    assert codes == sorted(codes), "currencies are not by code ascending"
    for currency in row["currencies"]:
        assert currency.keys() == {"currency_code", "current_balance_cents"}
        assert isinstance(currency["current_balance_cents"], int)


# ---------------------------------------------------------------------------
# /dashboard
# ---------------------------------------------------------------------------


def test_dashboard_has_the_sections_home_indexes_by(client):
    """`fetch_dashboard` feeds Home.

    Home indexes these sections by name and would render an empty panel, not
    an error, if one were renamed — the silent failure this test exists to make
    loud.
    """
    body = client.get("/dashboard")

    for key in (
        "month",
        "bank_accounts",
        "people",
        "archived_accounts",
        "archived_people",
        "categories",
        "totals",
    ):
        assert key in body, f"/dashboard lost `{key}` — Home indexes it by name"

    # Null-over-omission: the two archived sections are present and null rather
    # than absent, which is what lets the renderer tell "not asked for" from
    # "asked for, and there are none".
    assert body["archived_accounts"] is None
    assert body["archived_people"] is None

    assert {"year", "month"} <= body["month"].keys()
    assert isinstance(body["bank_accounts"], list)
    assert isinstance(body["people"], list)
    assert isinstance(body["categories"], list)
    assert {"net_home_cents", "unconverted_count"} <= body["totals"].keys()
    for row in body["bank_accounts"] + body["people"]:
        _assert_row_shape(row)


def test_a_two_currency_account_and_person_are_one_row_each_with_a_balance_per_currency(
    client, scratch
):
    """Home draws one row per account and a balance per currency under it, each in its
    own currency (contract: GET /v1/dashboard, "`bank_accounts`"); a client that kept the
    old one-currency row would show one of the two balances and call it the account's."""
    card = scratch.account("PEN", "USD")
    friend = scratch.account("PEN", "USD", person=True)
    scratch.opening_balance(card, "2026-01-01", "PEN")
    scratch.opening_balance(card, "2026-01-01", "USD")
    scratch.opening_balance(friend, "2026-01-01", "USD")
    _spend(scratch, card, -1200)

    body = client.get("/dashboard")

    card_row = _row(body["bank_accounts"], card)
    _assert_row_shape(card_row)
    assert _balances(card_row) == {"PEN": 50000 - 1200, "USD": 50000}
    friend_row = _row(body["people"], friend)
    _assert_row_shape(friend_row)
    assert _balances(friend_row) == {"PEN": 0, "USD": 50000}
    assert not any(r["id"] == friend for r in body["bank_accounts"])
    assert not any(r["id"] == card for r in body["people"])


def test_the_rows_come_in_the_accounts_order(client, scratch):
    """Rows follow `GET /accounts` (`sort_order`, then creation time) for bank accounts and
    for people alike (contract: GET /v1/dashboard, "`people`")."""
    banks = [scratch.account(), scratch.account("USD"), scratch.account("PEN", "USD")]
    people = [scratch.account(person=True), scratch.account("USD", person=True)]

    body = client.get("/dashboard")
    listed = client.get("/accounts", params={"include_people": "true"})["items"]

    for section, mine in ((body["bank_accounts"], banks), (body["people"], people)):
        order = [r["id"] for r in section if r["id"] in mine]
        assert sorted(order) == sorted(mine)
        assert order == [a["id"] for a in listed if a["id"] in mine]


def test_a_removed_currency_is_not_listed(client, scratch):
    """A row lists the account's live currencies only
    (contract: GET /v1/dashboard, "`bank_accounts`")."""
    account_id = scratch.account("PEN", "USD")
    assert set(_balances(_row(client.get("/dashboard")["bank_accounts"], account_id))) == {
        "PEN",
        "USD",
    }

    client.delete(f"/accounts/{account_id}/currencies/USD")

    row = _row(client.get("/dashboard")["bank_accounts"], account_id)
    assert _balances(row) == {"PEN": 0}


def test_an_archived_account_moves_whole_to_its_own_section(client, scratch):
    """`include_archived` is a parameter here. An archived account is real
    (docs/decisions.md "Archive is a prompt-free toggle"), so the row still
    exists when asked for — but it does **not** rejoin `bank_accounts`, and it moves
    with every currency in it (contract: GET /v1/dashboard, "`?include_archived=true`").

    The engine answers with a separate `archived_accounts` list — **null** until
    the flag is passed, never an empty list. Both halves matter:

      · separate, because a retired account must never be summed with the live
        ones; a client that merged the lists would overstate every balance.
      · null rather than `[]`, because that is how a reader tells "you did not
        ask" from "you asked and there are none" — which is exactly the
        difference a client uses to decide whether to draw the panel at
        all (`if archived_accounts is not None`).
    """
    account_id = scratch.account("PEN", "USD")
    friend = scratch.account("PEN", "USD", person=True)
    scratch.opening_balance(account_id, "2026-01-01", "USD")
    scratch.opening_balance(friend, "2026-01-01", "PEN")
    scratch.archive(account_id)
    scratch.archive(friend)

    default = client.get("/dashboard")
    assert not any(r["id"] == account_id for r in default["bank_accounts"])
    assert not any(r["id"] == friend for r in default["people"])
    assert default["archived_accounts"] is None  # not asked for
    assert default["archived_people"] is None

    asked = client.get("/dashboard", params={"include_archived": "true"})
    assert not any(r["id"] == account_id for r in asked["bank_accounts"])
    assert not any(r["id"] == friend for r in asked["people"])
    archived = _row(asked["archived_accounts"], account_id)
    _assert_row_shape(archived)
    assert _balances(archived) == {"PEN": 0, "USD": 50000}
    archived_person = _row(asked["archived_people"], friend)
    _assert_row_shape(archived_person)
    assert _balances(archived_person) == {"PEN": 50000, "USD": 0}

    client.post(f"/accounts/{account_id}/unarchive")
    back = client.get("/dashboard", params={"include_archived": "true"})
    assert _balances(_row(back["bank_accounts"], account_id)) == {"PEN": 0, "USD": 50000}
    assert not any(r["id"] == account_id for r in back["archived_accounts"])


def test_the_aggregates_are_home_currency_with_an_unconverted_count(client, scratch):
    """Categories and totals stay in the home currency, each figure paired with its
    `unconverted_count`, and `@Opening` is not among the categories
    (contract: GET /v1/dashboard, "Aggregates are home-currency only")."""
    account_id = scratch.account("PEN", "USD")
    scratch.opening_balance(account_id, "2026-01-01", "USD")
    _spend(scratch, account_id, -1200)

    body = client.get("/dashboard")

    assert {
        "inflow_home_cents",
        "outflow_home_cents",
        "net_home_cents",
        "unconverted_count",
    } <= body["totals"].keys()
    assert "@Opening" not in [c["name"] for c in body["categories"]]
    for category in body["categories"]:
        assert {"id", "name", "spent_home_cents", "unconverted_count"} <= category.keys()
        assert "spent_cents" not in category
        if category["unconverted_count"]:
            assert category["spent_home_cents"] is None


# ---------------------------------------------------------------------------
# /reports/monthly
# ---------------------------------------------------------------------------


def test_single_month_report_has_the_keys_the_table_renders(client, scratch):
    params = _month(scratch)
    body = client.get("/reports/monthly", params=params)

    assert body["month"] == {"year": int(params["year"]), "month": int(params["month"])}
    assert isinstance(body["categories"], list)
    assert {
        "inflow_home_cents",
        "outflow_home_cents",
        "net_home_cents",
        "unconverted_count",
    } <= body["totals"].keys()


def test_range_report_returns_one_entry_per_month_in_order(client):
    """Home's grid walks `months` positionally — four columns, oldest first.

    A range that came back unordered, or short, would silently shift every
    figure one column left.
    """
    body = client.get(
        "/reports/monthly",
        params={
            "from_year": "2026",
            "from_month": "1",
            "to_year": "2026",
            "to_month": "4",
        },
    )
    months = body["months"]
    assert [m["month"] for m in months] == [
        {"year": 2026, "month": 1},
        {"year": 2026, "month": 2},
        {"year": 2026, "month": 3},
        {"year": 2026, "month": 4},
    ]


def test_a_category_row_carries_its_hashtag_breakdown(client, scratch):
    """Home folds hashtag rows under their category and `⏎` filters the ledger
    by the pair. The nesting IS the feature: a flat list of hashtag totals could
    not be attributed to a category at all.

    Asserted structurally — the practice user's history is not fixed.
    """
    body = client.get("/reports/monthly", params=_month(scratch))
    for category in body["categories"]:
        assert {"id", "name", "spent_home_cents", "unconverted_count"} <= category.keys()
        assert isinstance(category["hashtag_breakdown"], list)
        for slice_ in category["hashtag_breakdown"]:
            assert isinstance(slice_["hashtag_ids"], list)
            assert isinstance(slice_["spent_home_cents"], int)


def test_a_months_categories_sum_to_its_net(client, scratch):
    """The one arithmetic claim worth making against real data.

    Home prints a per-category column and a `net` line from the same payload; if
    they are computed from different row sets, the screen contradicts itself. A
    transaction created here guarantees there is something to add up.
    """
    account_id = scratch.account()
    _spend(scratch, account_id, -3300)

    body = client.get("/reports/monthly", params=_month(scratch))
    if body["totals"]["unconverted_count"]:
        pytest.skip("unconverted rows in the month — the totals are not comparable")

    assert (
        sum(c["spent_home_cents"] for c in body["categories"]) == body["totals"]["net_home_cents"]
    )


def test_an_uncategorised_row_lands_under_pendiente_and_counts(client, scratch):
    """A row with no category
    is a real ledger row that shows up in the month's figures.

    The unit suite asserts Home *draws* `@Pendiente`; only the engine can say a
    category-less transaction actually files there and is actually counted.
    """
    account_id = scratch.account()
    tx_id = _spend(scratch, account_id, -4400)
    assert client.get(f"/transactions/{tx_id}")["id"] == tx_id  # accepted without a category

    body = client.get("/reports/monthly", params=_month(scratch))
    pendiente = next((c for c in body["categories"] if c["name"] == "@Pendiente"), None)
    assert pendiente is not None, "the month has no @Pendiente row"
    assert pendiente["spent_home_cents"] != 0


def test_a_row_waiting_for_a_hashtag_is_its_categorys_pending_hashtag_row(client, scratch):
    """Home's pending row stands on this: a row written with no hashtag counts
    in its category's breakdown as the `[<pending id>]` row, never as an empty
    `hashtag_ids` (contract: GET /v1/dashboard, "`hashtag_breakdown`"), and `⏎` on that
    row asks for the same category and `hashtag_id=<pending id>`, whose list and count are
    that row (contract: GET /v1/transactions). The pending hashtag is found by
    `system_key`, never by name.
    """
    account_id = scratch.account()
    category_id = scratch.category()
    tx_id = _spend(scratch, account_id, -2100, category_id=category_id)
    pending = pending_hashtag_of(client.get("/hashtags")["items"])
    assert pending is not None, "an untagged write did not make the pending hashtag exist"

    body = client.get("/reports/monthly", params=_month(scratch))
    for category in body["categories"]:
        for slice_ in category["hashtag_breakdown"]:
            assert slice_["hashtag_ids"], f"an empty hashtag row under {category['name']}"
    mine = next(c for c in body["categories"] if c["id"] == category_id)
    assert [s["hashtag_ids"] for s in mine["hashtag_breakdown"]] == [[pending[0]]]
    assert mine["hashtag_breakdown"][0]["spent_home_cents"] == -2100

    params = {"category_id": category_id, "hashtag_id": pending[0]}
    listed = client.get("/transactions", params=params)
    assert [item["id"] for item in listed["items"]] == [tx_id]
    assert client.get("/transactions/count", params=params)["count"] == 1


# ---------------------------------------------------------------------------
# the sign convention
# ---------------------------------------------------------------------------


def test_a_write_is_signed_but_a_bare_read_is_not(client, scratch):
    """`debit_as_negative` is a *read* preference; the write is always signed.

    CLAUDE.md calls the sign convention shared infrastructure — "input and
    output are both signed" is the contract the app presents, and it is the app
    that makes the output half true by asking for it. The engine stores the
    magnitude and signs on request.

    Asserting `-9999` on a bare read gets `9999` — wrong in exactly the way a
    second client would be wrong on its first afternoon. Web and iOS
    inherit this endpoint; the asymmetry should be written down somewhere that
    fails when it changes.
    """
    account_id = scratch.account()
    tx_id = _spend(scratch, account_id, -1200)  # signed going in

    bare = client.get(f"/transactions/{tx_id}")
    assert bare["amount_cents"] == 1200  # magnitude coming back

    asked = client.get(f"/transactions/{tx_id}", params={"debit_as_negative": "true"})
    assert asked["amount_cents"] == -1200
