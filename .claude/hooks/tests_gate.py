"""Test gate: the fast unit tests must pass before a commit and before the builder is done.

Wired twice in `.claude/settings.json` (CLAUDE.md "Dev loop" and "How work runs"):

- **PreToolUse Bash:** acts only when the command runs `git commit` (read as `_shell.py`
  describes); any other command passes untouched.
- **SubagentStop** for the builder: runs every time the builder tries to finish, except when
  `stop_hook_active` is true (the builder is already continuing because of this gate), so
  the gate cannot loop.

It runs `.venv/bin/pytest tests/unit -q -x` from the repo root with `.venv/bin` first on
PATH. A failing run exits 2 with the last 40 lines of output on stderr, which blocks the
commit (or keeps the builder working) and shows it why; a passing run exits 0 silently.
A run that outlasts 270 s (inside the hook's 300 s budget) is killed and blocks too.
`EXPENSE_HOOKS_PYTEST` (a shell-quoted command line) and `EXPENSE_HOOKS_PYTEST_TIMEOUT`
(seconds) replace the pytest command and the time limit for the hook tests.
Tests: `tests/unit/test_claude_hooks.py`.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys

from _shell import is_git_commit, read_input, repo_root, venv_env

TAIL_LINES = 40
TIMEOUT_SECONDS = 270.0


def _should_run(data: dict) -> bool:
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        tool_input = data.get("tool_input") or {}
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        return data.get("tool_name") == "Bash" and is_git_commit(str(command))
    if event == "SubagentStop":
        return not data.get("stop_hook_active")
    return False


def main() -> int:
    data = read_input()
    if not _should_run(data):
        return 0
    repo = repo_root()
    override = os.environ.get("EXPENSE_HOOKS_PYTEST")
    command = (
        shlex.split(override)
        if override
        else [str(repo / ".venv" / "bin" / "pytest"), "tests/unit", "-q", "-x"]
    )
    try:
        done = subprocess.run(
            command,
            cwd=repo,
            env=venv_env(repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=float(os.environ.get("EXPENSE_HOOKS_PYTEST_TIMEOUT") or TIMEOUT_SECONDS),
        )
    except subprocess.TimeoutExpired as exc:
        print(
            f'Blocked by CLAUDE.md "Dev loop": `pytest tests/unit` did not finish within '
            f"{exc.timeout:g} s — find the hanging test first.",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        print(
            f'Blocked by CLAUDE.md "Dev loop": could not run the unit tests: {exc}', file=sys.stderr
        )
        return 2
    if done.returncode == 0:
        return 0
    tail = "\n".join(done.stdout.splitlines()[-TAIL_LINES:])
    print(
        'Blocked by CLAUDE.md "Dev loop": `pytest tests/unit` fails — fix it first.\n' + tail,
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
