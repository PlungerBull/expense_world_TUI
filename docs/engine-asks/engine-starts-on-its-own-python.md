# The practice engine starts again, on the Python version its code needs

Raised 2026-09-30.

## Why

Every client checks its work against the practice engine: the engine running on port `8002`
over the disposable `expense_world_test` database. Since a change on 2026-09-30, that engine
crashes as it starts. Earlier on 2026-09-30 the same command started it without trouble.

The start command, run from the engine checkout:

```
SUPABASE_DB_URL=postgresql://expense_engine@127.0.0.1:5432/expense_world_test \
  ADMIN_DB_URL=postgresql://<owner>@127.0.0.1:5432/expense_world_test \
  .venv/bin/python -m uvicorn app.main:app --port 8002
```

The end of its traceback:

```
  File ".../app/main.py", line 18, in <module>
    from app.routers import (
  File ".../app/routers/accounts.py", line 11, in <module>
    from app.helpers import accounts as accounts_service
  File ".../app/helpers/accounts.py", line 44, in <module>
    from app.helpers.categories import ensure_system_category
  File ".../app/helpers/categories.py", line 42, in <module>
    def _reject_reserved_name(name: str, own_key: SystemCategoryKey | None = None) -> None:
TypeError: unsupported operand type(s) for |: 'EnumMeta' and 'NoneType'
```

The interpreter in the traceback is Python 3.9, from the checkout's `.venv`. The engine's code
uses the `X | None` type syntax, which Python runs only from 3.10. Until the engine starts, no
client can run its live contract checks or record the engine's current contract version
(`7e7cfb294fe255c7`).

## The ask

1. The engine's `.venv` runs a Python version the engine's code supports — 3.11 or newer
   recommended, matching the clients.
2. The engine states its minimum Python version where its install reads it (for example
   `requires-python` in its project metadata), so an install on an older Python fails at once
   with a clear message instead of a traceback at start-up.
3. If the start command above is no longer the right way to start the practice engine, the
   engine's own docs give the new one, and the owner passes it on.

## Done when

- The command above starts the engine on `8002`, and `GET /health` answers `{"status":"ok"}`.
- Installing the engine on Python 3.9 fails during the install and names the minimum version.

## What the CLI removes once it lands

Nothing: the CLI has no workaround. Its live contract checks and the contract version update
are paused until the practice engine starts again.
