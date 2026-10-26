# The Edit form's words and keys match what it does

**Status: approved by the owner on 2026-10-25, with A for all three questions, its tasks approved
the same day and the spec run before "Statement lines come from reconciliations"; tasks 2 and 3
wait for a pick in
[mockups/expense-world-edit-form-words.html](../mockups/expense-world-edit-form-words.html).**
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

Approved by the owner on 2026-10-25. They run in this
order: 1, 4, 2 and 3. Tasks 2 and 3 are **[UI]**, picked from
[mockups/expense-world-edit-form-words.html](../mockups/expense-world-edit-form-words.html).

1. **`s` on an archived account's row opens the Edit form.** With the cursor on such a row, `s`
   is in the footer and opens the form as `⏎` does; `d` stays off there, and `s` stays off while
   rows are selected or a bulk write runs. The comment in `check_action` that says the engine
   refuses `s` there goes. tui.md "On an archived account's row the ledger offers no `s` and no
   `d`" says what is now true. Tests for `s` on an archived row and `d` still off on it.
2. **[UI] The words for `s` and for `⏎` in "no batch"** read as screens 1 and 2 of the mockup
   are picked: the ledger's footer word and `?` card line for `s`, and the "no batch" `?` card
   line for `⏎`. tui.md follows. Tests pin each line.
3. **[UI] A refused part names its category and hashtags in the form's words**, as screen 3 of
   the mockup is picked: `part 1 (category)` and `part 1 (hashtags)`, as `part 1 (amount)` reads
   now. A test for each.
4. **An opening balance's hashtag refusal on the Edit form shows the engine's words alone.** The
   `OPENING_BALANCE_NOT_TAGGED` refusal shows no app line on the Edit form; the ledger's bulk `h`
   keeps its line, "Leave the opening balance out of the selection." A test for each screen.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
