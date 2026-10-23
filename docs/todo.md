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

### The LOG bar's note for a signed amount it can't read
Asked 2026-10-23 · Blocks: nothing (the line is refused either way)

On the LOG bar, `tottus -13.853,20 $BCP PEN` is refused, as you chose, but the note reads "the
line has no amount — a number needs a sign to be one", though `-13.853,20` has its sign.
- **A.** Keep the note as it is.
- **B.** For a signed number it can't read, the note says so: "can't read -13.853,20 as an
  amount".

**Recommended:** B, because the note should name what is wrong with what you typed.

### A comma used for decimals, with no dot
Asked 2026-10-23 · Blocks: nothing (today's reading stays until you pick)

Every amount field drops every comma as a thousands mark, so `1,5` is saved as 15.00 and
`-13,85` as -1,385.00, with no warning: a comma typed as the decimal mark makes the amount 10 or
100 times too big. `1,000` must keep reading as one thousand.
- **A.** Refuse an amount where a comma is followed by anything but exactly three digits:
  `1,5` and `-13,85` are refused with the field's usual note; `1,000` and `13,853.20` read as
  today.
- **B.** Keep today's reading.

**Recommended:** A, because a wrong amount saved silently is worse than one refused.

### The `?` card's `⏎` line on a split transaction in "no batch"
Asked 2026-10-23 · Blocks: nothing (the line reads as you picked)

In Reconciliations ▸ "no batch", the `?` card now says for `⏎`: "Edit the row: its date, title,
operation, amount or account", on every row. On a split transaction the amount can't be changed
there: its form shows the parts' amounts read-only.
- **A.** Keep one line for every row, as picked.
- **B.** A split transaction gets its own line: "Edit the row: its date, title, operation or
  account".
- **C.** Drop "amount" from the line on every row.

**Recommended:** B, because the card should say what `⏎` really does on the row under the
cursor.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Two ways to group refused rows.** The ledger's bulk edit groups its refusals with its own
  `group_refusals` (`rows 1, 2: <message>`,
  [transactions.py](../expense/tui/screens/transactions.py)), apart from the shared
  `grouped_refusals` the sheet import and the LOG bar use (`<field>: <words> rows 1, 2`,
  [formatting.py](../expense/formatting.py)). One helper; merging them changes what the bulk
  edit's toast says, so its wording is the owner's pick first [UI].
- **`a` on Manage ▸ Accounts reads its refusals as a form does.** `a` is sent from a list but
  goes through `format_error`, so a `CONCURRENT_CHANGE` on it says `save again`, where `t`, `d`
  and `c` say the list's `press r, then try again` (`list_refusal_text` in
  [_base.py](../expense/tui/screens/_base.py)). Send `a` through `list_refusal_text` too, which
  drops `_toggle`'s `error_text` parameter in [accounts.py](../expense/tui/screens/accounts.py);
  the `_toggle_busy` comment there says "archive toggle" though it guards `t` as well.
- **A code comment speaks of a "phase".** The `Staged` docstring in
  [log_bar.py](../expense/tui/screens/log_bar.py) says "`saved` is the phase-4 half"; say what
  `saved` means instead.
- **A non-date in the Edit form's date crashes the app.** On the `⏎` Edit form, and the
  bank-line Edit form that shares its code, `⏎` on a date bar holding a non-date (e.g. `abc`)
  accepts it, and `ctrl+s` raises an uncaught `typer.BadParameter`, so the app exits with a
  traceback ([edit_form.py](../expense/tui/screens/edit_form.py) stores the text unchecked;
  [dates.py](../expense/dates.py) raises; [_form.py](../expense/tui/screens/_form.py)
  `action_submit` does not catch it). The fix checks the date at `⏎`, as the amount field
  does; the message it shows is wording the owner picks first.
- **The DATE hint on a form with every line read-only [UI].** On the "no batch" Edit form of an
  archived account's line whose title and operation code are both set, the bar sits on DATE and
  the hint still reads `YYYY-MM-DD · enter to accept, or type a date`, though the bar takes
  nothing typed (`FormBar` in [_form.py](../expense/tui/screens/_form.py)). What the hint says
  there is the owner's pick, from a mockup.
- **The NAME hint on the account forms says "enter to save" [UI].** On Manage ▸ Accounts New and
  Edit, `⏎` on NAME moves to the next line, but its hint reads `enter to save`
  ([create_forms.py](../expense/tui/screens/create_forms.py) around lines 209 and 247). The
  account's COLOR hint, `optional · empty enter to skip` (around line 261), goes with it: `⏎`
  there keeps a colour the line holds. The wording is the owner's pick.
- **The note after `b` counts what moved.** `b` on one part of a split transaction moves every
  part, so the note reads `2 rows → BCP Oro PEN · 2 left their reconciliation` (the owner's pick,
  2026-10-18); the Edit form's "It left its reconciliation" has the same gap. Waits on the engine
  ask [a-line-move-answers-what-it-moved.md](to-engine/a-line-move-answers-what-it-moved.md): the
  answer to a move names only the transaction sent
  ([transactions.py](../expense/tui/screens/transactions.py) `bulk_receipt`).
- **No test pins a renamed or currency-split account on a `Not sent:` line.** The sheet import
  names a held-back row's account as it was created (`account 'BCP Oro PEN' (PEN)`, a renamed
  leg by its new name), as [commands.md](commands.md) says; only a hand-run check proved it. Add
  the test in [test_grouped_refusals.py](../tests/unit/test_grouped_refusals.py).
- **The "no batch" `?` card lists `esc Back` twice.** Seen by the acceptance check of
  2026-10-23 ([reconciliations.py](../expense/tui/screens/reconciliations.py)); one row, with a
  test.
- **A huge amount reads, then crashes what prints it.** `parse_amount`
  ([quickadd/money.py](../expense/quickadd/money.py)) reads a finite `1e5000`, typed or in either
  importer's file, as an integer of over 4,300 digits, and printing it (the bank preview, a row's
  repr) raises `ValueError`. The bound belongs to the engine: read the live contract for the
  largest amount it takes, and if it states none, it becomes an engine ask; the client never
  invents one.
- **No unit test pins that Reconciliations leaves archived accounts out.** The browse reads
  `GET /accounts` without `include_archived`
  ([reconciliations.py](../expense/tui/screens/reconciliations.py) `ReconciliationsScreen.fetch`),
  so an archived account and its reconciliations are not listed ([tui.md](tui.md)); only the
  acceptance check of 2026-10-18 saw it live. A unit test should hold it.
- **A test docstring says the sheet import brings a colour.**
  [test_tui_create_forms.py](../tests/unit/test_tui_create_forms.py) around line 409 says "(the
  sheet import's, say)"; the import sends no colour, and the colour no swatch shows is the
  engine's own on a row created with none, as [tui.md](tui.md) "Stepping past COLOR keeps it"
  says.
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
  `expense-world-split-screen.html` backs the split screen as built, and
  `expense-world-grouped-refusals.html` backs refused-row lines already built (linked from
  commands.md, tui.md and a test docstring).
  Deleting one means removing its links from tui.md and from code and test docstrings in the
  same change.
- **A whole-file live run of the bank-line tests leaves an empty account.** One
  `contract-lines-*` account stays on the practice user after `tests/contract/test_bank_lines.py`
  runs whole, though no test leaves one when run alone; find which pair of tests does it
  ([test_bank_lines.py](../tests/contract/test_bank_lines.py)).
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
- **Right amounts, no crashes, and the picks already made**: a dot-before-comma amount refused,
  `nan`/`inf` in a bank file, a split part holding only #Pendiente, the colour line, two "no
  batch" wordings, the note after `b`, the sheet import's report
  ([specs/right-amounts-no-crashes.md](specs/right-amounts-no-crashes.md)).
- **Move the official data into the app** (a wipe and one fresh sheet import). Open questions:
  [specs/before-the-official-import.md](specs/before-the-official-import.md).
- **Bank files become the intake** — rows arrive as BCP `.xlsx` downloads through the TUI
  import door; the first real bank import follows the official import. Plan:
  [file-import-plan.md](file-import-plan.md).
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.
- **`PickerModal` carries rows but is still a modal.** A surface carrying rows should be a
  pushed screen (the bulk `c`/`b`/`h` picks). The other modals (`HelpModal`, `PromptModal`,
  `DiscardStagedModal`, `ConfirmModal`) are short questions and stay modals. **[UI]** — the
  replacement needs drawing.
- **A superseded read can paint on a reconciliation's checklist.** A read started mid-burst of
  `space` ticks can still reach `_populate` after the last tick's answer empties the queue, when
  its worker passed the `is_cancelled` check just before the newer load cancelled it
  ([reconciliations.py](../expense/tui/screens/reconciliations.py) `_load_txns`, `_populate`).
  The stale read paints and spends `_land_on`, so the fresh read after it lands the cursor on row
  1, not on the line ticked last. Narrow window, not yet reproduced. The fix lets `_populate`
  paint only the newest load, with a test that holds the old read past the cancel.

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
