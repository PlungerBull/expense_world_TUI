# The sheet import goes through the engine

Catches up to contract `592f2467fa3df75a`, from `309e31fd5c266941`: item 2 of the engine's
hand-off of 2026-10-26, the new sheet import (`0f7cdbe45cece354`). The rest of the hand-off is in
[catch-up-bank-download-and-closing.md](catch-up-bank-download-and-closing.md), which runs first.

**Status: draft, for the owner to rewrite or approve; questions 1 to 3 wait on the owner. Its
tasks are drafted when the owner names it the current spec.** When done, the why moves to
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

1. **Names you don't have yet.** On the official import, onto an empty ledger, every name is new.
   - **A.** The app creates them at the apply, as today (an account under its name and
     currency, a category, a hashtag), then sends the table.
   - **B.** The import stops and lists them; you create each one in the app, then run it again.

   **Recommended:** A, because the official import would otherwise mean creating every account,
   category and hashtag by hand first.
2. **Confirming the table.**
   - **A.** The dry run prints the table; running it again with `--apply` is your confirmation.
     A name goes somewhere other than the engine's proposal only through `--account-name`
     (question 3).
   - **B.** The apply asks you name by name in the terminal.

   **Recommended:** A, because the import runs once, and the dry run already shows every match.
3. **Renaming an account as it comes in** (`--account-name "BCP:PEN=Sueldo Soles"`, remembered
   for later runs).
   - **A.** Keep it: it says which account a sheet name and currency goes to, created under that
     name when you don't have it.
   - **B.** Drop it: the accounts come in under the sheet's names, and you rename them in the app
     afterwards.

   **Recommended:** A, because the official import's plan renames the four BCP accounts this way
   ([before-the-official-import.md](before-the-official-import.md) "Decided").

---

## Tasks

Drafted when the owner names this the current spec.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** item 2 of the hand-off (`0f7cdbe45cece354`); the range as a whole is confirmed in
  the reply of [catch-up-bank-download-and-closing.md](catch-up-bank-download-and-closing.md).
- **The engine's "Done when" checks to report on:** no code reads the sheet itself; the contract
  tests upload a made-up sheet with a dry run and an apply.
- **The asks it closes:** none; the sheet import is the owner's own work.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
