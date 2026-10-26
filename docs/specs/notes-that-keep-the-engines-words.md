# Notes that keep the engine's words, and lines that say they are locked

**Status: approved by the owner on 2026-10-25, its questions answered; not started. Its tasks
are drafted when the owner names it the current spec.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Four small things found while building the last spec, not fixed there:

- When the engine refuses something, most app notes show its words as text the screen may treat
  as styling. A `[` in those words could make part of the message vanish. The bulk edit's note
  is already safe; the others are not.
- The Edit form marks every line that can't change `read-only`, and says no more: on a
  transaction in a completed reconciliation you see its date is `read-only`, but not why. The
  engine already sends a reason for each locked field with the line
  (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields").
- When missing settings stop a bulk edit, its note is titled "Refused"; the LOG bar's, for the
  same problem, is titled "Failed" and has a blank line before "Hint:".
- When you complete a reconciliation, the question says it locks the amount, account, title and
  date; the engine also locks the operation number and which reconciliation the row is in.

## What it must do

1. **Every note shows the engine's words exactly as sent**, `[` and all, never read as styling.
2. **The Edit form says why beside `read-only`**, e.g. "its reconciliation is completed", from
   the reason the engine sends; the wording on screen is picked from a mockup before it is built
   (question 1).
3. **The bulk edit's missing-settings note reads like the LOG bar's**: titled "Failed", with a
   blank line before "Hint:".
4. **The question before completing a reconciliation names everything it locks.**

## How the owner knows it is done

1. A refusal whose words hold `[like this]` shows them whole in its note.
2. Opening a transaction in a completed reconciliation, its DATE line says `read-only` and why.
3. A bulk edit stopped by missing settings shows the same note the LOG bar shows.
4. The complete question names the operation number among what it locks.

## What the owner settled

- **The reason beside `read-only`** (owner, 2026-10-25): the Edit form already shows a completed
  reconciliation's lines read-only; this spec adds why, after a mockup pick.
- **The bulk edit's missing-settings note is the LOG bar's** (owner, 2026-10-25): one problem,
  one note.

## Questions for the owner

1. **Which read-only lines say why?**
   - **A.** Every one: a completed reconciliation's lines, an opening balance's, an archived
     account's, each with the reason the engine sends for it.
   - **B.** Only a completed reconciliation's lines; the others keep plain `read-only`.

   **Recommended:** A, because the engine gives a reason for every locked line, so one rule
   covers them all and the app copies no rule of its own. Asked with the mockup, when the spec
   starts.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
