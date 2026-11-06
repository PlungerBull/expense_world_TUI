# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

Only the orchestrator edits this file; workers put tasks and questions in their reports. Closed
items get deleted, not ticked ([decisions.md](decisions.md) "The open-work list holds only open
work"). Cite items by title. **[UI]** means an HTML mockup in [mockups/](mockups/) must be
picked before any code. Engine asks wait in [to-engine/](to-engine/), one file each, until
handed over.

---

## Waiting on you

Everything that needs the owner: questions, and things only the owner can do. The orchestrator
adds an entry instead of guessing, acts on the answer, then deletes it. A question reads:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

### Approve the rewritten specs
Asked 2026-10-29 · Blocks: every spec in [specs/](specs/)

To approve, every question answered: [the official import](specs/before-the-official-import.md),
[a long account name in the LOG bar peek's count line](specs/a-long-name-in-the-peek-count.md)
and [footers that fit the screen](specs/footers-fit-the-screen.md).

Answered, waiting on its engine ask (for you to hand over) and a mockup of the preview:
[a statement PDF's preview names the lines the close will flag](specs/the-preview-names-the-lines-the-close-will-flag.md).

New, two questions: [a save that answers after you leave its
screen](specs/a-save-that-answers-after-you-leave.md).

Approved: [the test-suite leftovers](specs/test-suite-leftovers.md), ready to run;
[accounts carry their numbers](specs/accounts-carry-their-numbers.md), waiting on the engine.

**Recommended:** approve the rest.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
CLAUDE.md "Specs and tasks".

- **No LOG bar test checks the peek's title and count on a two-currency pick** (`$visa %usd`).
  Nothing you see changes.
- **The shared practice user holds no accounts,** so the tester proves LOG bar and account
  checks with unit tests only. Nothing you see changes. Waits on the engine ask "Give the
  shared practice user an account that every reseed keeps".
- **No live test sends a zero-amount `SALDO INICIAL` row dated before a person's opening
  balance.** Nothing you see changes. It waits on the engine ask "Say whether a zero-amount row
  dated earlier stops a sheet row being the opening balance"; then
  [test_sheet_import.py](../tests/contract/test_sheet_import.py) pins the answer.
- **File names still say reconciliation.** Nothing you see changes. The Statements screens live
  in [reconciliations.py](../expense/tui/screens/reconciliations.py), tested in
  test_tui_reconciliations.py and test_tui_reconcile_detail.py (with the monkeypatch strings
  that name the module); the `recon` abbreviations (`_recons`, `recon=`, the `recon-unfiled` and
  `recon-detail-load` worker groups, `_R_LABELS`, `_RECON_FIELD`) say statement too.
- **[UI] Below 66 columns the "no statement" list cuts the amount.**
- **[UI] The "no statement" `?` card lists keys that don't apply.** It shows `esc Back` twice, `esc
  Close the panel` (off there), and both `pgdn Load the next 10 rows` and `pgdn Next page` once
  every row is loaded; on a 30-row terminal it clips its last line. One row per key that works,
  with a test; the tests pinning today's doubled rows (`CARD_THIS_SCREEN` in
  test_tui_ledger_archived.py, "Moving around" in test_tui_reconciliations.py) change with it.
- **A huge amount reads, then crashes what prints it.** `parse_amount`
  ([quickadd/money.py](../expense/quickadd/money.py)) reads a finite `1e5000`, typed or in either
  importer's file, as an integer of over 4,300 digits, and printing it (the bank preview, a row's
  repr) raises `ValueError`. The live contract states no largest amount, so it waits on the
  engine ask "State the largest amount the engine takes, and refuse past it everywhere".
- **A row's day shows in UTC.** The engine sends times in UTC, and every list shows the first
  ten characters as the day ([formatting.py](../expense/formatting.py) `format_short_date`), so a
  row timed after 19:00 in Lima shows the next day, though the engine counts it on its own day.
  Rows dated by day alone (00:00 in the user's time zone) show right. Waits on the engine ask
  "Send each transaction's calendar day with it"; the lists then show that day.
- **Amounts follow your number format.** The app reads the Mac's region by default, and an
  optional setting on the owner's account wins when set, so every device agrees (an engine
  ask). The format is used both for amounts typed and for every amount shown.
  Under English (Peru), `1,5` is not a number, so it is refused instead of saved as 15.00.
  Needs a spec.
- **Bank files become the intake.** Plan: [file-import-plan.md](file-import-plan.md).
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.
- **One newest-read helper everywhere.** `NewestReadMixin` ([_base.py](../expense/tui/screens/_base.py))
  drops a replaced read's hand-backs; the statement screen's two count-error toasts
  (reconciliations.py `_read_txns`) still show for a replaced read, and
  [_growing.py](../expense/tui/screens/_growing.py) keeps its own `_generation`. Both use the mixin.

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
