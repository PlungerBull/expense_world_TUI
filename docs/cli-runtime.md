# CLI Runtime Behavior

How the CLI behaves at runtime — read/write semantics, error handling, working against the live engine. Companion to [cli-spec.md](cli-spec.md) (commands and flags).

## Overview

The CLI holds no business logic and **no local state beyond `~/.expense-config`** — no cache, no offline write queue ([decisions.md](decisions.md) "All reads are live"). The engine is the only authoritative store and runs on the same machine (`http://127.0.0.1:8000`), so every read is a live loopback HTTP call.

Everything here applies equally to the TUI (`expense world`) and the importers (`expense import`): they are clients of the same HTTP client and `fetch_*` functions, not separate runtimes.

## Read semantics

Every read command is a direct `GET`. What a command prints is what the engine computed at that moment, including home-currency figures (converted engine-side at read time).

- The engine's responses are IDs-only; list renderers resolve names through live reference-list reads, with a short-id fallback when one fails (cli-spec "Output conventions", "Name resolution").
- **Deleted is deleted.** A deleted row is invisible to every client — no list returns it, its get is a 404 — and no command restores it. The engine keeps the row in its table; undeleting is an operator task outside the API (contract: "Base Conventions", "There is no restore"). `expense activity list` still shows a deleted row's history.
- Transaction reads always send `debit_as_negative=true`, so the request pins the sign rather than depending on the engine default.

### Three list shapes

No list pages by position; every list is one of three shapes, each read its own way. The rules are the engine's (contract: "Base Conventions", "Lists come in three shapes, and none of them is paged by position"), with (contract: "Base Conventions", "Cursors, on every cursor-paged list") and (contract: "Base Conventions", "Date windows"); what each command prints under its table is cli-spec "Pagination (human mode)".

| Shape | Lists | How the CLI and TUI read it |
|---|---|---|
| **Whole** `{items}` | accounts, categories, hashtags, a category's hashtags, one account's reconciliations | One read, every row; no paging flags. |
| **Cursor** `{items, limit, next_cursor}` | transactions | `?after=<next_cursor>` until it is `null`; the count is its own read (`/transactions/count`), once per list. The TUI's growing lists are [tui.md](tui.md) §5. |
| **Cursor + date window** | activity, exchange-rate history | The cursor inside one window (30 days by default); older rows are a new window. Flat commands only. |

A stale `limit`, `offset` or unknown parameter is the engine's `422`, never a quietly wrong answer.

## Write semantics

Writes go straight to the engine the moment you press enter. There is **no offline write queue, no buffering, no replay**.

- Each write carries an `X-Idempotency-Key` (UUID) minted once per logical write by `ExpenseClient`; retrying is safe — the engine returns the original response. Keys are **permanent** (no TTL). Replay requires the *same* request: each key stores a fingerprint over method/path/query/body, and reusing a key with a different body returns `409`.
- `ExpenseClient` retries a timed-out or 5xx write up to twice (1s/2s backoff) **with the same key** before surfacing the error, printing a stderr notice per attempt. Connect failures are not retried, and reads never auto-retry.
- Any other network error fails fast: the CLI prints it and exits non-zero, so the next command can rely on the previous one having landed.

**Bulk writes** go through one shared path, [expense/batch_write.py](../expense/batch_write.py), used by `expense import sheet --apply` and the TUI's LOG bar (`ctrl+s`). Rows go out in chunked `POST /transactions/batch` calls of 200 rows by default, each with its own idempotency key. The engine takes at most 500 rows in one request (contract: POST /v1/transactions/batch); `ENGINE_BATCH_MAX` in that module is the limit's one home in the code, and a chunk size outside 1–500 is refused before anything is sent. A batch is **atomic** — one bad row and none of the chunk is written — so a refused chunk is re-posted one row per batch, letting the good rows land and making the bad one name itself. A `409` there is **not** a failure: ids are client-supplied, so a replayed id means the row is already in. That is what makes a retry after a half-written run safe and why `expense import sheet` re-runs converge instead of duplicating. A chunk refused with a `401`, `403` or `5xx` is not re-posted row by row — every row would fail the same way — and is reported once for the chunk; later chunks still go. **`SETTINGS_MISSING` stops the run**: it is a `422`, but about the account and not about any row, so its chunk is failed as one group with no row-by-row retry and no later chunk is sent (`refuses_every_write` in [expense/errors.py](../expense/errors.py), matched on the error code alone). Every run of several writes follows the same rule — the first `SETTINGS_MISSING` ends it and is shown once, with its hint ("Engine errors surface cleanly" below): `expense import sheet --apply` stops wherever it lands (a resource create, an opening balance or the batch) and prints the engine's error as any single command does; the LOG bar shows it as one toast and puts it on no row; a TUI bulk edit sends no further row.

## Engine errors surface cleanly

The engine's `{ error: { code, message, fields, reasons } }` envelope is rendered intact (format in cli-spec "Output conventions"); `--json` prints it verbatim. `EngineError` ([expense/errors.py](../expense/errors.py)) keeps `reasons` — each refused field's reason code (contract: "Error reasons"), `None` when the engine sends it null or leaves it out — for code to decide on. Commands add a hint line for known refusals (e.g. "revert first" on a locked reconciliation) without replacing the engine's message; each hint is chosen by the reason code (`reason_on` / `has_reason` in [expense/errors.py](../expense/errors.py)), never by the wording of `message` or `fields`. The `--json` envelope the CLI composes itself (`CONNECTION_ERROR`, `CONFIG_*`) has the same four keys, with `fields` and `reasons` null.

Two hints belong to no single command and live in the shared error text, `format_error` in [expense/errors.py](../expense/errors.py), which the CLI's human output and the TUI's toasts and banners print. Every command, and every screen that reports an engine error through that text, shows them after a blank line under the engine's code, message and fields; the TUI bank import shows them in its toast, its on-screen refusal being the code, the message and the refused rows:

- **A `401`** — the token is missing or invalid: `expense config set --token <pat>`, or `expense auth bootstrap` for an account not yet provisioned.
- **`SETTINGS_MISSING`** — the user's settings do not exist yet (contract: "Error codes"). Both rate reads list it among the codes they can return (contract: GET /v1/exchange-rates) (contract: GET /v1/exchange-rates/history). Matched on the error code alone: `Hint: Your user_settings row is missing. Run 'expense auth bootstrap' to provision it.`

Neither reaches `--json`, which stays the engine's body. The TUI's launch-time rate check shows nothing on any engine error, this one included.

## Working against the live engine

There is exactly **one engine: the local deployment** (`http://127.0.0.1:8000`, launchd service on the owner's Mac, set up by the engine's local-deployment guide). No staging, no sandbox — every PAT belongs to a real user and every write lands in the one true ledger.

**Developer default is live.** Plain `expense …` commands read `~/.expense-config` — the real credential. Reads are safe; ad-hoc writes are real writes. To inspect behaviour, use `--verbose` on a read, or the unit suite.

**Isolation levers, weakest to strongest:**

- `EXPENSE_CONFIG` redirects the config file. This isolates *local config only* — the same PAT still writes to the same ledger.
- A **separate PAT for a separate user** is data isolation within the same database (PATs: cli-spec "Auth model").
- **A second engine over the `expense_world_test` database** — how the contract suite runs. Nothing it writes can reach the real ledger, and the engine's test-database script, run with `--force`, wipes it. In the engine repo, `deploy/local/seed-test-user.sh` seeds a practice user, a PAT and a copy of `exchange_rates` (`--force` reseeds: it drops the practice user's rows, revokes its old PATs and prints a fresh one), then

      SUPABASE_DB_URL=postgresql://expense_engine@127.0.0.1:5432/expense_world_test \
        ADMIN_DB_URL=postgresql://<owner>@127.0.0.1:5432/expense_world_test \
        .venv/bin/python -m uvicorn app.main:app --port 8002 > /tmp/expense-test-engine.log 2>&1 &

  The engine refuses to start when its two URLs name different databases, so a URL left off, which falls back to the engine's `.env` and the real ledger, fails at startup. Run it from the engine checkout. `.venv/bin/python` is the engine checkout's own interpreter, the only one with the engine's dependencies (a bare `python` may not exist, and the system `python3` has no `uvicorn`); `-m uvicorn` is how the engine's own local setup starts it, not the console script. The trailing `&` and the redirect detach it: the engine keeps running after the agent that started it finishes, and its output goes to a log outside both checkouts. Started as an agent's own background task instead, it stops when that agent finishes.

  **A start that crashes may be the engine mid-edit.** The engine checkout's working tree can hold a half-written change, and the engine starts from the working tree, not from its last commit. When the engine fails to start, ask the owner whether the engine coders have unfinished work before writing an engine ask.

  **Port 8002, not 8001.** `:8001` is `todo_world_engine`'s — point the suite there and every request 404s while the refusal guard and the health check both look fine.

  **Connect as `expense_engine`, not the owner.** The engine refuses to start as a SUPERUSER, which would bypass every RLS policy. `postgresql:///expense_world_test` connects as the owner and hits that guard.

  **The key goes on the command line, nowhere else.** The reseed prints the practice user's fresh PAT once, in its output. Read it there and pass it inline as `EXPENSE_PAT=<key>` on the contract suite's own command line (below), never in a file (CLAUDE.md "Stay inside this repo"). The next reseed revokes it, so it is good for one check only. The session guard ([.claude/hooks/guard.py](../.claude/hooks/guard.py)) holds the file half: the seed's output may be redirected only to `/dev/null` and piped only into a plain `sed`/`grep`/`head`/`tail` filter (a `grep` pattern with no `[…]` or other glob), and a command run in the engine checkout that holds `$(…)` or a backtick is refused, so the key cannot be captured into a variable there either; its docstring lists the exact forms.

  **Pointing `expense` at it.** The CLI reads its key only from the file `EXPENSE_CONFIG` names ([expense/config.py](../expense/config.py)), so hand it the config as a pipe instead of a file: `EXPENSE_CONFIG=<(printf '{"engine_url":"http://127.0.0.1:8002","token":"<key>","main_currency":"PEN"}') expense …`. `main_currency` is there because `auth me` otherwise saves it back into the config; a command that writes the config (`config set`, `import sheet --account-name` saving a rename) fails on a pipe.

  **Stop it when the check ends:** `kill <pid>` of the engine you started, or `lsof -ti :8002 | xargs kill` — the only stop forms the guard lets the tester run.

**The contract suite** (`tests/contract/`) hits a real engine and is double-gated: `PYTEST_LIVE=1 EXPENSE_PAT=<key> EXPENSE_ENGINE_URL=http://127.0.0.1:8002 pytest tests/contract`, `<key>` being the one the last reseed printed. `EXPENSE_ENGINE_URL` names the target (the session guard refuses a contract run without it set to `:8002`); its default is the live `http://127.0.0.1:8000`, so always set it to the `:8002` test engine.

**It refuses to run against the real ledger.** Without `EXPENSE_PAT` the only credential is the developer's own config, so [tests/contract/conftest.py](../tests/contract/conftest.py) aborts the session with a message pointing at the practice database. `EXPENSE_ALLOW_REAL_LEDGER=1` overrides it.

What the suite does: walks real flows (config → ping → bootstrap → accounts/categories create → log → dashboard, plus the transaction cursor against `/count`, the whole lists, the activity window, `POST /transactions/import`, reconciliations and sealed periods, reports), redirects `EXPENSE_CONFIG` to a temp dir, and cleans up best-effort in reverse dependency order. Cleanup means **soft-deletes** — invisible to every client but still in the database — which is why it belongs on the practice database. Run it when engine-shape drift is suspected or before calling a release done; never in CI. It catches what mocks cannot, e.g. `amount_cents` returning as a magnitude unless the read asks for `debit_as_negative`.

**Fixture drift.** The unit suite mocks the engine, so it cannot notice the engine changing shape. [scripts/check_fixture_drift.py](../scripts/check_fixture_drift.py) compares every unit fixture key against the engine's published `openapi.json`; run it after any engine change, against the `:8002` test engine above (its default target): `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002`. The flag stays explicit because the session guard ([.claude/hooks/guard.py](../.claude/hooks/guard.py)) blocks any run of the script without `--engine-url …:8002`. It is not a pytest file, to keep the unit suite hermetic.

**Contract version.** The same run compares the contract's `info.version` with the version saved in [scripts/engine-contract-version](../scripts/engine-contract-version), the version this repo was last checked against: one line holding the version and nothing else, never a copy of the contract. A different version is reported with both numbers (`saved …, engine …`) and fails the run even when every fixture key matches; a missing saved version fails it too. A moved version also prints what changed, read from the contract's own change log (`x-changelog` in `/openapi.json`, which the engine keeps newest first): every entry newer than the saved version, in that order, each as its version and date followed by every change as `kind: text` (the engine sends `kind` as `added`, `changed` or `removed`). It says the whole contract changed instead when the log is missing, empty or not a list, its first entry is not the engine's current version, the saved version is not in it, or an entry newer than the saved version is malformed; the saved entry and older ones are never read. A matching version prints nothing about the version or the log. A run never changes the saved version. Recording one is its own step, which writes the engine's current version and checks nothing else: `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002 --record-version`.

**Unit tests never touch the network.** `tests/unit/` is respx-mocked; autouse fixtures in [tests/unit/conftest.py](../tests/unit/conftest.py) redirect `EXPENSE_CONFIG` and block real sockets. Never bypass them.
