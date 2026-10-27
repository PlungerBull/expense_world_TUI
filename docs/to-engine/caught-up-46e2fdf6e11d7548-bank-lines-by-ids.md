# Caught up with contract 46e2fdf6e11d7548: the bank-line list reads several lines by their ids in one call, and lists oldest first on request

2026-10-27

## Covers

Contract versions `6687b18541c068e3` to `46e2fdf6e11d7548`, the hand-off "The bank-line list
reads several lines by their ids in one call, and lists oldest first on request" of 2026-10-26.
The TUI's saved contract version moved from `592f2467fa3df75a` to `46e2fdf6e11d7548`.

## Done when, checked

- **The close's review screen draws its flagged lines from one `GET /bank-lines?ids=…` call and
  drops deleted lines on re-read, without a per-id loop:** worked. The screen reads the ids the
  close answered in `review_lines` with `GET /bank-lines?ids=…&sort=date_asc&limit=<n>`, on
  opening and after each edit or delete, and shows the lines in the engine's order. In the app
  against the practice engine, a close leaving three lines unassigned opened the screen with
  them oldest first; deleting one dropped it on the re-read, and the deleted line answered `404`
  on `GET /bank-lines/{id}`. The client reads no line one at a time and sorts none itself.
- **The TUI's contract snapshot is at `46e2fdf6e11d7548`:** worked. The version check and the
  fixture check pass against it.

The live contract suite passes whole against the practice engine (210 tests). New live tests
cover `ids` (only live lines among the ids, each in the list's row shape; deleted and unknown ids
left out, never refused; `/count` agreeing; `ids` with `account_id`; `CONFLICTING_PARAMETERS`
beside `unassigned_in_period_of`; `OUT_OF_RANGE` above 200 ids, a repeated id counted twice;
`INVALID_FORMAT` for empty and non-UUID entries), `sort=date_asc` (the newest-first list
reversed, on an account, beside `ids`, beside `reconciliation_id` and beside
`unassigned_in_period_of`; its cursors refused under another order; `/count` refusing `sort`),
and a future-dated row's refusal naming its row, "Row <n>: Must not be in the future." on
`rows.<n>.date`, on `POST /transactions/import` and `POST /transactions/import-sheet`. No live
test drives the same words on `POST /reconciliations/import` yet.

## Contract problems found

- `review_lines` on `POST /reconciliations/{id}/complete` states no bound on how many lines a
  close flags, while `ids` takes at most 200. A close flagging more than 200 lines needs several
  reads, and the lines come back oldest first only within each read, never across them. The TUI
  reads them 200 at a time in the order the close sent them. Either a bound on `review_lines`
  that fits one read, or a way to read a close's flagged lines without sending their ids, would
  close the gap.

## Asks this closes

- "The bank-line list reads several lines by their ids in one call"
