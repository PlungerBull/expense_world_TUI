# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

Only the orchestrator edits this file; workers put tasks and questions in their reports. Closed
items get deleted, not ticked ([decisions.md](decisions.md) "The open-work list holds only open
work"). Cite items by title. **[UI]** means an HTML mockup in [mockups/](mockups/) must be
picked before any code. Engine asks live in [to-engine/](to-engine/), one file each.

---

## Waiting on you

Everything that needs the owner: questions, and things only the owner can do. The orchestrator
adds an entry instead of guessing, acts on the answer, then deletes the entry. After a round of
answers it tells the owner what each answer unlocked, and drafts a spec in [specs/](specs/) for
work that is now unblocked. A question reads:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

### The engine moved to `1efa6f4627ff9acf`: fold it into the current spec?
Asked 2026-10-17 · Blocks: [specs/bank-lines-whole.md](specs/bank-lines-whole.md) (the loop is stopped)

This client last caught up to `890453f80a08cec9`; the current spec catches up to
`7ff6a09d863d6e44`. The practice engine now serves `1efa6f4627ff9acf`. The version check prints:

```
the engine's contract version has changed: saved 7ff6a09d863d6e44, engine 1efa6f4627ff9acf.
what the contract changed since 7ff6a09d863d6e44, newest first:
  1efa6f4627ff9acf  2026-10-17
    changed: `POST /transactions/import` → a row matched by `operation_code` on another day than its line now moves the line to the bank's day: every live part whose `date` differs takes 00:00 of the row's day in `display_timezone`, as a created row is dated. A line whose parts are on different days counts as differing. A `same_day` match never moves. The move is not made when the line is in a completed reconciliation, or when the row's day falls inside a sealed period of the line's account; the row is still `matched`, its title and code are still written, and the rest of the import is applied. Nothing about a stopped move is an error.
    added: `POST /transactions/import` → each row's `redated` (`true` when its line is moved to the bank's day, `false` on any other `matched` row, `null` otherwise) and `redate_blocked_by` (the id of the completed reconciliation that stopped the move: the line's own, else the one sealing the row's day; `null` otherwise), on the dry run and the apply alike; `counts.redated`, the number of lines moved.
    changed: `POST /transactions/import` → `day_mismatches` counts a moved line on the bank's day, not its old one, on the dry run and the apply alike, so a line moved to its bank day no longer makes two days disagree.
    changed: `POST /transactions/import` → a part the apply moves and retitles gets one `updated` activity entry carrying both changes.
    changed: wording only, *Sealed periods* and `PUT /transactions/{id}` → *Field locking* say the import never moves a line into a sealed period or out of a completed reconciliation.
```

In plain words: when a bank row matches one of your rows by its bank code but your row is dated
another day, the upload now moves your row to the bank's day (not inside a completed
reconciliation or a sealed month), and says which rows it moved.
- **A.** Fold it into the current spec: ask the engine coders for one hand-off file from
  `7ff6a09d863d6e44` to `1efa6f4627ff9acf`, record `1efa6f4627ff9acf` now so the loop runs, and
  add a task for the upload (with a mockup of how the preview shows a moved row).
- **B.** Finish the current spec on `7ff6a09d863d6e44` first and make `1efa6f4627ff9acf` its own
  catch-up spec; the loop runs with the version check red until then.
- **C.** Stop the loop until the engine coders' hand-off arrives.

**Recommended:** A, because the practice engine cannot go back to `7ff6a09d863d6e44`, the
change is small and touches only the upload, and the live tests of the upload would otherwise
fail against an engine this spec does not describe.

### "ok" on the purchase-whole screens
Asked 2026-10-17 · Blocks: tasks 2 and 3 of [specs/bank-lines-whole.md](specs/bank-lines-whole.md)

[mockups/expense-world-bank-lines-whole.html](mockups/expense-world-bank-lines-whole.html): the
columns are picked (date · title · operation number · amount, the title alone). Left: "ok" or what
to change on 2b–2d (ticking, the completed month, the "no batch" list) and 3a–3e (`d` deleting a
whole purchase), and the new words: the column name `Operation`, the date first on the month's
list, and `Purchase deleted.`

**Recommended:** none — these are your screens.

### The split screen's undrawn moments
Asked 2026-10-17 · Blocks: nothing; each answer that changes the screen becomes a backlog item

The split screen is built as drawn. Three moments the mockup does not draw:
1. A title typed on a part's line (`-40 @hogar lejía`) is refused in place: "a part keeps the
   purchase's title". **A.** keep the refusal · **B.** take the words as the part's note.
2. `esc` with parts typed leaves at once (nothing is written before `^s`). **A.** leave at once
   · **B.** ask "discard?" first, as the LOG bar does.
3. The part line has no `@`/`#` suggestion list; a name that matches nothing is refused.
   **A.** add the LOG bar's suggestion list · **B.** leave it out.

The rest is kept as built unless you say otherwise: the refusal reads `! <reason>`, the preview
says `no category`/`no amount`, a refused field other than the amount shows the engine's key
(`part 1 (category_id)`), the empty screen reads `0 parts · 0.00 of -100.00 · -100.00 left`, and
a successful split closes the screen and reloads the ledger with no message.

**Recommended:** 1 A, because a part has no title of its own and nothing typed is lost; 2 A,
because nothing is lost on the engine; 3 A, because the LOG bar has it and you will expect it.

### Is the one-time title alignment still needed?
Asked 2026-10-16 · Blocks: [specs/official-migration.md](specs/official-migration.md)

Before the migration, the plan has a one-time pass that renames your typed rows to the bank's
wording ([file-import-plan.md](file-import-plan.md) §6), so that the engine would recognise each
row by its title. Titles play no part in recognising a row: the engine recognises it by its bank
code, or by account, exact day and amount, and writes the bank's wording onto the row itself
when it recognises it. Rows typed a day off are the only ones it misses, and those show in
the days whose totals disagree.
- **A.** Drop the alignment pass; the month-by-month statement uploads do its job.
- **B.** Keep it as a one-time tidy-up of wording before the first upload.

**Recommended:** A, because the engine now does the renaming on every match, and a day-off row
is already caught by the days that disagree.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Catch up with purchases read, reconciled and deleted whole.** Spec (approved,
  the loop runs on it): [specs/bank-lines-whole.md](specs/bank-lines-whole.md).
- **Two unit tests fail at random in CI.** Each fails now and then on one Python version and
  passes on the others, because it reads the screen before the screen has finished drawing:
  `test_config_screen_shows_only_the_engine_connection`
  ([test_tui_system.py](../tests/unit/test_tui_system.py)) finds the `#card` text empty
  (`assert 'engine url' in ''`; CI runs 38196778409 on 2026-10-12, 38691759623 and 38810299743
  on 2026-10-15, 38853551793 on 2026-10-16), and
  `test_state8_a_partial_failure_ticks_what_landed`
  ([test_tui_log_bar.py](../tests/unit/test_tui_log_bar.py)) raises
  `NoMatches("No nodes match '#field' on LogBarScreen()")` (runs 38595998705 on 2026-10-14,
  38860403478 on 2026-10-16). Make each wait for what it reads, and check whether the shared
  helpers in [helpers.py](../tests/unit/helpers.py) (`wait_for_loaded`, `run_app`) should do
  that waiting for every test.
- **The split screen keeps copies of shared code.** `part_index` in
  [split.py](../expense/tui/screens/split.py) repeats `row_index` of
  [bank_import/engine.py](../expense/bank_import/engine.py) with another prefix; `hanging` is
  imported from the bank-import screen instead of a shared widget home; `real_tags` wraps
  `hashtags_to_send` instead of extending it; `refusal_lines` slices `format_error` by the length
  of `engine_words`; the head counts the listed parts instead of reading the engine's
  `part_count`, which `fetch_bank_line`'s docstring says the app never does; and
  `count_transactions(bank_line=...)` has no caller. One shared copy each, with tests.
- **The contract tests keep copies of `_safe` and `_refused`.** About 15 files in
  [tests/contract/](../tests/contract/) each define their own; one copy belongs in
  [conftest.py](../tests/contract/conftest.py) beside `client`, `reason_on` and `statuses`.
- **The guard allows a practice-engine start from a subfolder of the engine checkout.** It checks
  the interpreter word `.venv/bin/python`, not that the command runs from the checkout's root
  ([guard.py](../.claude/hooks/guard.py)); either check the folder or list it under the
  docstring's limits, with a test.

- **The guard allows a practice-engine start with only one of the two database URLs.** The engine
  coders' rule is that `SUPABASE_DB_URL` and `ADMIN_DB_URL` are both set on the start command,
  every time; the guard accepts either one alone and leans on the engine refusing to start
  ([guard.py](../.claude/hooks/guard.py)). Require both, with a test.

- **The app reads its settings file on every engine call.** `load_usable` at launch, then about
  25 `ensure_loaded()` calls ([reads.py](../expense/reads.py), [app.py](../expense/tui/app.py),
  the screens), so the app cannot take its settings as a pipe and an agent cannot point it at
  the practice engine without the key reaching a file. Load the settings once at launch and hand
  them to every screen; then the pipe form in [runtime.md](runtime.md) works for the app.

- **A test docstring tells history.** `test_tui_reconciliations.py` line 157 says "`date_start`
  orders the batch now"; state it in the present tense
  ([test_tui_reconciliations.py](../tests/unit/test_tui_reconciliations.py)).

- **Every thread worker hands back through `call_while_attached`.** A worker whose screen is
  popped or the app closing still runs its callback, which then queries pruned widgets
  ([tui.md](tui.md) "Async/workers"). `SectionScreen._load` and the LOG bar use the guard; about
  20 hand-backs still call `self.app.call_from_thread` directly: `_base.py` (`_execute_write`),
  `_growing.py`, `reconciliations.py`, `home.py`, `bank_import.py`, `transactions.py`,
  `edit_form.py`, `create_forms.py`, `setup.py`, `app.py`. Move them, checking first whether a
  write's `on_success` must still run after a dismiss, and add a guard in
  `test_suite_hygiene.py` that refuses a raw `call_from_thread` in `expense/tui/screens/`.
- **An amount typed with a dot for thousands is misread.** `parse_amount` drops every comma, so
  `13.853,20` is saved as 13.85 on every amount field. The owner chose (2026-10-15): every amount
  field refuses an amount whose comma comes after its dot, with the field's usual "can't read
  that" note ([quickadd/money.py](../expense/quickadd/money.py)).
- **The colour line on an edit screen starts on the colour the row already has.** Every other
  line starts on its current value; the colour line starts on the first swatch (a category) or
  on nothing (an account), so `enter` there turns a category blue and shows an account's colour
  as gone ([create_forms.py](../expense/tui/screens/create_forms.py)). Owner's pick
  (2026-10-15): it starts on the current colour, so `enter` keeps it.
- **The bulk `c` pick lists categories in the engine's order.** `_picker_options` moves
  `@Pendiente` to the end ([transactions.py](../expense/tui/screens/transactions.py)); the
  owner's pick (2026-10-15) is the order the engine sends, unchanged.
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, 2026 month by month).
  Spec (draft, deferred): [specs/official-migration.md](specs/official-migration.md).
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.
- **`PickerModal` carries rows but is still a modal.** A surface carrying rows should be a
  pushed screen (the bulk `c`/`b`/`h` picks). The other modals (`HelpModal`, `PromptModal`,
  `DiscardStagedModal`, `ConfirmModal`) are short questions and stay modals. **[UI]** — the
  replacement needs drawing.

---

## Parked

No commitment. Declined ideas stay listed so they are not proposed again.

- **A read-only board over every repo's loop**, at the `productivity_world` level, showing what
  each loop is doing and what waits on the owner. Worth it once more than two repos run a loop.
- **The quick-add launcher hotkey.** A global chord that opens the LOG bar from outside the TUI
  ([mockups/quick-add-launcher-options.html](mockups/quick-add-launcher-options.html), which
  also records the ⌘E conflict). Convenience, not access: `+` opens the LOG bar inside the app.
- **The quick-add "recents" row** (numbered last-N templates). **Declined 2026-08-25**; listed
  only so it is not re-proposed.
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer dashboards.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **An MCP server for agents.** The way for an agent to read or write the ledger on the owner's
  behalf, talking to the engine as every client does. It belongs beside the engine, not in this
  repo, and is a piece of work of its own.
