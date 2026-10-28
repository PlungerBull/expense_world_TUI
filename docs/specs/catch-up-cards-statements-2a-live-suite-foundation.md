# The live tests' foundation: holders and statements

Catches up to contract `e7393dd869963db1`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full" (`f91a1e0ae626c712` to `e06456a20aca6e4c`),
and the rename of card to holder in its hand-off of 2026-10-28, "A person carries an opening
balance, and a card is now called a holder everywhere" (`2cec1b59048f50dc`,
`e7393dd869963db1`). The catch-up is seven specs, run in this order:

1. part 1a, the app's reads and writes, done on 2026-10-28;
2. [catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md);
3. this one;
4. [catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md);
5. [catch-up-split-rows.md](catch-up-split-rows.md);
6. [catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md);
7. [catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).

It runs after 1b, whose app helpers the live tests call.

**Status: approved by the owner on 2026-10-28; it runs after part 1b. Task 1, changed for the
engine's hand-off "An account moves between holders, a holder is made and unmade with its
accounts, and a holder's bank lines list in one read", was approved again on 2026-10-28.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

**Built on the holder names.** The engine's rename of card to holder is in the live contract
since `e7393dd869963db1` (the hand-off of 2026-10-28, "A person carries an opening balance, and a
card is now called a holder everywhere"): the routes are `/holders`, the field is `holder_id`
everywhere, and every reason and message says holder, with nothing behaving differently; "card"
is left only for the bank's product, a credit card. The tests make a holder, then its accounts,
and set codes on the holder. People become holders in a later engine change, not yet in the
contract (the engine coders' answer of 2026-10-27, "Which of the terminal app's seven card and
statement specs the engine's coming changes touch"); once they do, a statement code on a
person's holder is refused.

---

## Why

The live tests ([tests/contract/](../../tests/contract/)) prove the engine's rules against a real
engine, so the terminal app, and the web and iPhone apps after it, build on rules that hold. Since
2026-10-27 most of them fail: every bank account now sits on a holder, made first
(contract: "Holders"); a month's statement is one record for the whole holder, with each account's
balances in it (contract: "Statements"); the old statement routes are gone; and the rule for
ordering a statement's lines by hand is gone, since the bank's PDF sets the order.

This spec lays the ground: the shared way every test makes its records, and the tests of a
statement's own life. The upload, the bank lines, people and the cleaner follow in
[2b](catch-up-cards-statements-2b-live-suite-upload-lines-people.md).

Nothing you see changes. Only the tests change.

## What it must do

1. **Every test builds its records the shared way.** A bank account is made with its holder
   first, and everything a test makes, holders and statements included, is cleaned up after it.
   A test fails when it leaves a holder behind, as it already does for an account, a category or
   a hashtag.
2. **The statement tests run on the new routes**: a holder's statement made, renamed, completed,
   reverted and deleted as one record, each account's balances in it, each refusal the engine
   names for it (contract: POST /v1/statements); a currency with no movement in the month
   closing by hand when its starting and ending balances are equal
   (contract: POST /v1/statements/{statement_id}/complete, "The statement holds a transaction on at least one account").
3. **A holder's statement code is tested on the holder** (contract: "Holders", "Statement code"),
   and a statement's order is only read, never written: the paper sets it.

## How the owner knows it is done

1. The files this spec touches pass live against the practice engine.
2. A test run of them leaves nothing on the practice user, holders included.

## Questions for the owner

None.

---

## Tasks

Drafted 2026-10-27; approved by the owner on 2026-10-28. Each needs the practice engine, which the
orchestrator starts before the task and stops after it. Each fixes the `(contract: …)`
citations of the files it touches.

1. **The shared helpers (builder).** In [conftest.py](../../tests/contract/conftest.py): a
   holder and its accounts made through `Scratch` in one write (`POST /holders` with `accounts`;
   contract: POST /v1/holders), a statement's body on `POST /statements` with `holder_id` and each
   account's balances, `Scratch`'s cleanup reverting and deleting statements before accounts, an
   account that a live statement holds being refused (`IN_LIVE_STATEMENT`), then deleting the
   accounts, each holder going with its last account (contract: DELETE /v1/accounts/{account_id}),
   and deleting only the holders it made with no account; `leaves_nothing` counting holders;
   `send_order` and `reconciliation_body` go.
   *Passes if:* a test making a holder of two accounts and a statement on it leaves nothing, one
   that leaves a holder fails naming it, and conftest.py names no `/cards` or `card_id`.
2. **The first half of the tests onto the shared helpers (builder).** These files stop posting
   `/accounts` themselves and build their accounts through `Scratch`:
   [test_freshman_flow.py](../../tests/contract/test_freshman_flow.py),
   [test_pending_hashtag.py](../../tests/contract/test_pending_hashtag.py),
   [test_refusal_reasons.py](../../tests/contract/test_refusal_reasons.py),
   [test_category_hashtags.py](../../tests/contract/test_category_hashtags.py),
   [test_create_sent_again.py](../../tests/contract/test_create_sent_again.py),
   [test_log_lifecycle.py](../../tests/contract/test_log_lifecycle.py) and
   [test_reports_and_dashboard.py](../../tests/contract/test_reports_and_dashboard.py).
   *Passes if:* none of these files posts `/accounts` or `/holders`, and they pass live.
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
   *Passes if:* none of these files posts `/accounts` or `/holders`, `_transaction_ids` is gone,
   and the files whose tests touch no statement pass live.
4. **A statement's life (builder).**
   [test_reconciliations_lifecycle.py](../../tests/contract/test_reconciliations_lifecycle.py)
   on `/statements`: made, renamed, completed, reverted and deleted as one record, each
   account's balances in it, refusals keyed by account, `NO_TRANSACTIONS_ASSIGNED` once per
   account (keyed `balances.<account id>.transactions`, each reading "At least one transaction
   must be assigned.", under the top-level message "Cannot complete a statement with no
   transaction on any of its accounts."), the holder's list (`GET /statements?holder_id=`).
   *Passes if:* the file passes live and names no half, `/reconciliations` or `card_id`.
5. **A holder's statement (builder).**
   [test_card_statement.py](../../tests/contract/test_card_statement.py) on `/statements`: one
   record per holder, `HOLDER_ACCOUNTS_MISSING`, `DIFFERENCE_NOT_ZERO`, the quiet currency
   closed by hand, an archived holder's statements frozen.
   *Passes if:* the file passes live and names no `twin`, half, `/reconciliations` or
   `CARD_ACCOUNTS_MISSING`.
6. **Codes on holders, and the order read only (builder).**
   [test_statement_codes.py](../../tests/contract/test_statement_codes.py) on `POST`/`PUT
   /holders`; [test_statement_order.py](../../tests/contract/test_statement_order.py) and
   [test_line_codes_and_statement_lines.py](../../tests/contract/test_line_codes_and_statement_lines.py)
   reading the order and the statement lines the upload sets, with no order written.
   *Passes if:* the three files pass live and none sends `PUT …/statement-order`.

## Reply to the engine

None of its own: its results are reported in the reply of
[2b](catch-up-cards-statements-2b-live-suite-upload-lines-people.md).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
