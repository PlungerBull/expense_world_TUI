# The typed surface

> What is typed: `expense` alone opens the TUI, and `expense import sheet` brings the owner's spreadsheet in. Everything else is done in the app ([decisions.md](decisions.md) "The TUI is the only surface"). This file holds the sheet import and the settings file; the app itself is [tui.md](tui.md).
>
> Engine contract (error shape, null-over-omission, idempotency, sign): (contract: "Base Conventions"), read live ([CLAUDE.md](../CLAUDE.md) "Key documentation") · Runtime behaviour: [runtime.md](runtime.md) · Open work: [todo.md](todo.md)

---

## The typed surface

| Typed | Does |
|---|---|
| `expense` | Opens the TUI ([tui.md](tui.md)). Needs an interactive terminal; clears the screen and scrollback, opens on the setup screen when there is no usable settings file, then checks today's exchange rate. |
| `expense import sheet <file.xlsx>` | The personal spreadsheet → the engine (below). |
| `expense --help` | Lists `import` (whose one command is `sheet`) and nothing else. |

`--verbose` / `-v` is the one root flag: it prints every HTTP request and response to stderr, Authorization redacted, for the app and the sheet import alike, and puts their bodies in the log ([runtime.md](runtime.md) "The log"). Any other word after `expense` is an unknown command (exit 2).

---

## Auth model

The key is one of the engine's long-lived Personal Access Tokens, prefixed `ewe_pat_`. The client treats it as an opaque Bearer token and does no client-side validation. A PAT is obtained out-of-band: the first one is minted by the operator, outside the API (contract: POST /v1/auth/pat). This client neither issues nor revokes PATs.

The HTTP client ([expense/http.py](../expense/http.py)) sends every call under `<engine_url>/v1`, but `GET /health`, the one unauthenticated call.

The settings file is `~/.expense-config` (chmod 600), or the path `EXPENSE_CONFIG` names. The TUI's setup screen creates it and System ▸ Config changes it ([runtime.md](runtime.md) "The settings file and a fresh start"):

| Field | Purpose |
|---|---|
| `engine_url` | Base URL of the engine (`http://127.0.0.1:8000`) |
| `token` | PAT (prefix `ewe_pat_`). Sent verbatim as `Authorization: Bearer <token>`. |
| `main_currency` | Mirrored from `/v1/auth/me` for formatting hints |
| `sheet_account_names` | The ledger name per sheet account, keyed by the sheet's name, as `--account-name` saves it ("`expense import sheet`" below) |

---

## `expense import sheet`

`import sheet <file.xlsx> [--create-names | --apply] [--account-name SHEET_NAME=LEDGER_NAME ...] [--json]` brings the personal sheet into the engine. The app sends the file whole, in base64, and reads no cell of it; the engine reads the workbook, matches every row against the ledger and writes everything or nothing (contract: POST /v1/transactions/import-sheet). A sheet with bad rows is refused whole on any step, nothing written or created (contract: POST /v1/transactions/import-sheet, "Rejected up front with `422`"). The sheet's layout is the engine's (contract: POST /v1/transactions/import-sheet, "The sheet"); sending the same sheet again matches every row and writes nothing (contract: POST /v1/transactions/import-sheet, "Matching").

**Three steps, because every name needs an id first.** The engine never looks a name up and never creates one: it answers counts only once a table gives every account, category and hashtag its id (contract: POST /v1/transactions/import-sheet, "Names"). Each step first sends the sheet as a dry run without a table, so a refused sheet stops there.

1. **Dry run** (no flag) writes nothing: it lists every name and where it goes, then the engine's counts once every name exists.
2. **`--create-names`** creates the missing categories and hashtags and imports nothing (contract: POST /v1/categories) (contract: POST /v1/hashtags). It never goes with `--apply`.
3. **`--apply`** imports with the table; it is refused, nothing written, while a name or an account is missing.

**The import makes no account.** A sheet account with no account is made in the app; `--account-name` then gives it the sheet's name.

**`--account-name "BCP=Sueldo Soles"`** (repeatable) puts the sheet's `BCP` rows on the ledger account of that name. It is saved to `sheet_account_names` in the settings file, dry run included, and applied on every later run. Two sheet names may go to one ledger account; the engine decides what may share one (contract: POST /v1/transactions/import-sheet, "Names").

**Exit codes:** 0 for a dry run, a create step and an apply that went through; 1 when the file cannot be read, the engine refused the sheet or a write, or `--apply` met a missing name or account; 2 for a usage error; 3 for a missing or unreadable settings file; 6 when the engine cannot be reached ([decisions.md](decisions.md) "Connection errors get exit code 6, off the click collision on 2").

What it prints (tables, counts, refused rows, the rename rules and their usage errors, the `--json` shapes) is said by [import_cmd.py](../expense/commands/import_cmd.py) and [engine.py](../expense/import_/engine.py), and pinned by their tests. Refused rows are grouped as the LOG bar's are ([runtime.md](runtime.md) "How refused rows read").

### Sanctioned exceptions

Deliberate, reviewed deviations — do not re-flag in future reviews:

- **`import sheet --create-names --json`** and **`import sheet --apply --json` with a name missing** are client-composed (shapes: the module docstring of [`import_cmd.py`](../expense/commands/import_cmd.py)): the create step is many engine calls, printed as the engine's answer to each, and the refused apply sends nothing, so its envelope is the app's.

---

## Output conventions

- **Errors** — the engine's `{ error: { code, message, fields, reasons, details } }` rendered as (reason codes are not shown):
  ```
  Error: VALIDATION_ERROR — Amount must not be zero.
    amount_cents: Must not be zero.
  ```
  The engine's words alone, here and on every refused row: the import adds no line of the
  TUI's (no hint, no key to press, no screen to open) — `errors.engine_text` in
  [expense/errors.py](../expense/errors.py); its own lines are the refused rows' head and
  `Fix the sheet and run it again.` (`_refused_lines` in import_cmd.py). The lines the app adds
  under a refusal are the TUI's ([tui.md](tui.md) "When the engine says no").
- **`--json`** — two-space indent, keys in insertion order, UTF-8 written as UTF-8 (`Café`, not `Caf\u00e9`). An engine error under `--json` is the engine's body verbatim. One serialiser, [expense/jsonout.py](../expense/jsonout.py), for the engine's answer, the names created and the error envelope.
