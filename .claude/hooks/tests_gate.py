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

**It skips code it has already passed.** Before running, it computes a fingerprint of:

- the working tree, untracked files that aren't ignored included, with every doc path left
  out (every `*.md` file and everything under `docs/`): a temporary index file starts as a
  copy of the real index (so unchanged files aren't re-read), takes `git add -A`, drops the
  doc paths and gives `git write-tree`. The real index is never touched;
- the installed packages (the `*.dist-info` names in the venv's site-packages) and the venv's
  Python version (`pyvenv.cfg`);
- the pytest command.

A green run saves the fingerprint computed before it in `tests-gate-passed`, in the folder
`git rev-parse --git-dir` names (a worktree keeps its own; it is never committed). When the
gate fires again with the same fingerprint it exits 0 without running pytest, so a change to
docs alone runs no tests. A red, timed-out or failed-to-start run clears the saved one. When
the fingerprint can't be computed (no git, not a repo, a conflicted index, an index that
can't be copied) the gate runs pytest every time and saves nothing; a saved fingerprint that
can't be read matches nothing, and a failed save or clear only means the next gate runs.
Tests: `tests/unit/test_claude_hooks.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _shell import is_git_commit, read_input, repo_root, venv_env

TAIL_LINES = 40
TIMEOUT_SECONDS = 270.0
STAMP_NAME = "tests-gate-passed"
DOC_PATHSPECS = (":(glob)**/*.md", "docs")
_DROP_DOCS = ("rm", "-r", "-q", "-f", "--cached", "--ignore-unmatch", "--", *DOC_PATHSPECS)
# git's location variables: the gate's git calls read the repo it runs in, never these
_GIT_LOCATION_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")


def _should_run(data: dict) -> bool:
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        tool_input = data.get("tool_input") or {}
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        return data.get("tool_name") == "Bash" and is_git_commit(str(command))
    if event == "SubagentStop":
        return not data.get("stop_hook_active")
    return False


def _git(repo: Path, *args: str, index: Path | None = None) -> str | None:
    """`git <args>` in `repo`; its stdout stripped, or None when it fails."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_VARS}
    if index is not None:
        env["GIT_INDEX_FILE"] = str(index)
    try:
        done = subprocess.run(
            ["git", *args], cwd=repo, env=env, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _git_path(repo: Path, *args: str) -> Path | None:
    out = _git(repo, "rev-parse", *args)
    return (repo / out).resolve() if out else None


def _tree(repo: Path, real_index: Path) -> str | None:
    """The working tree's tree id minus the doc paths, built in a throwaway index."""
    with tempfile.TemporaryDirectory(prefix="tests-gate-") as scratch:
        index = Path(scratch) / "index"
        if real_index.exists():
            shutil.copy2(real_index, index)  # keeps the mtime git's stat checks compare to
        if _git(repo, "add", "-A", index=index) is None:
            return None
        if _git(repo, *_DROP_DOCS, index=index) is None:
            return None
        return _git(repo, "write-tree", index=index) or None


def _venv(repo: Path) -> dict[str, object]:
    """The venv's installed packages and its Python version."""
    lib = repo / ".venv" / "lib"
    found = lib.glob("python*/site-packages/*.dist-info")
    packages = sorted(str(p.relative_to(lib)) for p in found)
    try:
        cfg = (repo / ".venv" / "pyvenv.cfg").read_text().splitlines()
    except OSError:
        cfg = []
    version = [line.strip() for line in cfg if line.split("=", 1)[0].strip().startswith("version")]
    return {"packages": packages, "python": version}


def _fingerprint(repo: Path, command: list[str]) -> str | None:
    """The fingerprint, or None when it can't be computed (so the gate runs pytest)."""
    try:
        return _compute(repo, command)
    except (OSError, ValueError):
        return None


def _compute(repo: Path, command: list[str]) -> str | None:
    real_index = _git_path(repo, "--git-path", "index")
    if real_index is None:
        return None
    tree = _tree(repo, real_index)
    if tree is None:
        return None
    parts = {"tree": tree, **_venv(repo), "command": command}
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def _passed(stamp: Path | None, fingerprint: str | None) -> bool:
    """The saved fingerprint matches; one that can't be read matches nothing."""
    if stamp is None or fingerprint is None:
        return False
    try:
        return stamp.read_text().strip() == fingerprint
    except (OSError, ValueError):
        return False


def _save(stamp: Path | None, fingerprint: str | None) -> None:
    """Save a green run's fingerprint; a failed save only means the next gate runs."""
    if stamp is None or fingerprint is None:
        _clear(stamp)
        return
    try:
        stamp.write_text(fingerprint + "\n")
    except OSError:
        _clear(stamp)


def _clear(stamp: Path | None) -> None:
    if stamp is None:
        return
    try:
        stamp.unlink(missing_ok=True)
    except OSError:
        pass


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
    git_dir = _git_path(repo, "--git-dir")
    stamp = git_dir / STAMP_NAME if git_dir else None
    fingerprint = _fingerprint(repo, command) if git_dir else None
    if _passed(stamp, fingerprint):
        return 0
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
        _clear(stamp)
        print(
            f'Blocked by CLAUDE.md "Dev loop": `pytest tests/unit` did not finish within '
            f"{exc.timeout:g} s — find the hanging test first.",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        _clear(stamp)
        print(
            f'Blocked by CLAUDE.md "Dev loop": could not run the unit tests: {exc}', file=sys.stderr
        )
        return 2
    if done.returncode == 0:
        _save(stamp, fingerprint)
        return 0
    _clear(stamp)
    tail = "\n".join(done.stdout.splitlines()[-TAIL_LINES:])
    print(
        'Blocked by CLAUDE.md "Dev loop": `pytest tests/unit` fails — fix it first.\n' + tail,
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
