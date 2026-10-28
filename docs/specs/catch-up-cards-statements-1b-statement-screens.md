# The statement screens on the engine's new routes

Catches up to contract `e7393dd869963db1`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full" (`f91a1e0ae626c712` to `e06456a20aca6e4c`),
and the rename of card to holder in its hand-off of 2026-10-28, "A person carries an opening
balance, and a card is now called a holder everywhere" (`2cec1b59048f50dc` and
`e7393dd869963db1`; that hand-off's opening balance on a person is
[catch-up-person-opening-balance.md](catch-up-person-opening-balance.md)'s). This is part 1b of
seven specs that share that range, run in this order:

1. [catch-up-cards-statements-1a-reads-and-writes.md](catch-up-cards-statements-1a-reads-and-writes.md):
   the app's reads and writes on the engine's new routes and names, the statement PDF upload
   among them;
2. this one: the statement screens on the engine's new routes, with nothing you see changing
   but the order of the flagged lines (question 1);
3. [catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md):
   the live tests' shared helpers, and a statement's life, on holders;
4. [catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md):
   the live tests of the upload on the published sample PDFs, bank lines, holders and people;
5. [catch-up-split-rows.md](catch-up-split-rows.md): the sheet import's counts line;
6. [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md): cards in the
   app;
7. [catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md):
   a card's statement on one screen.

It runs after part 1a, whose answer builders, account record and reads it uses.

**Status: draft, written 2026-10-27 for the owner to rewrite or approve; questions 1 and 2 wait
on the owner, and so do its tasks.** When done, the why moves to [decisions.md](../decisions.md)
and this file is deleted.

**Built on the holder names.** The engine's rename of card to holder is in the live contract
since `e7393dd869963db1` (shipped 2026-10-28): the routes are `/holders`, the field is
`holder_id` everywhere, and the reasons and messages say holder, with nothing behaving
differently: a statement carries `holder_id` (contract: "Statements"), the statements of a
holder are read with `GET /statements?holder_id=` (contract: GET /v1/statements), and a
statement missing an account of its holder is `HOLDER_ACCOUNTS_MISSING`
(contract: POST /v1/statements). "Card" stays the bank's product, a credit card and its paper.

---

## Why

On 2026-10-27 the engine made a holder's monthly statement one record for the whole holder
(contract: "Statements"). The routes the Reconciliations screens called are gone, so today these
break:

- the Reconciliations screens: the list, the new-statement form, ticking, complete, revert and
  delete;
- the lines a close flags.

This spec puts them back on the engine's new routes, **with the screens as they are today**: the
same keys, the same words, the same layout, each statement screen showing the account it is
opened on. The screens that change for whole-holder statements come in part 7, from mockups you
pick. It also brings every sentence of the engine's the app quotes up to the engine's words.

## What it must do

1. **Every statement read and write goes to the engine's statement routes.** One statement
   holds a balance per account of its holder, and each screen shows the account it is opened
   on, as it does today (contract: "Statements").
2. **The lines a close flags are read in full**, page by page, as the engine lists them, with
   no list of ids sent. The engine lists them in the statement's order, both currencies of a
   holder together (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it"); question 1.
3. **The app quotes the engine's current words.** Every sentence of the engine's that the app's
   tests, docs and mockups quote says "statement" where the engine does, among them the
   sealed-period sentence (contract: "Transactions (Ledger)", "Sealed periods") and the refusal
   to delete a line in a completed statement.
4. **The app's own lines fit the engine's refusals.** A line for a refusal the engine no longer
   sends goes; the line on `t` for an account that has been in a statement goes as question 2
   decides.

## How the owner knows it is done

1. On the practice engine, the Reconciliations screens list, create, tick, complete, revert and
   delete a statement, on an account with no statement code and on a card's account, as they
   do today.
2. After a close that flags lines, `f` lists every flagged line, more than one page of them
   included, in the order question 1 decides.
3. The unit suite and the drift check pass. The live suite passes once parts 2a and 2b are done.

## Questions for the owner

1. **The order of the lines a close flags.** Today they are listed oldest first. The engine
   now lists them only in the statement's order, both currencies of a holder together, and
   refuses any other order (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it").
   - **A.** Show them in the engine's order now.
   - **B.** Keep oldest first, by reading the lines by their ids, which the engine asks clients
     to stop doing, and which again stops at 200 lines.

   **Recommended:** A: it is the only order the engine gives this list, and it reads as the
   paper does. Part 7 redraws that screen anyway.

2. **The app's line when `t` is refused for an account that has been in a statement.** Today
   it says "On Reconciliations, press d on each of its reconciliations; a completed one needs u
   first." That is no longer true: the engine refuses an account that was ever in a statement,
   a deleted one included (contract: POST /v1/accounts/{account_id}/make-person).
   - **A.** Drop the app's line; the engine's own words show alone.
   - **B.** New words of the app's, drawn in a mockup first.

   **Recommended:** A: following the old line would delete statements and still be refused.

---

## Tasks

Drafted 2026-10-27; they wait on the owner's approval and on questions 1 and 2. Each leaves
`pytest tests/unit` green. Each task fixes the `(contract: …)` citations and the
[tui.md](../tui.md) and [runtime.md](../runtime.md) lines of the code it touches.

1. **The browse and the new-statement forms on the new routes (builder).** In
   [reconciliations.py](../../expense/tui/screens/reconciliations.py): the browse reads
   `GET /statements?holder_id=`, each row's balances from its account's entry in `balances`; the
   create forms send `POST /statements` with the holder (`holder_id`) and every account's
   balances; the "no batch" `!` mark matches a statement by its holder's accounts, its helper named for what it
   marks (today `blocking_windows`), and the `unfiled_rows` docstring and the comment over
   `UNFILED_FILTER` say what is true (catch-up leftovers).
   *Passes if:* the browse and create tests pass on the new answers, a refusal keyed
   `balances.<account_id>.<field>` lands under its field, and the browse's old builders are
   gone.
2. **A statement's screen read and shown from the new routes (builder).** reconciliations.py's
   detail screen reads `GET /statements/{id}` and shows the opened account's balances from its
   entry in `balances`, its header and lines as today.
   *Passes if:* the detail screen's reading and drawing tests pass on the new answers, and its
   refresh reads the statement by its id.
3. **A statement's actions on the new routes (builder).** The detail screen ticks with
   `statement_id`, saves the ending balance in `balances`, and completes, reverts and deletes
   under `/statements`; the close's `warnings` and `coverage_gap` are read per balance, the
   `GAP` fixture quoting the engine's current sentence (moved from test-suite-leftovers); a
   complete with no transaction is refused as `NO_TRANSACTIONS_ASSIGNED` keyed
   `balances.<account_id>.transactions`, `"At least one transaction must be assigned."`, once
   per account, under the top-level `"Cannot complete a statement with no transaction on any of
   its accounts."` (the engine's hand-off of 2026-10-28, its section 4).
   *Passes if:* the detail screen's tick, balance, complete, revert and delete tests pass on the
   new answers, the `NO_TRANSACTIONS_ASSIGNED` refusal lands under the opened account's
   transactions, the `GAP` fixture's last uncovered day falls before the statement's first, and
   no reconciliation builder is left.
4. **The flagged lines from the review list (builder).** The flagged-lines screen pages
   `GET /bank-lines?unassigned_in_period_of=<id>&sort=statement` with its count, as question 1
   decides, instead of reading by ids.
   *Passes if:* a unit test pages more than one page of flagged lines with no `ids` sent, and the
   count is the engine's.
5. **The engine's current words in the unit tests (builder).** Every quote of the engine's
   "completed reconciliation" words in tests/unit and helpers.py's `LOCK_MESSAGES` says what
   the engine sends now, the sealed-line delete's sentence read from the practice engine
   (moved from test-suite-leftovers; the contract does not print it).
   *Passes if:* no unit test quotes a sentence the engine no longer sends.
6. **The engine's current words in the docs, and the app's lines for its refusals (builder).**
   The same words in tui.md and the grouped-refusals mockup;
   [errors.py](../../expense/errors.py)'s lines for reasons no longer sent go (but
   `HAS_OPENING_BALANCE` and `PERSON_ACCOUNT`, in errors.py, tui.md and test_errors.py, which
   [catch-up-person-opening-balance.md](catch-up-person-opening-balance.md) removes), and
   `HAS_RECONCILIATION`'s as question 2 decides; the comment heading test_errors.py's
   archived-account rows says what the rows prove (moved from test-suite-leftovers).
   *Passes if:* no doc or mockup quotes a sentence the engine no longer sends, and no app line
   names a reason the contract lacks.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e7393dd869963db1` (`f91a1e0ae626c712`, `f0ee03d6faa96af1`,
  `29228c5191b6669b`, `c3caf28dd580253d`, `e767584fd1b13108`, `dc990e964df6b627`,
  `743f76692347e6a4`, `e06456a20aca6e4c`, `2cec1b59048f50dc`, `e7393dd869963db1`), shared with
  the six other parts; `d34fc8d06ff652c4` and `4ac20e42cf8566ee`, between them, are
  [catch-up-person-opening-balance.md](catch-up-person-opening-balance.md)'s.
- **The engine's "Done when" checks to report on:** every statement call uses `/statements`,
  at the level of the routes (one object per holder on screen is part 7's); a closed statement's
  review list pages in full through the review list route, with no ids sent.
- **The asks it closes:** a close's flagged lines past 200 ids.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
