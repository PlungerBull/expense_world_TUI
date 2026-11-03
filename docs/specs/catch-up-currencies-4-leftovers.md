# What the live tests for the upload, bank lines and kinds turned up

What part 4 of the catch-up to contract `f82426fb0a099676`, the live tests for the upload, bank
lines and kinds (done on 2026-10-31), turned up while it ran.

**Status: drafted on 2026-10-31 for the owner to rewrite or approve; one question.** It runs
after part 7 of the currencies catch-up (done on 2026-11-03),
which rewrites the statement screens these points touch. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

- **The Edit form still says "reconciliation"** where the engine and every other screen say
  statement: the note after a save that took a line out of its statement reads
  `Saved. It left its reconciliation.`, and the bank line's Edit form names the screen it came
  from `Reconciliations`.
- **Two live tests still drive the old Statements screen's reads** (the lines of a statement and
  the lines in no statement), and no live test drives the flagged lines' own read of the review
  list. Part 7 rewrites those screens; their live tests should then test the new screens' reads.
- **No live test has a line whose parts carry different dates** on the review list, though the
  engine states that such a line is listed when any of its parts counts.

## What it must do

1. **The Edit form says statement**, in the note after a save and in the screen's title, as
   question 1 picks.
2. **The live tests drive the statement screens' own reads**, the flagged lines' review list
   included, once part 7 has rewritten them.
3. **A live test lists a line whose parts carry different dates** on the review list when any of
   its parts counts.

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

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
