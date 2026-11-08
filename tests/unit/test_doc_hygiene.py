"""Doc hygiene guard (CLAUDE.md doc rules (5) "No provenance" and (6) "Point, don't restate").

Three checks keep a clean-up clean: no doc and no code in expense/, tests/ and scripts/ carries
a provenance tag (a mockup pane, a pick letter, an owner-and-date stamp; a bare "3 A" passes in
code), and each doc stays under a word budget.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

# docs/todo.md is out of the provenance scan: its owner questions point at mockup panes.
PROVENANCE_DOCS = sorted(
    [REPO_ROOT / "CLAUDE.md", REPO_ROOT / "README.md", REPO_ROOT / "AGENTS.md"]
    + [p for p in DOCS.glob("*.md") if p.name != "todo.md"]
)
BUDGET_DOCS = sorted(PROVENANCE_DOCS + [DOCS / "todo.md"])

# Case-insensitive; a spaced option letter must be a capital, so prose such as "screen 3 a row"
# stays legal. A bare "screen N" or "question N" is not a tag; "pane N" always is.
_LETTER = r"(?:\s?(?-i:[A-Z])|[a-z])"
_OWNER_STAMP_DOC = re.compile(r",\s*owner\)", re.IGNORECASE)
_PROVENANCE = [
    re.compile(r"\bpanes?\s+\d+[a-z]?\b", re.IGNORECASE),
    re.compile(rf"\bscreen\s+\d+{_LETTER}\b", re.IGNORECASE),
    re.compile(r"\bscreens\s+\d+\b", re.IGNORECASE),
    re.compile(rf"\bpicks?\s+\d+{_LETTER}\b", re.IGNORECASE),
    re.compile(rf"\bquestions?\s+\d+,?{_LETTER}\b", re.IGNORECASE),
    re.compile(r"\bquestions?\s+\d+,\s*(?-i:[A-Z])\b", re.IGNORECASE),
    re.compile(r"\(owner,\s*\d{4}-\d{2}-\d{2}\)", re.IGNORECASE),
    _OWNER_STAMP_DOC,
]

# Each doc's ceiling: its word count (`wc -w`) rounded up to the next 100, plus about 10%.
BUDGETS = {
    "AGENTS.md": 110,
    "CLAUDE.md": 3400,
    "README.md": 330,
    "docs/commands.md": 2530,
    "docs/decisions.md": 18000,
    "docs/file-import-plan.md": 220,
    "docs/runtime.md": 3500,
    "docs/todo.md": 2970,
    "docs/tui.md": 26800,
}


# CLAUDE.md rule (5) quotes the tags it forbids; that one sentence is not scanned.
_RULE_5 = re.compile(r"\*\*\(5\) No provenance\*\*.*?(?=\*\*\(6\))", re.DOTALL)


def _provenance_hits(rel: str, text: str) -> list[str]:
    text = _RULE_5.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    hits = []
    for pattern in _PROVENANCE:
        for match in pattern.finditer(text):
            lineno = text.count("\n", 0, match.start()) + 1
            hits.append(f"{rel}:{lineno}: {match.group(0)}")
    return hits


def _over_budget(rel: str, text: str, budgets: dict[str, int]) -> str | None:
    if rel not in budgets:
        return f"{rel} has no word budget: add it to BUDGETS in tests/unit/test_doc_hygiene.py"
    words = len(text.split())
    if words > budgets[rel]:
        return (
            f"{rel} is {words} words, over its budget of {budgets[rel]}: cut what restates "
            "code or another doc (CLAUDE.md doc rules (5) and (6)) before adding; "
            "raise the budget only in the same commit, saying why."
        )
    return None


def test_no_doc_holds_a_provenance_tag():
    hits = []
    for doc in PROVENANCE_DOCS:
        hits += _provenance_hits(doc.relative_to(REPO_ROOT).as_posix(), doc.read_text())
    assert not hits, (
        "Docs hold provenance tags (CLAUDE.md doc rule (5): state the fact, not where "
        "it was picked):\n  " + "\n  ".join(hits)
    )


def test_every_doc_is_within_its_word_budget():
    problems = []
    for doc in BUDGET_DOCS:
        rel = doc.relative_to(REPO_ROOT).as_posix()
        problem = _over_budget(rel, doc.read_text(), BUDGETS)
        if problem:
            problems.append(problem)
    assert not problems, "\n".join(problems)


def test_provenance_guard_trips():
    for text in (
        "as pane 10 draws it",
        "see panes 4, 5",
        "Pane 3",
        "pick 1 A",
        "picks 1A",
        "Question 2 B",
        "screen 3 C",
        "Done (owner, 2026-08-10)",
        "A heading, 2026-08-10, owner)",
        "pane 6A",
        "pane 3b",
        "pane 2c",
        "screens 1 to 5 of the mockup",
        "screens 1 to 4, 5 A and 6 A",
        "panes 4, 5, 8 and 9",
        "(owner, question 3, A, 2026)",
        "(question 8, B)",
        "see question 2, A)",
        "Pick 1 A",
        "Screen 2 A",
    ):
        assert _provenance_hits("docs/x.md", text), text
    quoted = '**(5) No provenance** — no "pane 10" or "pick 2 B". **(6) Point**'
    assert not _provenance_hits("CLAUDE.md", quoted)
    assert _provenance_hits("CLAUDE.md", quoted + " pane 10")
    hit = _provenance_hits("docs/x.md", "one\ntwo pane 10")[0]
    assert hit == "docs/x.md:2: pane 10"
    for text in (
        "§2",
        "80×24",
        "2 currencies",
        "the PDF preview's",
        "screen",
        "Question",
        "the pane that opens",
        "pick a row",
        "screen 3 columns",
        "the owner)",
        "a 30-row terminal",
        "screen 80 columns wide",
        "screen 3 a row",
        "question 3 is open",
        "pick 3 rows",
        "the screen 2 lines up",
    ):
        assert not _provenance_hits("docs/x.md", text), text


def test_budget_guard_trips():
    assert _over_budget("a.md", "one two three", {"a.md": 3}) is None
    over = _over_budget("a.md", "one two three four", {"a.md": 3})
    assert over is not None
    assert over.startswith("a.md is 4 words, over its budget of 3: cut what restates")
    missing = _over_budget("new.md", "one", {"a.md": 3})
    assert missing is not None
    assert "new.md has no word budget" in missing


def test_every_budget_names_a_doc_in_scope():
    assert set(BUDGETS) == {p.relative_to(REPO_ROOT).as_posix() for p in BUDGET_DOCS}


# Code guard: the same tags stay out of comments, docstrings, test names and parametrize ids.
CODE_ROOTS = ("expense", "tests", "scripts")
CODE_SUFFIXES = {".py", ".tcss"}
# This file holds the patterns and the samples that trip them; nothing else is exempt.
CODE_GUARD_INPUTS = {"tests/unit/test_doc_hygiene.py"}
_MOCKUP_FILE = re.compile(r"\bexpense-world-[\w-]*\.html\b")
# The docs' ", owner)" stamp is plain prose in code, so only the dated stamp is kept.
# An identifier or id joins the word and its number with "_" or "-": test_pane_4, "pane-4".
_NOT_ALNUM_BEFORE = r"(?<![^\W_])"
_NOT_ALNUM_AFTER = r"(?![^\W_])"


def _for_code(pattern: re.Pattern[str]) -> re.Pattern[str]:
    body = pattern.pattern.removeprefix(r"\b").removesuffix(r"\b")
    body = body.replace(r"\s+", r"[\s_-]+").replace(r"\s?", r"[\s_-]?")
    return re.compile(_NOT_ALNUM_BEFORE + body + _NOT_ALNUM_AFTER, pattern.flags)


_CODE_PROVENANCE = [_for_code(p) for p in _PROVENANCE if p is not _OWNER_STAMP_DOC]


def _mockup_stems() -> set[str]:
    return {p.stem for p in (DOCS / "mockups").glob("*.html")}


def _code_tag_hits(rel: str, text: str, stems: set[str]) -> list[str]:
    hits = []
    patterns = [*_CODE_PROVENANCE, _MOCKUP_FILE]
    if stems:
        names = "|".join(map(re.escape, sorted(stems)))
        patterns.append(re.compile(rf"\b(?:{names})\.html\b"))
    for pattern in patterns:
        for match in pattern.finditer(text):
            lineno = text.count("\n", 0, match.start()) + 1
            hits.append(f"{rel}:{lineno}: {match.group(0)}")
    return hits


def test_no_code_holds_a_mockup_tag():
    stems = _mockup_stems()
    hits = []
    for root in CODE_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if path.suffix not in CODE_SUFFIXES or rel in CODE_GUARD_INPUTS:
                continue
            if ".venv" in path.parts or "__pycache__" in path.parts:
                continue
            hits += _code_tag_hits(rel, path.read_text(), stems)
    assert not hits, (
        "Code holds mockup or provenance tags (state the fact, not which mockup pane or "
        "pick drew it):\n  " + "\n  ".join(hits)
    )


def test_code_tag_guard_trips():
    stems = {"quick-add-launcher-options", "accounts"}
    for text in (
        "# pane 4",
        "# Screen 1a",
        "# screens 1 to 3",
        "# pick 2 B",
        "# question 5 A",
        "# question 5, A",
        "def test_pane_4():",
        "def test_screen_1a():",
        'ids=["pane-4"]',
        "# (owner, 2026-10-21)",
        "# see expense-world-footers-fit.html",
        "# quick-add-launcher-options.html",
        "def test_x():  # panes 4, 5",
    ):
        assert _code_tag_hits("x.py", text, stems), text
    assert _code_tag_hits("x.py", "a\n# pane 4", stems) == ["x.py:2: pane 4"]
    for text in (
        "at 19:00 on 2026-10-21",
        "version 3.11.2",
        "l9 = row",
        "account = 'card-no-dollars'",
        'ids=["archived-account", "completed-statement"]',
        "color = '#1a2b3c'",
        "# 1. open the statement",
        "# step 2: refuse",
        "the screen 2 lines up",
        "(a bank, owner)",
        "# the accounts page",
        "def test_panel_4():",
        "def test_opane_4():",
    ):
        assert not _code_tag_hits("x.py", text, stems), text
