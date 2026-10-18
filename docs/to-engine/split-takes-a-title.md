# Splitting a transaction can also change its title, in the same write

2026-10-18

## Why

The owner splits a transaction and often renames it in the same moment: a bank line
`TOTTUS JOCKEY PLAZA -100.00` becomes two parts, and the owner wants its title to read
`Tottus — semana` while doing it. A title belongs to the transaction, so it is the same on every
part.

`POST /v1/transactions/{transaction_id}/split` takes each part's amount, category, note and
hashtags, but no title (contract: POST /v1/transactions/{transaction_id}/split). The only way
for a client to rename is a second write after the split, a `PUT` on one part, which the engine
carries to every part. Two writes are not one: the split can land and the rename fail, leaving
the owner with a half-done change, and every client would repeat that two-step dance.

## The ask

`POST /v1/transactions/{transaction_id}/split` accepts an optional `title` at the top level of
the body, next to `parts`.

- When present, every part the split leaves carries that title, in the same write as the split.
- When absent, every part keeps the transaction's current title, as today.
- It is checked like a title on `PUT /v1/transactions/{id}` (same length limit, same refusal
  shape), and a refused title refuses the whole split, keyed `title`.
- The idempotency replay covers it like the rest of the body.

## Done when

- A split with `title` returns parts that all carry that title, and a `GET` of the bank line
  shows it on every part.
- A split without `title` leaves the title as it was.
- A split with an invalid title is refused whole: nothing is split, and the error names
  `title`.
- The contract states the field in the split's operation.

## What this client removes once it lands

Nothing to remove: until it lands, the split screen shows the transaction's title but cannot
change it. Once it lands, the title becomes a field on that screen, sent with the split in one
write.
