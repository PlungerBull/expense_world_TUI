# The typed surface — Spec

> What is still typed: `expense` alone opens the TUI, and `expense import sheet` brings the owner's spreadsheet in. Everything else is done in the app ([decisions.md](decisions.md) "The TUI is the only surface"). This file holds the sheet import and the settings file; the app itself is [tui.md](tui.md).
>
> Engine contract (error shape, null-over-omission, idempotency, sign): (contract: "Base Conventions"), read live ([CLAUDE.md](../CLAUDE.md) "Key documentation") · Runtime behaviour: [runtime.md](runtime.md) · Open work: [todo.md](todo.md)

---

## The typed surface

| Typed | Does |
|---|---|
| `expense` | Opens the TUI ([tui.md](tui.md)). Needs an interactive terminal; clears the screen and scrollback, opens on the setup screen when there is no usable settings file, then checks today's exchange rate. |
| `expense import sheet <file.xlsx>` | The personal spreadsheet → the engine (below). |
| `expense --help` | Lists `import` (whose one command is `sheet`) and nothing else. |

`--verbose` / `-v` is the one root flag: it prints every HTTP request and response to stderr, Authorization redacted, for the app and the sheet import alike. Any other word after `expense` is an unknown command (exit 2).

---

## Auth model

The engine issues long-lived Personal Access Tokens prefixed `ewe_pat_`; anything else falls through to JWT verification. The client treats the token as an opaque Bearer token and does no client-side validation.

A PAT is obtained out-of-band: the first one is minted by the operator, outside the API (contract: POST /v1/auth/pat). This client neither issues nor revokes PATs.

All engine endpoints except `GET /health` are mounted under `/v1/`. The HTTP client's base path is `<engine_url>/v1`, with `/health` the one unauthenticated, un-prefixed exception.

The settings file is `~/.expense-config` (chmod 600), or the path `EXPENSE_CONFIG` names. The TUI's setup screen creates it and System ▸ Config changes it ([runtime.md](runtime.md) "The settings file and a fresh start"):

| Field | Purpose |
|---|---|
| `engine_url` | Base URL of the engine (`http://127.0.0.1:8000`) |
| `token` | PAT (prefix `ewe_pat_`). Sent verbatim as `Authorization: Bearer <token>`. |
| `main_currency` | Mirrored from `/v1/auth/me` for formatting hints |
| `sheet_account_names` | The ledger name per sheet account, keyed by the sheet's name (`expense import sheet --account-name`); a saved key ending in `:` and an upper-case code (`BCP:PEN`) is read as `BCP` |

---

## `expense import sheet`

- `import sheet <file.xlsx> [--create-names | --apply] [--account-name SHEET_NAME=LEDGER_NAME ...] [--json]` — the personal sheet → the engine. The app sends the file whole, in base64, as the import door sends a bank download, and reads no cell of it: the engine reads the workbook, matches every row against the ledger and writes everything or nothing (contract: POST /v1/transactions/import-sheet). Package: [expense/import_/](../expense/import_/), every step in [engine.py](../expense/import_/engine.py). Every step reads the settings file once, before the file, and needs it.
- **The sheet is the engine's layout:** a sheet named `data`, the twelve headers from `description` to `COD_EECC` in order, a row numbered as the spreadsheet numbers it (contract: POST /v1/transactions/import-sheet, "The sheet"). Rows sharing a `COD_EECC` are the parts of one split transaction, on one bank line (contract: POST /v1/transactions/import-sheet, "Splits"); a row whose `CATEGORY` reads exactly `SALDO INICIAL` is its account's opening balance as the engine decides it (contract: POST /v1/transactions/import-sheet, "Opening balances"). To the app `SALDO INICIAL` is a name like any other: listed, created by the create step, and, when only opening balances use it, an unused category you may delete.
- **Every name needs an id first.** The engine never looks a name up and never creates one; for each account (a name, which must hold every currency its rows are in), category and hashtag the sheet uses it proposes yours of that name, and it answers outcomes and counts only with a table giving every name its id (contract: POST /v1/transactions/import-sheet, "Names"). So the import is three steps of one command, each first sending the sheet as a dry run without a table: a refused sheet stops every step there, nothing created. The steps, as screens 1 to 5 of [expense-world-sheet-import-engine.html](mockups/expense-world-sheet-import-engine.html) draw them:
  1. **The dry run** (no flag) writes nothing. It prints one table per kind, `Accounts`, `Categories` and `Hashtags`, each name (one row per name) with its rows and where it goes, an account's table adding a `CUR` column that lists the currencies its rows are in, in the engine's order (`PEN + USD`; [expense-world-sheet-names-currencies.html](mockups/expense-world-sheet-names-currencies.html), option A): `yours` (the engine's proposal, or your account of a rename) or `missing`; a renamed account shows its ledger name first (`Sueldo Soles  missing`). Each table's columns are as wide as its longest name. While a name is missing it shows no counts and names the step that creates them, the same file as typed (quoted when it needs it):

     ```
     No counts yet: the engine counts once every name exists.

     9 names don't exist yet. Create them with:
       expense import sheet libro.xlsx --create-names
     Dry run — nothing written.
     ```

     Once every name exists, it sends the sheet again as a dry run with the table and prints the engine's counts under the tables (the split transactions with the sheet rows they hold, `split transactions 0 (0 rows)` when there are none), then the rows of zero and the rows on a closed statement's day, each line only when there are any:

     ```
     Rows: 1,961 · new 1,954 · matched 0 · sealed 0 · skipped 7
     Opening balances 4 · split transactions 3 (8 rows)

     Skipped, amount zero: rows 14, 90, 311, 1201, 1202, 1555, 1960
     Sealed, on a closed statement's day: rows 40, 41

     Dry run — nothing written. Run again with --apply to import.
     ```

  2. **`--create-names`** creates every missing account, category and hashtag through its own route and imports nothing: an account under its ledger name (its rename, else the sheet's name) holding the currencies its rows use, in the engine's order (contract: POST /v1/accounts, "Required"), a category or hashtag under the sheet's name with no colour, so it takes the engine's default (contract: POST /v1/categories) (contract: POST /v1/hashtags). Two of the sheet's names the engine holds as one (`Travel` and `travel`, compared trimmed and in any letter case) (contract: POST /v1/accounts, "Validation") (contract: POST /v1/transactions/import-sheet, "Names") are created once; two account names so held are one account holding the currencies of both names' rows, in the order the first name's rows list them and then those only the second adds. It prints `Created 4 accounts, 3 categories, 2 hashtags.` (a kind with none left out, one in the singular) and `Nothing imported. Run the dry run again to see the counts.`; run again, `Created no names: every one is yours.` A create the engine refuses stops the step: the names created before it are printed first (`Created 1 account.`), then the refusal as every engine error prints; under `--json` both are one document ("Sanctioned exceptions" below). With `--apply` it is a usage error (exit 2), since it imports nothing: `--create-names creates names and imports nothing, so it never goes with --apply.`
  3. **`--apply`** imports, sending the table with the sheet; the engine's answer is what happened. While a name is missing it is refused and sends nothing more:

     ```
     Not imported — nothing written.
     9 names don't exist yet. Create them with:
       expense import sheet libro.xlsx --create-names
     then run the dry run to see the counts.
     ```

     Otherwise it prints `Written: new 1,954 · matched 0 · sealed 0 · skipped 7`, the opening balances and split transactions line as the dry run prints it (`Opening balances 4 · split transactions 3 (8 rows)`), and the rows of zero and on a closed day as the dry run lists them. The same sheet sent again matches every row and writes nothing (contract: POST /v1/transactions/import-sheet, "Matching"); when rows matched and none is new or sealed it prints `Nothing new: every row is already in the ledger.` in place of the lists; a sheet whose rows are all zero gets its list instead.
- **A sheet with bad rows** is refused whole, on any of the three steps, and nothing is written or created (contract: POST /v1/transactions/import-sheet, "Rejected up front with `422`"). The `422` `VALIDATION_ERROR` whose every key is a row's (`rows.<row>…`), the refusal the sheet itself causes, prints every refused row in the engine's words, rows refused alike sharing one line through the same grouping as the LOG bar's ([runtime.md](runtime.md) "How refused rows read"): words that begin with their row (`Row 77: …`) read whole for one row, and once, without the row, before every row refused alike; any other row key reads `field: words`, then its rows. `N` counts the rows:

  ```
  Refused — nothing written. 4 rows:
    Row 77: FECHA is empty.
    Row 120: MONTO is not a whole number of cents.
    The day is after today. rows 1958, 1959

  Fix the sheet and run it again.
  ```

  A file refused whole (contract: POST /v1/transactions/import-sheet, "The file refused whole"), a refused table entry (an archived account the engine proposed, `INVALID_REFERENCE`) and every refusal fixing the sheet does not clear print as every engine error ("Output conventions" below), never with `Fix the sheet and run it again.`: a `409` `CONCURRENT_CHANGE` on `rows.<row>`, which clears by sending the sheet again (contract: POST /v1/transactions/import-sheet, "Concurrency"), a `409` `OPENING_BALANCE_EXISTS` (contract: POST /v1/transactions/import-sheet, "Opening balances") and the `422` `LIMIT_REACHED` once the line codes are used up (contract: POST /v1/transactions/import-sheet, "On apply").
- **Renaming an account.** `--account-name "BCP=Sueldo Soles"` (repeatable) puts the sheet's `BCP` rows on a ledger account named `Sueldo Soles`: yours of that name (archived accounts and people included), else a missing one the create step creates under it, holding the currencies `BCP`'s rows use. The sheet name matches ignoring case and leading or trailing spaces, and the ledger name is everything after the first `=`. **It is remembered:** once checked against the sheet's names, each rename is saved to `sheet_account_names` in the config (dry run included), keyed by the sheet's name, and applied on every later run; passing the flag again for the same account replaces every saved key of that name. A saved key ending in `:` and an upper-case code (`BCP:PEN`) is read as its name written with a currency, so as `BCP`; a `--account-name` name is read the same way, so a sheet account whose own name ends in `:` and three capital letters (`Caja:USD`) cannot be renamed; the keys of one name (`BCP:PEN`, `BCP:USD`, `BCP`) that go to one ledger name are one rename, and a key no sheet name matches renames nothing. **Two of the sheet's names may be renamed onto one ledger account:** both are sent with that account's id and the engine decides what may share an account (contract: POST /v1/transactions/import-sheet, "Names"). A malformed value is a usage error before anything is sent; an account the sheet does not have, or a sheet name whose saved keys go to different ledger names, is a usage error once the engine has listed the sheet's names: nothing is created, imported or saved (exit 2), and the second prints `Your saved renames send "BCP" to both "Sueldo Soles" and "Sueldo Dólares". Choose one with --account-name "BCP=<ledger name>".` until the flag for that name replaces the keys. An account that does not hold a currency its rows are in is refused in the table as the engine words it (`CURRENCY_NOT_HELD` on `names.accounts.<i>.account_id`, contract: POST /v1/transactions/import-sheet, "Names"), printed as every engine error ("Output conventions" below).
- **`--json`** prints the engine's answer as it sent it: the dry run's last answer (with the table once every name exists) and the apply's. `--create-names --json` prints `{"created": {"accounts": [...], "categories": [...], "hashtags": [...]}}`, the engine's answer to each create by kind, and, stopped part way, the `error` that stopped it beside them. A refusal is the engine's body; `--apply --json` while a name is missing is `{"error": {"code": "NAMES_MISSING", "message": "Not imported — nothing written. 9 names don't exist yet.", "fields": null, "reasons": null}}`.
- **Exit codes:** 0 for a dry run, a create step and an apply that went through; 1 when the file cannot be read, the engine refused the sheet or a write, or `--apply` met a missing name; 2 for a usage error; 3 for a missing or unreadable settings file; 6 when the engine cannot be reached ([decisions.md](decisions.md) "Connection errors get exit code 6, off the click collision on 2").

### Sanctioned exceptions

Deliberate, reviewed deviations — do not re-flag in future reviews:

- **`import sheet --create-names --json`** and **`import sheet --apply --json` with a name missing** — client-composed: the create step is many engine calls, printed as the engine's answer to each under `created`, and the refused apply sends nothing, so its `NAMES_MISSING` envelope is the app's, in the engine's envelope shape (`errors.error_envelope`). A create step stopped part way prints both, `{"created": {"accounts": [...], "categories": [...], "hashtags": [...]}, "error": {...}}`: the engine's answer to each name created before the stop, then the `error` of what stopped it, the engine's own for a refusal, the app's envelope for the engine out of reach (exit 6). [`expense/commands/import_cmd.py`]

---

## Output conventions

- **Errors** — the engine's `{ error: { code, message, fields, reasons } }` rendered as (reason codes are not shown):
  ```
  Error: VALIDATION_ERROR — Amount must not be zero.
    amount_cents: Must not be zero.
  ```
  The engine's words alone, here and on every refused row: the import adds no line of the
  TUI's (no hint, no key to press, no screen to open) — `errors.engine_text` in
  [expense/errors.py](../expense/errors.py); its own lines are the refused rows' head and
  `Fix the sheet and run it again.` ("A sheet with bad rows" above). The lines the app adds
  under a refusal are the TUI's ([tui.md](tui.md) "When the engine says no").
- **`--json`** — two-space indent, keys in insertion order, UTF-8 written as UTF-8 (`Café`, not `Café`). An engine error under `--json` is the engine's body verbatim. One serialiser, [expense/jsonout.py](../expense/jsonout.py), for the engine's answer, the names created and the error envelope.
