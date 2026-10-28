# The app talks to cards and statements again

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full" (`f91a1e0ae626c712` to `e06456a20aca6e4c`).
This is part 1 of five specs that share that range, run in this order:

1. this one: the app on the engine's new routes and names, with nothing you see changing;
2. [catch-up-cards-statements-2-live-suite.md](catch-up-cards-statements-2-live-suite.md): the
   live tests on cards, statements and the published sample PDFs;
3. [catch-up-split-rows.md](catch-up-split-rows.md): the sheet import's counts line;
4. [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md): cards in the
   app;
5. [catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md):
   a card's statement on one screen.

**Status: draft, written 2026-10-27 for the owner to rewrite or approve; questions 1 and 2 wait
on the owner, and so do its tasks.** When done, the why moves to [decisions.md](../decisions.md)
and this file is deleted.

---

## Why

On 2026-10-27 the engine made a card its own thing, holding its accounts, one per currency, and
made a card's monthly statement one record for the whole card (contract: "Cards")
(contract: "Statements"). The routes the app called for reconciliations are gone, and several
names the app sends and reads were renamed. The engine on your computer already runs this
version, so today these break:

- the Reconciliations screens: the list, the new-statement form, ticking, complete, revert and
  delete;
- moving a transaction to another account, on the Edit form or several at once in the ledger;
- the statement PDF upload, and the bank download's list of accounts;
- the lines a close flags.

This spec puts all of it back on the engine's new routes, **with the screens as they are
today**: the same keys, the same words, the same layout. The screens that change for cards and
whole-card statements come in parts 4 and 5, from mockups you pick.

**Still broken after this spec, until part 4 ("Cards in the app"):** creating a bank account,
`t` turning a person back into a bank account, `a` archiving a bank account, and the sheet
import's `--create-names`. Each needs a card, and how the app gives an account its card is your
pick in part 4. Until then, each shows the engine's refusal.

## What it must do

1. **Every statement read and write goes to the engine's statement routes.** One statement
   holds a balance per account of its card, and each screen shows the account it is opened
   on, as it does today (contract: "Statements").
2. **A transaction's statement is named as the engine names it now.** A move to another
   account takes the transaction out of its statement, as today, under the new name
   (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment").
3. **A card's accounts are found through the card.** The bank download's and the PDF upload's
   account list pairs a card's two accounts from the card, with the line's words as today
   (contract: "Cards").
4. **The statement PDF upload works again on the engine's new route and answer**, with its
   screens as built. A savings PDF sent for a card that holds another currency is refused in
   the engine's words (contract: POST /v1/statements/import, "Every account of the card is on the paper").
5. **The lines a close flags are read in full**, page by page, as the engine lists them, with
   no list of ids sent. The engine lists them in the statement's order, both currencies of a
   card together (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it"); question 1.
6. **The app quotes the engine's current words.** Every sentence of the engine's that the app's
   tests, docs and mockups quote says "statement" where the engine does, among them the
   sealed-period sentence (contract: "Transactions (Ledger)", "Sealed periods") and the refusal
   to delete a line in a completed statement.
7. **The app's own lines fit the engine's refusals.** A line for a refusal the engine no longer
   sends goes; the line on `t` for an account that has been in a statement goes as question 2
   decides.

## How the owner knows it is done

1. On the practice engine, the Reconciliations screens list, create, tick, complete, revert and
   delete a statement, on an account with no statement code and on a card's account, as they
   do today.
2. Moving a transaction to another account saves, and says it left its reconciliation, as
   today.
3. A statement PDF upload previews and closes its month, as built.
4. After a close that flags lines, `f` lists every flagged line, more than one page of them
   included.
5. The unit suite and the drift check pass, the drift check reading `e06456a20aca6e4c`. The
   live suite passes once part 2 is done.

## Questions for the owner

1. **The order of the lines a close flags.** Today they are listed oldest first. The engine
   now lists them only in the statement's order, both currencies of a card together, and
   refuses any other order (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it").
   - **A.** Show them in the engine's order now.
   - **B.** Keep oldest first, by reading the lines by their ids, which the engine asks clients
     to stop doing, and which again stops at 200 lines.

   **Recommended:** A: it is the only order the engine gives this list, and it reads as the
   paper does. Part 5 redraws that screen anyway.

2. **The app's line when `t` is refused for an account that has been in a statement.** Today
   it says "On Reconciliations, press d on each of its reconciliations; a completed one needs u
   first." That is no longer true: the engine refuses an account that was ever in a statement,
   a deleted one included (contract: POST /v1/accounts/{account_id}/make-person).
   - **A.** Drop the app's line; the engine's own words show alone.
   - **B.** New words of the app's, drawn in a mockup first.

   **Recommended:** A: following the old line would delete statements and still be refused.

---

## Tasks

Drafted 2026-10-27; they wait on the owner's approval. Each leaves `pytest tests/unit` green.
Each task fixes the `(contract: …)` citations and the [tui.md](../tui.md) and
[runtime.md](../runtime.md) lines of the code it touches.

1. **The fake engine answers as the new engine does (builder).** In
   [helpers.py](../../tests/unit/helpers.py): answer builders for the statement routes and the
   card routes, marked `@answer_of`, and one account-record builder carrying `card_id` and no
   statement code or partner, for every unit test to use (the ten files that build their own
   `_account` switch to it; test-suite leftovers point 1). The old reconciliation builders stay
   until their last user moves, in tasks 4 to 6.
   *Passes if:* the new builders match the live contract's answers in the drift check, and every
   unit test builds an account through the one builder.
2. **The new names on transactions and bank lines (builder).** `reconciliation_id` becomes
   `statement_id` and `left_reconciliation` becomes `left_statement` in
   [reads.py](../../expense/reads.py), [bank_line_write.py](../../expense/bank_line_write.py),
   [edit_form.py](../../expense/tui/screens/edit_form.py) and
   [transactions.py](../../expense/tui/screens/transactions.py), with their fixtures and tests;
   the words on screen stay.
   *Passes if:* unit tests pin a move sending `statement_id: null` and reading `left_statement`,
   and the drift check no longer names either old field.
3. **Cards and statements read through the engine (builder).** In reads.py: the statement
   list by card, one statement by id, and the cards list, and a helper that finds a card's
   accounts, replacing `card_partners`. [flow.py](../../expense/bank_import/flow.py)'s
   `account_picks` pairs a card's accounts from the card, keeping its words, and
   `reconciliation_names` reads `GET /statements/{id}`.
   *Passes if:* unit tests pin a card's two accounts as one line and an account alone on its
   card as its own, and the bank import's stopping statement is named through the new read.
4. **The statement upload on the new route (builder).**
   [statement.py](../../expense/bank_import/statement.py),
   [statement_upload.py](../../expense/tui/screens/statement_upload.py) and flow.py's
   `statement_call` use `POST /statements/import` and read its answer's `balances`,
   `creates`, `statement_id` and `statement`; the flagged lines come from each balance's
   `review_lines`; `CARD_ACCOUNT_NOT_ON_PAPER` shows in the engine's words. The screens stay
   as built.
   *Passes if:* the 26 tests of test_tui_statement_upload.py pass on the new answer, a new one
   pins `CARD_ACCOUNT_NOT_ON_PAPER`, and the old upload builder is gone.
5. **The browse and the new-statement forms on the new routes (builder).** In
   [reconciliations.py](../../expense/tui/screens/reconciliations.py): the browse reads
   `GET /statements?card_id=`, each row's balances from its account's entry in `balances`; the
   create forms send `POST /statements` with the card and every account's balances; the "no
   batch" `!` mark matches a statement by its card's accounts, its helper named for what it
   marks (today `blocking_windows`), and the `unfiled_rows` docstring and the comment over
   `UNFILED_FILTER` say what is true (catch-up leftovers).
   *Passes if:* the browse and create tests pass on the new answers, a refusal keyed
   `balances.<account_id>.<field>` lands under its field, and the browse's old builders are
   gone.
6. **A statement's screen on the new routes (builder).** reconciliations.py's detail screen
   reads `GET /statements/{id}`, shows the opened account's balances from `balances`, ticks
   with `statement_id`, saves the ending balance in `balances`, and completes, reverts and
   deletes under `/statements`; the close's `warnings` and `coverage_gap` are read per
   balance, the `GAP` fixture quoting the engine's current sentence (test-suite leftovers
   point 4).
   *Passes if:* the detail tests pass on the new answers, the `GAP` fixture's last uncovered
   day falls before the statement's first, and no reconciliation builder is left.
7. **The flagged lines from the review list (builder).** The flagged-lines screen pages
   `GET /bank-lines?unassigned_in_period_of=<id>&sort=statement` with its count, as question 1
   decides, instead of reading by ids.
   *Passes if:* a unit test pages more than one page of flagged lines with no `ids` sent, and the
   count is the engine's.
8. **The engine's current words, and the app's lines for its refusals (builder).** Every quote
   of the engine's "completed reconciliation" words in tests/unit, helpers.py's
   `LOCK_MESSAGES`, tui.md and the grouped-refusals mockup says what the engine sends now, the
   sealed-line delete's sentence read from the practice engine (test-suite leftovers point 15;
   the contract does not print it); [errors.py](../../expense/errors.py)'s lines for reasons no
   longer sent go, and `HAS_RECONCILIATION`'s as question 2 decides; the comments heading
   test_errors.py's archived-account and account-to-person rows say what the rows prove
   (test-suite leftovers point 9).
   *Passes if:* no unit test, doc or mockup quotes a sentence the engine no longer sends, and
   no app line names a reason the contract lacks.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e06456a20aca6e4c` (`f91a1e0ae626c712`, `f0ee03d6faa96af1`,
  `29228c5191b6669b`, `c3caf28dd580253d`, `e767584fd1b13108`, `dc990e964df6b627`,
  `743f76692347e6a4`, `e06456a20aca6e4c`), shared with parts 2 to 5.
- **The engine's "Done when" checks to report on:** every statement call uses `/statements`,
  at the level of the routes (one object per card on screen is part 5's); a closed statement's
  review list pages in full through the review list route, with no ids sent; this client's
  contract snapshot is at `e06456a20aca6e4c`, and it reports having read up to it.
- **The asks it closes:** a close's flagged lines past 200 ids.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
