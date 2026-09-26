"""Shared helpers for resource sub-apps (accounts, categories, hashtags)."""

import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

import typer

from expense import config as config_module
from expense.config import Config
from expense.context import get_verbose
from expense.currencies import MINOR_UNIT_SCALE
from expense.errors import EngineError
from expense.http import ExpenseClient
from expense.jsonout import emit_json

# Shared option declarations — one wording for flags repeated across command
# modules. Never mutate these; a command whose flag means something different
# declares it inline (e.g. `import sheet --json` emits the plan, not a body).
JSON_OPT = typer.Option(False, "--json", help="Output the raw engine response as JSON.")
LIMIT_OPT = typer.Option(
    None,
    "--limit",
    help="Max rows per page (human output defaults to 20; --json sends no default).",
)
OFFSET_OPT = typer.Option(None, "--offset", help="Rows to skip (pagination).")
INCLUDE_ARCHIVED_OPT = typer.Option(False, "--include-archived", help="Include archived rows.")
YES_OPT = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt.")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def visible_len(text: str) -> int:
    """Length of `text` ignoring ANSI escape sequences."""
    return len(_ANSI_RE.sub("", text))


def pad_left(text: str, width: int) -> str:
    """Left-align `text` (pad spaces on the right) to `width` visible cols."""
    return text + " " * max(width - visible_len(text), 0)


def pad_right(text: str, width: int) -> str:
    """Right-align `text` (pad spaces on the left) to `width` visible cols."""
    return " " * max(width - visible_len(text), 0) + text


def stdin_is_tty() -> bool:
    """Is there a human at the other end to answer a prompt?

    Its own function so a test can be run through `CliRunner` and still take
    the interactive branch: the runner swaps `sys.stdin` out for the duration
    of the call, so patching the stream itself never reaches `require_yes`.
    """
    return sys.stdin.isatty()


def color_supported() -> bool:
    """True iff stdout is a TTY and NO_COLOR env var is unset.

    Honors the de-facto NO_COLOR convention (https://no-color.org/).
    """
    return sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""


def color_swatch(hex_value: object, *, color: bool) -> str:
    """Render a 2-char ANSI swatch for `#RRGGBB`, or fall back to the hex.

    Returns `(none)` when the input is None. Invalid hex falls through to
    the raw string. Set `color=False` to always render the hex literally
    (e.g. when piping to a file).
    """
    if hex_value is None:
        return "(none)"
    if not isinstance(hex_value, str):
        return str(hex_value)
    if not color:
        return hex_value
    if len(hex_value) != 7 or not hex_value.startswith("#"):
        return hex_value
    try:
        r = int(hex_value[1:3], 16)
        g = int(hex_value[3:5], 16)
        b = int(hex_value[5:7], 16)
    except ValueError:
        return hex_value
    return f"\x1b[38;2;{r};{g};{b}m██\x1b[0m"


def truncate(text: object, max_width: int) -> str:
    """Truncate `text` to `max_width` visible chars, appending `…` if cut."""
    if text is None:
        return ""
    s = str(text)
    if visible_len(s) <= max_width:
        return s
    if max_width <= 1:
        return s[:max_width]
    return s[: max_width - 1] + "…"


def format_short_date(iso_value: object) -> str:
    """`2026-04-24T12:00:00Z` → `2026-04-24`. None / non-string → `—`."""
    if not isinstance(iso_value, str) or len(iso_value) < 10:
        return "—"
    return iso_value[:10]


def format_cents(value: object) -> str:
    """Render an integer-cents amount as grouped major units with 2 decimals.

    `651900` → `6,519.00`; `-418797` → `-4,187.97`; `0` → `0.00`; None → `(null)`.

    Integer arithmetic throughout — no float division — so large amounts never
    drift. This is a human-display convenience only; `--json` output stays the
    raw engine integer. Non-int, non-None values fall back to `str()`.
    """
    if value is None:
        return "(null)"
    if not isinstance(value, int) or isinstance(value, bool):
        return str(value)
    negative = value < 0
    cents = -value if negative else value
    major, minor = divmod(cents, MINOR_UNIT_SCALE)
    body = f"{major:,}.{minor:02d}"
    return f"-{body}" if negative else body


def format_cents_or_dash(value: object) -> str:
    """`format_cents`, but an absent amount is `—` rather than `(null)`.

    For fields where null is a *meaningful state the user will actually see*,
    not a shape error worth shouting about. `(null)` is the right output when a
    null means something went wrong — it is deliberately ugly so it gets
    noticed. It is the wrong output for a reconciliation's `ending_balance_cents`,
    which is null whenever you have opened a batch and not yet read the closing
    figure off the statement (engine `sql/040`, 2026-09-14): a normal, expected,
    every-month state that should not read as a defect.

    `—` is already this repo's mark for an absent value — see `format_short_date`
    above, and `amount_cell` in the TUI. `0` still renders as `0.00`, because an
    entered zero is a real statement balance and telling those two apart is the
    entire point of the engine change this pairs with.
    """
    return "—" if value is None else format_cents(value)


UNRATED_SUFFIX = "unrated"


def unconverted_of(payload: object) -> int:
    """The `unconverted_count` on an aggregate object, or 0 when absent/odd.

    Every home aggregate the engine returns — a category, a `hashtag_breakdown`
    row, a month's `totals` — carries this count alongside its figure.
    """
    if not isinstance(payload, dict):
        return 0
    count = payload.get("unconverted_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return 0
    return count


def format_aggregate(value: object, unconverted_count: object = 0) -> str:
    """Render a home-currency aggregate, which the engine may refuse to total.

    Since the engine's read-time-currency change (2026-08-05) every aggregate is
    nullable and paired with an `unconverted_count`: when any row in the group
    falls on a date with no resolvable rate, the figure comes back `None` and the
    count says how many rows are behind it.

    **A `None` here is neither zero nor missing** — the engine declined to report
    a partial total — so it renders as `3 unrated`, never `0.00`, and never by
    falling back to a native figure (the exact bug the engine deleted: reading
    USD cents as PEN cents understated by 3.58×). Phase 4 sketch, option C.

    A present figure formats exactly as `format_cents` does.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return format_cents(value)
    count = unconverted_of({"unconverted_count": unconverted_count})
    if count > 0:
        return f"{count} {UNRATED_SUFFIX}"
    return format_cents(value)


def has_aggregate(value: object, unconverted_count: object = 0) -> bool:
    """Whether an aggregate row is worth drawing at all.

    A category or hashtag combination with nothing spent this period is not
    rendered — the engine returns every non-deleted category whether or not it
    has activity, so the full-list view is `expense categories list`, not a
    report (user decision, 2026-08-16; Phase 4 sketch).

    A row the engine *could not price* is emphatically not empty: it keeps its
    line and says `3 unrated`, so it is never mistaken for one with no spending.
    """
    if unconverted_of({"unconverted_count": unconverted_count}) > 0:
        return True
    return isinstance(value, int) and not isinstance(value, bool) and value != 0


def format_field_value(key: object, value: object) -> str:
    """Render one `key: value` line for the single-resource `get` dumps.

    Money fields (keys ending in `_cents`) render as grouped major units via
    `format_cents` so a raw dump is as readable as the list tables; every other
    field is its literal value, or `(null)` when None.
    """
    if isinstance(key, str) and key.endswith("_cents"):
        return format_cents(value)
    return "(null)" if value is None else str(value)


def render_record(body: dict, *, json_mode: bool, skip: tuple[str, ...] = ()) -> None:
    """Dump one resource record: raw JSON in json_mode, else `  key: value` lines.

    The canonical renderer behind every `<resource> get` command. `skip` hides
    keys from the human dump only — `--json` stays the verbatim engine body.
    """
    if json_mode:
        emit_json(body)
        return
    for key, value in body.items():
        if key in skip:
            continue
        typer.echo(f"  {key}: {format_field_value(key, value)}")


def format_bool(value: object) -> str:
    """Human cell for booleans and truthy markers."""
    return "yes" if bool(value) else "no"


def format_month(month: dict | None) -> str:
    """Render the engine's `{year, month}` object as `YYYY-MM`."""
    if isinstance(month, dict):
        year = month.get("year")
        m = month.get("month")
        if isinstance(year, int) and isinstance(m, int):
            return f"{year:04d}-{m:02d}"
    return "(unknown)"


def redact_token(token: str) -> str:
    """8-prefix + 4-suffix mask for PATs; `****` when too short to mask safely.

    Callers own the empty/None policy (CLI shows None, TUI shows `(none)`).
    """
    if len(token) <= 8:
        return "****"
    return f"{token[:8]}****{token[-4:]}"


def items_of(body: object) -> list:
    """Rows of an engine list body (`{"items": [...]}`); [] for anything else.

    Every engine list endpoint returns an object with `items` — no route has
    returned a bare array since 2026-09-23 — so a bare list is not a body and
    yields no rows. That also makes a test fake still serving the old shape
    fail loudly instead of passing. Strict list-or-empty — never hands a dict
    or None to a row-builder.
    """
    if not isinstance(body, dict):
        return []
    items = body.get("items")
    return items if isinstance(items, list) else []


ENGINE_PAGE_CAP = 200  # the engine's hard cap on `limit` — the one copy (backlog 6.4a)
# Rows per table page, everywhere a human reads one: CLI list output and TUI
# lists share this single copy (20-row standard, picked 2026-07-11).
DEFAULT_PAGE_ROWS = 20


def effective_limit(limit: int | None, *, json_mode: bool) -> int | None:
    """The limit a list command sends: DEFAULT_PAGE_ROWS in human mode unless
    the user passed --limit. `--json` requests are left untouched (no default),
    so the raw body stays exactly what the engine returns today."""
    return DEFAULT_PAGE_ROWS if limit is None and not json_mode else limit


def fetch_all_pages(
    fetch_page: Callable[[int, int], Any], *, page_size: int = ENGINE_PAGE_CAP
) -> list[dict]:
    """Exhaust a paginated resource. `fetch_page(limit, offset)` returns one raw body.

    No caller is left since engine-uptake Phase 6 (the transaction readers
    moved to `fetch_all_cursor_pages`); Phase 10 deletes it. Stops on an empty page, a short
    page, or having collected >= body["total"] (when the engine sends an int
    total). One copy of the loop — the previous three hand-rolled variants each
    had their own termination rule.
    """
    out: list[dict] = []
    offset = 0
    while True:
        body = fetch_page(page_size, offset)
        page = items_of(body)
        out.extend(page)
        total = body.get("total") if isinstance(body, dict) else None
        if not page or len(page) < page_size or (isinstance(total, int) and len(out) >= total):
            return out
        offset += len(page)


def fetch_all_cursor_pages(
    fetch_page: Callable[[int, str | None], Any], *, page_size: int = ENGINE_PAGE_CAP
) -> list[dict]:
    """Exhaust a cursor-paged resource. `fetch_page(limit, after)` returns one raw body.

    `GET /transactions` is the one cursor-paged endpoint. The only stop is
    `next_cursor` being null (engine-spec) — not a short page, not a count: a
    page holding exactly the remaining rows already comes back null, and a
    short page with a cursor still has more.
    """
    out: list[dict] = []
    after: str | None = None
    while True:
        body = fetch_page(page_size, after)
        out.extend(items_of(body))
        after = body.get("next_cursor") if isinstance(body, dict) else None
        if after is None:
            return out


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


# The engine's stable key for the system category an uncategorised row is
# filed under (engine constants.SystemCategoryKey.PENDING, sql/038). Lookup is
# by this key, never by the display name — the owner may rename it.
PENDING_SYSTEM_KEY = "pending"
# What the CLI says when it has no reference list to read the real name from.
PENDING_FALLBACK_NAME = "pendiente"


def _pending_of(categories: list[dict]) -> tuple[str, str] | None:
    """`(id, name)` of the @Pendiente row among category rows, or None."""
    for c in categories:
        if c.get("system_key") == PENDING_SYSTEM_KEY and isinstance(c.get("id"), str):
            return (c["id"], c.get("name") or PENDING_FALLBACK_NAME)
    return None


def load_hashtag_name_map() -> dict[str, str]:
    """Live hashtag id → name map. Empty on any failure.

    The engine returns hashtag UUIDs in `hashtag_breakdown` rows and
    `hashtag_ids` columns; renderers join against this map to display human
    names like `Food + Club`. Empty map is safe — callers fall back to raw ids.
    """
    return _load_name_map("/hashtags", None)


def resolve_name(uuid_value: object, name_map: dict[str, str]) -> str:
    """Resolve `uuid_value` via `name_map`, falling back to a short-id form.

    None / non-string → `—`. Unresolvable UUID → first 8 chars (e.g. `de37af15`).
    """
    if uuid_value is None:
        return "—"
    if not isinstance(uuid_value, str):
        return str(uuid_value)
    return name_map.get(uuid_value, uuid_value[:8])


def account_choices(
    items: list, *, include_people: bool = True, with_balance: bool = False
) -> list[tuple]:
    """Picker tuples from account rows: `(id, name-or-'(unnamed)', currency)`,
    plus `current_balance_cents` when `with_balance`.

    Skips id-less rows and (unless `include_people`) person accounts. One copy
    of the build shared by the quick-log form, the new-reconciliation form,
    and the reconciliations browse (backlog 6.4c).
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
    never says which (`$` in `-$1800` is decoration). Shared by the flat
    `expense log "…"` echo and the TUI staged list, which needs it per row to
    total a batch **per currency**: soles are never added to dollars.
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

    One copy for both quick-add surfaces: the flat `expense log "…"` and the
    TUI quick-log form. What the shaping decides, and why:

    * **One superset accounts fetch** (`include_archived`, `include_people`)
      feeds both the name map and the suggestion pool; the pool then drops
      archived accounts, so you cannot type your way into a retired one but a
      transaction that already names one still renders.
    * **System categories are excluded** from the pool — `@Opening` is the
      engine's own bookkeeping, and `@Pendiente` is what an *empty* category
      means, so neither is something a typed line names.
    * **One read each, and it is every row** — the engine returns these lists
      whole (2026-09-23). Before that a single call stopped at the engine's
      default page, and every tag past it was invisible to the picker and
      unmatchable from a typed line.
    """
    from expense.commands import accounts_cmd, categories_cmd, hashtags_cmd

    accts = items_of(
        accounts_cmd.fetch_accounts(cfg, include_people=True, include_archived=True, **kw)
    )
    cats = items_of(categories_cmd.fetch_categories(cfg, **kw))
    tags = items_of(hashtags_cmd.fetch_hashtags(cfg, **kw))
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


def split_settled(people: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split person rows into `(outstanding, settled)`. Shared by every People panel.

    "Settled" is **exactly zero in the person's own currency**
    (`current_balance_cents == 0`). Three parts of that are load-bearing:

    * **Native, not home.** Every People table shows `current_balance_cents`, and
      a person whose currency has no rate today has a `null`
      `current_balance_home_cents` — treating that as settled would mark someone
      as square because an exchange rate was missing.
    * **Only an `int` counts.** A missing or non-numeric balance is *unknown*, not
      zero, so it stays in `outstanding` where it is visible.
    * **Settled is folded, never dropped.** The engine returns every person and
      explicitly refuses to filter on a computed balance (entry 2026-08-14): a
      settled person and a never-recorded loan must not look alike, and a
      coincidental net zero (lent 200, borrowed 200) is two live debts. Callers
      must always render the count — `▸ 3 settled` — never silently omit the rows.
      Deliberately *not* `has_aggregate`, which drops zero rows outright; that is
      the flow-report rule and it is the opposite of this one.

    Consumers: `expense dashboard` (`dashboard_cmd._render_people`) and the TUI
    Home screen's PEOPLE section (`home.home_rows`).
    """
    outstanding: list[dict] = []
    settled: list[dict] = []
    for person in people:
        balance = person.get("current_balance_cents")
        is_settled = isinstance(balance, int) and not isinstance(balance, bool) and balance == 0
        (settled if is_settled else outstanding).append(person)
    return outstanding, settled


def settled_label(count: int) -> str:
    """The fold line both People panels use: `▸ 3 settled` / `▸ 1 settled`.

    One copy so the CLI's printed line and the TUI's collapsed caret row cannot
    drift apart in wording. The TUI swaps the leading `▸` for `▶`/`▼` (its own
    fold carets) and keeps the rest.
    """
    return f"▸ {count} settled"


def parse_hashtag_ids(raw: str) -> list[str]:
    """`"a, b ,,c"` → `["a", "b", "c"]`. Shared by every command taking `--hashtag-ids`.

    Two behaviours here are load-bearing, not incidental:

    * **No client-side UUID validation.** A bad id is the engine's 422
      (`fields.hashtag_ids`, "Some hashtag IDs are invalid."), and it owns the
      archived-hashtag rule too — the thin-wrapper rule says we don't second-guess it.
    * **`""` → `[]`, not `None`.** An empty string is an explicit *clear*, so callers
      must pass the result to `build_update_payload` only when the flag was supplied;
      `[]` is a real value the engine acts on, while a dropped key means "leave alone".

    Consumers: `transactions update`, `log`.
    """
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def format_hashtag_cell(
    ids: object, name_map: dict[str, str], *, max_width: int | None = None, prefix: str = ""
) -> str:
    """Joined hashtag names for one table cell; unresolved ids show `xxxxxxxx…`.

    Empty / non-list → `—`. Shared by the CLI transactions table (width 24),
    the LOG bar's account peek (width 18) and the TUI Transactions screen, which
    passes no width: its table cuts the cell at the column edge itself
    (2026-09-12). Widths stay per-surface, and so does `prefix`: the peek asks
    for `#` so its rows read like the staged list directly above them.
    """
    if not isinstance(ids, list) or not ids:
        return "—"
    names = [
        prefix + (name_map.get(hid, hid[:8] + "…")) if isinstance(hid, str) else "?" for hid in ids
    ]
    joined = ", ".join(names)
    return joined if max_width is None else truncate(joined, max_width)


def render_table(
    headers: dict[str, str],
    rows: list[dict[str, str]],
    *,
    align_right: set[str] | frozenset[str] = frozenset(),
    sep: str = "  ",
    footer: dict[str, str] | None = None,
) -> None:
    """Render an ASCII table. Cells must be pre-formatted strings.

    `headers` is an ordered dict of {column-key: column-label}.
    Each `row` is a dict keyed by the same column keys.
    Cells listed in `align_right` are right-padded; the rest are left-padded.
    Width per column = max(header label, max(visible_len(cell) for cell in column)).

    `footer` (optional) is one summary row keyed like a data row; when given, it
    is printed below a second separator rule and its cells seed the column widths
    so the totals line stays aligned. A footer prints even when `rows` is empty.
    """
    if not rows and footer is None:
        return
    extra = [footer] if footer is not None else []
    widths = {
        key: max([len(headers[key])] + [visible_len(row.get(key, "")) for row in rows + extra])
        for key in headers
    }

    def fmt(text: str, key: str) -> str:
        return pad_right(text, widths[key]) if key in align_right else pad_left(text, widths[key])

    def rule() -> None:
        typer.echo(sep.join("-" * widths[key] for key in headers))

    typer.echo(sep.join(fmt(headers[key], key) for key in headers))
    rule()
    for row in rows:
        typer.echo(sep.join(fmt(row.get(key, ""), key) for key in headers))
    if footer is not None:
        rule()
        typer.echo(sep.join(fmt(footer.get(key, ""), key) for key in headers))


def query_params(**values: Any) -> dict[str, Any]:
    """The query string for one engine read: drop what was not asked for,
    encode what was, one way.

    - `None` means "not asked for" and is left out entirely. `0` is not None,
      so `offset=0` still goes.
    - A bool is a flag. `True` becomes the string `"true"` the engine reads;
      `False` is left out, because its absence IS the default.
    - Everything else passes through unchanged.

    Ints stay ints. Thirteen hand-written builders spelled this out, and they
    had already split on that last point: `reconcile` and `rates` sent
    `str(limit)` while `accounts`, `categories`, `hashtags`, `activity` and
    `transactions` sent `limit`, for the same engine parameter. httpx renders
    both identically, so nothing was broken — but two spellings of one value
    is how a real difference eventually hides.

    Keyword names are the **wire** names, not the Python ones, so the mapping
    a caller used to do by hand (`account` -> `account_id`) stays visible at
    the call site.
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


def require_yes(yes: bool, prompt_text: str, *, aborted_text: str = "Aborted.") -> None:
    """Enforce explicit confirmation before a write.

    Mirrors the pattern from `auth settings`: in non-TTY mode, --yes is mandatory;
    in TTY mode, prompt the user unless --yes was already passed.

    Destructive commands (the original callers) take the default wording.
    `expense log "<line>"` passes its own: nothing is being destroyed there —
    the prompt exists because a typed line is *parsed*, and the parse is what
    you are agreeing to.
    """
    if yes:
        return
    if not stdin_is_tty():
        typer.echo(
            "Error: --yes is required for this operation in non-interactive mode.",
            err=True,
        )
        raise typer.Exit(code=1)
    if not typer.confirm(prompt_text):
        typer.echo(aborted_text)
        raise typer.Exit(code=1)


def print_warnings(body: dict) -> None:
    """Render an engine `warnings` envelope to stderr, one line each.

    The warnings channel is deliberately per-endpoint rather than uniform: the
    key exists exactly where a warning can occur (engine-spec, "Warnings
    channel"). One endpoint carries it: `POST /reconciliations/{id}/complete`
    (since 2026-09-20), where it reports a stretch of days no completed period
    covers. Transaction restore was the other until the engine deleted restore
    on 2026-09-23.

    Worth not dropping: a transaction inside an uncovered stretch moves no
    period's arithmetic, because `difference_cents` is two balances typed off
    a statement minus the rows that were ticked. It is not hidden — it shows
    in reports and balances like any other row — but nothing else in the
    system will ever point at it.

    Human mode only; `--json` already passes the engine body through verbatim.
    """
    warnings = body.get("warnings") if isinstance(body, dict) else None
    if isinstance(warnings, list):
        for warning in warnings:
            typer.echo(f"Warning: {warning}", err=True)


def build_update_payload(items: dict[str, Any]) -> dict[str, Any]:
    """Drop None values; exit if nothing is left to update."""
    payload = {key: value for key, value in items.items() if value is not None}
    if not payload:
        typer.echo("Error: No fields to update; pass at least one flag.", err=True)
        raise typer.Exit(code=1)
    return payload


def render_totals(totals: dict | None) -> None:
    """Render the canonical inflow/outflow/net block.

    Shared by `dashboard` and `reports monthly` (single-month view) — both
    surface the same `{inflow, outflow, net}_home_cents` + `unconverted_count`
    shape. Empty/missing totals print '(no totals)'.

    Home-currency only since 2026-08-05: the native `{inflow, outflow,
    net}_cents` were deleted engine-side, because a sum across accounts in
    different currencies is a number in no currency at all. There is one figure
    per line now, so the old `(home: …)` parenthetical has nothing to hold.

    The three figures share a single `unconverted_count`, so they fail together
    — an unpriceable month collapses the whole block to one line rather than
    repeating the same count three times.
    """
    typer.echo("Totals:")
    if not isinstance(totals, dict):
        typer.echo("  (no totals)")
        return
    unconverted = unconverted_of(totals)
    if unconverted > 0:
        typer.echo(f"  {unconverted} {UNRATED_SUFFIX} — no totals this month")
        return
    for label in ("inflow", "outflow", "net"):
        amount = format_aggregate(totals.get(f"{label}_home_cents"), unconverted)
        typer.echo(f"  {label}: {amount}")


def hashtag_label(ids: list[str], name_map: dict[str, str]) -> str:
    """Format a hashtag-combo label, resolving ids via name_map.

    Empty ids -> `(no hashtags)`. Otherwise joins resolved names (or raw id
    fallback for any unresolved entry) with ` + `.
    """
    if not ids:
        return "(no hashtags)"
    return " + ".join(name_map.get(hid, hid) for hid in ids)


def render_category_table(categories: list[dict] | None) -> None:
    """Render the Categories block as Name / Home, with indented hashtag sub-rows.

    Shared by `dashboard` and `reports monthly` (single-month view). Both
    docstrings used to end by promising the other table agreed with them --
    same rules, same column name, because the two are read side by side -- and
    that promise was kept by two byte-identical copies. It is one function now,
    so agreeing is not something either caller can forget.

    The amount is `spent_home_cents` -- the only cross-account figure that
    exists since 2026-08-05, the native `spent_cents` having been deleted
    engine-side (a sum across currencies is a number in no currency). The
    column is called `Home` (Phase 4 sketch, option F).

    Categories and hashtag combinations with nothing spent are **not drawn**:
    the engine returns every non-deleted category whether or not it has
    activity, and a report is not a category list. One that could not be priced
    keeps its row and says `3 unrated` (`has_aggregate`).
    """
    typer.echo("Categories:")
    if not categories:
        typer.echo("  (no categories)")
        return

    name_map = load_hashtag_name_map()
    rows: list[dict[str, str]] = []
    for cat in categories:
        cat_unconverted = unconverted_of(cat)
        if not has_aggregate(cat.get("spent_home_cents"), cat_unconverted):
            continue
        rows.append(
            {
                "name": cat.get("name") or "(unnamed)",
                "home": format_aggregate(cat.get("spent_home_cents"), cat_unconverted),
            }
        )
        for sub in cat.get("hashtag_breakdown") or []:
            sub_unconverted = unconverted_of(sub)
            if not has_aggregate(sub.get("spent_home_cents"), sub_unconverted):
                continue
            ids = sub.get("hashtag_ids") or []
            rows.append(
                {
                    "name": "  " + hashtag_label(ids, name_map),
                    "home": format_aggregate(sub.get("spent_home_cents"), sub_unconverted),
                }
            )

    if not rows:
        typer.echo("  (no categories)")
        return

    render_table(
        headers={"name": "Name", "home": "Home"},
        rows=rows,
        align_right={"home"},
    )


def render_pagination_hint(
    body: Any,
    items: list[Any],
    *,
    note: str = "",
    always: bool = False,
    older: Literal["instant", "day_before"] = "instant",
) -> None:
    """Print `(showing N of M)`, and how to reach the rest when there is a rest.

    No-op when the body isn't paginated or the metadata is missing, and — by
    default — when one page holds everything, since there is then nothing to
    tell anyone.

    `always` prints the count even on a single page, and `note` rides on the
    same line for a list whose order is worth stating. Both exist for `rates
    list`, which kept its own tail (`showing 3 of 3 · newest first`) rather
    than use this helper, and so became the one paginated list that never
    said how to page. Its two extras cost one line each here; its missing
    instruction cost every user of it a trip to `--help`.

    A cursor-paged body (`transactions list`) has no total: when it carries a
    `next_cursor` the line says how to pass it back, and on the last page
    (`null`) nothing is printed. The cursor is bound to the filters *and* the
    sort, so the line names both. The offset branch below goes in engine-uptake
    Phase 10.

    A body that echoes a date window (`date_from` / `date_to` — `activity list`
    and `rates list` after engine-uptake Phase 8) also carries `next_cursor`,
    but is a different shape (engine debrief 6b §0) with its own line (mockup
    M5): the window, and no `--sort`, which neither command has. The
    transactions line must never print for it. Its line is always printed, even
    under an empty table, so an empty window never reads as "no history":
    `(from → to · more in this window: pass --after <c>)`, or on the window's
    last page how to go further back. `older` says how: `"instant"` (activity)
    passes the echoed `date_from` back exactly, since a bare day would widen to
    the whole day and repeat rows; `"day_before"` (rates, whose dates are
    inclusive days) passes the day before it. `note` rides on this line too.
    """
    if not isinstance(body, dict):
        return
    cursor = body.get("next_cursor")
    windowed = "date_from" in body or "date_to" in body
    if windowed:
        _render_window_hint(body, cursor, note=note, older=older)
        return
    if isinstance(cursor, str) and cursor:
        typer.echo(f"\n(more: pass --after {cursor} with the same filters and --sort)")
        return
    total = body.get("total")
    limit = body.get("limit")
    offset = body.get("offset")
    if not (isinstance(total, int) and isinstance(limit, int) and isinstance(offset, int)):
        return
    next_offset = offset + len(items)
    exhausted = next_offset >= total
    if exhausted and not always:
        return
    shown = f"showing {len(items)} of {total}"
    if note:
        shown += f" · {note}"
    more = "" if exhausted else f"; pass --offset {next_offset} --limit {limit} for more"
    typer.echo(f"\n({shown}{more})")


def _render_window_hint(
    body: dict, cursor: object, *, note: str, older: Literal["instant", "day_before"]
) -> None:
    """The date-window line of `render_pagination_hint` (engine debrief 6b §1).

    The bounds print exactly as the engine echoed them. Activity's are instants,
    in UTC when the engine chose the default window; no client-side zone math
    reformats them (todo.md engine ask "Activity takes calendar days").
    """
    date_from, date_to = body.get("date_from"), body.get("date_to")
    span = f"{date_from} → {date_to}"
    if note:
        span += f" · {note}"
    if isinstance(cursor, str) and cursor:
        typer.echo(f"\n({span} · more in this window: pass --after {cursor})")
        return
    if not isinstance(date_from, str) or not date_from:
        typer.echo(f"\n({span})")
        return
    back = date_from
    if older == "day_before":
        back = (date.fromisoformat(date_from[:10]) - timedelta(days=1)).isoformat()
    typer.echo(f"\n({span} · older: pass --to {back})")


def run_toggle(
    ctx: typer.Context,
    *,
    resource: str,
    id_: str,
    verb: str,
    json_output: bool,
    render_human: Callable[[dict], None],
    hints: dict[int, str] | None = None,
) -> None:
    """Execute one of the {archive, unarchive} toggle verbs.

    Both are POST /{resource}/{id}/{verb} with no body and an identical
    response shape (the resource row).

    `hints` maps HTTP status code → stderr hint string. When the engine
    raises an EngineError whose `.status` matches a key, the hint is
    printed before the error envelope renders. This lets archive/unarchive
    on resources with domain-specific 403/409 conditions (e.g. system
    categories, name conflicts) keep their friendly recovery prompts
    without forking the call site.
    """
    cfg: Config = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    with ExpenseClient(cfg, verbose=verbose) as client:
        body = _hinted(lambda: client.post(f"/{resource}/{id_}/{verb}"), hints)

    if json_output:
        emit_json(body)
    else:
        render_human(body)


def run_delete(
    ctx: typer.Context,
    *,
    resource: str,
    id_: str,
    confirm: str,
    yes: bool,
    json_output: bool,
    hints: dict[int, str] | None = None,
    skip: tuple[str, ...] = (),
) -> None:
    """Execute one `delete` command: confirm, DELETE /{resource}/{id}, render.

    The sibling of `run_toggle`, and written for the same reason. That one's
    docstring says `hints` exists so a resource with a domain-specific 403/409
    can "keep their friendly recovery prompts without forking the call site" —
    but only the toggle verbs ever got the helper, so all five deletes forked
    anyway, each re-spelling the same confirm → open → try → hint → render.

    What stays with the resource is what differs: `confirm` is its own warning
    (a hashtag cascades to junction rows, a reconciliation unassigns its
    transactions), `hints` its own recovery prompts, and `skip` the fields its
    record view drops. Everything else is plumbing.
    """
    require_yes(yes, confirm)

    cfg: Config = config_module.ensure_loaded()
    verbose = get_verbose(ctx)

    with ExpenseClient(cfg, verbose=verbose) as client:
        body = _hinted(lambda: client.delete(f"/{resource}/{id_}"), hints)

    render_record(body, json_mode=json_output, skip=skip)


def _hinted(call: Callable[[], dict], hints: dict[int, str] | None) -> dict:
    """Run one engine call; on an EngineError whose status has a hint, print it
    to stderr before letting the error out to `handle_errors`.

    The hint goes first because the error envelope below it is the engine's
    words, and the recovery prompt is ours.
    """
    try:
        return call()
    except EngineError as err:
        if hints and err.status in hints:
            typer.echo(hints[err.status], err=True)
        raise
