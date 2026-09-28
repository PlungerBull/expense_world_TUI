"""PreToolUse guard: blocks the tool calls CLAUDE.md forbids, before they run.

Wired in `.claude/settings.json` for Bash, Read, Write, Edit, MultiEdit, NotebookEdit, Glob,
Grep and WebFetch. Reads the hook JSON on stdin; a blocked call exits 2 with a one-line
reason on stderr (Claude Code hands it back to the model), an allowed one exits 0 silently.
Tests: `tests/unit/test_claude_hooks.py`.

What it blocks:

- **Live engine** ("Careful running live"): a Bash command or WebFetch URL naming port
  `:8000` after anything host-like (`127.0.0.1`, `127.1`, `localhost`, `[::]`, `tcp`, any
  name) or as a bare `:8000` word (`lsof -ti :8000`); a time such as `12:30:8000` or a
  number such as `8000000` is not a port. Read-only commands (`grep`, `git`, `sed`, …) and
  `echo`/`printf`/`awk` are not checked, so text that mentions the port stays usable;
  running `scripts/check_fixture_drift.py` (directly or with a python) without
  `--engine-url …:8002`; running `pytest tests/contract`, or any `PYTEST_LIVE=1` pytest run,
  without `EXPENSE_ENGINE_URL=…:8002` in the command.
- **Real config** ("Careful running live"): an `expense` run (`expense`, any `…/expense`,
  `python -m expense…`) without `EXPENSE_CONFIG=` somewhere in the command; any path to a
  `.expense-config` under the home folder, from a file tool or a Bash word.
- **Outside the repo** ("Stay inside this repo"): a file-tool path, or a Bash word that is
  an absolute, `~`, `$HOME` or `..` path (resolved against the hook's `cwd` and any `cd`
  earlier in the command), that lands under the home folder but outside the repo. Allowed:
  `~/.claude/**`; everything outside the home folder (system paths, the harness scratchpad
  under `/private/tmp`); and reads of the sibling engine checkout `../expense_world_engine`.
- **The engine checkout is read-only**: file-tool writes there are blocked for everyone. A
  Bash command that runs there (a `cd` into it, the hook's `cwd`, or a path word inside it)
  may only be a read (`cat`, `ls`, `grep`, `head`, `sed -n`, read-only `git`, …) with no
  redirect into it — except that the **tester** (`agent_type == "tester"`) may also start
  the test engine exactly as the ops guide says (`python -m uvicorn app.main:app --port
  8002` with both `SUPABASE_DB_URL` and `ADMIN_DB_URL` in the command and every `*_DB_URL`
  naming `expense_world_test`, env names compared case-insensitively — a missing one falls
  back to the engine's `.env`, which points at the real ledger), run
  `deploy/local/seed-test-user.sh --force`, and check it with `curl` (flags only from
  `-s -S -f -i -v`, their bundles, `--silent --show-error --fail --max-time <n>`; every
  URL on `127.0.0.1`/`localhost:8002`).
- **Stopping processes** ("Stay inside this repo"): `kill`, `pkill`, `killall` and
  `xargs kill` are blocked for everyone except the tester, who may run
  `kill [-SIGNAL] <numeric pid>…` and `lsof -ti :8002 | xargs [-r] kill` (or
  `lsof -t -i :8002`). The guard checks only the command's form, not which process a pid
  names; stopping only the engine it started is a rule the tester keeps.
- **Git** (single branch, never `--no-verify`): `push` with `--force`/`-f` (alone or in a
  short-flag cluster such as `-uf`)/`--force-with-lease`/`--mirror`/a `+refspec`; `commit --amend`;
  `rebase`, `reset --hard`, `filter-branch`, `filter-repo`, `update-ref`; new branches
  (`branch <name>`, `checkout -b/-B/--orphan`, `switch -c/-C/--orphan`, `worktree add`
  without `--detach` or with `-b`); `--no-verify`, `commit -n`, a commit with a `SKIP=`
  env prefix or after an `export SKIP=`; any `core.hooksPath`.

Limits: it reads commands as `_shell.py` describes, so a relative path without `..`, a path
built from variables, or a command hidden in `$(...)` or `bash -c "…"` passes. It is a
tripwire against slips, not a sandbox. Malformed hook input fails open rather than crash:
input that is not a JSON object, or a non-object `tool_input`, allows the call; a missing
or non-string `cwd` only falls back to the repo root, and every other check still applies.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from _shell import Segment, git_args, home_dir, is_within, read_input, repo_root, segments

LIVE = 'CLAUDE.md "Careful running live"'
STAY = 'CLAUDE.md "Stay inside this repo"'
BRANCH = 'CLAUDE.md "Dev loop" (single branch, never --no-verify)'

# `:8000` after a host-like word (not itself after a `:`, so `12:30:8000` is a time),
# after a bracketed IPv6 host, or standing bare.
_LIVE_ENGINE = re.compile(r"(?:(?<![\w.:-])[\w.-]+|\[[0-9A-Fa-f:.]*\]|(?<![\w.\]:-])):8000(?!\d)")
_TEST_ENGINE_URL = re.compile(r"https?://(?:127\.0\.0\.1|localhost):8002(?:/\S*)?")
_CURL_FLAGS = frozenset({"--silent", "--show-error", "--fail"})
_CURL_BUNDLE = re.compile(r"-[sSfiv]+")
_KILLERS = frozenset({"kill", "pkill", "killall"})
_LSOF_8002 = (["-ti", ":8002"], ["-t", "-i", ":8002"])
_PYTHON = re.compile(r"python(?:3(?:\.\d+)?)?")
_READ_ONLY = frozenset(
    {
        "cat",
        "less",
        "head",
        "tail",
        "ls",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "wc",
        "file",
        "stat",
        "diff",
        "tree",
        "jq",
        "cd",
        "pwd",
        "true",
        "realpath",
        "basename",
        "dirname",
    }
)
_GIT_READ = frozenset(
    {"log", "show", "diff", "status", "blame", "grep", "ls-files", "rev-parse", "describe"}
)
_FIND_WRITES = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fls"})
_READ_TOOLS = frozenset({"Read", "Glob", "Grep"})
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


class Context:
    def __init__(self, data: dict[str, Any]) -> None:
        self.repo = repo_root()
        self.home = home_dir()
        self.engine = self.repo.parent / "expense_world_engine"
        cwd = data.get("cwd")
        self.cwd = Path(cwd) if isinstance(cwd, str) and cwd else self.repo
        self.tester = data.get("agent_type") == "tester"

    def resolve(self, raw: str, cwd: Path) -> Path | None:
        """`raw` as an absolute path, if it is written as a path worth checking."""
        if "://" in raw:
            return None
        for prefix in ("${HOME}", "$HOME", "~"):
            if raw == prefix or raw.startswith(prefix + "/"):
                return Path(str(self.home) + raw[len(prefix) :]).resolve()
        if raw.startswith("/"):
            return Path(raw).resolve()
        if ".." in raw.split("/"):
            return (cwd / raw).resolve()
        return None

    def in_engine(self, path: Path) -> bool:
        return is_within(path, self.engine)

    def outside_reason(self, path: Path, *, write: bool) -> str | None:
        """Why touching `path` is blocked, or None."""
        if path.name == ".expense-config" and is_within(path, self.home):
            return f"{LIVE}: never touch the real config {path}"
        if not is_within(path, self.home) or is_within(path, self.repo):
            return None
        if is_within(path, self.home / ".claude"):
            return None
        if self.in_engine(path):
            if write:
                return f"{STAY}: the engine checkout is read-only ({path})"
            return None
        return f"{STAY}: {path} is outside this repo"


# ---------------------------------------------------------------------------
# File tools and WebFetch
# ---------------------------------------------------------------------------


def check_tool(ctx: Context, tool: str, tool_input: dict[str, Any]) -> str | None:
    if tool == "WebFetch":
        if _LIVE_ENGINE.search(str(tool_input.get("url", ""))):
            return f"{LIVE}: never call the live engine on :8000"
        return None
    if tool in _READ_TOOLS | _WRITE_TOOLS:
        raws = [tool_input.get("file_path"), tool_input.get("notebook_path")]
        if tool in {"Glob", "Grep"}:
            raws.append(tool_input.get("path") or str(ctx.cwd))
            raws.append(tool_input.get("pattern") if tool == "Glob" else None)
        for raw in raws:
            if not raw:
                continue
            path = ctx.resolve(str(raw), ctx.cwd) or (ctx.cwd / str(raw)).resolve()
            reason = ctx.outside_reason(path, write=tool in _WRITE_TOOLS)
            if reason:
                return reason
    return None


# ---------------------------------------------------------------------------
# Bash
# ---------------------------------------------------------------------------


def _path_words(seg: Segment) -> list[str]:
    out: list[str] = list(seg.env.values())
    for word in seg.words:
        out.append(word)
        if "=" in word:
            out.append(word.split("=", 1)[1])
    return out


def _is_read_only(seg: Segment) -> bool:
    name = seg.name
    if name == "sed":
        return "-n" in seg.words and not any(
            w.startswith("-i") or w == "--in-place" for w in seg.words
        )
    if name == "find":
        return not any(w in _FIND_WRITES for w in seg.words)
    ga = git_args(seg)
    if ga is not None:
        return ga[0] in _GIT_READ
    return name in _READ_ONLY


def _is_test_db(url: str) -> bool:
    return url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] == "expense_world_test"


def _tester_op(ctx: Context, seg: Segment, cwd: Path) -> bool:
    """The ops-guide commands the tester may run in the engine checkout."""
    words = seg.words
    if _PYTHON.fullmatch(seg.name) and words[1:] == [
        "-m",
        "uvicorn",
        "app.main:app",
        "--port",
        "8002",
    ]:
        env = {k.upper(): v for k, v in seg.env.items()}  # the engine ignores name case
        db_urls = [v for k, v in seg.env.items() if k.upper().endswith("_DB_URL")]
        required = {"SUPABASE_DB_URL", "ADMIN_DB_URL"} <= env.keys()
        return required and all(_is_test_db(v) for v in db_urls)
    script = words[1:] if seg.name in {"bash", "sh"} else words
    if len(script) == 2 and script[1] == "--force":
        target = (cwd / script[0]).resolve()  # an absolute script[0] replaces cwd
        seed = (ctx.engine / "deploy" / "local" / "seed-test-user.sh").resolve()
        return is_within(target, seed)  # the same file, compared the way every path is
    if seg.name == "lsof":
        return words[1:] in _LSOF_8002
    if seg.name == "curl":
        return _curl_is_health_check(words[1:])
    return False


def _curl_is_health_check(args: list[str]) -> bool:
    """`curl` with only allowlisted read flags and only test-engine URLs."""
    urls = 0
    i = 0
    while i < len(args):
        word = args[i]
        if word in {"--max-time", "-m"}:
            if i + 1 >= len(args) or not re.fullmatch(r"\d+(?:\.\d+)?", args[i + 1]):
                return False
            i += 2
            continue
        if word in _CURL_FLAGS or _CURL_BUNDLE.fullmatch(word):
            pass
        elif _TEST_ENGINE_URL.fullmatch(word):
            urls += 1
        else:
            return False
        i += 1
    return urls > 0


def _stops_processes(seg: Segment) -> bool:
    if seg.name in _KILLERS:
        return True
    return seg.name == "xargs" and any(w.rsplit("/", 1)[-1] in _KILLERS for w in seg.words)


def _tester_may_stop(seg: Segment, previous: Segment | None) -> bool:
    """`kill [-SIGNAL] <pid>…` with numeric pids, or `lsof -ti :8002 | xargs [-r] kill`."""
    words = seg.words
    if seg.name == "kill":
        pids = words[2:] if words[1:2] and words[1].startswith("-") else words[1:]
        return bool(pids) and all(re.fullmatch(r"[1-9]\d*", w) for w in pids)
    if seg.name == "xargs":
        return (
            words[1:] in (["kill"], ["-r", "kill"])
            and previous is not None
            and previous.name == "lsof"
            and previous.words[1:] in _LSOF_8002
        )
    return False


def _pushes_force(args: list[str]) -> bool:
    for w in args:
        if w in {"--force", "--force-with-lease", "--force-if-includes", "--mirror"}:
            return True
        if w.startswith("--force-with-lease=") or (w.startswith("+") and len(w) > 1):
            return True
        if w.startswith("-") and not w.startswith("--"):
            if "f" in w[1:].split("o", 1)[0]:  # `-o` takes a value; flags before it count
                return True
    return False


def _git_reason(seg: Segment, all_segments: list[Segment]) -> str | None:
    ga = git_args(seg)
    if ga is None:
        return None
    sub, args = ga
    if any("core.hookspath" in w.casefold() for w in seg.words):
        return f"{BRANCH}: never change core.hooksPath (it switches pre-commit off)"
    if "--no-verify" in seg.words:
        return f"{BRANCH}: --no-verify skips pre-commit and its gitleaks secret scan"
    if sub == "push" and _pushes_force(args):
        return f"{BRANCH}: no force-push"
    if sub == "commit":
        if "--amend" in args:
            return f"{BRANCH}: no history rewrites (commit --amend)"
        if _commit_has_short_n(args):
            return f"{BRANCH}: commit -n skips pre-commit and its gitleaks secret scan"
        exported = any(
            s.name == "export" and any(w.startswith("SKIP=") for w in s.words[1:])
            for s in all_segments
        )
        if "SKIP" in seg.env or exported:
            return f"{BRANCH}: SKIP= switches pre-commit checks off"
    if sub in {"rebase", "filter-branch", "filter-repo", "update-ref"}:
        return f"{BRANCH}: no history rewrites (git {sub})"
    if sub == "reset" and "--hard" in args:
        return f"{BRANCH}: no history rewrites (reset --hard)"
    if sub == "branch" and _branch_creates(args):
        return f"{BRANCH}: main is the only branch; no new branches"
    if sub == "checkout" and any(w in {"-b", "-B", "--orphan"} for w in args):
        return f"{BRANCH}: main is the only branch; no new branches"
    if sub == "switch" and any(
        w in {"-c", "-C", "--create", "--force-create", "--orphan"} for w in args
    ):
        return f"{BRANCH}: main is the only branch; no new branches"
    if sub == "worktree" and args[:1] == ["add"]:
        rest = args[1:]
        if any(w in {"-b", "-B"} for w in rest) or not ({"--detach", "-d"} & set(rest)):
            return f"{BRANCH}: a worktree must be `git worktree add --detach`, not a new branch"
    return None


def _commit_has_short_n(args: list[str]) -> bool:
    takes_value = set("mFCctS")
    skip = False
    for word in args:
        if skip:
            skip = False
            continue
        if word in {"--message", "--file", "--author", "--date", "--reuse-message"}:
            skip = True
            continue
        if word.startswith("-") and not word.startswith("--"):
            for ch in word[1:]:
                if ch == "n":
                    return True
                if ch in takes_value:
                    skip = word.endswith(ch)
                    break
    return False


def _branch_creates(args: list[str]) -> bool:
    listing = {
        "-d",
        "-D",
        "--delete",
        "-l",
        "--list",
        "--contains",
        "--no-contains",
        "--merged",
        "--no-merged",
        "--points-at",
        "--show-current",
    }
    if listing & set(args):
        return False
    return any(not w.startswith("-") for w in args)


def _runs_expense(seg: Segment) -> bool:
    if seg.name == "expense":
        return True
    return (
        bool(_PYTHON.fullmatch(seg.name))
        and seg.words[1:2] == ["-m"]
        and len(seg.words) > 2
        and (seg.words[2] == "expense" or seg.words[2].startswith("expense."))
    )


def _runs_drift_script(seg: Segment) -> bool:
    """`scripts/check_fixture_drift.py` run directly or by a python, not merely named."""
    if seg.name == "check_fixture_drift.py":
        return True
    if not _PYTHON.fullmatch(seg.name):
        return False
    script = next((w for w in seg.words[1:] if not w.startswith("-")), "")
    return script.endswith("check_fixture_drift.py")


def _runs_pytest(seg: Segment) -> bool:
    return seg.name.startswith("pytest") or (
        bool(_PYTHON.fullmatch(seg.name)) and seg.words[1:3] == ["-m", "pytest"]
    )


def _live_reason(seg: Segment, command: str) -> str | None:
    if seg.name not in _READ_ONLY | {"git", "sed", "echo", "printf", "awk"}:
        if any(_LIVE_ENGINE.search(w) for w in [*seg.words, *seg.env.values()]):
            return f"{LIVE}: never call the live engine on :8000 (use the :8002 test engine)"
    if _runs_drift_script(seg):
        words = seg.words
        urls = [words[i + 1] for i, w in enumerate(words[:-1]) if w == "--engine-url"]
        urls += [w.split("=", 1)[1] for w in words if w.startswith("--engine-url=")]
        if not any(":8002" in u for u in urls):
            return f"{LIVE}: check_fixture_drift.py needs an explicit --engine-url …:8002"
    if _runs_pytest(seg):
        live = any("tests/contract" in w for w in seg.words) or re.search(
            r"(?<!\w)PYTEST_LIVE=1", command
        )
        if live and not re.search(r"(?<!\w)EXPENSE_ENGINE_URL=\S*:8002", command):
            return f"{LIVE}: the contract suite needs EXPENSE_ENGINE_URL=http://127.0.0.1:8002"
    if _runs_expense(seg) and not re.search(r"(?<!\w)EXPENSE_CONFIG=\S", command):
        return f"{LIVE}: `expense` needs an EXPENSE_CONFIG= override, never the real config"
    return None


def check_bash(ctx: Context, command: str) -> str | None:
    cwd = ctx.cwd
    all_segments = segments(command)
    for seg in all_segments:  # the live engine first: it is the worst slip in any command
        reason = _live_reason(seg, command)
        if reason:
            return reason
    for index, seg in enumerate(all_segments):
        paths = [p for raw in _path_words(seg) + seg.inputs if (p := ctx.resolve(raw, cwd))]
        redirects = [ctx.resolve(raw, cwd) or (cwd / raw).resolve() for raw in seg.redirects]
        for path in [*paths, *redirects]:
            reason = ctx.outside_reason(path, write=False)
            if reason:
                return reason
        reason = _git_reason(seg, all_segments)
        if reason:
            return reason
        stops = _stops_processes(seg)
        if stops:
            previous = all_segments[index - 1] if index else None
            if not (ctx.tester and _tester_may_stop(seg, previous)):
                return (
                    f"{STAY}: only the tester stops processes, in the form `kill <pid>` or "
                    "`lsof -ti :8002 | xargs kill` (and it stops only the engine it started)"
                )
        if ctx.in_engine(cwd) or any(ctx.in_engine(p) for p in [*paths, *redirects]):
            if any(ctx.in_engine(p) for p in redirects):
                return f"{STAY}: the engine checkout is read-only (redirect into it)"
            if not (stops or _is_read_only(seg) or (ctx.tester and _tester_op(ctx, seg, cwd))):
                who = (
                    "the tester may only start the :8002 test engine, reseed the practice "
                    "user and stop what it started"
                    if ctx.tester
                    else "only the tester may start the test engine there"
                )
                return f"{STAY}: the engine checkout is read-only; {who}"
        if seg.name == "cd":
            target = seg.words[1] if len(seg.words) > 1 else "~"
            if target != "-":
                cwd = ctx.resolve(target, cwd) or (cwd / target).resolve()
    return None


def main() -> int:
    data = read_input()
    ctx = Context(data)
    tool = str(data.get("tool_name", ""))
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    if tool == "Bash":
        reason = check_bash(ctx, str(tool_input.get("command", "")))
    else:
        reason = check_tool(ctx, tool, tool_input)
    if reason:
        print(f"Blocked by {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
