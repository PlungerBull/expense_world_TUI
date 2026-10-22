# The full test suite runs once per task

**Status: approved by the owner on 2026-10-22; the loop runs its tasks.** Written by the orchestrator from the owner's request in chat on 2026-10-22
("the agents run full test suites all the time, we have to solve that") and the research that
followed. The engine half is expense_world_engine's `docs/specs/full-suite-once.md`. When done,
the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Since the faster-loop work (2026-10-16), the unit suite has grown from about 27 s to about 41 s
(2,608 tests, measured 2026-10-22), and a task still runs it three or four times:

- The tests gate runs it when the builder stops, and again at `git commit`, usually on exactly
  the code it has just passed.
- Builders and reviewers still run it by hand, although `builder.md` and `reviewer.md` tell them
  not to (the session logs since 2026-10-16 show it dozens of times). The librarian does too.

Companies that test at scale do three things this repo doesn't do yet. They never re-test code
that hasn't changed since it passed: Google's build tool, Bazel, caches test results. They
enforce test rules with tooling, not written instructions. And they keep one full run as the
safety net. Commit-time checks stay fast; the full suite runs once when the work is done and
again in CI.

## What it must do

- The whole unit suite runs once per task, when the builder stops. It runs again only if the
  code changed after that, for example after a reviewer sends the task back.
- Written docs never trigger a test run: a change that touches only docs (every `.md` file and
  everything under `docs/`) runs no tests at the builder's stop or at commit. CI still checks
  them on push.
- `git commit` still never lands on failing code. It doesn't rerun a suite that has already
  passed on the same code.
- The builder, reviewer and librarian can't run the whole unit suite by hand. They can still run
  the tests for what they changed (a file, a name filter, or the last failures), and a blocked
  run tells them how.
- The tester and the main session are not affected. The tester's one full run per spec stays.
- No check is dropped: the reviewer still runs on every task, and CI still runs the whole suite
  on every push.

## How the owner knows it is done

- In a task the reviewer approves the first time, the session log shows the whole unit suite ran
  once.
- A `git commit` right after the builder's passing run returns in a few seconds, not about 40,
  even when the orchestrator edited docs in between.
- A commit that changes only docs runs no tests.
- A builder or reviewer running `pytest tests/unit` is blocked, and the message says what to run
  instead.
- CI is green on the push that finishes the spec.

## Not in this spec

- **Running only the tests a change can affect** (`pytest-testmon`). Once the gate skips
  unchanged code, the builder's stop is the only full run. Testmon would only shorten that one
  run, would move the full run to commit, where a failure costs a round trip back to the
  builder, and would add a data file that can go stale. Revisit if the suite passes about 90 s.
- **Making the suite itself faster.** The suite grew by half in six days;
  `pytest tests/unit --durations=20` shows where the time goes. That is separate work, if the
  owner wants it.

## Tasks
