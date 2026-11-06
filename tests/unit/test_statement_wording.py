"""The app says "statement", never "reconciliation", in words a person reads.

The engine and the bank's paper both say "statement", and so does the app. The scan reads every
string literal in `expense/` (a docstring is not one: no one reads it on a screen) and fails on
"reconcil" in any case, bar the engine's own names, which are never reworded: an error code
(`RECONCILIATION_NOT_DRAFT`, capitals with an underscore) and the keys named in `KEYS`, each
exempt only as the whole string. It sees words the code writes itself; it cannot see an engine
message shown as the engine sent it (that arrives at run time) nor words assembled from pieces,
and it does not read comments or identifiers.
"""

import ast
import re
from pathlib import Path

import pytest

import expense

ROOT = Path(expense.__file__).parent

# An engine error code: capitals with at least one underscore.
CODE = re.compile(r"\b(?=[A-Z]*_)[A-Z_]*RECONCIL[A-Z_]*\b")
# Keys that are not words: the Home dispatch key and the engine's query key.
KEYS = frozenset({"statements", "unreconciled"})
WORD = re.compile("reconcil", re.IGNORECASE)


def says_reconciliation(value: str) -> bool:
    return value not in KEYS and bool(WORD.search(CODE.sub("", value)))


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _literals_with_the_word() -> list[str]:
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in docstrings:
                continue
            if says_reconciliation(node.value):
                found.append(f"{path.relative_to(ROOT.parent)}:{node.lineno}: {node.value[:60]!r}")
    return found


def test_no_string_the_app_writes_says_reconciliation():
    assert _literals_with_the_word() == []


@pytest.mark.parametrize(
    ("text", "caught"),
    [
        ("Complete reconciliation?", True),
        ("Not moved: X is reconciled", True),
        ("Delete Reconciliations", True),
        ("RECONCILIATIONS", True),
        ("3 unreconciled lines", True),
        ("reconciled", True),
        ("Reconciliations", True),
        ("RECONCILIATION_NOT_DRAFT", False),
        ("Press u: RECONCILIATION_NOT_DRAFT", False),
        ("unreconciled", False),
        ("statements", False),
        ("Complete statement?", False),
    ],
)
def test_the_scan_catches_the_word_and_spares_only_the_named_exemptions(text, caught):
    assert says_reconciliation(text) is caught
