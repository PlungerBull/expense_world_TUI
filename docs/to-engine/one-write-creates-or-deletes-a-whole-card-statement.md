# One write creates, or deletes, both halves of a card statement

Raised 2026-10-24.

## Why

A card statement is two reconciliations, one per currency, over exactly the same days, on the two
accounts sharing the statement code. The contract asks clients to guide the person so the two
halves are always created together, because a half created later, over the days of a completed
one, cannot complete until the completed one is reverted and the whole order is sent again.

The owner chose one form that makes both halves: the name and days typed once, then each half's
balances. Today that is two `POST /v1/reconciliations`. If the second is refused (a balance the
engine refuses, `STATEMENT_MONTH_TAKEN` on the other account, a lost connection), the first half
stands alone: exactly the state the contract asks clients to avoid. Deleting a card statement has
the same problem the other way: two `DELETE /v1/reconciliations/{id}`, and a half can be left
behind. Every client would have to detect and explain a half-made or half-deleted statement.

## The ask

1. **Create both halves in one write.** A way to create a card statement's two reconciliations
   together (for example `POST /v1/reconciliations` taking the second account and its balances,
   or a statement-level route; the shape is yours): one name and one `date_start`..`date_end`,
   and per account its `account_id` and balances. All or nothing: each half is checked as
   `POST /v1/reconciliations` checks one today, every refusal reported in one answer keyed to the
   half it concerns, and nothing written on any refusal. Standard idempotency. The answer carries
   both reconciliations.
2. **Delete both halves in one write.** A way to delete a card statement's two reconciliations
   together, from either half: all or nothing, with each half's checks as
   `DELETE /v1/reconciliations/{id}` applies them today (a completed half refused as there), the
   refusal naming the half it concerns. Standard idempotency.

A reconciliation with no other half keeps working exactly as today on both routes.

## Done when

- One write creates a PEN and a USD reconciliation over the same days on the two accounts sharing
  a code; both read back, each naming the other as its other half once "A reconciliation names
  its statement's other half and whether it is ordered" lands.
- When either half would be refused (for example the USD account already has a statement ending
  that month), nothing is created, and the refusal names the USD half.
- One write deletes both halves, from either half's id; when one half cannot be deleted, neither
  is, and the refusal names that half.
- A replay under the same idempotency key changes nothing more.
- The contract states both writes, their keys and their refusals.

## What this client removes once it lands

The card statement's create form and its delete send one write each instead of two, and no
longer need to tell the person that only one half was created or deleted, or offer to finish the
other half by hand.
