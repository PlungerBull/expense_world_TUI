# A create whose `id` is already in the ledger answers `ID_EXISTS` on that id before any other conflict

Raised 2026-10-21, against contract `fab230c456c2dba2`.

## Why

A client knows that a create it sends again already landed only from `409 ID_EXISTS` on the
item's own `id`. It sends a create again in two cases. A write that timed out or answered 5xx is
retried with the same ids. A sheet import run a second time sends every row with the id it got the
first time, and each row that is already there must count as "already there", not as failed.

Since the statement line arrived, the engine checks a taken `statement_line` before a taken `id`.
Against the practice engine on 2026-10-21, `POST /v1/transactions/batch` with two items sharing
`line_group` and `statement_line` `PRB-3db15602-001`, and one item with `statement_line`
`PRB-3db15602-002`, answered `201`. The same three items sent again, with the same ids, answered:

```
409 {"error": {"code": "CONFLICT",
  "message": "Another bank line already has statement line 'PRB-3db15602-001'.",
  "fields": {"transactions.0.statement_line": "Must not be a statement line another bank line already has."},
  "reasons": {"transactions.0.statement_line": "STATEMENT_LINE_EXISTS"}}}
```

These got the same answer, never `ID_EXISTS`: the group alone, the group in reverse order, and the
single coded item alone (a one-item batch). Its own line is the one holding the statement line,
so the answer reports a conflict with itself. The contract says "Only the first such item in
request order is named" (POST /v1/transactions/batch), but not which reason wins when one item
breaks two rules.

In the owner's sheet nearly every row carries a statement line, so a second run of the sheet
import, or a retry of a batch that landed but timed out, reports those rows as failed. The only
way a client could tell its own row from someone else's is to read `GET /v1/transactions/{id}`
after every `STATEMENT_LINE_EXISTS`: one more round trip per row, repeated in every client.

## The ask

On every create that takes a client `id` (`POST /v1/transactions` and each item of
`POST /v1/transactions/batch`), check a taken `id` before every other conflict, the
`OPERATION_CODE_EXISTS` and `STATEMENT_LINE_EXISTS` `409`s included. An item whose `id` is
already in the ledger then always answers `409 ID_EXISTS` on that id (`id`, or
`transactions.<i>.id` in a batch), whatever else it repeats. State the order in the contract, next
to "Only the first such item in request order is named".

In a batch whose items are a `line_group`, the same holds for every item of the group: the group
sent again answers `ID_EXISTS` on its first item's id.

## Done when

1. A batch item, grouped or not, whose `id` already exists and whose `statement_line` is the one
   its own line holds answers `409 ID_EXISTS` on `transactions.<i>.id`.
2. The same holds for `operation_code`, and for `POST /v1/transactions`.
3. A new `id` with a `statement_line` another line holds still answers `STATEMENT_LINE_EXISTS`.
4. The contract states which reason wins.

## What this client removes once it lands

Nothing. The client already treats `ID_EXISTS` on its own id as "already there". Until the order
changes, the sheet import cannot send statement lines without breaking its re-run and its retry,
so the client's half of statement lines waits for this.
