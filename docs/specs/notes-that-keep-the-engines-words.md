# Notes that keep the engine's words, and lines that say they are locked

**Status: drafted by the orchestrator on 2026-10-24 from what the spec
"Notes and hints that say what is true, and the bulk pick as a screen" found along the way;
waiting on the owner to rewrite or approve it, and to answer its questions.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Four small things found while building the last spec, not fixed there:

- When the engine refuses something, most app notes show its words as text the screen may treat
  as styling. A `[` in those words could make part of the message vanish. The bulk edit's note
  is already safe; the others are not.
- On a transaction inside a completed reconciliation, the Edit form lets you change its date,
  title, amount, account and operation number, but the engine refuses each change only when you
  save. The form should say so up front, as it does for an archived account's transaction.
- When missing settings stop a bulk edit, its note is titled "Refused"; the LOG bar's, for the
  same problem, is titled "Failed" and has a blank line before "Hint:".
- When you complete a reconciliation, the question says it locks the amount, account, title and
  date; the engine also locks the operation number and which reconciliation the row is in.

## What it must do

1. **Every note shows the engine's words exactly as sent**, `[` and all, never read as styling.
2. **On a transaction in a completed reconciliation, the Edit form shows the lines that can't
   change as read-only**, with a hint saying why, before you type anything (question 1).
3. **The bulk edit's missing-settings note reads like the LOG bar's** (question 2).
4. **The question before completing a reconciliation names everything it locks.**

## How the owner knows it is done

1. A refusal whose words hold `[like this]` shows them whole in its note.
2. Opening a transaction in a completed reconciliation, its DATE line says it can't change and
   why, and `⏎` there doesn't let you type a new date.
3. A bulk edit stopped by missing settings shows the same note the LOG bar shows.
4. The complete question names the operation number among what it locks.

## Questions for the owner

1. **A transaction in a completed reconciliation: what does the Edit form do?**
   - **A.** The lines that can't change (date, title, amount, account, operation number) show
     as read-only, with a hint like "read-only · its
     reconciliation is completed, so this can't change". An empty title or operation number can
     still be filled once, and category, hashtags and note stay editable, as the engine allows
     (contract: PUT /v1/transactions/{transaction_id}, "Field locking").
   - **B.** Leave it as today: you can type a new date, and the engine refuses it when you save.

   **Recommended:** A, because it matches how an archived account's transaction already
   behaves, and you find out before typing. The hint's exact wording gets a mockup to pick from
   before it is built.
2. **The bulk edit's missing-settings note:**
   - **A.** Same as the LOG bar's: titled "Failed", blank line before "Hint:".
   - **B.** Leave it as it is.

   **Recommended:** A: one problem, one note.

---

## Tasks

Drafted once the owner approves the spec and answers its questions.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
