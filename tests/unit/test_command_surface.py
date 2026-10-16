"""Guards for the typed surface: `expense` alone opens the app, and `expense import
sheet` is the one command (docs/decisions.md "The TUI is the only surface").

Walks the real Typer tree and asserts:
  - the tree is exactly `import sheet`, and `expense --help` names nothing else
  - a bare `expense` launches the app; `expense world` and the deleted command
    groups are unknown commands
  - every leaf command has a docstring with an `Example:` block, and every flag
    an example uses exists on that command (copy-paste safety)
  - every leaf command has a test driving it to a non-zero exit
"""

import inspect
import re
import shlex

import click
import pytest
from typer.main import get_command
from typer.testing import CliRunner

from expense import __main__ as entry
from expense.__main__ import app
from tests.unit.helpers import strip_panel


def _walk(typer_app, prefix=()):
    for cmd in typer_app.registered_commands:
        name = cmd.name or cmd.callback.__name__.rstrip("_")
        yield (*prefix, name), cmd.callback
    for grp in typer_app.registered_groups:
        yield from _walk(grp.typer_instance, (*prefix, grp.name))


_LEAVES = list(_walk(app))
_LEAF_IDS = [" ".join(path) for path, _ in _LEAVES]


# --- the surface itself ------------------------------------------------------


def test_the_only_typed_command_is_import_sheet():
    assert [path for path, _ in _LEAVES] == [("import", "sheet")]


_GONE = (
    "world",
    "accounts",
    "categories",
    "hashtags",
    "transactions",
    "reconcile",
    "reports",
    "dashboard",
    "rates",
    "activity",
    "auth",
    "whoami",
    "config",
    "ping",
    "log",
    "version",
    "bank",
)


def test_root_help_lists_only_import_sheet():
    commands = _CLICK_ROOT.commands
    assert list(commands) == ["import"]
    assert list(commands["import"].commands) == ["sheet"]

    root = CliRunner().invoke(app, ["--help"])
    sub = CliRunner().invoke(app, ["import", "--help"])
    assert root.exit_code == 0 and sub.exit_code == 0, root.output + sub.output
    root_text, sub_text = strip_panel(root.output), strip_panel(sub.output)
    root_listed, sub_listed = root_text.split("Commands ", 1)[1], sub_text.split("Commands ", 1)[1]
    assert root_listed == "import Bring rows in from a spreadsheet.", root_text
    assert sub_listed.split()[0] == "sheet", sub_text
    for gone in _GONE:
        assert not re.search(rf"\b{gone}\b", root_text), gone


def test_bare_expense_opens_the_app(monkeypatch):
    launched = []
    monkeypatch.setattr(entry, "open_app", lambda ctx: launched.append(ctx.obj.verbose))
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 0, result.output
    assert launched == [False]


def test_bare_expense_verbose_opens_the_app_verbose(monkeypatch):
    launched = []
    monkeypatch.setattr(entry, "open_app", lambda ctx: launched.append(ctx.obj.verbose))
    assert CliRunner().invoke(app, ["--verbose"]).exit_code == 0
    assert launched == [True]


def test_import_sheet_does_not_open_the_app(monkeypatch):
    launched = []
    monkeypatch.setattr(entry, "open_app", lambda ctx: launched.append(ctx))
    CliRunner().invoke(app, ["import", "sheet", "--help"])
    assert launched == []


@pytest.mark.parametrize(
    "argv",
    [
        ["world"],
        ["accounts", "list"],
        ["categories", "list"],
        ["hashtags", "list"],
        ["transactions", "list"],
        ["transactions", "batch"],
        ["reconcile", "list"],
        ["reports", "monthly"],
        ["dashboard"],
        ["rates", "list"],
        ["activity", "list"],
        ["auth", "me"],
        ["whoami"],
        ["config", "set"],
        ["ping"],
        ["log"],
        ["version"],
        ["import", "bank"],
    ],
    ids=lambda argv: " ".join(argv),
)
def test_deleted_commands_are_unknown(argv, monkeypatch):
    launched = []
    monkeypatch.setattr(entry, "open_app", lambda ctx: launched.append(ctx))
    result = CliRunner().invoke(app, argv)
    assert result.exit_code == 2, result.output
    assert "No such command" in result.output
    assert launched == []


# --- docstrings and their examples -------------------------------------------


@pytest.mark.parametrize(("path", "callback"), _LEAVES, ids=_LEAF_IDS)
def test_command_has_example_in_docstring(path, callback):
    cmd_name = " ".join(path)
    doc = inspect.getdoc(callback)
    assert doc, f"`expense {cmd_name}` has no docstring"
    assert "Example:" in doc, f"`expense {cmd_name}` docstring is missing an `Example:` block"


# Docstring examples must use flags the command actually declares, read from
# click's declared option strings rather than Python parameter names.

_CLICK_ROOT = get_command(app)
assert isinstance(_CLICK_ROOT, click.Group)


def _click_leaves(cmd, prefix=()):
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            yield from _click_leaves(sub, (*prefix, name))
    else:
        yield prefix, cmd


_CLICK_LEAVES = list(_click_leaves(_CLICK_ROOT))
_CLICK_LEAF_IDS = [" ".join(path) for path, _ in _CLICK_LEAVES]

# Examples may legitimately show root flags (e.g. --verbose).
_ROOT_FLAGS = {
    opt
    for param in _CLICK_ROOT.params
    for opt in (*param.opts, *param.secondary_opts)
    if opt.startswith("--")
}

_FLAG_RE = re.compile(r"--[a-zA-Z0-9][a-zA-Z0-9-]*")


def _example_blocks(doc: str):
    """Yield each `Example:` line joined with its indented continuation lines."""
    lines = doc.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("Example:"):
            block = [lines[i].strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and lines[i][:1].isspace():
                block.append(lines[i].strip())
                i += 1
            yield " ".join(block)
        else:
            i += 1


def _example_tokens(block: str) -> list[str]:
    try:
        tokens = shlex.split(block)
    except ValueError:  # unbalanced quote in prose — fall back to whitespace split
        tokens = block.split()
    flat: list[str] = []
    for tok in tokens:
        if tok.startswith("--") and "=" in tok:
            flag, _, value = tok.partition("=")
            flat.extend([flag, value])
        else:
            flat.append(tok)
    return flat


@pytest.mark.parametrize(("path", "command"), _CLICK_LEAVES, ids=_CLICK_LEAF_IDS)
def test_docstring_example_flags_exist(path, command):
    cmd_name = " ".join(path)
    allowed = set(_ROOT_FLAGS)
    int_flags = set()
    for param in command.params:
        for opt in (*param.opts, *param.secondary_opts):
            if opt.startswith("--"):
                allowed.add(opt)
                if isinstance(param.type, click.types.IntParamType):
                    int_flags.add(opt)

    for block in _example_blocks(command.help or ""):
        for flag in _FLAG_RE.findall(block):
            assert flag in allowed, (
                f"`expense {cmd_name}` docstring example uses {flag}, "
                f"which is not a flag on that command: {block!r}"
            )
        tokens = _example_tokens(block)
        for pos, tok in enumerate(tokens):
            if tok not in int_flags:
                continue
            value = tokens[pos + 1] if pos + 1 < len(tokens) else ""
            if value.startswith("<") and value.endswith(">"):
                continue  # placeholder like <id>
            assert re.fullmatch(r"-?\d+", value), (
                f"`expense {cmd_name}` docstring example gives int-typed {tok} "
                f"the value {value!r}: {block!r}"
            )


# --- the error-shape half of the testing convention ---------------------------


def test_every_command_has_an_error_shape_test():
    """Every command lands with a happy-path AND an error-shape test. The error
    path is the half that silently never arrives: the command works, the tests
    are green, and the first person to meet its refusal is the user.

    Reads `conftest.ERROR_TESTED`, which records real invocations rather than
    scanning the source, so a parametrized test counts exactly as much as a
    hand-written one. Under pytest-xdist a worker holds only its share of the
    registry, so this test passes there and the controller gives the verdict at
    session end, failing this nodeid (`conftest.ControllerVerdict`).
    """
    from tests.unit import conftest

    if conftest.PARTIAL_RUN:
        pytest.skip("a filtered run cannot see whether the whole suite covers a command")
    if conftest.ON_XDIST_WORKER:
        return  # decided on the controller once every worker has reported

    missing = conftest.missing_error_tests(conftest.ERROR_TESTED)
    assert not missing, conftest.missing_message(missing)


# --- the guard's own machinery ------------------------------------------------


def test_guard_knows_the_command_tree():
    from tests.unit import conftest

    assert conftest.missing_error_tests(set()) == _LEAF_IDS
    assert conftest.missing_error_tests({path for path, _ in _LEAVES}) == []


class _Report:
    def __init__(self, nodeid, when="call"):
        self.nodeid, self.when, self.location = nodeid, when, ("x.py", 1, nodeid)


_GUARD_ID = "tests/unit/test_command_surface.py::test_every_command_has_an_error_shape_test"


def _verdict(*worker_records, guard_seen=True):
    from tests.unit import conftest

    verdict = conftest.ControllerVerdict()
    for record in worker_records:
        verdict.add_worker({"error_tested": record}, None)
    verdict.see_report(_Report("tests/unit/test_x.py::test_other"))
    if guard_seen:
        verdict.see_report(_Report(_GUARD_ID))
    return verdict


def test_controller_fails_the_guard_when_no_worker_drove_import_sheet_to_an_error():
    failure = _verdict([], [["unrelated"]]).failure(partial=False)
    assert failure is not None
    assert (failure.nodeid, failure.outcome, failure.when) == (_GUARD_ID, "failed", "teardown")
    assert "import sheet" in str(failure.longrepr)


def test_controller_passes_when_any_one_worker_covered_the_command():
    assert _verdict([], [["import", "sheet"]]).failure(partial=False) is None


def test_controller_concludes_nothing_it_cannot_see():
    assert _verdict([]).failure(partial=True) is None  # filtered run
    assert _verdict([], guard_seen=False).failure(partial=False) is None  # guard not run
    assert _verdict().failure(partial=False) is None  # no workers: in-process run

    crashed = _verdict([])
    crashed.add_worker(None, "worker crashed")
    assert crashed.failure(partial=False) is None  # the crash already fails the run


@pytest.mark.parametrize(
    ("argv", "partial"),
    [
        (["tests/unit"], False),
        (["tests"], False),
        (["."], False),
        (["tests/unit/"], False),
        (["tests/unit/test_command_surface.py"], True),
        (["tests/unit/test_command_surface.py::test_x"], True),
        (["tests/contract"], True),
        (["tests/unit", "-k", "sheet"], True),
        (["tests/unit", "-m", "slow"], True),
        (["tests/unit", "--lf"], True),
        (["tests/unit", "--last-failed"], True),
        (["tests/unit", "--sw"], True),
        (["tests/unit", "--sw-skip"], True),
        (["tests/unit", "--deselect", "tests/unit/test_cmd_import.py"], True),
        (["tests/unit", "--ignore", "tests/unit/test_cmd_import.py"], True),
        (["tests/unit", "--ignore-glob", "*import*"], True),
        (["tests/unit", "--ff"], False),
    ],
    ids=lambda v: " ".join(v) if isinstance(v, list) else None,
)
def test_partial_run_detection(argv, partial, monkeypatch):
    """Parse real argv with pytest's own parser, so an option renamed or stored
    under another attribute shows up here rather than as a guard that never skips."""
    from _pytest.config import _prepareconfig

    from tests.unit import conftest

    repo = conftest._UNIT_DIR.parent.parent
    monkeypatch.chdir(repo)
    config = _prepareconfig([*argv, "--noconftest"])
    try:
        assert conftest.is_partial_run(config.option, config.args, repo) is partial
    finally:
        config._ensure_unconfigure()


_XDIST_SUITE_CALL = """
from typer.testing import CliRunner

from expense.__main__ import app


def test_import_sheet_refuses_a_missing_file():
    assert CliRunner().invoke(app, ["import", "sheet", "no-such.xlsx"]).exit_code != 0
"""


@pytest.mark.parametrize("covered", [True, False], ids=["covered", "uncovered"])
def test_guard_verdict_under_xdist(covered, tmp_path):
    """A tiny copy of tests/unit run with `-n 2`: the controller merges the
    workers' records, and fails the guard's nodeid when no worker covered the
    command. Skips until pytest-xdist is importable."""
    pytest.importorskip("xdist")
    import os
    import shutil
    import subprocess
    import sys

    from tests.unit import conftest

    unit = tmp_path / "tests" / "unit"
    unit.mkdir(parents=True)
    (tmp_path / "tests" / "__init__.py").write_text("")
    (unit / "__init__.py").write_text("")
    for name in ("conftest.py", "helpers.py"):
        shutil.copy(conftest._UNIT_DIR / name, unit / name)
    guard = inspect.getsource(test_every_command_has_an_error_shape_test)
    (unit / "test_guard.py").write_text("import pytest\n\n\n" + guard)
    if covered:
        (unit / "test_sheet.py").write_text(_XDIST_SUITE_CALL)
    for i in range(4):  # filler, so the run is spread over both workers
        (unit / f"test_filler_{i}.py").write_text("def test_ok():\n    pass\n")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit", "-n", "2", "-p", "no:cacheprovider"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = result.stdout + result.stderr
    if covered:
        assert result.returncode == 0, out
    else:
        assert result.returncode == 1, out
        assert "ERROR tests/unit/test_guard.py::test_every_command_has_an_error_shape_test" in out
        assert "import sheet" in out
