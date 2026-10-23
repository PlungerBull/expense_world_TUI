# The official import

**Status: every question answered (owner, 2026-10-21).** Turning sheet accounts into people
is built ([decisions.md](../decisions.md) "An account becomes a person, and back, with one
key"); the split purchases' grouping is built ([decisions.md](../decisions.md) "The sheet import brings a split purchase in
as one split transaction"). When the import is done, the why moves
to [decisions.md](../decisions.md) and this file is deleted.

---

## What it is

The live database is wiped and the owner's spreadsheet (`data` sheet) is imported once, onto an
empty ledger. Nothing typed into the app before the wipe is kept. **From then on the app is the
record:** every movement goes in through the app (bank uploads and the LOG bar), and the sheet
is not imported again (owner, 2026-10-21). Everything that writes to the real ledger is run or
approved by the owner.

## The sheet as it is imported (checked 2026-10-21)

- 4,191 rows, December 2022 to October 2026. Every row has a category and a hashtag; no row
  waits for a classification.
- Every row checked against a statement carries the statement's date and wording, and its
  statement line in `COD_EECC` (2025 to September 2026). Split purchases share one `COD_EECC`:
  9 of them.
- Loans follow one standard: every movement with a person is mirrored on an account named after
  that person, whose balance is the debt. Eight people: ALEJO, ALONSO, LC, ALEX, LIDIA, MATILDE,
  CARLOS, KORAKUEN; four of them hold both currencies, so they become twelve accounts.
- PARDO (the José Pardo apartment) holds one opening balance of 38,130, the payments made before
  the account was tracked.
- Two rows of zero (account maintenance on the dollar account) are skipped: the engine refuses
  zero amounts.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | Rename typed rows to the bank's wording once, before the first bank upload? | No: the sheet already carries the statements' wording, and every bank upload renames a matched row anyway (contract: POST /v1/transactions/import, "Matching") (2026-10-21). |
| 2 | Create the statements' reconciliations at the import? | No. Reconciling is the owner's call, made later; the `COD_EECC` months are its test data (2026-10-21). |
| 3 | Group the split purchases? | Yes, by their shared `COD_EECC`: built, [decisions.md](../decisions.md) "The sheet import brings a split purchase in as one split transaction" (2026-10-21). |
| 4 | Classify waiting rows before or after? | None are left in the sheet (2026-10-21). |
| 5 | Is anything owed on the old Oro card? | No, it has been at zero for a long time; it imports as the sheet has it, showing -691.64 PEN and -88.82 USD (2026-10-21). |
| 6 | The April `EXTORNO` row? | Gone: the row carries the bank's wording and date (2026-10-21). |
| 7 | Archive the closed accounts (both Interbank accounts, Alcancía)? | Yes, done by the owner in the app after the import (2026-10-21). |
| 8 | Is the sheet frozen after the import? | The app is the record; the sheet is not imported again (2026-10-21). |
| 9 | The engine's exchange rates or the sheet's? | The engine's: `T.C.` and `Solarizado` are ignored, and the soles totals of dollar rows differ slightly from the sheet's (2026-10-21). |
| — | Account names | The BCP accounts carry the bank's names: `Sueldo Soles`, `Cuenta Digital Dólares`, `VISA Infinite Sapphire PEN`, `VISA Infinite Sapphire USD` (the sheet import's `--account-name`, [commands.md](../commands.md) "Renaming an account leg") (2026-10-17). |
| — | People | Imported as bank accounts, then turned into people in the app with `t` on Manage ▸ Accounts ([decisions.md](../decisions.md) "An account becomes a person, and back, with one key") (2026-10-21). |

## Steps

1. Both specs above are built, engine halves first.
2. The owner wipes the live database.
3. The import's dry run, with the four `--account-name` renames: no row skipped but the two
   zero rows, the 9 split groups shown as one movement each, the four bank names listed.
4. The import with `--apply`, finishing with no failures.
5. In the app: the twelve person accounts turned into people, and the three closed accounts
   archived.

## How the owner knows it is done

1. The accounts screen shows the four bank names, the twelve people under people, and the three
   closed accounts archived.
2. Each split purchase shows as one split transaction.
3. Each account's balance equals its total in the sheet.
