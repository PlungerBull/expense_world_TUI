"""Every engine read, one copy each: the `fetch_*` functions and what they share.

Typer-free and render-free: a `fetch_*` takes a `Config`, makes live GETs and
returns the engine's body (or a value read off it). The TUI screens call
these as `reads.fetch_x(...)`, so a test patches one name for every caller.
The quick-add reference lists (`load_quickadd_refs`) and the id → name maps
live here too.

Nothing here writes to the engine. One function writes locally:
`cache_main_currency` saves the home currency a read returned into the config
file, and `fetch_me` calls it on every read.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from expense import config as config_module
from expense.config import Config
from expense.errors import EngineError
from expense.http import ExpenseClient

ENGINE_PAGE_CAP = 200  # the engine's hard cap on `limit` — the one copy


# Rows per table page, everywhere a human reads one: every TUI list shares
# this single copy (20-row standard).
DEFAULT_PAGE_ROWS = 20


def items_of(body: object) -> list:
    """Rows of an engine list body (`{"items": [...]}`); [] for anything else.

    Every engine list endpoint returns an object with `items` — no route has
    returns a bare array — so a bare list is not a body and
    yields no rows. That also makes a test fake still serving the old shape
    fail loudly instead of passing. Strict list-or-empty — never hands a dict
    or None to a row-builder.
    """
    if not isinstance(body, dict):
        return []
    items = body.get("items")
    return items if isinstance(items, list) else []


def query_params(**values: Any) -> dict[str, Any]:
    """The query string for one engine read: drop what was not asked for,
    encode what was, one way.

    - `None` means "not asked for" and is left out entirely. `0` is not None,
      so a zero still goes.
    - A bool is a flag. `True` becomes the string `"true"` the engine reads;
      `False` is left out, because its absence IS the default.
    - Everything else passes through unchanged.

    Ints stay ints: one spelling per value, so a real difference cannot hide.

    Keyword names are the **wire** names, not the Python ones, so the mapping
    (`account` -> `account_id`) stays visible at the call site.
    """
    out: dict[str, Any] = {}
    for key, value in values.items():
        if value is None or value is False:
            continue
        out[key] = "true" if value is True else value
    return out


def fetch_body(
    cfg: Config,
    *,
    path: str,
    params: dict | None,
    verbose: bool,
) -> Any:
    """One live resource read — the skeleton behind every `fetch_*`/`get`.

    A plain GET against the engine; param building stays with the caller.
    """
    with ExpenseClient(cfg, verbose=verbose) as client:
        return client.get(path, params=params or None)


def fetch_all_cursor_pages(
    fetch_page: Callable[[int, str | None], Any], *, page_size: int = ENGINE_PAGE_CAP
) -> list[dict]:
    """Exhaust a cursor-paged resource. `fetch_page(limit, after)` returns one raw body.

    `GET /transactions` is the one cursor-paged endpoint. The only stop is
    `next_cursor` being null (contract: "Base Conventions", "Cursors, on every
    cursor-paged list") — not a short page, not a count: a page holding exactly the
    remaining rows already comes back null, and a short page with a cursor still has more.
    """
    out: list[dict] = []
    after: str | None = None
    while True:
        body = fetch_page(page_size, after)
        out.extend(items_of(body))
        after = body.get("next_cursor") if isinstance(body, dict) else None
        if after is None:
            return out


def fetch_accounts(
    cfg,
    *,
    include_archived: bool = False,
    include_people: bool = False,
    verbose: bool = False,
):
    """GET /v1/accounts → the raw engine body. Pure data.

    Read by the TUI's Accounts screen.
    The engine returns every row as `{items}` and refuses `limit`/`offset`
    — there is no page to ask for.
    """
    params = query_params(include_archived=include_archived, include_people=include_people)
    return fetch_body(
        cfg,
        path="/accounts",
        params=params,
        verbose=verbose,
    )


def fetch_categories(
    cfg,
    *,
    verbose: bool = False,
) -> dict:
    """GET /v1/categories → the raw engine body. Pure data, no render.

    Read by the TUI's Categories screen.
    The engine returns every row as `{items}` and refuses `limit`/`offset`
    — there is no page to ask for.
    """
    return fetch_body(cfg, path="/categories", params=None, verbose=verbose)


def fetch_hashtags(
    cfg,
    *,
    verbose: bool = False,
) -> dict:
    """GET /v1/hashtags → the raw engine body. Pure data, no render.

    Read by the TUI's Hashtags screen.
    The engine returns every row as `{items}` and refuses `limit`/`offset`
    — there is no page to ask for.
    """
    return fetch_body(cfg, path="/hashtags", params=None, verbose=verbose)


def _filter_params(
    *,
    account: str | None,
    category: str | None,
    hashtag: str | None,
    reconciliation: str | None,
    unreconciled: bool,
    date_from: str | None,
    date_to: str | None,
) -> dict:
    """The filters `GET /transactions` and `/transactions/count` share — one copy.

    The engine declares them once for both endpoints, so the list and its count
    describe the same rows by construction; this mirrors that. Filters only:
    paging, `sort` and `debit_as_negative` are the list's own, and the count
    422s on any parameter it does not declare.
    """
    return query_params(
        account_id=account,
        category_id=category,
        hashtag_id=hashtag,
        reconciliation_id=reconciliation,
        unreconciled=unreconciled,
        date_from=date_from,
        date_to=date_to,
    )


def fetch_transactions(
    cfg,
    *,
    account: str | None = None,
    category: str | None = None,
    hashtag: str | None = None,
    reconciliation: str | None = None,
    unreconciled: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    after: str | None = None,
    limit: int | None = None,
    verbose: bool = False,
) -> dict:
    """GET /v1/transactions → the raw engine body. Pure data, no render.

    Cursor-paged: pass the previous page's `next_cursor` as `after`; `null`
    means the last page. There is no `offset` and no `total` — the count is
    `count_transactions`. A cursor belongs to one filter + sort, so a caller
    that changes either starts again from `after=None`.
    """
    params = {
        **_filter_params(
            account=account,
            category=category,
            hashtag=hashtag,
            reconciliation=reconciliation,
            unreconciled=unreconciled,
            date_from=date_from,
            date_to=date_to,
        ),
        **query_params(
            sort=sort,
            after=after,
            limit=limit,
            # Always signed: every TUI surface renders debits negative, so the
            # request pins the flag rather than depending on the engine default.
            debit_as_negative=True,
        ),
    }
    return fetch_body(
        cfg,
        path="/transactions",
        params=params,
        verbose=verbose,
    )


def count_transactions(
    cfg,
    *,
    account: str | None = None,
    category: str | None = None,
    hashtag: str | None = None,
    reconciliation: str | None = None,
    unreconciled: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    verbose: bool = False,
) -> int:
    """GET /v1/transactions/count → how many rows the same filters match.

    Raises when the body carries no int `count`. A count that falls back to a
    guess (`len(items)`) is how two panes showed "1 to file" over 1,716 rows
    with no error; a pane that cannot get the number fails instead.
    """
    body = fetch_body(
        cfg,
        path="/transactions/count",
        params=_filter_params(
            account=account,
            category=category,
            hashtag=hashtag,
            reconciliation=reconciliation,
            unreconciled=unreconciled,
            date_from=date_from,
            date_to=date_to,
        ),
        verbose=verbose,
    )
    count = body.get("count") if isinstance(body, dict) else None
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError(f"GET /transactions/count answered without a count: {body!r}")
    return count


def fetch_reconciliations(cfg, *, account_id: str, verbose: bool = False) -> dict:
    """GET /v1/reconciliations?account_id= → the raw engine body. Pure data.

    Read by the TUI's Reconciliations screens. The engine lists one account at
    a time: the
    account is required, the list comes back whole as `{items}` — no `limit`,
    no `offset`, no `total` — sorted `date_start` ascending, then creation time,
    oldest first (contract: "Reconciliations", "Ordering"). There is no read
    by id; a row not in its account's list has been deleted.
    """
    return fetch_body(
        cfg,
        path="/reconciliations",
        params=query_params(account_id=account_id),
        verbose=verbose,
    )


def fetch_dashboard(cfg, *, verbose: bool = False) -> dict:
    """GET /v1/dashboard → the raw engine body. Pure data, no rendering."""
    return fetch_body(cfg, path="/dashboard", params=None, verbose=verbose)


def fetch_range(
    cfg,
    *,
    from_ym: tuple[int, int],
    to_ym: tuple[int, int],
    verbose: bool = False,
) -> dict:
    """GET /v1/reports/monthly for a month range → the raw engine body. No rendering.

    Range rules (inverted range, max span) are the engine's — invalid ranges
    are sent as-is so its 422 surfaces.
    """
    params = query_params(
        from_year=from_ym[0],
        from_month=from_ym[1],
        to_year=to_ym[0],
        to_month=to_ym[1],
    )
    return fetch_body(cfg, path="/reports/monthly", params=params, verbose=verbose)


def fetch_rate(cfg, *, target: str, verbose: bool = False) -> dict:
    """GET /v1/exchange-rates for `target` (engine-direct). Returns the raw response body.

    `base` and `date` are not sent, so the engine defaults (USD, today) apply.
    """
    params = query_params(target=target)

    return fetch_body(cfg, path="/exchange-rates", params=params, verbose=verbose)


def rate_is_stale(body: dict) -> bool | None:
    """True when the requested day has no rate row of its own.

    `GET /exchange-rates` (contract: "Staleness: `rate_date` is the signal")
    returns both the day you asked about (`date`) and the
    day of the row it actually used (`rate_date`), and `rate_date < date` means
    the figure is being carried forward. That one comparison covers every way
    rate ingestion can fail — provider down, machine asleep, job crashed, or a
    rate refused as implausible by the engine's plausibility guard — which is
    why the engine exposes no bespoke staleness field for a client to read.

    Returns None when the body carries no usable pair of dates. That is the
    "don't know" answer, and callers must render nothing rather than guess: a
    shape change should go quiet, never cry wolf.

    String comparison is deliberate — both fields are ISO `YYYY-MM-DD`, which
    sorts lexicographically, and parsing them would only add a failure mode.
    """
    asked, used = body.get("date"), body.get("rate_date")
    if not isinstance(asked, str) or not isinstance(used, str):
        return None
    return used < asked


def fetch_rate_staleness(cfg, *, target: str, verbose: bool = False) -> bool | None:
    """Whether today's rate for `target` is missing — True/False, or None if unknown.

    A `404` is the same condition at its extreme (no rate at all on or before
    today) and counts as stale (contract: "Staleness: `rate_date` is the
    signal"). Every other engine error is
    a question about the engine rather than about the rate, so it answers None.

    Connection and config failures are deliberately not caught here: only the
    caller knows whether going quiet is the right response to being offline.
    """
    try:
        return rate_is_stale(fetch_rate(cfg, target=target, verbose=verbose))
    except EngineError as err:
        return True if err.status == 404 else None


def cache_main_currency(cfg: Config, settings: dict) -> None:
    """Save the engine's `main_currency` into the config file when it differs.

    `settings` is the `settings` object of an auth body (`GET /auth/me`,
    `POST /auth/bootstrap`). Writes the config file — the one local write in
    this module — and only when the value is present and not already cached.
    """
    main_currency = settings.get("main_currency") if settings else None
    if main_currency and main_currency != cfg.main_currency:
        updated = cfg.model_copy(update={"main_currency": main_currency})
        config_module.save(updated)


def fetch_me(cfg: Config, *, verbose: bool = False, client: "ExpenseClient | None" = None) -> dict:
    """GET /v1/auth/me, mirroring the home currency into ~/.expense-config.

    **The one auth-me path**, shared by the TUI's setup and Auth & profile
    screens. The caching is not incidental to the read: the header's
    stale-rate indicator targets the cached `main_currency`
    (`tui/app.refresh_rate_status`) and skips the check entirely when there is
    none. A read of `/auth/me` that skipped the caching would leave the user
    with no cached currency, and so unable ever to see the warning — the one
    thing that surface is for.

    Pass `client` to reuse one that is already open; the TUI does, because its
    screens build clients through a lazily-imported seam. Without it, one is
    opened and closed here.
    """
    if client is not None:
        body = client.get("/auth/me")
    else:
        with ExpenseClient(cfg, verbose=verbose) as opened:
            body = opened.get("/auth/me")
    cache_main_currency(cfg, body.get("settings") or {})
    return body


def _load_name_map(path: str, params: dict | None) -> dict[str, str]:
    """Live id → name map over one reference-list endpoint. Empty on any failure.

    The engine's responses are IDs-only, so renderers join against these maps
    to show human names. An empty map is always safe — callers fall back to
    short ids — which is why every failure (no config, engine down, auth)
    degrades to `{}` instead of raising.
    """
    try:
        cfg = config_module.ensure_loaded()
        with ExpenseClient(cfg) as client:
            items = items_of(client.get(path, params=params))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for item in items:
        rid = item.get("id")
        name = item.get("name")
        if isinstance(rid, str) and isinstance(name, str):
            out[rid] = name
    return out


def load_account_name_map() -> dict[str, str]:
    """Live account id → name map. Empty on any failure.

    Includes archived + people accounts so transaction rows can resolve
    references to retired accounts. Soft-deleted excluded.
    """
    return _load_name_map("/accounts", {"include_archived": "true", "include_people": "true"})


def load_category_name_map() -> dict[str, str]:
    """Live category id → name map. Empty on any failure."""
    return _load_name_map("/categories", None)


def load_hashtag_name_map() -> dict[str, str]:
    """Live hashtag id → name map. Empty on any failure.

    The engine returns hashtag UUIDs in `hashtag_breakdown` rows and
    `hashtag_ids` columns; renderers join against this map to display human
    names like `Food + Club`. Empty map is safe — callers fall back to raw ids.
    """
    return _load_name_map("/hashtags", None)


# The engine's stable key for `@Pendiente`, the system category an
# uncategorised row is filed under (contract: POST /v1/categories). Lookup is
# by this key, never by the display name — the owner may rename it.
PENDING_SYSTEM_KEY = "pending"


# What the app says when it has no reference list to read the real name from.
PENDING_FALLBACK_NAME = "pendiente"


def _pending_of(categories: list[dict]) -> tuple[str, str] | None:
    """`(id, name)` of the @Pendiente row among category rows, or None."""
    for c in categories:
        if c.get("system_key") == PENDING_SYSTEM_KEY and isinstance(c.get("id"), str):
            return (c["id"], c.get("name") or PENDING_FALLBACK_NAME)
    return None


def account_choices(
    items: list, *, include_people: bool = True, with_balance: bool = False
) -> list[tuple]:
    """Picker tuples from account rows: `(id, name-or-'(unnamed)', currency)`,
    plus `current_balance_cents` when `with_balance`.

    Skips id-less rows and (unless `include_people`) person accounts. One copy
    of the build shared by the edit form, the new-reconciliation form,
    and the reconciliations browse.
    """
    out: list[tuple] = []
    for a in items:
        if not a.get("id"):
            continue
        if not include_people and a.get("is_person"):
            continue
        row: tuple = (a["id"], a.get("name") or "(unnamed)", a.get("currency_code") or "?")
        if with_balance:
            row = (*row, a.get("current_balance_cents"))
        out.append(row)
    return out


@dataclass(frozen=True)
class QuickAddRefs:
    """The reference lists the quick-add grammar matches names against.

    `accounts`/`categories`/`hashtags` are the `(id, name, …)` tuples
    `quickadd.parse()` takes — extra columns are ignored, so accounts keep
    their currency for rendering. The three `*_names` maps are the *full*
    id → name sets (archived and system rows included), for resolving ids that
    the matching pool deliberately excludes.
    """

    accounts: list[tuple]
    categories: list[tuple]
    hashtags: list[tuple]
    account_names: dict[str, str]
    category_names: dict[str, str]
    hashtag_names: dict[str, str]
    # `(id, name)` of the @Pendiente system row, or None until the engine has
    # seeded it. Not in the matching pool (a typed line never names it; an
    # empty category IS it), but the echo and the staged list render its name.
    pending: tuple[str, str] | None = None


def pending_label(refs: "QuickAddRefs") -> str:
    """What a row with no category reads as — the @Pendiente row's own display
    name (the owner may have renamed it), or the plain word before it exists."""
    return refs.pending[1] if refs.pending else PENDING_FALLBACK_NAME


def currency_of(refs: "QuickAddRefs", account_id: object) -> str:
    """The account's currency code, or `''` when no account is named.

    The currency was only ever going to come from the account — a typed line
    never says which (`$` in `-$1800` is decoration). The TUI staged list
    needs it per row to total a batch **per currency**: soles are never added
    to dollars.
    """
    if not isinstance(account_id, str):
        return ""
    for row in refs.accounts:
        if row[0] == account_id and len(row) > 2:
            return str(row[2])
    return ""


def _id_name_map(rows: list) -> dict[str, str]:
    return {
        r["id"]: r["name"]
        for r in rows
        if isinstance(r.get("id"), str) and isinstance(r.get("name"), str)
    }


def load_quickadd_refs(cfg, **kw) -> QuickAddRefs:
    """Fetch and shape the three reference lists a typed line resolves against.

    One copy for every caller: in the TUI, the edit form, the LOG bar and the
    transactions screen. What the shaping
    decides, and why:

    * **One superset accounts fetch** (`include_archived`, `include_people`)
      feeds both the name map and the suggestion pool; the pool then drops
      archived accounts, so you cannot type your way into a retired one but a
      transaction that already names one still renders.
    * **System categories are excluded** from the pool — `@Opening` is the
      engine's own bookkeeping, and `@Pendiente` is what an *empty* category
      means, so neither is something a typed line names.
    * **One read each, and it is every row** — the engine returns these lists
      whole, so no tag is invisible to the picker or unmatchable from a typed
      line.
    """
    accts = items_of(fetch_accounts(cfg, include_people=True, include_archived=True, **kw))
    cats = items_of(fetch_categories(cfg, **kw))
    tags = items_of(fetch_hashtags(cfg, **kw))
    return QuickAddRefs(
        accounts=account_choices([a for a in accts if not a.get("is_archived")]),
        categories=[
            (c["id"], c.get("name") or "(unnamed)")
            for c in cats
            if c.get("id") and not c.get("is_system")
        ],
        hashtags=[(t["id"], t.get("name") or "(unnamed)") for t in tags if t.get("id")],
        account_names=_id_name_map(accts),
        category_names=_id_name_map(cats),
        hashtag_names=_id_name_map(tags),
        pending=_pending_of(cats),
    )
