# The sheet import's dry run counts the rows before every name has an id

Raised 2026-10-26.

## Why

The sheet import's dry run is how the owner checks the sheet before anything is written
(contract: POST /v1/transactions/import-sheet). Sent without `names`, it answers the names the
sheet uses and their proposals, and it judges every row, but every row's `outcome`,
`account_id` and `is_opening_balance` comes back `null` and every count is `0`. Checked on the
practice engine on 2026-10-26.

A client can only fill `names` with ids it has, and a name with no proposal has none until it is
created, which a dry run must not do. On the official import, onto an empty ledger, every name
is new, so the dry run can never show how many rows are new, matched, sealed or skipped, how many
are opening balances, or how many split lines there are. The owner sees those numbers for the
first time after the write, which is all or nothing and runs once. Every client that offers the
sheet import meets the same wall.

## The ask

A dry run without a full table answers outcomes and counts as the apply would, taking every name
the table does not give an id to be a new resource of that name (an account of that name and
currency) that holds no lines yet: its rows can only be `new`, `sealed` (never, for a new
account) or `skipped`; rows on names that do have an id (from the table sent, or, when no table
is sent, from their proposals) are matched against the ledger as today. `is_opening_balance` is
worked out the same way. The answer says which names it took as new, so a client never mistakes
an estimate for the table it must still confirm. The apply is unchanged: it still needs every
name mapped.

How it is shaped is the engine's call: a flag on the dry run (`assume_new_names`), or filling
outcomes from the proposals whenever `names` is omitted, would both do.

## Done when

- A dry run of a sheet whose names the ledger lacks, sent with no `names`, answers every row's
  outcome and `is_opening_balance`, and `counts` matching what the apply would write once those
  names exist.
- A dry run whose names all have proposals answers the same outcomes as an apply sent with those
  proposals as its table.
- The contract states how a name without an id is taken, and how the answer marks it.

## What this client removes once it lands

No workaround: this client waits for this ask before its sheet import's dry run shows the
engine's counts, rather than guessing them.
