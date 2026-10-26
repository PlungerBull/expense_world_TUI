"""Contract: every `(contract: …)` citation in the repo names a part the live contract holds.

Code comments, tests, scripts and docs point into the contract instead of restating it
(CLAUDE.md "Key documentation"). A pointer is only worth writing if a move or a rename in
the contract cannot orphan it silently, so this reads `GET /openapi.json` and checks every
citation in the repo's tracked and new files against it, naming each `file:line` it does
not hold. The forms, and where each is looked up:

  · `(contract: METHOD /v1/path)`: the contract has that operation.
  · `(contract: METHOD /v1/path, "Part")`: the operation has `Part` as a heading in its
    own `description`.
  · `(contract: "Section", "Part")`: `Section` is a tag name or a markdown section of the
    general description (`info.description`) or of a tag's description, and `Part` is a
    heading inside it. A tag holds its whole description; a markdown section runs to the
    next heading of its level or higher.
  · `(contract: "Part")`: `Part` is a heading anywhere in the contract (the general
    description, a tag's description or an operation's) or a tag name.

A heading, as the contract writes them, is one of:

  · a markdown heading line, `## Base Conventions` or `### Ordering`: the text after the
    `#`s;
  · a bold lead: a `**…**` span that opens a line, alone or after a list marker
    (`**Idempotency:** …`, `- **Staleness:** …`, `**Sealed periods.** …`,
    `**Filters,** …`, `**The built-in pending hashtag** (…) …`): the bold text without a
    closing `:`, `.` or `,`.

Nothing else is a heading: a bold span later in a line is emphasis, a bold cell is table
content, and the contract's `*Name*` italics refer to a heading, never make one. Names are
compared exactly, as written, after collapsing whitespace; a citation in code may wrap
across comment lines (`#`, `#:`), and is read joined.

Not scanned: docs/from-engine/ (the engine's own words, read once and deleted) and this
file. Not citations: `(contract: …)` written with an ellipsis, which names the form, and
CLAUDE.md's examples of the form (`_FORMAT_EXAMPLES`).

Read-only: nothing is written to the engine. Gating and target: conftest.py.
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()

SKIPPED_DIRS = ("docs/from-engine/",)

# CLAUDE.md "Key documentation" shows the four forms with placeholder names.
_FORMAT_EXAMPLES = {
    ("CLAUDE.md", '"Part"'),
    ("CLAUDE.md", '"Section", "Part"'),
    ("CLAUDE.md", "METHOD /v1/path"),
    ("CLAUDE.md", 'METHOD /v1/path, "Part"'),
}

_OPEN = "(contract:"
# The body runs to the first `)` outside a quoted name: a name may hold parentheses
# (the tag `Transactions (Ledger)`), a path never does.
_CITATION = re.compile(r'\(contract:((?:[^()"]|"[^"]*")*)\)')
# A citation wrapped across comment lines reads as one line.
_WRAP = re.compile(r"\s*\n\s*(?:#:?)?\s*")
_OPERATION = re.compile(r"^(GET|POST|PUT|PATCH|DELETE) (/\S+?)(?=,|$)")
_NAME = re.compile(r'"([^"]*)"')
_NAMES_ONLY = re.compile(r'^"[^"]*"(?:, "[^"]*")?$')

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_BOLD_LEAD = re.compile(r"^[ \t]*(?:[-*+][ \t]+|\d+\.[ \t]+)?\*\*(.+?)\*\*", re.MULTILINE)


def _squash(text: str) -> str:
    return " ".join(text.split())


def _headings(text: str) -> set[str]:
    """Every heading in one description, as the module docstring defines it."""
    text = _FENCE.sub("", text or "")
    names = {_squash(m.group(2)) for m in _MARKDOWN_HEADING.finditer(text)}
    names |= {_squash(m.group(1)).rstrip(":.,").rstrip() for m in _BOLD_LEAD.finditer(text)}
    return names


def _markdown_sections(text: str) -> dict[str, str]:
    """Each markdown heading's name and its text, up to the next heading of its level
    or higher."""
    text = _FENCE.sub("", text or "")
    found = list(_MARKDOWN_HEADING.finditer(text))
    sections: dict[str, str] = {}
    for i, heading in enumerate(found):
        level = len(heading.group(1))
        end = next((h.start() for h in found[i + 1 :] if len(h.group(1)) <= level), len(text))
        name = _squash(heading.group(2))
        sections[name] = sections.get(name, "") + text[heading.end() : end]
    return sections


@dataclass
class Contract:
    """Where each kind of citation is looked up."""

    operations: dict[str, set[str]] = field(default_factory=dict)  # "PUT /v1/x" → headings
    places: dict[str, set[str]] = field(default_factory=dict)  # tag or section → headings
    anywhere: set[str] = field(default_factory=set)

    @classmethod
    def from_openapi(cls, spec: dict) -> "Contract":
        contract = cls()
        general = spec.get("info", {}).get("description", "")
        tags = {t["name"]: t.get("description", "") for t in spec.get("tags", [])}
        for name, text in tags.items():
            contract.places.setdefault(name, set()).update(_headings(text))
        for text in [general, *tags.values()]:
            for name, body in _markdown_sections(text).items():
                contract.places.setdefault(name, set()).update(_headings(body))
            contract.anywhere |= _headings(text)
        contract.anywhere |= set(tags)
        for path, item in spec.get("paths", {}).items():
            for method, operation in item.items():
                if isinstance(operation, dict) and "responses" in operation:
                    heads = _headings(operation.get("description", ""))
                    contract.operations[f"{method.upper()} {path}"] = heads
                    contract.anywhere |= heads
        return contract

    def miss(self, body: str) -> str | None:
        """Why the contract does not hold the citation `body`, or None when it does."""
        operation = _OPERATION.match(body)
        if operation:
            name, rest = operation.group(0), body[operation.end() :]
            names = _NAME.findall(rest)
            if rest and not re.fullmatch(r', "[^"]*"', rest):
                return "not one of the citation forms"
            if name not in self.operations:
                return f"the contract has no operation {name}"
            if names and names[0] not in self.operations[name]:
                return f"{name} has no heading {names[0]!r}"
            return None
        if not _NAMES_ONLY.match(body):
            return "not one of the citation forms"
        names = _NAME.findall(body)
        if len(names) == 2:
            section, part = names
            if section not in self.places:
                return f"the contract has no tag or section {section!r}"
            if part not in self.places[section]:
                return f"{section!r} has no heading {part!r}"
            return None
        if names[0] not in self.anywhere:
            return f"the contract has no heading or tag {names[0]!r}"
        return None


def citations(rel: str, text: str) -> list[tuple[int, str | None]]:
    """(line, body) of each citation in one file; body is None where `(contract:`
    opens something that cannot be read as a citation."""
    found: list[tuple[int, str | None]] = []
    start = text.find(_OPEN)
    while start != -1:
        lineno = text.count("\n", 0, start) + 1
        match = _CITATION.match(text, start)
        body = _WRAP.sub(" ", match.group(1)).strip() if match else None
        if body != "…" and (rel, body) not in _FORMAT_EXAMPLES:
            found.append((lineno, body))
        start = text.find(_OPEN, start + len(_OPEN))
    return found


def broken_citations(contract: Contract, files: dict[str, str]) -> list[str]:
    """`file:line: citation — why` for each citation the contract does not hold."""
    broken = []
    for rel, text in sorted(files.items()):
        for lineno, body in citations(rel, text):
            if body is None:
                broken.append(f"{rel}:{lineno}: `{_OPEN}` — unreadable: no closing `)`")
            elif why := contract.miss(body):
                broken.append(f"{rel}:{lineno}: (contract: {body}) — {why}")
    return broken


def repo_files(root: Path = REPO_ROOT) -> dict[str, str]:
    """Every tracked or new (not ignored) text file under `root`, a git work tree,
    minus the skipped ones, keyed by its path from `root`."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    files = {}
    for rel in listed:
        path = root / rel
        if rel == SELF or rel.startswith(SKIPPED_DIRS) or not path.is_file():
            continue
        try:
            files[rel] = path.read_text()
        except UnicodeDecodeError:
            continue  # a spreadsheet or another binary holds no citation
    return files


def _live_contract(client) -> Contract:
    # `/openapi.json` sits at the root, outside `/v1`, and needs no login: the
    # client's own transport reads it, as the `statuses` fixture reads its hooks.
    response = client._client.get("/openapi.json")
    assert response.status_code == 200, response.text
    return Contract.from_openapi(response.json())


def test_every_citation_in_the_repo_resolves_against_the_live_contract(client):
    files = repo_files()
    assert "CLAUDE.md" in files and "expense/errors.py" in files
    assert sum(len(citations(rel, text)) for rel, text in files.items()) > 100
    broken = broken_citations(_live_contract(client), files)
    assert not broken, (
        "Citations the live contract does not hold — point each at the part that states "
        "the rule now (CLAUDE.md 'Key documentation'):\n  " + "\n  ".join(broken)
    )


def test_every_format_example_is_still_in_claude_md():
    text = (REPO_ROOT / "CLAUDE.md").read_text()
    stale = [body for _, body in sorted(_FORMAT_EXAMPLES) if f"(contract: {body})" not in text]
    assert not stale, "Stale _FORMAT_EXAMPLES entries (drop or update them): " + repr(stale)


# ---- the check catches a broken citation -------------------------------------

_SAMPLE_CONTRACT = {
    "info": {
        "description": (
            "## Base Conventions\n\n"
            "**Idempotency:** writes take a key.\n\n"
            "**A delete is final.** No route undeletes.\n"
            "- **Cursors, on every cursor-paged list:** opaque.\n"
            "Prose with **Bold mid-line:** is emphasis.\n"
            "| **Unpaged** | a table cell |\n\n"
            "```\n## Not a heading\n```\n\n"
            "## Error codes\n\nSee *Idempotency*.\n"
        )
    },
    "tags": [
        {
            "name": "Transactions (Ledger)",
            "description": "**Sealed periods.** A completed reconciliation seals.",
        },
        {
            "name": "Activity Log",
            "description": (
                "### Action codes\n\nA table.\n\n"
                "### Aggregate exceptions\n\n- **Hashtag links.** Not logged.\n"
            ),
        },
    ],
    "paths": {
        "/v1/exchange-rates": {
            "get": {
                "description": "- **Staleness:** `rate_date` is the day used.",
                "responses": {},
            }
        },
        "/v1/categories/{category_id}": {
            "put": {"description": "Renames follow the POST rules.", "responses": {}}
        },
    },
}

_HELD = (
    '(contract: "Base Conventions", "Idempotency")',
    '(contract: "Base Conventions", "A delete is final")',
    '(contract: "Base Conventions", "Cursors, on every cursor-paged list")',
    '(contract: "Error codes")',
    '(contract: "Transactions (Ledger)", "Sealed periods")',
    '(contract: "Sealed periods")',
    '(contract: "Aggregate exceptions", "Hashtag links")',
    '(contract: "Activity Log", "Hashtag links")',
    '(contract: GET /v1/exchange-rates, "Staleness")',
    "(contract: PUT /v1/categories/{category_id})",
    '# wrapped (contract: GET\n# /v1/exchange-rates, "Staleness") across a comment',
    '#: wrapped (contract: "Base Conventions", "A delete\n#: is final") in a `#:` block',
    "how a citation looks: (contract: …)",
)

_BROKEN = {
    '(contract: "Base Conventions", "There is no restore")': "has no heading",
    '(contract: "Staleness: `rate_date` is the signal")': "no heading or tag",
    '(contract: PUT /v1/categories/{category_id}, "Reserved names on rename")': "no heading",
    "(contract: DELETE /v1/exchange-rates)": "no operation",
    '(contract: "Aggregate exceptions", "Action codes")': "has no heading",
    '(contract: "Activity Log", "Aggregate exceptions item 3")': "has no heading",
    '(contract: "Bank Accounts", "Balances")': "no tag or section",
    '(contract: "Base Conventions", "Bold mid-line")': "has no heading",
    '(contract: "Unpaged")': "no heading or tag",
    '(contract: "Not a heading")': "no heading or tag",
    '(contract: "Error codes", "Idempotency")': "has no heading",
    '(contract: "Idempotency.")': "no heading or tag",
    "(contract: GET /v1/exchange-rates Staleness)": "not one of the citation forms",
    '(contract: "A", "B", "C")': "not one of the citation forms",
    "(contract: Base Conventions)": "not one of the citation forms",
    '(contract: "Base Conventions", "Idempotency"': "unreadable",
}


def test_citation_check_holds_the_good_and_names_each_broken_one():
    contract = Contract.from_openapi(_SAMPLE_CONTRACT)
    good = {f"docs/held{i}.md": text for i, text in enumerate(_HELD)}
    assert broken_citations(contract, good) == []
    bad = {f"docs/broken{i}.md": f"line one\n{text}\n" for i, text in enumerate(_BROKEN)}
    reported = broken_citations(contract, bad)
    assert len(reported) == len(_BROKEN), "\n".join(reported)
    for i, why in enumerate(_BROKEN.values()):
        line = next(r for r in reported if r.startswith(f"docs/broken{i}.md:2: "))
        assert why in line, line


def test_citation_check_skips_claude_md_examples_only_in_claude_md():
    example = '(contract: "Section", "Part")'
    assert citations("CLAUDE.md", example) == []
    assert citations("docs/runtime.md", example) == [(1, '"Section", "Part"')]
