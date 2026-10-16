# A faster agent loop

**Status: current.** Written by the orchestrator from the owner's answers in chat on
2026-10-16 (the owner approved items 2, 3 and 5 of the loop assessment and asked for the
broken guard test to be fixed). When done, the why moves to [decisions.md](../decisions.md) and
this file is deleted.

---

## What it must do

The agent loop spends most of its time waiting on `pytest tests/unit`: about 2¾ minutes a
run, run serially on a 10-core Mac, four or more times per task. Cut that wait without
dropping any check.

- The unit suite runs in parallel everywhere it runs: the tests gate, CI and by hand.
- The error-shape guard (`test_every_command_has_an_error_shape_test`) gives the right answer
  however the suite is run: in parallel, whole, one file, or filtered. Today it fails when run
  alone or in parallel.
- Starting and stopping the practice engine on `:8002` is one command, not a tester agent.

## How the owner knows it is done

- `pytest tests/unit` (the plain command) finishes in well under a minute on the owner's Mac.
- `pytest tests/unit/test_command_surface.py` passes or skips, and never fails on a gap that is
  really just the rest of the suite.
- CI is green on the push that finishes the spec.
- One command starts the practice engine and prints its key; one command stops it.

## Tasks

Approved by the owner in chat, 2026-10-16.

3. **Practice engine in one command.** A script in `scripts/` that starts the practice engine
   on `:8002` exactly as [runtime.md](../runtime.md) "Working against the live engine" says
   (reseed included, key printed to the terminal and never written to a file) and stops the
   engine it started. The guard lets the orchestrator and every worker run it, and nothing else
   in the engine checkout changes. CLAUDE.md "How work runs" says the orchestrator runs it
   instead of sending a tester to start or stop the engine.
   Passes if: the script's up and down work against the real engine checkout (tester shows it);
   `tests/unit/test_claude_hooks.py` covers that the guard allows the script and still blocks
   what it blocked before; runtime.md and CLAUDE.md name the script as the way to start and stop.
4. **Timing races in the TUI tests.** `tests/unit/test_tui_system.py::test_config_screen_shows_only_the_engine_connection`
   failed in CI on Python 3.11 (run of 2026-10-16 05:00 UTC, commit 1e080d4: the card rendered
   empty, `assert ('engine url' in '')`) while passing locally. Under `--cov` (what CI runs) more
   races show: `test_tui_log_bar.py::test_ctrl_s_writes_every_row_in_one_batch` fails every time
   with `-n0 --cov -k ctrl_s_writes` (`NoMatches '#field' on LogBarScreen`, from
   `_peek_loaded` → `_refresh_view` at expense/tui/screens/log_bar.py:1275 after the screen is
   gone), and intermittently `test_settings_missing_is_said_once_not_per_row`,
   `test_a_failed_save_first_keeps_the_screen_so_the_error_is_readable`,
   `test_tui_reconciliations.py::test_enter_reads_that_account_and_opens_the_panel_with_the_cursor_in_it`,
   `test_tui_bulk_edit.py::test_space_is_inert_and_unadvertised_where_no_screen_owns_a_selection`.
   Find each cause and fix it where it lives (a screen that updates after it is gone is a screen
   bug; a test that reads before the screen settled is a test bug). Covers todo.md's "Three
   flaky unit tests" item where it overlaps.
   Passes if: each cause is named in the report; `pytest tests/unit --cov` passes 10 runs in a
   row and `pytest tests/unit -n0 --cov` passes 3 in a row; CI is green on the push.
