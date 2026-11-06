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

To approve, every question answered: [the official import](specs/before-the-official-import.md).

New, two questions: [the LOG bar at 80 columns](specs/the-log-bar-at-80-columns.md).

New, one question, its mockup still to draw: [the `?` card at 24
rows](specs/the-keys-card-at-24-rows.md).

Answered, waiting on its engine ask (for you to hand over) and a mockup of the preview:
[a statement PDF's preview names the lines the close will flag](specs/the-preview-names-the-lines-the-close-will-flag.md).

New, two questions: [a save whose ending is not known](specs/a-save-whose-ending-is-not-known.md).

New, one question: [a split's parts show an income's `+`](specs/a-splits-parts-show-an-incomes-plus.md).

New engine ask, for you to hand over: "Save an account's changes and its opening balances in one
write, whole or not at all" ([to-engine/](to-engine/)).

Approved: [the test-suite leftovers](specs/test-suite-leftovers.md), ready to run;
[accounts carry their numbers](specs/accounts-carry-their-numbers.md), waiting on the engine.

**Recommended:** approve the rest.

### What gives way on a narrow "no statement" list
Asked 2026-11-05 · Blocks: "[UI] Below 66 columns the "no statement" list cuts the amount"

On a terminal under 68 columns, the Statements screen's list of lines in no statement cuts
the amount, then the currency. Pick in [the mockup](mockups/expense-world-no-statement-narrow.html):
- **A.** The operation number goes; the title keeps its room.
- **B.** The title shrinks further; every column stays.
- **C.** The title shrinks to 16 letters, then the operation number goes.
**Recommended:** C, because the amount and currency always show whole and every column stays
down to 60 columns.

### Which keys the "no statement" `?` card lists
Asked 2026-11-05 · Blocks: "[UI] The "no statement" `?` card lists keys that don't apply"

Pick in [the mockup](mockups/expense-world-no-statement-keys.html):
- **A.** Only the keys that work there.
- **B.** Every key of that list, the ones off right now dimmed.
**Recommended:** A, because every row does what it says, and the card fits a 24-row terminal.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
CLAUDE.md "Specs and tasks".

- **The `TRANSACTION_RULE` comment speaks of lists only.** Its comment in
  [theme.py](../expense/tui/theme.py) says the rule covers an amount "in a list"; it also covers
  a transaction named outside one (the question before a delete, a note after you leave), as
  [tui.md](tui.md) "Amounts" says. Nothing you see changes.
- **The footer guard has gaps.** `test_no_screen_draws_textuals_own_footer`
  ([test_tui_fitting_footer.py](../tests/unit/test_tui_fitting_footer.py)) misses attribute
  access (`widgets.Footer()`), skips any file named `footer.py` rather than that one path, and
  its module docstring speaks of list screens only; `FittingFooter`'s docstring
  ([footer.py](../expense/tui/widgets/footer.py)) says `?` lists a left-out key without "on a
  screen that has one". Nothing you see changes.
- **`(unnamed)` for a blank name is written out four times** (`not_done_line` in
  [_base.py](../expense/tui/screens/_base.py) and the account, category and hashtag lists);
  `title_or_untitled` is the one shared copy for titles, and names have none. Nothing you see
  changes.
- **The after-leaving code has small gaps.** `_landed_after_leaving` in
  [create_forms.py](../expense/tui/screens/create_forms.py) reads `left_behind.part.report`
  unguarded; `ReportedPart.record` writes `SaveReport`'s private `_answers`; `_opening_saved`'s
  `part` has no type. No test drives the real `esc` (the tests pop the screen), none covers an
  account save whose only write is the account, and the new-statement test calls `_created` by
  hand instead of driving the late answer. The comment on the balances save's `LeftBehind` in
  [statements.py](../expense/tui/screens/statements.py) names `_write_finished_after_leaving`
  where the words come from `_say_after_leaving`. Nothing you see changes.
- **No LOG bar test checks the peek's title and count on a two-currency pick** (`$visa %usd`).
  Nothing you see changes.
- **Two comments in [log_bar.py](../expense/tui/screens/log_bar.py) describe the peek's old
  border:** the `CHROME_LINES` comment and `AccountPeek._heading`'s docstring. Nothing you
  see changes.
- **The shared practice user holds no accounts,** so the tester proves LOG bar and account
  checks with unit tests only. Nothing you see changes. Waits on the engine ask "Give the
  shared practice user an account that every reseed keeps".
- **No live test sends a zero-amount `SALDO INICIAL` row dated before a person's opening
  balance.** Nothing you see changes. It waits on the engine ask "Say whether a zero-amount row
  dated earlier stops a sheet row being the opening balance"; then
  [test_sheet_import.py](../tests/contract/test_sheet_import.py) pins the answer.
- **[UI] Below 66 columns the "no statement" list cuts the amount.** Waits on "What gives way on a
  narrow "no statement" list" above.
- **[UI] Below 62 columns the "no statement" caption wraps a lone `·`.** Its last separator moves
  to a line of its own (`In no statement · BCP · 4 of 4 loaded · oldest first ·`).
- **[UI] The "no statement" `?` card lists keys that don't apply.** Waits on "Which keys the "no
  statement" `?` card lists" above. It shows `esc Back` twice, `esc
  Close the panel` (off there), and both `pgdn Load the next 10 rows` and `pgdn Next page` once
  every row is loaded; on a 30-row terminal it clips its last line. One row per key that works,
  with a test; the tests pinning today's doubled rows (`CARD_THIS_SCREEN` in
  test_tui_ledger_archived.py, "Moving around" in test_tui_statements.py) change with it.
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
