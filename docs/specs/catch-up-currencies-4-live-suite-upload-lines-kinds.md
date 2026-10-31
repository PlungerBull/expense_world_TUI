# The live tests for the upload, bank lines, the imports, kinds and codes

Catches up to contract `f82426fb0a099676`, from `e020782e3579d011`: the engine's hand-off of
2026-10-29, "An account holds its currencies: every route names an account and a currency code;
holders are gone" — the part on the statement upload, bank lines, the bank download and the
sheet, an account's kind and archiving, and statement codes, in the live suite. The catch-up is
seven specs, run in this order:

1. part 1, the app's reads and writes (done on 2026-10-30);
2. part 2, the PDF upload and the two imports (done on 2026-10-30);
3. part 3, the live tests' foundation (done on 2026-10-30);
4. this one;
5. [catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md);
6. [catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md);
7. [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).

**Status: approved by the owner on 2026-10-30; the current spec. It runs after part 3 (done on
2026-10-30),** whose shared helpers its tests use; its import, bank-line and Edit form tests call the app code specs
1 and 2 change. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

The live tests ([tests/contract/](../../tests/contract/)) prove the engine's rules against a real
engine. Part 3 of the currencies catch-up (done on 2026-10-30) moved the shared helpers and a
statement's own tests onto accounts that hold their currencies; this spec does the rest of the
suite that still builds on the old model: the statement PDF upload, bank lines and their moves,
the bank download and the sheet, turning an account into a person and back, archiving, and
statement codes.

The engine publishes three made-up statement PDFs to test the upload with: a savings account's,
a card's, and the card's next month with no dollar line
(contract: GET /v1/statements/samples/{sample}, "Testing the upload with it"), and states each
paper's layout, so the tests can draw papers of their own
(contract: POST /v1/statements/import, "The paper's layout").

Nothing you see changes. Only the tests change.

## What it must do

1. **The statement upload is tested on the account**: each currency the paper prints going to
   that currency of the account; a currency the paper shows at zero with no row left out, and
   refused when the account holds money in it at the start; a currency the account holds that
   the paper does not print refused when something is in it; a paper in a currency the account
   lacks refused (contract: POST /v1/statements/import, "Which currencies the statement covers");
   a line one day off moved to the paper's day, two days off not
   (contract: POST /v1/statements/import, "The bank's day wins"); a person refused both uploads.
2. **The published samples close a card**: `card`, then `card-no-dollars`, on one account of
   soles and dollars, the second closing its dollars with no line
   (contract: POST /v1/statements/import, "A card's currency with no row still closes").
3. **Bank lines are tested per currency**: listed and counted by account across its currencies,
   narrowed by `?currency_code=`, a statement's review list looking at every currency of its
   account (contract: GET /v1/bank-lines, "The rule, on every currency of the statement's account");
   a line moved to another currency or account, and the closed days, refusing on each key sent
   (contract: PUT /v1/bank-lines/{bank_line_id}, "`account_id` and `currency_code` move the line").
4. **The bank download and the sheet send each row to its own currency of the account**
   (contract: POST /v1/transactions/import, "Accounts") (contract: POST /v1/transactions/import-sheet, "Names").
5. **An account's kind and its archiving act on the whole account,** every currency at once,
   its opening balances kept (contract: POST /v1/accounts/{account_id}/make-person, "The account is the thing converted")
   (contract: POST /v1/accounts/{account_id}/archive, "Every currency at once").
6. **Statement codes are tested on the account**, one account per code and one statement per
   account per month (contract: "The days", "One statement per account per month"); a
   statement's order and statement lines are only read, as the paper sets them
   (contract: "Statements", "The bank's paper sets the order").

## How the owner knows it is done

1. The live suite passes against the practice engine, but for what
   [spec 5](catch-up-currencies-5-live-suite-account-currencies.md) adds.
2. The upload's tests run on the three published samples and papers the tests draw, and no real
   statement is in the repo.
3. A run leaves nothing on either practice user.

## What the owner settled

None: this spec changes only tests.

## Questions for the owner

None.

---

## Tasks

Drafted 2026-10-29. Each needs the practice engine, which the orchestrator starts before the
task and stops after it. Each builds its records through spec 3's `Scratch` and fixes the
`(contract: …)` citations of the files it touches. Three of its files skip whole until it
rewrites them, since spec 3 removed the helpers they import (`test_statement_codes.py`,
`test_statement_order.py`, `test_line_codes_and_statement_lines.py`; `grep -rn "on the holder
model until" tests/contract` finds each): the task rewriting one removes its skip and its
`# ruff: noqa: E402` line.

5. **Moves and the closed days (builder).**
   [test_bank_line_write.py](../../tests/contract/test_bank_line_write.py),
   [test_bank_line_edit_limits.py](../../tests/contract/test_bank_line_edit_limits.py) and
   [test_sealed_periods.py](../../tests/contract/test_sealed_periods.py) on `statement_id` and
   `left_statement`: a line moved by `currency_code` alone, by `account_id` alone and by both
   (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction"); `account_id` alone
   onto an account lacking the line's currency `CURRENCY_NOT_HELD` on `account_id`; a move onto
   a closed day `SEALED_PERIOD` on both keys sent; `edit_limits` naming `currency_code` exactly
   when it names `account_id` (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields");
   [test_create_into_reconciliation.py](../../tests/contract/test_create_into_reconciliation.py)
   replaced by one test that `statement_id` on `POST /transactions` and on a batch item is
   `UNKNOWN_FIELD` (contract: POST /v1/transactions, "No `statement_id`").
   *Passes if:* those files pass live and none names `reconciliation_id`.
6. **The bank download and the sheet (builder).**
   [test_bank_import.py](../../tests/contract/test_bank_import.py): a card's download to one
   account, each row to the currency in its own `Moneda`; a soles download to a soles and
   dollar account leaving dollars untouched; a dollar row to a soles-only account
   `CURRENCY_NOT_HELD` on `rows.<row>.account_id`, nothing written; every answer row and
   `day_mismatches` entry reading `account_id` and `currency_code`; the statement that stops a
   move named through the app's own read.
   [test_sheet_import.py](../../tests/contract/test_sheet_import.py): `names.accounts` one entry
   per account name, mapped to an account; `--create-names` making one account per name holding
   the currencies its rows use; an account lacking one `CURRENCY_NOT_HELD` on
   `names.accounts.<i>.account_id`; a renamed account found under its rename.
   *Passes if:* both files pass live through the app's own modules, and neither sends
   `currency_code` in `names.accounts`.
7. **Kinds and archiving on the account (builder).**
   [test_account_kind.py](../../tests/contract/test_account_kind.py) and
   [test_people_lifecycle.py](../../tests/contract/test_people_lifecycle.py) on
   `/accounts/{id}/…`: a person made with `POST /accounts` and `is_person: true`, two
   currencies in one write; `make-person` and `make-account` turning the whole account, its id,
   currencies, balances and opening balances kept (each currency's
   `opening_balance_transaction_id` the same before and after); their refusals in the engine's
   order: `404`, then on `account_id` `ACCOUNT_ARCHIVED`, `KIND_UNCHANGED` and
   `HAS_RECONCILIATION`, a deleted statement counting
   (contract: POST /v1/accounts/{account_id}/make-person, "Refusals"); `PUT /accounts/{id}`
   refusing `is_person` as `UNKNOWN_FIELD`; archive and unarchive acting on every currency at
   once, and a transaction in any currency of an archived account `INVALID_REFERENCE` on
   `account_id` (contract: "Bank Accounts", "No new rows on it"); a person refused
   `POST /statements` as `PERSON_TAKES_NO_STATEMENT` on `account_id`
   (contract: "What an account is", "A person takes no statement"). `HAS_OPENING_BALANCE` goes
   from the cases, the order and the docstrings; `_transaction_ids` becomes conftest.py's
   `live_ids`; [runtime.md](../runtime.md)'s clauses on people follow.
   *Passes if:* both files pass live, each refusal writing nothing, in the engine's order, with
   no `HAS_OPENING_BALANCE`, and no test sends `/people`.
8. **Codes, and the order read only (builder).**
   [test_statement_codes.py](../../tests/contract/test_statement_codes.py) on `POST` and
   `PUT /accounts`: set, changed and cleared; `INVALID_FORMAT`; `STATEMENT_CODE_EXISTS` for any
   second live account (contract: "What an account is", "One account per code"); a person
   carrying a code like any account (contract: "What an account is", "A person carries a code like any account");
   `STATEMENT_MONTH_TAKEN` from `POST` and `PUT /statements` on one account, a deleted statement
   not counting. `test_a_code_is_shared_only_across_currencies`,
   `test_a_cards_two_accounts_name_each_other_and_no_other_account_names_one`,
   `test_an_archived_card_account_leaves_both_with_no_partner` and
   `test_one_statement_per_code_per_month_on_the_accounts_code` go.
   [test_statement_order.py](../../tests/contract/test_statement_order.py) and
   [test_line_codes_and_statement_lines.py](../../tests/contract/test_line_codes_and_statement_lines.py)
   read the order and the statement lines the upload sets, every currency of the account in one
   order (contract: GET /v1/statements/{statement_id}/statement-order), with no order written.
   The review list's cases are task 4's, done in
   [test_bank_lines.py](../../tests/contract/test_bank_lines.py): the old review-list tests of
   `test_statement_order.py` go, not ported (a card's halves, a draft half beside a completed one,
   none listed on a completed statement, an account without a code, `sort=date_asc` on the
   review list), since the live contract no longer states them.
   *Passes if:* the three files pass live and none sends `PUT …/statement-order`, `POST /people`
   or `HAS_STATEMENT_CODE`, and [runtime.md](../runtime.md)'s line on the contract suite no longer
   names `HAS_STATEMENT_CODE`, which no operation sends.
9. **Task 3's review notes (builder).** In
   [test_statement_import.py](../../tests/contract/test_statement_import.py), the card's
   `MONEY_AT_START_NOT_COVERED` is checked by its key and reason and by the currency and amount
   its message names (`USD`, `30000`), not by the whole sentence, which the contract states for
   `POST /statements` only (contract: POST /v1/statements, "Order"); the comment on
   `SOLES_ONLY_MARCH` names what the data holds (two purchases, a payment, interest and a fee).
   In [conftest.py](../../tests/contract/conftest.py), `card_paper` asserts a row's type fits in
   10 characters and an undated row's label in 66, as it already does the description's 55, and
   the comment above the made-up PDFs describes the card's columns beside the savings ones.
   [runtime.md](../runtime.md)'s line on the contract suite introduces the statement upload as run
   on drawn savings and card papers and the published samples.
   *Passes if:* `test_statement_import.py` passes live, the message check names only the
   currency and the amount, and an over-long type or label in `card_paper` fails its assert.

## Reply to the engine

Written into [to-engine/](../to-engine/) when this spec is done, with the tester's results, and
those of part 3 of the currencies catch-up, the live tests' foundation, checked on 2026-10-30
against the practice engine: its 16 live files passed (92 tests) and left nothing on either
practice user. They prove an account and a person made with their currencies in one write and
deleted whole; the opening balance per currency (`REQUIRED`, `UNSUPPORTED_VALUE`,
`CURRENCY_NOT_HELD`, `OPENING_BALANCE_EXISTS` in one currency while the other takes its own);
every transaction and batch item naming its currency; the dashboard's one row per account with
a balance per live currency and no home-currency balance, the month's aggregates in the home
currency with `unconverted_count`; and a statement's life on the account: made, renamed,
completed, reverted and deleted as one record, `NO_TRANSACTIONS_ASSIGNED` per currency, the
list needing `?account_id=`, the period's refusals, locking, an archived account's statements
frozen, a currency with nothing left out and listed in `not_covered`, `DIFFERENCE_NOT_ZERO` per
currency, `MONEY_AT_START_NOT_COVERED`, a line giving a draft its currency's null balances, then
`BEGINNING_BALANCE_REQUIRED` and `ENDING_BALANCE_REQUIRED` in one answer, and `LOCKED` on a
completed statement gaining a currency. Each held as the contract states it.

- **Range:** `e020782e3579d011` → `f82426fb0a099676` (`07475793a38b47b4`, `d5241e52676b19f9`,
  `2d7db5f914b565d9`, `b54580104fce4fde`, `394b3a9034b36d98`, `ba0f857bc43b95ce`,
  `02fb846290642261`, `4d57bb4f05ecc3b3`, `4329913878f62787`, `3d0afdaa03d87d5c`,
  `7aec8f6ed9928caf`, `f82426fb0a099676`), shared by the seven specs.
- **The engine's "Done when" checks this spec reports on:** "A statement is the account's, with
  a starting and ending balance per currency it covers, and the PDF upload closes it", as the
  live suite proves it, the published samples included.
- **The checks of earlier hand-offs:** the live checks the hand-offs of 2026-10-27 and
  2026-10-28 asked this suite to report on a holder and its accounts are superseded by this
  catch-up: the suite reports on the account model only. The samples' check of the hand-off of
  2026-10-27 (the upload tested against the published samples) is reported here, on the
  account model.
- **The asks it closes:** none of its own. "Publish one made-up sample statement PDF per paper,
  so every client can test the statement upload" stays closed: the samples are tested live.
  "An account holds its currencies: the holder becomes the account, and each account becomes
  one of its currencies" closes with [spec 7](catch-up-currencies-7-statement-screen.md).
- **Contract problems found:** `POST /statements/import` lists `STATEMENT_MONTH_TAKEN` on `file`
  among its refusals, but its own rule makes the account's live statement whose `date_end` is in
  the paper's month the paper's, so no other statement can hold that month; only a
  `POST`/`PUT /statements` landing between the upload's read and its write reaches it. Either drop
  it from the upload's refusals, or state that it comes only from a concurrent statement write and
  name it under the upload's "Concurrency" part.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **The Edit form still says "reconciliation"** where the engine says statement: its note
  `Saved. It left its reconciliation.` and the bank-line form's crumb `Reconciliations`
  ([edit_form.py](../../expense/tui/screens/edit_form.py)). Words the owner sees.
- **Two live tests in [test_bank_lines.py](../../tests/contract/test_bank_lines.py) drive the old
  reconciliation screen's reads** (`_fetch_all_lines`, `line_rows`, `unfiled_rows`); part 7's
  statement screen rewrite ports them, and drives the flagged screen's own review-list read,
  which no live test drives yet.
- **No live test has a line whose parts carry different dates** on the review list ("A line is
  listed when any of its parts counts", GET /v1/bank-lines "Filters").
- **runtime.md's contract-suite paragraph cites the holder-era contract.** The live citation
  test, run on 2026-10-31, names four citations on [runtime.md](../runtime.md) line 94 the live
  contract does not hold (`"Reconciliations", "A statement's order"`, `GET /v1/reconciliations`,
  `PUT /v1/reconciliations/{reconciliation_id}`, `POST /v1/reconciliations/import`). No task of
  this spec or of spec 7 names that line.
