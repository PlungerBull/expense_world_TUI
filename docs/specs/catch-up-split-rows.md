# The sheet import says how many rows its split transactions come from

Catches up to contract `f0ee03d6faa96af1`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27 (`f91a1e0ae626c712` and `f0ee03d6faa96af1`), answering the ask "The sheet import's
counts say how many sheet rows its split lines come from".

**Status: draft, for the owner to rewrite or approve; question 1 waits on the owner. Its tasks
are drafted when the owner names it the current spec.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

`expense import sheet` tells you how many split transactions a sheet holds, but not how many of
the sheet's rows they come from, so a sheet with three splits of eight rows reads the same as
one with three splits of six. The engine now answers that count, `counts.split_rows`, on every
answer of the sheet import: both dry runs and the apply
(contract: POST /v1/transactions/import-sheet).

The same hand-off rewords two refusals' descriptions to name the sheet's `COD_EECC` instead of
"line code", and refuses a hand-made cursor of the wrong shape with `422 INVALID_CURSOR`, where
some routes used to answer `500` or `200`. Neither changes what you see.

## What it must do

1. **The sheet import's counts line shows the rows its split transactions hold**, on the dry run
   and the apply, in the words question 1 picks.
2. **Nothing compares the two reworded refusal descriptions as text**; anything that does is
   updated.
3. **No test expects a `500` or `200` for a malformed cursor**; a live test proves a malformed
   cursor is refused with `422 INVALID_CURSOR` on `after`.
4. **The contract version this client has caught up to is recorded** as `f0ee03d6faa96af1`.

## How the owner knows it is done

1. A dry run of a sheet with three split transactions of eight rows in all shows the count
   question 1 picks, `3` and `8`, and its apply shows the same.
2. A sheet with no split transaction shows `0` for both.
3. The unit suite, the live suite and the drift check pass, the version check reading
   `f0ee03d6faa96af1`.

## Questions for the owner

1. **How the counts line says it.** Today: `Opening balances 0 · split transactions 3`.
   - **A.** `Opening balances 0 · split transactions 3 (8 rows)`, the engine coders'
     suggestion.
   - **B.** `Opening balances 0 · split transactions 3 · rows in them 8`.

   **Recommended:** A: the rows read as a detail of the splits, beside them.

---

## Tasks

Drafted when the owner names this the current spec.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `f0ee03d6faa96af1` (`f91a1e0ae626c712`, `f0ee03d6faa96af1`).
- **The engine's "Done when" checks to report on:** the sheet import's count line shows the
  rows its split lines hold, from `counts.split_rows`; this client's contract snapshot is at
  `f0ee03d6faa96af1`, and it reports having read up to it.
- **The asks it closes:** "The sheet import's counts say how many sheet rows its split lines
  come from".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
