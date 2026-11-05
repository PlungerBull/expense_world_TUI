# A save that answers after you leave its screen

The Backlog run of 2026-11-05 found this while it moved the app's background work onto one
shared hand-back: you can leave a screen (`esc`) while its save is still on its way to the
engine, and when the engine answers, the app says nothing.

**Status: drafted on 2026-11-05; questions 1 and 2 for the owner.** It waits on no other spec.
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

## Questions for the owner

1. **You leave a screen before its save answers. What does the app show when it answers?**
   - **A.** Nothing, as today.
   - **B.** The message the screen would have shown: "Saved.", "Account created.", or the
     engine's refusal in full; for a bulk edit, the receipt and each refused row.
   - **C.** One short message for every save, such as "Saved." or "Not saved".
   **Recommended:** B. A refusal you never see is a change you think happened.
2. **The account form, left while it saves its opening balances?**
   - **A.** `esc` waits: you cannot leave until the whole save is done.
   - **B.** You leave, the opening balances still go, and you are told how each ended.
   - **C.** You leave, the opening balances not yet sent are dropped, and a message names them.
   **Recommended:** B. Nothing you typed is lost, and you are not held on the form.

Each picked message is drawn as a mockup in [mockups/](../mockups/) before it is built.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
