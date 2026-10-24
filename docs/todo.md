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

### Hand the engine a reply and ask for the next hand-off
Asked 2026-10-24 · Blocks: the catch-up from `f5cbc6ab4841f0a7` to the engine's current version,
and closing [specs/wording-and-the-bulk-pick.md](specs/wording-and-the-bulk-pick.md)

This client last caught up to contract `f5cbc6ab4841f0a7`. On 2026-10-24 the version check found
the engine moved again, from `a1859d71873b8807` (recorded) to `206db22a65774501`; it printed:

```
  206db22a65774501  2026-10-24
    changed: `statement_line` is built by the engine on every read, never stored: `<CODE>-<YYYYMM>-<NNN>`, from the statement code of the line's account, the year and month of the `date_end` of the completed reconciliation the line is in, and the line's `statement_place`, three digits, zero-padded (`SIG-202603-029`). It is `null` unless that reconciliation is completed, the line holds a place and its account has a statement code: a line in a draft reads `null`, and with a card's soles half completed and its dollars half still a draft, only the soles lines show codes. Every part of a line reads the same one, the parts of a split inside a completed reconciliation included. Changing the account's statement code changes every code its lines show; a revert makes them `null`, and completing again brings the same codes back. It is on every transaction response, every bank line (`GET /bank-lines`, `GET /bank-lines/{id}`, `GET`/`PUT /reconciliations/{id}/statement-order`), `PUT /transactions/{id}`'s `changed_parts` and the activity snapshots, as built when the entry is written. Every statement line stored before is gone. Stated in *Bank lines*, `GET /bank-lines/{id}`, *Bank Accounts* → *Statement code*, *A statement's order* and `POST /reconciliations/{id}/revert`.
    added: `POST /reconciliations/{id}/complete` on an account with a statement code is refused until its statement is fully ordered: every live bank line assigned to the reconciliation, and to its other half for a card, opening balances excepted, holds a place, and no two of them hold the same one. Otherwise `422` on `statement_order` with the new reason `STATEMENT_NOT_ORDERED`, the message counting the lines with no place and naming the places held twice, and nothing is written. It is checked last, after `UNASSIGNED_IN_PERIOD`; an already completed reconciliation is still a silent no-op, and an account without a statement code completes as before. It holds against a statement order, an assignment or a new half sent at the same moment. Stated in `POST /reconciliations/{id}/complete` and *A statement's order*.
    added: `PUT /accounts/{id}` setting or changing `statement_code` is refused when it would make one of the account's live reconciliations the twin (the other live account holding the code, exactly the same days) of one while either of the two is completed: `422` on `statement_code` with the new reason `COMPLETED_STATEMENT_JOINED`, naming both and which is completed, and nothing is written. Checked last, after `STATEMENT_MONTH_TAKEN`, on an archived account too, and against a complete or a reconciliation write sent at the same moment. Revert the completed reconciliation first. Two drafts may still join, sending the code the account already holds is no change, and clearing a code never joins anything. So no two live lines read the same `statement_line`. Stated in *Bank Accounts* → *Statement code*, `PUT /accounts/{id}` and *Bank lines*.
    changed: wording only, *Aggregate exceptions* (*Reconciliation side-effects*, *Bank lines*).
  00c19334d476f25f  2026-10-24
    added: `PUT /reconciliations/{id}/statement-order`, which sets a statement's order: body `{"places": [<bank line id> | null, ...]}`, the statement's bank lines top to bottom, `null` an empty slot for a line the bank's statement has and the ledger does not; for a card, both halves in one list, sent from either half. Each listed line's place is its position from 1. 1 to 999 entries, else `422` on `places` (`OUT_OF_RANGE`). Refused with nothing written, in this order: `404`; either half's account archived (`409` on `reconciliation_id`, `ACCOUNT_ARCHIVED`); an account without a statement code (`409` on `reconciliation_id`, new reason `NO_STATEMENT_CODE`); the statement's halves changing meanwhile (`409`, `CONCURRENT_CHANGE`); either half completed (`409` on `reconciliation_id`, `RECONCILIATION_NOT_DRAFT`); then every problem with the list in one `422`: a list ending in an empty slot (`places.<i>`, new reason `TRAILING_EMPTY_SLOT`), a line listed again (each later `places.<i>`, `DUPLICATE_IN_REQUEST`), an id naming no live line of the statement (`places.<i>`, new reason `LINE_NOT_IN_STATEMENT`), an opening balance (`places.<i>`, new reason `OPENING_BALANCE_NOT_PLACED`) and lines of the statement left out (`places`, new reason `STATEMENT_LINES_MISSING`, naming them). Each part of a line whose place changes gets an `UPDATED` entry and a `version` bump. Answers `200` with the statement as the read below returns it. Stated in *Reconciliations* → *A statement's order* and the route's section.
    added: `GET /reconciliations/{id}/statement-order`, the statement top to bottom from either half: `reconciliation_ids` (the statement's reconciliations, in their accounts' order), `places` (one `{"place", "bank_line"}` per place from 1 to the highest held, `bank_line` as `GET /bank-lines/{id}` returns it or `null` for an empty slot) and `unplaced` (its lines holding no place, opening balances among them, in `GET /bank-lines` order). On an account without a statement code it is `409` (`NO_STATEMENT_CODE`).
    added: `statement_place` on every transaction response (after `statement_line`, in `PUT /transactions/{id}`'s `changed_parts` and the activity snapshots too) and every bank line (`GET /bank-lines`, `GET /bank-lines/{id}`): the line's place in its bank statement, 1 to 999, `null` when it has none; every part of a line reads the same one. Every line reads `null` until a statement's order is sent. No other request takes it (`422`, `UNKNOWN_FIELD`).
    changed: a line's place stays only while it stays in its reconciliation. `PUT /transactions/{id}` taking a line out of its reconciliation (unassigning it, or assigning it to another) sets its `statement_place` to `null` in the same write; `DELETE /reconciliations/{id}` clears its lines' places too, and may now also be `409` (`CONCURRENT_CHANGE`) when a statement-order write places a line in it at the same moment. A revert and a split keep places. Stated in *Reconciliations* → *Assigning transactions*, `POST /reconciliations/{id}/revert` and `DELETE /reconciliations/{id}`.
    changed: wording only, `RECONCILIATION_NOT_DRAFT` covers the statement order; *Bank lines*, *Aggregate exceptions* (*Reconciliation side-effects*, *Bank lines*), `POST /transactions/{id}/split` and `POST /transactions/import` name the statement place.
```

Against it, 7 live tests fail: the 6 in `test_line_codes_and_statement_lines.py` that send
`statement_line`, and `test_bank_lines.py::test_a_bank_line_reads_its_figures`, whose bank line
now carries `statement_place`.

Only you can carry these to the engine coders:
1. The reply [caught-up-f5cbc6ab4841f0a7.md](to-engine/caught-up-f5cbc6ab4841f0a7.md), copied as
   is into the engine repo's `docs/from-tui/`.
2. The message asking for one hand-off file covering contract `f5cbc6ab4841f0a7` to
   `206db22a65774501`: no write takes `statement_line`, accounts gain a three-letter
   `statement_code`, one statement code takes one reconciliation per month, and (above) the
   engine now builds `statement_line` from a statement's order. The reply says the sheet import
   sets no statement lines, which answers the question in their
   `statement-line-from-reconciliation` about the lines it set.

When the file lands in [from-engine/](from-engine/), it becomes the catch-up spec. One choice is
yours now:
- **A.** Catching up to `206db22a65774501` is the next spec once the hand-off lands, and the 7
  failing live tests wait for it; the orchestrator records the new version now, so the wording
  spec's check can pass and it closes.
- **B.** Hold every new spec until the hand-off lands.

**Recommended:** A, because the wording spec's work passed every one of its own checks and does
not touch statement lines; only the version check stands between it and done.

### Hand the engine the ask on editing a whole line
Asked 2026-10-24 · Blocks: saving the split transaction's Edit form in one go

Copy [one-write-edits-a-whole-bank-line.md](to-engine/one-write-edits-a-whole-bank-line.md) as
is into the engine repo's `docs/from-tui/`. Only you can carry it.

### Amounts follow your number format
Asked 2026-10-23 · Blocks: the fix for `1,5` saved as 15.00

You asked to work as normal apps do: the app reads your Mac's region by default, and an
optional setting on your account wins when it is set, so every device agrees. Your Mac's region
is English (Peru): dot for decimals, comma for thousands, as your bank files write them. Under
it, `1,5` is not a number (a comma marks thousands, three digits after it), so it is refused
instead of saved as 15.00. The account setting is an ask to the engine. One choice is yours:
- **A.** Your format is used for amounts you type and for every amount the app shows.
- **B.** Only for amounts you type; the app keeps showing `13,853.20`.

**Recommended:** A, because that is what normal apps do: one format, both ways.

### Split transactions: your Edit form with its parts [UI]
Asked 2026-10-24 · Blocks: the "no batch" `?` card's line on a split row

Your design is drawn in
[mockups/expense-world-split-transaction-screen.html](mockups/expense-world-split-transaction-screen.html):
`⏎` on any part opens the Edit form with the shared fields on top and every part below (amount,
category, hashtags, note), parts added and dropped there; a reconciliation's list shows the
transaction as one line, as today. Two picks are open:
1. In the "no batch" list: **A.** `⏎` opens this form and `d` deletes, as today; **B.** only
   looking, changes and deletes from the ledger. **Recommended:** A, because the usual fix there
   is a wrong date or account, and you chose `⏎` there on 2026-10-17.
2. The `s` key (the Split screen) now that `⏎` edits the parts: **A.** `s` opens the same Edit
   form; **B.** `s` stays as today; **C.** `s` goes. **Recommended:** A, so there is one place to
   change parts.

Saving the form in one go needs the engine ask
[one-write-edits-a-whole-bank-line.md](to-engine/one-write-edits-a-whole-bank-line.md).

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
- **Catch up from contract `f5cbc6ab4841f0a7` to the engine's current one:** every write now
  refuses `statement_line`, so the live contract tests that send it fail
  ([test_line_codes_and_statement_lines.py](../tests/contract/test_line_codes_and_statement_lines.py),
  [test_bank_lines.py](../tests/contract/test_bank_lines.py)), and the shared batch writer's
  row refusals in [runtime.md](runtime.md) "Bulk writes" still list a taken statement line;
  accounts gain `statement_code`, one reconciliation per code per month. Waits on the hand-off
  file ("Hand the engine a reply and ask for the next hand-off" above).
- **No test pins a renamed or currency-split account on a `Not sent:` line.** The sheet import
  names a held-back row's account as it was created (`account 'BCP Oro PEN' (PEN)`, a renamed
  leg by its new name), as [commands.md](commands.md) says; only a hand-run check proved it. Add
  the test in [test_grouped_refusals.py](../tests/unit/test_grouped_refusals.py).
- **The "no batch" `?` card lists keys that don't apply.** It shows `esc Back` twice and `esc
  Close the panel`, which is off there, and both `pgdn Load the next 10 rows` and `pgdn Next page`
  once every row is loaded; on a 30-row terminal it clips its last line
  ([reconciliations.py](../expense/tui/screens/reconciliations.py)). One row per key that works,
  with a test.
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
  commands.md, tui.md and a test docstring), and still draws a `Must not be a statement line
  another bank line already has.` line the sheet import can no longer get.
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
- **Notes and hints that say what is true, and the bulk pick as a screen**: its tasks are done
  and its own checks pass; it waits on the moved contract version ("Waiting on you")
  ([specs/wording-and-the-bulk-pick.md](specs/wording-and-the-bulk-pick.md)).
- **Move the official data into the app** (a wipe and one fresh sheet import). Open questions:
  [specs/before-the-official-import.md](specs/before-the-official-import.md).
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
