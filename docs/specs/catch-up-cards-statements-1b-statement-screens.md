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

Every task is done (2026-10-28); the tester's acceptance check and the librarian's sweep remain.

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
- The `⚑` count right after a close is the length of every balance's `review_lines` joined, and
  a line flagged on two accounts is in both, so it can read one too many until the flagged screen
  has counted; the engine's count (`GET /bank-lines/count?unassigned_in_period_of=`) would be
  exact. Found by task 4.
- `fetch_bank_lines_by_ids` keeps a `sort` parameter, and a paragraph on ordering, that no app
  code passes any more; and the flagged-lines test's fake engine asserts `ids` is never sent
  inside the screen's worker, whose `except` turns a failure into a toast, so a regression fails
  by timeout, not by the assertion. Found by task 4's review.
- The flagged screen's head is blank while its first read loads; reading the count first and
  drawing the head as it lands would show it sooner, still the engine's count. Found by task 4's
  review.
- Engine words in unit tests that name no statement and were not checked: a missing bank line is
  "Bank line not found." in test_tui_delete.py and test_tui_flagged_lines.py but
  "bank_line not found." as the practice engine sends it in test_tui_reconciliations.py; the
  opening balance's zero-amount case says "Amount cannot be zero." where the contract prints
  "Must not be zero."; the sealed-line words cite the complete instead of the
  bank-line and transaction deletes; and some test names still say reconciliation. Found by
  task 5 and its review.
- tests/unit/test_tui_account_kind.py keeps the old `HAS_RECONCILIATION` words for `t` on a
  bank account: its route, `POST /accounts/{id}/make-person`, answers `404` from contract
  `0cf6711e3a98fefe`, so the catch-up to that contract rebuilds `t` on the holder's route and
  this test with it (owner, 2026-10-28, A). Found by task 5.
- tests/unit/test_no_read_only_fields.py still sends `places` to
  `PUT /reconciliations/{id}/statement-order`, a route the contract no longer has (only
  `GET /v1/statements/{statement_id}/statement-order`), with a dead citation. Found by task 6.
- The refusal drawn in `expense-world-edit-part.html` changed shape: the engine's message now
  names the other part of the bank line ("Transaction <id>, another part of the same bank line,
  refuses this change. …"), so the mockup needs a redraw, not a word swap. Found by task 6.
- `PERSON_TAKES_NO_STATEMENT` (contract `0cf6711e3a98fefe`) has no line or doc row; it is the
  catch-up to that contract's. Found by task 6.
- The citations and words of the routes contract `0cf6711e3a98fefe` dropped (the account archive,
  unarchive, make-person and make-account, `POST /people`) stay for the catch-up to that
  contract: tui.md ~830, 836, 898, 899, 903, 1000, 1001, 1148; errors.py ~198–203;
  decisions.md ~635, 717, 733; test_tui_account_kind.py (its docstrings, `_RECON_*` words and the
  test that a deleted statement lets `t` through, which the contract now denies); and
  `expense-world-person-reconciliations.html` and `expense-world-account-to-person.html`. The
  statement code's (tui.md ~1004, errors.py ~224, formatting.py ~284, test_tui_statement_code.py,
  `expense-world-statement-code-field.html`, and `statement_code` sent on `PUT /accounts`) are the
  cards spec's. Found by task 6 and its review.
