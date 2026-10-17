# Deleting a bank line deletes every one of its parts, in one write

Raised 2026-10-17.

## Why

In the owner's ledger a split purchase is one row, and deleting it deletes the whole purchase:
every part. Today the engine deletes one transaction per call (`DELETE /transactions/{id}`), so
a client deleting a purchase of three parts sends three deletes. When one of them fails (a part
the engine refuses, a dropped connection), the purchase is left half deleted: its total changes
without anyone choosing it, and the next bank upload of that period reports the day as
disagreeing.

All or nothing is a property only the engine can give, and every client that shows a split
purchase as one row needs it.

## The ask

1. **`DELETE /bank-lines/{id}`** soft-deletes every live part of the line in one write, all or
   nothing.
2. **The same rules as deleting a transaction, checked on every part before anything changes**:
   a line in a completed reconciliation is refused (`409`, `IN_COMPLETED_RECONCILIATION`), and
   so is any other case `DELETE /transactions/{id}` refuses.
3. **The response** lists the deleted parts, as `DELETE /transactions/{id}` returns its row.
4. The line releases its `operation_code`, as it does today when its last part is deleted, and
   the account's balance drops the whole line at once.
5. An unknown or already deleted line is `404`; a repeated request with the same idempotency key
   replays the first answer.

## Done when

- Deleting a 60 + 40 line leaves neither part live, `GET /bank-lines/{id}` is `404`, and the
  account's balance rises by 100 in one step.
- Deleting a line in a completed reconciliation is refused, and both parts are still there.
- A one-part line deletes exactly like `DELETE /transactions/{id}` on its transaction.

## What this client removes once it lands

Nothing yet: the client has not built split display. Without this ask, deleting a purchase from
its ledger row would send one delete per part and could leave half a purchase; with it, the row
is deleted in one call.
