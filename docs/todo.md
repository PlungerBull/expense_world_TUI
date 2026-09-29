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
adds an entry instead of guessing, acts on the answer, then deletes the entry. A question reads:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

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

### Before you re-import the sheet: rename `PENDIENTES`
Asked 2026-09-29 · Blocks: One-time title alignment after the official migration
The sheet still files rows under `PENDIENTES`, as a category and as a hashtag; the ledger has
neither (uncategorised rows go to the system category `@Pendiente`). Rename those rows in the
sheet before the re-import's `--apply`, or it creates `PENDIENTES` again. Every other account,
category and hashtag name resolves (dry run, 2026-09-27). Import before you complete any
reconciliation: a completed reconciliation seals its window, and the import then skips those
rows as `sealed`, never creating them (contract: POST /v1/transactions/import).

### Bank names: rename your accounts, or teach the import the bank's names?
Asked 2026-09-29 · Blocks: The TUI import door (C1), [file-import-plan.md](file-import-plan.md) §3
The bank says `VISA Infinite Sapphire`, `Sueldo Soles` and `Cuenta Digital Dólares`; your
accounts are `BCP Signature`, `BCP PEN` and `BCP USD`. They are the same accounts and the
names should match. Also confirm that `VISA Infinite Sapphire` is `BCP Signature`.
- **A.** Rename your accounts in the TUI to the bank's names, once. Nothing to build.
- **B.** Keep your names. Each account also stores the bank's name for it, and the import picks
  the account by itself (an engine ask, so web and iOS get it too, plus a mockup).

**Recommended:** A. It makes the names match with nothing to build.

### Tags that know the category: hide the other tags, or list them second?
Asked 2026-09-29 · Blocks: Tags that know the category
Panes **D** and **E** in [expense-world-log-legend-and-picker.html](mockups/expense-world-log-legend-and-picker.html)
§3. Label pickers in apps like Todoist and Gmail rank; they do not hide.
- **A. Pane D.** The category's tags come first, every other tag below a divider. No `##`, no
  empty-list case, no legend change; only [category-hashtags-plan.md](category-hashtags-plan.md)
  §5 H1 and H4 remain, each with a recommendation.
- **B. Pane E.** Only the category's tags; `##` opens the rest. All four §5 choices remain, plus
  where `##` goes in the full legend row.

**Recommended:** A. Nothing is ever out of reach, and it is the smaller build.


---

## Backlog

Open work, not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Tags that know the category.** Plan: [category-hashtags-plan.md](category-hashtags-plan.md).
  Waits on the "Tags that know the category" question above. **[UI]**
- **The TUI import door (C1).** Plan: [file-import-plan.md](file-import-plan.md) §3. Waits on
  "Bank names: rename your accounts, or teach the import the bank's names?" above. **[UI]**, nothing drawn.
- **The TUI is the only human surface; the flat CLI is for the agent** (with the repo rename and
  the engine-coder note). Spec: [specs/tui-only-plan.md](specs/tui-only-plan.md). **Deferred**
  until the owner picks it up; its open questions live in the spec.
- **One-time title alignment after the official migration.** Plan:
  [file-import-plan.md](file-import-plan.md) §6. Runs after the sheet re-import and before the
  2026 periods are completed, because a completed period locks its rows' titles. The engine's
  rule is **import first, reconcile second**: a reconciliation completed before its rows exist
  seals the window against them (contract: POST /v1/transactions), and the import then skips
  those rows as `sealed` (contract: POST /v1/transactions/import). Full sequence:
  [file-import-plan.md](file-import-plan.md) §10.

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

- **After `--apply`, the bank import's "may be logged twice" warning still says "check before
  --apply".** `render_result` in [bank_import_cmd.py](../expense/commands/bank_import_cmd.py)
  prints `excess_lines` the same way on preview and apply, so after `--apply` it reads
  `! 1 ledger row no file row matched — check / before --apply, it may be logged twice` — too
  late. The engine computes `excess` against the ledger before the write, so on an equal-count
  day (owner typed `Starbucks`, bank says `STARBUCKS MIRAFLORES LIMA PE`) the bank's row has
  just been written as `new` and the ledger now holds the duplicate. The picked mockup
  ([mockups/expense-world-bank-import-10b.html](mockups/expense-world-bank-import-10b.html)
  pane 2, pick C) and the test
  (`test_unmatched_ledger_rows_are_one_line_per_day_counted_up_front`) cover the preview only.
  Proposed wording, not yet picked: *"! 1 day where the ledger may now hold the same movement
  twice — check it and delete the extra one"*, with the same per-day lines under it. Draw the
  after-apply case beside pick C and let the owner pick. **[bug]** **[UI]** · Card purchases
  come in mainly through the import and typing one by hand stays possible, so this case is rare
  but real; no "rename to the bank's wording" offer is built.

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

- **Copy the agent loop to the engine repo**, with guards for its own real database; optionally a
  read-only board at the `productivity_world` level showing each repo's loop and what waits on the
  owner. Outside this repo, so the owner starts it ([decisions.md](decisions.md) "The agent loop:
  one per repo, the main session orchestrates").
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
