# A month's statement closes from the bank's PDF

Catches up to contract `592f2467fa3df75a`, from `309e31fd5c266941`: item 5 of the engine's
hand-off of 2026-10-26, the statement upload (`9063fab000b2e3d6`, worded again in
`9537a3f6276d7d85`). Its words follow contract `f82426fb0a099676`, where an account holds its
currencies and its statement holds balances for each currency with something in it.

**Status: approved and named the current spec by the owner on 2026-10-27, every question
answered; paused until the catch-up to `f82426fb0a099676` lands.** The upload is built; its move
to the account and its currencies is
part 2 of the currencies catch-up (done on 2026-10-30),
its live tests and the card's in
[catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md),
and the statement screen after a close in
[catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md). Every pick
the owner made here stands. When done, the why moves to [decisions.md](../decisions.md) and this
file is deleted.

---

## Why

Reconciling today means ticking each line into the month and putting the lines in the paper's
order by hand. That is not how a statement is checked: the bank sends the month as a PDF, and
the PDF already holds everything a reconciliation needs: each currency's starting and ending
balance, every line, and the lines' order on the paper. On a card, one PDF holds both
currencies, and it closes the account's one statement, every currency with something in it
together.

No statement holding lines on an account with a statement code can be completed by hand: the
engine completes it only once every line has its place on the paper, and no route sets the
places by hand; the paper sets them
(contract: POST /v1/statements/{statement_id}/complete, "On an account with a statement code, the statement must be fully ordered").

So a month's statement is opened with no paper and stays open; when the PDF arrives,
uploading it closes the month. The engine does the work (contract: POST /v1/statements/import),
so the web and iPhone apps get it for free; the app sends the file and shows the answer.

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

The engine read all 62 of the owner's PDFs (42 account, 20 card) and closed each with a
difference of zero, on 2026-10-26.

## What it must do

1. **Upload a month's PDF statement** from the app, for any account with a statement code: the
   Visa, one account in soles and dollars, or a savings account, one account in one currency.
   You drop the PDF on the LOG bar, as a bank download is dropped, and pick its account from the
   same list (one line per account): screens A1 and A2 of
   [expense-world-statement-pdf-upload.html](../mockups/expense-world-statement-pdf-upload.html).
2. **The engine closes the month from it** in one write: it creates the account's statement if
   none is open, or fills the open one, sets each currency's starting and ending balance from the
   PDF, matches each PDF line to a ledger line, creates the lines the ledger lacks, puts every
   line in the PDF's order, and completes the statement, the account's currencies with something
   in it at once.
3. **Lines in the ledger that the PDF does not hold are never changed or deleted.** A line in
   the month's open statement that the PDF does not print is taken out of it; a line on a day
   the PDF covers that is in no statement is flagged by the close, and shows as a close's
   flagged lines show (built in the catch-up spec), before and after the close.
4. **Before anything is written, the app shows what the upload would do**: each PDF line,
   matched, to be created, or an empty `0.00` line; which matched lines the engine moves to the
   paper's day, one day off it with the same amount; the lines it would take out; and each
   currency's balances. You confirm and it is written, or nothing is. The screens are picked
   from a mockup before they are built.
5. **A refused upload says why in the engine's words** and writes nothing: a PDF the engine
   cannot read, one whose lines don't add up to its own totals, a month already completed, an
   account with no statement code, a savings account's paper sent to an account whose other
   currency has a line, balances or money at the start in the month
   (`ACCOUNT_CURRENCY_NOT_ON_PAPER`), a currency the paper shows something in that the account
   does not hold (`CURRENCY_NOT_HELD`), money at the start in a currency the paper shows at zero
   with no row (`MONEY_AT_START_NOT_COVERED` on `file`), and the open statement changing while
   the upload writes (`CONCURRENT_CHANGE`, send it again).
6. **The reconciliation screens do only reconciliation work.** Editing a line from them opens the
   ledger's Edit form, as `⏎` on a "no batch" row does today.
7. **A live test closes a statement from a made-up PDF**, dry run and apply, and proves each
   refusal and that a replay writes once; one refusal is a line dated in the future, named
   "Row <place>: Must not be in the future." on `rows.<place>.date`. The PDF is made up: never one of your real statements,
   since this repo is public.

## How the owner knows it is done

1. The owner uploads a card's PDF for a month with no statement yet: the account's statement
   is created with each currency's balances from the PDF, every line is in the statement in the
   PDF's order, and the statement is completed; each line's statement line (read through the
   engine, never shown) matches its row on the paper, every currency in one numbering.
2. The same with a month opened beforehand and left open: the upload closes that one.
3. A PDF line the ledger lacks is created by the upload, under `@Pendiente` and the pending
   hashtag, and lands in the statement.
4. A ledger line dated inside the month that the PDF does not hold is shown as flagged after
   the upload, unchanged and outside the statement.
5. The preview shows all of it before anything is written, and leaving the preview writes
   nothing.
6. An account statement (one currency, an account holding one) closes the same way.
7. The reconciliation screen of a closed statement lists its lines in the PDF's order, its opening
   balance apart.
8. Uploading the PDF of a month already completed is refused with the engine's words and writes
   nothing.
9. A card's bottom charges (interest, insurance, the membership fee, the mailing fee) each land
   as their own transaction on the statement's last day.
10. Two identical lines on one day (same currency and amount) on the PDF and two in the ledger
    match both; two on the PDF and one in the ledger create one; one on the PDF and two in the
    ledger flag one.
11. A ledger line dated inside the month that the PDF does not hold does not stop the close.
12. A card month with dollars owed and no dollar line still closes in dollars, with equal
    starting and ending dollar balances and no line; a month with $0 owed and no dollar line
    gives no dollar balances, shown as "nothing this month" in the words
    [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md)'s
    question picks.
13. The live contract suite proves the upload, each of its refusals (a future-dated line's
    words, and a savings account's paper sent to an account whose other currency has a line,
    balances or money at the start, among them), and
    that a replay writes once, on the engine's published sample PDFs and on papers drawn to
    its stated layout.

## What the owner settled

- **The upload closes the month** (owner, 2026-10-25): the month's statement can be opened
  with no paper and stays open until the PDF arrives.
- **The upload creates the lines the ledger lacks and flags the lines the PDF lacks** (owner,
  2026-10-25).
- **One PDF closes one account's statement** (owner, 2026-10-25): every currency on it, together
  (contract: "Statements", "Which currencies a statement covers").
- **No ticking lines into the month by date** while it is open (owner, 2026-10-25): with no
  ending balance before the PDF, there is nothing to compare against.
- **Editing goes to the ledger's Edit form** (owner, 2026-10-25): the reconciliation screens
  stick to reconciliation work.
- **A card's bottom charges are each their own transaction on the statement's last day**
  (owner, 2026-10-25, question 1): interest, insurance, the membership fee and the mailing fee
  carry no date on the paper.
- **An installment purchase is one transaction a month,** each month's installment as the bank
  bills it (owner, 2026-10-25, question 2, A), so every statement adds up.
- **A flagged line never stops the close** (owner, 2026-10-25, question 3, A), wherever in the
  month it falls: the engine completes the statement and flags the line
  (contract: POST /v1/statements/{statement_id}/complete, "A line in no statement is not a refusal").
- **Matching counts duplicates** (owner, 2026-10-25, question 4): equal lines on one day are all
  accounted for, matched one to one up to the smaller count, the PDF's extra ones created, the
  ledger's extra ones flagged.
- **A month can be opened before its PDF** (owner, 2026-10-25, question 6, A): the upload closes
  the open one, or creates it.
- **The upload starts from the LOG bar** (owner, 2026-10-27, question 7, A): the PDF is
  dropped as a bank download is, and its account picked from the same list; screens A1 and A2
  of [expense-world-statement-pdf-upload.html](../mockups/expense-world-statement-pdf-upload.html)
  are approved.
- **The preview is the check against a wrong account's PDF** (owner, 2026-10-27, question 8,
  A): accounts carrying their numbers, and the engine checking a PDF's number against its
  account, are their own spec after this one ("Found along the way").
- **The PDF overturns "no PDF"** in [file-import-plan.md](../file-import-plan.md) (owner,
  2026-10-25), for statements.

## What the engine settled

From the live contract (contract: POST /v1/statements/import):

- **You name the account; the engine never picks it** by the card or account number the paper
  prints. The account needs a statement code
  (contract: POST /v1/statements/import, "Accounts").
- **A line the upload creates** is filed under `@Pendiente` and the pending hashtag, the paper's
  text as its title, for you to classify later.
- **A ledger line one day off a PDF line is matched** and moved to the paper's day on the close
  (contract: POST /v1/statements/import, "The bank's day wins"); the preview marks it
  `· day moved`.
- **A card's currency with no row still closes,** with no line, inside the account's statement,
  when the statement covers it
  (contract: POST /v1/statements/import, "A card's currency with no row still closes"); one the
  paper shows at zero with no row gets no balances
  (contract: POST /v1/statements/import, "A currency the paper shows at zero with no row").
- **A currency of the account the paper does not print** is left out when it has nothing in the
  month, and refused (`ACCOUNT_CURRENCY_NOT_ON_PAPER`) when it has a line, balances or money at
  the start
  (contract: POST /v1/statements/import, "A currency of the account the paper does not print at all").
- **Every currency the paper shows something in is one the account holds**, or the upload is
  refused (`CURRENCY_NOT_HELD`)
  (contract: POST /v1/statements/import, "Every currency the paper shows something in must be one the account holds").
- **A completed month is refused**: revert it first, then upload again; the same PDF then
  matches every line the first upload created.

## Questions for the owner

None open.

---

## Tasks

Approved by the owner on 2026-10-27. The screens are picked in
[expense-world-statement-pdf-screens.html](../mockups/expense-world-statement-pdf-screens.html):
screens 1 to 4 as drawn, 5 A and 6 A. Tasks 2 and 3, the upload's live tests and the upload in
the app, are built; their move to contract `f82426fb0a099676` is
part 2 of the currencies catch-up (done on 2026-10-30), and in [catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md).
Task 4, the statement screen after a close, is in
[catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md), with
screen 4 redrawn for a statement with a balance per currency it covers. Task 6, the card's live
tests, is in
[catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md),
built on the engine's sample PDFs. The one task left runs after
[catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).

5. **The docs say what changed (builder).** [file-import-plan.md](../file-import-plan.md) says
   the PDF closes an account's month in its statement, with no "draft spec" and no "reconciliation"
   left in that line; no doc speaks of a card statement's halves or calls the PDF's statement a
   reconciliation; [commands.md](../commands.md) and [runtime.md](../runtime.md) follow if they
   name the bank files the app takes.
   *Passes if:* no doc says the app takes no PDF, none speaks of a statement's halves, and
   each fact has one home.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** item 5 of the hand-off (`9063fab000b2e3d6`, `9537a3f6276d7d85`); the range as a
  whole is confirmed in the reply "Caught up with contract 592f2467fa3df75a: the terminal app sends a
  bank download whole, …". The upload's move to `f82426fb0a099676` is reported in the replies
  of the catch-up specs named in the status.
- **The engine's "Done when" checks to report on:** no code reads a PDF itself; the contract
  tests upload a made-up statement PDF with a dry run and an apply.
- **The asks it closes:** none; the engine built the upload ahead of this client's ask.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **Accounts carry their numbers, and a PDF is checked against its account** (question 8,
  A): a spec of its own after this one, holding the three points below.
  - **An account keeps its card numbers over time.** A card replaced with its balance carried
    over (a lost card, say) stays the same account: the account records which card number it had
    until which day and which one after (owner, 2026-10-25, question 5). A card that is closed
    ends its account, and a new card is a new account. Which of the owner's card numbers are
    which account is set in the app, card by card, once the field exists.
  - **An account's name comes from its bank and its number** (owner, 2026-10-25): an account holds
    its bank and the last 4 digits of its card or account number, and an optional alias; it shows
    as bank + last 4 digits (`BCP 1234`), or as its alias when it has one. The engine holds the
    fields and the rule and serves the name to show.
  - Its open questions: a replaced card's name (follows the new card, or keeps the first);
    accounts with no bank number, such as people and cash (keep a typed name, or must have one).

