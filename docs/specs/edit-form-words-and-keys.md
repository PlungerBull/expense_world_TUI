# The Edit form's words and keys match what it does

**Status: approved by the owner on 2026-10-25, with A for all three questions, its tasks approved
the same day and the spec run before "Statement lines come from reconciliations"; the words of
tasks 2 and 3 picked the same day in
[mockups/expense-world-edit-form-words.html](../mockups/expense-world-edit-form-words.html):
1 A, 2 A and 3 A.**
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

`⏎` and `s` now open one Edit form, with every part of a transaction on it. Three things around
it still describe the screens it replaced:

- On an archived account's row the ledger hides `s`, although `⏎` on that row opens the same
  form, where its parts' categories, hashtags and notes still change.
- Some words still describe the old screens. The ledger's `s` reads "Split the cursor row into
  parts". The `?` card in "no batch" says `⏎` edits "its date, title, operation, amount or
  account", leaving out category, hashtags and note. A refused part names the engine's field for
  category and hashtags (`part 1 (category_id)`, `part 1 (hashtag_ids)`), while the amount reads
  `part 1 (amount)`.
- When the engine refuses a hashtag on an opening balance from the Edit form, the form adds the
  ledger's line "Leave the opening balance out of the selection.", which reads wrong there. It is
  rare, since those hashtags already show read-only.

## What it must do

1. **`s` on an archived account's row** does what question 1 picks.
2. **The words for `s`, for `⏎` in "no batch", and for a refused part's category and hashtags**
   match the form, as question 2 picks.
3. **An opening balance's hashtag refusal on the Edit form** reads as question 3 picks.

## How the owner knows it is done

1. On an archived account's row, `s` behaves as picked.
2. The ledger's key line, the "no batch" `?` card and a refused part's line read as the picked
   mockup draws them.
3. The opening balance's hashtag refusal on the form shows what was picked.

## What the owner settled

On 2026-10-25 the owner answered each question with A:

1. **Question 1, A: `s` shows on an archived account's row** and opens the same Edit form `⏎`
   does, where only what the account still allows can change. `d` stays hidden there.
2. **Question 2, A: the words are reworded to match the form**, the exact words picked from a
   mockup first.
3. **Question 3, A: an opening balance's hashtag refusal on the Edit form shows the engine's
   words alone**, with no line of the app's own. The ledger's bulk edit keeps its line.

---

## Tasks

Approved by the owner on 2026-10-25. They run in this order: 2 and 3. Both are **[UI]**,
picked from
[mockups/expense-world-edit-form-words.html](../mockups/expense-world-edit-form-words.html).

2. **[UI] The words for `s` and for `⏎` in "no batch"** read as screens 1 A and 2 A of the
   mockup draw them: the ledger's footer says `s Edit` and its `?` card line "Edit the
   transaction and its parts", and the "no batch" `?` card line for `⏎` reads the same. tui.md
   follows. Tests pin each line.
3. **[UI] A refused part names its category and hashtags in the form's words**, as screen 3 A of
   the mockup draws it: `part 1 (category)` and `part 1 (hashtags)`, as `part 1 (amount)` reads
   now. A test for each.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **A mockup still draws the opening balance's line on the Edit form.** Pane 7 of
  [mockups/expense-world-pending-hashtag-manage.html](../mockups/expense-world-pending-hashtag-manage.html)
  says "The Edit form shows the same note", which task 4 takes off the form; tui.md cites that
  mockup only for the ledger's line. Part of the todo.md item "Mockups that back no open work".
- **A held reserved name may draw the category line on the Edit form.** `RESERVED_NAME_HELD`
  draws no line on the keys `hashtag_ids` and `hashtag_id` alone (`no_line_on` in
  [errors.py](../../expense/errors.py)); if the whole-line write sends it on
  `parts.<i>.hashtag_ids`, the Edit form shows the category line, though tui.md says it shows
  none there. Unconfirmed: check the live contract's key, and add a test for it.
