# The live tests run on cards, statements and the published sample PDFs

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full" (`f91a1e0ae626c712` to `e06456a20aca6e4c`).
The second of five specs for it, after
[catch-up-cards-statements-1-routes.md](catch-up-cards-statements-1-routes.md), whose app helpers
the live tests call; then [catch-up-split-rows.md](catch-up-split-rows.md),
[catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md) and
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).

**Status: draft, for the owner to rewrite or approve; no question waits on the owner. Its tasks
wait on the owner's approval.** When done, the why moves to [decisions.md](../decisions.md) and
this file is deleted.

---

## Why

The live tests ([tests/contract/](../../tests/contract/)) prove the engine's rules against a real
engine, so the terminal app, and the web and iPhone apps after it, build on rules that hold. Since
2026-10-27 most of them fail: every bank account now sits on a card, made first
(contract: "Cards"); a month's statement is one
record for the whole card, with each account's balances in it (contract: "Statements"); the old
statement routes are gone; and the rule for ordering a statement's lines by hand is gone, since
the bank's PDF sets the order.

The engine also publishes three made-up statement PDFs to test the upload with: a savings
account's, a card's, and the card's next month with no dollar line
(contract: GET /v1/statements/samples/{sample}), and states each paper's layout
(contract: POST /v1/statements/import, "The paper's layout"). The card's paper could not be
tested before: the tests could not draw one the engine reads.

Nothing you see changes. The tests change, and the script that cleans what a test run leaves on
the practice user.

## What it must do

1. **Every test builds its records the shared way.** A bank account is made with its card first,
   and everything a test makes, cards and statements included, is cleaned up after it. A test
   fails when it leaves a card behind, as it already does for an account, a category or a
   hashtag.
2. **The statement tests run on the new routes**: a card's statement made, renamed, completed,
   reverted and deleted as one record, each account's balances in it, each refusal the engine
   names for it (contract: POST /v1/statements); a currency with no movement in the month
   closing by hand when its starting and ending balances are equal
   (contract: POST /v1/statements/{statement_id}/complete, "The statement holds a transaction on at least one account").
3. **A card's statement code is tested on the card** (contract: "Cards", "Statement code"),
   and a statement's order is only read, never written: the paper sets it.
4. **The statement upload is tested on the published samples**: a card's paper closing both
   its currencies in one statement, its undated fees dated the statement's last day; the card's
   next month closing its dollar account with no line; a card's paper for a card missing an
   account in one of its currencies refused; a savings paper for a card holding another account
   refused. The papers the tests draw themselves (for a duplicate, a line one day off, a line
   dated in the future, totals that don't add up) follow the layout the engine states, and one
   test proves a drawn paper reads exactly as the savings sample does.
5. **The bank-line tests read a statement's review list as the engine serves it**: in the
   paper's order only, before and after the close
   (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it"); a line
   moved to another account says it left its statement; and a transaction can no longer be
   created straight into a statement (contract: POST /v1/transactions, "No `statement_id`").
6. **Cards, people and archiving are tested**: a card's routes and their refusals; a person
   turned back into a bank account onto a card; a bank account turned into a person only when it
   is alone on its card and never in a statement, its card going with it
   (contract: POST /v1/accounts/{account_id}/make-person, "Its card is deleted with it");
   archiving through the card, both currencies at once
   (contract: POST /v1/cards/{card_id}/archive, "Every account at once").
7. **The practice-data cleaner works on cards and statements,** reads every page of a test's
   leftovers, and its doc says how to clean either practice user.
8. **Every `(contract: …)` citation in the tests, the scripts and [runtime.md](../runtime.md)
   names a part the live contract holds.**

## How the owner knows it is done

1. The live suite passes against the practice engine, with the sheet import's create step left
   to [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md), which gives
   the import's new accounts their cards.
2. The upload's live tests run on the three published samples, and no real statement is in the
   repo.
3. A test run leaves nothing on either practice user, cards included.
4. The citation test passes on the tests, the scripts and runtime.md.

## Questions for the owner

None.

---

## Tasks

Drafted 2026-10-27; they wait on the owner's approval. Each needs the practice engine, which the
orchestrator starts before the task and stops after it.

1. **The shared helpers (builder).** In [conftest.py](../../tests/contract/conftest.py): a card
   and its accounts made through `Scratch`, a statement's body on `POST /statements` with each
   account's balances, `Scratch`'s cleanup deleting statements and then cards, `leaves_nothing`
   counting cards; `send_order` and `reconciliation_body` go.
   *Passes if:* a test making a card of two accounts and a statement on it leaves nothing, and
   one that leaves a card fails naming it.
2. **Every test through the shared helpers (builder).** The test files that post `/accounts`
   themselves build their accounts through `Scratch`; `_transaction_ids` in
   [test_account_kind.py](../../tests/contract/test_account_kind.py) is `live_ids`.
   *Passes if:* no contract test posts `/accounts` or `/cards` outside conftest.py, and the files
   whose tests touch no statement pass live.
3. **A statement's life (builder).**
   [test_reconciliations_lifecycle.py](../../tests/contract/test_reconciliations_lifecycle.py)
   and [test_card_statement.py](../../tests/contract/test_card_statement.py) on `/statements`:
   one record per card, refusals keyed by account, `CARD_ACCOUNTS_MISSING`,
   `DIFFERENCE_NOT_ZERO`, the quiet currency closed by hand, `NO_TRANSACTIONS_ASSIGNED` on every
   account, the card's list, an archived card's statements frozen.
   *Passes if:* both files pass live and name no `twin`, half or `/reconciliations`.
4. **Codes on cards, and the order read only (builder).**
   [test_statement_codes.py](../../tests/contract/test_statement_codes.py) on `POST`/`PUT
   /cards`; [test_statement_order.py](../../tests/contract/test_statement_order.py) and
   [test_line_codes_and_statement_lines.py](../../tests/contract/test_line_codes_and_statement_lines.py)
   reading the order and the statement lines the upload sets, with no order written.
   *Passes if:* the three files pass live and none sends `PUT …/statement-order`.
5. **The upload on the samples (builder).**
   [test_statement_import.py](../../tests/contract/test_statement_import.py) and
   [test_reserved_name_held.py](../../tests/contract/test_reserved_name_held.py) on
   `POST /statements/import`, reading each account's balances and the statement's id and
   `creates`; `STATEMENT_MONTH_TAKEN` on a card of one account; `CARD_ACCOUNT_NOT_ON_PAPER`; the
   `card` and `card-no-dollars` samples closing one card one after the other, the undated fees,
   `NO_ACCOUNT_FOR_CURRENCY`; the suite's drawn papers following the stated layout, and its
   drawn copy of the savings sample's rows answering the sample's rows, days and balances.
   *Passes if:* both files pass live, the card tests use only the published samples, and the
   drawn papers cite the stated layout instead of a probed one.
6. **Bank lines, moves and the import door (builder).**
   [test_bank_lines.py](../../tests/contract/test_bank_lines.py) reading the review list with
   `sort=statement` only, before and after a close, any other order refused;
   [test_bank_line_write.py](../../tests/contract/test_bank_line_write.py),
   [test_bank_line_edit_limits.py](../../tests/contract/test_bank_line_edit_limits.py) and
   [test_sealed_periods.py](../../tests/contract/test_sealed_periods.py) on `statement_id` and
   `left_statement`; [test_bank_import.py](../../tests/contract/test_bank_import.py) naming the
   statement that stops a move through the app's own read;
   [test_create_into_reconciliation.py](../../tests/contract/test_create_into_reconciliation.py)
   replaced by one test that `statement_id` on `POST /transactions` and a batch item is
   `UNKNOWN_FIELD`.
   *Passes if:* those files pass live and none names `reconciliation_id`.
7. **Cards, people and archiving (builder).** The card routes and `CARD_CURRENCY_TAKEN`,
   `CARD_HAS_STATEMENT`, `CARD_HAS_ACCOUNTS` and an archived card refused a new account;
   [test_account_kind.py](../../tests/contract/test_account_kind.py) and
   [test_people_lifecycle.py](../../tests/contract/test_people_lifecycle.py) with `make-account`
   onto a card and `make-person`'s new refusals (`CARD_HAS_OTHER_ACCOUNTS`,
   `HAS_RECONCILIATION` for a deleted statement too, `CARD_HAS_STATEMENT`) and its card deleted;
   archiving through the card, and `ARCHIVE_THE_CARD` on a bank account's own route.
   *Passes if:* those tests pass live, each refusal writing nothing.
8. **The cleaner and the last citations (builder).**
   [clean_practice_user.py](../../scripts/clean_practice_user.py) on `/statements` and cards
   (unarchive the card, revert and delete each statement, delete the transactions on every page,
   then the accounts and their cards), with
   [test_clean_practice_user.py](../../tests/contract/test_clean_practice_user.py);
   [runtime.md](../runtime.md) "Leftovers" saying a leftover on the reserved-names practice user
   is cleaned by passing that user's key as `EXPENSE_PAT`, and its paragraph on what the suite
   does saying what the suite now proves; every citation left in tests, scripts and runtime.md
   moved to the live contract.
   *Passes if:* the cleaner removes a card statement's leftovers on the practice engine, and the
   citation test names no file of tests/, scripts/ or runtime.md.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the five specs of this catch-up are done, with the
tester's results, as one reply.

- **Range:** `46e2fdf6e11d7548` → `e06456a20aca6e4c` (`f91a1e0ae626c712`, `f0ee03d6faa96af1`,
  `29228c5191b6669b`, `c3caf28dd580253d`, `e767584fd1b13108`, `dc990e964df6b627`,
  `743f76692347e6a4`, `e06456a20aca6e4c`), shared by the five specs.
- **The engine's "Done when" checks this spec reports on:** the upload is tested against the
  published samples.
- **The asks it closes:** "Publish one made-up sample statement PDF per paper, so every client
  can test the statement upload".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
