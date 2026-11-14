# The official import

**Status: draft for the owner to approve, rewritten on 2026-11-09 for built names: the engine
builds a bank account's name from its bank and card number (`BCP-5678`), never creates an
account in a sheet import, and lists one bank, BCP. Questions 15–17 are open, with mockup panes
17 and 18 of [expense-world-open-questions.html](../mockups/expense-world-open-questions.html).
It runs last, after the queued specs.** Turning an account into a person is built
([decisions.md](../decisions.md) "An account becomes a person, and back, with one key"); the
split purchases' grouping is built ([decisions.md](../decisions.md) "The sheet import brings a
split purchase in as one split transaction"); the sheet import goes through the engine. When the
import is done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## What it is

The live database is wiped and the owner's spreadsheet (`data` sheet) is imported once, onto an
empty ledger. Nothing typed into the app before the wipe is kept. **From then on the app is the
record:** every movement goes in through the app (bank uploads and the LOG bar), and the sheet
is not imported again. Everything that writes to the real ledger is run or approved by the
owner.

An **account** is one bank product, one person or the cash account, holding its currencies
(contract: "What an account is", "Its currencies"). The sheet names an account once for all its
currencies, so the Visa is one account holding soles and dollars, and each person is one account,
ALEJO in soles and in dollars on one. A bank account is made from its bank and its card's last 4
digits and named by the engine (`BCP-5678`); two accounts at one bank with no number would share
the name `BCP`, which the engine refuses (contract: POST /v1/accounts, "Validation"). A person is
named as typed. An account holds the statement code its PDFs print, and one PDF closes one
account's month.

## The sheet as it is imported (checked 2026-10-21)

- 4,191 rows, December 2022 to October 2026. Every row has a category and a hashtag; no row
  waits for a classification.
- Every row checked against a statement carries the statement's date and wording, and its
  statement line in `COD_EECC` (2025 to September 2026). Split purchases share one `COD_EECC`:
  9 of them.
- Loans follow one standard: every movement with a person is mirrored on an account named after
  that person, whose balance is the debt. Eight people: ALEJO, ALONSO, LC, ALEX, LIDIA, MATILDE,
  CARLOS, KORAKUEN; four of them hold both currencies.
- PARDO (the José Pardo apartment) holds one opening balance of 38,130, the payments made before
  the account was tracked.
- Two rows of zero (account maintenance on the dollar account) are skipped: the engine skips
  every row of zero.
- The engine coders imported the whole sheet on the practice engine on 2026-10-26: 4,191 rows in
  one apply. Five of its `COD_EECC` codes differ from the statements' PDFs; none needs fixing,
  since the import never stores a code and the PDFs set every statement line.
- The sheet names each row's account (`CUENTA`) and its currency (`MONEDA`). The engine never
  looks a name up: every sheet name is given an account's id, and a sheet name equal to an
  account's name is proposed for it (contract: POST /v1/transactions/import-sheet, "Names").

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | Rename typed rows to the bank's wording once, before the first bank upload? | No: the sheet already carries the statements' wording, and every bank upload renames a matched row anyway (2026-10-21). |
| 2 | Create the statements at the import? | No. Closing statements is the owner's call, made later (2026-10-21). |
| 3 | Group the split purchases? | Yes, by their shared `COD_EECC`: built (2026-10-21). |
| 4 | Classify waiting rows before or after? | None are left in the sheet (2026-10-21). |
| 5 | Is anything owed on the old Oro card? | No; it imports as the sheet has it, showing -691.64 PEN and -88.82 USD (2026-10-21). |
| 6 | The April `EXTORNO` row? | Gone: the row carries the bank's wording and date (2026-10-21). |
| 7 | Archive the closed accounts (both Interbank accounts, Alcancía)? | Yes, in the app after the import (2026-10-21). |
| 8 | Is the sheet frozen after the import? | The app is the record; the sheet is not imported again (2026-10-21). |
| 9 | The engine's exchange rates or the sheet's? | The engine's: `T.C.` and `Solarizado` are ignored (2026-10-21). |
| 10 | Does the sheet use one name for both BCP savings accounts? | No: Sueldo Soles and Cuenta Digital Dólares are accounts of their own (2026-11-05). |
| 11 | Oro and Interbank? | As the sheet names them: each name one account holding every currency its rows use (2026-11-05). |
| 12 | The engine's ledger update before the wipe? | Wipe first, then update the engine on the empty database (2026-11-05). |
| 13 | Account names | The engine's built names, with no alias: the Visa reads `BCP-` and its card's last 4, not `VISA Infinite Sapphire` (2026-11-08). |

## Open questions

15. **Where the sheet's accounts are made** (pane 17). **Answered 2026-11-12: A.**
    - **A.** All in the app first: each bank account on the New form with its bank, last 4,
      currencies and statement code, each person by its name. The import puts each bank
      account's sheet name on its account with `--account-name "VISA Infinite Sapphire=BCP-5678"`,
      and a person's sheet name finds the person of that name. The create step makes only
      categories and hashtags; the dry run lists a sheet account with no account as one to make
      in the app.
    - **B.** The create step also makes the people: a sheet account with no rename is made a
      person. Eight fewer names to type, but a bank account forgotten in the app becomes a
      person.
    - **Recommended:** A: one place makes accounts, no guess at which name is a person, and the
      `t` step after the import goes away.
16. **The closed accounts at other banks** (pane 18). **Answered 2026-11-12: A.** The engine lists only BCP, so the two
    Interbank accounts, and the Oro card and Alcancía if they are not BCP's, cannot be made as
    bank accounts.
    - **A.** Ask the engine to list their banks; each is made at its own bank, then archived.
    - **B.** Make them people: each keeps its rows and balance, but shows under people.
    - **Recommended:** A, so each closed account is what it was.
17. **Facts only you know.** **Answered 2026-11-13:** the Oro card and Alcancía are at BCP; every
    account that shares a bank has a last 4 of its own, typed in the app at step 3 and kept out
    of this repo; PARDO, the José Pardo apartment, is made a person until the app has a kind of
    account for an investment. So Interbank is the one bank the engine must add.
18. **Where the accounts are made, once the engine can suggest them.** **Answered 2026-11-13:**
    the engine says its bank list is fixed only as built, and that an account the user confirms
    in the import's request is no side effect. So this replaces 15 A and 16 A: a bank is a
    code the owner types (`IBK-4321`), the engine saying which codes it reads, and the
    import's review shows each sheet account with the engine's suggestion, the owner confirms or
    changes each, and one write makes the accounts, categories, hashtags and rows. Its screens:
    [expense-world-banks-and-import-review.html](../mockups/expense-world-banks-and-import-review.html),
    not yet picked. Steps 3 to 8 below change once the picks and the engine's hand-off land.

## What the engine settled

- **The Visa comes in as one account.** The sheet names it once, so the import puts each row in
  its own currency on the one account (contract: POST /v1/transactions/import-sheet, "Names").
- **Opening balances:** the first `SALDO INICIAL` row of each currency of an account is that
  currency's opening balance (contract: POST /v1/transactions/import-sheet, "Opening balances"),
  kept when the account becomes a person.

## Steps

1. The queued specs are done and the engine lists every bank the closed accounts were at
   (question 16 A).
2. The owner wipes the live database.
3. In the app: each bank account made with its bank, last 4, currencies and statement code; each
   person made by name, PARDO among them.
4. The import's dry run, with an `--account-name` for each bank account's sheet name: every
   account found, the categories and hashtags listed as missing.
5. `--create-names` makes the categories and hashtags, importing nothing.
6. The dry run again: no row skipped but the two zero rows; the 9 split purchases counted as 9
   split transactions; each first `SALDO INICIAL` row counted as its currency's opening balance.
7. The import with `--apply`, refused by nothing.
8. In the app: the closed accounts archived. No account is deleted.

## How the owner knows it is done

1. The accounts screen shows every bank account under its built name with its statement code,
   the eight people under people, and the closed accounts archived; the Visa is one account
   holding soles and dollars.
2. Each split purchase shows as one split transaction.
3. Each account's balance in each currency equals the sheet's total for that account and
   currency.

---

## Tasks

On the answers 15 A and 16 A (2026-11-12); each reads the live contract on the practice engine
before building. Tasks 1–4 and 6 are done; a sheet name two accounts share (`ambiguous`) is
left out of task 4's tests, since every create and rename refuses a taken name and only accounts
made before built names can share one (contract: POST /v1/transactions/import-sheet, "Names").
Question 18 adds tasks once its mockup is picked and the engine's hand-off for the asks "A bank
account's bank is a short code the user types, and the engine says which codes it can read" and "The sheet import suggests the accounts it is missing and makes
the ones the user confirms, with its names and rows, in one write" lands; task 5 runs after them.

5. **The rehearsal on the practice engine:** a made-up sheet with the real sheet's shape (a
   card in two currencies, two savings accounts, people, a split purchase, opening balances, a
   closed account at a second bank) goes through steps 3–8, and every balance matches.

## Found along the way

Not built in this spec; sorted when it is done.

- **`--account-name` to a name two live accounts hold takes the last one listed, silently**
  (`names_table`, expense/import_/engine.py). The engine refuses a second account of a taken
  name, so after the wipe no two accounts share one; only names older than built names could.
