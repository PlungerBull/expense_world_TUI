# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

Only the orchestrator edits this file; workers put tasks and questions in their reports. Closed
items get deleted, not ticked ([decisions.md](decisions.md) "The open-work list holds only open
work"). Cite items by title. **[UI]** means an HTML mockup in [mockups/](mockups/) must be
picked before any code. Engine asks live in [engine-asks/](engine-asks/), one file each.

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

### Tell the engine coders three of their notes are caught up
Asked 2026-10-15 · Blocks: nothing in this repo
Tell the engine coders, so they delete their copies:
- **tui-rename:** the drop box is now [engine-answers/](engine-answers/) and the rename brief is
  deleted. Once you have told them, the orchestrator deletes
  [engine-answers/tui-rename.md](engine-answers/tui-rename.md).
- **account-opening-balance** and **refusal-reasons:** the app follows both, and the live
  contract suite tests both.
**Recommended:** tell them now, in one message.

### A sheet row that is `PENDIENTES` on one side only
Asked 2026-10-12 · Blocks: [specs/official-migration.md](specs/official-migration.md) task 1
A row whose category or hashtag is `PENDIENTES` goes to `@Pendiente` with no `PENDIENTES`
hashtag. What happens to the row's other label?
- **A.** Category `COMIDA` + hashtag `PENDIENTES` goes to `@Pendiente` and loses `COMIDA`;
  category `PENDIENTES` + hashtag `#LUZ` keeps `#LUZ`.
- **B.** Category `COMIDA` + hashtag `PENDIENTES` keeps `COMIDA` and only loses the hashtag.
- **C.** Any such row goes to `@Pendiente` with no hashtag at all.
**Recommended:** none; it is your rule for your sheet.

### Splitting one bank line into several rows
Asked 2026-10-12 · Blocks: [specs/official-migration.md](specs/official-migration.md) task 2
A bank line's code sits on one row only, and card lines carry no code. A line of 100 split into
60 and 40 is not recognised when that period is uploaded again, and the line is added a second
time. Do you split bank lines, in the sheet today or in the app later?
- **A.** Yes. Ask the engine to give every bank line an identity it keeps, shared by the parts
  of a split, so a re-upload matches the line to its parts.
- **B.** No. One bank line is always one row; nothing to build.
**Recommended:** A if you ever split, because every client needs the same rule and only the
engine can keep it.

### Where "Pendiente" sits when you re-categorise several rows at once
Asked 2026-10-11 · Blocks: nothing
In Transactions, `c` on selected rows lists your categories in the engine's order and puts
`@Pendiente` last. The engine itself lists `@Pendiente` first. It is the one place the app moves
an item of a list the engine orders.
- **A.** Keep it last: it is the "undo a wrong pick" choice, out of the way of the real ones.
- **B.** Put it first, where the engine puts it.
**Recommended:** A, because it is how the screen works today and the everyday picks stay on top.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **A bank import's 409 names the engine's row key, not the file line.** A refused
  `POST /v1/transactions/import` maps `rows.<i>.*` keys to file lines only on a 422
  ([bank_import.py](../expense/tui/screens/bank_import.py), `row_refusals` in
  [bank_import/engine.py](../expense/bank_import/engine.py)); a 409 keyed
  `rows.<i>.operation_code` or `rows.<i>.id` shows the raw key, though its next-step line is
  right. It changes what the screen shows, so it needs a mockup first.

- **The guard allows a practice-engine start from a subfolder of the engine checkout.** It checks
  the interpreter word `.venv/bin/python`, not that the command runs from the checkout's root
  ([guard.py](../.claude/hooks/guard.py)); either check the folder or list it under the
  docstring's limits, with a test.

- **The guard allows a practice-engine start with only one of the two database URLs.** The engine
  coders' rule is that `SUPABASE_DB_URL` and `ADMIN_DB_URL` are both set on the start command,
  every time; the guard accepts either one alone and leans on the engine refusing to start
  ([guard.py](../.claude/hooks/guard.py)). Require both, with a test.

- **The guard blocks the practice user's reseed.** On 2026-10-14 the tester's
  run of the engine's seed script with `--force`, its output sent to `/dev/null`, was refused as a read or write in the engine
  checkout ([guard.py](../.claude/hooks/guard.py)), so a full acceptance check cannot get its key.
  Allow the reseed form [runtime.md](runtime.md) "Working against the live engine" gives,
  with a test in [test_claude_hooks.py](../tests/unit/test_claude_hooks.py).

- **The app reads its settings file on every engine call.** `load_usable` at launch, then about
  25 `ensure_loaded()` calls ([reads.py](../expense/reads.py), [app.py](../expense/tui/app.py),
  the screens), so the app cannot take its settings as a pipe and an agent cannot point it at
  the practice engine without the key reaching a file. Load the settings once at launch and hand
  them to every screen; then the pipe form in [runtime.md](runtime.md) works for the app.

- **The bank import works out a sign from `transaction_type`.** `excess_groups` flips the sign of
  the import response's `excess` rows from their `transaction_type`
  ([bank_import/engine.py](../expense/bank_import/engine.py)), a client-side copy of the engine's
  sign rule. Check whether `POST /v1/transactions/import` can answer signed; if it cannot, write
  an engine ask for a signed `excess`, and delete the flip once it lands.

- **A test docstring tells history.** `test_tui_reconciliations.py` line 157 says "`date_start`
  orders the batch now"; state it in the present tense
  ([test_tui_reconciliations.py](../tests/unit/test_tui_reconciliations.py)).

- **Three flaky unit tests.** Each failed in a full `pytest tests/unit` run on 2026-10-02 and
  passes alone; on 2026-10-14 `test_enter_home_with_unwritten_staged_rows_asks_first` blocked two
  commits and `test_config_screen_shows_only_the_engine_connection` one; for each, find whether the test asserts too early or the screen has a race.
  - `test_toggle_error_drops_queued_intents_and_resyncs`
    ([test_tui_reconcile_detail.py](../tests/unit/test_tui_reconcile_detail.py)): 2 PUTs sent,
    1 expected — the queued toggle went out before the failing PUT's error dropped it.
  - `test_config_screen_shows_only_the_engine_connection`
    ([test_tui_system.py](../tests/unit/test_tui_system.py)).
  - `test_enter_home_with_unwritten_staged_rows_asks_first`
    ([test_tui_bank_import.py](../tests/unit/test_tui_bank_import.py)).
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, title alignment).
  Spec (draft, deferred): [specs/official-migration.md](specs/official-migration.md).
- **Catch up with contract 42d70a629215928d** (completing a reconciliation asks for its ending
  balance, the live tests follow the engine). Spec (draft, deferred):
  [specs/engine-catch-up-42d70a6.md](specs/engine-catch-up-42d70a6.md).
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
