"""constraints.txt pins every package the app and its dev extra reach, so no install floats."""

import re
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement

CONSTRAINTS = Path(__file__).resolve().parents[2] / "constraints.txt"


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _reached() -> set[str]:
    """Every distribution reachable from the app with the dev extra, for this Python."""
    seen: dict[str, set[str]] = {}
    todo = [("expense-world-tui", {"dev"})]
    while todo:
        name, extras = todo.pop()
        name = _norm(name)
        if name in seen and extras <= seen[name]:
            continue
        seen.setdefault(name, set()).update(extras)
        for line in distribution(name).requires or []:
            req = Requirement(line)
            if req.marker is None or any(
                req.marker.evaluate({"extra": e}) for e in seen[name] | {""}
            ):
                todo.append((req.name, set(req.extras)))
    seen.pop("expense-world-tui")
    return set(seen)


def test_every_reached_package_is_pinned():
    pinned = {
        _norm(m.group(1))
        for line in CONSTRAINTS.read_text().splitlines()
        if (m := re.match(r"([A-Za-z0-9._-]+)==", line))
    }
    missing = sorted(_reached() - pinned)
    assert not missing, (
        f"not pinned in constraints.txt: {missing}; regenerate it as its header says"
    )
