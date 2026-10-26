# A month's statement closes from the bank's PDF

**Status: draft, for the owner to rewrite or approve; its questions wait on the owner. Its tasks
are drafted when the owner names it the current spec.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Reconciling today means ticking each line into the month and putting the lines in the paper's
order by hand. That is not how a statement is checked: the bank sends the month as a PDF, and
the PDF already holds everything a reconciliation needs: each currency's starting and ending
balance, every line, and the lines' order on the paper. On a card, one PDF holds both
currencies, so it is also what joins the card's soles and dollar halves into one statement.

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
7. **The engine asks follow the rule** ("Ask the engine to change" in
   [CLAUDE.md](../../CLAUDE.md)): the PDF is read, matched and closed by the engine; the app
   sends the file and shows the answer.

## How the owner knows it is done

These take the place of the checks [statement-lines-from-reconciliations.md](statement-lines-from-reconciliations.md)
moved here (its checks 4, 5, 6, 10, 11, 12 and part of 9).

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
9. The live contract suite proves the engine's new write, each of its refusals, and that a
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
- **The PDF overturns "no PDF"** in [file-import-plan.md](../file-import-plan.md) (owner,
  2026-10-25), for statements.

## Questions for the owner

1. **The charges at the bottom of a card statement** (interest, insurance, the membership fee,
   the mailing fee) carry no date and are in no download.
   - **A.** The upload creates each one as its own transaction on the statement's last day.
   - **B.** The upload creates one transaction holding them all, on the last day.

   **Recommended:** A, because each is a different charge you may want to categorize apart.
2. **An installment purchase.** The bank bills it one installment a month, as a line of that
   month's statement.
   - **A.** Each month's installment is its own transaction, as the bank bills it, so every
     statement adds up.
   - **B.** The whole purchase is one transaction on the day you bought it; then a month's
     statement does not add up while installments are left.

   **Recommended:** A, because the statement can only close when it adds up.
3. **A flagged line and closing.** A ledger line dated inside a card's month but not on its PDF
   is usually next month's: bought just before the last day, processed after it.
   - **A.** Flagged lines never stop the close; they wait for next month's PDF, or for you.
   - **B.** The month closes only once every flagged line is fixed or deleted.

   **Recommended:** A, because otherwise almost every card month would be stuck on lines that
   belong to the next one.
4. **Two identical lines.** Two charges on the same day, same amount, same currency (two parking
   tickets) can match either ledger line.
   - **A.** The engine takes either; they are the same to the statement.
   - **B.** You pick which.

   **Recommended:** A, because nothing tells them apart and the result is the same.
5. **Which card statements are one account?** Your card statements come under four card
   numbers. Two changes carry the balance on (a replaced card: the same account), and one starts
   from zero (a new card). Is each run one account in the app, and which app account is which?
   **Recommended:** none: only you know.
6. **Opening the month first.** When no statement is open for the month, the upload creates it.
   Should opening one beforehand stay possible?
   - **A.** Yes: open it when you like; the upload closes the open one or creates it.
   - **B.** No: the upload always creates it; `n` goes from the card's list.

   **Recommended:** A, because it is what you described, and the upload works either way.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
