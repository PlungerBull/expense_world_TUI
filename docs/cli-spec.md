# Expense CLI — Spec

> The flat command surface of the Hands: a Python (Typer) CLI where every command is a thin wrapper around `expense_world_engine` endpoints — no business logic lives in the CLI.
>
> Engine contract (error shape, null-over-omission, idempotency, sign): (contract: "Base Conventions"), read live ([CLAUDE.md](../CLAUDE.md) "Key documentation") · Runtime behaviour: [cli-runtime.md](cli-runtime.md) · The TUI: [tui.md](tui.md) · Open work: [todo.md](todo.md)

---

## Principles

- Every command is a thin wrapper around one or more engine API calls. No business logic in the CLI.
- Output is human-readable by default. Every read command supports `--json` for machine-readable output.
- The `debit_as_negative` convention is used end-to-end (negative = expense, positive = income), at input parsing and output rendering.
- Every write carries an `X-Idempotency-Key`, re-sent unchanged on a bounded retry ([cli-runtime.md](cli-runtime.md) "Write semantics").
- Engine errors surface intact: human mode may prettify, `--json` passes through verbatim — never swallow, never reformat lossily. (Deviations: Sanctioned exceptions below.)
- Destructive operations (delete, revert) prompt for confirmation unless `--yes` / `-y` is passed. A delete is final from every client ([cli-runtime.md](cli-runtime.md) "Read semantics"). Archive/unarchive are prompt-free — reversible toggles, not destruction.
- Archive = retired-but-real (contract: POST /v1/accounts/{account_id}/archive), delete = mistake/scrubbed (contract: "Base Conventions", "Deleted is deleted").

### Sanctioned exceptions

Deliberate, reviewed deviations from the principles above — do not re-flag in future reviews:

- **`accounts update --currency-code`** — exists solely to be rejected client-side with honest help text; currency is immutable after creation (the engine would 422 anyway). Fail-fast UX, not business logic. [`expense/commands/accounts_cmd.py`]
- **`import sheet --json`** — emits a client-composed plan/result summary. The import is a composite of many engine calls (resolve, create, batch) with no single engine response to pass through. [`expense/commands/import_cmd.py`]
- **`log --dry-run --json`** — emits the *parse* of a typed line, not an engine body: where the row would go, why, the payload that would be posted, and a span per token. There is no engine call to pass through; the point is to see what the grammar did before one happens. Without `--dry-run`, `log --json` is a verbatim engine body. [`expense/commands/log_cmd.py`]

---

## Auth model

The engine issues long-lived Personal Access Tokens prefixed `ewe_pat_`; anything else falls through to JWT verification. The CLI treats the token as an opaque Bearer token and does no client-side validation.

A PAT is obtained out-of-band: the first one is minted by the operator, outside the API (contract: POST /v1/auth/pat). No CLI command issues or revokes PATs.

All engine endpoints except `GET /health` are mounted under `/v1/`. The HTTP client's base path is `<engine_url>/v1`, with `/health` the one unauthenticated, un-prefixed exception.

Config lives in `~/.expense-config` (chmod 600):

| Field | Purpose |
|---|---|
| `engine_url` | Base URL of the engine (`http://127.0.0.1:8000`) |
| `token` | PAT (prefix `ewe_pat_`). Sent verbatim as `Authorization: Bearer <token>`. |
| `main_currency` | Mirrored from `/v1/auth/me` for formatting hints |
| `sheet_account_names` | The ledger name per sheet account leg, keyed `SHEET_NAME:CUR` (`expense import sheet --account-name`) |

---

## Command groups

### `expense config` *(CLI-local — not an engine feature)*
- `config set [--token <t>] [--engine-url <u>] [--main-currency <code>]` — `--main-currency` caches the value for formatting; `auth me` normally sets it for you.
- `config get [--show-token] [--json]`
- `config clear`

### `expense auth`
- `auth bootstrap` → `POST /v1/auth/bootstrap` (first-login upsert, idempotent). `--display-name` and `--timezone` are honored only on the first call; later calls only bump `last_login_at`. The display name is sent exactly as typed, here, on `auth profile` and in the TUI's first-time setup: the engine trims it and refuses an empty or whitespace-only one with a 422 (`display_name`, reason `EMPTY`), writing nothing (contract: POST /v1/auth/bootstrap) (contract: PUT /v1/auth/profile).
- `auth me` (alias: `whoami`) → `GET /v1/auth/me`
- `auth profile --display-name <n>` → `PUT /v1/auth/profile`. Re-bootstrap never overwrites a profile-set name.
- `auth settings --display-timezone <tz>` → `PUT /v1/auth/settings` — the only mutable setting. The home currency is read-only.

### `expense accounts`
- `accounts list [--include-archived] [--include-people]`
- `accounts get <id>`
- `accounts create`, `update`, `delete`
- `accounts archive <id>`, `accounts unarchive <id>`
- `accounts create-person --name <n> --currency-code <c> [--color] [--sort-order]` → `POST /v1/people`. A person *is* an account with `is_person = true`; money lent or borrowed is an ordinary transaction against her, and the computed balance **is** the debt (positive = they owe you). Creation is the only `/people` route: rename/recolor/archive/unarchive/delete/get are the ordinary `accounts` commands, and listing is `accounts list --include-people` plus the dashboard. There is no `expense people` group. A **409** gets a hint that people and bank accounts share one name list per currency; `accounts opening-balance` on a person is a 422.
- `accounts opening-balance <id> --amount <signed-cents> [--date] [--title]` → `POST /v1/accounts/{id}/opening-balance` — seeds the starting balance as a transaction under the `@Opening` system category (counts toward the balance, excluded from flow reports). One per account; the engine's 409 says to edit/delete the existing seed.
- Currency is immutable on update: pre-flight hint before the engine 422.

### `expense categories`
- `categories list`, `get <id>`, `create`, `update`, `delete`. Categories are not archivable.
- System categories (`@Opening`, `@Pendiente`) can be renamed but not deleted — the engine's 403 surfaces with `Hint: System categories can be renamed but not deleted.`

### `expense hashtags`
- Same shape as categories: `list`, `get`, `create`, `update`, `delete`. Not archivable.

### `expense log`

Two forms, one command, never mixed — passing a line **and** a content flag is refused client-side.

- `log --amount <cents> --account-id <id> [--title <t>] [--category-id <id>] [--date] [--description] [--hashtag-ids]` → `POST /v1/transactions`. Explicit, scriptable, no parsing, no prompt. Only `--amount` and `--account-id` are required: with no `--category-id` the engine files the row under `@Pendiente` (which counts like any other category); with no `--title` the row is titleless. Omitted flags are omitted keys, never nulls.
- `log "<line>" [--dry-run] [--yes] [--json]` — one typed line in the quick-add grammar: `expense log "tottus -38.60 $signature @korakuen #caja hoy"`. The grammar lives in [expense/quickadd/](../expense/quickadd/), shared verbatim with the TUI LOG bar — `$account`, `@category`, `#tag`, `//note`, a sign is what makes a number an amount, dates in both languages. Reference names match on "contains, anywhere" ([decisions.md](decisions.md) "Three quick-add grammar rules").
  - **Whether the line can be logged is decided client-side, then stated.** An amount and an account, every name resolved, not dated ahead → `POST /v1/transactions`. Anything else — no amount, no account, a name that matched none or several, a `#tag` that does not exist, a future date — is **refused**: the reasons are printed (with the candidates behind an ambiguous name), exit 1, nothing written. A missing title or category is not a reason. The rule is [expense/quickadd/route.py](../expense/quickadd/route.py), the same one the TUI bar uses.
  - **It always asks first.** The parsed row is echoed — the date in words, the account and category by name — and waits for y/N. `--yes` skips the ask; off a TTY `--yes` is mandatory.
  - **`--dry-run`** shows that echo and writes nothing. `--dry-run --json` emits the parse (see Sanctioned exceptions).
  - Refused client-side, exit 1: a line together with any content flag; neither form; the flag form missing `--amount` or `--account-id`; `--dry-run` without a line; `--json` with a line but no `--yes`.

### `expense transactions`
- `transactions list` — filters: `--account-id`, `--category-id`, `--hashtag-id`, `--reconciliation-id`, `--unreconciled`, `--from`, `--to`, `--search`. `--from`/`--to` take a day (`YYYY-MM-DD`, the whole day, inclusive — read by the engine in `display_timezone`) or a time with an offset. Paging: `--limit`, `--sort date_desc|date_asc` (passed through unchecked, so a wrong value is the engine's `422`), `--after <cursor>`. `--unreconciled` is rows assigned to no reconciliation — over an already-reconciled period, the orphan check to run after every import; combining it with `--reconciliation-id` is a `422`.
- `transactions get <id>` — full detail; history via `expense activity list --resource-type transaction --resource-id <id>`.
- `transactions update <id>` — partial update, including `hashtag_ids` and `reconciliation_id`. Field locks under a completed reconciliation surface as the engine's 422 with a "revert the reconciliation to draft first" hint; a date moved into a sealed period, or an assignment into a completed reconciliation, gets the same hint.
- `transactions delete <id>`.
- `transactions batch` — atomic multi-create from a JSON array of transactions, read from `--file` or stdin.

### `expense reconcile`
- `reconcile list --account-id <id> [--json]` — the account is required. The whole list as the engine returns it — `date_start` ascending, then creation time, oldest first (contract: "Reconciliations", "Ordering") — with no paging flags and no footer. Rows carry a `Diff` column — the engine's `difference_cents`. A reconciliation's rows are `expense transactions list --reconciliation-id <id>`.
- `reconcile create --account-id <id> --name <n> --date-start <day> --date-end <day> --beginning-balance <cents> [--ending-balance <cents>]`. Both dates and the beginning balance are required. Dates are calendar days (`YYYY-MM-DD`) sent as typed — the engine refuses any datetime, so a malformed day is its `422` on that field.
- `reconcile update <id>` — partial update (`--name`, `--date-start`, `--date-end`, `--beginning-balance`, `--ending-balance`); dates as on `create`. Editing `--date-start` repositions a period. Field locks under a completed reconciliation surface as the engine's 422 with a "revert first" hint. An inverted range gets a hint that `--date-end` must not precede `--date-start`; an overlap with another period points at `reconcile list --account-id <id>`.
- `reconcile delete <id> [--yes]` — draft only (engine 409 otherwise; hint "revert first"). Cascade-unassigns attached transactions.
- `reconcile complete <id>` — status → completed; prints the reconciliation as returned, plus the gap warning when there is one. Locks `amount_cents`, `account_id`, `title`, `date` on every assigned transaction plus the reconciliation's own balance/date fields. When the engine refuses because no transaction is assigned, the hint names `transactions update <tx-id> --reconciliation-id <recon-id>`; when it refuses because rows inside the period are in no reconciliation, the hint is the placeholder form `transactions list --account-id <id> --unreconciled --from <start> --to <end>`.
- `reconcile revert <id> --yes` — status → draft; prints the reconciliation. `--yes` required.

### `expense dashboard`
- `dashboard` → `GET /v1/dashboard` — current month only: bank accounts, people, categories (with hashtag-combination breakdown), totals. Historical months: `expense reports monthly`.
- `--include-archived` — adds the `archived_accounts` and `archived_people` panels, in that order, at the bottom, as two separate panels. The fields are `null` without the flag and `[]` with it, so a present-but-empty list still prints its header.
- **Settled people fold, they never disappear.** The `People:` panel draws everyone still owing or owed, then one `▸ 3 settled` line for the zero-balance rows (`split_settled` / `settled_label` in [_resource.py](../expense/commands/_resource.py)). "Settled" is exactly zero in the person's **own** currency, never the home figure, so a missing rate never reads as "paid back". `expense accounts list --include-people` names them. Archived people are not folded.
- **Aggregates are home-currency and nullable.** Every category/hashtag/totals table has one amount column, `Home`. Each figure is nullable with an `unconverted_count` beside it; a `null` renders as `3 unrated`, never `0.00` and never a native-currency fallback. Rows with nothing spent are not drawn (`expense categories list` is the full list); rows the engine could not price keep their line. Month-grid cells distinguish `—` (no activity) from `3 unrated`.
- `--json` — raw engine response.

### `expense reports`
- `reports monthly --date YYYY-MM` — single month.
- `reports monthly --from YYYY-MM --to YYYY-MM` — inclusive range (max 24 months). Mutually exclusive with `--date`.
- `--json` — raw engine response.

### `expense activity`
- `activity list [--resource-type <t>] [--resource-id <id>] [--from <time>] [--to <time>] [--after <cursor>] [--limit N]` → `GET /v1/activity` (audit log, newest first, one date window per read — the last 30 days by default, at most 366 days wide). `--from` / `--to` are sent as typed: a bare `YYYY-MM-DD` is the whole day in `display_timezone`, a time with an offset is that instant, and the two mix. `--resource-id` does not lift the window: pass `--from` to reach older history.

### `expense rates`
- `rates get --target <code> [--base USD] [--date YYYY-MM-DD]` → `GET /v1/exchange-rates`.
- `rates list [--date YYYY-MM-DD | --from YYYY-MM-DD --to YYYY-MM-DD] [--after <cursor>] [--limit N]` → `GET /v1/exchange-rates/history` (stored daily rates, newest first, one row per pair per day, one date window per read — the last 30 days by default). `--date X` is the window `--from X --to X`, and is refused together with either.
- Both carry `rate_e8: int` — the rate × 10^8. Human output renders 4 decimals via `rates_cmd.format_rate`, integer arithmetic only; `--json` passes the integer through. `RATE_SCALE` in `expense/currencies.py` mirrors the engine constant.

### `expense ping`
- `ping` → `GET /health`. Connectivity + auth sanity check. Prints `ok (0.1s)`.

### `expense version`
- `version` — prints the installed CLI version. No engine call, no config read.

### `expense import`

Two doors: `sheet` (the personal spreadsheet) and `bank` (a bank download, matched against the ledger). Both read `.xlsx` via the `openpyxl` extra (`pip install -e ".[import]"`) and are dry runs unless `--apply` is passed.

#### `expense import bank`
- `import bank <file.xlsx> [--account <name>] [--apply] [--all] [--json]` — a BCP download (sheet `data`: Fecha, Descripcion, Moneda, Monto, optional Numero de Operacion) → the ledger under `@Pendiente`. The engine does the duplicate matching in one `POST /transactions/import` ([expense/bank_import/engine.py](../expense/bank_import/engine.py)); the rules and their why: [decisions.md](decisions.md) "Bank downloads are matched against the ledger".
  - **The account is asked, not read.** On a TTY the accounts are listed (a card's PEN and USD legs are one entry); the account is asked every run and nothing is remembered by file name, so a re-download (`Sueldo Soles (1).xlsx`) asks like any other file. `--account` names it instead; off a TTY, and under `--json`, it is required. A file holding a currency the pick has no leg for is refused whole.
  - **Limits:** rows before 2026-01-01 are not sent (counted in the summary); a file over 500 rows is refused before any call.
  - **Preview:** the first 8 rows (`--all` for every one), numbered by their line in the file, each with its match; then the counts and a warning for any day where the ledger holds rows no file row matched. `--apply` is the same call with `dry_run: false`.
  - **Errors:** a `422` refuses the whole file and names each refused row by its line; a line the parser could not read is listed and not sent, and under `--apply` makes the exit code 1.
  - **`--json`** is the engine's response verbatim; what the client held back goes to stderr.

#### `expense import sheet`
- `import sheet <file.xlsx> [--apply] [--chunk-size N] [--account-name SHEET_NAME:CUR=LEDGER_NAME ...] [--json]` — the personal sheet → engine. Parses, resolves names to ids, plans, then writes through `POST /transactions/batch`. Package: [expense/import_/](../expense/import_/).
- **Opening balances:** rows marked `SALDO INICIAL` (case/whitespace-insensitive) in the title or category column go to `POST /v1/accounts/{id}/opening-balance` instead of the batch; their category/hashtag cells are discarded. One per (account, currency): extra rows are skipped as `duplicate-opening` (first line wins) and listed in the dry run. A 409 at apply time counts as already present.
- **Sheet and column matching is tolerant.** The worksheet name (`Data`) matches ignoring case and leading or trailing spaces. Columns match by header name, each field accepting several spellings — the alias table is [expense/import_/mapping.py](../expense/import_/mapping.py) `FIELD_HEADERS`; no label may serve two fields (guard: `test_header_aliases_are_unambiguous`).
- **Multi-currency account names split.** A `CUENTA` name used under two currencies becomes two accounts, each renamed with its currency (`BCP Oro` → `BCP Oro PEN` + `BCP Oro USD`). A name used under one currency passes through verbatim; a name already ending in its currency is not doubled. Rows resolve by the raw sheet name, so re-runs stay idempotent.
- **Renaming an account leg.** `--account-name "BCP:PEN=Sueldo Soles"` (repeatable) writes the sheet's `BCP` rows in PEN, and its opening balance, to a ledger account named `Sueldo Soles` instead of the derived name; other legs keep theirs (`BCP USD`). The sheet name matches ignoring case and leading or trailing spaces, the currency is upper-cased, and the ledger name is everything after the first `=`. **It is remembered:** each rename is saved to `sheet_account_names` in the config (dry run included) and applied on every later run, so a re-run without the flag reuses `Sueldo Soles` instead of creating `BCP PEN`; passing the flag again for the same leg replaces the saved name. With no config file yet the rename applies to that run only. The dry run shows a renamed leg as `Sueldo Soles [PEN]  (from "BCP")`; `--json` carries it as `name` + `source_name`. A malformed value, a leg the sheet does not have, or a rename that lands two sheet legs on one ledger account (same name and currency) is a usage error (exit 2): nothing is written and nothing saved.

### `expense world`
- `world` — launches the Textual TUI over the same fetch/write layer. `expense` with no args prints group help. Reference: [tui.md](tui.md).

---

## Global flags

| Flag | Applies to | Purpose |
|---|---|---|
| `--json` | every read command | Raw engine response, passed through verbatim |
| `--yes` / `-y` | every destructive command (delete, revert, clear) | Skip confirmation prompt |
| `--verbose` / `-v` | every command (root flag) | Print HTTP request/response to stderr, Authorization redacted |
| `--include-archived` | `accounts list`, `dashboard` | Include archived rows (accounts are the only archivable resource) |

---

## Output conventions

- **Tables** — Default rendering for every `<resource> list`. Plain columns, header row + separator dashes, two-space gap. Built via the shared helpers in [expense/commands/_resource.py](../expense/commands/_resource.py): `render_table(headers, rows, *, align_right)`, `pad_left`, `pad_right`, `visible_len`. Columns are chosen for at-a-glance scannability, not completeness — the full key:value dump is `<resource> get <id>`, and `--json` is raw.
  - **Process rule:** before adding a new `list` renderer (or new columns to an existing one), propose the column set explicitly and get user sign-off, via an HTML mockup in [mockups/](mockups/). Never invent columns from the engine response shape alone.
  - **Color swatches** — a `#RRGGBB` column renders as a 2-char ANSI 24-bit block via `color_swatch(hex, color=color_supported())`. `color_supported()` gates on `sys.stdout.isatty()` + `NO_COLOR` ([no-color.org](https://no-color.org)); off a TTY the hex string is printed so output stays grep-able.
  - **Name resolution** — ID columns resolve to names via live reference-list maps (`load_account_name_map`, `load_category_name_map`, `load_hashtag_name_map`); the engine's responses are IDs-only. Unresolvable IDs fall back silently to the first 8 chars; null IDs render as `—`. A name-map failure degrades to `{}` and never breaks a listing.
  - **Truncation** — free-text columns (`title`, `description`) truncate at 24 visible chars with `…`. The full value is in `get` / `--json`.
  - **Hashtag cells** — `transactions list` ends with a `Hashtags` column built by `format_hashtag_cell` (CLI width 24, TUI width 20). Empty renders `—`, never blank.
- **Pagination (human mode)** — every list is one of three shapes ([cli-runtime.md](cli-runtime.md) "Three list shapes"). The line under each table follows the shape:
  - **Whole** — `accounts list`, `categories list`, `hashtags list`, `reconcile list`. No `--limit`/`--offset` (the engine `422`s them), every row printed, **no footer line**. Guarded by `test_command_surface.py::test_whole_lists_take_no_paging_flags`.
  - **Cursor** — `transactions list`. Human mode asks for 20 rows (`DEFAULT_PAGE_ROWS` in [_resource.py](../expense/commands/_resource.py)) unless `--limit` says otherwise; when the engine returns a `next_cursor` the table ends with `(more: pass --after <cursor> with the same filters and --sort)` — the engine binds a cursor to the sort as well as the filters — and nothing on the last page. No total is printed.
  - **Cursor inside a date window** — `activity list` and `rates list`. The line under the table always prints the window the engine echoes, even over an empty table: `(2026-08-24 → 2026-09-23 · more in this window: pass --after <cursor>)` while the window has more. On its last page, activity prints `(2026-08-24 00:00 → 2026-09-23 23:59 · older: pass --to 2026-08-24T00:00:00-05:00)` — bounds are the engine's echoed instants in `display_timezone`, cut to the minute, and `--to` is the echoed `date_from` uncut; rates print `(2026-08-24 → 2026-09-23 · newest first · older: pass --to 2026-08-23)` — one day before the echoed `date_from`, since rate dates are inclusive.
  - `--json` sends **no** default limit and prints the engine body verbatim, whatever the shape. Why 20 rows: [decisions.md](decisions.md) "Every data table pages at 20 rows".
- **Amounts** — currency symbol prefix (`S/ 8,420.50`, `$5,200.00`). Native + home currency side by side when they differ. Outflows prefixed with `-`.
- **Dates (output)** — ISO 8601 (`2026-04-19`). Relative hints (`3 days ago`) only in `get` views.
- **Dates (input)** — commands that accept `--date` (`expense log`, `expense transactions update`) take `YYYY-MM-DD`, `YYYY-MM-DD HH:MM[:SS]`, `YYYY-MM-DDTHH:MM[:SS]`, `YYYY-MM-DDTHH:MM:SSZ`, or `YYYY-MM-DDTHH:MM:SS±HH:MM`. Naive forms get the local timezone attached by [expense/dates.py](../expense/dates.py) — the engine rejects naive datetimes, so this normalizer is the only place that accepts them. **Not** `reconcile create`/`update`: a period's dates are calendar days sent unnormalised.
- **Errors** — the engine's `{ error: { code, message, fields, reasons } }` rendered as (reason codes are not shown):
  ```
  Error: VALIDATION_ERROR — Amount must not be zero.
    amount_cents: Must not be zero.
  ```
- **`--json`** — pass-through: no reshaping, no truncation, no key renaming. Two-space indent, keys in the engine's order, UTF-8 written as UTF-8 (`Café`, not `Caf\u00e9`). One serialiser, [expense/jsonout.py](../expense/jsonout.py), for every command and for the error envelope.
