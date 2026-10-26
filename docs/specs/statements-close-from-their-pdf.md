# A month's statement closes from the bank's PDF

**Status: draft, for the owner to rewrite or approve; questions 1 to 6 answered on 2026-10-25,
questions 7 to 11 wait on the owner. Its tasks
are drafted when the owner names it the current spec.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Reconciling today means ticking each line into the month and putting the lines in the paper's
order by hand. That is not how a statement is checked: the bank sends the month as a PDF, and
the PDF already holds everything a reconciliation needs: each currency's starting and ending
balance, every line, and the lines' order on the paper. On a card, one PDF holds both
currencies, so it is also what joins the card's soles and dollar halves into one statement.

Until this lands, no reconciliation holding lines on an account with a statement code can be
completed from the app: the engine completes it only once every line has its place on the
paper, and no screen sets the places.

So a month's reconciliation is opened with no statement and stays open; when the PDF arrives,
uploading it closes the month. The engine does the work (the owner, 2026-10-25: ask the engine,
never a client-side workaround), so the web and iPhone apps get it for free.

What the bank's PDFs hold (read from every statement the owner has, 2026-10-25; every one adds
up to the cent, and each one's starting balance is the last one's ending balance):

- **A card statement** holds both currencies: a soles column and a dollar column, the soles
  lines first, then the dollar lines, each by the day the bank processed them. Its days are the
  bank's cycle (about the 26th to the 25th, varying), counted by the processing day, while a line
  imported from the bank's download carries the day of the purchase, so a statement holds lines
  bought a few days before its first day and leaves out lines bought just before its last day.
  Its total adds charges printed with no date (interest, insurance, the membership fee, the
  mailing fee). An installment purchase is billed one installment a month, as its own line. No
  line carries an operation number.
- **An account statement** (the salary and savings accounts) holds one currency and a calendar
  month, money out and money in as two columns, with no operation number either; the monthly
  zero-amount maintenance line is not a movement.

## What it must do

1. **Upload a month's PDF statement** from the app, on any account that holds a statement: a
   card's or a bank account's.
2. **The engine closes the month from it** in one write: it creates the month's statement if
   none is open (on a card, both currencies' halves, joined), sets each half's starting and
   ending balance from the PDF, matches each PDF line to a ledger line, creates the lines the
   ledger lacks, puts every line in the PDF's order, and completes the statement.
3. **Lines in the ledger that the PDF does not hold are flagged,** never changed or deleted by
   the upload: they stay out of the statement for the owner to look at, as a bank file's
   unclaimed lines do ([decisions.md](../decisions.md) "Bank downloads are matched against the ledger, not hashed").
4. **Before anything is written, the app shows what the upload would do**, as the import door
   does: the lines matched, the lines it would create, the lines flagged, and the balances; the
   owner confirms and it is written, or nothing is.
5. **A refused upload says why in the engine's words** (a PDF of another account, a month
   already completed, a PDF the engine cannot read) and writes nothing.
6. **The reconciliation screens do only reconciliation work.** Editing a line from them opens the
   ledger's Edit form, as `⏎` on a "no batch" row does today.
7. **An account keeps its card numbers over time.** A card replaced with its balance carried
   over (a lost card, say) stays the same account: the account records which card number it
   had until which day and which one after. A card that is closed ends its account, and a new
   card is a new account. So a PDF's card number, with its dates, names its account. On screen
   this is a field of the account form, picked from a mockup before it is built.
8. **An account's name comes from its bank and its number** (owner, 2026-10-25): an account
   holds its bank and the last 4 digits of its card or account number, and an optional alias;
   it shows as bank + last 4 digits (`BCP 1234`), or as its alias when it has one. The engine
   holds the fields and the rule and serves the name to show, so every client shows the same
   name; the app shows what the engine sends, and the account form edits the bank, the number
   and the alias (picked from a mockup first).
9. **The engine asks follow the rule** ("Ask the engine to change" in
   [CLAUDE.md](../../CLAUDE.md)): the PDF is read, matched and closed by the engine; the app
   sends the file and shows the answer.

## How the owner knows it is done

These take the place of the checks the statement catch-up moved here, by the owner's call of
2026-10-25 ([decisions.md](../decisions.md) "A card's statement is one statement, and a month
closes from the bank's PDF").

1. The owner uploads a card's PDF for a month with no statement yet: both halves are created
   with the PDF's balances, every line is in the statement in the PDF's order, and the
   statement is completed; each line's statement line (read through the engine, never shown)
   matches its row on the paper.
2. The same with a month opened beforehand and left open: the upload closes that one.
3. A PDF line the ledger lacks is created by the upload and lands in the statement.
4. A ledger line dated inside the month that the PDF does not hold is shown as flagged after
   the upload, unchanged and outside the statement.
5. The preview shows all of it before anything is written, and leaving the preview writes
   nothing.
6. An account statement (one currency) closes the same way.
7. The reconciliation screen of a closed statement lists its lines in the PDF's order, its
   opening balance apart.
8. Uploading the PDF of another account, or of a month already completed, is refused with the
   engine's words and writes nothing.
9. A card's bottom charges (interest, insurance, the membership fee, the mailing fee) each land
   as their own transaction on the statement's last day.
10. Two identical lines on one day (same currency and amount) on the PDF and two in the ledger
    match both; two on the PDF and one in the ledger create one; one on the PDF and two in the
    ledger flag one.
11. A ledger line dated inside the month that the PDF does not hold does not stop the close.
12. The owner records a replaced card's new number on its account; the next PDF, under the new
    number, closes that account's month.
13. The live contract suite proves the engine's new write, each of its refusals, and that a
    replay writes once.

## What the owner settled

- **The upload closes the month** (owner, 2026-10-25): the month's reconciliation can be opened
  with no statement and stays open until the PDF arrives.
- **The upload creates the lines the ledger lacks and flags the lines the PDF lacks** (owner,
  2026-10-25).
- **The PDF joins a card's halves** (owner, 2026-10-25): one PDF is one statement, every currency
  on it.
- **No ticking lines into the month by date** while it is open (owner, 2026-10-25): with no
  ending balance before the PDF, there is nothing to compare against.
- **Editing goes to the ledger's Edit form** (owner, 2026-10-25): the reconciliation screens
  stick to reconciliation work.
- **A card's bottom charges are each their own transaction on the statement's last day**
  (owner, 2026-10-25, question 1): interest, insurance, the membership fee and the mailing fee
  carry no date on the paper.
- **An installment purchase is one transaction a month,** each month's installment as the bank
  bills it (owner, 2026-10-25, question 2, A), so every statement adds up.
- **A flagged line never stops the close** (owner, 2026-10-25, question 3, A). The engine's rule
  today refuses a complete while a line dated inside the statement's days is in no
  reconciliation (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Validation"),
  and on a card the days are the bank's processing days while a line carries its purchase day,
  so a line bought just before the last day and processed after it would stop every month. A
  month closed from its PDF is judged by the PDF instead: an engine ask.
- **Matching counts duplicates** (owner, 2026-10-25, question 4): the engine groups the PDF's
  lines and the ledger's by day, currency and amount and compares how many each group holds, so
  equal lines on one day are all accounted for: matched up to the smaller count, the PDF's extra
  ones created, the ledger's extra ones flagged.
- **An account keeps its card numbers, with their days** (owner, 2026-10-25, question 5): a card
  replaced with its balance carried over stays the account ("this account was card XXXX up to
  DD/MM/YYYY, then card YYYY"); a closed card ends its account. Which of the owner's card numbers
  are which account is set in the app, card by card, once the field exists.
- **A month can be opened before its PDF** (owner, 2026-10-25, question 6, A): the upload closes
  the open one, or creates it.
- **The PDF overturns "no PDF"** in [file-import-plan.md](../file-import-plan.md) (owner,
  2026-10-25), for statements.

## Questions for the owner

Questions 9 to 11 are about the account's name (point 8).

7. **Picking the account.** A PDF names its card (by number) or its bank account (by its full
   account number).
   - **A.** The engine finds the account from that number; you pick only when no account holds
     it.
   - **B.** You pick the account each time, as the bank-file import asks, and the engine refuses
     a PDF of another account.

   **Recommended:** A, because the number names the account for certain once your accounts
   carry their numbers, and a wrong pick is impossible.
8. **Is this reading of question 3 right?** A ledger line dated inside the month that is not on
   its PDF never stops the close, wherever in the month it falls, near the end or not; it stays
   flagged for you. So the engine's rule that refuses a close while a line inside the days is in
   no reconciliation changes for a month closed from its PDF.
   - **A.** Yes.
   - **B.** No: only a line near the end of the month (bought before the last day, processed
     after it) may be left out; any other one stops the close until you fix it.

   **Recommended:** A, because the PDF is the bank's own record of the month, and a flagged line
   stays in front of you either way.
9. **A card's two accounts.** A card's soles and dollar accounts share one card number, so
   both would read `BCP 1234`.
   - **A.** The currency joins the name: `BCP 1234 PEN` and `BCP 1234 USD`.
   - **B.** Each gets an alias to tell them apart.

   **Recommended:** A, because it needs no typing and reads like the bank's own columns.
10. **A replaced card's name.** When a lost card is replaced and the account carries on (point
    7), its last 4 digits change.
    - **A.** The name follows the new card (`BCP 1234` becomes `BCP 5678`); an alias stays as it
      is.
    - **B.** The name keeps the first card's digits.

    **Recommended:** A, because the name then matches the card in your wallet and on the next
    PDF.
11. **Accounts with no bank number**, such as people, and cash if you keep any.
    - **A.** They keep a typed name, as today; bank and number are only for bank accounts and
      cards.
    - **B.** Every account must have a bank and a number.

    **Recommended:** A, because a person or cash has no bank number to show.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
