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
`(contract: …)` citations of the files it touches.

Every task is done; the spec's acceptance check comes next.

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
  `GET /bank-lines/{id}`'s "Response fields" (`is_opening_balance`) still says "a
  `PUT /statements/{id}/statement-order` that lists it is refused on its entry
  (`OPENING_BALANCE_NOT_PLACED`)", but no such route exists: `GET …/statement-order` is the only
  operation on that path, and no route sets the order by hand. Drop the sentence.
  `POST /accounts` says `is_person` that is `null` or "a value that is not a boolean is `422`
  (`INVALID_FORMAT`)", but the engine takes `"yes"`, `"no"`, `"true"`, `1` and `0` as booleans (checked
  live on 2026-10-31 with a body missing `name`, so nothing was written: `"maybe"` and `null`
  are refused on `is_person`, those five are not). Refuse them, or state which values count.
  `make-account` lists `HAS_RECONCILIATION`, but no person ever holds a statement (a person is
  refused every statement write, and an account that has had one never becomes a person), and a
  bank account with a statement is answered `KIND_UNCHANGED` first; the refusal cannot be
  reached. Drop it from `make-account`'s refusals, or say when it comes.

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
