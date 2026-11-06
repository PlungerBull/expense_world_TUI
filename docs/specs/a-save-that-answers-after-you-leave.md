# A save that answers after you leave its screen

The Backlog run of 2026-11-05 found this while it moved the app's background work onto one
shared hand-back: you can leave a screen (`esc`) while its save is still on its way to the
engine, and when the engine answers, the app says nothing.

**Status: questions 1 and 2 answered on 2026-11-06; questions 3 to 7, on the mockup of the
picked messages, wait for the owner.** It waits on no other spec.
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

A save, a delete, a bulk edit or a statement action runs in the background. If you press `esc`
before the engine answers, the screen closes. When the engine answers, the app drops the answer:

- If the save landed, you see no "Saved." and no "Account created.". It did save.
- If the engine refused it, you never see the refusal. The change did not happen, and nothing
  says so.
- A bulk edit you leave mid-run does not say which rows changed and which were refused.
- The account form saves the account first and then each opening balance. Leave it after the
  account saves and the opening balances after it are never sent, and nothing says so.

## What it must do

1. **A save you left still tells you how it ended**, as question 1 picks.
2. **The account form never loses an opening balance without saying so**, as question 2 picks.

## How the owner knows it is done

1. Leave a form while it saves: the app tells you how the save ended, as question 1 picks, both
   when it lands and when the engine refuses it.
2. Leave the account form while it saves an opening balance: what happens is what question 2
   picks.
3. The unit suite passes.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | You leave a screen before its save answers. What does the app show when it answers? | The message the screen would have shown: "Saved.", "Account created.", or the engine's refusal in full; for a bulk edit, the receipt and each refused row (2026-11-06). |
| 2 | The account form, left while it saves its opening balances? | You leave, the opening balances still go, and you are told how each ended (2026-11-06). |

## Questions for the owner

The picked messages are drawn in
[expense-world-save-after-leaving.html](../mockups/expense-world-save-after-leaving.html); each
question below is an A or B there.

3. **Pane 2: the first line of a refused save you left.** A: `Failed`, as today. B: what was not
   saved, `Not saved · Wong · -45.90`. **Recommended:** B, since you may have left two saves.
4. **Pane 3: a bulk edit's refused rows, once you have left the ledger.** A: by number,
   `rows 1, 3`. B: by date, title and amount. **Recommended:** B: the numbers point at a list
   you are no longer on.
5. **Pane 4: after you leave, does one refused opening balance stop the ones after it?** A: yes,
   and the message names those not sent. B: no, each still goes and the message says how each
   ended; the same for ticks on a statement still waiting to be sent. **Recommended:** B: only
   what the engine refused is left to redo.
6. **Pane 5: a statement completed after you left, with lines flagged.** A: the flagged lines
   open by themselves over wherever you are. B: a message with the engine's notes and where the
   flagged lines are. **Recommended:** B: no screen opens by itself.
7. **Pane 6: `c` saved a statement's balances after you left, so "Complete statement?" was never
   asked.** A: nothing. B: `Balances saved`, and that the statement is not completed.
   **Recommended:** B: you never think a statement is completed when it is not.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
