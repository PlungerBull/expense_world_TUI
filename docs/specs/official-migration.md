# Move the official data into the app

**Status: draft.** The owner reviews and completes this spec before the loop starts on it.
Background and the engine's rules: [file-import-plan.md](../file-import-plan.md) §6 and §10.
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## What it must do

The updated spreadsheet becomes the ledger of record, ready for bank files to take over.

- The BCP accounts carry the bank's names: `Sueldo Soles`, `Cuenta Digital Dólares`,
  `VISA Infinite Sapphire PEN`, `VISA Infinite Sapphire USD` (the sheet import's
  `--account-name`, [cli-spec.md](../cli-spec.md) "Renaming an account leg").
- No `PENDIENTES` category or hashtag appears. The import sends every row the sheet files under
  the `PENDIENTES` category to the built-in `@Pendiente` and drops the `PENDIENTES` hashtag, so the
  sheet stays as it is and a re-run never brings `PENDIENTES` back.
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

## Open questions for the owner

### Does the official data land on an empty ledger or on the 2026-08-20 import?
Asked 2026-09-29
The live ledger already holds the sheet as imported on 2026-08-20, with its accounts under the
old names (`BCP PEN`, …). A re-import with the new names on top of that creates the four new
accounts but leaves the rows already imported on the old ones.
- **A.** Start from an empty ledger, then import the updated sheet once.
- **B.** Keep the ledger. The four existing accounts are renamed in the app first, and the
  import then reuses them.

**Recommended:** none. It depends on whether anything in the live ledger was typed after the
2026-08-20 import and must be kept.

## Tasks

Draft, for the owner's approval.

1. The import sends `PENDIENTES` rows to `@Pendiente` and drops the `PENDIENTES` tag.
2. The title-alignment tool: read the bank downloads against the ledger, write the proposal list
   to a local file outside the repo, apply only the approved changes.
3. A written run sheet for the owner: every command in order, with what to check after each.
