# Runtime Behavior

How the app (`expense`, the TUI) and the sheet import (`expense import sheet`) behave at runtime — read/write semantics, error handling, working against the live engine. Companions: [tui.md](tui.md) (the app) and [commands.md](commands.md) (the sheet import and the settings file).

## Overview

The client holds no business logic and **no local state beyond `~/.expense-config`** — no cache, no offline write queue ([decisions.md](decisions.md) "All reads are live"). The engine is the only authoritative store and runs on the same machine (`http://127.0.0.1:8000`), so every read is a live loopback HTTP call.

Everything here applies equally to the TUI (`expense`) and the sheet import (`expense import sheet`): they are clients of the same HTTP client and `fetch_*` functions, not separate runtimes.

## The settings file and a fresh start

The engine address and key live in the settings file, `~/.expense-config` (or the path `EXPENSE_CONFIG` names; its fields are in [commands.md](commands.md)). [expense/config.py](../expense/config.py) is its one reader and writer: `save` writes a temp file beside it, sets it to chmod 600 and moves it into place.

**A fresh start needs no command.** When the app opens and there is no settings file it can use — none at all, or one that cannot be read (damaged or half-written JSON, a body that is not a config, bytes that are not text, a path it may not read: `config.load_usable`) — it opens on its setup screen, which asks for the engine address (offered as the local engine's, `http://127.0.0.1:8000`) and the key, and for a name when the engine has no profile for that key ([tui.md](tui.md) §2 "Setup comes first"). Nothing is written until the engine has accepted the address and key and the profile exists; then the file is saved, replacing a damaged one. `expense import sheet --apply`, finding no usable file, stops with a message pointing at the app's setup screen.

## Read semantics

Every read is a direct `GET`. What a screen shows is what the engine computed at that moment, including home-currency figures (converted engine-side at read time).

- The engine's responses are IDs-only; the screens resolve names through live reference-list reads (`load_*_name_map` in [expense/reads.py](../expense/reads.py)), with a short-id fallback when one fails.
- **Deleted is deleted.** A deleted row is invisible to every client — no list returns it, its get is a 404 — and nothing in the app restores it. The engine keeps the row in its table; undeleting is an operator task outside the API (contract: "Base Conventions", "There is no restore"). The engine's activity history still holds a deleted row's history; this client has no screen for it.
- Transaction reads always send `debit_as_negative=true`, so the request pins the sign rather than depending on the engine default.

### Three list shapes

No list pages by position; every list is one of three shapes, each read its own way. The rules are the engine's (contract: "Base Conventions", "Lists come in three shapes, and none of them is paged by position"), with (contract: "Base Conventions", "Cursors, on every cursor-paged list") and (contract: "Base Conventions", "Date windows").

| Shape | Lists | How the app reads it |
|---|---|---|
| **Whole** `{items}` | accounts, categories, hashtags, a category's hashtags, one account's reconciliations | One read, every row; no paging parameters. |
| **Cursor** `{items, limit, next_cursor}` | transactions | `?after=<next_cursor>` until it is `null`; the count is its own read (`/transactions/count`), once per list. The TUI's growing lists are [tui.md](tui.md) §5. |
| **Cursor + date window** | activity, exchange-rate history | The cursor inside one window (30 calendar days counting `date_to`'s own day when `date_from` is left out; at most 366, counting both ends). The window before it is read by sending the response's `previous_date_to` back unchanged as `date_to`, which reads no row twice; `null` means nothing earlier. No screen reads these. |

A stale `limit`, `offset` or unknown parameter is the engine's `422`, never a quietly wrong answer.

## Write semantics

Writes go straight to the engine the moment you press enter. There is **no offline write queue, no buffering, no replay**.

- Each write carries an `X-Idempotency-Key` (UUID) minted once per logical write by `ExpenseClient`; retrying is safe — the engine returns the original response. Keys are **permanent** (no TTL). Replay requires the *same* request: each key stores a fingerprint over method/path/query/body, and reusing a key with a different body returns `409`.
- `ExpenseClient` retries a timed-out or 5xx write up to twice (1s/2s backoff) **with the same key** before surfacing the error, printing a stderr notice per attempt. Connect failures are not retried, and reads never auto-retry.
- Any other network error fails fast: the app shows it and the sheet import prints it and exits non-zero, so nothing assumes a write landed that did not.

**Bulk writes** go through one shared path, [expense/batch_write.py](../expense/batch_write.py), used by `expense import sheet --apply` and the TUI's LOG bar (`ctrl+s`). Rows go out in chunked `POST /transactions/batch` calls of 200 rows by default, each with its own idempotency key. The engine takes at most 500 rows in one request (contract: POST /v1/transactions/batch); `ENGINE_BATCH_MAX` in that module is the limit's one home in the code, and a chunk size outside 1–500 is refused before anything is sent. A batch is **atomic** — one bad row and none of the chunk is written — so a refused chunk is re-posted one row per batch, letting the good rows land and making the bad one name itself. A row refused only because its own id is taken is **not** a failure: ids are client-supplied, so `ID_EXISTS` on `transactions.0.id` of its one-row batch (a batch refusal is keyed by item index (contract: POST /v1/transactions/batch)) means the row is already in. That is what makes a retry after a half-written run safe and why `expense import sheet` re-runs converge instead of duplicating. Every other `409` (a taken operation code, `CONCURRENT_CHANGE`, `RESERVED_NAME_HELD`) is a refusal of that row, like a `422` (`errors.is_own_id_replay` in [expense/errors.py](../expense/errors.py)). A chunk refused with a `401`, `403` or `5xx` is not re-posted row by row — every row would fail the same way — and is reported once for the chunk; later chunks still go. **`SETTINGS_MISSING` stops the run**: it is a `422`, but about the account and not about any row, so its chunk is failed as one group with no row-by-row retry and no later chunk is sent (`refuses_every_write` in [expense/errors.py](../expense/errors.py), matched on the error code alone). Every run of several writes follows the same rule — the first `SETTINGS_MISSING` ends it and is shown once: `expense import sheet --apply` stops wherever it lands (a resource create, an opening balance or the batch) and prints the engine's error, in its words alone; the LOG bar shows it as one toast, with its hint ("Engine errors surface cleanly" below), and puts it on no row; a TUI bulk edit sends no further row.

## Engine errors surface cleanly

The engine's `{ error: { code, message, fields, reasons } }` envelope is rendered intact (format in [commands.md](commands.md) "Output conventions"); `expense import sheet --json` prints it verbatim. `EngineError` ([expense/errors.py](../expense/errors.py)) keeps `reasons` — each refused field's reason code (contract: "Error reasons"), `None` when the engine sends it null or leaves it out — for code to decide on. The app may add a line for a known refusal without replacing the engine's message; it is chosen by the error code and the reason code, never by the route or the wording of `message` or `fields` ([decisions.md](decisions.md) "Hints are chosen by the engine's reasons, never its wording"). The lines for `CONFLICT`, `FORBIDDEN` and `LIMIT_REACHED` refusals, and for the two `VALIDATION_ERROR` reasons an opening balance draws, are listed in [tui.md](tui.md) "When the engine says no". The sheet import prints the engine's words alone, with none of the app's lines (`engine_text` in [expense/errors.py](../expense/errors.py)). The `--json` envelope the sheet import composes itself (`CONNECTION_ERROR`, `CONFIG_*`) has the same four keys, with `fields` and `reasons` null.

Two hints belong to no single screen and live in the shared error text, `format_error` in [expense/errors.py](../expense/errors.py), which the TUI's toasts and banners print. Every screen that reports an engine error through that text shows them after a blank line under the engine's code, message and fields; the TUI bank import shows them in its toast, its on-screen refusal of a `422` being the code, the message and the refused rows:

- **A `401`** — the key is missing or not valid: `Hint: the key is missing or not valid. Set a fresh one on System ▸ Config (press t).`
- **`SETTINGS_MISSING`** — the user's settings do not exist yet (contract: "Error codes"). Both rate reads list it among the codes they can return (contract: GET /v1/exchange-rates) (contract: GET /v1/exchange-rates/history). Matched on the error code alone: `Hint: First-time setup is not done yet. Open System ▸ Auth & profile and press b.`

Every remedy the shared text gives points at a screen of the app, never at a typed command (guard: `test_no_message_in_the_app_tells_the_owner_to_type_a_command` in [tests/unit/test_tui_setup.py](../tests/unit/test_tui_setup.py)).

Neither reaches `--json`, which stays the engine's body. The TUI's launch-time rate check shows nothing on any engine error, this one included.

## Working against the live engine

There is exactly **one engine: the local deployment** (`http://127.0.0.1:8000`, launchd service on the owner's Mac, set up by the engine's local-deployment guide). No staging, no sandbox — every PAT belongs to a real user and every write lands in the one true ledger.

**Developer default is live.** A plain `expense` (the app) or `expense import sheet` reads `~/.expense-config` — the real credential. Reads are safe; ad-hoc writes are real writes. To inspect behaviour, use the unit suite.

**Isolation levers, weakest to strongest:**

- `EXPENSE_CONFIG` redirects the config file. This isolates *local config only* — the same PAT still writes to the same ledger.
- A **separate PAT for a separate user** is data isolation within the same database (PATs: [commands.md](commands.md) "Auth model").
- **A second engine over the `expense_world_test` database** — how the contract suite runs. Nothing it writes can reach the real ledger, and the engine's test-database script, run with `--force`, wipes it.

  **Start and stop it with one command, from this repo:** `scripts/practice-engine up` and `scripts/practice-engine down` ([scripts/practice-engine](../scripts/practice-engine)). Every agent may run them; the orchestrator does, before and after a task that needs the contract live. `up` starts the engine exactly as below (or reuses the one already on `:8002`), waits for `/health`, reseeds the practice user and prints its fresh key to the terminal. `down` stops whatever listens on `:8002` when its command line is the practice engine's start (`-m uvicorn app.main:app --port 8002`), whoever started it, a tester's hand start included; anything else on the port is left alone. The script fixes the port, the database and the interpreter itself, takes no options, and runs everything under a fixed environment (`bash -p`, every inherited variable unset, `env -i` with only `HOME`, `USER`, `LOGNAME` and `PATH=/usr/bin:/bin:/usr/sbin:/sbin`), so nothing the caller sets reaches the engine or the reseed. The session guard ([.claude/hooks/guard.py](../.claude/hooks/guard.py)) lets a command that names the script through only when the whole command is `scripts/practice-engine up` or `scripts/practice-engine down`, optionally followed by `> /dev/null`, `2>&1` or one pipe into a plain `sed`/`grep`/`head`/`tail` filter: no chaining, grouping, substitution, env prefix or wrapper, so its output, which carries the key, reaches only the terminal; its docstring lists the exact shapes and what it cannot see. The rest of this item is what the script runs, and what the tester may still run by hand.

  In the engine repo, `deploy/local/seed-test-user.sh` seeds a practice user, a PAT and a copy of `exchange_rates` (`--force` reseeds: it drops the practice user's rows, revokes its old PATs and prints a fresh one), then

      SUPABASE_DB_URL=postgresql://expense_engine@127.0.0.1:5432/expense_world_test \
        ADMIN_DB_URL=postgresql://<owner>@127.0.0.1:5432/expense_world_test \
        .venv/bin/python -m uvicorn app.main:app --port 8002 > /tmp/expense-test-engine.log 2>&1 &

  The engine refuses to start when its two URLs name different databases, so a URL left off, which falls back to the engine's `.env` and the real ledger, fails at startup. Run it from the engine checkout. Start it only with `.venv/bin/python`, the engine checkout's own interpreter: the engine needs Python 3.12, and that interpreter is the one built on it with the engine's dependencies. The guard refuses the start with any other interpreter (`python`, `python3`, this repo's own venv, any other path). `-m uvicorn` is how the engine's own local setup starts it, not the console script. The trailing `&` and the redirect detach it: the engine keeps running after the agent that started it finishes, and its output goes to a log outside both checkouts. Started as an agent's own background task instead, it stops when that agent finishes.

  **A start that crashes may be the engine mid-edit.** The engine checkout's working tree can hold a half-written change, and the engine starts from the working tree, not from its last commit. When the engine fails to start, ask the owner whether the engine coders have unfinished work before writing an engine ask.

  **Port 8002, not 8001.** `:8001` is `todo_world_engine`'s — point the suite there and every request 404s while the refusal guard and the health check both look fine.

  **Connect as `expense_engine`, not the owner.** The engine refuses to start as a SUPERUSER, which would bypass every RLS policy. `postgresql:///expense_world_test` connects as the owner and hits that guard.

  **The key goes on the command line, nowhere else.** The reseed prints the practice user's fresh PAT once, in its output (`scripts/practice-engine up` passes that output through). Read it there and pass it inline as `EXPENSE_PAT=<key>` on the contract suite's own command line (below), never in a file (CLAUDE.md "Stay inside this repo"). The next reseed revokes it, so it is good for one check only. The session guard ([.claude/hooks/guard.py](../.claude/hooks/guard.py)) holds the file half: the seed's output, and the script's, may be redirected only to `/dev/null` and piped only into a plain `sed`/`grep`/`head`/`tail` filter (a `grep` pattern with no `[…]` or other glob), and a command run in the engine checkout that holds `$(…)` or a backtick is refused, so the key cannot be captured into a variable there either; its docstring lists the exact forms.

  **Pointing `expense` at it.** The app reads its key only from the file `EXPENSE_CONFIG` names ([expense/config.py](../expense/config.py)), so hand it the config as a pipe instead of a file: `EXPENSE_CONFIG=<(printf '{"engine_url":"http://127.0.0.1:8002","token":"<key>","main_currency":"PEN"}') expense …`. `main_currency` is there because a read of `/auth/me` otherwise saves it back into the config; anything that writes the config (the app's setup and Config screens, `import sheet --account-name` saving a rename) fails on a pipe. A pipe gives its contents to the first read only: `expense import sheet` reads the settings once, so it works this way, while the app reads them at launch and again for every engine call, so it does not.

  **Stop it when the check ends:** `scripts/practice-engine down`. By hand, only the tester may stop it: `kill <pid>` of the engine it started, or `lsof -ti :8002 | xargs kill` — the only stop forms the guard lets it run.

**The contract suite** (`tests/contract/`) hits a real engine and is double-gated: `PYTEST_LIVE=1 EXPENSE_PAT=<key> EXPENSE_ENGINE_URL=http://127.0.0.1:8002 pytest tests/contract`, `<key>` being the one the last reseed printed. `EXPENSE_ENGINE_URL` names the target (the session guard refuses a contract run without it set to `:8002`); its default is the live `http://127.0.0.1:8000`, so always set it to the `:8002` test engine.

**It refuses to run against the real ledger.** Without `EXPENSE_PAT` the only credential is the developer's own config, so [tests/contract/conftest.py](../tests/contract/conftest.py) aborts the session with a message pointing at the practice database. `EXPENSE_ALLOW_REAL_LEDGER=1` overrides it.

What the suite does: calls the engine directly through the app's HTTP client and walks real flows (settings file → health → bootstrap → account/category create → transaction create → dashboard, plus the transaction cursor against `/count`, the whole lists, a category's tags, the activity window, the exchange-rate history walk-back and its window limits, `POST /transactions/import` and its reported days, bank lines and splits (`GET /bank-lines/{id}`, `?bank_line_id=` on the list and the count), the pending hashtag, the system rows' fixed names, reconciliations and sealed periods, an account's opening balance, the reasons refusals carry, reports), redirects `EXPENSE_CONFIG` to a temp dir, and cleans up best-effort in reverse dependency order. Cleanup means **soft-deletes** — invisible to every client but still in the database — which is why it belongs on the practice database. Run it when engine-shape drift is suspected or before calling a release done; never in CI. It catches what mocks cannot, e.g. `amount_cents` returning as a magnitude unless the read asks for `debit_as_negative`.

**Fixture drift.** The unit suite mocks the engine, so it cannot notice the engine changing shape. [scripts/check_fixture_drift.py](../scripts/check_fixture_drift.py) compares every unit fixture key against the engine's published `openapi.json`; run it after any engine change, against the `:8002` test engine above (its default target): `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002`. The flag stays explicit because the session guard ([.claude/hooks/guard.py](../.claude/hooks/guard.py)) blocks any run of the script without `--engine-url …:8002`. It is not a pytest file, to keep the unit suite hermetic.

**Contract version.** The same run compares the contract's `info.version` with the version saved in [scripts/engine-contract-version](../scripts/engine-contract-version), the version this repo was last checked against: one line holding the version and nothing else, never a copy of the contract. A different version is reported with both numbers (`saved …, engine …`) and fails the run even when every fixture key matches; a missing saved version fails it too. A moved version also prints what changed, read from the contract's own change log (`x-changelog` in `/openapi.json`, which the engine keeps newest first): every entry newer than the saved version, in that order, each as its version and date followed by every change as `kind: text` (the engine sends `kind` as `added`, `changed` or `removed`). It says the whole contract changed instead when the log is missing, empty or not a list, its first entry is not the engine's current version, the saved version is not in it, or an entry newer than the saved version is malformed; the saved entry and older ones are never read. A matching version prints nothing about the version or the log. A run never changes the saved version. Recording one is its own step, which writes the engine's current version and checks nothing else: `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002 --record-version`.

**Unit tests never touch the network.** `tests/unit/` is respx-mocked; autouse fixtures in [tests/unit/conftest.py](../tests/unit/conftest.py) redirect `EXPENSE_CONFIG` and block real sockets. A third pins the terminal every test sees to 80×24 (`COLUMNS` and `LINES`, `TERMINAL_SIZE` in that file), so Typer's output is the same in any window and in a pipe; TUI tests take their size from `run_test(size=…)`, never from the environment. Never bypass them.
