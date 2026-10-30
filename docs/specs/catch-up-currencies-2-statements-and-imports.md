# The statement PDF upload and the two imports on an account and its currencies

Catches up to contract `f82426fb0a099676`, from `e020782e3579d011`: the engine's hand-off of
2026-10-29, "An account holds its currencies: every route names an account and a currency code;
holders are gone" — the part on the statement PDF upload, the bank download and the sheet
import. This is spec 2 of seven that share that range, run in this order:

1. part 1, the app's reads and writes (done on 2026-10-30): the
   app's reads and writes on an account and a currency code;
2. this one: the statement PDF upload, the bank download and the sheet import on the account;
3. [catch-up-currencies-3-live-suite-foundation.md](catch-up-currencies-3-live-suite-foundation.md):
   the live tests' shared helpers, and a statement's life, on the new model;
4. [catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md):
   the live tests of the upload, bank lines and the two kinds of account;
5. [catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md):
   an account's currencies proven live;
6. [catch-up-currencies-6-main-views.md](catch-up-currencies-6-main-views.md): the main views on
   the new model, from mockups you pick;
7. [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md): the
   Statements screens on the new model, an account's statement on one screen.

**Status: approved by the owner on 2026-10-30, not started; it runs after spec 1, whose fake
engine, account picks and "<account> · <code>" labels it uses.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

On 2026-10-29 the engine made each bank account and card one account holding its currencies,
and a statement **the account's**: one per account per month, with a starting and an ending
balance for each currency it covers (contract: "Statements", "Which currencies a statement covers").
Holders are gone, and so are the routes and names the imports used. So these break:

- the statement PDF upload and the bank download, and their list of accounts;
- `expense import sheet`, whose names table and renames are per name and currency.

This spec puts them back on the new model. As in spec 1, a currency reads "<account> · <code>"
where a currency's account was named. What else you see change:

- **The PDF upload shows a balance only for each currency the paper has something in**
  (contract: POST /v1/statements/import, "Which currencies the statement covers").
- **The account list of both doors has one line per account**, named by the account with its
  currencies, as a card's line reads today.
- **The sheet's account names are one per name**, mapped to one account, each row going to the
  currency in its own MONEDA (contract: POST /v1/transactions/import-sheet, "Names"). The names
  table lists each name's currencies in its CUR column, `PEN + USD`; `--account-name` drops its
  currency, `--account-name "BCP=Sueldo"`; your saved renames are read by their name alone, and
  two sheet names may go to one account ("What the owner settled").

The Statements screens (the list, the new-statement forms, the working screen, `c`) are not
here: [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md)
rebuilds them on the new model, so they stay as they are, and do not work against the engine,
until it is done ("What the owner settled").

## What it must do

1. **The statement PDF upload sends the account**, reads each row's and balance's currency from
   its `currency_code`, shows a balance for each currency the engine's answer holds and no
   other, and shows the new refusals in the engine's words
   (contract: POST /v1/statements/import, "Every currency the paper shows something in must be one the account holds")
   (contract: POST /v1/statements/import, "A currency of the account the paper does not print at all").
   The lines its close flags are counted from each balance's and each `not_covered` entry's
   (contract: POST /v1/statements/{statement_id}/complete, "`not_covered`").
2. **The bank download sends the account alone**: the account list both doors share has one
   line per live bank account, named by the account with its currencies, as a card's line reads
   today (`VISA Infinite Sapphire   PEN + USD`); each row goes to the currency in its own Moneda
   and shows it (contract: POST /v1/transactions/import, "Accounts"); a row in a currency the
   account lacks is refused in the engine's words, nothing written.
3. **The sheet import sends one entry per account name** with the account it maps to; the names
   table shows each name's currencies in its CUR column; `--create-names` creates one account per
   missing name with the currencies its rows use (contract: POST /v1/accounts, "Required");
   an account lacking a currency its name's rows use is refused in the engine's words;
   `--account-name SHEET_NAME=LEDGER_NAME` and the saved renames name a sheet account by its name
   alone, and two sheet names may be renamed onto one account ("What the owner settled").
4. **No request of the upload, the download or the sheet import sends a `/holders` route,
   `?holder_id=` or a per-currency id**, and the drift check's fixture check finds nothing in
   their builders; the Statements screens' builders, which still carry the holder, are spec 7's.

## How the owner knows it is done

On the practice engine, with the practice user's Visa holding soles and dollars and a code:

1. The engine's sample `card` PDF dropped for the Visa previews and closes the month, a balance
   shown for each currency the paper covers.
2. The account list of the PDF upload and of the bank download shows the Visa once,
   `VISA Infinite Sapphire   PEN + USD`.
3. A bank download for a two-currency account previews each row with its currency, and imports.
4. `expense import sheet` on a made-up sheet lists one row per account name with its currencies;
   `--create-names` creates one account per name holding those currencies; `--apply` imports.
5. The unit suite passes whole; the drift check reads `f82426fb0a099676` and its fixture check
   finds nothing outside the Statements screens' builders, which spec 7 moves.
   The live suite passes once specs 3 to 5 are done, apart from its citation test on the
   citations that still name holders or the Statements screens outside the live tests, which
   spec 7 fixes; none of them is on this spec's code.

## What the owner settled

- **A currency shows as its account's name and its code** (owner, 2026-10-29, the engine's
  hand-off "The owner's rulings").
- **The plan of the seven specs** (owner, 2026-10-29): `--account-name` and the saved renames
  lose the currency, and the sheet's `--create-names` makes one account per name with the
  currencies its rows use.
- **The Statements screens move to spec 7** (owner, 2026-10-30): spec 7 rebuilds the list, the
  new-statement forms, the working screen and `c`, so rebuilding today's here would be undone
  there. Until spec 7 is done they do not work against the engine; a month closes from its PDF,
  which this spec keeps working.
- **A saved rename is read by its name alone** (owner, 2026-10-30, question 4 A): `BCP:PEN` →
  `Sueldo Soles` reads as `BCP` → `Sueldo Soles`; two saved for one name that go to different
  ledger names stop the run before anything is written, naming both, until `--account-name` for
  that name replaces them.
- **Two sheet names may be renamed onto one account** (owner, 2026-10-30, question 5 A): both
  names' rows go to that account, each in its own currency; the engine decides what may share an
  account (contract: POST /v1/transactions/import-sheet, "Names").
- **The sheet's names table keeps its CUR column** (owner, 2026-10-30, question 3 A of
  [expense-world-sheet-names-currencies.html](../mockups/expense-world-sheet-names-currencies.html)):
  one row per account name, its currencies listed `PEN + USD`, as the bank download's list
  writes a card's.
- **A currency the paper does not cover shows nothing in the PDF preview** (owner, 2026-10-30,
  pick 1 B of
  [expense-world-statement-currency-picks.html](../mockups/expense-world-statement-currency-picks.html)):
  only the currencies the engine's answer holds balances for.

---

## Tasks

Approved by the owner on 2026-10-30, and rewritten at the owner's ask the same day. Each leaves
`pytest tests/unit` green. Each task fixes the `(contract: …)` citations and the
[tui.md](../tui.md), [runtime.md](../runtime.md) and [commands.md](../commands.md) lines of the
code it touches, and moves its tests onto spec 1's account builder. The statement builders in
[helpers.py](../../tests/unit/helpers.py) that the Statements screens' tests use stay as they
are until spec 7; the upload's tests build its answers in the shape the engine sends now.

From the acceptance check of 2026-10-30:

1. **The PDF upload's `STATEMENT_MONTH_TAKEN` row cites a rule the contract dropped (builder).**
   The row in [tui.md](../tui.md) "When the engine says no" (~1042) and the comment in
   [errors.py](../../expense/errors.py) (~207) cite `(contract: "Statements", "One statement per holder per month")`
   and say "another statement of its holder". *Passes if:* both say a month another statement
   of the account holds, and cite the part of the live contract that states it, checked with
   `Contract.from_openapi` and `broken_citations` from
   [test_contract_citations.py](../../tests/contract/test_contract_citations.py).

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `e020782e3579d011` → `f82426fb0a099676` (`07475793a38b47b4`, `d5241e52676b19f9`,
  `2d7db5f914b565d9`, `b54580104fce4fde`, `394b3a9034b36d98`, `ba0f857bc43b95ce`,
  `02fb846290642261`, `4d57bb4f05ecc3b3`, `4329913878f62787`, `3d0afdaa03d87d5c`,
  `7aec8f6ed9928caf`, `f82426fb0a099676`), shared with the six other specs.
- **The engine's "Done when" checks to report on:**
  - "A statement is the account's, with a starting and ending balance per currency it covers,
    and the PDF upload closes it": the PDF upload closes it; the statement screens are spec 7's.
  - "A transaction names an account and a currency it holds; one in a currency the account does
    not hold is refused, nothing written, and the app shows why": on the bank download and the
    sheet import, with spec 1's writes.
  - "No request in the TUI sends a `/holders` route, `POST /accounts/{id}/move`, `?holder_id=`
    or a per-currency id": for the upload, the download and the sheet import; the Statements
    screens' requests with spec 7.
- **The asks it closes:** none. "An account holds its currencies: the holder becomes the
  account, and each account becomes one of its currencies" closes with spec 7.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
