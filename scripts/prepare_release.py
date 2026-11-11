#!/usr/bin/env python3
"""Prepare a release on `develop`; the owner's command (scripts/release.py) ships it.

    python3 scripts/prepare_release.py X.Y.Z

Sets `version` in pyproject.toml and moves CHANGELOG.md's `## Unreleased` lines under
`## vX.Y.Z — YYYY-MM-DD` (today), leaving an empty Unreleased. The loop then commits both and
waits for CI. It refuses an empty Unreleased, a version not above the last tag, and a dirty tree.

CHANGELOG.md format, owned here: `## Unreleased` first, then one `## vX.Y.Z — YYYY-MM-DD` entry
per release, newest first, each a list of bullets. When the engine must be upgraded first, the
entry opens with an `Upgrading:` line naming the engine version. It is one line; whoever writes
the Unreleased lines writes it, and this script keeps it first.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release  # noqa: E402  (the tag and git helpers the owner's command also uses)

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_LINE = re.compile(r'^version = "[^"]*"$', re.MULTILINE)
UNRELEASED = re.compile(r"^## Unreleased\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def prepare(root: Path, version: str, today: date) -> str:
    if not SEMVER.fullmatch(version):
        raise release.Refusal(f"`{version}` is not X.Y.Z.")
    if release.git(root, "status", "--porcelain"):
        raise release.Refusal("The tree has changes. Commit them first.")
    release.git(root, "fetch", "--tags", "origin")
    last = release.tags(root)[-1:]
    if last and release.version_key(version) <= release.version_key(last[0]):
        raise release.Refusal(f"{version} is not above the last release, {last[0]}.")
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text()
    if not VERSION_LINE.search(text):
        raise release.Refusal('pyproject.toml has no `version = "…"` line.')
    changelog = (root / "CHANGELOG.md").read_text()
    found = UNRELEASED.search(changelog)
    lines = found.group(1).strip().splitlines() if found else []
    if not lines:
        raise release.Refusal("CHANGELOG.md has nothing under `## Unreleased`.")
    lines.sort(key=lambda line: not line.startswith("Upgrading:"))
    entry = f"## v{version} — {today.isoformat()}\n\n" + "\n".join(lines) + "\n\n"
    assert found
    (root / "CHANGELOG.md").write_text(
        changelog[: found.start()] + "## Unreleased\n\n" + entry + changelog[found.end() :]
    )
    pyproject.write_text(VERSION_LINE.sub(f'version = "{version}"', text, count=1))
    return f"Prepared v{version}: commit pyproject.toml and CHANGELOG.md, then wait for CI."


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    try:
        print(prepare(Path(__file__).resolve().parent.parent, argv[0], date.today()))
    except release.Refusal as refusal:
        print(f"Refused: {refusal}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
