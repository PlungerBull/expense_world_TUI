# Let a client read a bank line: its parts, its total and its part count

Raised 2026-10-16.

## Why

A transaction now carries `bank_line_id`, but nothing else about its line. To show the parts of
one purchase together, to open a re-split with the line's current parts, or to tell the owner
that a field change reaches "every part", a client needs three things the engine does not give:

- **which transactions are the line's parts.** There is no filter by `bank_line_id`, so a client
  has to search the ledger around the date and hope every part is on the page it loaded;
- **the line's total**, which every split must match. A client would add up the parts it found,
  which is balance math the engine already does and gets wrong when a part is missing;
- **how many parts the line has**, to know whether a row is a part at all.

Every client that shows splits (this one, the web dashboard, iOS) meets the same gap, and each
would rebuild the same search and the same sum, subtly differently.

## The ask

1. **`GET /transactions?bank_line_id=<id>`** lists exactly the line's live parts, in a stable
   order, with the usual pagination and response shape.
2. **Every transaction response carries its line's figures**: the line's signed total
   (`bank_line_total_cents`, or a nested `bank_line` object) and its live part count, on the same
   routes that carry `bank_line_id` today.
3. Both follow the line as parts are split, edited and deleted, as `bank_line_id` already does.

## Done when

- Splitting a transaction into 60 + 40 and listing `?bank_line_id=` returns exactly those two
  parts, each carrying the line total 100 and part count 2.
- A single transaction carries part count 1 and its own amount as the line total.
- Deleting one part leaves the other carrying part count 1 and the new total.
- The filter combines with the existing ledger filters and pagination.

## What this client removes once it lands

Nothing yet: the client has not built split display. Without this ask it would search the
ledger around each part's date to find its siblings and add their amounts itself; with it, the
ledger groups parts by the engine's figures and a re-split opens with the engine's list.
