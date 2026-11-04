# What the live tests for the upload, bank lines and kinds turned up

What part 4 of the catch-up to contract `f82426fb0a099676`, the live tests for the upload, bank
lines and kinds (done on 2026-10-31), turned up while it ran.

**Status: approved on 2026-11-03; question 1 answered (A), already shipped by part 7.** It
waits on no other spec. When done, the why moves to [decisions.md](../decisions.md) and this
file is deleted.

---

## Why

- **The Edit form still says "reconciliation"** where the engine and every other screen say
  statement: the note after a save that took a line out of its statement reads
  `Saved. It left its reconciliation.`, and the bank line's Edit form names the screen it came
  from `Reconciliations`.
- **Two live tests still drive the old Statements screen's reads** (the lines of a statement and
  the lines in no statement), and no live test drives the flagged lines' own read of the review
  list. Part 7 rewrites those screens; their live tests should then test the new screens' reads.

## What it must do

1. **The Edit form says statement**, in the note after a save and in the screen's title, as
   question 1 picks.
2. **The live tests drive the statement screens' own reads**, the flagged lines' review list
   included, once part 7 has rewritten them.

## How the owner knows it is done

1. Saving a line out of its statement on the Edit form says statement, never reconciliation.
2. The live suite passes against the practice engine and leaves nothing on either practice user.
3. The unit suite passes.

## Questions for the owner

1. **The note after a save that takes a line out of its statement.**
   - **A.** `Saved. It left its statement.`, and the bank line's Edit form names the screen it
     came from as part 7 names the Statements screen.
   - **B.** Other words: tell me which.

   **Recommended:** A: the engine's word, one word swapped.

   **Picked:** A.

---

## Tasks

Point 1 already holds: [edit_form.py](../../expense/tui/screens/edit_form.py) notes
`Saved. It left its statement.` and its crumb names `Statements`; the acceptance check confirms it.

1. **A live test drives the flagged lines' screen's own reads.** A new live test reads a
   statement's review list through the app's own calls, as the flagged lines' screen and the
   statement upload's result do (`count_bank_lines` with `review_of=` and the screen's list read
   with `sort="statement"`), on a draft and after its close: the count agrees with the list, and
   after the close the list is exactly the close's `review_lines` in their order, every currency
   of the account together. It cleans up after itself like every live test (conftest.py
   `scratch`).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- In [test_bank_lines.py](../../tests/contract/test_bank_lines.py),
  `test_the_statement_screen_lists_and_ticks_lines_through_its_own_reads` writes the lines in no
  statement's sort as the literal `"date_asc"` where `UNFILED_SORT` names it, and its docstring
  mixes the read's argument names (`reconciliation=`, `account=`) with the engine's (`account_id`,
  `unreconciled=true`) in one sentence. Nothing you see changes.
