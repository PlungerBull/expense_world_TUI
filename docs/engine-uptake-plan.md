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

**Two more engine changes on 2026-09-26** (engine `1f50722`, `73a0bdc`; engine `open-bugs.md`
→ *calendar-day-date-filters*, *strict-request-datetimes*):
- **`GET /transactions` and `/count`:** a bare `YYYY-MM-DD` in `date_from` / `date_to` is the
  whole calendar day in `display_timezone`, both ends inclusive. A datetime with an offset is
  that instant. A datetime **without** an offset, and a reversed range, are `422`. Phase 9 sends
  bare dates unconverted.
- **Every request datetime needs an offset:** reconciliation `date_start` / `date_end` refuse a
  bare date, a naive datetime or a number; a number is `422` everywhere. **No code change:**
  checked 2026-09-26, every write (transactions, opening balances, reconciliation create/edit,
  both importers, the LOG bar) goes through `to_canonical_aware` or `now_local_iso`, and nothing
  sends a number. Phase 12's contract run confirms it.
- **Reconciliation periods are days** (engine `5922bbf`, `sql/041`; engine `open-bugs.md` →
  *reconciliation-period-days*), shipped on this repo's ask. `date_start` / `date_end` are sent
  and returned as bare `YYYY-MM-DD`; any datetime there is `422`. **Phase 10c.**
- **A period always has both days** (engine `8f22ebb`, `sql/042`), the follow-up ask from
  Phase 10c's planning, shipped the same day. `date_start` / `date_end` are required on create
  and `null` for either is `422` on update. `complete` lost its "Required to complete"
  refusal, and the list sorts `date_start ASC, created_at ASC`. The live ledger had no
  reconciliations, so nothing was backfilled. Also **Phase 10c**.

**`:8000` already runs all of it** (checked 2026-09-26: `/transactions/import` is served, the
restore routes are gone). The engine coder restarted it with `5922bbf`, ahead of Phase 12, so
**the current CLI fails against the real ledger on several screens until this uptake lands**.
Accepted: the product is not in daily use. `:8002` was down on the same check. Phase 12 step 2
shrinks to bringing `:8002` up on the same code.

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

**Coming back after a write (owner, 2026-09-26):** after the edit form or `d`, the `u` list reads
fresh from the 10 oldest with the cursor on row 1, like any app's list. The same rule holds on
the ledger (Phase 7). It replaced a builder's call that re-read as many rows as were loaded.

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
| 7 | The ledger becomes one growing list | cursor §3.3 | M3 (**done**, `9942d4d`) |
| 8 | Activity and Rates: TUI screens deleted, flat commands windowed | 6b §2–3 | M1, M5 (**done**, `7ce6405`) |
| 9 | The flat `expense transactions list` | cursor §3.1 | M5 (**done**, `28572ce`) |
| 10 | Offset code deleted | 6b §4 | — (**done**, `79abe7d`) |
| 10b | Bank import through the engine's `POST /transactions/import` | engine-spec | — (**done**) |
| 10c | Reconciliation periods are days | engine-spec *Date inputs* | — (**done**, `da1b8ce`, `954a4eb`) |
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
| 10c | nothing | |
| 11 | 3–10, 10b, 10c | Documents what they built |
| 12 | 11, plus the owner | Push, restart, contract run |

**Shared files.** Phases that edit the same file should not run at the same time, or the
second coder rebases: [reconciliations.py](../expense/tui/screens/reconciliations.py) (5, 6),
[transactions_cmd.py](../expense/commands/transactions_cmd.py) (3, 9),
[bank_import_cmd.py](../expense/commands/bank_import_cmd.py) (6, 10b),
[_base.py](../expense/tui/screens/_base.py) `PagedListMixin` (7, 8),
[_resource.py](../expense/commands/_resource.py) (3, 4, 10),
[reconciliations.py](../expense/tui/screens/reconciliations.py) and
[reconcile_cmd.py](../expense/commands/reconcile_cmd.py) (5, 6, 10c).

## How to build a phase

For whoever picks up one phase. Read this section, the table above, and **your phase only**.
Your phase names the debrief sections that carry the engine facts.

- **The decisions are made.** Everything the owner sees was picked on 2026-09-25 (the table
  above). Build what your phase says. Do not re-open a pick. If something your phase needs is
  not written down, **stop and ask the owner**, and add the answer to your phase.
- **Commit on `main`, do not push.** Nothing is pushed until Phase 12 step 1, so `main` never
  carries a red CI run. Commit through `PATH="$PWD/.venv/bin:$PATH" git commit` (pre-commit runs
  mypy from the venv). Never `--no-verify`.
- **The unit suite is green.** Phase 9 fixed the last known failures (the 6 in
  `test_cmd_transactions.py`) on 2026-09-26. Your phase must leave it green.
- **Test fakes refuse `offset`.** Any fake for a transaction read uses `cursor_page()` from
  [tests/unit/helpers.py](../tests/unit/helpers.py) and asserts `"offset" not in kw`. Phase 2's
  `_patch_unfiled` in [test_tui_reconciliations.py](../tests/unit/test_tui_reconciliations.py)
  is the model.
- **Done means:** `pytest tests/unit` (green), `ruff check . && ruff format .`,
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
reload after an edit or a delete starts over from the 10 oldest (see "Coming back after a
write" above).

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

## Phase 7: the ledger becomes one growing list (M3) (done 2026-09-26, `9942d4d`)

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
- After a write, see the owner's answers below (this line used to say a bulk edit "removes the
  changed rows locally, as today", which was wrong: the ledger has always re-read after a write).
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

**Owner answers (2026-09-26):**
- **Any write starts the list over**: `+`, `⏎` edit, `c`/`b`/`h` on the ledger, `d` on the `u`
  list. The list reads fresh from its first 10, recounted, with the cursor on row 1 ("this
  should work like normal apps"). This replaced an earlier answer the same day that kept the
  loaded depth and the cursor's row number, which was built and then removed.
- **A refused bulk row further down drops out of the selection** (pick A of
  [expense-world-refused-row-after-reload.html](mockups/expense-world-refused-row-after-reload.html)):
  it stays selected only if the fresh read brings it back among the newest 10. Option B, keeping
  it selected off screen, was rejected: the legend would count a row you cannot see, and the next
  bulk key would change it.
- **Legend:** one line, `filter: category @Pendiente · 20 of 57 loaded · 3 selected`.
- `r` starts again from the newest 10, as `r` does on the `u` list (M6).
- **One copy** of the growing logic for both lists, built now rather than filed as a todo
  (answering the review of `9942d4d`).

**What was built:** `PagedListMixin` is deleted. Both growing lists read through `GrowingRead`
in [_growing.py](../expense/tui/screens/_growing.py): `read_first` (the first 10 and the count
together; a failed count raises), `grow` (`pgdn`, no recount), and `reset` (before any fresh
read). A reader, not a screen mixin, because the `u` list is one panel inside the
Reconciliations screen. **Review fix (`f396f49`, then carried into `GrowingRead`):** `reset`
drops the cursor, so a `pgdn` on the old list while the fresh read runs reads nothing, and a
`pgdn` read already in flight is dropped on arrival by a generation number. Otherwise, on a
filtered ledger whose fresh read ends one row further along, the first appended row repeated.
The ledger's resize only re-slices the window. `CursorList` lost its fetched-page mode
(`page_meta`, `PageRequested`); `WindowedList` gained `row_count`. The test fake is `fake_ledger` in
[helpers.py](../tests/unit/helpers.py). No in-screen filter change exists (Home pushes a new
ledger per filter), so "a filter change empties the list" has nothing to test.

## Phase 8: Activity and Rates (6b §2–3, owner decision) (done 2026-09-26, `7ce6405`, fixed in the follow-up)

- **TUI:** delete `ActivityScreen` and `RatesScreen` from
  [system.py](../expense/tui/screens/system.py), their Home entries (**M1**), and their tests.
- **`activity list`:** drop `--offset`; add `--from` / `--to` and `--after`, all **sent as
  typed**. Since engine `aaee6bf` (2026-09-26, asked after the reversal below) a bare day is
  the whole day in `display_timezone`, ending 23:59:59.999999, and the echoed window is in
  that zone, so the line under the table cuts it to the minute with no zone math. `--resource-id` help says the 30-day window still applies (owner
  decision in 6b §2.1).
- **`rates list`:** `--date X` sends `date_from=X&date_to=X`; drop `--offset`; add `--from` /
  `--to` (plain ISO dates here, no conversion). The "omit for full history" help text is no
  longer true: omitting both gives the last 30 days.
- **M5, the line under both tables** (dates from the window the engine echoes):
  - more rows in this window: `(2026-08-24 → 2026-09-23 · more in this window: pass --after <cursor>)`
  - the window's last page, activity: `(<from> → <to> · older: pass --to <date_from>)`, with
    both bounds and `--to` printed exactly as the engine echoed them (instants)
  - the window's last page, rates: `(2026-08-24 → 2026-09-23 · newest first · older: pass --to 2026-08-23)`,
    i.e. `--to` = the echoed `date_from` **minus one day**, because rate dates are inclusive
    (6b §3)
  - The line is printed even when the table is empty, so an empty window never reads as "no history".
- Both mocks move to the windowed envelope.
- **The line goes into the shared `render_pagination_hint`** in
  [_resource.py](../expense/commands/_resource.py), which both commands already call. Phase 9 gave
  it a cursor branch for `transactions list` (`(more: pass --after <c> with the same filters and
  --sort)`) that fires only on a body with **no** echoed `date_from` / `date_to`, so the windowed
  envelope falls past it today and prints nothing. Add the window branch there; a test in
  [test_resource.py](../tests/unit/test_resource.py) pins that a windowed body never gets the
  transactions line.

**Owner answer (2026-09-26), asked while planning this phase:**
- The header's `!` (today has no rate of its own) **stays as it is**, with no screen behind it.
  Only the comment in [header.py](../expense/tui/widgets/header.py) that sends you to "`Rates` on
  the home menu" changes.

**Reversed after review, 2026-09-26 (owner):** the calendar-day helper and the local-time
window line were built in `7ce6405` and **taken out** in the follow-up commit. Review found
three bugs: the day was placed in the profile's zone but the window was shown in the machine's;
`tzlocal` was called from `_resource.py` instead of `dates.py`; and the zone fallback read
`user.timezone`, which `GET /auth/me` does not send. All three came from `/activity` refusing
bare days, so the owner chose to **ask the engine** instead ([todo.md](todo.md) "Activity
takes calendar days"). **It landed the same day** (engine `aaee6bf`, follow-up `e879afc`): the CLI sends bare days
as typed and converts nothing. **`:8000` was restarted on it the same day** and the live
check passed: a bare day, its echoed Lima window, and page 2 by cursor.

**Builder's calls (M5; the owner does not use the typed commands):**
- The activity "older" hint prints the echoed `date_from` **exactly as the engine sent it** (an
  instant), not a bare date, which the engine would read as the whole day, repeating rows.
- `rates list --date` together with `--from` / `--to` is refused as a flag clash.
- An empty window prints `(no activity in this window)` / `(no rates in this window)`, and the
  window line under it.
- Activity action code 4 keeps its `RESTORED` label for old history rows.
- tui.md's "one client per page" worked example moves off `ActivityScreen` to a screen that
  still exists.

## Phase 9: the flat `expense transactions list` (done 2026-09-26, `28572ce`)

- Remove `--offset`; add `--sort` (passed through unchecked, so the engine's `422` is the one
  error) and `--after`.
- **M5, the line under the table**, only when `next_cursor` is not null:
  `(more: pass --after <cursor> with the same filters)`. No total, so no extra `/count` call.
  Nothing on the last page.
- **`--from` / `--to` pass through unconverted** (engine 2026-09-26: a bare date is the whole
  day). No client date math. The help text changes from "ISO 8601 bound (inclusive)" to
  "a day (YYYY-MM-DD, whole day, inclusive) or a time with an offset". With the restart this
  closes the `--to` defect in [todo.md](todo.md) "Small defects".
- **The reconcile checklist** is Phase 10c's, not this phase's.
- Tests: `--sort` and `--after` reach the request, `--offset` is gone, the hint appears only
  with a cursor, a `422` on `sort` renders through the standard envelope, and `--to 2026-08-31`
  reaches the request as exactly `date_to=2026-08-31`.

**Owner answers (2026-09-26), asked while planning this phase:**
- The hint names the sort too: `(more: pass --after <cursor> with the same filters and --sort)`,
  because the engine refuses a cursor under a different sort as well as different filters.
- `--sort` is sent as typed; its help lists the two values
  (`date_desc (default, newest first) or date_asc (oldest first).`).
- The hint is a cursor branch of the shared `render_pagination_hint`, not a local helper;
  Phase 10 deletes only its offset branch.
- cli-spec's flag list for the command is updated in this phase, not left to Phase 11.

**What was built:** `list_` drops `--offset` and gains `--sort` / `--after`, passed to the
unchanged `fetch_transactions`. `render_pagination_hint` prints the cursor line when
`next_cursor` is a string **and the body echoes no date window**, so activity and rates pages
(Phase 8) never get it (owner-approved fix, 2026-09-26). The 6 known failures are fixed, and the suite is green.

## Phase 10: offset code deleted (6b §4) (done 2026-09-26, `79abe7d`)

Delete `fetch_all_pages`, `OFFSET_OPT` and every `--offset`, and the offset branch of
`render_pagination_hint`. **Check:** `grep -rn offset expense/` finds nothing that talks to the
engine.

**What was built:** the three deletions, plus `render_pagination_hint` lost its now-unused
`always` and `items` parameters (it prints the window line, the cursor line, or nothing). The
tests' `page()` helper, the offset envelope, is gone; fixtures use `whole()` or `cursor_page()`.
`scripts/check_fixture_drift.py` no longer excuses `total` / `offset` / `has_more`, so a
fixture still carrying them reads as drift. New guard:
`test_command_surface.py::test_no_command_takes_offset`. Nothing the owner sees changed.

## Phase 10b: bank import through the engine (added 2026-09-26, done 2026-09-26)

**Why.** On 2026-09-25 the engine shipped `POST /transactions/import` (engine-spec, and engine
`open-bugs.md` → *bank-import*). It matches a bank download against the ledger, writes what is
missing in one database transaction, writes operation codes onto matched rows that lack one,
reports rows inside a closed period without writing them, and reports the groups where the
ledger holds more than the file. `expense import bank` still did all of that itself
(`bank_import/match.py`, `fetch_ledger`, a `PUT` per code, a `POST /transactions/batch`).
Two copies of the matching rule would drift, and every future client would need a third. **The owner's order (2026-09-26): the complete switch, no stopgap,
inside this uptake.**

**This phase absorbs todo.md's old item 2** ([file-import-plan.md](file-import-plan.md) §4–§7):
- **C2 (the title is the bank's text, whitespace collapsed; no description)** is built here,
  because the title is what this phase sends. The engine refuses a `description` on an import
  row anyway.
- **C3 (delete the amount-only rule)** is done by deleting the matcher: the engine runs only
  operation code, same day + title, adjacent day + title.
- **C4 (the floor)** is built here, client-side as the engine asks: rows dated before
  **2026-01-01** are never sent. **No `--since`** (owner, 2026-09-26, while reviewing this
  phase): the one-time floor fenced off the hand-typed rows the bank files overlap, and a
  typed-each-run flag was one forgotten run from duplicates. The overlap is removed at the
  source instead, by a one-time title alignment after the official migration
  ([file-import-plan.md](file-import-plan.md) §6, with the measurements that drove it).
- **C5 (closed periods shown, not hidden)** becomes rendering the engine's `sealed` outcome. The
  client-side reconciliation read and pre-filter are **not** built.
- C1 (the TUI import door) stays in file-import-plan.md, and is built on this phase's code.

**The flow** (one engine call per run):
1. Parse the file as today ([bank_import/parse.py](../expense/bank_import/parse.py)); the account
   pick, the leg per currency and the "currency with no leg" refusal are unchanged.
2. Drop the rows dated before 2026-01-01.
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

**Deleted:** `bank_import/match.py` whole; in
[bank_import_cmd.py](../expense/commands/bank_import_cmd.py) `fetch_ledger`, `_local_date`,
`payload_for`, the backfill `PUT` loop, the `post_transaction_batch` call and the parts of
`WriteReport` / `Placement` / `json_doc` that carried them; `clean_title` and `MERCHANT_WIDTH`
(C2); the matcher tests in [test_bank_import.py](../tests/unit/test_bank_import.py) (the parser
tests stay). [batch_write.py](../expense/batch_write.py) stays: the sheet importer and the LOG
bar still use it. The `bank_files` memory is untouched (C1 deletes it).

**Correction (2026-09-26):** an earlier draft said the bank rows written on 2026-09-12 carry
the old cleaned titles. None were written: the ledger ends on 2026-09-11 and holds no operation
codes, so 2026-09-12 was dry runs only.

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

**What was built:** [bank_import/engine.py](../expense/bank_import/engine.py) holds the floor
(`IMPORT_FLOOR`), the 500 cap, the request body, the response → `Placed` join by id, the
`excess` groups (signed from `transaction_type`), the `match` words and the `rows.<i>.<field>`
→ file-line map. The parser's `title` is the bank's text collapsed; `raw_title`, `clean_title`
and `MERCHANT_WIDTH` are gone. The command reads, makes the one call, and prints; a failed
period-name read still prints the import, under "a closed period", with one line saying why.
A file with no row from 2026 on sends nothing and exits 1. The account pick and `bank_files`
are unchanged.

## Phase 10c: reconciliation periods are days (added 2026-09-26, done 2026-09-26, `da1b8ce`, `954a4eb`)

**Why.** Engine `5922bbf` (this repo's ask, owner's pick 2026-09-26): a period's `date_start` /
`date_end` are plain calendar days on the wire and in storage. Every period rule was already in
days; only the value was a moment. The app still sends a midnight instant, which is now a `422`,
and the tick-list's last-day defect ([todo.md](todo.md) Small defects 1) closes here.

- **Saving a period, flat:** `reconcile create` / `update` send `--date-start` / `--date-end`
  **as typed**, no `to_canonical_aware`. A bad value is the engine's `422` on that field,
  rendered through the envelope. Help text: "the statement's first/last day, YYYY-MM-DD".
- **Saving a period, TUI form:** a bad date is still caught **at the field**, as today
  (owner 2026-09-26: "at the field, right away"). The check is the exact shape the engine
  accepts, `YYYY-MM-DD` zero-padded and a real day: a regex plus `date.fromisoformat`
  (3.11's `fromisoformat` alone also takes `20260831`, which the engine refuses). The hint
  stays "use YYYY-MM-DD". The payload is the typed text, unconverted. Not the LOG bar's
  forgiving dates: rejected by the owner the same day.
- **The tick-list** passes the returned `date_start` / `date_end` straight into `date_from` /
  `date_to`, as it already does; with bare days that is now the whole last day.
- **Display:** delete the `[:10]` slicing in `format_period`
  ([reconcile_cmd.py](../expense/commands/reconcile_cmd.py)) and in `blocking_windows`
  ([reconciliations.py](../expense/tui/screens/reconciliations.py), the `u` pane's `!` windows);
  the value is already a day.
- **Tests:** every unit fixture of a reconciliation carries bare days (today several carry
  `…T00:00:00Z`); create/update send exactly the typed day; the TUI form refuses `2026-8-31`,
  `20260831` and `31/08/2026` at the field and sends `2026-08-31` unchanged; the tick-list's
  `available` read sends `date_to` equal to the period's `date_end`, byte for byte.
  [test_reconciliations_lifecycle.py](../tests/contract/test_reconciliations_lifecycle.py)
  sends bare days (it sends `2026-04-01T00:00:00Z` today), and gains the engine's own check: a
  row logged at 23:30 on the last day is in the tick-list read.
- **Closes:** todo.md Small defects 1 (at the Phase 12 check), and the "periods are days"
  engine ask.

**What was built:** the day check is `is_calendar_day` in [dates.py](../expense/dates.py), the
one copy of the engine's day shape. Neither file imports `to_canonical_aware` any more. The
tick-list needed no code change, only its first test (`date_from` / `date_to` equal to the
period's days).

**Owner answer (2026-09-26), asked while planning this phase:** the TUI form's DATE END was
optional ("empty enter to skip") while the typed `create` has required it since 2026-09-20.
The owner saw no use for an undated period, and ruled that it is **the engine's to refuse**. The
form now requires DATE END, like DATE START.

**Follow-up, same day:** the engine shipped that ask (`8f22ebb`). Deleted here: the
missing-date hint on `reconcile complete` (and `_complete_hint`'s now-unused id), the
half-dated branches of `format_period`, the undated guard in `blocking_windows`, and the
`reconcile create` docstring that explained a client-side rule. Every unit fixture of a
reconciliation now carries both days. A contract test pins the rule (a missing `date_end` on
create, and `null` on update, are both `422`).

## Phase 11: docs and checks

- [cli-spec.md](cli-spec.md): every flag change in Phases 3–5, 8 and 9, and the deleted commands.
  The "Pagination (human mode)" paragraph is **already rewritten** (Phase 4); only check that its
  *Pending* line is gone.
- [cli-runtime.md](cli-runtime.md): a short "three list shapes" section pointing at engine-spec.
- [cli-spec.md](cli-spec.md) `expense import bank`: rewritten for Phase 10b (the engine matches;
  titles verbatim; the 2026-01-01 floor; the 500-row refusal; `--json` is the engine body).
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
    moved into the engine (Phase 10b), rule 4 is gone, titles are the bank's text, one floor
    (2026-01-01) plus a one-time title alignment. Rejected: keeping the client matcher beside
    the engine's; splitting a file over 500 rows; the `--since` floor (typed, or saved once).
- [file-import-plan.md](file-import-plan.md): move in the **midnight caveat** (cursor §6.1). The
  `u` pane's `!` hint is right only because every row is stored at 00:00 Lima; the first import
  that writes a real time of day is the point to ask the engine again (engine `open-bugs.md` D13).
  Without this move, deleting the debrief loses the warning.
- `pytest tests/unit`, `ruff check . && ruff format .`, `mypy`. Update the test count in
  CLAUDE.md and [todo.md](todo.md).

## Phase 12: the cutover

1. Push to `main`, CI green.
2. **`:8000` already runs the new engine code** (restarted by the engine coder 2026-09-26).
   **The owner brings up `:8002`** on the same code (engine side).
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
   - the bank import, as listed in Phase 10b;
   - `transactions list --to <day>` includes a row logged late on that day; a naive datetime is
     a `422` rendered through the envelope; reconciliation create/edit round-trips its dates
     as bare days, and a missing or `null` day is a `422` (Phase 10c; both already written in
     `test_reconciliations_lifecycle.py`).
6. Delete this file, the three debriefs and [sealed-periods-plan.md](sealed-periods-plan.md).
   In the same commit, remove what links to them, or `test_relative_doc_links_resolve` fails:
   the uptake and sealed-periods rows in [todo.md](todo.md) "Now", the plan link in CLAUDE.md's
   open-work paragraph, and the 6a debrief link in
   [category-hashtags-plan.md](category-hashtags-plan.md) §1 (point it at engine-spec instead).
   Tell the engine side to delete `open-bugs.md` → `transaction-cursor`, `phase-6-lists`,
   `bank-import`, `calendar-day-date-filters`, `strict-request-datetimes` and
   `reconciliation-period-days`.
