"""Shared fixtures for tests/unit. Non-fixture helpers: tests/unit/helpers.py.

A file-local fixture with the same name shadows these, so files can migrate
one at a time by deleting their local copy — never leave a diverged local
fixture named `configured` behind.
"""

import socket

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

#: Command paths some test drove to a non-zero exit — ("import", "sheet"), …
ERROR_TESTED: set[tuple[str, ...]] = set()

#: True when this run cannot see the whole suite (-k, -m, --lf, or a nodeid),
#: in which case the guard has nothing to conclude and skips.
PARTIAL_RUN = False

_LEAF_PATHS: frozenset[tuple[str, ...]] = frozenset()


def _leaf_paths() -> frozenset[tuple[str, ...]]:
    """Every leaf command path in the app `expense` actually runs."""
    from expense.__main__ import app

    def walk(typer_app, prefix=()):
        for cmd in typer_app.registered_commands:
            yield (*prefix, cmd.name or cmd.callback.__name__.rstrip("_"))
        for grp in typer_app.registered_groups:
            yield from walk(grp.typer_instance, (*prefix, grp.name))

    return frozenset(walk(app))


def pytest_configure(config):
    """Wrap CliRunner.invoke once, for the whole session."""
    global _LEAF_PATHS, PARTIAL_RUN
    from typer.testing import CliRunner

    _LEAF_PATHS = _leaf_paths()
    PARTIAL_RUN = bool(
        getattr(config.option, "keyword", "")
        or getattr(config.option, "markexpr", "")
        or getattr(config.option, "last_failed", False)
        or any("::" in arg for arg in config.args)
    )

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
    last = [i for i in items if i.name == "test_every_command_has_an_error_shape_test"]
    if last:
        items[:] = [i for i in items if i not in last] + last
