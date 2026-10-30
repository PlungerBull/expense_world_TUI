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

**Status: approved by the owner on 2026-10-30; the current spec. It runs after spec 2,** whose app
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

All eight done on 2026-10-30; the acceptance check and the librarian's sweep follow.

## Reply to the engine

None of its own: its results are reported in the reply of
[spec 4](catch-up-currencies-4-live-suite-upload-lines-kinds.md).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **One shared way to log a plain transaction in the live tests.**
  [test_reports_and_dashboard.py](../../tests/contract/test_reports_and_dashboard.py)'s `_spend`
  and [test_reserved_name_held.py](../../tests/contract/test_reserved_name_held.py) each build a
  `POST /transactions` body by hand, since `Scratch.line` takes no category and `Scratch.line` and
  `Scratch.row` both date at noon, which can be in the future. A `Scratch` helper dated a minute
  ago would replace both bodies, and `_post_row` in
  [test_transactions_cursor.py](../../tests/contract/test_transactions_cursor.py) would stop
  passing a day its `date=` overrides. The
  reports' tests dated a minute ago also fail when run in a month's first minute (display
  timezone), the report reading the new month while the row lands in the old one.
