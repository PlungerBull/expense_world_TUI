# Notes that keep the engine's words, and lines that say they are locked

Catches up to contract `592f2467fa3df75a`, from `309e31fd5c266941`: item 7 of the engine's
hand-off of 2026-10-26, a locked field's words (`f7a0a0bbcfe62975`). The rest of the hand-off is
in [catch-up-bank-download-and-closing.md](catch-up-bank-download-and-closing.md), which runs
first.

**Status: approved by the owner on 2026-10-25, its questions answered; not started. Its tasks
are drafted when the owner names it the current spec. The engine shipped the ask "A bank line's
edit limits say why each field is locked, in words" on 2026-10-26, so all four points can be
built.** When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

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
- **Every read-only line says why** (owner, 2026-10-25): a completed reconciliation's lines, an
  archived account's, an opening balance's, each with the reason the engine sends for it.
- **The engine sends the words** (owner, 2026-10-25): the engine sends each lock's reason as a
  code only (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"), so the app asks
  the engine to send a sentence with it, rather than keeping its own table from code to words.
  The engine ask "A bank line's edit limits say why each field is locked, in words" carries it;
  the Edit form shows the engine's sentence as sent, and the mockup picks only where it sits.

## What the engine sends

Each locked field now comes with its reason and its sentence, the sentence being the words the
engine refuses that field with when a write tries to change it
(contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). The six sentences, as shipped
on 2026-10-26: "Locked by completed reconciliation."; "The account is archived. Unarchive it
first."; "Must not move an opening balance to another account."; "The parts must add up to the
line's total."; "Must not move an opening balance out of the opening-balance category."; "Must
be empty: an opening balance carries no hashtag." The Edit form shows the sentence as sent and
keeps no table of its own from reason to words.

## Questions for the owner

None open. Where the reason sits beside `read-only` is picked from a mockup when the spec starts.

---

## Tasks

Drafted when the owner names this the current spec.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** item 7 of the hand-off (`f7a0a0bbcfe62975`, its example worded again in
  `592f2467fa3df75a`); the range as a whole is confirmed in the reply of
  [catch-up-bank-download-and-closing.md](catch-up-bank-download-and-closing.md).
- **The engine's "Done when" checks to report on:** the app shows each locked field's `message`
  and keeps no table of its own from code to sentence.
- **The asks it closes:** "A bank line's edit limits say why each field is locked, in words".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
