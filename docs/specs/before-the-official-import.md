# The official import

**Status: waits on the cards-and-statements catch-up, which reaches contract
`e7393dd869963db1`: the app working again
(part 1a, the app's reads and writes (done on 2026-10-28) and
[catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md)) and holders in
the app ([catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md)), and on
pairing in the app with the engine's move of an account onto another holder (decided 10). The
engine's rename of card to holder is in (contract `e7393dd869963db1`, the hand-off "A person
carries an opening balance, and a card is now called a holder everywhere", shipped 2026-10-28).
The move is in the live contract (contract: POST /v1/accounts/{account_id}/move), with its
hand-off of 2026-10-28. Question 2 waits on the owner.** Turning sheet accounts into people is built ([decisions.md](../decisions.md) "An account
becomes a person, and back, with one key"); the split purchases' grouping is built
([decisions.md](../decisions.md) "The sheet import brings a split purchase in as one split
transaction"); the sheet import goes through the engine (done on 2026-10-27). When the import is
done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

**Reshaped by the engine's next changes** (the engine coders' answer of 2026-10-27, "Which of
the terminal app's seven card and statement specs the engine's coming changes touch"). A person
carries an opening balance (shipped as contract `4ac20e42cf8566ee` on 2026-10-27, settled
below); an account moves between holders (in the live contract since `3e472b3256dcdc69`); and
people become holders, so the import creates every sheet name as a bank account on a holder of
its own, and you then turn the people into people and pair the Visa in the app before
reconciling. People becoming holders has not shipped: this spec is rewritten when it lands; its
questions wait until then.

---

## What it is

The live database is wiped and the owner's spreadsheet (`data` sheet) is imported once, onto an
empty ledger. Nothing typed into the app before the wipe is kept. **From then on the app is the
record:** every movement goes in through the app (bank uploads and the LOG bar), and the sheet
is not imported again (owner, 2026-10-21). Everything that writes to the real ledger is run or
approved by the owner.

Every bank account sits on a **holder**, the engine's name for one bank product: the Visa is one
holder holding a soles and a dollar account, each BCP savings account is a holder of its own, and
a person is on a person holder, ALEJO in soles and in dollars on one (contract: "Holders",
"Its kind"). A holder holds the statement code its PDFs print
(contract: "Holders", "Statement code"), and one PDF closes one holder's month.

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
- Two rows of zero (account maintenance on the dollar account) are skipped: the engine skips
  every row of zero.
- The engine coders imported the whole sheet on the practice engine on 2026-10-26: 4,191 rows in
  one apply. Five of its `COD_EECC` codes differ from the statements' PDFs (a zero row's, and two
  pairs of identical charges in the opposite order); none needs fixing, since the import never
  stores a code and the PDFs set every statement line.
- The sheet names an account by its name and currency only; it says nothing of holders.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | Rename typed rows to the bank's wording once, before the first bank upload? | No: the sheet already carries the statements' wording, and every bank upload renames a matched row anyway (contract: POST /v1/transactions/import, "Matching") (2026-10-21). |
| 2 | Create the statements at the import? | No. Closing statements is the owner's call, made later; the `COD_EECC` months are its test data (2026-10-21). With no statement at the import, every account can still be turned into a person or moved onto another holder. |
| 3 | Group the split purchases? | Yes, by their shared `COD_EECC`: built, [decisions.md](../decisions.md) "The sheet import brings a split purchase in as one split transaction" (2026-10-21). |
| 4 | Classify waiting rows before or after? | None are left in the sheet (2026-10-21). |
| 5 | Is anything owed on the old Oro card? | No, it has been at zero for a long time; it imports as the sheet has it, showing -691.64 PEN and -88.82 USD (2026-10-21). Whether its two currencies are one holder is question 2. |
| 6 | The April `EXTORNO` row? | Gone: the row carries the bank's wording and date (2026-10-21). |
| 7 | Archive the closed accounts (both Interbank accounts, Alcancía)? | Yes, done by the owner in the app after the import (2026-10-21): each closed account's holder is archived, which archives every account on it (contract: "Holders", "A holder is archived whole"). |
| 8 | Is the sheet frozen after the import? | The app is the record; the sheet is not imported again (2026-10-21). |
| 9 | The engine's exchange rates or the sheet's? | The engine's: `T.C.` and `Solarizado` are ignored, and the soles totals of dollar rows differ slightly from the sheet's (2026-10-21). |
| 10 | How do the Visa's two accounts end up on one holder? | By the engine's move of an account onto another holder, allowed while the account has never been in a statement, a deleted one included (contract: "Holders", "An account in no statement moves between holders"): pairing is moving one account onto the other currency's holder, and the holder it leaves, holding no live account, is deleted in the same write (contract: POST /v1/accounts/{account_id}/move). `--create-names` gives every account a holder of its own, and the Visa's two accounts are put on one holder in the app before the import (step 5), so no account is made by hand. Neither the import nor the statement upload can tell which accounts share a holder: the sheet holds only a name and a currency per account. The answer saying yes, "Yes to moving an account to another card, with the limits you proposed; no to the sheet import refusing a name used in two currencies", is handed over (2026-10-27). |
| — | Account names | The BCP accounts carry the bank's names: `Sueldo Soles`, `Cuenta Digital Dólares`, `VISA Infinite Sapphire PEN`, `VISA Infinite Sapphire USD` (the sheet import's `--account-name`, [commands.md](../commands.md) "Renaming an account") (2026-10-17). The Visa's two accounts keep their two names on one holder; the holder has a name of its own. |
| — | People | Imported as bank accounts, each on a holder of its own, then turned into people in the app with `t` on Manage ▸ Accounts ([decisions.md](../decisions.md) "An account becomes a person, and back, with one key") (2026-10-21). Since contract `e1959ea3b1d8ca6d` (the hand-off "A person is a holder; …", 2026-10-28), `t` turns the whole holder, which stays: a person in two currencies (the four people in both) has its two accounts paired onto one holder first, by the move, then `t` on it turns both (contract: POST /v1/holders/{holder_id}/make-person). Question 3 asks whether that stays the way. |

## What the engine settled

- **A future person keeps its opening balance** (contract `4ac20e42cf8566ee`, the hand-off "A
  person carries an opening balance, and a card is now called a holder everywhere"): the import
  makes an account's first `SALDO INICIAL` row its opening balance (contract: POST /v1/transactions/import-sheet, "Opening balances"),
  and turning the holder into a person holder keeps it
  (contract: POST /v1/holders/{holder_id}/make-person), so the balance stays the sheet's.

## Steps

The steps follow decided 10.

1. The app works with holders and can move an account onto another holder (the catch-up's specs
   named in the status, and the engine's move from decided 10).
2. The owner wipes the live database.
3. The import's dry run, with the four `--account-name` renames: every name listed as missing,
   the four bank names among them.
4. `--create-names` creates them, importing nothing: each account on a holder of its own, the
   holder named as [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md) decides.
5. In the app, before anything is imported:
   - the Visa's two accounts are put on one holder (the dollar account moved onto the soles
     account's holder, which deletes the dollar account's emptied holder), and any other bank
     product holding two currencies the same way (question 2);
   - the statement codes their PDFs print are set on the Visa's holder and on both BCP savings
     holders.
6. The dry run again: no row skipped but the two zero rows; the 9 split purchases counted as 9
   split transactions, with the rows they hold; a future person's first `SALDO INICIAL` row
   counted as its opening balance, which it keeps when it becomes a person.
7. The import with `--apply`, refused by nothing.
8. In the app: the twelve person accounts turned into people (each one's holder deleted with it),
   and the closed accounts' holders archived.

## How the owner knows it is done

1. The accounts screen shows the four bank names, the twelve people under people, and the closed
   accounts archived; the Visa's two accounts are on one holder, each BCP savings account is on a
   holder of its own, and the Visa's holder and both BCP savings holders carry their statement
   codes.
2. Each split purchase shows as one split transaction.
3. Each account's balance equals its total in the sheet.

## Questions for the owner

2. **The old Oro card and the two Interbank accounts: one holder each, or a holder per account?**
   Oro holds soles and dollars; the two Interbank accounts are closed.
   - **A.** One holder for each bank product: Oro's two currencies on one holder, and the
     Interbank accounts on one holder if they were one product in two currencies.
   - **B.** A holder per account.

   **Recommended:** A: a holder is one bank product, so the ledger shows them as they were; for
   closed accounts the only effect is that archiving the holder archives both together.

The name each holder gets when one name is used in two currencies (the four people in both
currencies) is a question of
[catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md).

3. **People in the import: still bank accounts turned with `t`?** Since 2026-10-28 `t` turns a
   whole holder, and a person in two currencies is one person holder of two. The import's create
   step makes each account a bank account on a holder of its own.
   - **A.** As planned: the import makes them bank accounts; in the app, each person's two
     currencies are paired onto one holder, then `t` turns it into a person holder.
   - **B.** Ask the engine for the sheet import to make the people as person holders itself,
     both currencies on one, given which sheet names are people.

   **Recommended:** none yet: it waits on the cards spec's questions 11 to 13, which decide how
   people are made and paired in the app; asked again when this spec is next.
