# The sheet import's counts say how many sheet rows its split lines come from

Raised 2026-10-27.

## Why

A split purchase in the owner's sheet is several rows sharing one `COD_EECC`, and the sheet
import brings it in as one bank line with a part per row (contract: POST
/v1/transactions/import-sheet). Its answer's `counts` say how many such lines there are
(`split_lines`), but nothing in the answer says how many of the sheet's rows they hold: a row
carries no group key, and on a dry run a new row has no `bank_line_id` to group by.

The owner reads the dry run to check the sheet before the one-time official import, and wants
to see "split transactions 3 (8 rows)": three split purchases, made from eight sheet rows. It
tells them the grouping read the sheet as they meant it. A client could count rows sharing a
bank line only after an apply, never on the dry run, and the grouping is the engine's rule, so
each client counting it would copy that rule.

## The ask

`counts` carries the number of sheet rows the split lines are made from, on the dry run and the
apply alike, beside `split_lines`. Its name is the engine's call; `split_rows` would do.

## Done when

- A dry run of a sheet with three split purchases of eight rows in all answers `split_lines: 3`
  and the new count `8`, and its apply answers the same.
- A sheet with no split purchases answers `0` for both.
- The contract states the new count under the counts it documents.

## What this client removes once it lands

No workaround: until it lands, the sheet import's count line reads "split transactions 3" with no
row count, and gains "(8 rows)" once the engine sends it.
