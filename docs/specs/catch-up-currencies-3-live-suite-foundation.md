# The live tests' foundation: accounts with their currencies, and statements

Catches up to contract `f82426fb0a099676`, from `e020782e3579d011`: the engine's hand-off of
2026-10-29, "An account holds its currencies: every route names an account and a currency code;
holders are gone" — the part on the live suite's shared helpers, the practice-data cleaner and a
statement's own tests. The catch-up is seven specs, run in this order:

1. part 1, the app's reads and writes (done on 2026-10-30);
2. part 2, the PDF upload and the two imports (done on 2026-10-30);
3. this one;
4. [catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md);
5. [catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md);
6. [catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md);
7. [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).

**Status: draft, written 2026-10-29 for the owner to approve. It runs after spec 2,** whose app
code the live tests call: the upload's and the bank download's request bodies and the
whole-line write ([conftest.py](../../tests/contract/conftest.py) builds its bodies with them).
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

The live tests ([tests/contract/](../../tests/contract/)) prove the engine's rules against a real
engine, so the terminal app, and the web and iPhone apps after it, build on rules that hold.
Today nearly all of them fail: they make an account per currency, file statements on the old
statement routes, pair a card's two halves, and make people on a route that is gone. On the
engine now an account is one record holding its currencies (contract: "What an account is",
"Its currencies"), every transaction names its account and a currency code
(contract: POST /v1/transactions, "`account_id` and `currency_code`"), and a month's statement
is the account's, with a starting and ending balance for each currency it covers
(contract: "Statements", "Which currencies a statement covers").

This spec lays the ground: the shared way every test makes its records and cleans them up, the
script that cleans what a failed run leaves on the practice user, the tests that only need
their accounts made the new way, and the tests of a statement's own life. The upload, bank
lines, imports, kinds and codes follow in
[spec 4](catch-up-currencies-4-live-suite-upload-lines-kinds.md); the new rules on an account's
currencies in [spec 5](catch-up-currencies-5-live-suite-account-currencies.md).

Nothing you see changes. Only the tests and the cleaning script change.

## What it must do

1. **Every test builds its records the shared way.** An account is made with its currencies in
   one write, a bank account or a person (contract: POST /v1/accounts); a transaction names
   its account and currency; a statement names its account and a balance per currency it
   covers (contract: POST /v1/statements). Everything a test makes, statements and opening
   balances included, is cleaned up after it, and a test that leaves an account, a category or
   a hashtag behind fails naming it.
2. **The cleaning script works on the account model:** it finds a test's leftover accounts,
   their statements and their transactions on every page, and removes them in the order the
   engine's deletes need, the account with all its currencies in one delete
   (contract: DELETE /v1/accounts/{account_id}).
3. **The tests that only make accounts run again**, the month reports and the dashboard reading
   one row per account with a balance per currency and no home-currency balance
   (contract: GET /v1/dashboard, "Balances are native only").
4. **An account's opening balance is tested per currency**: one per currency, the currency
   named, one the account does not hold refused
   (contract: POST /v1/accounts/{account_id}/opening-balance, "Validation").
5. **A statement's life is tested on the account**: made, renamed, completed, reverted and
   deleted as one record (contract: "Statements", "Every write acts on the whole statement"),
   listed by account, each refusal the engine names for it, a currency with nothing this month
   left out, a currency with money at the start required, a blank beginning balance refused at
   the close, and a currency with no movement closing when its two balances are equal
   (contract: POST /v1/statements/{statement_id}/complete, "The statement holds a transaction in at least one currency").

## How the owner knows it is done

1. The files this spec touches pass live against the practice engine.
2. A run of them leaves nothing on the practice user.
3. None of them, nor the cleaning script, names `/reconciliations`, `twin`, `holder_id`,
   `/holders` or `/people`.

## What the owner settled

None: this spec changes only tests and a test tool.

## Questions for the owner

None.

---

## Tasks

Drafted 2026-10-29. Each needs the practice engine, which the orchestrator starts before the
task and stops after it. Each fixes the `(contract: …)` citations of the files it touches.
Files left to spec 4 may fail live until it runs.

1. **The shared helpers (builder).** In [conftest.py](../../tests/contract/conftest.py):
   `account_body` sends `currencies` (contract: POST /v1/accounts, "Required");
   `Scratch.account(*codes, code=…, person=…)` makes a bank account or a person in one write,
   PEN when no code is given, and `Scratch.person` goes; `_item`, `line` and `opening_balance`
   carry `currency_code`; a statement's create body names `account_id` and one balance entry
   per currency asked (contract: POST /v1/statements, "`balances`"), made through
   `Scratch.statement`; the upload helpers post `/statements/import`, and `took` takes on the
   answer's `statement_id`; cleanup unarchives, reverts and deletes each statement, deletes the
   transactions, opening balances included, then the hashtags and categories, then each
   account in one `DELETE /accounts/{id}`; `send_order`, `reconciliation_body`, `card`,
   `lines_into` and every half go; `free_statement_codes` cites the rule it reads
   (contract: "What an account is", "One account per code"). `leaves_nothing` keeps counting
   accounts by id (`CLEANER.holdings`).
   *Passes if:* a test making an account of two currencies with an opening balance and a
   statement in each leaves nothing, one making a person of two currencies leaves nothing, one
   that leaves an account fails naming it, and conftest.py names no `/holders`, `holder_id`,
   `/reconciliations`, `reconciliation_id`, `twin` or `/people`.
2. **The cleaner (builder).** [clean_practice_user.py](../../scripts/clean_practice_user.py)
   reads each matched account's statements with `GET /statements?account_id=`
   (contract: GET /v1/statements, "`?account_id=<id>` is required"), with no twin or half,
   reverts the completed ones and deletes each, deletes the transactions on every page, then
   deletes each account whole; spec 1 gives its printout the account's currencies and code,
   this task its statements. [test_clean_practice_user.py](../../tests/contract/test_clean_practice_user.py)
   leaves an account of two currencies with a completed statement and transactions in both,
   and the script removes them; [runtime.md](../runtime.md) "Working against the live engine"
   says the script's order on the account model and that a leftover on the reserved-names
   practice user is cleaned by passing that user's key as `EXPENSE_PAT`.
   *Passes if:* the test passes live, the script reads past a page holding only refused
   deletes, and neither names `/reconciliations` or `twin`.
3. **Six small files onto the shared helpers (builder).**
   [test_freshman_flow.py](../../tests/contract/test_freshman_flow.py),
   [test_pending_hashtag.py](../../tests/contract/test_pending_hashtag.py),
   [test_refusal_reasons.py](../../tests/contract/test_refusal_reasons.py) (its completed
   statement holding its rows and itself, on `/statements`),
   [test_category_hashtags.py](../../tests/contract/test_category_hashtags.py),
   [test_create_sent_again.py](../../tests/contract/test_create_sent_again.py) and
   [test_log_lifecycle.py](../../tests/contract/test_log_lifecycle.py): accounts through
   `Scratch` or `account_body`, every transaction with its `currency_code`.
   *Passes if:* none of these files posts an account body of its own, and they pass live.
4. **Reports and the dashboard (builder).**
   [test_reports_and_dashboard.py](../../tests/contract/test_reports_and_dashboard.py):
   `bank_accounts`, `people` and the archived sections one row per account,
   `{id, name, currencies}`, each currency `{currency_code, current_balance_cents}`, live
   currencies only, in the accounts' order (contract: GET /v1/dashboard, "`bank_accounts`");
   no `current_balance_home_cents` anywhere on an account row; the month's categories and
   totals still in the home currency with `unconverted_count`
   (contract: GET /v1/dashboard, "Aggregates are home-currency only").
   *Passes if:* the file passes live and names no `current_balance_home_cents` but to prove it
   absent.
5. **Opening balance, resources, system names, transactions and the cursor (builder).**
   [test_opening_balance.py](../../tests/contract/test_opening_balance.py) per currency:
   `currency_code` required (`REQUIRED`), `UNSUPPORTED_VALUE`, `CURRENCY_NOT_HELD` on
   `currency_code`, a second in one currency `OPENING_BALANCE_EXISTS` while the other currency
   takes its own, each named by its own entry's `opening_balance_transaction_id`
   (contract: "Bank Accounts", "Opening balance"), its person test on a person account;
   [test_resources_lifecycle.py](../../tests/contract/test_resources_lifecycle.py),
   [test_system_names.py](../../tests/contract/test_system_names.py),
   [test_transactions_lifecycle.py](../../tests/contract/test_transactions_lifecycle.py) and
   [test_transactions_cursor.py](../../tests/contract/test_transactions_cursor.py) on the
   account's shape and with `currency_code` on every create and batch item, each answer
   echoing it.
   *Passes if:* none of these files posts an account body of its own or `/people`, and they
   pass live.
6. **A statement's life (builder).**
   [test_reconciliations_lifecycle.py](../../tests/contract/test_reconciliations_lifecycle.py),
   renamed for statements, on `/statements`: made, renamed, completed, reverted and deleted as
   one record, its balances keyed by `currency_code`; `NO_TRANSACTIONS_ASSIGNED` on
   `balances.<code>.transactions` for every currency of the statement, each reading "At least
   one transaction must be assigned."; the account's list, `?account_id=` required
   (`REQUIRED`, `INVALID_FORMAT`, an unknown id `[]`); the period's refusals; complete locking
   a transaction and revert unlocking it; delete keeping its transactions; an archived
   account's statements frozen until unarchived.
   *Passes if:* the file passes live and names no `/reconciliations`, `reconciliation_id`,
   half or `twin`.
7. **A statement's currencies, part 1 (builder).**
   [test_card_statement.py](../../tests/contract/test_card_statement.py), renamed for an
   account's statement, every half and twin test gone (`HOLDER_ACCOUNTS_MISSING` and
   `?statement_of=` with them): one statement per account holding PEN and USD; a currency with
   nothing this month left out of `POST /statements`, and listed in `not_covered` at the close
   (contract: POST /v1/statements/{statement_id}/complete, "`not_covered`"); `DIFFERENCE_NOT_ZERO`
   keyed `balances.<code>.difference_cents`; the quiet currency closing with no line when its
   two balances are equal; a `PUT` naming one currency keeping the other; an archived account's
   statements frozen (contract: "Bank Accounts", "Its statements are frozen").
   *Passes if:* those tests pass live and the file names no `twin`, half, `/reconciliations`
   or `HOLDER_ACCOUNTS_MISSING`.
8. **A statement's currencies, part 2 (builder).** In the same file:
   `MONEY_AT_START_NOT_COVERED` on `balances.<code>` from `POST /statements` and from the
   complete, cleared by adding that currency with `PUT /statements/{id}`
   (contract: POST /v1/statements/{statement_id}/complete, "Every currency with money at the start has balances in it");
   a line placed in a draft lacking its currency giving the draft that currency's balances,
   both `null`, `difference_cents` `null`
   (contract: "Statements", "A line in a currency the statement holds no balances for gives it that currency's balances");
   the complete then refused with `BEGINNING_BALANCE_REQUIRED` and `ENDING_BALANCE_REQUIRED` in
   one answer (contract: POST /v1/statements/{statement_id}/complete, "Every balance must be entered"),
   and completing once both are filled; a completed statement gaining no currency (`LOCKED` on
   `balances.<code>`); `not_covered` naming a currency the statement holds no balances for, `[]`
   when it covers them all.
   *Passes if:* those tests pass live, each refusal writing nothing.

## Reply to the engine

None of its own: its results are reported in the reply of
[spec 4](catch-up-currencies-4-live-suite-upload-lines-kinds.md).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
