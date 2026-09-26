"""Step 9 gate — regression armor for the CLI surface.

Walks the Typer command tree and asserts:
  - every leaf command has a non-empty docstring
  - every docstring contains an `Example:` block (gate criterion 1)
  - every read command exposes a --json flag (gate criterion 2)
  - every destructive command (delete/archive/revert/clear) exposes --yes
    (the confirm-destructive convention)
  - every flag used in an `Example:` line exists on that command, and
    int-typed flags get int-looking values (copy-paste safety)

If a future PR adds a new command or wrapper (quick-add parser, etc.)
and forgets these conventions, this test will fail loudly.
"""

import inspect
import re
import shlex

import click
import pytest
from typer.main import get_command
from typer.testing import CliRunner

from expense.__main__ import app

READ_COMMAND_LEAVES: set[tuple[str, ...]] = {
    ("dashboard",),
    ("ping",),
    ("whoami",),
    ("config", "get"),
    ("auth", "bootstrap"),
    ("auth", "me"),
    ("auth", "profile"),
    ("auth", "settings"),
    ("reports", "monthly"),
    ("rates", "get"),
}


def _walk(typer_app, prefix=()):
    for cmd in typer_app.registered_commands:
        name = cmd.name or cmd.callback.__name__.rstrip("_")
        yield (*prefix, name), cmd.callback
    for grp in typer_app.registered_groups:
        yield from _walk(grp.typer_instance, (*prefix, grp.name))


_LEAVES = list(_walk(app))
_LEAF_IDS = [" ".join(path) for path, _ in _LEAVES]


def _is_read(path: tuple[str, ...]) -> bool:
    if path in READ_COMMAND_LEAVES:
        return True
    return path[-1] in {"list", "get"}


def test_typer_tree_walk_finds_expected_command_count():
    # A floor, not a pin: it catches a walker that finds nothing, not a
    # deliberate deletion. 49 on 2026-09-25, after the five `restore` commands
    # and `reconcile get` left with the engine routes they called.
    assert len(_LEAVES) >= 45, (
        f"Expected at least 45 leaf commands across the CLI; "
        f"walker found {len(_LEAVES)} — Typer introspection may be broken."
    )


@pytest.mark.parametrize(("path", "callback"), _LEAVES, ids=_LEAF_IDS)
def test_command_has_example_in_docstring(path, callback):
    cmd_name = " ".join(path)
    doc = inspect.getdoc(callback)
    assert doc, f"`expense {cmd_name}` has no docstring (gate criterion 1)"
    assert "Example:" in doc, (
        f"`expense {cmd_name}` docstring is missing an `Example:` block (Step 9 gate criterion 1)"
    )


_READ_LEAVES = [(path, cb) for path, cb in _LEAVES if _is_read(path)]
_READ_LEAF_IDS = [" ".join(path) for path, _ in _READ_LEAVES]


@pytest.mark.parametrize(("path", "callback"), _READ_LEAVES, ids=_READ_LEAF_IDS)
def test_read_command_has_json_flag(path, callback):
    sig = inspect.signature(callback)
    assert "json_output" in sig.parameters, (
        f"`expense {' '.join(path)}` is a read command but has no --json flag "
        f"(Step 9 gate criterion 2)"
    )


# --- Confirm-destructive convention ------------------------------------------
# CLAUDE.md non-negotiable: deletes, reverts, and clears prompt for confirmation
# unless --yes is passed. Matched by leaf name — a destructive command under a
# new name (e.g. `remove`) must be added to the set. `archive`/`unarchive`
# (accounts-only since the 2026-08-06 schema slimming) are deliberately
# prompt-free — reversible toggles, not destruction (archive
# reclassified 2026-07-11; see decisions.md).

_DESTRUCTIVE_NAMES = {"delete", "revert", "clear"}
_DESTRUCTIVE_LEAVES = [(path, cb) for path, cb in _LEAVES if path[-1] in _DESTRUCTIVE_NAMES]
_DESTRUCTIVE_LEAF_IDS = [" ".join(path) for path, _ in _DESTRUCTIVE_LEAVES]


def test_destructive_walker_finds_known_commands():
    # Pin the count: a drop means a destructive command was renamed out of the
    # name set above and now evades the --yes guard — extend the set instead.
    # 7 since 2026-09-12: `inbox delete` left with the inbox command group.
    assert len(_DESTRUCTIVE_LEAVES) == 7, sorted(_DESTRUCTIVE_LEAF_IDS)


def test_no_command_restores_or_lists_deleted_rows():
    """Deleted is deleted (engine, 2026-09-23): `POST /{resource}/{id}/restore`
    is a 404 and `?include_deleted=` a 422 on every list. Undeleting is operator
    SQL on the engine host, so no client command may offer either."""
    restores = [" ".join(path) for path, _ in _LEAVES if path[-1] == "restore"]
    assert not restores, restores
    flagged = [
        " ".join(path)
        for path, cb in _LEAVES
        if "include_deleted" in inspect.signature(cb).parameters
    ]
    assert not flagged, flagged


def test_no_command_takes_offset():
    """No engine list pages by offset since 2026-09-23 (`?offset=` is a 422
    everywhere), so an `--offset` flag could only ever produce that error."""
    flagged = [
        " ".join(path)
        for path, cb in _LEAVES
        for name, param in inspect.signature(cb).parameters.items()
        if name == "offset" or "--offset" in (getattr(param.default, "param_decls", None) or ())
    ]
    assert not flagged, flagged


# Lists the engine returns whole and refuses to page (2026-09-23, `?limit=` /
# `?offset=` are a 422). A paging flag here could only ever produce that error.
_WHOLE_LISTS = [
    ("accounts", "list"),
    ("categories", "list"),
    ("hashtags", "list"),
    ("reconcile", "list"),
]


def test_whole_lists_take_no_paging_flags():
    leaves = dict(_LEAVES)
    assert set(_WHOLE_LISTS) <= set(leaves), "a whole-list command was renamed"
    flagged = [
        " ".join(path)
        for path in _WHOLE_LISTS
        if {"limit", "offset"} & set(inspect.signature(leaves[path]).parameters)
    ]
    assert not flagged, flagged


@pytest.mark.parametrize(("path", "callback"), _DESTRUCTIVE_LEAVES, ids=_DESTRUCTIVE_LEAF_IDS)
def test_destructive_command_requires_yes(path, callback):
    sig = inspect.signature(callback)
    assert "yes" in sig.parameters, (
        f"`expense {' '.join(path)}` is destructive but exposes no --yes flag "
        f"(confirm-destructive convention)"
    )


# --- Example-line copy-paste safety -----------------------------------------
# Docstring examples must use flags the command actually declares. Flags like
# --account-id map to params named `account`, so validation goes through
# click's declared option strings, not Python parameter names.

_CLICK_ROOT = get_command(app)


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


def test_root_help_renders():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ("config", "auth", "accounts", "dashboard"):
        assert group in result.stdout, f"`expense --help` is missing `{group}`"


# ---------------------------------------------------------------------------
# Gate criterion 3 — the error-shape half of the testing convention
# ---------------------------------------------------------------------------

#: Leaves that never reach the engine, so "an error-shape test" is not a thing
#: they can have. Each is checked below to still BE a leaf, so this list cannot
#: quietly outlive the commands it excuses (the same rot
#: tests/unit/test_suite_hygiene.py guards two other allowlists against).
NO_ENGINE_CALL: set[tuple[str, ...]] = {
    ("version",),  # prints __version__
    ("world",),  # launches the TUI; its writes are tested through the TUI suite
    ("config", "set"),  # ~/.expense-config only
    ("config", "get"),
    ("config", "clear"),
}


def test_the_no_engine_call_list_still_names_real_commands():
    """An exemption for a command that no longer exists excuses nothing, and
    hides that it stopped existing."""
    stale = sorted(NO_ENGINE_CALL - {path for path, _ in _LEAVES})
    assert not stale, f"NO_ENGINE_CALL names commands that are gone: {stale}"


def test_every_command_has_an_error_shape_test():
    """CLAUDE.md "Testing conventions": *every* command lands with a happy-path
    AND an error-shape test. The happy path is self-enforcing — a command with
    no test at all is a command nobody wrote a test for, and that gets noticed.
    The error path is the half that silently never arrives: the command works,
    the tests are green, and the first person to meet its 409 is the user.

    Twenty-odd commands were missing one when this landed (2026-09-19), in a
    clear pattern — `list` and `create`, on every resource. Not a coincidence:
    those are the two verbs whose happy path is the most fun to write.

    Reads `conftest.ERROR_TESTED`, which records real invocations rather than
    scanning the source, so a parametrized test counts exactly as much as a
    hand-written one.
    """
    from tests.unit import conftest

    if conftest.PARTIAL_RUN:
        pytest.skip("a filtered run cannot see whether the whole suite covers a command")

    expected = {path for path, _ in _LEAVES} - NO_ENGINE_CALL
    missing = sorted(" ".join(path) for path in expected - conftest.ERROR_TESTED)
    assert not missing, (
        "these commands have no test that drives them to a non-zero exit — add "
        "one asserting the engine's envelope reaches the user (or, if the "
        f"command truly cannot fail, list it in NO_ENGINE_CALL with a reason): {missing}"
    )
