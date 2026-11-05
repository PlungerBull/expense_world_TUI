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
adds an entry instead of guessing, acts on the answer, then deletes it. A question reads:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

### Approve the rewritten specs
Asked 2026-10-29 · Blocks: every spec in [specs/](specs/)

To approve, every question answered: [the official import](specs/before-the-official-import.md).
To pick from a mockup, then approve:
[a long account name in the LOG bar peek's count line](specs/a-long-name-in-the-peek-count.md)
and [footers that fit the screen](specs/footers-fit-the-screen.md).

Answered, waiting on its engine ask (for you to hand over) and a mockup of the preview:
[a statement PDF's preview names the lines the close will flag](specs/the-preview-names-the-lines-the-close-will-flag.md).

Approved: [the test-suite leftovers](specs/test-suite-leftovers.md), ready to run;
[accounts carry their numbers](specs/accounts-carry-their-numbers.md), waiting on the engine.

**Recommended:** approve the rest.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
CLAUDE.md "Specs and tasks".

- **About 20 unit test files name accounts with a currency code** (`BCP Signature PEN`,
  `BCP USD`), where an account holds its currencies; `test_tui_log_bar.py` shows the shape.
  Nothing you see changes. `grep -rln 'BCP PEN\|BCP Signature PEN\|BCP USD' tests/unit`.
- **No LOG bar test checks the peek's title and count on a two-currency pick** (`$visa %usd`).
  Nothing you see changes.
- **The shared practice user holds no accounts,** so the tester proves LOG bar and account
  checks with unit tests only. Nothing you see changes. Waits on the engine ask "Give the
  shared practice user an account that every reseed keeps".
- **The live test of a person's opening balance proves less than it could.** Nothing you see
  changes. `test_an_existing_person_gets_its_opening_balance_in_each_currency` in
  [test_sheet_import.py](../tests/contract/test_sheet_import.py) reads `currencies[]` but not
  `rows[].is_opening_balance` or `counts.opening_balances`; both balances are positive (one
  negative would prove the sign). A zero-amount earlier `SALDO INICIAL` row waits on the engine
  ask "Say whether a zero-amount row dated earlier stops a sheet row being the opening balance".
- **No unit test covers an apply that lists sealed rows.** Nothing you see changes. In
  [test_cmd_import.py](../tests/unit/test_cmd_import.py), "Sealed, on a closed statement's day"
  is asserted only on the dry run; `expense import sheet --apply` prints it through the same list
  as the rows of zero. Done when an apply test pins that list's line.
- **The live sheet test's docstring cites nothing for its counts.** Nothing you see changes.
  [test_sheet_import.py](../tests/contract/test_sheet_import.py)'s module docstring says what
  `split_lines` and `split_rows` count with no citation of its own; it could cite
  (contract: POST /v1/transactions/import-sheet, "Response").
- **The statement upload's live-test gaps.** Nothing you see changes. In
  [test_statement_import.py](../tests/contract/test_statement_import.py) no live test opens a
  card's month before its paper, applies a card paper with $0 dollars to a soles-and-dollars
  account, or draws the "balances alone" `ACCOUNT_CURRENCY_NOT_ON_PAPER` apart from a dollar
  line; `CONCURRENT_CHANGE` is proven only in unit tests, which pin 120 columns.
- **Old engine words in a mockup and three tests.** Nothing you see changes.
  [expense-world-opening-balance.html](mockups/expense-world-opening-balance.html) draws
  `Amount cannot be zero.` (the engine: `Must not be zero.`);
  [test_tui_statement_list.py](../tests/unit/test_tui_statement_list.py),
  [test_tui_edit_form.py](../tests/unit/test_tui_edit_form.py) and
  [test_tui_bulk_edit.py](../tests/unit/test_tui_bulk_edit.py) quote `Validation failed.` Done
  when each is the practice engine's own words.
- **Part 7's test leftovers.** Nothing you see changes. test_no_read_only_fields.py's sample
  paths read `/reconciliations/…`; balance refusals in test_tui_reconcile_detail.py and
  test_errors.py are keyed `balances.<account_id>.…`, where the engine keys them by currency
  code; docstrings in test_tui_bank_import.py and test_tui_reconciliations.py claim a list is
  "not by `sort_order`", which the fixture no longer proves; the drift script's note for `l12` is
  loose; test_statement_codes.py calls the account holding a code `holder`.
- **The statement screens' live tests say less than they check, and `u` is unpinned.** Nothing
  you see changes. In [test_bank_lines.py](../tests/contract/test_bank_lines.py), the "no statement"
  and statement-screen tests' docstrings miss the currency and number they check, and the latter
  writes `"date_asc"` for `UNFILED_SORT`. No test pins that `u` on the Statements browse brings
  back the shared table's edge and gap and `esc` takes them away.
- **The flagged lines' screen shares no read with its live test.** Nothing you see changes.
  [reconciliations.py](../expense/tui/screens/reconciliations.py) builds the review-list read
  inline and the live test types it again; decisions.md "A screen's live test reads through the
  screen's own read" wants one function both call.
- **Code calls a statement a "batch" or a reconciliation.** Nothing you see changes. The module
  docstrings of edit_form.py and reconciliations.py ("New batch:"), comments there ("no batch",
  "One batch", `unreadable_note`), reads.py's and cursor_list.py's `set_headers` docstrings, a
  test docstring ("date_start orders the batch now"), and the decisions.md heading "Rows in no
  batch live in the reconciliation view…", renamed with its citations in tui.md,
  reconciliations.py and decisions.md in one change.
- **The Statements screens' unit tests prove less than they could.** Nothing you see changes.
  No test pins the revert question, `u`'s tooltip, the "it orders the statement" hint or the
  `loading…` caption. In test_tui_statement_balances.py the 60-column starting and ending boxes
  pass without the fix (give one the long name), `_box_at` waits with `pilot.pause()`, nothing
  covers the refusal lines at 60 columns, and `NOVIEMBRE` aliases `NOVIEMBRE_IBK`; in
  test_tui_statement_screen.py the refusal-lines test (c) waits on a condition true before and
  after (wait for the rows to grow).
- **Small tidy-ups in the Statements code.** Nothing you see changes. In reconciliations.py,
  `_UNFILED_LAYOUT` writes a literal gap `2` beside checklist.py's `GAP` and is a
  `dict[str, object]` unpacked with `**`; `_panel_gap` repeats `pane_rows`' chrome sum.
  `CursorList`'s `header_rule_span` needs `header_rule=False`, unenforced; `UnderHead` takes
  `screen_stack[-2]`, not its own place in the stack.
- **[UI] Below 66 columns the "no statement" list cuts the amount.**
- **Three live files still build an opening balance's body by hand.** Nothing you see changes.
  test_create_sent_again.py, test_opening_balance.py (`_seed_body`) and
  test_reserved_name_held.py in [tests/contract/](../tests/contract/) should start from
  `Scratch.opening_balance_body` and change only what their refusal needs. Done when the three
  pass against the practice engine, leaving nothing on either practice user.
- **Three small finds in the practice engine's start script and the drift script.** The `$!`
  comment calls the launcher's pid "the backgrounded subshell" and runs past 100 characters; the
  guard's launcher-name exemption passes a name built at run time (its docstring states the
  limit); `--record-version` takes a version listed anywhere in the change log, untested.
- **`a` on Manage ▸ Accounts reads its refusals as a form does.** `a` is sent from a list but
  goes through `format_error`, so a `CONCURRENT_CHANGE` on it says `save again`, where `t`, `d`
  and `c` say the list's `press r, then try again` (`list_refusal_text` in
  [_base.py](../expense/tui/screens/_base.py)). Send `a` through `list_refusal_text` too, which
  drops `_toggle`'s `error_text` parameter in [accounts.py](../expense/tui/screens/accounts.py);
  the `_toggle_busy` comment there says "archive toggle" though it guards `t` as well.
- **Unused test parameters in test_tui_create_forms.py.** Nothing you see changes. `_run_refused`
  and its callers take a `monkeypatch` they no longer use, and
  `test_an_emptied_colour_bar_goes_back_to_the_rows_own_swatch` asks for toasts it never reads.
- **A code comment speaks of a "phase".** The `Staged` docstring in
  [log_bar.py](../expense/tui/screens/log_bar.py) says "`saved` is the phase-4 half"; say what
  `saved` means instead.
- **[UI] The "no statement" `?` card lists keys that don't apply.** It shows `esc Back` twice, `esc
  Close the panel` (off there), and both `pgdn Load the next 10 rows` and `pgdn Next page` once
  every row is loaded; on a 30-row terminal it clips its last line. One row per key that works,
  with a test; the tests pinning today's doubled rows (`CARD_THIS_SCREEN` in
  test_tui_ledger_archived.py, "Moving around" in test_tui_reconciliations.py) change with it.
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
  Rows dated by day alone (00:00 in the user's time zone) show right. Waits on the engine ask
  "Send each transaction's calendar day with it"; the lists then show that day.
- **"A transaction is split" is spelled three ways.** `is_split_line` in
  [reconciliations.py](../expense/tui/screens/reconciliations.py) and the inline
  `bank_line_part_count(line) > 1` in transactions.py and edit_form.py; one helper in
  formatting.py. Also one shared title cell for `(untitled)` (checklist.py and the "no statement"
  rows), and the delete question shows `—` for the same untitled line: `(untitled)` everywhere.
- **A guard against "purchase" in the app's words.** The owner's word is "transaction"
  (2026-10-17); add a test in [test_suite_hygiene.py](../tests/unit/test_suite_hygiene.py) that
  fails when a user-visible string in `expense/` says "purchase". Code comments and docstrings
  say "purchase" too (transactions.py, reconciliations.py, reads.py, bank_import.py,
  quickadd/route.py, app.tcss): make them "split transaction" or "bank line" first, so the guard
  needs no exemption for comments.
- **Mockups that back no open work.** A mockup lives only while it backs open work; many in
  [mockups/](mockups/) back built screens and draw an older app. Delete each one no spec, todo
  item or to-engine file links, with its links from docs, code and docstrings.
  `expense-world-sheet-import-engine.html` is one (named only in import_cmd.py's and
  test_cmd_import.py's docstrings); seven are linked from nowhere: bank-import-10b,
  currencies-transaction-picks, no-batch-caption, opening-balance-rows, pending-hashtag-home,
  refusal-hints and screen-map; leftover-picks is linked only from a retired spec, and
  statements-screens only from code and tests.
- **Two more copies of the name filter.** `matching` in
  [picker.py](../expense/tui/widgets/picker.py) is the shared name filter; reconciliations.py
  (around line 1181) still copies it, and create_forms.py (around line 156) has a two-field
  version. One shared copy, with tests.
- **Code comments still carry mockup tags, and one module docstring is stale.** About sixteen
  comments (app.tcss, reconciliations.py, statement_upload.py, bank_import.py, modals.py,
  log_bar.py), the "Screen 1…4" tags in import_cmd.py and test_cmd_import.py, "pane N" in test
  docstrings and names like `test_a_cards_preview_is_screen_1a_and_writes_nothing` point at
  mockup panes; say what the code does. bank_import.py, log_bar.py and
  test_tui_statement_upload.py name two mockups that do not exist. reconciliations.py's module
  docstring describes the old New form, complete and delete.
- **The app reads its settings file on every engine call.** `load_usable` at launch, then about
  25 `ensure_loaded()` calls ([reads.py](../expense/reads.py), [app.py](../expense/tui/app.py),
  the screens), so the app cannot take its settings as a pipe and an agent cannot point it at
  the practice engine without the key reaching a file. Load the settings once at launch and hand
  them to every screen; then the pipe form in [runtime.md](runtime.md) works for the app.

- **Every thread worker hands back through `call_while_attached`.** A worker whose screen is
  gone still runs its callback on pruned widgets ([tui.md](tui.md) "Async / workers"). About 20
  hand-backs in `expense/tui/` still call `self.app.call_from_thread`; move them (checking whether
  a write's `on_success` must run after a dismiss) and guard against a raw one in
  `test_suite_hygiene.py`.
- **Three comments still describe the split screen.** `key_index`'s docstring in
  [errors.py](../expense/errors.py) says "the split's `parts`"; the
  [transactions.py](../expense/tui/screens/transactions.py) module docstring says `s` opens the
  Edit form "on DATE as `⏎` does", though it opens on the first line that can change; and the
  [edit_form.py](../expense/tui/screens/edit_form.py) module docstring says the form opens on
  DATE, though it opens on the first line that can change.
- **Amounts follow your number format.** The app reads the Mac's region by default, and an
  optional setting on the owner's account wins when set, so every device agrees (an engine
  ask). The format is used both for amounts typed and for every amount shown.
  Under English (Peru), `1,5` is not a number, so it is refused instead of saved as 15.00.
  Needs a spec.
- **Bank files become the intake.** Plan: [file-import-plan.md](file-import-plan.md).
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.
- **A superseded read can paint on a statement's list.** A read started mid-burst of `space`
  ticks can pass `_load_txns`' `is_cancelled` check just before a newer load cancels it, then
  paint in `_populate` and spend `_land_on`, so the cursor lands on row 1, not the line ticked
  last. Not yet reproduced. `_populate` paints only the newest load, with a test.

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
