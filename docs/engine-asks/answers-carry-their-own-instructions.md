# An answer to a client carries its own instructions, never a pointer into the engine's files

Raised 2026-10-11.

## Why

No client reads a file in the engine's checkout: a client learns the engine only from its
published contract and from the answers the engine coders write for it. An answer that says
"do it as engine file X shows" therefore cannot be followed, and cannot be checked either.

The answer "The engine runs on Python 3.12" (shipped 2026-10-11) does this. Its instruction is
to start the practice engine exactly as the header of the engine's practice-user seed script
shows. The client cannot open that header, so it cannot tell whether the command it already
uses is the same one.

The command the CLI uses, run from the engine checkout, which started the engine cleanly on
2026-10-11 and answered `GET /health` with `{"status":"ok"}`:

```
SUPABASE_DB_URL=postgresql://expense_engine@127.0.0.1:5432/expense_world_test \
  ADMIN_DB_URL=postgresql://<owner>@127.0.0.1:5432/expense_world_test \
  .venv/bin/python -m uvicorn app.main:app --port 8002
```

## The ask

1. Confirm that the command above is the one the engine intends for the practice engine, or
   give the right one in full.
2. From now on, an answer written for a client spells out every command, route, field and
   value it relies on, and names no engine file path.

## Done when

- The owner has the confirmed start command in writing, in full.
- The next answer written for a client names no engine file.

## What the CLI removes once it lands

Nothing: the CLI has no workaround. If the confirmed command differs from the one above, the
CLI changes its ops guide and its session guard to match.
