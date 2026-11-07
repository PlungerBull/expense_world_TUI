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

New, one question, its mockup drawn: [the `?` card's leftovers](specs/help-card-leftovers.md),
what the small fixes on screen found.

Answered, waiting on its engine ask (for you to hand over) and a mockup of the preview:
[a statement PDF's preview names the lines the close will flag](specs/the-preview-names-the-lines-the-close-will-flag.md).

New engine ask, for you to hand over: "Save an account's changes and its opening balances in one
write, whole or not at all" ([to-engine/](to-engine/)).

Approved: [the test-suite leftovers](specs/test-suite-leftovers.md), ready to run;
[accounts carry their numbers](specs/accounts-carry-their-numbers.md), waiting on the engine.

**Recommended:** approve the rest.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
CLAUDE.md "Specs and tasks".

- **No test draws a marked or refused part row with an income.** In the Edit form's parts table
  both rows print the same cell as the locked row, which a test pins with `+3,200.00`, but
  neither has a test of its own (`parts_lines` in
  [parts_table.py](../expense/tui/widgets/parts_table.py)). Nothing you see changes.
- **The `TRANSACTION_RULE` comment speaks of lists only.** Its comment in
  [theme.py](../expense/tui/theme.py) says the rule covers an amount "in a list"; it also covers
  a transaction named outside one (the question before a delete, a note after you leave) and the
  Edit form's parts count line, a sum, as [tui.md](tui.md) "Amounts" says. Nothing you see changes.
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
  unguarded; `_opening_saved`'s `part` has no type. No test drives the real `esc` (the tests pop the screen), none covers an
  account save whose only write is the account, and the new-statement test calls `_created` by
  hand instead of driving the late answer. The comment on the balances save's `LeftBehind` in
  [statements.py](../expense/tui/screens/statements.py) names `_write_finished_after_leaving`
  where the words come from `_say_after_leaving`. Nothing you see changes.
- **New statement's refusal after leaving is untested under a 5xx or no answer.** It is a bar
  form and follows `open_it_again` ([_form.py](../expense/tui/screens/_form.py)), but no test
  drives it. Nothing you see changes.
- **The quit-question tests need tidying.**
  [test_tui_quit_asks.py](../tests/unit/test_tui_quit_asks.py): the LOG bar `y` test records
  whether the bar is still in the stack but never asserts it; the `bar_empty` helper sits
  between tests; two preview screens are imported inside test bodies; the import hand-back test
  reads `seen_app` before assigning it; no test covers a second `ctrl+q` quitting at once once
  every save ended while the question was up. A docstring in
  [test_tui_left_behind_account_form.py](../tests/unit/test_tui_left_behind_account_form.py)
  (~line 110) wraps mid-phrase. Nothing you see changes.
- **A screen gone before its save's thread starts would raise instead of reporting.** The LOG
  bar, bank import and statement upload workers read `self.app` for `counted_save`
  ([_base.py](../expense/tui/screens/_base.py)) before their `try`; it cannot happen today,
  since `esc` is refused while they save. Nothing you see changes.
- **Setup's `esc Quit` leaves through `app.exit()`, not the shared quit.** It is refused while
  setup saves, so no save is lost; it is the one quit not going through `action_quit`
  ([app.py](../expense/tui/app.py)). Nothing you see changes.
- **`test_coming_back_from_a_statement_keeps_the_panel_on_the_same_row` waits weakly**
  ([test_tui_statements.py](../tests/unit/test_tui_statements.py) ~line 567): it waits for
  `_statement_list is not None`, which the old list already passes, so it can pass without
  proving the cursor after the read, or fail at random under the parallel run. It should wait
  for the read's cursor on `b2`. Nothing you see changes.
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
- **The "no statement" list under 68 columns.** The Statements screen's list of lines in no
  statement cuts its amount, then its currency, under 68 columns, and under 62 its caption wraps a
  lone `·` onto a line of its own. Parked 2026-11-07: the app is built for 80 columns.
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer dashboards.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **An MCP server for agents.** The way for an agent to read or write the ledger on the owner's
  behalf, talking to the engine as every client does. It belongs beside the engine, not in this
  repo, and is a piece of work of its own.
