# The reconciliation list reads a card statement as one row

Raised 2026-10-25.

## Why

A card statement is two reconciliations, one per currency, over the same days. The owner's list
of a card's statements shows **one row per statement**: its name, its days, each half's
difference, whether it is completed, half completed or a draft, and whether it is in order. Either
card account opens the same list, and a month that has only one half says so.

Today `GET /v1/reconciliations` takes one `account_id` and returns that account's
reconciliations only. Each names its other half (`twin_id`) and carries the statement's two
counts, but nothing of the other half itself: not its status, not its `difference_cents`, not
whether it exists when the item has no twin. So one read of the soles account cannot fill the
dollar difference, cannot tell "half completed" from "draft", and never sees a month whose only
half is on the dollar account. A client would read both accounts' lists and join them by
`twin_id` itself, which is two reads where the owner's check asks for one, and every client
would carry the same join.

## The ask

`GET /v1/reconciliations` can list a statement's halves together, in one page:

1. **Read by statement, not only by account**: for an account with a statement code, the list
   includes the reconciliations of every account sharing that code (the card's other currency),
   ordered by period, so either card account reads the same list. For example a parameter that
   asks for the account's whole statement set, or the list doing it whenever the account has a
   code; the shape is the engine's call.
2. **Each item carries what the row needs of its other half**, so a client never reads the twin
   to draw the row: the twin's `status` and `difference_cents` (and its `ending_balance_cents`,
   since a difference is blank until a balance is entered), or the twin itself embedded.
3. Paging and the count stay consistent with the new set, with a stated order.

## Done when

- One read from either account of a card lists every statement of the card once per half (or
  once per statement, if the engine prefers grouping), each item naming its twin's status and
  difference; the same read from the other account returns the same set.
- A month with only a dollar half appears in the read from the soles account.
- An account with no statement code reads exactly as today.
- The contract states the parameter (or behaviour), the order and the twin fields.

## What this client removes once it lands

Nothing to remove: without it the card's list cannot show one row per statement from one read
and would need a second read and its own join of the two accounts' lists. With it the list reads
one page.
