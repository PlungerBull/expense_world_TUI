# Saving a card statement's form writes both halves' balances in one write

Raised 2026-10-25.

## Why

A card statement is two reconciliations, one per currency. The owner fixes a statement on one
form: its name, its days, and each half's begin and end balance (soles and dollars). Renaming it
or moving its days is already one write on either half, which writes both halves.

Balances are not: `PUT /v1/reconciliations/{reconciliation_id}` writes `beginning_balance_cents`
and `ending_balance_cents` to the half the path names only, and an unknown field is `422`, so
there is no way to send the other half's balances in the same write. A save that changes both
halves' balances (a mistyped soles begin balance and the dollar end balance from the paper) is two
writes. If the second is refused (the statement completed meanwhile, a concurrent change), the
first stays written and the statement is half saved. Every client with this form would carry the
same two-write chain and the same partial-save handling.

## The ask

`PUT /v1/reconciliations/{reconciliation_id}` on either half of a card also takes the other half's
balances in the same write, for example `twin.beginning_balance_cents` and
`twin.ending_balance_cents`, with the same rules each half's own balances follow (`NOT_NULL` on a
begin balance, `null` allowed on an end balance, `LOCKED` on a completed half), refused under the
`twin.` key as complete and delete already do, all or nothing. On a reconciliation with no twin,
a `twin.` field is refused as it is today.

## Done when

- One `PUT` on the soles half sending its own begin balance and `twin.ending_balance_cents`
  writes both halves in one write; each half's version bumps by one, with one activity entry each.
- The same from the dollar half writes the same.
- A `twin.` balance refused (`LOCKED` on a completed half, `NOT_NULL`) writes nothing on either
  half, keyed `twin.<field>`.
- A `twin.` balance on a reconciliation with no twin is refused, writing nothing.
- A replay under the same idempotency key answers the same and writes once.
- The contract states the fields and their refusals.

## What this client removes once it lands

Nothing to remove: without it the statement's edit form would save in two writes and handle a
half-saved statement. With it the form saves in one write, and a refused save changes nothing.
