"""Guard: a toast shows the engine's words as text, never as styling.

Textual reads a toast's message as content markup unless the call says
`markup=False`, so a `[like this]` in the engine's words would vanish, read as
a style, and a stray `[/]` would raise. Every `notify` in the app's code is
therefore one of two things:

* a **fixed sentence**: its message is a string literal, or a choice between
  two (`"Saved." if done else "Not saved."`), written in the app and read by
  whoever writes it; or
* a call that **says how its message reads**, passing `markup=` itself:
  `toast` in expense/tui/widgets/refusal.py passes `markup=False`, and the one
  toast whose colours are content markup on purpose (the ledger's bulk edit
  note, its words escaped inside it) passes `markup=True`.

Anything else — a variable, `format_error(...)`, an f-string, a constant
from elsewhere — fails here and goes through `toast`. So does `notify`
handed on uncalled (`call_while_attached(self, self.notify, ...)`), since the
call it makes cannot be read here.

What this cannot catch:

* a `markup=True` call whose words are not escaped: the guard trusts the
  caller who says it;
* `notify` reached under another name (`getattr(self, "notify")`), or a
  `Notification` built by hand;
* engine words drawn anywhere but a toast — a `Static("…")`, `.update("…")`,
  `Label`, an `Option` prompt, `Content.from_markup`, `Text.from_markup`. Those
  are held by the per-screen tests in test_tui_engine_words.py, and by the
  rule in docs/tui.md "When the engine says no" that they draw `Text`.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "expense"


def _fixed(node: ast.expr | None) -> bool:
    """A string literal, or a choice between fixed sentences."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.IfExp):
        return _fixed(node.body) and _fixed(node.orelse)
    return False


def _message(call: ast.Call) -> ast.expr | None:
    if call.args:
        return call.args[0]
    return next((k.value for k in call.keywords if k.arg == "message"), None)


def markup_toasts(source: str, name: str) -> list[str]:
    """Each `notify` in `source` that may read words as markup, as
    `name:line: code`."""
    tree = ast.parse(source)
    called: set[int] = set()
    found: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "notify"
        ):
            called.add(id(node.func))
            says = any(k.arg == "markup" for k in node.keywords)
            if not says and not _fixed(_message(node)):
                found.append(f"{name}:{node.lineno}: {ast.unparse(node)}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "notify" and id(node) not in called:
            found.append(f"{name}:{node.lineno}: {ast.unparse(node)} handed on uncalled")
    return sorted(found)


def test_the_reader_tells_a_fixed_sentence_from_words_it_did_not_write():
    """The guard is only as good as this reader: each spelling lands on the
    side it belongs to."""
    safe = """
self.notify("Saved.")
self.notify("Saved." if left else "Not saved.", severity="error")
self.app.notify(message="Connected.")
toast(self, format_error(exc), title="Failed", severity="error")
host.notify(message, markup=False, **options)
self.notify(note, title=head, markup=True)
call_while_attached(self, toast, self, format_error(exc))
"""
    assert markup_toasts(safe, "safe.py") == []
    unsafe = """
self.notify(format_error(exc), title="Failed", severity="error")
self.notify(message)
self.app.notify(f"Not saved:\\n{message}")
self.notify(DATE_UNREADABLE, severity="error")
self.notify("Saved." if left else message)
self._host.notify(message=words)
call_while_attached(self, self.notify, format_error(exc), severity="error")
"""
    found = markup_toasts(unsafe, "unsafe.py")
    assert [line.split(":")[1] for line in found] == ["2", "3", "4", "5", "6", "7", "8"]
    assert found[-1].endswith("handed on uncalled")


def test_no_toast_reads_words_it_did_not_write_as_markup():
    found = [
        problem
        for path in sorted(PACKAGE.rglob("*.py"))
        for problem in markup_toasts(
            path.read_text(encoding="utf-8"), str(path.relative_to(PACKAGE.parent))
        )
    ]
    assert found == [], (
        "These toasts read their message as content markup, so a `[` in words the "
        "app did not write would vanish or raise. Send them through `toast` "
        "(expense/tui/widgets/refusal.py):\n" + "\n".join(found)
    )
