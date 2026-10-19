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

### `⏎` on an empty account or category on the Edit form
Asked 2026-10-18 · Blocks: nothing (the form works either way)

On the `⏎` Edit form, pressing `⏎` on the ACCOUNT or CATEGORY line with nothing typed picks the
first name in the list. So stepping through the form with `⏎` can move a transaction to another
account, or change its category, without your meaning to.
- **A.** `⏎` with nothing typed keeps the account or category the transaction has.
- **B.** It picks the first name in the list, as now.

**Recommended:** A, because stepping past a line should never change it.

### `esc` after adding hashtags on a split part
Asked 2026-10-18 · Blocks: nothing (the screen works either way)

On a split part's HASHTAGS line, `⏎` on a name adds that hashtag at once. If you then press `esc`
while still on that line, the hashtags you just added stay.
- **A.** They stay, since each was added with `⏎`.
- **B.** They go, like any typing not yet left.

**Recommended:** A, because `⏎` is how you say "keep this" everywhere else on the screen.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **A non-date in the Edit form's date crashes the app.** On the `⏎` Edit form, and the
  bank-line Edit form that shares its code, `⏎` on a date bar holding a non-date (e.g. `abc`)
  accepts it, and `ctrl+s` raises an uncaught `typer.BadParameter`, so the app exits with a
  traceback ([edit_form.py](../expense/tui/screens/edit_form.py) stores the text unchecked;
  [dates.py](../expense/dates.py) raises; [_form.py](../expense/tui/screens/_form.py)
  `action_submit` does not catch it). The fix checks the date at `⏎`, as the amount field
  does; the message it shows is wording the owner picks first.
- **A comment cites a decisions.md heading in the wrong case.**
  [_base.py](../expense/tui/screens/_base.py) line 419 cites "the ledger fills the window"; the
  heading in [decisions.md](decisions.md) is "The ledger fills the window".
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
- **Two wordings in "no batch".** The owner's picks (2026-10-18): the `?` card's line for `⏎`
  reads "Edit the row: its date, title, operation, amount or account"; and `c`'s question counts
  in written English, "1 ticked row" for one and "5 ticked rows" otherwise
  ([reconciliations.py](../expense/tui/screens/reconciliations.py)). Tests follow.
- **The note after `b` counts what moved.** `b` on one part of a split transaction moves every
  part (the engine's rule), so the note says `2 rows → BCP Oro PEN · 2 left their
  reconciliation`, not the count of rows selected (the owner's pick, 2026-10-18). The count is the
  engine's: if its answer does not say what moved, it becomes an engine ask, never one read per
  part ([transactions.py](../expense/tui/screens/transactions.py)).
- **A bank file cell reading `nan` or `inf` crashes the import.** `parse_amount` turns the
  amount into cents outside its `try`, so `nan` raises `ValueError` and `inf` or `Infinity`
  raise `OverflowError` instead of refusing the row as not an amount
  ([parse.py](../expense/bank_import/parse.py)). Refuse it, with a test.
- **Leftovers in the import door.** The apply still builds `day_mismatches` the screen after
  importing no longer shows; `reason_cell` picks a row's style by comparing the reason's words
  (a kind on `FileLine` would not); `Placed.rule` and `Placed.sealed_by` are read but used only
  by tests; `test_apply_writes_once_and_the_result_says_what_to_check` is named for a screen
  that no longer says what to check; no test draws a row whose amount could not be read; the
  `ImportCounts` docstring says "summary" ([bank_import.py](../expense/tui/screens/bank_import.py),
  [engine.py](../expense/bank_import/engine.py), [flow.py](../expense/bank_import/flow.py)).
- **A unit fixture quotes an old refusal.** `SEALED_LINE_WORDS` in
  [test_tui_reconciliations.py](../tests/unit/test_tui_reconciliations.py) reads "This bank line
  is in a completed reconciliation and cannot be deleted. …"; the engine sends "Cannot delete a
  bank line assigned to a completed reconciliation. Revert the reconciliation to draft first.",
  as [test_tui_delete.py](../tests/unit/test_tui_delete.py) already has. The test passes either
  way, since the app shows the engine's words whole; align the fixture.
- **A row's day shows in UTC.** The engine sends times in UTC, and every list shows the first
  ten characters as the day ([formatting.py](../expense/formatting.py) `format_short_date`), so a
  row timed after 19:00 in Lima shows the next day, though the engine counts it on its own day.
  Rows dated by day alone (00:00 in the user's time zone) show right. Decide between showing the
  day in the user's `display_timezone` and an engine ask for each row's local day.
- **"A transaction is split" is spelled three ways.** `is_split_line` in
  [reconciliations.py](../expense/tui/screens/reconciliations.py) and the inline
  `bank_line_part_count(line) > 1` in transactions.py and edit_form.py; one helper in
  formatting.py. Also one shared title cell for `(untitled)` (checklist.py and the "no batch"
  rows), and the delete question shows `—` for the same untitled line: one fallback everywhere.
- **A guard against "purchase" in the app's words.** The owner's word is "transaction"
  (2026-10-17); add a test in [test_suite_hygiene.py](../tests/unit/test_suite_hygiene.py) that
  fails when a user-visible string in `expense/` says "purchase". Code comments and docstrings
  say "purchase" too (split.py, transactions.py, reconciliations.py, reads.py, bank_import.py,
  quickadd/route.py, app.tcss): make them "split transaction" or "bank line" first, so the guard
  needs no exemption for comments.
- **Mockups that back no open work.** The rule is a mockup lives only while it backs open work;
  most in [mockups/](mockups/) back screens already built, among them
  `expense-world-bank-lines-whole.html` (whose pane 2c still shows a part count the built row
  does not), `expense-world-screen-map.html` (linked from nowhere), and
  `expense-world-bank-import-10b.html`; `expense-world-import-door.html` (screens 3, 4 and 6) and
  `expense-world-bank-lines-upload.html` (screens 1 to 3) still draw the import's old preview,
  and the screen map's split pane still draws the typed line the split screen no longer has;
  `expense-world-split-screen.html` backs the split screen as built.
  Deleting one means removing its links from tui.md and from code and test docstrings in the
  same change.
- **A whole-file live run of the bank-line tests leaves an empty account.** One
  `contract-lines-*` account stays on the practice user after `tests/contract/test_bank_lines.py`
  runs whole, though no test leaves one when run alone; find which pair of tests does it
  ([test_bank_lines.py](../tests/contract/test_bank_lines.py)).
- **A split part holding only the pending hashtag never drops.** A part whose only content is
  `#Pendiente` is not empty, so it stays when its fields close, shows `—` in every cell and is
  sent as an id alone, which the engine refuses ([split.py](../expense/tui/screens/split.py)).
  It should drop like an empty part, with a test.
- **Three more copies of the name filter.** `matching` in
  [picker.py](../expense/tui/widgets/picker.py) is the shared name filter; reconciliations.py
  (around line 817) and modals.py (around line 222) still copy it, and create_forms.py (around
  line 104) has a two-field version. One shared copy, with tests.
- **The reconciliation detail's `r` reads the account's whole list to refresh one record.**
  The engine reads one reconciliation by its id (contract: GET /v1/reconciliations/{reconciliation_id});
  `r` should read it that way and treat a `404` as gone. Its comment and the docstring of
  `test_r_refreshes_record_from_its_account_list_and_never_writes` still say there is no read by
  id ([reconciliations.py](../expense/tui/screens/reconciliations.py) around line 1077,
  [test_tui_reconcile_detail.py](../tests/unit/test_tui_reconcile_detail.py) line 1074). The
  lifecycle contract test's docstring says the state machine follows the read by id; the next
  test is `test_a_period_refuses_any_datetime`
  ([test_reconciliations_lifecycle.py](../tests/contract/test_reconciliations_lifecycle.py)).
- **The live import test names the stopping reconciliation without the app's own read.**
  `test_a_completed_reconciliation_stops_the_move_and_the_rest_imports` calls
  `GET /reconciliations/{id}` directly; it should name it through `reconciliation_names`
  ([flow.py](../expense/bank_import/flow.py)), so the app's path is proven live and not only
  mocked ([test_bank_import.py](../tests/contract/test_bank_import.py)).
- **No test covers a split refused with a 5xx.** `refusal_lines` leaves out
  `Nothing was split.` when the status is 500 or more ([split.py](../expense/tui/screens/split.py));
  add a unit test in [test_tui_split.py](../tests/unit/test_tui_split.py).
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

- **A test docstring tells history.** `test_tui_reconciliations.py` line 183 says "`date_start`
  orders the batch now"; state it in the present tense
  ([test_tui_reconciliations.py](../tests/unit/test_tui_reconciliations.py)).

- **Every thread worker hands back through `call_while_attached`.** A worker whose screen is
  popped or the app closing still runs its callback, which then queries pruned widgets
  ([tui.md](tui.md) "Async / workers"). `SectionScreen._load` and the LOG bar use the guard; about
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
