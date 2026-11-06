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

1. **The bar forms' "open it again" line only under a clear refusal.** A Manage New or Edit form
   (categories, hashtags) or New account, left while it saves, ends its refusal with
   `Nothing was saved: open it again to fix it.` only when the engine refused with a status
   under 500; under a 5xx or no answer, the engine's words alone, as the ledger's Edit forms do
   (mockup pane 1).
2. **The account Edit form names only what was clearly refused.** Its save's last line
   (`Open the account's Edit form to set … again.`) names only the parts refused with a status
   under 500, and is left out when none was (mockup pane 2).
3. **Quitting asks while saves are still being sent.** `ctrl+q`, and `q` on Home, with any write
   sent and not answered or waiting its turn, on any screen: `N saves are still being sent. Quit
   anyway?` (`1 save is still being sent. …`), then `If you quit now, no screen will tell you
   whether they were saved.` (`… whether it was saved.`); only `y` quits; with none, it quits
   at once (mockup pane 3).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
- **`test_a_statement_created_after_leaving_opens_its_accounts_panel` is flaky under the
  parallel run** ([test_tui_statements.py](../../tests/unit/test_tui_statements.py)): once on
  2026-11-06 it read the cursor on `r2` instead of `new-1`, as if it waits for a list, not the
  list read after the create; alone it passes every time. Nothing you see changes.
