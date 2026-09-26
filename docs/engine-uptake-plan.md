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

**Added 2026-09-26 (owner):** Phase 10b takes up the engine's `POST /transactions/import` of
2026-09-25, so the bank importer stops matching on its own and the uptake closes with no
second copy of an engine rule left in this repo. Its facts are in engine-spec, not a debrief.

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

## Mockup decisions (settled 2026-09-25)

Mockup: [mockups/expense-world-engine-uptake.html](mockups/expense-world-engine-uptake.html)
(round 1 drawn 2026-09-23, round 2 on 2026-09-25; round 1 is in git history). **Every item is
picked**, so no phase is gated any more.

| # | What | Decision | Phase |
|---|---|---|---|
| **M1** | Home without Activity and Rates | **Yes.** SYSTEM keeps Config and Auth & profile | 8 |
| **M2** | Reconciliations browse | **Owner's shape.** The screen opens with **accounts only**, and no lower panel. `⏎` on an account reads *that* account's reconciliations and opens the panel under the list, with the cursor in it. `esc` closes the panel. **`u` works only while an account's panel is open**, never on the plain account list, and is not in the footer there. It swaps the panel for that account's "no batch" list **in the same place** | 5 |
| **M3** | The ledger | **One growing list** (option C): opens with **10** rows, `pgdn` **appends** the next 10, and `↑↓` scroll the whole of it. A resize keeps you where you are. `a` selects every row loaded so far. The footer reads `N of M loaded` | 7 |
| **M4** | Count next to rows (`u` pane, LOG bar peek) | No pick: the look is unchanged, and a failed count fails the pane (2026-09-23) | 2 |
| **M5** | Typed-command output | **The builder's call**: the owner never uses the typed commands. The exact output is written into Phases 4, 5, 8 and 9 | 4, 5, 8, 9 |
| **M6** | The "no batch" (`u`) list | **Owner's shape.** Opens with the **10** oldest, and `pgdn` **appends** the next 10. **The cursor jumps to the first new row.** At the end, `pgdn` does nothing and leaves the footer. `r` starts again from the 10 oldest. Caption: `N of M loaded` | 2 |

**One builder's call, left open by the mockup:** when you come back to the `u` list from the edit
form (or after `d`), it re-reads as many rows as were loaded (capped at the engine's 200), so a
long walk is not thrown back to 10. The cursor goes to the same position, or to the last row if
the list is now shorter.

---

## The phases at a glance

| Phase | What | Debrief | Mockup |
|---|---|---|---|
| 1 | Shared pieces for the transaction cursor | cursor §3.1–3.2 | — (**done**) |
| 2 | The two panes that would show wrong numbers without an error | cursor §3.4–3.5 | M4, M6 (**done**, `be85a8b`) |
| 3 | Deleted is deleted: restore commands and `include_deleted` removed | 6a §1 | — (**done**, `8d2fb7c`) |
| 4 | Small lists come back whole | 6a §3 | M5 (**done**, `c65a125`) |
| 5 | Reconciliations: one account at a time, no by-id read | 6a §4 | M2, M5 (**done**, `192831c`) |
| 6 | The two whole-list readers of transactions move to the cursor | cursor §3.2 | — (**done**, `b5602d7`) |
| 7 | The ledger becomes one growing list | cursor §3.3 | M3 |
| 8 | Activity and Rates: TUI screens deleted, flat commands windowed | 6b §2–3 | M1, M5 |
| 9 | The flat `expense transactions list` | cursor §3.1 | M5 |
| 10 | Offset code deleted | 6b §4 | — |
| 10b | Bank import through the engine's `POST /transactions/import` | engine-spec | — |
| 11 | Docs and checks | — | — |
| 12 | Cutover: restart, verify, contract suite, delete the debriefs | all §4/§5 | — |

**Order and dependencies.** Each phase can go to a different coder. What must land first:

| Phase | Needs first | Why |
|---|---|---|
| 3, 4, 6, 9 | nothing | |
| 5 | 2 (done) | The "no batch" list it rehouses is Phase 2's |
| 7 | 2 (done), **8** | Reuses Phase 2's growing list; converts `PagedListMixin` in place, which Activity and Rates use until Phase 8 deletes them |
| 8 | nothing | |
| 10 | 3, 4, 5, 6, 8, 9 | Deletes `fetch_all_pages` and `OFFSET_OPT`, which those phases stop using |
| 10b | 6 (done) | Deletes `fetch_ledger`, which Phase 6 moved to the cursor |
| 11 | 3–10, 10b | Documents what they built |
| 12 | 11, plus the owner | Push, restart, contract run |

**Shared files.** Phases that edit the same file should not run at the same time, or the
second coder rebases: [reconciliations.py](../expense/tui/screens/reconciliations.py) (5, 6),
[transactions_cmd.py](../expense/commands/transactions_cmd.py) (3, 9),
[bank_import_cmd.py](../expense/commands/bank_import_cmd.py) (6, 10b),
[_base.py](../expense/tui/screens/_base.py) `PagedListMixin` (7, 8),
[_resource.py](../expense/commands/_resource.py) (3, 4, 10).

## How to build a phase

For whoever picks up one phase. Read this section, the table above, and **your phase only**.
Your phase names the debrief sections that carry the engine facts.

- **The decisions are made.** Everything the owner sees was picked on 2026-09-25 (the table
  above). Build what your phase says. Do not re-open a pick. If something your phase needs is
  not written down, **stop and ask the owner**, and add the answer to your phase.
- **Commit on `main`, do not push.** Nothing is pushed until Phase 12 step 1, so `main` never
  carries a red CI run. Commit through `PATH="$PWD/.venv/bin:$PATH" git commit` (pre-commit runs
  mypy from the venv). Never `--no-verify`.
- **The unit suite is red at the start, on purpose.** After Phase 6 there are **6 known
  failures**, all in `test_cmd_transactions.py` (fixed by Phase 9). Your phase must leave no failure outside
  that set, and must fix the ones it owns.
- **Test fakes refuse `offset`.** Any fake for a transaction read uses `cursor_page()` from
  [tests/unit/helpers.py](../tests/unit/helpers.py) and asserts `"offset" not in kw`. Phase 2's
  `_patch_unfiled` in [test_tui_reconciliations.py](../tests/unit/test_tui_reconciliations.py)
  is the model.
- **Done means:** `pytest tests/unit` (known failures only), `ruff check . && ruff format .`,
  `mypy`; every doc paragraph your change makes false is corrected in the same commit (tui.md,
  cli-spec.md); and your phase's row in the table above is marked **done** with the commit hash.

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

## Phase 2: the two panes that show wrong numbers without an error (done 2026-09-25, `be85a8b`)

**The unfiled pane (`u`)**, [reconciliations.py](../expense/tui/screens/reconciliations.py)
`_load_unfiled`: one list read (`sort="date_asc"`, `unreconciled=True`, `account_id`,
`limit=UNFILED_PAGE`) plus one `count_transactions` with the same three filters, in the same
worker. Stop reversing the rows. Delete `unfiled_offset()` and the "no sort parameter" comment.
**M6:** `UNFILED_PAGE` becomes 10. `pgdn` fetches `after=next_cursor` and appends; the cursor lands
on the first new row. The count is read with the first page and on `r`, not on each `pgdn`. The
reload after an edit or a delete follows the builder's call above.

**The LOG bar peek**, [log_bar.py](../expense/tui/screens/log_bar.py): `_load_peek` fetches the
page and `count_transactions(account=…)` together; `_peek_loaded` takes the total from the count;
the `len(items)` fallback is deleted, and a failed count goes to `_peek_failed`.

**Tests:** the request carries `sort=date_asc`, **and** a mock returning rows oldest-first
renders them oldest at the top. The caption's total is the count figure (1716 against a 10-row
page). A failed count shows as a failed pane or peek, not as a number. `pgdn` sends the previous
`next_cursor`, appends (20 rows, the first 10 unchanged), and puts the cursor on row 11. `pgdn`
on a null cursor sends nothing. `r` returns to 10.

## Phase 3: deleted is deleted (done 2026-09-25, `8d2fb7c`)

- Delete the five `restore` commands (accounts, categories, hashtags, transactions, reconcile)
  and their tests.
- Delete `INCLUDE_DELETED_OPT` and every `include_deleted` parameter and `--include-deleted`
  flag (26 references). The `Deleted` column that `--include-deleted` switched on goes with it.
- Reword the `print_warnings` docstring (only `complete` produces warnings now) and the
  "archive/restore" comment in [_resource.py](../expense/commands/_resource.py).
- [test_command_surface.py](../tests/unit/test_command_surface.py): the command count drops by
  five.

The TUI never called restore or sent `include_deleted`. **One text change:** the `d` confirm
on the "no batch" list now reads "It leaves every balance and report, and no screen or command
can bring it back" (owner pick, 2026-09-25). **Also done:** the three contract lifecycles
(resources, reconciliations, transactions) end on the row being gone (absent from the list, 404
on get and on the old restore route) instead of restoring it, and
`test_command_surface.py::test_no_command_restores_or_lists_deleted_rows` keeps both from coming
back. `_list_all` in the resources lifecycle still pages by offset; Phase 4 owns it.

## Phase 4: small lists come back whole (done 2026-09-25, `c65a125`)

- `fetch_accounts` / `fetch_categories` / `fetch_hashtags` and their `list` commands: drop
  `limit`, `offset`, `--limit`, `--offset`, and the pagination hint. **M5:** the table prints
  every row and **no footer line** at all.
- One GET each instead of `fetch_all_pages`: the TUI categories and hashtags screens, the picker
  loaders, `_load_name_map`, and the sheet importer's reference fetch
  ([import_/apply.py](../expense/import_/apply.py)).
- The 20-row window on the categories and hashtags screens keeps paging client-side over the
  full set. Nothing visible changes there.
- Fixes a live bug in passing: 56 hashtags against a default page of 50 lost 6 tags anywhere a
  caller forgot to page.

**Owner answers (2026-09-25), asked while planning this phase:**

- `--limit` / `--offset` are **deleted outright**, with no stub and no friendlier message: a
  stale `--limit` gets Typer's own "No such option". The rule behind it: **delete anything that
  no longer points anywhere.** So `fetch_all_pages` lost its flat-list branch (no caller can
  hand it one now), and the test mocks of these three lists moved to the real `{items}` shape
  (`whole()` in [tests/unit/helpers.py](../tests/unit/helpers.py)); the fakes refuse `limit` /
  `offset` the way the engine does.
- **A guard:** `test_command_surface.py::test_whole_lists_take_no_paging_flags`.
- **Review fix (2026-09-25):** the first commit converted only the HTTP-level mocks. About 20
  TUI fakes that replace `fetch_accounts` / `fetch_categories` / `fetch_hashtags` directly still
  returned bare lists, and passed whatever shape the code expected. They are now `whole([...])`.
  `items_of` lost its bare-list branch, because no engine route returns an array and only those
  fakes used it. A bare list now yields no rows, which also flushed out `/v1/activity` fakes
  serving an array. `test_suite_hygiene.py::test_whole_list_fakes_serve_the_engine_shape` catches
  the case that still slips through: a fake returning `[]`.
- **The contract suite's `_list_all`** (handed over by Phase 3) is one read, and asserts the body
  is exactly `{items}`. It runs for real only at Phase 12.
- **The cli-spec pagination paragraph was rewritten whole now**, as the three list shapes and
  their footers (M5), with a *Pending* line naming the commands whose code has not caught up.
  Phases 5, 8 and 9 each delete their command from that line.

## Phase 5: reconciliations, one account at a time (6a §4) (done 2026-09-26, `192831c`)

- `fetch_reconciliations` requires `account_id` and loses `include_deleted`, `limit`, `offset`.
- **Browse screen (M2, owner's shape; round 2 of the mockup draws it).**
  - Opens with the **account list only**: no lower panel, and no reconciliations read.
    Heading `Reconciliations — pick an account`. Footer: `⏎ Its reconciliations`, `n New`,
    `esc Back`, `? Keys`. **No `u`** here.
  - `⏎` on an account: `GET /reconciliations?account_id=<id>`, then the panel opens under the
    list with the cursor in it. Caption `Reconciliations · <account> · oldest → newest`. The
    account row keeps an accent `▸` so you can see which one is open. An account with none shows
    `none yet · n to create one` inside the panel. A failed read toasts and leaves the panel
    closed.
  - In the panel: `⏎` opens that reconciliation (as today), `n` creates one for this account,
    `u` swaps the panel for this account's "no batch" list **in the same place**, and `esc`
    closes the panel, back to the account list.
  - In the "no batch" list, `esc` returns to the reconciliations panel, not to the plain account
    list. Everything else there is Phase 2's, unchanged.
  - Coming back from an opened reconciliation re-reads that account's list and lands on the same
    row in the open panel. After `n` saves, the panel re-reads and lands on the new one.
  - `blocking_windows` (the `!` flag) takes the open account's list, which the panel already
    holds, so the "no batch" list costs no extra read.
  - The list arrives in period order, so check whether `_batch_sort_key` is still needed.
  - Tests: nothing is read for reconciliations until `⏎`; `u` on the plain list does nothing and
    is not in the footer; `esc` from the panel closes it; `esc` from "no batch" returns to the
    panel; returning from a reconciliation keeps the panel open on the same row.
- **`reconcile list` requires `--account-id`** (**M5**): Typer's own "Missing option
  '--account-id'" when it is left out. Same columns as today, in the engine's period order.
- **Delete `reconcile get` and `fetch_reconciliation`.** A batch's rows are
  `transactions list --reconciliation-id <id>`.
- **Working-screen refresh:** re-read the account's list and find the row by id. "Not there"
  now reliably means deleted, because the list is whole.
- **`reconcile complete`'s hint:** delete the dead by-id read and always print the bare hint
  (owner decision, 6a §4.3).

**Found while planning, not in the debrief (2026-09-25):**

- `activity list` also read `GET /reconciliations/{id}`, to name each reconciliation row.
  After the restart that is a `405`, and the row would quietly show a short id. It is now named
  from the activity row's own snapshot (`after_snapshot`, or `before_snapshot` for a delete),
  with no read.
- The `complete` hint named `--date-from` / `--date-to`, flags `transactions list` never had.
  It now names `--from` / `--to`.

**Owner answers (2026-09-25), asked while planning this phase:**

- The activity gap is fixed **here**. The label is **`<name> / <account>`** (`August 2026 /
  BCP PEN`): either half alone when the other is missing, then the short id.
- `n` on the plain account list uses **the account under the cursor**, with no ACCOUNT step.
  Saved, **that account's panel opens with the cursor on the new one**. The form dismisses
  with the id it minted.
- With no panel open, the account list **fills the screen**. The panel halves it.
- The breadcrumb **grows to `Reconciliations ▸ <account>`** while a panel is open (as drawn).
- The two contract checks (no account is a `422`, a GET by id is a `405`) were **written
  here**, in `test_reconciliations_lifecycle.py`. They first run at Phase 12.

**Owner answer (2026-09-26), after review:** the "no batch" list's footer reads **`⏎ Edit`**,
as the mockup draws it (it said `⏎ Open` until then). The reconciliation list in the same panel
keeps `⏎ Open`.

## Phase 6: the two whole-list readers of transactions (done 2026-09-26, `b5602d7`)

The bank importer's `fetch_ledger` ([bank_import_cmd.py](../expense/commands/bank_import_cmd.py))
and the checklist's `_fetch_all_txns` move from `fetch_all_pages(lambda limit, offset: …)` to
`fetch_all_cursor_pages(lambda limit, after: …)`. No sort, no count.

**Tests:** a mock serving two cursor pages; both pages' rows are matched or listed.

**What was built:** both readers call `fetch_all_cursor_pages`. `fetch_all_pages` has no caller
left and waits for Phase 10. The bank importer's test fake pages the ledger by cursor and refuses
`offset`.

**Owner answer (2026-09-26), asked while planning this phase:** the checklist's last-day rows
(todo.md *Small defects* 1) are **the engine's to fix**, not patched here. The request was
written into the engine repo as `expense_world_engine/docs/ask-calendar-day-date-filters.md`
(a one-off exception the owner granted to "never write in the engine repo"). It asks that a bare
date be **accepted** as a whole calendar day, not refused, because refusing would stop the
reconcile screen loading at all.

**Short-lived by design:** Phase 10b deletes `fetch_ledger` and the local matcher, including
this phase's change to them. Phase 6 keeps the importer working until then.

## Phase 7: the ledger becomes one growing list (M3)

**Needs Phase 8 first**: with Activity and Rates gone, **the ledger is the only user of
`PagedListMixin`**, so the mixin is **converted in place**. There is no second mixin. The owner's
shape replaces pages with one list that grows.

**Reuse Phase 2's growing list; do not build another.** [cursor_list.py](../expense/tui/widgets/cursor_list.py)
already has it: `GROW_STEP` (10), `set_growth(more=…)`, `append_rows(rows, more=…)` (which puts
the cursor on the first new row) and the `MoreRequested` message, posted by `pgdn` and shown in
the footer as `pgdn 10 more`. The `?` card lists that key only on screens that handle
`on_cursor_list_more_requested`. The "no batch" list in
[reconciliations.py](../expense/tui/screens/reconciliations.py) is the working example.

- It opens with **10** rows (`sort` default, newest first) and holds the loaded rows, the last
  `next_cursor`, and the count.
- `pgdn` fetches `after=next_cursor` and **appends** 10 rows; `↑↓` scroll across everything loaded.
  `pgdn` does nothing when the cursor is null. `pgup` has no fetch to do: it scrolls up a
  screenful, as in any list.
- The cursor lands on the first new row, the same as the `u` list (M6).
- The count is fetched when the screen opens, when the filter changes (which also empties the
  list and drops the cursor), and after a `c`/`b`/`h` bulk edit. **Not** on `pgdn`.
- A bulk edit on a filtered ledger removes the changed rows locally, as today. The kept cursor is
  still valid, because the engine's cursor is a bookmark on the last row read, not a row number.
- **Resize:** nothing is fetched. The list keeps its rows and the cursor stays on its row.
- `a` selects every loaded row. The line under the list reads `N of M loaded` (mockup round 2,
  M3 option C), where the old `rows 41–60 of 214 · page 3 of 11` was. `fetch_page_body`'s "past
  the end" snapping and `page_meta` are deleted, and so is `CursorList`'s fetched-page mode
  (`page_meta`, `PageRequested`) once the ledger stops using it.

**Tests:** replace the fakes in [test_tui_paging.py](../tests/unit/test_tui_paging.py) and
[test_tui_transactions.py](../tests/unit/test_tui_transactions.py) with cursor fakes that
**refuse** `offset`. `pgdn` sends the previous `next_cursor` and appends; the cursor lands on the
first new row; `pgdn` on a null cursor sends nothing; a filter change empties the list and
recounts; a bulk edit recounts; a resize sends no request; `a` selects all loaded rows.

## Phase 8: Activity and Rates (6b §2–3, owner decision)

- **TUI:** delete `ActivityScreen` and `RatesScreen` from
  [system.py](../expense/tui/screens/system.py), their Home entries (**M1**), and their tests.
- **`activity list`:** drop `--offset`; add `--from` / `--to` and `--after`. A bare date becomes
  an instant with an offset through the **shared calendar-day helper** (see below), because the
  engine refuses naive instants. `--resource-id` help says the 30-day window still applies
  (owner decision in 6b §2.1).
- **`rates list`:** `--date X` sends `date_from=X&date_to=X`; drop `--offset`; add `--from` /
  `--to` (plain ISO dates here, no conversion). The "omit for full history" help text is no
  longer true: omitting both gives the last 30 days.
- **M5, the line under both tables** (dates from the window the engine echoes):
  - more rows in this window: `(2026-08-24 → 2026-09-23 · more in this window: pass --after <cursor>)`
  - the window's last page, activity: `(2026-08-24 → 2026-09-23 · older: pass --to 2026-08-24)`,
    i.e. `--to` = the echoed `date_from`
  - the window's last page, rates: `(2026-08-24 → 2026-09-23 · newest first · older: pass --to 2026-08-23)`,
    i.e. `--to` = the echoed `date_from` **minus one day**, because rate dates are inclusive
    (6b §3)
  - The line is printed even when the table is empty, so an empty window never reads as "no history".
- **The shared calendar-day helper** is built by whichever of Phases 8 and 9 lands first, in
  [dates.py](../expense/dates.py), and reused by the other. A bare `YYYY-MM-DD` becomes the
  start of that day in the user's `display_timezone` for `--from`, and the start of the **next**
  day for `--to`, so `--to` includes the whole day. A value that already carries a time passes
  through unchanged. This is the conversion the calendar-day engine ask in [todo.md](todo.md)
  would delete.
- Both mocks move to the windowed envelope.

## Phase 9: the flat `expense transactions list`

- Remove `--offset`; add `--sort` (passed through unchecked, so the engine's `422` is the one
  error) and `--after`.
- **M5, the line under the table**, only when `next_cursor` is not null:
  `(more: pass --after <cursor> with the same filters)`. No total, so no extra `/count` call.
  Nothing on the last page.
- **`--from` / `--to` become calendar days** through the shared helper described in Phase 8
  (build it here if Phase 8 has not landed). This fixes
  the `--to` defect in [todo.md](todo.md) "Small defects" on the flat side, and gets ahead of
  6b §5 (the engine will soon refuse bare dates here).
- Tests: `--sort` and `--after` reach the request, `--offset` is gone, the hint appears only
  with a cursor, and a `422` on `sort` renders through the standard envelope.

## Phase 10: offset code deleted (6b §4)

Delete `fetch_all_pages`, `OFFSET_OPT` and every `--offset`, and the offset branch of
`render_pagination_hint`. **Check:** `grep -rn offset expense/` finds nothing that talks to the
engine.

## Phase 10b: bank import through the engine (added 2026-09-26)

**Why.** On 2026-09-25 the engine shipped `POST /transactions/import` (engine-spec, and engine
`open-bugs.md` → *bank-import*). It matches a bank download against the ledger, writes what is
missing in one database transaction, writes operation codes onto matched rows that lack one,
reports rows inside a closed period without writing them, and reports the groups where the
ledger holds more than the file. `expense import bank` still does all of that itself
([bank_import/match.py](../expense/bank_import/match.py), `fetch_ledger`, a `PUT` per code, a
`POST /transactions/batch`). Two copies of the matching rule would drift, and every future
client would need a third. **The owner's order (2026-09-26): the complete switch, no stopgap,
inside this uptake.**

**This phase absorbs todo.md's old item 2** ([file-import-plan.md](file-import-plan.md) §4–§7):
- **C2 (the title is the bank's text, whitespace collapsed; no description)** is built here,
  because the title is what this phase sends. The engine refuses a `description` on an import
  row anyway.
- **C3 (delete the amount-only rule)** is done by deleting the matcher: the engine runs only
  operation code, same day + title, adjacent day + title.
- **C4 (the floors)** is built here. The engine says both stay client-side: rows dated before
  2026-01-01, or before `--since YYYY-MM-DD` (the one-time floor, owner 2026-09-20), are
  never sent.
- **C5 (closed periods shown, not hidden)** becomes rendering the engine's `sealed` outcome. The
  client-side reconciliation read and pre-filter are **not** built.
- C1 (the TUI import door) stays in file-import-plan.md, and is built on this phase's code.

**The flow** (one engine call per run):
1. Parse the file as today ([bank_import/parse.py](../expense/bank_import/parse.py)); the account
   pick, the leg per currency and the "currency with no leg" refusal are unchanged.
2. Drop the rows under either floor.
3. **More than 500 rows left: refuse before sending** (owner 2026-09-26). The line names the
   count and says to export a shorter date range. Never split a file across requests: a row in
   a later request can be claimed by a row an earlier one just created, and silently vanish.
4. Build the rows: a fresh `uuid4` `id`, the leg's `account_id`, `date` as the **calendar day**
   (`YYYY-MM-DD`, no conversion to an instant), signed `amount_cents`, `title`, `operation_code`.
5. `POST /transactions/import` with `dry_run: true` without `--apply`, `false` with it. The apply
   is **one** call, not a dry run followed by a write: its response is what happened. The
   standard idempotency key covers retries.
6. Render the response. A `422` names rows as `rows.<index>.<field>`; map the index back to the
   file's line number so the refusal reads `! row 14: …`, and nothing was written.

**Where the code lives (one copy, for the TUI door to reuse):** request-building and the
response → per-row view model go in [expense/bank_import/](../expense/bank_import/) as pure
functions (e.g. `engine.py`), tested without HTTP. The command only reads, calls and prints.

**Output (M5, the builder's call):**
- The preview table keeps its columns. `match` reads `new`, `in ledger · operation`,
  `in ledger · same day`, `in ledger · ± 1 day` (`adjacent_day`), with ` · +code` when
  `backfill_code` is set, and `closed · <period name>` for `sealed`.
- The period name comes from `GET /reconciliations?account_id=` for the legs that have a
  `sealed` row (the response carries ids only), the same name-join pattern as elsewhere.
- Sealed rows are also their own block under the table (C5: "a visible skipped block"), so a
  bank restating something inside a closed month is noticed.
- The summary line counts `new`, `matched` (by rule), `sealed`, `backfilled`, and the file's
  refused and floor-skipped rows. `excess` renders as today's warning block.
- **`--json` is the engine's response verbatim** (CLAUDE.md: `--json` is the raw engine body).
  Parser refusals, floor skips and the 500-row refusal go to stderr.
- Exit 1 on a `422` or any parser-refused row on `--apply`, as today.

**Deleted:** [bank_import/match.py](../expense/bank_import/match.py) whole; in
[bank_import_cmd.py](../expense/commands/bank_import_cmd.py) `fetch_ledger`, `_local_date`,
`payload_for`, the backfill `PUT` loop, the `post_transaction_batch` call and the parts of
`WriteReport` / `Placement` / `json_doc` that carried them; `clean_title` and `MERCHANT_WIDTH`
(C2); the matcher tests in [test_bank_import.py](../tests/unit/test_bank_import.py) (the parser
tests stay). [batch_write.py](../expense/batch_write.py) stays: the sheet importer and the LOG
bar still use it. The `bank_files` memory is untouched (C1 deletes it).

**Known consequence, not a decision:** the bank rows written on 2026-09-12 carry the old cleaned
titles. A later card file (no operation numbers) overlapping those days would not match them
by title. The `--since` floor at the first real import, set after the last existing row, is
what keeps them apart.

**Tests:**
- Unit, request side: floors applied; the 501st row refused before any call; the leg per
  currency; a bare calendar day in `date`; the title collapsed; no `description`; `dry_run`
  true without `--apply`, false with it; exactly one `POST /transactions/import` per run and no
  `GET /transactions`, `PUT` or `/batch`.
- Unit, response side (respx, the fixture copied from engine-spec's shape): each outcome and
  rule renders; `sealed` names the period; `excess` renders; `--json` is the body byte for byte;
  a `422` on `rows.3.date` reads as the file's line.
- Error-shape test (the command-surface guard already requires one).
- **Contract, run at Phase 12:** a dry run writes nothing; an apply creates a row, and the same
  file again reports it `matched` by `operation_code`; a row inside a completed period comes
  back `sealed`.

**Check:** `grep -rn "match_rows\|fetch_ledger\|transactions/batch" expense/commands/bank_import_cmd.py`
finds nothing.

## Phase 11: docs and checks

- [cli-spec.md](cli-spec.md): every flag change in Phases 3–5, 8 and 9, and the deleted commands.
  The "Pagination (human mode)" paragraph is **already rewritten** (Phase 4); only check that its
  *Pending* line is gone.
- [cli-runtime.md](cli-runtime.md): a short "three list shapes" section pointing at engine-spec.
- [cli-spec.md](cli-spec.md) `expense import bank`: rewritten for Phase 10b (the engine matches;
  titles verbatim; `--since`; the 500-row refusal; `--json` is the engine body).
- [tui.md](tui.md): the growing-list `PagedListMixin` (ledger and `u` list), the new
  Reconciliations browse, Activity and Rates gone, and in §4 (the keymap) that `pgdn` means
  "10 more" in a growing list and "next page" everywhere else.
- [decisions.md](decisions.md), new entries:
  - "The transaction list pages by cursor": the shrinking work queue, and the
    probe-then-offset-then-reverse read rejected.
  - "Activity and Rates leave the TUI".
  - "Deleted is deleted": restore is an operator task now.
  - "Long lists grow, they do not page": the owner's 2026-09-25 shape for the ledger and the
    "no batch" list (10 at a time, `pgdn` appends, the cursor on the first new row, a resize
    keeps your place). Rejected: page swapping with its resize trade-off (M3 options A and B in
    round 1 of the mockup).
  - "Reconciliations opens on the accounts": nothing is read until `⏎`. Rejected: read on
    cursor move, and read every account up front (M2 options A and B).
  - "Bank downloads are matched against the ledger" is **amended**, not replaced: the matching
    moved into the engine (Phase 10b), rule 4 is gone, titles are the bank's text. Rejected:
    keeping the client matcher beside the engine's; splitting a file over 500 rows.
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
   ledger, a bulk re-category, then `pgdn`) and on the `u` list (edit a row, then `pgdn`).
5. **Contract suite** against `:8002` (`PYTEST_LIVE=1`). This also closes ask 1's pending
   contract run ([sealed-periods-plan.md](sealed-periods-plan.md) §10 step 7). First add contract
   tests for what nothing has checked against a real engine:
   - cursor pages walked to a null cursor with no row repeated; `sort=date_asc` the exact
     reverse of the default; `/count` equal to the rows walked; `offset` a `422`;
   - a small list returns everything with no `total` (the reconciliation half, including the
     `422` without `account_id` and the `405` by id, was written in Phase 5);
   - an activity window walked to null, then the older window from the echoed `date_from`;
   - the bank import, as listed in Phase 10b.
6. Delete this file, the three debriefs and [sealed-periods-plan.md](sealed-periods-plan.md).
   In the same commit, remove what links to them, or `test_relative_doc_links_resolve` fails:
   the uptake and sealed-periods rows in [todo.md](todo.md) "Now", the plan link in CLAUDE.md's
   open-work paragraph, and the 6a debrief link in
   [category-hashtags-plan.md](category-hashtags-plan.md) §1 (point it at engine-spec instead).
   Tell the engine side to delete `open-bugs.md` → `transaction-cursor`, `phase-6-lists` and
   `bank-import`.
