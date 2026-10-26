# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

Only the orchestrator edits this file; workers put tasks and questions in their reports. Closed
items get deleted, not ticked ([decisions.md](decisions.md) "The open-work list holds only open
work"). Cite items by title. **[UI]** means an HTML mockup in [mockups/](mockups/) must be
picked before any code. Engine asks wait in [to-engine/](to-engine/), one file each, until
handed over.

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

### An archived card account with no statements
Asked 2026-10-26 · Blocks: question 2 of [specs/catch-up-bank-download-and-closing.md](specs/catch-up-bank-download-and-closing.md)

When a card account is archived before it ever had a statement, should the card's list on
Reconciliations still show its empty column? The question and its options are in the spec.

**Recommended:** A (no column), because the column was empty anyway.

### Two practice keys in CLAUDE.md and the guard
Asked 2026-10-26 · Blocks: nothing

CLAUDE.md and the guard script's comments and messages still speak of "the practice user's key";
the reseed now prints two. May the orchestrator change the wording to "both practice users'
keys"? No rule changes.
- **A.** Yes.
- **B.** No, leave it.

**Recommended:** A, so the instructions match what the reseed prints.

### Approve the spec for the engine words' leftovers
Asked 2026-10-26 · Blocks: [specs/engine-words-leftovers.md](specs/engine-words-leftovers.md)

What the notes spec turned up: a name or title holding `[like this]` still loses it in lists, a
backslash can drop from the bulk edit's note, and several tests prove less than they say.
The only thing you see change is bracketed names showing whole. Approve it or rewrite it.

**Recommended:** approve it, after the engine catch-up, which matters more.

### Approve the spec for the sheet import through the engine
Asked 2026-10-26 · Blocks: [specs/sheet-import-through-the-engine.md](specs/sheet-import-through-the-engine.md), and so [specs/before-the-official-import.md](specs/before-the-official-import.md)

The engine now reads your spreadsheet itself; `expense import sheet` sends it the file, and the
app's own reader goes. It holds three questions: whether the app creates the accounts,
categories and hashtags you don't have yet, how you confirm which name goes where, and whether
renaming an account as it comes in stays. Approve it or rewrite it, and answer them there.

**Recommended:** approve it with the recommended answers, to run after the engine catch-up.

### Approve the spec for closing a statement from its PDF
Asked 2026-10-25 · Blocks: [specs/statements-close-from-their-pdf.md](specs/statements-close-from-their-pdf.md)

The engine shipped the upload on 2026-10-26, and the draft is rewritten to what shipped: you
name the account, the engine reads the PDF, creates the missing lines under `@Pendiente`, takes
out the extra ones, puts every line in the paper's order and completes the month. It holds two
questions: where you start the upload, and whether a PDF of the wrong account waits for
accounts to carry their bank numbers (the card numbers and account names you described move to
their own spec if not). Approve it or rewrite it, and answer them there.

**Recommended:** approve it with the recommended answers, to run fourth.

### Approve the spec for the test suites' leftovers
Asked 2026-10-25 · Blocks: [specs/test-suite-leftovers.md](specs/test-suite-leftovers.md)

Ten small things, all inside the tests and their tools: copies to merge, stale test sentences
and comments, a test that checks less than its name says, the drift check covering more of the
engine's answers, and the practice-data cleaner reading every page. Nothing you see changes.
Approve it or rewrite it.

**Recommended:** approve it, after the PDF spec, which matters more.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **`a` on Manage ▸ Accounts reads its refusals as a form does.** `a` is sent from a list but
  goes through `format_error`, so a `CONCURRENT_CHANGE` on it says `save again`, where `t`, `d`
  and `c` say the list's `press r, then try again` (`list_refusal_text` in
  [_base.py](../expense/tui/screens/_base.py)). Send `a` through `list_refusal_text` too, which
  drops `_toggle`'s `error_text` parameter in [accounts.py](../expense/tui/screens/accounts.py);
  the `_toggle_busy` comment there says "archive toggle" though it guards `t` as well.
- **A code comment speaks of a "phase".** The `Staged` docstring in
  [log_bar.py](../expense/tui/screens/log_bar.py) says "`saved` is the phase-4 half"; say what
  `saved` means instead.
- **Leftovers in the test suites**: a draft spec waiting for the owner's approval
  ([specs/test-suite-leftovers.md](specs/test-suite-leftovers.md)).
- **No test pins a renamed or currency-split account on a `Not sent:` line.** The sheet import
  names a held-back row's account as it was created (`account 'BCP Oro PEN' (PEN)`, a renamed
  leg by its new name), as [commands.md](commands.md) says; only a hand-run check proved it. Add
  the test in [test_grouped_refusals.py](../tests/unit/test_grouped_refusals.py).
- **The "no batch" `?` card lists keys that don't apply.** It shows `esc Back` twice and `esc
  Close the panel`, which is off there, and both `pgdn Load the next 10 rows` and `pgdn Next page`
  once every row is loaded; on a 30-row terminal it clips its last line
  ([reconciliations.py](../expense/tui/screens/reconciliations.py)). One row per key that works,
  with a test. Two tests pin today's cards whole, the doubled rows included, and change with the
  fix: the ledger's `CARD_THIS_SCREEN` (doubled `esc`) in
  [test_tui_ledger_archived.py](../tests/unit/test_tui_ledger_archived.py) and the "no batch"
  "Moving around" group (doubled `pgdn`) in
  [test_tui_reconciliations.py](../tests/unit/test_tui_reconciliations.py).
- **A huge amount reads, then crashes what prints it.** `parse_amount`
  ([quickadd/money.py](../expense/quickadd/money.py)) reads a finite `1e5000`, typed or in either
  importer's file, as an integer of over 4,300 digits, and printing it (the bank preview, a row's
  repr) raises `ValueError`. The bound belongs to the engine: read the live contract for the
  largest amount it takes, and if it states none, it becomes an engine ask; the client never
  invents one.
- **No unit test pins that Reconciliations leaves an archived account with no statement code
  out.** The browse reads `GET /accounts` with `include_archived` and leaves archived accounts
  out of its list itself, so the whole card's list can name an archived card account's column
  ([reconciliations.py](../expense/tui/screens/reconciliations.py) `ReconciliationsScreen.fetch`,
  [tui.md](tui.md)); `test_an_archived_card_accounts_halves_still_show_under_its_column` pins
  it for a card account only. A unit test should hold it for an account with no code.
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
  They go with the import door's rewrite in
  [specs/catch-up-bank-download-and-closing.md](specs/catch-up-bank-download-and-closing.md).
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
  say "purchase" too (transactions.py, reconciliations.py, reads.py, bank_import.py,
  quickadd/route.py, app.tcss): make them "split transaction" or "bank line" first, so the guard
  needs no exemption for comments.
- **Mockups that back no open work.** The rule is a mockup lives only while it backs open work;
  most in [mockups/](mockups/) back screens already built, among them
  `expense-world-statement-screen.html` and `expense-world-statement-order.html` (screens the owner
  dropped on 2026-10-25 for the PDF statement; they link only each other and the card-statement
  mockup), the panes of `expense-world-card-statement.html` that draw them (screen 3, its
  `o Order` footer and `shift+↑↓`, and the `e` form of "Three more things"; its panes 1 A, 2 A
  and question 3 B back what is built, linked from tui.md, decisions.md, reconciliations.py and
  two unit tests),
  `expense-world-bank-lines-whole.html` (whose pane 2c still shows a part count the built row
  does not), `expense-world-screen-map.html` (linked from nowhere), and
  `expense-world-bank-import-10b.html`; `expense-world-import-door.html` (screens 3, 4 and 6) and
  `expense-world-bank-lines-upload.html` (screens 1 to 3) still draw the import's old preview,
  the screen map's split pane and `expense-world-split-screen.html` (linked from the screen map)
  draw a split screen the app no longer has, `⏎` and `s` opening the Edit form instead;
  `expense-world-wording-picks.html` backs hints and the bulk pick already built (its question 1
  is answered by the Edit form, drawn in `expense-world-split-transaction-screen.html`; linked from tui.md, bulk_pick.py and the
  docstrings of test_tui_form_hints.py, test_tui_edit_form.py and test_tui_bulk_edit.py), and
  `expense-world-opening-balance-note.html` backs the begin balance hint already built (panes
  1 B and 2 B; linked from tui.md, decisions.md and test_tui_form_hints.py), and
  `expense-world-grouped-refusals.html` backs refused-row lines already built (linked from
  commands.md, tui.md and a test docstring), and still draws a `Must not be a statement line
  another bank line already has.` line the sheet import can no longer get. Ledger footers still
  read `s Split` where the app says `s Edit`, in `expense-world-archived-account.html` (whose
  screen 1 A also draws `s` gone on an archived row), `expense-world-bank-lines-whole.html`,
  `expense-world-pending-hashtag-home.html` and the "today" pane of
  `expense-world-split-transaction-screen.html`; the screen map's ledger `?` card reads "Split
  the cursor row into parts"; `expense-world-enter-and-esc.html` draws the crumb
  `Transactions ▸ Split`, where it is `▸ Edit`; and pane 7 of
  `expense-world-pending-hashtag-manage.html` says the Edit form shows the opening balance's
  note, which it does not.
  Deleting one means removing its links from tui.md and from code and test docstrings in the
  same change.
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
- **Three comments still describe the split screen.** `key_index`'s docstring in
  [errors.py](../expense/errors.py) says "the split's `parts`"; the
  [transactions.py](../expense/tui/screens/transactions.py) module docstring says `s` opens the
  Edit form "on DATE as `⏎` does", though it opens on the first line that can change; and the
  [edit_form.py](../expense/tui/screens/edit_form.py) module docstring says the form opens on
  DATE, though it opens on the first line that can change.
- **The engine catch-up of 2026-10-26**: the hand-off, planned into four specs, its notes
  spec done on 2026-10-26; the rest run in this order: the bank download and closing a
  statement, the current spec
  ([specs/catch-up-bank-download-and-closing.md](specs/catch-up-bank-download-and-closing.md));
  the sheet import through the engine
  ([specs/sheet-import-through-the-engine.md](specs/sheet-import-through-the-engine.md)), a
  draft with three questions; and the PDF statement below.
- **Leftovers of the engine's words**: a draft spec waiting for the owner's approval
  ([specs/engine-words-leftovers.md](specs/engine-words-leftovers.md)).
- **Amounts follow your number format.** The app reads the Mac's region by default, and an
  optional setting on the owner's account wins when set, so every device agrees (an engine
  ask). The format is used both for amounts typed and for every amount shown (owner, 2026-10-25).
  Under English (Peru), `1,5` is not a number, so it is refused instead of saved as 15.00.
  Needs a spec.
- **A month's statement closes from the bank's PDF**: a draft spec, rewritten to the engine's
  upload of 2026-10-26, waiting for the owner's approval and answers
  ([specs/statements-close-from-their-pdf.md](specs/statements-close-from-their-pdf.md)).
- **Move the official data into the app** (a wipe and one fresh sheet import), every question
  answered: [specs/before-the-official-import.md](specs/before-the-official-import.md). It
  follows the sheet import through the engine.
- **Bank files become the intake** — rows arrive as BCP `.xlsx` downloads through the TUI
  import door; the first real bank import follows the official import. Plan:
  [file-import-plan.md](file-import-plan.md).
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.
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
