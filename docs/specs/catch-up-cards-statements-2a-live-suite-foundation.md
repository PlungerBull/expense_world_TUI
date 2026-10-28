# The live tests' foundation: cards and statements

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full" (`f91a1e0ae626c712` to `e06456a20aca6e4c`).
The catch-up is seven specs, run in this order:

1. [catch-up-cards-statements-1a-reads-and-writes.md](catch-up-cards-statements-1a-reads-and-writes.md);
2. [catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md);
3. this one;
4. [catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md);
5. [catch-up-split-rows.md](catch-up-split-rows.md);
6. [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md);
7. [catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).

It runs after 1b, whose app helpers the live tests call.

**Status: draft, for the owner to rewrite or approve; no question waits on the owner. Its tasks
are drafted and wait on the owner's approval.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

The live tests ([tests/contract/](../../tests/contract/)) prove the engine's rules against a real
engine, so the terminal app, and the web and iPhone apps after it, build on rules that hold. Since
2026-10-27 most of them fail: every bank account now sits on a card, made first
(contract: "Cards"); a month's statement is one record for the whole card, with each account's
balances in it (contract: "Statements"); the old statement routes are gone; and the rule for
ordering a statement's lines by hand is gone, since the bank's PDF sets the order.

This spec lays the ground: the shared way every test makes its records, and the tests of a
statement's own life. The upload, the bank lines, people and the cleaner follow in
[2b](catch-up-cards-statements-2b-live-suite-upload-lines-people.md).

Nothing you see changes. Only the tests change.

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

## How the owner knows it is done

1. The files this spec touches pass live against the practice engine.
2. A test run of them leaves nothing on the practice user, cards included.

## Questions for the owner

None.

---

## Tasks

Drafted 2026-10-27; they wait on the owner's approval. Each needs the practice engine, which the
orchestrator starts before the task and stops after it. Each fixes the `(contract: …)`
citations of the files it touches.

1. **The shared helpers (builder).** In [conftest.py](../../tests/contract/conftest.py): a card
   and its accounts made through `Scratch`, a statement's body on `POST /statements` with each
   account's balances, `Scratch`'s cleanup deleting statements and then cards, `leaves_nothing`
   counting cards; `send_order` and `reconciliation_body` go.
   *Passes if:* a test making a card of two accounts and a statement on it leaves nothing, and
   one that leaves a card fails naming it.
2. **The first half of the tests onto the shared helpers (builder).** These files stop posting
   `/accounts` themselves and build their accounts through `Scratch`:
   [test_freshman_flow.py](../../tests/contract/test_freshman_flow.py),
   [test_pending_hashtag.py](../../tests/contract/test_pending_hashtag.py),
   [test_refusal_reasons.py](../../tests/contract/test_refusal_reasons.py),
   [test_category_hashtags.py](../../tests/contract/test_category_hashtags.py),
   [test_create_sent_again.py](../../tests/contract/test_create_sent_again.py),
   [test_log_lifecycle.py](../../tests/contract/test_log_lifecycle.py) and
   [test_reports_and_dashboard.py](../../tests/contract/test_reports_and_dashboard.py).
   *Passes if:* none of these files posts `/accounts` or `/cards`, and they pass live.
3. **The second half of the tests onto the shared helpers (builder).** The same for
   [test_opening_balance.py](../../tests/contract/test_opening_balance.py),
   [test_sheet_import.py](../../tests/contract/test_sheet_import.py) (its create step through
   `expense import sheet --create-names` waits on
   [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md)),
   [test_resources_lifecycle.py](../../tests/contract/test_resources_lifecycle.py),
   [test_system_names.py](../../tests/contract/test_system_names.py),
   [test_transactions_lifecycle.py](../../tests/contract/test_transactions_lifecycle.py),
   [test_transactions_cursor.py](../../tests/contract/test_transactions_cursor.py) and
   [test_account_kind.py](../../tests/contract/test_account_kind.py), whose `_transaction_ids`
   becomes conftest.py's `live_ids`. The files whose own tasks rework them (here and in 2b) move
   onto `Scratch` in those tasks.
   *Passes if:* none of these files posts `/accounts` or `/cards`, `_transaction_ids` is gone,
   and the files whose tests touch no statement pass live.
4. **A statement's life (builder).**
   [test_reconciliations_lifecycle.py](../../tests/contract/test_reconciliations_lifecycle.py)
   on `/statements`: made, renamed, completed, reverted and deleted as one record, each
   account's balances in it, refusals keyed by account, `NO_TRANSACTIONS_ASSIGNED` on every
   account, the card's list.
   *Passes if:* the file passes live and names no half or `/reconciliations`.
5. **A card's statement (builder).**
   [test_card_statement.py](../../tests/contract/test_card_statement.py) on `/statements`: one
   record per card, `CARD_ACCOUNTS_MISSING`, `DIFFERENCE_NOT_ZERO`, the quiet currency closed by
   hand, an archived card's statements frozen.
   *Passes if:* the file passes live and names no `twin`, half or `/reconciliations`.
6. **Codes on cards, and the order read only (builder).**
   [test_statement_codes.py](../../tests/contract/test_statement_codes.py) on `POST`/`PUT
   /cards`; [test_statement_order.py](../../tests/contract/test_statement_order.py) and
   [test_line_codes_and_statement_lines.py](../../tests/contract/test_line_codes_and_statement_lines.py)
   reading the order and the statement lines the upload sets, with no order written.
   *Passes if:* the three files pass live and none sends `PUT …/statement-order`.

## Reply to the engine

None of its own: its results are reported in the reply of
[2b](catch-up-cards-statements-2b-live-suite-upload-lines-people.md).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
