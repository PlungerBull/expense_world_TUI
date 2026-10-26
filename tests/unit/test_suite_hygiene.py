"""Guard: the TUI tests must wait on a condition, never on the clock.

A timed `pilot.pause(0.05)` is a guess at how long the app takes, and it is
wrong in both directions — too short on a loaded CI box (a red build with no
bug behind it, which teaches everyone to stop trusting red), too long on a
normal run. `wait_for(pilot, predicate)` in [helpers.py](helpers.py) polls
every 20ms and continues the instant the thing is there, failing loudly at the
wait site after 2s; a bare `pilot.pause()` drains the message pump once, which
is what a *non-event* assertion needs (an inert keypress, a confirm that must
not fire) since no predicate can express "wait until nothing happens".

This test keeps a timed pause from landing silently.

`time.sleep` is deliberately NOT guarded: its uses are fake engine clients
simulating latency, not test waits.
"""

import ast
import re
from pathlib import Path

from tests.unit.helpers import load_drift_script

TESTS_DIR = Path(__file__).resolve().parent
SELF = Path(__file__).name  # this file quotes the very pattern it forbids

_TIMED_PAUSE = re.compile(r"pilot\.pause\(\s*[0-9]")

# The one pause that must stay on the clock: its fake fetch does a real
# time.sleep(0.15), and the test's whole point is to outlast it and prove the
# superseded worker never paints. Keyed on the full line so that editing it
# re-opens the question here rather than silently widening the exemption.
JUSTIFIED = {
    "await pilot.pause(0.25)  # window for the cancelled worker to (not) paint",
}


def test_no_timed_pauses_in_tests():
    offenders = [
        f"{path.name}:{lineno}: {stripped}"
        for path in sorted(TESTS_DIR.glob("*.py"))
        if path.name != SELF
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if _TIMED_PAUSE.search(line) and (stripped := line.strip()) not in JUSTIFIED
    ]
    assert not offenders, (
        "timed pauses are flaky under load — wait on the condition with "
        "wait_for(pilot, predicate), or use a bare pilot.pause() when the "
        f"assertion is a non-event: {offenders}"
    )


def test_justified_exemption_still_exists():
    """The allowlist must not outlive the line it exempts (dead-exemption rot)."""
    corpus = "\n".join(
        path.read_text() for path in sorted(TESTS_DIR.glob("*.py")) if path.name != SELF
    )
    stale = [line for line in JUSTIFIED if line not in corpus]
    assert not stale, f"JUSTIFIED exempts lines that no longer exist: {stale}"


# ---------------------------------------------------------------------------
# Guard: the fixture-drift exemptions must not outlive the keys they exempt
# ---------------------------------------------------------------------------


def test_known_local_exemptions_still_match():
    """Every KNOWN_LOCAL key must still be a key some fixture writes.

    Same rot as `test_justified_exemption_still_exists` above, one list over:
    the drift script can only report keys it does not know, so a stale entry is
    invisible — it goes on quietly excusing whatever key next takes the name.

    ENVELOPE_KEYS is deliberately NOT guarded: it spells out the engine's
    envelope contract (pagination, the error shape, the bootstrap wrapper), so an
    entry no fixture happens to use today is documentation, not rot.
    """
    drift = load_drift_script()
    in_use = set()
    for path in sorted(TESTS_DIR.glob("*.py")):
        source = path.read_text()
        prose, comment_at = drift._prose_spans(source)  # the scanner's own rule
        for lineno, line in enumerate(source.splitlines(), start=1):
            if lineno in prose:
                continue
            code = line[: comment_at[lineno]] if lineno in comment_at else line
            in_use |= set(drift.KEY_RE.findall(code))
    stale = sorted(key for key in drift.KNOWN_LOCAL if key not in in_use)
    assert not stale, (
        "KNOWN_LOCAL in scripts/check_fixture_drift.py exempts keys no fixture "
        f"writes any more — delete them: {stale}"
    )


# ---------------------------------------------------------------------------
# Guard: rendering must not depend on the environment the suite runs in
# ---------------------------------------------------------------------------

_BARE_CONSOLE = re.compile(r"\bConsole\(")


def test_no_bare_rich_console_in_tests():
    """Rich sniffs the environment for `is_terminal` unless told not to.

    A `Console(file=StringIO(), width=N)` with no `force_terminal` renders plain
    text here and ANSI spans on a machine that exports FORCE_COLOR or a CI that
    looks like a TTY — the same assertion passing or failing on where it runs.
    `helpers.render_text` pins `force_terminal` explicitly in both directions;
    `ansi=True` is how a test asks for the codes.

    A guard test, not a line of prose telling everyone not to set FORCE_COLOR.
    """
    offenders = [
        f"{path.name}:{lineno}: {line.strip()}"
        for path in sorted(TESTS_DIR.glob("*.py"))
        if path.name not in {SELF, "helpers.py"}
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if _BARE_CONSOLE.search(line)
    ]
    assert not offenders, (
        "build the console through helpers.render_text(renderable, width=..., "
        f"ansi=...) so terminal detection cannot decide the assertion: {offenders}"
    )


# ---------------------------------------------------------------------------
# Guard: one definition of how a TUI test boots the app
# ---------------------------------------------------------------------------

_OWN_HARNESS = re.compile(r"\basyncio\.run\(|\.run_test\(")


def test_tui_tests_boot_through_the_shared_harness():
    """`helpers.run_app(body, size=...)` is the only place an ExpenseApp starts.

    With one harness, anything the whole suite needs from it — a default
    viewport, a fixture, an exception wrapper — is applied once, not per test.

    `asyncio.gather` and friends are untouched; this is about who starts the app.
    """
    offenders = [
        f"{path.name}:{lineno}: {line.strip()}"
        for path in sorted(TESTS_DIR.glob("*.py"))
        if path.name not in {SELF, "helpers.py"}
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if _OWN_HARNESS.search(line)
    ]
    assert not offenders, (
        "start the app with helpers.run_app(scenario, size=...) rather than a "
        f"local asyncio.run/run_test pair: {offenders}"
    )


# A fake of one of the whole lists that returns a bare array. The engine answers
# `{items}` and has no route that returns an array; `items_of` reads
# a bare array as no rows, so a non-empty one fails its test. This catches the
# case that slips through: a fake returning `[]`, which reads the same as an empty
# `{items}` and would pass whatever shape the code expected.
_BARE_LIST_FAKE = re.compile(
    r"fetch_(?:accounts|categories|hashtags)\"?,\s*(?:lambda[^:]*:\s*)?\[", re.S
)


def test_whole_list_fakes_serve_the_engine_shape():
    offenders = [
        f"{path.name}: {m.group(0)!r}"
        for path in sorted(TESTS_DIR.glob("*.py"))
        if path.name != SELF
        for m in _BARE_LIST_FAKE.finditer(path.read_text())
    ]
    assert not offenders, f"serve these lists as whole([...]) from helpers.py: {offenders}"


# ---------------------------------------------------------------------------
# Guard: every fake engine refuses the read-only fields
# ---------------------------------------------------------------------------
#
# The engine sets `line_code`, `statement_line` and `statement_place` itself
# (`helpers.READ_ONLY_FIELDS`) and refuses each in every request body
# (contract: "Transactions (Ledger)", "Bank lines"). Read by AST, not by regex,
# so a class's own `post`/`put` and its bases are what is checked, wherever
# they sit in the file.

_VERBS = ("post", "put")


def _base_names(node: ast.ClassDef) -> set[str]:
    names = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _fake_client_kin(trees: list[ast.Module]) -> set[str]:
    """`FakeClient` and every class in `trees` that derives from it, at any depth."""
    kin = {"FakeClient"}
    classes = [node for tree in trees for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    grew = True
    while grew:
        grew = False
        for node in classes:
            if node.name not in kin and _base_names(node) & kin:
                kin.add(node.name)
                grew = True
    return kin


def _callee_name(call: ast.Call) -> str | None:
    callee = call.func
    return callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)


def _calls_refuse_read_only_fields(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    calls = (node for node in ast.walk(func) if isinstance(node, ast.Call))
    return any(_callee_name(call) == "refuse_read_only_fields" for call in calls)


def _unchecked_fakes(rel: str, tree: ast.Module, kin: set[str]) -> list[str]:
    """Each `post`/`put` of a class in `tree` that is neither `FakeClient` kin
    (whose `__getattribute__` checks them) nor calls `refuse_read_only_fields` itself."""
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name in kin:
            continue
        for item in node.body:
            if (
                isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
                and item.name in _VERBS
                and not _calls_refuse_read_only_fields(item)
            ):
                hits.append(f"{rel}:{item.lineno}: {node.name}.{item.name}")
    return hits


def test_every_fake_engine_refuses_read_only_fields():
    """A class with its own `post` or `put` is a fake engine: the app's writes
    reach it instead of `httpx`, so conftest's `_no_read_only_fields_in_requests` sees
    them only if it is `FakeClient` kin or calls `helpers.refuse_read_only_fields`
    (docs/tui.md "Test conventions")."""
    paths = sorted(TESTS_DIR.glob("*.py"))
    trees = {path.name: ast.parse(path.read_text()) for path in paths}
    kin = _fake_client_kin(list(trees.values()))
    hits = [hit for name, tree in trees.items() for hit in _unchecked_fakes(name, tree, kin)]
    assert not hits, (
        "these fake engines answer writes without the read-only field check: subclass "
        "helpers.FakeClient, or call helpers.refuse_read_only_fields(method, path, json_body) "
        f"first in each post/put: {hits}"
    )


def test_fake_engine_guard_trips():
    def hits(source: str) -> list[str]:
        tree = ast.parse(source)
        return _unchecked_fakes("x.py", tree, _fake_client_kin([tree]))

    for source in (
        "class C:\n    def post(self, path, json_body=None):\n        return {}\n",
        "class C:\n    def put(self, path, json_body=None):\n        return {}\n",
        "class C(Other):\n    def post(self, path, json_body=None):\n        check(json_body)\n",
        "class C:\n    def post(self, p, b=None):\n        refuse_read_only_fields('POST', p, b)\n"
        "    def put(self, p, b=None):\n        return {}\n",
    ):
        assert hits(source), source
    for source in (
        "class C(FakeClient):\n    def post(self, path, json_body=None):\n        return {}\n",
        "class L(helpers.FakeClient):\n    pass\n"
        "class C(L):\n    def put(self, path, json_body=None):\n        return {}\n",
        "class C:\n    def post(self, p, b=None):\n        refuse_read_only_fields('POST', p, b)\n",
        "class C:\n    def post(self, p, b=None):\n"
        "        h.refuse_read_only_fields('POST', p, b)\n",
        "class C:\n    def get(self, path):\n        return {}\n",
    ):
        assert not hits(source), source
