# TODO — the workpad

**The hub for open work in this repo, and the one place questions for the owner wait.** A
spec's tasks live in that spec's "Tasks" section; everything else open lives here. Nothing else
tracks pending work — no issue tracker, no `TODO:` comments in code. How the work
runs: CLAUDE.md "How work runs (the agent loop)".

**Current spec:** [specs/error-reasons.md](specs/error-reasons.md). The owner writes specs in
[specs/](specs/) and names the current one here.

- **Only the orchestrator edits this file** (and a spec's "Tasks" section). Workers put tasks
  and questions in their reports.
- **A spec's tasks** are drafted into that spec's "Tasks" section by the orchestrator and
  approved by the owner before the loop runs. The plan docs linked under **Now** are drafts until the owner approves them or
  rewrites them as specs.
- **Closed items get deleted**, not ticked. Git history is the archive
  ([decisions.md](decisions.md) "The open-work list holds only open work").
- Items marked **[UI]** need an HTML mockup in [mockups/](mockups/) reviewed and explicitly
  picked before any code (CLAUDE.md "Mock every screen before building it").
- **Absolute dates only.**
- **Cite items by title, never by number** — numbering shifts every time an item closes.

Sections: **Questions for the owner** · **Now** (the sequenced queue) · **Small defects** ·
**Ergonomics**, **Cosmetic** and **Parked** (none of it blocking). Engine asks are not here:
each is its own file in [engine-asks/](engine-asks/).

---

## Questions for the owner

Everything waiting on the owner. The orchestrator adds an entry instead of guessing; once the
owner answers, it acts on the answer and deletes the entry. Each entry:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

### The engine's contract moved: catch up now, and how?
Asked 2026-09-28 · Blocks: every new task (CLAUDE.md "A moved contract version goes to the owner")
The version check against the practice engine reports saved `9d593f48328c0c6a`, engine
`ef2132c3c3b2ff6f`. What the contract changed, newest first, as the check prints it:
- `ef2132c3c3b2ff6f` (2026-09-28)
  - added: `error.reasons` on every error, same keys as `fields`, each naming the rule broken
    (`RANGE_INVERTED`, `PERIOD_OVERLAPS`, `SEALED_PERIOD`, `LOCKED`, …); switch on `reasons`,
    never on `fields` or message wording. *Error reasons* lists them all.
  - added: `x-error-reasons` on every operation, listing the reasons it can return.
  - changed: sealed periods are identified by the `SEALED_PERIOD` reason; the top-level message
    is no longer a fixed string.
  - changed: `POST /transactions/batch` keys an unknown hashtag on its item,
    `transactions.<index>.hashtag_ids`, reported with the other item failures.
  - changed: a field breaking two rules is named by the first rule checked (batch: a future
    date inside a sealed period is now reported as a future date).
  - changed: `GET /reports/monthly` field messages are full sentences.
  - changed: date and datetime format messages no longer start with `"Value error, "`.
- `b2405c2af20fb7e6` (2026-09-28)
  - changed: wording only; `POST /transactions` states its full validation, including the
    zero-amount `422`. Behaviour is unchanged.

Unit tests (1676) and the live contract suite (49) still pass, and no fixture field drifted, so
nothing is visibly broken; but the CLI matches message wording in places the engine now says to
replace with `reasons` (the reconciliation refusal hints, sealed-period reporting). This lands
both open engine asks, the reconciliation refusal reasons (landed, deleted with the CLI's switch)
and [post-transactions-states-non-zero.md](engine-asks/post-transactions-states-non-zero.md).
- **A.** Catch up as the next spec: switch every message match to `error.reasons`, check the
  batch and monthly-report error handling, cite the new contract parts, delete both asks,
  record the new version. You write the spec (or approve a draft the orchestrator writes).
- **B.** Only the small part now: the comment citation and deleting the non-zero ask, then
  record the version; the `reasons` switch waits as an item in "Now".
- **C.** Not now: the loop stays stopped until you pick A or B.

**Recommended:** A. Recording the version without switching to `reasons` would leave the CLI on
wording the engine no longer promises, the exact thing this spec exists to prevent.

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
Asked 2026-09-27 · Blocks: [file-import-plan.md](file-import-plan.md) §6, and Small defects
"After `--apply`, the bank import's warning…"
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
The draft is in [tui-only-plan.md](tui-only-plan.md) "Draft note to the engine coder".
- **A.** Send it as written, with the new name filled in.
- **B.** Change it. Say how.

**Recommended:** A.

---

## Now

An index; the depth lives in each plan doc, which is deleted when it ships (its why moves to
[decisions.md](decisions.md)).

| # | Item | Plan | Status |
|---|---|---|---|
| **0** | **The engine uptake's TUI checks** | The list below | Owner, through normal use on the real ledger |
| 1 | Tags that know the category | [category-hashtags-plan.md](category-hashtags-plan.md) | Questions for the owner + **[UI]** |
| 2 | The TUI import door (C1) | [file-import-plan.md](file-import-plan.md) §3 | **[UI]**, nothing drawn |
| 3 | The TUI is the only human surface; the flat CLI is for the agent (incl. repo rename + engine-coder note) | [tui-only-plan.md](tui-only-plan.md) | Decided 2026-09-26; questions for the owner open; starts after the in-flight work |
| 4 | One-time title alignment after the official migration | [file-import-plan.md](file-import-plan.md) §6 | Runs after the re-import, before the 2026 periods are completed |
| 5 | The agent loop: orchestrator + builder/tester/reviewer/librarian, one loop per repo | [agent-loop-plan.md](agent-loop-plan.md) | Rules, worker files, guards and pre-approved commands built; §6.5 (the first spec) finished 2026-09-28; rollout step 3 next: adjust, record the setup in decisions.md, delete the plan |

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
completed, because a completed period locks its rows' titles. The engine's rule is absolute:
**import first, reconcile second**. A reconciliation completed before its rows exist seals the
window against them (contract: POST /v1/transactions), and the import then skips those rows as
`sealed`, never creating them (contract: POST /v1/transactions/import). Full sequence:
[file-import-plan.md](file-import-plan.md) §10.

**Before the sheet re-import's `--apply`:** the sheet still files rows under `PENDIENTES`, as a
category and as a hashtag; the ledger has neither (uncategorised rows go to the system category
`@Pendiente`). Rename those rows in the sheet first, or the apply creates `PENDIENTES` again.
Every other account, category and hashtag name resolves (dry run, 2026-09-27).

---

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
   after-apply case beside pick C and let the owner pick. **[UI]** · Tied to the question for
   the owner on hand-logged card purchases: if a rename proposal is built, this
   case mostly stops happening.

3. **The system-category delete hint names only `@Opening`.** `_SYSTEM_HINT` in
   [categories_cmd.py](../expense/commands/categories_cmd.py) reads *"The system category
   (@Opening) can be renamed but not deleted."*, but `@Pendiente` is a system category too, so
   refusing to delete it shows a hint that names the wrong category. Name both, or word it without
   a name. Add an error-shape test deleting `@Pendiente`.

4. **The guard's limits list misses two cases, and one rule has no test.**
   [guard.py](../.claude/hooks/guard.py): a path inside a `python -c` or `awk` program string
   is not checked (same class as the listed `bash -c`), and a bare heredoc body with a `cd`
   line moves the guard's tracked folder, so the rest of the command is blocked. Name both in
   the docstring's limits. [test_claude_hooks.py](../tests/unit/test_claude_hooks.py) has no
   Bash case whose hook `cwd` is the harness scratchpad or `~/.claude`; add one pinning that
   both pass. Builder work.

5. **The contract suite's conftest repeats the ops guide and tells history.**
   [tests/contract/conftest.py](../tests/contract/conftest.py): its module docstring copies the
   seed, start and suite commands that [cli-runtime.md](cli-runtime.md) "Working against the
   live engine" owns (cut it to a pointer), and the comment above `DEFAULT_ENGINE_URL`
   describes an old default (state only what is). Builder work.

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
