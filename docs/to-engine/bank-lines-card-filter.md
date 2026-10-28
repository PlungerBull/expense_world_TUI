# List a card's bank lines in no statement in one read

Raised 2026-10-27.

## Why

A statement covers its whole card: "It is created with a balance for every live account of its
card" (contract: "Statements", "A statement covers its whole card"). A client closing a card's
month by hand shows the owner the card's lines in no statement, to pick into the draft. Those
are the lines of every account of the card, both currencies together.

`GET /bank-lines` cannot list them in one read. Its filters are `sort`, `after`, `limit`,
`account_id`, `statement_id`, `unreconciled`, `date_from`, `date_to`,
`unassigned_in_period_of` and `ids`; `GET /bank-lines/count` takes the same filters but the
paging ones. None of them names a card:

- `?unreconciled=true&account_id=<id>` lists one account's lines in no statement, so a
  two-currency card takes two reads.
- `?unassigned_in_period_of=<statement id>` spans every account of the card, but only the days
  of the statement's review list, and only with `sort=statement`.

So a client lists a card's leftovers by reading each account's list and merging them itself:
two cursor-paged lists merged by date on the client, one count per account added up, and the
merge redone whenever either list grows. Each of the four clients would write that merge, and
an order merged on the client drifts from the engine's own (`date_desc`, `date_asc` and their
tie-breaks under *Ordering*).

## The ask

A `?card_id=<card id>` filter on `GET /bank-lines` and `GET /bank-lines/count`: the lines on any
live account of that card. It combines with `unreconciled`, `date_from`, `date_to` and every
`sort` the other filters take, and pages by cursor like every filter. A card id naming no live
card of the caller's is refused as `account_id` is refused for an unknown account. Whether it
combines with `account_id` (both apply, or the pair is refused as conflicting) is the engine's
call; the contract says which.

## Done when

- `GET /bank-lines?card_id=<id>&unreconciled=true&sort=date_asc` lists a two-currency card's
  lines in no statement, both currencies together, oldest first, paged by cursor.
- `GET /bank-lines/count?card_id=<id>&unreconciled=true` counts the same lines.
- The contract states the filter, its refusals and how it combines with the others.

## What this client removes once it lands

The one read per account of a card, the merge of the two lists by date on the client, and the
count added up from each account's count, for the list of a card's lines in no statement.
