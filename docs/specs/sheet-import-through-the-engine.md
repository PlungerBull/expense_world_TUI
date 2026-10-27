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

**Answered (owner, 2026-10-26), found in task 1:** a dry run sent before every name has an id
answers no counts, and the engine does not say which names only opening balances use, so the app
would create a `SALDO INICIAL` category no row needs. Both become engine asks, and task 2 waits
for them, so the dry run looks as the owner picked.

**The engine declined both asks on 2026-10-26**, with no contract change. Whether a row is an
opening balance depends on the account its name goes to, and on whether two of the sheet's
names go to one account, so the engine answers outcomes and counts only once every account,
category and hashtag the sheet uses has an id, and never guesses before. A dry run sent without
the table lists the names and the rows, with no outcomes and every count `0`. A category the app
creates for a name only opening balances use, like `SALDO INICIAL`, is an ordinary unused
category, which you may delete. So the dry run you picked (screen 1 A, with its counts) can only
show counts once every name exists.

**Answered (owner, 2026-10-27), question 4: C, a step of its own creates the names.** The dry
run never writes: while names are missing it lists them, with no counts, and says the command
that creates them; that step creates every missing account, category and hashtag (`SALDO
INICIAL` with the rest) and imports nothing; once every name exists, the dry run shows the
engine's counts; then `--apply` imports.

**Answered (owner, 2026-10-27), picks 1 and 2 and the screens:** the step is a flag on the same
command, `expense import sheet <file> --create-names` (1 A); `--apply` while names are still
missing is refused, writes nothing and names that step (2 A); and screens 1 to 5 of
[expense-world-sheet-import-engine.html](../mockups/expense-world-sheet-import-engine.html) are
approved as drawn.

**Answered (owner, 2026-10-27), found in task 2:** the engine sends how many split lines a sheet
makes but not how many of its rows they hold, so screens 3 and 4 read `split transactions 3`
without the mockup's `(8 rows)`. That count becomes the engine ask "The sheet import's counts say
how many sheet rows its split lines come from", and the `(N rows)` shows once it lands.

---

## Tasks

Approved by the owner on 2026-10-26.

Every task is done; the acceptance check runs next.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** item 2 of the hand-off (`0f7cdbe45cece354`); the range as a whole is confirmed in
  the reply "Caught up with contract 592f2467fa3df75a: the terminal app sends a bank download
  whole, …".
- **The engine's "Done when" checks to report on:** no code reads the sheet itself; the contract
  tests upload a made-up sheet with a dry run and an apply.
- **The asks it closes:** none. The engine declined "The sheet import's dry run counts the rows
  before every name has an id" and "The sheet import marks the names only opening balances use"
  on 2026-10-26; the reply says how the app shows the dry run without them.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **A comment in errors.py names the wrong function.** The comment above `_ENVELOPE_ERRORS` in
  [errors.py](../../expense/errors.py) says "EngineError stays a dedicated branch in render()";
  that branch lives in `json_body` and `exit_code_of`. (Task 2.)
- **The batch chunk size is reached only by tests.** `batch_write`'s `chunk_size` and
  `require_sendable_chunk_size` ([batch_write.py](../../expense/batch_write.py)) are reached
  only by tests now that the sheet import sends no batches; the LOG bar always uses the default.
  (Task 2.)
