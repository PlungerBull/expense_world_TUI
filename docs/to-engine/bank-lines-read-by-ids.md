# The bank-line list reads several lines by their ids in one call

Raised 2026-10-26.

## Why

Completing a statement answers `review_lines`: the ids of the bank lines the close flagged for
review, on each half (contract: POST /v1/reconciliations/{reconciliation_id}/complete). A
client shows the owner those lines, with their date, account, title and amount, so the owner
can decide what to do with each. Once the close is done, nothing lists them again:
`GET /bank-lines?unassigned_in_period_of=` lists none on a completed statement, so the ids are
all the client has.

Today the only way to read them is `GET /bank-lines/{bank_line_id}`, once per id. A close that
flags twenty lines costs twenty round trips before the screen can draw, and after the owner
edits or deletes one, the client reads every remaining id again to drop the ones that are gone.
Every client (terminal, web, iOS) would repeat that loop.

## The ask

A read of several bank lines by their ids in one call, for example
`GET /bank-lines?ids=<id>,<id>,…`, answering each line as `GET /bank-lines` lists it, in an
order the contract states (the close's own order, oldest first, fits the flagged lines). An id
naming a deleted line, or another user's, is left out of the answer, not a refusal, so a client
re-reading a list after a delete gets the lines that are still there. The contract states the
largest number of ids one call takes, and whether this filter combines with the others.

How it is shaped is the engine's call: a filter on the list, as above, or a list of the lines a
completed reconciliation's close flagged, would both do.

## Done when

- One call answers every live line among the ids sent, each in the list's shape, in the stated
  order, leaving out deleted and unknown ids.
- The contract states the order, the bound on the ids and how the filter combines with the
  others.

## What this client removes once it lands

The screen of a close's flagged lines reads each line by its own id, one call per line, and
reads them one by one again after each edit or delete. Both become one call.
