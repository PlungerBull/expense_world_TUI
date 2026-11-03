"""Doc hygiene guard (CLAUDE.md doc rules (5) "No provenance" and (6) "Point, don't restate").

Two checks keep a clean-up clean: no doc carries a provenance tag (a mockup pane, a
pick letter, an owner-and-date stamp), and each doc stays under a word budget.
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
_PROVENANCE = [
    re.compile(r"\bpanes?\s+\d+[a-z]?\b", re.IGNORECASE),
    re.compile(rf"\bscreen\s+\d+{_LETTER}\b", re.IGNORECASE),
    re.compile(r"\bscreens\s+\d+\b", re.IGNORECASE),
    re.compile(rf"\bpicks?\s+\d+{_LETTER}\b", re.IGNORECASE),
    re.compile(rf"\bquestions?\s+\d+,?{_LETTER}\b", re.IGNORECASE),
    re.compile(r"\bquestions?\s+\d+,\s*(?-i:[A-Z])\b", re.IGNORECASE),
    re.compile(r"\(owner,\s*\d{4}-\d{2}-\d{2}\)", re.IGNORECASE),
    re.compile(r",\s*owner\)", re.IGNORECASE),
]

# Each doc's ceiling: its word count (`wc -w`) rounded up to the next 100, plus about 10%.
BUDGETS = {
    "AGENTS.md": 110,
    "CLAUDE.md": 4900,
    "README.md": 330,
    "docs/commands.md": 2530,
    "docs/decisions.md": 21200,
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
