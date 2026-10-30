# The sheet import says how many rows its split transactions come from

Catches up to contract `e7393dd869963db1`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full", and the rename of card to holder
(`2cec1b59048f50dc`, `e7393dd869963db1`) in the engine's hand-off of 2026-10-28, "A person carries an
opening balance, and a card is now called a holder everywhere". This spec takes the first
hand-off's part "Smaller changes" (`f91a1e0ae626c712` and `f0ee03d6faa96af1`), answering the ask "The sheet
import's counts say how many sheet rows its split lines come from"; the rename does not touch
it. The rest of that range is caught up in the app's reads and writes, its statement screens
and the catch-up to contract `f82426fb0a099676`
(1 (done on 2026-10-30), 2 (done on 2026-10-30),
[3](catch-up-currencies-3-live-suite-foundation.md), [4](catch-up-currencies-4-live-suite-upload-lines-kinds.md),
[5](catch-up-currencies-5-live-suite-account-currencies.md), [6](catch-up-currencies-6-main-views.md),
[7](catch-up-currencies-7-statement-screen.md)), which takes over the range's live tests and
screens.

**Status: approved and named the current spec by the owner on 2026-10-27, its question
answered and its tasks approved. Task 2 runs after the live suite's foundation
([catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md)),
and after the app's sheet import code is on the new model
(part 2 of the currencies catch-up, done on 2026-10-30),
since the live sheet test runs that code.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

`expense import sheet` tells you how many split transactions a sheet holds, but not how many of
the sheet's rows they come from, so a sheet with three splits of eight rows reads the same as
one with three splits of six. The engine now answers that count, `counts.split_rows`, on every
answer of the sheet import: both dry runs and the apply
(contract: POST /v1/transactions/import-sheet, "Response").

The same hand-off rewords two refusals' descriptions to name the sheet's `COD_EECC` instead of
"line code", and refuses a hand-made cursor of the wrong shape with `422 INVALID_CURSOR`, where
some lists used to answer `500` or `200`
(contract: "Base Conventions", "Cursors, on every cursor-paged list"). Neither changes what you
see.

## What it must do

1. **The sheet import's counts line shows the rows its split transactions hold**, on the dry run
   and the apply, in the words question 1 picks.
2. **Nothing compares the two reworded refusal descriptions as text**; anything that does is
   updated.
3. **A live test proves a cursor the engine did not issue is refused** with `422 INVALID_CURSOR`
   on `after`, on each of the four cursor-paged lists (`GET /transactions`, `GET /activity`,
   `GET /bank-lines` and `GET /exchange-rates/history`), and no test expects a `500` or `200`
   for one. The cursor is a string the client never builds, so the test sends one that is not a
   cursor at all.

## How the owner knows it is done

1. A dry run of a sheet with three split transactions of eight rows in all shows the count
   question 1 picks, `3` and `8`, and its apply shows the same.
2. A sheet with no split transaction shows `0` for both.
3. The unit suite and the live suite pass, and the drift check no longer names
   `counts.split_rows`. The live checks run after the live suite's foundation
   ([catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md)).

## What the owner settled

- **The counts line** (owner, 2026-10-27, question 1, A): `Opening balances 0 · split
  transactions 3 (8 rows)`, as
  [expense-world-sheet-import-engine.html](../mockups/expense-world-sheet-import-engine.html)
  draws it; a sheet with none reads `split transactions 0 (0 rows)`.

## Questions for the owner

None open.

---

## Tasks

Approved by the owner on 2026-10-27.

2. **The live suite proves the count and the cursor refusal (builder), after
   [catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md)
   and part 2 of the currencies catch-up (done on 2026-10-30).**
   The live sheet import checks `split_rows` beside `split_lines`
   ([test_sheet_import.py](../../tests/contract/test_sheet_import.py)), its `names.accounts`
   entries one per sheet account name with no `currency_code`
   (contract: POST /v1/transactions/import-sheet, "Body"); a cursor the engine did not issue is
   refused `422 INVALID_CURSOR` on `after` on each of the four cursor-paged lists; no test
   expects `500` or `200` for one.
   *Passes if:* those live tests run green against the practice engine, no `names.accounts`
   entry the live sheet test sends carries `currency_code`, and nothing in the repo compares the
   two reworded refusal descriptions as text.


## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e7393dd869963db1`, the rename's `2cec1b59048f50dc` and
  `e7393dd869963db1` among it; this spec covers the part "Smaller changes"
  (`f91a1e0ae626c712`, `f0ee03d6faa96af1`).
- **The engine's "Done when" checks to report on:** the sheet import's count line shows the
  rows its split lines hold, from `counts.split_rows`.
- **The asks it closes:** "The sheet import's counts say how many sheet rows its split lines
  come from".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
