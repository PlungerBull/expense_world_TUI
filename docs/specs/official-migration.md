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
  `--account-name`, [commands.md](../commands.md) "Renaming an account leg").
- `PENDIENTE` means "not classified yet", on the category and on the hashtag alike. No
  `PENDIENTE` or `PENDIENTES` category or hashtag is created: a row whose category carries that
  name goes to the built-in `@Pendiente` category, a row whose hashtag carries it goes to the
  built-in pending hashtag, and the other side keeps its own value. The sheet stays as it is and
  a re-run never brings the names back. The pending hashtag is an engine ask
  ([engine-asks/built-in-pending-hashtag.md](../engine-asks/built-in-pending-hashtag.md)).
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

1. The import sends a `PENDIENTE`/`PENDIENTES` category to `@Pendiente` and a
   `PENDIENTE`/`PENDIENTES` hashtag to the built-in pending hashtag, each by its system key, and
   creates neither name. Waits on the pending-hashtag engine ask.
2. The title-alignment tool: read the bank downloads against the ledger, write the proposal list
   to a local file outside the repo, apply only the approved changes.
3. A written run sheet for the owner: every command in order, with what to check after each.
