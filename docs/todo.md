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

### Approve the spec for the catch-up's leftovers
Asked 2026-10-26 · Blocks: [specs/catch-up-leftovers.md](specs/catch-up-leftovers.md)

Small things the bank download and closing catch-up turned up: old engine words still quoted in
tests and docs, six mockups drawing old screens, and a completed statement's footer still
offering `c Complete` and `d Delete`; and, from the catch-up of 2026-10-27, whether the "no
batch" list now lists oldest first, as the engine can since 2026-10-26. The footer and that order
are the two things you see change, and their questions are in the spec. Approve it or rewrite it,
and answer them there.

**Recommended:** approve it with 1 B (drop `c` only) and 2 B (oldest first), after the sheet
import and the PDF specs.

### Approve the spec for closing a statement from its PDF
Asked 2026-10-25 · Blocks: [specs/statements-close-from-their-pdf.md](specs/statements-close-from-their-pdf.md)

The engine shipped the upload on 2026-10-26, and the draft is rewritten to what shipped: you
name the account, the engine reads the PDF, creates the missing lines under `@Pendiente`, takes
out the extra ones, puts every line in the paper's order and completes the month. It holds two
questions: where you start the upload, and whether a PDF of the wrong account waits for
accounts to carry their bank numbers (the card numbers and account names you described move to
their own spec if not). Approve it or rewrite it, and answer them there.

Set aside by the owner on 2026-10-26: not to run now.

**Recommended:** approve it with the recommended answers when you take it up again.

### Approve the spec for the test suites' leftovers
Asked 2026-10-25 · Blocks: [specs/test-suite-leftovers.md](specs/test-suite-leftovers.md)

Eighteen small things, all inside the tests and their tools: copies to merge, stale test
sentences and comments, tests that check less than they say or fail at random in CI, the drift
check covering more of the engine's answers, the practice-data cleaner reading every page, the
guard checking a test-engine start whole, and two heads pinned showing a bracketed name whole.
Nothing you see changes. On 2026-10-27 you moved the future-dated line's live test out (it
waits on the PDF spec) and brought in the backlog's test-only items. Approve it, and say
whether it runs before or after the PDF spec.

**Recommended:** approve it and run it now: the PDF spec is set aside, and this one waits on
no answer.

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
  ([specs/test-suite-leftovers.md](specs/test-suite-leftovers.md)); every backlog item that
  lives only in the tests and their tools is in it.
- **A live test checks a statement upload's words for a future-dated line.** The engine names
  the line, "Row <place>: Must not be in the future." on `rows.<place>.date`, on POST
  /reconciliations/import as on the other two imports (contract version `46e2fdf6e11d7548`);
  no live test sends a statement PDF yet, since none made up exists in this repo. It needs the
  made-up statement PDF that point 7 of
  [specs/statements-close-from-their-pdf.md](specs/statements-close-from-their-pdf.md) builds,
  so it comes after that spec, as its own spec.
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
- **A comment cites a decisions.md heading in the wrong case.**
  [_base.py](../expense/tui/screens/_base.py) line 419 cites "the ledger fills the window"; the
  heading in [decisions.md](decisions.md) is "The ledger fills the window".
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
  does not), `expense-world-screen-map.html` (linked from nowhere; its `#sheet` pane draws the
  app reading the `.xlsx` itself), `expense-world-sheet-import-engine.html` (backs the sheet
  import built on 2026-10-27; linked from commands.md, import_cmd.py and test_cmd_import.py),
  and
  `expense-world-bank-import-10b.html`; `expense-world-import-door.html` (screens 3, 4 and 6) and
  `expense-world-bank-lines-upload.html` (screens 1 to 3) still draw the import's old preview,
  the screen map's split pane and `expense-world-split-screen.html` (linked from the screen map)
  draw a split screen the app no longer has, `⏎` and `s` opening the Edit form instead;
  `expense-world-wording-picks.html` backs hints and the bulk pick already built (its question 1
  is answered by the Edit form, drawn in `expense-world-split-transaction-screen.html`; linked from tui.md, bulk_pick.py and the
  docstrings of test_tui_form_hints.py, test_tui_edit_form.py and test_tui_bulk_edit.py), and
  `expense-world-opening-balance-note.html` backs the begin balance hint already built (panes
  1 B and 2 B; linked from tui.md, decisions.md and test_tui_form_hints.py), and
  `expense-world-grouped-refusals.html` backs the LOG bar's refused-row lines already built
  (screens 2 A and 3 A, linked from tui.md and a test docstring), and its screens 1 and 3 draw
  the old sheet import's `--apply` output (`Accounts: created 0, reused 31`, a `Failures` block),
  which the app no longer prints. Ledger footers still
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

- **The app reads its settings file on every engine call.** `load_usable` at launch, then about
  25 `ensure_loaded()` calls ([reads.py](../expense/reads.py), [app.py](../expense/tui/app.py),
  the screens), so the app cannot take its settings as a pipe and an agent cannot point it at
  the practice engine without the key reaching a file. Load the settings once at launch and hand
  them to every screen; then the pipe form in [runtime.md](runtime.md) works for the app.

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
  spec and the bank download and closing a statement done on 2026-10-26, the sheet import
  through the engine on 2026-10-27; the PDF statement below is what is left.
- **Amounts follow your number format.** The app reads the Mac's region by default, and an
  optional setting on the owner's account wins when set, so every device agrees (an engine
  ask). The format is used both for amounts typed and for every amount shown (owner, 2026-10-25).
  Under English (Peru), `1,5` is not a number, so it is refused instead of saved as 15.00.
  Needs a spec.
- **A month's statement closes from the bank's PDF**: a draft spec, rewritten to the engine's
  upload of 2026-10-26, waiting for the owner's approval and answers
  ([specs/statements-close-from-their-pdf.md](specs/statements-close-from-their-pdf.md)).
- **Move the official data into the app** (a wipe and one fresh sheet import), every question
  answered: [specs/before-the-official-import.md](specs/before-the-official-import.md). The
  sheet import through the engine it waited on is done (2026-10-27).
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
