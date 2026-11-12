# The whole app is type-checked, and the running app keeps a log

**Status: approved 2026-11-11, with every question answered as recommended.** It runs after
[Lean docs](lean-docs.md), and [Code conventions B](code-conventions-b.md) follows it. When
done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Counted 2026-11-11:
1. **mypy checks six modules,** about 8% of the app. Over all of `expense/` it reports 115
   errors in 20 files, all in `tui/` (statements.py 24, transactions.py 18, _base.py 15, the
   rest 7 or fewer).
2. **No trail.** The app writes no log. `--verbose` prints requests to stderr, which the running
   TUI swallows, as it does the write-retry notice. A crash leaves only a traceback on exit, so
   a problem in daily use leaves nothing to read afterwards.

## Owner's answers

1. **The log lives at `~/Library/Logs/expense_world/tui.log`,** the Mac's place for logs,
   beside the engine's; Console.app opens it.
2. **It holds:**
   - each request's method, path, status and time;
   - every engine refusal in full;
   - every write retry;
   - every unexpected error, with its traceback.

   With `--verbose`, request and reply bodies go in too. Descriptions and amounts stay out unless asked for.

## What it must do

1. **mypy checks all of `expense/`,** with today's flags, green in pre-commit and CI.
2. **The running app writes a rotating log** (a few files of bounded size) at the place in
   answer 1, holding what answer 2 says.
   - It never holds the token, the Authorization header or the config.
   - The place can be redirected like the config. The unit tests redirect it, so no test writes to the owner's log.
3. **CLAUDE.md's code rules state both,** in a line each; docs/runtime.md holds the log's
   detail.
4. **Nothing else the owner sees changes.**

## How the owner knows it is done

1. mypy over all of `expense/` reports no errors, and pre-commit and CI run it on the whole
   package, with no file list.
2. The tester opens the app against the practice engine and visits each screen. Afterwards the log file exists and holds the requests made. A search of it for the practice key and for `Bearer` finds nothing.
3. `pytest tests/unit`, the live contract suite and the drift script pass.

---

## Tasks

Each task leaves `pytest tests/unit` green and mypy green on everything it covers.

Counted 2026-11-12 after task 5: 18 errors in 5 files; the other 60 modules are checked.

6. mypy: log_bar.py, create_forms.py, statement_upload.py, bank_import.py and
   leftover_lines.py, 18 (6, 4, 4, 2, 2); the file list becomes the whole package and `follow_imports = "silent"`
   goes with it; CLAUDE.md's lint line says so.
7. **The log:**
   - requests, refusals, retries and unexpected errors, at the fixed place, rotating, with no token;
   - the redirect, and the unit tests' redirect;
   - docs/runtime.md.
8. `--verbose` adds request and reply bodies to the log; a test that no token or Authorization
   value reaches it.

## Found along the way

Not built in this spec; sorted when it is done.
