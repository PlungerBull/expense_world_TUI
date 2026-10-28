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

### Approve the first two specs of the cards and statements catch-up, and their tasks
Asked 2026-10-27 · Blocks: [specs/catch-up-cards-statements-1-routes.md](specs/catch-up-cards-statements-1-routes.md), [specs/catch-up-cards-statements-2-live-suite.md](specs/catch-up-cards-statements-2-live-suite.md)

The engine's hand-off of 2026-10-27 (contract `46e2fdf6e11d7548` to `e06456a20aca6e4c`) makes a
card its own thing in the engine and a month's statement one record for the whole card. Much of
the app stops working against it: the statement screens, creating and archiving accounts, moving
a transaction to another account, and the PDF upload. On 2026-10-27 you said to catch up, and the
hand-off is planned into five specs, run in order. The first two change nothing you see: spec 1
puts the app on the engine's new routes and names, spec 2 the live tests (8 tasks each, drafted
in each spec). Spec 1 holds two small questions: the order of the lines a close flags, and the
app's line when `t` is refused for an account that has been in a statement.

**Recommended:** approve both, with 1 A and 2 A in spec 1, and run them now. Creating a bank
account, `t` from person to bank account, `a` on a bank account and `--create-names` stay broken
until the catch-up's "Cards in the app".

### Approve the sheet import's counts line spec
Asked 2026-10-27 · Blocks: [specs/catch-up-split-rows.md](specs/catch-up-split-rows.md)

Part 3 of the catch-up: the sheet import says how many sheet rows its split transactions come
from. Its question 1 is the words, `split transactions 3 (8 rows)` or `split transactions 3 ·
rows in them 8`, and whether `(0 rows)` shows when there are none. Two tasks are drafted.

**Recommended:** approve it with 1 A, `(0 rows)` shown, to run after spec 2.

### Hand over the answer on moving an account to another card
Asked 2026-10-27 · Blocks: question 1 of [specs/before-the-official-import.md](specs/before-the-official-import.md), and pairing in [specs/catch-up-cards-statements-3-cards.md](specs/catch-up-cards-statements-3-cards.md)

The engine coders proposed on 2026-10-27 one action, "move this account to that card", allowed
only while the account has never been in a statement. The answer
[to-engine/move-an-account-to-another-card.md](to-engine/move-an-account-to-another-card.md)
says yes to it with their limits, and no to their optional extra, the sheet import refusing a
name used in both currencies whose accounts sit on different cards: your four people with both
currencies must each be alone on a card, so that refusal would be a guess. Copy it into the
engine repo's `docs/from-tui/` and say when it is done.

**Recommended:** hand it over as written.

### Hand over four more asks to the engine
Asked 2026-10-27 · Blocks: questions of [specs/catch-up-cards-statements-3-cards.md](specs/catch-up-cards-statements-3-cards.md) and [specs/catch-up-cards-statements-4-statement-screen.md](specs/catch-up-cards-statements-4-statement-screen.md)

Four things every app would otherwise work out on its own, each its own file in
[to-engine/](to-engine/):
- "Create a bank account and its own card in one write";
- "Delete a card with its last account, so no client leaves an empty card behind";
- "List a card's bank lines in no statement in one read";
- "Say what a client does with a flagged line on a card with a statement code".

Each is an option in a question of "Cards in the app" or "A card's statement on one screen", so
handing them over now lets the engine coders work while specs 1 and 2 run.
- **A.** Hand over all four now.
- **B.** Wait until you answer those specs' questions.

**Recommended:** A, since each is the complete fix and the app works around none of them.

### Read the specs for cards and for the statement screen
Asked 2026-10-27 · Blocks: [specs/catch-up-cards-statements-3-cards.md](specs/catch-up-cards-statements-3-cards.md), [specs/catch-up-cards-statements-4-statement-screen.md](specs/catch-up-cards-statements-4-statement-screen.md)

The catch-up's last two specs change what you see: where cards live in the app, how a new bank
account gets its card, pairing and unpairing, archiving a whole card, the statement screen for
a two-currency card, closing a currency with no movement by hand, and when flagged lines show.
Their questions are in each spec; the ones about screens come with mockups.

**Recommended:** read them now and say if anything is missing; the mockups are drawn while specs
1 and 2 run, and you pick from them then.

### Answer the official import's three questions
Asked 2026-10-27 · Blocks: [specs/before-the-official-import.md](specs/before-the-official-import.md)

The import now needs every bank account on a card, and an account never changes card today. The
spec answers your question of 2026-10-27, whether the import or the PDF upload could work out
which accounts share a card (neither can), and asks: (1) how the Visa's two accounts end up on
one card, (2) whether the old Oro card and the two Interbank accounts are one card each, and (3)
what happens to a future person whose first row is an opening balance.

**Recommended:** 1 A (every account gets its own card, then you pair the Visa in the app before
importing, once the engine's move lands), 2 A (one card per bank product), 3 A (the balance stays
the sheet's). The import runs after the catch-up's "Cards in the app".

### Approve the spec for the catch-up's leftovers
Asked 2026-10-26 · Blocks: [specs/catch-up-leftovers.md](specs/catch-up-leftovers.md)

Four small things the bank download and closing catch-up turned up, none of which you see except
four mockups redrawn with the app's current words. Its questions and everything about statements
moved into the cards and statements catch-up on 2026-10-27.

**Recommended:** approve it, to run after the catch-up.

### Approve the spec for the test suites' leftovers
Asked 2026-10-25 · Blocks: [specs/test-suite-leftovers.md](specs/test-suite-leftovers.md)

Eleven small things, all inside the tests and their tools: copies to merge, stale comments, tests
that check less than they say or fail at random in CI, the drift check covering more of the
engine's answers, and the guard checking a test-engine start whole. Nothing you see changes. On
2026-10-27 the points about cards and statements moved into the catch-up.

**Recommended:** approve it, to run after the catch-up.

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
- **The statement detail's `r` reads the account's whole list to refresh one record.**
  The engine reads one statement by its id (contract: GET /v1/statements/{statement_id});
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
- **The engine catch-up of 2026-10-27, cards and statements** (to `e06456a20aca6e4c`): five
  specs, run in order:
  [specs/catch-up-cards-statements-1-routes.md](specs/catch-up-cards-statements-1-routes.md),
  [specs/catch-up-cards-statements-2-live-suite.md](specs/catch-up-cards-statements-2-live-suite.md),
  [specs/catch-up-split-rows.md](specs/catch-up-split-rows.md),
  [specs/catch-up-cards-statements-3-cards.md](specs/catch-up-cards-statements-3-cards.md) and
  [specs/catch-up-cards-statements-4-statement-screen.md](specs/catch-up-cards-statements-4-statement-screen.md).
- **Amounts follow your number format.** The app reads the Mac's region by default, and an
  optional setting on the owner's account wins when set, so every device agrees (an engine
  ask). The format is used both for amounts typed and for every amount shown (owner, 2026-10-25).
  Under English (Peru), `1,5` is not a number, so it is refused instead of saved as 15.00.
  Needs a spec.
- **A month's statement closes from the bank's PDF**: paused until the cards and statements
  catch-up is done ([specs/statements-close-from-their-pdf.md](specs/statements-close-from-their-pdf.md)).
- **Move the official data into the app** (a wipe and one fresh sheet import):
  [specs/before-the-official-import.md](specs/before-the-official-import.md), after the catch-up's
  "Cards in the app" and the engine's move of an account to another card.
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
