# A bank import's unclaimed ledger lines carry their title, amount and parts' details

Raised 2026-10-16.

## Why

`POST /transactions/import` reports each day whose file total and ledger total disagree, with
`unclaimed_lines: [{bank_line_id, transaction_ids}]`: the ledger lines on that day the file did
not claim. To fix the day, the owner has to see what those lines are — their title and amount —
next to the file rows that were not found. With only ids, a client makes one read per
transaction to draw the list, which multiplies round trips on exactly the screen where the owner
is comparing the bank to the ledger. Every client that shows the report needs the same details.

## The ask

1. Each entry of `unclaimed_lines` carries the line's `title`, its signed total (`net_cents`,
   inflow positive, outflow negative, like the day's totals) and its parts, each with
   `transaction_id`, signed `amount_cents`, `category_id` and `description`.
2. The figures are those of the ledger after the import, like the day's `ledger_net_cents`.

## Done when

- A dry run with a ledger line the file does not claim reports that line with its title, signed
  total and parts, and the line's total plus the matched rows equals the day's
  `ledger_net_cents`.
- A split line reports one entry with both parts listed.

## What this client removes once it lands

Nothing yet: the client has not built the days-that-disagree view. Without this ask it would
read each unclaimed transaction by id to show its title and amount; with it, the view draws from
the import answer alone.
