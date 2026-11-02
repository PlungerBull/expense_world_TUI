# The live tests for an account's currencies

Catches up to contract `f82426fb0a099676`, from `e020782e3579d011`: the engine's hand-off of
2026-10-29, "An account holds its currencies: every route names an account and a currency code;
holders are gone" — the part on what is new about an account: made with its currencies, a
currency added and removed, edited and deleted whole, a transaction's currency, the old names
refused, and the account's closed days, as the live suite proves them. The catch-up is seven
specs, run in this order:

1. part 1, the app's reads and writes (done on 2026-10-30);
2. part 2, the PDF upload and the two imports (done on 2026-10-30);
3. part 3, the live tests' foundation (done on 2026-10-30);
4. part 4, the live tests for the upload, bank lines and kinds (done on 2026-10-31);
5. this one;
6. part 6, the main views (done on 2026-10-31);
7. [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).

**Status: approved by the owner on 2026-10-31; it runs now, after part 6.** Its tests
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
   *Passes if:* the citation test names no file of tests/contract/, scripts/ or runtime.md, and
   runtime.md names no `/reconciliations`, `twin`, holder or `POST /people`. The unit tests'
   holder-era citations go with the statement screens they test, in
   [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md)'s task 9.

## Reply to the engine

Written into [to-engine/](../to-engine/) when this spec is done, with the tester's results.

- **Range:** `e020782e3579d011` → `f82426fb0a099676`, shared by the seven specs (the versions
  are listed in part 4's reply to the engine).
- **The engine's "Done when" checks this spec reports on,** as the live suite proves them (the
  app's half of each is part 6's, done on 2026-10-31): `GET /accounts` lists
  an account holding PEN and USD, a balance for each, and no route or field names a holder; an
  account in soles and dollars, and a person in soles and dollars, are each created in one
  write, a currency is added later and one with nothing booked is removed; archiving,
  unarchiving, turning into a person and back, and deleting act on the account, all its
  currencies at once; a transaction in a currency the account does not hold is refused,
  nothing written. `CONCURRENT_CHANGE` is not tested live, and why.
- **Contract problems found:** `OPERATION_CODE_EXISTS` on a second bank line with a taken
  operation code (contract: POST /v1/transactions, "Unique per currency of an account among live bank lines").
  The contract gives it "on `operation_code` (`OPERATION_CODE_EXISTS`) with `"Another bank line
  on this account already has operation code '<code>'."`", a phrasing that everywhere else in the
  contract names the field's own text. The engine sends that sentence as `error.message`, and
  `fields["operation_code"]` as "Must not be an operation code already on this account.", which
  the contract never states. Ask: either move the sentence into `fields`, or reword the contract
  to "(message `"…"`)" and state the field's own text. The live suite tests neither side until
  then; the tester confirms both engine answers in this note before the reply is written. Also: a batch with two items sharing one operation code on one currency is
  `DUPLICATE_IN_REQUEST` on `transactions.<i>.operation_code`
  (contract: POST /v1/transactions/batch), but the contract does not say which item `<i>` is. The
  engine names the second. A statement's repeated currency names "the later entry"; ask the
  contract to say the same here. The live suite accepts either item until then.
- **The asks it closes:** none; "An account holds its currencies: the holder becomes the
  account, and each account becomes one of its currencies" closes with
  [spec 7](catch-up-currencies-7-statement-screen.md).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **No unit test shows how `x` on Manage ▸ Accounts draws the remove's two `404`s**, "account
  not found." and "currency <code> not found.", which the live engine answers before any other
  refusal (found by task 2 on 2026-10-31).
