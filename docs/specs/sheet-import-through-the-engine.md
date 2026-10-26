# The sheet import goes through the engine

Catches up to contract `592f2467fa3df75a`, from `309e31fd5c266941`: item 2 of the engine's
hand-off of 2026-10-26, the new sheet import (`0f7cdbe45cece354`). It runs after
the catch-up of the bank download and closing a statement (done on 2026-10-26), which held
most of the rest of the hand-off.

**Status: approved, the current spec (owner, 2026-10-26).** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

`expense import sheet` is the door for your spreadsheet, and the official import goes through it
([before-the-official-import.md](before-the-official-import.md)). Today the app reads the sheet
itself: it parses every cell, groups split purchases by `COD_EECC`, finds opening balances,
skips zero rows and sends the rows in batches. That is the books' own logic, and it now lives in
the engine (contract: POST /v1/transactions/import-sheet): the engine reads the whole file,
matches every row against the ledger, and writes everything or nothing. The app's own reader
goes, so the web and iPhone apps never have to rebuild it.

The engine never looks up an account, category or hashtag by name, and never creates one. For
each name the sheet uses it proposes the one you already have under that name, if any; the
import is written only with a table you confirm, giving every name its account, category or
hashtag.

What changes for you, from the engine's rules:

- **The sheet must have exactly the engine's layout:** a sheet named `data`, the twelve headers
  from `description` to `COD_EECC` in order. Today the app accepts other spellings. The engine
  coders imported your whole sheet as it is on 2026-10-26, so it already fits.
- **One bad row stops the whole import**, every refusal listed by its row, and nothing is
  written. Today the bad rows are left out and the rest imports.
- **An opening balance is a row whose CATEGORY reads exactly `SALDO INICIAL`**; today a title
  reading so counts too, in any letter case.
- **Rows of zero are skipped and listed**, a row on a day a completed statement locks is listed
  as `sealed` and not created, and sending the same sheet again writes nothing.

## What it must do

1. **`expense import sheet <file>` sends the file to the engine** and shows its answer: a dry run
   unless `--apply` is passed, as today. The app reads no cell of the sheet; its reader goes,
   and so does `--chunk-size`, since the engine takes the sheet in one request.
2. **The dry run shows the names table**: every account (a name in one currency), category and
   hashtag the sheet uses, how many rows use it, and what it goes to: one you have, or none
   yet (question 1). Then the counts the engine sends: new, matched, sealed, skipped, opening
   balances and split purchases.
3. **The apply sends the confirmed table** (questions 1 and 2) and shows what was written.
4. **A refusal shows in the engine's words, by sheet row**, rows refused alike sharing one line,
   as the import's refusals read today ([commands.md](../commands.md) "`expense import sheet`").
5. **A live test imports a made-up sheet**, dry run and apply, then sends it again and sees
   nothing new. The sheet is made up: never your real one, since this repo is public.

## How the owner knows it is done

1. The dry run of a made-up sheet on the practice engine shows the names table and the counts.
2. Its apply writes it; a second apply writes nothing and shows every row matched.
3. A made-up sheet with one bad row is refused whole, naming the row, and nothing is written.
4. The unit suite and the live suite pass.

## Questions for the owner

**Answered (owner, 2026-10-26):** a name you don't have yet is created by the app at the apply
(question 1, A); running again with `--apply` is the confirmation (question 2, A);
`--account-name` stays, remembered for later runs (question 3, A); and a sheet account used in
two currencies becomes two accounts under the sheet's same name, one per currency, the currency
telling them apart (where today the app adds the currency to the name, `BCP Oro PEN`).

---

## Tasks

Approved by the owner on 2026-10-26.

1. **The sheet import's engine calls, in one shared home.** A module beside the command holds
   the request and answer of POST /v1/transactions/import-sheet (the file whole, in base64, as
   the bank import door sends a download) and the names table: each name the engine lists goes
   to its proposal, a renamed account (the `--account-name` flag, or the rename saved in
   `sheet_account_names`) to your account of that name and currency, and a name with neither to
   a new one. The apply runs a dry run first, so a refused sheet creates nothing; then it
   creates each new name through its own route (an account under the sheet's name and
   currency, or its rename; a category; a hashtag), then sends the table. Every write carries
   its idempotency key. Unit tests cover the table, the creates, each refusal it handles, and a
   refusal after a create. Nothing the user sees changes in this task.
2. **[UI] The command goes through the engine, and the old reader goes.** `expense import
   sheet` prints as screens 1 to 3 of
   [expense-world-sheet-import-engine.html](../mockups/expense-world-sheet-import-engine.html)
   draw, once the owner picks; `--json` prints the engine's answer, with the names the apply
   created. The app's own reader of the sheet goes with its tests (the parse, plan, apply,
   header aliases and currency-split naming), and so does `--chunk-size`; `openpyxl` leaves the
   app's dependencies and stays only for the tests that build made-up sheets.
   [commands.md](../commands.md) and [runtime.md](../runtime.md) say what the import does now.
   Waits on the owner's pick.
3. **A live test of the sheet import.** A made-up sheet on the practice engine: the dry run
   lists its names and counts; the apply writes it; a second apply writes nothing and every row
   comes back matched; a made-up sheet with one bad row is refused whole, naming the row, and
   nothing is written, no name included; a renamed account lands under its rename.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** item 2 of the hand-off (`0f7cdbe45cece354`); the range as a whole is confirmed in
  the reply "Caught up with contract 592f2467fa3df75a: the terminal app sends a bank download
  whole, …".
- **The engine's "Done when" checks to report on:** no code reads the sheet itself; the contract
  tests upload a made-up sheet with a dry run and an apply.
- **The asks it closes:** none; the sheet import is the owner's own work.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
