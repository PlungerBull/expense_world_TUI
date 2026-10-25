# A reconciliation's bank lines can be listed in the statement's order

Raised 2026-10-24.

## Why

A statement line exists so that a statement's lines keep the paper (PDF) statement's order. The
person never needs to see the code itself; what they need is to go down a reconciliation's lines
and the PDF together, row for row, ticking and checking as they go.

Today `GET /v1/bank-lines` has one order, newest first, and no `sort` parameter, so a
reconciliation's lines come back in the reverse of date order whatever their `statement_place`.
A client could re-sort a page by `statement_place`, but the list is paged by cursor, so a re-sorted
page is wrong as soon as the reconciliation holds more lines than one page; reading every page to
sort them is the extra round trips and drifting copy of an engine rule this client avoids.

## The ask

`GET /v1/bank-lines` (and `GET /v1/bank-lines/count` where it matters) can list a reconciliation's
lines in the statement's order: by `statement_place` ascending, lines with no place after every
placed one (in a stated order among themselves, for example oldest first, matching "The statement
order lists a statement's unplaced lines oldest first"), with a stated tie-break for a place held
by two lines. Offered at least when `reconciliation_id` is given (for example `sort=statement` or
a `sort` parameter with that value; the shape is yours), with cursor paging that stays correct in
that order. Every other use of the route keeps today's default.

## Done when

- `GET /v1/bank-lines?reconciliation_id=<id>&<the statement order>` on an ordered statement
  returns the reconciliation's lines with places 1, 2, 4, 5 … in that order (the gaps being the
  other half's lines on a card), then its unplaced lines.
- Paging through it with a small `limit` returns every line once, in the same order.
- A place held by two lines returns both, in the stated tie-break.
- On an account without a statement code the order is still defined (every line unplaced).
- The contract states the order, its tie-breaks and where it is accepted.

## What this client removes once it lands

Nothing to remove: without it a reconciliation's screen keeps listing its lines newest first, and
the person has to search the screen for each PDF row. With it, the screen lists the lines in the
PDF's order.
