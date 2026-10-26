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

None open. The owner picked the three screens of
[expense-world-read-only-reasons.html](../mockups/expense-world-read-only-reasons.html) on
2026-10-26: 1 B, 2 A and 3 A.

---

## Tasks

The engine's move to `592f2467fa3df75a` breaks the bank download import and the close of a
statement, and the live suite and the drift check's fixture check fail on them (the close's
fixture lacks `review_lines`). Those failures are the catch-up's, which runs next
([catch-up-bank-download-and-closing.md](catch-up-bank-download-and-closing.md) "How the owner
knows it is done" 4); this spec's acceptance check reports them and does not fail on them.

6. **The drift check's fixture check passes on this spec's tests.** The tester's acceptance
   check of 2026-10-26 found the fixture check flagging seven keys this spec's tests added, none
   of them an engine field: `amount`, `note`, `tx1`, `kor`, `category_names`,
   `pickable_categories` and `markup` (test_tui_edit_form.py, test_tui_engine_words.py,
   test_tui_create_forms.py, test_tui_opening_balance.py). Passes if: `check_fixture_drift.py`
   against `:8002` reports only the known `review_lines (complete_answer)` gap, each of the seven
   either reshaped out of the tests or listed in `KNOWN_LOCAL` with a note saying what writes it
   (an entry only while a fixture still writes it, as
   `test_known_local_exemptions_still_match` guards); no key an engine answer could hold is
   exempted.

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

- **The live `edit_limits` test never reads a refused write back.** Its module docstring says
  every refusal writes nothing, but the writes refused on locked line fields and on locked part
  amounts, categories and hashtags are checked only by their refusal; the next read comes after
  a revert or an unarchive, so a refused write applied in part would go unseen
  ([test_bank_line_edit_limits.py](../../tests/contract/test_bank_line_edit_limits.py)).
- **Nothing checks the unit fake engine's lock sentences against the contract.** `LOCK_MESSAGES`
  in [helpers.py](../../tests/unit/helpers.py) holds the six sentences; the drift check compares
  keys, not values, so a sentence the engine rewords would drift unseen.
- **A name or title holding `[like this]` loses it in lists.** A table cell passed as a plain
  string is read as styling: an account named `BCP [like this]` shows `BCP `. `_cell` in
  [cursor_list.py](../../expense/tui/widgets/cursor_list.py) passes every list's text through
  that way, and the bank import preview's title does too
  ([bank_import.py](../../expense/tui/screens/bank_import.py)). Names and titles in lists should
  show as sent.
- **Engine words ending in a backslash lose one in the bulk edit's note.** The app's closing `[/]`
  follows the words straight after, and the styling reader takes the backslash as escaping it
  (`refusal_notes` in [transactions.py](../../expense/tui/screens/transactions.py); the limit is
  stated in `as_markup`'s docstring in [refusal.py](../../expense/tui/widgets/refusal.py)).
  Closing the style after the line's end, or leaving the last line's style open, shows the same
  text without the limit.
- **Toasts of the owner's own typing have no test of their own.** `No account matches "…"`,
  `Nothing matches "…"`, System's invalid-URL and config-save toasts go through `toast`, but no
  test types `[like this]` into them.
- **The test helper `toasts_shown` reads Textual's private `Toast` class**
  ([helpers.py](../../tests/unit/helpers.py)), which Textual does not export; an upgrade could
  move it.
- **tui.md's rule on showing the engine's words sits between a sentence and the table of reasons
  it introduces** ("When the engine says no" in [tui.md](../tui.md)), so that sentence's "below"
  points past it.
- **Two bulk-edit tests check less than the stop note's rules.** No test pins `N of M refused`
  when two or more rows are refused for their own reason before missing settings stop the run
  (the row the stop met is not counted among them), and the mid-run stop's test checks the
  selection alone, not the receipt for the row that landed, the `Failed` note, or that no
  `Refused` note shows ([test_tui_bulk_edit.py](../../tests/unit/test_tui_bulk_edit.py)).
- **The old words for what complete locks remain in a test and two mockups.** The docstring of
  [test_reconciliations_lifecycle.py](../../tests/contract/test_reconciliations_lifecycle.py)
  says completion locks "amount/account/title/date"; the complete question in
  `expense-world-split-transaction-screen.html` and `expense-world-card-statement.html`
  ([mockups/](../mockups/)) still reads the old sentence. The app and the live contract lock six
  things: amount, date, title, account, operation number and reconciliation.
