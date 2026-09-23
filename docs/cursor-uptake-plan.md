# Cursor uptake: the plan, phase by phase

**For:** whoever builds the CLI side of the engine's 2026-09-23 change. **Written:** 2026-09-23.
**What it covers:** the order of the work and what "done" means for each step. **The facts about
the engine change live in [engine-debrief-2026-09-23.md](engine-debrief-2026-09-23.md)**: new
parameters, response shape, the `422`s, the client rules. This plan cites its sections (`§2.5`)
and does not repeat them.
**When done:** delete this file together with the debrief (Phase 7). The reasons worth keeping
move to [decisions.md](decisions.md) in Phase 6.

---

## Where things stand (2026-09-23)

- The engine repo has the new code: `GET /transactions` pages by cursor, takes `?sort=`, and the
  count has moved to `GET /transactions/count`. **The running engine on `:8000` is still the old
  process.** A read-only check the same day found it still returns `total` and `offset`.
- **The new CLI will not work on the old engine either.** The old engine ignores `sort`, so the
  rows come back newest-first with no error, and it has no `/transactions/count`. So the engine
  restart happens in Phase 7, straight after the merge, and not before.
- The product is not in daily use yet, so no phase needs to keep the TUI usable while the work is
  in progress. Work on `main` directly.
- **One engine commit landed after the debrief: `724c3fc`, unknown query parameters are a `422`
  on every endpoint.** Three consequences. `GET /transactions/count` declares only the filters,
  so sending it `debit_as_negative`, `sort`, `limit` or `after` is a `422` (Phase 1 guards this).
  Debrief §2.4's "a misspelled parameter name is silently ignored" is no longer true. And the
  engine ask to reject unknown parameters is done (see "Left out").
- **Call sites.** The debrief's list (§1) was checked against every caller in this repo: 7 calls
  across 6 sites, and none is missing. The sheet importer's `fetch_all_pages` reads only
  accounts, categories and hashtags, so it is unaffected. The contract suite's paging helper
  walks only accounts, categories and hashtags too.

## The phases at a glance

| Phase | What | Why it comes here |
|---|---|---|
| 1 | Shared pieces: fetch, count, fetch-all-by-cursor, test builder, drift keys | Every later phase uses them |
| 2 | The two panes that would show wrong numbers without an error: the `u` pane and the LOG bar peek | Most dangerous: they would look right |
| 3 | The two that would fail with an error: the bank importer and the reconciliation checklist | Small once Phase 1 exists |
| 4 | The ledger screen: stepping through pages by cursor | The biggest change in the TUI |
| 5 | The flat `expense transactions list` | Only changes a flag and a hint line |
| 6 | Docs and checks | Before the cutover, so the merge lands complete |
| 7 | Cutover: restart the engines, verify, run the contract suite, delete the debrief | Only possible once everything above is done |

Phases 2 to 5 depend only on Phase 1, not on each other.

---

## Phase 1: shared pieces (done 2026-09-23)

**Goal:** one copy of each new building block, so no screen builds its own
(CLAUDE.md "One copy of everything shared"). Nothing visible changes in this phase.

**What landed**

- [transactions_cmd.py](../expense/commands/transactions_cmd.py): `fetch_transactions` has no
  `offset` and gains `sort` and `after`. The new `count_transactions` returns an int and raises
  `ValueError` when the body has no int `count`. Both build their filters through one
  `_filter_params`, and the count sends **nothing but** the filters. A test compares the two
  signatures so the filter lists cannot drift.
- [_resource.py](../expense/commands/_resource.py): `fetch_all_cursor_pages`, which stops only on
  a null `next_cursor`. `fetch_all_pages` is unchanged.
- [helpers.py](../tests/unit/helpers.py): `cursor_page()`.
- [check_fixture_drift.py](../scripts/check_fixture_drift.py): **no change.** `next_cursor`,
  `count` and `coverage_gap` are declared schema properties in the engine (`CursorPage`,
  `TransactionCountResponse`, `CoverageGapResponse`), so they are in `openapi.json` already and
  do not belong in `ENVELOPE_KEYS`. What the script cannot catch is the reverse case: a
  transaction fixture still carrying `total`/`offset` passes, because those keys are real on
  other endpoints. `cursor_page()` and the Phase 7 contract test cover that.

**What fails now, by design:** `test_cmd_import_bank.py` (24, Phase 3) and the
`transactions list` tests (8, Phase 5). **What does not fail but is just as broken:** the ledger,
`u` pane and peek tests replace `fetch_transactions` with fakes that still accept `offset`, so
they stay green against broken screens. Phases 2 and 4 must replace those fakes, not only
adjust them.

**Decided with the owner (2026-09-23)** for every pane that shows a count:

- **If the rows load but the count fails, the pane fails as a whole** (the `u` pane goes back
  with its "Failed" note; the peek shows its error line). The pane never shows rows next to a
  missing or guessed number.
- **Rows and count are fetched together, in one worker, and shown only when both are in.** No
  number filling in after the list appears.

**Commit per phase locally; push once at Phase 7 step 1**, so `main` never carries a red CI run.

---

## Phase 2: the two panes that show wrong numbers without an error

**Goal:** after the restart, neither pane can show a wrong number with no error to go with it.
Debrief §1 explains why these come first.

### 2a. The unfiled pane (`u`) in [reconciliations.py](../expense/tui/screens/reconciliations.py)

- `_load_unfiled`:
  - replace the two reads (a `limit=1` read to learn the total, then a read at an offset) with
    one list read: `sort="date_asc"`, `unreconciled=True`, `account_id`, `limit=UNFILED_PAGE`;
  - make one `count_transactions` call with the same three filters for "N to file";
  - stop reversing the rows for display, since they now arrive oldest-first.
- Delete `unfiled_offset()` and the comment above `UNFILED_PAGE` that says "the engine has no sort
  parameter".
- **Keep the page at 40 rows plus `r` to reload.** Nothing visible changes. The reason for the cap
  is gone (debrief §3.4); real scrolling is its own **[UI]** item, see "Left out" below.
- Leave the `!` hint (`blocking_windows`) alone. The engine declined to take it over (debrief
  §6.1), and Phase 6 moves its caveat into the file-import plan.

### 2b. The LOG bar account peek in [log_bar.py](../expense/tui/screens/log_bar.py)

- `_load_peek`: fetch the page as today, plus `count_transactions(account=…)` in the same worker.
- `_peek_loaded`: take the total from the count, and **delete the `len(items)` fallback**. A
  missing count goes to `_peek_failed`, which reports it instead of showing a wrong number.

**Tests** (in `test_tui_reconciliations.py` and `test_tui_log_bar.py`; they hold 19 and 5
`total`/`offset` mentions to rework)

- The request carries `sort=date_asc`. The engine now `422`s a misspelled parameter name
  (`724c3fc`), but test the order anyway, since that is what the owner sees:
- **Test the rendered order:** with a mock that returns rows oldest-first, the pane shows them in
  that order, with the oldest at the top. It must not reverse them.
- "N to file" is the `/count` figure, not the number of rows on the page. Use a count larger than
  the page, for example 1716 against 40 rows.
- The peek shows the count from `/count`. A count read that fails, or comes back without `count`,
  shows as a failed peek, not as a number.

---

## Phase 3: the two that fail with an error

**Goal:** the importer and the checklist read every matching row by cursor.

- [bank_import_cmd.py](../expense/commands/bank_import_cmd.py) `fetch_ledger`, and
  [reconciliations.py](../expense/tui/screens/reconciliations.py) `_fetch_all_txns`: switch both
  from `fetch_all_pages(lambda limit, offset: …)` to
  `fetch_all_cursor_pages(lambda limit, after: …)`.
- Neither needs a sort, and the default is fine. Neither needs a count.

**Tests:** in `test_cmd_import_bank.py` and in the checklist tests, use a mock that serves two
cursor pages and check that both pages' rows are matched or listed. The same test also covers the
case where a single page would have silently truncated the list.

---

## Phase 4: the ledger screen

**Goal:** [transactions.py](../expense/tui/screens/transactions.py) pages by cursor, and nothing
visible changes except that the page count stays correct. The only page keys are `pgdn` and
`pgup` ([cursor_list.py](../expense/tui/widgets/cursor_list.py)), and there is no "jump to last",
so nothing is lost.

**Changes**

- A new `CursorPagedListMixin` in [_base.py](../expense/tui/screens/_base.py), next to
  `PagedListMixin`. Activity and Rates keep `PagedListMixin`; their endpoints still page by
  offset (debrief §3.3). The two mixins share the row measuring (`page_rows`,
  `measure_list_rows`) but not the paging logic.
- What the new mixin holds:
  - the **cursor stack**: the cursors used to reach each page, with page 1 being `None`;
  - the current page's `next_cursor`;
  - the count.
- **`pgdn`:** push the current page's cursor and fetch with `after=next_cursor`. Do nothing when
  `next_cursor` is `null`.
- **`pgup`:** pop and refetch from the cursor below. Rows edited since are read fresh.
- **When to fetch the count** (debrief §2.5 rule 4):
  - when the screen opens;
  - when the filter changes, which is also when the stack is cleared (the existing
    `reset_page()` moment);
  - after a `c`/`b`/`h` bulk edit, because rows leave a filtered list.

  It is **not** fetched on page turns. It feeds `_page_total`, which both `legend_text` and
  `page_meta` read.
- **`page_meta`** for the subtitle: `(depth × page_rows, count)`, where depth is the size of the
  stack. `CursorList` stays unchanged.
- **Empty page after deletes:** step back one cursor. Delete the "past the end" snapping that
  `fetch_page_body` does; it has no equivalent here (debrief §3.3).
- **Terminal resize:** see Decision B below.

**Tests** (`test_tui_transactions.py`)

- `pgdn` sends the previous page's `next_cursor` as `after`.
- `pgup` returns to the right cursor.
- `pgdn` does nothing on the last page.
- A filter change clears the stack and fetches the count again.
- A bulk edit fetches the count again.
- An empty page after deletes steps back.
- No request from this screen ever carries `offset`.

**Decision B, open: what a terminal resize does.**
- **Recommended:** keep your place. Refetch the current page from its own starting cursor with
  the new `limit`, and keep the stack, since the cursors are bookmarks rather than positions. The
  subtitle's "page X of Y" may be slightly off until the next reload.
- **The debrief's option:** clear the stack and go back to page 1. It is simpler and the page
  numbers are always exact, but you lose your place.

---

## Phase 5: the flat `expense transactions list`

**Changes** in [transactions_cmd.py](../expense/commands/transactions_cmd.py) `list_`:

- Remove `--offset`. `OFFSET_OPT` itself stays, because other commands use it.
- Add `--sort` with values `date_desc` or `date_asc`. Pass the value to the engine unchecked, so
  the engine's `422` is the one error (CLAUDE.md "Thin wrapper").
- Add `--after <cursor>`.
- `--json` stays the raw body, `next_cursor` included.
- **The hint line.** Today `render_pagination_hint` reads `total` and `offset`, so it would print
  nothing after the restart. Replace it with a cursor hint for this command only:
  `(showing 50; pass --after <cursor> for more)`. Print it only when `next_cursor` is not `null`,
  and make no extra `/count` call. `rates list` and the other lists keep the offset hint.
- The docstring's `Example:` block: add one `--sort date_asc` example.

**Tests** (`test_cmd_transactions.py`)

- `--sort` and `--after` reach the request.
- `--offset` is no longer an option.
- The hint appears only when there is a cursor.
- **The error-shape test:** a `422` with `fields: {"sort": …}` renders through the standard
  envelope (CLAUDE.md "Testing conventions").

**Check before building:** the hint line is part of the flat table's output. It changes no
column, but it is output the user reads. Confirm the wording above with the owner before it ships
(CLAUDE.md, the rule on proposing `list` changes before shipping them).

---

## Phase 6: docs and checks

- [cli-spec.md](cli-spec.md): `transactions list` flags (`--sort`, `--after`, no `--offset`).
- [cli-runtime.md](cli-runtime.md): a short paging section. The transaction list is the one
  cursor-paged read, and every other list pages by offset. Point to engine-spec for the rules.
- [tui.md](tui.md): `CursorPagedListMixin` beside `PagedListMixin`, and which screens use which.
- [decisions.md](decisions.md), a new entry, "The transaction list pages by cursor":
  - the reason is the shrinking work queue: with offset paging, filing 40 rows made "next page"
    skip 40 rows the owner never saw;
  - the rejected alternative is the probe-then-offset-then-reverse read, and why it was wrong;
  - point to the engine's plan.
- [file-import-plan.md](file-import-plan.md): move in the **midnight caveat** from debrief §6.1.
  - The `u` pane's `!` hint is right only because every row is stored at 00:00 Lima.
  - The first import that writes a real time of day is the point to ask the engine again
    (engine `open-bugs.md` D13).

  Without this move, deleting the debrief in Phase 7 loses the warning.
- [todo.md](todo.md): the "Engine asks" section points to this plan while the work is open. When
  the plan is deleted, it says the change is done, in one line.
- Run `pytest tests/unit`, `ruff check . && ruff format .`, and `mypy`. Update the test count in
  CLAUDE.md and todo.md.

---

## Phase 7: the cutover

In this order:

1. Commit and push to `main`, with CI green.
2. **The owner restarts the live engine (`:8000`) and the disposable test engine (`:8002`)** on
   the new engine code. This is on the engine side, so this repo does not do it.
3. Run `python scripts/check_fixture_drift.py` against the new engine. It cannot run earlier,
   because until the restart the running engine serves the old `openapi.json`.
4. **Debrief §4 checks on the real ledger** (reads, plus an importer dry run):
   - the `u` pane's header count equals `GET /transactions/count?account_id=…&unreconciled=true`,
     and its rows start from the oldest date;
   - an importer dry run over a statement already imported flags every row as a duplicate;
   - the ledger read oldest-first, page by page, gives exactly the same ids as one full read.
     The 744 groups of rows sharing a date and creation time test the tie-breaking.

   The debrief's "file a page, then scroll on" check needs real scrolling in the `u` pane, which
   is deferred. Run it on the ledger instead: a filtered ledger, a bulk re-category, then `pgdn`.
5. **Contract suite** against `:8002` (`PYTEST_LIVE=1`). This run also closes ask 1's pending
   contract run ([sealed-periods-plan.md](sealed-periods-plan.md) §10 step 7). First add one
   contract test for what nothing has tested against a real engine:
   - cursor pages over a small fixture set, walked to a `null` cursor with no row repeated;
   - `sort=date_asc` is the exact reverse of the default order;
   - `/count` equals the number of rows walked;
   - `offset` gives a `422`.
6. Delete this file and the debrief. Tell the engine side to delete `open-bugs.md` →
   `transaction-cursor`.

---

## Left out, on purpose

- **Real scrolling in the `u` pane.** With cursors the 40-row cap has no reason to exist, but
  removing it changes what the owner sees. It goes to [todo.md](todo.md) as a **[UI]** item with
  its own mockup.
- **Using `coverage_gap` on `complete`.** Both surfaces already print the corrected warning as it
  comes. Reading the fields is optional (debrief §5.4) and has no screen that needs it yet.
