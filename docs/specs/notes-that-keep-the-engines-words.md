# Notes that keep the engine's words, and lines that say they are locked

Catches up to contract `592f2467fa3df75a`, from `309e31fd5c266941`: item 7 of the engine's
hand-off of 2026-10-26, a locked field's words (`f7a0a0bbcfe62975`). The rest of the hand-off is
in [catch-up-bank-download-and-closing.md](catch-up-bank-download-and-closing.md), which runs
after this one.

**Status: approved by the owner on 2026-10-25, its questions answered; the current spec since
2026-10-26, the owner choosing it before the engine catch-up. The engine shipped the ask "A bank
line's edit limits say why each field is locked, in words" on 2026-10-26, so all four points can
be built.** When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

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

Three mockup picks, in
[expense-world-read-only-reasons.html](../mockups/expense-world-read-only-reasons.html): where
the reason sits beside `read-only` (screen 1), an OK for the bulk edit's note (screen 2), and the
words of the complete question (screen 3). Tasks 3 to 5 wait on them.

---

## Tasks

The engine's move to `592f2467fa3df75a` breaks the bank download import and the close of a
statement, and the live suite and the drift check's fixture check fail on them (the close's
fixture lacks `review_lines`). Those failures are the catch-up's, which runs next
([catch-up-bank-download-and-closing.md](catch-up-bank-download-and-closing.md) "How the owner
knows it is done" 4); this spec's acceptance check reports them and does not fail on them.

1. **The app reads a locked field as the engine sends it.** Each entry of `edit_limits`'
   `locked_fields` and `locked_part_fields` is `{reason, message}`
   (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). Nothing you see changes.
   Passes if: the unit fake engine's `edit_limits` (tests/unit/helpers.py) answers every entry
   in that shape, with the contract's sentence for each reason, and every unit test that builds
   one goes through it; the Edit form locks the same lines as before from the new shape; the live
   test of `edit_limits` (tests/contract/test_bank_line_edit_limits.py) passes against `:8002`,
   reading `reason` where it read the bare code and checking, for each reason it draws, that the
   read's `message` is the write's words on that field; the app keeps no table from reason to
   sentence; tui.md says what `edit_limits` carries.
2. **Every note shows the engine's words exactly as sent** (What it must do 1; the "Already
   settled" pane of the mockup). Passes if: every place the app puts engine words on screen (a
   toast's message or title, a refusal under a screen, a question, a status line) shows them as
   text, never as styling; a unit test per place drives a refusal whose message and field words
   hold `[like this]` and finds them whole; a guard test fails when new app code hands engine
   words to a toast as styling, its docstring stating what it cannot catch; nothing else in any
   note changes; tui.md states the rule where it describes refusals.
3. **The Edit form says why beside `read-only`** (What it must do 2), as the owner picks on
   screen 1 of the mockup. Waits on that pick.
4. **The bulk edit's missing-settings note reads like the LOG bar's** (What it must do 3), screen
   2 of the mockup. Waits on the owner's OK.
5. **The question before completing a reconciliation names everything it locks** (What it must
   do 4), as the owner picks on screen 3 of the mockup. Waits on that pick.

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
