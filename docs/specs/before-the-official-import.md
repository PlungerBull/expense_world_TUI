# The official import

**Status: approved; questions 15–18 answered by 2026-11-13. A bank account is a 3–4 letter code
and a required last 4 (`IBK-4321`), and only a bank the engine reads takes a statement code
(question 18). The import's review makes the accounts, categories, hashtags and rows in one write,
on a screen the command opens (panes 3 B and 4 A of
[expense-world-banks-and-import-review.html](../mockups/expense-world-banks-and-import-review.html)).
The engine shipped both in contract 3.1, which [the catch-up to 3.1](catch-up-to-3-1.md) takes
first; tasks 7 and 8 wait on question 19.** Turning an account into a person is built
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
ALEJO in soles and in dollars on one. A bank account is made from a code of 3 or 4 letters and its
card's last 4 digits, both required, and named by the engine (`IBK-4321`); no bank has to exist
first. A person and the cash account are named as typed. Only a bank the engine reads statement
PDFs for (`GET /banks`: BCP) holds a statement code, the one its PDFs print, and one PDF closes one
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
| 14 | What a bank is | A code of 3 or 4 letters the owner types and a required last 4, named `CODE-1234` by the engine; no list of banks, no full names, no suggestions for now (the TUI can add them from the owner's accounts later); a statement code only at a bank `GET /banks` lists, which means "the banks whose PDFs the engine reads"; no new check on bank downloads (2026-11-13). |

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
    in the import's request is no side effect. So this replaces 15 A and 16 A: a bank is a code
    (decision 14), and the import's review shows each sheet account with the engine's suggestion,
    the owner confirms or changes each, and one write makes the accounts, categories, hashtags and
    rows. Panes 1 and 2 of
    [expense-world-banks-and-import-review.html](../mockups/expense-world-banks-and-import-review.html)
    draw decision 14. **Picked 2026-11-13: 3 B**, `expense import sheet <file>` opens the review
    as a screen in the app, named "Import sheet"; **4 A**, `⏎` on a row opens the New account form
    filled from the engine's suggestion.
19. **What the hand-off left open** (panes 5, 6 and 7 of
    [expense-world-banks-and-import-review.html](../mockups/expense-world-banks-and-import-review.html)).
    On the owner's sheet the engine suggests a BCP bank account with no last 4 for the five
    `BCP …` names and nothing for the other 13.
    - **Pane 5, a row the engine half-suggests:** A, the row asks for the last 4 and `^s` waits
      for it, as for a kind; or B, the row shows the guess and the engine's refusal comes back on
      `^s`. **Recommended:** A, so every gap shows before sending.
    - **Pane 6, a row the engine refuses on `^s`:** A, the review marks the row and shows the
      engine's words under the table; or B, a question box with the words. **Recommended:** A,
      so the words stay beside the row while it is fixed.
    - **Pane 7, BANK typed in small letters:** A, sent as typed and refused in the engine's
      words; or B, capitals as typed, as STATEMENT CODE already does. **Recommended:** B, so the
      two code lines behave alike.

## What the engine settled

- **The Visa comes in as one account.** The sheet names it once, so the import puts each row in
  its own currency on the one account (contract: POST /v1/transactions/import-sheet, "Names").
- **Opening balances:** the first `SALDO INICIAL` row of each currency of an account is that
  currency's opening balance (contract: POST /v1/transactions/import-sheet, "Opening balances"),
  kept when the account becomes a person.

## Steps

1. The queued specs and this spec's tasks 7 and 8 are done.
2. The owner wipes the live database.
3. The import's review: each sheet account set as a bank account (code, last 4, a statement code
   at BCP), a person by its name (PARDO among them) or the cash account, the closed ones marked
   archived; the categories and hashtags listed to make.
4. The review's count: no row skipped but the two zero rows; the 9 split purchases counted as 9
   split transactions; each first `SALDO INICIAL` row counted as its currency's opening balance.
5. The import, one write, refused by nothing. No account is deleted.

## How the owner knows it is done

1. The accounts screen shows every bank account under its built name, the BCP ones with their
   statement code,
   the eight people under people, and the closed accounts archived; the Visa is one account
   holding soles and dollars.
2. Each split purchase shows as one split transaction.
3. Each account's balance in each currency equals the sheet's total for that account and
   currency.

---

## Tasks

Each reads the live contract on the practice engine before building. Tasks 1–4 and 6 are done, on
the answers 15 A and 16 A (2026-11-12); task 8 replaces what tasks 2 and 3 built. Tasks 7 and 8
run after [the catch-up to 3.1](catch-up-to-3-1.md), which records contract 3.1, and each waits on
question 19's pick for its panes.

7. **The bank account form, as decision 14 and panes 1, 2 and 7 draw it.** On Manage ▸ Accounts New and Edit, and `t`'s
   question when it makes a bank account, BANK is a typed code of 3 or 4 letters with no
   suggestions and LAST 4 is required; the statement code line shows only while BANK is a code
   `GET /banks` lists. The Edit form removes a number only while another stays. A refusal is the engine's words
   under its line: `INVALID_FORMAT` and, when `t` makes a person that carries a statement code a
   bank account at a bank `GET /banks` does not list, `BANK_TAKES_NO_STATEMENT_CODE` under BANK.
8. **The import's review, as panes 3 B, 4 A, 5 and 6 draw it.** Each missing account prefilled
   from the engine's `suggestion`; `^s` sends the dry run with `create`, ids generated here and
   `names` pointing at them, and asks with its `created` and counts before the apply; a refusal
   keyed `create.<list>.<i>.<field>` shows on its row. It replaces making every account in the app first, `--account-name` and the sheet names it saves, `--create-names`, and archiving
   the closed accounts by hand.
5. **The rehearsal on the practice engine,** after 7 and 8: a made-up sheet with the real sheet's
   shape (a card in two currencies, two savings accounts, people, a split purchase, opening
   balances, a closed account at a bank the engine doesn't read) goes through steps 3–5, and
   every balance matches.

## Reply to the engine

Part 2 of the reply to the hand-off of 2026-11-14 (part 1 is
[the catch-up to 3.1](catch-up-to-3-1.md)'s), written once tasks 7, 8 and 5 are done. It reports
on the hand-off's "Done when" checks for the forms (`IBK-4321` made, `ibk` and a missing last 4
refused in the engine's words, or `ibk` taken as `IBK` if pane 7 is B) and for the review (each
missing account prefilled, one apply making them and every row, shown on the rehearsal's made-up
sheet), and closes the screen side of the two asks part 1 names.

## Found along the way

Not built in this spec; sorted when it is done.

- **`--account-name` to a name two live accounts hold takes the last one listed, silently**
  (`names_table`, expense/import_/engine.py). The engine refuses a second account of a taken
  name, so after the wipe no two accounts share one; only names older than built names could.
  It goes with `--account-name` in task 8.
