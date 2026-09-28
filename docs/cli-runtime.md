# CLI Runtime Behavior

How the CLI behaves at runtime — read/write semantics, error handling, working against the live engine. Companion to [cli-spec.md](cli-spec.md) (commands and flags).

## Overview

The CLI holds no business logic and **no local state beyond `~/.expense-config`** — no cache, no offline write queue ([decisions.md](decisions.md) "All reads are live"). The engine is the only authoritative store and runs on the same machine (`http://127.0.0.1:8000`), so every read is a live loopback HTTP call.

Everything here applies equally to the TUI (`expense world`) and the importers (`expense import`): they are clients of the same HTTP client and `fetch_*` functions, not separate runtimes.

## Read semantics

Every read command is a direct `GET`. What a command prints is what the engine computed at that moment, including home-currency figures (converted engine-side at read time).

- The engine's responses are IDs-only; list renderers resolve names via live reference-list fetches (`load_account_name_map` / `load_category_name_map` / `load_hashtag_name_map` in [expense/commands/_resource.py](../expense/commands/_resource.py)), degrading to 8-char short ids on failure (cli-spec "Output conventions").
- **Deleted is deleted.** A deleted row is invisible to every client — no list returns it, its get is a 404 — and no command restores it. The engine keeps the row in its table; undeleting is an operator task (engine repo `deploy/local/README.md`, "Undeleting a row"). `expense activity list` still shows a deleted row's history.
- Transaction reads always send `debit_as_negative=true`, so the request pins the sign rather than depending on the engine default.

### Three list shapes

No list pages by position; every list is one of three shapes, each read its own way. The contract is engine-spec *Base Conventions* ([../../expense_world_engine/docs/engine-spec.md](../../expense_world_engine/docs/engine-spec.md)); what each command prints under its table is cli-spec "Pagination (human mode)".

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

**Bulk writes** go through one shared path, [expense/batch_write.py](../expense/batch_write.py), used by `expense import sheet --apply` and the TUI's LOG bar (`ctrl+s`). Rows go out in chunked `POST /transactions/batch` calls (default 200/request), each with its own idempotency key. A batch is **atomic** — one bad row and none of the chunk is written — so a refused chunk is re-posted one row per batch, letting the good rows land and making the bad one name itself. A `409` there is **not** a failure: ids are client-supplied, so a replayed id means the row is already in. That is what makes a retry after a half-written run safe and why `expense import sheet` re-runs converge instead of duplicating.

## Engine errors surface cleanly

The engine's `{ error: { code, message, fields } }` envelope is rendered intact (format in cli-spec "Output conventions"); `--json` prints it verbatim. Commands add a hint line for known refusals (e.g. "revert first" on a locked reconciliation) without replacing the engine's message.

## Working against the live engine

There is exactly **one engine: the local deployment** (`http://127.0.0.1:8000`, launchd service on the owner's Mac — engine repo `deploy/local/README.md`). No staging, no sandbox — every PAT belongs to a real user and every write lands in the one true ledger.

**Developer default is live.** Plain `expense …` commands read `~/.expense-config` — the real credential. Reads are safe; ad-hoc writes are real writes. To inspect behaviour, use `--verbose` on a read, or the unit suite.

**Isolation levers, weakest to strongest:**

- `EXPENSE_CONFIG` redirects the config file. This isolates *local config only* — the same PAT still writes to the same ledger.
- A **separate PAT for a separate user** is data isolation within the same database (PATs: cli-spec "Auth model").
- **A second engine over the `expense_world_test` database** — how the contract suite runs. Nothing it writes can reach the real ledger, and `deploy/local/create-test-db.sh --force` wipes it. In the engine repo, `deploy/local/seed-test-user.sh` seeds a practice user, a PAT and a copy of `exchange_rates` (`--force` reseeds: it drops the practice user's rows, revokes its old PATs and prints a fresh one), then

      SUPABASE_DB_URL=postgresql://expense_engine@127.0.0.1:5432/expense_world_test \
        ADMIN_DB_URL=postgresql://<owner>@127.0.0.1:5432/expense_world_test \
        python -m uvicorn app.main:app --port 8002

  (`python -m uvicorn`, not the console script — engine `deploy/local/README.md` "TCC".)

  **Port 8002, not 8001.** `:8001` is `todo_world_engine`'s — point the suite there and every request 404s while the refusal guard and the health check both look fine.

  **Connect as `expense_engine`, not the owner.** The engine refuses to start as a SUPERUSER, which would bypass every RLS policy. `postgresql:///expense_world_test` connects as the owner and hits that guard.

**The contract suite** (`tests/contract/`) hits a real engine and is double-gated: `PYTEST_LIVE=1 EXPENSE_PAT=<token> EXPENSE_ENGINE_URL=http://127.0.0.1:8002 pytest tests/contract`. `EXPENSE_ENGINE_URL` names the target; its default is the live `http://127.0.0.1:8000`, so always set it to the `:8002` test engine.

**It refuses to run against the real ledger.** Without `EXPENSE_PAT` the only credential is the developer's own config, so [tests/contract/conftest.py](../tests/contract/conftest.py) aborts the session with a message pointing at the practice database. `EXPENSE_ALLOW_REAL_LEDGER=1` overrides it.

What the suite does: walks real flows (config → ping → bootstrap → accounts/categories create → log → dashboard, plus the transaction cursor against `/count`, the whole lists, the activity window, `POST /transactions/import`, reconciliations and sealed periods, reports), redirects `EXPENSE_CONFIG` to a temp dir, and cleans up best-effort in reverse dependency order. Cleanup means **soft-deletes** — invisible to every client but still in the database — which is why it belongs on the practice database. Run it when engine-shape drift is suspected or before calling a release done; never in CI. It catches what mocks cannot, e.g. `amount_cents` returning as a magnitude unless the read asks for `debit_as_negative`.

**Fixture drift.** The unit suite mocks the engine, so it cannot notice the engine changing shape. [scripts/check_fixture_drift.py](../scripts/check_fixture_drift.py) compares every unit fixture key against the engine's published `openapi.json`; run it after any engine change, against the `:8002` test engine above (`--engine-url http://127.0.0.1:8002` — its default target is the live `:8000`). It is not a pytest file, to keep the unit suite hermetic.

**Unit tests never touch the network.** `tests/unit/` is respx-mocked; autouse fixtures in [tests/unit/conftest.py](../tests/unit/conftest.py) redirect `EXPENSE_CONFIG` and block real sockets. Never bypass them.
