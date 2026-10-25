# A reconciliation names its statement's other half and whether the statement is ordered

Raised 2026-10-24; revised 2026-10-24 with the engine coders' fix (a second count, for places held
twice).

## Why

A card statement is two reconciliations, one per currency, over the same days, and it completes
only once every line of both halves has a place and no place is held by two lines. A client
listing an account's reconciliations wants to show a card statement as one statement and say,
before the person presses complete, whether it still needs putting in order.

Today `ReconciliationResponse` says neither. The only way to learn a reconciliation's other half
is `GET /v1/reconciliations/{id}/statement-order`, one read per reconciliation listed, and the only
way to learn whether it is ordered is the same read, counting `unplaced` and looking for a place
held twice. The alternative, pairing halves in the client by statement code and days, copies the
engine's own pairing rule into every client, and drifts the day the rule changes.

## The ask

On every reconciliation response (`GET /v1/reconciliations`, `GET /v1/reconciliations/{id}`, and
every write that answers with a reconciliation):

1. **`twin_id`**: the other half of its statement (the reconciliation on the other live account
   sharing the statement code, over exactly the same days), `null` when there is none.
2. **`unplaced_count`**: how many live lines of the statement (both halves, opening balances
   excepted) have no place.
3. **A count of places held by two or more lines** (for example `shared_place_count`; the name is
   yours).

Both counts read `null` on an account without a statement code, since there is no order there.
When both read `0`, the order is complete: `POST …/complete` will not refuse
`STATEMENT_NOT_ORDERED`.

## Done when

- A card's PEN and USD reconciliations over the same days each read the other's id as `twin_id`;
  a USD one over other days reads `null`.
- A statement with 2 lines unplaced and place 4 held by two lines reads `unplaced_count: 2` and a
  shared-place count of `1` on both halves, and completing is refused as unordered.
- A statement with 0 lines unplaced but place 4 still held twice reads `unplaced_count: 0` and a
  shared-place count of `1`, and completing is still refused as unordered.
- Once the order is sent with every line placed once, both counts read `0` on both halves, and
  completing is not refused as unordered.
- An account without a statement code reads `twin_id: null` and both counts `null`.
- `GET /v1/reconciliations?account_id=…` returns all three fields with no extra read per row.

## What this client removes once it lands

The reconciliation list reads one page and shows each card statement as one, with whether it
needs ordering, instead of reading every statement's order to find its other half, its unplaced
lines and its places held twice.
