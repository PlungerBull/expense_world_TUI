# The statement read lists every line a statement needs, on any account, oldest first

Raised 2026-10-25.

## Why

The owner checks a month's statement on one screen that reads like the paper: the statement's
lines in the paper's order, both currencies of a card mixed, and under them the lines of the
period that are not on any statement yet, oldest first, so nothing to tick is missed. The same
screen serves an account with no statement code, its lines oldest first.

Today that screen would need several reads and its own sorting:

- `GET /v1/reconciliations/{reconciliation_id}/statement-order` gives a statement's own lines in
  order, but refuses an account with no statement code (`NO_STATEMENT_CODE`).
- The lines of the period in no reconciliation come from `GET /v1/bank-lines` with
  `account_id`, `unreconciled=true`, `date_from` and `date_to`, which sorts newest first only.
  For a card that is one read per account, and the client would merge the two by date and
  reverse them, carrying its own copy of the order and its tie-breaks.
- Which lines count as "in the period and in no reconciliation" is already the engine's rule:
  the complete refuses with `UNASSIGNED_IN_PERIOD` while any exists, each half counting its own
  account's rows inside its own period, `@Opening` seeds exempt. A client listing them itself
  holds a second copy of that rule, which drifts.

## The ask

On `GET /v1/reconciliations/{reconciliation_id}/statement-order`:

1. **Add `unassigned`**: the lines the statement still needs, exactly the rows the complete's
   `UNASSIGNED_IN_PERIOD` check counts (each half's own account, inside its own period, in no
   reconciliation, `@Opening` seeds left out as that check leaves them out), each line as
   `GET /bank-lines/{id}` returns it, oldest first by the same order and tie-breaks as
   `unplaced`, a card's two halves mixed by date. `[]` when there are none, and on a completed
   statement.
2. **Answer on an account with no statement code too**, instead of `409 NO_STATEMENT_CODE`:
   `places` is `[]`, `unplaced` lists the reconciliation's lines oldest first, and `unassigned`
   as above. The `PUT` keeps refusing such an account, since it has no order to write.

## Done when

- A draft card statement with one line of each account dated inside its days and in no
  reconciliation reads both in `unassigned`, oldest first, mixed by date, read the same from
  either half; ticking one into its half moves it to `unplaced`.
- A line in another reconciliation, a line dated outside the period, a deleted line and an
  `@Opening` seed never appear in `unassigned`.
- `unassigned` is empty exactly when the complete would not refuse with `UNASSIGNED_IN_PERIOD`.
- An account with no statement code reads `places: []`, its lines oldest first in `unplaced`, and
  `unassigned`; its `PUT` is still `409 NO_STATEMENT_CODE`.
- The contract states the new key, its order and which lines it holds.

## What this client removes once it lands

Nothing to remove: without it the statement's screen cannot list the lines still to tick oldest
first, mixed across a card's two accounts, without its own merge and sort and its own copy of the
"in the period, in no reconciliation" rule. With it the screen makes one read for everything it
shows.
