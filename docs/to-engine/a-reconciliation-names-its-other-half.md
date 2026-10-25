# A reconciliation names its statement's other half and whether the statement is ordered

Raised 2026-10-24.

## Why

A card statement is two reconciliations, one per currency, over the same days, and it completes
only once every line of both halves has a place. A client listing an account's reconciliations
wants to show a card statement as one statement and say, before the person presses complete,
whether it still needs putting in order.

Today `ReconciliationResponse` says neither. The only way to learn a reconciliation's other half
is `GET /v1/reconciliations/{id}/statement-order`, one read per reconciliation listed, and the only
way to learn whether it is ordered is the same read, counting `unplaced` and looking for a place
held twice. The alternative, pairing halves in the client by statement code and days, copies the
engine's own twin rule into every client, and drifts the day the rule changes.

## The ask

On every reconciliation response (`GET /v1/reconciliations`, `GET /v1/reconciliations/{id}`, and
every write that answers with a reconciliation):

1. **`twin_id`**: the other half of its statement (the reconciliation on the other live account
   sharing the statement code, over exactly the same days), `null` when there is none.
2. **`unplaced_count`**: how many live lines of the statement (both halves, opening balances
   excepted) have no place, `null` on an account without a statement code. With a place held
   twice counted too, or a separate field for it, so that `0` means `POST …/complete` will not
   refuse `STATEMENT_NOT_ORDERED`.

## Done when

- A card's PEN and USD reconciliations over the same days each read the other's id as `twin_id`;
  a USD one over other days reads `null`.
- A statement with 3 lines unplaced reads `unplaced_count: 3` on both halves; after the order is
  sent it reads `0`, and completing is not refused as unordered.
- An account without a statement code reads `twin_id: null` and `unplaced_count: null`.
- `GET /v1/reconciliations?account_id=…` returns both fields with no extra read per row.

## What this client removes once it lands

The reconciliation list reads one page and shows each card statement as one, with whether it
needs ordering, instead of reading every statement's order to find its other half and its
unplaced lines.
