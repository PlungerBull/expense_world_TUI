"""PreToolUse guard: blocks the tool calls CLAUDE.md forbids, before they run.

Wired in `.claude/settings.json` for Bash, Read, Write, Edit, MultiEdit, NotebookRead,
NotebookEdit, Glob, Grep and WebFetch. Reads the hook JSON on stdin; a blocked call exits 2
with a one-line reason on stderr (Claude Code hands it back to the model), an allowed one
exits 0 silently.
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
- **Outside the repo** ("Stay inside this repo"): a file-tool path, or a Bash path that
  lands under the home folder but outside the repo. A Bash word counts as a path when it is
  absolute, `~`, `$HOME` or `..`; while the command's folder is outside the repo, any other
  word too (not a flag, a `$` word or a URL), read against that folder, and a command run
  in such a folder is itself a read there. The folder is the hook's `cwd`, then every `cd`
  in the command: a bare `cd` goes home, and `cd -` goes back to the folder the last `cd`
  left. Allowed: `~/.claude/**`; everything outside the home folder (system paths, the
  harness scratchpad under `/private/tmp`).
- **The engine checkout is closed** (the sibling `../expense_world_engine`): no agent reads
  or writes a file there. Every file tool (Read, NotebookRead, Glob, Grep and the writers)
  on a path inside it is blocked for everyone. A Bash command that runs there (after a `cd`
  into it, from the hook's `cwd`, with a path word inside it, or with a `<`/`>` redirect into
  it) is blocked. Two things pass:
  - for everyone, a bare `cd <dir>` out of it (exactly one target word, no env prefix, no
    redirect, the target outside it);
  - for the **tester** (`agent_type == "tester"`) alone, the ops guide's commands, each with
    no `$NAME`/`${…}` expansion other than `$HOME`: `cd <dir>` (one word); `sleep <n>`; a
    bare `true`; the test-engine start (`<python> -m uvicorn app.main:app --port 8002`,
    `<python>` being exactly `python`, `python3`, `.venv/bin/python` or
    `.venv/bin/python3`, whose env prefix names only `SUPABASE_DB_URL` and/or
    `ADMIN_DB_URL`, at least one of them, and every one naming `expense_world_test`, env
    names compared case-insensitively — any other name is one the engine ignores, so it
    guards nothing; a URL left off falls back to the engine's `.env`, and the engine refuses
    to start when its two URLs name different databases, so a start with one test URL fails
    at startup, while a start with none reads both from `.env`, which names the real ledger);
    `deploy/local/seed-test-user.sh --force` with no env prefix (relative, `..`, absolute
    or `~` path, or through `bash`/`sh`); `curl` and `lsof` with no env prefix (curl flags
    only from `-s -S -f -i -v`, their bundles, `--silent --show-error --fail --max-time <n>`;
    every URL on `127.0.0.1`/`localhost:8002`); the stop forms below; and stdin filters with
    no env prefix and no file operand — `sed` whose every script is one `s` command
    (delimiter not `?`, `*` or `[`; flags only `g`, `p`, `i`, `I` or a number; options only
    `-E -r -n -e`), `grep` with one glob-free pattern and flags from
    `-v -i -E -F -o -c -q -x -w`, `head`/`tail` with only `-n <n>`/`-<n>`.
  A command that touches the engine checkout is blocked whole when it holds `$(`, a
  backtick, `<(` or `>(` anywhere, or an `export`/`declare`/`typeset`/`readonly`/`local`/
  `set`/`alias`/`eval`/`source`/`.` command. The engine's test-database wipe script is not
  allowed: the ops guide does not give it to the tester.
- **The practice user's key stays off disk** (CLAUDE.md "Stay inside this repo": the tester
  never writes the key to a file), wherever the command runs: the seed's own redirects may
  only be `/dev/null`, and every command piped straight after it (a pipe as `_shell.py`
  marks one) must be one of the stdin filters above, redirecting only to `/dev/null` — so
  `| sed 's/…/…/'` and `> /dev/null` pass, and `| tee f`, `|(tee f)`, `| cat > f` or `> f`
  are blocked.
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

Limits: it is a tripwire against slips, not a sandbox, and reads commands as `_shell.py`
describes. What passes:

- a path built from variables, or a command hidden in `$(...)` or `bash -c "…"`, in a
  command that does not otherwise touch the engine checkout;
- a path inside a program string such as `python -c "…"` or an `awk '…'` program, the
  same way as `bash -c "…"`;
- a `cd -` before any `cd` in the command (the guard does not know the shell's previous
  folder), and `pushd`/`popd`;
- the seed's key reaching a file through a `( … )` group: `(seed …) > f` or
  `(seed …; true) | tee f`;
- environment set before the command (an earlier `export`, a profile);
- a tester's `sed` script the shell expands as a glob (an unquoted `s/x.*/y/` matching a
  real path);
- a test-engine start whose `*_DB_URL`s name an `expense_world_test` database on another
  host (only the database name is checked);
- a WebFetch `file://` URL.

It errs the other way too: a word written like an engine path is blocked even as a
`grep` pattern or `echo` text (`grep -rn '../expense_world_engine' docs`); search for the
bare name (`grep -rn expense_world_engine docs`) instead. A heredoc body is read as
commands, so a `cd` line in a bare heredoc body moves the folder the guard tracks and the
rest of the command is read against that folder, often blocked; write the body through
`"$(cat <<'EOF' … EOF)"`, as CLAUDE.md "Dev loop" gives for commit messages.

Malformed hook input fails open rather than crash: input that is not a JSON object, or a
non-object `tool_input`, allows the call; a missing or non-string `cwd` only falls back to
the repo root, and every other check still applies.
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
# The test-engine start: the PATH's python or the engine's own venv, nothing else.
_START_PYTHONS = frozenset({"python", "python3", ".venv/bin/python", ".venv/bin/python3"})
_START_ARGS = ["-m", "uvicorn", "app.main:app", "--port", "8002"]
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
# One sed `s` command: a delimiter that is not a glob character, pattern and replacement
# (escapes allowed, no newline), and only the flags that neither read nor write a file.
_SED_SUB = re.compile(
    r"s([^\\\n?*\[])((?:(?!\1)[^\\\n]|\\.)*)\1((?:(?!\1)[^\\\n]|\\.)*)\1[gpiI0-9]*"
)
# Shell text that runs another command or changes what the next one does: a command or
# process substitution anywhere in the command, a builtin that sets shell state, and a
# `$NAME`/`${…}` expansion other than `$HOME` in a tester-allowlisted command.
_SUBSTITUTIONS = ("$(", "`", "<(", ">(")
_SHELL_STATE = frozenset(
    {"export", "declare", "typeset", "readonly", "local", "set", "alias", "eval", "source", "."}
)
_EXPANSION = re.compile(r"\$[\w{(]")
_GREP_FLAGS = re.compile(r"-[viEFocqxw]+")
_READ_TOOLS = frozenset({"Read", "NotebookRead", "Glob", "Grep"})
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

    def resolve_word(self, raw: str, cwd: Path) -> Path | None:
        """`resolve`, and outside the repo also any other word that could be a relative path.

        Inside the repo a bare relative word is the repo's own file; in any other folder it
        is read against that folder, so `cd /Users && cat name/…` is seen for what it reads.
        """
        path = self.resolve(raw, cwd)
        if path is not None or is_within(cwd, self.repo):
            return path
        if not raw or raw.startswith(("-", "$")) or "://" in raw:
            return None
        return (cwd / raw).resolve()

    def in_engine(self, path: Path) -> bool:
        return is_within(path, self.engine)

    def outside_reason(self, path: Path) -> str | None:
        """Why touching `path` is blocked, or None."""
        if path.name == ".expense-config" and is_within(path, self.home):
            return f"{LIVE}: never touch the real config {path}"
        if not is_within(path, self.home) or is_within(path, self.repo):
            return None
        if is_within(path, self.home / ".claude"):
            return None
        if self.in_engine(path):
            return None  # the engine checkout has its own rule: `engine_reason`, `check_bash`
        return f"{STAY}: {path} is outside this repo"

    def engine_reason(self, path: Path) -> str | None:
        """Why a file tool may not touch `path`, if it is in the engine checkout."""
        if self.in_engine(path):
            return (
                f"{STAY}: no agent reads or writes the engine checkout ({path}); "
                "the contract is the practice engine's /openapi.json"
            )
        return None


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
            reason = ctx.outside_reason(path) or ctx.engine_reason(path)
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


def _expands(seg: Segment) -> bool:
    """Any word, env value or redirect with a `$` expansion other than `$HOME`."""
    words = [*seg.words, *seg.env.values(), *seg.redirects, *seg.inputs]
    return any(_EXPANSION.search(re.sub(r"\$\{?HOME\b\}?", "", w)) for w in words)


def _tester_idle(seg: Segment) -> bool:
    """`cd <dir>`, `sleep <n>` and a bare `true`: they read no file."""
    if seg.env:
        return False
    if seg.name == "cd":
        return len(seg.words) <= 2
    if seg.name == "sleep":
        return len(seg.words) == 2 and bool(re.fullmatch(r"\d+(?:\.\d+)?", seg.words[1]))
    return seg.words == ["true"]


def _filters_stdin(seg: Segment) -> bool:
    """`sed`/`grep`/`head`/`tail` that read only stdin: no file operand, no file flag, no env
    prefix (`GREP_OPTIONS=-r` would turn a filter into a recursive read)."""
    if seg.env:
        return False
    args = seg.words[1:]
    if seg.name == "sed":
        return _sed_on_stdin(args)
    if seg.name == "grep":
        patterns = [w for w in args if not _GREP_FLAGS.fullmatch(w)]
        # no glob characters: the shell could expand the pattern into file names
        return len(patterns) == 1 and not re.match(r"-|.*[*?\[]", patterns[0])
    if seg.name in {"head", "tail"}:
        i = 0
        while i < len(args):
            if args[i] == "-n" and i + 1 < len(args) and args[i + 1].isdigit():
                i += 2
            elif re.fullmatch(r"-n?\d+", args[i]):
                i += 1
            else:
                return False
        return True
    return False


def _sed_on_stdin(args: list[str]) -> bool:
    scripts = 0
    with_e = False
    i = 0
    while i < len(args):
        word = args[i]
        if word in {"-E", "-r", "-n"}:
            i += 1
        elif word == "-e" and i + 1 < len(args) and _SED_SUB.fullmatch(args[i + 1]):
            scripts, with_e, i = scripts + 1, True, i + 2
        elif not with_e and scripts == 0 and _SED_SUB.fullmatch(word):
            scripts, i = 1, i + 1
        else:
            return False  # a file operand, a file flag, or a script that is not one `s`
    return scripts > 0


def _is_test_db(url: str) -> bool:
    return url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] == "expense_world_test"


def _is_seed(ctx: Context, seg: Segment, cwd: Path) -> bool:
    """`deploy/local/seed-test-user.sh --force` (maybe through bash/sh), by any path."""
    script = seg.words[1:] if seg.name in {"bash", "sh"} else seg.words
    if len(script) != 2 or script[1] != "--force":
        return False
    target = ctx.resolve(script[0], cwd) or (cwd / script[0]).resolve()
    seed = (ctx.engine / "deploy" / "local" / "seed-test-user.sh").resolve()
    return is_within(target, seed)  # the same file, compared the way every path is


def _tester_op(ctx: Context, seg: Segment, cwd: Path) -> bool:
    """The ops-guide commands the tester may run in the engine checkout."""
    words = seg.words
    if words[:1] and words[0] in _START_PYTHONS and words[1:] == _START_ARGS:
        names = {k.upper() for k in seg.env}  # the engine ignores name case
        # only the two URLs the engine reads: no PYTHONPATH, no name the engine ignores
        only_db = names <= {"SUPABASE_DB_URL", "ADMIN_DB_URL"}
        return bool(names) and only_db and all(_is_test_db(v) for v in seg.env.values())
    if seg.env:
        return False
    if _is_seed(ctx, seg, cwd):
        return True
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
    substitutes = any(s in command for s in _SUBSTITUTIONS)
    shell_state = any(s.name in _SHELL_STATE for s in all_segments)
    seed_pipe = False
    oldpwd: Path | None = None  # the folder a `cd -` returns to, once a `cd` has named it
    for seg in all_segments:  # the live engine first: it is the worst slip in any command
        reason = _live_reason(seg, command)
        if reason:
            return reason
    for index, seg in enumerate(all_segments):
        target = None
        if seg.name == "cd":
            word = seg.words[1] if len(seg.words) > 1 else "~"  # a bare `cd` goes home
            if word == "-":
                target = oldpwd
            else:
                target = ctx.resolve(word, cwd) or (cwd / word).resolve()
        name = seg.words[0] if seg.words else ""
        raws = [raw for raw in _path_words(seg) if not (raw == name and "/" not in raw)]
        paths = [p for raw in raws if (p := ctx.resolve_word(raw, cwd))]
        if target is not None:
            paths.append(target)
        redirects = [
            ctx.resolve(raw, cwd) or (cwd / raw).resolve() for raw in seg.redirects + seg.inputs
        ]
        here = [] if seg.name == "cd" else [cwd]  # a command run in a folder reads there
        for path in [*paths, *redirects, *here]:
            reason = ctx.outside_reason(path)
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
        # The practice user's key never reaches a file: the seed and every filter it pipes
        # into may redirect only to /dev/null, and only stdin filters may read its output.
        if _is_seed(ctx, seg, cwd):
            seed_pipe = True
            if any(raw != "/dev/null" for raw in seg.redirects):
                return f"{STAY}: the practice user's key never goes to a file (only /dev/null)"
        elif seed_pipe and seg.piped:
            if not _filters_stdin(seg) or seg.inputs or _expands(seg):
                return (
                    f"{STAY}: the seed's output goes only through a stdin filter "
                    "(`sed 's/…/…/'`, `grep`, `head`, `tail`), never to a file"
                )
            if any(raw != "/dev/null" for raw in seg.redirects):
                return f"{STAY}: the practice user's key never goes to a file (only /dev/null)"
        else:
            seed_pipe = False
        # a bare `cd <dir>` out of the engine checkout reads nothing there
        leaving = (
            seg.name == "cd"
            and len(seg.words) <= 2
            and not (seg.env or redirects)
            and not (target and ctx.in_engine(target))
        )
        touches = ctx.in_engine(cwd) or any(ctx.in_engine(p) for p in [*paths, *redirects])
        if touches and (substitutes or shell_state):
            return (
                f"{STAY}: no agent reads the engine checkout; a command there may not hold "
                "`$(…)`, backticks, `<(…)`, `>(…)` or a shell-state builtin (`export`, …)"
            )
        if touches and not leaving:
            if any(ctx.in_engine(p) for p in redirects):
                return f"{STAY}: no agent reads or writes the engine checkout (a redirect)"
            tester_ok = (
                ctx.tester
                and not _expands(seg)
                and (stops or _tester_idle(seg) or _filters_stdin(seg) or _tester_op(ctx, seg, cwd))
            )
            if not tester_ok:
                who = (
                    "the tester may only start the :8002 test engine, reseed the practice "
                    "user and stop what it started"
                    if ctx.tester
                    else "only the tester goes there, to start the test engine"
                )
                return f"{STAY}: no agent reads or writes the engine checkout; {who}"
        if target is not None:
            oldpwd, cwd = cwd, target
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
