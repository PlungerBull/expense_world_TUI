# Give every business refusal of a delete or an opening balance a machine-readable reason

Raised 2026-10-14.

## Why

The contract tells clients to switch on `code` and `reasons`, never on wording (contract: "Base
Conventions", "`fields` and `reasons` semantics"). But `reasons` is `null` on every code except
`VALIDATION_ERROR` and `SETTINGS_MISSING`, so these refusals reach a client with nothing to switch
on but the status:

- `DELETE /v1/accounts/{account_id}` — `409` when the account still has transactions.
- `DELETE /v1/categories/{category_id}` — `409` when a transaction still uses it, `403` for a
  system category.
- `DELETE /v1/transactions/{transaction_id}` — `409` when the row sits in a completed
  reconciliation.
- `POST /v1/accounts/{account_id}/opening-balance` — `409` when the account already has an
  opening balance, and `409` when the `transaction_id` is taken.

A `409` on any of these can also mean an idempotency key reused with a different request
(contract: "Error codes"). So a client that tells the user what to do next ("archive it instead",
"revert the reconciliation to draft first", "it already has one: change it") has to guess which
rule fired from the status and the route. Every client (terminal, web, iOS) makes the same guess.

## The ask

Each business refusal above carries a reason a client can switch on, in the same shape the other
codes use, for example `HAS_TRANSACTIONS` (account, category), `SYSTEM_CATEGORY` (category),
`IN_COMPLETED_RECONCILIATION` (transaction), `OPENING_BALANCE_EXISTS` and `ID_TAKEN` (opening
balance). An idempotency-key reuse keeps a reason of its own, so it is never mistaken for one of
these. The names are yours to choose; each gets listed in the operation's `x-error-reasons`.

## Done when

Each refusal listed above returns a reason, the contract lists it on its operation, and no two
of them share one.

## What the CLI removes once it lands

The terminal client chooses its "what to do next" line from the HTTP status and the route. Once
this lands, it chooses by reason, and the status-and-route guess is deleted.
