# The sheet import says how many rows its split transactions come from

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full", its part "Smaller changes" (`f91a1e0ae626c712` and `f0ee03d6faa96af1`), answering the ask "The sheet
import's counts say how many sheet rows its split lines come from". The rest of that hand-off is
caught up in
[catch-up-cards-statements-1-routes.md](catch-up-cards-statements-1-routes.md),
[catch-up-cards-statements-2-live-suite.md](catch-up-cards-statements-2-live-suite.md),
[catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md) and
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).

**Status: draft, for the owner to rewrite or approve; question 1 waits on the owner. Its tasks
are drafted and wait on the owner's approval.** When done, the why moves to
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
   `counts.split_rows`. The live checks run once the shared helpers of the live suite create
   accounts on cards
   ([catch-up-cards-statements-2-live-suite.md](catch-up-cards-statements-2-live-suite.md)).

## Questions for the owner

1. **How the counts line says it.** Today: `Opening balances 0 · split transactions 3`.
   - **A.** `Opening balances 0 · split transactions 3 (8 rows)`, the engine coders'
     suggestion, as
     [expense-world-sheet-import-engine.html](../mockups/expense-world-sheet-import-engine.html)
     draws it. A sheet with none reads `split transactions 0 (0 rows)`.
   - **B.** `Opening balances 0 · split transactions 3 · rows in them 8`.

   **Recommended:** A, with the rows shown at zero too: the rows read as a detail of the
   splits, beside them, and every count shows on every run.

---

## Tasks

Drafted on 2026-10-27; they wait on the owner's approval and question 1.

1. **The counts line shows the split rows (builder).** The sheet import reads
   `counts.split_rows` with the other counts and prints it in the words question 1 picks, on the
   dry run and the apply ([import_cmd.py](../../expense/commands/import_cmd.py) `_counts_lines`,
   [engine.py](../../expense/import_/engine.py) `SheetCounts`); the fake engine's sheet answer
   carries it ([helpers.py](../../tests/unit/helpers.py) `sheet_counts`); the sample output in
   [commands.md](../commands.md) "`expense import sheet`" follows.
   *Passes if:* unit tests pin the line with splits and with none, on the dry run and the
   apply; the drift check no longer names `counts.split_rows`; commands.md shows the picked
   words.
2. **The live suite proves the count and the cursor refusal (builder), after the live suite's
   shared helpers create accounts on cards.** The live sheet import checks `split_rows` beside
   `split_lines` ([test_sheet_import.py](../../tests/contract/test_sheet_import.py)); a cursor
   the engine did not issue is refused `422 INVALID_CURSOR` on `after` on each of the four
   cursor-paged lists; no test expects `500` or `200` for one.
   *Passes if:* those live tests run green against the practice engine, and nothing in the repo
   compares the two reworded refusal descriptions as text.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e06456a20aca6e4c`; this spec covers its part "Smaller
  changes" (`f91a1e0ae626c712`, `f0ee03d6faa96af1`).
- **The engine's "Done when" checks to report on:** the sheet import's count line shows the
  rows its split lines hold, from `counts.split_rows`.
- **The asks it closes:** "The sheet import's counts say how many sheet rows its split lines
  come from".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
