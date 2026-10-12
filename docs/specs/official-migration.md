# Move the official data into the app

**Status: draft, deferred.** The loop does not start on it until the owner says so; its open
questions are in [todo.md](../todo.md) "Waiting on you".
Background and the engine's rules: [file-import-plan.md](../file-import-plan.md) §6 and §10.
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## What it must do

The updated spreadsheet becomes the ledger of record, ready for bank files to take over.

The owner wipes the live database and imports the updated sheet once, onto an empty ledger.
Nothing typed into the app before the wipe is kept.

- The BCP accounts carry the bank's names: `Sueldo Soles`, `Cuenta Digital Dólares`,
  `VISA Infinite Sapphire PEN`, `VISA Infinite Sapphire USD` (the sheet import's
  `--account-name`, [cli-spec.md](../cli-spec.md) "Renaming an account leg").
- No `PENDIENTE` or `PENDIENTES` category or hashtag appears. The import sends every row whose
  category or hashtag carries that name to the built-in `@Pendiente` and writes no such hashtag,
  so the sheet stays as it is and a re-run never brings it back.
- The hand-typed rows of the last weeks take the bank's wording, so a bank file covering those
  days matches them instead of adding them twice. The app proposes each change and the owner
  approves the list before anything is written ([file-import-plan.md](../file-import-plan.md) §6).
- The order is fixed by the engine: **import → title alignment → complete the 2026
  reconciliations → first real bank import.** A completed reconciliation locks its rows'
  titles and seals its window against new rows (contract: POST /v1/transactions/import).

Everything that writes to the real ledger is run or approved by the owner.

## How the owner knows it is done

1. The import's dry run lists the four renamed accounts and no `PENDIENTES`; `--apply` finishes
   with no failures.
2. The accounts screen shows the four bank names.
3. The title-alignment list was reviewed and applied.
4. A dry run of a fresh bank download shows the aligned rows as already in the ledger, none as
   new.

## Tasks

Draft, for the owner's approval.

1. The import sends every row whose category or hashtag is `PENDIENTE` or `PENDIENTES` to
   `@Pendiente` and writes no such tag.
2. The title-alignment tool: read the bank downloads against the ledger, write the proposal list
   to a local file outside the repo, apply only the approved changes.
3. A written run sheet for the owner: every command in order, with what to check after each.
