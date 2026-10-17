"""Doc link-rot guard (CLAUDE.md "Docs must outlive any one contributor").

Every relative link in the docs must resolve to a file inside this repo. The
engine is learned only from its live contract (`GET /openapi.json`, CLAUDE.md
"Key documentation"), so no doc links to or cites a path in the engine's
folder; the one exception is the tester's start/reseed commands for the
practice engine (docs/runtime.md "Working against the live engine").
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

DOC_FILES = sorted(
    [REPO_ROOT / "AGENTS.md", REPO_ROOT / "CLAUDE.md", REPO_ROOT / "README.md"]
    + list(DOCS.glob("*.md"))
    + list((DOCS / "specs").glob("*.md"))
    + list((DOCS / "to-engine").glob("*.md"))
)
# Scanned for engine-folder paths too: the mockups are HTML, not markdown links.
ENGINE_SCAN_FILES = DOC_FILES + sorted((DOCS / "mockups").glob("*.html"))

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
    names = {p.relative_to(REPO_ROOT).as_posix() for p in DOC_FILES}
    assert {
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "docs/decisions.md",
        "docs/commands.md",
        "docs/specs/README.md",
        "docs/to-engine/README.md",
    } <= names


def test_relative_doc_links_resolve():
    broken = []
    for doc in DOC_FILES:
        for target in _relative_targets(doc):
            resolved = (doc.parent / target).resolve()
            if not resolved.is_relative_to(REPO_ROOT):
                broken.append(f"{doc.relative_to(REPO_ROOT)} -> {target} (outside this repo)")
            elif not resolved.exists():
                broken.append(f"{doc.relative_to(REPO_ROOT)} -> {target}")
    assert not broken, "Broken relative links:\n  " + "\n  ".join(broken)


# ---- no path into the engine's folder ---------------------------------------
# The link check above strips code spans and never sees HTML, so a path written
# as text slips past it. These patterns catch the shapes such a path takes: a
# relative path to the engine folder, any path inside it, and the engine's own
# files named bare. The program's name alone (`expense_world_engine`) is not a
# path and passes.

_ENGINE_PATHS = [
    re.compile(r"(?:\.\./)+expense_world_engine\b"),
    re.compile(r"expense_world_engine/[\w.-]"),
    re.compile(r"\bengine-spec(?:\.md)?\b"),
    re.compile(r"\bdeploy/\w"),
    re.compile(r"\bsql/\d{3}"),
]

# The tester's start/reseed commands for the practice engine (CLAUDE.md "Stay
# inside this repo", docs/runtime.md "Working against the live engine").
# Each entry is (doc, exact text): a match wholly inside that text in that doc
# passes; the same text anywhere else is still caught.
_ALLOWED = [
    ("CLAUDE.md", "It starts the engine on `:8002` from `../expense_world_engine`"),
    ("CLAUDE.md", "`deploy/local/seed-test-user.sh --force`"),
    ("docs/runtime.md", "In the engine repo, `deploy/local/seed-test-user.sh` seeds"),
]


def _engine_path_hits(rel: str, text: str) -> list[str]:
    allowed = [
        (m.start(), m.end())
        for doc, snippet in _ALLOWED
        if doc == rel
        for m in re.finditer(re.escape(snippet), text)
    ]
    hits = []
    reported: list[tuple[int, int]] = []
    for pattern in _ENGINE_PATHS:
        for match in pattern.finditer(text):
            if any(lo <= match.start() and match.end() <= hi for lo, hi in allowed):
                continue
            # One path can match two patterns (`../x/docs/...`); report it once.
            if any(match.start() < hi and lo < match.end() for lo, hi in reported):
                continue
            reported.append(match.span())
            lineno = text.count("\n", 0, match.start()) + 1
            hits.append(f"{rel}:{lineno}: {match.group(0)}")
    return hits


def test_no_doc_cites_a_path_in_the_engine_folder():
    hits = []
    for doc in ENGINE_SCAN_FILES:
        hits += _engine_path_hits(doc.relative_to(REPO_ROOT).as_posix(), doc.read_text())
    assert not hits, (
        "Docs cite paths in the engine's folder. Cite the live contract instead "
        '(GET /openapi.json: "Section" or METHOD /v1/path), or say it in plain words:\n  '
        + "\n  ".join(sorted(hits))
    )


def test_every_allowlisted_snippet_is_still_in_its_doc():
    stale = [
        f"{doc}: {snippet}"
        for doc, snippet in _ALLOWED
        if snippet not in (REPO_ROOT / doc).read_text()
    ]
    assert not stale, "Stale _ALLOWED entries (drop or update them):\n  " + "\n  ".join(stale)


def test_engine_path_guard_trips():
    engine = "expense_world_engine"
    for text in (
        f"[spec](../../{engine}/docs/engine-spec.md)",
        f"see `../{engine}`",
        f"`{engine}/docs/decisions.md`",
        "engine-spec *Base Conventions*",
        "engine repo `deploy/local/README.md`",
        "`deploy/cloud/README.md`",
        "migration `sql/026`",
    ):
        assert _engine_path_hits("docs/x.md", text), text
    # A path matching two patterns is reported once.
    assert len(_engine_path_hits("docs/x.md", f"[s](../../{engine}/docs/a.md)")) == 1
    for doc, snippet in _ALLOWED:
        assert not _engine_path_hits(doc, snippet), snippet
        assert _engine_path_hits("docs/x.md", snippet), snippet
    # The program's name, and the sibling-checkout tree, are not paths into it.
    assert not _engine_path_hits("README.md", f"over the `{engine}` HTTP API")
    assert not _engine_path_hits("README.md", f"└── {engine}/   ← engine")


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


# ---- the five list orders carry their direction ------------------------------
# The contract states the order of accounts, categories, a category's tags,
# tags and an account's reconciliations with its direction. A doc or a comment
# that cites one of those "Ordering" rules gives the direction in the same
# paragraph, and none paraphrases an order as SQL. The owner's specs are not
# scanned: they list the citations under one sentence that carries the wording.

_ORDERING_CITATIONS = (
    '(contract: GET /v1/accounts, "Ordering")',
    '(contract: GET /v1/categories, "Ordering")',
    '(contract: GET /v1/categories/{category_id}/hashtags, "Ordering")',
    '(contract: "Reconciliations", "Ordering")',
)
_SQL_ORDER = re.compile(r"\b(?:date_start|created_at|sort_order|uses)`?\s+(?:ASC|DESC)\b")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t#:]*\n")

ORDER_SCAN_FILES = sorted(
    [doc for doc in DOC_FILES if doc.parent != DOCS / "specs"]
    + list(PKG.rglob("*.py"))
    + [p for p in (REPO_ROOT / "tests").rglob("*.py") if p != Path(__file__).resolve()]
)


def _order_hits(rel: str, text: str) -> list[str]:
    hits = [f"{rel}: SQL-style order `{m.group(0)}`" for m in _SQL_ORDER.finditer(text)]
    for paragraph in _PARAGRAPH_BREAK.split(text):
        flat = " ".join(paragraph.split())
        for citation in _ORDERING_CITATIONS:
            if citation in flat and "oldest first" not in flat:
                hits.append(f"{rel}: {citation} without its direction")
    return hits


def test_list_orders_state_their_direction():
    hits = []
    for path in ORDER_SCAN_FILES:
        hits += _order_hits(path.relative_to(REPO_ROOT).as_posix(), path.read_text())
    assert not hits, (
        'Give the order in the contract\'s words, direction included ("oldest first"):\n  '
        + "\n  ".join(hits)
    )


def test_list_order_guard_trips():
    for text in (
        "in period order (`date_start ASC, created_at ASC`)",
        "sorted by `sort_order` ASC",
        "by `uses` DESC",
        f"`uses` descending, then creation time\n{_ORDERING_CITATIONS[2]}.",
        f"# `date_start` ascending\n# {_ORDERING_CITATIONS[3]}\n#\n# oldest first, elsewhere",
    ):
        assert _order_hits("docs/x.md", text), text
    for citation in _ORDERING_CITATIONS:
        assert not _order_hits("docs/x.md", f"then creation time, oldest first\n  {citation}.")
