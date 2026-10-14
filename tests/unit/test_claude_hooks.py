"""The Claude Code hooks in `.claude/hooks/`: every guard tripped, every neighbour let through.

Each hook runs as a subprocess with crafted hook JSON on stdin, exactly as Claude Code runs
it. The repo and home folder are a throwaway tree under `tmp_path` (`CLAUDE_PROJECT_DIR`
and `EXPENSE_HOOKS_HOME`), so nothing here reads the real home folder or `~/.expense-config`,
and no engine is called. `tests_gate.py` runs a stub instead of the real suite.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"
TEST_DB = "postgresql://expense_engine@127.0.0.1:5432/expense_world_test"
ADMIN_TEST_DB = "postgresql://owner@127.0.0.1:5432/expense_world_test"
START_PYTHON = ".venv/bin/python"
UVICORN = f"{START_PYTHON} -m uvicorn app.main:app --port 8002"
START_TEST_ENGINE = f"SUPABASE_DB_URL={TEST_DB} ADMIN_DB_URL={ADMIN_TEST_DB} {UVICORN}"
SCRATCH = "/private/tmp/claude-501/scratchpad"
IN_ENGINE = "cd ../expense_world_engine && "
SEED = "../expense_world_engine/deploy/local/seed-test-user.sh --force"


class Sandbox:
    """A fake home folder holding the repo and its sibling engine checkout."""

    def __init__(self, tmp_path: Path) -> None:
        self.home = (tmp_path / "home").resolve()
        self.repo = self.home / "Documents" / "expense_world_CLI"
        self.engine = self.home / "Documents" / "expense_world_engine"
        self.repo.mkdir(parents=True)
        self.engine.mkdir(parents=True)

    def fill(self, text: str) -> str:
        return text.format(home=self.home, repo=self.repo, engine=self.engine)

    def run(self, script: str, payload: object, **env: str) -> subprocess.CompletedProcess[str]:
        """Run a hook with `payload` as its JSON input (a `str` goes to stdin as is)."""
        full_env = {
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(self.repo),
            "EXPENSE_HOOKS_HOME": str(self.home),
            "PYTHONDONTWRITEBYTECODE": "1",
            **env,
        }
        return subprocess.run(
            [sys.executable, str(HOOKS / script)],
            input=payload if isinstance(payload, str) else json.dumps(payload),
            capture_output=True,
            text=True,
            env=full_env,
            timeout=60,
        )

    def guard(self, tool: str, tool_input: dict, *, agent: str | None = None, cwd: str = ""):
        payload = {
            "session_id": "s",
            "hook_event_name": "PreToolUse",
            "cwd": self.fill(cwd) if cwd else str(self.repo),
            "tool_name": tool,
            "tool_input": {k: self.fill(v) for k, v in tool_input.items()},
        }
        if agent:
            payload["agent_type"] = agent
        return self.run("guard.py", payload)


@pytest.fixture
def box(tmp_path):
    return Sandbox(tmp_path)


def _blocked(result, rule: str) -> None:
    assert result.returncode == 2, (result.returncode, result.stderr)
    reason = result.stderr.strip()
    assert reason.startswith("Blocked by CLAUDE.md"), reason
    assert rule in reason, reason
    assert "\n" not in reason, "the reason is one line"


def _allowed(result) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stdout == "" and result.stderr == ""


LIVE = "Careful running live"
STAY = "Stay inside this repo"
GIT = "Dev loop"

# ---------------------------------------------------------------------------
# guard.py — Bash, blocked
# ---------------------------------------------------------------------------

BLOCKED_BASH = [
    ("curl http://127.1:8000/v1/accounts", LIVE),
    ("curl 'http://[::]:8000/health'", LIVE),
    ("curl http://example.local:8000/health", LIVE),
    ("lsof -i tcp:8000", LIVE),
    ("lsof -ti tcp:8000 | xargs kill", LIVE),
    ("kill 12345", STAY),  # only the tester stops processes
    ("pkill -f uvicorn", STAY),
    ("killall python", STAY),
    ("lsof -ti :8002 | xargs kill", STAY),
    ("git push --mirror", GIT),
    ("lsof -ti :8000", LIVE),
    ("kill $(lsof -ti :8000)", LIVE),
    ("git push -uf origin main", GIT),
    ("git status; git push --force # it's fine", GIT),  # shlex fails on the lone quote
    # live engine
    ("curl http://127.0.0.1:8000/health", LIVE),
    ("curl -s localhost:8000/v1/accounts | jq .", LIVE),
    ("python -c 'import httpx; httpx.get(\"http://0.0.0.0:8000\")'", LIVE),
    ("python scripts/check_fixture_drift.py", LIVE),
    ("./scripts/check_fixture_drift.py", LIVE),
    (".venv/bin/python3 -u scripts/check_fixture_drift.py", LIVE),
    ("python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8000", LIVE),
    (".venv/bin/pytest tests/contract", LIVE),
    ("PYTEST_LIVE=1 EXPENSE_PAT=x pytest tests/contract -q", LIVE),
    ("PYTEST_LIVE=1 EXPENSE_PAT=x python -m pytest", LIVE),
    ("EXPENSE_ENGINE_URL=http://127.0.0.1:8000 pytest tests/contract", LIVE),
    # real config
    ("expense", LIVE),
    (".venv/bin/expense", LIVE),
    ("expense import sheet s.xlsx --apply", LIVE),
    ("python -m expense", LIVE),
    ("EXPENSE_CONFIG=~/.expense-config expense", LIVE),
    ("EXPENSE_CONFIG={home}/.expense-config .venv/bin/expense import sheet s.xlsx", LIVE),
    ("cat ~/.expense-config", LIVE),
    ("cat $HOME/.expense-config", LIVE),
    ("cp {home}/.expense-config {repo}/cfg", LIVE),
    # outside the repo
    ("cat ~/Documents/notes.txt", STAY),
    ("ls {home}/Desktop", STAY),
    ("cat ../../secret.txt", STAY),
    ("cd ~/Desktop && ls", STAY),
    ("grep -r token < ~/notes.txt", STAY),
    ("echo x > ~/out.txt", STAY),
    ("git -C ../other_repo status", STAY),
    # the engine checkout is closed: no writes
    ("echo x > ../expense_world_engine/app/x.py", STAY),
    ("cd ../expense_world_engine && rm -rf app", STAY),
    ("sed -i '' s/a/b/ ../expense_world_engine/app/main.py", STAY),
    ("cd ../expense_world_engine && git pull", STAY),
    ("git -C ../expense_world_engine commit -am x", STAY),
    ("cd {engine} && " + START_TEST_ENGINE, STAY),  # not the tester
    ("find ../expense_world_engine -name '*.pyc' -delete", STAY),
    # ... and no reads, by any path spelling or after a `cd`
    ("cat ../expense_world_engine/docs/engine-spec.md", STAY),
    ("cat {engine}/app/main.py", STAY),
    ("cat ~/Documents/expense_world_engine/app/main.py", STAY),
    ("head -50 $HOME/Documents/expense_world_engine/README.md", STAY),
    ("tail -n 20 ../expense_world_engine/app/main.py", STAY),
    ("less ../expense_world_engine/app/main.py", STAY),
    ("grep -rn uvicorn {engine}/deploy", STAY),
    ("rg openapi ../expense_world_engine", STAY),
    ("find ../expense_world_engine -name '*.md'", STAY),
    ("ls ../expense_world_engine", STAY),
    ("sed -n 1,20p ../expense_world_engine/app/main.py", STAY),
    ("awk 'NR<5' ../expense_world_engine/app/main.py", STAY),
    ("wc -l < ../expense_world_engine/app/main.py", STAY),
    ("git -C ../expense_world_engine log --oneline -5", STAY),
    ("git -C {engine} show HEAD:app/main.py", STAY),
    ("git -C ../expense_world_engine diff HEAD~1", STAY),
    ("cd ../expense_world_engine && ls deploy/local", STAY),
    ("cd ../expense_world_engine && git log --oneline -5", STAY),
    ("cd {engine} && cat app/main.py", STAY),
    ("cd ../expense_world_engine", STAY),  # only the tester goes there
    ("cd . <(cat ../expense_world_engine/app/main.py >&2)", STAY),  # not just a `cd`
    ("cd {repo} ../expense_world_engine/app/main.py", STAY),
    # relative paths are read against any folder outside the repo; a bare `cd` goes home
    ("cd && cat Documents/expense_world_engine/app/main.py", STAY),
    ("cd {home}/.. && cat home/Documents/expense_world_engine/app/main.py", STAY),
    ("cd {home}/.. && grep -rn uvicorn home/Documents/expense_world_engine", STAY),
    # git: force-push and history rewrites
    ("git push --force", GIT),
    ("git push -f origin main", GIT),
    ("git push --force-with-lease origin main", GIT),
    ("git push origin +main", GIT),
    ("git commit --amend --no-edit", GIT),
    ("git rebase -i HEAD~3", GIT),
    ("git reset --hard HEAD~1", GIT),
    ("git filter-branch --tree-filter x", GIT),
    ("git filter-repo --path x", GIT),
    ("git update-ref refs/heads/main HEAD~1", GIT),
    # git: new branches
    ("git branch feature", GIT),
    ("git checkout -b feature", GIT),
    ("git switch -c feature", GIT),
    ("git worktree add .claude/worktrees/x", GIT),
    ("git worktree add -b x --detach .claude/worktrees/x", GIT),
    # git: skipping the pre-commit checks
    ("git commit --no-verify -m x", GIT),
    ("git commit -n -m x", GIT),
    ("git commit -anm x", GIT),
    ("SKIP=gitleaks git commit -m x", GIT),
    ("export SKIP=ruff && git commit -m x", GIT),
    ("git push --no-verify", GIT),
    ("git config core.hooksPath /dev/null", GIT),
    ("git -c core.hooksPath=/dev/null commit -m x", GIT),
]


@pytest.mark.parametrize(("command", "rule"), BLOCKED_BASH)
def test_guard_blocks_bash(box, command, rule):
    _blocked(box.guard("Bash", {"command": command}), rule)


# ---------------------------------------------------------------------------
# guard.py — Bash, allowed neighbours
# ---------------------------------------------------------------------------

ALLOWED_BASH = [
    # naming the drift script or the contract suite is not running it
    "grep -n default scripts/check_fixture_drift.py",
    "git diff scripts/check_fixture_drift.py",
    "sed -n 1,40p scripts/check_fixture_drift.py",
    "cat scripts/check_fixture_drift.py",
    "grep -rn EXPENSE_ENGINE_URL tests/contract",
    "git diff tests/contract/conftest.py",
    "echo 'engine on :8000'",
    "printf ':8000\\n'",
    "awk '/:8000/' docs/cli-runtime.md",
    "python -c 'print(\"12:30:8000\")'",
    "python -c 'print(8000000)'",
    "git push -u origin main",
    "git push -o ci.skip origin main",
    "git commit -m 'note: SKIP=ruff is banned here'",
    "grep -n :8000 docs/cli-runtime.md",
    "curl http://127.0.0.1:8002/health",
    "python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002",
    "python scripts/check_fixture_drift.py --engine-url=http://127.0.0.1:8002",
    "PYTEST_LIVE=1 EXPENSE_PAT=x EXPENSE_ENGINE_URL=http://127.0.0.1:8002 pytest tests/contract",
    ".venv/bin/pytest tests/unit -q",
    "grep -rn 127.0.0.1:8000 docs",
    "grep -n expense-config .gitignore",
    f"EXPENSE_CONFIG={SCRATCH}/cfg expense",
    f"export EXPENSE_CONFIG={SCRATCH}/cfg && .venv/bin/expense import sheet s.xlsx",
    "cat ~/.claude/agents/builder.md",
    "ls /opt/homebrew/bin && echo x > /dev/null",
    f"echo x > {SCRATCH}/x.txt",
    "ruff check . && ruff format .",
    "git worktree add --detach .claude/worktrees/x",
    "git commit -m 'plain commit'",
    "git commit -am 'fix -n handling'",
    "git commit -m \"$(cat <<'EOF'\nsubject\n\ngit rebase and 127.0.0.1:8000 in prose\nEOF\n)\"",
    "PATH=$PWD/.venv/bin:$PATH git commit -m x",
    "git push",
    "git push origin main",
    "git branch",
    "git branch -a",
    "git branch -d old",
    "git checkout main",
    "git checkout -- expense/http.py",
    "git reset HEAD expense/http.py",
    "git status --short",
]


@pytest.mark.parametrize("command", ALLOWED_BASH)
def test_guard_allows_bash(box, command):
    _allowed(box.guard("Bash", {"command": command}))


# ---------------------------------------------------------------------------
# guard.py — the tester exception
# ---------------------------------------------------------------------------

TESTER_ALLOWED = [
    ("lsof -ti :8002 | xargs kill", "{engine}"),
    ("curl -s http://127.0.0.1:8002/health", "{engine}"),
    ("cd ../expense_world_engine && " + START_TEST_ENGINE, ""),
    ("cd {engine} && " + START_TEST_ENGINE + f" > {SCRATCH}/engine.log 2>&1 &", ""),
    (START_TEST_ENGINE, "{engine}"),
    # one test URL is enough: the engine refuses to start when its two URLs differ
    (f"cd ../expense_world_engine && SUPABASE_DB_URL={TEST_DB} {UVICORN}", ""),
    (f"cd ../expense_world_engine && ADMIN_DB_URL={ADMIN_TEST_DB} {UVICORN}", ""),
    ("cd ../expense_world_engine && deploy/local/seed-test-user.sh --force", ""),
    ("bash deploy/local/seed-test-user.sh --force", "{engine}"),
    ("kill 12345", "{engine}"),
    ("kill -TERM 12345", ""),
    ("lsof -t -i :8002 | xargs -r kill", "{engine}"),
    ("curl -sSf --max-time 5 http://localhost:8002/health", "{engine}"),
    ("curl --silent --fail -m 2 http://127.0.0.1:8002/health", "{engine}"),
    # the seed by every path spelling, and its key redacted or dropped on the way out
    ("{engine}/deploy/local/seed-test-user.sh --force", ""),
    ("~/Documents/expense_world_engine/deploy/local/seed-test-user.sh --force", ""),
    ("../expense_world_engine/deploy/local/seed-test-user.sh --force", ""),
    ("bash {engine}/deploy/local/seed-test-user.sh --force", ""),
    (
        "cd ../expense_world_engine && deploy/local/seed-test-user.sh --force "
        "| sed 's/ewe_pat_[A-Za-z0-9_]*/ewe_pat_<redacted>/g'",
        "",
    ),
    (
        "cd ../expense_world_engine && deploy/local/seed-test-user.sh --force 2>&1 "
        "| grep -v ewe_pat_ | tail -n 5",
        "",
    ),
    ("cd ../expense_world_engine && deploy/local/seed-test-user.sh --force > /dev/null", ""),
    ("deploy/local/seed-test-user.sh --force | sed -E -e 's|ewe_pat_.*|<key>|'", "{engine}"),
    ("deploy/local/seed-test-user.sh --force | head -3", "{engine}"),
    ("cd ../expense_world_engine && sleep 2 && true", ""),
    ("cd $HOME/Documents/expense_world_engine && deploy/local/seed-test-user.sh --force", ""),
    (SEED + " 2>&1 | sed 's/ewe_pat_.*$/<key>/' > /dev/null", ""),
]


@pytest.mark.parametrize(("command", "cwd"), TESTER_ALLOWED)
def test_guard_lets_the_tester_run_the_test_engine(box, command, cwd):
    _allowed(box.guard("Bash", {"command": command}, agent="tester", cwd=cwd))


TESTER_BLOCKED = [
    # curl in the engine checkout: allowlisted flags and :8002 URLs only
    ("cd ../expense_world_engine && curl --output=x.json http://127.0.0.1:8002/health", STAY),
    ("cd ../expense_world_engine && curl -sox.json http://127.0.0.1:8002/health", STAY),
    ("cd ../expense_world_engine && curl --dump-header=h.txt http://127.0.0.1:8002/health", STAY),
    (
        "cd ../expense_world_engine && curl --url=http://127.1:8000/v1/accounts "
        "http://127.0.0.1:8002/health",
        LIVE,
    ),
    (
        "cd ../expense_world_engine && curl --url=http://127.0.0.1:8003/ "
        "http://127.0.0.1:8002/health",
        STAY,
    ),
    ("cd ../expense_world_engine && curl -m http://127.0.0.1:8002/health", STAY),
    # stopping processes: numeric pids and the :8002 lsof pipe only
    ("kill -TERM $PID", STAY),
    ("pkill -f 'uvicorn app.main:app --port 8002'", STAY),
    ("pkill -f 'uvicorn|8002'", STAY),
    ("killall python", STAY),
    ("xargs kill < pids.txt", STAY),
    ("lsof -ti tcp:8000 | xargs kill", LIVE),
    # env names are case-insensitive to the engine
    (
        f"cd ../expense_world_engine && admin_db_url=postgresql://o@127.0.0.1:5432/expense_world "
        f"{START_TEST_ENGINE}",
        STAY,
    ),
    (
        f"cd ../expense_world_engine && SUPABASE_DB_URL=postgresql://expense_engine@127.0.0.1"
        f":5432/expense_world {UVICORN}",
        STAY,
    ),
    (
        "cd ../expense_world_engine && PYTHONPATH=/private/tmp/x "
        f"SUPABASE_DB_URL={TEST_DB} {UVICORN}",
        STAY,
    ),
    (f"cd ../expense_world_engine && FOO_URL={TEST_DB} {UVICORN}", STAY),
    # a `*_DB_URL` name the engine ignores leaves both real URLs to `.env`
    (f"cd ../expense_world_engine && FOO_DB_URL={TEST_DB} {UVICORN}", STAY),
    (
        f"cd ../expense_world_engine && SUPABASE_DB_URL={TEST_DB} OTHER_DB_URL=postgresql://"
        f"expense_engine@127.0.0.1:5432/expense_world {UVICORN}",
        STAY,
    ),
    (
        f"cd ../expense_world_engine && SUPABASE_DB_URL={TEST_DB} "
        + UVICORN.replace("8002", "8001"),
        STAY,
    ),
    ("cd ../expense_world_engine && curl -X POST http://127.0.0.1:8002/v1/accounts", STAY),
    ("cd ../expense_world_engine && curl -o x http://127.0.0.1:8002/health", STAY),
    ("lsof -ti :8000 | xargs kill", LIVE),
    ("cd ../expense_world_engine && " + UVICORN.replace("8002", "8000"), STAY),
    ("cd ../expense_world_engine && " + UVICORN, STAY),  # no test-db env
    (
        "cd ../expense_world_engine && SUPABASE_DB_URL=postgresql://expense_engine@127.0.0.1"
        f":5432/expense_world ADMIN_DB_URL={ADMIN_TEST_DB} {UVICORN}",
        STAY,
    ),
    ("cd ../expense_world_engine && " + START_TEST_ENGINE + " > engine.log", STAY),
    ("cd ../expense_world_engine && deploy/local/seed-test-user.sh", STAY),
    ("cd ../expense_world_engine && deploy/local/create-test-db.sh --force", STAY),
    ("cd ../expense_world_engine && pip install httpx", STAY),
    ("cd ../expense_world_engine && git pull", STAY),
    # the tester reads no engine file either
    ("cd ../expense_world_engine && cat app/main.py", STAY),
    ("cd ../expense_world_engine && ls", STAY),
    ("cd ../expense_world_engine && git log --oneline -5", STAY),
    ("cd ../expense_world_engine && sed -n 1p app/main.py", STAY),
    ("cd ../expense_world_engine && sed 's/a/b/' app/main.py", STAY),
    ("cd ../expense_world_engine && sed 's/a/b/w out.txt'", STAY),
    ("cd ../expense_world_engine && sed -f script.sed", STAY),
    ("cd ../expense_world_engine && sed 's/a/b/' < app/main.py", STAY),
    ("cd ../expense_world_engine && grep -r uvicorn", STAY),
    ("cd ../expense_world_engine && grep uvicorn app/main.py", STAY),
    ("cd ../expense_world_engine && grep -f patterns.txt", STAY),
    ("cd ../expense_world_engine && grep '*'", STAY),
    ("cd ../expense_world_engine && tail README.md", STAY),
    ("cd ../expense_world_engine && head -n 5 README.md", STAY),
    ("cd ../expense_world_engine && echo *", STAY),
    ("cd ../expense_world_engine && deploy/local/seed-test-user.sh --force | tee key.txt", STAY),
    ("cd ../expense_world_engine && deploy/local/seed-test-user.sh --force > key.txt", STAY),
    ("cat ../expense_world_engine/docs/engine-spec.md", STAY),
    ("grep -rn uvicorn {engine}/deploy", STAY),
    ("git -C ../expense_world_engine log -1", STAY),
    # substitutions, extra arguments and env prefixes do not ride on an allowed command
    (IN_ENGINE + "true <(cat app/main.py >&2)", STAY),
    (IN_ENGINE + "sleep 0 <(cat app/main.py >&2)", STAY),
    (IN_ENGINE + "true `cat app/main.py >&2`", STAY),
    (IN_ENGINE + 'true "$(cat app/main.py >&2)"', STAY),
    (IN_ENGINE + "true app/main.py", STAY),
    (IN_ENGINE + "sleep 1 app/main.py", STAY),
    (IN_ENGINE + "sleep x", STAY),
    (IN_ENGINE + "cd deploy local", STAY),
    (IN_ENGINE + "GREP_OPTIONS=-r grep uvicorn", STAY),
    ("export GREP_OPTIONS=-r && " + IN_ENGINE + "grep uvicorn", STAY),
    (IN_ENGINE + "grep $PATTERN", STAY),
    (IN_ENGINE + 'sed "s/a/$X/"', STAY),
    (IN_ENGINE + "sed 's?a?b?'", STAY),
    (IN_ENGINE + "sed 's*a*b*'", STAY),
    (IN_ENGINE + "sed 's[a[b['", STAY),
    (IN_ENGINE + "PYTHONPATH=/private/tmp/x " + START_TEST_ENGINE, STAY),
    (IN_ENGINE + START_TEST_ENGINE + " <(cat .env >&2)", STAY),
    (IN_ENGINE + "BASH_ENV=x bash deploy/local/seed-test-user.sh --force", STAY),
    (IN_ENGINE + "deploy/local/seed-test-user.sh --force `cat .env`", STAY),
    (IN_ENGINE + "deploy/local/seed-test-user.sh $(cat .env)", STAY),
    # the practice user's key never goes to a file, wherever the command runs
    (SEED + " | sed 's/a/b/' > key.txt", STAY),
    (SEED + f" > {SCRATCH}/key.txt", STAY),
    (SEED + f" | tee {SCRATCH}/key.txt", STAY),
    (SEED + " | cat > key.txt", STAY),
    (SEED + " | dd of=key.txt", STAY),
    (SEED + " | sed 's/a/b/' | tee key.txt", STAY),
    (SEED + " 2>&1 | grep -v x >> key.txt", STAY),
    # `cd -` returns to the folder the guard last left
    (IN_ENGINE + "cd {repo} && cd - && cat app/main.py", STAY),
    (IN_ENGINE + "cd {repo} && cd - && ls", STAY),
    # a pipe run into `(` or across a newline is still a pipe
    (SEED + " |(tee key.txt)", STAY),
    (SEED + " |\ntee key.txt", STAY),
    ("(" + SEED + ")|tee key.txt", STAY),
    ("kill -9 -1", STAY),  # not a pid the tester started
    ("curl http://127.0.0.1:8000/health", LIVE),  # every other check still applies
    ("cat ~/Documents/notes.txt", STAY),
]


@pytest.mark.parametrize(("command", "rule"), TESTER_BLOCKED)
def test_guard_tester_exception_is_narrow(box, command, rule):
    cwd = "{engine}" if command.startswith("kill") else ""
    _blocked(box.guard("Bash", {"command": command}, agent="tester", cwd=cwd), rule)


# Every interpreter but the engine checkout's own `.venv/bin/python`.
OTHER_START_PYTHONS = [
    "python",
    "python3",
    "python3.12",
    ".venv/bin/python3",
    ".venv/bin/python3.12",
    "./.venv/bin/python",
    "venv/bin/python",
    "tools/python3",
    "/usr/bin/python3",
    "/private/tmp/x/python",
    "{engine}/.venv/bin/python",
    "{repo}/.venv/bin/python",  # the CLI's own venv
    "../expense_world_CLI/.venv/bin/python",
]


@pytest.mark.parametrize("python", OTHER_START_PYTHONS)
@pytest.mark.parametrize("prefix", [IN_ENGINE, ""])
def test_guard_starts_the_test_engine_with_its_own_python_only(box, python, prefix):
    assert START_TEST_ENGINE.count(START_PYTHON) == 1
    command = prefix + START_TEST_ENGINE.replace(START_PYTHON, python)
    cwd = "" if prefix else "{engine}"
    _blocked(box.guard("Bash", {"command": command}, cwd=cwd, agent="tester"), STAY)


@pytest.mark.parametrize("agent", ["builder", "reviewer", "librarian", None])
def test_guard_keeps_the_test_engine_start_to_the_tester(box, agent):
    command = "cd ../expense_world_engine && deploy/local/seed-test-user.sh --force"
    _blocked(box.guard("Bash", {"command": command}, agent=agent), STAY)


# ---------------------------------------------------------------------------
# guard.py — file tools and WebFetch
# ---------------------------------------------------------------------------

BLOCKED_TOOLS = [
    ("Read", {"file_path": "{home}/.expense-config"}, LIVE),
    ("Edit", {"file_path": "{home}/.expense-config"}, LIVE),
    ("Grep", {"path": "{home}/.expense-config", "pattern": "token"}, LIVE),
    ("Read", {"file_path": "{home}/Desktop/notes.txt"}, STAY),
    ("Write", {"file_path": "{home}/Desktop/notes.txt"}, STAY),
    ("MultiEdit", {"file_path": "{home}/other/x.py"}, STAY),
    ("NotebookEdit", {"notebook_path": "{home}/x.ipynb"}, STAY),
    ("Glob", {"pattern": "**/*.md", "path": "{home}"}, STAY),
    ("Glob", {"pattern": "{home}/Documents/**"}, STAY),
    ("Grep", {"pattern": "x", "path": "{home}/Desktop"}, STAY),
    ("Read", {"file_path": "{repo}/../other_repo/x.py"}, STAY),
    ("Write", {"file_path": "{engine}/app/main.py"}, STAY),
    ("Edit", {"file_path": "{engine}/docs/engine-spec.md"}, STAY),
    ("Read", {"file_path": "{engine}/docs/engine-spec.md"}, STAY),
    ("Read", {"file_path": "{repo}/../expense_world_engine/app/main.py"}, STAY),
    ("NotebookRead", {"notebook_path": "{engine}/notes.ipynb"}, STAY),
    ("Grep", {"pattern": "uvicorn", "path": "{engine}"}, STAY),
    ("Grep", {"pattern": "uvicorn", "path": "../expense_world_engine/deploy"}, STAY),
    ("Glob", {"pattern": "../expense_world_engine/**/*.md"}, STAY),
    ("Glob", {"pattern": "**/*.md", "path": "{engine}"}, STAY),
    ("WebFetch", {"url": "http://127.0.0.1:8000/health", "prompt": "x"}, LIVE),
    ("WebFetch", {"url": "http://localhost:8000/openapi.json", "prompt": "x"}, LIVE),
    ("WebFetch", {"url": "http://127.1:8000/health", "prompt": "x"}, LIVE),
]


@pytest.mark.parametrize("agent", ["builder", None])
def test_guard_lets_an_agent_leave_the_engine_but_not_read_it(box, agent):
    _allowed(box.guard("Bash", {"command": "cd {repo} && ls"}, agent=agent, cwd="{engine}"))
    _blocked(box.guard("Bash", {"command": "ls"}, agent=agent, cwd="{engine}"), STAY)
    command = "cd {repo} <(cat app/main.py >&2)"
    _blocked(box.guard("Bash", {"command": command}, agent=agent, cwd="{engine}"), STAY)
    command = "cd {repo} && cd - && cat app/main.py"
    _blocked(box.guard("Bash", {"command": command}, agent=agent, cwd="{engine}"), STAY)
    command = "cd {repo} && cat ../expense_world_engine/app/main.py"
    _blocked(box.guard("Bash", {"command": command}, agent=agent, cwd="{engine}"), STAY)


OUTSIDE_CWD_READS = [
    ("cat Documents/expense_world_engine/app/main.py", "{home}"),
    ("ls", "{home}/Documents"),
    ("cat home/Documents/expense_world_engine/app/main.py", "{home}/.."),
    ("sed -n 1p expense_world_engine/app/main.py", "{home}/Documents"),
]


@pytest.mark.parametrize("agent", ["tester", "builder"])
@pytest.mark.parametrize(("command", "cwd"), OUTSIDE_CWD_READS)
def test_guard_reads_relative_paths_against_a_cwd_outside_the_repo(box, agent, command, cwd):
    _blocked(box.guard("Bash", {"command": command}, agent=agent, cwd=cwd), STAY)


OUTSIDE_CWD_ALLOWED = [
    ("ls", SCRATCH),
    ("cat notes.txt && head -5 out/log.txt", SCRATCH),
    ("ls", "{home}/.claude"),
    ("cat agents/builder.md", "{home}/.claude"),
    ("grep -rn builder agents", "{home}/.claude/projects"),
]


@pytest.mark.parametrize("agent", ["tester", "builder", None])
@pytest.mark.parametrize(("command", "cwd"), OUTSIDE_CWD_ALLOWED)
def test_guard_allows_a_cwd_in_the_scratchpad_or_claude_folder(box, agent, command, cwd):
    _allowed(box.guard("Bash", {"command": command}, agent=agent, cwd=cwd))


def test_guard_lets_the_tester_cd_back_into_the_engine(box):
    command = "cd {repo} && cd - && deploy/local/seed-test-user.sh --force > /dev/null"
    _allowed(box.guard("Bash", {"command": command}, agent="tester", cwd="{engine}"))


@pytest.mark.parametrize(("tool", "tool_input", "rule"), BLOCKED_TOOLS)
def test_guard_blocks_tool(box, tool, tool_input, rule):
    _blocked(box.guard(tool, tool_input), rule)


ENGINE_READS = [
    ("Read", {"file_path": "{engine}/app/main.py"}, ""),
    ("NotebookRead", {"notebook_path": "{engine}/x.ipynb"}, ""),
    ("Grep", {"pattern": "uvicorn"}, "{engine}"),  # no path: the cwd, inside the engine
    ("Glob", {"pattern": "**/*.py"}, "{engine}"),
    ("Glob", {"pattern": "{engine}/deploy/**"}, ""),
]


@pytest.mark.parametrize("agent", ["tester", "builder", "reviewer", "librarian", None])
@pytest.mark.parametrize(("tool", "tool_input", "cwd"), ENGINE_READS)
def test_guard_blocks_every_agent_reading_the_engine(box, agent, tool, tool_input, cwd):
    _blocked(box.guard(tool, tool_input, agent=agent, cwd=cwd), STAY)


ALLOWED_TOOLS = [
    ("Read", {"file_path": "{repo}/expense/http.py"}),
    ("Write", {"file_path": "{repo}/expense/new.py"}),
    ("Edit", {"file_path": "{repo}/docs/cli-spec.md"}),
    ("Write", {"file_path": "{home}/.claude/projects/p/memory/note.md"}),
    ("Read", {"file_path": "{home}/.claude/agents/builder.md"}),
    ("Glob", {"pattern": "**/*.py"}),
    ("Grep", {"pattern": "x"}),
    ("Read", {"file_path": "/usr/lib/os-release"}),
    ("Write", {"file_path": f"{SCRATCH}/notes.txt"}),
    ("WebFetch", {"url": "http://127.0.0.1:8002/health", "prompt": "x"}),
    ("WebFetch", {"url": "https://docs.python.org/3/", "prompt": "x"}),
]


@pytest.mark.parametrize(("tool", "tool_input"), ALLOWED_TOOLS)
def test_guard_allows_tool(box, tool, tool_input):
    _allowed(box.guard(tool, tool_input))


# ---------------------------------------------------------------------------
# lint_edit.py
# ---------------------------------------------------------------------------


def _ruff() -> str:
    beside = Path(sys.executable).parent / "ruff"
    found = str(beside) if beside.exists() else shutil.which("ruff")
    assert found, "ruff is a dev dependency"
    return found


def _lint(box: Sandbox, path: Path, tool: str = "Edit"):
    payload = {
        "hook_event_name": "PostToolUse",
        "cwd": str(box.repo),
        "tool_name": tool,
        "tool_input": {"file_path": str(path)},
    }
    return box.run("lint_edit.py", payload, EXPENSE_HOOKS_RUFF=_ruff())


@pytest.mark.parametrize(
    ("source", "expected"),
    [("import os\n", "F401"), ("x=1\n", "Would reformat")],
    ids=["lint-error", "unformatted"],
)
def test_lint_edit_reports_ruff_problems(box, source, expected):
    path = box.repo / "pkg" / "mod.py"
    path.parent.mkdir()
    path.write_text(source)
    result = _lint(box, path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    assert expected in out["additionalContext"]


@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit"])
def test_lint_edit_is_silent_on_a_clean_file(box, tool):
    path = box.repo / "clean.py"
    path.write_text("x = 1\n")
    _allowed(_lint(box, path, tool))


def test_lint_edit_ignores_non_python_files(box):
    path = box.repo / "README.md"
    path.write_text("import os\n")
    _allowed(_lint(box, path))


def test_lint_edit_ignores_python_outside_the_repo(box, tmp_path):
    path = tmp_path / "elsewhere.py"
    path.write_text("import os\n")
    _allowed(_lint(box, path))


# ---------------------------------------------------------------------------
# tests_gate.py
# ---------------------------------------------------------------------------


def _stub(exit_code: int, lines: int = 1) -> str:
    code = f"import sys\nfor i in range({lines}): print(f'line {{i}}')\nsys.exit({exit_code})"
    return shlex.join([sys.executable, "-c", code])


PASSING, FAILING = _stub(0), _stub(1)


def _gate(box: Sandbox, payload: dict, stub: str | None):
    env = {"EXPENSE_HOOKS_PYTEST": stub} if stub else {}
    return box.run("tests_gate.py", payload, **env)


def _bash(command: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def _stop(active: bool) -> dict:
    return {"hook_event_name": "SubagentStop", "agent_type": "builder", "stop_hook_active": active}


@pytest.mark.parametrize(
    "payload",
    [_bash("git commit -m x"), _bash("git add . && git commit -m x"), _stop(False)],
    ids=["commit", "add-then-commit", "builder-stop"],
)
def test_tests_gate_blocks_on_failing_tests(box, payload):
    result = _gate(box, payload, _stub(1, lines=100))
    assert result.returncode == 2
    assert result.stderr.startswith('Blocked by CLAUDE.md "Dev loop"')
    assert "line 99" in result.stderr and "line 60" in result.stderr
    assert "line 59" not in result.stderr, "only the tail of the output"


@pytest.mark.parametrize(
    "payload",
    [_bash("git commit -m x"), _stop(False)],
    ids=["commit", "builder-stop"],
)
def test_tests_gate_passes_on_green_tests(box, payload):
    _allowed(_gate(box, payload, PASSING))


@pytest.mark.parametrize(
    "payload",
    [
        _bash("git status"),
        _bash("grep -rn 'git commit' docs"),
        _stop(True),
        {"hook_event_name": "PostToolUse", "tool_name": "Bash"},
    ],
    ids=["not-a-commit", "commit-in-a-pattern", "stop-hook-active", "other-event"],
)
def test_tests_gate_does_not_run_tests(box, payload):
    _allowed(_gate(box, payload, FAILING))


def test_tests_gate_runs_the_unit_suite_from_the_repo_root(box):
    record = box.home / "argv.txt"
    fake = box.repo / ".venv" / "bin" / "pytest"
    fake.parent.mkdir(parents=True)
    fake.write_text(f'#!/bin/sh\necho "$(pwd) $*" > "{record}"\nexit 0\n')
    fake.chmod(0o755)
    _allowed(_gate(box, _bash("git commit -m x"), None))
    assert record.read_text().strip() == f"{box.repo} tests/unit -q -x"


def test_tests_gate_blocks_when_pytest_is_missing(box):
    result = _gate(box, _bash("git commit -m x"), None)
    assert result.returncode == 2
    assert "could not run the unit tests" in result.stderr


def _ops_guide_start_command() -> str:
    """The test-engine start block from docs/cli-runtime.md, lines joined by `\\`."""
    doc = (Path(__file__).resolve().parents[2] / "docs" / "cli-runtime.md").read_text()
    lines = doc.splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip().startswith("SUPABASE_DB_URL="))
    block = []
    for line in lines[first:]:
        block.append(line.strip())
        if not line.endswith("\\"):
            break
    return "\n".join(block).replace("<owner>", "owner")  # the doc's placeholder


def test_guard_lets_the_tester_run_the_ops_guide_command(box):
    command = _ops_guide_start_command()
    assert command.count("\\\n") == 2 and "--port 8002" in command
    # the checkout's own interpreter, detached with its output in a log, so the
    # engine outlives the agent that starts it
    assert ".venv/bin/python -m uvicorn" in command
    assert command.endswith(" &") and "> /tmp/" in command
    _allowed(
        box.guard("Bash", {"command": "cd ../expense_world_engine && " + command}, agent="tester")
    )


def test_guard_lets_the_tester_run_the_documented_reseed(box):
    """The reseed exactly as CLAUDE.md and the ops guide name it, run from the engine."""
    root = Path(__file__).resolve().parents[2]
    seed = "deploy/local/seed-test-user.sh --force"
    assert f"`{seed}`" in (root / "CLAUDE.md").read_text()
    assert "`deploy/local/seed-test-user.sh`" in (root / "docs" / "cli-runtime.md").read_text()
    _allowed(
        box.guard("Bash", {"command": "cd ../expense_world_engine && " + seed}, agent="tester")
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS disks are case-insensitive")
@pytest.mark.parametrize(
    "seed",
    [
        "deploy/local/seed-test-user.sh --force",
        "./deploy/local/seed-test-user.sh --force",
        "bash deploy/local/seed-test-user.sh --force",
    ],
)
@pytest.mark.parametrize(
    ("project", "cwd"), [("documents", "Documents"), ("Documents", "documents")]
)
def test_guard_seed_path_ignores_case_on_macos(box, seed, project, cwd):
    def spell(path: Path, word: str) -> str:
        return str(path).replace("/Documents/", f"/{word}/")

    payload = {
        "hook_event_name": "PreToolUse",
        "cwd": spell(box.repo, cwd),
        "tool_name": "Bash",
        "agent_type": "tester",
        "tool_input": {"command": "cd ../expense_world_engine && " + seed},
    }
    _allowed(box.run("guard.py", payload, CLAUDE_PROJECT_DIR=spell(box.repo, project)))


@pytest.mark.parametrize(
    "stdin",
    [
        "not json",
        "[1, 2]",
        '{"tool_name": "Bash", "cwd": 42, "tool_input": {"command": "git status"}}',
        '{"tool_name": "Bash", "cwd": ["/"], "tool_input": {"command": "git status"}}',
        '{"tool_name": "Bash", "tool_input": ["git push --force"]}',
        '{"tool_name": "Read", "tool_input": "/etc/passwd"}',
        '{"tool_name": "Bash", "tool_input": {"command": 7}}',
    ],
    ids=["not-json", "array", "int-cwd", "list-cwd", "list-input", "str-input", "int-command"],
)
def test_guard_fails_open_on_malformed_input(box, stdin):
    _allowed(box.run("guard.py", stdin))


def test_tests_gate_blocks_when_the_suite_hangs(box):
    stub = shlex.join([sys.executable, "-c", "import time; time.sleep(30)"])
    result = box.run(
        "tests_gate.py",
        _bash("git commit -m x"),
        EXPENSE_HOOKS_PYTEST=stub,
        EXPENSE_HOOKS_PYTEST_TIMEOUT="0.5",
    )
    assert result.returncode == 2
    assert "did not finish within 0.5 s" in result.stderr
