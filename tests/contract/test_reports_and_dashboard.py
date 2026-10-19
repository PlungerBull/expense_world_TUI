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

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from expense.errors import EngineError
from expense.reads import pending_hashtag_of


def _safe_delete(client, path):
    try:
        client.delete(path)
    except EngineError:
        pass


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds").replace("+00:00", "Z")


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


def test_dashboard_accounts_carry_their_own_currency_and_balance(client):
    """Home draws every balance in the account's *own* currency
    — which only works while the row says which currency that is."""
    account_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": account_id,
            "name": f"contract-dash-{account_id[:8]}",
            "currency_code": "USD",
        },
    )
    try:
        body = client.get("/dashboard")
        row = next((a for a in body["bank_accounts"] if a["id"] == account_id), None)
        assert row is not None, "a live account is missing from /dashboard"
        assert row["currency_code"] == "USD"
        assert isinstance(row["current_balance_cents"], int)
    finally:
        _safe_delete(client, f"/accounts/{account_id}")


def test_dashboard_keeps_archived_accounts_in_their_own_section(client):
    """`include_archived` is a parameter here. An archived account is real
    (docs/decisions.md "Archive is a prompt-free toggle"), so the row still
    exists when asked for — but it does **not** rejoin `bank_accounts`.

    The engine answers with a separate `archived_accounts` list — **null** until
    the flag is passed, never an empty list. Both halves matter:

      · separate, because a retired account must never be summed with the live
        ones; a client that merged the lists would overstate every balance.
      · null rather than `[]`, because that is how a reader tells "you did not
        ask" from "you asked and there are none" — which is exactly the
        difference a client uses to decide whether to draw the panel at
        all (`if archived_accounts is not None`).

    Assuming the merge, or an empty list, and iterating the null is precisely
    how a second client would meet this.
    """
    account_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": account_id,
            "name": f"contract-arch-{account_id[:8]}",
            "currency_code": "PEN",
        },
    )
    try:
        client.post(f"/accounts/{account_id}/archive")

        default = client.get("/dashboard")
        assert not any(a["id"] == account_id for a in default["bank_accounts"])
        assert default["archived_accounts"] is None  # not asked for

        asked = client.get("/dashboard", params={"include_archived": "true"})
        assert not any(a["id"] == account_id for a in asked["bank_accounts"])
        assert any(a["id"] == account_id for a in asked["archived_accounts"])
    finally:
        _safe_delete(client, f"/accounts/{account_id}")


# ---------------------------------------------------------------------------
# /reports/monthly
# ---------------------------------------------------------------------------


def test_single_month_report_has_the_keys_the_table_renders(client):
    now = _now()
    body = client.get("/reports/monthly", params={"year": str(now.year), "month": str(now.month)})

    assert body["month"] == {"year": now.year, "month": now.month}
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


def test_a_category_row_carries_its_hashtag_breakdown(client):
    """Home folds hashtag rows under their category and `⏎` filters the ledger
    by the pair. The nesting IS the feature: a flat list of hashtag totals could
    not be attributed to a category at all.

    Asserted structurally — the practice user's history is not fixed.
    """
    now = _now()
    body = client.get("/reports/monthly", params={"year": str(now.year), "month": str(now.month)})
    for category in body["categories"]:
        assert {"id", "name", "spent_home_cents", "unconverted_count"} <= category.keys()
        assert isinstance(category["hashtag_breakdown"], list)
        for slice_ in category["hashtag_breakdown"]:
            assert isinstance(slice_["hashtag_ids"], list)
            assert isinstance(slice_["spent_home_cents"], int)


def test_a_months_categories_sum_to_its_net(client):
    """The one arithmetic claim worth making against real data.

    Home prints a per-category column and a `net` line from the same payload; if
    they are computed from different row sets, the screen contradicts itself. A
    transaction created here guarantees there is something to add up.
    """
    now = _now()
    account_id = str(uuid4())
    tx_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": account_id,
            "name": f"contract-sum-{account_id[:8]}",
            "currency_code": "PEN",
        },
    )
    try:
        client.post(
            "/transactions",
            json_body={
                "id": tx_id,
                "title": "report row",
                "amount_cents": -3300,
                "account_id": account_id,
                "date": _now_iso(),
            },
        )
        body = client.get(
            "/reports/monthly", params={"year": str(now.year), "month": str(now.month)}
        )
        if body["totals"]["unconverted_count"]:
            pytest.skip("unconverted rows in the month — the totals are not comparable")

        assert (
            sum(c["spent_home_cents"] for c in body["categories"])
            == (body["totals"]["net_home_cents"])
        )
    finally:
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_an_uncategorised_row_lands_under_pendiente_and_counts(client):
    """A row with no category
    is a real ledger row that shows up in the month's figures.

    The unit suite asserts Home *draws* `@Pendiente`; only the engine can say a
    category-less transaction actually files there and is actually counted.
    """
    now = _now()
    account_id = str(uuid4())
    tx_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": account_id,
            "name": f"contract-pend-{account_id[:8]}",
            "currency_code": "PEN",
        },
    )
    try:
        created = client.post(
            "/transactions",
            json_body={
                "id": tx_id,
                "title": "no category",
                "amount_cents": -4400,
                "account_id": account_id,
                "date": _now_iso(),
            },
        )
        assert created["id"] == tx_id  # accepted without a category at all

        body = client.get(
            "/reports/monthly", params={"year": str(now.year), "month": str(now.month)}
        )
        pendiente = next((c for c in body["categories"] if c["name"] == "@Pendiente"), None)
        assert pendiente is not None, "the month has no @Pendiente row"
        assert pendiente["spent_home_cents"] != 0
    finally:
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/accounts/{account_id}")


def test_a_row_waiting_for_a_hashtag_is_its_categorys_pending_hashtag_row(client):
    """Home's pending row stands on this: a row written with no hashtag counts
    in its category's breakdown as the `[<pending id>]` row, never as an empty
    `hashtag_ids` (contract: GET /v1/dashboard), and `⏎` on that row asks for the
    same category and `hashtag_id=<pending id>`, whose list and count are that
    row (contract: GET /v1/transactions). The pending hashtag is found by
    `system_key`, never by name.
    """
    now = _now()
    account_id = str(uuid4())
    category_id = str(uuid4())
    tx_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": account_id,
            "name": f"contract-ph-{account_id[:8]}",
            "currency_code": "PEN",
        },
    )
    client.post(
        "/categories",
        json_body={"id": category_id, "name": f"contract-ph-{category_id[:8]}", "color": "#123456"},
    )
    try:
        client.post(
            "/transactions",
            json_body={
                "id": tx_id,
                "title": "waits for a hashtag",
                "amount_cents": -2100,
                "account_id": account_id,
                "category_id": category_id,
                "date": _now_iso(),
            },
        )
        pending = pending_hashtag_of(client.get("/hashtags")["items"])
        assert pending is not None, "an untagged write did not make the pending hashtag exist"

        body = client.get(
            "/reports/monthly", params={"year": str(now.year), "month": str(now.month)}
        )
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
    finally:
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/categories/{category_id}")
        _safe_delete(client, f"/accounts/{account_id}")


# ---------------------------------------------------------------------------
# the sign convention
# ---------------------------------------------------------------------------


def test_a_write_is_signed_but_a_bare_read_is_not(client):
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
    account_id = str(uuid4())
    tx_id = str(uuid4())
    client.post(
        "/accounts",
        json_body={
            "id": account_id,
            "name": f"contract-sign-{account_id[:8]}",
            "currency_code": "PEN",
        },
    )
    try:
        created = client.post(
            "/transactions",
            json_body={
                "id": tx_id,
                "title": "an expense",
                "amount_cents": -1200,  # signed going in
                "account_id": account_id,
                "date": _now_iso(),
            },
        )
        assert created["amount_cents"] == 1200  # magnitude coming back

        bare = client.get(f"/transactions/{tx_id}")
        assert bare["amount_cents"] == 1200

        asked = client.get(f"/transactions/{tx_id}", params={"debit_as_negative": "true"})
        assert asked["amount_cents"] == -1200
    finally:
        _safe_delete(client, f"/transactions/{tx_id}")
        _safe_delete(client, f"/accounts/{account_id}")
