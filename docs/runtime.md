# Runtime Behavior

How to run and repair the app (`expense`) and the sheet import (`expense import sheet`), then the few read, write and error rules the code cannot say. Both share one HTTP client and the `fetch_*` functions. No cache and no offline write queue: [decisions.md](decisions.md) "All reads are live".

## The settings file and a fresh start

The engine address and key live in `~/.expense-config` (or the path `EXPENSE_CONFIG` names; fields in [commands.md](commands.md)). [expense/config.py](../expense/config.py) is its one reader and writer. The app reads it once, at launch, and a save replaces what it holds (`config.hold`; why: [decisions.md](decisions.md) "The app holds its settings from launch, and only the newest read hands back").

**A fresh start needs no command.** With no usable settings file the app opens on its setup screen, which writes one, replacing a damaged one, only once setup is done ([tui.md](tui.md) §2 "Setup comes first"). `expense import sheet`, finding no usable file, stops on every step with a message pointing at that screen (exit 3).

## Read semantics

Every read is a direct `GET`; a screen shows what the engine computed at that moment, home-currency figures included.

- Responses are IDs-only; names resolve through live reads ([tui.md](tui.md) §1 "Name resolution is live HTTP and fails silently by design").
- **Deleted is deleted.** A deleted row is invisible to every client (no list returns it, its get is a 404) and nothing in the app restores it. The engine keeps the row; undeleting is an operator task outside the API (contract: "Base Conventions", "A delete is final"). The engine's activity history still holds a deleted row's history; this client has no screen for it.
- Transaction reads always send `debit_as_negative=true`, pinning the sign rather than trusting the default. The bank upload's rows and their days' unclaimed parts (contract: POST /v1/transactions/import) and a bank line's parts (contract: GET /v1/bank-lines/{bank_line_id}) arrive unsigned, as a magnitude and a `transaction_type`; `signed_cents` in [expense/formatting.py](../expense/formatting.py) signs them, the one place the app reads the sign off the type.

### Three list shapes

No list pages by position (contract: "Base Conventions", "Lists come in three shapes, and none of them is paged by position"). The app reads each shape its own way; [expense/reads.py](../expense/reads.py) holds the readers.

- **Whole `{items}`** (accounts, categories, hashtags, a category's hashtags, an account's statements): one read, no paging parameters.
- **Cursor `{items, limit, next_cursor}`** (transactions, bank lines): `?after=<next_cursor>` until it is `null` (contract: "Base Conventions", "Cursors, on every cursor-paged list"). A count is its own read, `/transactions/count` or `/bank-lines/count`, on the list's own filters. [tui.md](tui.md) says which screen counts which list and which reads every page.
- **Cursor + date window** (activity, exchange-rate history): the cursor inside one window (contract: "Base Conventions", "Date windows"); the window before it is read by sending the response's `previous_date_to` back unchanged as `date_to`, and `null` means nothing earlier. No screen reads these.

A stale `limit`, `offset` or unknown parameter is the engine's `422`, never a quietly wrong answer.

## Write semantics

Writes go straight to the engine when you press enter: **no offline queue, no buffering, no replay**. [expense/http.py](../expense/http.py) mints an `X-Idempotency-Key` (UUID) per logical write and retries a write that timed out (connect timeouts included) or got a `500`, `502`, `503` or `504` twice, **with the same key**, so a retry is safe (`_RETRYABLE_STATUS`). Every other failure, a refused connect included, fails fast, so nothing assumes a write landed that did not, and reads never retry.

**Bulk writes** (the LOG bar's save) go through [expense/batch_write.py](../expense/batch_write.py), whose docstring gives the rules: chunks, refused rows going again, a re-run writing nothing twice. **A refusal every further write would draw stops the run** (`errors.refuses_every_write`; [decisions.md](decisions.md) "Missing settings stop a multi-write run"): nothing more is sent and the app says it once, on no row.

**How refused rows read** (the LOG bar's table, the ledger's bulk-edit toasts, the sheet import's refused rows) goes through one grouping, `grouped_refusals` in [expense/formatting.py](../expense/formatting.py): one line per kind of refusal, then the rows it hit. *Alike* is the same code, fields and reasons (`errors.refusal_kind`), never the top-level message, and holds across every send of the run. What each surface adds: [tui.md](tui.md) "Refused rows read one line per kind of error".

## Engine errors surface cleanly

The `{ error: { code, message, fields, reasons, details } }` envelope is rendered intact. `EngineError` ([expense/errors.py](../expense/errors.py)) keeps `reasons` (contract: "Error reasons") and `details` (contract: "Error format"), `None` when the engine sends them null or leaves them out. The app may add a line for a known refusal without replacing the engine's message ([tui.md](tui.md) "When the engine says no"); the sheet import adds none ([commands.md](commands.md) "Output conventions").

Two hints belong to no single screen and live in `format_error`: a `401` (the key is missing or not valid) and `SETTINGS_MISSING` (first-time setup not done; matched on the code alone, contract: "Error codes"). Every remedy the shared text gives points at a screen of the app, never a typed command (guard: `test_no_message_in_the_app_tells_the_owner_to_type_a_command` in [tests/unit/test_tui_setup.py](../tests/unit/test_tui_setup.py)). The launch-time rate check shows nothing on any engine error.

## The log

The running app (the TUI and `expense import sheet`) appends to `~/Library/Logs/expense_world/tui.log`, where Console.app opens it, or to the file `EXPENSE_LOG` names. [expense/applog.py](../expense/applog.py) sets it up at launch, rotating; a place it cannot write leaves the app running with no log. It holds each request's method, path with query, status and time ([expense/http.py](../expense/http.py)), every engine refusal as the engine sent it (so it can echo a value the user typed), every write retry with its idempotency key, and every unexpected error with its traceback. `--verbose` adds the request and reply bodies, never a header; without it no description or amount goes in. The token, the Authorization header and the config never do: `redact` blanks every token a client has sent, any `Bearer` value and any `ewe_pat_` string in every record, traceback included. Every unit test points it at the conftest redirect, and the contract suite never configures it, so neither writes to the owner's log.

## Working against the live engine

There is exactly **one engine: the local deployment** (`http://127.0.0.1:8000`, a launchd service on the owner's Mac, set up by the engine's local-deployment guide). No staging, no sandbox: every PAT belongs to a real user and every write lands in the one true ledger, a plain `expense` included ([CLAUDE.md](../CLAUDE.md) "Careful running live").

**Isolation levers, weakest to strongest:**

- `EXPENSE_CONFIG` redirects the config file: *local config only*; the same PAT still writes to the same ledger.
- A **separate PAT for a separate user** isolates data within the same database (PATs: [commands.md](commands.md) "Auth model").
- **A second engine over the `expense_world_test` database**, the practice engine, which is how the contract suite runs. Nothing it writes can reach the real ledger.

  **Start and stop it with one command, from this repo:** `scripts/practice-engine up` and `scripts/practice-engine down` (the script's header says what each prints and how it keeps the caller's environment out). Every agent may run them; the orchestrator does, before and after a task that needs the contract live. `up` runs the engine's own practice launcher, `deploy/local/client-practice-engine.sh 8002`, run from the engine checkout's root, which serves an export of the engine's last commit, never uncommitted work, over `expense_world_test` on `127.0.0.1:8002`, and names that commit in its log (`/tmp/expense-test-engine.log`). A reused engine keeps its commit: after a new engine commit, `down` then `up`. `down` stops, by its pid, only the `:8002` listener whose command line ends in the launcher's engine start (`-m uvicorn app.main:app --host 127.0.0.1 --port 8002`) and whose working folder is the launcher's export. The session guard ([.claude/hooks/guard.py](../.claude/hooks/guard.py)) lets the script through only in the exact shapes its docstring lists, so its output, which carries both keys, reaches only the terminal ([decisions.md](decisions.md) "The practice engine has one script, run in exact shapes").

  **The practice users.** In the engine repo, `deploy/local/seed-test-user.sh` seeds two practice users, a PAT for each and a copy of `exchange_rates`. The **shared practice user** is the one every contract test writes as; the **reserved-names practice user** owns categories named `@Pendiente` and `@Opening` and a hashtag named `Pendiente`, so a test can draw the engine's refusal of a reserved name. With `--force` it reseeds: it revokes every PAT each user holds, prints one fresh one per user (`shared practice user (<id>):`, then `reserved-names practice user (<id>):`) and refreshes `exchange_rates`; each user's id and rows stay, so a test cleans up what it makes and never assumes a practice user starts empty. The shared user always holds `BCP-0000` (number 0000, soles and dollars), which the statement samples upload to, and `BCP-0001` (number 0001, soles only), for the `card-soles-only` sample. The seed prints their ids as `EXPENSE_PRACTICE_ACCOUNT_ID=<id>` and `EXPENSE_PRACTICE_SOLES_ACCOUNT_ID=<id>`, new whenever an account was deleted, so nothing hard-codes them.

  **By hand, only the tester** starts it, with the launcher alone, run from the root of the engine checkout, `expense_world_engine`, beside this repo ([README](../README.md) "Checkout layout"):

      nohup deploy/local/client-practice-engine.sh 8002 > /tmp/expense-test-engine.log 2>&1 < /dev/null &

  The launcher fixes the database and the interpreter itself, so the start takes no environment; `nohup`, the redirects and the `&` keep it running after the agent that started it finishes (started as an agent's own background task instead, it stops with that agent). The guard refuses every other start, since an engine run by hand serves uncommitted work. At the start of each check the tester reseeds by running `deploy/local/seed-test-user.sh --force`, from the same folder. It stops only the engine it started: `kill <pid>`, or `lsof -ti :8002 | xargs kill`.

  **Port 8002, not 8001.** `:8001` is `todo_world_engine`'s: point the suite there and every request 404s while the refusal guard and the health check both look fine.

  **The keys go on the command line, nowhere else.** The shared practice user's key goes in `EXPENSE_PAT`, the reserved-names user's in `EXPENSE_RESERVED_PAT`, both inline on the command that uses them, never in a file ([CLAUDE.md](../CLAUDE.md) "Stay inside this repo"). The next reseed revokes both, so each is good for one check; the practice accounts' ids are no key.

  **Pointing `expense` at it.** The app reads its key only from the file `EXPENSE_CONFIG` names, so hand it the config as a pipe: `EXPENSE_CONFIG=<(printf '{"engine_url":"http://127.0.0.1:8002","token":"<key>","main_currency":"PEN"}') expense …`. `main_currency` is there because a read of `/auth/me` otherwise saves it back; anything that writes the config (the setup and Config screens, `import sheet --account-name` saving a rename) fails on a pipe. A pipe gives its contents to the first read only, and the app and each step of `expense import sheet` read the settings once, so both work this way.

  **Stop it when the check ends:** `scripts/practice-engine down`.

**The contract suite** (`tests/contract/`) hits a real engine and is double-gated: `PYTEST_LIVE=1 EXPENSE_PAT=<key> EXPENSE_RESERVED_PAT=<reserved key> EXPENSE_PRACTICE_ACCOUNT_ID=<account id> EXPENSE_PRACTICE_SOLES_ACCOUNT_ID=<soles account id> EXPENSE_ENGINE_URL=http://127.0.0.1:8002 pytest tests/contract`, the four values being those the last reseed printed. `EXPENSE_ENGINE_URL` defaults to the live `:8000`, so always set it to `:8002` (the guard refuses a run without it). A test needing the reserved-names user or an account's id fails, naming the variable, rather than skipping ([tests/contract/conftest.py](../tests/contract/conftest.py)). Without `EXPENSE_PAT` the suite refuses to start on the developer's own config ([decisions.md](decisions.md) "Contract tests verify against a disposable database"); `EXPENSE_ALLOW_REAL_LEDGER=1` overrides it. It runs in one process: both conftest files turn `-n auto` into zero workers for any live run, and only an explicit `-n N` overrides them ([decisions.md](decisions.md) "Live contract runs stay in one process").

**What it pins:** each file in `tests/contract/` says so in its docstring. Every test calls the engine through the app's own HTTP client; `test_contract_citations.py` checks every `(contract: …)` citation in the repo against the live contract. A test builds what it needs through `Scratch` in [tests/contract/conftest.py](../tests/contract/conftest.py), which undoes it best-effort with **soft-deletes**: invisible to every client but still in the database, which is why it belongs on the practice database. Run it when engine-shape drift is suspected or before calling a release done; never in CI.

**Leftovers.** A contract test names what it builds `contract-…` (`freshman-…` in the freshman walk) and marks a bank account by a last 4 starting `9`; each test fails in its teardown when it leaves an account, category or hashtag it made (`leaves_nothing`), on the shared user and, for a test asking for `reserved_client`, on the reserved-names one. [scripts/clean_practice_user.py](../scripts/clean_practice_user.py) removes such leftovers through the engine's API; its docstring says what it matches and how to run it. A leftover on the reserved-names user is cleaned by passing that user's key as `EXPENSE_PAT`.

**Fixture drift.** The unit suite mocks the engine, so it cannot notice the engine changing shape. Run [scripts/check_fixture_drift.py](../scripts/check_fixture_drift.py) after any engine change, against the `:8002` practice engine: `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002` (the guard blocks a run without that flag). It checks every fixture key in `tests/unit`, and every `answer_of`-marked builder in [tests/unit/helpers.py](../tests/unit/helpers.py), against the engine's published `openapi.json`; `scan_fixtures`, `keyword_builders`, `_checked` and `extra_keys` in the script, and `answer_of`, say how. A clean run means no field is dead everywhere and every marked answer matches its endpoint, not that every fixture does: the key check unions every schema, a fixture no marked builder makes gets only the key check, and a value a test passes in place of a `None` in the bare answer is not looked into.

**Contract version.** The same run compares the contract's `info.version` with [scripts/engine-contract-version](../scripts/engine-contract-version), the version this repo was last checked against, as an opaque string: one line, never a copy of the contract. Any difference fails the run, even when every fixture key matches, a compatible `breaking.adding` step included ([decisions.md](decisions.md) "The version check stops on any contract move, the second number included"), and prints what changed, read from the contract's change log; a missing saved version fails it too. A run never changes the saved version: `--record-version` on the same command records the engine's, and only a version the change log lists first. The script's docstring and `version_problem`, `changes_report` and `main` say the rest.

**Unit tests never touch the network,** the owner's config or the owner's log, and see an 80×24 terminal: the autouse fixtures in [tests/unit/conftest.py](../tests/unit/conftest.py) say how.
