# The app reads and writes on the engine's new routes

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full" (`f91a1e0ae626c712` to `e06456a20aca6e4c`).
This is part 1a of seven specs that share that range, run in this order:

1. this one: the app's reads and writes on the engine's new routes and names, the statement
   PDF upload among them, with nothing you see changing;
2. [catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md):
   the statement screens on the engine's new routes, with nothing you see changing;
3. [catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md):
   the live tests' shared helpers, and a statement's life, on cards;
4. [catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md):
   the live tests of the upload on the published sample PDFs, bank lines, cards and people;
5. [catch-up-split-rows.md](catch-up-split-rows.md): the sheet import's counts line;
6. [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md): cards in the
   app;
7. [catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md):
   a card's statement on one screen.

**Status: draft, written 2026-10-27 for the owner to rewrite or approve; its tasks are drafted
and wait on the owner's approval.** When done, the why moves to [decisions.md](../decisions.md)
and this file is deleted.

**Waits on the engine's rename** (the engine coders' answer of 2026-10-27, "Which of the
terminal app's seven card and statement specs the engine's coming changes touch"). The engine's
next breaking change renames card to holder: `/cards` becomes `/holders`, `card_id` becomes
`holder_id` everywhere, and every card-named reason and message says holder, with nothing
behaving differently; this spec is built on the holder names once that hand-off lands, so
nothing is renamed twice. People become holders in a later change, so the bank download's
account list is built only from holders that are not people.

---

## Why

On 2026-10-27 the engine made a card its own thing, holding its accounts, one per currency, and
made a card's monthly statement one record for the whole card (contract: "Cards")
(contract: "Statements"). The routes the app called for reconciliations are gone, and several
names the app sends and reads were renamed. The engine on your computer already runs this
version, so today these break:

- moving a transaction to another account, on the Edit form or several at once in the ledger;
- the statement PDF upload, and the bank download's list of accounts;
- the Reconciliations screens (part 1b).

This spec puts the app's reads and writes, and the statement PDF upload, back on the engine's
new routes, **with the screens as they are today**: the same keys, the same words, the same
layout. The Reconciliations screens follow in part 1b; the screens that change for cards and
whole-card statements come in parts 6 and 7, from mockups you pick.

**Still broken after this spec, until part 6 ("Cards in the app"):** creating a bank account,
`t` turning a person back into a bank account, `a` archiving a bank account, and the sheet
import's `--create-names`. Each needs a card, and how the app gives an account its card is your
pick in part 6. Until then, each shows the engine's refusal.

## What it must do

1. **The fake engine the unit tests run against answers as the engine does now**: statements
   and cards on their own routes, and an account carrying its card (contract: "Cards").
2. **A transaction's statement is named as the engine names it now.** A move to another
   account takes the transaction out of its statement, as today, under the new name
   (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment").
3. **A card's accounts are found through the card.** The bank download's and the PDF upload's
   account list pairs a card's two accounts from the card, with the line's words as today
   (contract: "Cards").
4. **The statement PDF upload works again on the engine's new route and answer**, with its
   screens as built. A savings PDF sent for a card that holds another currency is refused in
   the engine's words (contract: POST /v1/statements/import, "Every account of the card is on the paper").

## How the owner knows it is done

1. Moving a transaction to another account saves, and says it left its reconciliation, as
   today.
2. A statement PDF upload previews and closes its month, as built.
3. The bank download's list of accounts shows a card's two accounts as one line, as today.
4. The unit suite and the drift check pass, the drift check reading `e06456a20aca6e4c`. The
   live suite passes once parts 2a and 2b are done.

## Questions for the owner

None: what you see stays as it is. The two questions about the flagged lines and the app's
line on `t` are in part 1b.

---

## Tasks

Drafted 2026-10-27; they wait on the owner's approval. Each leaves `pytest tests/unit` green.
Each task fixes the `(contract: …)` citations and the [tui.md](../tui.md) and
[runtime.md](../runtime.md) lines of the code it touches.

1. **The fake engine answers on the statement and card routes (builder).** In
   [helpers.py](../../tests/unit/helpers.py): answer builders for the statement routes and the
   card routes, marked `@answer_of`. The old reconciliation builders stay until their last user
   moves, in part 1b.
   *Passes if:* the drift check names none of the new builders, and each is used by at least one
   unit test.
2. **One account record for every unit test (builder).** One account-record builder in
   helpers.py carrying `card_id` and no statement code or partner; the ten unit test files that
   build their own `_account` switch to it (test-suite leftovers point 1).
   *Passes if:* no unit test file defines its own `_account`, and no account fixture carries
   `statement_code` or `statement_partner_id`.
3. **The new names on transactions and bank lines (builder).** `reconciliation_id` becomes
   `statement_id` and `left_reconciliation` becomes `left_statement` in
   [reads.py](../../expense/reads.py), [bank_line_write.py](../../expense/bank_line_write.py),
   [edit_form.py](../../expense/tui/screens/edit_form.py) and
   [transactions.py](../../expense/tui/screens/transactions.py), with their fixtures and tests;
   the words on screen stay.
   *Passes if:* unit tests pin a move sending `statement_id: null` and reading `left_statement`,
   and the drift check no longer names either old field.
4. **Cards and statements read through the engine (builder).** In reads.py: the statement
   list by card, one statement by id, and the cards list, and a helper that finds a card's
   accounts, replacing `card_partners`. [flow.py](../../expense/bank_import/flow.py)'s
   `account_picks` pairs a card's accounts from the card, keeping its words, and
   `reconciliation_names` reads `GET /statements/{id}`.
   *Passes if:* unit tests pin a card's two accounts as one line and an account alone on its
   card as its own, and the bank import's stopping statement is named through the new read.
5. **The statement upload on the new route (builder).**
   [statement.py](../../expense/bank_import/statement.py),
   [statement_upload.py](../../expense/tui/screens/statement_upload.py) and flow.py's
   `statement_call` use `POST /statements/import` and read its answer's `balances`,
   `creates`, `statement_id` and `statement`; the flagged lines come from each balance's
   `review_lines`; `CARD_ACCOUNT_NOT_ON_PAPER` shows in the engine's words. The screens stay
   as built.
   *Passes if:* the 26 tests of test_tui_statement_upload.py pass on the new answer, a new one
   pins `CARD_ACCOUNT_NOT_ON_PAPER`, and the old upload builder is gone.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e06456a20aca6e4c` (`f91a1e0ae626c712`, `f0ee03d6faa96af1`,
  `29228c5191b6669b`, `c3caf28dd580253d`, `e767584fd1b13108`, `dc990e964df6b627`,
  `743f76692347e6a4`, `e06456a20aca6e4c`), shared with the six other parts.
- **The engine's "Done when" checks to report on:** this client's contract snapshot is at
  `e06456a20aca6e4c` (recorded in commit `ab67440`), and it reports having read up to it.
- **The asks it closes:** none.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
