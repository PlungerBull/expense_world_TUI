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

### Ask the engine coders for one catch-up file from `890453f80a08cec9`
Asked 2026-10-17 · Blocks: the next catch-up (backlog "Catch up with the engine after `890453f80a08cec9`")

The current spec ends at contract `890453f80a08cec9`. The engine has moved on (`ce4e5cb642e53fdb`:
a purchase is reconciled whole, and more in progress). Once the engine coders finish, ask them
for one hand-off file from `890453f80a08cec9` to their current version
([from-engine/README.md](from-engine/README.md)); it becomes the next catch-up spec.

**Recommended:** none — only you can hand it over.

### "ok" on the split screens 1 and 3
Asked 2026-10-17 · Blocks: task 5 of [specs/bank-lines-and-pending-hashtag.md](specs/bank-lines-and-pending-hashtag.md)

[mockups/expense-world-split-action.html](mockups/expense-world-split-action.html): screen 1
(how `s` opens the split screen, redrawn with each part its own ledger row) and screen 3
(splitting again, opening with the current parts). Your other picks are in.

**Recommended:** none — these are your screens.

### Is the one-time title alignment still needed?
Asked 2026-10-16 · Blocks: [specs/official-migration.md](specs/official-migration.md)

Before the migration, the plan has a one-time pass that renames your typed rows to the bank's
wording ([file-import-plan.md](file-import-plan.md) §6), because the engine used to recognise a
row only when its title matched. The engine no longer looks at titles: it recognises a row by its
bank code, or by account, exact day and amount, and it writes the bank's wording onto the row
itself when it recognises it. Rows typed a day off are the only ones it misses, and those show in
the days whose totals disagree.
- **A.** Drop the alignment pass; the month-by-month statement uploads do its job.
- **B.** Keep it as a one-time tidy-up of wording before the first upload.

**Recommended:** A, because the engine now does the renaming on every match, and a day-off row
is already caught by the days that disagree.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Catch up with the engine after `890453f80a08cec9`.** Waits for the engine's hand-off file
  ("Waiting on you" above), which becomes its spec. Known so far: a purchase is reconciled whole
  (`ce4e5cb642e53fdb`), so the live test
  `test_a_line_in_two_reconciliations_is_split_reconciliation_mixed` expects a refusal that no
  longer happens; and the ledger's keys on a part of a split purchase, owner's picks of
  2026-10-17: every part stays an ordinary row, `c` and `h` change only the selected parts, `b`
  reaches every part, and `d` on any part deletes the whole purchase, its question naming how
  many parts go. `d` waits on [to-engine/delete-a-bank-line.md](to-engine/delete-a-bank-line.md).

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

- **A test docstring tells history.** `test_tui_reconciliations.py` line 157 says "`date_start`
  orders the batch now"; state it in the present tense
  ([test_tui_reconciliations.py](../tests/unit/test_tui_reconciliations.py)).

- **Every thread worker hands back through `call_while_attached`.** A worker whose screen is
  popped or the app closing still runs its callback, which then queries pruned widgets
  ([tui.md](tui.md) "Async/workers"). `SectionScreen._load` and the LOG bar use the guard; about
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
- **Catch up with bank lines, splits and the pending hashtag.** Spec (approved,
  the loop runs on it): [specs/bank-lines-and-pending-hashtag.md](specs/bank-lines-and-pending-hashtag.md).
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, 2026 month by month).
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
