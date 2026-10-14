"""How engine values read on screen, one copy each: cells, labels and shared wording.

Pure: no HTTP, no typer, no config. A function here takes engine data and
returns text, or the shaped rows a table draws. The TUI and the typed commands
both render through these, so a figure reads the same wherever it appears.
"""

import re

from expense.currencies import MINOR_UNIT_SCALE

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def visible_len(text: str) -> int:
    """Length of `text` ignoring ANSI escape sequences."""
    return len(_ANSI_RE.sub("", text))


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


def format_month(month: dict | None) -> str:
    """Render the engine's `{year, month}` object as `YYYY-MM`."""
    if isinstance(month, dict):
        year = month.get("year")
        m = month.get("month")
        if isinstance(year, int) and isinstance(m, int):
            return f"{year:04d}-{m:02d}"
    return "(unknown)"


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

    The engine converts currency at read time, so every aggregate is
    nullable and paired with an `unconverted_count`: when any row in the group
    falls on a date with no resolvable rate, the figure comes back `None` and the
    count says how many rows are behind it.

    **A `None` here is neither zero nor missing** — the engine declined to report
    a partial total — so it renders as `3 unrated`, never `0.00`, and never by
    falling back to a native figure (the exact bug the engine deleted: reading
    USD cents as PEN cents understated by 3.58×).

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
    report.

    A row the engine *could not price* is emphatically not empty: it keeps its
    line and says `3 unrated`, so it is never mistaken for one with no spending.
    """
    if unconverted_of({"unconverted_count": unconverted_count}) > 0:
        return True
    return isinstance(value, int) and not isinstance(value, bool) and value != 0


def redact_token(token: str) -> str:
    """8-prefix + 4-suffix mask for PATs; `****` when too short to mask safely.

    Callers own the empty/None policy (CLI shows None, TUI shows `(none)`).
    """
    if len(token) <= 8:
        return "****"
    return f"{token[:8]}****{token[-4:]}"


def resolve_name(uuid_value: object, name_map: dict[str, str]) -> str:
    """Resolve `uuid_value` via `name_map`, falling back to a short-id form.

    None / non-string → `—`. Unresolvable UUID → first 8 chars (e.g. `de37af15`).
    """
    if uuid_value is None:
        return "—"
    if not isinstance(uuid_value, str):
        return str(uuid_value)
    return name_map.get(uuid_value, uuid_value[:8])


def format_hashtag_cell(
    ids: object, name_map: dict[str, str], *, max_width: int | None = None, prefix: str = ""
) -> str:
    """Joined hashtag names for one table cell; unresolved ids show `xxxxxxxx…`.

    Empty / non-list → `—`. Shared by the CLI transactions table (width 24),
    the LOG bar's account peek (width 18) and the TUI Transactions screen, which
    passes no width: its table cuts the cell at the column edge itself.
    Widths stay per-surface, and so does `prefix`: the peek asks
    for `#` so its rows read like the staged list directly above them.
    """
    if not isinstance(ids, list) or not ids:
        return "—"
    names = [
        prefix + (name_map.get(hid, hid[:8] + "…")) if isinstance(hid, str) else "?" for hid in ids
    ]
    joined = ", ".join(names)
    return joined if max_width is None else truncate(joined, max_width)


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
      explicitly refuses to filter on a computed balance: a
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


SYSTEM_HINT = "System categories can be renamed but not deleted."


STATUS_LABELS = {1: "draft", 2: "completed"}


def format_status(value: object) -> str:
    """Human label for the engine's integer status. Shared by flat table + TUI."""
    if value is None:
        return "—"
    return STATUS_LABELS.get(value, str(value))


def format_period(item: dict) -> str:
    """`date_start → date_end`. Shared by flat table + TUI. Both are calendar
    days on the wire (contract: "Date inputs"), and every period has both
    (contract: POST /v1/reconciliations)."""
    return f"{item['date_start']} → {item['date_end']}"


#: A month in which a row had no activity at all. Distinct from `3 unrated`,
#: which means there *was* activity the engine could not price.
NO_ACTIVITY_MARK = "—"


#: The month-totals rows the grid carries under the categories, in draw order.
#:
#: `inflow`/`outflow` come back from the engine **positive** — outflow is not a
#: negative number — so only `net` is signed. Renderers must colour accordingly
#: or a month's spending reads as income.
TOTALS_KEYS = ("inflow", "outflow", "net")


def _grid_cell_value(payload: dict) -> dict:
    """One grid cell: the home figure plus the count that explains a missing one.

    Kept as a dict rather than a bare int because `None` alone cannot carry the
    difference between "nothing happened" and "the engine refused to price
    this" — the conflation this dict exists to prevent.
    """
    return {
        "cents": payload.get("spent_home_cents"),
        "unconverted": unconverted_of(payload),
    }


def _totals_cell(totals: dict, key: str) -> dict:
    """One totals cell, same shape as `_grid_cell_value`.

    All three figures share the month's single `unconverted_count`, so they fail
    together: an unpriceable month reports `3 unrated` on every row rather than a
    partial total on some.
    """
    return {
        "cents": totals.get(f"{key}_home_cents"),
        "unconverted": unconverted_of(totals),
    }


def cell_is_empty(cell: object) -> bool:
    """True for a cell with no activity — nothing spent, and nothing unpriced."""
    if not isinstance(cell, dict):
        return True
    return not has_aggregate(cell.get("cents"), cell.get("unconverted"))


def build_range_grid(months: list[dict]) -> dict:
    """Merge a range payload into grid rows. Pure data; shared by flat + TUI.

    Categories (and each category's hashtag combos) keep first-appearance order
    across the window. All amount cells are home-currency (`spent_home_cents` /
    `net_home_cents`) — the only figures that exist, the native aggregates
    having been deleted engine-side.

    A cell carries its `unconverted_count` alongside the figure, because three
    states have to stay distinguishable: a number, *no activity that month*, and
    *the engine could not price this* (`cents: None` with a non-zero count). A
    month a row is absent from has no cell at all, which reads as no activity.

    Rows (and combos) with nothing spent in **any** month of the window are
    dropped entirely — the engine returns every non-deleted category for every
    month, so keeping them would fill the grid with blank lines. Returns::

        {
          "labels": ["2026-04", ...],
          "rows": [{"id", "name",
                    "cells": {label: {"cents": int|None, "unconverted": int}},
                    "breakdown": [{"hashtag_ids": [...], "cells": {...}}]}],
          "totals": {"inflow":  {label: {"cents": int|None, "unconverted": int}},
                     "outflow": {label: ...},
                     "net":     {label: ...}},
        }

    `totals` carries all three `TOTALS_KEYS` — the flat range table draws only
    `net`, but Home's grid needs inflow and outflow, and computing them twice
    would be two places to get the `unconverted_count` rule wrong.
    """
    labels = [format_month(m.get("month")) for m in months]

    order: list[str] = []
    rows_by_id: dict[str, dict] = {}
    combo_index: dict[tuple[str, tuple[str, ...]], dict] = {}
    for label, month_payload in zip(labels, months, strict=True):
        for cat in month_payload.get("categories") or []:
            cat_id = cat.get("id")
            if not isinstance(cat_id, str):
                continue
            row = rows_by_id.get(cat_id)
            if row is None:
                row = {
                    "id": cat_id,
                    "name": cat.get("name") or "(unnamed)",
                    "cells": {},
                    "breakdown": [],
                }
                rows_by_id[cat_id] = row
                order.append(cat_id)
            row["cells"][label] = _grid_cell_value(cat)
            for sub in cat.get("hashtag_breakdown") or []:
                ids = sub.get("hashtag_ids") or []
                combo_key = (cat_id, tuple(ids))
                combo = combo_index.get(combo_key)
                if combo is None:
                    combo = {"hashtag_ids": ids, "cells": {}}
                    combo_index[combo_key] = combo
                    row["breakdown"].append(combo)
                combo["cells"][label] = _grid_cell_value(sub)

    totals_rows: dict[str, dict[str, dict]] = {key: {} for key in TOTALS_KEYS}
    for label, month_payload in zip(labels, months, strict=True):
        totals = month_payload.get("totals") or {}
        for key in TOTALS_KEYS:
            totals_rows[key][label] = _totals_cell(totals, key)

    rows = []
    for cid in order:
        row = rows_by_id[cid]
        if all(cell_is_empty(c) for c in row["cells"].values()):
            continue
        row["breakdown"] = [
            combo
            for combo in row["breakdown"]
            if not all(cell_is_empty(c) for c in combo["cells"].values())
        ]
        rows.append(row)

    return {"labels": labels, "rows": rows, "totals": totals_rows}
