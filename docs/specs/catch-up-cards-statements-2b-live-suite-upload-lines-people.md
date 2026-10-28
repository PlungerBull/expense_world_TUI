# The live tests for the upload, bank lines and people

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full" (`f91a1e0ae626c712` to `e06456a20aca6e4c`).
The catch-up is seven specs, run in this order:

1. [catch-up-cards-statements-1a-reads-and-writes.md](catch-up-cards-statements-1a-reads-and-writes.md);
2. [catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md);
3. [catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md);
4. this one;
5. [catch-up-split-rows.md](catch-up-split-rows.md);
6. [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md);
7. [catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).

It runs after 2a, whose shared helpers its tests use.

**Status: draft, for the owner to rewrite or approve; no question waits on the owner. Its tasks
are drafted and wait on the owner's approval.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

The live tests ([tests/contract/](../../tests/contract/)) prove the engine's rules against a real
engine. Since 2026-10-27 most of them fail: every bank account now sits on a card
(contract: "Cards"), a month's statement is one record for the whole card
(contract: "Statements"), and the old statement routes are gone.
[2a](catch-up-cards-statements-2a-live-suite-foundation.md) moves the shared helpers and a
statement's own tests onto the new engine; this spec does the rest: the statement upload, the
bank lines, people and archiving, and the script that cleans the practice user.

The engine also publishes three made-up statement PDFs to test the upload with: a savings
account's, a card's, and the card's next month with no dollar line
(contract: GET /v1/statements/samples/{sample}), and states each paper's layout
(contract: POST /v1/statements/import, "The paper's layout"). The card's paper could not be
tested before: the tests could not draw one the engine reads.

Nothing you see changes. The tests change, and the script that cleans what a test run leaves on
the practice user.

## What it must do

1. **The statement upload is tested on the published samples**: a card's paper closing both
   its currencies in one statement, its undated fees dated the statement's last day; the card's
   next month closing its dollar account with no line; a card's paper for a card missing an
   account in one of its currencies refused; a savings paper for a card holding another account
   refused. The papers the tests draw themselves (for a duplicate, a line one day off, a line
   dated in the future, totals that don't add up) follow the layout the engine states, and one
   test proves a drawn paper reads exactly as the savings sample does.
2. **The bank-line tests read a statement's review list as the engine serves it**: in the
   paper's order only, before and after the close
   (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it"); a line
   moved to another account says it left its statement; and a transaction can no longer be
   created straight into a statement (contract: POST /v1/transactions, "No `statement_id`").
3. **Cards, people and archiving are tested**: a card's routes and their refusals; a person
   turned back into a bank account onto a card; a bank account turned into a person only when it
   is alone on its card and never in a statement, its card going with it
   (contract: POST /v1/accounts/{account_id}/make-person, "Its card is deleted with it");
   archiving through the card, both currencies at once
   (contract: POST /v1/cards/{card_id}/archive, "Every account at once").
4. **The practice-data cleaner works on cards and statements,** reads every page of a test's
   leftovers, and its doc says how to clean either practice user.
5. **Every `(contract: …)` citation in the tests, the scripts and [runtime.md](../runtime.md)
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
orchestrator starts before the task and stops after it. Each fixes the `(contract: …)`
citations of the files it touches, and moves them onto 2a's shared helpers.

1. **The upload on the new route (builder).**
   [test_statement_import.py](../../tests/contract/test_statement_import.py) and
   [test_reserved_name_held.py](../../tests/contract/test_reserved_name_held.py) on
   `POST /statements/import`, reading each account's balances and the statement's id and
   `creates`; `STATEMENT_MONTH_TAKEN` on a card of one account; `CARD_ACCOUNT_NOT_ON_PAPER`;
   the suite's drawn papers following the stated layout instead of a probed one.
   *Passes if:* both files pass live and the drawn papers cite the stated layout.
2. **The card tests from the published samples (builder).** In test_statement_import.py: the
   `card` and `card-no-dollars` samples closing one card one after the other, the undated fees
   dated the statement's last day, `NO_ACCOUNT_FOR_CURRENCY` for a card missing its other
   currency, and the suite's drawn copy of the savings sample's rows answering the sample's
   rows, days and balances.
   *Passes if:* those tests pass live, the card tests use only the published samples, and no
   real statement is in the repo.
3. **Bank lines and the review list (builder).**
   [test_bank_lines.py](../../tests/contract/test_bank_lines.py) reading the review list with
   `sort=statement` only, before and after a close, any other order refused.
   *Passes if:* the file passes live and names no `reconciliation_id`.
4. **Moves and the import door (builder).**
   [test_bank_line_write.py](../../tests/contract/test_bank_line_write.py),
   [test_bank_line_edit_limits.py](../../tests/contract/test_bank_line_edit_limits.py) and
   [test_sealed_periods.py](../../tests/contract/test_sealed_periods.py) on `statement_id` and
   `left_statement`; [test_bank_import.py](../../tests/contract/test_bank_import.py) naming the
   statement that stops a move through the app's own read;
   [test_create_into_reconciliation.py](../../tests/contract/test_create_into_reconciliation.py)
   replaced by one test that `statement_id` on `POST /transactions` and a batch item is
   `UNKNOWN_FIELD`.
   *Passes if:* those files pass live and none names `reconciliation_id`.
5. **Cards, people and archiving (builder).** The card routes and `CARD_CURRENCY_TAKEN`,
   `CARD_HAS_STATEMENT`, `CARD_HAS_ACCOUNTS` and an archived card refused a new account;
   [test_account_kind.py](../../tests/contract/test_account_kind.py) and
   [test_people_lifecycle.py](../../tests/contract/test_people_lifecycle.py) with `make-account`
   onto a card and `make-person`'s new refusals (`CARD_HAS_OTHER_ACCOUNTS`,
   `HAS_RECONCILIATION` for a deleted statement too, `CARD_HAS_STATEMENT`) and its card deleted;
   archiving through the card, and `ARCHIVE_THE_CARD` on a bank account's own route.
   *Passes if:* those tests pass live, each refusal writing nothing.
6. **The cleaner (builder).**
   [clean_practice_user.py](../../scripts/clean_practice_user.py) on `/statements` and cards
   (unarchive the card, revert and delete each statement, delete the transactions on every page,
   then the accounts and their cards), with
   [test_clean_practice_user.py](../../tests/contract/test_clean_practice_user.py);
   [runtime.md](../runtime.md) "Leftovers" saying a leftover on the reserved-names practice user
   is cleaned by passing that user's key as `EXPENSE_PAT`.
   *Passes if:* the cleaner removes a card statement's leftovers on the practice engine, and
   reads past a page holding only refused deletes.
7. **The last citations (builder).** Every citation left in tests/, scripts/ and runtime.md moved
   to the live contract, and runtime.md's paragraph on what the suite does saying what the suite
   now proves.
   *Passes if:* the citation test names no file of tests/, scripts/ or runtime.md.

## Reply to the engine

Written into [to-engine/](../to-engine/) when this spec is done, with the tester's results, and
those of [2a](catch-up-cards-statements-2a-live-suite-foundation.md).

- **Range:** `46e2fdf6e11d7548` → `e06456a20aca6e4c` (`f91a1e0ae626c712`, `f0ee03d6faa96af1`,
  `29228c5191b6669b`, `c3caf28dd580253d`, `e767584fd1b13108`, `dc990e964df6b627`,
  `743f76692347e6a4`, `e06456a20aca6e4c`), shared by the seven specs.
- **The engine's "Done when" checks this spec reports on:** the upload is tested against the
  published samples.
- **The asks it closes:** "Publish one made-up sample statement PDF per paper, so every client
  can test the statement upload".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
