"""PostToolUse lint: ruff-checks the Python file an Edit/Write/MultiEdit just changed.

Wired in `.claude/settings.json` for Edit, Write and MultiEdit. For a `.py` file inside the
repo it runs `ruff check` and `ruff format --check` on that one file (CLAUDE.md "Dev loop"
lint/format). The edit has already happened, so this reports rather than blocks: problems go
back to the model as PostToolUse `additionalContext` JSON on stdout; a clean file, a non-`.py`
file or a file outside the repo produces no output. It always exits 0.

The ruff binary is the repo's `.venv/bin/ruff`; `EXPENSE_HOOKS_RUFF` overrides it for the
hook tests. Tests: `tests/unit/test_claude_hooks.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from _shell import is_within, read_input, repo_root, venv_env


def main() -> int:
    data = read_input()
    tool_input = data.get("tool_input") or {}
    raw = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not raw or not str(raw).endswith(".py"):
        return 0
    repo = repo_root()
    path = Path(str(raw)).resolve()
    if not is_within(path, repo) or not path.is_file():
        return 0
    ruff = os.environ.get("EXPENSE_HOOKS_RUFF") or str(repo / ".venv" / "bin" / "ruff")
    problems: list[str] = []
    for args in (["check", "--quiet", str(path)], ["format", "--check", "--quiet", str(path)]):
        try:
            done = subprocess.run(
                [ruff, *args], cwd=repo, env=venv_env(repo), capture_output=True, text=True
            )
        except OSError as exc:
            problems.append(f"ruff could not run: {exc}")
            break
        if done.returncode != 0:
            output = (done.stdout + done.stderr).strip()
            problems.append(f"$ ruff {' '.join(args)}\n{output or 'failed'}")
    if problems:
        message = "ruff found problems in the file just edited — fix them:\n" + "\n\n".join(
            problems
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": message,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
