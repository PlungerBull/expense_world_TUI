"""Guard: nothing outside `expense/commands/` leans on a typed command.

`expense/commands/` holds what the typed commands alone use, so a command file
can go without touching the TUI or the imports. What both surfaces share lives
outside it: the engine reads in `expense/reads.py`, the formatters in
`expense/formatting.py`, the bank-import steps in `expense/bank_import/flow.py`.
`expense/__main__.py` registers the Typer groups and is the one module allowed
to import the package.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "expense"
COMMANDS = PACKAGE / "commands"
ENTRY_POINT = PACKAGE / "__main__.py"

#: The shared homes. They serve the TUI too, so they neither print nor parse flags.
SHARED_HOMES = (
    PACKAGE / "reads.py",
    PACKAGE / "formatting.py",
    PACKAGE / "bank_import" / "flow.py",
)


def _imported_modules(path: Path) -> set[str]:
    """Every module a file imports, as absolute dotted names.

    `from expense import commands` counts as `expense.commands`: each imported
    name is also recorded as a submodule of the module it comes from.
    """
    package = ".".join(path.relative_to(PACKAGE.parent).with_suffix("").parts[:-1])
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parent = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                base = ".".join([*parent, base] if base else parent)
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def _leans_on_commands(path: Path) -> bool:
    return any(
        name == "expense.commands" or name.startswith("expense.commands.")
        for name in _imported_modules(path)
    )


def test_the_import_reader_resolves_every_spelling(tmp_path, monkeypatch):
    """The guard below is only as good as this reader: each way of writing the
    import has to come out as `expense.commands…`."""
    monkeypatch.setattr(f"{__name__}.PACKAGE", tmp_path / "expense")
    screens = tmp_path / "expense" / "tui" / "screens"
    screens.mkdir(parents=True)
    spellings = {
        "import expense.commands.rates_cmd": True,
        "from expense.commands import rates_cmd": True,
        "from expense.commands._resource import items_of": True,
        "from expense import commands": True,
        "from ...commands import rates_cmd": True,
        "from ... import commands": True,
        "def f():\n    from expense.commands import rates_cmd": True,
        "from expense import reads": False,
        "from expense.tui.screens import commands_help": False,
        "from . import commands": False,  # expense.tui.screens.commands
    }
    for index, (source, expected) in enumerate(spellings.items()):
        path = screens / f"m{index}.py"
        path.write_text(source + "\n", encoding="utf-8")
        assert _leans_on_commands(path) is expected, source


def test_only_the_entry_point_imports_the_typed_commands():
    offenders = sorted(
        str(path.relative_to(PACKAGE.parent))
        for path in PACKAGE.rglob("*.py")
        if COMMANDS not in path.parents and path != ENTRY_POINT and _leans_on_commands(path)
    )
    assert not offenders, (
        "these modules import from expense.commands — move what they need to "
        f"expense/reads.py or expense/formatting.py instead: {offenders}"
    )


def test_the_shared_homes_are_typer_free():
    offenders = sorted(
        str(path.relative_to(PACKAGE.parent))
        for path in SHARED_HOMES
        if any(name == "typer" or name.startswith("typer.") for name in _imported_modules(path))
    )
    assert not offenders, f"a shared home imports typer: {offenders}"


def test_the_shared_homes_exist():
    missing = [str(path.relative_to(PACKAGE.parent)) for path in SHARED_HOMES if not path.exists()]
    assert not missing, f"SHARED_HOMES names files that are gone: {missing}"
