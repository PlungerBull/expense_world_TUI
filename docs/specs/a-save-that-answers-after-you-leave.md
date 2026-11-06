# A save that answers after you leave its screen

The Backlog run of 2026-11-05 found this while it moved the app's background work onto one
shared hand-back: you can leave a screen (`esc`) while its save is still on its way to the
engine, and when the engine answers, the app says nothing.

**Status: every question answered and the mockup picked on 2026-11-06; the tasks wait for the
owner's approval.** It waits on no other spec.
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
| 3 | The mockup, [expense-world-save-after-leaving.html](../mockups/expense-world-save-after-leaving.html) | 2B a refused save's message is titled with what was not saved (`Not saved · Wong · -45.90`), stays 10 seconds and ends `Nothing was saved: open it again to fix it.` · 3B a bulk edit's refused rows are named by date, title and amount, the first four and `and N more` · 4B after you leave, each write still waiting still goes, a refused one stopping none after it, and the message says how each ended (`Not all saved · Account BCP 5678`); the same for a statement's ticks · 5B a statement completed after you left says `Statement completed · SIG-202610`, its `⚠` notes and `⚑ 3 lines flagged for review: open the statement and press f.`, and opens no screen · 6B balances saved after you left say `Balances saved · SIG-202611` and `The statement is not completed: open it and press c.` (2026-11-06). |

---

## Tasks

Drafted on 2026-11-06 for the owner to approve. Each task's "passes if…" is written when it
starts. "Left" means the screen that sent the write has closed before the engine answered; on a
screen still open, nothing changes.

1. **A write still finishes after its screen has left.** The shared write plumbing hands an
   answer that arrives after the screen has left to the app instead of dropping it: a success
   shows the message the screen would have toasted, a refusal shows the 10-second message
   titled with what was not saved, the engine's words in full and its app line. Writes still
   waiting behind it are sent, each one's ending said, a refusal stopping none. Proved on the
   ledger's `d` (`Transaction deleted.`, or `Not deleted · Wong · -45.90`).
2. **The list actions.** Manage's `a`, `t`, `c`, `x` and `d`, the "no statement" list's `d`, the
   flagged lines' `d` and Auth's bootstrap, each with its words (below).
3. **The Manage forms.** New and Edit for hashtags and categories, New account: `Hashtag
   created.`, `Category created.`, `Account created.`, `Person created.`, `Saved.`; a refusal ends
   `Nothing was saved: open it again to fix it.` The list you went back to reads again from row
   1 when the save changed it.
4. **The Edit forms.** The ledger's and the "no statement" list's: `Saved.` or `Saved. It left
   its statement.`, the list reading again; a refusal keeps its `! part 2 (amount): …` lines.
5. **The account Edit form** (pane 4 B): the account's changes, then each opening balance, all
   sent after you leave; all saved says `Saved.`, otherwise one `Not all saved · Account …` (or
   `Not saved · Account …` when nothing was) saying how each part ended and naming the
   currencies to set again.
6. **The ledger's bulk edit** (pane 3 B): the receipt and each kind of refusal after you leave,
   the rows named by date, title and amount, four at most and `and N more`; a run-wide stop as
   today.
7. **A statement's ticks, new statement, revert and delete.** Ticks still waiting are sent, a
   refused one titled with its line; `Statement created.`, `Statement reverted to draft.`,
   `Statement deleted.`, or their refusals.
8. **A statement's complete and its balances** (panes 5 B and 6 B): `Statement completed ·
   SIG-202610` with its `⚠` notes and the `⚑` line, opening no screen; `Balances saved ·
   SIG-202611` and `The statement is not completed: open it and press c.`

**Words to approve with the tasks:** a refused message's first line is what did not happen, then
`·` and what it was. The mockup draws `Not saved`, `Not created`, `Not deleted`, `Not archived`
and `Not all saved`; the others follow the same way: `Not unarchived`, `Not made a person`, `Not
made a bank account`, `Not added · PEN on BCP 4471`, `Not removed · PEN on BCP 4471`, `Not
provisioned`, `Not ticked` and `Not unticked` for a statement's line, `Not reverted`, `Not
completed`. A transaction is named `<title> · <amount>`, an account `Account <name>` (`Person
<name>` for a person), a category `Category <name>`, a hashtag `Hashtag #<name>`, a statement
`Statement <name>`.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- The account form saves the account and each opening balance as separate writes, so every
  client must chain them and say how each ended. One engine write taking both would let a save
  land whole or not at all: an engine ask.
