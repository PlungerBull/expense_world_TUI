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
