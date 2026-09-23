# Engine debrief: everything that changed on 2026-09-23, and what the CLI must do

**For:** whoever changes the CLI/TUI next. **Status:** all of it is shipped and pushed in the
engine. **The CLI is broken until §3 is done.** Four call sites fail with a `422`, and two keep
running but show wrong numbers without any error.
**Authority:** `expense_world_engine/docs/engine-spec.md`. If this note and the spec disagree,
the spec wins.
**When done:** delete this file, and tell the engine side to delete its `docs/open-bugs.md` entry
`transaction-cursor`.

This one file replaces `engine-change-transaction-pagination.md` and the 2026-09-22
`engine-asks-brief.md`. Both are gone.

---

## 0. The day at a glance

Five engine commits, in order:

| Commit | What | For the CLI |
|---|---|---|
| `f6a3181` | The pagination plan written down (`docs/transaction-pagination-plan.md`) | Nothing. Background only. |
| `6e93a16` | The manual "erase everything" procedure fixed (`deploy/local/README.md`) | Nothing to fix. One CLI fact now lives there, see §6.2. |
| `7997fc6` | **`GET /transactions` is cursor-paged, gains `?sort=`, and the count moves to `GET /transactions/count`** (ask A1) | ⚠️ **Breaking.** §1–§4 |
| `7788252` | **The coverage-gap warning on `complete` names the right days, and returns them as data** (asks A2 + A5) | ➕ Additive. Nothing breaks. §5 |
| `acbd10f` | Asks A3 and A4 declined, with reasons (engine `open-bugs.md` D13, D14) | Read §6.1. One CLI hint is right only by luck. |

---

## 1. What is broken right now, and how it shows

It fails in two ways, and **the silent one is the dangerous one**:

| Site | What happens today | Visible? |
|---|---|---|
| **Unfiled pane** (`tui/screens/reconciliations.py:395-420`) | The `limit=1` probe succeeds but has no `total`, so it falls back to `len(items)` = 1, skips the second read, and shows **one row and "1 to file"** | ❌ **Silent, wrong** |
| **LOG bar account peek** (`tui/screens/log_bar.py:1109-1127`) | No `total`, so it falls back to `len(items)` and the account's row count is understated | ❌ **Silent, wrong** |
| **Ledger screen** (`tui/screens/transactions.py`, via `PagedListMixin.page_fetch_kwargs`) | Always sends `offset`, so `422` | ✅ Loud |
| **Bank importer's duplicate matching** (`commands/bank_import_cmd.py:181` `fetch_ledger`) | `fetch_all_pages` sends `offset=0`, so `422`. **The importer is down.** | ✅ Loud |
| **Reconciliation checklist** (`tui/screens/reconciliations.py:707` `_fetch_all_txns`) | `fetch_all_pages` sends `offset=0`, so `422` | ✅ Loud |
| **Flat `expense transactions list`** | Works for page 1 (no `--offset` sent). `--offset` is a `422` | Partly |

Fix the two silent ones even if you do nothing else. A pane that says "1 to file" when the
real figure is 1,716 looks correct to the owner, so they will believe it.

---

## 2. The cursor change (A1)

### 2.1 What changed and why

`GET /transactions` used to page by position (`limit` / `offset`, with a `total`). It now pages by
**bookmark**: every page hands back a `next_cursor`, and you pass that back as `?after=` to get the
next page. The row count moved to its own endpoint, `GET /transactions/count`.

The reason is the unfiled pane. It is a work queue that shrinks as you file rows. With offset
paging, filing 40 rows shifts every remaining row up by 40, so "the next page" skipped 40 rows the
owner had never seen. That happened silently, on every batch. A bookmark points at the last row you
saw, so rows filed behind it don't move anything ahead of it.

**Only this one endpoint changed.** Every other list keeps `limit` / `offset` / `total` exactly as
before: `/accounts`, `/categories`, `/hashtags`, `/reconciliations`, `/activity`,
`/exchange-rates/history`, `/categories/{id}/hashtags`. So does the transaction list embedded in
`GET /reconciliations/{id}`.

### 2.2 `GET /transactions`

| Param | Meaning |
|---|---|
| `account_id`, `category_id`, `hashtag_id`, `reconciliation_id`, `unreconciled`, `date_from`, `date_to`, `search`, `include_deleted`, `debit_as_negative` | **Unchanged.** |
| `sort` | **New.** `date_desc` (default, newest first) or `date_asc` (oldest first). |
| `limit` | Unchanged: 1–200, default 50. |
| `after` | **New.** The `next_cursor` from the previous page. Omit it for the first page. |
| `offset` | **Gone. Sending it at all, even `offset=0`, is a `422`.** |

Response (shape taken from the running engine; values shortened):

```json
{
  "items": [
    {"id": "2ecfc4b0-…", "date": "2024-04-06T05:00:00Z", "amount_cents": 711, "…": "…"},
    {"id": "3c5bcd77-…", "date": "2024-04-06T05:00:00Z", "amount_cents": 11112, "…": "…"}
  ],
  "limit": 2,
  "next_cursor": "eyJrIjpbIjIwMjQtMDQtMDZUMDU6MDA6MDArMDA6MDAiLC…"
}
```

- Items are the same transaction objects as before, so nothing about a row changed.
- **There is no `total` and no `offset` in the response any more.**
- `next_cursor` is `null` on the last page. That is the only stop signal. A page that happens to
  hold exactly the remaining rows already comes back with `null`, so you never fetch an empty page.
- **Order:** `date`, then `created_at`, then `id`, all in the direction `sort` names. `date_asc` is
  the exact reverse of `date_desc`.

### 2.3 `GET /transactions/count`

Same filter params as the list (`sort` / `after` / `limit` don't apply). Returns:

```json
{"count": 1716}
```

It takes exactly the same filters, from the same code, so the count and the list always describe
the same rows.

### 2.4 The `422`s you can now hit

All in the standard error shape. `fields` names the parameter.

| You sent | `fields` | Meaning |
|---|---|---|
| `offset=…` (any value) | `offset` | Old paging code. Switch to `after`. |
| `sort=newest` (anything but the two values) | `sort` | Typo. There is no silent fallback to the default. |
| `after=<cursor>` with different filters or sort than the cursor was issued under | `after` | The message names what differs, e.g. ``This cursor was issued for a different `sort`, `unreconciled`.`` Drop the cursor and start from page 1. |
| `after=<anything the engine didn't issue>` | `after` | Corrupt or hand-built cursor. |

⚠️ **A misspelled parameter *name* is not a `422`.** `?sorrt=date_asc` is silently ignored and
you get newest-first (engine `open-bugs.md` → `query-params-open`, not fixed). Only a wrong
*value* for `sort` is caught. Have a test check that the rows really come back oldest-first,
not only that the request succeeded.

### 2.5 Rules for the client

1. **The cursor is a black box.** Store it, send it back, never parse or build one. Its
   contents are the engine's to change without notice.
2. **A cursor belongs to one filter + sort.** Whenever the filter or sort changes, throw the
   cursor away and start from page 1. (Resetting on filter change is what `reset_page()` already
   does. Keep doing that.) Changing `limit` mid-scroll is fine: page size isn't part of the binding.
3. **Stop when `next_cursor` is `null`.** Don't stop on a short page and don't compare against a
   count. `null` is the contract.
4. **Ask for the count once**, when a pane opens or after a write that changes it, not on every
   page. Not having to count on every page is the reason the count got its own endpoint.
5. **Forward only.** There is no `before=`. For "previous page", keep the cursors you've already
   been given (see the Ledger screen below).
6. **To start at the oldest rows, use `sort=date_asc`.** Don't jump to "the last page"; that
   concept is gone.

---

## 3. Site by site

### 3.1 `commands/transactions_cmd.py`: `fetch_transactions` + `transactions list`

`fetch_transactions(…, limit, offset, …)` drops `offset` and gains `sort: str | None` and
`after: str | None`. The flat `expense transactions list` command loses `--offset` (`OFFSET_OPT`
stays, since other commands still use it). Give it `--sort` and, if you want flat-CLI paging,
`--after`. Print `next_cursor` in `--json` mode (it's already in the body) and, in table mode, a
hint to pass it back.

### 3.2 A cursor version of `fetch_all_pages` (`commands/_resource.py`)

`fetch_all_pages(fetch_page(limit, offset))` is shared with the offset endpoints, so **don't change
it.** Add a sibling for this one endpoint, e.g.:

```python
def fetch_all_cursor_pages(fetch_page: Callable[[int, str | None], Any], *,
                           page_size: int = ENGINE_PAGE_CAP) -> list[dict]:
    out, after = [], None
    while True:
        body = fetch_page(page_size, after)
        out.extend(items_of(body))
        after = body.get("next_cursor")
        if after is None:
            return out
```

Two callers move to it:

- **`commands/bank_import_cmd.py:181` `fetch_ledger`.** The importer's duplicate matching over the
  leg accounts. **This breaks the importer outright until fixed.**
- **`tui/screens/reconciliations.py:707` `_fetch_all_txns`.** The reconciliation working screen's
  checklist.

### 3.3 Ledger screen: `tui/screens/transactions.py`

It uses `PagedListMixin` (`tui/screens/_base.py:172`), which **Activity and Rates also use**, and
they stay offset-paged. So don't convert the mixin. Give the Ledger screen a cursor variant (a
`CursorPagedListMixin`, or the same logic inline):

- **Next page:** fetch with `after=<the current page's next_cursor>`. Disable "next" when it is `null`.
- **Previous page:** keep a stack of the cursors you used to reach each page (page 1 = `None`).
  "Previous" pops and refetches with the cursor below. Rows edited since are re-read, which is what
  you want.
- **"Page X of Y" / the total:** call `GET /transactions/count` with the same filters when the
  screen loads or the filter changes, and after a bulk edit (a `c`/`b`/`h` re-category on a filtered
  list makes rows leave). Y = `ceil(count / page_rows)`.
- **Terminal resize (`_viewport_resized`):** you can't re-anchor by offset any more. Refetch the
  current page with its own starting cursor and the new `limit`. The first visible row stays first,
  which is what the old re-anchoring was trying to achieve. The stack of *earlier* cursors stays
  valid (they're bookmarks, not positions), but the page count shifts. Clearing the stack and
  recounting is the simple, correct choice.
- **"Past the end" snapping** (`fetch_page_body`'s refetch when a delete emptied the last page) is
  no longer needed. A cursor page is never "past the end". If a page comes back empty after
  deletes, step back one cursor.
- **Jump to last page** is gone. If you want "oldest first", flip to `sort=date_asc`.

### 3.4 Unfiled pane: `tui/screens/reconciliations.py:390-420` (silently wrong today, §1)

Today it makes two reads: `limit=1` to learn `total`, then `offset=unfiled_offset(total, UNFILED_PAGE)`
to reach the oldest rows, reversed for display. Replace both:

- `sort=date_asc`, `unreconciled=true`, `account_id=…` → the oldest rows first, directly. Nothing to
  reverse and no second read.
- **"N to file"** comes from `GET /transactions/count` with the same three filters.
- `unfiled_offset()` (line 84) and its comment's "the engine has no sort parameter" can be deleted.
- **The 40-row cap (`UNFILED_PAGE`)** existed because offset paging couldn't survive rows being
  filed mid-scroll. With `after=`, it can: file some rows, fetch the next page with the cursor you
  already hold, and nothing is skipped. Keeping one page plus `r` to reload still works if you'd
  rather not change the UX now. Just know the reason for the cap is gone.

### 3.5 LOG bar account peek: `tui/screens/log_bar.py:1109-1127` (silently wrong today, §1)

`_load_peek` fetches `limit=PEEK_LIMIT` and `_peek_loaded` reads `body["total"]`, which no longer
exists. Get the total from `GET /transactions/count?account_id=…`, fetched alongside the peek. The
fallback `len(items)` is what understates it now. Delete the fallback rather than keep it, so a
missing count shows up as an error instead of a wrong number.

### 3.6 Unchanged, so don't touch these

- Every other list endpoint's `limit` / `offset` / `total`, and `fetch_all_pages` for them.
- `GET /reconciliations/{id}`'s embedded `transactions` + `transactions_total` / `_limit` /
  `_offset` / `_truncated`. Still offset-paged. Its order just gained a final `id` tie-break
  (`date DESC, created_at DESC, id DESC`), so it's now fully deterministic.
- Transaction objects themselves, all write endpoints, and `debit_as_negative`.

---

## 4. Checking it works

- **Unfiled pane on the real ledger:** the header count matches
  `GET /transactions/count?account_id=…&unreconciled=true`, the rows start from the oldest date,
  and filing a page then scrolling on neither skips nor repeats a row.
- **Importer:** a dry run over a statement you have already imported flags every row as a
  duplicate, as it did before today.
- **Ledger screen:** `date_asc` page 1 equals the old last page, reversed. The ledger has 744
  groups of rows sharing both `date` and `created_at`, so paging through all of it and comparing
  the ids to one full fetch catches any tie-handling mistake.

---

## 5. `complete` names the gap correctly and returns it as data (A2 + A5)

**Status:** shipped in the engine, commit `7788252`. **Additive**, so nothing in the CLI breaks.
**Authority:** `engine-spec.md` → `POST /reconciliations/{id}/complete`, the `warnings` and
`coverage_gap` paragraph.

### 5.1 What was wrong

When you complete a period after skipping days, the engine warns you. The warning named the
**wrong two days**: it used the last *covered* day and the first *covered* day. With June closed on
2026-06-25 and the next period starting 2026-07-24, the user was told:

> 2026-06-25 to 2026-07-24 is not covered by any completed reconciliation on this account — the
> days after 'June 2026' and before this period are sealed by nothing.

The uncovered days are really **2026-06-26 to 2026-07-23**. On top of that, the dates existed only
inside the sentence, so no screen could use them.

### 5.2 The new response

Two keys, both **always present** on `complete`, both built from the same object in the engine so
they can never disagree:

```json
{
  "...": "the reconciliation, unchanged",
  "warnings": [
    "The days 2026-06-26 to 2026-07-23 are not covered by any completed reconciliation on this account — they fall between 'June 2026' and this period (3 unfiled transactions in them)."
  ],
  "coverage_gap": {
    "first_uncovered_day": "2026-06-26",
    "last_uncovered_day":  "2026-07-23",
    "unfiled_count": 3
  }
}
```

With no gap: `"warnings": []` and `"coverage_gap": null`.

| Field | Meaning |
|---|---|
| `first_uncovered_day`, `last_uncovered_day` | Plain dates (`YYYY-MM-DD`) in the user's `display_timezone`. **Both inclusive, both uncovered.** A one-day gap has the same day in both. |
| `unfiled_count` | Rows on this account, dated in those days, not deleted, and assigned to **no** reconciliation. This is the same rule that blocks a close. The `@Opening` seed is not counted, and **a row filed under a draft is not counted** (it is filed). |

The sentence's count wording is "no unfiled transactions in them" at zero, "1 unfiled transaction
in them" at one, and "N unfiled transactions in them" above that.

### 5.3 Behaviour worth knowing

- **An empty gap still warns.** `unfiled_count: 0` is the usual case. The skipped days are the
  finding, whether or not anything is in them.
- **Completing an already-completed period re-reports the gap.** It used to return `[]` because
  nothing happened. Now `null` / `[]` only ever means "there is no gap", never "the engine didn't
  look".
- **Only the gap *before* the period is reported.** If you close an older period late, when a
  later one is already completed, the days *after* it are not reported (engine `open-bugs.md` →
  `gap-after-unreported`). Don't build anything on the assumption that it reports both sides.
- **Old idempotent replays** return their stored snapshot as-is. A key used before 2026-09-23 comes
  back without a `coverage_gap` key. Treat a missing key as "unknown", not as "no gap".
- `revert` is unchanged and carries neither key.

### 5.4 What the CLI needs to do

**Required: nothing.** Both surfaces already print `warnings` verbatim:
`commands/reconcile_cmd.py:596` (via `print_warnings`) and
`tui/screens/reconciliations.py:1063` (`_show_warnings`). They now print the corrected sentence,
count included.

**Optional:**

- Read `coverage_gap` when you want the numbers, e.g. to style an empty gap differently from one
  holding rows. **Never parse the sentence.** The fields are the contract, and the prose may be
  reworded.
- **To show the rows in the gap, use the unfiled pane (§3.4), not a date-filtered query.** With
  `sort=date_asc`, the pane lists an account's unfiled rows oldest-first. A completed period can
  never contain an unfiled row, so any old unfiled row sits in a gap and shows up at the top.
  The owner agreed this is enough, so no dedicated "open the gap" view is needed.
- ⚠️ **If you do filter `GET /transactions` by the gap's days, be careful with `date_to`.**
  `date_from` / `date_to` compare exact moments, not calendar days. `date_to=2026-07-23` means
  midnight UTC at the *start* of the 23rd, which is 19:00 on the 22nd in Lima. Every row dated the
  23rd (stored as midnight Lima, 05:00 UTC) is dropped. For an inclusive last day, pass the **next
  day's midnight in the user's zone**, e.g. `date_to=2026-07-24T00:00:00-05:00`. Only a filter
  built this way returns the same rows `unfiled_count` counted, apart from `@Opening`, which the
  filter includes and the count doesn't. Engine `open-bugs.md` → `date-filter-not-calendar-days`,
  not fixed yet.

---

## 6. Declined asks, and one other change

### 6.1 A3 and A4 are declined (engine `open-bugs.md` → D13, D14)

- **A3, a per-row "inside a reconciliation window" flag:** declined. The unfiled pane's `!` hint
  stays client-side. It uses only structured fields from `GET /reconciliations`, and the engine
  still makes the real decision at close time. **But it is right only by luck, and this is the part
  that matters for the CLI.** The engine treats a period as whole calendar days in the user's
  timezone. The client compares the ISO date prefix of `date`. The two agree today only because
  every live row is stored at exactly 00:00 America/Lima (3,895 of 3,895, checked 2026-09-23), and
  Lima has no daylight saving. **Nothing enforces midnight.** If file import (`file-import-plan.md`)
  or anything else starts writing a real time of day, the `!` will be wrong on rows near midnight.
  At that point, ask the engine again: D13 names that as the condition for reopening.
- **A4, `?status=` on `GET /reconciliations`:** declined. `?account_id=` exists, the browse
  screen deliberately fetches everything and slices client-side, and the collection is small.
  Nothing to do.

### 6.2 The erasure procedure now names the CLI's config temp file (`6e93a16`)

`deploy/local/README.md` → "Erasing everything", step 5, now deletes `~/.expense-config*`, not
just `~/.expense-config`. `config.save()` (`expense/config.py:73`) writes a `NamedTemporaryFile`
beside the real file and then `os.replace()`s it, so a crash mid-write leaves a file holding the same
live token. **Nothing to fix.** If you ever change where or how `config.save()` writes its temp
file, tell the engine side so that step still catches it.

---

## 7. Checklist

- [ ] **Unfiled pane:** `sort=date_asc` + `/count`; delete `unfiled_offset` *(silently wrong today)*
- [ ] **LOG bar peek:** total from `/count`, delete the `len(items)` fallback *(silently wrong today)*
- [ ] `fetch_all_cursor_pages`; move `bank_import_cmd.fetch_ledger` and `_fetch_all_txns` to it *(importer down today)*
- [ ] Ledger screen: cursor stack, `/count` for the total, resize and empty-page handling
- [ ] `fetch_transactions`: drop `offset`, add `sort` / `after`; `transactions list` flags
- [ ] Tests assert that `sort=date_asc` really comes back oldest-first (a misspelled param name is not caught, §2.4)
- [ ] Run the §4 checks against the real ledger
- [ ] *(optional)* Read `coverage_gap` where the count or dates are useful; never parse the sentence
- [ ] *(optional)* Any `date_to` built from `last_uncovered_day` uses the next day's midnight in the user's zone
- [ ] Delete this file; tell the engine side to delete `open-bugs.md` → `transaction-cursor`
