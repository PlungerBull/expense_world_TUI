# TODO — the workpad

**The single open-work queue for this repo.** Nothing else tracks pending work — no issue
tracker, no `TODO:` comments in code.

- **Closed items get deleted**, not ticked. Git history is the archive
  ([decisions.md](decisions.md) "The open-work list holds only open work").
- Items marked **[UI]** need an HTML mockup in [mockups/](mockups/) reviewed and explicitly
  picked before any code (CLAUDE.md "Mock every screen before building it").
- **Absolute dates only.**
- **Cite items by title, never by number** — numbering shifts every time an item closes.

Sections: **Now** (the sequenced queue, one plan doc per item) · **Engine asks** · **Small
defects** · **Ergonomics**, **Cosmetic** and **Parked** (none of it blocking).

---

## Now

An index; the depth lives in each plan doc, which is deleted when it ships (its why moves to
[decisions.md](decisions.md)).

| # | Item | Plan | Status |
|---|---|---|---|
| **0** | **The engine uptake's TUI checks** | The list below | Owner, through normal use on the real ledger |
| 1 | Tags that know the category | [category-hashtags-plan.md](category-hashtags-plan.md) | 4 decisions + **[UI]** |
| 2 | The TUI import door (C1) | [file-import-plan.md](file-import-plan.md) §3 | **[UI]**, nothing drawn |
| 3 | The TUI is the only human surface; the flat CLI is for the agent (incl. repo rename + engine-coder note) | [tui-only-plan.md](tui-only-plan.md) | Decided 2026-09-26; 7 owner questions open; starts after the in-flight work |
| 4 | One-time title alignment after the official migration | [file-import-plan.md](file-import-plan.md) §6 | Runs after the re-import, before the 2026 periods are completed |
| 5 | **Owner question:** after the official migration, will the owner still log card purchases by hand? If yes: a standing "rename your row to the bank's wording?" proposal in the import (an engine ask plus a mockup). If no: close this | [file-import-plan.md](file-import-plan.md) §6 | Open question, asked 2026-09-27 |
| 6 | The agent loop: orchestrator + builder/tester/reviewer, one loop per repo | [agent-loop-plan.md](agent-loop-plan.md) | Decided 2026-09-27; owner to name the first spec (recommended: take up the engine's published contract) |

**The engine uptake's TUI checks.** Do these through normal use of `expense world` on the real
ledger, undoing any change by hand, and report anything wrong; delete this list and item 0 when
they pass:

1. On a filtered ledger, re-category a few rows in bulk, then `pgdn`: no row skipped or repeated.
2. On an account's "no batch" (`u`) list, edit a row, then `pgdn`: the same.
3. The categories and hashtags screens show a correct "page N of M", and no `422` appears.
4. In Reconciliations, `⏎` on an account shows its full history, oldest period first.
5. On a batch's working screen, `r` keeps the header current; deleting that batch from another
   terminal shows "record gone".

**Order.** Tags that know the category is independent and could move earlier. The title
alignment waits for the official migration data and must run before the 2026 periods are
completed, because a completed period locks its rows' titles. The engine's rule is absolute
([engine plan §9](../../expense_world_engine/docs/file-import-plan.md)): **import first,
reconcile second** — a reconciliation created before its rows exist seals the window against
them, and the import is then refused. Full sequence: [file-import-plan.md](file-import-plan.md)
§10.

**Before the sheet re-import's `--apply`:** the sheet still files rows under `PENDIENTES`, as a
category and as a hashtag; the ledger has neither (uncategorised rows go to the system category
`@Pendiente`). Rename those rows in the sheet first, or the apply creates `PENDIENTES` again.
Every other account, category and hashtag name resolves (dry run, 2026-09-27).

---

## Engine asks

**Raising these is encouraged, not a last resort** (CLAUDE.md "Ask the engine to change"). Each
entry says what to ask for, why no client can do it properly today, and **what this repo deletes
when it lands**. Handed to the owner for the engine coder; never edited in the engine repo.

- **Move `design-philosophy.md` out of the engine repo.** It is the product vision for every
  client, not an engine rule, and once agents stay inside their own repo no client can read it
  from the engine's folder. Owner's call (2026-09-27): it lives in the `productivity_world`
  root, made a small tracked repo of its own (shared docs only, the project folders ignored)
  so it has history and a backup. **This repo deletes** its CLAUDE.md link to the engine copy.

## Small defects

1. **Field navigation in the edit form is broken on macOS.** `⌃↑` / `⌃↓` are claimed by
   Mission Control / Application Windows before the terminal sees them. The footer no longer
   advertises them; the keys are still bound in [_form.py](../expense/tui/screens/_form.py).
   What is left is choosing the replacement. **[UI]**
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

2. **After `--apply`, the bank import's "may be logged twice" warning still says "check before
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
   after-apply case beside pick C and let the owner pick. **[UI]** · Tied to Now item 5 (the
   owner question on hand-logged card purchases): if a rename proposal is built, this case
   mostly stops happening.

3. **The system-category delete hint names only `@Opening`.** `_SYSTEM_HINT` in
   [categories_cmd.py](../expense/commands/categories_cmd.py) reads *"The system category
   (@Opening) can be renamed but not deleted."*, but `@Pendiente` is a system category too, so
   refusing to delete it shows a hint that names the wrong category. Name both, or word it without
   a name. Add an error-shape test deleting `@Pendiente`.

## Ergonomics

1. **Shell completions** — zsh, bash, fish. `expense <TAB>` shows commands, `expense auth
   <TAB>` shows subcommands. No design questions open.

2. **Human-name resolution for reference flags.** Accept a UUID or a name on every
   `--account-id` / `--category-id` / `--hashtag-id` / `--reconciliation-id`, via the existing
   list endpoints: case-insensitive exact match, ambiguous matches rejected with a "be more
   specific" error pointing at `expense <resource> list`; UUIDs pass through. Deserves its own
   plan-mode session. Decide deliberately whether it reuses the quick-add matcher
   (contains-anywhere over `load_quickadd_refs`, [quickadd/parse.py](../expense/quickadd/parse.py))
   or keeps a stricter exact match.

3. **"Move between accounts" convenience** — one command writing the two ordinary
   `POST /transactions` a transfer consists of. Purely client-side sugar over two writes, which
   is also the argument against it. **[UI]** — needs a mockup covering naming, flags, and the
   two legs' default titles and categories. See [decisions.md](decisions.md) "Transfers are two
   ordinary transactions".

4. **`expense import csv`** — only if a real migration needs it. Only a reader would be new; the
   write half is shared ([batch_write.py](../expense/batch_write.py)).

## Cosmetic — safe to leave

1. **`PickerModal` carries rows but is still a modal.** A surface carrying rows should be a
   pushed screen (the bulk `c`/`b`/`h` picks). The other modals (`HelpModal`, `PromptModal`,
   `DiscardStagedModal`, `ConfirmModal`) are short questions and stay modals. **[UI]** — the
   replacement needs drawing.

2. **`QuickAddLogScreen` is an edit-only screen with a create-era name.** Rename the class and
   `quick_log.py` (≈6 source + 5 test files, nothing behavioural) — `EditFormScreen` /
   `edit_form.py` is the obvious target. [tui.md](tui.md) links to the module;
   `test_relative_doc_links_resolve` catches a miss.

---

## Parked — no commitment

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
