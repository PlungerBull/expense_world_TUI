"""Direct unit tests for the shared reads (expense/reads.py) and formatters
(expense/formatting.py) the TUI is drawn from.

Covers: the cents and nullable-aggregate formatters, the live reference
lookups, the cursor-paged transaction reads and their count, the People fold,
and the quick-add reference lists.
"""

import httpx
import pytest
import respx

from expense import config as config_module
from expense.errors import EngineError
from expense.formatting import (
    bank_line_part_count,
    format_aggregate,
    format_cents,
    format_hashtag_cell,
    format_month,
    has_aggregate,
    redact_token,
    settled_label,
    signed_cents,
    split_settled,
    whole_number,
)
from expense.reads import (
    account_choices,
    fetch_all_cursor_pages,
    fetch_body,
    hashtags_to_send,
    items_of,
    load_account_index,
    load_account_name_map,
    load_category_name_map,
    load_hashtag_name_map,
    load_quickadd_refs,
    query_params,
)
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import cursor_page, error_response, whole

# ---------------------------------------------------------------------------
# format_cents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (651900, "6,519.00"),
        (-418797, "-4,187.97"),
        (-1027202, "-10,272.02"),
        (-800, "-8.00"),
        (0, "0.00"),
        (5, "0.05"),
        (-1, "-0.01"),
        (99, "0.99"),
        (None, "(null)"),
    ],
)
def test_format_cents(value, expected):
    assert format_cents(value) == expected


def test_format_cents_non_int_falls_back_to_str():
    # Booleans are an int subclass but are never amounts — keep them literal.
    assert format_cents(True) == "True"
    assert format_cents("n/a") == "n/a"


def test_signed_cents_reads_the_sign_off_the_type():
    """An unsigned transaction response — a magnitude and `transaction_type`,
    1 out and 2 in (contract: "Base Conventions", "Sign convention — responses")
    — signed the app's way."""
    assert signed_cents({"amount_cents": 2590, "transaction_type": 1}) == -2590
    assert signed_cents({"amount_cents": 5000, "transaction_type": 2}) == 5000


# ---------------------------------------------------------------------------
# format_aggregate / has_aggregate — the nullable home aggregates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "count", "expected"),
    [
        (-50000, 0, "-500.00"),  # a present figure formats as any amount does
        (0, 0, "0.00"),  # a real zero is a real zero
        (-50000, 3, "-500.00"),  # a figure wins over a stale count
        (None, 3, "3 unrated"),  # the engine refused to report a partial total
        (None, 1, "1 unrated"),
        (None, 0, "(null)"),  # null with no count is just missing data
        (None, None, "(null)"),
        (None, "3", "(null)"),  # a non-int count is not a count
        (None, True, "(null)"),  # bool is an int subclass but never a count
    ],
)
def test_format_aggregate(value, count, expected):
    assert format_aggregate(value, count) == expected


def test_format_aggregate_never_renders_a_null_as_zero():
    """The whole point: `null` is not `0`, and never falls back to a native figure."""
    rendered = format_aggregate(None, 3)
    assert "0.00" not in rendered
    assert rendered == "3 unrated"


@pytest.mark.parametrize(
    ("value", "count", "shown"),
    [
        (-50000, 0, True),  # spent something
        (50000, 0, True),  # earned something
        (0, 0, False),  # nothing spent — not drawn
        (None, 0, False),  # nothing to say at all
        (None, 3, True),  # unpriceable is NOT empty; it keeps its row
        (0, 2, True),  # a count always wins
        (True, 0, False),  # bool is not an amount
    ],
)
def test_has_aggregate(value, count, shown):
    assert has_aggregate(value, count) is shown


# ---------------------------------------------------------------------------
# format_month
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"year": 2026, "month": 7}, "2026-07"),
        ({"year": 2026, "month": 12}, "2026-12"),
        ({"year": 2026}, "(unknown)"),
        ({"year": "2026", "month": "7"}, "(unknown)"),
        (None, "(unknown)"),
    ],
)
def test_format_month(value, expected):
    assert format_month(value) == expected


# ---------------------------------------------------------------------------
# fetch_body
# ---------------------------------------------------------------------------


@respx.mock
def test_fetch_body_issues_one_live_get(configured):
    from expense import config as config_module

    route = respx.get(f"{BASE}/v1/things", params={"limit": "5"}).mock(
        return_value=httpx.Response(200, json=whole([{"id": "a"}]))
    )
    body = fetch_body(
        config_module.ensure_loaded(),
        path="/things",
        params={"limit": 5},
        verbose=False,
    )
    assert body == whole([{"id": "a"}])
    assert route.call_count == 1


@respx.mock
def test_fetch_body_empty_params_sends_no_query(configured):
    from expense import config as config_module

    route = respx.get(f"{BASE}/v1/things").mock(return_value=httpx.Response(200, json=whole([])))
    fetch_body(config_module.ensure_loaded(), path="/things", params={}, verbose=False)
    assert route.calls.last.request.url.query == b""


# ---------------------------------------------------------------------------
# load_*_name_map — live reference lookups, `{}` on any failure
# ---------------------------------------------------------------------------


def _list_body(items: list[dict]) -> httpx.Response:
    return httpx.Response(200, json=whole(items))


@respx.mock
def test_load_account_name_map_fetches_live_with_archived_and_people(configured):
    route = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=_list_body([{"id": "a1", "name": "BCP"}, {"id": "p1", "name": "Mom"}])
    )
    assert load_account_name_map() == {"a1": "BCP", "p1": "Mom"}

    params = route.calls.last.request.url.params
    assert params["include_archived"] == "true"
    assert params["include_people"] == "true"
    assert "limit" not in params and "offset" not in params


@respx.mock
def test_load_account_index_gives_names_and_archived_ids_from_one_read(configured):
    """One `GET /accounts?include_archived=true&include_people=true` gives every
    name and the ids whose `is_archived` is true (contract: GET /v1/accounts)."""
    route = respx.get(f"{BASE}/v1/accounts").mock(
        return_value=_list_body(
            [
                {"id": "a1", "name": "BCP", "is_archived": False, "is_person": False},
                {"id": "a2", "name": "Ahorro viejo", "is_archived": True, "is_person": False},
                {"id": "p1", "name": "Mom", "is_archived": False, "is_person": True},
            ]
        )
    )
    index = load_account_index()
    assert index.names == {"a1": "BCP", "a2": "Ahorro viejo", "p1": "Mom"}
    assert index.archived == {"a2"}
    assert route.call_count == 1
    params = route.calls.last.request.url.params
    assert params["include_archived"] == "true" and params["include_people"] == "true"


def test_load_account_index_without_config_is_empty():
    """No engine to ask: no names and no archived ids, so no key is taken away."""
    index = load_account_index()
    assert index.names == {} and index.archived == frozenset()


@respx.mock
def test_load_category_name_map_fetches_live(configured):
    route = respx.get(f"{BASE}/v1/categories").mock(
        return_value=_list_body([{"id": "c1", "name": "Food"}])
    )
    assert load_category_name_map() == {"c1": "Food"}
    assert "include_archived" not in route.calls.last.request.url.params


@respx.mock
def test_load_hashtag_name_map_fetches_live(configured):
    route = respx.get(f"{BASE}/v1/hashtags").mock(
        return_value=_list_body([{"id": "h1", "name": "trabajo"}])
    )
    assert load_hashtag_name_map() == {"h1": "trabajo"}
    assert "include_archived" not in route.calls.last.request.url.params


@respx.mock
def test_load_name_map_is_one_read_of_the_whole_list(configured):
    """The engine returns the list whole and refuses `limit`/`offset`."""
    rows = [{"id": f"c{i}", "name": f"n{i}"} for i in range(201)]
    route = respx.get(f"{BASE}/v1/categories").mock(return_value=_list_body(rows))
    out = load_category_name_map()
    assert len(out) == 201
    assert route.call_count == 1
    params = route.calls.last.request.url.params
    assert "limit" not in params and "offset" not in params


@respx.mock
def test_load_name_map_skips_rows_without_a_string_id_and_name(configured):
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=_list_body([{"id": "c1", "name": "Food"}, {"id": "c2"}, {"name": "orphan"}])
    )
    assert load_category_name_map() == {"c1": "Food"}


def test_load_name_map_without_config_is_empty():
    """No config → no engine to ask; renderers degrade to short ids, never raise."""
    assert load_account_name_map() == {}
    assert load_category_name_map() == {}
    assert load_hashtag_name_map() == {}


@respx.mock
def test_load_name_map_on_engine_error_is_empty(configured):
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=error_response(401, "UNAUTHORIZED", "nope", None)
    )
    assert load_category_name_map() == {}


# ---------------------------------------------------------------------------
# redact_token / format_hashtag_cell
# ---------------------------------------------------------------------------


def test_redact_token_masks_middle():
    assert redact_token("ewe_pat_abcd1234wxyz") == "ewe_pat_****wxyz"


def test_redact_token_short_tokens_fully_masked():
    assert redact_token("short") == "****"
    assert redact_token("12345678") == "****"  # exactly 8 → still fully masked


def test_format_hashtag_cell_resolves_names():
    cell = format_hashtag_cell(["h1", "h2"], {"h1": "trabajo", "h2": "club"}, max_width=24)
    assert cell == "trabajo, club"


def test_format_hashtag_cell_unresolved_id_gets_short_id_with_ellipsis():
    cell = format_hashtag_cell(["0123456789abcdef"], {}, max_width=24)
    assert cell == "01234567…"


def test_format_hashtag_cell_truncates_to_max_width():
    cell = format_hashtag_cell(["h1", "h2"], {"h1": "a" * 20, "h2": "b" * 20}, max_width=10)
    assert len(cell) == 10
    assert cell.endswith("…")


def test_format_hashtag_cell_empty_or_non_list_is_dash():
    assert format_hashtag_cell([], {}, max_width=24) == "—"
    assert format_hashtag_cell(None, {}, max_width=24) == "—"
    assert format_hashtag_cell("h1", {}, max_width=24) == "—"


# ---------------------------------------------------------------------------
# items_of
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (whole([{"id": "a"}]), [{"id": "a"}]),  # whole list
        (cursor_page([{"id": "a"}], next_cursor="c1"), [{"id": "a"}]),  # cursor page
        ({"items": []}, []),
        ({"items": None}, []),  # items present but null
        ({"limit": 3}, []),  # dict without items — never a row source
        ([{"id": "a"}], []),  # a bare array is not an engine body
        ([], []),
        (None, []),
        ("oops", []),  # scalar garbage
    ],
)
def test_items_of(body, expected):
    assert items_of(body) == expected


# ---------------------------------------------------------------------------
# EngineError
# ---------------------------------------------------------------------------


def test_engine_error_attribute_access():
    """EngineError instances expose .status, .code, .fields for hint lookups."""
    err = EngineError(code="X", message="m", fields={"a": "b"}, status=403, raw_body={})
    assert err.status == 403
    assert err.code == "X"
    assert err.fields == {"a": "b"}


# ---------------------------------------------------------------------------
# account_choices
# ---------------------------------------------------------------------------

_ACCOUNT_ROWS = [
    {
        "id": "a1",
        "name": "BCP",
        "currency_code": "PEN",
        "current_balance_cents": 100,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "a2",
        "name": None,
        "currency_code": None,
        "is_person": False,
        "opening_balance_transaction_id": None,
    },
    {
        "id": "p1",
        "name": "Mom",
        "currency_code": "PEN",
        "is_person": True,
        "opening_balance_transaction_id": None,
    },
    {"name": "no-id row is skipped"},
]


def test_account_choices_includes_people_by_default():
    rows = account_choices(_ACCOUNT_ROWS)
    assert [r[0] for r in rows] == ["a1", "a2", "p1"]
    assert rows[0] == ("a1", "BCP", "PEN")
    assert rows[1] == ("a2", "(unnamed)", "?")  # null name/currency fallbacks


def test_account_choices_can_exclude_people():
    rows = account_choices(_ACCOUNT_ROWS, include_people=False)
    assert [r[0] for r in rows] == ["a1", "a2"]


def test_account_choices_with_balance_appends_cents():
    rows = account_choices(_ACCOUNT_ROWS, include_people=False, with_balance=True)
    assert rows[0] == ("a1", "BCP", "PEN", 100)
    assert rows[1][3] is None  # missing balance stays None


# ---------------------------------------------------------------------------
# fetch_all_cursor_pages (the one pagination loop)
# ---------------------------------------------------------------------------


def _pager(pages):
    """fetch_page stub serving canned bodies; records (limit, after) calls."""
    calls: list[tuple[int, str | None]] = []

    def fetch_page(limit, after):
        calls.append((limit, after))
        return pages[len(calls) - 1]

    return fetch_page, calls


def test_fetch_all_cursor_pages_walks_by_next_cursor():
    """Each page's `next_cursor` goes back as `after`; null is the stop."""
    fetch_page, calls = _pager(
        [
            cursor_page([{"id": "a"}, {"id": "b"}], next_cursor="c1"),
            cursor_page([{"id": "c"}, {"id": "d"}], next_cursor="c2"),
            cursor_page([{"id": "e"}]),
        ]
    )
    rows = fetch_all_cursor_pages(fetch_page, page_size=2)
    assert [r["id"] for r in rows] == ["a", "b", "c", "d", "e"]
    assert calls == [(2, None), (2, "c1"), (2, "c2")]


def test_fetch_all_cursor_pages_short_page_with_cursor_keeps_going():
    """A short page is not the end — only a null cursor is.

    (contract: "Base Conventions", "Cursors, on every cursor-paged list")
    """
    fetch_page, calls = _pager(
        [cursor_page([{"id": "a"}], next_cursor="c1"), cursor_page([{"id": "b"}])]
    )
    assert [r["id"] for r in fetch_all_cursor_pages(fetch_page)] == ["a", "b"]
    assert calls == [(200, None), (200, "c1")]


def test_fetch_all_cursor_pages_full_page_with_null_cursor_stops():
    """A page holding exactly the remaining rows comes back null — no empty fetch."""
    fetch_page, calls = _pager([cursor_page([{"id": f"t{i}"} for i in range(200)])])
    assert len(fetch_all_cursor_pages(fetch_page)) == 200
    assert calls == [(200, None)]


@respx.mock
def test_fetch_all_cursor_pages_never_sends_offset(configured):
    """Through the real fetch: `offset` is a 422 on `GET /transactions`."""
    from expense import config as config_module
    from expense.reads import fetch_transactions

    route = respx.get(f"{BASE}/v1/transactions").mock(
        side_effect=[
            httpx.Response(200, json=cursor_page([{"id": "a"}], next_cursor="c1")),
            httpx.Response(200, json=cursor_page([{"id": "b"}])),
        ]
    )
    cfg = config_module.ensure_loaded()
    rows = fetch_all_cursor_pages(
        lambda limit, after: fetch_transactions(cfg, account="acct", limit=limit, after=after)
    )
    assert [r["id"] for r in rows] == ["a", "b"]
    first, second = (call.request.url.params for call in route.calls)
    assert "offset" not in first and "offset" not in second
    assert "after" not in first
    assert second["after"] == "c1"
    assert second["account_id"] == "acct"


# --------------------------------------------------------------------------- #
# split_settled / settled_label — the People fold
# --------------------------------------------------------------------------- #


def test_split_settled_partitions_on_the_native_balance():
    people = [
        {"name": "Eliana", "current_balance_cents": 20000},
        {"name": "Ana", "current_balance_cents": 0},
        {"name": "Marco", "current_balance_cents": -45000},
    ]
    outstanding, settled = split_settled(people)
    assert [p["name"] for p in outstanding] == ["Eliana", "Marco"]
    assert [p["name"] for p in settled] == ["Ana"]


def test_split_settled_ignores_the_home_balance():
    """A missing exchange rate must never read as "she paid me back"."""
    people = [
        # Square in her own currency, unpriceable in home — settled.
        {"name": "Beto", "current_balance_cents": 0, "current_balance_home_cents": None},
        # Owes 200 in her own currency, unpriceable in home — still outstanding.
        {"name": "Cora", "current_balance_cents": 20000, "current_balance_home_cents": None},
        # Home rounds to zero, native does not. Native decides.
        {"name": "Dina", "current_balance_cents": 1, "current_balance_home_cents": 0},
    ]
    outstanding, settled = split_settled(people)
    assert [p["name"] for p in outstanding] == ["Cora", "Dina"]
    assert [p["name"] for p in settled] == ["Beto"]


def test_split_settled_treats_an_unknown_balance_as_outstanding():
    """Missing or non-numeric is *unknown*, not zero — it stays visible."""
    people = [
        {"name": "NoKey"},
        {"name": "Null", "current_balance_cents": None},
        {"name": "Text", "current_balance_cents": "0"},
        {"name": "Bool", "current_balance_cents": False},  # not an int balance
    ]
    outstanding, settled = split_settled(people)
    assert [p["name"] for p in outstanding] == ["NoKey", "Null", "Text", "Bool"]
    assert settled == []


def test_split_settled_never_drops_a_row():
    people = [{"current_balance_cents": n} for n in (0, 1, 0, -2, 0)]
    outstanding, settled = split_settled(people)
    assert len(outstanding) + len(settled) == len(people)


def test_settled_label_shape():
    assert settled_label(3) == "3 settled"
    assert settled_label(1) == "1 settled"


# ---------------------------------------------------------------------------
# load_quickadd_refs — the reference lists both quick-add surfaces match against
# ---------------------------------------------------------------------------


@respx.mock
def test_load_quickadd_refs_shapes_all_three_lists(configured):
    respx.get(f"{BASE}/v1/accounts").mock(
        return_value=_list_body(
            [
                {
                    "id": "a1",
                    "name": "BCP PEN",
                    "currency_code": "PEN",
                    "opening_balance_transaction_id": None,
                },
                {
                    "id": "a2",
                    "name": "Retired",
                    "currency_code": "PEN",
                    "is_archived": True,
                    "opening_balance_transaction_id": None,
                },
            ]
        )
    )
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=_list_body(
            [{"id": "c1", "name": "KORAKUEN"}, {"id": "c2", "name": "Opening", "is_system": True}]
        )
    )
    respx.get(f"{BASE}/v1/hashtags").mock(return_value=_list_body([{"id": "h1", "name": "TAXI"}]))

    refs = load_quickadd_refs(config_module.ensure_loaded())

    # accounts keep their currency — the parser ignores the extra column, the
    # renderer needs it to say "-38.60 PEN"
    assert refs.accounts == [("a1", "BCP PEN", "PEN")]
    assert refs.categories == [("c1", "KORAKUEN")]
    assert refs.hashtags == [("h1", "TAXI")]


@respx.mock
def test_load_quickadd_refs_pool_excludes_what_the_maps_keep(configured):
    """You cannot type your way into an archived account or a system category,
    but a row that already names one still renders its name."""
    respx.get(f"{BASE}/v1/accounts").mock(
        return_value=_list_body(
            [
                {
                    "id": "a2",
                    "name": "Retired",
                    "is_archived": True,
                    "opening_balance_transaction_id": None,
                }
            ]
        )
    )
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=_list_body([{"id": "c2", "name": "Opening", "is_system": True}])
    )
    respx.get(f"{BASE}/v1/hashtags").mock(return_value=_list_body([]))

    refs = load_quickadd_refs(config_module.ensure_loaded())

    assert refs.accounts == [] and refs.categories == []
    assert refs.account_names == {"a2": "Retired"}
    assert refs.category_names == {"c2": "Opening"}


@respx.mock
def test_load_quickadd_refs_names_the_opening_category_by_its_system_key(configured):
    """The @Opening row is found by `system_key`, never by its name (the owner
    may rename it), from the same categories read; none means None."""
    respx.get(f"{BASE}/v1/accounts").mock(return_value=_list_body([]))
    cats = respx.get(f"{BASE}/v1/categories")
    cats.mock(
        return_value=_list_body(
            [
                {"id": "c1", "name": "@Opening", "is_system": False},
                {"id": "c2", "name": "Apert", "is_system": True, "system_key": "opening_balance"},
                {"id": "c3", "name": "@Pendiente", "is_system": True, "system_key": "pending"},
            ]
        )
    )
    respx.get(f"{BASE}/v1/hashtags").mock(return_value=_list_body([]))

    refs = load_quickadd_refs(config_module.ensure_loaded())

    assert refs.opening == "c2"
    assert cats.call_count == 1
    cats.mock(return_value=_list_body([{"id": "c1", "name": "KORAKUEN"}]))
    assert load_quickadd_refs(config_module.ensure_loaded()).opening is None


@respx.mock
def test_load_quickadd_refs_reads_every_hashtag_in_one_call(configured):
    """56 hashtags against the old default page of 50 lost 6 tags to the
    picker. The engine now returns the list whole: one read, no paging."""
    respx.get(f"{BASE}/v1/accounts").mock(return_value=_list_body([]))
    respx.get(f"{BASE}/v1/categories").mock(return_value=_list_body([]))
    tags = [{"id": f"h{i}", "name": f"tag{i}"} for i in range(56)]
    route = respx.get(f"{BASE}/v1/hashtags").mock(return_value=_list_body(tags))

    refs = load_quickadd_refs(config_module.ensure_loaded())

    assert len(refs.hashtags) == 56
    assert route.call_count == 1
    params = route.calls.last.request.url.params
    assert "limit" not in params and "offset" not in params


@respx.mock
def test_load_quickadd_refs_names_the_pending_hashtag_by_its_system_key(configured):
    """The pending hashtag is found by `system_key`, never by its name, from the
    same hashtags read, and stays in the pool; none yet means None."""
    respx.get(f"{BASE}/v1/accounts").mock(return_value=_list_body([]))
    respx.get(f"{BASE}/v1/categories").mock(return_value=_list_body([]))
    tags = respx.get(f"{BASE}/v1/hashtags")
    tags.mock(
        return_value=_list_body(
            [
                {"id": "h1", "name": "Pendiente", "system_key": None},
                {"id": "hp", "name": "Por etiquetar", "system_key": "pending"},
            ]
        )
    )

    refs = load_quickadd_refs(config_module.ensure_loaded())

    assert refs.pending_hashtag == ("hp", "Por etiquetar")
    assert refs.pending_hashtag_id == "hp"
    assert ("hp", "Por etiquetar") in refs.hashtags
    assert tags.call_count == 1
    tags.mock(return_value=_list_body([{"id": "h1", "name": "Pendiente", "system_key": None}]))
    none_yet = load_quickadd_refs(config_module.ensure_loaded())
    assert none_yet.pending_hashtag is None and none_yet.pending_hashtag_id is None


@pytest.mark.parametrize(
    ("ids", "pending", "sent"),
    [
        # tagging a pending row: only the real hashtags go, in their order
        (["hp", "h1"], "hp", ["h1"]),
        (["h1", "hp", "h2"], "hp", ["h1", "h2"]),
        # the pending hashtag alone, or no hashtag, goes as it is
        (["hp"], "hp", ["hp"]),
        ([], "hp", []),
        (["h1", "h2"], "hp", ["h1", "h2"]),
        # no pending hashtag yet: nothing to drop
        (["h1", "h2"], None, ["h1", "h2"]),
        ([], None, []),
    ],
)
def test_hashtags_to_send_drops_the_pending_hashtag_beside_a_real_one(ids, pending, sent):
    """(contract: "Transactions (Ledger)", "The pending hashtag is never combined")"""
    assert hashtags_to_send(ids, pending) == sent
    assert hashtags_to_send(tuple(ids), pending) == sent  # a parsed line's tuple too


@pytest.mark.parametrize(
    ("ids", "pending", "sent"),
    [
        (["hp"], "hp", []),
        (["hp", "h1"], "hp", ["h1"]),
        ([], "hp", []),
        (["h1"], "hp", ["h1"]),
        (["hp"], None, ["hp"]),
    ],
)
def test_hashtags_to_send_without_the_pending_one_alone(ids, pending, sent):
    """`pending_alone=False`, the split's parts: the pending hashtag never goes,
    alone or not, so a part with no real hashtag sends none
    (contract: POST /v1/transactions/{transaction_id}/split)."""
    assert hashtags_to_send(ids, pending, pending_alone=False) == sent


@pytest.mark.parametrize(
    ("value", "number"),
    [
        (0, 0),
        (-10000, -10000),
        (True, None),
        (False, None),
        (None, None),
        ("12", None),
        (1.5, None),
    ],
)
def test_whole_number_takes_an_int_and_never_a_flag(value, number):
    assert whole_number(value) == number


# ---- query_params -----------------------------------------------------------
def test_query_params_drops_what_was_not_asked_for():
    assert query_params(a=None, b="x") == {"b": "x"}


def test_query_params_encodes_a_flag_as_the_engine_reads_it():
    # False is absent, not `"false"`: absence IS the default
    assert query_params(include_people=True, include_archived=False) == {"include_people": "true"}


def test_query_params_keeps_a_zero():
    """A zero was asked for, and `0 is None` is False — the guard has to be
    identity, not truthiness."""
    assert query_params(limit=0) == {"limit": 0}


def test_query_params_sends_one_spelling_of_a_number():
    """`reconcile` and `rates` sent `str(limit)`; everything else sent `limit`."""
    assert query_params(limit=20) == {"limit": 20}


TRANSACTION_RESPONSE = {
    "id": "55555555-5555-5555-5555-555555555555",
    "user_id": "u_123",
    "title": "coffee",
    "amount_cents": 500,
    "date": "2026-04-24T12:00:00Z",
    "account_id": "acct-id",
    "category_id": "cat-id",
    "description": None,
    "transaction_type": 1,
    "hashtag_ids": [],
    "reconciliation_id": None,
    "bank_line_id": "66666666-6666-6666-6666-666666666666",
    "created_at": "2026-04-24T10:00:00Z",
    "updated_at": "2026-04-24T10:00:00Z",
    "version": 1,
    "deleted_at": None,
}


# ---------------------------------------------------------------------------
# fetch_transactions / count_transactions — the cursor-paged pair
# ---------------------------------------------------------------------------


@respx.mock
def test_fetch_transactions_sends_sort_and_after_never_offset(configured):
    from expense import config as config_module
    from expense.reads import fetch_transactions

    route = respx.get(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(200, json=cursor_page([TRANSACTION_RESPONSE]))
    )
    fetch_transactions(
        config_module.ensure_loaded(),
        account="acct-id",
        unreconciled=True,
        sort="date_asc",
        after="c1",
        limit=40,
    )
    assert dict(route.calls.last.request.url.params) == {
        "account_id": "acct-id",
        "unreconciled": "true",
        "sort": "date_asc",
        "after": "c1",
        "limit": "40",
        "debit_as_negative": "true",
    }


@respx.mock
def test_fetch_transaction_reads_one_row_signed(configured):
    """One row by id, always signed, so the caller never reads the sign off
    `transaction_type` (contract: "Base Conventions", "Sign convention — responses")."""
    from expense import config as config_module
    from expense.reads import fetch_transaction

    row = {**TRANSACTION_RESPONSE, "id": "tx-open", "amount_cents": -320000}
    route = respx.get(f"{BASE}/v1/transactions/tx-open").mock(
        return_value=httpx.Response(200, json=row)
    )
    assert fetch_transaction(config_module.ensure_loaded(), "tx-open") == row
    assert dict(route.calls.last.request.url.params) == {"debit_as_negative": "true"}


@respx.mock
def test_transaction_reads_pass_the_bank_line_through(configured):
    """`bank_line_id` reaches the caller as the engine sent it, from the list
    and from the read by id."""
    from expense import config as config_module
    from expense.reads import fetch_transaction, fetch_transactions

    line = TRANSACTION_RESPONSE["bank_line_id"]
    respx.get(f"{BASE}/v1/transactions").mock(
        return_value=httpx.Response(200, json=cursor_page([TRANSACTION_RESPONSE]))
    )
    respx.get(f"{BASE}/v1/transactions/{TRANSACTION_RESPONSE['id']}").mock(
        return_value=httpx.Response(200, json=TRANSACTION_RESPONSE)
    )
    cfg = config_module.ensure_loaded()
    assert fetch_transactions(cfg)["items"][0]["bank_line_id"] == line
    assert fetch_transaction(cfg, TRANSACTION_RESPONSE["id"])["bank_line_id"] == line


BANK_LINE_RESPONSE = {
    "id": "66666666-6666-6666-6666-666666666666",
    "account_id": "acct-id",
    "operation_code": None,
    "net_cents": -10000,
    "part_count": 2,
    # Each part the transaction response, unsigned: a magnitude and its type.
    "parts": [
        {
            **TRANSACTION_RESPONSE,
            "id": "55555555-5555-5555-5555-555555555555",
            "amount_cents": 6000,
        },
        {**TRANSACTION_RESPONSE, "id": "tx-two", "amount_cents": 4000},
    ],
}


@respx.mock
def test_fetch_bank_line_reads_one_line_as_the_engine_sends_it(configured):
    """One GET by the line's id, no query, the body untouched: `part_count`,
    `net_cents` and `parts` are the engine's (contract: GET /v1/bank-lines/{bank_line_id})."""
    from expense import config as config_module
    from expense.reads import fetch_bank_line

    line = BANK_LINE_RESPONSE["id"]
    route = respx.get(f"{BASE}/v1/bank-lines/{line}").mock(
        return_value=httpx.Response(200, json=BANK_LINE_RESPONSE)
    )
    assert fetch_bank_line(config_module.ensure_loaded(), line) == BANK_LINE_RESPONSE
    assert route.call_count == 1
    assert dict(route.calls.last.request.url.params) == {}


PENDING_HASHTAG = {"id": "h-pend", "name": "Por etiquetar", "system_key": "pending"}
#: A user's own hashtag that took the default name before the engine reserved it.
NAMED_PENDIENTE = {"id": "h-user", "name": "Pendiente", "system_key": None}


def test_the_pending_hashtag_is_found_by_its_system_key_under_its_current_name():
    from expense.reads import pending_hashtag_of

    rows = [NAMED_PENDIENTE, {"id": "h1", "name": "Food", "system_key": None}, PENDING_HASHTAG]
    assert pending_hashtag_of(rows) == ("h-pend", "Por etiquetar")


def test_no_pending_hashtag_yet_is_none_and_a_hashtag_named_pendiente_is_not_it():
    from expense.reads import pending_hashtag_of

    assert pending_hashtag_of([]) is None
    assert pending_hashtag_of([NAMED_PENDIENTE, {"id": "h1", "name": "Food"}]) is None


@respx.mock
def test_fetch_pending_hashtag_reads_the_hashtag_list(configured):
    from expense import config as config_module
    from expense.reads import fetch_pending_hashtag

    route = respx.get(f"{BASE}/v1/hashtags")
    route.mock(return_value=_list_body([NAMED_PENDIENTE, PENDING_HASHTAG]))
    cfg = config_module.ensure_loaded()
    assert fetch_pending_hashtag(cfg) == ("h-pend", "Por etiquetar")
    route.mock(return_value=_list_body([NAMED_PENDIENTE]))
    assert fetch_pending_hashtag(cfg) is None


@respx.mock
def test_fetch_transaction_raises_the_engines_refusal(configured):
    from expense import config as config_module
    from expense.reads import fetch_transaction

    respx.get(f"{BASE}/v1/transactions/gone").mock(
        return_value=error_response(404, "NOT_FOUND", "Transaction not found.")
    )
    with pytest.raises(EngineError) as caught:
        fetch_transaction(config_module.ensure_loaded(), "gone")
    assert caught.value.code == "NOT_FOUND"


@respx.mock
def test_count_transactions_sends_the_filters_and_nothing_else(configured):
    """The count 422s on any parameter it does not declare — `debit_as_negative`,
    `sort`, `limit` and `after` are the list's own and must never reach it."""
    from expense import config as config_module
    from expense.reads import count_transactions

    route = respx.get(f"{BASE}/v1/transactions/count").mock(
        return_value=httpx.Response(200, json={"count": 1716})
    )
    count = count_transactions(
        config_module.ensure_loaded(),
        account="acct-id",
        unreconciled=True,
        date_from="2026-06-01",
    )
    assert count == 1716
    assert dict(route.calls.last.request.url.params) == {
        "account_id": "acct-id",
        "unreconciled": "true",
        "date_from": "2026-06-01",
    }


@pytest.mark.parametrize("body", [{}, {"count": None}, {"count": "3"}, {"count": True}, []])
@respx.mock
def test_count_transactions_raises_without_an_int_count(configured, body):
    """Never a guessed number: a body without an int `count` is an error."""
    from expense import config as config_module
    from expense.reads import count_transactions

    respx.get(f"{BASE}/v1/transactions/count").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(ValueError, match="without a count"):
        count_transactions(config_module.ensure_loaded(), account="acct-id")


def test_list_and_count_take_the_same_filters():
    """The engine declares one filter set for both endpoints; so do we. A filter
    added to one function and not the other is a header counting different rows
    than the list shows, with no error anywhere."""
    import inspect

    from expense.reads import count_transactions, fetch_transactions

    list_only = {"sort", "after", "limit"}
    list_params = set(inspect.signature(fetch_transactions).parameters) - list_only
    assert list_params == set(inspect.signature(count_transactions).parameters)


@respx.mock
def test_count_bank_lines_sends_the_filters_and_nothing_else(configured):
    """`GET /bank-lines/count` takes the list's filters and refuses `after` and
    `limit` (contract: GET /v1/bank-lines/count)."""
    from expense import config as config_module
    from expense.reads import count_bank_lines

    route = respx.get(f"{BASE}/v1/bank-lines/count").mock(
        return_value=httpx.Response(200, json={"count": 42})
    )
    count = count_bank_lines(config_module.ensure_loaded(), account="acct-id", unreconciled=True)
    assert count == 42
    assert dict(route.calls.last.request.url.params) == {
        "account_id": "acct-id",
        "unreconciled": "true",
    }


@pytest.mark.parametrize("body", [{}, {"count": None}, {"count": "3"}, {"count": True}, []])
@respx.mock
def test_count_bank_lines_raises_without_an_int_count(configured, body):
    from expense import config as config_module
    from expense.reads import count_bank_lines

    respx.get(f"{BASE}/v1/bank-lines/count").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(ValueError, match="without a count"):
        count_bank_lines(config_module.ensure_loaded(), account="acct-id")


def test_the_line_list_and_its_count_take_the_same_filters():
    import inspect

    from expense.reads import count_bank_lines, fetch_bank_lines

    list_params = set(inspect.signature(fetch_bank_lines).parameters) - {"after", "limit"}
    assert list_params == set(inspect.signature(count_bank_lines).parameters)


@pytest.mark.parametrize(
    ("line", "count"),
    [
        ({"part_count": 3}, 3),
        ({"part_count": 1}, 1),
        ({"part_count": None}, 0),
        ({"part_count": True}, 0),
        ({"part_count": "2"}, 0),
        ({}, 0),
        (None, 0),
    ],
)
def test_bank_line_part_count_reads_only_the_engines_whole_number(line, count):
    """The engine's `part_count`, or 0 for anything that is not a whole number,
    which every reader takes as a line never split
    (contract: GET /v1/bank-lines/{bank_line_id})."""
    assert bank_line_part_count(line) == count
