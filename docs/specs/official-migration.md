# Move the official data into the app

**Status: draft, deferred.** The loop does not start on it until the owner says so; its open
questions are in [todo.md](../todo.md) "Waiting on you".
Background and the engine's rules: [file-import-plan.md](../file-import-plan.md) §6 and §10.
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## What it must do

The updated spreadsheet becomes the ledger of record, and 2026 is brought in line with the bank,
ready for bank files to take over.

The owner wipes the live database and imports the updated sheet once, onto an empty ledger.
Nothing typed into the app before the wipe is kept.

- The BCP accounts carry the bank's names: `Sueldo Soles`, `Cuenta Digital Dólares`,
  `VISA Infinite Sapphire PEN`, `VISA Infinite Sapphire USD` (the sheet import's
  `--account-name`, [commands.md](../commands.md) "Renaming an account leg").
- `PENDIENTE` means "not classified yet", on the category and on the hashtag alike. No
  `PENDIENTE` or `PENDIENTES` category or hashtag is created: a row whose category carries that
  name goes to the built-in `@Pendiente` category, a row whose hashtag carries it goes to the
  built-in pending hashtag, and the other side keeps its own value. The sheet stays as it is and
  a re-run never brings the names back. The app finds the pending hashtag through
  [bank-lines-and-pending-hashtag.md](bank-lines-and-pending-hashtag.md).
- The sheet comes in as it is: one transaction per row. Rows split from one bank purchase are
  not grouped; how to mark them is decided later. Everything up to 31-Dec-2025 is accepted as
  imported.
- 2026 is checked month by month against the bank statements (EECC). For each month, in order,
  the owner uploads that month's statement: rows the ledger already has take the bank's code and
  wording, missing ones are added, and the days whose totals disagree show where a split or a
  duplicate needs fixing by hand. Then the owner completes that month's reconciliation, which
  seals it, and moves to the next month.
- The month-by-month check needs the bank upload of
  [bank-lines-and-pending-hashtag.md](bank-lines-and-pending-hashtag.md).

Everything that writes to the real ledger is run or approved by the owner.

## How the owner knows it is done

1. The import's dry run lists the four renamed accounts and no `PENDIENTES`; `--apply` finishes
   with no failures.
2. The accounts screen shows the four bank names.
3. Every 2026 month up to the last statement has been uploaded, shows no day that disagrees,
   and its reconciliation is complete.
4. Uploading the last month's statement again shows every row as already in the ledger, none as
   new.

## Tasks

Draft, for the owner's approval. The sheet import brings every row in as it is, one transaction
per row; it does not group split rows (owner, 2026-10-16). 2026 is then worked month by month
from the bank statements, through the bank upload that
[bank-lines-and-pending-hashtag.md](bank-lines-and-pending-hashtag.md) makes work on the new
engine.

1. The import sends a `PENDIENTE`/`PENDIENTES` category to `@Pendiente` and a
   `PENDIENTE`/`PENDIENTES` hashtag to the built-in pending hashtag, each by its system key, and
   creates neither name. The pending hashtag is found by `reads.pending_hashtag_of`.
2. A written run sheet for the owner: every command in order, with what to check after each —
   the wipe, the sheet import, then for each 2026 month: upload that month's statement, fix the
   days that disagree (a split, a duplicate), complete that month's reconciliation.
