# A save whose ending is not known

What [a save that answers after you leave](../decisions.md) (done on 2026-11-06) turned up: two
cases where the app says something untrue, or nothing, about a save that may have landed.

**Status: drafted on 2026-11-06; questions answered and its mockup,
[expense-world-save-ending-unknown.html](../mockups/expense-world-save-ending-unknown.html),
approved on 2026-11-06; the current spec.** It waits on
no other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

- **A save that failed without a clear answer.** When the engine fails with a server error, or
  does not answer at all, a save may still have landed. The ledger's Edit forms then leave out
  their "open it again" line. The Manage forms (categories, hashtags, a new account) and the
  account Edit form, once you have left them, still end with `Nothing was saved: open it again to
  fix it.` or `Open the account's Edit form to set PEN again.`, which may be untrue.
- **Quitting with saves still waiting.** If you quit the app (`ctrl+q`) while saves are still
  waiting to be sent, they are dropped, and nothing says so.

## What it must do

1. **A save whose ending is not known never says it was not saved**, as question 1 picks.
2. **Quitting never drops a waiting save without saying so**, as question 2 picks.

## How the owner knows it is done

1. A Manage form or the account Edit form, left while it saves and answered by a server error:
   the message says what question 1 picks.
2. `ctrl+q` with a save still waiting: what happens is what question 2 picks.
3. The unit suite passes.

## Questions for the owner

1. **A save that failed with a server error or no answer, after you left its form?**
   - **A.** Leave out the "open it again" line, as the ledger's Edit forms do: the engine's
     words alone.
   - **B.** Say it plainly: `It may have saved: open it to check.`
   **Recommended:** A: it matches the Edit forms, and it adds no new sentence.
   **Picked:** A.
2. **`ctrl+q` while saves still wait to be sent?**
   - **A.** As today: the app quits and they are dropped.
   - **B.** The app asks first: `2 saves are still being sent. Quit anyway?`, only `y` quits.
   - **C.** The app waits for them, then quits.
   **Recommended:** B: you learn something is still going and choose.
   **Picked:** B.

Each picked message is drawn as a mockup in [mockups/](../mockups/) before it is built.

---

## Tasks

5. **`test_a_statement_created_after_leaving_opens_its_accounts_panel` is flaky under the
   parallel run** ([test_tui_statements.py](../../tests/unit/test_tui_statements.py) ~line 628):
   2 of 3 full runs on 2026-11-06 read the cursor on `r2` instead of `new-1`; alone it passes.
   It waits for what the create's read brings, so it passes every time.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **New statement's refusal after leaving is untested under a 5xx or no answer.** It is a bar
  form, so it follows the same rule, but no test drives it, and tui.md's "A statement's
  writes" bullet does not say it ends with the dim line. Nothing you see changes.
- **Manage ▸ Accounts does not read again when every write of the account save ended with no
  clear answer.** `_landed_after_leaving` in
  [create_forms.py](../../expense/tui/screens/create_forms.py) reads it again only when a part was
  answered saved (`SaveReport.landed`), so a save that may have landed leaves the list as it
  was until `r`.
- **The quit-question tests and one docstring need tidying.**
  [test_tui_quit_asks.py](../../tests/unit/test_tui_quit_asks.py): the LOG bar `y` test records
  whether the bar is still in the stack but never asserts it; the `bar_empty` helper sits
  between tests; two preview screens are imported inside test bodies; the import hand-back test
  reads `seen_app` before assigning it. A docstring in
  [test_tui_left_behind_account_form.py](../../tests/unit/test_tui_left_behind_account_form.py)
  (~line 110) wraps mid-phrase. No test covers a second `ctrl+q` quitting at once once every
  save ended while the question was up. Nothing you see changes.
- **A screen gone before its save's thread starts would raise instead of reporting.** The LOG
  bar, bank import and statement upload workers read `self.app` for their count before their
  `try`; it cannot happen today, since `esc` is refused while they save. Nothing you see
  changes.
- **Setup's `esc Quit` leaves through `app.exit()`, not the quit question.** It is refused while
  setup saves, so no save is lost; it is the one quit not going through the shared one.
  Nothing you see changes.
