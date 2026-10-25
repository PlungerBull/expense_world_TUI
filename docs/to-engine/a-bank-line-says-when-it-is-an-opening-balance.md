# A bank line says when it is an account's opening balance

Raised 2026-10-25.

## Why

An account's opening balance is a ledger line like any other, and it can be assigned to a
reconciliation, but it never takes a place in a statement's order: the statement-order read always
lists it under `unplaced`, and a list that places it is refused (`OPENING_BALANCE_NOT_PLACED`).

The owner puts a statement in order on its own screen by moving lines up and down. That screen has
to know which line is the opening balance, to show it apart and never send it in the order.
Today the only way is to read the account and match its `opening_balance_transaction_id` against
each line's parts: an extra read per account, and every client repeating the same match.

## The ask

Every bank line the engine returns (`GET /v1/bank-lines/{bank_line_id}`, `GET /v1/bank-lines`,
the statement-order read's `places` and `unplaced`, and the whole-line write's answer) carries
**`is_opening_balance`**: `true` when the line is its account's opening balance, `false`
otherwise.

## Done when

- An account's opening balance line reads `is_opening_balance: true` on each of those reads, and
  every other line `false`.
- On a statement-order read, the line with `true` is the one a list may not place.
- The contract states the field.

## What this client removes once it lands

Nothing to remove: without it the statement's screen would read each account and match its
opening balance against every line's parts to keep that line out of the order. With it the
screen reads the flag on the line.
