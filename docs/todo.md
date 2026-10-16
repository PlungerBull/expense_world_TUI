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

### A row with no hashtag: is it "not classified yet"?
Asked 2026-10-15 · Blocks: [specs/official-migration.md](specs/official-migration.md) task 1
`PENDIENTE` means "not classified yet" on both the category and the hashtag. The engine already
has `@Pendiente` for categories, and files every row typed with no category there. It has no
such hashtag, so it gets asked for one. Should a row typed with no hashtag land on it the same
way?
- **A.** Yes, like the category: no hashtag means `#Pendiente`, so every row always has one, and
  the sheet's `PENDIENTES` lands there on whichever side it sits.
- **B.** No: `#Pendiente` is only set by hand or by the import; a row may also have no hashtag.
**Recommended:** A, because it makes both sides work the same and "what is still unclassified"
one list.

### How the sheet shows that rows are parts of one bank line
Asked 2026-10-15 · Blocks: [specs/official-migration.md](specs/official-migration.md) task 2
You split bank lines, so the engine is asked to keep one identity across a split
([engine-asks/split-bank-lines-keep-one-identity.md](engine-asks/split-bank-lines-keep-one-identity.md)).
The import must also tell which sheet rows belong together. How does the sheet show it today?
- **A.** The parts sit on consecutive rows: the first carries the bank code, the next rows with
  no code and the same date and account belong to it.
- **B.** Nothing marks them; you would add a marker column before the import.
- **C.** Something else.
**Recommended:** none; only you know how the sheet is filled.

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
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, title alignment).
  Spec (draft, deferred): [specs/official-migration.md](specs/official-migration.md).
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
