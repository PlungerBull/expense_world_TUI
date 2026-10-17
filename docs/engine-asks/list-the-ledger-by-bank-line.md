# The ledger can be read one bank line per row, with each line's parts inside

Raised 2026-10-17.

## Why

The owner's ledger shows a split purchase as **one row**: its title, date, account, total and
how many parts it has, with the parts shown only when the purchase is opened. Every other
transaction is a row as today.

`GET /transactions` lists parts, one row each. To draw the owner's ledger from it, a client has
to:

- group the parts on each page by `bank_line_id`;
- read every split line's figures separately (`GET /bank-lines/{id}`, one call per line today);
- merge the parts of a line that a page boundary cut in two, and hide the row it already drew;
- count purchases itself, since `GET /transactions/count` counts parts, so "10 of 133" is
  wrong as soon as one purchase is split.

That is list arithmetic the engine already knows how to do, and the web dashboard and iOS would
each rebuild it, subtly differently.

## The ask

1. **A list read with one row per live bank line**, in the ledger's default order, with the
   same cursor pagination as `GET /transactions` and a matching count. A page never cuts a
   line's parts in two.
2. **Each row carries** the line's `id`, `account_id`, `operation_code`, signed `net_cents`,
   `part_count`, and its parts as ordinary transaction responses, in the order
   `GET /transactions?bank_line_id=` lists them. A one-part line then draws as an ordinary
   transaction, and a split line takes its title, date and account from its parts, with no
   second read. This is the shape already agreed for an import's `unclaimed_lines`.
3. **Filters that apply to a whole line**: `account_id`, `date_from` / `date_to`, `search`, and
   `reconciliation_id` / `unreconciled` (a line is wholly in or out of a reconciliation; see the
   ask "a bank line is reconciled whole"). Filters by category or hashtag stay on
   `GET /transactions`, where each part is its own row: that is how the owner wants a ledger
   filtered by category to read.
4. The engine coders say whether this read makes the planned read of up to 200 bank lines per
   call unnecessary, or whether both are useful.

## Done when

- A ledger holding two single transactions and one line split 60 + 40 lists three rows and
  counts three; the split row carries `part_count` 2, `net_cents` -100 and both parts.
- With `limit=1`, paging through that ledger returns each line whole, on one page.
- `?account_id=` lists only the lines on that account; a date range lists the lines on those
  days.
- Splitting, editing or deleting a part changes the row on the next read.

## What this client removes once it lands

Nothing yet: the client has not built split display. Without this ask it would group parts by
bank line on each page, read each split line's figures one call at a time, and merge the parts
a page boundary cut in two; with it, the ledger draws one engine row per line.
