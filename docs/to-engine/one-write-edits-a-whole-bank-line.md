# One write edits a whole bank line: its line fields and its full set of parts

Raised 2026-10-24.

## Why

A client edits a bank line on one form: its line fields at the top (title, date, account,
operation code) and its parts below, each with its own amount, category, hashtags and
description. The person can add a part, drop one, or drop all but one. They press save once.

Today one save can need several writes, none atomic with the others:

- **Line fields and parts changed together** need `PUT /v1/transactions/{id}` for the date,
  account or operation code, then `POST /v1/transactions/{id}/split` for the parts. The split takes
  `title` but forbids `date`, `account_id` and `operation_code`. If the second write is refused,
  the line is half saved.
- **Changing the total and re-splitting** in one save means a `PUT` of `amount_cents` on one part
  first, because "The total is kept" holds on the split. Then comes the split. That is two writes
  again.
- **Going back to one part** is not a split: `parts` must hold 2 to 500 parts. It needs a `DELETE`
  of each part that goes and a `PUT` of the amount on the one that stays. That is several writes,
  and between them the line's total is wrong.
- **Changing only a category or a description on two parts** is either one `PUT` per part (not
  atomic), or a split. A split soft-deletes every part and creates new ones with new ids, so a
  one-word fix deletes and recreates every part and writes a deleted and a created entry in the
  activity log for each.

Every client with a line editor (this one, then web and iOS) would rebuild the same sequence of
writes, with the same half-saved states and rollback problems. Only the engine can apply the
whole edit as one change.

## The ask

1. **`PUT /v1/bank-lines/{bank_line_id}`** edits the line in one atomic write. The body holds any
   of the line fields `title`, `date`, `account_id`, `operation_code`, `statement_line` and
   `reconciliation_id`, under the rules `PUT /v1/transactions/{id}` applies to them today (Line
   fields, Field locking, Archived accounts, Sealed periods, Reconciliations → Assigning
   transactions). It also holds an optional `parts`.
2. **`parts`, when sent, is the line's complete new set, 1 to 500 parts.** Each part carries `id`,
   signed `amount_cents`, and optionally `category_id`, `description` and `hashtag_ids`, as a split
   part does today.
   - A part whose `id` is a live part of this line is **updated in place**. It keeps its id, and
     its version and activity log follow `PUT /v1/transactions/{id}`. A part sent unchanged is not
     written.
   - A part with a new client `id` is **created** on the line. It takes the line's fields and its
     reconciliation, as a split part does.
   - A live part of the line that is not in `parts` is **deleted**.
   - `parts` omitted leaves the parts as they are.
3. **The total.** Outside a completed reconciliation, the parts may add up to a new total. Inside
   one, they must add up to the line's current total, as a split requires today, and the line
   fields stay locked as Field locking says. Redistributing amounts, adding a part and dropping a
   part stay allowed there, as a split is.
4. **All or nothing.** Every refusal is reported together where the rules allow, keyed by the
   field sent, for example `title` or `parts.<i>.amount_cents`, using the reasons the transaction
   and split routes use today. If anything is refused, nothing is written.
5. **The answer** is the line as `GET /v1/bank-lines/{id}` returns it after the write. Beside it
   comes `changed_parts` as `PUT /v1/transactions/{id}` answers today, plus the ids of the parts
   created and of those deleted. An idempotent replay answers exactly as the first request did.
6. Opening-balance lines follow "Opening balances stay put", and `parts` on one holding an opening
   balance is refused, as a split is.

## Done when

- One `PUT` that changes the date and re-splits 60 + 40 into 70 + 30 changes both, keeps both
  parts' ids, and writes nothing if either is refused.
- One `PUT` on a 60 + 40 line sending a single part of 100, the first part's id, leaves one part
  of 100 with that id and the other part deleted, in one write.
- One `PUT` adding a third part with a new id, outside a completed reconciliation, may change the
  total; inside one, a changed total is refused with nothing written.
- One `PUT` changing only the second part's category writes only that part, and its id stays.
- In a completed reconciliation, a `title` change is refused as locked, and a redistribution of
  the amounts with the same total is accepted.
- A replay with the same idempotency key answers as the first request did.

## What this client removes once it lands

The line editor sends one write per save instead of a chain: no line-field write followed by a
split, no amount change before a re-split, and no deleting parts one by one to get back to a
single part. A save is never half applied, so the editor needs no state for "saved the top but
not the parts". A one-word fix on a part no longer recreates every part.
