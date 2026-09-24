# Engine debrief: Phase 6, part 2 (activity and rates scroll by cursor; offset is gone)

**For:** whoever changes the CLI/TUI next. **Status:** shipped and pushed in the engine
(`51cce79`, `eac853b`, `716fa21`, all 2026-09-23). **The running engine on `:8000` is still the
old process.** Nothing breaks until it is restarted. Restart it only once this work has landed,
the same rule as `cursor-uptake-plan.md`.
**Authority:** `expense_world_engine/docs/engine-spec.md`, in two places: *Lists come in three
shapes*, *Cursors* and *Date windows* under Base Conventions, and then the `GET /activity` and
`GET /exchange-rates/history` sections. If this note and the spec disagree, the spec wins. The
design reasoning is in `expense_world_engine/docs/transaction-pagination-plan.md` §4.1 and
Phase 6.
**When done:** delete this file, and tell the engine side to delete its `docs/open-bugs.md` entry
`phase-6-lists`, or the parts of it that are done.

This continues `engine-debrief-2026-09-23-phase6.md` (part 1: restore gone, caps, lists whole).
That debrief's shape table listed `/activity` and `/exchange-rates/history` as "still offset, for
now". This is the "later debrief" it promised.

---

## 0. At a glance

| Commit | What | For the CLI |
|---|---|---|
| `51cce79` **6.5** | **`GET /activity` scrolls by cursor inside a date window** | ⚠️ Breaking. §2 |
| `eac853b` **6.6** | **`GET /exchange-rates/history` scrolls the same way; `?date=` is gone** | ⚠️ Breaking. §3 |
| `716fa21` **6.7** | **The engine's offset code is deleted. No endpoint pages by position** | Cleanup. §4 |

**All the breakage is loud.** A stale `offset=` gets a `422` that names `after` as the replacement.
A stale `date=` on rates gets a `422` as an unknown param. Nothing returns wrong data with a 200.

**Every list is now one of three shapes, and all three are built:**

| Shape | Response | Lists |
|---|---|---|
| **Unpaged** | `{items}`, the whole set | `/accounts`, `/categories`, `/hashtags`, `/categories/{id}/hashtags`, `/reconciliations?account_id=` |
| **Cursor** | `{items, limit, next_cursor}` | `/transactions` |
| **Cursor + date window** | `{items, limit, next_cursor, date_from, date_to}` | `/activity`, `/exchange-rates/history` |

---

## 1. How a windowed list works (both endpoints)

This is the one new idea. Everything in §2 and §3 follows from it.

- **The window is a fence around the scroll.** Each request reads one stretch of time,
  `date_from` to `date_to`, **both ends inclusive**. Inside it you scroll with the cursor
  exactly as on `/transactions`: send `after=<next_cursor>` until `next_cursor` is `null`.
  **`null` means the end of this window, not the end of the data.**
- **Defaults:** an omitted `date_to` is "now". An omitted `date_from` is **30 days** before
  `date_to`.
- **Maximum:** `date_to − date_from` may be at most **366 days**. Wider is a `422` on both
  fields: refused, never clamped. `date_from` after `date_to` is a `422` on `date_from`.
- **The response echoes the window it read**, defaults already resolved: `date_from` and
  `date_to`. **To load older rows, send `date_to` = the echoed `date_from`.** The client never
  needs to know what the default is. With both ends inclusive, a row stamped exactly on the
  boundary would appear in both windows. That can't happen for rates (dates, see §3). For the
  log, subtract one microsecond if you care.
- **The cursor remembers the window.** On page 2 and later, the engine reads the window from
  the cursor, so a default "last 30 days" does not creep forward while you scroll. Send the same
  `date_from` / `date_to` you sent on page 1 (or omit them again if you omitted them). A cursor
  reused with a different filter or window is a `422` on `after`.
- **`?limit=`** is `[1, 200]`, default 50, and may change between pages.
- **`?offset=`** is a `422`: `fields: {"offset": "Removed; pass the previous page's
  \`next_cursor\` as \`after\`."}`.
- **Forward only.** There is no `before=`. For "previous page", keep the cursors you already
  received.
- **No `total` and no count endpoint** for either list. Nothing needed one.

The helper you already have for `/transactions`, `fetch_all_cursor_pages`
(`commands/_resource.py:311`), walks one window whole. It takes `fetch_page(limit, after)`, so
close over the window params.

---

## 2. `GET /activity` (6.5)

### 2.1 What changed

- **Params:** `resource_type`, `resource_id`, `date_from`, `date_to`, `after`, `limit`.
- **`date_from` / `date_to` are instants**, RFC 3339 **with an offset** (`2026-09-01T00:00:00-05:00`
  or `…Z`). A naive value such as `2026-09-01T00:00:00` is a `422`. A bare date is a `422` too.
  So `--from 2026-09-01` in the CLI has to become midnight in the user's `display_timezone`
  before sending. The engine will not guess a zone.
- **Order is `created_at DESC, id DESC`.** Before this it was `created_at DESC` alone, and a batch
  that stamps up to 200 entries with one timestamp came back in arbitrary order. The order within
  such a batch is now stable. Nothing to change in the CLI; it's just no longer random.
- ⚠️ **`resource_id` does NOT lift the window** (owner decision, 2026-09-23). `activity list
  --resource-id X` now shows **only the last 30 days** of that item's history. To see an older
  item's creation, the user adds a `--from` that reaches back to it. This is on purpose: one rule,
  not a special case. Say so in the command's help text so it doesn't read as a bug.

### 2.2 Site by site

| Site | Change |
|---|---|
| `commands/activity_cmd.py:257` `fetch_activity` | Drop `offset`. Add `after`, `date_from`, `date_to`. |
| `commands/activity_cmd.py:283` `list_` | Drop `--offset` (`OFFSET_OPT`). Add `--from` / `--to`, converting a bare date to midnight in `display_timezone` with an offset. Print the echoed window, and "older: `--to <date_from>`" when the window is exhausted. Help text for `--resource-id` says the window still applies. |
| `commands/activity_cmd.py:254` `render_pagination_hint(body, items)` | The offset hint has nothing to point at. Replace it with a cursor/window hint, or drop it. |
| `tui/screens/system.py:227` `ActivityScreen(PagedListMixin, …)` | Leave `PagedListMixin` (it sends `limit`/`offset`). Scroll by cursor within the window, and add a key for "older window" that re-fetches with `date_to` = the echoed `date_from`. The legend "most recent first" stays true. |
| `tests/unit/test_cmd_activity.py` | Mocks return `{items, total, limit, offset}`. Change them to the windowed envelope and add the window params. |

---

## 3. `GET /exchange-rates/history` (6.6)

### 3.1 What changed

- **Params:** `date_from`, `date_to`, `after`, `limit`. These are **ISO dates** (`2026-09-01`), not
  instants.
- **`?date=` is gone.** Sending it is a `422` as an unknown param. **One day is
  `date_from=X&date_to=X`.**
- **The default `date_to` is today in the user's `display_timezone`**, the same "today" as
  `GET /exchange-rates`. The default window is 31 rows at one rate per day (30 days back, both
  ends inclusive).
- **Order is `rate_date DESC, base DESC, target DESC`.** Within one day this used to be `base ASC`.
  With only USD→PEN stored this makes no visible difference.
- An empty window is `200` with `items: []` and `next_cursor: null`, not a `404`, as before.
- For "older", send `date_to` = the echoed `date_from` minus one day. Dates are inclusive, so
  reusing the same day would repeat that day's row.

### 3.2 Site by site

| Site | Change |
|---|---|
| `commands/rates_cmd.py:138` `fetch_rates_history` | Drop `offset` and `date`. Add `after`, `date_from`, `date_to`. |
| `commands/rates_cmd.py:159` `list_` | `--date X` sends `date_from=X&date_to=X`. Drop `--offset`. Optionally add `--from` / `--to`. The "Omit for full history" help text is no longer true: omitting it gives the last 30 days. |
| `commands/rates_cmd.py:199` `render_pagination_hint(…, always=True)` | Same as §2.2: the offset hint has nothing to point at. |
| `tui/screens/system.py:304` `RatesScreen(PagedListMixin, …)` | Leave `PagedListMixin`. The `f` filter (`action_filter_date`, line 378) becomes a one-day window. The "(no rates stored yet)" empty text should say "in this window" instead. |
| `tests/unit/test_cmd_rates.py` | Same as the activity mocks. |

---

## 4. Offset is gone from every endpoint (6.7)

With 6.6, no endpoint accepts `offset` any more. The engine deleted its own offset code, and
the CLI's offset code now has nothing to talk to. **Once §2 and §3 (and part 1's §3) are
done:**

| Site | Change |
|---|---|
| `commands/_resource.py:286` `fetch_all_pages` | Delete it. Part 1 already turned its unpaged callers into single GETs (`tui/screens/categories.py:44`, `hashtags.py:38`, `reconciliations.py:209`, `_resource.py:342/508/511`). Any caller still paging `/transactions` (`bank_import_cmd.py:192`, `reconciliations.py:713`, `import_/apply.py:70`) belongs on `fetch_all_cursor_pages`, per the transaction-cursor debrief. |
| `commands/_resource.py:29` `OFFSET_OPT` | Delete, with every `--offset` option. |
| `commands/_resource.py:849` `render_pagination_hint` | Drop the offset branch. |
| `tui/screens/_base.py:172` `PagedListMixin` | Once the activity, rates and ledger screens have left it, nothing uses it. Delete it or turn it into the cursor version. |

**Check:** `grep -rn "offset" expense/` should find nothing that talks to the engine.

---

## 5. Also found (engine side, not yet fixed)

**`GET /transactions` accepts a naive `date_from` / `date_to`** and reads it as UTC. That's
inconsistent with the rule `/activity` now enforces. It's logged in the engine as
`transaction-date-filter-naive`, to be fixed together with `date-filter-not-calendar-days`. When
it is, bare dates on `/transactions` will start to `422` unless that fix accepts them on purpose.
**Don't build on bare dates being read as UTC there.**
