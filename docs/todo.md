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

To approve, every question answered: [the official import](specs/before-the-official-import.md),
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

- **No LOG bar test checks the peek's title and count on a two-currency pick** (`$visa %usd`).
  Nothing you see changes.
- **The shared practice user holds no accounts,** so the tester proves LOG bar and account
  checks with unit tests only. Nothing you see changes. Waits on the engine ask "Give the
  shared practice user an account that every reseed keeps".
- **No live test sends a zero-amount `SALDO INICIAL` row dated before a person's opening
  balance.** Nothing you see changes. It waits on the engine ask "Say whether a zero-amount row
  dated earlier stops a sheet row being the opening balance"; then
  [test_sheet_import.py](../tests/contract/test_sheet_import.py) pins the answer.
- **The statement upload's live-test gaps.** Nothing you see changes. In
  [test_statement_import.py](../tests/contract/test_statement_import.py) no live test opens a
  card's month before its paper, applies a card paper with $0 dollars to a soles-and-dollars
  account, or draws the "balances alone" `ACCOUNT_CURRENCY_NOT_ON_PAPER` apart from a dollar
  line; `CONCURRENT_CHANGE` is proven only in unit tests, which pin 120 columns.
- **Code names still call a statement a "batch" or a reconciliation.** Nothing you see changes.
  In reconciliations.py `_batch_list`, `_show_batches`, `_load_batches`, the mode and widget id
  `"batches"`, `ReconciliationsScreen`, `ReconciliationDetailScreen`, `NewReconciliationScreen`
  (imported by home.py, help.py, statement_upload.py); reads.py's `reconciliation` parameter (the
  engine's `statement_id`); home.py's `"reconciliations"` key; and comments in formatting.py,
  dates.py, theme.py, _base.py, help.py, transactions.py, bank_import.py and log_bar.py.
- **`_panel_layout` returns an untyped dict.** Nothing you see changes. In reconciliations.py it
  returns `dict[str, object]`, unpacked with `**` into `set_headers`, so mypy cannot check it;
  type it as `_UnfiledLayout` is.
- **[UI] Below 66 columns the "no statement" list cuts the amount.**
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
- **A row's day shows in UTC.** The engine sends times in UTC, and every list shows the first
  ten characters as the day ([formatting.py](../expense/formatting.py) `format_short_date`), so a
  row timed after 19:00 in Lima shows the next day, though the engine counts it on its own day.
  Rows dated by day alone (00:00 in the user's time zone) show right. Waits on the engine ask
  "Send each transaction's calendar day with it"; the lists then show that day.
- **Mockups that back no open work.** A mockup lives only while it backs open work; many in
  [mockups/](mockups/) back built screens and draw an older app. Delete each one no spec, todo
  item or to-engine file links, with its links from docs, code and docstrings.
  `expense-world-sheet-import-engine.html` is one (named only in import_cmd.py's and
  test_cmd_import.py's docstrings); seven are linked from nowhere: bank-import-10b,
  currencies-transaction-picks, no-batch-caption, opening-balance-rows, pending-hashtag-home,
  refusal-hints and screen-map; leftover-picks is linked only from a retired spec, and
  statements-screens only from code and tests.
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
