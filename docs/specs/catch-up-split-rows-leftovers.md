# What the sheet import's split rows catch-up turned up

What the catch-up to contract `e7393dd869963db1`, the sheet import's split rows (done on
2026-11-03), turned up while it ran.

**Status: approved on 2026-11-03; question 1 answered (A).** It waits on no other spec. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

- **An apply that writes new rows and skips or seals none ends on an empty line.**
  `expense import sheet --apply` prints its `Written:` line, then the opening balances and split
  transactions line, then a blank line with nothing after it. The blank line is there to
  separate the counts from the lists of rows of zero and rows on a closed statement's day; when
  there are no lists it separates nothing. The dry run prints its blank line only when a list
  follows.
- **No unit test pins an apply's output when some rows are new and none is skipped or sealed**,
  so nothing would notice that output changing.

## What it must do

1. **An apply's output ends as question 1 picks** when some rows are new and none is skipped or
   sealed.
2. **A unit test pins that output**, line for line.

## How the owner knows it is done

1. An apply of a sheet where every row is new and none is zero or on a closed day ends as
   question 1 picks.
2. The unit suite passes.

## Questions for the owner

1. **The end of an apply with nothing skipped or sealed.**
   - **A.** No blank line after the counts when no list follows, as the dry run already does:

         Written: new 9 · matched 0 · sealed 0 · skipped 0
         Opening balances 0 · split transactions 3 (8 rows)

   - **B.** Keep the blank line:

         Written: new 9 · matched 0 · sealed 0 · skipped 0
         Opening balances 0 · split transactions 3 (8 rows)
         (empty line)

   **Recommended:** A: the blank line separates nothing, and the dry run already leaves it out.

   **Picked:** A.

---

## Tasks

All done.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **No unit test covers an apply that lists sealed rows.** "Sealed, on a closed statement's day"
  is asserted only on the dry run; the apply prints it through the same list as the rows of zero.
