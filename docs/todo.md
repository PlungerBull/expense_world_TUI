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

### The engine moved its contract: one purchase's parts can now be read
Asked 2026-10-17 · Blocks: every task of [specs/bank-lines-and-pending-hashtag.md](specs/bank-lines-and-pending-hashtag.md)

The practice engine serves contract `c572d3a5f4f509d1`; this app last caught up with
`3129bfa2c43a4446`. The version check prints:

```
c572d3a5f4f509d1  2026-10-17
  added: `GET /bank-lines/{id}`, one bank line read by id: `id`, `account_id`, `operation_code`
  (`null` when the line has none), `net_cents` (the signed sum of its live parts, inflow
  positive, outflow negative), `part_count` (its live parts) and `transaction_ids` (its live
  parts' ids, in the order `GET /transactions?bank_line_id=` lists them by default). [...]
  changed: *Transactions (Ledger)* → *Bank lines* points to the new line read. No transaction
  response field changes.
3d7205a872889283  2026-10-17
  added: `GET /transactions` and `GET /transactions/count` take `?bank_line_id=`, the live parts
  of one bank line. [...] No transaction response field changes.
```

This is the first half of the "read a bank line" ask: the parts of one purchase and its total,
one purchase per read. Reading up to 200 purchases at once has not shipped, and no hand-off file
has arrived yet. Nothing in the app breaks.
- **A.** Catch up now: one task in the current spec reads the new parts list and the new line
  read, for the ledger, the split screen and the edit form to use.
- **B.** Wait for the engine's hand-off file and the 200-at-once read, then catch up in one go.

**Recommended:** A, because it adds without breaking, and tasks 4–6 need it; until the 200-at-once
read ships, a ledger page reads each split purchase on it separately.

### Finish picking the bank-lines and pending-hashtag screens
Asked 2026-10-16 · Blocks: tasks 4, 5 and 8 of [specs/bank-lines-and-pending-hashtag.md](specs/bank-lines-and-pending-hashtag.md)

Your picks of 2026-10-17 are in the spec. Still open, each on its page's "To answer" box:
- the ledger, redrawn your way, [mockups/expense-world-split-lines-ledger.html](mockups/expense-world-split-lines-ledger.html):
  a letter for the split mark, one for what `⏎` opens, and what `c` and `h` do with a split
  purchase selected;
- Manage, [mockups/expense-world-pending-hashtag-manage.html](mockups/expense-world-pending-hashtag-manage.html):
  "ok" on the Hashtags table.

**Recommended:** none — these are your screens.

### Does the split screen stop you saving until nothing is left?
Asked 2026-10-17 · Blocks: task 5 of [specs/bank-lines-and-pending-hashtag.md](specs/bank-lines-and-pending-hashtag.md)

The split screen already counts what is left to place as you type (100 split 50/50 shows
`0.00 left`; one 50 changed to 40 shows `-10.00 left`). You asked that saving is not allowed
until it reaches 0. The engine already refuses a split that does not add up, and this repo's
rule is that the app does not copy an engine rule: if the engine ever changes it, every app
would have to change too.
- **A.** `^s` is off until 0 is left; the count turns red while it is not.
- **B.** The count turns red while it is not 0, and `^s` still sends; the engine refuses and its
  words show under the parts.

**Recommended:** B, because the red count already tells you before you press, and the rule stays
in one place; A is fine if you want the key off.

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
