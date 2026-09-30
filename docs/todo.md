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

### Review the three draft specs
Asked 2026-09-29 · Blocks: each spec's work
[tag-suggestions.md](specs/tag-suggestions.md), [official-migration.md](specs/official-migration.md)
and [tui-import-door.md](specs/tui-import-door.md) are first drafts. Each ends with its open
questions and draft tasks. Correct what is wrong, answer the questions, and name the one the loop
starts on.

### Check the TUI after the engine update
Asked 2026-09-29 · Blocks: The TUI is the only human surface
Do these through normal use of `expense world` on the real ledger, undoing any change by hand,
and report anything wrong. This entry is deleted when they pass.

1. On a filtered ledger, re-category a few rows in bulk, then `pgdn`: no row skipped or repeated.
2. On an account's "no batch" (`u`) list, edit a row, then `pgdn`: the same.
3. The categories and hashtags screens show a correct "page N of M", and no `422` appears.
4. In Reconciliations, `⏎` on an account shows its full history, oldest period first.
5. On a batch's working screen, `r` keeps the header current; deleting that batch from another
   terminal shows "record gone".

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Tag suggestions that know the category.** Spec (draft): [specs/tag-suggestions.md](specs/tag-suggestions.md).
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, title alignment).
  Spec (draft): [specs/official-migration.md](specs/official-migration.md).
- **Import bank files from the TUI** (with the after-apply "may be logged twice" wording). Spec
  (draft): [specs/tui-import-door.md](specs/tui-import-door.md).
- **The TUI is the only human surface; the flat CLI is for the agent** (with the repo rename and
  the engine-coder note). Spec: [specs/tui-only-plan.md](specs/tui-only-plan.md). **Deferred**
  until the owner picks it up; its open questions live in the spec.
- **Field navigation in the edit form is broken on macOS.** `⌃↑` / `⌃↓` are claimed by
  Mission Control / Application Windows before the terminal sees them. The footer no longer
  advertises them; the keys are still bound in [_form.py](../expense/tui/screens/_form.py).
  What is left is choosing the replacement. **[bug]** **[UI]**
  - `shift+↑` / `shift+↓` are bindable (probed live). Then plain `↑↓` on the three fields with
    a suggestion list needs a meaning: options **J** and **K** in
    [mockups/expense-world-plus-and-arrows.html](mockups/expense-world-plus-and-arrows.html)
    §4, neither picked.
  - **`tab` / `shift+tab`**, not drawn in the mockup: plain `↑↓` keep their one meaning and
    nothing is sacrificed. Every form has exactly one focusable widget (`Input#bar`), so `tab`
    is free today. Fits [decisions.md](decisions.md) "One key per job".
  - To decide with it: forms have no `?` card (a focused `Input` swallows printable keys), so
    a form key has no discovery surface — possibly the one case where an arrow-family key
    earns a footer slot (`⇥ Field` beside `esc Cancel  ^s Save`), against the "arrows never
    get a slot" rule in [tui.md](tui.md) §4.

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

- **`QuickAddLogScreen` is an edit-only screen with a create-era name.** Rename the class and
  `quick_log.py` (≈6 source + 5 test files, nothing behavioural) — `EditFormScreen` /
  `edit_form.py` is the obvious target. [tui.md](tui.md) links to the module;
  `test_relative_doc_links_resolve` catches a miss.

---

## Parked

No commitment. Declined ideas stay listed so they are not proposed again.

- **A read-only board over every repo's loop**, at the `productivity_world` level, showing what
  each loop is doing and what waits on the owner. Worth it once more than two repos run a loop.
  Copying the loop itself to the engine is an open ask:
  [engine-asks/engine-agent-loop.md](engine-asks/engine-agent-loop.md).
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
