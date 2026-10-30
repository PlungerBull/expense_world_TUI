# The live tests for an account's currencies

Catches up to contract `f82426fb0a099676`, from `e020782e3579d011`: the engine's hand-off of
2026-10-29, "An account holds its currencies: every route names an account and a currency code;
holders are gone" — the part on what is new about an account: made with its currencies, a
currency added and removed, edited and deleted whole, a transaction's currency, the old names
refused, and the account's closed days, as the live suite proves them. The catch-up is seven
specs, run in this order:

1. part 1, the app's reads and writes (done on 2026-10-30);
2. part 2, the PDF upload and the two imports (done on 2026-10-30);
3. [catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md);
4. [catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md);
5. this one;
6. [catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md);
7. [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).

**Status: draft, written 2026-10-29 for the owner to approve. It runs after spec 4;** its tests
build their records through spec 3's `Scratch`. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Each new engine capability gets its live test in this client, so a wrong rule shows here first,
before the web and iPhone apps build on it. The engine now makes an account with its currencies
in one write, adds a currency to an account and removes one, and edits, archives, converts and
deletes the account with every currency at once (contract: "What an account is", "Its currencies").
Every transaction names a currency its account holds
(contract: POST /v1/transactions, "`account_id` and `currency_code`"), the old per-currency ids
and the holder routes are refused, and an account's closed days stay closed for a currency added
later (contract: POST /v1/accounts/{account_id}/currencies, "The account's statements are not touched").
None of this has a live test yet.

Two writes sent at the same moment can be refused `CONCURRENT_CHANGE`
(contract: "Base Conventions", "Concurrent changes"); a live test cannot make two requests land
at the same moment reliably, so it is not tested live.

Nothing you see changes. Only the tests change.

## What it must do

1. **Making an account is tested live:** a bank account and a person, each with soles and
   dollars in one write, all or nothing, and each refusal in the engine's order, writing nothing
   (contract: POST /v1/accounts, "Validation").
2. **Adding and removing a currency is tested live,** each refusal first one first and writing
   nothing, a removed currency added back
   (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals").
3. **Editing and deleting act on the whole account:** a rename and a new code in one write, the
   currency never edited (contract: PUT /v1/accounts/{account_id}, "Not fields of the `PUT`"),
   and the delete taking every currency (contract: DELETE /v1/accounts/{account_id}, "Refusals").
4. **A transaction's currency is tested live:** one the account does not hold refused, alone and
   in a batch, nothing written; the lists narrowed by currency.
5. **The old names are refused:** a former per-currency id, the holder routes, the move and the
   people route, and `?holder_id=`.
6. **An account's closed days hold for a currency added later**
   (contract: "Transactions (Ledger)", "Sealed periods").
7. **The reads are pinned:** an account's keys, its currencies' keys and order, bank accounts
   before people (contract: "Bank Accounts", "Account response"), and the activity log's entries
   for an account and its currencies (contract: GET /v1/activity, "Accounts and their currencies").
8. **Every `(contract: …)` citation in the tests, the scripts and [runtime.md](../runtime.md)
   names a part the live contract holds**, and runtime.md says what the suite proves.

## How the owner knows it is done

1. The live suite passes against the practice engine, these tests included.
2. A run leaves nothing on either practice user.
3. The citation test passes on the tests, the scripts and runtime.md.

## What the owner settled

None: this spec changes only tests and runtime.md.

## Questions for the owner

None.

---

## Tasks

Drafted 2026-10-29. Each needs the practice engine, which the orchestrator starts before the
task and stops after it. Each builds its records through spec 3's `Scratch`, cites the live
contract, and proves each refusal wrote nothing by reading the account back, its `version` and
its `currencies` unchanged.

1. **Making an account (builder).** A new tests/contract/test_account_create.py: the Visa in
   PEN and USD and ALEJO (`is_person: true`) in PEN and USD, each `201` in one write, its
   currencies PEN before USD at `0` with no opening balance; `currency_code` and `holder_id` on
   the body `UNKNOWN_FIELD`, and an unknown field in an entry keyed
   `currencies.<i>.<field>`; the refusals in order, each step proven against the next by one
   body breaking both: `OUT_OF_RANGE` on `currencies` (empty, eleven entries); then in one
   answer `EMPTY` on `name` and `DUPLICATE_CURRENCY` on `currencies.1.currency_code`;
   `ID_EXISTS` on `id` for a deleted account's id and for a former per-currency id, read from
   the practice user's older activity entries (contract: GET /v1/activity, "Older and restored entries");
   `LIMIT_REACHED` on `id` (contract: "Base Conventions", "Create caps"), by filling the cap
   with accounts the test deletes after, if that runs in under a minute, and otherwise left out
   with the reason in the test's docstring; `UNSUPPORTED_VALUE` on every such
   `currencies.<i>.currency_code`; `409 NAME_EXISTS` on `name`, either kind, ignoring case;
   `409 STATEMENT_CODE_EXISTS`.
   *Passes if:* the file passes live, every refusal leaves no account, and its docstring says
   which cases it leaves out and why.
2. **Adding and removing a currency (builder).** A new
   tests/contract/test_account_currencies.py: `POST /accounts/{id}/currencies` → `201`, the new
   currency at `0`, the account's `version` unmoved; refused `404` for an unknown or deleted
   account, `UNSUPPORTED_VALUE`, `409 DUPLICATE_CURRENCY` on `currency_code`, and on an archived
   account `422 INVALID_REFERENCE` on `account_id`
   (contract: POST /v1/accounts/{account_id}/currencies, "Refusals"). `DELETE
   /accounts/{id}/currencies/{code}` → `200`, the currency gone, `version` unmoved; refused in
   order: `404` "account not found.", `404` "currency <code> not found." (`EUR`, `usd`, one
   removed before), `ACCOUNT_ARCHIVED` on `account_id`, `LAST_CURRENCY` on `currency_code`,
   `HAS_TRANSACTIONS` on `account_id` while its opening balance stands and `200` once it is
   deleted, `IN_LIVE_STATEMENT` on `account_id` while a draft holds its balances; the removed
   code added back `201` at `0`.
   *Passes if:* the file passes live, every refusal writing nothing, in the engine's order.
3. **Editing and deleting the account (builder).** In test_account_currencies.py:
   `PUT /accounts/{id}` with `{"name": …, "statement_code": …}` → one write, `version` up by one;
   `statement_code: null` clearing it; `currency_code` `IMMUTABLE`; `currencies`, `is_person`,
   `is_archived` and `holder_id` `UNKNOWN_FIELD`; `NOT_NULL` on `name`; `409 NAME_EXISTS` and
   `409 STATEMENT_CODE_EXISTS`. `DELETE /accounts/{id}` → `200` with `deleted_at` and the
   currencies it held, `GET` then `404`, its name and code taken at once by a new account;
   refused `HAS_TRANSACTIONS` before `IN_LIVE_STATEMENT`, the second on an account whose only
   hold is a statement with USD balances and no transaction.
   *Passes if:* those tests pass live, each refusal writing nothing.
4. **A transaction's currency (builder).** A new tests/contract/test_transaction_currency.py:
   `POST /transactions` echoing `account_id` and `currency_code`; `currency_code` missing
   `REQUIRED`; `UNSUPPORTED_VALUE`; USD on a soles-only account `CURRENCY_NOT_HELD` on
   `currency_code`; a batch with one bad item refused on `transactions.<i>.currency_code`,
   nothing written; a line group whose items differ in `currency_code`
   `LINE_GROUP_FIELDS_DIFFER` (contract: POST /v1/transactions/batch, "Line groups"); one
   operation code taken in each currency of one account
   (contract: POST /v1/transactions, "Unique per currency of an account among live bank lines");
   `GET /transactions` and `/count` by `?account_id=` covering both currencies,
   `?currency_code=` with it or alone, `UNSUPPORTED_VALUE` for an unsupported code, and a
   cursor sent with `currency_code` changed `INVALID_CURSOR` on `after`
   (contract: "Base Conventions", "Cursors, on every cursor-paged list").
   *Passes if:* the file passes live and every refusal leaves the account's count unchanged.
5. **The old names refused (builder).** In test_transaction_currency.py: a former per-currency
   id, read as in task 1, `404` on `GET`, `PUT` and `DELETE /accounts/{id}`,
   `INVALID_REFERENCE` on `account_id` of `POST /transactions`, and an empty list and count `0`
   as `?account_id=` on `/transactions` and `/bank-lines`; `GET /holders`, `GET /holders/{id}`,
   `POST /accounts/{id}/move` and `POST /people` answering exactly as a made-up route does;
   `?holder_id=` `UNKNOWN_PARAMETER` on `GET /statements`, `/transactions`, `/bank-lines` and
   `/bank-lines/count` (contract: "Base Conventions", "Unknown query parameters").
   *Passes if:* the tests pass live, and no test sends an old name but to prove its refusal.
6. **The account's closed days (builder).** In
   [test_sealed_periods.py](../../tests/contract/test_sealed_periods.py): a soles-only account
   with a completed statement takes USD (`201`); a USD transaction dated on a day it seals
   `SEALED_PERIOD`, one dated after it accepted; the completed statement still holding PEN
   only, and still after a revert.
   *Passes if:* those tests pass live and leave nothing.
7. **The reads (builder).** A new tests/contract/test_account_reads.py: `GET /accounts` and
   `GET /accounts/{id}` keys exactly `id, user_id, name, color, is_person, statement_code,
   is_archived, sort_order, currencies, created_at, updated_at, version, deleted_at`, each
   currency exactly `{currency_code, current_balance_cents, opening_balance_transaction_id}`,
   PEN before USD, no home value; every bank account before every person
   (contract: GET /v1/accounts, "Ordering"); an archived account's currencies listed with
   `?include_archived=true`; `GET /activity?resource_id=<account id>` reading one `account` and
   two `currency` entries for a create, the `account` entry alone for a `PUT`, an archive and a
   kind change, one `currency` entry for an add or a removal, each snapshot with the contract's
   keys (contract: "What an account is", "Account snapshot").
   *Passes if:* the file passes live and names no `holder`.
8. **The last citations (builder).** Every citation left in tests/, scripts/ and runtime.md
   moved to the live contract, and runtime.md's paragraph on what the suite does saying what
   it proves on the account model, specs 3 and 4 included.
   *Passes if:* the citation test names no file of tests/, scripts/ or runtime.md, and
   runtime.md names no `/reconciliations`, `twin`, holder or `POST /people`.

## Reply to the engine

Written into [to-engine/](../to-engine/) when this spec is done, with the tester's results.

- **Range:** `e020782e3579d011` → `f82426fb0a099676`, shared by the seven specs (the versions
  are listed in [spec 4](catch-up-currencies-4-live-suite-upload-lines-kinds.md)'s reply).
- **The engine's "Done when" checks this spec reports on,** as the live suite proves them (the
  app's half of each is [spec 6](catch-up-currencies-6-main-views.md)'s): `GET /accounts` lists
  an account holding PEN and USD, a balance for each, and no route or field names a holder; an
  account in soles and dollars, and a person in soles and dollars, are each created in one
  write, a currency is added later and one with nothing booked is removed; archiving,
  unarchiving, turning into a person and back, and deleting act on the account, all its
  currencies at once; a transaction in a currency the account does not hold is refused,
  nothing written. `CONCURRENT_CHANGE` is not tested live, and why.
- **The asks it closes:** none; "An account holds its currencies: the holder becomes the
  account, and each account becomes one of its currencies" closes with
  [spec 7](catch-up-currencies-7-statement-screen.md).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
