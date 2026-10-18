# The import answer names the reconciliation that stops a move to the bank's day

2026-10-18

## Why

When a file row matches a ledger line by operation code but a completed reconciliation stops
its move to the bank's day, the import answer's row carries `redate_blocked_by`, the
reconciliation's id (contract: POST /v1/transactions/import). The owner sees that row as
`✗ Not moved: Septiembre 2026 is reconciled`, so the client needs the reconciliation's name.

There is no `GET /v1/reconciliations/{id}`; reconciliations are listed one account at a time
(contract: GET /v1/reconciliations). So the client makes a second call, reads the account's
whole list, and looks the id up in it. That second read can fail when the import itself
answered, and then the row has to say "a reconciliation" instead of its name. Every client
would repeat the same extra read.

## The ask

Each row of the import answer whose move is stopped also carries the stopping reconciliation's
name, next to its id: for example `redate_blocked_by: { "id": "…", "name": "Septiembre 2026" }`,
or a sibling `redate_blocked_by_name`, whichever fits the contract's style. It applies to the
dry run and the apply alike.

## Done when

- A dry run and an apply with a move stopped by a completed reconciliation return that
  reconciliation's name on the row, matching the name `GET /v1/reconciliations?account_id=…`
  lists for it.
- A row whose move is not stopped carries no name (null, as `redate_blocked_by` is today).
- The contract states the field in the import's response.

## What this client removes once it lands

The extra read of the account's reconciliations during an import preview, and the fallback
wording for when that read fails.
