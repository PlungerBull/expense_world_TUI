# Caught up with contract e7393dd869963db1: the sheet import counts the rows its split lines come from

2026-11-03

## Covers

The part "Smaller changes" (`f91a1e0ae626c712` and `f0ee03d6faa96af1`) of your hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full", in the range `46e2fdf6e11d7548` →
`e7393dd869963db1`. The rename of card to holder in that range (`2cec1b59048f50dc`,
`e7393dd869963db1`, your hand-off of 2026-10-28) does not touch this part; the rest of the range
is answered in the replies for `f82426fb0a099676`. The version this client has read up to is
`f82426fb0a099676`.

How the terminal app uses it:
- The sheet import's counts line shows the split transactions and the sheet rows they hold,
  both from your `counts`: `Opening balances 0 · split transactions 3 (8 rows)`, or
  `split transactions 0 (0 rows)` when the sheet has none. It shows on the dry run and on the
  apply.
- The client never builds a cursor; it sends back only the `next_cursor` you gave it.
- Nothing in the client compares the reworded descriptions of `OPENING_BALANCE_NOT_SPLIT` and
  `LINE_GROUP_FIELDS_DIFFER` as text; it reads reason codes, never their descriptions.

## Done when, checked

All checked against the practice engine on 2026-11-03: the unit suite 3697 passed, the live
contract suite 338 passed, the fixture check found no drift, and the contract version had not
moved.

- **"The sheet import's count line shows the rows its split lines hold, from
  `counts.split_rows`":** worked. Run against the practice engine, a made-up sheet with three
  split transactions of 3, 3 and 2 rows printed `split transactions 3 (8 rows)` on the dry run
  and on the apply; a sheet with no split printed `split transactions 0 (0 rows)` on both. The
  live suite checks `split_rows` beside `split_lines` on a dry run and an apply: one split line
  from two sheet rows reads `1` and `2`.
- **A cursor you did not issue is refused:** the live suite sends `after=not-a-cursor` to
  `GET /transactions`, `GET /activity`, `GET /bank-lines` and `GET /exchange-rates/history`;
  each answers `422 VALIDATION_ERROR` with `INVALID_CURSOR` on `after`. No test expects a `500`
  or a `200` for one.

## Contract problems found

None.

## Asks this closes

- "The sheet import's counts say how many sheet rows its split lines come from".
