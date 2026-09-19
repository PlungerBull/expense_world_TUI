"""Doc link-rot guard (CLAUDE.md "Docs must outlive any one contributor").

Every relative markdown link in the top-level docs must resolve. Links into
the sibling engine repo (../expense_world_engine) are verified only when that
checkout is present — the sibling layout is a documented assumption (README
"Checkout layout"), not something CI can rely on.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = REPO_ROOT.parent / "expense_world_engine"

DOC_FILES = sorted(
    [REPO_ROOT / "AGENTS.md", REPO_ROOT / "CLAUDE.md", REPO_ROOT / "README.md"]
    + list((REPO_ROOT / "docs").glob("*.md"))
)

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_FENCED_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")


def _relative_targets(doc: Path) -> list[str]:
    text = _INLINE_CODE.sub("", _FENCED_BLOCK.sub("", doc.read_text()))
    targets = []
    for raw in _LINK.findall(text):
        target = raw.split("#", 1)[0]  # drop in-page anchors
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        targets.append(target)
    return targets


def test_expected_doc_set_present():
    names = {p.name for p in DOC_FILES}
    assert {"AGENTS.md", "CLAUDE.md", "README.md", "decisions.md", "cli-spec.md"} <= names


def test_relative_doc_links_resolve():
    broken = []
    for doc in DOC_FILES:
        for target in _relative_targets(doc):
            resolved = (doc.parent / target).resolve()
            if resolved.is_relative_to(REPO_ROOT):
                if not resolved.exists():
                    broken.append(f"{doc.relative_to(REPO_ROOT)} -> {target}")
            elif ENGINE_ROOT.exists() and not resolved.exists():
                broken.append(f"{doc.relative_to(REPO_ROOT)} -> {target} (engine repo)")
    assert not broken, "Broken relative links:\n  " + "\n  ".join(broken)


# ---- decisions.md headings quoted from the source ---------------------------
# Code points at a decision rather than restating it (CLAUDE.md: the rationale,
# with rejected alternatives, lives in decisions.md). A pointer is only worth
# writing if a rename cannot silently orphan it, so the headings quoted from
# .py files are checked the way the markdown links above are.

DECISIONS = REPO_ROOT / "docs" / "decisions.md"
PKG = REPO_ROOT / "expense"

# `docs/decisions.md "Some heading"` — the form every pointer in the package
# uses. The quoted heading may wrap across lines (and across a comment's `#`
# markers), so the match spans newlines and the whitespace is normalised after.
# A trailing `.` or `,` inside the quotes is not part of the heading.
_POINTER = re.compile(r'decisions\.md\s*[,:]?\s*"([^"]{1,160})"')
_WRAP = re.compile(r"\s*\n\s*#?\s*")


def _decision_headings() -> set[str]:
    heads = set()
    for line in DECISIONS.read_text().splitlines():
        if line.startswith("## "):
            head = line[3:].strip()
            heads.add(head)
            # Entries are titled `Thing happened (2026-08-25)`; code cites the
            # title without the date, which is the stable half.
            heads.add(re.sub(r"\s*\((?:hardened\s+)?20\d\d-\d\d-\d\d.*\)$", "", head).strip())
    return heads


def _quoted_pointers() -> list[tuple[Path, int, str]]:
    found = []
    for path in sorted(PKG.rglob("*.py")):
        text = path.read_text()
        for match in _POINTER.finditer(text):
            heading = _WRAP.sub(" ", match.group(1)).strip().rstrip(" .,")
            lineno = text.count("\n", 0, match.start()) + 1
            found.append((path, lineno, heading))
    return found


def test_decision_pointers_in_code_resolve():
    headings = _decision_headings()
    broken = [
        f"{path.relative_to(REPO_ROOT)}:{lineno} -> {quoted!r}"
        for path, lineno, quoted in _quoted_pointers()
        if not any(quoted.lower() in head.lower() for head in headings)
    ]
    assert not broken, "Quoted decisions.md headings that no longer exist:\n  " + "\n  ".join(
        broken
    )
