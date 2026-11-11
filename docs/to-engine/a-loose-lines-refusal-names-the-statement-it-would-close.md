# A loose-lines refusal names the statement it would close

Raised 2026-11-11.

## Why

A statement PDF's upload refused `LOOSE_LINES_ON_SEALED_DAYS` (dry run or apply) lists the
lines that refuse in `details.bank_line_ids`, and every client opens a screen to deal with them.
That screen's head says which month cannot close yet ("Can't close March 2026 yet"), because the
owner may be holding several papers. The refusal names no statement and no days: a client would
have to work the month out from the paper itself or from the lines' dates, an engine rule
re-implemented, and wrong on a paper whose days cross a month's end.

## The ask

1. **`details` on `LOOSE_LINES_ON_SEALED_DAYS` carries the statement the close or upload would
   close:** its name as the engine names statements (for example `March 2026`) and its days
   (`date_start`, `date_end`), on `POST /statements/import` (dry run and apply) and on
   `POST /statements/{id}/complete`.
2. **On an upload with no statement yet for that month,** the same fields for the statement the
   upload would make.
3. The contract states the fields beside `bank_line_ids` and `count`, in the published shape
   the ask "An error's `details` has a published shape for each refusal that carries one" asks
   for.

## Done when

- An upload's dry run refused for a loose line answers the statement's name and days in
  `details`, whether or not the statement exists yet.
- A close refused for a loose line answers the same for the statement being closed.

## What this client removes once it lands

Its leftover-lines screen reads "Can't close the statement yet" for an upload; with the name in
the refusal it reads "Can't close March 2026 yet", as every client will.
