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

### Ask the engine coders for one catch-up file from `7ff6a09d863d6e44`
Asked 2026-10-17 · Blocks: the next catch-up (backlog "Catch up with the engine after `7ff6a09d863d6e44`")

The current spec catches up to `7ff6a09d863d6e44`; the practice engine serves
`786d68f3b071dbf4`. Ask the engine coders for one hand-off file covering every change from
`7ff6a09d863d6e44` to their current version ([from-engine/README.md](from-engine/README.md)); it
becomes the next catch-up spec.

**Recommended:** none — only you can hand it over.

### The help card's line for `⏎` in "no batch"
Asked 2026-10-17 · Blocks: nothing (only words)

The `?` card in "no batch" says `⏎` "Edit the row: its date or its account", but the Edit form
there also changes the title, the operation number and, on a row never split, the amount.
- **A.** "Edit the row: its date, title, operation, amount or account".
- **B.** "Edit the row's bank columns".
- **C.** Keep it.

**Recommended:** A, because it names what the form changes.

### "1 ticked rows"
Asked 2026-10-17 · Blocks: nothing (only words)

With one row ticked, `c` asks "Locks amount/account/title/date on the 1 ticked rows."
- **A.** "1 ticked row" when there is one, "5 ticked rows" otherwise.
- **B.** Keep the words exactly as given.

**Recommended:** A, because it reads as written English either way.

### The note after `b` moves one part of a split purchase
Asked 2026-10-17 · Blocks: nothing (the move works; only its note)

`b` on one part of a split purchase moves every part to the new account (the engine's rule), but
the note at the bottom counts the rows you selected: `1 row → BCP Oro PEN · 1 left its
reconciliation`, while both parts moved and both left it.
- **A.** Keep it: the note counts the rows you selected.
- **B.** Count what moved: `2 rows → BCP Oro PEN · 2 left their reconciliation`.
- **C.** Add a phrase: `1 row → BCP Oro PEN · the whole purchase moved`.

**Recommended:** B, because the note then says what happened in the ledger; it costs one engine
read per selected part, so the engine may be asked to say what moved in its answer instead.

### The split screen's three moments
Asked 2026-10-17 · Blocks: nothing; each pick that changes the screen becomes a task

[mockups/expense-world-split-moments.html](mockups/expense-world-split-moments.html): a title
typed on a part's line (1), `esc` with parts typed (2), and the `@`/`#` suggestion list on a
part's line (3), each as built and its alternative. The rest of the split screen stays as built.

**Recommended:** 1 A (refused: a part has no title of its own), 2 A (leave at once: nothing is
sent before `^s`), 3 A (the LOG bar's suggestion list).

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
- **Catch up with the engine after `7ff6a09d863d6e44`** (owner, 2026-10-17: after the current
  spec). Waits for the engine's hand-off file ("Waiting on you" above), which becomes its spec.
  Known so far from the contract's change log: `1efa6f4627ff9acf` moves a line matched by
  operation code on another day to the bank's day, with `redated`, `redate_blocked_by` and
  `counts.redated` on the import; `786d68f3b071dbf4` is wording only (among it the
  `OPERATION_CODE_EXISTS` message now speaks of bank lines).
- **A row's day shows in UTC.** The engine sends times in UTC, and every list shows the first
  ten characters as the day ([formatting.py](../expense/formatting.py) `format_short_date`), so a
  row timed after 19:00 in Lima shows the next day, though the engine counts it on its own day.
  Rows dated by day alone (00:00 in the user's time zone) show right. Decide between showing the
  day in the user's `display_timezone` and an engine ask for each row's local day.
- **"A purchase is split" is spelled three ways.** `is_split_purchase` in
  [reconciliations.py](../expense/tui/screens/reconciliations.py) and the inline
  `bank_line_part_count(line) > 1` in transactions.py and edit_form.py; one helper in
  formatting.py. Also one shared title cell for `(untitled)` (checklist.py and the "no batch"
  rows), and the delete question shows `—` for the same untitled line: one fallback everywhere.
- **A guard against "purchase" in the app's words.** The owner's word is "transaction"
  (2026-10-17); add a test in [test_suite_hygiene.py](../tests/unit/test_suite_hygiene.py) that
  fails when a user-visible string in `expense/` says "purchase".
- **A whole-file live run of the bank-line tests leaves an empty account.** One
  `contract-lines-*` account stays on the practice user after `tests/contract/test_bank_lines.py`
  runs whole, though no test leaves one when run alone; find which pair of tests does it
  ([test_bank_lines.py](../tests/contract/test_bank_lines.py)).
- **The split screen keeps copies of shared code.** `part_index` in
  [split.py](../expense/tui/screens/split.py) repeats `row_index` of
  [bank_import/engine.py](../expense/bank_import/engine.py) with another prefix; `hanging` is
  imported from the bank-import screen instead of a shared widget home; `real_tags` wraps
  `hashtags_to_send` instead of extending it; `refusal_lines` slices `format_error` by the length
  of `engine_words`; `_int_or_none` is one more copy of the "int and not bool" check of
  formatting.py, cells.py, edit_form.py and reads.py; and `_as_part` in
  [test_tui_split.py](../tests/unit/test_tui_split.py) repeats `import_part` of
  [helpers.py](../tests/unit/helpers.py). One shared copy each, with tests.
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
  Spec (draft, deferred): [specs/official-migration.md](specs/official-migration.md). Whether the plan's one-time title
  alignment ([file-import-plan.md](file-import-plan.md) §6) stays is decided when the owner plans
  the import (owner, 2026-10-17).
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
