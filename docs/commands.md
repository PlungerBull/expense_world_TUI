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
| `sheet_account_names` | The ledger name per sheet account leg, keyed `SHEET_NAME:CUR` (`expense import sheet --account-name`) |

---

## `expense import sheet`

- `import sheet <file.xlsx> [--apply] [--chunk-size N] [--account-name SHEET_NAME:CUR=LEDGER_NAME ...] [--json]` — the personal sheet → engine. Reads `.xlsx` via `openpyxl`, one of the app's core dependencies. Parses, resolves names to ids, plans, then writes through `POST /transactions/batch` ([runtime.md](runtime.md) "Write semantics"). A dry run unless `--apply` is passed. Package: [expense/import_/](../expense/import_/).
- **Opening balances:** rows marked `SALDO INICIAL` (case/whitespace-insensitive) in the title or category column go to `POST /v1/accounts/{id}/opening-balance` instead of the batch; their category/hashtag cells are discarded. One per (account, currency): extra rows are skipped as `duplicate-opening` (first line wins) and listed in the dry run. At apply time a refused opening balance counts as already present when it is a seed an earlier run wrote: refused only because its own `transaction_id` is taken (`ID_EXISTS`), which a seed sent again answers before any other refusal (contract: POST /v1/accounts/{account_id}/opening-balance). Any other refusal, a different opening balance on the account (`OPENING_BALANCE_EXISTS`) included, is a failure, printed in the engine's words.
- **`COD_EECC` is the statement line; rows sharing one are one split transaction.** The optional `COD_EECC` column holds the bank statement line a row was checked against (`SIG-202603-029`). Each row sends it, trimmed, as its `statement_line`; a blank cell sends none, and a sheet without the column imports every row as a movement of its own with no statement line. Rows sharing a `COD_EECC` go as the items of one `line_group` in one `POST /transactions/batch`, so the engine makes them the parts of one bank line, one movement sharing one line code and one statement line (contract: POST /v1/transactions/batch, "Line groups"); a row whose code no other row has is a movement of its own carrying it. A batch chunk never cuts a group: a group that does not fit in a chunk starts the next one, and one longer than `--chunk-size` goes whole, as one bigger request.
  - **A group goes whole or not at all.** It is skipped whole when its rows differ on account (name and currency), date or title, which the engine refuses in a group (same citation), and when the parse skipped one of its rows for any reason but a zero amount (a bad date, an unknown currency, a missing category, …), so the movement never lands without a part. Its other rows count as `split-mismatch` on the `Skipped N row(s) — …` line, and a line under it says why, naming the code: one per field that differs, giving the group's first row and each row that differs from it (`SIG-202603-029: line 3120 is 2026-03-14, line 3122 is 2026-03-15.`; an account reads `BCP [PEN]`, a title in quotes), or one for unreadable rows (`SIG-202603-029: line 3122 can't be read, so lines 3120, 3121 wait for it.`). The rest imports; once the sheet is fixed, a re-run brings the whole group in. A zero-amount part is only dropped, and the rest of its group goes; a group left with one row goes as that row alone, carrying its statement line. A part not sent because a resource it needs was not created keeps its whole group back.
  - **What it prints.** The dry run's first line counts the movements the rows make (`Parsed 4188 transactions to import, as 4167 movements.`), and a line under the skipped rows counts the split transactions (`9 split transactions (30 rows) come in as one movement each.`, or `1 split transaction (3 rows) comes in as one movement.`; no line when there is none). `--apply` prints the whole `Skipped N row(s) — …` block too, every reason included (`zero-amount` as well), with its lines under it, before it writes. `--json` carries `movements`, `split_transactions`, `split_rows` and `split_mismatches` (those lines as text), and each skipped row's code as its `detail`; the `--apply` JSON carries `skipped` and `split_mismatches` too.
  - **What failed** prints under `Failures (N rows):`, one line per kind of failure: what went wrong, then the sheet lines it hit, `rows 3, 5, 7, 11` for several or `row 77` for one; the rest of a refused chunk goes again ([runtime.md](runtime.md) "Bulk writes"). Screens 1 A and 3 A in [expense-world-grouped-refusals.html](mockups/expense-world-grouped-refusals.html):

    ```
    Transactions: created 4153, already-present 0, failed 12
    Failures (12 rows):
      statement_line: Must not be a statement line another bank line already has. rows 3, 5, 7, 11
      date: Must not be null. row 77
      Part of a split transaction refused for another row. rows 4, 12
      Not sent: category 'NEW' was not created. rows 2, 9, 14, 30
      Part of a split transaction not sent for another row. row 31
    ```

    `N` counts the transaction and opening-balance rows that failed.
    - **A row the engine refuses** shows each refused field's name, as the engine keys it with the row's place in the request taken off, then the engine's words for it (`errors.row_words`); a row refused on two fields joins the pairs with ` · ` (`amount_cents: Must not be zero. · date: Must not be null.`), and a refusal naming no field shows its message. Rows refused alike share one line, wherever they were sent: alike is the same code, fields and reasons as the row reads them (`BatchFailure.kind` in [batch_write.py](../expense/batch_write.py)), never the top-level message, which counts the items a send named. The other rows of a split transaction the engine refused one part of share the app's line `Part of a split transaction refused for another row.`.
    - **A row held back** because a resource it needs was not created shares one line per resource, `Not sent: category 'NEW' was not created.` (an account or a hashtag the same way). A split transaction goes whole or not at all, so its other rows share `Part of a split transaction not sent for another row.`.
    - **Lines of their own**, never joined, their words as they stand: a refusal naming no row (`FORBIDDEN — nope rows 2, 3`, its rows after its first line and its field lines under it), an opening balance not sent or refused (`sheet line 9 (opening balance): CODE — message`), a stop, and the line naming the sheet lines never sent.
    - **`--json`** keeps one entry per failure, rows not grouped: `chunk` (`-1` before or beside the batch), `lines` (its sheet lines), `words` (as the line prints them) and `detail` (the engine's whole answer, `CODE — message` and one `key: words` line per field; empty for a line the app writes).

    A row whose statement line a live line in the ledger already holds — an edited row, whose content and so its id changed — is refused `STATEMENT_LINE_EXISTS`, on the group's first part for a split transaction, and every part fails with it; a row sent again unchanged is already there, never refused. `DUPLICATE_IN_REQUEST` and `LINE_GROUP_FIELDS_DIFFER` on `statement_line` would print the same way, against the rows named, but the import never draws them: rows sharing a code, trimmed and compared case-sensitively as the engine compares them, go as one group, and a group's parts carry one account, date, title and statement line (contract: POST /v1/transactions/batch, "Line groups").
  - **`LIMIT_REACHED` (`LINE_CODES_EXHAUSTED`) ends the run**: every line code has been given, so nothing more is sent. At the batch, the row it names (and its split transaction's other parts) fails against its sheet line, in the engine's words, and one line names the sheet lines never sent, in runs that skip every line already settled: `sheet lines 5-6, 9-4188 were not sent` (`sheet line 5 was not sent` for one); a connection lost mid-run names them the same way, after the error; the summary counts the rows not sent as failed, and the exit code is 1. At an opening balance it prints as `SETTINGS_MISSING` does, `Error:` and the engine's words alone, and no transaction is sent.
  - Opening-balance rows send no statement line: the opening-balance endpoint takes none (contract: POST /v1/accounts/{account_id}/opening-balance).
- **Categories and hashtags match by name** (ignoring case and leading or trailing spaces); one the ledger lacks is created at apply time with just its name. A created category is sent no colour, so it takes the engine's default (contract: POST /v1/categories).
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
