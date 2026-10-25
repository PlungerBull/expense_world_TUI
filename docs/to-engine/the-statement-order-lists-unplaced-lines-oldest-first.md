# The statement order lists a statement's unplaced lines oldest first

Raised 2026-10-24.

## Why

Putting a statement in order means copying the paper statement's order, top to bottom, both
currencies mixed. The owner's card statements list their lines mostly by date, oldest first, with
a few exceptions. So the quickest way to order a statement is to start from its lines in date
order and move only the exceptions.

Today `GET /v1/reconciliations/{id}/statement-order` returns `unplaced` in `GET /bank-lines`'s
default order, newest first, which is the reverse of the paper. A client wanting to start from
date order would have to re-sort the lines itself, and every client would then carry its own copy
of the sort and its tie-break (two lines on one day, a soles line and a dollar line on one day),
each subtly different.

## The ask

On `GET /v1/reconciliations/{reconciliation_id}/statement-order` (and the `PUT`'s answer, which
reads the same), list `unplaced` **oldest first**: by date ascending, both halves of a card
interleaved, with a stated tie-break for lines on the same date (for example the line code
ascending, so lines of one day keep the order they were created in). `places` is unchanged.

A client then offers the order "every placed line in its place, then the unplaced lines as
listed" as its starting suggestion, and the person moves only what the paper shows differently.

## Done when

- A card statement with no line placed reads `unplaced` in date order, oldest first, soles and
  dollar lines mixed by date.
- Two lines on the same date read in the stated tie-break order, the same on every read and from
  either half.
- A line assigned after the last list appears in `unplaced` by its date among the other unplaced
  lines, not at the top.
- The contract states the order and the tie-break.

## What this client removes once it lands

Nothing to remove: without it the order screen starts from the lines newest first and the person
arranges every line by hand. With it, the screen opens in date order and the person fixes only
the exceptions.
