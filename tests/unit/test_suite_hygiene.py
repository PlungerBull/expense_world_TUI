"""Guard: the TUI tests must wait on a condition, never on the clock.

A timed `pilot.pause(0.05)` is a guess at how long the app takes, and it is
wrong in both directions — too short on a loaded CI box (a red build with no
bug behind it, which teaches everyone to stop trusting red), too long on a
normal run. `wait_for(pilot, predicate)` in [helpers.py](helpers.py) polls
every 20ms and continues the instant the thing is there, failing loudly at the
wait site after 2s; a bare `pilot.pause()` drains the message pump once, which
is what a *non-event* assertion needs (an inert keypress, a confirm that must
not fire) since no predicate can express "wait until nothing happens".

Backlog Phase 8 swept the last 31 timed pauses out on 2026-08-18. This test is
what keeps the 32nd from landing silently — the second pass over the same
problem (commit `9d8d2c3` was the first), which is why it is armor now.

`time.sleep` is deliberately NOT guarded: its uses are fake engine clients
simulating latency, not test waits.
"""

import re
from pathlib import Path

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

_DRIFT_SCRIPT = TESTS_DIR.parent.parent / "scripts" / "check_fixture_drift.py"


def _drift_module():
    """Load scripts/check_fixture_drift.py without importing `scripts` as a package.

    The script is deliberately not a pytest file — it reads the engine's
    openapi.json, and tests/unit is hermetic. Only its constants are read here,
    which costs no network.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_check_fixture_drift", _DRIFT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_known_local_exemptions_still_match():
    """Every KNOWN_LOCAL key must still be a key some fixture writes.

    Same rot as `test_justified_exemption_still_exists` above, one list over:
    the drift script can only report keys it does not know, so a stale entry is
    invisible — it goes on quietly excusing whatever key next takes the name.
    Eight had rotted when this landed (2026-09-19), including `tag1`, whose note
    named test_tui_inbox.py, deleted with the Inbox on 2026-09-12.

    ENVELOPE_KEYS is deliberately NOT guarded: it spells out the engine's
    envelope contract (pagination, the error shape, the bootstrap wrapper), so an
    entry no fixture happens to use today is documentation, not rot.
    """
    drift = _drift_module()
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
    Nine files had their own copy of that console and six tests failed under
    `FORCE_COLOR=1` (2026-09-19). `helpers.render_text` pins `force_terminal`
    explicitly in both directions; `ansi=True` is how a test asks for the codes.

    The workaround this replaces was a line in CLAUDE.md telling everyone not to
    set FORCE_COLOR — prose, remembered by whoever had read it.
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

    144 tests wrote their own `app = ExpenseApp()` / `run_test` / `asyncio.run`
    quartet until 2026-09-19. Repetition was the smaller half of the cost: with
    144 copies, anything the whole suite needs from its harness — a default
    viewport, a fixture, an exception wrapper — has to be applied 144 times or
    not at all, so in practice it never gets applied.

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
