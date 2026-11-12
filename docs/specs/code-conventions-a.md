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

8. `--verbose` adds request and reply bodies to the log; a test that no token or Authorization
   value reaches it. The token also reaches no traceback: `EngineConnectionError` takes httpx's
   message as its own (expense/errors.py:45-49), so a token pasted with a trailing space would
   ride in a logged traceback (tui/app.py:161-166, errors.py:441-442); a filter in
   expense/applog.py that blanks the token in every record closes every such path.

## Found along the way

Not built in this spec; sorted when it is done.
- **Older `# type: ignore`s mypy no longer needs:** `self.app.after_quit_question(...)` at
  expense/tui/screens/log_bar.py:1051 and setup.py:375 could go through `expense_app(...)` as
  bank_import.py does; modals.py:38-50 keeps four that a Screen-host base could clear.
- **`self._name` shadows Textual's `DOMNode._name`** (the widget's `name`) in `AccountPeek`
  (log_bar.py:687), `EditAccountScreen` (create_forms.py:907) and `StatementLeftoverScreen`
  (leftover_lines.py:468); harmless today, as nothing reads the widget's name, but a rename such
  as `_account_name` keeps the two apart.
- **System ▸ Config `t` saves a pasted token unstripped** (expense/tui/screens/system.py:91-94):
  a trailing space on the paste makes every request fail as a refused header.
- **About 15 `except Exception` blocks show nothing and log nothing** (the rate check, the header
  stats, the name maps: reads.py:645, :662; _base.py:757, :869, :980, :1029; transactions.py:525,
  :533, :546, :706; statements.py:578, :2158, :2727; header.py:97; cursor_list.py:487; app.py:156),
  so a bug inside one never reaches the log.
- **A 5xx whose body is not the engine's error shape** logs only its request line
  (expense/http.py:159-179), not the body the engine sent.
