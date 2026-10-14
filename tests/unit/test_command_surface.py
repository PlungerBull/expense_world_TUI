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
    hand-written one.
    """
    from tests.unit import conftest

    if conftest.PARTIAL_RUN:
        pytest.skip("a filtered run cannot see whether the whole suite covers a command")

    expected = {path for path, _ in _LEAVES}
    missing = sorted(" ".join(path) for path in expected - conftest.ERROR_TESTED)
    assert not missing, (
        "these commands have no test that drives them to a non-zero exit — add "
        f"one asserting the engine's envelope reaches the user: {missing}"
    )
