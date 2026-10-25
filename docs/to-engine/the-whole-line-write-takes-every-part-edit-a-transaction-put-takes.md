# The whole-line write takes every part edit that PUT /transactions/{id} takes

Raised 2026-10-25.

## Why

A line editor saves a whole bank line in one `PUT /v1/bank-lines/{id}`: the line fields and
the complete set of parts. Two kinds of line refuse `parts` outright, even when the edit is one
`PUT /v1/transactions/{id}` that would be accepted on the same part:

- **A line with a part on an archived account** refuses `parts` with `ACCOUNT_ARCHIVED`. But
  `PUT /v1/transactions/{id}` accepts a new category, hashtags and description on that same part
  (*Archived accounts*).
- **A line holding an opening balance** refuses `parts` with `OPENING_BALANCE_NOT_SPLIT`. But
  `PUT /v1/transactions/{id}` accepts a new amount and description on its one part (*Opening
  balances stay put*).

So the client has to pick its route by the kind of line, which copies those two rules. And on an
archived account's split line, putting two parts into new categories takes two writes, one per
part. That save is not atomic: if the second write is refused, the first part has its new
category and the second does not. Every client with a line editor would build the same switch
and the same chain of writes.

## The ask

On those two kinds of line, `PUT /v1/bank-lines/{id}` accepts `parts` when it changes only
what `PUT /v1/transactions/{id}` would accept on each part:

1. **The same set of parts**: every id a live part of this line, none left out. No part is
   created or deleted.
2. **On each part, only the fields its rules leave open**: on an archived account's line, its
   `category_id`, `hashtag_ids` and `description`, with its `amount_cents` sent as it is. On an
   opening balance's line, its `amount_cents` and `description`.
3. Anything else stays refused with today's reasons and keys (`ACCOUNT_ARCHIVED`,
   `OPENING_BALANCE_NOT_SPLIT`, `OPENING_BALANCE_CATEGORY_FIXED`, `OPENING_BALANCE_NOT_TAGGED`,
   keyed `parts` or `parts.<i>.<field>`), all or nothing, as every whole-line write is.

## Done when

- One `PUT /v1/bank-lines/{id}` on an archived account's 60 + 40 line, giving both parts new
  categories, writes both in one write and keeps both ids. A changed amount, a new part or a
  dropped part there is still `ACCOUNT_ARCHIVED`, with nothing written.
- One `PUT /v1/bank-lines/{id}` on an opening balance's line, sending its one part with a new
  amount and description, writes them. A second part is still `OPENING_BALANCE_NOT_SPLIT`, and a
  new category on its part is refused as `PUT /v1/transactions/{id}` refuses it.
- A replay with the same idempotency key answers as the first request did.

## What this client removes once it lands

The line editor sends every save through `PUT /v1/bank-lines/{id}`. It no longer switches to
`PUT /v1/transactions/{id}` for an archived account's line or an opening balance, and it no
longer sends one write per part when two parts of an archived account's line change together.
