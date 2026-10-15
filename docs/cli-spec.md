# The typed surface — Spec

> What is still typed: `expense` alone opens the TUI, and `expense import sheet` brings the owner's spreadsheet in. Everything else is done in the app ([decisions.md](decisions.md) "The TUI is the only surface"). This file holds the sheet import and the settings file; the app itself is [tui.md](tui.md).
>
> Engine contract (error shape, null-over-omission, idempotency, sign): (contract: "Base Conventions"), read live ([CLAUDE.md](../CLAUDE.md) "Key documentation") · Runtime behaviour: [cli-runtime.md](cli-runtime.md) · Open work: [todo.md](todo.md)

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

The settings file is `~/.expense-config` (chmod 600), or the path `EXPENSE_CONFIG` names. The TUI's setup screen creates it and System ▸ Config changes it ([cli-runtime.md](cli-runtime.md) "The settings file and a fresh start"):

| Field | Purpose |
|---|---|
| `engine_url` | Base URL of the engine (`http://127.0.0.1:8000`) |
| `token` | PAT (prefix `ewe_pat_`). Sent verbatim as `Authorization: Bearer <token>`. |
| `main_currency` | Mirrored from `/v1/auth/me` for formatting hints |
| `sheet_account_names` | The ledger name per sheet account leg, keyed `SHEET_NAME:CUR` (`expense import sheet --account-name`) |

---

## `expense import sheet`

- `import sheet <file.xlsx> [--apply] [--chunk-size N] [--account-name SHEET_NAME:CUR=LEDGER_NAME ...] [--json]` — the personal sheet → engine. Reads `.xlsx` via `openpyxl`, one of the app's core dependencies. Parses, resolves names to ids, plans, then writes through `POST /transactions/batch` ([cli-runtime.md](cli-runtime.md) "Write semantics"). A dry run unless `--apply` is passed. Package: [expense/import_/](../expense/import_/).
- **Opening balances:** rows marked `SALDO INICIAL` (case/whitespace-insensitive) in the title or category column go to `POST /v1/accounts/{id}/opening-balance` instead of the batch; their category/hashtag cells are discarded. One per (account, currency): extra rows are skipped as `duplicate-opening` (first line wins) and listed in the dry run. At apply time a refused opening balance counts as already present when it is a seed an earlier run wrote: refused because its own `transaction_id` is taken (`ID_EXISTS`), or because the account already has one (`OPENING_BALANCE_EXISTS`, what a re-sent seed draws) and the account's `opening_balance_transaction_id`, read with `GET /v1/accounts/{id}`, is that same id (contract: "Bank Accounts", "Opening balance"). Any other refusal, a different opening balance on the account, or a read that fails is a failure, printed in the engine's words.
- **Sheet and column matching is tolerant.** The worksheet name (`Data`) matches ignoring case and leading or trailing spaces. Columns match by header name, each field accepting several spellings — the alias table is [expense/import_/mapping.py](../expense/import_/mapping.py) `FIELD_HEADERS`; no label may serve two fields (guard: `test_header_aliases_are_unambiguous`).
- **Multi-currency account names split.** A `CUENTA` name used under two currencies becomes two accounts, each renamed with its currency (`BCP Oro` → `BCP Oro PEN` + `BCP Oro USD`). A name used under one currency passes through verbatim; a name already ending in its currency is not doubled. Rows resolve by the raw sheet name, so re-runs stay idempotent.
- **Renaming an account leg.** `--account-name "BCP:PEN=Sueldo Soles"` (repeatable) writes the sheet's `BCP` rows in PEN, and its opening balance, to a ledger account named `Sueldo Soles` instead of the derived name; other legs keep theirs (`BCP USD`). The sheet name matches ignoring case and leading or trailing spaces, the currency is upper-cased, and the ledger name is everything after the first `=`. **It is remembered:** each rename is saved to `sheet_account_names` in the config (dry run included) and applied on every later run, so a re-run without the flag reuses `Sueldo Soles` instead of creating `BCP PEN`; passing the flag again for the same leg replaces the saved name. With no config file yet the rename applies to that run only. The dry run shows a renamed leg as `Sueldo Soles [PEN]  (from "BCP")`; `--json` carries it as `name` + `source_name`. A malformed value, a leg the sheet does not have, or a rename that lands two sheet legs on one ledger account (same name and currency) is a usage error (exit 2): nothing is written and nothing saved.
- **Exit codes:** 0 for a dry run, and for an apply where no transaction row or resource create failed; 1 when one did, when the file cannot be read, or when the engine refused the run; 3 for a missing or unreadable settings file; 6 when the engine cannot be reached ([decisions.md](decisions.md) "Connection errors get exit code 6, off the click collision on 2").

### Sanctioned exceptions

Deliberate, reviewed deviations — do not re-flag in future reviews:

- **`import sheet --json`** — emits a client-composed plan/result summary. The import is a composite of many engine calls (resolve, create, batch) with no single engine response to pass through. [`expense/commands/import_cmd.py`]

---

## Output conventions

- **Errors** — the engine's `{ error: { code, message, fields, reasons } }` rendered as (reason codes are not shown):
  ```
  Error: VALIDATION_ERROR — Amount must not be zero.
    amount_cents: Must not be zero.
  ```
  The engine's words alone, here and on every refused row or resource the report lists: the
  import adds no line of its own (no hint, no key to press, no screen to open) —
  `errors.engine_text` in [expense/errors.py](../expense/errors.py). The lines the app adds
  under a refusal are the TUI's ([tui.md](tui.md) "When the engine says no").
- **`--json`** — two-space indent, keys in insertion order, UTF-8 written as UTF-8 (`Café`, not `Café`). An engine error under `--json` is the engine's body verbatim. One serialiser, [expense/jsonout.py](../expense/jsonout.py), for the plan, the result and the error envelope.
