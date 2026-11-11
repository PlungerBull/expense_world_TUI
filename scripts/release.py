#!/usr/bin/env python3
"""The owner's release command, run in the live folder; it never runs anywhere else.

    python3 scripts/release.py          release the version on origin/develop
    python3 scripts/release.py back     install the tag before the one installed
    python3 scripts/release.py latest   install the newest tag again

The agents prepare a release on `develop` (scripts/prepare_release.py: the version in
pyproject.toml and the CHANGELOG entry, committed, CI green). This command writes no commit.
It moves `main` to that commit, tags it `vX.Y.Z`, pushes both, and reinstalls `expense` with
pipx: package `expense-world-tui`, not editable, Python 3.12, every dependency at the version
constraints.txt fixes.

The release is the commit on origin/develop that last changed pyproject's `[project] version`,
not develop's head. It refuses, and says what to do, when: it runs outside the live folder; the
tree is dirty; the live folder is on a branch other than `main`; develop has no prepared
release (the tag is already on origin, the version is not above the last tag, or CHANGELOG.md
has no entry for it); CI has not passed on that commit; `main` cannot fast-forward to it; the
push is rejected. After any refusal past the fetch, the live folder is as it was.

`back` and `latest` check out a tag or `main` and reinstall; `main` and the tags stay as they
are. After `back` the live folder is on a detached tag; a release (or `latest`) checks `main`
out again first, so a release works from there. Setup: README.md "Install (the owner's app)".
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

LIVE = Path("/Users/ternero/Library/Application Support/expense_world/tui")
PACKAGE = "expense-world-tui"
ENTRY = re.compile(r"^## v(\d+\.\d+\.\d+) — \d{4}-\d{2}-\d{2}$", re.MULTILINE)


class Refusal(Exception):
    """The command stops, and the message says what to do."""


def version_key(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in tag.lstrip("v").split("."))


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if done.returncode:
        raise Refusal(f"`git {' '.join(args)}` failed: {done.stderr.strip()}")
    return done.stdout.strip()


def tags(root: Path) -> list[str]:
    """Every release tag, oldest first."""
    return sorted(git(root, "tag", "--list", "v*").split(), key=version_key)


def _step(text: str) -> None:
    print(f"- {text}")


def _clean_tree(root: Path) -> None:
    if git(root, "status", "--porcelain"):
        raise Refusal("The live folder has changes. Nothing is written here by hand: undo them.")


def _in_live_folder(root: Path, live: Path) -> None:
    if root.resolve() != live.resolve():
        raise Refusal(f"This command runs only in the live folder, {live}. Run it there.")


def _install(root: Path, then: str) -> None:
    """Reinstall with pipx; on failure `then` says what to run after fixing it."""
    pip_args = f"-c {shlex.quote(str(root / 'constraints.txt'))}"
    _step("reinstalling expense with pipx")
    done = subprocess.run(
        [
            "pipx",
            "install",
            "--force",
            "--python",
            "python3.12",
            f"--pip-args={pip_args}",
            str(root),
        ]
    )
    if done.returncode:
        raise Refusal(f"pipx failed (its message is above). Fix that, then {then}")


def _ci_passed(root: Path, sha: str) -> bool:
    done = subprocess.run(
        ["gh", "run", "list", "--commit", sha, "--json", "status,conclusion"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if done.returncode:
        raise Refusal(f"`gh run list` failed: {done.stderr.strip()}")
    runs = json.loads(done.stdout)
    passed = [r["status"] == "completed" and r["conclusion"] == "success" for r in runs]
    return bool(passed) and all(passed)


def _version_at(root: Path, ref: str) -> str | None:
    """pyproject's `[project] version` at `ref`, None when there is none (or no such commit)."""
    done = subprocess.run(
        ["git", "show", f"{ref}:pyproject.toml"], cwd=root, capture_output=True, text=True
    )
    if done.returncode:
        return None
    return tomllib.loads(done.stdout).get("project", {}).get("version")


def _prepared_commit(root: Path) -> str:
    """The newest commit on origin/develop whose version differs from its parent's."""
    for sha in git(root, "log", "--format=%H", "origin/develop", "--", "pyproject.toml").split():
        if _version_at(root, sha) != _version_at(root, f"{sha}^"):
            return sha
    raise Refusal("develop has no prepared release: no commit sets a version. Ask the loop.")


def release(root: Path, live: Path = LIVE) -> str:
    _in_live_folder(root, live)
    _clean_tree(root)
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch not in ("main", "HEAD"):
        raise Refusal(f"The live folder is on `{branch}`, not `main`. Run `git checkout main`.")
    _step("fetching")
    git(root, "fetch", "--tags", "origin")
    sha = _prepared_commit(root)
    version = _version_at(root, sha)
    tag = f"v{version}"
    unprepared = "develop has no prepared release: "
    ask = " Ask the loop to prepare one."
    if version is None:
        raise Refusal(f"{unprepared}the newest version change removes the version.{ask}")
    released = tags(root)[-1:]
    if git(root, "ls-remote", "--tags", "origin", f"refs/tags/{tag}"):
        raise Refusal(f"{unprepared}{tag} is already released.{ask}")
    if released and version_key(tag) <= version_key(released[0]):
        raise Refusal(f"{unprepared}{tag} is not above the last release, {released[0]}.{ask}")
    if version not in ENTRY.findall(git(root, "show", f"{sha}:CHANGELOG.md")):
        raise Refusal(f"{unprepared}CHANGELOG.md has no entry for {tag}.{ask}")
    if not _ci_passed(root, sha):
        raise Refusal(f"CI has not passed on the {tag} commit ({sha[:8]}). Wait, then run again.")
    _step(f"moving main to {sha[:8]}")
    start = git(root, "rev-parse", "HEAD") if branch == "HEAD" else "main"
    before = git(root, "rev-parse", "main")
    try:
        git(root, "checkout", "main")
        try:
            git(root, "merge", "--ff-only", sha)
        except Refusal as err:
            raise Refusal(f"main cannot fast-forward to the {tag} commit. Ask the loop.") from err
        _step(f"tagging {tag} and pushing")
        git(root, "tag", tag, sha)
        git(root, "push", "--atomic", "origin", "main", f"refs/tags/{tag}")
    except Refusal as err:
        git(root, "reset", "--hard", before)
        if tag in tags(root):
            git(root, "tag", "-d", tag)
        if start != "main":
            git(root, "checkout", "--detach", start)
        raise Refusal(f"{err} Nothing changed; run this again.") from err
    _install(root, "run `scripts/release.py latest`.")
    return f"Released {tag}."


def _installed_tag(root: Path) -> str:
    return git(root, "describe", "--tags", "--abbrev=0", "HEAD")


def back(root: Path, live: Path = LIVE) -> str:
    _in_live_folder(root, live)
    _clean_tree(root)
    all_tags = tags(root)
    current = _installed_tag(root)
    earlier = [t for t in all_tags if version_key(t) < version_key(current)]
    if not earlier:
        raise Refusal(f"There is no release before {current}.")
    previous = earlier[-1]
    git(root, "checkout", "--detach", previous)
    _install(
        root,
        "run `scripts/release.py latest` to return (`back` again goes one release further).",
    )
    return (
        f"Installed {previous}; the live folder sits on that tag; main and the tags stay.\n"
        "To return: run `scripts/release.py latest`, or release the next version."
    )


def latest(root: Path, live: Path = LIVE) -> str:
    _in_live_folder(root, live)
    _clean_tree(root)
    git(root, "checkout", "main")
    _install(root, "run `scripts/release.py latest` again.")
    return f"Installed main, {_installed_tag(root)}."


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    commands = {"": release, "back": back, "latest": latest}
    if len(argv) > 1 or (argv and argv[0] not in commands):
        print(__doc__)
        return 2
    try:
        print(commands[argv[0] if argv else ""](root))
    except Refusal as refusal:
        print(f"Refused: {refusal}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
