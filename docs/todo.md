# TODO — the workpad

**The single open-work queue for this repo.** Nothing else tracks pending work — no
issue tracker, no scattered `TODO:` comments in code (there are none, and that is
deliberate: a comment nobody greps is not a queue).

Rules, unchanged from the backlog this file replaces
([decisions.md](decisions.md) "The open-work list holds only open work"):

- **Closed items get deleted**, not ticked and archived. Git history is the archive.
- Items marked **[UI]** change something the user sees and need an HTML mockup in
  [mockups/](mockups/) reviewed and explicitly picked before any code (CLAUDE.md
  "Mock every screen before building it" — showing is not approval).
- **Absolute dates only.** Never "recently".
- **Cite items by title, never by number.** Numbering is presentation — it shifts every
  time an item closes, and it has shifted twice already. Code and docs that point here
  quote the item's bolded title instead, so a renumber can never make them lie.

**The CLI is behind the engine's current code (2026-09-23).** Catching up is the first item
under *Now*, and it blocks everything else. Last green baseline before it: **1250 unit tests
(2026-09-19)**, contract suite **24/24** against the disposable engine (2026-09-19).

**The file has four working sections,** in this order:

- **Now**: the sequenced queue, one plan document per item.
- **Engine asks**: what this repo needs from the engine and has not got.
- **Small defects**: real bugs found along the way, each small and self-contained. They are
  kept apart from *Now* so they don't get lost in a large plan or hold one up.
- **Ergonomics**, **Cosmetic** and **Parked**: the standing list, none of it blocking.

---

## Now (re-sequenced 2026-09-23)

**This section is an index. The depth lives in the plan docs**, per the "each fact has one
home" rule. Each plan carries its own decisions and is **deleted when it ships**, with the
whys moving to [decisions.md](decisions.md).

| # | Item | Plan | Status |
|---|---|---|---|
| **0** | **Engine uptake: everything the engine changed on 2026-09-23** | [engine-uptake-plan.md](engine-uptake-plan.md) | In progress since 2026-09-23 |
| 1 | Sealed periods reach the user | [sealed-periods-plan.md](sealed-periods-plan.md) | Built 2026-09-21/22; closes with the engine uptake's contract run |
| 2 | The import rules that need no screen (C2–C5) | [file-import-plan.md](file-import-plan.md) §4–§7 | Accepted 2026-09-19 |
| 3 | Tags that know the category | [category-hashtags-plan.md](category-hashtags-plan.md) | 4 decisions + **[UI]** |
| 4 | The TUI import door (C1) | [file-import-plan.md](file-import-plan.md) §3 | **[UI]**, nothing drawn |

**Why this order.** The engine uptake comes first because nothing else can be tested against
the engine until it lands, and it closes sealed periods on the way. The import rules are what
the first real bank import rests on. Tags that know the category is independent of them and
could move earlier. The import door is the largest and the only one with nothing drawn.

One rule from the engine side is **absolute**
([engine plan §9](../../expense_world_engine/docs/file-import-plan.md)):
**import first, reconcile second.** A reconciliation created before its rows exist seals the
window against them, and the import is then refused.

```
engine uptake ──▶ restart ──▶ owner: update the sheet, re-import, create + close the 2026 periods
                                │
import rules ───────────────────┴──▶ category tags ──▶ import door ──▶ first real bank import
```

---

## Engine asks

**Raising these is encouraged, not a last resort** (CLAUDE.md "Ask the engine to change").
Each entry says what to ask for, why no client can do it properly today, and **what this repo
deletes when it lands**. Never edited here: they are handed to the owner for the engine coder.

1. **Date filters on `GET /transactions` in calendar days.** `date_from` / `date_to` compare
   exact instants, and a bare date is read as midnight UTC. A row dated the 31st in Lima is stored
   at 05:00 UTC, so `date_to=…-31` drops it (see the defect "The reconciliation checklist never offers
   rows dated on the period's last day"). The engine already
   logs this as `date-filter-not-calendar-days` and `transaction-date-filter-naive`, to be fixed
   together. **The ask is to schedule it**, and to accept a bare date as a whole calendar day in
   the user's `display_timezone`, not to refuse it: every client otherwise re-derives
   "next day's midnight in the user's zone". **Deletes here:** the client-side bare-date →
   instant conversion on the flat `--from`/`--to` of `transactions list` and `activity list`
   (added by the engine uptake).

Answered on 2026-09-23: `?sort=date_asc` with cursor paging, and the gap fields with the wording
fix, both shipped. A window flag on transaction reads and `?status=` on `GET /reconciliations`
were declined (engine `open-bugs.md` D13, D14).

## Small defects

Real bugs, each small and self-contained. None of them waits on the engine uptake unless it says so.

1. **The reconciliation checklist never offers rows dated on the period's last day.** Found
   2026-09-23. The draft working screen lists the account's unassigned rows "in range" with
   `date_to=<date_end>` taken straight from the reconciliation
   ([reconciliations.py](../expense/tui/screens/reconciliations.py), the `available` read). The
   engine reads that bare date as midnight UTC at the **start** of `date_end`, 19:00 the evening
   before in Lima, so every row dated on the last day (stored 05:00 UTC) is left out. On a
   month-end statement that is the 31st's rows, which then block the close as "unassigned" with
   no way to tick them from this screen. **The complete fix is the engine ask on calendar-day date filters.** Until then the
   `u` pane still reaches those rows. Pin with a test either way.

2. **`expense transactions list --to <date>` excludes that date.** Same cause, flat side: the
   help text says "(inclusive)", and the docstring's own example
   (`--to 2026-08-31 --unreconciled`) misses the 31st. Fixed on the client side by the engine
   uptake, or by the same engine ask, whichever lands first.

3. **The fixture-drift check cannot see stale envelope keys.**
   [check_fixture_drift.py](../scripts/check_fixture_drift.py) checks each fixture key against
   every engine schema at once, so a transaction fixture still carrying `total` or `offset`
   passes, because those keys are real on other endpoints. Found 2026-09-23. After the engine uptake no
   endpoint serves `total` or `offset` at all, so the first run after the restart will catch them.
   The general fix (mapping each fixture to the endpoint it mocks) is the script's own documented
   limitation. Low priority.

4. **Field navigation in the edit form is broken on macOS.** `⌃↑` is Mission Control
   and `⌃↓` is Application Windows — the OS claims both before the terminal sees them,
   so `^↑ Prev field` / `^↓ Next field` have very likely never worked. Raised by the
   user 2026-08-20 ("normal arrows up and down should switch between fields"), then
   deferred with the rest of the form work. **The footer stopped advertising them
   2026-08-24** (with the plain `↑ ↓` rows, which the 2026-08-20 trim had missed) — the
   keys stay bound in [_form.py](../expense/tui/screens/_form.py), so what is left here
   is only choosing the replacement.
   `shift+↑` / `shift+↓` **are** bindable and were probed live (arrows are not
   printable, so the terminal sends a distinct `CSI 1;2A`). The open question is what
   plain `↑↓` should then do on the three fields that have a suggestion list —
   options **J** and **K** are drawn in
   [mockups/expense-world-plus-and-arrows.html](mockups/expense-world-plus-and-arrows.html)
   §4, neither picked. **[UI]** · *smallest item here; one answer unblocks it.*

   **A third candidate the mockup does not draw: `tab` / `shift+tab` (found 2026-08-27,
   during the movement-key sweep).** It is the only option that costs nothing —
   plain `↑↓` keep their single meaning (the suggestion list) and nothing is
   sacrificed, which is what J-vs-K was a choice *between*. Verified that day: every
   form has exactly one focusable widget (`Input#bar`), so Textual's screen-level
   `tab` → `app.focus_next` is a **no-op on every form today**; the key is free.
   `tab` is also already the de-facto region key elsewhere — Outstanding is the one
   screen with two focusable regions and `tab` moves between them, undesigned. Fits
   the rule set 2026-08-27 in [decisions.md](decisions.md) "One key per job".
   **One wrinkle to decide with it:** forms have no `?` card (a focused `Input`
   swallows printable keys), so a form key has no discovery surface — this may be the
   one case where an arrow-family key earns a footer slot (`⇥ Field` beside
   `esc Cancel  ^s Save`), against the standing "arrows never get a slot" rule from
   [tui.md](tui.md) §4.

## Ergonomics

1. **Shell completions** — zsh, bash, fish. `expense <TAB>` shows commands,
   `expense auth <TAB>` shows subcommands. Lowest-effort discoverability win for the
   flat path; no design questions open.

2. **Human-name resolution for reference flags.** Accept either a UUID or a
   human-readable name on every `--account-id` / `--category-id` / `--hashtag-id` /
   `--reconciliation-id`. Client-side lookup via the existing list endpoints:
   case-insensitive exact match, ambiguous matches rejected with a "be more specific"
   error pointing at `expense <resource> list`; UUIDs pass through unchanged.
   Significant feature — **deserves its own plan-mode session.** Note the quick-add
   grammar already solved the same problem its own way (contains-anywhere matching over
   `load_quickadd_refs`, [quickadd/parse.py](../expense/quickadd/parse.py)); decide
   deliberately whether the flag path reuses that matcher or keeps its stricter
   exact-match rule, rather than ending up with two by accident.

3. **"Move between accounts" convenience** — one command writing the two ordinary
   `POST /transactions` calls a transfer now consists of (out one account, in the
   other). The engine has had no transfer concept since 2026-08-10, so this is purely
   client-side sugar over two writes — which is also the argument *against* it, since
   the CLI's job is to exercise the engine's surface, not invent one. Explicitly **not**
   parity work. **[UI]** — needs a mockup covering naming, flags, and what the two
   legs' titles and categories default to. See [decisions.md](decisions.md) "Transfers
   are two ordinary transactions".

4. **`expense import csv`** — CSV variant of the shipped `.xlsx` importer. **Conditional:
   only if a real migration needs it**; the xlsx path already covered the original one.
   Cheaper now than when it was written down — the write half is shared
   ([batch_write.py](../expense/batch_write.py)), so only a reader would be new.

## Cosmetic — safe to leave

1. **Four modals are still modals** — `PickerModal` (the bulk `c`/`b`/`h` picks),
   `HelpModal` (`?`), `PromptModal` (the engine-URL edit) and `DiscardStagedModal`
   (the LOG bar's unsaved-rows guard). **The box itself is already gone** (`1c3b2de`,
   2026-09-20: `#modal` draws `border-top`/`border-bottom` only, so every modal that
   shares it lost its vertical edges — this item said "still draw a box" until
   2026-09-22, which was false). What is left is the other half of the rule: a surface
   carrying **rows** should be a pushed screen. `PickerModal` is the only one that
   does — the other three are short questions, which is what a modal is for.
   **[UI]** — `PickerModal`'s replacement needs drawing. `ConfirmModal` is settled:
   it stays a modal (a question), unboxed, and gained a second caller on 2026-09-22
   (the unfiled pane's `d`).


2. **`QuickAddLogScreen` is an edit-only screen with a create-era name.** Its create
   mode was retired 2026-08-25 when `+` moved to the LOG bar
   ([mockups/expense-world-two-doors.html](mockups/expense-world-two-doors.html)); the
   class, and the module `quick_log.py`, still carry the name of the door that closed.
   A rename is mechanical (≈6 source + 5 test files) and touches nothing behavioural,
   which is exactly why it was **not** folded into the phase-4 commit — it would have
   buried a real diff under noise. `EditFormScreen` / `edit_form.py` is the obvious
   target. If the module is renamed, [tui.md](tui.md) links to it and
   `test_relative_doc_links_resolve` will catch a miss.

---

## Parked — no commitment

- **The quick-add launcher hotkey.** A global chord that opens the LOG bar from outside
  the TUI ([mockups/quick-add-launcher-options.html](mockups/quick-add-launcher-options.html),
  which also records the ⌘E conflict). Deliberately left open when the quick-add item
  closed 2026-08-25 — the bar is reachable by `+` and the flat `expense log "<line>"`,
  so this is convenience, not access.
- **The quick-add "recents" row** — numbered last-N templates, option E of
  [mockups/expense-world-log-revamp.html](mockups/expense-world-log-revamp.html).
  **Declined 2026-08-25**, kept here only so it is not re-proposed as new.
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer
  dashboards. Deliberately deferred as scope creep during the build; still deferred.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **Flat-CLI color conventions.** Rich-based output styling beyond what ships (color
  swatches, `NO_COLOR` honoured via `color_supported()`). No demand established.
- **`auth pat create` / `auth pat revoke`.** PATs are issued out-of-band; a future web
  dashboard is expected to issue them. See [cli-spec.md](cli-spec.md) "Auth model".

