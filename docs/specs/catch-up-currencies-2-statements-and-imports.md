# Statements and imports on an account and its currencies

Catches up to contract `f82426fb0a099676`, from `e020782e3579d011`: the engine's hand-off of
2026-10-29, "An account holds its currencies: every route names an account and a currency code;
holders are gone" — the part on statements, the statement PDF upload, the bank download and the
sheet import. This is spec 2 of seven that share that range, run in this order:

1. part 1, the app's reads and writes (done on 2026-10-30): the
   app's reads and writes on an account and a currency code;
2. this one: statements, the statement PDF upload, the bank download and the sheet import on the
   account, with the screens as close to today as the new model allows;
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

**Status: draft, written 2026-10-29 for the owner to approve; it runs after spec 1, whose fake
engine, account picks and "<account> · <code>" labels it uses.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

On 2026-10-29 the engine made each bank account and card one account holding its currencies,
and a statement **the account's**: one per account per month, with a starting and an ending
balance for each currency it covers (contract: "Statements", "Which currencies a statement covers").
Holders are gone, and so are the routes and names the statement screens and the imports used.
So these break:

- the Reconciliations screens: the list, the new-statement forms, ticking, complete, revert,
  delete and the flagged lines;
- the statement PDF upload and the bank download, and their list of accounts;
- `expense import sheet`, whose names table and renames are per name and currency.

This spec puts them back on the new model, **with the screens as close to today as it allows**.
As in spec 1, a currency reads "<account> · <code>" where a currency's account was named. What
else you see change:

- **A statement may hold fewer currencies than its account.** A Visa month with no dollar line
  and no dollars owed at its start has no dollar balances, and a starting balance can be blank
  until it is entered (contract: "Statements", "A balance not entered is `null`, never zero").
  How the screens show both is question 1; `c` asks for a blank one as question 2 picks.
- **The PDF upload shows a balance only for each currency the paper has something in**
  (contract: POST /v1/statements/import, "Which currencies the statement covers").
- **The sheet's account names are one per name**, mapped to one account, each row going to the
  currency in its own MONEDA (contract: POST /v1/transactions/import-sheet, "Names"). The names
  table shows each name's currencies as question 3 picks; `--account-name` drops its currency,
  `--account-name "BCP=Sueldo"`, and your saved renames follow questions 4 and 5.

The statement screen drawn for the new model, a statement per account with a balance per
currency, is spec 7.

## What it must do

1. **Every statement read and write names the account.** The statement list is read by the
   account (contract: GET /v1/statements, "`?account_id=<id>` is required"), a new statement
   names it, and every balance is keyed by its currency
   (contract: POST /v1/statements, "`balances`") (contract: PUT /v1/statements/{statement_id}, "`balances`");
   an account's statement code is read from the account
   (contract: "What an account is", "Statement code"). Nothing reads a holder.
2. **The Reconciliations list opens on one row per account and currency**, as today's rows per
   account; `⏎` on either of an account's rows lists the account's statements, with a Diff
   column per currency of the account on an account with a statement code, as a card's
   accounts have one each today.
3. **A currency a statement does not cover, and a blank starting balance, show as question 1
   picks**, on the list and on the working screen.
4. **A new statement takes its account's balances in one write**: an account of one currency
   on today's one-account form, an account of two on today's card form, its two lines each
   naming one currency of the account; both currencies' balances are asked for as today, the
   engine taking `0` → `0` for one with nothing in it (contract: POST /v1/statements, "`balances`").
5. **The working screen, opened on one currency of a statement**, shows that currency's
   balances and lists that currency's lines, in the statement and in none
   (contract: GET /v1/bank-lines, "Filters"). After a line is ticked in or out it reads the
   statement again, which may have gained that currency's balances, both blank
   (contract: "Statements", "A line in a currency the statement holds no balances for gives it that currency's balances").
6. **`c` completes on the new rules.** It asks for the opened currency's missing balances as
   question 2 picks; a blank starting balance or a currency with money at the start in another
   currency is refused in the engine's words, which name the currency to open
   (contract: POST /v1/statements/{statement_id}/complete, "Every balance must be entered")
   (contract: POST /v1/statements/{statement_id}/complete, "Every currency with money at the start has balances in it").
   The notes and flagged lines of each currency the statement does not cover show beside the
   balances' own (contract: POST /v1/statements/{statement_id}/complete, "`not_covered`").
7. **The statement PDF upload sends the account**, reads each row's and balance's currency from
   its `currency_code`, and shows the new refusals in the engine's words
   (contract: POST /v1/statements/import, "Every currency the paper shows something in must be one the account holds")
   (contract: POST /v1/statements/import, "A currency of the account the paper does not print at all").
8. **The bank download sends the account alone**: its list of accounts has one line per account,
   named by the account with its currencies, as a card's line reads today (`VISA Infinite
   Sapphire   PEN + USD`); each row goes to the currency in its own Moneda and shows it
   (contract: POST /v1/transactions/import, "Accounts"); a row in a currency the account lacks is
   refused in the engine's words, nothing written.
9. **The sheet import sends one entry per account name** with the account it maps to; the names
   table shows each name's currencies (question 3); `--create-names` creates one account per
   missing name with the currencies its rows use (contract: POST /v1/accounts, "Required");
   an account lacking a currency its name's rows use is refused in the engine's words;
   `--account-name SHEET_NAME=LEDGER_NAME` and the saved renames name a sheet account by its name
   alone (questions 4 and 5).
10. **No request sends a `/holders` route, `?holder_id=` or a per-currency id**, and the drift
    check's fixture check is clean.

## How the owner knows it is done

On the practice engine, with the practice user's Visa holding soles and dollars and a code:

1. The Reconciliations list shows "VISA Infinite Sapphire · PEN" and "VISA Infinite Sapphire ·
   USD"; `⏎` on either lists the Visa's statements with a Diff for each currency; `n` creates
   one with both currencies' balances; ticking, complete, revert and delete work as today.
2. A month with no dollar movement shows its dollars as question 1 picks, and `c` on a statement
   with a blank starting balance asks for it as question 2 picks.
3. The engine's sample `card` PDF dropped for the Visa previews and closes the month, a balance
   shown for each currency.
4. A bank download for a two-currency account previews each row with its currency, and imports.
5. `expense import sheet` on a made-up sheet lists one row per account name with its currencies;
   `--create-names` creates one account per name holding those currencies; `--apply` imports.
6. The unit suite and the drift check pass whole, the drift check reading `f82426fb0a099676`.
   The live suite passes once specs 3 to 5 are done.

## What the owner settled

- **A currency shows as its account's name and its code** (owner, 2026-10-29, the engine's
  hand-off "The owner's rulings").
- **The plan of the seven specs** (owner, 2026-10-29): `--account-name` and the saved renames
  lose the currency, and the sheet's `--create-names` makes one account per name with the
  currencies its rows use.
- **The lines a close flags show in the engine's order** (owner, 2026-10-28, 1 A): the
  statement's order, every currency of the account together, is the only order the engine gives
  this list (contract: GET /v1/bank-lines, "Read in the statement's order, and only in it").

## Questions for the owner

1. **A currency the statement does not cover, and a blank starting balance**: answered once, by
   question 2 and question 3's first part of
   [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md); this
   spec shows them the way those answers pick, on today's screens.
2. **`c` when the opened currency's starting balance is blank, or the statement holds no
   balances for it while it had money at the start**: answered once, by question 3's second part
   of [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).
3. **The sheet's names table, one row per account name** [mockup to draw]. Today each row is a
   name in one currency, with a CUR column; the engine now lists each name once with every
   currency its rows use.
   - **A.** The CUR column lists them, `PEN + USD`, as the bank download's list writes a card's.
   - **B.** No CUR column; the currencies after the name, `Visa (PEN, USD)`.

   **Recommended:** A: the table keeps its columns.
4. **Your saved renames.** Your config keeps renames per name and currency (`BCP:PEN` →
   `Sueldo Soles`); a rename is now per name.
   - **A.** A saved rename is read by its name alone; two for one name that go to different
     ledger names stop the run, naming both, nothing imported, until `--account-name` for that
     name replaces them.
   - **B.** Saved renames with a currency are left out and dropped at the next save; the run
     lists them, and you pass `--account-name` again.

   **Recommended:** A: your renames keep working, and a clash is shown, never guessed.
5. **Two sheet names renamed onto one account.** Today it is refused before anything is
   written. The engine now takes two names for one account, each row in its own currency
   (contract: POST /v1/transactions/import-sheet, "Names").
   - **A.** Allowed: both names' rows go to that account.
   - **B.** Still refused.

   **Recommended:** A: the engine decides what may share an account, and the app only checks
   that what you typed is well formed.

---

## Tasks

Drafted 2026-10-29; they wait on the owner's approval. Each leaves `pytest tests/unit` green.
Each task fixes the `(contract: …)` citations and the [tui.md](../tui.md),
[runtime.md](../runtime.md) and [commands.md](../commands.md) lines of the code it touches, and
moves its tests onto spec 1's account builder.

1. **Statements in the fake engine, the reads and the Reconciliations list (builder).** In
   [helpers.py](../../tests/unit/helpers.py): the statement builders read as the engine does now,
   `account_id`, `balances` by `currency_code` with a beginning balance that may be `null`, and
   `not_covered` on the complete. In [reads.py](../../expense/reads.py), `fetch_statements` takes
   the account's id. The browse
   ([reconciliations.py](../../expense/tui/screens/reconciliations.py)) lists spec 1's picks,
   its other columns as today; its panel reads the account's statements and its code from the
   account, one Diff per currency of the account, a missing currency read as an empty
   balance; `balance_of`, `statement_columns` and their kin key by currency; `holder_of` and
   `holder_mates` go.
   *Passes if:* unit tests pin the panel of a two-currency account opened from either row, its
   Diff columns, a statement holding only soles, and the one read `GET /statements?account_id=`;
   no screen reads `/holders`.
2. **The new-statement forms on the account (builder).** `n` opens the one-account form on an
   account of one currency and the card form on one of two, the card form's accounts line
   reading "<account> · <code> + <account> · <code>", then the code; each sends one
   `POST /statements` with `account_id` and an entry per currency, keyed `currency_code`. The
   retired `ACCOUNT_NOT_ON_HOLDER` and `HOLDER_ACCOUNTS_MISSING` leave the tests; a refusal of
   one currency's balances (`balances.<code>…`) shows in the engine's words.
   *Passes if:* unit tests pin both forms' bodies, a `CURRENCY_NOT_HELD` on
   `balances.1.currency_code` and a `MONEY_AT_START_NOT_COVERED` on `balances.USD` each shown,
   with what was typed kept.
3. **The working screen, its lists and complete on the new shape (builder).** Opened on one
   currency, its head is that currency's entry in `balances`; the checklist, the "no batch" list
   (`u`) and their counts read `?account_id=` with `?currency_code=`; ticking re-reads the
   statement; `ending_balance_body` keys by `currency_code`; a complete's flagged lines and
   notes take each `not_covered` entry's beside the balances'; `BEGINNING_BALANCE_REQUIRED` and
   `MONEY_AT_START_NOT_COVERED` show in the engine's words.
   [statement.py](../../expense/bank_import/statement.py)'s `review_line_ids` reads
   `not_covered` too.
   *Passes if:* unit tests pin the lists' params, a tick that gains a blank dollar balance shown
   after the re-read, the ending-balance write's body, a `not_covered` flagged line counted in
   `⚑`, and each new refusal shown.
4. **A missing currency, a blank start, and `c` asking for them (builder; waits on questions 1
   and 2).** The list's cells and the working screen's head show a currency the statement does
   not cover and a blank starting balance as question 1 picks; `c` asks for the opened
   currency's missing balances as question 2 picks and saves them in one
   `PUT /statements/{id}`, sending only that currency (contract: PUT /v1/statements/{statement_id}, "`balances`").
   *Passes if:* unit tests pin each cell as picked, and `c` on a blank starting balance and on a
   currency the statement lacks each asking, saving one body, then asking to complete.
5. **The statement PDF upload on the account (builder).** statement.py reads each row's and
   balance's `currency_code` and the apply's `statement.not_covered`; flow.py's
   `statement_call` sends the pick's account;
   [statement_upload.py](../../expense/tui/screens/statement_upload.py) names lines and
   balances by currency and shows `CURRENCY_NOT_HELD`, `ACCOUNT_CURRENCY_NOT_ON_PAPER`,
   `MONEY_AT_START_NOT_COVERED` on `file` and `CONCURRENT_CHANGE` in the engine's words.
   *Passes if:* unit tests pin an upload's body sending the account's id, a card answer's two
   balance lines and a one-currency answer's one, the retired `HOLDER_ACCOUNT_NOT_ON_PAPER` gone,
   and each new refusal shown.
6. **The bank download on the account, and the holder reads gone (builder).**
   [flow.py](../../expense/bank_import/flow.py)'s `account_picks` makes one pick per live bank
   account, named by it, its currencies its own; the call sends its id; each row's and each
   day's currency come from their `currency_code`, a card file's day naming
   "<account> · <code>"; `CURRENCY_NOT_HELD` on `rows.<row>.account_id` shows in the engine's
   words. `fetch_holders`, `holder_accounts`, `card_name` and the holder builders go. Files:
   flow.py, [engine.py](../../expense/bank_import/engine.py),
   [bank_import.py](../../expense/tui/screens/bank_import.py), reads.py, helpers.py.
   *Passes if:* unit tests pin a two-currency account's one line, the call's body, a row's and a
   day's currency, and the refusal; nothing in the code or the tests names a holder.
7. **The sheet import on account names (builder; waits on question 3).**
   [engine.py](../../expense/import_/engine.py) sends `names.accounts` as `{name, account_id}`,
   one per name; the table reads each name's `currencies` and shows them as question 3 picks;
   `--create-names` sends `POST /accounts` with each missing name's `currencies`; a rename is
   keyed by the sheet's name, `--account-name SHEET_NAME=LEDGER_NAME`, the config's
   `sheet_account_names` keyed by name; `CURRENCY_NOT_HELD` on
   `names.accounts.<i>.account_id` shows in the engine's words. The per-currency account
   builder goes. Files: engine.py, [import_cmd.py](../../expense/commands/import_cmd.py),
   [config.py](../../expense/config.py), the sheet tests, commands.md.
   *Passes if:* unit tests pin the body, a two-currency name's create, the table as picked, a
   rename in the new form, and the refusal; the drift check passes whole.
8. **The saved renames and two names on one account (builder; waits on questions 4 and 5).**
   A saved rename keyed with a currency is read as question 4 picks, and two sheet names renamed
   onto one account as question 5 picks; commands.md says so.
   *Passes if:* unit tests pin a config holding `BCP:PEN` and `BCP:USD` as picked, and two names
   renamed onto one account as picked.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `e020782e3579d011` → `f82426fb0a099676` (`07475793a38b47b4`, `d5241e52676b19f9`,
  `2d7db5f914b565d9`, `b54580104fce4fde`, `394b3a9034b36d98`, `ba0f857bc43b95ce`,
  `02fb846290642261`, `4d57bb4f05ecc3b3`, `4329913878f62787`, `3d0afdaa03d87d5c`,
  `7aec8f6ed9928caf`, `f82426fb0a099676`), shared with the six other specs.
- **The engine's "Done when" checks to report on:**
  - "A statement is the account's, with a starting and ending balance per currency it covers,
    and the PDF upload closes it": on today's statement screens (one statement per account on
    one screen is spec 7's).
  - "A transaction names an account and a currency it holds; one in a currency the account does
    not hold is refused, nothing written, and the app shows why": on the bank download and the
    sheet import, with spec 1's writes.
  - "`GET /accounts` lists the Visa as one account holding PEN and USD, a balance for each, and
    no route or field the TUI uses names a holder": with spec 1, no route or field the app uses
    names a holder.
  - "No request in the TUI sends a `/holders` route, `POST /accounts/{id}/move`, `?holder_id=`
    or a per-currency id": with spec 1, for every request.
- **The asks it closes:** none. "An account holds its currencies: the holder becomes the
  account, and each account becomes one of its currencies" closes with spec 7.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
