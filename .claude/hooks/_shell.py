"""Shared plumbing for the Claude Code hooks in this folder (stdlib only).

Holds what more than one hook needs: where the repo and the home folder are, reading the
hook's JSON input, and a rough split of a Bash command into its simple commands.

The split is a tripwire's reading of a command, not a shell parser:

- `shlex` in POSIX mode splits words and keeps quoted text whole; `;`, `&`, `|`, `(`, `)`
  and newlines separate commands. A command straight after `|` or `|&` (parentheses or a
  newline written against the bar count too: `(a)|b`, `a |(b)`, `a |⏎b`) is marked piped;
  a command after anything else, such as `(a; b) | c`'s `c` after `b`, is not.
  `<`/`>` operators (with any file-descriptor digits written against them, as in `2>&1`)
  and the word after them are redirects. A `( … )` group is not tracked: its commands are
  separate, and a redirect after the `)` (`(a) > f`) belongs to no command.
- Leading `NAME=value` words are the command's environment; the wrappers `env`, `nohup`,
  `exec`, `command` and `time` are stepped over.
- A backslash-newline continuation joins its two lines first.
- Heredoc bodies, `$(...)`, backticks, variables other than `$HOME`, aliases and functions
  are not understood. A command shlex cannot split (unbalanced quotes) falls back to
  splitting on `;`, `&&`, `||`, `|` and newlines, then on whitespace.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SEPARATOR_CHARS = frozenset(";&|\n()")
_WRAPPERS = frozenset({"env", "nohup", "exec", "command", "time"})


def repo_root() -> Path:
    """The repo: `$CLAUDE_PROJECT_DIR`, else the folder two levels above this file."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[2]


def home_dir() -> Path:
    """The home folder; `EXPENSE_HOOKS_HOME` overrides it for the hook tests."""
    env = os.environ.get("EXPENSE_HOOKS_HOME")
    return Path(env).resolve() if env else Path.home().resolve()


def read_input() -> dict[str, Any]:
    """The hook's JSON input from stdin; an unreadable input counts as empty."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def venv_env(repo: Path) -> dict[str, str]:
    """The current environment with the repo's `.venv/bin` first on PATH."""
    env = dict(os.environ)
    env["PATH"] = f"{repo / '.venv' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def is_within(path: Path, root: Path) -> bool:
    """`path` is `root` or below it (case-insensitive on macOS, whose disk is)."""
    if sys.platform == "darwin":
        return str(path).casefold().startswith(str(root).casefold().rstrip("/") + "/") or (
            str(path).casefold() == str(root).casefold()
        )
    return path == root or root in path.parents


_FD_PREFIX = re.compile(r"(?<![^\s;&|(])\d+(?=[<>])")  # the `2` in `2>&1`


def tokens(command: str) -> list[str]:
    command = _FD_PREFIX.sub("", command.replace("\\\n", " "))
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return re.sub(r"&&|\|\||[;|\n]", " ; ", command).split()


def _is_separator(token: str) -> bool:
    return bool(token) and all(ch in _SEPARATOR_CHARS for ch in token)


def _is_redirect(token: str) -> bool:
    return bool(token) and ("<" in token or ">" in token) and all(ch in "<>&|" for ch in token)


def _is_assignment(token: str) -> bool:
    name, sep, _ = token.partition("=")
    return bool(sep) and name.isidentifier()


@dataclass
class Segment:
    """One simple command: its env prefix, its words, and the files it redirects to/from."""

    env: dict[str, str] = field(default_factory=dict)
    words: list[str] = field(default_factory=list)
    redirects: list[str] = field(default_factory=list)  # `>`/`>>` targets: writes
    inputs: list[str] = field(default_factory=list)  # `<` sources: reads
    piped: bool = False  # its stdin is the previous command's output (`|` or `|&`)

    @property
    def name(self) -> str:
        """The command's basename (`/x/.venv/bin/expense` -> `expense`), or ''."""
        return self.words[0].rsplit("/", 1)[-1] if self.words else ""


def _segment(raw: list[str], piped: bool = False) -> Segment:
    seg = Segment(piped=piped)
    rest: list[str] = []
    i = 0
    while i < len(raw):
        tok = raw[i]
        if _is_redirect(tok):
            if i + 1 < len(raw) and not tok.endswith("&"):
                if ">" in tok:
                    seg.redirects.append(raw[i + 1])
                elif tok == "<":
                    seg.inputs.append(raw[i + 1])
                # `<<` / `<<<`: a heredoc delimiter or a here-string, not a file
            i += 2
            continue
        rest.append(tok)
        i += 1
    while rest and (_is_assignment(rest[0]) or rest[0] in _WRAPPERS):
        tok = rest.pop(0)
        if _is_assignment(tok):
            name, _, value = tok.partition("=")
            seg.env[name] = value
    seg.words = rest
    return seg


def segments(command: str) -> list[Segment]:
    """The simple commands in `command`, in order (see the module docstring for limits)."""
    out: list[Segment] = []
    current: list[str] = []
    piped = False
    for tok in tokens(command):
        if _is_separator(tok):
            if current:
                out.append(_segment(current, piped))
            current = []
            # `|` or `|&`, also run into parentheses or a newline (`(a)|b`, `a |(b)`, `a |⏎b`)
            piped = re.sub(r"[()\n]", "", tok) in {"|", "|&"}
        else:
            current.append(tok)
    if current:
        out.append(_segment(current, piped))
    return out


def git_args(seg: Segment) -> tuple[str, list[str]] | None:
    """For a `git` command: its subcommand and the words after it; otherwise None.

    Steps over git's own options before the subcommand (`-C <dir>`, `-c <k=v>`, `--x=y`).
    """
    if seg.name != "git":
        return None
    words = seg.words[1:]
    i = 0
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in {"-C", "-c", "--git-dir", "--work-tree", "--namespace"} else 1
    if i >= len(words):
        return ("", [])
    return (words[i], words[i + 1 :])


def is_git_commit(command: str) -> bool:
    """`command` runs `git commit` somewhere in it."""
    return any((ga := git_args(seg)) is not None and ga[0] == "commit" for seg in segments(command))
