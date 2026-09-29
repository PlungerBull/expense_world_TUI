# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

**Current spec:** none. The owner writes specs in [specs/](specs/) and names the current one
here.

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
Asked 2026-09-26 · Blocks: The TUI is the only human surface
Do these through normal use of `expense world` on the real ledger, undoing any change by hand,
and report anything wrong. This entry is deleted when they pass.

1. On a filtered ledger, re-category a few rows in bulk, then `pgdn`: no row skipped or repeated.
2. On an account's "no batch" (`u`) list, edit a row, then `pgdn`: the same.
3. The categories and hashtags screens show a correct "page N of M", and no `422` appears.
4. In Reconciliations, `⏎` on an account shows its full history, oldest period first.
5. On a batch's working screen, `r` keeps the header current; deleting that batch from another
   terminal shows "record gone".

### Before you re-import the sheet: rename `PENDIENTES`
Asked 2026-09-27 · Blocks: One-time title alignment after the official migration
The sheet still files rows under `PENDIENTES`, as a category and as a hashtag; the ledger has
neither (uncategorised rows go to the system category `@Pendiente`). Rename those rows in the
sheet before the re-import's `--apply`, or it creates `PENDIENTES` again. Every other account,
category and hashtag name resolves (dry run, 2026-09-27). Import before you complete any
reconciliation: a completed reconciliation seals its window, and the import then skips those
rows as `sealed`, never creating them (contract: POST /v1/transactions/import).

### Why does the practice engine start as `python -m uvicorn`?
Asked 2026-09-28 · Blocks: nothing; [cli-runtime.md](cli-runtime.md) "Working against the live engine" points agents at a guide they may no longer open
The ops guide says to start the practice engine as `python -m uvicorn`, not the `uvicorn` command,
and gives the reason only as a pointer to the engine's local-deployment guide ("TCC", a macOS
permission rule). No agent may read the engine's folder now, so the reason has to be written here.
- **A.** Paste the reason from that guide (or say it in your own words) and it goes into
  cli-runtime.md.
- **B.** Ask the engine coder to put it in the engine's published contract or a note you hand over.

**Recommended:** A. It is one sentence, and it is an ops fact, not an API rule.

### Will you still log card purchases by hand after the official migration?
Asked 2026-09-27 · Blocks: [file-import-plan.md](file-import-plan.md) §6, and Backlog
"After `--apply`, the bank import's \"may be logged twice\" warning…"
- **A.** Yes. The import then offers "rename your row to the bank's wording?" every time it
  finds a match (an engine ask plus a mockup).
- **B.** No. Nothing to build; this closes.

**Recommended:** none. It depends on how you will work.

### Do the bank's product names match your accounts?
Asked 2026-09-20 · Blocks: The TUI import door (C1), [file-import-plan.md](file-import-plan.md) §3
The bank says `VISA Infinite Sapphire`, `Sueldo Soles` and `Cuenta Digital Dólares`. Your
accounts are `BCP Signature`, `BCP PEN` and `BCP USD`.
- **A.** They are the same accounts under other names. Only `BCP Signature` needs confirming:
  it is the Infinite card, renamed.
- **B.** A card is missing from the system and needs creating.

**Recommended:** none. Only you know.

### Tags that know the category: the four choices in §5
Asked 2026-09-20 · Blocks: Tags that know the category
[category-hashtags-plan.md](category-hashtags-plan.md) §5 holds four choices, H1–H4. Each is
laid out with its reasons and a recommendation: which screens narrow the tag list, what a
category with no tags shows, whether the "show all tags" shortcut is `##`, and whether usage
counts show.
- **A.** Accept all four recommendations.
- **B.** Go through them one by one.

**Recommended:** A. Each one is argued in §5.

### Tags that know the category: does the legend row change?
Asked 2026-09-20 · Blocks: Tags that know the category
The LOG bar's one-row legend lists the whole quick-add grammar. If `##` (show all tags) ships,
the legend is the only place anyone would discover it, and that row is already full.
- **A.** The legend gains `##`, and something else gets shorter.
- **B.** The legend stays as it is. `##` goes undocumented on screen.

**Recommended:** none yet. The mockup re-pick decides it.

### Tags that know the category: does a deleted transaction still count as "using" a tag?
Asked 2026-09-20 · Blocks: Tags that know the category
The engine says no. So deleting a row can quietly drop a tag out of that category's
suggestions.
- **A.** That matches what you expect. Keep it.
- **B.** A deleted row should still count. That is an engine ask.

**Recommended:** A. It is how the engine already works.

### TUI-only: should the flat commands print JSON only?
Asked 2026-09-26 · Blocks: The TUI is the only human surface
- **A.** JSON only. The human tables, page footers, colour swatches and name columns go.
- **B.** Keep a plain human mode.

**Recommended:** A. The agent reads JSON, and the TUI is the human view.

### TUI-only: one flat command per engine endpoint, or only the ones the agent uses?
Asked 2026-09-26 · Blocks: The TUI is the only human surface
- **A.** One per endpoint.
- **B.** Only the ones the agent actually uses.

**Recommended:** A, so the agent can check any endpoint.

### TUI-only: what happens to `import bank`, `import sheet` and `expense log`?
Asked 2026-09-26 · Blocks: The TUI is the only human surface
The imports are flat-only until the TUI import door ships, and `import bank` asks you which
account a file belongs to. `expense log "<line>"` is the flat twin of the LOG bar.
- **A.** They stay as human commands until the TUI import door ships, then shrink like the
  rest.
- **B.** They stay as human commands for good.

**Recommended:** none yet.

### TUI-only: which command guard tests stay?
Asked 2026-09-26 · Blocks: The TUI is the only human surface
Every flat command must have an `Example:`, an error test, `--json` on reads and `--yes` on
deletes ([test_command_surface.py](../tests/unit/test_command_surface.py)). Confirmation prompts
are for people, and the agent always passes `--yes`.
- **A.** Keep them all.
- **B.** Drop the people-only ones (prompts, `Example:`). Keep the error test and `--json`.

**Recommended:** none yet.

### TUI-only: where does the shared code live?
Asked 2026-09-26 · Blocks: The TUI is the only human surface
The TUI takes its reads and formatters from `expense/commands/*`. If the commands shrink, that
name stops fitting.
- **A.** It stays in `expense/commands/`.
- **B.** It moves to a package not named after the commands.

**Recommended:** none yet.

### TUI-only: what is the repo's new name?
Asked 2026-09-26 · Blocks: The TUI is the only human surface
Today it is `PlungerBull/expense_CLI_menu` on GitHub and `expense_world_CLI` locally. Name it,
and say whether the `expense` command keeps its name:
- **A.** `expense` stays.
- **B.** `expense` changes too, to a name you give.

**Recommended:** A. It is what you type every day.

### TUI-only: is the note to the engine coder right?
Asked 2026-09-26 · Blocks: The TUI is the only human surface
The draft is in [tui-only-plan.md](specs/tui-only-plan.md) "Draft note to the engine coder".
- **A.** Send it as written, with the new name filled in.
- **B.** Change it. Say how.

**Recommended:** A.

---

## Backlog

Open work, not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Tags that know the category.** Plan: [category-hashtags-plan.md](category-hashtags-plan.md).
  Waits on the "Tags that know the category" questions above. **[UI]**
- **The TUI import door (C1).** Plan: [file-import-plan.md](file-import-plan.md) §3. Waits on
  "Do the bank's product names match your accounts?" above. **[UI]**, nothing drawn.
- **The TUI is the only human surface; the flat CLI is for the agent** (with the repo rename and
  the engine-coder note). Spec: [specs/tui-only-plan.md](specs/tui-only-plan.md). Waits on the
  "TUI-only" questions and the TUI check above.
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
   after-apply case beside pick C and let the owner pick. **[bug]** **[UI]** · Tied to the question in Waiting on you
   on hand-logged card purchases: if a rename proposal is built, this
   case mostly stops happening.

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
