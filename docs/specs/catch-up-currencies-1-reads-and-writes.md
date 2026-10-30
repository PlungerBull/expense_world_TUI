# The app's reads and writes on an account and its currencies

Catches up to contract `f82426fb0a099676`, from `e020782e3579d011`: the engine's hand-off of
2026-10-29, "An account holds its currencies: every route names an account and a currency code;
holders are gone" — the part on accounts, transactions, bank lines, Home and the app's shared
reads. This is spec 1 of seven that share that range, run in this order:

1. this one: the app's reads and writes on an account and a currency code, with the screens as
   close to today as the new model allows;
2. [catch-up-currencies-2-statements-and-imports.md](catch-up-currencies-2-statements-and-imports.md):
   statements, the statement PDF upload, the bank download and the sheet import on the account;
3. [catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md):
   the live tests' shared helpers, and a statement's life, on the new model;
4. [catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md):
   the live tests of the upload, bank lines and the two kinds of account;
5. [catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md):
   an account's currencies proven live;
6. [catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md): the main views on
   the new model, from mockups you pick;
7. [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md): an
   account's statement on one screen.

**Status: approved by the owner on 2026-10-29, running; it runs first of the seven.** When
done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

On 2026-10-29 the engine made each bank account, card and person **one account holding its
currencies**: the Visa is one account with soles and dollars, no longer two accounts on a holder
(contract: "What an account is", "Its currencies"). Every route now names the account and a
currency code, and the per-currency ids the app sends are refused. The practice engine already
runs this version, and the engine on your computer will once you apply its update, so these
break:

- logging a transaction in the LOG bar, and the quick-add line;
- moving a transaction on the Edit form, or several at once in the ledger;
- the ledger's Account column and Home's balances;
- Manage ▸ Accounts, creating an account or a person, and an account's opening balance.

This spec puts the app's reads and writes on the new model, **with the screens as close to today
as it allows**. The one change you see: where a list or a picker showed one row per currency's
account, each row now reads as the engine names a currency, the account's name and its code:
"VISA Infinite Sapphire · USD". Picking the currency as a field of its own, and every screen
redrawn for the new model, come in spec 6.

**Until spec 6:** a new account still has one currency (the New account form keeps its one
CURRENCY line), no screen adds or removes a currency, and Manage ▸ Accounts acts on the whole
account from any of its rows. The statement screens, the statement PDF upload, the bank download
and the sheet import stay broken until spec 2.

## What it must do

1. **The fake engine the unit tests run against answers as the engine does now**: an account
   with its `currencies`, each transaction and bank line naming its account and its currency
   code, and `/dashboard`'s rows one per account; the drift check finds nothing in this spec's
   routes.
2. **A currency is picked as one row per account and currency**, labelled "<account> · <code>",
   in the engine's order: the accounts in their order, PEN before USD within one account
   (contract: GET /v1/accounts, "Ordering") (contract: "Bank Accounts", "Per-currency order").
   Archived accounts and people are left in or out of each list as today.
3. **Every transaction write names the account and the currency**: the LOG bar's create and
   batch, the Edit form's save, the ledger's bulk `b` and the whole-line write
   (contract: POST /v1/transactions, "`account_id` and `currency_code`")
   (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction")
   (contract: PUT /v1/bank-lines/{bank_line_id}, "`account_id` and `currency_code` move the line").
   A move sends only the key that changed, and a change of either takes the row out of its
   statement, as a move does today
   (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment"). A currency the
   account does not hold is refused in the engine's words, nothing written.
4. **Every transaction and bank line shows its currency from its own `currency_code`**: the
   ledger's Account column, the Edit form, the LOG bar's staged totals and its peek. A list or
   count of one account's currency reads `?account_id=` with `?currency_code=`
   (contract: GET /v1/transactions) (contract: GET /v1/bank-lines, "Filters").
5. **Home reads `/dashboard`'s accounts** (contract: GET /v1/dashboard, "`bank_accounts`")
   (contract: GET /v1/dashboard, "`people`"), and shows one row per account and currency, each
   balance in its own currency, never summed (contract: GET /v1/dashboard, "Balances are native only");
   a person settled in one currency and owing in the other shows in each place; `⏎` opens the
   ledger on that account and currency.
6. **Manage ▸ Accounts lists one row per account and currency**, and `e`, `a`, `t` and `d` act on
   the account under the cursor, every currency at once
   (contract: POST /v1/accounts/{account_id}/archive, "Every currency at once")
   (contract: "What an account is", "An account is deleted whole"); `d`'s question names the
   account and each of its currencies with its balance, as the owner settled.
7. **The New and Edit account forms write the new model.** A new account's one currency goes in
   its `currencies`, and a person is created on the same route, as a person
   (contract: POST /v1/accounts, "Required") (contract: POST /v1/accounts, "Optional"). The Edit
   form's opening balance is the opened row's currency's, sent with its code
   (contract: POST /v1/accounts/{account_id}/opening-balance, "Required"). A statement code
   another account holds is refused in the engine's words alone, as the owner settled
   (contract: "What an account is", "One account per code").
8. **The practice-data cleaner's printout** names each account with its currencies and its
   statement code. Its reads of statements move in spec 3
   ([catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md)).

## How the owner knows it is done

On the practice engine, with the practice user's Visa holding soles and dollars:

1. In the LOG bar, `-12.50 $visa` offers "VISA Infinite Sapphire · PEN" and "VISA Infinite
   Sapphire · USD"; the one picked saves, and the ledger shows the row on it.
2. On the Edit form, a transaction moved from the Visa's soles to its dollars saves, and the
   ledger shows it in dollars; moved out of a draft statement, it says it left it, as today.
3. Home shows the Visa as two rows, each with its own balance; `⏎` on the dollars row opens the
   ledger on the Visa's dollar rows alone.
4. On Manage ▸ Accounts, `a` on either of the Visa's rows archives the Visa: both rows dim, and
   `a` again brings both back. A new bank account and a new person in one currency each save.
5. The unit suite passes; the drift check reads `f82426fb0a099676`, and its fixture check names
   only what spec 2 moves: the statements, the PDF upload, the bank download, the sheet import
   and the holder routes. A transaction in a currency its account does not hold is proven by
   the unit tests here and live in spec 5.

## What the owner settled

- **A currency shows as its account's name and its code** (owner, 2026-10-29, the engine's
  hand-off "The owner's rulings"): "VISA Infinite Sapphire · USD"; a currency has no name of its
  own.
- **The currency is picked as its own field** (owner, 2026-10-29): in the LOG bar, the Edit form,
  the ledger and the account forms; that is spec 6's, and until then a currency is picked as
  "<account> · <code>".
- **When `t` is refused for an account that has been in a statement, the engine's words show
  alone** (owner, 2026-10-28, 2 A): the engine refuses an account that was ever in a statement,
  a deleted one included (contract: POST /v1/accounts/{account_id}/make-person).
- **`STATEMENT_CODE_EXISTS` reads in the engine's words alone** (owner, 2026-10-28, question 9 A
  of the cards spec): the app's own line under it goes.
- **`d` on Manage ▸ Accounts names the whole account until spec 6** (owner, 2026-10-29,
  question 1 A, [mockups/expense-world-currencies-delete.html](../mockups/expense-world-currencies-delete.html)):
  whichever of the account's rows the cursor is on, the question's second line is the account,
  its kind, then each currency it holds with that currency's balance,
  `Prueba · bank · PEN 0.00 · USD 0.00`, then today's sentence; a one-currency account reads
  `Efectivo · bank · PEN 350.00`.

---

## Tasks

Approved by the owner on 2026-10-29. Each leaves `pytest tests/unit` green.
Each task fixes the `(contract: …)` citations and the [tui.md](../tui.md) and
[runtime.md](../runtime.md) lines of the code it touches. Old shapes a task cannot yet remove
stay, named for what they are, until the task that moves their last user removes them.

5. **Home on the dashboard's accounts (builder).** `/dashboard`'s rows `{id, name, currencies}`
   become one Home row per account and currency, named "<account> · <code>", the balance cell
   as today; PEOPLE folds a row as settled when that currency's balance is exactly zero
   ([formatting.py](../../expense/formatting.py)'s `split_settled`, its docstring without the
   home value); `⏎` opens the ledger on that account and currency (task 4).
   `HOME_DASHBOARD` reads as the engine's answer. Files:
   [home.py](../../expense/tui/screens/home.py), formatting.py, helpers.py, the Home tests.
   *Passes if:* unit tests pin a two-currency account's two rows in the engine's order, a person
   settled in soles and owing in dollars showing once in each place, and `⏎` handing the ledger
   the account and the currency.
6. **Manage ▸ Accounts on the account's currencies (builder).** One row per
   account and currency, named "<account> · <code>", Cur and Balance that currency's, the other
   cells the account's; `e`, `a`, `t` and `d` act on the cursor row's account, through the
   routes the screen calls today; after `a` or `t` the cursor comes back to the same row; `d`
   asks as "What the owner settled" draws it. Files: [accounts.py](../../expense/tui/screens/accounts.py) and its
   tests (accounts, account kind, Manage actions, delete) on task 1's builder.
   *Passes if:* unit tests pin a two-currency account's rows, `a` on either row sending one
   `POST /accounts/{id}/archive` with the account's id and both rows dim after the reload, and
   the delete question as picked.
7. **The New and Edit account forms on the new model (builder).** New
   account keeps its one CURRENCY line and sends it as `currencies: [{currency_code}]`; a person
   is created with `POST /accounts` and `is_person: true`, so the form names no `/people` route.
   Edit account, opened on a row, sends name, colour and code in one `PUT /accounts/{id}`
   (contract: PUT /v1/accounts/{account_id}, "`statement_code`"), and that row's currency's
   opening balance with `currency_code`, its id read from that currency's
   `opening_balance_transaction_id`; `STATEMENT_CODE_EXISTS` shows the engine's words alone.
   Files: [create_forms.py](../../expense/tui/screens/create_forms.py), errors.py, and the
   create-form, opening-balance and statement-code tests on task 1's builder.
   *Passes if:* unit tests pin a new bank account's body and a new person's, an opening balance
   saved on a two-currency account's dollars row sending `currency_code: USD` while its soles one
   stays, and the code refusal's line as picked.
8. **The practice-data cleaner's printout on the account (builder).**
   [clean_practice_user.py](../../scripts/clean_practice_user.py)'s printout names each matched
   account with its currencies, read from its `currencies`, and its statement code, where it
   reads the account's `currency_code` today (contract: "Bank Accounts", "`currencies`"). Its
   statement reads, `plan()` and `apply()`, are spec 3's task 2
   ([catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md)).
   *Passes if:* its unit tests, on task 1's builder, pin the printout naming a two-currency
   account's currencies and its code, and no line of the script reads an account's
   `currency_code`.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `e020782e3579d011` → `f82426fb0a099676` (`07475793a38b47b4`, `d5241e52676b19f9`,
  `2d7db5f914b565d9`, `b54580104fce4fde`, `394b3a9034b36d98`, `ba0f857bc43b95ce`,
  `02fb846290642261`, `4d57bb4f05ecc3b3`, `4329913878f62787`, `3d0afdaa03d87d5c`,
  `7aec8f6ed9928caf`, `f82426fb0a099676`), shared with the six other specs.
- **The engine's "Done when" checks to report on:**
  - "The TUI has read up to `f82426fb0a099676` and says so": this client's contract snapshot is
    at `f82426fb0a099676`, recorded on 2026-10-29.
  - "A transaction names an account and a currency it holds; one in a currency the account does
    not hold is refused, nothing written, and the app shows why": on the LOG bar's create and
    batch, the Edit form's and the ledger's moves, and the whole-line write.
  - "Archiving, unarchiving, turning into a person and back, and deleting act on the account,
    all its currencies at once": at the level of the routes, from Manage ▸ Accounts (one row
    per account on screen is spec 6's).
  - "No request in the TUI sends a `/holders` route, `POST /accounts/{id}/move`, `?holder_id=`
    or a per-currency id": for the transaction, bank-line, Home and Manage ▸ Accounts calls;
    the statement and import calls are spec 2's.
- **The asks it closes:** none. "An account holds its currencies: the holder becomes the
  account, and each account becomes one of its currencies" closes with spec 7.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **The LOG bar's words still count accounts where they mean currencies** (task 2's reviewer,
  2026-10-29): `$visa` on the two-currency Visa says `"$visa" matches 2 accounts` on the hint and
  in a refusal ([route.py](../../expense/quickadd/route.py)), and the peek's status reads "of N in
  this account" while it counts one currency of the account. New wording is the owner's pick;
  spec 6, which redraws the LOG bar, is the natural home.
- **The LOG bar's test accounts keep the old per-currency names** (task 2's builder): "BCP
  Signature PEN", so their labels read "BCP Signature PEN · PEN"; rename them to account names
  holding currencies.
