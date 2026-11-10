"""Guard: the app's word is "transaction", never "purchase" (CLAUDE.md "No new terms")."""

import re
from pathlib import Path

EXPENSE_DIR = Path(__file__).resolve().parents[2] / "expense"
_PURCHASE = re.compile(r"purchase", re.IGNORECASE)


def _text_of(path: Path) -> str:
    try:
        return path.read_text()
    except UnicodeDecodeError:
        return ""


def _purchase_hits(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root.parent)}:{lineno}: {line.strip()}"
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix != ".pyc")
        for lineno, line in enumerate(_text_of(path).splitlines(), start=1)
        if _PURCHASE.search(line)
    ]


def test_the_app_never_says_purchase():
    hits = _purchase_hits(EXPENSE_DIR)
    assert not hits, f"the app says transaction and never purchase, found in: {hits}"


def test_purchase_guard_trips(tmp_path):
    pkg = tmp_path / "expense"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n# A Purchase here\n")
    (pkg / "b.tcss").write_text("/* PURCHASE */\n")
    (pkg / "c.py").write_text("y = 2\n")
    (pkg / "d.md").write_text("purchase\n")
    (pkg / "e.bin").write_bytes(b"\xff\xfepurchase")
    hits = [h.split(": ")[0] for h in _purchase_hits(pkg)]
    assert hits == ["expense/a.py:2", "expense/b.tcss:1", "expense/d.md:1"]
