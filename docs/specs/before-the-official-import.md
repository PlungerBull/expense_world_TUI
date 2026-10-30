# The official import

**Status: draft, written 2026-10-29 for the owner to approve, with five questions. It runs last:
after the catch-up to contract `f82426fb0a099676`
(1 (done on 2026-10-30), 2 (done on 2026-10-30),
[3](catch-up-currencies-3-live-suite-foundation.md), [4](catch-up-currencies-4-live-suite-upload-lines-kinds.md),
[5](catch-up-currencies-5-live-suite-account-currencies.md), [6](catch-up-currencies-6-main-views.md),
[7](catch-up-currencies-7-statement-screen.md)) and the specs that follow it.** Turning sheet
accounts into people is built ([decisions.md](../decisions.md) "An account becomes a person, and
back, with one key"); the split purchases' grouping is built ([decisions.md](../decisions.md) "The
sheet import brings a split purchase in as one split transaction"); the sheet import goes through
the engine. When the import is done, the why moves to [decisions.md](../decisions.md) and this
file is deleted.

---

## What it is

The live database is wiped and the owner's spreadsheet (`data` sheet) is imported once, onto an
empty ledger. Nothing typed into the app before the wipe is kept. **From then on the app is the
record:** every movement goes in through the app (bank uploads and the LOG bar), and the sheet
is not imported again (owner, 2026-10-21). Everything that writes to the real ledger is run or
approved by the owner.

An **account** is one bank product or one person, holding its currencies
(contract: "What an account is", "Its currencies"). The sheet names an account once for all its
currencies, so the Visa is one account holding soles and dollars, and each person is one account,
ALEJO in soles and in dollars on one. Each BCP savings account is an account of its own when the
sheet gives it a name of its own (question 1). An account holds the statement code its PDFs print
(contract: "What an account is", "Statement code"), and one PDF closes one account's month.

## The sheet as it is imported (checked 2026-10-21)

- 4,191 rows, December 2022 to October 2026. Every row has a category and a hashtag; no row
  waits for a classification.
- Every row checked against a statement carries the statement's date and wording, and its
  statement line in `COD_EECC` (2025 to September 2026). Split purchases share one `COD_EECC`:
  9 of them.
- Loans follow one standard: every movement with a person is mirrored on an account named after
  that person, whose balance is the debt. Eight people: ALEJO, ALONSO, LC, ALEX, LIDIA, MATILDE,
  CARLOS, KORAKUEN; four of them hold both currencies. Each is one account, so they become eight
  accounts.
- PARDO (the José Pardo apartment) holds one opening balance of 38,130, the payments made before
  the account was tracked.
- Two rows of zero (account maintenance on the dollar account) are skipped: the engine skips
  every row of zero.
- The engine coders imported the whole sheet on the practice engine on 2026-10-26: 4,191 rows in
  one apply. Five of its `COD_EECC` codes differ from the statements' PDFs (a zero row's, and two
  pairs of identical charges in the opposite order); none needs fixing, since the import never
  stores a code and the PDFs set every statement line.
- The sheet names each row's account (`CUENTA`) and its currency (`MONEDA`). One name is one
  account holding every currency its rows use; two names may name one account
  (contract: POST /v1/transactions/import-sheet, "Names").

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | Rename typed rows to the bank's wording once, before the first bank upload? | No: the sheet already carries the statements' wording, and every bank upload renames a matched row anyway (contract: POST /v1/transactions/import, "Matching") (2026-10-21). |
| 2 | Create the statements at the import? | No. Closing statements is the owner's call, made later; the `COD_EECC` months are its test data (2026-10-21). With no statement at the import, every account can still be turned into a person (contract: POST /v1/accounts/{account_id}/make-person, "Refusals"). |
| 3 | Group the split purchases? | Yes, by their shared `COD_EECC`: built, [decisions.md](../decisions.md) "The sheet import brings a split purchase in as one split transaction" (2026-10-21). |
| 4 | Classify waiting rows before or after? | None are left in the sheet (2026-10-21). |
| 5 | Is anything owed on the old Oro card? | No, it has been at zero for a long time; it imports as the sheet has it, showing -691.64 PEN and -88.82 USD (2026-10-21). |
| 6 | The April `EXTORNO` row? | Gone: the row carries the bank's wording and date (2026-10-21). |
| 7 | Archive the closed accounts (both Interbank accounts, Alcancía)? | Yes, done by the owner in the app after the import (2026-10-21): each closed account is archived, every currency of it with it (contract: POST /v1/accounts/{account_id}/archive). |
| 8 | Is the sheet frozen after the import? | The app is the record; the sheet is not imported again (2026-10-21). |
| 9 | The engine's exchange rates or the sheet's? | The engine's: `T.C.` and `Solarizado` are ignored, and the soles totals of dollar rows differ slightly from the sheet's (2026-10-21). |
| — | Account names | The BCP accounts carry the bank's names, through the sheet import's `--account-name` ([commands.md](../commands.md) "Renaming an account") (2026-10-17): `Sueldo Soles`, `Cuenta Digital Dólares` and the Visa's name (question 3). A rename names a sheet name, with no currency, and gives one account; the app shows each of its currencies as "<account> · <code>" (`Sueldo Soles · PEN`). |
| — | People | Imported as bank accounts, then turned into people in the app with `t` on Manage ▸ Accounts ([decisions.md](../decisions.md) "An account becomes a person, and back, with one key") (2026-10-21). Each person is one account, so one `t` turns it with every currency it holds (contract: "What an account is", "The kind changes on the account"); nothing is paired first. Question 4 asks whether that stays the way. |

## What the engine settled

- **The Visa comes in as one account.** The sheet names it once, so the create step makes one
  account holding soles and dollars, and the import puts each row in its own currency
  (contract: POST /v1/transactions/import-sheet, "Names"). Nothing is moved or paired in the app.
- **A future person keeps its opening balances:** the import makes the first `SALDO INICIAL`
  row of each currency of an account that currency's opening balance, each currency keeping its
  own (contract: POST /v1/transactions/import-sheet, "Opening balances"), and turning the account
  into a person keeps them (contract: "People / Person Accounts", "Person rules"), so each balance
  stays the sheet's.

## Steps

1. The app is caught up to contract `f82426fb0a099676` (the seven specs named in the status).
2. The owner wipes the live database.
3. The import's dry run, with the `--account-name` renames: every name listed as missing, the
   bank names among them.
4. `--create-names` creates them, importing nothing: each account once, holding the currencies
   its rows use.
5. In the app, before anything is imported: the statement codes their PDFs print are set on the
   Visa and on both BCP savings accounts.
6. The dry run again: no row skipped but the two zero rows; the 9 split purchases counted as 9
   split transactions, with the rows they hold; a future person's first `SALDO INICIAL` row in
   each currency counted as that currency's opening balance, which it keeps when it becomes a
   person.
7. The import with `--apply`, refused by nothing.
8. In the app: `t` on each of the eight person accounts, turning it into a person, and the closed
   accounts archived. No account is deleted.

## How the owner knows it is done

1. The accounts screen shows the bank names, the eight people under people, and the closed
   accounts archived; the Visa is one account holding soles and dollars, and the Visa and both
   BCP savings accounts carry their statement codes.
2. Each split purchase shows as one split transaction.
3. Each account's balance in each currency equals the sheet's total for that account and
   currency.

## Questions for the owner

1. **Does the sheet use one name for both BCP savings accounts?** Sueldo Soles is in soles and
   Cuenta Digital Dólares in dollars. If the sheet calls both by one name, the engine makes them
   one account, while the bank sends each its own PDF with its own statement code.
   - **A.** Rename one of them in the sheet (its rows' `CUENTA`) before the import, so each is an
     account of its own.
   - **B.** Ask the engine to let one sheet name split into two accounts by currency.

   **Recommended:** none: whether the sheet uses one name is a fact only you know. If it does, A:
   the sheet is imported once, so an engine rule for it would serve one run.
2. **Oro and Interbank follow the sheet's names, right?** Each name the sheet uses for them
   becomes one account holding every currency its rows use: Oro one account in soles and
   dollars, and each Interbank name one account.
   - **A.** Yes, as the sheet names them.
   - **B.** No: rename some of their rows in the sheet before the import, so they split
     differently.

   **Recommended:** A: an account is one bank product, so the ledger shows them as they were;
   for closed accounts the only effect is that archiving one archives every currency of it.
3. **The Visa's name.** The app shows each currency after the name, so the old names
   `VISA Infinite Sapphire PEN` and `VISA Infinite Sapphire USD` would read
   `VISA Infinite Sapphire PEN · PEN`.
   - **A.** `VISA Infinite Sapphire`, with no currency in the name.
   - **B.** Another name you give.

   **Recommended:** A: the currency already shows beside it.
4. **People in the import.**
   - **A.** As planned: the create step makes them bank accounts, then `t` on each in the app
     turns it into a person, every currency with it.
   - **B.** The create step makes them people directly, told which sheet names are people.

   **Recommended:** A: it is built, and eight presses of `t` is all it takes.
5. **The engine's ledger update before the wipe.** The engine says the owner moves the live
   ledger to the new model and checks every balance before and after. The import wipes the
   database anyway.
   - **A.** Wipe first, then update the engine on the empty database: nothing old is kept, so
     there is nothing to check.
   - **B.** Update the engine on today's ledger and check its balances before and after, then
     wipe.

   **Recommended:** A: the check would prove a ledger that is thrown away right after.
