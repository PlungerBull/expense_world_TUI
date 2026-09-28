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
