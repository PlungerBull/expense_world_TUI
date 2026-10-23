# Changing a line field answers with every part it moved and whether each left its reconciliation

Raised 2026-10-23.

## Why

A client moving transactions to another account (`PUT /transactions/{id}` with `account_id`,
plus `reconciliation_id: null` when the row is assigned) tells the person what the write did,
for example `2 rows → BCP Oro PEN · 2 left their reconciliation`.

A line field changes every live part of the bank line in the same write ("Line fields", "Bank
lines"). But the answer is only the transaction named by `{id}`. So a client moving one part of a
60 + 40 split cannot tell that two rows moved, or that both left their reconciliation. It reports
one.

The same happens when a person selects both parts of one line and moves them: the second `PUT`
writes nothing, because "A part that already has the value sent is not written", but it still
answers 200 like a real move. The client counts it twice.

The only way for the client to know is to read the line (`GET /bank-lines/{id}`) before or after
each move. That adds a round trip per row and can race with other writes. Only the engine knows
which parts its write changed, and every client that shows the outcome of a move needs the same
answer.

## The ask

1. **The `PUT /transactions/{id}` answer says which parts the write changed.** It keeps the
   transaction named by `{id}` as it is today, and adds the line's parts that this write changed,
   `{id}` included when it changed. Each part comes as a transaction, or at least as its `id`.
2. **Each changed part says whether this write took it out of a reconciliation:** it was assigned
   before the write, and is in none after it, or in another one. One way is each part's
   `reconciliation_id` before and after; another is a flag such as `left_reconciliation`.
3. **A part the write did not change is not listed.** A second `PUT` sending the value a part
   already has, including the other part of a line already moved, lists nothing, so a client
   counts each moved row once.
4. **The same holds for every line field:** `title`, `date`, `account_id`, `operation_code`,
   `statement_line` and `reconciliation_id`. An empty body, or a body changing only
   `amount_cents`, `category_id`, `description` or `hashtag_ids`, lists at most `{id}`.
5. **An idempotent replay answers exactly as the first request did.**

## Done when

- Moving one part of a 60 + 40 line to another account, with `reconciliation_id: null` while the
  line is in a draft reconciliation, answers with both parts listed as changed and both marked as
  having left their reconciliation.
- Then sending the same `account_id` on the other part answers with no part changed.
- Moving a one-part line answers with that one part, marked as having left its reconciliation
  only if it was assigned.
- A move of a line in no reconciliation lists its parts with none marked as having left one.
- A replay with the same idempotency key returns the first answer, lists included.

## What this client removes once it lands

Today the note after a bulk account move, and the Edit form's "It left its reconciliation",
count one row per request sent. They decide "left its reconciliation" from the list read before
the move, so a split line's other parts go uncounted, and two parts of one line can be counted
twice. With this ask, both notes count what the engine's answer lists, and the client never reads
the line again to find out.
