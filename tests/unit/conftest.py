"""Shared fixtures for tests/unit. Non-fixture helpers: tests/unit/helpers.py.

A file-local fixture with the same name shadows these, so files can migrate
one at a time by deleting their local copy — never leave a diverged local
fixture named `configured` behind.
"""

import socket
from pathlib import Path

import pytest

from expense import config as config_module
from expense import http as http_module
from tests.unit import helpers

# Loopback stays reachable so a locally-bound helper never trips the guard;
# every engine URL in the suite is a real hostname, which does not.
_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch):
    """Backstop: fail loudly if a unit test reaches the real network.

    respx intercepts at the httpcore layer, so a *mocked* request never opens a
    socket — only a request that no respx route matched (a forgotten
    ``@respx.mock``, a URL typo) falls through to a real DNS lookup / connect and
    trips this guard, so a leak is a hard failure instead of a silent
    production ping.
    """
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect

    def _guard(host: object) -> None:
        if str(host) not in _ALLOWED_HOSTS:
            raise RuntimeError(
                f"Real network blocked in unit tests: attempted to reach {host!r}. "
                "Mock it with @respx.mock (or use the fake_client fixture)."
            )

    def _fake_getaddrinfo(host, *args, **kwargs):
        _guard(host)
        return real_getaddrinfo(host, *args, **kwargs)

    def _fake_connect(self, address):
        _guard(address[0] if isinstance(address, tuple) else address)
        return real_connect(self, address)

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", _fake_connect)
    yield


@pytest.fixture(autouse=True)
def _hermetic_paths(tmp_path, monkeypatch):
    """Point the config env at a nonexistent tmp file for EVERY test.

    Every ExpenseApp launch mounts HomeScreen, whose header stat worker
    (net · spent · owed) calls ensure_loaded + fetch_dashboard on mount —
    without this, tests would read the developer's actual ~/.expense-config
    and could ping a real engine. (The worker is failure-silent, so with this
    tmp path ensure_loaded raises and it no-ops.) `configured` re-sets the env
    var afterward and still wins.
    """
    monkeypatch.setenv("EXPENSE_CONFIG", str(tmp_path / "hermetic-config"))
    yield


#: The terminal every unit test sees: 80x24, the size `shutil.get_terminal_size`
#: falls back to with no terminal, and Textual's `run_test` default.
TERMINAL_SIZE = (80, 24)


@pytest.fixture(autouse=True)
def _pinned_terminal_size(monkeypatch):
    """Give EVERY test the same terminal size, whatever window runs the suite.

    Typer prints a usage error in a Rich box as wide as the terminal. Rich
    takes that width from an exported COLUMNS first, then from the real window.
    A shell that exports a small COLUMNS, or a narrow window, wraps the box
    mid-sentence, so a plain substring assertion on `result.output` fails
    without being wrong about anything. Setting COLUMNS and LINES here
    replaces the shell's values and outranks the window, so CliRunner output
    is the same in a 40-column pane, a 250-column one and a pipe.

    TUI tests are untouched: Textual's headless driver takes its size from
    `run_test(size=...)`, never from the environment.
    """
    columns, lines = TERMINAL_SIZE
    monkeypatch.setenv("COLUMNS", str(columns))
    monkeypatch.setenv("LINES", str(lines))
    yield


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """Config saved under tmp_path — every engine call goes to the mocked engine."""
    monkeypatch.setenv("EXPENSE_CONFIG", str(tmp_path / ".expense-config"))
    config_module.save(
        config_module.Config(
            engine_url=helpers.ENGINE_URL,
            token="ewe_pat_test",
        )
    )
    yield


@pytest.fixture
def fake_client(monkeypatch):
    """A helpers.FakeClient wired into the TUI's lazy-import seams.

    Patches expense.http.ExpenseClient (factory returning this one instance)
    and expense.config.ensure_loaded (opaque stub — re-monkeypatch after
    taking this fixture if a test needs a real Config). The sheet import
    imports ExpenseClient at module top — keep respx for it.
    """
    client = helpers.FakeClient()

    monkeypatch.setattr("expense.http.ExpenseClient", lambda *a, **k: client)
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())
    return client


@pytest.fixture(autouse=True)
def _no_retry_backoff(monkeypatch):
    """Zero the write-retry waits for EVERY unit test.

    `expense.http` sleeps `_RETRY_BACKOFF_SECONDS` (1s then 2s) between the
    attempts of a same-key write retry. That is right in production and pure
    dead time here: any test that mocks a 5xx or a timeout on a write pays it
    for real, and a test that forgot to opt out of the waits would be the
    slowest in the suite for no reason.

    The replacement keeps the table's *length*, so
    `test_every_retry_has_a_backoff_to_index` still measures the real retry
    count rather than a stub's shape.
    """
    monkeypatch.setattr(
        "expense.http._RETRY_BACKOFF_SECONDS",
        tuple(0 for _ in http_module._RETRY_BACKOFF_SECONDS),
    )
    yield


# ---------------------------------------------------------------------------
# Which commands were driven down their error path (the guard in
# test_command_surface.py::test_every_command_has_an_error_shape_test reads this)
# ---------------------------------------------------------------------------
#
# Recorded at runtime, not scanned out of the source: a parametrized test builds
# its argv from a variable, which a reader of the text cannot see. Watching the
# invocations happen is immune to how the argv was spelled.
#
# Where the verdict is given depends on how the suite runs:
#   - one process (`-n0`): the guard test runs last and asserts on this
#     process's registry, which by then holds the whole suite.
#   - parallel (the default, `-n auto` from pyproject's addopts): each worker
#     sees only its share of the tests, so a worker's
#     guard test cannot conclude anything. Workers hand their registry to the
#     controller (`workeroutput`), and the controller gives the verdict at
#     session end, as a teardown error on the guard's own nodeid.
# Every xdist hook below is `optionalhook`, so pytest does not reject them as
# unknown hooks if the xdist plugin is absent; the suite itself needs xdist,
# since pytest rejects addopts' `-n` without it.

GUARD_NAME = "test_every_command_has_an_error_shape_test"

#: Command paths some test drove to a non-zero exit — ("import", "sheet"), …
ERROR_TESTED: set[tuple[str, ...]] = set()

#: True when this run cannot see the whole suite (a file or nodeid instead of the
#: suite's directory, -k, -m, --lf, --sw, --sw-skip, --deselect, --ignore,
#: --ignore-glob), in which case
#: the guard has nothing to conclude and skips.
PARTIAL_RUN = False

#: True inside a pytest-xdist worker, whose guard test leaves the verdict to the
#: controller.
ON_XDIST_WORKER = False

_LEAF_PATHS: frozenset[tuple[str, ...]] = frozenset()

_UNIT_DIR = Path(__file__).resolve().parent


def _leaf_paths() -> frozenset[tuple[str, ...]]:
    """Every leaf command path in the app `expense` actually runs."""
    from expense.__main__ import app

    def walk(typer_app, prefix=()):
        for cmd in typer_app.registered_commands:
            yield (*prefix, cmd.name or cmd.callback.__name__.rstrip("_"))
        for grp in typer_app.registered_groups:
            yield from walk(grp.typer_instance, (*prefix, grp.name))

    return frozenset(walk(app))


def missing_error_tests(recorded) -> list[str]:
    """The commands no recorded invocation drove to a non-zero exit, as typed."""
    return sorted(" ".join(path) for path in _LEAF_PATHS - set(recorded))


def missing_message(missing: list[str]) -> str:
    return (
        "these commands have no test that drives them to a non-zero exit — add "
        f"one asserting the engine's envelope reaches the user: {missing}"
    )


def is_partial_run(option, args, invocation_dir) -> bool:
    """True unless the run collects all of tests/unit, unfiltered.

    Whole means every path given is tests/unit itself or a directory above it
    (plain `pytest` passes the `testpaths` entry, `tests`). A file, a nodeid, or
    any option that drops tests leaves the registry short of the suite.
    """
    if (
        getattr(option, "keyword", "")
        or getattr(option, "markexpr", "")
        or getattr(option, "lf", False)
        or getattr(option, "stepwise", False)
        or getattr(option, "stepwise_skip", False)
        or getattr(option, "deselect", None)
        or getattr(option, "ignore", None)
        or getattr(option, "ignore_glob", None)
    ):
        return True
    for arg in args:
        if "::" in arg:
            return True
        path = (Path(invocation_dir) / arg).resolve()
        if path != _UNIT_DIR and path not in _UNIT_DIR.parents:
            return True
    return False


class ControllerVerdict:
    """The xdist controller's side of the guard: merge the workers' registries
    and, at session end, fail the guard's nodeid if a command went untested."""

    def __init__(self) -> None:
        self.recorded: set[tuple[str, ...]] = set()
        self.workers = 0
        self.lost_worker = False
        self.guard_report = None

    def add_worker(self, workeroutput, error) -> None:
        if error or "error_tested" not in (workeroutput or {}):
            self.lost_worker = True
            return
        self.workers += 1
        self.recorded.update(tuple(path) for path in workeroutput["error_tested"])

    def see_report(self, report) -> None:
        if report.when == "call" and report.nodeid.endswith("::" + GUARD_NAME):
            self.guard_report = report

    def failure(self, partial: bool):
        """A failed teardown report for the guard, or None when it passes or
        cannot be decided (no workers, guard not run, partial run, lost worker)."""
        if not self.workers or self.guard_report is None or partial or self.lost_worker:
            return None
        missing = missing_error_tests(self.recorded)
        if not missing:
            return None
        return pytest.TestReport(
            nodeid=self.guard_report.nodeid,
            location=self.guard_report.location,
            keywords={},
            outcome="failed",
            longrepr=missing_message(missing),
            when="teardown",
        )


_CONTROLLER = ControllerVerdict()


def pytest_configure(config):
    """Wrap CliRunner.invoke once, for the whole session."""
    global _LEAF_PATHS, PARTIAL_RUN, ON_XDIST_WORKER
    from typer.testing import CliRunner

    _LEAF_PATHS = _leaf_paths()
    PARTIAL_RUN = is_partial_run(config.option, config.args, config.invocation_params.dir)
    ON_XDIST_WORKER = hasattr(config, "workerinput")

    original = CliRunner.invoke

    def recording_invoke(self, cli, args=None, **kwargs):
        result = original(self, cli, args, **kwargs)
        if result.exit_code != 0 and args:
            tokens = tuple(a for a in args if isinstance(a, str) and not a.startswith("-"))
            # longest leaf path that prefixes the argv — `import sheet x.xlsx`
            # records ("import", "sheet"), never ("import", "sheet", "x.xlsx")
            for size in (3, 2, 1):
                if tokens[:size] in _LEAF_PATHS:
                    ERROR_TESTED.add(tokens[:size])
                    break
        return result

    CliRunner.invoke = recording_invoke
    config.add_cleanup(lambda: setattr(CliRunner, "invoke", original))


def pytest_collection_modifyitems(items):
    """Run the error-shape guard last.

    It reads a registry every other test writes to, so its answer depends on
    having seen them all — collected alphabetically it sits at `c`, ahead of
    most of the suite, and reports a gap that is really just the rest of the
    run. Same reason tests/contract/conftest.py gates in a hook rather than a
    fixture: a rule about the whole session belongs where the whole session is.
    """
    last = [i for i in items if i.name == GUARD_NAME]
    if last:
        items[:] = [i for i in items if i not in last] + last


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    """xdist controller: a worker finished — keep what its tests recorded."""
    _CONTROLLER.add_worker(getattr(node, "workeroutput", None), error)


def pytest_runtest_logreport(report):
    _CONTROLLER.see_report(report)


def pytest_sessionfinish(session):
    config = session.config
    if hasattr(config, "workeroutput"):  # an xdist worker: hand the registry over
        config.workeroutput["error_tested"] = [list(path) for path in sorted(ERROR_TESTED)]
        return
    failure = _CONTROLLER.failure(PARTIAL_RUN)
    if failure is not None:
        config.hook.pytest_runtest_logreport(report=failure)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
