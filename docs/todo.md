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

### Review the two draft specs
Asked 2026-09-29 · Blocks: each spec's work
[tag-suggestions.md](specs/tag-suggestions.md) and [official-migration.md](specs/official-migration.md)
have no open questions left and their mockups are approved. Approve each one's draft tasks.

### Where "Pendiente" sits when you re-categorise several rows at once
Asked 2026-10-11 · Blocks: nothing
In Transactions, `c` on selected rows lists your categories in the engine's order and puts
`@Pendiente` last. The engine itself lists `@Pendiente` first. It is the one place the app moves
an item of a list the engine orders.
- **A.** Keep it last: it is the "undo a wrong pick" choice, out of the way of the real ones.
- **B.** Put it first, where the engine puts it.
**Recommended:** A, because it is how the screen works today and the everyday picks stay on top.

### Tags below the divider: A–Z or the engine's order
Asked 2026-10-11 · Blocks: [specs/tag-suggestions.md](specs/tag-suggestions.md)
The tag-suggestions spec lists a category's own tags first, then a divider, then every other tag
A–Z. Everywhere else the app shows tags in the engine's order (your own `sort_order` ascending, then oldest
first), so A–Z would be the app sorting a list itself.
- **A.** Keep A–Z below the divider, as the approved mockup shows.
- **B.** Below the divider, keep the engine's order, the same as today's `#` list.
- **C.** Ask the engine for the whole two-group list, so no client sorts anything.
**Recommended:** C, because web and iOS need the same list and should not each sort it; B if you
want it without waiting on the engine.

### Hand the engine coders one ask
Asked 2026-10-11 · Blocks: nothing
[engine-asks/answers-carry-their-own-instructions.md](engine-asks/answers-carry-their-own-instructions.md)
asks them to confirm the practice engine's start command in full, because their answer points at
an engine file this repo cannot read. Only you can hand it over.
**Recommended:** none, it is an errand.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Catch up to engine contract `26c9f9880ad3540c`** (list orders state their direction; the
  practice engine starts only with its own Python). Spec (current):
  [specs/engine-catch-up-26c9f988.md](specs/engine-catch-up-26c9f988.md).

- **The guard allows a practice-engine start from a subfolder of the engine checkout.** It checks
  the interpreter word `.venv/bin/python`, not that the command runs from the checkout's root
  ([guard.py](../.claude/hooks/guard.py)); either check the folder or list it under the
  docstring's limits, with a test.

- **Three flaky unit tests.** Each failed once in a full `pytest tests/unit` run on 2026-10-02
  and passes alone; for each, find whether the test asserts too early or the screen has a race.
  - `test_toggle_error_drops_queued_intents_and_resyncs`
    ([test_tui_reconcile_detail.py](../tests/unit/test_tui_reconcile_detail.py)): 2 PUTs sent,
    1 expected — the queued toggle went out before the failing PUT's error dropped it.
  - `test_config_screen_shows_only_the_engine_connection`
    ([test_tui_system.py](../tests/unit/test_tui_system.py)).
  - `test_enter_home_with_unwritten_staged_rows_asks_first`
    ([test_tui_bank_import.py](../tests/unit/test_tui_bank_import.py)).
- **Tag suggestions that know the category.** Spec (draft): [specs/tag-suggestions.md](specs/tag-suggestions.md).
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, title alignment).
  Spec (draft): [specs/official-migration.md](specs/official-migration.md).
- **The TUI is the only surface** (flat commands deleted except the imports, three new TUI
  features, the repo rename and the engine-coder note). Spec: [specs/tui-only-plan.md](specs/tui-only-plan.md),
  paused; its open questions live in the spec.
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.
- **Shell completions** — zsh, bash, fish. `expense <TAB>` shows commands, `expense auth
  <TAB>` shows subcommands. No design questions open.

- **Human-name resolution for reference flags.** Accept a UUID or a name on every
  `--account-id` / `--category-id` / `--hashtag-id` / `--reconciliation-id`, via the existing
  list endpoints: case-insensitive exact match, ambiguous matches rejected with a "be more
  specific" error pointing at `expense <resource> list`; UUIDs pass through. Deserves its own
  plan-mode session. Decide deliberately whether it reuses the quick-add matcher
  (contains-anywhere over `load_quickadd_refs`, [quickadd/parse.py](../expense/quickadd/parse.py))
  or keeps a stricter exact match.

- **"Move between accounts" convenience** — one command writing the two ordinary
  `POST /transactions` a transfer consists of. Purely client-side sugar over two writes, which
  is also the argument against it. **[UI]** — needs a mockup covering naming, flags, and the
  two legs' default titles and categories. See [decisions.md](decisions.md) "Transfers are two
  ordinary transactions".

- **`expense import csv`** — only if a real migration needs it. Only a reader would be new; the
  write half is shared ([batch_write.py](../expense/batch_write.py)).

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
  also records the ⌘E conflict). Convenience, not access: `+` and `expense log "<line>"` exist.
- **The quick-add "recents" row** (numbered last-N templates). **Declined 2026-08-25**; listed
  only so it is not re-proposed.
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer dashboards.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **Flat-CLI color conventions** beyond what ships. No demand established.
- **`auth pat create` / `auth pat revoke`.** PATs are issued out-of-band; a future web dashboard
  is expected to issue them. See [cli-spec.md](cli-spec.md) "Auth model".
