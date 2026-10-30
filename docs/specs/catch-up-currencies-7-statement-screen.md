# An account's statement on one screen

Catches up to contract `f82426fb0a099676`, from `e020782e3579d011`: the engine's hand-off of
2026-10-29, "An account holds its currencies: every route names an account and a currency code;
holders are gone" — its parts on what the statement screens show: a statement per account, a
starting and ending balance per currency it covers, a blank beginning balance, the close's
notes on a currency it does not cover (its section 9), and the PDF upload's screens (its
section 10).

The seven specs of this catch-up, run in this order:

1. part 1, the app's reads and writes (done on 2026-10-30)
2. [catch-up-currencies-2-statements-and-imports.md](catch-up-currencies-2-statements-and-imports.md)
3. [catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md)
4. [catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md)
5. [catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md)
6. [catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md)
7. this one

**Status:** draft, written 2026-10-29 for the owner to approve. It runs after
[catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md), last of the seven.
Its screens are drawn as mockups when it is named the current spec, every option
its own pane: panes 2A, 3A, 4A, 6A, 7A, 9B, 10B and 11B of
[expense-world-card-statement-questions.html](../mockups/expense-world-card-statement-questions.html)
and screens 1 to 3 of
[expense-world-statement-pdf-screens.html](../mockups/expense-world-statement-pdf-screens.html)
are redrawn in the account's words; panes 5A and 5B are drawn again for question 1.

---

## Why

The engine keeps an account's statement as one thing: one name, one set of days, one status
for the whole account, and a starting and ending balance for each currency with something in
it, never added together (contract: "Statements"). A Visa month can no longer be half closed.
[catch-up-currencies-2-statements-and-imports.md](catch-up-currencies-2-statements-and-imports.md)
keeps today's statement screens working on that. This spec makes the screens show the
statement the way the engine holds it, and the way the bank's paper prints it.

What the engine now holds, and today's screens do not show:

- **A statement covers a currency only when something is in it:** a line, or money at its start
  (the currency's balance the day before the first day is not zero). A Visa month with no dollar
  line and $0 owed has no dollar balances; with $300 owed it keeps them, `-30000` → `-30000`
  (contract: "Statements", "Which currencies a statement covers").
- **A beginning balance may be blank:** a dollar line placed in a soles-only draft gives the
  statement dollar balances, both blank, to be filled before it completes
  (contract: "Statements", "A line in a currency the statement holds no balances for gives it that currency's balances").
  A blank balance is "not entered", never zero, and its difference "not checked yet"
  (contract: "Statements", "A balance not entered is `null`, never zero").
- **Completing asks for what is missing:** a blank beginning balance, and a currency with money
  at the start the statement does not cover, are refused by name
  (contract: POST /v1/statements/{statement_id}/complete, "Every balance must be entered")
  (contract: POST /v1/statements/{statement_id}/complete, "Every currency with money at the start has balances in it").
- **The close reviews every currency,** a covered one or not: a currency the statement does not
  cover gets its own notes, in `not_covered`
  (contract: POST /v1/statements/{statement_id}/complete, "`not_covered`").
- **A statement's lines come in one order,** the paper's numbering across both currencies, then
  the lines with no place, oldest first (contract: "Statements", "A statement's order").
- **A line moved to its account's other currency can stay in its open statement**
  (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction").
- **An account's lines in no statement come in one read,** every currency together, with their
  count (contract: GET /v1/bank-lines, "Filters").
- **The engine says what to do with a flagged line** on an account with a statement code: keep
  the paper's, by deleting the flagged line; or keep your own, by reverting, deleting the line
  the upload made, moving yours to the row's day and uploading the PDF again
  (contract: POST /v1/statements/{statement_id}/complete, "What a client does with a flagged line").

## What it must do

1. **Every statement screen says "Statements"** where the app says "reconciliation": Home's
   LEDGER row, the crumbs, the titles, the questions and the notes.
2. **The browse lists one row per bank account,** its name and its currencies, and opens that
   account's statements, each row a statement with a difference per currency it covers, its
   status and its order, as pane 2A redrawn.
3. **A statement's screen shows the whole statement** (question 3 A): one list in the paper's
   order, both currencies mixed and numbered 1, 2, 3 … with no gaps, a currency column, each
   covered currency's starting, ending and difference once at the top, the opening balance
   listed apart (contract: GET /v1/bank-lines, "Ordering"). Its head shows a bracketed name
   whole, pinned by a test as the other heads in
   [test_tui_bracketed_names.py](../../tests/unit/test_tui_bracketed_names.py) are.
4. **A currency the statement does not cover** shows as question 2 picks, on the statement's
   head, on the list of statements and in the PDF preview; **a blank beginning balance** reads
   as question 3 picks.
5. **The New statement form** asks for the balances as question 1 picks, and sends one
   `POST /statements` with `account_id` and an entry per currency typed
   (contract: POST /v1/statements, "`balances`").
6. **`c` gets every balance it needs:** a covered currency's blank beginning or ending balance,
   and a currency with money at the start the engine names (`MONEY_AT_START_NOT_COVERED`), are
   entered as question 3 picks, saved with one `PUT /statements/{id}` naming only the currencies
   that change (contract: PUT /v1/statements/{statement_id}, "`balances`"), then completed. A
   currency with money at the start and no movement is closed by typing its ending balance in
   an empty box (question 4 A); the engine judges it
   (contract: POST /v1/statements/{statement_id}/complete, "Every currency adds up").
7. **After a line joins or moves,** the screen reads the statement again, so a currency it gained,
   blank, shows to be filled. A line moved to its account's other currency stays in its open
   statement (question 8 A), as the Edit form of
   [catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md) sends it.
8. **The close's notes show,** each covered currency's under its balances as today, and each
   `not_covered` entry's as question 4 picks.
9. **The flagged lines show whenever a statement has any** (question 6 A), open or completed,
   counted when the screen opens, every currency together in the statement's order; on an account
   with a statement code the engine's two ways read as words under the list (question 11 B).
10. **The lines in no statement are the whole account's,** every currency together, in one read
    with their count, oldest first (question 10 B and B).
11. **A completed statement's footer** shows `d` and not `c` (question 9 B). **An open statement
    on an account with a statement code waits for its PDF:** no ticking, no `c`.
12. **The PDF upload's and the bank download's account list** name each account by its own name
    and its currencies, every bank account in both (question 7 A and A). The PDF preview shows
    each covered currency's balances, and a currency it does not cover as question 2 picks
    (contract: POST /v1/statements/import, "Which currencies the statement covers").
13. **The new refusals read as question 5 picks:** on the upload `CURRENCY_NOT_HELD`,
    `ACCOUNT_CURRENCY_NOT_ON_PAPER`, `MONEY_AT_START_NOT_COVERED` on `file` and
    `CONCURRENT_CHANGE` (contract: POST /v1/statements/import, "Accounts")
    (contract: POST /v1/statements/import, "Concurrency"); on `POST /statements` and
    `PUT /statements/{id}`, `CONCURRENT_CHANGE` when a currency joins or leaves the account
    mid-write (contract: PUT /v1/statements/{statement_id}, "Sent at the same moment as another write").
14. **The mockups these screens replace are deleted, with their links:**
    `expense-world-card-statement.html`, `expense-world-statement-order.html`,
    `expense-world-statement-screen.html`, `expense-world-statement-flagged-lines.html` and
    `expense-world-card-statement-questions.html` in [mockups/](../mockups/), once the new
    screens' mockups are picked; they are linked from tui.md, decisions.md, todo.md,
    `reconciliations.py` and the statement screens' tests.

## How the owner knows it is done

1. The Visa's statement opens as one screen: both currencies' lines in the paper's one
   numbering, each currency's balances at the top, the opening balance apart.
2. A Visa month with no dollar line and $0 owed shows the dollars as question 2 picks, and
   completes with soles alone.
3. A Visa month with $300 owed in dollars and no dollar movement is created with its dollar
   balances, `-300.00` → `-300.00`, and completes; left out, it is refused by name and the screen
   asks for them as question 3 picks.
4. On an account with no statement code, ticking a dollar line into a soles-only draft shows
   the dollars blank, "not entered" as question 3 picks; `c` asks for them, and with them
   filled the statement completes.
5. The close's notes on a currency the statement does not cover show as question 4 picks.
6. An open statement on an account with a statement code offers no ticking and no `c`; a
   completed one offers `d` and not `c`.
7. The flagged lines show as question 6 says, and the account's lines in no statement list
   every currency together, oldest first.
8. A line moved to its account's other currency stays in its open statement.
9. The PDF upload and the bank download list each bank account once, its name and currencies;
   a PDF refusal shows as question 5 picks.
10. No screen says "reconciliation".
11. The unit suite, the live suite and the drift check pass.

## What the owner settled

All answered 2026-10-28, each as recommended, in the card statement spec this one rewrites:

- **Question 1 B:** "Statements", everywhere the app says "reconciliation", the same word as the
  engine's and the paper's.
- **Question 3 A:** one list in the paper's order, both currencies mixed and numbered 1, 2, 3 …
  with no gaps, a currency column, and each currency's starting, ending and difference once at
  the top.
- **Question 4 A:** a currency closed by hand with no movement (now: money at the start and no
  line) takes its ending balance typed as any; the box starts empty, and the engine judges it.
- **Question 6 A:** `⚑` and `f` show whenever a statement has flagged lines, open or completed,
  counted when the screen opens.
- **Question 7:** the account list of the PDF upload and the bank download names the account by
  its own name and its currencies (A), and the PDF upload lists every bank account, the same
  list as the download, an account with no statement code refused in the engine's words (A).
- **Question 8 A:** a transaction moved to its account's other currency while in an open
  statement stays in it.
- **Question 9 B:** a completed statement's footer drops `c`; `d` stays, and the engine's refusal
  says to revert first.
- **Question 10 B and B:** the list of lines in no statement is the whole account's, every
  currency together, in one read with its count, oldest first.
- **Question 11 B,** settled by the engine on 2026-10-28: on an account with a statement code, the
  flagged lines screen shows the engine's two ways as words; you do each step on the other
  screens.

And earlier:

- **An account with a statement code waits for its PDF** (owner, 2026-10-27, question 5 A of
  [expense-world-statement-pdf-screens.html](../mockups/expense-world-statement-pdf-screens.html)):
  its open statement offers no ticking and no `c`.
- **Editing goes to the ledger's Edit form** (owner, 2026-10-25): the statement screens stick to
  statement work.

## Questions for the owner

1. **The New statement form** [mockup to draw]. The engine needs a starting balance only for a
   currency with money at the start, and the app cannot know which that is: no read gives a
   currency's balance on a past day (contract: POST /v1/statements, "`balances`").
   - **A.** A starting and an ending balance line for each currency of the account, each
     optional; a currency left empty is not sent, and one the engine needs comes back refused by
     name, the cursor on its starting balance.
   - **B.** A `currencies` line first, then a starting and an ending balance for each currency
     picked.
   - **C.** As A, and an engine ask: a read of each currency's balance on a day, so the form
     marks the currencies that need a starting balance before it is sent.

   **Recommended:** A: the form you know, each line named by its currency, and the engine judges
   what is missing. The starting balance's second hint line,
   `0.00 if it holds the account's opening balance, which already counts it`, stays on each.
2. **A currency the statement does not cover** [mockup to draw], on the statement's head, the list
   of statements and the PDF preview.
   - **A.** A row of its own: `USD   nothing this month`.
   - **B.** No row: only the covered currencies show.

   **Recommended:** A: you see that the dollars were looked at and had nothing. The words are new
   to the app; "nothing this month" is the engine's suggestion. Keep them, or name others.
3. **A blank beginning balance, and how `c` gets the balances it needs** [mockup to draw].
   - **How a blank one reads:** **A.** `not entered`, the engine's suggestion, beside a
     difference reading `not checked yet`. **B.** A dim `—`, as an empty ending balance reads
     today.

     **Recommended:** A: blank is not zero, and the words say so.
   - **What `c` does:** **A.** On a draft with any blank balance, `c` opens a box for each one,
     starting balance then ending balance, currency by currency, as today's `Ending balance
     first` box; after a `MONEY_AT_START_NOT_COVERED` refusal it opens the same boxes for the
     currency the engine names; then the usual question. **B.** `c` shows the engine's words, and
     a key of its own opens the boxes for every covered currency.

     **Recommended:** A: one key leads through what is missing, as `c` does today.
4. **Where a `not_covered` currency's notes sit** [mockup to draw].
   - **A.** Under the head, beside the covered currencies' notes, each led by its currency:
     `⚠ USD: <the engine's sentence>`.
   - **B.** On the uncovered currency's own row (question 2 A).

   **Recommended:** B with question 2 A, else A.
5. **The upload's new refusals, and a currency joining or leaving mid-write.**
   - **A.** The engine's words alone, as every refusal shows, with the app's line for
     `CONCURRENT_CHANGE` that already exists (`It changed at the same moment: press r, then try
     again.` on a screen, `save again.` on a form).
   - **B.** On `CONCURRENT_CHANGE`, the app reads the account again and sends the write once more
     by itself.

   **Recommended:** A: the engine's words already say what to do, and nothing is sent that you
   did not ask for.

---

## Tasks

Each screen task waits on the mockups of its questions, picked by the owner. The builder reads
the question, the files named and the tui.md section named.

1. **"Statements" everywhere** (point 1). [home.py](../../expense/tui/screens/home.py),
   [reconciliations.py](../../expense/tui/screens/reconciliations.py) and their tests; tui.md §2
   and §4 where the screens are named. *Passes if:* no screen, crumb, question or note says
   "reconciliation"; a test fails on one; tui.md says "Statements".
2. **The browse and the list of statements** (point 2; questions 2 and 3). The browse and
   `statement_headers` in [reconciliations.py](../../expense/tui/screens/reconciliations.py) and
   their tests; tui.md §4 "The Reconciliations browse". *Passes if:* one row per bank account
   with its currencies; each statement row shows a difference per covered currency, its status
   and order, an uncovered currency and a blank balance as questions 2 and 3 pick; the tests
   pin each.
3. **The New statement form** (point 5; question 1). `NewReconciliationScreen` and
   `NewCardStatementScreen` in [reconciliations.py](../../expense/tui/screens/reconciliations.py),
   one form for every account, and its tests; tui.md §4 "A card statement's create form". *Passes
   if:* one `POST /statements` with `account_id` and an entry per currency typed; a currency left
   empty is not sent; `MONEY_AT_START_NOT_COVERED` puts the cursor on that currency's starting
   balance with the engine's words; the tests pin each.
4. **The statement's head and its one list** (points 3 and 4; questions 2 and 3). The detail
   screen in [reconciliations.py](../../expense/tui/screens/reconciliations.py),
   [test_tui_bracketed_names.py](../../tests/unit/test_tui_bracketed_names.py) and the statement
   tests; tui.md §4 "A reconciliation's batch screen". *Passes if:* the head shows each covered
   currency's balances, an uncovered one and a blank one as picked, a bracketed name whole; the
   list is the paper's order, both currencies in one numbering with a currency column, the
   opening balance apart; the tests pin each.
5. **`c` and the balances it needs** (point 6; questions 3 and 4 A). `ending_balance_body` and
   the `c` handler in [reconciliations.py](../../expense/tui/screens/reconciliations.py) and
   their tests; tui.md §4 "`c` needs the ending balance". *Passes if:* `c` asks for each blank
   balance as question 3 picks, saves them in one `PUT` naming only the changed currencies,
   then asks to complete; `BEGINNING_BALANCE_REQUIRED` and `MONEY_AT_START_NOT_COVERED` lead to
   the same boxes; a currency with no movement closes on an empty box typed; the tests pin each.
6. **Re-reads, notes and the footer** (points 7, 8 and 11; questions 4 and 5). The tick and
   complete handlers in [reconciliations.py](../../expense/tui/screens/reconciliations.py) and
   their tests; tui.md §4. *Passes if:* after a tick the screen reads the statement again and a
   currency it gained shows blank; `not_covered` notes show as question 4 picks; a completed
   statement's footer has `d` and not `c`; an open one on an account with a code has neither
   ticking nor `c`; `CONCURRENT_CHANGE` reads as question 5 picks; the tests pin each.
7. **The flagged lines and the lines in no statement** (points 9 and 10). `FlaggedLinesScreen`
   and the `u` list in [reconciliations.py](../../expense/tui/screens/reconciliations.py) and
   their tests; tui.md §4 "The lines a complete flagged for review". *Passes if:* `⚑` and `f`
   show whenever the review list counts any, open or completed; on an account with a code the
   two ways read as words; `u` lists the account's lines in no statement in one read with its
   count, oldest first; the tests pin each.
8. **The PDF upload and the account list; old mockups go** (points 12 to 14; questions 2 and 5).
   [statement_upload.py](../../expense/tui/screens/statement_upload.py),
   [bank_import.py](../../expense/tui/screens/bank_import.py), `account_picks` in
   [flow.py](../../expense/bank_import/flow.py) and their tests; tui.md §2 "A statement PDF
   closes its month". *Passes if:* the list names each bank account by name and currencies, in
   both doors; the preview shows covered and uncovered currencies as question 2 picks; each new
   refusal reads as question 5 picks; the replaced mockups are deleted and
   `test_docs_links.py` passes.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results, as
part 7 of 7 of the reply to `f82426fb0a099676`, the last.

- **Range:** `e020782e3579d011` → `f82426fb0a099676`, shared with the other six specs of this
  catch-up: its sections 9 and 10, on screen. It also reports that the earlier ranges' checks
  still open are answered by this catch-up as a whole, since the holder model they checked is
  gone: `46e2fdf6e11d7548` → `e7393dd869963db1`, the parts on the live suite, cards and the
  card's statement screen (parts 2a, 2b, 3 and 4 of that catch-up);
  `3e472b3256dcdc69` → `256f3190cf24fc36`, the hand-off "An account moves between holders, a
  holder is made and unmade with its accounts, and a holder's bank lines list in one read"; and
  `4dd95f836dba7be2` → `e020782e3579d011`, the parts of the hand-off "A person is a holder;
  unpairing is one write; the PDF upload moves a line one day off; the change log reaches back;
  your practice engine serves only shipped code" not answered by the reply for
  `e020782e3579d011`.
- **The engine's "Done when" checks to report on:** "A statement is the account's, with a
  starting and ending balance per currency it covers, and the PDF upload closes it."; and, for
  the whole catch-up, from the seven specs' results: "The TUI has read up to `f82426fb0a099676`
  and says so." and "No request in the TUI sends a `/holders` route, `POST /accounts/{id}/move`,
  `?holder_id=` or a per-currency id."
- **The asks it closes:** "An account holds its currencies: the holder becomes the account, and
  each account becomes one of its currencies". Answered by the account holding its currencies,
  with no holder left to move or make: "Yes to moving an account to another card, with the
  limits you proposed; no to the sheet import refusing a name used in two currencies", "Delete a
  card with its last account, so no client leaves an empty card behind", "Create a bank account
  and its own card in one write" and "Move an account onto a new holder in one write". Built
  here: "List a card's bank lines in no statement in one read" (question 10) and "Say what a
  client does with a flagged line on a card with a statement code" (question 11);
  "Name a flagged line's twin wherever the flagged lines are read" is answered differently by
  the engine (question 11).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
