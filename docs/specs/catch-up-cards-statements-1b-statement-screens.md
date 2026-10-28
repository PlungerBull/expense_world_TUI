# The statement screens on the engine's new routes

Catches up to contract `e7393dd869963db1`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full" (`f91a1e0ae626c712` to `e06456a20aca6e4c`),
and the rename of card to holder in its hand-off of 2026-10-28, "A person carries an opening
balance, and a card is now called a holder everywhere" (`2cec1b59048f50dc` and
`e7393dd869963db1`; that hand-off's opening balance on a person is
caught up on its own, done on 2026-10-28). This is part 1b of
seven specs that share that range, run in this order:

1. part 1a, done on 2026-10-28: the app's reads and writes on the engine's new routes and
   names, the statement PDF upload among them;
2. this one: the statement screens on the engine's new routes, with nothing you see changing
   but the order of the flagged lines, now the statement's;
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

**Status: approved by the owner on 2026-10-28, with 1 A and 2 A; it runs after part 1a.** When done, the why moves to [decisions.md](../decisions.md)
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
   holder together (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it"), as the owner settled.
3. **The app quotes the engine's current words.** Every sentence of the engine's that the app's
   tests, docs and mockups quote says "statement" where the engine does, among them the
   sealed-period sentence (contract: "Transactions (Ledger)", "Sealed periods") and the refusal
   to delete a line in a completed statement.
4. **The app's own lines fit the engine's refusals.** A line for a refusal the engine no longer
   sends goes; the line on `t` for an account that has been in a statement goes, as the
   owner settled.

## How the owner knows it is done

1. On the practice engine, the Reconciliations screens list, create, tick, complete, revert and
   delete a statement, on an account with no statement code and on a card's account, as they
   do today.
2. After a close that flags lines, `f` lists every flagged line, more than one page of them
   included, in the statement's order.
3. The unit suite and the drift check pass. The live suite passes once parts 2a and 2b are done.

## What the owner settled

- **The lines a close flags show in the engine's order** (owner, 2026-10-28, 1 A): the statement's
  order, both currencies of a holder together, is the only order the engine gives this list
  (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it"), and it reads
  as the paper does. Part 7 redraws that screen.
- **When `t` is refused for an account that has been in a statement, the engine's words show
  alone** (owner, 2026-10-28, 2 A): the app's line about deleting reconciliations goes, since the
  engine refuses an account that was ever in a statement, a deleted one included
  (contract: POST /v1/accounts/{account_id}/make-person).

---

## Tasks

Drafted 2026-10-27; approved by the owner on 2026-10-28. Each leaves
`pytest tests/unit` green. Each task fixes the `(contract: …)` citations and the
[tui.md](../tui.md) and [runtime.md](../runtime.md) lines of the code it touches.

4. **The flagged lines from the review list (builder).** The flagged-lines screen pages
   `GET /bank-lines?unassigned_in_period_of=<id>&sort=statement` with its count, in the statement's
   order as the owner settled, instead of reading by ids.
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
   `HAS_OPENING_BALANCE`, and `PERSON_ACCOUNT` on the opening-balance route, which
   are gone ([decisions.md](../decisions.md) "A person carries an opening balance"); this spec
   drops `PERSON_ACCOUNT`'s lines on the statement routes), and
   `HAS_RECONCILIATION`'s goes too, as the owner settled; the comment heading test_errors.py's
   archived-account rows says what the rows prove (moved from test-suite-leftovers).
   *Passes if:* no doc or mockup quotes a sentence the engine no longer sends, and no app line
   names a reason the contract lacks.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e7393dd869963db1` (`f91a1e0ae626c712`, `f0ee03d6faa96af1`,
  `29228c5191b6669b`, `c3caf28dd580253d`, `e767584fd1b13108`, `dc990e964df6b627`,
  `743f76692347e6a4`, `e06456a20aca6e4c`, `2cec1b59048f50dc`, `e7393dd869963db1`), shared with
  the six other parts; `d34fc8d06ff652c4` and `4ac20e42cf8566ee`, between them, are
  answered by the catch-up on a person's opening balance, done on 2026-10-28.
- **The engine's "Done when" checks to report on:** every statement call uses `/statements`,
  at the level of the routes (one object per holder on screen is part 7's); a closed statement's
  review list pages in full through the review list route, with no ids sent.
- **The asks it closes:** a close's flagged lines past 200 ids.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- The card form that opens a statement shows two accounts, the open one and one other; on a
  holder of three or more, the engine refuses the statement with `HOLDER_ACCOUNTS_MISSING`
  (contract: POST /v1/statements). It joins the question on a holder of three currencies in
  [catch-up-cards-statements-1a-leftovers.md](catch-up-cards-statements-1a-leftovers.md). Found
  by task 1.
- A holder of two accounts with no statement code, possible now that pairing needs no code, opens
  the card form on `n` (its accounts line with no code), while its panel shows only the open
  account's columns. How such a card's statements look is the statement screen spec's to draw
  ([catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md)).
  Found by task 1's review.
- The one-account New statement form, opened on its own (only tests do), sends one balance even
  for an account whose holder holds two. Found by task 1's review.
