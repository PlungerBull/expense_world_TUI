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

**Nothing here is a regression and nothing blocks daily use.** The flat CLI and the
TUI are both feature-complete against the engine; **1250 unit tests green
(2026-09-19)**, contract suite **24/24** against the disposable engine (2026-09-19 — the
first run since 2026-08-25, and the first ever for the reconciliation, reports and
dashboard modules added the same day).

**Since 2026-09-20 the file has two halves.** *Now* is the sequenced queue: four
items the engine's 2026-09-20 changes put in front of this repo, in dependency
order, tackled one at a time. Everything under it is the standing kind-grouped
list — one genuine defect (the macOS field keys, under **Bugs**), the rest
ergonomics and one cosmetic follow-up. **There are no open engine-side asks:**
both closed on 2026-09-13 and 2026-09-20 respectively.

**The Inbox was deleted 2026-09-12** — engine (`sql/038`) and CLI in one day: a ledger row
needs an account, an amount and a date; a missing category files it under `@Pendiente`,
which counts everywhere; the LOG bar refuses a line it cannot stage instead of parking it;
and — since the same evening — Home is the month itself (four months since 2026-09-13, with Overview folded in and deleted), with `⏎` on `@Pendiente` opening
the ledger filtered to it and `space` + `c`/`b`/`h` editing rows in bulk (the `p` filter
and the stats line lasted the day; [decisions.md](decisions.md) "Home is the month"). The why, with the
rejected alternatives, is in [decisions.md](decisions.md) "The Inbox is deleted"; the
screens in [mockups/expense-world-pendiente-not-inbox.html](mockups/expense-world-pendiente-not-inbox.html)
(pane 6 option A). Per the first rule above, the item is gone — git history is the archive.

**The quick-add bar closed 2026-08-25** — all four phases: the grammar
([expense/quickadd/](../expense/quickadd/)), `expense log "<line>"`, the TUI LOG bar
([log_bar.py](../expense/tui/screens/log_bar.py)) and its save, with `+` now opening
it. Its why lives in [decisions.md](decisions.md) (four entries) and its design in
[mockups/expense-world-quickadd-batch.html](mockups/expense-world-quickadd-batch.html);
per the first rule above, the item itself is gone — git history is the archive.

---

## Now — four asks, in order (set 2026-09-20)

Three things landed in the engine on 2026-09-20: `GET /categories/{id}/hashtags`,
sealed periods (its E1–E4), and the engine half of the file-import plan. What they
need from this repo is **four asks, each with its own plan document** — so one can
be picked up, reviewed in depth and built without the other three in context.

**This section is an index. The depth lives in the plan docs**, per the "each fact
has one home" rule; nothing below is restated there and nothing there is restated
here. Each doc carries its own decisions-to-review section, and is **deleted when
its ask ships**, with the whys moving to [decisions.md](decisions.md).

| # | Ask | Plan | Gate |
|---|---|---|---|
| 1 | Sealed periods reach the user | [sealed-periods-plan.md](sealed-periods-plan.md) | settled 2026-09-20 — **building** |
| 2 | The import rules that need no screen (C2–C5) | [file-import-plan.md](file-import-plan.md) §4–§7 | accepted 2026-09-19 |
| 3 | Tags that know the category | [category-hashtags-plan.md](category-hashtags-plan.md) | 4 decisions + **[UI]** |
| 4 | The TUI import door (C1) | [file-import-plan.md](file-import-plan.md) §3 | **[UI]**, nothing drawn |

**Why this order.** Ask 1 is first because it blocks the owner's next real task —
≈24 reconciliations created and closed by hand for 2026, every one able to hit a
refusal this repo currently renders as a bare validation error. Ask 2 is what the
first real bank import rests on. Ask 3 is independent of both and could move
earlier if wanted. Ask 4 is the largest and the only one with nothing drawn.

One rule from the engine side is **absolute**
([engine plan §9](../../expense_world_engine/docs/file-import-plan.md)):
**import first, reconcile second.** A reconciliation created before its rows
exist seals the window against them, and the import is then refused.

```
ask 1 ──▶ owner: update the sheet, re-import, create + close the 2026 periods
             │
ask 2 ───────┴──▶ ask 3 ──▶ ask 4 ──▶ first real bank import
```

---

## Bugs

1. **Field navigation in the edit form is broken on macOS.** `⌃↑` is Mission Control
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

3. **Shell completions** — zsh, bash, fish. `expense <TAB>` shows commands,
   `expense auth <TAB>` shows subcommands. Lowest-effort discoverability win for the
   flat path; no design questions open.

4. **Human-name resolution for reference flags.** Accept either a UUID or a
   human-readable name on every `--account-id` / `--category-id` / `--hashtag-id` /
   `--reconciliation-id`. Client-side lookup via the existing list endpoints:
   case-insensitive exact match, ambiguous matches rejected with a "be more specific"
   error pointing at `expense <resource> list`; UUIDs pass through unchanged.
   Significant feature — **deserves its own plan-mode session.** Note the quick-add
   grammar already solved the same problem its own way (contains-anywhere matching over
   `load_quickadd_refs`, [quickadd/parse.py](../expense/quickadd/parse.py)); decide
   deliberately whether the flag path reuses that matcher or keeps its stricter
   exact-match rule, rather than ending up with two by accident.

5. **"Move between accounts" convenience** — one command writing the two ordinary
   `POST /transactions` calls a transfer now consists of (out one account, in the
   other). The engine has had no transfer concept since 2026-08-10, so this is purely
   client-side sugar over two writes — which is also the argument *against* it, since
   the CLI's job is to exercise the engine's surface, not invent one. Explicitly **not**
   parity work. **[UI]** — needs a mockup covering naming, flags, and what the two
   legs' titles and categories default to. See [decisions.md](decisions.md) "Transfers
   are two ordinary transactions".

6. **`expense import csv`** — CSV variant of the shipped `.xlsx` importer. **Conditional:
   only if a real migration needs it**; the xlsx path already covered the original one.
   Cheaper now than when it was written down — the write half is shared
   ([batch_write.py](../expense/batch_write.py)), so only a reader would be new.

## Cosmetic — safe to leave

7. **`QuickAddLogScreen` is an edit-only screen with a create-era name.** Its create
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

