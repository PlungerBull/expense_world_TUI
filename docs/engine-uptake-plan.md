# Engine uptake: everything the engine changed on 2026-09-23, phase by phase

**For:** whoever builds the CLI side of the engine's 2026-09-23 changes. **Written:**
2026-09-23. **Replaces** `cursor-uptake-plan.md`, which covered only the first of the day's
three debriefs.

**What it covers:** the order of the work and what "done" means for each step. **The facts live
in the three engine debriefs**, and this plan cites their sections and does not repeat them:

| Short name | File | What it covers |
|---|---|---|
| **cursor** | [engine-debrief-2026-09-23.md](engine-debrief-2026-09-23.md) | `GET /transactions` by cursor, `?sort=`, `/transactions/count`, the gap fields |
| **6a** | [engine-debrief-2026-09-23-phase6.md](engine-debrief-2026-09-23-phase6.md) | Restore gone, create caps, small lists whole, reconciliations per account |
| **6b** | [engine-debrief-2026-09-23-phase6-part2.md](engine-debrief-2026-09-23-phase6-part2.md) | Activity and rates by cursor inside a date window; offset gone everywhere |

**When done:** delete this file and the three debriefs (Phase 12). The reasons worth keeping move
to [decisions.md](decisions.md) in Phase 11.

---

## Where things stand (2026-09-23)

- **The engine repo has all of it; the running engines do not.** `:8000` (the real ledger) and
  `:8002` (the disposable test engine) still run the old code. **The CLI in this repo works only
  against the old engine, and the new CLI will work only against the new one.** So both engines
  are restarted in Phase 12, straight after the merge, and not before.
- **After the restart, every list is one of three shapes** (6b §0). No endpoint pages by offset.

  | Shape | Lists |
  |---|---|
  | **Whole** `{items}` | accounts, categories, hashtags, a category's hashtags, reconciliations of one account |
  | **Cursor** `{items, limit, next_cursor}` | transactions |
  | **Cursor + date window** | activity, exchange-rate history |

- **Also since the debriefs:** engine `724c3fc` refuses any query parameter an endpoint does not
  declare with a `422`, on every route. Every stale `limit`, `offset` or `include_deleted` fails
  loudly. None of the breakage returns wrong data with a `200` **except the two panes in
  Phase 2**, which never send a stale parameter.
- **The product is not in daily use**, so no phase keeps the TUI usable in between. Commit each
  phase on `main` locally, and **push once, at Phase 12 step 1**, so `main` never carries a red
  CI run.

## Owner decisions already made (2026-09-23)

- **Activity and Rates leave the TUI.** They are not fully fledged features; the flat
  `expense activity list` and `expense rates list` stay. So 6b's "older window" key on the two
  screens is **not built**, and the ledger is left as the only paged screen in the TUI.
- **A pane whose count cannot be read fails as a whole.** It never shows rows next to a missing
  or guessed number.
- **Rows and count load together**, in one worker, and the pane shows nothing until both are in.
- **The `reconcile complete` hint degrades to the generic one** now that the by-id read is gone
  (6a §4.3).

## Open decisions, all in one mockup

Everything the owner will see changing goes in **one mockup file**, [mockups/expense-world-engine-uptake.html](mockups/expense-world-engine-uptake.html) (drawn 2026-09-23),
reviewed and picked **before any phase that touches a screen or a table** (CLAUDE.md "Mock every
screen before building it"). It covers:

| # | What | Phase |
|---|---|---|
| **M1** | Home without Activity and Rates | 8 |
| **M2** | Reconciliations browse: fetch the account's batches when the cursor moves, or every account's up front (about 9 reads) (6a §4.2) | 5 |
| **M3** | Ledger screen after a terminal resize: keep your place, or go back to page 1 | 7 |
| **M4** | The `u` pane and the LOG bar peek: unchanged look, oldest first, the count-failure state | 2 |
| **M5** | Flat output: the `transactions list` cursor hint; the small lists losing their "showing 20 of 56" hint; `activity list` / `rates list` printing their window and "older: `--to …`"; `reconcile list` requiring `--account-id` | 4, 5, 8, 9 |
| **M6** *(optional)* | Real scrolling in the `u` pane, now that the reason for the 40-row cap is gone (cursor §3.4) | later |

Phases 1, 3, 6 and 10 change nothing the owner sees and can be built before the pick.

---

## The phases at a glance

| Phase | What | Debrief | Mockup |
|---|---|---|---|
| 1 | Shared pieces for the transaction cursor | cursor §3.1–3.2 | — (**done**) |
| 2 | The two panes that would show wrong numbers without an error | cursor §3.4–3.5 | M4 |
| 3 | Deleted is deleted: restore commands and `include_deleted` removed | 6a §1 | — |
| 4 | Small lists come back whole | 6a §3 | M5 |
| 5 | Reconciliations: one account at a time, no by-id read | 6a §4 | M2, M5 |
| 6 | The two whole-list readers of transactions move to the cursor | cursor §3.2 | — |
| 7 | The ledger screen pages by cursor | cursor §3.3 | M3 |
| 8 | Activity and Rates: TUI screens deleted, flat commands windowed | 6b §2–3 | M1, M5 |
| 9 | The flat `expense transactions list` | cursor §3.1 | M5 |
| 10 | Offset code deleted | 6b §4 | — |
| 11 | Docs and checks | — | — |
| 12 | Cutover: restart, verify, contract suite, delete the debriefs | all §4/§5 | — |

**Order.** The mockup comes first, because it gates Phases 2, 4, 5, 7, 8 and 9. Phases 3 and 6
are built while the owner reviews it. After the pick, Phase 2 comes first among the screen
phases because it is the one silent failure. Phases 3–9 are
independent of each other except that **4 and 5 must land before 10** (they remove the last
unpaged callers of `fetch_all_pages`), and **6 must land before 10** too.

---

## Phase 1: shared pieces (done 2026-09-23, `d666f78`)

- `fetch_transactions` has no `offset` and gains `sort` and `after`.
- `count_transactions` returns an int and raises when the body has no int `count`.
- Both build their filters through one `_filter_params`, and the count sends **nothing but** the
  filters. A test compares the two signatures so the filter lists cannot drift apart.
  `include_deleted` is already out of both (6a §1).
- `fetch_all_cursor_pages` stops only on a null `next_cursor`; `cursor_page()` is the test
  builder.
- The fixture-drift script needs **no** new keys: `next_cursor`, `count` and `coverage_gap` are
  declared engine schema properties. It cannot catch a transaction fixture still carrying
  `total`/`offset`, because those keys are real elsewhere. `cursor_page()` and the Phase 12
  contract test cover that.
- **What does not fail but is broken:** the ledger, `u` pane and peek tests replace
  `fetch_transactions` with fakes that still accept `offset`, so they stay green against broken
  screens. Phases 2 and 7 **replace** those fakes rather than adjusting them.

## Phase 2: the two panes that show wrong numbers without an error

**The unfiled pane (`u`)**, [reconciliations.py](../expense/tui/screens/reconciliations.py)
`_load_unfiled`: one list read (`sort="date_asc"`, `unreconciled=True`, `account_id`,
`limit=UNFILED_PAGE`) plus one `count_transactions` with the same three filters, in the same
worker. Stop reversing the rows. Delete `unfiled_offset()` and the "no sort parameter" comment.
Keep 40 rows plus `r` (M6 decides whether that changes).

**The LOG bar peek**, [log_bar.py](../expense/tui/screens/log_bar.py): `_load_peek` fetches the
page and `count_transactions(account=…)` together; `_peek_loaded` takes the total from the count;
the `len(items)` fallback is deleted, and a failed count goes to `_peek_failed`.

**Tests:** the request carries `sort=date_asc`, **and** a mock returning rows oldest-first
renders them oldest at the top. "N to file" is the count figure (1716 against a 40-row page). A
failed count shows as a failed pane or peek, not as a number.

## Phase 3: deleted is deleted (6a §1)

- Delete the five `restore` commands (accounts, categories, hashtags, transactions, reconcile)
  and their tests.
- Delete `INCLUDE_DELETED_OPT` and every `include_deleted` parameter and `--include-deleted`
  flag (26 references). The `Deleted` column that `--include-deleted` switched on goes with it.
- Reword the `print_warnings` docstring (only `complete` produces warnings now) and the
  "archive/restore" comment in [_resource.py](../expense/commands/_resource.py).
- [test_command_surface.py](../tests/unit/test_command_surface.py): the command count drops by
  five.

No screen changes: the TUI never called restore or sent `include_deleted`.

## Phase 4: small lists come back whole (6a §3)

- `fetch_accounts` / `fetch_categories` / `fetch_hashtags` and their `list` commands: drop
  `limit`, `offset`, `--limit`, `--offset`, and the pagination hint (**M5**).
- One GET each instead of `fetch_all_pages`: the TUI categories and hashtags screens, the picker
  loaders, `_load_name_map`, and the sheet importer's reference fetch
  ([import_/apply.py](../expense/import_/apply.py)).
- The 20-row window on the categories and hashtags screens keeps paging client-side over the
  full set. Nothing visible changes there.
- Fixes a live bug in passing: 56 hashtags against a default page of 50 lost 6 tags anywhere a
  caller forgot to page.

## Phase 5: reconciliations, one account at a time (6a §4)

- `fetch_reconciliations` requires `account_id` and loses `include_deleted`, `limit`, `offset`.
- **Browse screen:** per-account fetch, shape decided by **M2**. The list arrives in period
  order, so check whether `_batch_sort_key` is still needed.
- **`reconcile list` requires `--account-id`** (**M5**).
- **Delete `reconcile get` and `fetch_reconciliation`.** A batch's rows are
  `transactions list --reconciliation-id <id>`.
- **Working-screen refresh:** re-read the account's list and find the row by id. "Not there"
  now reliably means deleted, because the list is whole.
- **`reconcile complete`'s hint:** delete the dead by-id read and always print the bare hint
  (owner decision, 6a §4.3).
- **The `u` pane's `!` hint** needs the per-account reconciliations read, the same as the browse
  screen.

## Phase 6: the two whole-list readers of transactions

The bank importer's `fetch_ledger` ([bank_import_cmd.py](../expense/commands/bank_import_cmd.py))
and the checklist's `_fetch_all_txns` move from `fetch_all_pages(lambda limit, offset: …)` to
`fetch_all_cursor_pages(lambda limit, after: …)`. No sort, no count.

**Tests:** a mock serving two cursor pages; both pages' rows are matched or listed.

## Phase 7: the ledger screen pages by cursor

With Activity and Rates gone (Phase 8), **the ledger is the only user of `PagedListMixin`**, so
the mixin is **converted in place** to cursor paging. There is no second mixin.

- It holds the stack of cursors used to reach each page (page 1 = `None`), the current page's
  `next_cursor`, and the count.
- `pgdn` pushes and fetches with `after=next_cursor`, and does nothing when it is null. `pgup`
  pops and refetches.
- The count is fetched when the screen opens, when the filter changes (which also clears the
  stack), and after a `c`/`b`/`h` bulk edit. **Not** on page turns.
- `page_meta` is `(depth × page_rows, count)`. An empty page after deletes steps back one cursor;
  `fetch_page_body`'s "past the end" snapping is deleted.
- **Resize:** decided by **M3**.

**Tests:** replace the fakes in [test_tui_paging.py](../tests/unit/test_tui_paging.py) and
[test_tui_transactions.py](../tests/unit/test_tui_transactions.py) with cursor fakes that
**refuse** `offset`. `pgdn` sends the previous `next_cursor`; `pgup` returns to the right cursor;
`pgdn` is a no-op on the last page; a filter change clears the stack and recounts; a bulk edit
recounts; an empty page steps back.

## Phase 8: Activity and Rates (6b §2–3, owner decision)

- **TUI:** delete `ActivityScreen` and `RatesScreen` from
  [system.py](../expense/tui/screens/system.py), their Home entries (**M1**), and their tests.
- **`activity list`:** drop `--offset`; add `--from` / `--to` (a bare date becomes midnight in
  `display_timezone` with an offset, because the engine refuses naive instants) and `--after`.
  Print the echoed window and "older: `--to <date_from>`" (**M5**). `--resource-id` help says
  the 30-day window still applies (owner decision in 6b §2.1).
- **`rates list`:** `--date X` sends `date_from=X&date_to=X`; drop `--offset`; optionally
  `--from` / `--to`. The "omit for full history" help text is no longer true.
- Both mocks move to the windowed envelope.

## Phase 9: the flat `expense transactions list`

- Remove `--offset`; add `--sort` (passed through unchecked, so the engine's `422` is the one
  error) and `--after`.
- The cursor hint, only when `next_cursor` is not null, with no extra `/count` call (**M5**).
- **`--from` / `--to` become calendar days**, the same conversion as `activity list`. This fixes
  the `--to` defect in [todo.md](todo.md) "Small defects" on the flat side, and gets ahead of
  6b §5 (the engine will soon refuse bare dates here).
- Tests: `--sort` and `--after` reach the request, `--offset` is gone, the hint appears only
  with a cursor, and a `422` on `sort` renders through the standard envelope.

## Phase 10: offset code deleted (6b §4)

Delete `fetch_all_pages`, `OFFSET_OPT` and every `--offset`, and the offset branch of
`render_pagination_hint`. **Check:** `grep -rn offset expense/` finds nothing that talks to the
engine.

## Phase 11: docs and checks

- [cli-spec.md](cli-spec.md): every flag change in Phases 3–5, 8 and 9, and the deleted commands.
- [cli-runtime.md](cli-runtime.md): a short "three list shapes" section pointing at engine-spec.
- [tui.md](tui.md): the cursor `PagedListMixin`; Activity and Rates gone.
- [decisions.md](decisions.md), new entries:
  - "The transaction list pages by cursor": the shrinking work queue, and the
    probe-then-offset-then-reverse read rejected.
  - "Activity and Rates leave the TUI".
  - "Deleted is deleted": restore is an operator task now.
- [file-import-plan.md](file-import-plan.md): move in the **midnight caveat** (cursor §6.1). The
  `u` pane's `!` hint is right only because every row is stored at 00:00 Lima; the first import
  that writes a real time of day is the point to ask the engine again (engine `open-bugs.md` D13).
  Without this move, deleting the debrief loses the warning.
- `pytest tests/unit`, `ruff check . && ruff format .`, `mypy`. Update the test count in
  CLAUDE.md and [todo.md](todo.md).

## Phase 12: the cutover

1. Push to `main`, CI green.
2. **The owner restarts `:8000` and `:8002`** on the new engine code (engine side).
3. `python scripts/check_fixture_drift.py` against the new engine.
4. The debriefs' own checks on the real ledger (reads plus importer dry runs): cursor §4, 6a §5.
   The cursor debrief's "file a page, then scroll on" check runs on the ledger (a filtered
   ledger, a bulk re-category, then `pgdn`) unless M6 gave the `u` pane real scrolling.
5. **Contract suite** against `:8002` (`PYTEST_LIVE=1`). This also closes ask 1's pending
   contract run ([sealed-periods-plan.md](sealed-periods-plan.md) §10 step 7). First add contract
   tests for what nothing has checked against a real engine:
   - cursor pages walked to a null cursor with no row repeated; `sort=date_asc` the exact
     reverse of the default; `/count` equal to the rows walked; `offset` a `422`;
   - a small list returns everything with no `total`; `GET /reconciliations` without
     `account_id` is a `422`;
   - an activity window walked to null, then the older window from the echoed `date_from`.
6. Delete this file, the three debriefs and [sealed-periods-plan.md](sealed-periods-plan.md).
   In the same commit, remove what links to them, or `test_relative_doc_links_resolve` fails:
   the uptake and sealed-periods rows in [todo.md](todo.md) "Now", the plan link in CLAUDE.md's
   open-work paragraph, and the 6a debrief link in
   [category-hashtags-plan.md](category-hashtags-plan.md) §1 (point it at engine-spec instead).
   Tell the engine side to delete `open-bugs.md` → `transaction-cursor` and `phase-6-lists`.
